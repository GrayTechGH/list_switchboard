#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Orwell Prize for Political Writing parsers.

Maintenance notes:
- The Orwell site mixes Political Writing with Political Fiction, Journalism,
  Reporting Homelessness, Youth, and other prize categories. Official parsing
  must stay bounded to Political Writing sections.
- V1 covers the current Political Writing prize line and does not fold in the
  older combined Orwell Prize for Books history.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag
from lxml import html as lxml_html

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER,
    assign_positions, normalize_heading, normalize_line,
    strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER,
    assign_positions, normalize_heading, normalize_line,
    strip_publication_notes,
  )
  from .generic import position_sort_key


AWARD_NAME = 'Orwell Prize for Political Writing'
CATEGORY = 'Political Writing'
RESULT_FINALIST = 'finalist'
RESULT_ORDER = {
  RESULT_WINNER: 0,
  RESULT_FINALIST: 1,
  RESULT_SHORTLISTED: 2,
}
HEADER_ALIASES = {
  'year': 'year',
  'award year': 'year',
  'author': 'author',
  'authors': 'author',
  'title': 'title',
  'book': 'title',
  'work': 'title',
  'result': 'result',
  'status': 'result',
}
RESULT_ALIASES = {
  'winner': RESULT_WINNER,
  'won': RESULT_WINNER,
  'finalist': RESULT_FINALIST,
  'finalists': RESULT_FINALIST,
  'shortlist': RESULT_SHORTLISTED,
  'shortlisted': RESULT_SHORTLISTED,
}


class OrwellOfficialParser(AwardParserBase):
  """
  Parse official Orwell Foundation Political Writing pages.

  Accepted source shapes:
  - Official finalist/winner news sections with title/author rows.
  - Per-book detail pages headed by year/category/result.
  - Official previous-winners tables or lists with explicit year/title/author.
  """

  AWARD_NAME = AWARD_NAME

  def parse(self, pages, base_url, name, category=CATEGORY):
    if isinstance(pages, (str, bytes)):
      pages = ((base_url, pages),)
    rows = []
    for page_url, page_html in pages:
      rows.extend(self.parse_rows(page_html, page_url, category))
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url, category):
    soup = BeautifulSoup(html or '', 'html.parser')
    rows = []
    rows.extend(self.detail_rows(soup, base_url, category))
    rows.extend(self.table_rows(lxml_html.fromstring(html or '<html></html>'), base_url, category))
    for heading in self.political_writing_headings(soup):
      current_result = self.result_from_heading(self.node_text(heading))
      for node in self.section_nodes(heading):
        if self.is_heading_node(node):
          node_result = self.result_from_heading(self.node_text(node))
          if node_result is not None:
            current_result = node_result
          continue
        for item in self.row_nodes(node):
          row = self.row_from_node(
            item, base_url, category, current_result or RESULT_FINALIST)
          if row is not None:
            rows.append(row)
    return rows

  def detail_rows(self, soup, base_url, category):
    rows = []
    heading = soup.find(
      lambda tag: isinstance(tag, Tag)
      and self.is_heading_node(tag)
      and self.is_political_writing_heading(self.node_text(tag))
      and self.is_detail_heading(self.node_text(tag))
      and self.year_from_text(self.node_text(tag)) is not None)
    if heading is None:
      return rows
    result = self.result_from_heading(self.node_text(heading))
    if result is None:
      return rows
    title_node = heading.find_next(['h1', 'h2', 'h3', 'p'])
    while title_node is not None and normalize_heading(self.node_text(title_node)) == normalize_heading(self.node_text(heading)):
      title_node = title_node.find_next(['h1', 'h2', 'h3', 'p'])
    if title_node is None:
      return rows
    title = self.clean_title(self.node_text(title_node))
    author = ''
    publisher = ''
    for node in title_node.find_all_next(['p', 'div', 'span', 'h3', 'h4'], limit=8):
      text = self.node_text(node)
      if not text:
        continue
      if self.is_peer_prize_heading(node):
        break
      label, value = self.label_value(text)
      if label == 'author':
        author = self.clean_author(value)
      elif label == 'publisher':
        publisher = normalize_line(value)
      elif not author and not self.is_ignored_row(text):
        author = self.clean_author(text)
      if author:
        break
    if title and author:
      rows.append({
        'award_year': str(self.year_from_text(self.node_text(heading))),
        'title': title,
        'author': author,
        'result': result,
        'source_url': self.first_link_url(title_node, base_url) or base_url,
        'category': category,
        'publisher': publisher,
      })
    return rows

  def political_writing_headings(self, soup):
    return [
      node for node in soup.find_all(['h1', 'h2', 'h3', 'h4', 'strong'])
      if self.is_political_writing_heading(self.node_text(node))
    ]

  def is_political_writing_heading(self, value):
    text = normalize_heading(value)
    return (
      'political writing' in text
      and not any(boundary in text for boundary in (
        'political fiction',
        'journalism',
        'reporting homelessness',
        'exposing britain',
        'youth prize',
        'bernard crick',
      )))

  def section_nodes(self, heading):
    nodes = []
    for sibling in heading.next_siblings:
      if not isinstance(sibling, Tag):
        continue
      if self.is_peer_prize_heading(sibling):
        break
      nodes.append(sibling)
    return nodes

  def is_peer_prize_heading(self, node):
    if not self.is_heading_node(node):
      return False
    text = normalize_heading(self.node_text(node))
    if self.is_political_writing_heading(text):
      return False
    return any(value in text for value in (
      'political fiction',
      'journalism',
      'reporting homelessness',
      'exposing britain',
      'youth prize',
      'bernard crick',
      'orwell prize for books',
      'combined book prize',
    ))

  def is_heading_node(self, node):
    name = getattr(node, 'name', None) or getattr(node, 'tag', '')
    return (name or '').lower() in {
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong'}

  def row_nodes(self, node):
    children = node.find_all('li') if isinstance(node, Tag) else []
    return children or [node]

  def row_from_node(self, node, base_url, category, default_result):
    text = self.clean_row_text(self.node_text(node))
    if self.is_ignored_row(text):
      return None
    result, work_text = self.result_and_work_text(text, default_result)
    title, author = self.title_author_from_node(node, work_text)
    if not title or not author:
      title, author = self.title_author_from_text(work_text)
    year = (
      self.year_from_text(text)
      or self.year_from_text(self.node_text(self.nearest_year_heading(node)))
      or self.year_from_text(base_url))
    if year is None or not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': self.clean_title(title),
      'author': self.clean_author(author),
      'result': result,
      'source_url': self.first_link_url(node, base_url) or base_url,
      'category': category,
    }

  def title_author_from_node(self, node, work_text):
    if not isinstance(node, Tag):
      return '', ''
    title_node = node.find(['em', 'i'])
    if title_node is None:
      return '', ''
    title = self.node_text(title_node)
    full_text = self.node_text(node)
    after = full_text.split(title, 1)[1] if title in full_text else work_text
    author = self.author_from_text_after_title(after)
    if not author:
      _title, author = self.title_author_from_text(work_text)
    return title, author

  def title_author_from_text(self, value):
    text = strip_publication_notes(self.strip_result_prefix(value))
    text = re.sub(r'^\s*(?:\d{4}\s*)+', '', text).strip()
    for separator in (' | ', ' - ', ' \u2013 ', ' \u2014 '):
      if separator in text:
        title, author = text.split(separator, 1)
        return title.strip(), self.author_before_publisher(author)
    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', text, re.I)
    if by_match is not None:
      return by_match.group(1).strip(), self.author_before_publisher(by_match.group(2))
    if ',' in text:
      title, author = text.rsplit(',', 1)
      return title.strip(), author.strip()
    return '', ''

  def author_from_text_after_title(self, value):
    text = normalize_line(value).strip(' ,:-\u2013\u2014|')
    text = re.sub(r'^\s*by\s+', '', text, flags=re.I)
    return self.author_before_publisher(text)

  def author_before_publisher(self, value):
    text = normalize_line(value)
    text = re.sub(r'\s*\([^()]*\)\s*$', '', text).strip()
    if ',' in text:
      author, _publisher = text.rsplit(',', 1)
      return author.strip()
    return text.strip()

  def result_and_work_text(self, text, default_result):
    match = re.match(
      r'^\s*(winner|finalists?|shortlist(?:ed)?)\s*:\s*(.+)$',
      text,
      re.I)
    if match is None:
      return default_result, text
    result = RESULT_ALIASES.get(normalize_heading(match.group(1)), default_result)
    return result, match.group(2).strip()

  def result_from_heading(self, text):
    heading = normalize_heading(text)
    if 'winner' in heading:
      return RESULT_WINNER
    if 'finalist' in heading:
      return RESULT_FINALIST
    if 'shortlist' in heading:
      return RESULT_SHORTLISTED
    return None

  def is_detail_heading(self, text):
    heading = normalize_heading(text)
    return (
      'book prize' in heading
      and ('winner' in heading or 'finalist' in heading)
      and 'finalists' not in heading
      and 'shortlist' not in heading)

  def table_rows(self, root, base_url, category):
    rows = []
    for table in root.xpath('//table'):
      heading_text = self.node_text_lxml(self.nearest_lxml_heading(table))
      if heading_text and not self.is_political_writing_heading(heading_text):
        continue
      header_map = self.header_map(table)
      if not self.has_required_columns(header_map):
        continue
      rows.extend(self.rows_from_table(table, header_map, base_url, category))
    return rows

  def rows_from_table(self, table, header_map, base_url, category):
    rows = []
    current_year = None
    current_result_by_year = {}
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
      result = self.result_from_cell(
        self.cell_for_key(cells, header_map, 'result', missing_year))
      if result is None:
        result = (
          RESULT_SHORTLISTED
          if current_result_by_year.get(year) == RESULT_SHORTLISTED
          else RESULT_WINNER)
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
        'source_url': self.first_link_url_lxml(title_cell, base_url) or base_url,
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
    if text in RESULT_ALIASES:
      return RESULT_ALIASES[text]
    for alias, result in RESULT_ALIASES.items():
      if text.startswith(alias + ' '):
        return result
    return None

  def nearest_lxml_heading(self, node):
    for sibling in node.itersiblings(preceding=True):
      if (sibling.tag or '').lower() in {'h1', 'h2', 'h3', 'h4'}:
        return sibling
    return None

  def nearest_year_heading(self, node):
    current = node
    while isinstance(current, Tag):
      for sibling in current.previous_siblings:
        if isinstance(sibling, Tag) and self.is_heading_node(sibling):
          if self.year_from_text(self.node_text(sibling)):
            return sibling
      current = current.parent
    return None

  def clean_cell_text(self, cell):
    if cell is None:
      return ''
    text = normalize_line(' '.join(
      text.strip()
      for text in cell.xpath(
        './/text()[not(ancestor::sup or ancestor::style or ancestor::script)]')
      if text.strip()))
    return normalize_line(re.sub(r'\s*\[\s*\d+\s*\]\s*', ' ', text))

  def clean_row_text(self, value):
    text = normalize_line(value)
    text = re.sub(r'\s*\[\s*\d+\s*\]\s*', ' ', text)
    return normalize_line(text)

  def clean_title(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    text = normalize_line(value)
    text = re.sub(r'^\s*by\s+', '', text, flags=re.I)
    text = re.sub(r'\s*,?\s*(?:translated|translation|edited|ed\.?|eds?\.?)\b.*$', '', text, flags=re.I)
    return strip_publication_notes(text).strip(' "\u201c\u201d,')

  def strip_result_prefix(self, value):
    return re.sub(
      r'^\s*(?:winner|finalists?|shortlist(?:ed)?)\s*:\s*',
      '',
      value or '',
      flags=re.I).strip()

  def is_ignored_row(self, value):
    text = normalize_heading(value)
    if not text:
      return True
    return any(value in text for value in (
      'political fiction',
      'journalism',
      'reporting homelessness',
      'youth prize',
      'orwell prize for books',
      'judges',
      'jury',
      'deadline',
      'submit',
      'eligibility',
    ))

  def label_value(self, text):
    match = re.match(r'^\s*([A-Za-z ]+)\s*:\s*(.+)$', text or '')
    if match is None:
      return '', text
    return normalize_heading(match.group(1)), match.group(2).strip()

  def first_link_url(self, node, base_url):
    if not isinstance(node, Tag):
      return ''
    link = node.find('a', href=True)
    return urljoin(base_url, link['href']) if link is not None else ''

  def first_link_url_lxml(self, node, base_url):
    hrefs = node.xpath('(.//a[@href])[1]/@href')
    return urljoin(base_url, hrefs[0]) if hrefs else ''

  def node_text(self, node):
    if node is None:
      return ''
    if isinstance(node, Tag):
      return normalize_line(node.get_text(' ', strip=True))
    return normalize_line(str(node))

  def node_text_lxml(self, node):
    if node is None:
      return ''
    return normalize_line(' '.join(
      text.strip()
      for text in node.xpath('.//text()[not(ancestor::script or ancestor::style)]')
      if text.strip()))

  def year_from_text(self, value):
    match = re.search(r'(19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def dedupe_rows(self, rows):
    best_by_key = {}
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['category']),
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      current = best_by_key.get(key)
      if current is None or RESULT_ORDER.get(row['result'], 99) < RESULT_ORDER.get(current['result'], 99):
        best_by_key[key] = row
    return list(best_by_key.values())

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      award_rows = sorted(
        by_year[year],
        key=lambda row: RESULT_ORDER.get(row.get('result'), 99))
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in award_rows
      ]
      entries.extend(assign_positions(
        award_rows,
        int(year),
        tied_winners_share_position=True))
    return entries


class OrwellWikipediaParser(OrwellOfficialParser):
  """Parse the bounded Political Writing table on Wikipedia's Orwell page."""

  def parse(self, html, base_url, name, category=CATEGORY):
    root = lxml_html.fromstring(html or '<html></html>')
    rows = []
    for table in self.political_writing_tables(root):
      header_map = self.header_map(table)
      if self.has_required_columns(header_map):
        rows.extend(self.rows_from_table(table, header_map, base_url, category))
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def political_writing_tables(self, root):
    for heading in root.xpath('//h2|//h3|//h4'):
      text = normalize_heading(self.node_text_lxml(heading))
      if 'political writing' not in text or '2019' not in text:
        continue
      for sibling in heading.itersiblings():
        if (sibling.tag or '').lower() in {'h2', 'h3', 'h4'}:
          break
        if (sibling.tag or '').lower() == 'table':
          yield sibling
        for table in sibling.xpath('.//table'):
          yield table
