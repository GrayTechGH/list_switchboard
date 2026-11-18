#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Write a registry-complete CSV catalog of built-in import lists."""

import argparse
import csv
import io
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / '_dev_tools' / 'import_list_catalog.csv'
PROGRESS_STATUS_PATH = ROOT / '_dev_tools' / 'import_progress_status.json'
sys.path.insert(0, str(ROOT))

from _dev_tools.import_update_audit import (  # noqa: E402
  DEFAULT_AUDIT_PATH, atomic_write_text, load_records,
)
from url_fetcher import available_url_fetchers  # noqa: E402


FIELDNAMES = (
  'registry_index',
  'order',
  'source_id',
  'name',
  'discontinued',
  'url',
  'filter_categories',
  'match_series',
  'requires_series_matching',
  'supports_incremental_update',
  'automatic_source_only',
  'source_choices',
  'Manual Test',
  'Update candidate',
  'Updates',
)


def bool_text(value):
  return 'true' if bool(value) else 'false'


def joined_labels(items):
  return ' | '.join(
    str(item.get('label') or '').strip()
    for item in items
    if str(item.get('label') or '').strip())


def manual_test_statuses(progress_status_path=PROGRESS_STATUS_PATH):
  try:
    data = json.loads(Path(progress_status_path).read_text(encoding='utf-8'))
  except (OSError, ValueError):
    return {}
  return {
    str(row.get('source_id') or ''): str(
      row.get('manual_status') or 'not_checked')
    for row in (data.get('recipes') or ())
    if row.get('source_id')
  }


def catalog_rows(fetchers=None, progress_status_path=PROGRESS_STATUS_PATH,
                 audit_status_path=DEFAULT_AUDIT_PATH):
  fetchers = tuple(fetchers if fetchers is not None else available_url_fetchers())
  manual_status = manual_test_statuses(progress_status_path)
  audit = load_records(audit_status_path)
  rows = []
  for index, fetcher in enumerate(fetchers, start=1):
    filters = tuple(fetcher.get_filter_list())
    source_choices = tuple(fetcher.source_choices())
    candidate = audit.get(fetcher.source_id, {}).get('candidate', '')
    if fetcher.NAME.endswith(' (discontinued)') and candidate == 'Yes':
      raise ValueError(f'{fetcher.source_id}: discontinued lists must be No.')
    rows.append({
      'registry_index': index,
      'order': fetcher.order,
      'source_id': fetcher.source_id,
      'name': fetcher.NAME,
      'discontinued': bool_text(fetcher.NAME.endswith(' (discontinued)')),
      'url': fetcher.display_url,
      'filter_categories': joined_labels(filters),
      'match_series': bool_text(fetcher.options.get('match_series', True)),
      'requires_series_matching': bool_text(
        getattr(fetcher, 'REQUIRES_SERIES_MATCHING', False)),
      'supports_incremental_update': bool_text(
        getattr(fetcher, 'SUPPORTS_INCREMENTAL_UPDATE', False)),
      'automatic_source_only': bool_text(len(source_choices) == 1),
      'source_choices': joined_labels(source_choices),
      'Manual Test': manual_status.get(fetcher.source_id, 'not_checked'),
      'Update candidate': candidate,
      'Updates': 'Yes' if getattr(fetcher, 'SUPPORTS_INCREMENTAL_UPDATE', False) else 'No',
    })
  return rows


def write_catalog(
    output_path=DEFAULT_OUTPUT, fetchers=None,
    progress_status_path=PROGRESS_STATUS_PATH, audit_status_path=DEFAULT_AUDIT_PATH):
  output_path = Path(output_path)
  rows = catalog_rows(fetchers, progress_status_path=progress_status_path,
    audit_status_path=audit_status_path)
  output = io.StringIO(newline='')
  writer = csv.DictWriter(output, fieldnames=FIELDNAMES, lineterminator='\n')
  writer.writeheader()
  writer.writerows(rows)
  atomic_write_text(output_path, output.getvalue(), encoding='utf-8-sig')
  return output_path, len(rows)


def parse_args(argv=None):
  parser = argparse.ArgumentParser(
    description='Create a CSV catalog of every registered import list.')
  parser.add_argument(
    '--output',
    type=Path,
    default=DEFAULT_OUTPUT,
    help=f'output path (default: {DEFAULT_OUTPUT})')
  parser.add_argument('--audit-ledger', type=Path, default=DEFAULT_AUDIT_PATH,
    help='persistent Update candidate decisions')
  return parser.parse_args(argv)


def main(argv=None):
  options = parse_args(argv)
  output_path, count = write_catalog(options.output, audit_status_path=options.audit_ledger)
  print(f'Wrote {count} import lists to {output_path}')


if __name__ == '__main__':
  main()
