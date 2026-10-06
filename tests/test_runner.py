import argparse

import yaml

import monitor.runner as runner
from monitor.models import Job

STATE = {"jobs": [], "fail": False}


def fake_fetch(http, board, company):
    if STATE["fail"]:
        raise RuntimeError("boom")
    return [Job(f"fake:{board}", jid, company, title, f"https://x/{jid}", "Haifa, Israel", desc)
            for jid, title, desc in STATE["jobs"]]


def setup(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setitem(runner.ADAPTERS, "fake", (fake_fetch, None))

    def fake_send(self, text):
        if STATE.get("tg_down"):
            return False
        sent.append(text)
        return True
    monkeypatch.setattr(runner.Telegram, "send", fake_send)
    STATE["tg_down"] = False
    comp = tmp_path / "companies.yaml"
    comp.write_text(yaml.safe_dump({"companies": [
        {"name": "Acme", "ats": "fake", "board": "acme", "status": "verified"},
        {"name": "Elbit Systems", "status": "custom"}]}))
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    cfg["run"]["failure_alert_after"] = 2
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True))
    args = argparse.Namespace(config=str(tmp_path / "config.yaml"), companies=str(comp),
                              db=str(tmp_path / "jobs.db"), only=None, dry_run=True, verbose=False)
    return args, sent


def test_baseline_then_only_new_jobs(tmp_path, monkeypatch):
    args, sent = setup(tmp_path, monkeypatch)
    STATE.update(fail=False, jobs=[
        ("1", "Firmware Engineer", "• 0-2 years of experience"),
        ("2", "Senior Firmware Engineer", "• 8 years of experience"),
        ("3", "Embedded Software Engineer", "• 5+ years of experience")])

    runner.run(args)                                   # first run = baseline
    assert "קו בסיס" in sent[0] and "Firmware Engineer" in sent[1] and len(sent) == 2
    sent.clear()

    runner.run(args)                                   # nothing new -> silence
    assert sent == []

    STATE["jobs"].append(("4", "Junior Embedded Engineer", "• B.Sc. in EE"))
    STATE["jobs"].append(("5", "Network Software Engineer", "• 3 years of experience"))
    runner.run(args)
    assert len(sent) == 1 and "Junior Embedded Engineer" in sent[0] and "🟢" in sent[0]
    sent.clear()

    runner.run(args)                                   # same jobs again -> no duplicates
    assert sent == []


def test_failure_alert_once(tmp_path, monkeypatch):
    args, sent = setup(tmp_path, monkeypatch)
    STATE.update(fail=True, jobs=[])
    runner.run(args)
    assert sent == []
    runner.run(args)
    runner.run(args)
    alerts = [s for s in sent if "נכשל" in s]
    assert len(alerts) == 1


def test_detection_is_cached(tmp_path, monkeypatch):
    args, sent = setup(tmp_path, monkeypatch)
    comp = tmp_path / "companies.yaml"
    comp.write_text(yaml.safe_dump({"companies": [
        {"name": "Valens", "domain": "valens.com", "status": "detect"},
        {"name": "NoSite", "domain": "TBD", "status": "detect"}]}))
    calls = []
    monkeypatch.setattr(runner, "run_detection",
                        lambda c, http: (calls.append(c["name"]) or (("fake", "valens"), "")))
    STATE.update(fail=False, jobs=[("1", "Firmware Engineer", "• no experience required")])
    runner.run(args)
    runner.run(args)
    assert calls == ["Valens"]                          # second run used the cache
    assert any("Valens → fake" in s for s in sent)


def test_messages_survive_a_telegram_outage(tmp_path, monkeypatch):
    args, sent = setup(tmp_path, monkeypatch)
    STATE.update(fail=False, jobs=[("1", "Firmware Engineer", "• no experience required")])
    STATE["tg_down"] = True
    runner.run(args)                                   # baseline match can't be delivered
    assert sent == []
    STATE["tg_down"] = False
    runner.run(args)                                   # delivered on the next run
    assert len(sent) == 1 and "Firmware Engineer" in sent[0]
    runner.run(args)
    assert len(sent) == 1                              # and only once


def test_old_database_is_migrated(tmp_path):
    import sqlite3
    from monitor.store import Store
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE jobs (key TEXT PRIMARY KEY, source TEXT, company TEXT, title TEXT,"
                      " url TEXT, status TEXT, reason TEXT, first_seen INTEGER);"
                      "INSERT INTO jobs VALUES ('s#1','s','A','T','u','match','',1);")
    con.commit()
    con.close()
    st = Store(str(db))
    assert st.known_ids("s") == {"1"} and st.pending() == []
