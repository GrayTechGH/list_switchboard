#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Booker Prize official-site and Wikipedia fallback parsers.

Maintenance notes:
- V1 imports winners and shortlists only. Official longlist sections are
  intentionally ignored even when the year page exposes them.
- International Booker pages can include translator credits near the work
  author. Matching remains title plus work author; translator text is stripped
  from parsed authors.
"""

import re
from urllib.parse import urljoin

from lxml import html as lxml_html

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key


RESULT_ORDER = {
  RESULT_WINNER: 0,
  RESULT_SHORTLISTED: 1,
}
STAGE_RESULTS = {
  'winner': RESULT_WINNER,
  'winners': RESULT_WINNER,
  'shortlist': RESULT_SHORTLISTED,
  'shortlisted': RESULT_SHORTLISTED,
  'the shortlist': RESULT_SHORTLISTED,
}
IGNORED_STAGES = {
  'longlist',
  'longlisted',
  'the longlist',
}
HEADER_ALIASES = {
  'year': 'year',
  'award year': 'year',
  'author': 'author',
  'authors': 'author',
  'writer': 'author',
  'title': 'title',
  'book': 'title',
  'work': 'title',
  'novel': 'title',
  'result': 'result',
  'status': 'result',
  'outcome': 'result',
  'stage': 'result',
}
RESULT_ALIASES = {
  'winner': RESULT_WINNER,
  'won': RESULT_WINNER,
  'shortlist': RESULT_SHORTLISTED,
  'shortlisted': RESULT_SHORTLISTED,
  'finalist': RESULT_SHORTLISTED,
  'finalists': RESULT_SHORTLISTED,
}


class BookerPrizeOfficialParser(AwardParserBase):
  """
  Parse one official Booker Library prize-year page.

  Invariants:
  - Stage selection comes from the nearest preceding Winner/Shortlist/Longlist
    heading, not from page-wide text.
  - Linked detail pages are optional cleanup only; year/result come from the
    prize-year page context.
  """

  def __init__(self, award_name, category, url_marker='/the-booker-library/books/',
               *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.AWARD_NAME = award_name
    self.award_name = award_name
    self.category = category
    self.url_marker = url_marker

  def parse(self, html, base_url, name, category=None, fetch_url=None, **_kwargs):
    notes = []
    rows = self.parse_rows(html, base_url, category or self.category, fetch_url, notes)
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
    for link in self.book_links(root, base_url):
      result = self.result_for_link(link)
      if result not in (RESULT_WINNER, RESULT_SHORTLISTED):
        continue
      context = self.link_context(link)
      title, author = self.title_author_from_context(link, context)
      source_url = urljoin(base_url, link.get('href') or '')
      if fetch_url is not None and source_url:
        try:
          detail_title, detail_author = self.title_author_from_detail(
            fetch_url(source_url))
        except Exception as err:
          notes.append(
            'Official Booker detail page failed for %s: %s' % (
              source_url, str(err) or err.__class__.__name__))
        else:
          title = detail_title or title
          author = detail_author or author
      title = self.clean_title(title)
      author = self.clean_author(author)
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

  def book_links(self, root, base_url):
    links = []
    seen = set()
    for link in root.xpath('//a[@href]'):
      url = urljoin(base_url, link.get('href') or '')
      if self.url_marker not in url:
        continue
      if url in seen:
        continue
      seen.add(url)
      links.append(link)
    return links

  def result_for_link(self, link):
    for node in self.context_chain(link):
      heading = self.stage_heading_before(node)
      if heading is None:
        continue
      stage = normalize_heading(self.node_text(heading))
      if stage in IGNORED_STAGES:
        return None
      if stage in STAGE_RESULTS:
        return STAGE_RESULTS[stage]
    return None

  def context_chain(self, link):
    nodes = []
    current = self.link_context(link)
    while current is not None:
      nodes.append(current)
      current = current.getparent()
    return nodes

  def stage_heading_before(self, node):
    current = node
    while current is not None:
      for sibling in current.itersiblings(preceding=True):
        heading = self.stage_heading_in(sibling)
        if heading is not None:
          return heading
      current = current.getparent()
    return None

  def stage_heading_in(self, node):
    candidates = []
    if node.tag in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}:
      candidates.append(node)
    candidates.extend(node.xpath('.//*[self::h1 or self::h2 or self::h3 or self::h4 or self::h5 or self::h6]'))
    for candidate in reversed(candidates):
      text = normalize_heading(self.node_text(candidate))
      if text in STAGE_RESULTS or text in IGNORED_STAGES:
        return candidate
    return None

  def link_context(self, link):
    for xpath in (
        'ancestor::article[1]',
        'ancestor::li[1]',
        'ancestor::div[contains(@class, "card")][1]',
        'ancestor::section[1]'):
      nodes = link.xpath(xpath)
      if nodes:
        return nodes[0]
    return link

  def title_author_from_context(self, link, context):
    title = self.title_from_node(link) or self.title_from_node(context)
    author = self.author_from_context(context, title)
    if not author:
      parsed_title, parsed_author = self.title_author_from_text(self.node_text(context))
      title = title or parsed_title
      author = author or parsed_author
    return title, author

  def title_from_node(self, node):
    title_nodes = node.xpath(
      '(.//*[self::h1 or self::h2 or self::h3 or self::h4]'
      '|.//*[contains(concat(" ", normalize-space(@class), " "), " title ")])[1]')
    if title_nodes:
      title = self.node_text(title_nodes[0])
      if title:
        return title
    return self.node_text(node)

  def author_from_context(self, context, title=''):
    for xpath in (
        './/*[contains(concat(" ", normalize-space(@class), " "), " author ")]',
        './/*[starts-with(translate(normalize-space(.), "AUTHORBY", "authorby"), "author:")]',
        './/*[starts-with(translate(normalize-space(.), "BY", "by"), "by ")]'):
      for node in context.xpath(xpath):
        author = self.clean_author(self.node_text(node))
        if author and normalize_heading(author) != normalize_heading(title):
          return author
    for line in self.visible_lines(context):
      if self.looks_like_author_line(line):
        return self.strip_author_label(line)
    return ''

  def title_author_from_detail(self, html):
    root = self.html_root(html)
    title_nodes = root.xpath('(//main//h1|//h1)[1]')
    title = self.node_text(title_nodes[0]) if title_nodes else ''
    context = self.nearest_detail_context(title_nodes[0]) if title_nodes else root
    author = self.author_from_context(context, title) or self.author_from_context(root, title)
    return self.clean_title(title), self.clean_author(author)

  def nearest_detail_context(self, node):
    for xpath in ('ancestor::header[1]', 'ancestor::section[1]', 'ancestor::main[1]'):
      nodes = node.xpath(xpath)
      if nodes:
        return nodes[0]
    return node.getparent() or node

  def visible_lines(self, node):
    lines = []
    for item in node.xpath(
        './/*[self::h1 or self::h2 or self::h3 or self::h4 or self::p or self::li or self::span]'):
      text = self.node_text(item)
      if text and text not in lines:
        lines.append(text)
    if not lines:
      text = self.node_text(node)
      if text:
        lines.append(text)
    return lines

  def looks_like_author_line(self, value):
    text = normalize_heading(value)
    return text.startswith('author ') or text.startswith('by ')

  def strip_author_label(self, value):
    text = normalize_line(value)
    text = re.sub(r'^\s*author\s*:?\s*', '', text, flags=re.I)
    text = re.sub(r'^\s*by\s+', '', text, flags=re.I)
    return self.clean_author(text)

  def title_author_from_text(self, value):
    text = strip_publication_notes(normalize_line(value))
    text = re.sub(r'\btranslated\s+by\b.+$', '', text, flags=re.I).strip()
    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', text, re.I)
    if by_match is not None:
      return by_match.group(1), by_match.group(2)
    return '', ''

  def clean_title(self, value):
    text = normalize_line(value)
    text = re.sub(r'\s*\|\s*.*$', '', text)
    return strip_publication_notes(text).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    text = normalize_line(value)
    text = re.sub(r'^\s*author\s*:?\s*', '', text, flags=re.I)
    text = re.sub(r'^\s*by\s+', '', text, flags=re.I)
    text = re.sub(r'\btranslated\s+by\b.+$', '', text, flags=re.I)
    text = re.sub(r'\s*\|\s*.*$', '', text)
    text = re.sub(r'\s*,?\s*(?:winner|shortlisted|shortlist|longlisted|longlist|published|publication)\b.*$', '', text, flags=re.I)
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

  def year_from_url(self, url):
    matches = re.findall(r'(?:/|^)((?:19|20)\d{2})(?:/|$)', url or '')
    return int(matches[-1]) if matches else None

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
        self.build_award_entry(row, row['source_url'], year, row['category'],
                               award=self.award_name)
        for row in award_rows
      ]
      entries.extend(assign_positions(
        award_rows,
        int(year),
        tied_winners_share_position=True))
    return entries


class BookerPrizeWikipediaParser(BookerPrizeOfficialParser):
  """Parse Booker and International Booker Wikipedia result tables."""

  def parse(self, html, base_url, name, category=None, **_kwargs):
    rows = self.parse_wikipedia_rows(html, base_url, category or self.category)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_wikipedia_rows(self, html, base_url, category):
    root = self.html_root(html)
    rows = []
    for table in root.xpath('//table'):
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
      result = self.result_from_cell(
        self.cell_for_key(cells, header_map, 'result', missing_year))
      if result == 'ignored':
        continue
      if result is None:
        row_count = row_count_by_year.get(year, 0)
        result = RESULT_WINNER if row_count == 0 else RESULT_SHORTLISTED
      if result not in (RESULT_WINNER, RESULT_SHORTLISTED):
        continue
      title = self.clean_title(self.clean_cell_text(title_cell))
      author = self.clean_author(self.clean_cell_text(author_cell))
      if not title or not author:
        continue
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
    if not text or text in IGNORED_STAGES:
      return 'ignored'
    if 'longlist' in text or 'longlisted' in text:
      return 'ignored'
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
    text = re.sub(r'\s*\[\s*[a-z0-9]+\s*\]\s*', ' ', text, flags=re.I)
    return normalize_line(text)

  def first_link_url(self, cell, base_url):
    hrefs = cell.xpath('(.//a[@href])[1]/@href')
    return urljoin(base_url, hrefs[0]) if hrefs else ''
