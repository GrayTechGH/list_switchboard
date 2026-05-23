#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Shirley Jackson Awards parser for SFADB year pages.

Maintenance notes:
- SFADB exposes one overview page with linked yearly award pages.
- Book categories use "Title, Author (publisher)" rows, with winners marked
  by "Winner:" or "Winner (tie):".
- Editor suffixes (', ed.', ', eds.') are stripped from anthology author fields.
"""

import re

try:
  from calibre_plugins.list_switchboard.parser.sfadb_base import (
    SFADBParser, StandardItemMixin,
  )
except ImportError:
  from .sfadb_base import SFADBParser, StandardItemMixin


AWARD_NAME = 'Shirley Jackson Award'
YEAR_PAGE_URL = re.compile(r'/Shirley_Jackson_Awards_(\d{4})$')
CATEGORY_BOUNDARIES = frozenset({
  'novel', 'novella', 'novelette', 'short fiction', 'short story',
  'single author collection', 'single-author collection', 'collection',
  'edited anthology', 'anthology', 'special award', 'judges',
})


class ShirleyJacksonParser(StandardItemMixin, SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = CATEGORY_BOUNDARIES


def parse_shirley_jackson_awards(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=None, log=None, progress=None):
  return ShirleyJacksonParser().parse(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=fetch_url, log=log, progress=progress)
