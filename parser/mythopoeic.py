#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Mythopoeic Awards parser for SFADB year pages.

Maintenance notes:
- SFADB exposes one overview page with linked yearly award pages.
- Fiction categories use "Title, Author (publisher)" rows, usually with a
  "Winner:" prefix for the winning row.
"""

import re

try:
  from calibre_plugins.list_switchboard.parser.sfadb_base import (
    SFADBParser, StandardItemMixin,
  )
except ImportError:
  from .sfadb_base import SFADBParser, StandardItemMixin


AWARD_NAME = 'Mythopoeic Award'
YEAR_PAGE_URL = re.compile(r'/Mythopoeic_Awards_(\d{4})$')
CATEGORY_BOUNDARIES = frozenset({
  'fantasy', 'adult literature', 'young adult literature', 'ya literature',
  "children's literature", 'childrens literature', 'children literature',
  'childrens and young adult literature',
  'children and young adult literature', 'inklings studies',
  'myth and fantasy studies', 'myth fantasy studies',
  'scholarship', 'scholarship in inklings studies',
  'scholarship in myth and fantasy studies',
})


class MythopoeicParser(StandardItemMixin, SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = CATEGORY_BOUNDARIES


def parse_mythopoeic_awards(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=None, log=None, progress=None):
  return MythopoeicParser().parse(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=fetch_url, log=log, progress=progress)
