#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Bram Stoker Awards parser for SFADB year pages.

Maintenance notes:
- SFADB exposes one overview page with linked yearly award pages.
- Book categories use "Title, Author (publisher)" rows, with winners marked
  by "Winner:" or "Winner (tie):".
"""

import re

try:
  from calibre_plugins.list_switchboard.parser.sfadb_base import (
    SFADBParser, StandardItemMixin,
  )
except ImportError:
  from .sfadb_base import SFADBParser, StandardItemMixin


AWARD_NAME = 'Bram Stoker Award'
YEAR_PAGE_URL = re.compile(r'/Bram_Stoker_Awards_(\d{4})$')
CATEGORY_BOUNDARIES = frozenset({
  'lifetime achievement', 'novel', 'first novel', 'young adult novel',
  'young adult', 'middle grade novel', 'middle grade', 'long fiction',
  'fiction collection', 'collection', 'anthology', 'nonfiction',
  'non fiction', 'non-fiction', 'short fiction', 'poetry collection',
  'graphic novel', 'comic book graphic novel or other illustrated narrative',
  'illustrated narrative', 'screenplay', 'screenplay/teleplay',
  'short nonfiction', 'short non fiction', 'specialty press award',
})


class BramStokerParser(StandardItemMixin, SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = CATEGORY_BOUNDARIES


def parse_bram_stoker_awards(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=None, log=None, progress=None):
  return BramStokerParser().parse(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=fetch_url, log=log, progress=progress)
