from monitor import detect
from monitor.adapters import comeet, simple, workday


class FakeHttp:
    """Routes by URL prefix. Values may be callables taking (url, params_or_payload)."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def _hit(self, url, arg):
        self.calls.append((url, arg))
        for prefix, val in sorted(self.routes.items(), key=lambda kv: -len(kv[0])):
            if url.startswith(prefix):
                return val(url, arg) if callable(val) else val
        raise RuntimeError(f"404 {url}")

    def get_json(self, url, params=None):
        return self._hit(url, params)

    def post_json(self, url, payload):
        return self._hit(url, payload)

    def get_text(self, url):
        return self._hit(url, None)


# ---------------- Workday ----------------
FACETS = [{"facetParameter": "locationMainGroup", "values": [
    {"facetParameter": "locationHierarchy1", "descriptor": "Country", "values": [
        {"descriptor": "United States", "id": "us1", "count": 900},
        {"descriptor": "Israel", "id": "il1", "count": 25}]}]}]


def wd_list(url, payload):
    if not payload["appliedFacets"]:
        return {"total": 925, "facets": FACETS, "jobPostings": [{"title": "US job", "externalPath": "/job/us"}]}
    assert payload["appliedFacets"] == {"locationHierarchy1": ["il1"]}
    start = payload["offset"]
    rows = [{"title": f"Firmware Engineer {i}", "externalPath": f"/job/Yokneam/FW_{i}",
             "locationsText": "Yokneam"} for i in range(start, min(start + 20, 25))]
    return {"total": 25, "jobPostings": rows}


def test_workday_scopes_to_israel_and_pages():
    api = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite"
    http = FakeHttp({api + "/jobs": wd_list, api + "/job/": {"jobPostingInfo": {
        "jobDescription": "<p>Requirements:</p><ul><li>B.Sc.</li></ul>", "location": "Yokneam, Israel"}}})
    jobs = workday.fetch(http, "nvidia/wd5/NVIDIAExternalCareerSite", "NVIDIA")
    assert len(jobs) == 25 and all(j.israel for j in jobs)
    assert jobs[0].url == "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/Yokneam/FW_0"
    workday.details(http, "nvidia/wd5/NVIDIAExternalCareerSite", jobs[0])
    assert "B.Sc." in jobs[0].description and jobs[0].location == "Yokneam, Israel"


# ---------------- Greenhouse / Lever / Amazon / SmartRecruiters ----------------
def test_greenhouse_unescapes_content():
    http = FakeHttp({"https://boards-api.greenhouse.io/v1/boards/catonetworks/jobs": {"jobs": [
        {"id": 7, "title": "Network Software Engineer", "absolute_url": "https://gh/7",
         "location": {"name": "Tel Aviv, Israel"}, "content": "&lt;p&gt;Requirements:&lt;/p&gt;&lt;ul&gt;&lt;li&gt;C&lt;/li&gt;&lt;/ul&gt;"}]}})
    [j] = simple.greenhouse_fetch(http, "catonetworks", "Cato")
    assert j.job_id == "7" and j.description == "Requirements:\n• C"


def test_lever_eu_and_country():
    http = FakeHttp({"https://api.eu.lever.co/v0/postings/mobileye": [
        {"id": "abc", "text": "C++ Software Engineer", "hostedUrl": "https://lever/abc", "country": "IL",
         "categories": {"location": "Jerusalem"}, "description": "<p>Hi</p>",
         "lists": [{"text": "Requirements", "content": "<li>1-2 years of experience</li>"}]}]})
    [j] = simple.lever_fetch(http, "eu:mobileye", "Mobileye")
    assert j.location == "Jerusalem, Israel" and "1-2 years" in j.description


def test_amazon_builds_qualification_sections():
    http = FakeHttp({"https://www.amazon.jobs/en/search.json": {"jobs": [
        {"id_icims": "10458621", "title": "Embedded Software Engineer", "job_path": "/en/jobs/10458621",
         "normalized_location": "Haifa, ISR", "description": "Build chips",
         "basic_qualifications": "- Knowledge of C", "preferred_qualifications": "- 3+ years of experience"}]}})
    [j] = simple.amazon_fetch(http, "ISR", "Amazon")
    assert j.url == "https://www.amazon.jobs/en/jobs/10458621"
    assert "Preferred qualifications:" in j.description


def test_smartrecruiters_list_and_details():
    base = "https://api.smartrecruiters.com/v1/companies/Wix2/postings"
    http = FakeHttp({base: {"totalFound": 1, "content": [
        {"id": "99", "name": "Junior Backend Engineer", "location": {"city": "Tel Aviv", "country": "il"}}]},
        base + "/99": {"jobAd": {"sections": {"qualifications": {"title": "Qualifications", "text": "<li>C++</li>"}}}}})
    [j] = simple.smartrecruiters_fetch(http, "Wix2", "Wix")
    assert j.location == "Tel Aviv, Israel"
    simple.smartrecruiters_details(http, "Wix2", j)
    assert "C++" in j.description


# ---------------- Comeet ----------------
TOKEN = "ABCDEF0123456789ABCDEF01"


def test_comeet_board_from_embedded_script():
    page = f'<script>COMEET.init({{"token": "{TOKEN}", "company-uid": "98.A50"}})</script>'
    assert comeet.board_from_html(page) == (f"98.A50|{TOKEN}", None)


def test_comeet_resolve_via_hosted_page_and_fetch():
    http = FakeHttp({
        "https://drivenets.com/careers": '<a href="https://www.comeet.com/jobs/drivenets/12.ABC/x/98.A50">Apply</a>',
        "https://www.comeet.com/jobs/drivenets/12.ABC": f'<script>var c = {{"token":"{TOKEN}"}}</script>',
        "https://www.comeet.co/careers-api/2.0/company/12.ABC/positions": [
            {"uid": "98.A50", "name": "Software Engineer - Data-Path", "url_active_page": "https://dn/98.A50",
             "location": {"city": "Tel Aviv", "country": "IL"},
             "details": [{"name": "Requirements", "value": "<ul><li>C</li></ul>"}]}],
    })
    board = comeet.resolve(http, "https://drivenets.com/careers")
    assert board == f"12.ABC|{TOKEN}"
    [j] = comeet.fetch(http, board, "DriveNets")
    assert j.source == "comeet:12.ABC" and j.location == "Tel Aviv, Israel"


# ---------------- Detector ----------------
def test_detect_follows_careers_link():
    http = FakeHttp({
        "https://valens.com/careers": '<iframe src="https://boards.greenhouse.io/embed/job_board?for=valens"></iframe>',
        "https://valens.com": '<a href="/careers">Careers</a> <script src="/js/ab.min.js"></script>',
    })
    assert detect.detect(http, "valens.com") == ("greenhouse", "valens")


def test_detect_workday_and_lever_eu():
    assert detect.scan('href="https://intel.wd1.myworkdayjobs.com/en-US/External"') == ("workday", "intel/wd1/External")
    assert detect.scan('href="https://jobs.eu.lever.co/mobileye/123"') == ("lever", "eu:mobileye")
    assert detect.scan("<html>nothing here</html>") is None
