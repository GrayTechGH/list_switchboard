#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Miles Franklin Literary Award parser for Wikipedia winner and shortlist tables.

Maintenance notes:
- Wikipedia splits winners and shortlists into separate table families. Winners
  appear from 1957 onward; shortlist tables begin in 1987.
- V1 imports winners and shortlists only. The separate longlist sections are
  intentionally ignored.
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


AWARD_NAME = 'Miles Franklin Literary Award'
CATEGORY = 'Novel'
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Miles_Franklin_Award'


HEADER_ALIASES = {
  'year': 'year',
  'author': 'author',
  'authors': 'author',
  'title': 'title',
  'work': 'title',
  'book': 'title',
  'novel': 'title',
  'result': 'result',
  'status': 'result',
  'publisher': 'publisher',
  'ref': 'ref',
}


class MilesFranklinWikipediaParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def parse(self, html, base_url=WIKIPEDIA_URL, name=AWARD_NAME):
    soup = BeautifulSoup(html, 'html.parser')
    rows = self.parse_winner_rows(soup, base_url)
    rows.extend(self.parse_shortlist_rows(soup, base_url))
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_winner_rows(self, soup, base_url):
    rows = []
    for table in soup.find_all('table'):
      header_map = self.header_map(table)
      if not self.is_winner_table(header_map):
        continue
      rows.extend(self.winner_table_rows(table, header_map, base_url))
    return rows

  def parse_shortlist_rows(self, soup, base_url):
    rows = []
    for table in soup.find_all('table'):
      header_map = self.header_map(table)
      if not self.is_shortlist_table(header_map):
        continue
      rows.extend(self.shortlist_table_rows(table, header_map, base_url))
    return rows

  def header_map(self, table):
    for tr in table.find_all('tr'):
      cells = tr.find_all(['th', 'td'], recursive=False)
      mapped = {}
      for index, cell in enumerate(cells):
        key = HEADER_ALIASES.get(normalize_heading(self.clean_cell_text(cell)))
        if key is not None and key not in mapped:
          mapped[key] = index
      if {'year', 'author', 'title'}.issubset(set(mapped)):
        return mapped
    return {}

  def is_winner_table(self, header_map):
    return {'year', 'author', 'title'}.issubset(set(header_map)) and 'result' not in header_map

  def is_shortlist_table(self, header_map):
    return {'year', 'author', 'title', 'result'}.issubset(set(header_map))

  def winner_table_rows(self, table, header_map, base_url):
    rows = []
    current_year = None
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      if not cells or self.row_matches_header(cells, header_map):
        continue

      missing_year_cell = self.row_omits_year(cells, header_map, current_year)
      year = self.year_for_row(cells, header_map, missing_year_cell, current_year)
      if year is None:
        continue
      current_year = year

      title_cell = self.cell_for_key(cells, header_map, 'title', missing_year_cell)
      author_cell = self.cell_for_key(cells, header_map, 'author', missing_year_cell)
      title = self.clean_title(self.clean_cell_text(title_cell)) if title_cell is not None else ''
      author = self.clean_author(self.clean_cell_text(author_cell)) if author_cell is not None else ''
      if not title or not author:
        continue

      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': RESULT_WINNER,
        'source_url': self.first_link_url(title_cell, base_url) or base_url,
        'category': CATEGORY,
      })
    return rows

  def shortlist_table_rows(self, table, header_map, base_url):
    rows = []
    current_year = None
    current_result_by_year = {}
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      if not cells or self.row_matches_header(cells, header_map):
        continue

      missing_year_cell = self.row_omits_year(cells, header_map, current_year)
      year = self.year_for_row(cells, header_map, missing_year_cell, current_year)
      if year is None:
        continue
      current_year = year

      title_cell = self.cell_for_key(cells, header_map, 'title', missing_year_cell)
      author_cell = self.cell_for_key(cells, header_map, 'author', missing_year_cell)
      result_cell = self.cell_for_key(cells, header_map, 'result', missing_year_cell)
      result = self.result_from_cell(result_cell)
      if result is None:
        result = current_result_by_year.get(year)
      if result not in {RESULT_WINNER, RESULT_SHORTLISTED, RESULT_LONGLISTED}:
        continue
      current_result_by_year[year] = result
      if result == RESULT_LONGLISTED:
        continue

      title = self.clean_title(self.clean_cell_text(title_cell)) if title_cell is not None else ''
      author = self.clean_author(self.clean_cell_text(author_cell)) if author_cell is not None else ''
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
      if HEADER_ALIASES.get(normalize_heading(self.clean_cell_text(cells[index]))) != key:
        return False
    return True

  def row_omits_year(self, cells, header_map, current_year):
    if current_year is None or header_map.get('year') != 0:
      return False
    if len(cells) > max(header_map.values()):
      return False
    first_text = self.clean_cell_text(cells[0]) if cells else ''
    return self.year_from_text(first_text) is None

  def year_for_row(self, cells, header_map, missing_year_cell, current_year):
    if missing_year_cell:
      return current_year
    year_cell = self.cell_for_key(cells, header_map, 'year', False)
    return self.year_from_text(self.clean_cell_text(year_cell)) if year_cell is not None else current_year

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
    if cell is None:
      return None
    text = normalize_heading(self.clean_cell_text(cell))
    if not text:
      return None
    if text.startswith('winner'):
      return RESULT_WINNER
    if text.startswith('shortlist') or text.startswith('finalist'):
      return RESULT_SHORTLISTED
    if text.startswith('longlist'):
      return RESULT_LONGLISTED
    return None

  def clean_cell_text(self, cell):
    if cell is None:
      return ''
    cell = BeautifulSoup(str(cell), 'html.parser')
    for node in cell.find_all(['sup', 'style', 'script']):
      node.decompose()
    text = normalize_line(cell.get_text(' ', strip=True))
    text = re.sub(r'\s*\[\s*\d+\s*\]\s*', ' ', text)
    return normalize_line(text)

  def clean_title(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def first_link_url(self, cell, base_url):
    link = cell.find('a', href=True) if cell is not None else None
    return urljoin(base_url, link['href']) if link is not None else ''

  def year_from_text(self, value):
    match = re.search(r'(19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def dedupe_rows(self, rows):
    winners = {
      (
        row['award_year'],
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      for row in rows
      if row.get('result') == RESULT_WINNER
    }
    deduped = []
    seen = set()
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      if row.get('result') == RESULT_SHORTLISTED and key in winners:
        continue
      if key in seen:
        continue
      seen.add(key)
      deduped.append(row)
    return deduped

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in by_year[year]
      ]
      entries.extend(assign_positions(
        award_rows, int(year), tied_winners_share_position=True))
    return entries


def parse_miles_franklin_wikipedia(
    html, base_url=WIKIPEDIA_URL, name=AWARD_NAME):
  return MilesFranklinWikipediaParser().parse(html, base_url, name)
