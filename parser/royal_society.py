#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Royal Society Science Book Prize parsers.

Maintenance notes:
- The official archive card list marks recent winners as `Shortlist`; linked
  book detail pages are therefore load-bearing for winner promotion.
- V1 imports the adult Science Book Prize only. The Young People's Book Prize
  uses a different archive shape and should stay out of this parser until it has
  its own source review.
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


AWARD_NAME = 'Royal Society Trivedi Science Book Prize'
CATEGORY = 'Science Book Prize'
RESULT_ORDER = {
  RESULT_WINNER: 0,
  RESULT_SHORTLISTED: 1,
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


class RoyalSocietyScienceBookPrizeParser(AwardParserBase):
  """
  Parse official Royal Society Science Book Prize card and detail pages.

  Invariants:
  - Landing-card rows default to shortlisted.
  - Detail pages, when available, are the only official source for promoting a
    landing row to winner.
  """

  AWARD_NAME = AWARD_NAME

  def parse(self, html, base_url, name, category=CATEGORY, fetch_url=None, **_kwargs):
    notes = []
    rows = self.parse_rows(html, base_url, category, fetch_url, notes)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def parse_rows(self, html, base_url, category, fetch_url, notes):
    rows = []
    for item in self.landing_items(html, base_url):
      row = self.row_from_landing_item(item, category)
      if fetch_url is not None and item.get('source_url'):
        try:
          detail = self.row_from_detail_page(
            fetch_url(item['source_url']),
            item['source_url'],
            category)
        except Exception as err:
          notes.append(
            'Official Royal Society detail page failed for %s: %s' % (
              item['source_url'], str(err) or err.__class__.__name__))
        else:
          if detail is not None:
            row = detail
          else:
            notes.append(
              'Official Royal Society detail page had no usable prize row for %s' %
              item['source_url'])
      if row is not None:
        rows.append(row)
    return rows

  def landing_items(self, html, base_url):
    root = self.html_root(html)
    items = []
    seen = set()
    for link in root.xpath('//a[@href]'):
      url = urljoin(base_url, link.get('href') or '')
      if not self.is_book_detail_url(url):
        continue
      if url in seen:
        continue
      seen.add(url)
      context = self.link_context(link)
      text = self.node_text(context)
      title, author = self.title_author_from_landing(link, context)
      items.append({
        'source_url': url,
        'title': title,
        'author': author,
        'award_year': self.year_from_text(text) or self.year_from_text(url),
        'result': RESULT_SHORTLISTED,
      })
    return items

  def is_book_detail_url(self, url):
    return bool(re.search(
      r'/medals-and-prizes/science-book-prize/books/(?:19|20)\d{2}/[^/]+/?$',
      url or ''))

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

  def title_author_from_landing(self, link, context):
    title = self.title_from_node(link) or self.title_from_node(context)
    author = self.author_from_context(context, title)
    if not title or not author:
      parsed_title, parsed_author = self.title_author_from_text(self.node_text(context))
      title = title or parsed_title
      author = author or parsed_author
    return self.clean_title(title), self.clean_author(author)

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

  def row_from_detail_page(self, html, base_url, category):
    root = self.html_root(html)
    result, year = self.result_year_from_detail(root)
    title, author = self.title_author_from_detail(root)
    if year is None or result is None or not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': self.clean_title(title),
      'author': self.clean_author(author),
      'result': result,
      'source_url': base_url,
      'category': category,
    }

  def result_year_from_detail(self, root):
    for node in root.xpath('//h1|//h2|//h3|//h4|//p|//span|//strong'):
      text = self.node_text(node)
      result = self.result_from_text(text)
      year = self.year_from_text(text)
      if result is not None and year is not None:
        return result, year
    text = self.node_text(root)
    return self.result_from_text(text), self.year_from_text(text)

  def result_from_text(self, value):
    text = normalize_heading(value)
    if 'winner' in text:
      return RESULT_WINNER
    if 'shortlist' in text or 'shortlisted' in text or 'finalist' in text:
      return RESULT_SHORTLISTED
    return None

  def title_author_from_detail(self, root):
    title_nodes = root.xpath('(//main//h1|//h1)[1]')
    title = self.node_text(title_nodes[0]) if title_nodes else ''
    detail_context = self.nearest_detail_context(title_nodes[0]) if title_nodes else root
    author = self.author_from_context(detail_context, title)
    if not author:
      author = self.author_from_context(root, title)
    return title, author

  def nearest_detail_context(self, node):
    for xpath in ('ancestor::header[1]', 'ancestor::section[1]', 'ancestor::main[1]'):
      nodes = node.xpath(xpath)
      if nodes:
        return nodes[0]
    return node.getparent() or node

  def title_from_node(self, node):
    title_nodes = node.xpath(
      '(.//*[self::h1 or self::h2 or self::h3 or self::h4]'
      '|.//*[contains(concat(" ", normalize-space(@class), " "), " title ")])[1]')
    if title_nodes:
      title = self.node_text(title_nodes[0])
      if title:
        return title
    text = self.node_text(node)
    lines = self.visible_lines(node)
    for line in lines or [text]:
      if self.looks_like_ignored_line(line) or self.looks_like_author_line(line):
        continue
      if self.year_from_text(line) is not None or self.result_from_text(line) is not None:
        continue
      return line
    return ''

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
    if title:
      after_title = self.node_text(context).split(title, 1)[-1]
      author = self.author_from_text_after_title(after_title)
      if author:
        return author
    return ''

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

  def looks_like_ignored_line(self, value):
    text = normalize_heading(value)
    return any(fragment in text for fragment in (
      'read more',
      'find out more',
      'shortlist',
      'winner',
      'other shortlisted books',
      'judges',
      'newsletter',
      'book prize',
      'science book prize',
    ))

  def title_author_from_text(self, value):
    text = strip_publication_notes(normalize_line(value))
    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', text, re.I)
    if by_match is not None:
      return by_match.group(1), by_match.group(2)
    author_match = re.match(r'^(.+?)\s+author\s*:?\s+(.+)$', text, re.I)
    if author_match is not None:
      return author_match.group(1), author_match.group(2)
    return '', ''

  def author_from_text_after_title(self, value):
    text = normalize_line(value).strip(' ,:-|')
    match = re.match(r'^(?:author\s*:?\s*|by\s+)(.+?)(?:\s+(?:winner|shortlist|book prize)\b|$)', text, re.I)
    return self.clean_author(match.group(1)) if match is not None else ''

  def clean_title(self, value):
    text = normalize_line(value)
    text = re.sub(r'\s*\|\s*.*$', '', text)
    return strip_publication_notes(text).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    text = normalize_line(value)
    text = re.sub(r'^\s*author\s*:?\s*', '', text, flags=re.I)
    text = re.sub(r'^\s*by\s+', '', text, flags=re.I)
    text = re.sub(r'\s*\|\s*.*$', '', text)
    text = re.sub(r'\s*,?\s*(?:winner|shortlisted|shortlist|published|publication)\b.*$', '', text, flags=re.I)
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
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in award_rows
      ]
      entries.extend(assign_positions(
        award_rows,
        int(year),
        tied_winners_share_position=True))
    return entries


class RoyalSocietyScienceBookPrizeWikipediaParser(
    RoyalSocietyScienceBookPrizeParser):
  """Parse Royal Society Science Book Prize Wikipedia history tables."""

  def parse(self, html, base_url, name, category=CATEGORY, **_kwargs):
    rows = self.parse_wikipedia_rows(html, base_url, category)
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
      if not self.has_required_columns(header_map):
        continue
      rows.extend(self.rows_from_table(table, header_map, base_url, category))
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

  def rows_from_table(self, table, header_map, base_url, category):
    rows = []
    current_year = None
    current_result_by_year = {}
    header_seen = False
    for tr in table.xpath('.//tr'):
      cells = tr.xpath('./td|./th')
      if not cells:
        continue
      if not header_seen and self.row_matches_header(cells, header_map):
        header_seen = True
        continue
      if all(index < len(cells) and cells[index].tag == 'th'
             for index in header_map.values()):
        continue
      missing_year_cell = self.row_omits_year(cells, header_map, current_year)
      year_cell = self.cell_for_key(cells, header_map, 'year', missing_year_cell)
      year = self.year_from_text(self.clean_cell_text(year_cell)) or current_year
      if year is None:
        continue
      current_year = year
      title_cell = self.cell_for_key(cells, header_map, 'title', missing_year_cell)
      author_cell = self.cell_for_key(cells, header_map, 'author', missing_year_cell)
      if title_cell is None or author_cell is None:
        continue
      result = self.result_from_cell(
        self.cell_for_key(cells, header_map, 'result', missing_year_cell))
      if result is None:
        result = (
          RESULT_SHORTLISTED
          if current_result_by_year.get(year) == RESULT_SHORTLISTED else None)
      if result not in (RESULT_WINNER, RESULT_SHORTLISTED):
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
    return self.year_from_text(self.clean_cell_text(cells[0])) is None

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
    if cell is None:
      return ''
    text = normalize_line(' '.join(
      text.strip()
      for text in cell.xpath(
        './/text()[not(ancestor::sup or ancestor::script or ancestor::style)]')
      if text.strip()))
    text = re.sub(r'\s*\[\s*\d+\s*\]\s*', ' ', text)
    return normalize_line(text)

  def first_link_url(self, cell, base_url):
    hrefs = cell.xpath('(.//a[@href])[1]/@href')
    return urljoin(base_url, hrefs[0]) if hrefs else ''
