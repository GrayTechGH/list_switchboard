#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
International Horror Guild Awards parser for official legacy pages and SFADB.

Maintenance notes:
- horroraward.org is the official source. Its final-awards page covers works
  from 2007; prevrec.html covers works from 1994-2006.
- The official pages are old HTML with mixed category shapes: standalone
  headings, inline "CATEGORY: winner" rows, bullets, BR-delimited nominees,
  and list items.
- SFADB is a replacement fallback, not a supplement. Its page years are
  announcement years, so this parser uses SFADB's Eligibility Year when present
  to match the official work-year convention.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, UnicodeDammit

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, split_title_author, strip_editor_marker,
    strip_publication_notes, strip_square_notes, strip_tie_marker,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
  from calibre_plugins.list_switchboard.parser.sfadb_base import (
    SFADBParser, StandardItemMixin, html_root, node_text,
  )
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, split_title_author, strip_editor_marker,
    strip_publication_notes, strip_square_notes, strip_tie_marker,
  )
  from .generic import position_sort_key
  from .sfadb_base import SFADBParser, StandardItemMixin, html_root, node_text


AWARD_NAME = 'International Horror Guild Award'
OFFICIAL_FINAL_URL = 'https://www.horroraward.org/index.html'
OFFICIAL_PREVIOUS_URL = 'https://www.horroraward.org/prevrec.html'
OFFICIAL_METADATA_URL = 'https://www.horroraward.org/ihg.html'
SFADB_URL = 'https://www.sfadb.com/International_Horror_Guild_Awards'
SFADB_YEAR_PAGE_URL = re.compile(r'/International_Horror_Guild_Awards_(\d{4})$')
YEAR_RE = re.compile(r'^(?:19|20)\d{2}$')
WORKS_YEAR_RE = re.compile(r'WORKS?\s+from\s+((?:19|20)\d{2})', re.I)
ELIGIBILITY_YEAR_RE = re.compile(r'Eligibility Year\s*:\s*((?:19|20)\d{2})', re.I)

CATEGORY_BOUNDARIES = frozenset({
  'art', 'artist', 'anthology', 'collection',
  'collection single author', 'fiction collection',
  'film', 'first novel', 'graphic story/illustrated narrative',
  'graphic story illustrated narrative', 'graphic narrative',
  'iillustrated narrative', 'illustrated narrativel',
  'illustrated narrative', 'intermediate form', 'living legend', 'long fiction',
  'long form', 'long story', 'medium fiction', 'mid length fiction',
  'mid-length fiction', 'non fiction', 'non-fiction', 'nonfiction', 'novel',
  'periodical', 'publication', 'short fiction', 'short form', 'short story',
  'special award', 'television', 'television show',
})

OFFICIAL_CATEGORY_LABELS = tuple(sorted(CATEGORY_BOUNDARIES, key=len, reverse=True))

EXPECTED_COVERAGE = {
  'novel': {
    1994: (1, 1), 1995: (1, 1), 1996: (1, 1), 1997: (1, 1),
    1998: (6, 1), 1999: (5, 1), 2000: (5, 1), 2001: (6, 1),
    2002: (6, 1), 2003: (6, 1), 2004: (5, 1), 2005: (5, 1),
    2006: (5, 1), 2007: (5, 1),
  },
  'first novel': {
    1994: (1, 1), 1995: (1, 1), 1996: (1, 1), 1997: (1, 1),
    1998: (5, 2), 1999: (5, 1), 2000: (5, 1), 2001: (5, 1),
    2002: (5, 1), 2003: (6, 1), 2004: (5, 1),
  },
  'long fiction': {
    1994: (1, 1), 1995: (1, 1), 1996: (1, 1), 1997: (1, 1),
    1998: (5, 1), 1999: (5, 1), 2000: (5, 1), 2001: (6, 1),
    2002: (5, 1), 2003: (5, 1), 2004: (4, 1), 2005: (4, 1),
    2006: (5, 1), 2007: (4, 1),
  },
  'mid-length fiction': {
    2002: (5, 2), 2003: (5, 1), 2004: (5, 1), 2005: (4, 1),
    2006: (5, 1), 2007: (4, 1),
  },
  'collection': {
    1994: (1, 1), 1995: (1, 1), 1996: (1, 1), 1997: (1, 1),
    1998: (5, 1), 1999: (5, 1), 2000: (6, 2), 2001: (5, 1),
    2002: (6, 1), 2003: (6, 2), 2004: (5, 1), 2005: (4, 1),
    2006: (4, 2), 2007: (5, 1),
  },
  'anthology': {
    1994: (1, 1), 1995: (1, 1), 1996: (1, 1), 1997: (1, 1),
    1998: (5, 1), 1999: (5, 1), 2000: (5, 1), 2001: (6, 1),
    2002: (5, 1), 2003: (6, 1), 2004: (4, 1), 2006: (3, 1),
    2007: (5, 1),
  },
  'nonfiction': {
    1998: (5, 1), 1999: (5, 1), 2000: (5, 1), 2001: (5, 1),
    2002: (5, 1), 2003: (5, 1), 2004: (4, 1), 2005: (5, 1),
    2006: (5, 1), 2007: (5, 1),
  },
  'illustrated narrative': {
    1994: (1, 1), 1995: (1, 1), 1996: (1, 1), 1997: (1, 1),
    1998: (5, 1), 1999: (4, 1), 2000: (5, 1), 2001: (5, 1),
    2002: (6, 1), 2003: (5, 1), 2004: (5, 1), 2005: (5, 1),
    2006: (4, 1), 2007: (5, 1),
  },
}

SFADB_LONG_FICTION_HEADINGS = {
  1996: ('short form',),
  1997: ('short form',),
  2000: ('long story',),
  2002: ('long form',),
}

SFADB_ILLUSTRATED_CORRECTION = {
  'title': 'Cages',
  'authors': ['David McKean'],
  'result': RESULT_SHORTLISTED,
}

SFADB_PERSON_NAME_CORRECTIONS = {
  'Caitlin_R_Kiernan': 'Caitlín R. Kiernan',
  'China_Mieville': 'China Miéville',
  'R_M_Guera': 'R. M. Guéra',
}

OFFICIAL_EXACT_ROWS = {
  normalize_heading("A Prayer for the Dying Stewart O'Nan Henry Holt"): (
    'A Prayer for the Dying',
    "Stewart O'Nan",
  ),
}

OFFICIAL_EXACT_PREFIX_ROWS = (
  ('Wither by J.G. (Passarella Pocket)',
   'Wither', ('J.G. Passarella',)),
  ('Dead Heat by DelStone, Jr., Dave Dorman, Illustration',
   'Dead Heat', ('Del Stone, Jr.',)),
  ('City Fishing by Steve Rasnic Tem (Silver Salamander)',
   'City Fishing', ('Steve Rasnic Tem',)),
  ('Dark Terrors 4, Stephen Jones & David Sutton, Editors',
   'Dark Terrors 4', ('Stephen Jones', 'David Sutton')),
  ('The Best of Cemetery Dance, Richard Chizmar, Editor',
   'The Best of Cemetery Dance', ('Richard Chizmar',)),
  ('Imagination Fully Dilated, Alan Clark & Elizabeth Engstrom, Editors',
   'Imagination Fully Dilated', ('Alan Clark', 'Elizabeth Engstrom')),
  ('Sirens and Other Daemon Lovers, Ellen Datlow & Terri Windling, Editors',
   'Sirens and Other Daemon Lovers', ('Ellen Datlow', 'Terri Windling')),
  ("The Crow: Shattered Lives and Broken Dreams, J. O'Barr, Ed Kramer, Editors",
   'The Crow: Shattered Lives and Broken Dreams', ("J. O'Barr", 'Ed Kramer')),
  ('Subterranean Gallery, Richard Chizmar & William Schafer, Editors',
   'Subterranean Gallery', ('Richard Chizmar', 'William Schafer')),
  ("The Year's Best Fantasy and Horror, 12th Annual Edition, "
   'Ellen Datlow & Terri Windling, Editors',
   "The Year's Best Fantasy and Horror, 12th Annual Edition",
   ('Ellen Datlow', 'Terri Windling')),
  ('Northern Frights 5, Don Hutchison, Editor',
   'Northern Frights 5', ('Don Hutchison',)),
  ('The Mammoth Book of Best NewHorror, Stephen Jones, Editor',
   'The Mammoth Book of Best New Horror', ('Stephen Jones',)),
  ('White of the Moon: New Tales of Madness and Dread Stephen Jones, Editor',
   'White of the Moon: New Tales of Madness and Dread', ('Stephen Jones',)),
  ('The St. James Guide to Horror, Ghosts and Gothic Writers, '
   'David Pringle, Editor',
   'The St. James Guide to Horror, Ghosts and Gothic Writers',
   ('David Pringle',)),
  ('Fantasy and Horror: A Critical and Historical Guide to Literature, '
   'Illustration, Film, TV, Radio and the Internet, Neil Barron, Editor',
   'Fantasy and Horror: A Critical and Historical Guide to Literature, '
   'Illustration, Film, TV, Radio and the Internet',
   ('Neil Barron',)),
  ('Lord of a Visible World: An Autobiography in Letters by Howard Phillips '
   'Lovecraft, Edited by S. T. Joshi and David E. Schultz',
   'Lord of a Visible World: An Autobiography in Letters',
   ('Howard Phillips Lovecraft', 'S. T. Joshi', 'David E. Schultz')),
  ('S.T. Joshi and Stefan Dziemianowicz, editors. Supernatural Literature '
   'of the World:',
   'Supernatural Literature of the World: An Encyclopedia',
   ('S.T. Joshi', 'Stefan Dziemianowicz')),
  ('Christopher Frayling. Mad, Bad and Dangerous? The Scientists and The Cinema',
   'Mad, Bad and Dangerous? The Scientists and The Cinema',
   ('Christopher Frayling',)),
  ('Kelly Link. Magic for Beginners (Small Beer Press',
   'Magic for Beginners', ('Kelly Link',)),
  ('Flinch #1 - 7 Axel Alonso, Joan Hilty, Editors',
   'Flinch #1-7', ('Axel Alonso', 'Joan Hilty')),
  ('Preacher Ancient History: Ancient History, Garth Ennis-Text, '
   'Richard Case-Art DC',
   'Preacher Ancient History: Ancient History',
   ('Garth Ennis', 'Richard Case')),
  ('The House on the Borderland, adapted by Bruce Corben and Simon '
   'Revelstroke with Lee Loughridge, from novel by William Hope Hodgson',
   'The House on the Borderland',
   ('Bruce Corben', 'Simon Revelstroke', 'William Hope Hodgson')),
  ('"Mostly White," Flinch #9, February 2000, by Bruce Jones and Dave '
   'Taylor with Pamela Rameo',
   'Mostly White, Flinch #9, February 2000',
   ('Bruce Jones', 'Dave Taylor')),
  ('30 DAYS OF NIGHT, Issues #1-3 by Steve Niles (Story), Ben Templesmith '
   '(Art) and Ashley Wood (Covers)',
   '30 DAYS OF NIGHT, Issues #1-3',
   ('Steve Niles', 'Ben Templesmith')),
)

OFFICIAL_IGNORED_PREFIX_ROWS = (
  'An Encyclopedia (Three Volumes) (Greenwood Press)',
)

MISSING_NOMINATION_NOTES = {
  1997: (
    'Official IHG 1997 page states nominations are not listed due to the '
    'changeover in administration and system of nomination and judging.'),
  1996: (
    'Official IHG 1996 page states the 1996, 1995, and 1994 awards were not '
    'administered in the current manner and no nominations are available.'),
  1995: (
    'Official IHG 1995 page states the 1996, 1995, and 1994 awards were not '
    'administered in the current manner and no nominations are available.'),
  1994: (
    'Official IHG 1994 page states the 1996, 1995, and 1994 awards were not '
    'administered in the current manner and no nominations are available.'),
}


def category_key(value):
  return normalize_heading(value).replace('non fiction', 'nonfiction')


def clean_source_text(value):
  value = normalize_line(value).replace('\x00', ' ').replace('\xa0', ' ')
  replacements = {
    '\u2018': "'",
    '\u2019': "'",
    '\u201c': '"',
    '\u201d': '"',
    '\u2022': ' ',
    '&#150;': '-',
    '&#151;': '-',
  }
  for old, new in replacements.items():
    value = value.replace(old, new)
  return normalize_line(value)


def expected_coverage(category):
  return EXPECTED_COVERAGE.get(category_key(category), {})


def require_complete_ihg_result(parsed, category, source_label):
  expected = expected_coverage(category)
  if not expected:
    return parsed
  actual = {}
  for entry in parsed.get('entries', ()):
    year = int(entry.get('award_year', 0) or 0)
    total, winners = actual.get(year, (0, 0))
    actual[year] = (
      total + 1,
      winners + int(entry.get('result') == RESULT_WINNER),
    )
  if actual != expected:
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    mismatched = {
      year: {'expected': expected[year], 'actual': actual.get(year)}
      for year in sorted(set(expected) & set(actual))
      if actual[year] != expected[year]
    }
    raise ValueError(
      f'{source_label} returned incomplete {category} coverage '
      f'(expected {sum(total for total, _winners in expected.values())} rows; '
      f'got {sum(total for total, _winners in actual.values())}; '
      f'missing years={missing}; unexpected years={unexpected}; '
      f'mismatched years={mismatched})')
  return parsed


class InternationalHorrorGuildSFADBParser(StandardItemMixin, SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = SFADB_YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = CATEGORY_BOUNDARIES

  def parse_year(self, html, source_url, year, category, category_aliases):
    eligibility_year = self.eligibility_year(html) or year
    self._current_category = category_key(category)
    source_aliases = category_aliases
    if category_key(category) == 'long fiction':
      source_aliases = SFADB_LONG_FICTION_HEADINGS.get(
        eligibility_year, ('long fiction',))
    rows = super().parse_year(
      html, source_url, eligibility_year, category, source_aliases)
    if category_key(category) == 'illustrated narrative':
      if eligibility_year == 1998 and not any(
          category_key(row.get('title', '')) == 'cages' for row in rows):
        correction = self.build_award_entry(
          SFADB_ILLUSTRATED_CORRECTION,
          OFFICIAL_PREVIOUS_URL,
          eligibility_year,
          category)
        rows.insert(min(2, len(rows)), correction)
      if eligibility_year == 1999:
        rows = [
          row for row in rows
          if category_key(row.get('title', '')) != 'red range'
        ]
      for row in rows:
        row.pop('position', None)
      rows = assign_positions(
        rows, eligibility_year, tied_winners_share_position=True)
    return rows

  def parse_item_node(self, node):
    title_nodes = node.xpath('.//b')
    italic_title = False
    quote_match = None
    if not title_nodes:
      quote_match = re.search(
        r'[\u201c"](.+?)[\u201d"]',
        node_text(node))
      if quote_match is None:
        title_nodes = node.xpath('.//i')
        italic_title = bool(title_nodes)
    person_links = node.xpath('.//a[@href]')
    if not person_links:
      return super().parse_item_node(node)
    if quote_match is not None:
      title = quote_match.group(1)
    elif title_nodes:
      title_node = title_nodes[0]
      title = node_text(title_node)
      tail = clean_source_text(title_node.tail or '').strip()
      if italic_title and re.match(r'^(?:#|\([^)]*(?:series|issue)[^)]*\))', tail, re.I):
        title = normalize_line(
          f'{title} {tail.split(",", 1)[0]}').strip(' ,')
    else:
      return super().parse_item_node(node)
    authors = []
    seen = set()
    for link in person_links:
      previous = link.getprevious()
      before = clean_source_text(
        previous.tail if previous is not None else node.text or '')
      after = clean_source_text(link.tail or '')
      if re.search(r'\btranslated\s+by\s*$', before, re.I):
        continue
      if self._current_category == 'illustrated narrative' and (
          re.search(r'\bwith\s*$', before, re.I) or
          re.search(
            r'\b(?:covers?|colou?rs?|colou?red|letters?|lettered|'
            r'lettering)\s+(?:by\s*)?$',
            before,
            re.I)):
        continue
      if re.match(
          r'^\s*,?\s*\(?\s*(?:covers?|colou?rs?|colou?red|letters?|lettered|'
          r'lettering)\b(?!\s+by\b)',
          after,
          re.I):
        continue
      href_key = (link.get('href') or '').rsplit('/', 1)[-1]
      href_key = href_key.split('?', 1)[0].split('#', 1)[0]
      href_key = re.sub(r'\.html?$', '', href_key, flags=re.I)
      author = SFADB_PERSON_NAME_CORRECTIONS.get(
        href_key,
        node_text(link).strip(' ,'))
      key = author.casefold()
      if author and key not in seen:
        seen.add(key)
        authors.append(author)
    if not title or not authors:
      return super().parse_item_node(node)
    winner_nodes = node.xpath(
      './/*[contains(concat(" ", normalize-space(@class), " "), " winner ")]')
    return {
      'title': title,
      'authors': authors,
      'result': RESULT_WINNER if winner_nodes else RESULT_SHORTLISTED,
    }

  def parse_item(self, text):
    parsed = super().parse_item(text)
    if parsed is not None and parsed.get('result') != RESULT_WINNER:
      parsed['result'] = RESULT_SHORTLISTED
    return parsed

  def eligibility_year(self, html):
    root = html_root(html)
    match = ELIGIBILITY_YEAR_RE.search(node_text(root))
    return int(match.group(1)) if match is not None else None


class InternationalHorrorGuildParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def parse_official(
      self, html, base_url, name, category, category_aliases=(),
      fetch_url=None, log=None, progress=None):
    parsed_results = [
      self.parse_official_page(html, base_url, name, category, category_aliases)
    ]
    if fetch_url is not None and base_url != OFFICIAL_PREVIOUS_URL:
      try:
        previous_html = fetch_url(OFFICIAL_PREVIOUS_URL)
        parsed_results.append(self.parse_official_page(
          previous_html,
          OFFICIAL_PREVIOUS_URL,
          name,
          category,
          category_aliases))
      except Exception as err:
        note = f'Official IHG previous-recipient page failed: {err}'
        parsed_results.append({'entries': (), 'notes': [note]})
        if log is not None:
          log(note)
    rows = []
    notes = [
      'Official IHG 2007 final-awards page includes nominee/shortlist rows.',
      'Official IHG 1998-2006 recipient page generally includes Other '
      'Nominees / Also nominated rows.',
      'Official IHG 1994-1997 sections are winner-only in this parser when '
      'official pages state nominations are unavailable or not listed.',
    ]
    for parsed in parsed_results:
      rows.extend(parsed.get('entries', ()))
      notes.extend(parsed.get('notes', ()))
    return self.parsed_from_rows(name, base_url, rows, self.unique_notes(notes))

  def parse_sfadb(
      self, html, base_url, name, category, category_aliases=(),
      fetch_url=None, log=None, progress=None):
    parsed = InternationalHorrorGuildSFADBParser().parse(
      html,
      base_url,
      name,
      category,
      category_aliases,
      fetch_url=fetch_url,
      log=log,
      progress=progress)
    notes = list(parsed.get('notes', ()))
    notes.append(
      'SFADB is used as a replacement fallback for historical IHG nominee rows; '
      'official IHG pages remain the primary source.')
    if category_key(category) == 'illustrated narrative':
      notes.append(
        'SFADB omits the official 1998 nominee Cages, which is restored from '
        'the official IHG history; SFADB-only 1999 entry Red Range is excluded '
        'to preserve official-history scope.')
    parsed['notes'] = self.unique_notes(notes)
    return parsed

  def parse_official_page(
      self, html, base_url, name, category, category_aliases=()):
    rows = []
    notes = []
    for row in self.official_row_specs(html, category, category_aliases):
      year = row['year']
      if year in MISSING_NOMINATION_NOTES:
        note = MISSING_NOMINATION_NOTES[year]
        if note not in notes:
          notes.append(note)
      parsed = self.parse_work_text(
        row['text'],
        year,
        category,
        row['result'],
        notes,
        title_hint=row.get('title_hint'))
      if parsed is not None:
        rows.append(self.build_award_entry(
          parsed, base_url, year, category))
    return self.parsed_from_rows(name, base_url, rows, notes)

  def official_row_specs(self, html, category, category_aliases):
    soup = self.official_soup(html)
    tags = list(soup.find_all(True))
    order = {id(tag): index for index, tag in enumerate(tags)}
    default_year = self.work_year(clean_source_text(soup.get_text(' ', strip=True)))
    candidates = []
    current_year = default_year
    for tag in tags:
      tag_text = self.node_text_with_breaks(tag)
      if tag.name == 'a':
        anchor_name = normalize_line(tag.get('name', ''))
        if YEAR_RE.match(anchor_name):
          current_year = int(anchor_name)
      elif tag.name in {'h1', 'h2', 'h3', 'h4', 'p'}:
        year_text = clean_source_text(tag_text)
        if YEAR_RE.match(year_text):
          current_year = int(year_text)
      if tag.name not in {'b', 'li'} or current_year is None:
        continue
      text = tag_text
      category_text, remainder = self.category_and_raw_remainder(text)
      if category_text is None:
        continue
      if self.has_category_ancestor(tag):
        continue
      candidates.append({
        'tag': tag,
        'order': order[id(tag)],
        'year': current_year,
        'category': category_text,
        'remainder': remainder,
      })

    rows = []
    for index, candidate in enumerate(candidates):
      if not self.category_matches(
          candidate['category'], category, category_aliases):
        continue
      next_order = (
        candidates[index + 1]['order']
        if index + 1 < len(candidates) else len(tags))
      winner_node = candidate['tag']
      winner_text = candidate['remainder']
      if not winner_text:
        winner_node = self.next_winner_node(
          tags, candidate['order'], next_order)
        if winner_node is None:
          continue
        winner_text = self.node_text_with_breaks(winner_node)
      tied = self.candidate_has_tie(candidate['tag'], winner_node)
      winner_parts = self.split_structural_winners(winner_text, tied)
      winner_hints = self.title_hints(winner_node)
      for winner_part in winner_parts:
        rows.append({
          'year': candidate['year'],
          'text': winner_part,
          'title_hint': self.match_title_hint(winner_part, winner_hints),
          'result': RESULT_WINNER,
        })

      marker_order = self.nominee_marker_order(
        tags, max(candidate['order'], order.get(id(winner_node), 0)), next_order)
      nominee_start = marker_order
      if nominee_start is None and candidate['year'] >= 1998:
        nominee_start = order.get(id(winner_node), candidate['order'])
      nominee_rows = []
      for tag in tags[(nominee_start or next_order) + 1:next_order]:
        if tag.name != 'li':
          continue
        text = self.list_item_text(tag)
        if not text or self.category_and_raw_remainder(text)[0] is not None:
          continue
        nominee_rows.append({
          'year': candidate['year'],
          'text': text,
          'title_hint': self.match_title_hint(
            text, self.title_hints(tag, stop_at_nested_list=True)),
          'result': RESULT_SHORTLISTED,
        })
      if not nominee_rows:
        nominee_rows.extend(self.bullet_nominee_rows(
          candidate['tag'],
          candidates[index + 1]['tag'] if index + 1 < len(candidates) else None,
          candidate['year']))
      rows.extend(nominee_rows)
    return rows

  def node_text_with_breaks(self, node):
    parts = []
    for item in node.descendants:
      if isinstance(item, NavigableString):
        parts.append(str(item))
      elif getattr(item, 'name', None) == 'br':
        parts.append('\n')
    text = ''.join(parts).replace('\x00', ' ')
    return re.sub(r'[ \t\r\f\v]+', ' ', text).strip()

  def list_item_text(self, node):
    parts = []
    for item in node.descendants:
      if getattr(item, 'name', None) == 'li':
        break
      if isinstance(item, NavigableString):
        parts.append(str(item))
      elif getattr(item, 'name', None) == 'br':
        parts.append('\n')
    text = ''.join(parts).replace('\x00', ' ')
    return re.sub(r'[ \t\r\f\v]+', ' ', text).strip()

  def category_and_raw_remainder(self, text):
    text = '\n'.join(
      clean_source_text(line)
      for line in (text or '').splitlines()
      if clean_source_text(line))
    if ':' in text:
      category_text, remainder = text.split(':', 1)
      category_text = self.clean_category_label(category_text)
      if self.is_category_boundary(category_text):
        return category_text, remainder.strip()
    category_text = self.clean_category_label(text)
    if self.is_category_boundary(category_text):
      return category_text, ''
    return None, ''

  def has_category_ancestor(self, tag):
    for parent in tag.parents:
      if getattr(parent, 'name', None) not in {'b', 'li'}:
        continue
      parent_text = self.node_text_with_breaks(parent)
      if self.category_and_raw_remainder(parent_text)[0] is not None:
        return True
    return False

  def next_winner_node(self, tags, start_order, end_order):
    for tag in tags[start_order + 1:end_order]:
      if tag.name != 'b' or tag.find_parent('b') is not None:
        continue
      text = self.node_text_with_breaks(tag)
      if (
          text and not self.is_nominee_marker(text) and
          self.category_and_raw_remainder(text)[0] is None):
        return tag
    return None

  def candidate_has_tie(self, candidate_node, winner_node):
    context = self.node_text_with_breaks(candidate_node)
    sibling = candidate_node.next_sibling
    while sibling is not None and sibling is not winner_node:
      if isinstance(sibling, NavigableString):
        context = f'{context} {sibling}'
      sibling = sibling.next_sibling
    return bool(re.search(r'(?:\btie\b|\*tie\*)', context, re.I))

  def nominee_marker_order(self, tags, start_order, end_order):
    for index in range(start_order + 1, end_order):
      tag = tags[index]
      if self.is_nominee_marker(self.node_text_with_breaks(tag)):
        return index
    return None

  def bullet_nominee_rows(self, candidate_node, next_candidate_node, year):
    rows = []
    buffer = []
    in_nominees = False

    def flush():
      text = clean_source_text(' '.join(buffer))
      buffer.clear()
      text = re.sub(r'^\s*(?:&bull;|•)\s*', '', text)
      if text and not self.is_noise_line(text):
        rows.append({
          'year': year,
          'text': text,
          'title_hint': '',
          'result': RESULT_SHORTLISTED,
        })

    for item in candidate_node.next_elements:
      if item is next_candidate_node:
        break
      if isinstance(item, NavigableString):
        text = clean_source_text(str(item))
        if not text:
          continue
        if self.is_nominee_marker(text):
          in_nominees = True
          buffer.clear()
          continue
        if in_nominees:
          if re.search(r'(?:&bull;|•)', text):
            flush()
          buffer.append(text)
      elif in_nominees and getattr(item, 'name', None) == 'br':
        flush()
    flush()
    return rows

  def split_structural_winners(self, text, tied):
    raw_parts = [
      clean_source_text(part)
      for part in (text or '').splitlines()
      if clean_source_text(part) and
      normalize_heading(clean_source_text(part)) != 'tie'
    ]
    if not tied:
      text = clean_source_text(' '.join(raw_parts))
      return [text] if text else []
    if len(raw_parts) > 1:
      return raw_parts
    text = clean_source_text(' '.join(raw_parts))
    return [
      clean_source_text(part)
      for part in re.split(
        r'(?<=\))\s+and\s+(?=[A-Z"\'])',
        text)
      if clean_source_text(part)
    ]

  def title_hints(self, node, stop_at_nested_list=False):
    hints = []
    for title_node in node.find_all(['i', 'b']):
      if stop_at_nested_list and title_node.find_parent('li') is not node:
        continue
      text = clean_source_text(title_node.get_text(' ', strip=True))
      if (
          text and not self.is_nominee_marker(text) and
          not text.lstrip().startswith(('(', '[')) and
          self.category_and_raw_remainder(text)[0] is None and
          text not in hints):
        hints.append(text)
    return hints

  def match_title_hint(self, text, hints):
    normalized = clean_source_text(text)
    for hint in hints:
      normalized_hint = clean_source_text(hint)
      index = normalized.find(normalized_hint)
      if index >= 0 and normalized[:index].count('(') <= normalized[:index].count(')'):
        return hint
    return ''

  def parse_work_text(
      self, text, year, category, result, notes, title_hint=''):
    text = self.clean_work_text(text)
    if not text or self.is_noise_line(text):
      return None
    if any(
        normalize_heading(text).startswith(normalize_heading(prefix))
        for prefix in OFFICIAL_IGNORED_PREFIX_ROWS):
      return None
    exact = self.official_exact_prefix(text)
    if exact is not None:
      title, authors = exact
      return {
        'title': title,
        'authors': list(authors),
        'result': result,
      }
    parsed = OFFICIAL_EXACT_ROWS.get(normalize_heading(text))
    if parsed is None:
      parsed = self.parse_title_hint(text, title_hint)
    if parsed is None:
      parsed = self.parse_editor_comma(text)
    if parsed is None and category_key(category) == 'illustrated narrative':
      parsed = self.parse_illustrated(text)
    if parsed is None:
      parsed = self.parse_translated_author_first(text)
    if parsed is None:
      parsed = self.parse_by(text)
    if parsed is None:
      parsed = self.parse_dot(text, year)
    if parsed is None:
      parsed = self.parse_comma(text)
    if parsed is None:
      notes.append(
        f'Official IHG {year} {category} row could not be parsed: {text}')
      return None
    title, author = parsed
    title = self.clean_title(title)
    author = clean_source_text(author)
    if not title or not author:
      return None
    authors = self.split_contributors(author)
    if not authors:
      return None
    return {'title': title, 'authors': authors, 'result': result}

  def official_exact_prefix(self, text):
    key = normalize_heading(text)
    for prefix, title, authors in OFFICIAL_EXACT_PREFIX_ROWS:
      if key.startswith(normalize_heading(prefix)):
        return title, authors
    return None

  def parse_translated_author_first(self, text):
    match = re.match(
      r'^(.+?)\s*\(\s*Translated\s+by\s+[^)]+\)\s*\.\s*(.+)$',
      text,
      re.I)
    if match is None:
      return None
    title = re.sub(
      r'\s*[\[(](?:US|UK|Australia)\s*:.*$',
      '',
      match.group(2),
      flags=re.I)
    return strip_publication_notes(title), match.group(1)

  def parse_title_hint(self, text, title_hint):
    title_hint = clean_source_text(title_hint)
    if not title_hint:
      return None
    match = re.search(re.escape(title_hint), text, re.I)
    if match is None:
      return None
    prefix = text[:match.start()].strip(' "\'.,;:-')
    suffix = text[match.end():].strip()
    suffix_credit = strip_publication_notes(suffix).strip(' "\'.,;:-')
    if suffix_credit:
      role_match = re.search(
        r'\s*,?\s*(?:words?|story|art|written|created|adapted|illustrated|'
        r'iillustrated|edited)\s+(?:and\s+(?:art|illustrations?)\s+)?by\s+',
        suffix_credit,
        re.I)
      if role_match is not None:
        title_tail = suffix_credit[:role_match.start()].strip(' ,;')
        if title_tail:
          title_hint = normalize_line(
            f'{title_hint.rstrip(" ,")}, {title_tail}')
        suffix_credit = suffix_credit[role_match.end():]
      suffix_credit = re.sub(
        r'^(?:by|edited\s+by)\s+', '', suffix_credit, flags=re.I)
      return title_hint, suffix_credit
    prefix_credit = strip_publication_notes(prefix).strip(' "\'.,;:-')
    if prefix_credit:
      return title_hint, prefix_credit
    return None

  def parse_illustrated(self, text):
    work_text = strip_publication_notes(clean_source_text(text))
    work_text = re.sub(
      r'(?P<separator>\s*(?:,|;|&|\band\b)\s*)?'
      r'(?P<name>[^,;()]+?)\s*'
      r'\((?:covers?|colou?rs?|colou?red|letters?|lettered|lettering)\)',
      '',
      work_text,
      flags=re.I)
    role_match = re.search(
      r'\s+(?:written|created|adapted|illustrated|iillustrated|'
      r'words?|story|art)\s+(?:and\s+(?:art|illustrations?)\s+)?by\s+',
      work_text,
      re.I)
    if role_match is not None:
      return (
        work_text[:role_match.start()].strip(' ,;'),
        work_text[role_match.end():].strip())
    by_match = re.search(r'\s+by\s+', work_text, re.I)
    if by_match is not None:
      return (
        work_text[:by_match.start()].strip(' ,;'),
        work_text[by_match.end():].strip())
    dash_role = re.search(r'\s*[\u2013\u2014-]\s*(?:text|art)\b', work_text, re.I)
    if dash_role is not None:
      comma_at = work_text.rfind(',', 0, dash_role.start())
      if comma_at > 0:
        return work_text[:comma_at].strip(' ,;'), work_text[comma_at + 1:]
    editor_match = re.match(
      r'^(.*?),\s*(.+?),\s*(?:eds?|editors?)\.?$', work_text, re.I)
    if editor_match is not None:
      return editor_match.group(1), editor_match.group(2)
    return None

  def split_contributors(self, value):
    value = re.sub(
      r',\s*([^,]+),\s*Illustrations?\.?$',
      '',
      value,
      flags=re.I)
    value = re.sub(
      r'(?:\s*(?:,|;|&|\band\b)\s*)?'
      r'[^,;()]+?\s*'
      r'\((?:covers?|colou?rs?|colou?red|letters?|lettered|lettering)\)',
      '',
      value,
      flags=re.I)
    value = self.clean_author(value)
    value = re.sub(
      r'\s*,?\s*(?:translated\s+by|translation\s+by)\s+.+$',
      '',
      value,
      flags=re.I)
    value = re.sub(
      r'\s*\((?:writers?|story|art|artists?|illustrators?|illustrations?|'
      r'creators?(?:/writers?)?|adapters?|adapted|words?)\)\s*',
      ',',
      value,
      flags=re.I)
    value = re.sub(
      r'\b(?:written|created|adapted|illustrated|iillustrated|'
      r'words?|story|art)\s+(?:and\s+(?:art|illustrations?)\s+)?by\b',
      ',',
      value,
      flags=re.I)
    value = re.sub(r'\bfrom\s+(?:the\s+)?novel\s+by\b', ',', value, flags=re.I)
    value = re.sub(r'\s*[\u2013\u2014]\s*(?:text|art)\b', ',', value, flags=re.I)
    value = re.sub(r'\s*,?\s*(?:eds?|editors?)\.?$', '', value, flags=re.I)
    value = clean_source_text(value).strip(' ,;')
    shared_surname = re.fullmatch(
      r'([^,;/&]+?)\s+(?:and|&)\s+([^,;/&]+)', value, flags=re.I)
    if shared_surname is not None:
      left, right = (part.strip() for part in shared_surname.groups())
      right_words = right.split()
      if len(left.split()) == 1 and len(right_words) > 1:
        value = f'{left} {right_words[-1]} & {right}'
    parts = [
      part.strip(' "\'.,;')
      for part in re.split(r'\s*(?:,|;|&|\band\b|\bwith\b)\s*', value, flags=re.I)
      if part.strip(' "\'.,;')
    ]
    authors = []
    seen = set()
    for part in parts:
      if authors and re.fullmatch(r'(?:Jr|Sr|II|III|IV|V)\.?', part, re.I):
        authors[-1] = f'{authors[-1]}, {part}'
        continue
      if category_key(part) in {
          'art', 'artist', 'cover', 'covers', 'illustration', 'illustrations',
          'story', 'text', 'et al',
      }:
        continue
      part = re.sub(r'^DelStone\b', 'Del Stone', part)
      key = part.casefold()
      if key not in seen:
        seen.add(key)
        authors.append(part)
    return authors

  def parse_by(self, text):
    match = re.match(r'^(.+)\s+by\s+(.+)$', text, re.I)
    if match is None:
      return None
    return match.group(1), match.group(2)

  def parse_editor_comma(self, text):
    match = re.match(r'^(.*?),\s*(.+?),?\s+(?:eds?|editors?)\.?$', text, re.I)
    if match is not None:
      return match.group(1), match.group(2)
    match = re.match(r'^(.*?)(?:,\s*)?edited\s+by\s+(.+)$', text, re.I)
    if match is not None:
      return match.group(1), match.group(2)
    return None

  def parse_dot(self, text, year):
    separators = list(re.finditer(r'\s*\.\s+', text))
    if not separators:
      return None
    if year == 2007:
      separator = separators[0]
    else:
      separator = next(
        (
          item for item in separators
          if len(text[:item.start()].strip().split()) >= 2
        ),
        separators[-1])
    first = text[:separator.start()]
    second = text[separator.end():]
    if not first.strip() or not second.strip():
      return None
    if year == 2007:
      return first, second
    return second, first

  def parse_comma(self, text):
    title, author = split_title_author(text)
    if title and author:
      return title, author
    return None

  def clean_work_text(self, text):
    text = clean_source_text(strip_square_notes(strip_tie_marker(text)))
    text = re.sub(r'^\s*(?:&bull;|•|[-*])\s*', '', text)
    text = re.sub(r'\s*\[[^\]]*TIE[^\]]*\]\s*$', '', text, flags=re.I)
    return normalize_line(text.strip(' .,'))

  def clean_title(self, value):
    value = strip_publication_notes(clean_source_text(value))
    value = re.sub(r'\s+edited$', '', value, flags=re.I)
    value = value.strip(' .,')
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
      value = value[1:-1].strip()
    elif value.count('"') == 1:
      value = value.strip('"').strip()
    return value

  def clean_author(self, value):
    value = clean_source_text(value)
    value = re.sub(r'\s+and\s*$', '', value, flags=re.I)
    value = strip_publication_notes(value)
    value = re.sub(r'\s*,?\s*(?:eds?|editors?|illustrations?)\.?$', '', value, flags=re.I)
    value = re.sub(r'^\s*(?:edited\s+by|by)\s+', '', value, flags=re.I)
    return strip_editor_marker(value).strip(' "\'.,')

  def official_lines(self, html):
    soup = self.official_soup(html)
    for removable in soup.find_all(['script', 'style']):
      removable.decompose()
    for br in soup.find_all('br'):
      br.replace_with('\n')
    text = soup.get_text('\n')
    text = text.replace('\x00', ' ')
    raw_lines = []
    for line in text.splitlines():
      for part in re.split(r'\s*(?:\u2022|&bull;)\s*', line):
        part = clean_source_text(part)
        if part:
          raw_lines.append(part)
    return self.join_wrapped_lines(raw_lines)

  def official_soup(self, html):
    if isinstance(html, bytes):
      html = UnicodeDammit(html).unicode_markup
    return BeautifulSoup((html or '').replace('\x00', ' '), 'html.parser')

  def join_wrapped_lines(self, lines):
    joined = []
    buffer = ''
    for line in lines:
      if buffer and buffer.endswith('.') and not self.starts_control_line(line):
        buffer = normalize_line(f'{buffer} {line}')
      elif self.starts_new_logical_line(line):
        if buffer:
          joined.append(buffer)
        buffer = line
      elif buffer:
        buffer = normalize_line(f'{buffer} {line}')
      else:
        buffer = line
    if buffer:
      joined.append(buffer)
    return joined

  def starts_control_line(self, line):
    return (
      YEAR_RE.match(line) or
      self.work_year(line) is not None or
      self.is_nominee_marker(line) or
      self.category_and_remainder(line)[0] is not None)

  def starts_new_logical_line(self, line):
    if self.starts_control_line(line):
      return True
    if re.match(r'^(?:TOP|The IHG Awards|FINAL AWARDS ANNOUNCED)$', line, re.I):
      return True
    if re.match(r'^(?:[A-Z][\w.\'&-]+|")', line):
      return True
    return False

  def work_year(self, line):
    match = WORKS_YEAR_RE.search(line)
    return int(match.group(1)) if match is not None else None

  def is_nominee_marker(self, line):
    return normalize_heading(line) in {'other nominees', 'also nominated'}

  def category_and_remainder(self, line):
    if ':' in line:
      category_text, remainder = line.split(':', 1)
      category_text = self.clean_category_label(category_text)
      if self.is_category_boundary(category_text):
        return category_text, normalize_line(remainder)
    category_text = self.clean_category_label(line)
    if self.is_category_boundary(category_text):
      return category_text, ''
    return None, ''

  def clean_category_label(self, label):
    label = clean_source_text(label)
    label = re.sub(r'\s*\([^)]*tie[^)]*\)\s*', ' ', label, flags=re.I)
    label = re.sub(r'\s*\[[^\]]*tie[^\]]*\]\s*', ' ', label, flags=re.I)
    return normalize_line(label.strip(' :'))

  def is_category_boundary(self, label):
    return category_key(label) in CATEGORY_BOUNDARIES

  def category_matches(self, label, category, category_aliases):
    label_key = category_key(label)
    aliases = {category, *(category_aliases or ())}
    alias_keys = {category_key(alias) for alias in aliases if alias}
    return label_key in alias_keys

  def split_possible_tied_winners(self, text, year, result):
    text = self.clean_work_text(text)
    if not text:
      return []
    if result != RESULT_WINNER or year == 2007:
      return [text]
    return [
      normalize_line(part)
      for part in re.split(
        r'\s+(?=[A-Z][A-Za-z.\'-]+(?:\s+[A-Z][A-Za-z.\'-]+)+\.\s+)',
        text)
      if normalize_line(part)
    ]

  def is_noise_line(self, line):
    heading = normalize_heading(line)
    return (
      heading in {'top', 'the ihg awards', 'final awards announced'} or
      heading.startswith('awards were presented') or
      heading.startswith('the international horror guild awards for work'))

  def parsed_from_rows(self, name, base_url, rows, notes):
    rows = self.dedupe_rows(rows)
    by_year = {}
    for row in rows:
      year = str(row.get('award_year', ''))
      if year:
        clean_row = dict(row)
        clean_row.pop('position', None)
        by_year.setdefault(year, []).append(clean_row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      year_rows = sorted(
        by_year[year],
        key=lambda row: 0 if row.get('result') == RESULT_WINNER else 1)
      entries.extend(assign_positions(
        year_rows, int(year), tied_winners_share_position=True))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=self.unique_notes(notes))

  def dedupe_rows(self, rows):
    ordered = []
    seen = set()
    for row in rows:
      key = (
        row.get('award_year'),
        category_key(row.get('category', '')),
        category_key(row.get('title', '')),
        category_key(row.get('author', '')),
      )
      if key in seen:
        continue
      seen.add(key)
      ordered.append(row)
    return ordered

  def unique_notes(self, notes):
    unique = []
    for note in notes:
      if note and note not in unique:
        unique.append(note)
    return unique


def parse_international_horror_guild_official(
    html, base_url, name, category, category_aliases, fetch_url=None,
    log=None, progress=None):
  return InternationalHorrorGuildParser().parse_official(
    html,
    base_url,
    name,
    category,
    category_aliases,
    fetch_url=fetch_url,
    log=log,
    progress=progress)


def parse_international_horror_guild_sfadb(
    html, base_url, name, category, category_aliases, fetch_url=None,
    log=None, progress=None):
  return InternationalHorrorGuildParser().parse_sfadb(
    html,
    base_url,
    name,
    category,
    category_aliases,
    fetch_url=fetch_url,
    log=log,
    progress=progress)
