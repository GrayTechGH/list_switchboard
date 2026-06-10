#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
National Book Award official archive and Wikipedia fallback parsers.

Maintenance notes:
- Official National Book Foundation archive pages expose one category per
  `?cat=` URL. V1 imports the winner and finalists sections only; longlists
  are intentionally ignored until a stage-depth recipe is planned.
- The Wikipedia fallback is a replacement source, not a merge layer. It is
  deliberately table-bound so category history prose does not become entries.
"""

import re
from urllib.parse import urljoin

from lxml import html as lxml_html

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, RESULT_NOMINEE, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_NOMINEE, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key


AWARD_NAME = 'National Book Award'
PLACEHOLDER_TITLES = {
  'finalists not announced',
  'winner not announced',
  'winners not announced',
}


class NationalBookAwardParser(AwardParserBase):
  """
  Parse official National Book Foundation annual category pages.

  Invariants:
  - Winner rows come from `.winner-book`; finalist rows come from
    `.finalists-wrapper`.
  - Longlist rows are ignored even when present on recent archive pages.
  """

  AWARD_NAME = AWARD_NAME

  def parse(self, html, base_url, name, category, category_aliases=()):
    rows = self.parse_rows(html, base_url, category)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url, category):
    root = self.html_root(html)
    year = self.year_from_url(base_url) or self.year_from_text(self.node_text(root))
    if year is None:
      return []
    rows = []
    rows.extend(self.rows_from_nodes(
      root.xpath(
        '//div[contains(concat(" ", normalize-space(@class), " "), " winner-book ")]'
        '//*[contains(concat(" ", normalize-space(@class), " "), " winner-book-item ")]'),
      base_url,
      year,
      category,
      RESULT_WINNER))
    rows.extend(self.rows_from_nodes(
      root.xpath(
        '//div[contains(concat(" ", normalize-space(@class), " "), " finalists-wrapper ")]'
        '//figure[contains(concat(" ", normalize-space(@class), " "), " winner-list ")]'),
      base_url,
      year,
      category,
      RESULT_NOMINEE))
    return rows

  def rows_from_nodes(self, nodes, base_url, year, category, result):
    rows = []
    for node in nodes:
      title, author, source_url = self.work_from_node(node, base_url)
      if not title or not author or self.is_placeholder_title(title):
        continue
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': source_url or base_url,
        'category': category,
      })
    return rows

  def work_from_node(self, node, base_url):
    title_node = self.first_title_node(node)
    if title_node is None:
      return '', '', ''
    title = self.clean_title(self.node_text(title_node))
    author = self.clean_author(self.author_text(node))
    return title, author, self.node_href(title_node, base_url)

  def first_title_node(self, node):
    nodes = node.xpath(
      '(.//*[self::h1 or self::h2 or self::h3]//a[@href]'
      '|.//figcaption//a[@href]'
      '|.//a[@href][not(ancestor::*[contains(concat(" ", normalize-space(@class), " "), " author ")])])[1]')
    return nodes[0] if nodes else None

  def author_text(self, node):
    candidates = node.xpath(
      './/*[contains(concat(" ", normalize-space(@class), " "), " book-data ")]//h2'
      '|.//p[contains(concat(" ", normalize-space(@class), " "), " author ")]'
      '|.//*[contains(concat(" ", normalize-space(@class), " "), " author ")]')
    for candidate in candidates:
      text = self.clean_author(self.node_text(candidate))
      if text:
        return text
    return ''

  def clean_title(self, value):
    return normalize_line(value).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    text = normalize_line(value)
    text = re.sub(r'^\s*by\s+', '', text, flags=re.I)
    return strip_publication_notes(text).strip(' "\u201c\u201d,')

  def is_placeholder_title(self, title):
    return normalize_heading(title) in PLACEHOLDER_TITLES

  def html_root(self, html):
    return lxml_html.fromstring(html or '<html></html>')

  def node_text(self, node):
    return normalize_line(' '.join(
      text.strip()
      for text in node.xpath('.//text()[not(ancestor::script or ancestor::style)]')
      if text.strip()))

  def node_href(self, node, base_url):
    href = node.get('href')
    return urljoin(base_url, href) if href else ''

  def year_from_url(self, url):
    match = re.search(r'national-book-awards-(19|20)(\d{2})', url or '')
    return int(match.group(0)[-4:]) if match is not None else None

  def year_from_text(self, value):
    match = re.search(r'(19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def dedupe_rows(self, rows):
    deduped = []
    seen = set()
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['category']),
        row['result'],
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
        award_rows,
        int(year),
        tied_winners_share_position=True))
    return entries


class NationalBookAwardWikipediaParser(AwardParserBase):
  """
  Parse category-specific National Book Award Wikipedia recipient tables.
  """

  AWARD_NAME = AWARD_NAME
  HEADER_ALIASES = {
    'year': 'year',
    'award year': 'year',
    'author': 'author',
    'authors': 'author',
    'writer': 'author',
    'work': 'title',
    'book': 'title',
    'title': 'title',
    'result': 'result',
    'status': 'result',
    'outcome': 'result',
  }
  RESULT_ALIASES = {
    'winner': RESULT_WINNER,
    'won': RESULT_WINNER,
    'finalist': RESULT_NOMINEE,
    'finalists': RESULT_NOMINEE,
    'nominee': RESULT_NOMINEE,
    'nominees': RESULT_NOMINEE,
    'shortlisted': RESULT_NOMINEE,
  }

  def parse(self, html, base_url, name, category, category_aliases=()):
    rows = self.parse_rows(html, base_url, category)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url, category):
    root = self.html_root(html)
    rows = []
    for table in root.xpath('//table[contains(concat(" ", normalize-space(@class), " "), " wikitable ")]|//table'):
      if not self.accept_table(table, category):
        continue
      header_map = self.header_map(table)
      if self.has_required_columns(header_map):
        rows.extend(self.rows_from_table(table, header_map, base_url, category))
    return rows

  def accept_table(self, table, category):
    context = normalize_heading(' '.join(
      self.node_text(node)
      for node in table.xpath('./caption|preceding::h2[1]|preceding::h3[1]|preceding::h4[1]')))
    if normalize_heading(category) == 'nonfiction':
      rejected = (
        'arts and letters', 'history and biography', 'philosophy and religion',
        'the sciences', 'contemporary affairs',
      )
      if any(value in context for value in rejected):
        return False
    return (
      'recipient' in context
      or 'winner' in context
      or 'finalist' in context
      or not context)

  def rows_from_table(self, table, header_map, base_url, category):
    rows = []
    current_year = None
    row_count_by_year = {}
    for tr in table.xpath('.//tr'):
      cells = tr.xpath('./td|./th')
      if not cells or self.row_matches_header(cells, header_map):
        continue
      missing_year = self.row_omits_year(cells, header_map, current_year)
      year_cell = self.cell_for_key(cells, header_map, 'year', False)
      year = None if missing_year else self.year_from_text(self.clean_cell_text(year_cell))
      if year is None:
        year = current_year
      if year is None:
        continue
      current_year = year

      title_cell = self.cell_for_key(cells, header_map, 'title', missing_year)
      author_cell = self.cell_for_key(cells, header_map, 'author', missing_year)
      if title_cell is None or author_cell is None:
        continue
      title = self.clean_title(self.clean_cell_text(title_cell))
      author = self.clean_author(self.clean_cell_text(author_cell))
      if not title or not author or self.is_placeholder_title(title):
        continue

      result = self.result_from_cell(self.cell_for_key(cells, header_map, 'result', missing_year))
      if result is None:
        row_count = row_count_by_year.get(year, 0)
        result = RESULT_WINNER if row_count == 0 else RESULT_NOMINEE
      row_count_by_year[year] = row_count_by_year.get(year, 0) + 1

      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': self.first_link_url(title_cell, base_url) or base_url,
        'category': category,
      })
    return rows

  def header_map(self, table):
    for tr in table.xpath('.//tr'):
      mapped = {}
      for index, cell in enumerate(tr.xpath('./th|./td')):
        key = self.HEADER_ALIASES.get(normalize_heading(self.clean_cell_text(cell)))
        if key is not None and key not in mapped:
          mapped[key] = index
      if self.has_required_columns(mapped):
        return mapped
    return {}

  def has_required_columns(self, header_map):
    return all(key in header_map for key in ('year', 'title', 'author'))

  def row_matches_header(self, cells, header_map):
    for key, index in header_map.items():
      if index >= len(cells):
        return False
      if self.HEADER_ALIASES.get(normalize_heading(self.clean_cell_text(cells[index]))) != key:
        return False
    return True

  def row_omits_year(self, cells, header_map, current_year):
    if current_year is None or header_map.get('year') != 0:
      return False
    first_text = self.clean_cell_text(cells[0]) if cells else ''
    return self.year_from_text(first_text) is None and len(cells) <= max(header_map.values())

  def cell_for_key(self, cells, header_map, key, missing_year):
    index = header_map.get(key)
    if index is None:
      return None
    if missing_year and index > header_map.get('year', -1):
      index -= 1
    if index < 0 or index >= len(cells):
      return None
    return cells[index]

  def result_from_cell(self, cell):
    text = normalize_heading(self.clean_cell_text(cell))
    if not text:
      return None
    if text in self.RESULT_ALIASES:
      return self.RESULT_ALIASES[text]
    for alias, result in self.RESULT_ALIASES.items():
      if text.startswith(alias + ' '):
        return result
    return None

  def clean_cell_text(self, cell):
    if cell is None:
      return ''
    text = normalize_line(' '.join(
      text.strip()
      for text in cell.xpath(
        './/text()[not(ancestor::sup or ancestor::style or ancestor::script)]')
      if text.strip()))
    text = re.sub(r'\s*\[\s*[a-z0-9]+\s*\]\s*', ' ', text, flags=re.I)
    return normalize_line(text)

  def clean_title(self, value):
    return normalize_line(value).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def is_placeholder_title(self, title):
    return normalize_heading(title) in PLACEHOLDER_TITLES

  def html_root(self, html):
    return lxml_html.fromstring(html or '<html></html>')

  def first_link_url(self, cell, base_url):
    hrefs = cell.xpath('(.//a[@href])[1]/@href')
    return urljoin(base_url, hrefs[0]) if hrefs else ''

  def node_text(self, node):
    return normalize_line(' '.join(
      text.strip() for text in node.xpath('.//text()') if text.strip()))

  def year_from_text(self, value):
    match = re.search(r'(19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def dedupe_rows(self, rows):
    deduped = []
    seen = set()
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['category']),
        row['result'],
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
        award_rows,
        int(year),
        tied_winners_share_position=True))
    return entries
