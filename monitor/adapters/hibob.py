"""HiBob public careers API; companyIdentifier is the public tenant subdomain."""
from ..http import html_to_text
from ..models import Job


def fetch(http, board, company):
    base = f'https://{board}.careers.hibob.com'
    data = http._req('GET', base + '/api/job-ad', headers={
        'Accept': 'application/json', 'companyIdentifier': board}).json()
    if not isinstance(data.get('jobAdDetails'), list):
        raise ValueError('HiBob: jobAdDetails missing')
    return [Job(f'hibob:{board}', p['id'], company, p['title'], f"{base}/jobs/{p['id']}",
                location=', '.join(filter(None, [p.get('site'), p.get('country')])),
                description=html_to_text((p.get('description') or '') + '\n<h3>Requirements:</h3>'
                                         + (p.get('requirements') or '')))
            for p in data['jobAdDetails']]
