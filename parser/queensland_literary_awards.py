#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Queensland Literary Awards parsers.

Maintenance notes:
- State Library of Queensland's history page is the primary V1 source. It
  exposes year, category, and result headings followed by book rows.
- V1 keeps six largest published-book recipes only. Fellowships, manuscript
  awards, poetry, short-story, digital, and person-only categories stay out of
  scope.
"""

import re
import unicodedata
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


AWARD_NAME = 'Queensland Literary Awards'
OFFICIAL_URL = 'https://www.slq.qld.gov.au/queensland-literary-awards/past-winners'
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Queensland_Literary_Awards'

HEADER_ALIASES = {
  'category': 'category',
  'award': 'category',
  'author': 'author',
  'authors': 'author',
  'writer': 'author',
  'writers': 'author',
  'title': 'title',
  'book': 'title',
  'work': 'title',
  'result': 'result',
  'status': 'result',
  'year': 'year',
}

RESULT_ALIASES = {
  'winner': RESULT_WINNER,
  'winners': RESULT_WINNER,
  'finalist': RESULT_SHORTLISTED,
  'finalists': RESULT_SHORTLISTED,
  'shortlist': RESULT_SHORTLISTED,
  'shortlisted': RESULT_SHORTLISTED,
}

NOISE_KEYS = {
  '',
  'not awarded',
  'not applicable',
  'na',
  'n a',
}


def _normalized_text(value):
  return unicodedata.normalize('NFKC', value or '')


def _category_key(value):
  value = normalize_heading(_normalized_text(value))
  return value.replace('non fiction', 'nonfiction')


class QueenslandLiteraryAwardsMixin(AwardParserBase):

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
    value = self.strip_unbalanced_publication_note(value)
    value = self.strip_title_publication_note(value)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def clean_author(self, value):
    value = strip_publication_notes(normalize_line(_normalized_text(value)))
    value = re.sub(
      r'^\s*(?:by|written\s+by|illustrated\s+by|author|authors|writer)\s*:?\s*',
      '',
      value,
      flags=re.I)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def strip_unbalanced_publication_note(self, value):
    value = normalize_line(_normalized_text(value))
    return re.sub(r'\s+\([^)]*$', '', value).strip()

  def strip_title_publication_note(self, value):
    value = normalize_line(_normalized_text(value))
    value = re.sub(r'\s*\[[^\[\]]*\]\s*$', '', value).strip()
    match = re.match(r'^(.*)\s+\(([^()]*)\)\s*$', value)
    if match is None:
      return value
    note = normalize_line(match.group(2))
    if re.match(r'^(?:and|or|the|a|an)\b', note, re.I):
      return value
    return match.group(1).strip()

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True) if node is not None else None
    if link is None and getattr(node, 'name', None) == 'a' and node.get('href'):
      link = node
    return urljoin(base_url, link['href']) if link is not None else ''

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def parse_title_author_line(self, text):
    text = normalize_line(_normalized_text(text))
    text = re.sub(r'^\s*(?:winner|finalist|shortlisted)\s*:?\s*', '', text, flags=re.I)
    if re.match(r'^\s*(?:by|written\s+by|illustrated\s+by)\b', text, re.I):
      return '', ''
    by_match = re.match(r'^(.+?)\s+(?:by|written\s+by|illustrated\s+by)\s+(.+)$', text, re.I)
    if by_match is not None:
      return self.clean_title(by_match.group(1)), self.clean_author(by_match.group(2))
    dash_match = re.match(r'^(.+?)\s+[\u2013\u2014-]\s+(.+)$', text)
    if dash_match is not None:
      return self.clean_title(dash_match.group(1)), self.clean_author(dash_match.group(2))
    return '', ''

  def dedupe_rows(self, rows):
    deduped = []
    index_by_key = {}
    for row in rows:
      title_key = normalize_heading(row.get('title', ''))
      author_key = normalize_heading(row.get('author', ''))
      if not title_key or not author_key:
        continue
      key = (row.get('award_year'), _category_key(row.get('category', '')), title_key, author_key)
      existing_index = index_by_key.get(key)
      if existing_index is None:
        index_by_key[key] = len(deduped)
        deduped.append(row)
      elif (
          deduped[existing_index].get('result') != RESULT_WINNER
          and row.get('result') == RESULT_WINNER):
        deduped[existing_index] = row
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
      year_rows = sorted(
        by_year[year],
        key=lambda row: 0 if row.get('result') == RESULT_WINNER else 1)
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in year_rows
      ]
      entries.extend(assign_positions(
        award_rows, year, tied_winners_share_position=True))
    return entries


class QueenslandLiteraryAwardsOfficialParser(QueenslandLiteraryAwardsMixin):

  def parse(self, html, base_url=OFFICIAL_URL, name=AWARD_NAME, **_kwargs):
    rows = self.parse_rows(html, base_url)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    root = soup.find('main') or soup.body or soup
    rows = []
    current_year = None
    current_category = None
    current_result = None
    pending_title = None
    pending_url = ''

    for node in root.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'p', 'li']):
      if node.find_parent(['script', 'style', 'nav', 'header', 'footer']):
        continue
      text = self.clean_text(node)
      if not text:
        continue
      key = normalize_heading(text)
      if key in NOISE_KEYS:
        pending_title = None
        pending_url = ''
        continue
      if self.year_from_text(text) is not None and node.name in {'h1', 'h2', 'h3'}:
        current_year = self.year_from_text(text)
        current_category = None
        current_result = None
        pending_title = None
        pending_url = ''
        continue
      if self.category_matches(text):
        current_category = self.category
        current_result = None
        pending_title = None
        pending_url = ''
        continue
      if key in RESULT_ALIASES:
        current_result = RESULT_ALIASES[key]
        pending_title = None
        pending_url = ''
        continue
      if node.name in {'h2', 'h3'}:
        current_category = None
        current_result = None
        pending_title = None
        pending_url = ''
        continue
      if current_year is None or current_category is None or current_result is None:
        continue
      if self.is_non_entry_line(text):
        continue
      title, author = self.parse_title_author_line(text)
      if title and author:
        rows.append(self.row(
          current_year, title, author, current_result,
          self.first_link_url(node, base_url) or base_url))
        pending_title = None
        pending_url = ''
        continue
      if pending_title is None:
        pending_title = self.clean_title(text)
        pending_url = self.first_link_url(node, base_url) or base_url
        continue
      author = self.clean_author(text)
      if author:
        rows.append(self.row(
          current_year, pending_title, author, current_result,
          pending_url or self.first_link_url(node, base_url) or base_url))
      pending_title = None
      pending_url = ''
    return rows

  def row(self, year, title, author, result, source_url):
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': source_url,
      'category': self.category,
      'award': self.AWARD_NAME,
    }

  def is_non_entry_line(self, text):
    key = normalize_heading(text)
    if key in NOISE_KEYS or key in RESULT_ALIASES:
      return True
    if self.category_matches(text):
      return True
    if self.year_from_text(text) is not None and re.match(r'^\s*(?:19|20)\d{2}\b', text):
      return True
    return False


class QueenslandLiteraryAwardsWikipediaParser(QueenslandLiteraryAwardsMixin):

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
      header_map = self.header_map(table)
      if not {'category', 'title', 'author', 'result', 'year'}.issubset(set(header_map)):
        continue
      rows.extend(self.table_rows(table, header_map, base_url))
    return rows

  def header_map(self, table):
    for tr in table.find_all('tr'):
      cells = tr.find_all(['th', 'td'], recursive=False)
      mapped = {}
      for index, cell in enumerate(cells):
        key = HEADER_ALIASES.get(normalize_heading(self.clean_text(cell)))
        if key is not None and key not in mapped:
          mapped[key] = index
      if {'category', 'title', 'author', 'result', 'year'}.issubset(set(mapped)):
        return mapped
    return {}

  def table_rows(self, table, header_map, base_url):
    rows = []
    current_year = None
    current_result = None
    current_category = ''
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      if not cells or self.row_matches_header(cells, header_map):
        continue
      missing_year_cell = self.row_omits_cell(cells, header_map, 'year', current_year)
      year = self.year_for_row(cells, header_map, missing_year_cell, current_year)
      if year is None:
        continue
      current_year = year
      category_cell = self.cell_for_key(cells, header_map, 'category', missing_year_cell)
      category = self.clean_text(category_cell) or current_category
      if category:
        current_category = category
      if not self.category_matches(category):
        continue
      result_cell = self.cell_for_key(cells, header_map, 'result', missing_year_cell)
      result = self.result_from_cell(result_cell) or current_result
      if result is not None:
        current_result = result
      if result not in {RESULT_WINNER, RESULT_SHORTLISTED}:
        continue
      title_cell = self.cell_for_key(cells, header_map, 'title', missing_year_cell)
      author_cell = self.cell_for_key(cells, header_map, 'author', missing_year_cell)
      title = self.clean_title(self.clean_text(title_cell))
      author = self.clean_author(self.clean_text(author_cell))
      if not title or not author:
        continue
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': self.first_link_url(title_cell, base_url) or base_url,
        'category': self.category,
      })
    return rows

  def row_matches_header(self, cells, header_map):
    for key, index in header_map.items():
      if index >= len(cells):
        return False
      if HEADER_ALIASES.get(normalize_heading(self.clean_text(cells[index]))) != key:
        return False
    return True

  def row_omits_cell(self, cells, header_map, key, current_value):
    if current_value is None or header_map.get(key) != 0:
      return False
    if len(cells) > max(header_map.values()):
      return False
    return True

  def year_for_row(self, cells, header_map, missing_year_cell, current_year):
    if missing_year_cell:
      return current_year
    year_cell = self.cell_for_key(cells, header_map, 'year', False)
    return self.year_from_text(self.clean_text(year_cell)) if year_cell is not None else current_year

  def cell_for_key(self, cells, header_map, key, missing_year_cell):
    index = header_map.get(key)
    if index is None:
      return None
    if missing_year_cell and index > header_map['year']:
      index -= 1
    if index < 0 or index >= len(cells):
      return None
    return cells[index]

  def result_from_cell(self, cell):
    text = normalize_heading(self.clean_text(cell))
    if not text:
      return None
    if text.startswith('winner'):
      return RESULT_WINNER
    if text.startswith('finalist') or text.startswith('shortlist'):
      return RESULT_SHORTLISTED
    return None


def parse_queensland_literary_awards_official(
    html, category, category_aliases=(), url=OFFICIAL_URL, name=AWARD_NAME):
  return QueenslandLiteraryAwardsOfficialParser(
    category, category_aliases).parse(html, url, name)


def parse_queensland_literary_awards_wikipedia(
    html, category, category_aliases=(), url=WIKIPEDIA_URL, name=AWARD_NAME):
  return QueenslandLiteraryAwardsWikipediaParser(
    category, category_aliases).parse(html, url, name)
