#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Women's Prize official-site and Wikipedia fallback parsers.

Maintenance notes:
- The fiction and nonfiction prizes share official page structure and cross-link
  one another. Detail-page result text must match the configured prize label so
  sibling-prize books do not leak into the wrong recipe.
- V1 imports winners and shortlists only. Longlists remain out of scope even
  when official landing pages expose them.
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
HEADER_ALIASES = {
  'year': 'year',
  'award year': 'year',
  'author': 'author',
  'authors': 'author',
  'writer': 'author',
  'writers': 'author',
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
  'short list': RESULT_SHORTLISTED,
  'finalist': RESULT_SHORTLISTED,
  'finalists': RESULT_SHORTLISTED,
}


class WomensPrizeOfficialParser(AwardParserBase):
  """
  Parse Women's Prize landing pages and linked official library detail pages.

  Invariants:
  - Detail rows are accepted only when result text names the configured prize.
  - Longlist cards are ignored for the V1 winner/shortlist recipe scope.
  """

  def __init__(self, award_name, category, prize_aliases=(), *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.AWARD_NAME = award_name
    self.award_name = award_name
    self.category = category
    self.prize_aliases = tuple(prize_aliases or (award_name,))

  def parse(self, html, base_url, name, category=None, fetch_url=None, **_kwargs):
    notes = []
    rows = self.parse_rows(
      html,
      base_url,
      category or self.category,
      fetch_url,
      notes)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def parse_rows(self, html, base_url, category, fetch_url, notes):
    rows = []
    for item in self.landing_items(html, base_url):
      if fetch_url is not None and item['source_url']:
        try:
          detail = self.row_from_detail_page(
            fetch_url(item['source_url']),
            item['source_url'],
            category)
        except Exception as err:
          notes.append(
            'Official Women\'s Prize detail page failed for %s: %s' % (
              item['source_url'], str(err) or err.__class__.__name__))
        else:
          if detail is not None:
            rows.append(detail)
          continue
      row = self.row_from_landing_item(item, category)
      if row is not None:
        rows.append(row)
    return rows

  def landing_items(self, html, base_url):
    root = self.html_root(html)
    items = []
    seen = set()
    for link in root.xpath('//a[@href]'):
      url = urljoin(base_url, link.get('href') or '')
      if '/library/' not in url:
        continue
      if url in seen:
        continue
      seen.add(url)
      context = self.link_context(link)
      stage_text = self.node_text(context)
      heading = self.nearest_stage_heading(context)
      if heading is not None:
        stage_text = self.node_text(heading) + ' ' + stage_text
      result = self.result_from_text(stage_text)
      if result is None:
        continue
      title, author = self.title_author_from_landing(link)
      items.append({
        'source_url': url,
        'title': title,
        'author': author,
        'result': result,
        'award_year': self.year_from_text(stage_text),
      })
    return items

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

  def nearest_stage_heading(self, node):
    current = node
    while current is not None:
      for sibling in current.itersiblings(preceding=True):
        if (
            sibling.tag in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
            and self.result_from_text(self.node_text(sibling)) is not None):
          return sibling
      current = current.getparent()
    return None

  def title_author_from_landing(self, link):
    title = ''
    author = ''
    title_nodes = link.xpath(
      '(.//*[self::h1 or self::h2 or self::h3 or self::h4]'
      '|.//*[contains(concat(" ", normalize-space(@class), " "), " title ")])[1]')
    if title_nodes:
      title = self.clean_title(self.node_text(title_nodes[0]))
    if not title:
      title = self.clean_title(self.node_text(link))
    author_nodes = link.xpath(
      '(.//*[contains(concat(" ", normalize-space(@class), " "), " author ")]'
      '|.//p[contains(translate(normalize-space(.), "BY", "by"), "by ")])[1]')
    if author_nodes:
      author = self.clean_author(self.node_text(author_nodes[0]))
    if not author:
      title, author = self.title_author_from_text(self.node_text(link))
    return title, author

  def row_from_detail_page(self, html, base_url, category):
    root = self.html_root(html)
    text = self.node_text(root)
    if not self.names_configured_prize(text):
      return None
    result = self.result_from_text(text)
    year = self.year_from_result_text(text) or self.year_from_text(text)
    title, author = self.title_author_from_detail(root)
    if year is None or result is None or not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': base_url,
      'category': category,
    }

  def row_from_landing_item(self, item, category):
    if not item.get('title') or not item.get('author') or not item.get('award_year'):
      return None
    return {
      'award_year': str(item['award_year']),
      'title': item['title'],
      'author': item['author'],
      'result': item['result'],
      'source_url': item['source_url'],
      'category': category,
    }

  def title_author_from_detail(self, root):
    title = ''
    author = ''
    title_nodes = root.xpath('(//main//h1|//h1)[1]')
    if title_nodes:
      title = self.clean_title(self.node_text(title_nodes[0]))
    header = self.nearest_header(title_nodes[0]) if title_nodes else root
    author_nodes = header.xpath(
      './/*[contains(concat(" ", normalize-space(@class), " "), " author ")]'
      '|.//p[starts-with(translate(normalize-space(.), "BY", "by"), "by ")]'
      '|.//*[starts-with(translate(normalize-space(.), "BY", "by"), "by ")]')
    for node in author_nodes:
      author = self.clean_author(self.node_text(node))
      if author:
        break
    if not author and title:
      after_title = self.node_text(root).split(title, 1)[-1]
      author = self.author_from_text_after_title(after_title)
    return title, author

  def nearest_header(self, node):
    for xpath in ('ancestor::header[1]', 'ancestor::section[1]', 'ancestor::main[1]'):
      nodes = node.xpath(xpath)
      if nodes:
        return nodes[0]
    return node.getparent() or node

  def names_configured_prize(self, value):
    text = normalize_heading(value)
    return any(normalize_heading(alias) in text for alias in self.prize_aliases)

  def result_from_text(self, value):
    text = normalize_heading(value)
    if 'longlist' in text or 'longlisted' in text:
      return None
    if 'winner' in text or 'won ' in text:
      return RESULT_WINNER
    if 'shortlist' in text or 'shortlisted' in text:
      return RESULT_SHORTLISTED
    return None

  def year_from_result_text(self, value):
    aliases = '|'.join(re.escape(normalize_heading(alias)) for alias in self.prize_aliases)
    text = normalize_heading(value)
    match = re.search(
      r'(?:winner|shortlisted|shortlist).{0,80}?((?:19|20)\d{2}).{0,80}?(?:%s)' % aliases,
      text)
    if match is None:
      match = re.search(
        r'((?:19|20)\d{2}).{0,80}?(?:%s).{0,80}?(?:winner|shortlisted|shortlist)' % aliases,
        text)
    return int(match.group(1)) if match is not None else None

  def title_author_from_text(self, value):
    text = strip_publication_notes(normalize_line(value))
    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', text, re.I)
    if by_match is not None:
      return self.clean_title(by_match.group(1)), self.clean_author(by_match.group(2))
    for separator in (' | ', ' - ', ' \u2013 ', ' \u2014 '):
      if separator in text:
        title, author = text.split(separator, 1)
        return self.clean_title(title), self.clean_author(author)
    return '', ''

  def author_from_text_after_title(self, value):
    text = normalize_line(value).strip(' ,:-\u2013\u2014|')
    match = re.match(r'^(?:by\s+)?([^|.]+)', text, re.I)
    return self.clean_author(match.group(1)) if match is not None else ''

  def clean_title(self, value):
    text = normalize_line(value)
    text = re.sub(r'\s*\|\s*.*$', '', text)
    return strip_publication_notes(text).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    text = normalize_line(value)
    text = re.sub(r'^\s*by\s+', '', text, flags=re.I)
    text = re.sub(r'\s*\|\s*.*$', '', text)
    text = re.sub(r'\s*,?\s*(?:published|publication|winner|shortlisted|shortlist)\b.*$', '', text, flags=re.I)
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


class WomensPrizeWikipediaParser(WomensPrizeOfficialParser):
  """Parse Women's Prize Wikipedia winner/shortlist tables."""

  def parse(self, html, base_url, name, category=None, category_aliases=(), **_kwargs):
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
      title = self.clean_title(self.clean_cell_text(title_cell))
      author = self.clean_author(self.clean_cell_text(author_cell))
      if not title or not author:
        continue
      result = self.result_from_wikipedia_cell(
        self.cell_for_key(cells, header_map, 'result', missing_year))
      if result is None:
        row_count = row_count_by_year.get(year, 0)
        result = RESULT_WINNER if row_count == 0 else RESULT_SHORTLISTED
      if result not in (RESULT_WINNER, RESULT_SHORTLISTED):
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

  def result_from_wikipedia_cell(self, cell):
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
    text = re.sub(r'\s*\[\s*[a-z0-9]+\s*\]\s*', ' ', text, flags=re.I)
    return normalize_line(text)

  def first_link_url(self, cell, base_url):
    hrefs = cell.xpath('(.//a[@href])[1]/@href')
    return urljoin(base_url, hrefs[0]) if hrefs else ''
