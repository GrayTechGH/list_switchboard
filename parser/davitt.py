#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Davitt Award parsers.
"""

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


class DavittLibraryThingParser(LibraryThingAwardParserBase):

  AWARD_NAME = AWARD_NAME

  def result_from_heading(self, heading):
    text = normalize_heading(heading.get_text(' ', strip=True))
    if text.startswith('winner'):
      return 'winner'
    if text.startswith('shortlist'):
      return 'nominee'
    return None


class DavittWikipediaParser(WikipediaAwardTableParserBase):

  AWARD_NAME = AWARD_NAME

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
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
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
