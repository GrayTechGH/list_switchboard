#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Dilys Award parsers.
"""

try:
  from calibre_plugins.list_switchboard.parser.librarything_base import (
    LibraryThingAwardParserBase,
  )
  from calibre_plugins.list_switchboard.parser.wikipedia_base import (
    WikipediaAwardTableParserBase,
  )
except ImportError:
  from .librarything_base import LibraryThingAwardParserBase
  from .wikipedia_base import WikipediaAwardTableParserBase


AWARD_NAME = 'Dilys Award'


class DilysLibraryThingParser(LibraryThingAwardParserBase):
  AWARD_NAME = AWARD_NAME


class DilysWikipediaParser(WikipediaAwardTableParserBase):
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
