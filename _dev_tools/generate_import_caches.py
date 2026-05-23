#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Pre-generate parsed import cache files from registered URL fetchers.

This script mirrors the normal fetcher-facing import path closely enough to
produce ordinary `import_<list_id>.json` files that can be copied into
Calibre's `plugins/list_switchboard` storage folder.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import UnicodeDammit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))


from storage import build_import_cache_data, safe_list_id  # noqa: E402
from url_fetcher import available_url_fetchers  # noqa: E402


def decode_response(response):
  data = response.read()
  charset = response.headers.get_content_charset() if response.headers else None
  known_encodings = (charset,) if charset else ()
  decoded = UnicodeDammit(
    data,
    known_definite_encodings=known_encodings,
    is_html=True).unicode_markup
  if decoded:
    return decoded
  if charset:
    try:
      return data.decode(charset)
    except (LookupError, UnicodeDecodeError):
      pass
  for candidate in ('utf-8', 'windows-1252'):
    try:
      return data.decode(candidate)
    except (LookupError, UnicodeDecodeError):
      pass
  return data.decode(charset or 'utf-8', 'replace')


def load_source_text(source):
  source_text = str(source)
  if '://' not in source_text:
    return Path(source_text).read_text(encoding='utf-8')
  headers = {
    'User-Agent': (
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
      'AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'close',
  }
  request = Request(source_text, headers=headers)
  with urlopen(request, timeout=30) as response:
    return decode_response(response)


def memoized_loader(load_source=load_source_text):
  cache = {}

  def fetch(source):
    key = str(source)
    if key not in cache:
      cache[key] = load_source(source)
    return cache[key]

  fetch.cache = cache
  return fetch


def recipe_matches(fetcher, recipe_filters):
  if not recipe_filters:
    return True
  source_id = str(getattr(fetcher, 'source_id', '') or '')
  name = str(getattr(fetcher, 'NAME', '') or '')
  values = {
    source_id.casefold(),
    name.casefold(),
  }
  return any(filter_text.casefold() in values for filter_text in recipe_filters)


def output_path_for_fetcher(fetcher, output_dir):
  list_id = safe_list_id(getattr(fetcher, 'source_id', '') or fetcher.NAME)
  return Path(output_dir) / f'import_{list_id}.json'


def generate_cache_for_fetcher(
    fetcher, output_dir, fetch_source, force=False, emit=print):
  output_path = output_path_for_fetcher(fetcher, output_dir)
  if output_path.exists() and not force:
    emit(f'Skipped {fetcher.NAME}: {output_path.name} already exists')
    return {'status': 'skipped', 'fetcher': fetcher, 'path': output_path}

  emit(f'Fetching {fetcher.NAME}...')
  parsed = fetcher.fetch_and_parse(
    fetch_source,
    sleep=lambda *_args, **_kwargs: None,
    fetch_error=lambda *_args, **_kwargs: None,
    log=lambda message: emit(f'  {message}'),
    progress=lambda done, total, message: emit(f'  [{done}/{total}] {message}'))

  list_id = safe_list_id(getattr(fetcher, 'source_id', '') or fetcher.NAME)
  cache_data = build_import_cache_data(list_id, parsed, recipe=fetcher)
  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text(
    json.dumps(cache_data, indent=2, sort_keys=True) + '\n',
    encoding='utf-8')
  emit(f'Wrote {output_path.name}')
  return {
    'status': 'written',
    'fetcher': fetcher,
    'path': output_path,
    'entries': len(cache_data.get('entries') or []),
  }


def generate_import_caches(
    fetchers, output_dir, recipe_filters=None, force=False, fail_fast=False,
    load_source=load_source_text, emit=print):
  fetch_source = memoized_loader(load_source)
  results = []
  failures = []
  for fetcher in fetchers:
    if not recipe_matches(fetcher, recipe_filters):
      continue
    try:
      results.append(generate_cache_for_fetcher(
        fetcher, output_dir, fetch_source, force=force, emit=emit))
    except Exception as err:
      failure = {'fetcher': fetcher, 'error': err}
      failures.append(failure)
      emit(f'Failed {fetcher.NAME}: {err}')
      if fail_fast:
        raise
  return results, failures, fetch_source.cache


def parse_args(argv=None):
  parser = argparse.ArgumentParser(
    description='Generate ordinary import_<list_id>.json cache files from registered fetchers.')
  parser.add_argument(
    '--output',
    default=str(ROOT / '_dev_tools' / 'generated_import_caches'),
    help='Output directory for generated import cache files.')
  parser.add_argument(
    '--recipe',
    action='append',
    dest='recipes',
    default=[],
    help='Limit generation to an exact recipe source_id or display name. Repeatable.')
  parser.add_argument(
    '--force',
    action='store_true',
    help='Overwrite existing generated files.')
  parser.add_argument(
    '--fail-fast',
    action='store_true',
    help='Stop on the first recipe failure instead of continuing.')
  return parser.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  fetchers = available_url_fetchers()
  results, failures, _cache = generate_import_caches(
    fetchers,
    args.output,
    recipe_filters=args.recipes,
    force=args.force,
    fail_fast=args.fail_fast)
  written = sum(1 for result in results if result.get('status') == 'written')
  skipped = sum(1 for result in results if result.get('status') == 'skipped')
  print(
    f'Finished cache generation: {written} written, '
    f'{skipped} skipped, {len(failures)} failed.')
  return 1 if failures else 0


if __name__ == '__main__':
  raise SystemExit(main())
