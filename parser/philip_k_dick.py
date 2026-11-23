#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Philip K. Dick Award parser for SFADB year pages.

Maintenance notes:
- SFADB exposes one page per award year with Winner, Special Citation, and
  Finalists sections.
- Year pages use a section-result model rather than one award-category block.
  RESULT_SECTIONS configures shared year parsing, including the legacy text shape.
- Special citations use .5-style positions to match the user's preferred list
  indexing. Only the assign_year_positions() hook differs from the base because
  special citations require a separate counter.
"""

import re

try:
  from calibre_plugins.list_switchboard.parser.sfadb_base import (
    SFADBParser,
    normalize_line,
    strip_publication_notes, strip_square_notes, strip_tie_marker,
    split_title_author as award_split_title_author,
  )
except ImportError:
  from .sfadb_base import (
    SFADBParser,
    normalize_line,
    strip_publication_notes, strip_square_notes, strip_tie_marker,
    split_title_author as award_split_title_author,
  )


AWARD_NAME = 'Philip K. Dick Award'
CATEGORY_NAME = 'Novel'
YEAR_PAGE_URL = re.compile(r'/Philip_K_Dick_Award_(\d{4})$')
SECTION_RESULTS = {
  'winner': 'winner',
  'special citation': 'special-citation',
  'finalists': 'nominee',
}
BOUNDARY_HEADINGS = frozenset({
  'where and when', 'eligibility year', 'judges', 'copyright',
})


def _special_citation_position(year, index):
  if index == 0:
    return f'{year}.5'
  return f'{year}.5{index}'


def _split_title_author(text):
  work_text = strip_publication_notes(text)
  work_text = re.sub(
    r'\s*,\s*translated\s+by\s+.+$', '', work_text, flags=re.I).strip()
  return award_split_title_author(work_text)


class PhilipKDickParser(SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = BOUNDARY_HEADINGS
  RESULT_SECTIONS = SECTION_RESULTS

  def parse(self, overview_html, base_url, name=None, category=None,
            category_aliases=None, fetch_url=None, log=None, progress=None,
            cached_parsed=None, incremental_update=False, enable_incremental=False):
    return super().parse(
      overview_html, base_url,
      name='Philip K. Dick Award - Novel',
      category=CATEGORY_NAME,
      category_aliases=(),
      fetch_url=fetch_url, log=log, progress=progress, cached_parsed=cached_parsed,
      incremental_update=incremental_update, enable_incremental=enable_incremental)

  def assign_year_positions(self, rows, year):
    entries = []
    suffix_index = 0
    citation_index = 0
    winner_seen = False
    for row in rows:
      result = row['result']
      if result == 'winner' and not winner_seen:
        position = str(year)
        winner_seen = True
      elif result == 'special-citation':
        position = _special_citation_position(year, citation_index)
        citation_index += 1
      else:
        suffix_index += 1
        position = f'{year}.{suffix_index:02d}'
      entries.append(dict(row, position=position))
    return entries

  def parse_item(self, text):
    text = strip_tie_marker(strip_square_notes(normalize_line(text)))
    title, author = _split_title_author(text)
    if not title or not author:
      return None
    return {
      'title': strip_publication_notes(title).strip(' \"\u201c\u201d,'),
      'author': strip_publication_notes(author).strip(),
      'result': 'nominee',  # overwritten by parse_year after section detection
    }


def parse_philip_k_dick_award_novel(
    overview_html, base_url, fetch_url=None, log=None, progress=None):
  return PhilipKDickParser().parse(
    overview_html, base_url,
    fetch_url=fetch_url, log=log, progress=progress)
