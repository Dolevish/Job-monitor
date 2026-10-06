import requests

from monitor.http import Http, retry_delay


def test_retry_after_and_backoff_are_bounded(monkeypatch):
    response = requests.Response()
    response.headers["Retry-After"] = "4"
    assert retry_delay(response, 0) == 4
    response.headers["Retry-After"] = "1000"
    assert retry_delay(response, 0) == 30
    response.headers["Retry-After"] = "invalid"
    monkeypatch.setattr("monitor.http.random.uniform", lambda a, b: 0.5)
    assert retry_delay(response, 1) == 4.5


def test_http_retries_429_with_server_delay(monkeypatch):
    limited, success = requests.Response(), requests.Response()
    limited.status_code, success.status_code = 429, 200
    limited.headers["Retry-After"] = "3"
    responses = iter([limited, success])
    delays = []
    http = Http(retries=2)
    monkeypatch.setattr(http.s, "request", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr("monitor.http.time.sleep", delays.append)
    assert http._req("GET", "https://acme.test") is success
    assert delays == [3]
