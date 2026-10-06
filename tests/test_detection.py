import html

import pytest
import requests

from monitor import detect
from monitor.adapters import comeet
from tests.test_adapters import FakeHttp, TOKEN


@pytest.mark.parametrize("page", [
    f'COMEET.init({{token:"{TOKEN}", "company-uid":"98.A50"}})',
    f'var token="{TOKEN}"; var company_uid="98.A50";',
    f'var comeetvar={{"comeet_token":"{TOKEN}","comeet_uid":"98.A50"}};',
    f'<div data-token="{TOKEN}" data-company-uid="98.A50"></div>',
    html.escape(f'{{"token":"{TOKEN}","companyUid":"98.A50"}}'),
    f'{{\\"token\\":\\"{TOKEN}\\",\\"company_uid\\":\\"98.A50\\"}}',
    f'https://www.comeet.co/careers-api/2.0/company/98.A50/positions?details=true&token={TOKEN}',
])
def test_comeet_settings_variants(page):
    assert comeet.board_from_html(page)[0] == f"98.A50|{TOKEN}"


def test_detector_skips_assets_newsletters_and_duplicate_hosts():
    root = "https://example.com"
    page = ('<link href="/wp-job-openings/jobs.css">'
            '<a href="/join-our-newsletter/">Join our newsletter</a>'
            '<a href="https://www.example.com/careers/">Careers</a>'
            '<a href="/careers">Careers</a>'
            '<a href="/de/careers/">Careers</a>')
    urls = detect._candidates(root, page, common=False)
    assert urls == ["https://www.example.com/careers/"]


def test_detect_follows_nested_careers_links_and_integration_script():
    http = FakeHttp({
        "https://example.com": '<a href="/careers">Careers</a>',
        "https://example.com/careers": '<a href="/careers/open-positions">Open positions</a>',
        "https://example.com/careers/open-positions": '<!-- comeet --><script src="/js/comeet-config.js"></script>',
        "https://example.com/js/comeet-config.js": f'var token="{TOKEN}"; var company_uid="98.A50";',
    })
    assert detect.detect(http, "example.com") == ("comeet", f"98.A50|{TOKEN}")
    assert len(http.calls) == 4


def test_detect_hosted_page_token_with_company_uid_from_url():
    http = FakeHttp({
        "https://example.com": '<a href="https://www.comeet.co/jobs/acme/12.ABC">Jobs</a>',
        "https://www.comeet.com/jobs/acme/12.ABC": f'var token="{TOKEN}";',
        "https://www.comeet.co/jobs/acme/12.ABC": f'var token="{TOKEN}";',
    })
    assert detect.detect(http, "example.com") == ("comeet", f"12.ABC|{TOKEN}")


@pytest.mark.parametrize("status", [403, 429])
def test_detection_stops_requests_to_blocked_host(status):
    response = requests.Response()
    response.status_code = status

    def fail(url, params):
        raise requests.HTTPError("blocked", response=response)

    http = FakeHttp({"https://example.com": fail})
    trace = []
    assert detect.detect(http, "example.com", trace=trace) is None
    assert len(http.calls) == 1 and trace[0].startswith(str(status))


def test_detection_obeys_budget_when_homepage_fails():
    http = FakeHttp({})
    assert detect.detect(http, "example.com", max_pages=3) is None
    assert len(http.calls) == 3


def test_detect_eightfold_uses_bootstrap_domain_and_actual_careers_host():
    page = '<code id="pcsx-data">{&#34;domain&#34;:&#34;qualcomm.com&#34;}</code>'
    assert detect.scan(page, "https://careers.qualcomm.com") == (
        "eightfold", "careers.qualcomm.com|qualcomm.com")


def test_eightfold_bootstrap_preserves_escaped_json_inside_settings():
    import json
    data = {"domain": "qualcomm.com", "configs": {"footer": '<a href="https://example.com">Jobs</a>'}}
    page = '<code id="pcsx-data">' + html.escape(json.dumps(data)) + '</code>'
    assert detect.scan(page, "https://careers.qualcomm.com")[1] == "careers.qualcomm.com|qualcomm.com"
