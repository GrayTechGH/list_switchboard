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
  from calibre_plugins.list_switchboard.parser.award_base import (
    normalize_line, parse_winner_prefix,
  )
  from calibre_plugins.list_switchboard.parser.sfadb_base import (
    node_text, SFADBParser, StandardItemMixin,
  )
except ImportError:
  from .award_base import normalize_line, parse_winner_prefix
  from .sfadb_base import SFADBParser, StandardItemMixin
  from .sfadb_base import node_text


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


def normalize_collective_title(value):
  """
  Remove SFADB's display punctuation from a series/cycle heading.

  Quotation marks distinguish the collective title from its component works
  on the source page; they are not part of the matchable title.
  """
  title = normalize_line(value).rstrip(' :')
  quote_pairs = (('"', '"'), ('“', '”'), ('‘', '’'))
  while len(title) >= 2 and any(
      title.startswith(opening) and title.endswith(closing)
      for opening, closing in quote_pairs):
    title = title[1:-1].strip()
  return title


def text_before_descendant(node, boundary):
  """Return text that structurally precedes ``boundary`` inside ``node``."""
  fragments = []
  for fragment in node.xpath('.//text()'):
    parent = fragment.getparent()
    if parent is boundary or boundary in parent.iterancestors():
      break
    fragments.append(str(fragment))
  return normalize_line(' '.join(fragments))


class MythopoeicParser(StandardItemMixin, SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = CATEGORY_BOUNDARIES

  def parse_item_node(self, node):
    """
    Preserve bold cycle/component titles without publisher or date metadata.

    SFADB sometimes places a collective title outside the first bold node, or
    appends a bold list of component works after the linked author. The bold
    nodes are authoritative work text; linked person nodes are contributors.
    """
    _text, result = parse_winner_prefix(node_text(node))
    title_nodes = node.xpath('.//b')
    author_nodes = node.xpath('.//a')
    if not title_nodes or not author_nodes:
      return super().parse_item_node(node)
    bold_titles = [
      normalize_line(node_text(title_node))
      for title_node in title_nodes
      if normalize_line(node_text(title_node))
    ]
    authors = [
      normalize_line(node_text(author_node))
      for author_node in author_nodes
      if normalize_line(node_text(author_node))
    ]
    if not bold_titles or not authors:
      return super().parse_item_node(node)

    leading_text, _leading_result = parse_winner_prefix(
      text_before_descendant(node, title_nodes[0]))
    leading_title = leading_text.strip(' ,(')
    if leading_title:
      title = leading_title
      components = bold_titles
    else:
      title = bold_titles[0]
      components = bold_titles[1:]
    if components:
      title = normalize_collective_title(title)
      title = f"{title}: {'; '.join(components)}"
    return {
      'title': title,
      'authors': authors,
      'result': result,
    }


def parse_mythopoeic_awards(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=None, log=None, progress=None):
  return MythopoeicParser().parse(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=fetch_url, log=log, progress=progress)
