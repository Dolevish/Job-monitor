"""Coverage reports count company entries separately from deduplicated feeds."""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .adapters import ADAPTERS, source_key


def report(companies, plans, results, notes=None):
    by_source = {r.feed.key: r for r in results}
    rows = []
    for c in companies:
        state, found = plans[c['name']]
        row = {'company': c['name'], 'status': 'unavailable', 'source': None,
               'secondary': c.get('status') == 'secondary', 'jobs': None,
               'detail_errors': 0, 'note': (notes or {}).get(c['name']) or c.get('note', '')}
        if state == 'ready' and found and found[0] in ADAPTERS:
            row['source'] = source_key(*found)
            r = by_source[row['source']]
            row.update(jobs=r.fetched, detail_errors=len(r.detail_errors), seconds=round(r.seconds, 2))
            row['status'] = 'failed' if r.error else ('partial' if r.detail_errors else ('ok' if r.fetched else 'empty'))
            if r.error:
                row['note'] = r.error
        rows.append(row)
    counts = Counter(row['status'] for row in rows)
    return {'checked_at': datetime.now(timezone.utc).isoformat(), 'configured': len(rows),
            'polled_entries': len(rows) - counts['unavailable'], 'feeds': len(results),
            'successful_entries': counts['ok'], 'empty_entries': counts['empty'],
            'partial_entries': counts['partial'], 'failed_entries': counts['failed'],
            'skipped': counts['unavailable'],
            'secondary_entries': sum(row['secondary'] for row in rows),
            'companies': rows}


def output(data, path=None):
    print('coverage: ' + ' '.join(f'{k}={v}' for k, v in data.items() if k not in {'companies', 'checked_at'}))
    for row in data['companies']:
        if row['status'] not in {'ok'}:
            note = row['note'] or ('No listings returned; verify the source' if row['status'] == 'empty'
                                   else f"{row['detail_errors']} detail errors" if row['status'] == 'partial'
                                   else 'No supported source configured')
            print(f"    COVERAGE {row['status']:11} {row['company']}: {note}")
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
