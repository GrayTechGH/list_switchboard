#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Aurora Award parser for SFADB year pages.

Maintenance notes:
- SFADB exposes one overview page with linked yearly award pages.
- Related Work includes magazines, TV, and person-only rows; that recipe uses
  books_only=True so the imported list stays useful for Calibre matching.
- books_only is stored as an instance attribute so parse_item() can read it
  without changing its signature (see SFADBParser refactor warning).
"""

import re

try:
  from calibre_plugins.list_switchboard.parser.sfadb_base import (
    SFADBParser, StandardItemMixin,
    normalize_heading, split_title_author, strip_publication_notes,
  )
except ImportError:
  from .sfadb_base import (
    SFADBParser, StandardItemMixin,
    normalize_heading, split_title_author, strip_publication_notes,
  )


AWARD_NAME = 'Aurora Award'
YEAR_PAGE_URL = re.compile(r'/Aurora_Awards_(\d{4})$')
CATEGORY_BOUNDARIES = frozenset({
  'hall of fame', 'novel', 'ya novel', 'young adult novel', 'short story',
  'novelette/novella', 'novelette', 'novella', 'related work', 'graphic novel',
  'poem/song', 'poem', 'song', 'artistic achievement',
  'cover art/interior illustration', 'cover art', 'interior illustration',
  'nonfiction', 'non fiction', 'non-fiction', 'visual presentation',
  'fan achievement', 'fan publication', 'fan organizational', 'fan music/filk',
  'fan achievement other', 'fan achievement (other)', 'fan related work',
  'lifetime achievement', 'best of the decade',
})
NON_BOOK_RELATED_MARKERS = frozenset({
  'magazine', 'periodical', 'podcast', 'show', 'television', 'tv', 'web site',
  'website',
})
NON_BOOK_RELATED_TITLES = frozenset({
  'on spec', 'prisoners of gravity', 'reboot',
})


def _is_book_like_related_work(text):
  title, author = split_title_author(text)
  if not title or not author:
    return False
  if normalize_heading(title) in NON_BOOK_RELATED_TITLES:
    return False
  words = set(normalize_heading(text).split())
  return not words.intersection(NON_BOOK_RELATED_MARKERS)


class AuroraParser(StandardItemMixin, SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = CATEGORY_BOUNDARIES

  def __init__(self, books_only=False):
    self.books_only = books_only

  def _filter_item(self, text):
    if self.books_only and not _is_book_like_related_work(text):
      return False
    return True


def parse_aurora_awards(
    overview_html, base_url, name, category, category_aliases,
    books_only=False, fetch_url=None, log=None, progress=None):
  return AuroraParser(books_only=books_only).parse(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=fetch_url, log=log, progress=progress)
