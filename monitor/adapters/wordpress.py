"""Public WordPress job listings. Total-page headers prevent silent truncation."""
from .pages import unique_extend, description
from ..http import html_to_text
from ..models import Job


def fetch(http, board, company):
    out, seen = [], set()
    for page in range(1, 101):
        response = http._req('GET', board, params={'per_page': 100, 'page': page})
        data = response.json()
        if not isinstance(data, list) or 'X-WP-TotalPages' not in response.headers:
            raise ValueError('WordPress: missing posts or pagination metadata')
        batch = []
        for p in data:
            body = html_to_text(p.get('content', {}).get('rendered'))
            batch.append(Job(f'wordpress:{board}', str(p['id']), company,
                             html_to_text(p['title']['rendered']), p['link'],
                             location='Israel', israel=True, description=body or None,
                             posted=p.get('date', ''),
                             extra={'detail_selector': '.elementor-location-single .elementor-element-b5aaf32'}))
        unique_extend(out, batch, seen)
        if page >= int(response.headers['X-WP-TotalPages']):
            if len(out) != int(response.headers['X-WP-Total']):
                raise ValueError('WordPress: result count changed or pagination incomplete')
            return out
        if not batch:
            raise ValueError('WordPress: empty intermediate page')
    raise ValueError('WordPress: pagination limit reached')


details = description
