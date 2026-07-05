#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Shared helpers for official ALA/YALSA award parsers.

Maintenance notes:
- This base owns only mechanical behavior shared by YALSA award pages:
  current-page fetching, annual/YMA supplement handling, semantic text
  extraction, title/creator cleanup, dedupe, and positioning.
- Award-specific parsers still own source boundaries, heading labels, result
  semantics, and notes. In particular, do not blur true public finalist
  shortlists with Honor Book mappings.
"""

from datetime import date
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key


YMA_URL_TEMPLATE = (
  'https://www.ala.org/news/{year}/01/'
  'american-library-association-announces-{year}-youth-media-award-winners')

SEMANTIC_TAGS = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li')
YEAR_RE = re.compile(r'\b((?:19|20)\d{2})\b')
CREATOR_RE = re.compile(
  r'\s+(written and illustrated by|illustrated and written by|'
  r'written by|illustrated by|created by|edited by|by)\s+',
  re.I)
PUBLISHER_RE = re.compile(
  r'\s*(?:,?\s+(?:and\s+)?(?:co-)?published by|'
  r',?\s+a\s+[^,.;]+?\s+book\s+published by|'
  r'\.?\s+The book is published by)\s+.+$',
  re.I)
CREATOR_PREFIX_RE = re.compile(
  r'^\s*(?:written and illustrated by|illustrated and written by|'
  r'written by|illustrated by|created by|edited by|by)\s+',
  re.I)


def yma_awards_url(year):
  return YMA_URL_TEMPLATE.format(year=int(year))


class YALSAOfficialAwardParserBase(AwardParserBase):
  """
  Base class for official YALSA award sources with current/YMA supplements.

  Type constraints:
  - Subclasses must define AWARD_NAME, CATEGORY, HISTORY_URL, CURRENT_URL,
    CURRENT_FETCH_MESSAGE, CURRENT_FAILED_LABEL, SUPPLEMENT_FETCH_LABEL,
    SUPPLEMENT_FAILED_LABEL, NO_ENTRIES_MESSAGE, and FINAL_NOTE.
  - Subclasses must provide history_rows(), current_page_rows(),
    annual_page_rows(), yma_page_rows(), and annual_award_links().
  """

  AWARD_NAME = ''
  CATEGORY = ''
  HISTORY_URL = ''
  CURRENT_URL = ''
  CURRENT_FETCH_MESSAGE = 'Fetching current YALSA award page'
  CURRENT_FAILED_LABEL = 'Current YALSA award page'
  SUPPLEMENT_FETCH_LABEL = 'YALSA award supplement'
  SUPPLEMENT_FAILED_LABEL = 'YALSA award supplement'
  NO_ENTRIES_MESSAGE = 'No YALSA award entries found on official ALA/YALSA pages.'
  FINAL_NOTE = ''

  def parse(
      self, html, base_url=None, name=None, fetch_url=None,
      current_year=None, current_page=None, supplement_pages=(),
      log=None, progress=None):
    base_url = base_url or self.HISTORY_URL
    name = name or self.AWARD_NAME
    rows = self.history_rows(html, base_url)
    notes = []
    max_history_year = max((int(row['award_year']) for row in rows), default=None)

    current_year = int(current_year or date.today().year)
    annual_urls = {}
    if current_page is not None:
      rows.extend(self.current_page_rows(current_page, self.CURRENT_URL))
      annual_urls.update(self.annual_award_links(current_page, self.CURRENT_URL))
    elif fetch_url is not None:
      try:
        if progress is not None:
          progress(1, 1, self.CURRENT_FETCH_MESSAGE)
        fetched_current_page = fetch_url(self.CURRENT_URL)
        rows.extend(self.current_page_rows(fetched_current_page, self.CURRENT_URL))
        annual_urls.update(self.annual_award_links(fetched_current_page, self.CURRENT_URL))
      except Exception as err:
        notes.append(f'{self.CURRENT_FAILED_LABEL} could not be fetched: {self.CURRENT_URL}: {err}')
        if log is not None:
          log(f'{self.CURRENT_FAILED_LABEL} failed: {self.CURRENT_URL}: {err}')

    for page_url, page_html in supplement_pages or ():
      rows.extend(self.supplement_page_rows(page_html, page_url))

    if fetch_url is not None and max_history_year is not None:
      years = range(max_history_year + 1, current_year + 1)
      total = max(1, len(tuple(years)))
      for index, year in enumerate(range(max_history_year + 1, current_year + 1), 1):
        url = annual_urls.get(year) or yma_awards_url(year)
        try:
          if progress is not None:
            progress(index, total, f'Fetching {year} {self.SUPPLEMENT_FETCH_LABEL}')
          rows.extend(self.supplement_page_rows(fetch_url(url), url))
        except Exception as err:
          notes.append(f'{self.SUPPLEMENT_FAILED_LABEL} could not be fetched: {url}: {err}')
          if log is not None:
            log(f'{self.SUPPLEMENT_FAILED_LABEL} failed: {url}: {err}')

    entries = self.entries_from_rows(self.dedupe_rows(rows))
    if not entries:
      raise ValueError(self.NO_ENTRIES_MESSAGE)
    if self.FINAL_NOTE:
      notes.append(self.FINAL_NOTE)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def supplement_page_rows(self, html, base_url):
    if 'american-library-association-announces' in (base_url or ''):
      return self.yma_page_rows(html, base_url)
    return self.annual_page_rows(html, base_url)

  def annual_award_links_matching(self, html, base_url, pattern):
    soup = BeautifulSoup(html or '', 'html.parser')
    links = {}
    for link in soup.find_all('a', href=True):
      text = normalize_line(link.get_text(' ', strip=True))
      match = re.search(pattern, text, re.I)
      if match is None:
        continue
      links[int(match.group(1))] = urljoin(base_url, link['href'])
    return links

  def section_lines(self, html, is_start_heading, is_next_heading):
    section = []
    in_section = False
    for line in self.text_lines(html):
      key = normalize_heading(line)
      if not in_section and is_start_heading(key):
        in_section = True
      elif in_section and is_next_heading(key):
        break
      if in_section:
        section.append(line)
    return section

  def rows_from_text(self, year, text, result, source_url):
    rows = []
    for part in self.entry_texts(text):
      parsed = self.parse_entry_text(part)
      if parsed is None:
        continue
      title, author = parsed
      if not title or not author:
        continue
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': source_url,
        'category': self.CATEGORY,
      })
    return rows

  def entry_texts(self, text):
    text = self.clean_stage_prefix(text)
    if not text:
      return []
    if re.search(r'["\u201c]', text):
      return self.quoted_entry_texts(text)
    if ';' in text:
      return [part.strip(' ,.;') for part in re.split(r'\s*;\s*(?:and\s+)?', text) if part.strip()]
    text = PUBLISHER_RE.sub('', text).strip()
    return self.creator_scanned_entry_texts(text)

  def quoted_entry_texts(self, text):
    pieces = []
    for match in re.finditer(r'["\u201c][^"\u201d]+["\u201d]', text):
      start = match.start()
      end = match.end()
      next_match = re.search(r'\s*(?:;|,)?\s*(?:and\s+)?["\u201c]', text[end:])
      piece_end = end + next_match.start() if next_match is not None else len(text)
      pieces.append(text[start:piece_end].strip(' ,.;'))
    return pieces or [text]

  def creator_scanned_entry_texts(self, text):
    matches = list(CREATOR_RE.finditer(text))
    if len(matches) <= 1:
      return [text.strip(' ,.;')] if text.strip(' ,.;') else []

    parts = []
    start = 0
    for index, match in enumerate(matches):
      next_match = matches[index + 1] if index + 1 < len(matches) else None
      if next_match is None:
        parts.append(text[start:].strip(' ,.;'))
        break
      if next_match.group(1).casefold().startswith('illustrated'):
        continue
      prefix = text[match.end():next_match.start()]
      split = self.split_before_next_title(prefix)
      if split is None:
        continue
      split_index, delimiter_length = split
      part_end = match.end() + split_index
      parts.append(text[start:part_end].strip(' ,.;'))
      start = match.end() + split_index + delimiter_length
    return [part for part in parts if part]

  def split_before_next_title(self, value):
    for pattern in (r';\s*(?:and\s+)?', r',\s+and\s+', r',\s+'):
      match = re.search(pattern, value)
      if match is not None:
        return match.start(), match.end() - match.start()
    return None

  def parse_entry_text(self, text):
    text = self.clean_entry_text(text)
    if not text:
      return None
    quote_offsets = [offset for offset in (text.find('"'), text.find('\u201c')) if offset >= 0]
    if quote_offsets:
      text = text[min(quote_offsets):].strip()
    quoted = re.match(r'^["\u201c]([^"\u201d]+)["\u201d]\s*,?\s*(.+)$', text)
    if quoted is not None:
      return quoted.group(1).strip(' ,'), self.clean_creator_text(quoted.group(2))

    match = re.match(
      r'^(.+?)\s*,?\s+(?:written and illustrated by|illustrated and written by|'
      r'written by|illustrated by|created by|edited by|by)\s+(.+)$',
      text,
      re.I)
    if match is None:
      return None
    return (
      self.clean_title_text(match.group(1)),
      self.clean_creator_text(match.group(2)))

  def clean_stage_prefix(self, text):
    text = normalize_line(text)
    text = re.sub(r'^\s*(?:winners?|finalists?)\s*:?\s*', '', text, flags=re.I)
    return text.strip()

  def clean_entry_text(self, text):
    text = self.clean_stage_prefix(text)
    text = re.sub(r'\bb\s+y\b', 'by', text)
    text = PUBLISHER_RE.sub('', text).strip()
    text = re.sub(r'\s+\.$', '', text).strip()
    return text.strip(' ,.;')

  def clean_title_text(self, text):
    return strip_publication_notes(normalize_line(text)).strip(' "\'\u2018\u2019\u201c\u201d,.;:')

  def clean_creator_text(self, text):
    text = normalize_line(text)
    text = PUBLISHER_RE.sub('', text).strip(' .')
    text = re.sub(r',?\s+(?:has been|was)\s+named\s+.+$', '', text, flags=re.I)
    text = CREATOR_PREFIX_RE.sub('', text)
    text = strip_publication_notes(text)
    text = re.sub(r'\s+and\s+$', '', text, flags=re.I)
    return normalize_line(text).strip(' "\'\u2018\u2019\u201c\u201d,.;:')

  def text_lines(self, html):
    soup = BeautifulSoup(html or '', 'html.parser')
    for removable in soup.find_all(['script', 'style', 'sup']):
      removable.decompose()
    lines = []
    for node in soup.find_all(SEMANTIC_TAGS):
      text = normalize_line(node.get_text(' ', strip=True))
      if text:
        lines.append(text)
    if lines:
      return lines
    text = soup.get_text('\n')
    return [normalize_line(line) for line in text.splitlines() if normalize_line(line)]

  def year_from_url_or_lines(self, url, lines):
    match = YEAR_RE.search(url or '')
    if match is not None:
      return int(match.group(1))
    for line in lines:
      match = YEAR_RE.search(line)
      if match is not None:
        return int(match.group(1))
    return None

  def dedupe_rows(self, rows):
    by_key = {}
    for row in rows:
      key = (row.get('award_year', ''), normalize_heading(row.get('title', '')))
      current = by_key.get(key)
      if current is None:
        by_key[key] = row
        continue
      if row.get('result') == RESULT_WINNER and current.get('result') != RESULT_WINNER:
        by_key[key] = row
      elif row.get('result') == current.get('result') and len(row.get('author', '')) > len(current.get('author', '')):
        by_key[key] = row
    return list(by_key.values())

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(int(row['award_year']), []).append(row)
    entries = []
    for year in sorted(by_year):
      year_rows = sorted(
        by_year[year],
        key=lambda row: 0 if row.get('result') == RESULT_WINNER else 1)
      positioned = assign_positions(year_rows, year, tied_winners_share_position=True)
      for row in positioned:
        entries.append(self.build_award_entry(
          row,
          row.get('source_url') or self.HISTORY_URL,
          year,
          row.get('category') or self.CATEGORY,
          award=self.AWARD_NAME))
    return entries
