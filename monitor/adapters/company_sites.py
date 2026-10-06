"""Explicit HTML schemas for the remaining company-owned careers pages.

Selectors are scoped to job cards. A redesigned page is an error, never a silent
empty result. Candidate descriptions are fetched lazily by the runner.
"""
from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urljoin, urlparse, parse_qs, unquote

from .pages import soup, text, description, unique_extend, same_host_link, walk
from ..http import html_to_text
from ..models import Job

# board = profile name; each profile is tied to one verified company site.
PROFILES = {
    'valens': ('https://www.valens.com/positions/', '.position-card', '.card-title', 'a.link-wrapper', '.location'),
    'xtend': ('https://xtend.me/careers/', 'a.careers-job-card', 'h3', None, '.careers-job-tag-loc'),
    'rad': ('https://www.rad.com/career/', 'a.position-search-item', 'h3', None, '.location'),
    'silicom': ('https://www.silicom-usa.com/careers/', 'a.awsm-job-item', 'h2', None, '.awsm-job-specification-job-location'),
    'nova': ('https://www.novami.com/results/', '.positionBox', '.positionTitle', 'a.positionTitle', '.locationLink'),
    'abra': ('https://www.abra-it.com/career/', '.career__our-careers-item', 'a.title', 'a.title', '.tags li'),
    'deloitte': ('https://careers.deloitte.co.il/positions/?page=all', '.position-row', '.position-row-title', 'a', '.position-location'),
    'aman': ('https://www.aman.co.il/careers/', 'article.aman-job-card', '.aman-job-card__title-link', '.aman-job-card__title-link', '.aman-job-card__tag'),
}
NATIONAL = {'aman'}


def fetch(http, board, company):
    if board == 'deloitte':
        return deloitte(http, company)
    if board == 'xsight':
        return xsight(http, company)
    if board == 'abra':
        return abra(http, company)
    if board == 'gstat':
        return gstat(http, company)
    if board == 'unitronics':
        return unitronics(http, company)
    if board == 'bynet':
        return bynet(http, company)
    url, selector, title_selector, link_selector, loc_selector = PROFILES[board]
    out, seen, pages = [], set(), set()
    while url and len(pages) < 100:
        if url in pages:
            raise ValueError(f'{board}: repeated pagination URL')
        pages.add(url)
        doc, batch = soup(http.get_text(url)), []
        cards = doc.select(selector)
        if not cards:
            raise ValueError(f'{board}: job cards missing; check site schema')
        for card in cards:
            a = card.select_one(link_selector) if link_selector else card
            title = text(card.select_one(title_selector))
            if not a or not a.get('href') or not title:
                raise ValueError(f'{board}: malformed job card')
            target = urljoin(url, a['href'])
            location = text(card.select_one(loc_selector))
            if board == 'nova' and card.get('data-location') == 'israel':
                location += ', Israel'
            if board == 'abra' and location.lower() in {'center', 'north', 'south', 'מרכז', 'צפון', 'דרום'}:
                location += ', Israel'
            batch.append(Job(f'site:{board}', unquote(urlparse(target).path.rstrip('/')), company,
                             title, target, location=location, israel=True if board in NATIONAL else None,
                             extra={'detail_selector': '.position-page .section-content-wrapper .content'} if board == 'valens' else {}))
        unique_extend(out, batch, seen)
        nxt = doc.select_one('a.next.page-numbers, a[rel=next]')
        url = same_host_link(url, nxt['href']) if nxt else None
    if url:
        raise ValueError(f'{board}: pagination limit reached')
    return out


def gstat(http, company):
    url = 'https://g-stat.com/careers/'
    doc = soup(http.get_text(url))
    rows = doc.select('.jobs_accordion .row')
    if not rows:
        raise ValueError('G-STAT: jobs accordion missing')
    jobs = []
    for row in rows:
        title = row.select_one('.job-title[data-id]')
        link = row.select_one('a[href*="shareArticle"]')
        if not title or not link:
            raise ValueError('G-STAT: job metadata missing')
        target = parse_qs(urlparse(link['href']).query)['url'][0]
        desc = '\n'.join(html_to_text(str(n)) for n in row.select('.text-col'))
        jobs.append(Job('site:gstat', title['data-id'], company, text(title), target,
                        location='Israel', israel=True, description=desc))
    return jobs


def unitronics(http, company):
    url = 'https://www.unitronicsplc.com/careers/'
    doc = soup(http.get_text(url))
    jobs = []
    for heading in doc.select('h1.vc_custom_heading'):
        container = heading.parent
        body = heading.find_next_sibling('div', class_='wpb_text_column')
        if body is None:
            continue
        title = text(heading)
        jid = hashlib.sha256(title.encode()).hexdigest()[:16]
        jobs.append(Job('site:unitronics', jid, company, title, url,
                        description=html_to_text(str(body))))
    if not jobs:
        raise ValueError('Unitronics: job sections missing')
    return jobs


def bynet(http, company):
    url = 'https://www.bynet.co.il/career/open-positions/'
    doc = soup(http.get_text(url))
    script = doc.select_one('#vacancies-data')
    if script is None:
        raise ValueError('Bynet: vacancies-data missing')
    data = json.loads(script.get_text())
    if not isinstance(data, list):
        raise ValueError('Bynet: invalid vacancies')
    return [Job('site:bynet', str(p['order_id']), company, p['description'],
                url, location=p.get('living_area1') or 'Israel',
                israel=True, posted=p.get('orderDate') or '',
                description=html_to_text('\n'.join(p.get(k) or '' for k in ('notes',))))
            for p in data]


details = description


def abra(http, company):
    url = 'https://www.abra-it.com/career/'
    out, seen = [], set()
    for _ in range(200):
        response = http._req('POST', 'https://www.abra-it.com/wp-admin/admin-ajax.php',
                             data={'action': 'abra_ajax_filter_jobs', 'offset': len(out),
                                   'search': '', 'department': '', 'category': '', 'location': '',
                                   'attendance': '', 'workplace_type': ''}).json()
        if not response.get('success'):
            raise ValueError('abra: public job search failed')
        data, batch = response['data'], []
        for card in soup(data['html']).select('.career__our-careers-item'):
            a = card.select_one('a.title')
            if a is None:
                raise ValueError('abra: malformed job card')
            target = urljoin(url, a['href'])
            batch.append(Job('site:abra', unquote(urlparse(target).path.rstrip('/')), company,
                             text(a), target, location=text(card.select_one('.tags')), israel=True))
        unique_extend(out, batch, seen)
        if not data['has_more']:
            if len(out) != int(data['total']):
                raise ValueError('abra: incomplete pagination')
            return out
        if not batch:
            raise ValueError('abra: empty intermediate page')
    raise ValueError('abra: pagination limit reached')


def xsight(http, company):
    url = 'https://xsightlabs.com/careers/jobs'
    doc = soup(http.get_text(url))
    # Next.js publishes the complete list as serialized component props. Parse JSON only.
    chunks = []
    for script in doc.select('script'):
        raw = script.get_text()
        if 'self.__next_f.push(' not in raw:
            continue
        try:
            item, _ = json.JSONDecoder().raw_decode(raw.split('self.__next_f.push(', 1)[1])
        except ValueError:
            continue
        if len(item) > 1 and item[0] == 1 and isinstance(item[1], str):
            chunks.append(item[1])
    for chunk in chunks + [''.join(chunks)]:
        for match in re.finditer(r'(?:^|\n)[0-9a-f]+:', chunk):
            try:
                value, _ = json.JSONDecoder().raw_decode(chunk[match.end():])
            except ValueError:
                continue
            for obj in walk(value):
                if not isinstance(obj.get('jobs'), list):
                    continue
                return [Job('site:xsight', p['uid'], company, p['title'], urljoin(url, p['href']),
                            location=p['locationLong'], posted=p.get('timeUpdated', ''),
                            israel=p.get('location', {}).get('country') == 'IL',
                            extra={'detail_selector': '.jobs-detail-content'}) for p in obj['jobs']]
    raise ValueError('Xsight: complete job list missing')


def deloitte(http, company):
    url = 'https://careers.deloitte.co.il/positions/'
    doc = soup(http.get_text(url))
    container = doc.select_one('.positions-continer[data-total]')
    if container is None:
        raise ValueError('Deloitte: job list metadata missing')
    total = int(container['data-total'])
    endpoint = same_host_link(url, container['data-ajax-url'])
    out, seen = [], set()
    for page in range(100):
        batch = []
        for card in doc.select('.position-row'):
            a = card.select_one('a[href]')
            target = urljoin(url, a['href'])
            batch.append(Job('site:deloitte', unquote(urlparse(target).path.rstrip('/')), company,
                             text(card.select_one('.position-row-title')), target,
                             location=text(card.select_one('.position-location'))))
        unique_extend(out, batch, seen)
        if len(out) >= total:
            return out
        if not batch:
            raise ValueError('Deloitte: incomplete pagination')
        data = http._req('POST', endpoint, data={
            'action': 'deloitte_careers_load_more_positions_ajax', 'paged': page + 1,
            'department': '', 'location': '', 'interest': '', 'keywords': ''}).json()
        doc = soup(data['positions'])
    raise ValueError('Deloitte: pagination limit reached')
