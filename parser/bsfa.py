#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
British Science Fiction Association Awards parser for SFADB year pages.

Maintenance notes:
- SFADB exposes complete yearly pages with category headings and bullet rows.
- Current BSFA pages include several book-like categories; each recipe selects
  one configured category from the same year-page source.
"""

import re

try:
  from calibre_plugins.list_switchboard.parser.sfadb_base import (
    SFADBParser, StandardItemMixin,
  )
except ImportError:
  from .sfadb_base import SFADBParser, StandardItemMixin


AWARD_NAME = 'British Science Fiction Association Award'
YEAR_PAGE_URL = re.compile(r'/British_SF_Association_Awards_(\d{4})$')
CATEGORY_BOUNDARIES = frozenset({
  'novel', 'novels', 'shorter fiction', 'shorter fiction novelette or novella',
  'short fiction', 'translated short fiction', 'fiction for younger readers',
  'best fiction for younger readers', 'collection', 'collection or anthology',
  'collection/anthology', 'nonfiction long', 'non fiction long', 'long nonfiction',
  'long non fiction', 'nonfiction short', 'non fiction short', 'short nonfiction',
  'short non fiction', 'non-fiction', 'non fiction', 'media presentation',
  'media', 'artist', 'artwork', 'audio fiction', 'original audio fiction',
})


class BSFAParser(StandardItemMixin, SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = CATEGORY_BOUNDARIES


def parse_bsfa_awards(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=None, log=None, progress=None):
  return BSFAParser().parse(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=fetch_url, log=log, progress=progress)
