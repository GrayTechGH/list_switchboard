#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Seiun Award parser for SFADB year pages.

Maintenance notes:
- SFADB exposes only foreign/translated Seiun categories.
- This recipe intentionally imports only the long-form book-matchable category
  labels and excludes translated short story/short form categories.
- Seiun rows use 'Title, Author' order without publisher parentheticals, which
  is the same shape as other SFADB parsers but with a tighter boundary set to
  avoid absorbing short-form categories.
"""

import re

try:
  from calibre_plugins.list_switchboard.parser.sfadb_base import (
    SFADBParser, StandardItemMixin,
  )
except ImportError:
  from .sfadb_base import SFADBParser, StandardItemMixin


AWARD_NAME = 'Seiun Award'
YEAR_PAGE_URL = re.compile(r'/Seiun_Awards_(\d{4})$')
CATEGORY_BOUNDARIES = frozenset({
  'japanese novel', 'japanese long form', 'japanese long story',
  'japanese long work', 'best japanese long work', 'best japanese long story',
  'foreign novel', 'foreign long form', 'foreign long story',
  'translated novel', 'translated long form', 'translated long story',
  'translated story', 'translated short form', 'translated short story',
  'foreign story', 'foreign short form', 'foreign short story',
  'foreign nonfiction', 'nonfiction', 'non fiction', 'non-fiction',
  'comic', 'comics', 'foreign media',
})
# Aliases accepted as the translated-novel category heading on year pages.
TRANSLATED_NOVEL_ALIASES = (
  'foreign novel',
  'translated novel',
  'translated long form',
  'translated long story',
  'foreign long form',
)
JAPANESE_LONG_WORK_ALIASES = (
  'japanese novel',
  'japanese long work',
  'japanese long form',
  'japanese long story',
  'best japanese long work',
  'best japanese long story',
)
COMIC_ALIASES = ('comic', 'comics')
NONFICTION_ALIASES = ('nonfiction', 'non fiction', 'non-fiction', 'foreign nonfiction')


class SeiunParser(StandardItemMixin, SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = CATEGORY_BOUNDARIES


def parse_seiun_awards(
    overview_html, base_url, name='Seiun - Translated Novel',
    fetch_url=None, log=None, progress=None):
  return SeiunParser().parse(
    overview_html, base_url, name,
    category='Translated Novel',
    category_aliases=TRANSLATED_NOVEL_ALIASES,
    fetch_url=fetch_url, log=log, progress=progress)
