#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Reusable BookNotification award table parser base.

Maintenance notes:
- BookNotification pages can mix book awards with person/special awards. Every
  production use should configure a category allowlist through category and
  category_aliases instead of parsing every row on the page.
- The user-status Read column is intentionally ignored.
"""

import re
from urllib.parse import urljoin

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


DEFAULT_ALLOWED_RESULTS = ('winner', 'nominee')

HEADER_ALIASES = {
  'year': 'year',
  'award year': 'year',
  'read': 'read',
  'category': 'category',
  'award category': 'category',
  'author': 'author',
  'authors': 'author',
  'writer': 'author',
  'writers': 'author',
  'title': 'title',
  'book': 'title',
  'work': 'title',
  'result': 'result',
  'status': 'result',
}

RESULT_ALIASES = {
  'won': 'winner',
  'winner': 'winner',
  'win': 'winner',
  'nominated': 'nominee',
  'nominee': 'nominee',
  'nominees': 'nominee',
  'finalist': 'nominee',
  'finalists': 'nominee',
}


class BookNotificationAwardParserBase(AwardParserBase):
  """
  Parse BookNotification award tables into award import entries.

  Invariants:
  - Tables must expose explicit Year, Category, Author, Title, and Result
    columns.
  - The configured category/category_aliases are an allowlist, not metadata
    decoration.
  """

  AWARD_NAME = ''

  def parse(
      self, html, base_url, name, category, category_aliases=(),
      allowed_results=DEFAULT_ALLOWED_RESULTS, require_title=True,
      tied_winners_share_position=False):
    rows = self.parse_rows(
      html,
      base_url,
      category,
      category_aliases,
      set(allowed_results or DEFAULT_ALLOWED_RESULTS),
      require_title)
    entries = self.entries_from_rows(
      self.dedupe_rows(rows),
      tied_winners_share_position=tied_winners_share_position)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(
      self, html, base_url, category, category_aliases, allowed_results,
      require_title):
    root = self.html_root(html)
    rows = []
    for table in self.all_tables(root):
      header_map = self.header_map(table)
      if not self.has_required_columns(header_map):
        continue
      rows.extend(self.table_rows(
        table, header_map, base_url, category, category_aliases,
        allowed_results, require_title))
    return rows

  def header_map(self, table):
    for tr in self.all_rows(table):
      mapped = {}
      for index, header in enumerate(self.direct_cells(tr, include_headers=True)):
        key = HEADER_ALIASES.get(normalize_heading(self.clean_cell_text(header)))
        if key is not None and key not in mapped:
          mapped[key] = index
      if self.has_required_columns(mapped):
        return mapped
    return {}

  def has_required_columns(self, header_map):
    return all(
      key in header_map
      for key in ('year', 'category', 'author', 'title', 'result'))

  def table_rows(
      self, table, header_map, base_url, category, category_aliases,
      allowed_results, require_title):
    rows = []
    for tr in self.all_rows(table):
      cells = self.direct_cells(tr, include_headers=True)
      if not cells or self.row_matches_header(cells, header_map):
        continue
      row = self.parse_row(
        cells, header_map, base_url, category, category_aliases,
        allowed_results, require_title)
      if row is not None:
        rows.append(row)
    return rows

  def parse_row(
      self, cells, header_map, base_url, category, category_aliases,
      allowed_results, require_title):
    year_cell = self.cell_for_key(cells, header_map, 'year')
    category_cell = self.cell_for_key(cells, header_map, 'category')
    author_cell = self.cell_for_key(cells, header_map, 'author')
    title_cell = self.cell_for_key(cells, header_map, 'title')
    result_cell = self.cell_for_key(cells, header_map, 'result')
    if any(cell is None for cell in (
        year_cell, category_cell, author_cell, title_cell, result_cell)):
      return None

    year = self.year_from_text(self.clean_cell_text(year_cell))
    row_category = self.clean_cell_text(category_cell)
    if year is None or not self.category_matches(
        row_category, category, category_aliases):
      return None

    result = self.result_from_cell(result_cell)
    if result not in allowed_results:
      return None

    title = self.clean_title(self.clean_cell_text(title_cell))
    author = self.clean_author(self.clean_cell_text(author_cell))
    if not author or (require_title and not title):
      return None

    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': self.first_link_url(title_cell, base_url) or base_url,
      'category': category,
    }

  def row_matches_header(self, cells, header_map):
    for key, index in header_map.items():
      if index >= len(cells):
        return False
      if HEADER_ALIASES.get(normalize_heading(self.clean_cell_text(cells[index]))) != key:
        return False
    return True

  def cell_for_key(self, cells, header_map, key):
    index = header_map.get(key)
    if index is None or index < 0 or index >= len(cells):
      return None
    return cells[index]

  def result_from_cell(self, cell):
    text = normalize_heading(self.clean_cell_text(cell))
    return RESULT_ALIASES.get(text)

  def clean_cell_text(self, cell):
    return normalize_line(' '.join(
      text.strip()
      for text in cell.xpath(
        './/text()[not(ancestor::style or ancestor::script)]')
      if text.strip()))

  def clean_title(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def first_link_url(self, cell, base_url):
    hrefs = cell.xpath('(.//a[@href])[1]/@href')
    return urljoin(base_url, hrefs[0]) if hrefs else ''

  def html_root(self, html):
    return lxml_html.fromstring(html or '<html></html>')

  def all_tables(self, root):
    return root.xpath('//table')

  def all_rows(self, table):
    return table.xpath('.//tr')

  def direct_cells(self, row, include_headers=False):
    selector = './td|./th' if include_headers else './td'
    return row.xpath(selector)

  def year_from_text(self, value):
    match = re.search(r'(19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def category_matches(self, row_category, category, category_aliases):
    aliases = {category, *category_aliases}
    normalized = {normalize_heading(alias) for alias in aliases}
    return normalize_heading(row_category) in normalized

  def dedupe_rows(self, rows):
    deduped = []
    seen = set()
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['category']),
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      if key in seen:
        continue
      seen.add(key)
      deduped.append(row)
    return deduped

  def entries_from_rows(self, rows, tied_winners_share_position=False):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in by_year[year]
      ]
      entries.extend(assign_positions(
        award_rows,
        int(year),
        tied_winners_share_position=tied_winners_share_position))
    return entries
