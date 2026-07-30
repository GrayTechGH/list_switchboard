#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
World Fantasy Awards parser for SFADB year pages.

Maintenance notes:
- SFADB exposes complete yearly pages with category headings and bullet rows.
- Book categories use "Title, Author (publisher)" rows, sometimes prefixed by
  "Winner:" and sometimes marked with "(tie)".
- Special award headings use a startswith check rather than exact membership
  because sub-categories vary ('Special Award Professional', etc.).
"""

import re

try:
  from calibre_plugins.list_switchboard.parser.sfadb_base import (
    SFADBParser, StandardItemMixin,
    node_text, normalize_heading, parse_winner_prefix, strip_tie_marker,
  )
except ImportError:
  from .sfadb_base import (
    SFADBParser, StandardItemMixin,
    node_text, normalize_heading, parse_winner_prefix, strip_tie_marker,
  )


AWARD_NAME = 'World Fantasy Award'
BASE_URL = 'https://www.sfadb.com/World_Fantasy_Awards'
YEAR_PAGE_URL = re.compile(r'/World_Fantasy_Awards_(\d{4})$')
CATEGORY_BOUNDARIES = frozenset({
  'life achievement', 'novel', 'novels', 'novella', 'long fiction',
  'short fiction', 'short story', 'anthology', 'collection',
  'collection/anthology', 'artist',
  'special award non professional', 'special award nonprofessional',
  'special convention award', 'convention award',
})


class WorldFantasyParser(StandardItemMixin, SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = CATEGORY_BOUNDARIES

  def is_category_boundary(self, line):
    heading = normalize_heading(line)
    if not heading:
      return False
    # Prefix check covers 'Special Award Professional' and similar variants.
    if heading.startswith('special award'):
      return True
    return heading in self.CATEGORY_BOUNDARIES

  def parse_item(self, text):
    # World Fantasy uses 'Winner:' prefix without the trailing '(winner)' suffix
    # form, but both are handled by StandardItemMixin.parse_item via
    # parse_winner_prefix(). The tie marker must be stripped before splitting.
    text = strip_tie_marker(text)
    return super().parse_item(text)

  def parse_item_node(self, node):
    """
    Parse live SFADB rows using their bold-title and linked-person boundaries.

    Anthology rows can credit several comma-separated editors before a trailing
    ``eds.`` marker. Flattening that markup to text makes the first editor look
    like part of the title to the shared single-editor comma splitter.
    """
    text = node_text(node)
    cleaned, result = parse_winner_prefix(text)
    if normalize_heading(cleaned) == 'no award':
      return None
    title_nodes = node.xpath('(./b | ./strong)[1]')
    if not title_nodes:
      return self.parse_item(text)
    title = node_text(title_nodes[0]).strip(' "\u201c\u201d,')
    authors = list(dict.fromkeys(
      author for author in (
        node_text(link) for link in node.xpath('./a[@href]')
      ) if author
    ))
    if not title or not authors:
      return self.parse_item(text)
    return {
      'title': title,
      'authors': authors,
      'result': result,
    }


def parse_world_fantasy_awards(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=None, log=None, progress=None):
  return WorldFantasyParser().parse(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=fetch_url, log=log, progress=progress)
