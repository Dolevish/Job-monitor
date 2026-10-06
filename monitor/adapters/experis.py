"""The read-only job search used by Experis Israel's public website."""
from .pages import unique_extend
from ..http import html_to_text
from ..models import Job

QUERY = '''query SearchByFilter($where: RootQueryToJobConnectionWhereArgs) {
  allJob(where: $where) {
    nodes { title databaseId uri jobFields { jobcode jobdescription }
            jobAreas { nodes { name } } }
    pageInfo { offsetPagination { hasMore total } }
  }
}'''


def fetch(http, board, company):
    out, seen = [], set()
    for offset in range(0, 10000, 100):
        data = http.post_json('https://experiscontent.experis.co.il/graphql', {
            'query': QUERY, 'variables': {'where': {'offsetPagination': {'offset': offset, 'size': 100}}}})
        if data.get('errors'):
            raise ValueError('Experis: GraphQL search failed')
        result = data['data']['allJob']
        batch = []
        for p in result['nodes']:
            body = html_to_text(p['jobFields']['jobdescription'])
            batch.append(Job(f'experis:{board}', str(p['databaseId']), company, p['title'] or f"משרה {p['jobFields']['jobcode']} (כותרת חסרה במקור)",
                             'https://experis.co.il' + p['uri'], israel=True,
                             location=', '.join(n['name'] for n in p['jobAreas']['nodes']),
                             description=body or None))
        unique_extend(out, batch, seen)
        info = result['pageInfo']['offsetPagination']
        if not info['hasMore']:
            if len(out) != int(info['total']):
                raise ValueError('Experis: incomplete result count')
            return out
        if not batch:
            raise ValueError('Experis: empty intermediate page')
    raise ValueError('Experis: pagination limit reached')
