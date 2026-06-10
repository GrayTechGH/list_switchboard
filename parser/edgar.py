#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Edgar Award parser for official category database pages.

Maintenance notes:
- The official site exposes category pages as paginated tables, but may return
  an anti-bot verification page to normal fetchers. Empty/unusable official
  results are expected to be handled by the fetcher's source fallback.
- Bold table rows denote winners on the official category pages.
"""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from lxml import html as lxml_html

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, assign_positions, normalize_heading, normalize_line,
    strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    AwardParserBase, assign_positions, normalize_heading, normalize_line,
    strip_publication_notes,
  )
  from .generic import position_sort_key


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
            fetch_url=None, log=None, progress=None):
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
      author = self.clean_author(values.get('author s name'))
      if year is None or not title or not author:
        continue
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
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
    return bool(row.xpath('.//strong|.//b'))

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
