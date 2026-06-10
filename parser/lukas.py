#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Lukas Prize Project parsers.

Maintenance notes:
- The Lukas Prize Project mixes the Book Prize, Mark Lynton History Prize, and
  Work-in-Progress Award on shared official pages. Parser boundaries must stay
  anchored to the configured prize heading so sibling prize rows do not leak in.
- The Book Prize recipe uses LibraryThing and Wikipedia replacement fallbacks.
  Mark Lynton uses Wikipedia only.
"""

import re
from urllib.parse import urljoin

from lxml import html as lxml_html

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER,
    assign_positions, normalize_heading, normalize_line,
    strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
  from calibre_plugins.list_switchboard.parser.librarything_base import (
    LibraryThingAwardParserBase,
  )
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER,
    assign_positions, normalize_heading, normalize_line,
    strip_publication_notes,
  )
  from .generic import position_sort_key
  from .librarything_base import LibraryThingAwardParserBase


AWARD_NAME = 'J. Anthony Lukas Book Prize'
CATEGORY = 'Book Prize'
MARK_LYNTON_AWARD_NAME = 'Mark Lynton History Prize'
MARK_LYNTON_CATEGORY = 'History Prize'
RESULT_FINALIST = 'finalist'
RESULT_ORDER = {
  RESULT_WINNER: 0,
  RESULT_FINALIST: 1,
  RESULT_SHORTLISTED: 2,
  'nominee': 3,
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
  'publisher': 'publisher',
}
RESULT_ALIASES = {
  'winner': RESULT_WINNER,
  'finalist': RESULT_FINALIST,
  'finalists': RESULT_FINALIST,
  'shortlist': RESULT_SHORTLISTED,
  'shortlisted': RESULT_SHORTLISTED,
}


class LukasOfficialParser(AwardParserBase):
  """
  Parse official Columbia/Nieman Lukas Book Prize pages.

  Invariants:
  - Only rows inside a J. Anthony Lukas Book Prize section are accepted.
  - Peer prize headings are hard boundaries.
  """

  AWARD_NAME = AWARD_NAME
  CATEGORY = CATEGORY
  CATEGORY_ALIASES = (
    'J. Anthony Lukas Book Prize',
    'Lukas Book Prize',
  )
  PEER_PRIZE_ALIASES = (
    'Mark Lynton History Prize',
    'Lynton History Prize',
    'J. Anthony Lukas Work-in-Progress Award',
    'J. Anthony Lukas Work-In-Progress Awards',
    'J. Anthony Lukas Work-In-Progress Prizes',
    'Lukas Work-in-Progress',
    'Work-in-Progress Award',
    'Work-in-Progress Awards',
    'Work-in-Progress Prizes',
  )

  def parse(self, pages, base_url, name, category=None):
    if isinstance(pages, (str, bytes)):
      pages = ((base_url, pages),)
    category = category or self.CATEGORY
    rows = []
    for page_url, page_html in pages:
      rows.extend(self.parse_rows(page_html, page_url, category))
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url, category):
    root = self.html_root(html)
    rows = []
    for heading in self.prize_headings(root):
      current_result = self.result_from_heading(self.node_text(heading))
      for node in self.section_nodes(heading):
        node_result = (
          self.result_from_heading(self.node_text(node))
          if self.is_heading_node(node) else None)
        if node_result is not None:
          current_result = node_result
          continue
        section_tables = node.xpath('self::table|.//table')
        if section_tables:
          for table in section_tables:
            header_map = self.header_map(table)
            if self.has_required_columns(header_map):
              rows.extend(self.rows_from_table(table, header_map, base_url, category))
          continue
        for item in self.row_nodes(node):
          row = self.row_from_node(
            item, base_url, category, current_result or RESULT_SHORTLISTED)
          if row is not None:
            rows.append(row)
    return rows

  def prize_headings(self, root):
    headings = []
    for heading in root.xpath('//h1|//h2|//h3|//h4|//strong|//p'):
      if self.is_configured_prize_heading(heading):
        headings.append(heading)
    return headings

  def book_prize_headings(self, root):
    return self.prize_headings(root)

  def section_nodes(self, heading):
    nodes = []
    for sibling in heading.itersiblings():
      if self.is_peer_prize_heading(sibling):
        break
      nodes.append(sibling)
    return nodes

  def is_peer_prize_heading(self, node):
    if not self.is_heading_node(node):
      return False
    if self.is_configured_prize_heading(node):
      return False
    text = normalize_heading(self.node_text(node))
    return any(alias in text for alias in self.normalized_peer_prize_aliases())

  def is_configured_prize_heading(self, node):
    text = normalize_heading(self.node_text(node))
    return any(alias in text for alias in self.normalized_category_aliases())

  def normalized_category_aliases(self):
    return tuple(
      normalize_heading(alias)
      for alias in self.CATEGORY_ALIASES
      if normalize_heading(alias))

  def normalized_peer_prize_aliases(self):
    return tuple(
      normalize_heading(alias)
      for alias in self.PEER_PRIZE_ALIASES
      if normalize_heading(alias))

  def is_heading_node(self, node):
    return (node.tag or '').lower() in {
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong'}

  def row_nodes(self, node):
    children = node.xpath('.//li')
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

  def parse_table_rows(self, root, base_url, category):
    rows = []
    for table in root.xpath('//table'):
      header_map = self.header_map(table)
      if not self.has_required_columns(header_map):
        continue
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
      result = self.result_from_cell(
        self.cell_for_key(cells, header_map, 'result', missing_year))
      if result is None:
        row_count = row_count_by_year.get(year, 0)
        result = RESULT_WINNER if row_count == 0 else RESULT_SHORTLISTED
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

  def result_and_work_text(self, text, default_result):
    match = re.match(
      r'^\s*(winner|finalists?|shortlist(?:ed)?)\s*:?\s*(.+)$',
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

  def title_author_from_node(self, node, work_text):
    title_nodes = node.xpath('(.//em|.//i)[1]')
    if not title_nodes:
      return '', ''
    title_node = title_nodes[0]
    title = self.node_text(title_node)
    before = []
    after = []
    seen_title = False
    for text_node in node.xpath('.//text()[not(ancestor::script or ancestor::style)]'):
      parent = text_node.getparent()
      text = normalize_line(str(text_node))
      if not text:
        continue
      if parent is title_node or title_node in parent.xpath('ancestor-or-self::*'):
        seen_title = True
        continue
      if seen_title:
        after.append(text)
      else:
        before.append(text)
    author = self.author_from_text_after_title(' '.join(after))
    if not author:
      prefix = self.strip_result_prefix(' '.join(before))
      author = self.author_from_text_before_title(prefix)
    if not author:
      _title, author = self.title_author_from_text(work_text)
    return title, author

  def title_author_from_text(self, value):
    text = strip_publication_notes(self.strip_result_prefix(value))
    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', text, re.I)
    if by_match is not None:
      return by_match.group(1).strip(), by_match.group(2).strip()
    for_match = re.match(r'^(.+?)\s+for\s+(?:their\s+book\s+)?(.+)$', text, re.I)
    if for_match is not None:
      return for_match.group(2).strip(), for_match.group(1).strip()
    if ',' in text:
      author, title = text.split(',', 1)
      return title.strip(), author.strip()
    return '', ''

  def author_from_text_after_title(self, value):
    text = normalize_line(value)
    match = re.search(r'\bby\s+(.+)$', text, re.I)
    if match is not None:
      return match.group(1).strip()
    return ''

  def author_from_text_before_title(self, value):
    text = normalize_line(value).strip(' ,:')
    if text.casefold().startswith('by '):
      text = text[3:].strip()
    return text

  def strip_result_prefix(self, value):
    return re.sub(
      r'^\s*(?:winner|finalists?|shortlist(?:ed)?)\s*:?\s*',
      '',
      value or '',
      flags=re.I).strip()

  def is_ignored_row(self, value):
    text = normalize_heading(value)
    if not text:
      return True
    if any(alias in text for alias in self.normalized_peer_prize_aliases()):
      return True
    return any(value in text for value in (
      'juror',
      'jury',
      'deadline',
      'submit',
      'eligibility',
    ))

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

  def html_root(self, html):
    return lxml_html.fromstring(html or '<html></html>')

  def node_text(self, node):
    if node is None:
      return ''
    return normalize_line(' '.join(
      text.strip()
      for text in node.xpath('.//text()[not(ancestor::script or ancestor::style)]')
      if text.strip()))

  def nearest_year_heading(self, node):
    current = node
    while current is not None:
      for sibling in current.itersiblings(preceding=True):
        if self.is_heading_node(sibling) and self.year_from_text(self.node_text(sibling)):
          return sibling
      current = current.getparent()
    return None

  def first_link_url(self, node, base_url):
    hrefs = node.xpath('(.//a[@href])[1]/@href|ancestor-or-self::a[@href][1]/@href')
    return urljoin(base_url, hrefs[0]) if hrefs else ''

  def year_from_text(self, value):
    match = re.search(r'(19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

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

  def clean_cell_text(self, cell):
    if cell is None:
      return ''
    text = normalize_line(' '.join(
      text.strip()
      for text in cell.xpath(
        './/text()[not(ancestor::sup or ancestor::style or ancestor::script)]')
      if text.strip()))
    return normalize_line(re.sub(r'\s*\[\s*\d+\s*\]\s*', ' ', text))

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


class LukasWikipediaParser(LukasOfficialParser):
  """Parse the J. Anthony Lukas Book Prize Wikipedia recipient table."""

  def parse(self, html, base_url, name, category=None):
    category = category or self.CATEGORY
    rows = self.parse_table_rows(self.html_root(html), base_url, category)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))


class MarkLyntonHistoryPrizeParser(LukasOfficialParser):
  """Parse official Columbia/Nieman Mark Lynton History Prize pages."""

  AWARD_NAME = MARK_LYNTON_AWARD_NAME
  CATEGORY = MARK_LYNTON_CATEGORY
  CATEGORY_ALIASES = (
    'Mark Lynton History Prize',
    'Lynton History Prize',
  )
  PEER_PRIZE_ALIASES = (
    'J. Anthony Lukas Book Prize',
    'Lukas Book Prize',
    'J. Anthony Lukas Work-in-Progress Award',
    'J. Anthony Lukas Work-In-Progress Awards',
    'J. Anthony Lukas Work-In-Progress Prizes',
    'Lukas Work-in-Progress',
    'Work-in-Progress Award',
    'Work-in-Progress Awards',
    'Work-in-Progress Prizes',
  )


class MarkLyntonHistoryPrizeWikipediaParser(MarkLyntonHistoryPrizeParser):
  """Parse the Mark Lynton History Prize Wikipedia recipient table."""

  def parse(self, html, base_url, name, category=None):
    category = category or self.CATEGORY
    rows = self.parse_table_rows(self.html_root(html), base_url, category)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))


class LukasLibraryThingParser(LibraryThingAwardParserBase):
  """Parse LibraryThing Lukas fallback rows with source-specific result names."""

  AWARD_NAME = AWARD_NAME

  def result_from_heading(self, heading):
    text = normalize_heading(heading.get_text(' ', strip=True))
    if text.startswith('winner'):
      return RESULT_WINNER
    if text.startswith('finalist'):
      return RESULT_FINALIST
    if text.startswith('shortlist') or text.startswith('shortlisted'):
      return RESULT_SHORTLISTED
    if text.startswith('nominee'):
      return 'nominee'
    return None

  def dedupe_rows(self, rows):
    return LukasOfficialParser().dedupe_rows(rows)

  def entries_from_rows(self, rows):
    return LukasOfficialParser().entries_from_rows(rows)
