#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Prometheus Award parser for SFADB year pages.

Maintenance notes:
- SFADB exposes one overview page with linked yearly award pages.
- Hall of Fame includes non-book media; that recipe uses books_only=True so
  the imported list stays useful for Calibre matching.
- books_only is stored as an instance attribute so parse_item() can read it
  without changing its signature (see SFADBParser refactor warning).
- Quoted titles are always short fiction and are rejected unconditionally.
"""

import re

try:
  from calibre_plugins.list_switchboard.parser.sfadb_base import (
    SFADBParser, StandardItemMixin,
    normalize_heading, normalize_line, strip_tie_marker,
  )
except ImportError:
  from .sfadb_base import (
    SFADBParser, StandardItemMixin,
    normalize_heading, normalize_line, strip_tie_marker,
  )


AWARD_NAME = 'Prometheus Award'
YEAR_PAGE_URL = re.compile(r'/Prometheus_Awards_(\d{4})$')
CATEGORY_BOUNDARIES = frozenset({
  'novel', 'hall of fame', 'young adult honor roll',
  'special award', 'special awards',
})
NON_BOOK_MARKERS = frozenset({
  'album', 'episode', 'film', 'movie', 'musical', 'play', 'poem', 'song',
  'teleplay', 'television', 'tv',
})


def _is_quoted_title(text):
  text = strip_tie_marker(normalize_line(text))
  return text.startswith(('"', '\u201c'))


def _is_book_like_hall_of_fame_item(text):
  if _is_quoted_title(text):
    return False
  notes = [
    normalize_heading(match.group(1))
    for match in re.finditer(r'\(([^()]*)\)', text)
  ]
  for note in notes:
    if set(note.split()).intersection(NON_BOOK_MARKERS):
      return False
  return True


class PrometheusParser(StandardItemMixin, SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = CATEGORY_BOUNDARIES

  def __init__(self, books_only=False):
    self.books_only = books_only

  def _filter_item(self, text):
    if self.books_only and not _is_book_like_hall_of_fame_item(text):
      return False
    return True


def parse_prometheus_awards(
    overview_html, base_url, name, category, category_aliases,
    books_only=False, fetch_url=None, log=None, progress=None):
  return PrometheusParser(books_only=books_only).parse(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=fetch_url, log=log, progress=progress)
