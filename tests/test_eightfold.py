import pytest

from monitor.adapters import eightfold
from tests.test_adapters import FakeHttp

BASE = "https://careers.qualcomm.com"
BOARD = "careers.qualcomm.com|qualcomm.com"


def test_eightfold_pages_and_fetches_details():
    def search(url, params):
        assert params["domain"] == "qualcomm.com" and params["location"] == "Israel"
        start = params["start"]
        positions = [{"id": i, "name": "Firmware Engineer", "locations": ["Haifa, Israel"],
                      "positionUrl": f"/careers/job/{i}"} for i in range(start + 1, min(start + 3, 4))]
        return {"status": 200, "error": {"message": "", "body": ""},
                "data": {"count": 3, "positions": positions}}

    http = FakeHttp({BASE + "/api/pcsx/search": search,
                     BASE + "/api/pcsx/position_details": {"data": {
                         "id": 1, "jobDescription": "<h3>Requirements:</h3><li>C++</li>",
                         "publicUrl": BASE + "/careers/job/1", "locations": ["Haifa, Israel"]}}})
    jobs = eightfold.fetch(http, BOARD, "Qualcomm")
    assert [j.job_id for j in jobs] == ["1", "2", "3"]
    assert jobs[0].source == "eightfold:" + BOARD and jobs[0].description is None
    eightfold.details(http, BOARD, jobs[0])
    assert jobs[0].description == "Requirements:\n• C++"
    assert jobs[0].url == BASE + "/careers/job/1"


@pytest.mark.parametrize("body", [
    {}, {"error": "unavailable", "data": {}}, {"data": {}},
    {"data": {"count": 5, "positions": []}},
])
def test_eightfold_invalid_or_incomplete_response_is_not_an_empty_success(body):
    with pytest.raises(ValueError):
        eightfold.fetch(FakeHttp({BASE + "/api/pcsx/search": body}), BOARD, "Qualcomm")


def test_eightfold_repeated_page_does_not_silently_truncate():
    body = {"data": {"count": 3, "positions": [{"id": 1, "name": "Firmware Engineer"}]}}
    with pytest.raises(ValueError, match="repeated page"):
        eightfold.fetch(FakeHttp({BASE + "/api/pcsx/search": body}), BOARD, "Qualcomm")


def test_eightfold_missing_details_can_be_retried():
    [job] = eightfold.fetch(FakeHttp({BASE + "/api/pcsx/search": {"data": {
        "count": 1, "positions": [{"id": 1, "name": "Firmware Engineer"}]}}}), BOARD, "Qualcomm")
    with pytest.raises(ValueError):
        eightfold.details(FakeHttp({BASE + "/api/pcsx/position_details": {"data": {"id": 1}}}), BOARD, job)
    assert job.description is None
