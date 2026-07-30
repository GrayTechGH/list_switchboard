#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Bram Stoker Awards parser for SFADB year pages.

Maintenance notes:
- SFADB exposes one overview page with linked yearly award pages.
- The printed award page year is the announcement year. The explicit
  Eligibility Year is the canonical import position year.
- SFADB's bold title and linked-person markup is load-bearing for multi-editor
  books and role-rich graphic works; do not flatten those rows before parsing.
- ISFDB uses structural bold "and" separators between contributors. Bram's
  subclass preserves those contributor boundaries without changing other
  award families.
"""

import re

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    assign_positions, normalize_heading, normalize_line, parse_winner_prefix,
    strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.isfdb_base import (
    ISFDBAwardParserBase,
  )
  from calibre_plugins.list_switchboard.parser.sfadb_base import (
    SFADBParser, StandardItemMixin, html_root, node_text,
  )
except ImportError:
  from .award_base import (
    assign_positions, normalize_heading, normalize_line, parse_winner_prefix,
    strip_publication_notes,
  )
  from .isfdb_base import ISFDBAwardParserBase
  from .sfadb_base import (
    SFADBParser, StandardItemMixin, html_root, node_text,
  )


AWARD_NAME = 'Bram Stoker Award'
YEAR_PAGE_URL = re.compile(r'/Bram_Stoker_Awards_(\d{4})$')
CATEGORY_BOUNDARIES = frozenset({
  'life achievement', 'lifetime achievement', 'special trustee award',
  'novel', 'first novel', 'young adult novel',
  'young adult', 'middle grade novel', 'middle grade', 'long fiction',
  'novelette', 'novella', 'novella/novelette', 'long fiction/novelette',
  'fiction collection', 'collection', 'anthology', 'nonfiction book',
  'nonfiction', 'non fiction', 'non-fiction', 'long nonfiction',
  'long non fiction', 'long non-fiction', 'short fiction', 'short story',
  'other media', 'work for younger readers', 'alternative forms', 'poetry',
  'poetry collection',
  'graphic novel', 'comic book graphic novel or other illustrated narrative',
  'illustrated narrative', 'screenplay', 'screenplay/teleplay',
  'short nonfiction', 'short non fiction', 'specialty press award',
})

LONG_FICTION_LINEAGE_ALIASES = (
  'novelette',
  'novella',
  'novella/novelette',
  'long fiction/novelette',
)

# These SFADB rows do not label creator roles consistently. The author/artist
# corrections are intentionally narrow and are grounded in HWA final ballots
# or publisher creator credits; colorists, letterers, and other production-only
# roles remain excluded.
GRAPHIC_CREATOR_CORRECTIONS = {
  normalize_heading('The Sandman: The Dream Hunters'): (
    'Neil Gaiman', 'Yoshitaka Amano',
  ),
  normalize_heading("Victor LaValle's Destroyer"): (
    'Victor LaValle', 'Dietrich Smith',
  ),
  normalize_heading('Abbott'): ('Saladin Ahmed', 'Sami Kivelä'),
  normalize_heading('Bone Parish Vol. 2'): ('Cullen Bunn', 'Jonas Scharf'),
  normalize_heading('Calcutta Horror'): (
    'Alessandro Manzetti', 'Stefano Cardoselli',
  ),
  normalize_heading('Mary Shelley Presents'): (
    'Nancy Holder', 'Chiara Di Francia', 'Amelia Woo',
  ),
  normalize_heading('Lonesome Days, Savage Nights'): (
    'Steve Niles', 'Salvatore Simeone', 'Szymon Kudranski',
  ),
  normalize_heading('Joker/Harley: Criminal Insanity'): (
    'Kami Garcia', 'Mico Suayan', 'Jason Badower', 'Mike Mayhew',
  ),
  normalize_heading('Proctor Valley Road'): (
    'Grant Morrison', 'Alex Child', 'Naomi Franquiz',
  ),
}


class BramStokerParser(StandardItemMixin, SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = CATEGORY_BOUNDARIES

  def parse_year(self, html, source_url, year, category, category_aliases):
    root = html_root(html)
    match = re.search(
      r'\bEligibility Year\s*:\s*((?:19|20)\d{2})\b',
      node_text(root),
      re.I)
    award_year = int(match.group(1)) if match is not None else year
    aliases = tuple(category_aliases)
    if (
        normalize_heading(category) == 'long fiction'
        and award_year < 1999
        and award_year != 1993):
      aliases += LONG_FICTION_LINEAGE_ALIASES
    return super().parse_year(
      html, source_url, award_year, category, aliases)

  def parse_item_node(self, node):
    text, result = parse_winner_prefix(node_text(node))
    if normalize_heading(text) == 'no award':
      return None
    title_nodes = node.xpath('./b|./strong')
    person_nodes = node.xpath('./a[@href]')
    if not person_nodes:
      return super().parse_item_node(node)

    if title_nodes and _node_precedes(node, title_nodes[0], person_nodes[0]):
      title_text = node_text(title_nodes[0])
    else:
      # Early Novelette/Novella rows leave the quoted work title unbolded and
      # may bold its containing anthology after the author link.
      title_text, _unused_result = parse_winner_prefix(
        _text_before_descendant(node, person_nodes[0]))
    title = strip_publication_notes(
      normalize_line(title_text)).strip(' "\u201c\u201d,')
    authors = _linked_people(person_nodes)
    heading = _category_heading(node)

    if heading in {'fiction collection', 'collection'}:
      authors = []
      for person_node in person_nodes:
        preceding = _text_before_descendant(node, person_node)
        if re.search(r'\bedited\s+by\s*$', preceding, re.I):
          break
        _append_person(authors, person_node)
    elif heading in {
        'graphic novel',
        'illustrated narrative',
        'comic book graphic novel or other illustrated narrative',
    }:
      corrected = GRAPHIC_CREATOR_CORRECTIONS.get(normalize_heading(title))
      if corrected is not None:
        authors = list(corrected)
      else:
        authors = []
        for person_node in person_nodes:
          preceding = _text_before_descendant(node, person_node)
          if re.search(
              r'\b(?:colou?rs?(?:ed)?|lettered|inked)\s+by\s*$',
              preceding,
              re.I):
            break
          _append_person(authors, person_node)
        illus_match = re.search(r'\billus(\d+)\b', text, re.I)
        if illus_match is not None:
          production_index = int(illus_match.group(1))
          authors = authors[:production_index]

    if not title or not authors:
      return super().parse_item_node(node)
    return {
      'title': title,
      'authors': authors,
      'result': result,
    }


class BramStokerISFDBParser(ISFDBAwardParserBase):
  """
  Preserve Bram-specific ISFDB contributor and provenance semantics.

  ISFDB Bram rows use bold ``and`` nodes as contributor separators. Splitting
  only at those structural nodes preserves suffix punctuation such as ``Jr.``
  and ``IV``. The award-year page, not a linked title record, is the evidence
  for the imported award result.
  """

  AWARD_NAME = AWARD_NAME

  def author_from_cell(self, cell):
    authors = []
    fragments = []
    for fragment in cell.xpath('.//text()'):
      parent = fragment.getparent()
      value = normalize_line(str(fragment))
      if (
          value.casefold() == 'and'
          and parent is not None
          and str(parent.tag).casefold() in {'b', 'strong'}):
        _append_author_fragment(authors, fragments)
        fragments = []
      else:
        fragments.append(str(fragment))
    _append_author_fragment(authors, fragments)
    return authors

  def clean_author(self, value):
    if isinstance(value, (list, tuple)):
      return [
        cleaned
        for cleaned in (
          strip_publication_notes(normalize_line(author)).strip(' ,')
          for author in value
        )
        if cleaned
      ]
    return super().clean_author(value)

  def first_record_url(self, _cell, _base_url):
    return ''

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      award_rows = [
        self.build_award_entry(
          row, row['source_url'], year, row['category'], award=row.get('award'))
        for row in by_year[year]
      ]
      entries.extend(assign_positions(
        award_rows, int(year), tied_winners_share_position=True))
    return entries


def _category_heading(node):
  blocks = node.xpath(
    'ancestor::div['
    'contains(concat(" ", normalize-space(@class), " "), " categoryblock ")'
    '][1]')
  if not blocks:
    return ''
  headings = blocks[0].xpath(
    './/div['
    'contains(concat(" ", normalize-space(@class), " "), " category ")'
    '][1]')
  return normalize_heading(node_text(headings[0]) if headings else '')


def _linked_people(person_nodes):
  authors = []
  for person_node in person_nodes:
    _append_person(authors, person_node)
  return authors


def _append_person(authors, person_node):
  author = normalize_line(node_text(person_node))
  if author and author not in authors:
    authors.append(author)


def _text_before_descendant(node, boundary):
  fragments = []
  for fragment in node.xpath('.//text()'):
    parent = fragment.getparent()
    if parent is boundary or boundary in parent.iterancestors():
      break
    fragments.append(str(fragment))
  return normalize_line(' '.join(fragments))


def _node_precedes(root, first, second):
  for descendant in root.iter():
    if descendant is first:
      return True
    if descendant is second:
      return False
  return False


def _append_author_fragment(authors, fragments):
  author = normalize_line(' '.join(fragments)).strip(' ,')
  if author and author not in authors:
    authors.append(author)


def parse_bram_stoker_awards(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=None, log=None, progress=None):
  return BramStokerParser().parse(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=fetch_url, log=log, progress=progress)
