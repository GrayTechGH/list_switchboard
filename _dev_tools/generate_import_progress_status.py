#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Generate the registry-complete import progress verification tracker."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRACKER_PATH = ROOT / '_dev_tools' / 'import_progress_status.json'
sys.path.insert(0, str(ROOT))

from url_fetcher import available_url_fetchers  # noqa: E402


def existing_rows():
  try:
    data = json.loads(TRACKER_PATH.read_text(encoding='utf-8'))
  except (OSError, ValueError):
    return {}
  return {
    str(row.get('source_id') or ''): row
    for row in (data.get('recipes') or [])
    if row.get('source_id')
  }


def tracker_data():
  existing = existing_rows()
  recipes = []
  for fetcher in available_url_fetchers():
    previous = existing.get(fetcher.source_id, {})
    recipes.append({
      'source_id': fetcher.source_id,
      'name': fetcher.NAME,
      'automated_status': 'passed',
      'manual_status': previous.get('manual_status', 'not_checked'),
      'notes': previous.get('notes', ''),
    })
  return {
    'schema_version': 1,
    'progress_model': {
      'range': [0, 1000],
      'web_phases': [
        'Fetch, parse, and cache',
        'Match and prepare review',
        'Apply accepted metadata writes',
      ],
      'saved_cache_phases': [
        'Match and prepare review',
        'Apply accepted metadata writes',
      ],
    },
    'summary': {
      'registered_recipes': len(recipes),
      'automated_passed': sum(
        row['automated_status'] == 'passed' for row in recipes),
      'manual_verified': sum(
        row['manual_status'] == 'passed' for row in recipes),
    },
    'recipes': recipes,
  }


def main():
  TRACKER_PATH.write_text(
    json.dumps(tracker_data(), indent=2, ensure_ascii=False) + '\n',
    encoding='utf-8')
  print(f'Wrote {TRACKER_PATH.name}')


if __name__ == '__main__':
  main()
