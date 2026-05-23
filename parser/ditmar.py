#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Ditmar Award parser for SFADB year pages.

Maintenance notes:
- SFADB exposes one overview page with linked yearly award pages.
- The import recipes intentionally keep to bookish categories: Novel,
  Novella/Novelette, and Collected Work.
- Older Ditmar category labels varied heavily, so fetchers own conservative
  aliases for book-shaped historical labels instead of treating every early
  "Australian SF" category as a novel.
"""

import re

try:
  from calibre_plugins.list_switchboard.parser.sfadb_base import (
    SFADBParser, StandardItemMixin,
  )
except ImportError:
  from .sfadb_base import SFADBParser, StandardItemMixin


AWARD_NAME = 'Ditmar Award'
YEAR_PAGE_URL = re.compile(r'/Ditmar_Awards_(\d{4})$')
CATEGORY_BOUNDARIES = frozenset({
  'novel', 'best novel', 'australian novel', 'australian sf novel',
  'australian sf or fantasy novel', 'australian long fiction',
  'australian long sf or fantasy', 'long fiction',
  'novella', 'novelette', 'novella or novelette',
  'short story', 'short fiction', 'australian short fiction',
  'collected work', 'australian collected work', 'collection', 'anthology',
  'australian magazine or anthology',
  'fan publication in any medium', 'fan publication', 'fan writer', 'fan artist',
  'artwork', 'best artwork', 'new talent', 'best new talent',
  'william atheling jr award for criticism or review',
  'william atheling jr. award for criticism or review',
  'contemporary writer', 'australian fanzine', 'international fiction',
  'international sf', 'international publication', 'dramatic presentation',
  'special award', 'special committee award',
})
NOVEL_ALIASES = (
  'novel',
  'best novel',
  'australian novel',
  'australian sf novel',
  'australian sf or fantasy novel',
  'australian long fiction',
  'australian long sf or fantasy',
  'long fiction',
)
NOVELLA_NOVELETTE_ALIASES = (
  'novella or novelette',
  'novella',
  'novelette',
)
COLLECTED_WORK_ALIASES = (
  'collected work',
  'australian collected work',
  'collection',
  'anthology',
)


class DitmarParser(StandardItemMixin, SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = CATEGORY_BOUNDARIES


def parse_ditmar_awards(
    overview_html, base_url, name='Ditmar - Novel', category='Novel',
    category_aliases=NOVEL_ALIASES, fetch_url=None, log=None, progress=None):
  return DitmarParser().parse(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=fetch_url, log=log, progress=progress)
