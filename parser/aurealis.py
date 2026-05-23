#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Aurealis Award parser for SFADB year pages.

Maintenance notes:
- SFADB exposes one overview page with linked yearly award pages.
- The book-ish import recipes intentionally exclude short story categories.
- Novella categories can contain quoted magazine-style short fiction rows; those
  recipes can request quoted-title filtering via skip_quoted=True.
- skip_quoted is stored as an instance attribute so parse_item() can read it
  without changing its signature (see SFADBParser refactor warning).
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


AWARD_NAME = 'Aurealis Award'
YEAR_PAGE_URL = re.compile(r'/Aurealis_Awards_(\d{4})$')
CATEGORY_BOUNDARIES = frozenset({
  'golden aurealis novel', 'golden aurealis short story',
  'sf novel', 'science fiction novel', 'sf novella', 'science fiction novella',
  'sf short story', 'science fiction short story',
  'fantasy novel', 'fantasy novella', 'fantasy short story',
  'horror novel', 'horror novella', 'horror short story',
  'anthology', 'collection', 'graphic novel/illustrated work',
  'illustrated book/graphic novel', 'graphic novel', 'illustrated work',
  'young adult novel', 'ya novel', 'young adult short story',
  "children's book", 'childrens book',
  "children's fiction", 'childrens fiction', 'children fiction',
  "children's fiction told primarily through words",
  'childrens fiction told primarily through words',
  "children's fiction told primarily through pictures",
  'childrens fiction told primarily through pictures',
  "children's 8 12 years long fiction", 'childrens 8 12 years long fiction',
  "children's short fiction", 'childrens short fiction',
  "children's illustrated work/picture book", 'childrens illustrated work/picture book',
  "children's 8 12 years illustrated work/picture book",
  'childrens 8 12 years illustrated work/picture book',
  'sara douglass book series', 'sara douglass book series award',
  "convenors' award", 'convenors award',
  'kris hembury encouragement award',
})


def _is_quoted_title(text):
  text = strip_tie_marker(normalize_line(text))
  return text.startswith(('"', '\u201c'))


class AurealisParser(StandardItemMixin, SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = CATEGORY_BOUNDARIES

  def __init__(self, skip_quoted=False):
    self.skip_quoted = skip_quoted

  def _filter_item(self, text):
    if self.skip_quoted and _is_quoted_title(text):
      return False
    return True


def parse_aurealis_awards(
    overview_html, base_url, name, category, category_aliases,
    skip_quoted=False, fetch_url=None, log=None, progress=None):
  return AurealisParser(skip_quoted=skip_quoted).parse(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=fetch_url, log=log, progress=progress)
