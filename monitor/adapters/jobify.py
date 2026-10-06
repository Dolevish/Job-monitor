"""Company-scoped fallback listings from Jobify, using its public Livewire view.

The POST only changes pagination of the public search component. It never calls
application/login methods. The signed snapshot and CSRF token are kept in memory.
"""
import json
import re
from urllib.parse import urlparse

from .pages import soup, text, unique_extend, description
from ..models import Job

BASE = 'https://jobify360.co.il'


def component(doc, company_id):
    for el in doc.select('[wire\\:snapshot]'):
        snapshot = el['wire:snapshot']
        data = json.loads(snapshot)
        if data.get('memo', {}).get('name') == 'jobs-by-company':
            if str(data['data']['companyId']) != company_id:
                raise ValueError('Jobify: wrong employer returned')
            return snapshot
    raise ValueError('Jobify: company search component missing')


def parse_cards(doc, board, company):
    batch = []
    for card in doc.select('a.job-item[href]'):
        title = text(card.select_one('.title'))
        if not title:
            raise ValueError('Jobify: job title missing')
        info = card.select('.jil .jit')
        target = card['href']
        batch.append(Job(f'jobify:{board}', urlparse(target).path.rsplit('/', 1)[-1],
                         company, title, target, location=text(info[0]) if info else '',
                         israel=True, posted=text(info[1]) if len(info) > 1 else '',
                         extra={'detail_selector': '#white-border-box', 'secondary_source': 'Jobify'}))
    return batch


def fetch(http, board, company):
    if not board.isdigit():
        raise ValueError('Jobify requires a verified numeric employer ID')
    url = f'{BASE}/company/{board}'
    doc = soup(http.get_text(url))
    snapshot = component(doc, board)
    csrf = doc.select_one('meta[name="csrf-token"]')
    if csrf is None:
        raise ValueError('Jobify: search token missing')
    out, seen, rows_read = [], set(), 0
    for page in range(1, 101):
        # Same public component as the site's pagination buttons; no named calls.
        updates = {'paginators.page': page}
        if page == 1:
            updates['perPage'] = 100
        data = http.post_json(BASE + '/livewire/update', {
            '_token': csrf['content'], 'components': [{
                'snapshot': snapshot,
                'updates': updates, 'calls': []}]})
        comp = data['components'][0]
        snapshot = comp['snapshot']
        state = json.loads(snapshot)
        if str(state['data']['companyId']) != board:
            raise ValueError('Jobify: employer changed during pagination')
        doc = soup(comp['effects']['html'])
        batch = parse_cards(doc, board, company)
        total_match = re.search(r'סה["״]?כ\s*משרות\s*:\s*([\d,]+)', text(doc))
        if not total_match:
            raise ValueError('Jobify: total result count missing')
        total = int(total_match[1].replace(',', ''))
        unique_extend(out, batch, seen)
        rows_read += len(batch)  # total includes duplicate links present in the public board
        if rows_read >= total:
            return out
        if not batch:
            raise ValueError('Jobify: incomplete pagination')
    raise ValueError('Jobify: pagination limit reached')


details = description
