"""Employer-scoped public Jobnet results, including full requirements."""
import re
from urllib.parse import parse_qs, urlparse, urljoin

from .pages import soup, text, unique_extend
from ..http import html_to_text
from ..models import Job

BASE = 'https://www.jobnet.co.il'


def fetch(http, board, company):
    if not board.isdigit():
        raise ValueError('Jobnet requires a verified numeric employer ID')
    out, seen = [], set()
    for page in range(100):
        doc = soup(http.get_text(f'{BASE}/jobs?companyid={board}&p={page}'))
        count = re.search(r'נמצאו\s*([\d,]+)\s*משרות', text(doc))
        if not count and 'לא נמצאו תוצאות' in text(doc):
            return out
        if not count:
            raise ValueError('Jobnet: result count missing')
        batch = []
        for card in doc.select('[itemtype="https://schema.org/JobPosting"]'):
            org = card.select_one('[itemprop=hiringOrganization] a')
            if org is None or parse_qs(urlparse(org['href'].lower()).query).get('companyid') != [board]:
                raise ValueError('Jobnet: wrong employer in results')
            heading = card.select_one('[itemprop=title]')
            target = urljoin(BASE, heading.parent['href'])
            jid = parse_qs(urlparse(target).query)['positionid'][0]
            body = '\n'.join(html_to_text(str(n)) for n in card.select('[itemprop=description], [itemprop=skills]'))
            if not body:
                raise ValueError('Jobnet: job description missing')
            batch.append(Job(f'jobnet:{board}', jid, company, text(heading), target,
                             location='; '.join(text(n) for n in card.select('[itemprop=jobLocation]')),
                             israel=True, description=body, posted=text(card.select_one('[itemprop=datePosted]')),
                             extra={'secondary_source': 'Jobnet'}))
        unique_extend(out, batch, seen)
        if len(out) >= int(count[1].replace(',', '')):
            return out
        if not batch:
            raise ValueError('Jobnet: incomplete pagination')
    raise ValueError('Jobnet: pagination limit reached')
