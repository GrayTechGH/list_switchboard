#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Gumshoe Award parsers.
"""

try:
  from calibre_plugins.list_switchboard.parser.librarything_base import ( # type: ignore
    LibraryThingAwardParserBase,
  )
  from calibre_plugins.list_switchboard.parser.wikipedia_base import ( # type: ignore
    WikipediaAwardTableParserBase,
  )
  from calibre_plugins.list_switchboard.parser.award_base import normalize_heading # type: ignore
except ImportError:
  from .librarything_base import LibraryThingAwardParserBase
  from .wikipedia_base import WikipediaAwardTableParserBase
  from .award_base import normalize_heading


AWARD_NAME = 'Gumshoe Award'


class GumshoeLibraryThingParser(LibraryThingAwardParserBase):
  AWARD_NAME = AWARD_NAME


class GumshoeWikipediaParser(WikipediaAwardTableParserBase):

  AWARD_NAME = AWARD_NAME

  def parse(self, html, base_url, name, category, category_aliases=()):
    root = self.html_root(html)
    rows = []
    for _heading, table in self.tables_under_category_headings(
        root, category, category_aliases, match='contains'):
      header_map = self.header_map(table)
      rows.extend(self._winner_rows(table, header_map, base_url, category))
      break
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(name, base_url, entries)

  def _winner_rows(self, table, header_map, base_url, category):
    rows = []
    current_year = None
    for index, tr in enumerate(self.all_rows(table)):
      cells = self.direct_cells(tr, include_headers=True)
      if not cells:
        continue
      if index == 0 and all(cell.tag == 'th' for cell in cells):
        continue
      year = self.year_from_text(self.clean_cell_text(cells[0])) or current_year
      current_year = year
      if year is None or len(cells) < 3:
        continue
      author_cell = cells[1]
      title_cell = cells[2]
      rows.append({
        'award_year': str(year),
        'title': self.clean_title(self.clean_cell_text(title_cell)),
        'author': self.clean_author(self.clean_cell_text(author_cell)),
        'result': 'winner',
        'source_url': self.first_link_url(title_cell, base_url) or base_url,
        'category': category,
      })
    return [row for row in rows if row['title'] and row['author']]


def parse_gumshoe_librarything(html, base_url, name, category, category_aliases=()):
  return GumshoeLibraryThingParser().parse(
    html, base_url, name, category, category_aliases)


def parse_gumshoe_wikipedia(html, base_url, name, category, category_aliases=()):
  return GumshoeWikipediaParser().parse(
    html, base_url, name, category, category_aliases)
