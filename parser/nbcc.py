#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
National Book Critics Circle official archive and Wikipedia fallback parsers.

Maintenance notes:
- Official NBCC year pages have two useful server-rendered shapes: older
  heading/list blocks such as `General Nonfiction Winner`, and newer
  `ul.award-year-list` sections with result classes on each list item.
- V1 imports winners and finalists only. Official longlist rows are ignored
  even when the newer archive pages expose them.
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


AWARD_NAME = 'National Book Critics Circle Award'
DEFAULT_CATEGORY = 'Nonfiction'
RESULT_CLASS_ALIASES = {
  'winner': RESULT_WINNER,
  'finalist': RESULT_NOMINEE,
}
RESULT_TEXT_ALIASES = {
  'winner': RESULT_WINNER,
  'winners': RESULT_WINNER,
  'finalist': RESULT_NOMINEE,
  'finalists': RESULT_NOMINEE,
  'shortlist': RESULT_NOMINEE,
  'shortlisted': RESULT_NOMINEE,
}
HEADER_ALIASES = {
  'year': 'year',
  'award year': 'year',
  'author': 'author',
  'authors': 'author',
  'writer': 'author',
  'book': 'title',
  'title': 'title',
  'work': 'title',
  'result': 'result',
  'status': 'result',
  'outcome': 'result',
}


class NBCCAwardParser(AwardParserBase):
  """
  Parse official NBCC `past-awards/YYYY/` pages.

  Invariants:
  - Category allowlists are required by the fetcher; special/person awards and
    other book categories must not broaden a configured recipe.
  - `Longlist` rows are ignored in V1.
  """

  AWARD_NAME = AWARD_NAME

  def parse(self, html, base_url, name, category=DEFAULT_CATEGORY, category_aliases=()):
    rows = self.parse_rows(html, base_url, category, category_aliases)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url, category, category_aliases):
    root = self.html_root(html)
    year = self.year_from_url(base_url) or self.year_from_text(self.node_text(root))
    if year is None:
      return []
    aliases = self.accepted_categories(category, category_aliases)
    rows = []
    rows.extend(self.parse_modern_rows(root, base_url, year, category, aliases))
    rows.extend(self.parse_legacy_rows(root, base_url, year, category, aliases))
    return rows

  def parse_modern_rows(self, root, base_url, year, category, aliases):
    rows = []
    for section in root.xpath('//ul[contains(concat(" ", normalize-space(@class), " "), " award-year-list ")]'):
      heading_nodes = section.xpath('./h3[1]')
      if not heading_nodes:
        continue
      if normalize_heading(self.node_text(heading_nodes[0])) not in aliases:
        continue
      for item in section.xpath('./li'):
        result = self.result_from_class(item.get('class') or '')
        if result is None:
          continue
        row = self.row_from_item(item, base_url, year, category, result)
        if row is not None:
          rows.append(row)
    return rows

  def parse_legacy_rows(self, root, base_url, year, category, aliases):
    rows = []
    for heading in root.xpath('//h2|//h3|//h4'):
      parsed = self.category_result_from_heading(self.node_text(heading), aliases)
      if parsed is None:
        continue
      result = parsed
      for list_node in heading.xpath('following-sibling::*[self::ul][1]'):
        for item in list_node.xpath('./li'):
          row = self.row_from_item(item, base_url, year, category, result)
          if row is not None:
            rows.append(row)
        break
    return rows

  def row_from_item(self, item, base_url, year, category, result):
    title_node = self.first_title_node(item)
    if title_node is None:
      return None
    title = self.clean_title(self.node_text(title_node))
    author = self.clean_author(self.author_text_before_title(item, title_node))
    if not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': self.first_link_url(title_node, base_url) or base_url,
      'category': category,
    }

  def category_result_from_heading(self, text, aliases):
    heading = normalize_heading(text)
    for result_word, result in RESULT_TEXT_ALIASES.items():
      suffix = ' ' + result_word
      if not heading.endswith(suffix):
        continue
      category_text = heading[:-len(suffix)].strip()
      if category_text in aliases:
        return result
    return None

  def result_from_class(self, class_value):
    for value in re.split(r'\s+', class_value or ''):
      result = RESULT_CLASS_ALIASES.get(normalize_heading(value))
      if result is not None:
        return result
    return None

  def first_title_node(self, item):
    nodes = item.xpath('(.//em)[1]')
    return nodes[0] if nodes else None

  def author_text_before_title(self, item, title_node):
    parts = []
    for node in item.xpath('.//text()[not(ancestor::script or ancestor::style or ancestor::figure)]'):
      parent = node.getparent()
      if parent is not None and (
          parent is title_node or title_node in parent.xpath('ancestor-or-self::*')):
        break
      text = normalize_line(str(node))
      if text:
        parts.append(text)
    return normalize_line(' '.join(parts))

  def accepted_categories(self, category, category_aliases):
    return {
      normalize_heading(value)
      for value in (category, *category_aliases)
      if value
    }

  def clean_title(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    text = normalize_line(value)
    text = re.sub(r'^\s*by\s+', '', text, flags=re.I)
    text = re.sub(r'\s*,?\s*$', '', text).strip()
    text = re.sub(
      r'\s*,?\s*(?:translated|translation|edited|ed\.?|eds?\.?)\b.*$',
      '',
      text,
      flags=re.I)
    return strip_publication_notes(text).strip(' "\u201c\u201d,')

  def html_root(self, html):
    return lxml_html.fromstring(html or '<html></html>')

  def node_text(self, node):
    return normalize_line(' '.join(
      text.strip()
      for text in node.xpath('.//text()[not(ancestor::script or ancestor::style)]')
      if text.strip()))

  def first_link_url(self, node, base_url):
    hrefs = node.xpath('(.//a[@href])[1]/@href|ancestor-or-self::a[@href][1]/@href')
    return urljoin(base_url, hrefs[0]) if hrefs else ''

  def year_from_url(self, url):
    match = re.search(r'/past-awards/((?:19|20)\d{2})(?:\D|$)', url or '')
    return int(match.group(1)) if match is not None else None

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
    result_order = {RESULT_WINNER: 0, RESULT_NOMINEE: 1}
    for year in sorted(by_year, key=lambda value: int(value)):
      award_rows = sorted(
        by_year[year],
        key=lambda row: result_order.get(row.get('result'), 99))
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in award_rows
      ]
      entries.extend(assign_positions(
        award_rows,
        int(year),
        tied_winners_share_position=True))
    return entries


class NBCCWikipediaParser(AwardParserBase):
  """
  Parse category-specific NBCC Wikipedia award tables.
  """

  AWARD_NAME = AWARD_NAME

  def parse(self, html, base_url, name, category=DEFAULT_CATEGORY, category_aliases=()):
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
      header_map = self.header_map(table)
      if self.has_required_columns(header_map):
        rows.extend(self.rows_from_table(table, header_map, base_url, category))
    return rows

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
      if not title or not author:
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
        key = HEADER_ALIASES.get(normalize_heading(self.clean_cell_text(cell)))
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
      if HEADER_ALIASES.get(normalize_heading(self.clean_cell_text(cells[index]))) != key:
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
    if text in RESULT_TEXT_ALIASES:
      return RESULT_TEXT_ALIASES[text]
    for alias, result in RESULT_TEXT_ALIASES.items():
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
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    return NBCCAwardParser().clean_author(value)

  def first_link_url(self, cell, base_url):
    hrefs = cell.xpath('(.//a[@href])[1]/@href')
    return urljoin(base_url, hrefs[0]) if hrefs else ''

  def html_root(self, html):
    return lxml_html.fromstring(html or '<html></html>')

  def year_from_text(self, value):
    match = re.search(r'(19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def dedupe_rows(self, rows):
    return NBCCAwardParser().dedupe_rows(rows)

  def entries_from_rows(self, rows):
    return NBCCAwardParser().entries_from_rows(rows)
