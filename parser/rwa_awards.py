#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
RWA award parsers for Wikipedia-backed historical award pages.

Maintenance notes:
- RITA/Golden Medallion winners are parsed from Wikipedia's consolidated
  winner table. Vivian winners are parsed separately from the winner section on
  the same article.
- The RITA and Vivian sources are winner-only; do not infer finalists from
  external RWA finalist announcements without a separate source review.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, RESULT_WINNER, assign_positions, normalize_heading,
    normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_WINNER, assign_positions, normalize_heading,
    normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key


RITA_AWARD_NAME = 'RWA RITA Awards'
VIVIAN_AWARD_NAME = 'RWA Vivian Awards'
RITA_URL = 'https://en.wikipedia.org/wiki/RITA_Award'

HEADER_ALIASES = {
  'year': 'year',
  'category': 'category',
  'award category': 'category',
  'sorting category': 'sorting_category',
  'title': 'title',
  'work': 'title',
  'book': 'title',
  'author': 'author',
  'authors': 'author',
}


class RWARITAAwardsParser(AwardParserBase):

  AWARD_NAME = RITA_AWARD_NAME

  def parse(self, html, base_url=RITA_URL, name=RITA_AWARD_NAME):
    rows = self.dedupe_rows(self.parse_rows(html, base_url))
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    table = self.rita_winners_table(soup)
    if table is None:
      return []
    header_map = self.header_map(table)
    if not self.has_required_columns(header_map):
      return []
    return self.table_rows(table, header_map, base_url)

  def rita_winners_table(self, soup):
    for heading in soup.find_all(['h2', 'h3']):
      heading_text = normalize_heading(heading.get_text(' ', strip=True))
      if heading_text != 'rita award winners' and not heading_text.startswith(
          'rita award winners '):
        continue
      for sibling in heading.find_all_next(['h2', 'h3', 'table']):
        if sibling.name in {'h2', 'h3'}:
          break
        header_map = self.header_map(sibling)
        if self.has_required_columns(header_map):
          return sibling
    for table in soup.find_all('table'):
      header_map = self.header_map(table)
      if self.has_required_columns(header_map):
        return table
    return None

  def header_map(self, table):
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      mapped = {}
      for index, cell in enumerate(cells):
        key = HEADER_ALIASES.get(normalize_heading(self.clean_cell_text(cell)))
        if key is not None and key not in mapped:
          mapped[key] = index
      if self.has_required_columns(mapped):
        return mapped
    return {}

  def has_required_columns(self, header_map):
    return all(key in header_map for key in ('year', 'category', 'title', 'author'))

  def table_rows(self, table, header_map, base_url):
    rows = []
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      if not cells or self.is_header_row(cells):
        continue
      year_cell = self.cell_for_key(cells, header_map, 'year')
      category_cell = self.cell_for_key(cells, header_map, 'category')
      title_cell = self.cell_for_key(cells, header_map, 'title')
      author_cell = self.cell_for_key(cells, header_map, 'author')
      year = self.year_from_text(self.clean_cell_text(year_cell))
      if year is None or category_cell is None or title_cell is None or author_cell is None:
        continue
      category = self.clean_category(self.clean_cell_text(category_cell))
      title = self.clean_title(self.clean_cell_text(title_cell))
      author = self.clean_author(self.clean_cell_text(author_cell))
      if not category or not title or not author:
        continue
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': RESULT_WINNER,
        'source_url': self.first_link_url(title_cell, base_url) or base_url,
        'category': category,
      })
    return rows

  def is_header_row(self, cells):
    headings = {normalize_heading(self.clean_cell_text(cell)) for cell in cells}
    return {'year', 'category', 'title', 'author'}.issubset(headings)

  def cell_for_key(self, cells, header_map, key):
    index = header_map.get(key)
    if index is None or index >= len(cells):
      return None
    return cells[index]

  def clean_cell_text(self, cell):
    if cell is None:
      return ''
    cell = BeautifulSoup(str(cell), 'html.parser')
    for node in cell.find_all(['sup', 'style', 'script']):
      node.decompose()
    text = normalize_line(cell.get_text(' ', strip=True).replace('\xa0', ' '))
    text = re.sub(r'\s*\[\s*\d+\s*\]\s*', ' ', text)
    return normalize_line(text)

  def clean_category(self, value):
    return normalize_line(value).strip(' "\'\u2018\u2019\u201c\u201d,')

  def clean_title(self, value):
    value = strip_publication_notes(normalize_line(value))
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

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
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in by_year[year]
      ]
      entries.extend(assign_positions(award_rows, int(year)))
    return entries


class RWAVivianAwardsParser(RWARITAAwardsParser):

  AWARD_NAME = VIVIAN_AWARD_NAME

  def parse(self, html, base_url=RITA_URL, name=VIVIAN_AWARD_NAME):
    notes = [
      'Vivian Award imports are winner-only; no complete, stable shortlist '
      'source is available in V1.'
    ]
    rows = self.dedupe_rows(self.parse_rows(html, base_url, notes))
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def parse_rows(self, html, base_url, notes=None):
    soup = BeautifulSoup(html, 'html.parser')
    section = self.vivian_section_nodes(soup)
    if not section:
      return []
    rows = []
    current_category = ''
    for node in section:
      if node.name in {'h3', 'h4'}:
        current_category = self.clean_category(self.heading_text(node))
        continue
      if node.name == 'table':
        rows.extend(self.vivian_table_rows(node, base_url, notes))
        continue
      if node.name in {'p', 'li'}:
        row = self.vivian_text_row(
          node,
          base_url,
          fallback_category=current_category,
          notes=notes)
        if row is not None:
          rows.append(row)
    return rows

  def vivian_section_nodes(self, soup):
    heading = None
    for candidate in soup.find_all(['h2', 'h3']):
      heading_text = normalize_heading(self.heading_text(candidate))
      if heading_text == 'vivian award winners' or heading_text.startswith(
          'vivian award winners '):
        heading = candidate
        break
    if heading is None:
      return []
    nodes = []
    for sibling in heading.find_all_next(['h2', 'h3', 'h4', 'p', 'li', 'table']):
      if sibling.name == 'h2' and sibling is not heading:
        break
      nodes.append(sibling)
    return nodes

  def heading_text(self, node):
    node = BeautifulSoup(str(node), 'html.parser')
    for edit_span in node.find_all(class_=lambda value: value and 'mw-editsection' in value):
      edit_span.decompose()
    return self.clean_cell_text(node)

  def vivian_table_rows(self, table, base_url, notes):
    header_map = self.header_map(table)
    if self.has_required_columns(header_map):
      return self.table_rows(table, header_map, base_url)
    rows = []
    current_category = ''
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      if not cells:
        continue
      cell_texts = [self.clean_cell_text(cell) for cell in cells]
      if len(cells) == 1 and self.year_from_text(cell_texts[0]) is None:
        current_category = self.clean_category(cell_texts[0])
        continue
      row = self.vivian_text_row(
        tr,
        base_url,
        fallback_category=current_category,
        notes=notes)
      if row is not None:
        rows.append(row)
    return rows

  def vivian_text_row(self, node, base_url, fallback_category='', notes=None):
    text = self.clean_cell_text(node)
    text = re.sub(r'^\s*winner\s*:?\s*', '', text, flags=re.I)
    match = re.match(r'^(?:(?P<category>.+?)\s*:\s*)?(?P<year>20\d{2})\s*:\s*(?P<work>.+)$', text)
    if match is None:
      match = re.match(
        r'^(?P<year>20\d{2})\s*[-–—]\s*(?:(?P<category>.+?)\s*:\s*)?(?P<work>.+)$',
        text)
    if match is None:
      return None
    year = int(match.group('year'))
    category = self.clean_category(match.group('category') or fallback_category)
    title, author = self.title_author_from_text(match.group('work'))
    if not category or not title or not author:
      return None
    if notes is not None and re.search(r'\brescind(?:ed)?\b', text, re.I):
      note = (
        f'Vivian {year} {category} winner is imported as listed, but the '
        'source text marks the award as rescinded.'
      )
      if note not in notes:
        notes.append(note)
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': RESULT_WINNER,
      'source_url': self.first_link_url(node, base_url) or base_url,
      'category': category,
    }

  def title_author_from_text(self, value):
    value = strip_publication_notes(normalize_line(value))
    value = re.sub(r'\s*\b(?:award\s+)?rescinded\b.*$', '', value, flags=re.I).strip()
    match = re.match(r'^(?P<title>.+?)\s+by\s+(?P<author>.+)$', value, re.I)
    if match is None:
      return '', ''
    return (
      self.clean_title(match.group('title')),
      self.clean_author(match.group('author')))


def parse_rwa_rita_awards(html, base_url=RITA_URL, name=RITA_AWARD_NAME):
  return RWARITAAwardsParser().parse(html, base_url, name)


def parse_rwa_vivian_awards(html, base_url=RITA_URL, name=VIVIAN_AWARD_NAME):
  return RWAVivianAwardsParser().parse(html, base_url, name)
