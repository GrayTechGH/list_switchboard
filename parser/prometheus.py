#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Prometheus Award parser for SFADB year pages.

Maintenance notes:
- SFADB exposes one overview page with linked yearly award pages.
- The Young Adult Honor Roll is not an SFADB annual category. It uses the
  official LFS standalone reading-list page and its section headings.
- Hall of Fame includes non-book media; that recipe uses books_only=True so
  the imported list stays useful for Calibre matching.
- Hall of Fame ballots may repeat a work for several years. The recipe keeps
  one row per normalized work/credit, promoting winners and otherwise retaining
  the latest nomination.
- books_only is stored as an instance attribute so parse_item() can read it
  without changing its signature (see SFADBParser refactor warning).
- Quoted titles are always short fiction and are rejected unconditionally.
"""

import re

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import AwardParserBase
  from calibre_plugins.list_switchboard.parser.base import (
    entry_source_object, imported_entry,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
  from calibre_plugins.list_switchboard.parser.sfadb_base import (
    SFADBParser, StandardItemMixin,
    normalize_heading, normalize_line, strip_tie_marker,
  )
except ImportError:
  from .award_base import AwardParserBase
  from .base import entry_source_object, imported_entry
  from .generic import position_sort_key
  from .sfadb_base import (
    SFADBParser, StandardItemMixin,
    normalize_heading, normalize_line, strip_tie_marker,
  )


AWARD_NAME = 'Prometheus Award'
YEAR_PAGE_URL = re.compile(r'/Prometheus_Awards_(\d{4})$')
CATEGORY_BOUNDARIES = frozenset({
  'novel', 'hall of fame', 'special award', 'special awards',
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


def _hall_of_fame_entry_key(entry):
  def normalized_identity(value):
    value = normalize_line(value).casefold().replace('&', ' and ')
    return re.sub(r'[^a-z0-9]+', ' ', value).strip()

  authors = entry.get('authors') or (entry.get('author', ''),)
  normalized_authors = []
  for author in authors:
    normalized_author = normalized_identity(author)
    if normalized_author:
      normalized_authors.append(normalized_author)
  return (
    normalized_identity(entry.get('title', '')),
    tuple(sorted(normalized_authors)),
  )


def _hall_of_fame_entry_priority(entry):
  try:
    year = int(entry.get('award_year', 0) or 0)
  except (TypeError, ValueError):
    year = 0
  return entry.get('result') == 'winner', year


def collapse_repeated_hall_of_fame_entries(entries):
  """
  Return one Prometheus Hall of Fame row per normalized work and credit.

  Hall of Fame works may appear on several annual ballots before winning.
  Winners replace every nomination for the same work; otherwise the most
  recent nomination represents the still-pending work.
  """
  selected = {}
  for entry in entries:
    key = _hall_of_fame_entry_key(entry)
    previous = selected.get(key)
    if (
        previous is None
        or _hall_of_fame_entry_priority(entry)
        > _hall_of_fame_entry_priority(previous)):
      selected[key] = entry
  return sorted(
    selected.values(),
    key=lambda item: position_sort_key(item.get('position', '')))


class PrometheusYoungAdultHonorRollParser(AwardParserBase):
  """
  Parse the official LFS Young Adult Honor Roll as a page-ordered book list.

  Invariants:
  - Only ``span.booktitle`` works are imported, excluding unmarked songs.
  - Retail work links never replace the containing official page as provenance.
  - The source's malformed unclosed list items require html5lib repair before
    section and row traversal.
  """

  AWARD_NAME = AWARD_NAME
  CATEGORY = 'Young Adult Honor Roll'
  REQUIRED_HEADINGS = frozenset({
    'best novel winners',
    'hall of fame winners',
    'best novel finalists',
  })

  def parse(self, html, base_url, name):
    html = re.sub(r'^\s*<\?xml[^>]*\?>', '', html or '', count=1, flags=re.I)
    soup = BeautifulSoup(html, 'html5lib')
    headings = {
      normalize_heading(heading.get_text(' ', strip=True))
      for heading in soup.find_all('h2')
    }
    if not self.REQUIRED_HEADINGS.issubset(headings):
      raise ValueError(
        'Official Prometheus Young Adult Honor Roll sections were not found.')

    entries = []
    seen = set()
    for heading in soup.find_all('h2'):
      heading_text = normalize_line(heading.get_text(' ', strip=True))
      default_result = self.result_from_heading(heading_text)
      for row in self.section_rows(heading):
        row_text = normalize_line(row.get_text(' ', strip=True))
        authors = self.authors_from_row(row_text)
        result = default_result or self.result_from_heading(row_text)
        if not authors or result is None:
          continue
        year, recognition_years = self.recognition_years(row_text)
        for title_node in row.select('span.booktitle'):
          title = self.clean_title(title_node.get_text(' ', strip=True))
          key = (
            self.identity_key(title),
            tuple(sorted(self.identity_key(author) for author in authors)),
          )
          if not title or key in seen:
            continue
          seen.add(key)
          metadata = {
            'award': self.AWARD_NAME,
            'category': self.CATEGORY,
            'result': result,
            'recognition': heading_text,
          }
          if year:
            metadata['award_year'] = year
          if len(recognition_years) > 1:
            metadata['recognition_years'] = recognition_years
          entries.append(imported_entry(
            len(entries) + 1,
            title,
            authors,
            source=entry_source_object(base_url),
            **metadata))
    return self.parsed_result(name, base_url, entries)

  def section_rows(self, heading):
    for sibling in heading.find_next_siblings():
      if sibling.name == 'h2':
        break
      for row in sibling.find_all('li'):
        yield row

  def result_from_heading(self, value):
    heading = normalize_heading(value)
    if 'winner' in heading:
      return 'winner'
    if 'finalist' in heading or 'nominee' in heading:
      return 'nominee'
    return None

  def authors_from_row(self, value):
    match = re.search(
      r'\b(?:both\s+)?by\s+(.+?)(?=\s*\([^()]*\)\s*$|$)',
      value,
      re.I)
    if match is None:
      return []
    credit = re.split(
      r'\s+-\s+especially\b',
      match.group(1),
      maxsplit=1,
      flags=re.I)[0]
    return [
      normalize_line(author).strip(' ,')
      for author in re.split(r'\s+(?:and|&)\s+', credit, flags=re.I)
      if normalize_line(author).strip(' ,')
    ]

  def recognition_years(self, value):
    notes = re.findall(r'\(([^()]*)\)', value)
    years = re.findall(r'(?:19|20)\d{2}', notes[-1] if notes else '')
    return (years[-1] if years else ''), years

  def clean_title(self, value):
    return normalize_line(value).strip(' "\u201c\u201d,')

  def identity_key(self, value):
    value = normalize_line(value).casefold().replace('&', ' and ')
    return re.sub(r'[^a-z0-9]+', ' ', value).strip()


class PrometheusParser(StandardItemMixin, SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = CATEGORY_BOUNDARIES

  def __init__(self, books_only=False):
    self.books_only = books_only

  def parse(self, overview_html, base_url, name, category, category_aliases,
            fetch_url=None, log=None, progress=None):
    parsed = super().parse(
      overview_html, base_url, name, category, category_aliases,
      fetch_url=fetch_url, log=log, progress=progress)
    if normalize_heading(category) == 'hall of fame':
      parsed['entries'] = collapse_repeated_hall_of_fame_entries(
        parsed.get('entries', ()))
    return parsed

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
