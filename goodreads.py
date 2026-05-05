#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Goodreads lookup and recovery helpers.

Maintenance notes:
- Goodreads is best-effort enrichment. Network failures, parse failures, or
  missing BeautifulSoup must produce empty results rather than abort imports.
- self.goodreads_series_cache stores both book lookups keyed by Goodreads id and
  source-page lookups keyed as "source:{url}".
- GOODREADS_LOOKUP_DELAY_SECONDS throttles both book and source lookups. Keep
  the shared last_goodreads_lookup_time so mixed lookup types do not burst.
"""

import json
import time
from collections import OrderedDict

try:
  from bs4 import BeautifulSoup
except Exception:
  BeautifulSoup = None

try:
  from calibre_plugins.list_switchboard.matching import normalize_key, normalize_match_text
except ImportError:
  from matching import normalize_key, normalize_match_text


GOODREADS_LOOKUP_DELAY_SECONDS = 1.5


def unique_case_insensitive(names):
  seen = OrderedDict()
  for name in names:
    key = normalize_key(name)
    if key and key not in seen:
      seen[key] = name.strip()
  return list(seen.values())


class GoodreadsMixin:
  """
  Looks up Goodreads series/source data during import recovery.

  Type constraints:
  - self.fetch_url(), self.sleep_with_events(), self.update_import_progress(),
    and debug helpers are expected on self through ListSwitchboardCore.
  - self.db.new_api.field_for('identifiers', ...) must return an identifier
    mapping for goodreads_id_for_book().

  Invariants:
  - Public lookup methods return empty lists/dicts on failure, never None.
  - Cache values are immutable-by-convention within a single import run.

  Refactor warning:
  - Do not make Goodreads lookup mandatory for normal matching. It is a fallback
    path and should not block direct title/series matches.
  """

  def identifiers_for_book(self, book_id):
    try:
      identifiers = self.db.new_api.field_for('identifiers', book_id, default_value={}) or {}
      return identifiers if isinstance(identifiers, dict) else {}
    except Exception:
      return {}

  def goodreads_id_for_book(self, book_id):
    identifiers = self.identifiers_for_book(book_id)
    for key in ('goodreads', 'gr'):
      value = identifiers.get(key)
      if value:
        return str(value).strip()
    return ''

  def fetch_goodreads_series_names(self, goodreads_id):
    if not goodreads_id:
      return []
    if goodreads_id in self.goodreads_series_cache:
      return self.goodreads_series_cache[goodreads_id]

    elapsed = time.time() - self.last_goodreads_lookup_time
    if elapsed < GOODREADS_LOOKUP_DELAY_SECONDS:
      delay = GOODREADS_LOOKUP_DELAY_SECONDS - elapsed
      self.debug_goodreads_throttled(delay)
      self.sleep_with_events(delay, f'Waiting before Goodreads lookup for book {goodreads_id}...')

    url = f'https://www.goodreads.com/book/show/{goodreads_id}'
    self.update_import_progress(message=f'Looking up Goodreads book {goodreads_id}...')
    self.debug_goodreads_lookup_url(url)
    self.last_goodreads_lookup_time = time.time()
    try:
      html = self.fetch_url(url)
      series_names = self.extract_goodreads_series_names(html)
    except Exception as err:
      self.debug_goodreads_lookup_failed(goodreads_id, err)
      series_names = []
    self.goodreads_series_cache[goodreads_id] = series_names
    self.debug_goodreads_lookup_result(goodreads_id, series_names)
    return series_names

  def fetch_goodreads_source_data(self, url):
    if not url or 'goodreads.com/' not in url:
      return {'series_names': [], 'books': []}
    cache_key = f'source:{url}'
    if cache_key in self.goodreads_series_cache:
      return self.goodreads_series_cache[cache_key]

    elapsed = time.time() - self.last_goodreads_lookup_time
    if elapsed < GOODREADS_LOOKUP_DELAY_SECONDS:
      delay = GOODREADS_LOOKUP_DELAY_SECONDS - elapsed
      self.debug_goodreads_throttled(delay, source=True)
      self.sleep_with_events(delay, 'Waiting before Goodreads source lookup...')

    self.debug_goodreads_lookup_url(url, source=True)
    self.update_import_progress(message='Looking up Goodreads source page...')
    self.last_goodreads_lookup_time = time.time()
    try:
      html = self.fetch_url(url)
      data = self.extract_goodreads_source_data(html)
    except Exception as err:
      self.debug_goodreads_lookup_failed(url, err, source=True)
      data = {'series_names': [], 'books': []}
    self.goodreads_series_cache[cache_key] = data
    self.debug_goodreads_source_result(data)
    return data

  def extract_goodreads_source_data(self, html):
    if BeautifulSoup is None:
      return {'series_names': [], 'books': []}
    soup = BeautifulSoup(html or '', 'html.parser')
    series_names = []
    heading = soup.find('h1')
    if heading is not None:
      series_names.append(heading.get_text(' ', strip=True))

    books = []
    seen_titles = set()
    for link in soup.find_all('a', href=True):
      href = link.get('href') or ''
      title = link.get_text(' ', strip=True)
      if not title or '/book/show/' not in href:
        continue
      title_key = normalize_match_text(title)
      if not title_key or title_key in seen_titles:
        continue
      seen_titles.add(title_key)
      container = link.find_parent(['div', 'li', 'tr'])
      author = ''
      if container is not None:
        author_link = container.find('a', href=lambda value: value and '/author/show/' in value)
        if author_link is not None:
          author = author_link.get_text(' ', strip=True)
      books.append({'title': title, 'author': author})
    return {'series_names': unique_case_insensitive(series_names), 'books': books}

  def extract_goodreads_series_names(self, html):
    if BeautifulSoup is None:
      return []
    soup = BeautifulSoup(html or '', 'html.parser')
    script_node = soup.find('script', attrs={'id': '__NEXT_DATA__'})
    if script_node is None:
      return []
    raw_payload = script_node.string or script_node.get_text() or ''
    try:
      payload = json.loads(raw_payload)
    except Exception as err:
      self.debug_goodreads_json_failed(err)
      return []
    values = []
    self.collect_goodreads_series_values(payload, values)
    return unique_case_insensitive(values)

  def collect_goodreads_series_values(self, node, values):
    if isinstance(node, list):
      for item in node:
        self.collect_goodreads_series_values(item, values)
      return
    if not isinstance(node, dict):
      return

    typename = str(node.get('__typename') or '').casefold()
    if 'series' in typename:
      for key in ('title', 'name', 'seriesTitle'):
        value = node.get(key)
        if value:
          values.append(str(value))
    for key in ('series', 'bookSeries', 'primarySeries'):
      value = node.get(key)
      if isinstance(value, str):
        values.append(value)
      elif isinstance(value, (dict, list)):
        self.collect_goodreads_series_values(value, values)

    for child in node.values():
      if isinstance(child, (dict, list)):
        self.collect_goodreads_series_values(child, values)

  def debug_import_goodreads_candidates(self, entry, candidates):
    self.debug_log(
      f'import Goodreads recovery entry={entry.get("title", "")} candidates={candidates}',
      section='import')

  def debug_import_goodreads_source_candidates(self, entry, data, candidates):
    self.debug_log(
      f'import Goodreads source recovery entry={entry.get("title", "")} '
      f'series={data.get("series_names", [])} books={len(data.get("books", []))} '
      f'candidates={candidates}', section='import')

  def debug_goodreads_throttled(self, delay, source=False):
    name = 'source lookup' if source else 'lookup'
    self.debug_log(f'Goodreads {name} throttled for {delay:.2f}s', section='goodreads')

  def debug_goodreads_lookup_url(self, url, source=False):
    name = 'source lookup' if source else 'lookup'
    self.debug_log(f'Goodreads {name} url={url}', section='goodreads')

  def debug_goodreads_lookup_failed(self, identifier, err, source=False):
    if source:
      self.debug_log(f'Goodreads source lookup failed url={identifier}: {err}', section='goodreads')
    else:
      self.debug_log(f'Goodreads lookup failed id={identifier}: {err}', section='goodreads')

  def debug_goodreads_lookup_result(self, goodreads_id, series_names):
    self.debug_log(f'Goodreads lookup id={goodreads_id} series={series_names}', section='goodreads')

  def debug_goodreads_source_result(self, data):
    self.debug_log(
      f'Goodreads source lookup series={data.get("series_names", [])} '
      f'books={len(data.get("books", []))}', section='goodreads')

  def debug_goodreads_json_failed(self, err):
    self.debug_log(f'Goodreads JSON parse failed: {err}', section='goodreads')
