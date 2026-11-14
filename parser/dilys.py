#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Dilys Award parsers.
"""

try:
  from calibre_plugins.list_switchboard.parser.booknotification_base import (
    BookNotificationAwardParserBase,
  )
  from calibre_plugins.list_switchboard.parser.librarything_base import (
    LibraryThingAwardParserBase,
  )
  from calibre_plugins.list_switchboard.parser.wikipedia_base import (
    WikipediaAwardTableParserBase,
  )
except ImportError:
  from .booknotification_base import BookNotificationAwardParserBase
  from .librarything_base import LibraryThingAwardParserBase
  from .wikipedia_base import WikipediaAwardTableParserBase


AWARD_NAME = 'Dilys Award'


class DilysLibraryThingParser(LibraryThingAwardParserBase):
  AWARD_NAME = AWARD_NAME


class DilysWikipediaParser(WikipediaAwardTableParserBase):
  """
  Parse the consolidated Wikipedia winner/finalist table.

  Maintenance notes:
  - Finalist rows omit the row-spanned year cell but retain an unmapped trailing
    `Ref.` cell, so their raw cell count alone does not reveal the missing year.
  """

  AWARD_NAME = AWARD_NAME

  def row_omits_year(self, cells, header_map, current_year):
    if super().row_omits_year(cells, header_map, current_year):
      return True
    if current_year is None or header_map.get('year') != 0 or not cells:
      return False
    if self.year_from_text(self.clean_cell_text(cells[0])) is not None:
      return False

    result_index = header_map.get('result')
    if result_index is None or result_index < 1 or result_index >= len(cells):
      return False
    shifted_result = self.result_from_cell(cells[result_index - 1])
    unshifted_result = self.result_from_cell(cells[result_index])
    return shifted_result is not None and unshifted_result is None


class DilysBookNotificationParser(BookNotificationAwardParserBase):
  AWARD_NAME = AWARD_NAME


def parse_dilys_librarything(html, base_url, name, category, category_aliases=()):
  return DilysLibraryThingParser().parse(
    html, base_url, name, category, category_aliases)


def parse_dilys_wikipedia(html, base_url, name, category, category_aliases=()):
  return DilysWikipediaParser().parse(
    html,
    base_url,
    name,
    category,
    category_aliases,
    allowed_results=('winner', 'shortlisted'))


def parse_dilys_booknotification(html, base_url, name, category, category_aliases=()):
  return DilysBookNotificationParser().parse(
    html, base_url, name, category, category_aliases)
