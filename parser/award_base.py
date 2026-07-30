#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Shared helpers for award-list parsers.

Maintenance notes:
- This module is award-generic. Source-shape parsers such as SFADB, official
  history pages, and table/archive pages should still own their page traversal.
- Helpers here preserve the shared award entry contract used by import recipes:
  title, authors, position, source, award_year, award, category, and result.
- Amazon retail links are never award provenance. Source-specific parsers
  should retain the containing page when known; parsed_result() provides a
  list-level safety net for award parsers that still expose an Amazon URL.
- Wikipedia work/article links are identity metadata, not award provenance.
  Wikipedia-backed results retain the containing list page as their source.
- LibraryThing work links follow the same rule: the containing award/category
  page is the source that establishes the result.
- Non-award sources such as book clubs and community lists should inherit from
  ListParserBase directly.
"""

import re
from urllib.parse import urljoin, urlsplit

DEFAULT_AUTHOR_NAME_SUFFIXES = (
  'Jr', 'Sr', 'Inc', 'Ph.D', 'Phd', 'MD', 'M.D', 'I', 'II', 'III', 'IV',
  'Junior', 'Senior',
)
AWARD_AUTHOR_SUFFIXES = ('Jr', 'Sr', 'II', 'III', 'IV', 'V')

try:
  from calibre.utils.config import tweaks
except ImportError:
  tweaks = {'author_name_suffixes': DEFAULT_AUTHOR_NAME_SUFFIXES}

try:
  from calibre_plugins.list_switchboard.parser.base import (
    entry_source_object, imported_entry, parsed_source, ListParserBase)
except ImportError:
  from .base import entry_source_object, imported_entry, parsed_source, ListParserBase


RESULT_WINNER = 'winner'
RESULT_NOMINEE = 'nominee'
RESULT_SHORTLISTED = 'shortlisted'
RESULT_LONGLISTED = 'longlisted'


def normalize_line(value):
  return re.sub(r'\s+', ' ', value or '').strip()


def normalize_heading(value):
  value = normalize_line(value).casefold()
  value = value.replace('&', ' and ')
  value = re.sub(r'[^a-z0-9/]+', ' ', value)
  return re.sub(r'\s+', ' ', value).strip()


def award_entry_source_url(href, page_url):
  """Resolve an entry link without replacing award provenance with Amazon."""
  source_url = urljoin(page_url, href or '')
  return page_url if is_amazon_retail_url(source_url) else source_url


def is_amazon_retail_url(url):
  hostname = (urlsplit(url or '').hostname or '').casefold().rstrip('.')
  return (
    hostname == 'amzn.to' or
    hostname == 'amzn.eu' or
    hostname.startswith('amazon.') or
    '.amazon.' in hostname
  )


def is_wikipedia_url(url):
  hostname = (urlsplit(url or '').hostname or '').casefold().rstrip('.')
  return hostname == 'wikipedia.org' or hostname.endswith('.wikipedia.org')


def is_librarything_url(url):
  hostname = (urlsplit(url or '').hostname or '').casefold().rstrip('.')
  return hostname == 'librarything.com' or hostname.endswith('.librarything.com')


def strip_publication_notes(value):
  value = strip_square_notes(normalize_line(value))
  while True:
    stripped = re.sub(r'\s*(?:\([^()]*\)|\[[^\[\]]*\])\s*$', '', value).strip()
    if stripped == value:
      return value
    value = stripped


def strip_square_notes(value):
  return re.sub(r'\s*\[[^\[\]]*\]\s*$', '', value or '').strip()


def strip_tie_marker(value):
  value = re.sub(r'^\s*\(tie\)\s*:?\s*', '', value, flags=re.I)
  value = re.sub(r'\s*\(tie\)\s*$', '', value, flags=re.I)
  return value.strip()


def strip_editor_marker(value):
  return re.sub(
    r'(?:,\s*|\s+)(?:eds?|editors?)\.?\s*$',
    '',
    value,
    flags=re.I).strip()


def _normalize_author_suffix(value):
  return normalize_line(value).casefold().rstrip('.')


def _combined_author_suffixes(configured=()):
  return {
    _normalize_author_suffix(suffix)
    for suffix in (
      *AWARD_AUTHOR_SUFFIXES,
      *DEFAULT_AUTHOR_NAME_SUFFIXES,
      *(configured or ()),
    )
    if normalize_line(suffix)
  }


AUTHOR_NAME_SUFFIXES = _combined_author_suffixes(
  tweaks.get('author_name_suffixes', ()))


def is_author_suffix(value):
  return _normalize_author_suffix(value) in AUTHOR_NAME_SUFFIXES


def _split_suffix_coauthor(value):
  match = re.match(
    r'^\s*(jr\.?|sr\.?|ii|iii|iv|v)\s*,?\s*(?:&|and|with)\s+(.+)$',
    value,
    re.I)
  if match is None:
    return None
  return match.group(1).strip(), match.group(2).strip()


def split_title_author_byline(text):
  """
  Split a source-contract ``Title by Author`` byline at its final boundary.

  Use this only when the source defines the final `` by `` phrase as the
  author delimiter. A non-greedy/first split corrupts titles that contain the
  word themselves, such as ``Never Judge a Lady by Her Cover``.
  """
  match = re.match(r'^(.+)\s+by\s+(.+)$', normalize_line(text), re.I)
  if match is None:
    return '', ''
  return match.group(1).strip(), match.group(2).strip()


def split_title_author(text):
  """
  Split 'Title, Author (publisher)' rows into title and author.

  Handles:
  - 'Title, Author, ed.' / 'Title, Author, eds.' editor patterns.
  - Author suffixes like 'Jr.' that should stay attached to the author.
  - Coauthors after suffixes, such as 'Author, Jr., with Coauthor'.
  """
  work_text = strip_publication_notes(text)
  editor_match = re.match(r'^(.*),\s*(.+?),\s*eds?\.?$', work_text, re.I)
  if editor_match is not None:
    return editor_match.group(1).strip(), editor_match.group(2).strip()
  if ',' not in work_text:
    return '', ''
  title, author = work_text.rsplit(',', 1)
  if is_author_suffix(author):
    title, author_base = title.rsplit(',', 1) if ',' in title else ('', title)
    author = f'{author_base.strip()}, {author.strip()}'
  else:
    suffix_coauthor = _split_suffix_coauthor(author)
    if suffix_coauthor is not None and ',' in title:
      title, author_base = title.rsplit(',', 1)
      suffix, coauthor = suffix_coauthor
      author = f'{author_base.strip()}, {suffix} & {coauthor}'
    elif re.match(r'^\s*(?:&|and|with)\s+', author, re.I) and ',' in title:
      previous_title, author_suffix = title.rsplit(',', 1)
      if is_author_suffix(author_suffix) and ',' in previous_title:
        title, author_base = previous_title.rsplit(',', 1)
        coauthor = re.sub(r'^\s*(?:&|and|with)\s+', '', author, flags=re.I).strip()
        author = f'{author_base.strip()}, {author_suffix.strip()} & {coauthor}'
  return title.strip(), author.strip()


def text_lines(soup):
  """
  Extract text lines from a BeautifulSoup document.

  Prefers block-tag extraction because it preserves semantic boundaries. Falls
  back to newline-split plain text for pages that use only <br> separators.
  """
  block_lines = [
    normalize_line(node.get_text(' ', strip=True))
    for node in soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'li'])
  ]
  block_lines = [line for line in block_lines if line]
  if block_lines:
    return block_lines
  for br in soup.find_all('br'):
    br.replace_with('\n')
  text = soup.get_text(' ')
  text = re.sub(r'\s*\n\s*', '\n', text)
  return [normalize_line(line) for line in text.splitlines() if normalize_line(line)]


def parse_winner_prefix(text):
  """
  Strip winner markers and return (cleaned_text, result).

  Refactor warning:
  - Prefix and suffix winner markers both appear in real award history pages.
    Do not collapse this to one form.
  """
  text = strip_tie_marker(strip_square_notes(normalize_line(text)))
  winner_match = re.match(r'^winner(?:\s*\(\s*tie\s*\))?\s*:\s*(.+)$', text, re.I)
  if winner_match is not None:
    return winner_match.group(1).strip(), RESULT_WINNER
  if re.search(r'\(\s*winner\s*\)\s*$', text, re.I):
    text = re.sub(r'\s*\(\s*winner\s*\)\s*$', '', text, flags=re.I).strip()
    return text, RESULT_WINNER
  return text, RESULT_NOMINEE


def assign_positions(rows, year, tied_winners_share_position=False):
  """
  Convert a list of award rows into entries with year-based positions.

  Position contract:
  - First winner in the year: str(year)
  - If tied_winners_share_position is true, every winner row gets str(year)
  - All other rows: '{year}.{suffix:02d}' with a counter that increments for
    every non-first-winner row, regardless of result type.
  """
  entries = []
  suffix_index = 0
  winner_seen = False
  for row in rows:
    if row.get('result') == RESULT_WINNER and (
        tied_winners_share_position or not winner_seen):
      position = str(year)
      winner_seen = True
    else:
      suffix_index += 1
      position = f'{year}.{suffix_index:02d}'
    entry = dict(row)
    entry['position'] = position
    entries.append(entry)
  return entries


class AwardParserBase(ListParserBase):
  """
  Base class for award parsers that share the standard parsed-entry contract.

  Invariants:
  - Award parsers default to match_series = False.
  - Source-specific subclasses still own parse() because award sites expose
    different page, table, archive, and fallback shapes.
  """

  AWARD_NAME = ''
  MATCH_SERIES = False

  def build_award_entry(self, row, source_url, year, category, award=None):
    metadata = dict(row)
    title = metadata.pop('title', '')
    authors = metadata.pop('authors', metadata.pop('author', ''))
    position = metadata.pop('position', '')
    metadata.pop('source_url', None)
    metadata.update({
      'award_year': str(year),
      'award': award or self.AWARD_NAME,
      'category': category,
    })
    return imported_entry(
      position, title, authors,
      source=entry_source_object(source_url),
      **metadata)

  def parsed_result(self, name, url, entries, notes=None):
    normalized_entries = []
    for entry in entries:
      source = entry.get('source') if isinstance(entry, dict) else None
      source_url = source.get('url') if isinstance(source, dict) else ''
      linked_wikipedia_article = (
        source_url != url and is_wikipedia_url(url) and is_wikipedia_url(source_url))
      linked_librarything_work = (
        source_url != url and is_librarything_url(url) and is_librarything_url(source_url))
      if (is_amazon_retail_url(source_url) or linked_wikipedia_article or
          linked_librarything_work):
        entry = dict(entry)
        source = dict(source)
        source['url'] = url
        entry['source'] = source
      normalized_entries.append(entry)
    return {
      'name': name,
      'source': parsed_source(name, url),
      'entries': normalized_entries,
      'notes': notes or [],
      'match_series': self.MATCH_SERIES,
    }
