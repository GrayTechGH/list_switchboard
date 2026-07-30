#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Theakston Old Peculier Crime Novel of the Year parsers.
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


AWARD_NAME = 'Theakston Old Peculier Crime Novel of the Year'


class TheakstonLibraryThingParser(LibraryThingAwardParserBase):

  AWARD_NAME = AWARD_NAME

  def result_from_heading(self, heading):
    text = normalize_heading(heading.get_text(' ', strip=True))
    if text.startswith('winner'):
      return 'winner'
    if text.startswith('shortlist'):
      return 'nominee'
    return None


class TheakstonWikipediaParser(WikipediaAwardTableParserBase):
  AWARD_NAME = AWARD_NAME

  def row_omits_year(self, cells, header_map, current_year):
    """
    Detect the first row covered by Wikipedia's year/result rowspans.

    The live table has an unmapped trailing reference column. On the first
    shortlist row, that extra cell makes the shortened row look full-width to
    the shared parser even though the year cell is omitted. The row's third
    physical cell is the row-spanned Shortlist marker; later rows are handled
    by the shared short-row logic once that result has been established.
    """
    if (
        current_year is not None
        and header_map.get('year') == 0
        and len(cells) >= 3
        and self.year_from_text(self.clean_cell_text(cells[0])) is None
        and self.result_from_cell(cells[2]) == 'shortlisted'):
      return True
    return super().row_omits_year(cells, header_map, current_year)


def parse_theakston_librarything(html, base_url, name, category, category_aliases=()):
  return TheakstonLibraryThingParser().parse(
    html, base_url, name, category, category_aliases)


def parse_theakston_wikipedia(html, base_url, name, category, category_aliases=()):
  return TheakstonWikipediaParser().parse(
    html,
    base_url,
    name,
    category,
    category_aliases,
    allowed_results=('winner', 'shortlisted'))
