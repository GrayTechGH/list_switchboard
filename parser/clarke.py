#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Arthur C. Clarke Award parsers.

Maintenance notes:
- The official Clarke page is the primary source. It exposes winners and
  shortlists on one page as year groups with "Title - Author" rows.
- SFADB exposes one page per award year with Winner, optional Runner-up, and
  Shortlist sections. It stays as the replacement fallback and is the only
  source here that preserves historical runner-up labels.
- The award is always for a novel, so there is no category-selection layer.
  Clarke year pages use a section-result model (headings map to result strings)
  rather than the category/boundary model shared by other SFADB parsers.
  SFADBParser.parse() and year_links() are reused; parse_year() is overridden
  because the per-page structure differs from the standard category pattern.
"""

import re

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import AwardParserBase
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
  from calibre_plugins.list_switchboard.parser.sfadb_base import (
    SFADBParser,
    normalize_heading, normalize_line, strip_publication_notes,
    text_lines, assign_positions,
  )
except ImportError:
  from .award_base import AwardParserBase
  from .generic import position_sort_key
  from .sfadb_base import (
    SFADBParser,
    normalize_heading, normalize_line, strip_publication_notes,
    text_lines, assign_positions,
  )


AWARD_NAME = 'Arthur C. Clarke Award'
CATEGORY_NAME = 'Novel'
RECIPE_NAME = 'Arthur C. Clarke Award - Novel'
YEAR_PAGE_URL = re.compile(r'/Arthur_C_Clarke_Award_(\d{4})$')
OFFICIAL_YEAR = re.compile(r'^((?:19|20)\d{2})(.*)$')
OFFICIAL_DASH_SEPARATOR = re.compile(r'\s+[-\u2013\u2014]\s*|\s*[-\u2013\u2014]\s+')
OFFICIAL_WINNER_SUFFIX = re.compile(r'\s*(?:[-\u2013\u2014]\s*)?winner\s*$', re.I)
OFFICIAL_STOP_TEXT = re.compile(
  r'\s*[-\u2013\u2014_]*\s*(?:to submit titles|contact|submissions for the '
  r'publishing year|the arthur c\.?\s*clarke award is administered).*$',
  re.I)
SECTION_RESULTS = {
  'winner': 'winner',
  'runner up': 'runner-up',
  'runner-up': 'runner-up',
  'shortlist': 'nominee',
}
BOUNDARY_HEADINGS = frozenset({
  'where and when', 'eligibility year', 'judges', 'copyright',
})
OFFICIAL_STOP_HEADINGS = (
  'to submit titles',
  'contact',
  'submissions for the publishing year',
  'the arthur c clarke award is administered',
)


def _split_title_author(text):
  work_text = strip_publication_notes(text)
  if ',' not in work_text:
    return '', ''
  title, author = work_text.rsplit(',', 1)
  return title.strip(), author.strip()


def _is_boundary(line):
  heading = normalize_heading(line)
  if not heading:
    return False
  if heading in BOUNDARY_HEADINGS:
    return True
  return heading.startswith('this page last updated')


def _split_official_row(text):
  matches = list(OFFICIAL_DASH_SEPARATOR.finditer(text))
  if not matches:
    return '', ''
  match = matches[-1]
  return text[:match.start()].strip(), text[match.end():].strip()


def _official_tokens(soup):
  started = False
  for token in soup.stripped_strings:
    text = normalize_line(token)
    if not text:
      continue
    heading = normalize_heading(text)
    if not started:
      marker = heading.find('winners and shortlists')
      if marker < 0:
        continue
      started = True
      text = re.sub(r'^.*?winners\s+and\s+shortlists', '', text, flags=re.I).strip()
      if not text:
        continue
      heading = normalize_heading(text)
    trimmed = OFFICIAL_STOP_TEXT.sub('', text).strip()
    if trimmed != text:
      if trimmed:
        yield trimmed
      break
    if any(heading.startswith(stop) for stop in OFFICIAL_STOP_HEADINGS):
      break
    yield text


class OfficialClarkeParser(AwardParserBase):
  """
  Parser for the official Arthur C. Clarke Award winners/shortlists page.

  Invariants:
  - The official page does not identify runner-up rows. Only explicit WINNER
    markers become winners; all other rows in the year group are nominees.
  - Parsing starts at the "Winners and shortlists" marker so homepage copy,
    judges, and contact text do not become import rows.
  """

  AWARD_NAME = AWARD_NAME

  def parse(self, html, base_url, name=None, category=None,
            category_aliases=None, fetch_url=None, log=None, progress=None):
    soup = BeautifulSoup(html, 'html.parser')
    rows_by_year = {}
    current_year = None
    for token in _official_tokens(soup):
      token_parts = self.year_token_parts(token)
      for year, row_text in token_parts:
        if year is not None:
          current_year = year
          rows_by_year.setdefault(current_year, [])
        if not row_text or current_year is None:
          continue
        parsed = self.parse_item(row_text)
        if parsed is not None:
          rows_by_year.setdefault(current_year, []).append(parsed)

    entries = []
    for year in sorted(rows_by_year):
      rows = [
        self.build_award_entry(row, base_url, year, CATEGORY_NAME)
        for row in rows_by_year[year]
      ]
      entries.extend(assign_positions(rows, year))
    return self.parsed_result(
      name or RECIPE_NAME,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def year_token_parts(self, token):
    parts = []
    remaining = token
    while remaining:
      match = OFFICIAL_YEAR.match(remaining)
      if match is not None:
        year = int(match.group(1))
        rest = match.group(2).strip()
        parts.append((year, rest))
        break
      embedded = re.search(r'\s((?:19|20)\d{2})\s*', remaining)
      if embedded is None:
        parts.append((None, remaining))
        break
      prefix = remaining[:embedded.start()].strip()
      if prefix:
        parts.append((None, prefix))
      remaining = remaining[embedded.start():].strip()
    return parts

  def parse_item(self, text):
    text = normalize_line(text)
    if normalize_heading(text) in ('about us', 'winners and shortlists'):
      return None
    result = 'winner' if OFFICIAL_WINNER_SUFFIX.search(text) else 'nominee'
    text = OFFICIAL_WINNER_SUFFIX.sub('', text).strip(' -\u2013\u2014')
    title, author = _split_official_row(text)
    if not title or not author:
      return None
    return {
      'title': strip_publication_notes(title).strip(' "\u201c\u201d,'),
      'author': strip_publication_notes(author).strip(),
      'result': result,
    }


class ClarkeParser(SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = YEAR_PAGE_URL
  # Not used directly — Clarke pages use section headings, not category/boundary.
  CATEGORY_BOUNDARIES = frozenset()

  def parse(self, overview_html, base_url, name=None, category=None,
            category_aliases=None, fetch_url=None, log=None, progress=None):
    # Clarke has a fixed name and category; callers do not pass them.
    return super().parse(
      overview_html, base_url,
      name=RECIPE_NAME,
      category=CATEGORY_NAME,
      category_aliases=(),
      fetch_url=fetch_url, log=log, progress=progress)

  def parse_year(self, html, source_url, year, category, category_aliases):
    soup_lines = text_lines(BeautifulSoup(html, 'html.parser'))
    rows = []
    result = None
    for line in soup_lines:
      heading = normalize_heading(line)
      if heading in SECTION_RESULTS:
        result = SECTION_RESULTS[heading]
        continue
      if result is None:
        continue
      if _is_boundary(line):
        result = None
        continue
      parsed = self.parse_item(line)
      if parsed is None:
        continue
      parsed['result'] = result
      parsed.update({
        'source_url': source_url,
        'award_year': str(year),
        'award': self.AWARD_NAME,
        'category': CATEGORY_NAME,
      })
      rows.append(parsed)
    return assign_positions(rows, year)

  def parse_item(self, text):
    text = normalize_line(text)
    title, author = _split_title_author(text)
    if not title or not author:
      return None
    return {
      'title': strip_publication_notes(title).strip(' \"\u201c\u201d,'),
      'author': strip_publication_notes(author).strip(),
      'result': 'nominee',  # overwritten by parse_year after section detection
    }


def parse_clarke_award_novel(
    overview_html, base_url, fetch_url=None, log=None, progress=None):
  return ClarkeParser().parse(
    overview_html, base_url,
    fetch_url=fetch_url, log=log, progress=progress)
