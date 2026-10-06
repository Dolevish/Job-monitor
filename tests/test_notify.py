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
