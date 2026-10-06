"""Public Taleo legacy job list, with validated pagination and record schema."""
import re
from urllib.parse import unquote

from .pages import soup, unique_extend
from ..models import Job
from ..http import html_to_text


def parse(page, board, company):
    doc = soup(page)
    history = doc.select_one('input#initialHistory')
    if history is None:
        raise ValueError('Taleo: job list state missing')
    return parse_state(history['value'], board, company)


def parse_state(raw, board, company):
    total = re.search(r'listRequisition\.nbElements!\|!(\d+)', raw)
    if not total:
        raise ValueError('Taleo: result count missing')
    values = re.split(r'!%24!|!\$!', raw)[2].split('!|!')
    jobs = []
    for i in range(len(values) - 17):
        internal = values[i]
        if not internal.isdigit() or not (values[i+2] == internal == values[i+4] == values[i+5] == values[i+6] == values[i+7] == values[i+8]):
            continue
        if values[i+1] != values[i+3] or not re.fullmatch(r'[A-Z0-9]+', values[i+9]):
            raise ValueError('Taleo: unexpected job record schema')
        jid, location = values[i+9], values[i+10]
        jobs.append(Job(f'taleo:{board}', jid, company, values[i+1],
                        f'https://{board}.taleo.net/careersection/ex/jobdetail.ftl?job={jid}',
                        location=location, israel=True if 'IL-IL-' in location else None,
                        posted=values[i+17], extra={'detail_selector': '#requisitionDescriptionInterface'}))
    return jobs, int(total[1])


def fetch(http, board, company):
    url = f'https://{board}.taleo.net/careersection/ex/joblist.ftl'
    doc = soup(http.get_text(url + '?dropListSize=100'))
    history = doc.select_one('input#initialHistory')
    if history is None:
        raise ValueError('Taleo: job list state missing')
    raw = history['value']
    fields = {i['name']: i.get('value', '') for i in doc.select('form#ftlform input[name]')
              if i.get('type') not in {'checkbox', 'radio'}}
    out, seen = [], set()
    for page in range(1, 101):
        batch, total = parse_state(raw, board, company)
        unique_extend(out, batch, seen)
        if len(out) >= total:
            return out
        if not batch:
            raise ValueError('Taleo: incomplete pagination')
        values = re.split(r'!%24!|!\$!', raw)[3].split('!|!')
        fields.update(dict(zip(values[::2], values[1::2])))
        # Public job-list pagination component; no application or account action.
        fields.update({'ftlinterfaceid': 'requisitionListInterface', 'ftlcompid': 'rlPager',
                       'jsfCmdId': 'rlPager', 'ftlcompclass': 'PagerComponent',
                       'ftlcallback': 'ftlPager_processResponse', 'ftlajaxid': f'ftlx{page}',
                       'rlPager.currentPage': page + 1, 'dropListSize': 100})
        raw = http._req('POST', url.replace('.ftl', '.ajax'), data=fields).text
    raise ValueError('Taleo: pagination limit reached')


def details(http, board, job):
    doc = soup(http.get_text(job.url))
    history = doc.select_one('input#initialHistory')
    if history is None or 'descRequisition' not in history['value']:
        raise ValueError('Taleo: full job description unavailable')
    values = history['value'].split('!%24!')[2].split('!|!')
    if len(values) < 13 or values[10] != job.job_id:
        raise ValueError('Taleo: job detail identity mismatch')
    sections = [html_to_text(unquote(v.removeprefix('!*!'))) for v in values[11:13]]
    if not any(sections):
        raise ValueError('Taleo: empty description')
    job.description = sections[0] + '\nQualifications:\n' + sections[1]
