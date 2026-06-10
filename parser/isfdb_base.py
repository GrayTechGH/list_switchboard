#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Reusable ISFDB award category parser base.

Maintenance notes:
- ISFDB award category pages expose award records as tables rather than the
  overview/year-page structure used by SFADB.
- Subclasses or fetchers should configure AWARD_NAME and call parse() with the
  recipe category plus aliases. The parser accepts pages whose rows either
  include a Category column or are already scoped to one category.
- ISFDB can include person, publisher, artist, and no-title award records beside
  book-like records. Fetchers should choose book-focused categories; subclasses
  may override include_row() for source-specific pruning.
"""

import re
from urllib.parse import urljoin

from lxml import html as lxml_html

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, assign_positions, normalize_heading, normalize_line,
    strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    AwardParserBase, assign_positions, normalize_heading, normalize_line,
    strip_publication_notes,
  )
  from .generic import position_sort_key


RESULT_BY_LEVEL = {
  'win': 'winner',
  'winner': 'winner',
  'won': 'winner',
  '1': 'winner',
  'nomination': 'nominee',
  'nominee': 'nominee',
  'nominated': 'nominee',
  'finalist': 'nominee',
  'finalists': 'nominee',
  'shortlist': 'shortlisted',
  'shortlisted': 'shortlisted',
  'longlist': 'longlisted',
  'longlisted': 'longlisted',
}


class ISFDBAwardParserBase(AwardParserBase):
  """
  Parse ISFDB award rows into the shared award import entry schema.

  Type constraints:
  - AWARD_NAME: str, used when rows do not expose an award-name column.
  - parse() receives an ISFDB award category/all-records HTML page and returns
    the normal parsed-result dict used by import review and matching.
  - include_row() receives an lxml row element.

  Invariants:
  - Category filtering is applied only when a row exposes a category cell; pages
    scoped to one configured category are accepted without a category column.
  - Winner/nominee positions are assigned with the shared annual award contract.
  """

  AWARD_NAME = ''

  HEADER_ALIASES = {
    'award level': 'level',
    'level': 'level',
    'place': 'level',
    'rank': 'level',
    'title': 'title',
    'work': 'title',
    'author': 'author',
    'authors': 'author',
    'author s name': 'author',
    'year': 'year',
    'award year': 'year',
    'category': 'category',
    'award category': 'category',
    'award name': 'award',
    'award': 'award',
  }

  def parse(self, html, base_url, name, category, category_aliases=()):
    rows = self.parse_rows(html, base_url, category, category_aliases)
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url, category, category_aliases):
    root = lxml_html.fromstring(html or '<html></html>')
    rows = []
    title_nodes = root.xpath('//title')
    award_year = self.year_from_text(
      self.node_text(title_nodes[0]) if title_nodes else '')
    for table in root.xpath('//table'):
      header_map = self.header_map(table)
      if self.has_required_columns(header_map):
        for tr in table.xpath('.//tr'):
          parsed = self.parse_table_row(
            tr, header_map, base_url, category, category_aliases)
          if parsed is not None:
            rows.append(parsed)
        continue
      rows.extend(self.parse_grouped_category_rows(table, base_url, category))
      if award_year is not None:
        rows.extend(self.parse_award_year_rows(
          table, base_url, award_year, category, category_aliases))
    return rows

  def parse_grouped_category_rows(self, table, base_url, category):
    """
    Parse ISFDB category pages grouped by year.

    Some category pages do not expose column headers. Their stable shape is a
    year heading row followed by records with award level, title, and author.
    """
    rows = []
    current_year = None
    for tr in table.xpath('.//tr'):
      cells = self.direct_cells(tr, include_headers=True)
      if not cells:
        continue
      if len(cells) == 1:
        year = self.year_from_text(self.node_text(cells[0]))
        if year is not None:
          current_year = year
        continue
      if current_year is None or len(cells) < 3:
        continue
      level_cell, title_cell, author_cell = cells[:3]
      result = self.result_from_level(self.node_text(level_cell))
      title = self.clean_title(self.title_from_cell(title_cell))
      author = self.clean_author(self.author_from_cell(author_cell))
      if not title or not author or result is None:
        continue
      row = {
        'award_year': str(current_year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': self.first_record_url(title_cell, base_url) or base_url,
        'category': category,
        'award': self.AWARD_NAME,
      }
      if self.include_row(row, tr):
        rows.append(row)
    return rows

  def parse_award_year_rows(
      self, table, base_url, award_year, category, category_aliases):
    """
    Parse ISFDB award-year pages grouped by category.

    Award-year `ay.cgi` pages expose one year per page. Their stable shape is a
    blank separator row, a category heading row, optional separator rows such as
    `--- Finalists ---`, then records with award level, title, and author.
    """
    rows = []
    current_category = None
    for tr in table.xpath('./tr|./tbody/tr'):
      cells = self.direct_cells(tr)
      if not cells:
        continue
      if len(cells) == 1:
        heading_text = self.node_text(cells[0])
        if cells[0].xpath('.//a[contains(@href, "/award_category.cgi?")]'):
          current_category = heading_text
        continue
      if current_category is None or len(cells) < 3:
        continue
      level_cell, title_cell, author_cell = cells[:3]
      result = self.result_from_level(self.node_text(level_cell))
      if result is None:
        continue
      if not self.category_matches(current_category, category, category_aliases):
        continue
      title = self.clean_title(self.title_from_cell(title_cell))
      author = self.clean_author(self.author_from_cell(author_cell))
      if not title or not author:
        continue
      row = {
        'award_year': str(award_year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': self.first_record_url(title_cell, base_url) or base_url,
        'category': category,
        'award': self.AWARD_NAME,
      }
      if self.include_row(row, tr):
        rows.append(row)
    return rows

  def header_map(self, table):
    first_rows = table.xpath('.//tr')
    if not first_rows:
      return {}
    headers = self.direct_cells(first_rows[0], include_headers=True)
    if not headers:
      return {}
    mapped = {}
    for index, header in enumerate(headers):
      key = self.HEADER_ALIASES.get(
        normalize_heading(self.node_text(header)))
      if key is not None and key not in mapped:
        mapped[key] = index
    return mapped

  def has_required_columns(self, header_map):
    return all(key in header_map for key in ('title', 'author', 'year', 'level'))

  def parse_table_row(self, tr, header_map, base_url, category, category_aliases):
    cells = tr.xpath('./th|./td')
    if not cells or len(cells) <= max(header_map.values()):
      return None
    title_cell = cells[header_map['title']]
    author_cell = cells[header_map['author']]
    year = self.year_from_text(self.cell_text(cells, header_map.get('year')))
    title = self.clean_title(self.title_from_cell(title_cell))
    author = self.clean_author(self.author_from_cell(author_cell))
    level = self.cell_text(cells, header_map.get('level'))
    result = self.result_from_level(level)
    row_category = (
      self.cell_text(cells, header_map.get('category'))
      if 'category' in header_map else category
    )
    if not year or not title or not author or result is None:
      return None
    if not self.category_matches(row_category, category, category_aliases):
      return None
    row = {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': self.first_record_url(title_cell, base_url) or base_url,
      'category': category,
      'award': self.cell_text(cells, header_map.get('award')) or self.AWARD_NAME,
    }
    return row if self.include_row(row, tr) else None

  def include_row(self, _row, _tr):
    return True

  def cell_text(self, cells, index):
    if index is None or index >= len(cells):
      return ''
    return self.node_text(cells[index])

  def title_from_cell(self, cell):
    links = cell.xpath('.//a[contains(@href, "/title.cgi?")]')
    if not links:
      links = cell.xpath('.//a')
    return self.node_text(links[0]) if links else self.node_text(cell)

  def author_from_cell(self, cell):
    return self.node_text(cell)

  def first_record_url(self, cell, base_url):
    hrefs = cell.xpath('(.//a[@href])[1]/@href')
    return urljoin(base_url, hrefs[0]) if hrefs else ''

  def direct_cells(self, row, include_headers=False):
    selector = './td|./th' if include_headers else './td'
    return row.xpath(selector)

  def node_text(self, node):
    return normalize_line(' '.join(
      text.strip() for text in node.xpath('.//text()') if text.strip()))

  def year_from_text(self, value):
    match = re.search(r'(19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def result_from_level(self, value):
    value = normalize_line(value)
    heading = normalize_heading(value)
    if heading == 'no award':
      return None
    if heading.startswith('win'):
      return 'winner'
    if heading.startswith('nomination'):
      return 'nominee'
    if heading in RESULT_BY_LEVEL:
      return RESULT_BY_LEVEL[heading]
    if re.match(r'^\d+$', value or ''):
      return 'nominee'
    return None

  def category_matches(self, row_category, category, category_aliases):
    aliases = {category, *category_aliases}
    normalized = {normalize_heading(alias) for alias in aliases}
    return normalize_heading(row_category) in normalized

  def clean_title(self, value):
    value = re.sub(r'\s+Award Record #\s*\d+\s*$', '', value or '', flags=re.I)
    value = re.sub(r'\s+\(no ISFDB title record\)\s*$', '', value, flags=re.I)
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    return strip_publication_notes(normalize_line(value)).strip()

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      award_rows = [
        self.build_award_entry(
          row, row['source_url'], year, row['category'], award=row.get('award'))
        for row in by_year[year]
      ]
      entries.extend(assign_positions(award_rows, int(year)))
    return entries
