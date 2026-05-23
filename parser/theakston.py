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
