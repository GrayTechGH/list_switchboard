#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Shared base class for SFADB award parsers.

Maintenance notes:
- All SFADB award pages follow the same structure: one overview page with year
  links, one page per year with category headings and bullet rows.
- Subclasses must define AWARD_NAME, YEAR_PAGE_URL, CATEGORY_BOUNDARIES, and
  implement parse_item().
- parse_item() receives a normalized line and returns a dict with 'title',
  'author', and 'result', or None to skip the row.
- The position-assignment contract: winner rows in a year get str(year),
  preserving tied winners; nominees get year.NN with a two-digit suffix. If a
  year has no winner, all rows get year.NN suffixes.
- Subclasses that need extra parse_item arguments (books_only, skip_quoted)
  should bind those via instance attributes set in __init__ or class attributes,
  not by overriding the calling convention of parse_item().
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, assign_positions, is_author_suffix, normalize_heading,
    normalize_line, parse_winner_prefix, split_title_author,
    strip_editor_marker, strip_publication_notes, strip_square_notes,
    strip_tie_marker, text_lines,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    AwardParserBase, assign_positions, is_author_suffix, normalize_heading,
    normalize_line, parse_winner_prefix, split_title_author,
    strip_editor_marker, strip_publication_notes, strip_square_notes,
    strip_tie_marker, text_lines,
  )
  from .generic import position_sort_key


YEAR_LINK = re.compile(r'^(19|20)\d{2}$')


# ---------------------------------------------------------------------------
# Base parser class
# ---------------------------------------------------------------------------

class SFADBParser(AwardParserBase):
  """
  Base class for SFADB award parsers that follow the overview/year-page pattern.

  Type constraints:
  - AWARD_NAME: str, used in every entry dict.
  - YEAR_PAGE_URL: compiled re.Pattern, must have one capture group for the year.
  - CATEGORY_BOUNDARIES: frozenset or set of normalized heading strings that
    signal the end of the current category section.

  Invariants:
  - parse() is the public entry point; it orchestrates year-link discovery,
    per-year fetching, and entry collection.
  - parse_item() is the per-row parser. It receives a raw text line and returns
    a dict with 'title', 'author', and 'result', or None to skip the row.
  - category_lines() uses normalize_heading() against CATEGORY_BOUNDARIES, so
    subclasses only need to define the boundary set, not the loop logic.

  Refactor warning:
  - Do not add optional kwargs to parse_item(). Filtering variations (books_only,
    skip_quoted) belong as instance or class attributes read inside parse_item().
  """

  AWARD_NAME = ''
  YEAR_PAGE_URL = None      # compiled regex with one capture group for the year
  CATEGORY_BOUNDARIES = frozenset()

  def parse(self, overview_html, base_url, name, category, category_aliases,
            fetch_url=None, log=None, progress=None):
    soup = BeautifulSoup(overview_html, 'html.parser')
    year_links = self.year_links(soup, base_url)
    entries = []
    notes = []
    self._progress(progress, 0, len(year_links), f'Preparing {name} year pages...')
    for index, year_link in enumerate(year_links, start=1):
      year = year_link['year']
      url = year_link['url']
      self._progress(progress, index, len(year_links),
                     f'Fetching {self.AWARD_NAME} {year}...')
      try:
        html = fetch_url(url) if fetch_url is not None else ''
      except Exception as err:
        notes.append(f'{self.AWARD_NAME} {year} could not be fetched: {err}')
        self._log(log, 'fetch-failed', {'year': year, 'url': url, 'error': str(err)})
        continue
      year_entries = self.parse_year(html, url, year, category, category_aliases)
      if year_entries:
        entries.extend(year_entries)
        self._log(log, 'year-parsed',
                  {'year': year, 'url': url, 'entries': len(year_entries)})
      else:
        self._log(log, 'year-skipped',
                  {'year': year, 'url': url, 'category': category})
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes)

  def year_links(self, soup, base_url):
    links = []
    seen = set()
    for link in soup.find_all('a', href=True):
      text = link.get_text(' ', strip=True)
      if not YEAR_LINK.match(text):
        continue
      url = urljoin(base_url, link['href'])
      match = self.YEAR_PAGE_URL.search(url)
      if match is None:
        continue
      year = int(match.group(1))
      if year in seen:
        continue
      seen.add(year)
      links.append({'year': year, 'url': url})
    return sorted(links, key=lambda item: item['year'])

  def parse_year(self, html, source_url, year, category, category_aliases):
    soup = BeautifulSoup(html, 'html.parser')
    category_rows = self.category_block_lines(soup, category_aliases)
    if category_rows is not None:
      rows = []
      for line in category_rows:
        parsed = self.parse_item(line)
        if parsed is not None:
          rows.append(self.build_award_entry(parsed, source_url, year, category))
      return assign_positions(rows, year, tied_winners_share_position=True)

    rows = []
    for line in self.category_lines(text_lines(soup), category_aliases):
      parsed = self.parse_item(line)
      if parsed is not None:
        rows.append(self.build_award_entry(parsed, source_url, year, category))
    return assign_positions(rows, year, tied_winners_share_position=True)

  def category_block_lines(self, soup, aliases):
    """
    Return item rows from SFADB's div.categoryblock layout when present.

    SFADB's live pages use a category heading div followed by list rows inside
    the same categoryblock. Older fixtures and some saved samples use simple
    paragraph headings, so callers fall back to text_lines() when no structural
    category blocks are found.
    """
    blocks = soup.find_all('div', class_='categoryblock')
    if not blocks:
      return None
    normalized_aliases = {normalize_heading(alias) for alias in aliases}
    selected = []
    for block in blocks:
      heading_node = block.find('div', class_='category')
      heading = normalize_heading(heading_node.get_text(' ', strip=True) if heading_node else '')
      if heading not in normalized_aliases:
        continue
      for item in block.find_all('li'):
        line = normalize_line(item.get_text(' ', strip=True))
        if line:
          selected.append(line)
    return selected

  def category_lines(self, lines, aliases):
    normalized_aliases = {normalize_heading(alias) for alias in aliases}
    in_category = False
    selected = []
    for line in lines:
      heading = normalize_heading(line)
      if heading in normalized_aliases:
        in_category = True
        continue
      if in_category and self.is_category_boundary(line):
        break
      if in_category:
        selected.append(line)
    return selected

  def is_category_boundary(self, line):
    heading = normalize_heading(line)
    return bool(heading) and heading in self.CATEGORY_BOUNDARIES

  def parse_item(self, text):
    """
    Parse one category line into {'title', 'author', 'result'} or return None.

    Subclasses must override this. The base implementation handles the common
    'Winner: Title, Author (publisher)' and '(winner)' suffix shapes.
    Subclasses that need additional filtering (books_only, skip_quoted, etc.)
    should check instance attributes here rather than changing the signature.
    """
    raise NotImplementedError

  def _log(self, log, label, data):
    if log is not None:
      log(f'{self.AWARD_NAME} {label}: {data}')

  def _progress(self, progress, done, total, message):
    if progress is not None:
      progress(done, total, message)


# ---------------------------------------------------------------------------
# Mixin for the common Winner:/comma-split item shape
# ---------------------------------------------------------------------------

class StandardItemMixin:
  """
  parse_item() for awards that use 'Title, Author (publisher)' rows with
  optional 'Winner:' prefix or '(winner)' suffix.

  Invariants:
  - 'no award' rows are silently dropped.
  - Editor suffixes (', ed.' / ', eds.') are stripped from the author field.
  - Tie markers are stripped before title/author splitting.

  Subclasses may override _filter_item(text) -> bool to reject rows before
  title/author splitting (e.g. quoted-title or non-book filtering).
  """

  def parse_item(self, text):
    text, result = parse_winner_prefix(text)
    if normalize_heading(text) == 'no award':
      return None
    if not self._filter_item(text):
      return None
    title, author = split_title_author(text)
    if not title or not author:
      return None
    return {
      'title': strip_publication_notes(title).strip(' \"\u201c\u201d,'),
      'author': strip_editor_marker(strip_publication_notes(author)).strip(),
      'result': result,
    }

  def _filter_item(self, text):
    """Return False to drop this row before title/author splitting."""
    return True
