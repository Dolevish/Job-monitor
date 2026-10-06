import argparse
import time

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
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
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
                              db=str(tmp_path / "jobs.db"), only=None, dry_run=False, verbose=False)
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
    st.close()


def test_baseline_review_has_separate_limit(tmp_path, monkeypatch):
    args, sent = setup(tmp_path, monkeypatch)
    cfg = yaml.safe_load(open(args.config))
    cfg["run"].update(baseline_max=1, baseline_review_max=1)
    open(args.config, "w").write(yaml.safe_dump(cfg))
    STATE.update(fail=False, jobs=[
        ("1", "Junior Firmware Engineer", "• C"),
        ("2", "Firmware Engineer", "• C"),
        ("3", "Junior Embedded Engineer", "• C"),
        ("4", "Embedded Software Engineer", "• C")])
    runner.run(args)
    assert len(sent) == 3  # summary + one match + one review
    assert sum("🟡" in msg for msg in sent) == 1
    runner.run(args)
    assert len(sent) == 3  # capped jobs don't leak into later runs


def test_recent_legacy_review_is_reclassified_without_reset(tmp_path, monkeypatch):
    from monitor.store import Store
    args, sent = setup(tmp_path, monkeypatch)
    STATE.update(fail=False, jobs=[("1", "Firmware Engineer", "• C/C++")])
    st = Store(args.db)
    st.add_job(fake_fetch(None, "acme", "Acme")[0], "review", "no years stated")
    st.db.execute("UPDATE jobs SET classification_version=1")
    st.mark_ok("fake:acme", 1)
    st.close()
    runner.run(args)
    assert len(sent) == 1 and "Firmware Engineer" in sent[0]
    runner.run(args)
    assert len(sent) == 1


def test_old_legacy_review_stays_seen(tmp_path, monkeypatch):
    from monitor.store import Store
    args, sent = setup(tmp_path, monkeypatch)
    STATE.update(fail=False, jobs=[("1", "Firmware Engineer", "• C/C++")])
    st = Store(args.db)
    st.add_job(fake_fetch(None, "acme", "Acme")[0], "review")
    st.db.execute("UPDATE jobs SET classification_version=1, first_seen=?", (int(time.time()) - 4 * 86400,))
    st.mark_ok("fake:acme", 1)
    st.close()
    runner.run(args)
    assert sent == []


def test_failed_details_are_retried_before_classification(tmp_path, monkeypatch, capsys):
    from monitor.store import Store
    args, sent = setup(tmp_path, monkeypatch)
    calls = []

    def fetch(http, board, company):
        return [Job("fake:acme", "1", company, "Junior Firmware Engineer", "https://x/1", "Israel")]

    def details(http, board, job):
        calls.append(job.job_id)
        if len(calls) == 1:
            raise RuntimeError("temporary detail failure")
        job.description = "• C++"

    monkeypatch.setitem(runner.ADAPTERS, "fake", (fetch, details))
    runner.run(args)
    assert not any("Junior Firmware Engineer" in msg for msg in sent)
    st = Store(args.db)
    assert st.known_ids("fake:acme") == set()
    st.close()
    runner.run(args)
    assert sum("Junior Firmware Engineer" in msg for msg in sent) == 1
    runner.run(args)
    assert calls == ["1", "1"]
    assert "RETRY details next run" in capsys.readouterr().out


def test_dry_run_preserves_existing_queue_and_state(tmp_path, monkeypatch):
    args, sent = setup(tmp_path, monkeypatch)
    STATE.update(fail=False, tg_down=True, jobs=[("1", "Firmware Engineer", "• no experience required")])
    runner.run(args)
    before = (tmp_path / "jobs.db").read_bytes()
    STATE["tg_down"] = False
    args.dry_run = True
    runner.run(args)
    assert (tmp_path / "jobs.db").read_bytes() == before
    sent.clear()
    args.dry_run = False
    runner.run(args)
    assert len(sent) == 1 and "Firmware Engineer" in sent[0]


def test_dry_run_does_not_create_database(tmp_path, monkeypatch):
    args, sent = setup(tmp_path, monkeypatch)
    args.dry_run = True
    STATE.update(fail=False, jobs=[("1", "Firmware Engineer", "• no experience required")])
    runner.run(args)
    assert not (tmp_path / "jobs.db").exists()


def test_failed_source_alert_is_retried_after_telegram_recovers(tmp_path, monkeypatch):
    args, sent = setup(tmp_path, monkeypatch)
    STATE.update(fail=True, tg_down=True, jobs=[])
    runner.run(args)
    runner.run(args)
    STATE["tg_down"] = False
    runner.run(args)
    runner.run(args)
    assert sum("נכשל" in msg for msg in sent) == 1


def test_legacy_detection_is_refreshed_without_reset(tmp_path, monkeypatch):
    from monitor.store import Store
    st = Store(str(tmp_path / "jobs.db"))
    st.save_detection("Acme", None, None, "previous failed lookup")
    st.db.execute("UPDATE detections SET detector_version=1")
    company = {"name": "Acme", "careers": "https://acme.test/careers", "status": "detect"}
    assert runner.plan(company, st)[0] == "detect"
    st.save_detection("Acme", None, None, "current lookup")
    assert runner.plan(company, st)[0] == "skip"
    st.close()


def test_no_new_jobs_does_not_count_as_empty_feed(tmp_path, monkeypatch, capsys):
    from monitor.store import Store
    args, sent = setup(tmp_path, monkeypatch)
    STATE.update(fail=False, jobs=[("1", "Firmware Engineer", "• no experience required")])
    runner.run(args)
    runner.run(args)
    st = Store(args.db)
    assert st.source_counts("fake:acme") == (1, 0)
    st.close()
    log = capsys.readouterr().out
    assert "new=   0" in log and "WARNING empty feed" not in log


def test_missing_credentials_fail_run_and_preserve_job_queue(tmp_path, monkeypatch):
    from monitor.store import Store
    real_send = runner.Telegram.send
    args, sent = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(runner.Telegram, "send", real_send)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    monkeypatch.delenv("TELEGRAM_CHAT_ID")
    STATE.update(fail=False, jobs=[("1", "Junior Firmware Engineer", "• C")])
    assert runner.run(args) == 1
    st = Store(args.db)
    assert len(st.pending()) == 1
    st.close()


def test_empty_source_is_visible_in_logs_and_health(tmp_path, monkeypatch, capsys):
    from monitor.store import Store
    args, sent = setup(tmp_path, monkeypatch)
    STATE.update(fail=False, jobs=[])
    runner.run(args)
    st = Store(args.db)
    assert st.source_counts("fake:acme") == (0, 1)
    st.close()
    assert "WARNING empty feed" in capsys.readouterr().out


def test_full_previous_schema_migrates_without_losing_delivery_history(tmp_path):
    import sqlite3
    from monitor.store import Store
    path = str(tmp_path / "previous.db")
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE jobs (key TEXT PRIMARY KEY, source TEXT, company TEXT, title TEXT,
                           url TEXT, status TEXT, reason TEXT, first_seen INTEGER,
                           message TEXT, notified INTEGER DEFAULT 0);
        CREATE TABLE sources (source TEXT PRIMARY KEY, first_run INTEGER, last_ok INTEGER,
                              failures INTEGER DEFAULT 0, alerted INTEGER DEFAULT 0, last_error TEXT);
        CREATE TABLE detections (company TEXT PRIMARY KEY, ats TEXT, board TEXT, ok INTEGER,
                                 checked_at INTEGER, note TEXT);
        INSERT INTO jobs VALUES ('s#1','s','Acme','Firmware Engineer','https://x','review','',1,'sent',1);
        INSERT INTO sources VALUES ('s',1,1,0,0,'');
        INSERT INTO detections VALUES ('Acme','comeet','98.A50|public-token',1,1,'');
    """)
    con.close()
    st = Store(path)
    assert st.known_ids("s") == {"1"} and st.pending() == []
    assert st.source_seen("s") and st.source_counts("s") == (None, 0)
    assert st.detection("Acme")[4] == 1
    st.mark_ok("s", 3)
    assert st.source_counts("s") == (3, 0)
    st.close()


def test_source_check_writes_coverage_without_notifications_or_database(tmp_path, monkeypatch):
    import json
    args, sent = setup(tmp_path, monkeypatch)
    args.check_sources = True
    args.coverage_json = str(tmp_path / 'coverage.json')
    STATE.update(fail=False, jobs=[('1', 'Firmware Engineer', '• C++')])
    assert runner.run(args) == 1  # fixture's Elbit entry has no configured source
    assert sent == [] and not (tmp_path / 'jobs.db').exists()
    data = json.loads((tmp_path / 'coverage.json').read_text())
    assert data['successful_entries'] == 1 and data['skipped'] == 1
