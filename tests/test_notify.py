import monitor.notify as notify


class Resp:
    def __init__(self, code, body):
        self.status_code, self._body, self.text = code, body, str(body)
        self.ok = code == 200

    def json(self):
        return self._body


def test_config_error_is_reported_once_and_not_retried(monkeypatch, capsys):
    calls = []

    def post(url, json, timeout):
        calls.append(json["text"])
        return Resp(403, {"ok": False, "description": "Forbidden: bot can't send messages to bots"})
    monkeypatch.setattr(notify.requests, "post", post)
    monkeypatch.setattr(notify.time, "sleep", lambda s: None)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", " 123 ")
    tg = notify.Telegram()
    assert tg.chat == "123"
    assert tg.send("a") is False and tg.send("b") is False
    assert calls == ["a"]                       # one request total, no retries after a 403
    assert "bot can't send messages to bots" in capsys.readouterr().out


def test_missing_credentials_never_count_as_delivery(monkeypatch, capsys):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert notify.Telegram().send("pending") is False
    assert "remain queued" in capsys.readouterr().out
    assert notify.Telegram(dry_run=True).send("preview") is True


def test_review_and_temporary_job_are_labeled():
    from monitor.models import Job, Verdict
    job = Job("t", "1", "Acme", "Graduate Machine Learning Engineer temporary", "https://x", "Israel", "")
    text = notify.job_message(job, Verdict("review", "adjacent field", (1, None), True))
    assert "תחום משיק" in text and "משרה זמנית" in text
    assert "לא צוין ותק" not in text
