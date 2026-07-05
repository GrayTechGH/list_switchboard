#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Costa/Whitbread award parsers for Wikipedia category tables.

Maintenance notes:
- The original Costa site is gone; V1 deliberately uses Wikipedia category
  pages as the live parsed source and keeps archived/news sources as
  validation-only references.
- Category pages use row-spanned years and result cells. Some older Biography
  rows omit the visible shortlist result after the winner row, so blank
  same-year rows after a winner are treated as shortlisted entries.
"""

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


AWARD_PREFIX = 'Costa/Whitbread Book Award'
OVERALL_AWARD_NAME = 'Costa/Whitbread Book of the Year'
MAIN_URL = 'https://en.wikipedia.org/wiki/Costa_Book_Awards'
NOVEL_URL = 'https://en.wikipedia.org/wiki/Costa_Book_Award_for_Novel'
FIRST_NOVEL_URL = 'https://en.wikipedia.org/wiki/Costa_Book_Award_for_First_Novel'
BIOGRAPHY_URL = 'https://en.wikipedia.org/wiki/Costa_Book_Award_for_Biography'
CHILDRENS_BOOK_URL = (
  'https://en.wikipedia.org/wiki/Costa_Book_Award_for_Children%27s_Book')


HEADER_ALIASES = {
  'year': 'year',
  'author': 'author',
  'authors': 'author',
  'title': 'title',
  'book': 'title',
  'result': 'result',
  'status': 'result',
  'ref': 'ref',
  'refs': 'ref',
  'references': 'ref',
  'subject': 'subject',
}

CATEGORY_ALIASES = {
  'novel': 'Novel',
  'first novel': 'First Novel',
  'childrens book': "Children's Book",
  'children s book': "Children's Book",
  'children book': "Children's Book",
  'children': "Children's Book",
  'poetry': 'Poetry',
  'biography': 'Biography',
  'short story': 'Short Story',
}


class CostaWhitbreadCategoryParser(AwardParserBase):

  def __init__(self, award_name, category):
    super().__init__()
    self.AWARD_NAME = award_name
    self.category = category

  def parse(self, html, base_url, name=None):
    rows = self.dedupe_rows(self.parse_rows(html, base_url))
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name or self.AWARD_NAME,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for table in soup.find_all('table'):
      header_map = self.header_map(table)
      if not self.has_category_columns(header_map):
        continue
      rows.extend(self.table_rows(table, header_map, base_url))
    return rows

  def header_map(self, table):
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      mapped = {}
      for index, cell in enumerate(cells):
        header = HEADER_ALIASES.get(normalize_heading(self.clean_cell_text(cell)))
        if header is not None and header not in mapped:
          mapped[header] = index
      if self.has_category_columns(mapped):
        if 'result' not in mapped:
          result_index = mapped.get('title', -1) + 1
          if result_index < len(cells):
            mapped['result'] = result_index
        return mapped
    return {}

  def has_category_columns(self, header_map):
    return all(key in header_map for key in ('year', 'author', 'title'))

  def table_rows(self, table, header_map, base_url):
    rows = []
    current_year = None
    current_result_by_year = {}
    winner_seen_by_year = {}
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      if not cells or self.is_header_row(cells):
        continue

      missing_year_cell = self.row_omits_year(cells, header_map, current_year)
      year_cell = self.cell_for_key(cells, header_map, 'year', missing_year_cell)
      year = (
        self.year_from_text(self.clean_cell_text(year_cell))
        if year_cell is not None and not missing_year_cell else current_year)
      if year is None:
        continue
      current_year = year

      author_cell = self.cell_for_key(cells, header_map, 'author', missing_year_cell)
      title_cell = self.cell_for_key(cells, header_map, 'title', missing_year_cell)
      result_cell = self.cell_for_key(cells, header_map, 'result', missing_year_cell)
      if author_cell is None or title_cell is None:
        continue

      author_text = self.clean_cell_text(author_cell)
      title_text = self.clean_cell_text(title_cell)
      if self.is_no_award_row(author_text, title_text):
        continue

      result = self.result_from_cell(result_cell)
      if result is None:
        inherited_result = current_result_by_year.get(year)
        if inherited_result == RESULT_SHORTLISTED:
          result = inherited_result
      if result is None and winner_seen_by_year.get(year):
        result = RESULT_SHORTLISTED
      if result not in {RESULT_WINNER, RESULT_SHORTLISTED}:
        continue

      title = self.clean_title(title_text)
      author = self.clean_author(author_text)
      if not title or not author:
        continue

      current_result_by_year[year] = result
      if result == RESULT_WINNER:
        winner_seen_by_year[year] = True
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': self.first_link_url(title_cell, base_url) or base_url,
        'category': self.category,
      })
    return rows

  def is_header_row(self, cells):
    headings = {normalize_heading(self.clean_cell_text(cell)) for cell in cells}
    return {'year', 'author', 'title'}.issubset(headings)

  def row_omits_year(self, cells, header_map, current_year):
    if current_year is None or header_map.get('year') != 0:
      return False
    if len(cells) > max(header_map.values()):
      return False
    first_text = self.clean_cell_text(cells[0]) if cells else ''
    return self.year_from_text(first_text) is None

  def cell_for_key(self, cells, header_map, key, missing_year_cell):
    index = header_map.get(key)
    if index is None:
      return None
    if missing_year_cell and index > header_map['year']:
      index -= 1
    return cells[index] if 0 <= index < len(cells) else None

  def result_from_cell(self, cell):
    if cell is None:
      return None
    text = normalize_heading(self.clean_cell_text(cell))
    if not text:
      return None
    if text.startswith('winner') or text.startswith('won'):
      return RESULT_WINNER
    if text.startswith('shortlist') or text.startswith('finalist'):
      return RESULT_SHORTLISTED
    return None

  def is_no_award_row(self, author_text, title_text):
    text = normalize_heading(f'{author_text} {title_text}')
    return not title_text or 'no award presented' in text

  def clean_cell_text(self, cell):
    if cell is None:
      return ''
    cell = BeautifulSoup(str(cell), 'html.parser')
    for node in cell.find_all(['sup', 'style', 'script', 'img']):
      node.decompose()
    for br in cell.find_all('br'):
      br.replace_with('\n')
    text = normalize_line(cell.get_text(' ', strip=True).replace('\xa0', ' '))
    text = re.sub(r'\s*\[\s*\d+\s*\]\s*', ' ', text)
    return normalize_line(text)

  def clean_title(self, value):
    value = strip_publication_notes(normalize_line(value))
    value = re.sub(r'\{\{\s*blue\s+ribbon\s*\}\}', '', value, flags=re.I)
    value = re.sub(r'\bblue\s+ribbon\b', '', value, flags=re.I)
    return normalize_line(value).strip(' "\'\u2018\u2019\u201c\u201d,')

  def clean_author(self, value):
    value = strip_publication_notes(normalize_line(value))
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def first_link_url(self, cell, base_url):
    link = cell.find('a', href=True) if cell is not None else None
    return urljoin(base_url, link['href']) if link is not None else ''

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def dedupe_rows(self, rows):
    deduped = []
    seen = set()
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['category']),
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
      year_rows = sorted(
        by_year[year],
        key=lambda row: 0 if row.get('result') == RESULT_WINNER else 1)
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in year_rows
      ]
      entries.extend(assign_positions(
        award_rows, int(year), tied_winners_share_position=True))
    return entries


class CostaWhitbreadBookOfTheYearParser(CostaWhitbreadCategoryParser):

  def __init__(self):
    super().__init__(OVERALL_AWARD_NAME, 'Book of the Year')

  def parse_rows(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for table in soup.find_all('table'):
      header_map = self.overall_header_map(table)
      if not header_map:
        continue
      rows.extend(self.overall_table_rows(table, header_map, base_url))
    return rows

  def overall_header_map(self, table):
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      mapped = {}
      for index, cell in enumerate(cells):
        key = normalize_heading(self.clean_cell_text(cell))
        if key == 'year':
          mapped['year'] = index
        category = CATEGORY_ALIASES.get(key)
        if category is not None:
          mapped[category] = index
      if 'year' in mapped and any(key in mapped for key in CATEGORY_ALIASES.values()):
        return mapped
    return {}

  def overall_table_rows(self, table, header_map, base_url):
    rows = []
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      if not cells:
        continue
      year_cell = self.cell_for_key(cells, header_map, 'year', False)
      year = self.year_from_text(self.clean_cell_text(year_cell))
      if year is None:
        continue
      for category, index in header_map.items():
        if category == 'year' or index >= len(cells):
          continue
        cell = cells[index]
        if not self.is_overall_winner_cell(cell):
          continue
        row = self.overall_row(cell, base_url, year, category)
        if row is not None:
          rows.append(row)
          break
    return rows

  def is_overall_winner_cell(self, cell):
    markup = str(cell).casefold()
    if 'blue ribbon' in markup or 'blueribbon_icon' in markup:
      return True
    return cell.find(['b', 'strong']) is not None

  def overall_row(self, cell, base_url, year, category):
    title_node = cell.find('i')
    title = self.clean_title(self.clean_cell_text(title_node))
    full_text = self.clean_title(self.clean_cell_text(cell))
    if title:
      author = self.clean_author(full_text.split(title, 1)[0].strip(' ,;\n'))
      source_url = self.first_link_url(title_node, base_url) or base_url
    else:
      lines = [normalize_line(line) for line in full_text.splitlines() if normalize_line(line)]
      if len(lines) < 2:
        return None
      author = self.clean_author(lines[0])
      title = self.clean_title(lines[1])
      source_url = base_url
    if not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': RESULT_WINNER,
      'source_url': source_url,
      'category': category,
    }


def parse_costa_whitbread_category(html, base_url, name, category):
  return CostaWhitbreadCategoryParser(name, category).parse(html, base_url, name)


def parse_costa_whitbread_book_of_the_year(
    html, base_url=MAIN_URL, name=OVERALL_AWARD_NAME):
  return CostaWhitbreadBookOfTheYearParser().parse(html, base_url, name)
