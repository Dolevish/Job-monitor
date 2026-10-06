"""Public, company-owned job feeds for Elbit Systems and Ness."""
from .pages import unique_extend
from ..http import html_to_text
from ..models import Job


def elbit_fetch(http, board, company):
    data = http.get_json('https://elbitsystemscareer.com/cron/jobs.json')
    if not isinstance(data, list):
        raise ValueError('Elbit: jobs array missing')
    jobs = []
    for p in data:
        jid = str(p['jobId'])
        body = html_to_text('\n'.join(p.get(k) or '' for k in ('description', 'requirements', 'skills')))
        if not body:
            raise ValueError('Elbit: empty description')
        jobs.append(Job(f'elbit:{board}', jid, company, p['jobTitle'],
                        f'https://elbitsystemscareer.com/job?jid={jid}',
                        location=p.get('locationAddress') or '', israel=True,
                        posted=p.get('openDate', ''), description=body))
    return jobs


def ness_fetch(http, board, company):
    out, seen = [], set()
    for page in range(1, 101):
        data = http.get_json('https://www.ness-tech.co.il/careers/api/Careers/GetOrderDetailsList', {
            'rows': 100, 'page': page, 'profId': '', 'areasId': '',
            'freeText': '', 'isHot': 'false', 'isToggle': 'false'})
        batch = [Job(f'ness:{board}', str(p['index']), company, p['title'],
                     f"https://www.ness-tech.co.il/careers/job/{p['index']}",
                     location=p.get('posLocation') or 'Israel', israel=True,
                     description=html_to_text(p.get('posDescription')), posted=p.get('lastUpdated', ''))
                 for p in data['allOrderDetailsList']]
        unique_extend(out, batch, seen)
        if len(out) >= int(data['getTotalCount']):
            return out
        if not batch:
            raise ValueError('Ness: incomplete pagination')
    raise ValueError('Ness: pagination limit reached')
