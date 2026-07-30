#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Crime Writers of Canada award parsers.

Maintenance notes:
- Both current sources use explicit ``and`` credits for some coauthored books;
  normalize those boundaries before the shared entry builder creates the
  canonical author list.
- The dedicated Best Novel Wikipedia page emits each row-spanned year as a
  separate table row under Parsoid. Its highlighted/bold row is the winner and
  the remaining work rows for that year are nominees.
"""

import re

try:
  from calibre_plugins.list_switchboard.parser.librarything_base import (
    LibraryThingAwardParserBase,
  )
  from calibre_plugins.list_switchboard.parser.wikipedia_base import (
    WikipediaAwardTableParserBase,
  )
  from calibre_plugins.list_switchboard.parser.award_base import normalize_heading
except ImportError:
  from .librarything_base import LibraryThingAwardParserBase
  from .wikipedia_base import WikipediaAwardTableParserBase
  from .award_base import normalize_heading


AWARD_NAME = 'Crime Writers of Canada Award'


class CrimeWritersOfCanadaAuthorMixin:

  def clean_author(self, value):
    author = super().clean_author(value)
    return re.sub(r'\s+and\s+', ' & ', author, flags=re.I)


class CrimeWritersOfCanadaLibraryThingParser(
    CrimeWritersOfCanadaAuthorMixin, LibraryThingAwardParserBase):

  AWARD_NAME = AWARD_NAME

  def result_from_heading(self, heading):
    text = normalize_heading(heading.get_text(' ', strip=True))
    if text.startswith('winner'):
      return 'winner'
    if text.startswith('shortlist') or text.startswith('nominee') or text.startswith('finalist'):
      return 'nominee'
    return None


class CrimeWritersOfCanadaWikipediaParser(
    CrimeWritersOfCanadaAuthorMixin, WikipediaAwardTableParserBase):

  AWARD_NAME = AWARD_NAME

  def parse(self, html, base_url, name, category, category_aliases=()):
    root = self.html_root(html)
    rows = []
    for _heading, table in self.tables_under_category_headings(
        root, category, category_aliases, match='exact'):
      rows.extend(self.table_rows(
        table,
        self.header_map(table),
        base_url,
        category,
        category_aliases,
        {'winner'}))
    if not rows:
      for table in self.all_tables(root):
        header_map = self.header_map(table)
        if not self.has_required_columns(header_map):
          continue
        rows.extend(self.table_rows(
          table,
          header_map,
          base_url,
          category,
          category_aliases,
          {'winner'}))
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(name, base_url, entries)

  def table_rows(
      self, table, header_map, base_url, category, category_aliases,
      allowed_results):
    rows = self._table_rows_standard(
      table, header_map, base_url, category, category_aliases, allowed_results)
    if rows:
      for row in rows:
        row['result'] = 'winner'
      return rows
    if not self.has_required_columns(header_map):
      return []
    if self.has_split_year_rows(table):
      return self.split_year_award_rows(
        table, header_map, base_url, category)
    rows = []
    current_year = None
    for tr in self.all_rows(table):
      cells = self.direct_cells(tr, include_headers=True)
      if not cells or self.row_matches_header(cells, header_map):
        continue
      year_text = self.clean_cell_text(cells[header_map['year']])
      year = self.year_from_text(year_text) or current_year
      if year is None:
        continue
      current_year = year
      title_cell = self.cell_for_key(cells, header_map, 'title', False)
      author_cell = self.cell_for_key(cells, header_map, 'author', False)
      if title_cell is None or author_cell is None:
        continue
      title = self.clean_title(self.clean_cell_text(title_cell))
      author = self.clean_author(self.clean_cell_text(author_cell))
      if not title or not author:
        continue
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': 'winner',
        'source_url': self.first_link_url(title_cell, base_url) or base_url,
        'category': category,
      })
    return rows

  def has_split_year_rows(self, table):
    for tr in self.all_rows(table):
      cells = self.direct_cells(tr, include_headers=True)
      if len(cells) == 1 and self.year_from_text(self.clean_cell_text(cells[0])):
        return True
    return False

  def split_year_award_rows(self, table, header_map, base_url, category):
    rows = []
    current_year = None
    for tr in self.all_rows(table):
      cells = self.direct_cells(tr, include_headers=True)
      if not cells or self.row_matches_header(cells, header_map):
        continue
      if len(cells) == 1:
        current_year = self.year_from_text(self.clean_cell_text(cells[0])) or current_year
        continue
      if current_year is None:
        continue
      # Parsoid separates the rowspan year into the preceding row, so the
      # author/title indexes are shifted left for every work row.
      title_cell = self.cell_for_key(cells, header_map, 'title', True)
      author_cell = self.cell_for_key(cells, header_map, 'author', True)
      if title_cell is None or author_cell is None:
        continue
      title = self.clean_title(self.clean_cell_text(title_cell))
      author = self.clean_author(self.clean_cell_text(author_cell))
      if not title or not author:
        continue
      result = (
        'winner'
        if self.is_highlighted_winner_row(tr, title_cell, author_cell)
        else 'nominee')
      rows.append({
        'award_year': str(current_year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': self.first_link_url(title_cell, base_url) or base_url,
        'category': category,
      })
    return rows

  def is_highlighted_winner_row(self, row, title_cell, author_cell):
    style = re.sub(r'\s+', '', row.get('style') or '').casefold()
    if 'background:lightyellow' in style:
      return True
    return bool(
      title_cell.xpath('.//b|.//strong')
      and author_cell.xpath('.//b|.//strong'))


def parse_crime_writers_canada_librarything(
    html, base_url, name, category, category_aliases=()):
  return CrimeWritersOfCanadaLibraryThingParser().parse(
    html, base_url, name, category, category_aliases)


def parse_crime_writers_canada_wikipedia(
    html, base_url, name, category, category_aliases=()):
  return CrimeWritersOfCanadaWikipediaParser().parse(
    html, base_url, name, category, category_aliases)
