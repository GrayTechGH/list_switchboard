#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Stella Prize parsers for the official archive and Wikipedia fallback.

Maintenance notes:
- V1 imports winners and shortlists only. The official archive and Wikipedia
  both expose longlists, but those rows are deliberately skipped.
- The official archive cards carry genre labels. They are not award categories,
  so parsed entries use one stable category shared with the fallback source.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, RESULT_LONGLISTED, RESULT_SHORTLISTED, RESULT_WINNER,
    assign_positions, normalize_heading, normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_LONGLISTED, RESULT_SHORTLISTED, RESULT_WINNER,
    assign_positions, normalize_heading, normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key


AWARD_NAME = 'Stella Prize'
CATEGORY = 'All genres'
OFFICIAL_URL = 'https://stella.org.au/past-prize-winners/'
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Stella_Prize'

HEADER_ALIASES = {
  'year': 'year',
  'author': 'author',
  'authors': 'author',
  'writer': 'author',
  'writers': 'author',
  'title': 'title',
  'book': 'title',
  'work': 'title',
  'result': 'result',
  'status': 'result',
  'stage': 'result',
  'ref': 'ref',
  'refs': 'ref',
}

RESULT_LABELS = {
  'winner': RESULT_WINNER,
  'winners': RESULT_WINNER,
  'shortlist': RESULT_SHORTLISTED,
  'shortlisted': RESULT_SHORTLISTED,
  'shortlisted books': RESULT_SHORTLISTED,
  'shortlisted works': RESULT_SHORTLISTED,
  'finalist': RESULT_SHORTLISTED,
  'finalists': RESULT_SHORTLISTED,
  'longlist': RESULT_LONGLISTED,
  'longlisted': RESULT_LONGLISTED,
  'longlisted books': RESULT_LONGLISTED,
  'longlisted works': RESULT_LONGLISTED,
}


class StellaParserMixin(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def clean_text(self, node):
    if node is None:
      return ''
    node = BeautifulSoup(str(node), 'html.parser')
    for removable in node.find_all(['script', 'style', 'sup']):
      removable.decompose()
    text = normalize_line(node.get_text(' ', strip=True).replace('\xa0', ' '))
    text = re.sub(r'\s*\[\s*\d+\s*\]\s*', ' ', text)
    return normalize_line(text)

  def clean_title(self, value):
    value = strip_publication_notes(normalize_line(value))
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def clean_author(self, value):
    value = strip_publication_notes(normalize_line(value))
    value = re.sub(r'^\s*(?:by|author|authors)\s*:\s*', '', value, flags=re.I)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True) if node is not None else None
    return urljoin(base_url, link['href']) if link is not None else ''

  def result_from_text(self, value):
    heading = normalize_heading(value)
    if not heading:
      return None
    if heading in RESULT_LABELS:
      return RESULT_LABELS[heading]
    for label, result in RESULT_LABELS.items():
      if heading.startswith(label + ' '):
        return result
    return None

  def included_result(self, result):
    return result in {RESULT_WINNER, RESULT_SHORTLISTED}

  def dedupe_rows(self, rows):
    deduped = []
    index_by_key = {}
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      existing_index = index_by_key.get(key)
      if existing_index is None:
        index_by_key[key] = len(deduped)
        deduped.append(row)
        continue
      if (
          deduped[existing_index].get('result') != RESULT_WINNER
          and row.get('result') == RESULT_WINNER):
        deduped[existing_index] = row
    return deduped

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      year_rows = sorted(
        by_year[year],
        key=lambda row: 0 if row.get('result') == RESULT_WINNER else 1)
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, CATEGORY)
        for row in year_rows
      ]
      entries.extend(assign_positions(
        award_rows, int(year), tied_winners_share_position=True))
    return entries


class StellaOfficialParser(StellaParserMixin):

  def parse(self, html, base_url=OFFICIAL_URL, name=AWARD_NAME):
    rows = self.dedupe_rows(self.parse_rows(html, base_url))
    self.validate_expected_counts(html, rows, name)
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    for removable in soup.find_all(['script', 'style', 'sup']):
      removable.decompose()
    rows = []
    seen_nodes = set()
    for node in self.candidate_cards(soup):
      node_id = id(node)
      if node_id in seen_nodes:
        continue
      seen_nodes.add(node_id)
      row = self.row_from_card(node, base_url)
      if row is None:
        continue
      rows.append(row)
    return rows

  def candidate_cards(self, soup):
    candidates = []
    for node in soup.find_all(['article', 'li', 'div', 'section']):
      text = self.clean_text(node)
      if self.stage_from_card_text(text) is None:
        continue
      candidates.append(node)
    return candidates

  def row_from_card(self, card, base_url):
    stage = self.stage_from_card_text(self.clean_text(card))
    if stage is None:
      return None
    year, result = stage
    if not self.included_result(result):
      return None
    title_node = self.title_node(card)
    author_node = self.author_node(card, title_node)
    title = self.clean_title(self.clean_text(title_node))
    author = self.clean_author(self.clean_text(author_node))
    if not title or not author:
      title, author = self.title_author_from_lines(card, year, result)
    if not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': self.first_link_url(title_node or card, base_url) or base_url,
      'category': CATEGORY,
    }

  def stage_from_card_text(self, text):
    heading = normalize_line(text)
    match = re.search(
      r'\bthe\s+((?:19|20)\d{2})\s+stella\s+prize\s+'
      r'(winner|shortlist|longlist)\b',
      heading,
      re.I)
    if match is None:
      match = re.search(
        r'\b((?:19|20)\d{2})\s+stella\s+prize\s+'
        r'(winner|shortlist|longlist)\b',
        heading,
        re.I)
    if match is None:
      return None
    result = self.result_from_text(match.group(2))
    if result is None:
      return None
    return int(match.group(1)), result

  def title_node(self, card):
    for node in card.find_all(True):
      classes = ' '.join(node.get('class', []) or ())
      class_key = normalize_heading(classes)
      if any(key in class_key for key in ('book title', 'work title', 'title')):
        text = self.clean_text(node)
        if self.looks_like_entry_title(text):
          return node
    for tag in ('h2', 'h3', 'h4', 'h5'):
      for node in card.find_all(tag):
        text = self.clean_text(node)
        if self.looks_like_entry_title(text):
          return node
    for node in card.find_all('a', href=True):
      text = self.clean_text(node)
      if self.looks_like_entry_title(text):
        return node
    return None

  def author_node(self, card, title_node):
    for node in card.find_all(True):
      classes = ' '.join(node.get('class', []) or ())
      class_key = normalize_heading(classes)
      if 'author' in class_key or 'writer' in class_key:
        text = self.clean_author(self.clean_text(node))
        if self.looks_like_author(text):
          return node
    if title_node is not None:
      for sibling in title_node.find_next_siblings():
        text = self.clean_author(self.clean_text(sibling))
        if self.looks_like_author(text):
          return sibling
    return None

  def title_author_from_lines(self, card, year, result):
    lines = [
      line for line in self.text_lines(card)
      if not self.is_stage_line(line, year, result) and not self.is_genre_line(line)
    ]
    if not lines:
      return '', ''
    for line in lines:
      parsed = self.parse_title_by_author(line)
      if parsed is not None:
        return parsed
    if len(lines) >= 2:
      return self.clean_title(lines[0]), self.clean_author(lines[1])
    return '', ''

  def text_lines(self, node):
    lines = [
      self.clean_text(item)
      for item in node.find_all(['h2', 'h3', 'h4', 'h5', 'p', 'li', 'span'])
    ]
    deduped = []
    seen = set()
    for line in lines:
      key = normalize_heading(line)
      if not line or key in seen:
        continue
      seen.add(key)
      deduped.append(line)
    return deduped

  def parse_title_by_author(self, text):
    match = re.match(r'^(.+?)\s+by\s+(.+)$', normalize_line(text), re.I)
    if match is None:
      return None
    return self.clean_title(match.group(1)), self.clean_author(match.group(2))

  def looks_like_entry_title(self, text):
    heading = normalize_heading(text)
    if not heading:
      return False
    if 'stella prize' in heading:
      return False
    if heading in {'winner', 'shortlist', 'longlist'}:
      return False
    return not self.is_genre_line(text)

  def looks_like_author(self, text):
    heading = normalize_heading(text)
    if not heading or self.is_genre_line(text):
      return False
    if 'stella prize' in heading:
      return False
    if heading in {'winner', 'shortlist', 'longlist'}:
      return False
    return len(text) <= 120

  def is_stage_line(self, line, year, result):
    stage = self.stage_from_card_text(line)
    if stage is not None and stage[0] == year and stage[1] == result:
      return True
    return self.result_from_text(line) == result

  def is_genre_line(self, line):
    return normalize_heading(line) in {
      'fiction',
      'non fiction',
      'nonfiction',
      'poetry',
      'graphic novel',
      'memoir',
      'essays',
      'young adult',
      'short stories',
      'history',
      'biography',
    }

  def validate_expected_counts(self, html, rows, name):
    expected = self.expected_counts(html)
    if not expected:
      return
    actual = {
      RESULT_WINNER: sum(1 for row in rows if row.get('result') == RESULT_WINNER),
      RESULT_SHORTLISTED: sum(
        1 for row in rows if row.get('result') == RESULT_SHORTLISTED),
    }
    missing = []
    for result, count in expected.items():
      if actual.get(result, 0) < count:
        missing.append(f'{result}: expected {count}, parsed {actual.get(result, 0)}')
    if missing:
      raise ValueError(
        f'{name} official archive appears incomplete; ' + '; '.join(missing))

  def expected_counts(self, html):
    text = self.clean_text(BeautifulSoup(html, 'html.parser'))
    counts = {}
    patterns = (
      r'\b(\d+)\s+(?:stella\s+prize\s+)?(winners?|shortlisted|shortlist)\b',
      r'\b(winners?|shortlisted|shortlist)\s*\(?\s*(\d+)\s*\)?',
    )
    for pattern in patterns:
      for match in re.finditer(pattern, text, re.I):
        first, second = match.group(1), match.group(2)
        if first.isdigit():
          count, label = int(first), second
        else:
          label, count = first, int(second)
        if count >= 100:
          continue
        result = self.result_from_text(label)
        if result in {RESULT_WINNER, RESULT_SHORTLISTED}:
          counts[result] = max(counts.get(result, 0), count)
    return counts


class StellaWikipediaParser(StellaParserMixin):

  def parse(self, html, base_url=WIKIPEDIA_URL, name=AWARD_NAME):
    rows = self.dedupe_rows(self.parse_rows(html, base_url))
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for table in soup.find_all('table'):
      header_map = self.header_map(table)
      if not {'year', 'author', 'title', 'result'}.issubset(set(header_map)):
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
      if {'year', 'author', 'title', 'result'}.issubset(set(mapped)):
        return mapped
    return {}

  def table_rows(self, table, header_map, base_url):
    rows = []
    current_year = None
    current_result = None
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      if not cells or self.row_matches_header(cells, header_map):
        continue
      missing_year_cell = self.row_omits_year(cells, header_map, current_year)
      year = self.year_for_row(cells, header_map, missing_year_cell, current_year)
      if year is None:
        continue
      current_year = year

      result_cell = self.cell_for_key(cells, header_map, 'result', missing_year_cell)
      result = self.result_from_text(self.clean_text(result_cell)) or current_result
      if result is not None:
        current_result = result
      if result == RESULT_LONGLISTED:
        continue
      if not self.included_result(result):
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
        'category': CATEGORY,
      })
    return rows

  def row_matches_header(self, cells, header_map):
    for key, index in header_map.items():
      if index >= len(cells):
        return False
      if HEADER_ALIASES.get(normalize_heading(self.clean_text(cells[index]))) != key:
        return False
    return True

  def row_omits_year(self, cells, header_map, current_year):
    if current_year is None or header_map.get('year') != 0:
      return False
    if len(cells) > max(header_map.values()):
      return False
    return self.year_from_text(self.clean_text(cells[0])) is None

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


def parse_stella_official(html, base_url=OFFICIAL_URL, name=AWARD_NAME):
  return StellaOfficialParser().parse(html, base_url, name)


def parse_stella_wikipedia(html, base_url=WIKIPEDIA_URL, name=AWARD_NAME):
  return StellaWikipediaParser().parse(html, base_url, name)
