import html
import json
from types import SimpleNamespace

import pytest
import yaml

from monitor.adapters import ADAPTERS, source_key
from monitor.adapters import apple, ashby, company_sites, experis, hibob, israeli, jobify, jobnet, oracle, pages, taleo, wordpress
from monitor.coverage import report
from monitor.filters import Filters, required_years
from monitor.models import Job, Verdict
from monitor.notify import job_message
from monitor.runner import Feed, Result, process


class FakeHttp:
    def __init__(self, texts=(), jsons=(), responses=()):
        self.texts, self.jsons, self.responses = iter(texts), iter(jsons), iter(responses)
        self.calls = []

    def get_text(self, url):
        self.calls.append(('GET', url))
        return next(self.texts)

    def get_json(self, url, params=None):
        self.calls.append(('GET', url, params))
        return next(self.jsons)

    def post_json(self, url, payload):
        self.calls.append(('POST', url, payload))
        return next(self.jsons)

    def _req(self, method, url, **kw):
        self.calls.append((method, url, kw))
        return next(self.responses)


def response(data, headers=None):
    return SimpleNamespace(json=lambda: data, headers=headers or {})


def job(**kwargs):
    return Job('source', '1', 'Acme', 'Firmware Engineer', 'https://example.test/job/1', **kwargs)


def test_every_company_has_supported_source_or_explicit_missing_identity():
    companies = yaml.safe_load(open('companies.yaml'))['companies']
    assert len(companies) == 72
    for c in companies:
        assert c.get('status') in {'detect', 'signature', 'needs_source'} or c['ats'] in ADAPTERS
        if c.get('status') == 'needs_source':
            assert c['name'] == 'ACM' and c['note']


def test_oracle_fetches_later_pages_and_preserves_source_identity():
    def data(jid):
        return {'items': [{'TotalJobsCount': 2, 'requisitionList': [{'Id': jid, 'Title': 'Firmware Engineer', 'PrimaryLocation': 'Israel'}]}]}
    http = FakeHttp(jsons=[data(1), data(2)])
    jobs = oracle.fetch(http, 'edbz/CX_1', 'TI')
    assert [j.job_id for j in jobs] == ['1', '2']
    assert jobs[0].source == source_key('oracle_hcm', 'edbz/CX_1')
    assert 'offset=100' in http.calls[1][2]['finder']
    with pytest.raises(ValueError, match='repeated'):
        oracle.fetch(FakeHttp(jsons=[data(1), data(1)]), 'edbz/CX_1', 'TI')


def test_oracle_does_not_accept_wrong_job_details():
    with pytest.raises(ValueError, match='missing job details'):
        oracle.details(FakeHttp(jsons=[{'items': [{'Id': 2, 'ExternalDescriptionStr': 'wrong'}]}]), 'edbz/CX_1', job())


def hydration(data):
    return 'window.__staticRouterHydrationData = JSON.parse(' + json.dumps(json.dumps({'loaderData': data})) + ');'


def test_apple_keeps_mandatory_and_preferred_qualifications_separate():
    http = FakeHttp(texts=[hydration({'jobDetails': {'jobsData': {
        'jobNumber': '1', 'description': 'Develop firmware',
        'minimumQualifications': 'At least 5 years of embedded firmware design',
        'preferredQualifications': '8 years of experience preferred'}}})])
    j = job()
    apple.details(http, 'Israel', j)
    assert required_years(j.description) == (5, None)
    assert 'Preferred Qualifications:' in j.description


def test_apple_repeated_page_is_not_reported_as_complete():
    data = hydration({'search': {'totalRecords': 2, 'searchResults': [{
        'id': '1', 'postingTitle': 'Firmware Engineer', 'transformedPostingTitle': 'firmware-engineer'}]}})
    with pytest.raises(ValueError, match='repeated'):
        apple.fetch(FakeHttp(texts=[data, data]), 'Israel', 'Apple')


def test_ashby_respects_unlisted_jobs_and_secondary_locations():
    http = FakeHttp(jsons=[{'jobs': [
        {'id': '1', 'title': 'Firmware Engineer', 'jobUrl': 'https://x/1', 'location': 'London',
         'secondaryLocations': [{'location': 'Tel Aviv'}], 'descriptionPlain': 'Requirements: C++'},
        {'id': 'hidden', 'isListed': False}]}])
    jobs = ashby.fetch(http, 'acme', 'Acme')
    assert len(jobs) == 1 and 'Tel Aviv' in jobs[0].location
    with pytest.raises(ValueError, match='jobs array'):
        ashby.fetch(FakeHttp(jsons=[{}]), 'acme', 'Acme')


def test_full_description_wins_over_truncated_structured_metadata():
    body = 'Requirements: 5 years of experience building embedded firmware. ' * 3
    doc = '<script type="application/ld+json">{"@type":"JobPosting","description":"Junior opportunity"}</script>'
    doc += '<div id="full">' + body + '</div>'
    j = job(extra={'detail_selector': '#full'})
    pages.description(FakeHttp(texts=[doc]), '', j)
    assert '5 years' in j.description and 'Junior opportunity' not in j.description
    with pytest.raises(ValueError, match='full description'):
        pages.description(FakeHttp(texts=['<p>No longer available</p>']), '', j)


def snapshot(board='8'):
    return json.dumps({'memo': {'name': 'jobs-by-company'}, 'data': {'companyId': board}})


def jobify_card(jid):
    return f'<a class="job-item" href="https://jobify360.co.il/jobs/{jid}"><b class="title">Firmware Engineer</b></a>'


def jobify_reply(jid, total=2):
    return {'components': [{'snapshot': snapshot(), 'effects': {'html': f'סך הכל סה"כ משרות: {total}' + jobify_card(jid)}}]}


def test_jobify_does_not_reset_page_size_on_every_page():
    initial = f'<meta name="csrf-token" content="public-view-token"><div wire:snapshot="{html.escape(snapshot(), quote=True)}"></div>'
    http = FakeHttp(texts=[initial], jsons=[jobify_reply('a'), jobify_reply('b')])
    jobs = jobify.fetch(http, '8', 'Matrix')
    assert len(jobs) == 2
    assert http.calls[1][2]['components'][0]['updates']['perPage'] == 100
    assert http.calls[2][2]['components'][0]['updates'] == {'paginators.page': 2}
    assert all(c[2]['components'][0]['calls'] == [] for c in http.calls[1:])
    assert jobs[0].extra['secondary_source'] == 'Jobify'


def test_jobify_rejects_employer_mismatch():
    doc = pages.soup(f'<div wire:snapshot="{html.escape(snapshot("99"), quote=True)}"></div>')
    with pytest.raises(ValueError, match='wrong employer'):
        jobify.component(doc, '8')


def test_jobnet_verifies_employer_on_each_card():
    doc = '''נמצאו 1 משרות <div itemtype="https://schema.org/JobPosting">
    <p itemprop="hiringOrganization"><a href="/Company?companyID=999">wrong employer</a></p></div>'''
    with pytest.raises(ValueError, match='wrong employer'):
        jobnet.fetch(FakeHttp(texts=[doc]), '22462', 'ONE')


def test_wordpress_uses_total_headers_and_refuses_partial_results():
    p = {'id': 1, 'title': {'rendered': 'Firmware Engineer'}, 'link': 'https://x/1'}
    http = FakeHttp(responses=[response([p], {'X-WP-TotalPages': '2', 'X-WP-Total': '2'}),
                              response([], {'X-WP-TotalPages': '2', 'X-WP-Total': '2'})])
    with pytest.raises(ValueError, match='incomplete'):
        wordpress.fetch(http, 'https://x/wp-json/wp/v2/jobs', 'GAV')
    assert http.calls[1][2]['params']['page'] == 2


def test_hibob_uses_public_tenant_header_and_includes_requirements():
    p = {'id': '1', 'title': 'Firmware Engineer', 'site': 'IL', 'country': 'Israel',
         'description': 'Build firmware', 'requirements': '<p>5 years of experience</p>'}
    http = FakeHttp(responses=[response({'jobAdDetails': [p]})])
    jobs = hibob.fetch(http, 'public-tenant', 'HiBob')
    assert http.calls[0][2]['headers']['companyIdentifier'] == 'public-tenant'
    assert '5 years' in jobs[0].description


def test_elbit_links_use_published_site_route():
    p = {'jobId': 123, 'jobTitle': 'Firmware Engineer', 'description': 'Develop firmware', 'requirements': 'C++'}
    j = israeli.elbit_fetch(FakeHttp(jsons=[[p]]), 'israel', 'Elbit')[0]
    assert j.url == 'https://elbitsystemscareer.com/job?jid=123'
    assert j.source == source_key('elbit', 'israel')


def test_ness_repeated_pages_are_errors():
    data = {'getTotalCount': 2, 'allOrderDetailsList': [{'index': 1, 'title': 'Firmware Engineer', 'posDescription': 'C'}]}
    with pytest.raises(ValueError, match='repeated'):
        israeli.ness_fetch(FakeHttp(jsons=[data, data]), 'israel', 'Ness')


def test_abra_reads_all_ajax_pages():
    def part(jid, more):
        return response({'success': True, 'data': {'html': f'<div class="career__our-careers-item"><a class="title" href="/career/{jid}">Firmware Engineer</a></div>', 'total': 2, 'has_more': more}})
    http = FakeHttp(responses=[part(1, True), part(2, False)])
    jobs = company_sites.fetch(http, 'abra', 'abra')
    assert len(jobs) == 2 and http.calls[1][2]['data']['offset'] == 1


def test_deloitte_does_not_stop_at_initial_cards():
    def card(jid):
        return f'<div class="position-row"><span class="position-row-title">Firmware Engineer</span><a href="/position/{jid}"></a></div>'
    initial = '<div class="positions-continer" data-total="2" data-ajax-url="/wp-admin/admin-ajax.php">' + card(1) + '</div>'
    http = FakeHttp(texts=[initial], responses=[response({'positions': card(2)})])
    assert len(company_sites.fetch(http, 'deloitte', 'Deloitte')) == 2
    assert http.calls[1][2]['data']['action'] == 'deloitte_careers_load_more_positions_ajax'


def test_xsight_only_reads_complete_jobs_prop_not_featured_roles():
    posting = {'uid': 'A.123', 'title': 'Firmware Engineer', 'href': '/careers/jobs/A.123/firmware',
               'locationLong': 'Israel', 'location': {'country': 'IL'}}
    payload = '1:' + json.dumps({'jobs': [posting]}) + '\n'
    page = '<script>self.__next_f.push(' + json.dumps([1, payload]) + ')</script>'
    jobs = company_sites.fetch(FakeHttp(texts=[page]), 'xsight', 'Xsight')
    assert len(jobs) == 1 and jobs[0].israel
    with pytest.raises(ValueError, match='complete job list'):
        company_sites.fetch(FakeHttp(texts=[page.replace('jobs\\"', 'roles\\"')]), 'xsight', 'Xsight')


def test_unrecognised_company_page_is_not_a_successful_empty_feed():
    with pytest.raises(ValueError, match='job cards missing'):
        company_sites.fetch(FakeHttp(texts=['<html>Enable JavaScript</html>']), 'valens', 'Valens')


def test_coverage_separates_aliases_failures_empty_and_partial():
    companies = [{'name': n, 'status': 'secondary' if n == 'D' else 'verified'} for n in 'ABCDEFG']
    plans = {n: ('ready', ('site', b)) for n, b in zip('ABCDEF', ['a', 'a', 'b', 'c', 'd', 'e'])}
    plans['G'] = ('skip', None)
    results = [Result(Feed('site', b, b, 'site:' + b), fetched=count, error=error,
                      detail_errors=details) for b, count, error, details in [
                          ('a', 3, '', []), ('b', 0, 'blocked', []), ('c', 0, '', []),
                          ('d', 2, '', ['missing details']), ('e', 1, '', [])]]
    data = report(companies, plans, results)
    assert (data['configured'], data['polled_entries'], data['feeds']) == (7, 6, 5)
    assert (data['successful_entries'], data['empty_entries'], data['partial_entries'], data['failed_entries'], data['skipped']) == (3, 1, 1, 1, 1)
    assert data['secondary_entries'] == 1


def test_secondary_source_is_visible_in_notification():
    assert 'מקור חלופי: Jobify' in job_message(job(extra={'secondary_source': 'Jobify'}), Verdict('review'))


def test_new_graduate_cad_is_reviewed():
    flt = Filters(yaml.safe_load(open('config.yaml'))['filters'])
    j = job(location='Israel', description='Requirements: B.Sc. in Computer Science')
    j.title = 'Graduate CAD Engineer'
    assert flt.classify(j).status == 'review'


def test_jobify_counts_duplicate_rows_but_returns_each_posting_once():
    initial = f'<meta name="csrf-token" content="view-token"><div wire:snapshot="{html.escape(snapshot(), quote=True)}"></div>'
    first = jobify_reply('a', 4)
    first['components'][0]['effects']['html'] += jobify_card('b')
    second = jobify_reply('b', 4)
    second['components'][0]['effects']['html'] += jobify_card('c')
    jobs = jobify.fetch(FakeHttp(texts=[initial], jsons=[first, second]), '8', 'Matrix')
    assert [j.job_id for j in jobs] == ['a', 'b', 'c']


def taleo_state(jid, number, delimiter='!%24!'):
    row = ['false'] * 3 + [jid, 'Firmware Engineer', jid, 'Firmware Engineer'] + [jid] * 5
    row += [number, 'IL-IL-Tel Aviv', 'false', '', '', '', '', 'Full-time', 'Oct 6, 2026', 'Apply']
    return delimiter.join(['ftlx0!|!callback', 'requisitionListInterface!|!listRequisition',
                           '!|!'.join(row), 'listRequisition.nbElements!|!2!|!listRequisition.size!|!100'])


def test_taleo_paginates_using_read_only_public_pager_component():
    initial = '<form id="ftlform"><input name="ftlpageid" value="reqListAllJobsPage">'
    initial += '<input id="initialHistory" name="initialHistory" value="' + html.escape(taleo_state('100', '260000A'), quote=True) + '"></form>'
    http = FakeHttp(texts=[initial], responses=[SimpleNamespace(text=taleo_state('200', '260000B', '!$!'))])
    jobs = taleo.fetch(http, 'radware', 'Radware')
    assert [j.job_id for j in jobs] == ['260000A', '260000B']
    assert http.calls[1][1].endswith('/joblist.ajax')
    assert http.calls[1][2]['data']['ftlcompclass'] == 'PagerComponent'
    assert http.calls[1][2]['data']['rlPager.currentPage'] == 2


def test_missing_description_is_retried_even_if_adapter_has_no_details(monkeypatch):
    monkeypatch.setitem(ADAPTERS, 'fake', (lambda *args: [job(location='Israel')], None))
    flt = Filters(yaml.safe_load(open('config.yaml'))['filters'])
    result = process(Feed('fake', 'a', 'Acme', 'fake:a'), FakeHttp(), flt, set())
    assert result.fetched == 1 and result.detail_errors
    assert not result.jobs and not result.candidates


def test_experience_under_requirements_does_not_include_optional_or_company_years():
    assert required_years('Requirements:\nAt least 5 years building firmware\nPreferred Qualifications:\n10 years of experience') == (5, None)
    assert required_years('About us:\nOur company is 25 years old\nRequirements:\nC++') is None
