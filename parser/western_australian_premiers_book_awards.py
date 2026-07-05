#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Western Australian Premier's Book Awards parser.

Maintenance notes:
- Wikipedia is the V1 parsed source because it exposes structured honorees
  tables. The official State Library of WA archive is reference-only until it
  exposes a stable nominee-complete structure.
- V1 keeps published-book categories only and skips fellowship, unpublished
  manuscript, script, digital, poetry, history-only, and special/person rows.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key


AWARD_NAME = "Western Australian Premier's Book Awards"
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Western_Australian_Premier%27s_Book_Awards'

HEADER_ALIASES = {
  'award': 'category',
  'category': 'category',
  'prize': 'category',
  'author': 'author',
  'authors': 'author',
  'writer': 'author',
  'writers': 'author',
  'title': 'title',
  'book': 'title',
  'work': 'title',
  'result': 'result',
  'status': 'result',
  'year': 'year',
}

SKIP_CATEGORY_KEYS = {
  'daisy utemorrah award',
  'digital narrative',
  'history',
  'poetry',
  'script',
  'special award',
  'wa history',
  'wa writer s fellowship',
  'wa writers fellowship',
  'western australian writer s fellowship',
  'western australian writers fellowship',
  'writer s fellowship',
  'writers fellowship',
}


def _category_key(value):
  value = normalize_heading(value)
  return value.replace('non fiction', 'nonfiction')


class WesternAustralianPremiersBookAwardsWikipediaParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def __init__(self, category, category_aliases=()):
    self.category = category
    self.category_aliases = tuple(category_aliases or (category,))
    self.category_keys = {_category_key(alias) for alias in self.category_aliases}

  def parse(self, html, base_url=WIKIPEDIA_URL, name=AWARD_NAME, **_kwargs):
    rows = self.parse_rows(html, base_url)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for table in soup.find_all('table'):
      grid = self.table_grid(table)
      header_index, header_map = self.header_map(grid)
      if not {'year', 'title', 'author'}.issubset(set(header_map)):
        continue
      rows.extend(self.table_rows(grid[header_index + 1:], header_map, base_url))
    return rows

  def table_grid(self, table):
    grid = []
    rowspans = {}
    for tr in table.find_all('tr'):
      row = []
      column = 0
      for cell in tr.find_all(['th', 'td'], recursive=False):
        while column in rowspans:
          span_cell, remaining = rowspans[column]
          row.append(span_cell)
          if remaining <= 1:
            del rowspans[column]
          else:
            rowspans[column] = (span_cell, remaining - 1)
          column += 1
        colspan = self.span_value(cell, 'colspan')
        rowspan = self.span_value(cell, 'rowspan')
        for _index in range(colspan):
          row.append(cell)
          if rowspan > 1:
            rowspans[column] = (cell, rowspan - 1)
          column += 1
      while column in rowspans:
        span_cell, remaining = rowspans[column]
        row.append(span_cell)
        if remaining <= 1:
          del rowspans[column]
        else:
          rowspans[column] = (span_cell, remaining - 1)
        column += 1
      if row:
        grid.append(row)
    return grid

  def span_value(self, cell, attribute):
    try:
      return max(1, int(cell.get(attribute, 1)))
    except Exception:
      return 1

  def header_map(self, grid):
    for row_index, row in enumerate(grid):
      mapped = {}
      for index, cell in enumerate(row):
        key = HEADER_ALIASES.get(normalize_heading(self.clean_text(cell)))
        if key is not None and key not in mapped:
          mapped[key] = index
      if {'year', 'title', 'author'}.issubset(set(mapped)):
        return row_index, mapped
    return 0, {}

  def table_rows(self, grid, header_map, base_url):
    rows = []
    current_year = None
    current_category = ''
    current_result = None
    for row in grid:
      year = self.year_from_text(self.cell_text(row, header_map, 'year')) or current_year
      if year is None:
        continue
      current_year = year

      category = self.cell_text(row, header_map, 'category') or current_category
      if category:
        current_category = category
      if self.category_is_skipped(category) or not self.category_matches(category):
        continue

      result = self.result_from_text(self.cell_text(row, header_map, 'result'))
      if result is not None:
        current_result = result
      elif current_result == RESULT_SHORTLISTED:
        result = RESULT_SHORTLISTED
      elif 'result' not in header_map:
        result = RESULT_WINNER
      else:
        result = current_result
      if result not in {RESULT_WINNER, RESULT_SHORTLISTED}:
        continue

      title_cell = self.cell_for_key(row, header_map, 'title')
      title = self.clean_title(self.clean_text(title_cell))
      author = self.clean_author(self.cell_text(row, header_map, 'author'))
      if not title or not author:
        continue
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': self.first_link_url(title_cell, base_url) or base_url,
        'category': self.category,
      })
    return rows

  def cell_for_key(self, row, header_map, key):
    index = header_map.get(key)
    if index is None or index < 0 or index >= len(row):
      return None
    return row[index]

  def cell_text(self, row, header_map, key):
    return self.clean_text(self.cell_for_key(row, header_map, key))

  def category_matches(self, value):
    return _category_key(value) in self.category_keys

  def category_is_skipped(self, value):
    key = _category_key(value)
    return key in SKIP_CATEGORY_KEYS

  def result_from_text(self, value):
    key = normalize_heading(value)
    if not key:
      return None
    if key.startswith('winner') or key in {'won'}:
      return RESULT_WINNER
    if key.startswith('shortlist') or key.startswith('finalist') or key.startswith('honour'):
      return RESULT_SHORTLISTED
    return None

  def clean_text(self, node):
    if node is None:
      return ''
    node = BeautifulSoup(str(node), 'html.parser')
    for removable in node.find_all(['script', 'style', 'sup']):
      removable.decompose()
    return normalize_line(node.get_text(' ', strip=True).replace('\xa0', ' '))

  def clean_title(self, value):
    value = strip_publication_notes(normalize_line(value))
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def clean_author(self, value):
    value = strip_publication_notes(normalize_line(value))
    value = re.sub(r'^\s*(?:by|author|writer)\s*:?\s*', '', value, flags=re.I)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True) if node is not None else None
    return urljoin(base_url, link['href']) if link is not None else ''

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def dedupe_rows(self, rows):
    deduped = []
    seen = set()
    for row in rows:
      key = (
        row.get('award_year'),
        _category_key(row.get('category', '')),
        normalize_heading(row.get('title', '')),
        normalize_heading(row.get('author', '')),
      )
      if not key[2] or not key[3] or key in seen:
        continue
      seen.add(key)
      deduped.append(row)
    return deduped

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      try:
        year = int(row['award_year'])
      except Exception:
        continue
      by_year.setdefault(year, []).append(row)

    entries = []
    for year in sorted(by_year):
      year_rows = sorted(
        by_year[year],
        key=lambda row: 0 if row.get('result') == RESULT_WINNER else 1)
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in year_rows
      ]
      entries.extend(assign_positions(
        award_rows, year, tied_winners_share_position=True))
    return entries


def parse_western_australian_premiers_book_awards(
    html, category, category_aliases=(), url=WIKIPEDIA_URL, name=AWARD_NAME):
  return WesternAustralianPremiersBookAwardsWikipediaParser(
    category, category_aliases).parse(html, url, name)
