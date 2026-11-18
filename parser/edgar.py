#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Edgar Award parser for official category database pages.

Maintenance notes:
- The official site exposes category pages as paginated tables, but may return
  an anti-bot verification page to normal fetchers. Empty/unusable official
  results are expected to be handled by the fetcher's source fallback.
- The official CSS class `edgar-winner` makes winner rows bold. Older captures
  may instead contain literal `strong` or `b` elements.
"""

import re
import json
import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from lxml import html as lxml_html

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, assign_positions, is_author_suffix, normalize_heading,
    normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
  from calibre_plugins.list_switchboard.parser.incremental import (
    ParsedUnitCache, project_source_rows, restore_source_rows)
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError
except ImportError:
  from .award_base import (
    AwardParserBase, assign_positions, is_author_suffix, normalize_heading,
    normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key
  from .incremental import ParsedUnitCache, project_source_rows, restore_source_rows
  from errors import ImportCancelledError, CamoufoxRequiredError


AWARD_NAME = 'Edgar Award'
PAGE_SIZE = 100
MAX_PAGES = 50


class EdgarAwardsParser(AwardParserBase):
  """
  Parses official Edgar category tables into the shared award-entry contract.

  Invariants:
  - The first page is supplied by the fetcher; additional pages are optional and
    fetched only when the page reports more rows than the first page contains.
  - Rows without both a title and author are skipped because several Edgar
    categories are people, TV, magazine, store, or organization awards.
  """

  AWARD_NAME = AWARD_NAME

  def parse(self, html, base_url, name, category,
            fetch_url=None, log=None, progress=None, cached_parsed=None,
            incremental_update=False, enable_incremental=False):
    if enable_incremental:
      return self.parse_with_year_cache(html, base_url, name, category,
        fetch_url, log, progress, cached_parsed, incremental_update)
    notes = []
    rows = self.parse_page(html, base_url, category)
    pages_seen = {base_url}
    total_records = self.total_records(html)
    page_count = self.page_count(total_records) if total_records is not None else 1
    self._progress(progress, 1, page_count, f'Parsed {name} page 1...')

    page_number = 2
    while fetch_url is not None and page_number <= min(page_count, MAX_PAGES):
      url = self.page_url(base_url, page_number)
      if url in pages_seen:
        break
      pages_seen.add(url)
      try:
        page_html = fetch_url(url)
      except Exception as err:
        notes.append(f'{AWARD_NAME} page {page_number} could not be fetched: {err}')
        self._log(log, 'fetch-failed', {'url': url, 'error': str(err)})
        break
      page_rows = self.parse_page(page_html, url, category)
      if not page_rows:
        break
      rows.extend(page_rows)
      self._progress(progress, page_number, page_count,
                     f'Parsed {name} page {page_number}...')
      page_number += 1

    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes)

  def parse_with_year_cache(self, html, base_url, name, category,
      fetch_url, log, progress, cached_parsed, incremental_update):
    cache = ParsedUnitCache('edgar-ordered-ballots-v1',
      json.dumps([base_url, name, category, PAGE_SIZE, type(self).__name__]),
      cached_parsed, incremental_update)
    total = self.total_records(html)
    first = self.parse_page(html, base_url, category)
    original = {}
    for key, unit in cache.old_units.items():
      try:
        original[key] = restore_source_rows(cache.previous(key), unit.get('metadata') or {})
      except (ValueError, TypeError):
        continue
    rows = self.reuse_ordered_tail(first, total, cache, original)
    notes = []
    complete = True
    pages = self.page_count(total) if total is not None else 1
    self._progress(progress, 1, pages, f'Parsed {name} page 1...')
    if rows is None:
      rows = list(first)
      for number in range(2, min(pages, MAX_PAGES) + 1):
        try:
          page_rows = self.parse_page(fetch_url(self.page_url(base_url, number)),
            self.page_url(base_url, number), category)
          if not page_rows:
            raise ValueError('No usable Edgar table rows.')
          rows.extend(page_rows)
        except (ImportCancelledError, CamoufoxRequiredError):
          raise
        except Exception as err:
          notes.append(f'{AWARD_NAME} page {number} could not be fetched or parsed: {err}')
          complete = False
          break
        self._progress(progress, number, pages, f'Parsed {name} page {number}...')
      complete = complete and total is not None and len(rows) == total
      if not complete and rows:
        boundary = min(int(row['award_year']) for row in rows)
        # The last fetched page may end inside a ballot. Keep its prior whole
        # year rather than mixing a promoted fresh winner with stale nominees.
        if original.get(str(boundary)):
          rows = [row for row in rows if int(row['award_year']) > boundary] + original[str(boundary)]
        for year, old_rows in original.items():
          if int(year) < boundary:
            rows.extend(old_rows)
    entries = sorted(self.entries_from_rows(rows),
      key=lambda item: position_sort_key(item.get('position', '')))
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    for year, year_rows in by_year.items():
      projected, metadata = project_source_rows(year_rows, entries,
        lambda row: (str(row['award_year']), row['title'], tuple(row['authors'])))
      metadata['settled'] = any(row['result'] == 'winner' for row in year_rows)
      cache.put(str(year), projected, revision=str(year), complete=complete, metadata=metadata)
    state = cache.state(entries)
    state['discovery'] = {'total': total,
      'row_order': [self.row_identity(row) for row in rows],
      'refresh_units': [str(max(int(year) for year in by_year))] if by_year else []}
    result = self.parsed_result(name, base_url, entries, notes)
    result['incremental_state'] = state
    return result

  def row_identity(self, row):
    return json.dumps([str(row['award_year']), row['title'], row['authors'],
      row['category'], row['result']], ensure_ascii=False, separators=(',', ':'))

  def reuse_ordered_tail(self, first, total, cache, original):
    """Cut off only at a contiguous cached suffix with a whole settled ballot.

    The advertised count must explain the changed front exactly. Page offsets
    never identify cached rows; recompute page provenance after inserts shift
    the historical tail. Missing/pending/unsettled tail units force a full crawl.
    """
    order = cache.old_discovery.get('row_order')
    old_total = cache.old_discovery.get('total')
    if (not first or type(total) is not int or type(old_total) is not int or
        not isinstance(order, list) or len(order) != old_total or
        any(not isinstance(key, str) for key in order) or len(set(order)) != len(order) or
        len(first) != min(total, PAGE_SIZE)):
      return None
    fresh = [self.row_identity(row) for row in first]
    if len(set(fresh)) != len(fresh):
      return None
    positions = {key: index for index, key in enumerate(order)}
    known = {self.row_identity(row): row for rows in original.values() for row in rows}
    latest = max(int(row['award_year']) for row in first)
    for offset, key in enumerate(fresh):
      anchor = positions.get(key)
      if anchor is None or fresh[offset:] != order[anchor:anchor+len(fresh)-offset]:
        continue
      current_order = fresh[:offset] + order[anchor:]
      if (len(current_order) != total or len(set(current_order)) != total or
          any(key not in known for key in order[anchor+len(fresh)-offset:])):
        continue
      matched = set(fresh[offset:])
      whole_ballot = False
      for year, rows in original.items():
        identities = {self.row_identity(row) for row in rows}
        if (identities and identities <= matched and int(year) < min(latest, datetime.datetime.now().year) and
            (cache.old_units[year].get('metadata') or {}).get('settled') is True):
          whole_ballot = True
      tail = [known[key] for key in order[anchor+len(fresh)-offset:]]
      if not whole_ballot or any(
          int(row['award_year']) >= min(latest, datetime.datetime.now().year) or
          cache.old_units[str(row['award_year'])].get('complete') is not True or
          (cache.old_units[str(row['award_year'])].get('metadata') or {}).get('settled') is not True
          for row in tail):
        continue
      rows = list(first) + [dict(row) for row in tail]
      if [int(row['award_year']) for row in rows] != sorted(
          (int(row['award_year']) for row in rows), reverse=True):
        continue
      for index, row in enumerate(rows):
        row['source_url'] = self.page_url(first[0]['source_url'], index // PAGE_SIZE + 1) if index >= PAGE_SIZE else first[0]['source_url']
      return rows
    return None

  def parse_page(self, html, source_url, default_category):
    root = lxml_html.fromstring(html or '<html></html>')
    rows = []
    for table in root.xpath('//table'):
      headers = self.table_headers(table)
      if not self.has_award_headers(headers):
        continue
      rows.extend(self.table_rows(table, headers, source_url, default_category))
    return rows

  def table_headers(self, table):
    first_rows = table.xpath('.//tr')
    if not first_rows:
      return []
    cells = self.direct_cells(first_rows[0], include_headers=True)
    return [normalize_heading(self.node_text(cell)) for cell in cells]

  def has_award_headers(self, headers):
    required = {'award year', 'award category', 'title', 'author s name'}
    return required.issubset(set(headers))

  def table_rows(self, table, headers, source_url, default_category):
    rows = []
    for tr in table.xpath('.//tr')[1:]:
      cells = self.direct_cells(tr, include_headers=True)
      if len(cells) < len(headers):
        continue
      values = {
        headers[index]: self.node_text(cells[index])
        for index in range(min(len(headers), len(cells)))
      }
      year = self.year_from_text(values.get('award year'))
      title = self.clean_title(values.get('title'))
      authors = self.clean_authors(values.get('author s name'))
      if year is None or not title or not authors:
        continue
      rows.append({
        'award_year': str(year),
        'title': title,
        'authors': authors,
        'result': 'winner' if self.row_is_winner(tr) else 'nominee',
        'source_url': source_url,
        'category': values.get('award category') or default_category,
      })
    return rows

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in by_year[year]
      ]
      entries.extend(assign_positions(award_rows, int(year)))
    return entries

  def total_records(self, html):
    match = re.search(r'Total\s+Records\s+Found:\s*([0-9,]+)', html or '', re.I)
    if match is None:
      return None
    return int(match.group(1).replace(',', ''))

  def page_count(self, total_records):
    if total_records <= 0:
      return 1
    return (total_records + PAGE_SIZE - 1) // PAGE_SIZE

  def page_url(self, base_url, page_number):
    split = urlsplit(base_url)
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    query['instance'] = '1'
    query['listpage'] = str(page_number)
    return urlunsplit((
      split.scheme,
      split.netloc,
      split.path,
      urlencode(query),
      split.fragment,
    ))

  def row_is_winner(self, row):
    return bool(row.xpath('''
      descendant-or-self::*[
        contains(concat(" ", normalize-space(@class), " "), " edgar-winner ")
      ] | .//strong | .//b
    '''))

  def direct_cells(self, row, include_headers=False):
    selector = './td|./th' if include_headers else './td'
    return row.xpath(selector)

  def node_text(self, node):
    return normalize_line(' '.join(
      text.strip() for text in node.xpath('.//text()') if text.strip()))

  def year_from_text(self, value):
    match = re.search(r'(19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def clean_title(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    return strip_publication_notes(normalize_line(value)).strip()

  def clean_authors(self, value):
    """Split the bounded official author cell without splitting suffixes."""
    value = self.clean_author(value)
    parts = re.split(
      r'\s*(?:,\s*(?:and\s+)?|;\s*|&|\band\b)\s*', value, flags=re.I)
    authors = []
    for part in parts:
      part = normalize_line(part).strip(' ,;')
      if not part:
        continue
      if is_author_suffix(part) and authors:
        authors[-1] = f'{authors[-1]}, {part}'
      elif part not in authors:
        authors.append(part)
    return authors

  def _log(self, log, label, data):
    if log is not None:
      log(f'{AWARD_NAME} {label}: {data}')

  def _progress(self, progress, done, total, message):
    if progress is not None:
      progress(done, total, message)


def parse_edgar_awards(
    html, base_url, name, category, fetch_url=None, log=None, progress=None):
  return EdgarAwardsParser().parse(
    html,
    base_url,
    name,
    category,
    fetch_url=fetch_url,
    log=log,
    progress=progress)
