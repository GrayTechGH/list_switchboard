#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Giller Prize parser for the Wikipedia nominees and winners tables.

Maintenance notes:
- The Wikipedia tables use row-spanned year, jury, and result cells. The parser
  tracks the current award year and result stage across shortened rows.
- V1 deliberately imports winners and shortlists only. Longlist rows are parsed
  as a boundary stage but skipped from the returned entries.
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


AWARD_NAME = 'Giller Prize'
CATEGORY = 'Fiction'
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Giller_Prize'


class GillerWikipediaParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

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
      if not self.is_giller_results_table(table):
        continue
      rows.extend(self.table_rows(table, base_url))
    return rows

  def is_giller_results_table(self, table):
    for tr in table.find_all('tr'):
      headers = [
        normalize_heading(self.clean_cell_text(cell))
        for cell in tr.find_all(['th', 'td'], recursive=False)
      ]
      if {'year', 'jury', 'author', 'book', 'result'}.issubset(set(headers)):
        return True
    return False

  def table_rows(self, table, base_url):
    rows = []
    current_year = None
    current_result_by_year = {}
    for tr in table.find_all('tr'):
      parsed = self.parse_table_row(
        tr, base_url, current_year, current_result_by_year)
      if parsed is None:
        continue
      current_year, result, row = parsed
      current_result_by_year[current_year] = result
      if result == RESULT_LONGLISTED:
        continue
      rows.append(row)
    return rows

  def parse_table_row(self, tr, base_url, current_year, current_result_by_year):
    cells = tr.find_all(['td', 'th'], recursive=False)
    if not cells or self.is_header_row(cells):
      return None

    first_text = self.clean_cell_text(cells[0])
    year = self.year_from_text(first_text)
    if year is not None:
      current_year = year
      author_cell = self.cell_at(cells, 2)
      title_cell = self.cell_at(cells, 3)
      result_cell = self.cell_at(cells, 4)
    elif current_year is not None:
      author_cell = self.cell_at(cells, 0)
      title_cell = self.cell_at(cells, 1)
      result_cell = self.first_result_cell(cells[2:])
    else:
      return None

    if author_cell is None or title_cell is None:
      return None

    result = self.result_from_cell(result_cell)
    if result is None:
      result = current_result_by_year.get(current_year)
    if result not in {RESULT_WINNER, RESULT_SHORTLISTED, RESULT_LONGLISTED}:
      return None

    title = self.clean_title(self.clean_cell_text(title_cell))
    author = self.clean_author(self.clean_cell_text(author_cell))
    if not title or not author:
      return None

    return current_year, result, {
      'award_year': str(current_year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': self.first_link_url(title_cell, base_url) or base_url,
      'category': CATEGORY,
    }

  def is_header_row(self, cells):
    headings = {normalize_heading(self.clean_cell_text(cell)) for cell in cells}
    return {'year', 'author', 'book', 'result'}.issubset(headings)

  def cell_at(self, cells, index):
    return cells[index] if index < len(cells) else None

  def first_result_cell(self, cells):
    for cell in cells:
      if self.result_from_cell(cell) is not None:
        return cell
    return None

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
    link = cell.find('a', href=True)
    return urljoin(base_url, link['href']) if link is not None else ''

  def year_from_text(self, value):
    match = re.search(r'(19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def dedupe_rows(self, rows):
    deduped = []
    seen = set()
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
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


def parse_giller_wikipedia(html, base_url=WIKIPEDIA_URL, name=AWARD_NAME):
  return GillerWikipediaParser().parse(html, base_url, name)
