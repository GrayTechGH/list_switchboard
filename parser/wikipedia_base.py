#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Reusable Wikipedia award table parser base.

Maintenance notes:
- Wikipedia award pages vary by article. This base accepts only table shapes
  with explicit year, title/work, author, and result/stage columns.
- Award-specific parsers or fetchers should document every production use in
  `_docs/PARSER_FETCHER_GUIDE.md` before relying on this base.
- Current production users:
  `CrimeWritersOfCanadaWikipediaParser`, `DavittWikipediaParser`,
  `DilysWikipediaParser`, `GumshoeWikipediaParser`,
  `NedKellyWikipediaParser`, and `TheakstonWikipediaParser`.
- Shared parser-family bases should keep this user list in their module
  maintenance notes so later refactors can quickly see the real dependency
  surface before changing shared behavior.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, assign_positions, normalize_heading, normalize_line,
    strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
except ImportError:
  from .award_base import (
    AwardParserBase, assign_positions, normalize_heading, normalize_line,
    strip_publication_notes,
  )
  from .generic import position_sort_key


DEFAULT_ALLOWED_RESULTS = ('winner', 'shortlisted', 'nominee')

HEADER_ALIASES = {
  'award year': 'year',
  'year': 'year',
  'title': 'title',
  'work': 'title',
  'book': 'title',
  'novel': 'title',
  'author': 'author',
  'authors': 'author',
  'writer': 'author',
  'writers': 'author',
  'recipient': 'author',
  'recipients': 'author',
  'result': 'result',
  'status': 'result',
  'stage': 'result',
  'level': 'result',
  'category': 'category',
  'award category': 'category',
}

RESULT_ALIASES = {
  'winner': 'winner',
  'won': 'winner',
  'win': 'winner',
  'shortlist': 'shortlisted',
  'shortlisted': 'shortlisted',
  'short list': 'shortlisted',
  'finalist': 'shortlisted',
  'finalists': 'shortlisted',
  'nominee': 'nominee',
  'nominees': 'nominee',
  'nominated': 'nominee',
}


class WikipediaAwardTableParserBase(AwardParserBase):
  """
  Parse conservative Wikipedia award tables into award import entries.

  Invariants:
  - Tables without year, title/work, and author columns are ignored.
  - Blank result cells are accepted only when the previous row in the same
    table/year established a shortlist/finalist result.
  """

  AWARD_NAME = ''

  def parse(
      self, html, base_url, name, category, category_aliases=(),
      allowed_results=None):
    rows = self.parse_rows(
      html,
      base_url,
      category,
      category_aliases,
      allowed_results or DEFAULT_ALLOWED_RESULTS)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(
      self, html, base_url, category, category_aliases, allowed_results):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for table in soup.find_all('table'):
      header_map = self.header_map(table)
      if not self.has_required_columns(header_map):
        continue
      rows.extend(self.table_rows(
        table, header_map, base_url, category, category_aliases,
        set(allowed_results)))
    return rows

  def header_map(self, table):
    for tr in table.find_all('tr'):
      headers = tr.find_all(['th', 'td'], recursive=False)
      mapped = {}
      for index, header in enumerate(headers):
        key = HEADER_ALIASES.get(
          normalize_heading(self.clean_cell_text(header)))
        if key is not None and key not in mapped:
          mapped[key] = index
      if self.has_required_columns(mapped):
        return mapped
    return {}

  def has_required_columns(self, header_map):
    return all(key in header_map for key in ('year', 'title', 'author'))

  def tables_under_category_headings(
      self, soup, category, category_aliases, match='exact'):
    """
    Yield (heading, table) pairs for headings that match the target category.

    Maintenance note:
    This intentionally preserves the current loose `heading.find_next('table')`
    lookup used by subclasses. It does not enforce section boundaries.
    """
    accepted = {
      normalize_heading(value) for value in (category, *category_aliases) if value
    }
    for heading in soup.find_all(['h2', 'h3', 'h4']):
      text = normalize_heading(heading.get_text(' ', strip=True))
      hit = (
        text in accepted if match == 'exact'
        else any(alias and alias in text for alias in accepted)
      )
      if not hit:
        continue
      table = heading.find_next('table')
      if table is not None:
        yield heading, table

  def table_rows(
      self, table, header_map, base_url, category, category_aliases,
      allowed_results):
    return self._table_rows_standard(
      table, header_map, base_url, category, category_aliases, allowed_results)

  def _table_rows_standard(
      self, table, header_map, base_url, category, category_aliases,
      allowed_results):
    rows = []
    current_year = None
    current_result_by_year = {}
    header_row_seen = False
    header_indexes = set(header_map.values())

    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      if not cells:
        continue
      if not header_row_seen and self.row_matches_header(cells, header_map):
        header_row_seen = True
        continue
      if all(index < len(cells) and cells[index].name == 'th'
             for index in header_indexes):
        continue

      missing_year_cell = self.row_omits_year(cells, header_map, current_year)
      year_text = (
        self.clean_cell_text(cells[header_map['year']])
        if not missing_year_cell and header_map['year'] < len(cells) else '')
      year = self.year_from_text(year_text) or current_year
      if year is None:
        continue
      current_year = year

      title_cell = self.cell_for_key(cells, header_map, 'title', missing_year_cell)
      author_cell = self.cell_for_key(cells, header_map, 'author', missing_year_cell)
      result_cell = self.cell_for_key(cells, header_map, 'result', missing_year_cell)
      category_cell = self.cell_for_key(cells, header_map, 'category', missing_year_cell)
      if title_cell is None or author_cell is None:
        continue

      row_category = (
        self.clean_cell_text(category_cell)
        if category_cell is not None else category)
      if not self.category_matches(row_category, category, category_aliases):
        continue

      result = self.result_from_cell(result_cell)
      if result is None:
        result = (
          'shortlisted'
          if current_result_by_year.get(year) == 'shortlisted' else None)
      if result not in allowed_results:
        continue
      current_result_by_year[year] = result

      title = self.clean_title(self.clean_cell_text(title_cell))
      author = self.clean_author(self.clean_cell_text(author_cell))
      if not title or not author:
        continue
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': self.first_link_url(title_cell, base_url) or base_url,
        'category': category,
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
    if text in RESULT_ALIASES:
      return RESULT_ALIASES[text]
    for alias, result in RESULT_ALIASES.items():
      if text.startswith(alias + ' '):
        return result
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

  def category_matches(self, row_category, category, category_aliases):
    aliases = {category, *category_aliases}
    normalized = {normalize_heading(alias) for alias in aliases}
    return normalize_heading(row_category) in normalized

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
