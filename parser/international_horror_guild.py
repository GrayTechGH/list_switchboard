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

from bs4 import BeautifulSoup, UnicodeDammit

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
  'graphic story illustrated narrative', 'illustrated narrativel',
  'illustrated narrative', 'living legend', 'long fiction',
  'mid length fiction', 'mid-length fiction', 'non fiction', 'non-fiction',
  'nonfiction', 'novel', 'periodical', 'publication', 'short fiction',
  'special award', 'television',
})

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


class InternationalHorrorGuildSFADBParser(StandardItemMixin, SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = SFADB_YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = CATEGORY_BOUNDARIES

  def parse_year(self, html, source_url, year, category, category_aliases):
    eligibility_year = self.eligibility_year(html) or year
    return super().parse_year(
      html, source_url, eligibility_year, category, category_aliases)

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
    parsed['notes'] = self.unique_notes(notes)
    return parsed

  def parse_official_page(
      self, html, base_url, name, category, category_aliases=()):
    rows = []
    notes = []
    current_year = None
    current_category = None
    target_category = False
    nominee_mode = False
    lines = self.official_lines(html)
    for line in lines:
      work_year = self.work_year(line)
      if work_year is not None:
        current_year = work_year
        current_category = None
        target_category = False
        nominee_mode = False
        continue
      if YEAR_RE.match(line):
        current_year = int(line)
        current_category = None
        target_category = False
        nominee_mode = False
        continue
      if current_year in MISSING_NOMINATION_NOTES:
        note = MISSING_NOMINATION_NOTES[current_year]
        if note not in notes:
          notes.append(note)
      if self.is_nominee_marker(line):
        nominee_mode = True
        continue
      category_text, remainder = self.category_and_remainder(line)
      if category_text is not None:
        current_category = category_text
        target_category = self.category_matches(
          category_text, category, category_aliases)
        nominee_mode = False
        if target_category and remainder:
          rows.extend(self.rows_from_work_text(
            remainder,
            base_url,
            current_year,
            category,
            RESULT_WINNER,
            notes))
        continue
      if not target_category or current_year is None:
        continue
      result = RESULT_SHORTLISTED if nominee_mode else RESULT_WINNER
      rows.extend(self.rows_from_work_text(
        line, base_url, current_year, category, result, notes))
    return self.parsed_from_rows(name, base_url, rows, notes)

  def rows_from_work_text(self, text, source_url, year, category, result, notes):
    if year is None:
      return []
    parsed_rows = []
    for work_text in self.split_possible_tied_winners(text, year, result):
      parsed = self.parse_work_text(work_text, year, category, result, notes)
      if parsed is not None:
        parsed_rows.append(self.build_award_entry(
          parsed, source_url, year, category))
    return parsed_rows

  def parse_work_text(self, text, year, category, result, notes):
    text = self.clean_work_text(text)
    if not text or self.is_noise_line(text):
      return None
    parsed = self.parse_by(text)
    if parsed is None:
      parsed = self.parse_editor_comma(text)
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
    author = self.clean_author(author)
    if not title or not author:
      return None
    return {'title': title, 'author': author, 'result': result}

  def parse_by(self, text):
    match = re.match(r'^(.*?)\s+by\s+(.+)$', text, re.I)
    if match is None:
      return None
    return match.group(1), match.group(2)

  def parse_editor_comma(self, text):
    match = re.match(r'^(.*?),\s*(.+?),?\s+(?:eds?|editors?)\.?$', text, re.I)
    if match is not None:
      return match.group(1), match.group(2)
    match = re.match(r'^(.*?),\s*edited\s+by\s+(.+)$', text, re.I)
    if match is not None:
      return match.group(1), match.group(2)
    return None

  def parse_dot(self, text, year):
    separators = list(re.finditer(r'\s*\.\s+', text))
    if not separators:
      return None
    separator = separators[0] if year == 2007 else separators[-1]
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
    return normalize_line(text.strip(' "\'.,'))

  def clean_title(self, value):
    value = strip_publication_notes(clean_source_text(value))
    return value.strip(' "\'.,')

  def clean_author(self, value):
    value = strip_publication_notes(clean_source_text(value))
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
