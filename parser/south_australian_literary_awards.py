#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
South Australian Literary Awards parsers.

Maintenance notes:
- V1 is winner-only. The official SLSA archive and Wikipedia expose stable
  winner history, but not a nominee-complete historical shortlist archive.
- Category matching is source-specific and intentionally narrow so fellowships,
  manuscript, poetry, theatre, multimedia, innovation, and person-only awards
  do not leak into the core published-book recipes.
"""

import re
import unicodedata
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, RESULT_WINNER, assign_positions, normalize_heading,
    normalize_line, split_title_author, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_WINNER, assign_positions, normalize_heading,
    normalize_line, split_title_author, strip_publication_notes,
  )
  from .generic import position_sort_key


AWARD_NAME = 'South Australian Literary Awards'
OFFICIAL_URL = 'https://stories.slsa.sa.gov.au/south-australian-literary-awards/'
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/South_Australian_Literary_Awards'

HEADER_ALIASES = {
  'award': 'category',
  'category': 'category',
  'prize': 'category',
  'author': 'author',
  'authors': 'author',
  'writer': 'author',
  'writers': 'author',
  'title': 'title',
  'book': 'title',
  'work': 'title',
  'winner': 'title',
  'result': 'result',
  'status': 'result',
  'year': 'year',
}

NO_ENTRY_KEYS = {
  '',
  'joint winner',
  'joint winners',
  'joint winners:',
  'no award',
  'no winner',
  'not awarded',
  'not presented',
  'winner',
  'winners',
}


def _normalized_text(value):
  return unicodedata.normalize('NFKC', value or '')


def _category_key(value):
  value = normalize_heading(_normalized_text(value))
  return value.replace('non fiction', 'nonfiction')


class SouthAustralianLiteraryAwardsMixin(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def __init__(self, category, category_aliases=()):
    self.category = category
    self.category_aliases = tuple(category_aliases or (category,))
    self.category_keys = {_category_key(alias) for alias in self.category_aliases}

  def category_matches(self, value):
    return _category_key(value) in self.category_keys

  def clean_text(self, node):
    if node is None:
      return ''
    node = BeautifulSoup(str(node), 'html.parser')
    for removable in node.find_all(['script', 'style', 'sup']):
      removable.decompose()
    return normalize_line(_normalized_text(node.get_text(' ', strip=True)).replace('\xa0', ' '))

  def clean_title(self, value):
    value = normalize_line(_normalized_text(value))
    value = re.sub(r'\s*\[[^\[\]]*\]\s*$', '', value).strip()
    value = re.sub(r'\s+\([^)]*$', '', value).strip()
    match = re.match(r'^(.*)\s+\(([^()]*)\)\s*$', value)
    if match is not None:
      note = normalize_line(match.group(2))
      if not re.match(r'^(?:and|or|the|a|an)\b', note, re.I):
        value = match.group(1).strip()
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def clean_author(self, value):
    value = strip_publication_notes(normalize_line(_normalized_text(value)))
    value = re.sub(r'^\s*(?:by|author|writer)\s*:?\s*', '', value, flags=re.I)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True) if node is not None else None
    if link is None and getattr(node, 'name', None) == 'a' and node.get('href'):
      link = node
    return urljoin(base_url, link['href']) if link is not None else ''

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def is_no_entry_text(self, text):
    key = normalize_heading(text)
    return key in NO_ENTRY_KEYS or key.startswith('no winner ')

  def strip_entry_prefix(self, text):
    text = normalize_line(_normalized_text(text))
    text = re.sub(
      r'^\s*(?:winner|winners|joint\s+winners?|award\s+winner)\s*:?\s*',
      '',
      text,
      flags=re.I)
    return text.strip()

  def strip_leading_year(self, text):
    match = re.match(r'^\s*((?:19|20)\d{2})(?:\s*[/\u2013\u2014-]\s*(?:\d{2,4}))?\s*[:\u2013\u2014-]\s*(.+)$', text)
    if match is None:
      return None, text
    return int(match.group(1)), match.group(2).strip()

  def parse_title_author_line(self, text):
    text = self.strip_entry_prefix(text)
    if not text or self.is_no_entry_text(text):
      return '', ''
    by_match = re.match(r'^(.+?)\s+(?:by|written\s+by)\s+(.+)$', text, re.I)
    if by_match is not None:
      return self.clean_title(by_match.group(1)), self.clean_author(by_match.group(2))
    title, author = split_title_author(text)
    if title and author:
      return self.clean_title(title), self.clean_author(author)
    dash_match = re.match(r'^(.+?)\s+[\u2013\u2014-]\s+(.+)$', text)
    if dash_match is not None:
      return self.clean_title(dash_match.group(1)), self.clean_author(dash_match.group(2))
    return '', ''

  def split_joint_rows(self, text):
    text = self.strip_entry_prefix(text)
    if ';' not in text:
      return [text]
    return [part.strip() for part in text.split(';') if part.strip()]

  def row(self, year, title, author, source_url):
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': RESULT_WINNER,
      'source_url': source_url,
      'category': self.category,
      'award': self.AWARD_NAME,
    }

  def dedupe_rows(self, rows):
    deduped = []
    seen = set()
    for row in rows:
      title_key = normalize_heading(row.get('title', ''))
      author_key = normalize_heading(row.get('author', ''))
      if not title_key or not author_key:
        continue
      key = (row.get('award_year'), _category_key(row.get('category', '')), title_key, author_key)
      if key in seen:
        continue
      seen.add(key)
      deduped.append(row)
    return deduped

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      try:
        year = int(row['award_year'])
      except Exception:
        continue
      by_year.setdefault(year, []).append(row)

    entries = []
    for year in sorted(by_year):
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in by_year[year]
      ]
      entries.extend(assign_positions(
        award_rows, year, tied_winners_share_position=True))
    return entries


class SouthAustralianLiteraryAwardsOfficialParser(SouthAustralianLiteraryAwardsMixin):

  def parse(self, html, base_url=OFFICIAL_URL, name=AWARD_NAME, **_kwargs):
    rows = self.parse_rows(html, base_url)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    root = soup.find('main') or soup.find('article') or soup.body or soup
    rows = []
    current_category = None
    pending_year = None

    for node in root.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'tr']):
      if node.find_parent(['script', 'style', 'nav', 'header', 'footer']):
        continue
      text = self.clean_text(node)
      if not text:
        continue
      if node.name == 'tr':
        row = self.parse_table_row(node, current_category, base_url)
        if row is not None:
          rows.extend(row)
        continue
      if node.name in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}:
        if self.category_matches(text):
          current_category = self.category
          pending_year = None
        elif self.year_from_text(text) is None:
          current_category = None
          pending_year = None
        continue
      if current_category is None:
        continue
      year, entry_text = self.strip_leading_year(text)
      if year is None:
        bare_year = self.year_from_text(text)
        if bare_year is not None and normalize_heading(text) == str(bare_year):
          pending_year = bare_year
          continue
        year = pending_year
      if year is None or self.is_no_entry_text(entry_text):
        continue
      for part in self.split_joint_rows(entry_text):
        part_year, part_text = self.strip_leading_year(part)
        title, author = self.parse_title_author_line(part_text)
        if title and author:
          rows.append(self.row(
            part_year or year,
            title,
            author,
            self.first_link_url(node, base_url) or base_url))
    return rows

  def parse_table_row(self, tr, current_category, base_url):
    cells = tr.find_all(['td', 'th'], recursive=False)
    if len(cells) < 2:
      return None
    texts = [self.clean_text(cell) for cell in cells]
    if any(self.category_matches(text) for text in texts):
      return None
    if current_category is None:
      return None
    year = self.year_from_text(texts[0])
    if year is None:
      return None
    candidates = []
    if len(texts) >= 3:
      candidates.append(f'{texts[1]}, {texts[2]}')
    candidates.append(' '.join(texts[1:]))
    rows = []
    for candidate in candidates:
      if self.is_no_entry_text(candidate):
        continue
      title, author = self.parse_title_author_line(candidate)
      if title and author:
        rows.append(self.row(
          year,
          title,
          author,
          self.first_link_url(cells[1], base_url) or base_url))
        break
    return rows


class SouthAustralianLiteraryAwardsWikipediaParser(SouthAustralianLiteraryAwardsMixin):

  def parse(self, html, base_url=WIKIPEDIA_URL, name=AWARD_NAME, **_kwargs):
    rows = self.parse_rows(html, base_url)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for table in soup.find_all('table'):
      grid = self.table_grid(table)
      header_index, header_map = self.header_map(grid)
      if not {'year', 'title', 'author'}.issubset(set(header_map)):
        continue
      rows.extend(self.table_rows(grid[header_index + 1:], header_map, base_url))
    return rows

  def table_grid(self, table):
    grid = []
    rowspans = {}
    for tr in table.find_all('tr'):
      row = []
      column = 0
      for cell in tr.find_all(['th', 'td'], recursive=False):
        while column in rowspans:
          span_cell, remaining = rowspans[column]
          row.append(span_cell)
          if remaining <= 1:
            del rowspans[column]
          else:
            rowspans[column] = (span_cell, remaining - 1)
          column += 1
        colspan = self.span_value(cell, 'colspan')
        rowspan = self.span_value(cell, 'rowspan')
        for _index in range(colspan):
          row.append(cell)
          if rowspan > 1:
            rowspans[column] = (cell, rowspan - 1)
          column += 1
      while column in rowspans:
        span_cell, remaining = rowspans[column]
        row.append(span_cell)
        if remaining <= 1:
          del rowspans[column]
        else:
          rowspans[column] = (span_cell, remaining - 1)
        column += 1
      if row:
        grid.append(row)
    return grid

  def span_value(self, cell, attribute):
    try:
      return max(1, int(cell.get(attribute, 1)))
    except Exception:
      return 1

  def header_map(self, grid):
    for row_index, row in enumerate(grid):
      mapped = {}
      for index, cell in enumerate(row):
        key = HEADER_ALIASES.get(normalize_heading(self.clean_text(cell)))
        if key is not None and key not in mapped:
          mapped[key] = index
      if {'year', 'title', 'author'}.issubset(set(mapped)):
        return row_index, mapped
    return 0, {}

  def table_rows(self, grid, header_map, base_url):
    rows = []
    current_year = None
    current_category = ''
    for row in grid:
      year = self.year_from_text(self.cell_text(row, header_map, 'year')) or current_year
      if year is None:
        continue
      current_year = year
      category = self.cell_text(row, header_map, 'category') or current_category
      if category:
        current_category = category
      if not self.category_matches(category):
        continue
      result = self.result_from_text(self.cell_text(row, header_map, 'result'))
      if result is not None and result != RESULT_WINNER:
        continue
      title_cell = self.cell_for_key(row, header_map, 'title')
      title = self.clean_title(self.clean_text(title_cell))
      author = self.clean_author(self.cell_text(row, header_map, 'author'))
      if not title or not author or self.is_no_entry_text(title):
        continue
      rows.append(self.row(
        year,
        title,
        author,
        self.first_link_url(title_cell, base_url) or base_url))
    return rows

  def cell_for_key(self, row, header_map, key):
    index = header_map.get(key)
    if index is None or index < 0 or index >= len(row):
      return None
    return row[index]

  def cell_text(self, row, header_map, key):
    return self.clean_text(self.cell_for_key(row, header_map, key))

  def result_from_text(self, value):
    key = normalize_heading(value)
    if not key:
      return None
    if key.startswith('winner') or key in {'won'}:
      return RESULT_WINNER
    if key.startswith('shortlist') or key.startswith('finalist') or key.startswith('longlist'):
      return 'not-winner'
    return None


def parse_south_australian_literary_awards_official(
    html, category, category_aliases=(), url=OFFICIAL_URL, name=AWARD_NAME):
  return SouthAustralianLiteraryAwardsOfficialParser(
    category, category_aliases).parse(html, url, name)


def parse_south_australian_literary_awards_wikipedia(
    html, category, category_aliases=(), url=WIKIPEDIA_URL, name=AWARD_NAME):
  return SouthAustralianLiteraryAwardsWikipediaParser(
    category, category_aliases).parse(html, url, name)
