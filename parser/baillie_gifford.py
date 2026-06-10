#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Baillie Gifford Prize official archive and Wikipedia fallback parsers.

Maintenance notes:
- Official year pages expose book links in `The winner` and `The shortlist`
  sections. Linked book detail pages carry cleaner title,
  subtitle, and author fields, so the official parser uses them when a fetcher
  supplies linked-page fetching.
- The Wikipedia fallback is a replacement source and is intentionally partial:
  it preserves winners/shortlists from table rows, but not official longlists.
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
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER,
    assign_positions, normalize_heading, normalize_line,
    strip_publication_notes,
  )
  from .generic import position_sort_key


AWARD_NAME = 'Baillie Gifford Prize'
DEFAULT_CATEGORY = 'Non-Fiction'
STAGE_RESULTS = {
  'the winner': RESULT_WINNER,
  'winner': RESULT_WINNER,
  'the shortlist': RESULT_SHORTLISTED,
  'shortlist': RESULT_SHORTLISTED,
}


class BaillieGiffordPrizeParser(AwardParserBase):
  """
  Parse official Baillie Gifford `year-by-year/YYYY` pages.

  Invariants:
  - Only `/books-and-authors/` links inside winner/shortlist sections become
    entries; longlists, judge/news/podcast/gallery links are ignored.
  - Linked detail-page failures stay as parser notes when the year page still
    has enough title/author text to produce entries.
  """

  AWARD_NAME = AWARD_NAME

  def parse(self, html, base_url, name, category=DEFAULT_CATEGORY, fetch_url=None, **_kwargs):
    notes = []
    rows = self.parse_rows(html, base_url, category, fetch_url, notes)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def parse_rows(self, html, base_url, category, fetch_url, notes):
    root = self.html_root(html)
    year = self.year_from_url(base_url) or self.year_from_text(self.node_text(root))
    if year is None:
      return []
    rows = []
    for section, result in self.stage_sections(root):
      for link in self.book_links(section):
        title, author, source_url = self.work_from_link(link, base_url, fetch_url, notes)
        if not title or not author:
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

  def stage_sections(self, root):
    sections = []
    for heading in root.xpath('//h2'):
      key = normalize_heading(self.node_text(heading))
      result = STAGE_RESULTS.get(key)
      if result is None:
        continue
      containers = heading.xpath('ancestor::section[1]')
      if containers:
        sections.append((containers[0], result))
    return sections

  def book_links(self, section):
    links = []
    seen = set()
    for link in section.xpath('.//a[contains(@href, "/books-and-authors/")]'):
      href = link.get('href')
      if not href or href in seen:
        continue
      seen.add(href)
      links.append(link)
    return links

  def work_from_link(self, link, base_url, fetch_url, notes):
    source_url = urljoin(base_url, link.get('href') or '')
    if fetch_url is not None and source_url:
      try:
        detail = self.parse_detail_page(fetch_url(source_url), source_url)
      except Exception as err:
        notes.append(
          'Baillie Gifford detail page failed for %s: %s' % (
            source_url, str(err) or err.__class__.__name__))
      else:
        if detail[0] and detail[1]:
          return detail[0], detail[1], source_url
    title = self.title_from_link(link)
    author = self.author_from_link(link)
    return title, author, source_url

  def parse_detail_page(self, html, base_url):
    root = self.html_root(html)
    h1_nodes = root.xpath('(//main//h1|//h1)[1]')
    if not h1_nodes:
      return '', '', base_url
    title = self.clean_title(self.node_text(h1_nodes[0]))
    header_nodes = h1_nodes[0].xpath('ancestor::header[1]')
    header = header_nodes[0] if header_nodes else h1_nodes[0].getparent()
    subtitle = ''
    author = ''
    if header is not None:
      subtitle_nodes = header.xpath(
        './/*[contains(concat(" ", normalize-space(@class), " "), " h-3 ")]/p'
        '|.//*[contains(concat(" ", normalize-space(@class), " "), " subtitle ")]')
      for node in subtitle_nodes:
        subtitle = self.clean_title(self.node_text(node))
        if subtitle:
          break
      author_nodes = header.xpath(
        './/p[contains(concat(" ", normalize-space(@class), " "), " step-4 ")]'
        '|.//*[contains(concat(" ", normalize-space(@class), " "), " author ")]')
      for node in author_nodes:
        author = self.clean_author(self.node_text(node))
        if author:
          break
    if subtitle and subtitle != title:
      title = f'{title}: {subtitle}'
    return title, author, base_url

  def title_from_link(self, link):
    title_nodes = link.xpath(
      '(.//*[contains(concat(" ", normalize-space(@class), " "), " winner-box__title ")]'
      '|.//*[contains(concat(" ", normalize-space(@class), " "), " listing__title ")]'
      '|.//*[self::h2 or self::h3])[1]')
    if title_nodes:
      return self.clean_title(self.node_text(title_nodes[0]))
    text = re.sub(r'^\s*(19|20)\d{2}\s+', '', self.node_text(link))
    return self.clean_title(text)

  def author_from_link(self, link):
    author_nodes = link.xpath(
      '(.//*[contains(concat(" ", normalize-space(@class), " "), " winner-box__author ")]'
      '|.//*[contains(concat(" ", normalize-space(@class), " "), " listing__sub ")]'
      '|.//*[contains(concat(" ", normalize-space(@class), " "), " author ")])[1]')
    if not author_nodes:
      return ''
    return self.clean_author(self.node_text(author_nodes[0]))

  def clean_title(self, value):
    return normalize_line(value).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    text = re.sub(r'^\s*by\s+', '', normalize_line(value), flags=re.I)
    return strip_publication_notes(text).strip(' "\u201c\u201d,')

  def html_root(self, html):
    return lxml_html.fromstring(html or '<html></html>')

  def node_text(self, node):
    return normalize_line(' '.join(
      text.strip()
      for text in node.xpath('.//text()[not(ancestor::script or ancestor::style)]')
      if text.strip()))

  def year_from_url(self, url):
    match = re.search(r'/year-by-year/((?:19|20)\d{2})(?:\D|$)', url or '')
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
    result_order = {
      RESULT_WINNER: 0,
      RESULT_SHORTLISTED: 1,
    }
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


class BaillieGiffordWikipediaParser(AwardParserBase):
  """
  Parse Baillie Gifford Prize Wikipedia result tables.
  """

  AWARD_NAME = AWARD_NAME
  RESULT_ALIASES = {
    'winner': RESULT_WINNER,
    'won': RESULT_WINNER,
    'shortlist': RESULT_SHORTLISTED,
    'shortlisted': RESULT_SHORTLISTED,
    'finalist': RESULT_SHORTLISTED,
  }
  HEADER_ALIASES = {
    'year': 'year',
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

  def parse(self, html, base_url, name, category=DEFAULT_CATEGORY, **_kwargs):
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
    return re.sub(r'\s*\[\s*[a-z0-9]+\s*\]\s*', ' ', text, flags=re.I).strip()

  def clean_title(self, value):
    return normalize_line(value).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def first_link_url(self, cell, base_url):
    hrefs = cell.xpath('(.//a[@href])[1]/@href')
    return urljoin(base_url, hrefs[0]) if hrefs else ''

  def html_root(self, html):
    return lxml_html.fromstring(html or '<html></html>')

  def year_from_text(self, value):
    match = re.search(r'(19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def dedupe_rows(self, rows):
    return BaillieGiffordPrizeParser().dedupe_rows(rows)

  def entries_from_rows(self, rows):
    return BaillieGiffordPrizeParser().entries_from_rows(rows)
