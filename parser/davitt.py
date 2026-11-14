#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Davitt Award parsers.

Maintenance notes:
- Both fallback sources can expose coauthors as one explicit ``and`` credit;
  normalize that boundary before the entry builder creates the author list.
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


AWARD_NAME = 'Davitt Award'


class DavittAuthorMixin:

  def clean_author(self, value):
    author = super().clean_author(value)
    return re.sub(r'\s+and\s+', ' & ', author, flags=re.I)


class DavittLibraryThingParser(DavittAuthorMixin, LibraryThingAwardParserBase):

  AWARD_NAME = AWARD_NAME

  def result_from_heading(self, heading):
    text = normalize_heading(heading.get_text(' ', strip=True))
    if text.startswith('winner'):
      return 'winner'
    if text.startswith('shortlist'):
      return 'nominee'
    return None


class DavittWikipediaParser(DavittAuthorMixin, WikipediaAwardTableParserBase):

  AWARD_NAME = AWARD_NAME

  def parse_rows(
      self, html, base_url, category, category_aliases, allowed_results):
    """Parse summary tables and only the matching category history table.

    The Davitt article combines category-bearing decade tables with an Adult
    Novel history table that has no Category column.  Treating every
    category-less table as the configured recipe leaks Adult Novel winners
    into other Davitt recipes.
    """
    root = self.html_root(html)
    rows = []
    for table in self.all_tables(root):
      header_map = self.header_map(table)
      if not self.has_required_columns(header_map):
        continue
      if 'category' not in header_map:
        headings = table.xpath('preceding::h2|preceding::h3|preceding::h4')
        table_category = self.node_text(headings[-1]) if headings else ''
        if not self.category_matches(
            table_category, category, category_aliases):
          continue
      rows.extend(self.table_rows(
        table, header_map, base_url, category, category_aliases,
        set(allowed_results)))
    return rows

  def dedupe_rows(self, rows):
    """Collapse winners repeated across Wikipedia's category/history tables.

    Wikipedia lists the same Davitt winners in more than one table.  Author
    typos can differ between those tables, so author cannot be part of the
    identity key here.  Document order is significant: the main
    winners-by-category table appears first and is retained.
    """
    deduped = []
    seen = set()
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['category']),
        normalize_heading(row['title']),
      )
      if key in seen:
        continue
      seen.add(key)
      deduped.append(row)
    return deduped

  def table_rows(
      self, table, header_map, base_url, category, category_aliases,
      allowed_results):
    rows = self._table_rows_standard(
      table, header_map, base_url, category, category_aliases, allowed_results)
    if rows:
      for row in rows:
        row['result'] = 'winner'
      return rows
    rows = []
    current_year = None
    for tr in self.all_rows(table):
      cells = self.direct_cells(tr, include_headers=True)
      if not cells or self.row_matches_header(cells, header_map):
        continue
      missing_year = self.row_omits_year(cells, header_map, current_year)
      year_text = (
        self.clean_cell_text(cells[header_map['year']])
        if not missing_year and header_map['year'] < len(cells) else '')
      year = self.year_from_text(year_text) or current_year
      current_year = year
      if year is None:
        continue
      title_cell = self.cell_for_key(cells, header_map, 'title', missing_year)
      author_cell = self.cell_for_key(cells, header_map, 'author', missing_year)
      category_cell = self.cell_for_key(cells, header_map, 'category', missing_year)
      if title_cell is None or author_cell is None:
        continue
      row_category = self.clean_cell_text(category_cell) if category_cell is not None else category
      if not self.category_matches(row_category, category, category_aliases):
        continue
      rows.append({
        'award_year': str(year),
        'title': self.clean_title(self.clean_cell_text(title_cell)),
        'author': self.clean_author(self.clean_cell_text(author_cell)),
        'result': 'winner',
        'source_url': self.first_link_url(title_cell, base_url) or base_url,
        'category': category,
      })
    return [row for row in rows if row['title'] and row['author']]


def parse_davitt_librarything(html, base_url, name, category, category_aliases=()):
  return DavittLibraryThingParser().parse(
    html, base_url, name, category, category_aliases)


def parse_davitt_wikipedia(html, base_url, name, category, category_aliases=()):
  return DavittWikipediaParser().parse(
    html, base_url, name, category, category_aliases, allowed_results=('winner',))
