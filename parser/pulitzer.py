#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Pulitzer Prize official category-page parser.

Maintenance notes:
- Pulitzer category pages expose year sections with winner headings followed
  by a `Finalists:` marker and finalist work links.
- The rendered page can duplicate finalist links, so dedupe is load-bearing.
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


AWARD_NAME = 'Pulitzer Prize'


class PulitzerAwardParser(AwardParserBase):
  """
  Parse official Pulitzer category pages into award import entries.

  Invariants:
  - Work rows must include an isolated `Title, by Author` text fragment.
  - `No award` winner headings are skipped, but later finalists for that year
    are retained.
  """

  AWARD_NAME = AWARD_NAME

  def parse(self, html, base_url, name, category, category_aliases=()):
    root = self.html_root(html)
    if self.is_challenge_page(root):
      raise ValueError('Pulitzer page returned a Cloudflare challenge')
    rows = self.parse_rows_from_root(root, base_url, category)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url, category):
    return self.parse_rows_from_root(self.html_root(html), base_url, category)

  def parse_rows_from_root(self, root, base_url, category):
    rows = []
    current_year = None
    current_result = RESULT_WINNER
    for token in self.tokens(root, base_url):
      year = self.year_from_text(token['text'])
      if year is not None:
        current_year = year
        current_result = RESULT_WINNER
        continue
      if self.is_finalists_label(token['text']):
        current_result = RESULT_NOMINEE
        continue
      if current_year is None or self.is_no_award(token['text']):
        continue
      if not self.is_work_token(token, current_result):
        continue
      title, author = self.title_author_from_text(token['text'])
      if not title or not author:
        continue
      rows.append({
        'award_year': str(current_year),
        'title': title,
        'author': author,
        'result': current_result,
        'source_url': token.get('href') or base_url,
        'category': category,
      })
    return rows

  def tokens(self, root, base_url):
    tokens = []
    for node in root.xpath(
        '//body//*[not(ancestor::script or ancestor::style)]'):
      tag = (node.tag or '').lower()
      text = self.node_text(node)
      if not text:
        continue
      if tag in {'h2', 'h3', 'h4'}:
        tokens.append({'kind': 'heading', 'text': text, 'href': self.first_link_url(node, base_url)})
      elif tag == 'a' and not node.xpath('ancestor::h2|ancestor::h3|ancestor::h4'):
        tokens.append({'kind': 'link', 'text': text, 'href': self.node_href(node, base_url)})
      elif tag not in {'a'} and not node.xpath('./*'):
        tokens.append({'kind': 'text', 'text': text, 'href': ''})
    return tokens

  def is_work_token(self, token, result):
    if self.title_author_from_text(token['text']) == ('', ''):
      return False
    if token['kind'] == 'heading':
      return True
    if token['kind'] == 'link':
      return result == RESULT_NOMINEE
    return False

  def title_author_from_text(self, value):
    text = normalize_line(value)
    match = re.match(r'^(.+?)\s*,?\s+by\s+(.+)$', text, re.I)
    if match is None:
      return '', ''
    title = self.clean_title(match.group(1))
    author = self.clean_author(match.group(2))
    return title, author

  def clean_title(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def year_from_text(self, value):
    text = normalize_line(value)
    return int(text) if re.match(r'^(19|20)\d{2}$', text) else None

  def is_finalists_label(self, value):
    return normalize_heading(value).rstrip(':') == 'finalists'

  def is_no_award(self, value):
    return normalize_heading(value) == 'no award'

  def html_root(self, html):
    return lxml_html.fromstring(html or '<html></html>')

  def is_challenge_page(self, root):
    title = normalize_heading(' '.join(root.xpath('//title/text()')))
    text = normalize_heading(self.node_text(root))
    return title == 'just a moment' and 'cloudflare' in text

  def node_text(self, node):
    return normalize_line(' '.join(
      text.strip()
      for text in node.xpath('.//text()[not(ancestor::script or ancestor::style)]')
      if text.strip()))

  def node_href(self, node, base_url):
    href = node.get('href')
    return urljoin(base_url, href) if href else ''

  def first_link_url(self, node, base_url):
    hrefs = node.xpath('(.//a[@href])[1]/@href')
    return urljoin(base_url, hrefs[0]) if hrefs else ''

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


def parse_pulitzer_award(html, base_url, name, category, category_aliases=()):
  return PulitzerAwardParser().parse(
    html, base_url, name, category, category_aliases)


class PulitzerWikipediaParser(AwardParserBase):
  """
  Parse Pulitzer category-specific Wikipedia recipient tables.

  Invariants:
  - Wikipedia lists winners first and finalists afterward, without a result
    column.
  - Known tied-winner years must be configured by the fetcher because the table
    shape alone cannot always distinguish the second winner from a finalist.
  """

  AWARD_NAME = AWARD_NAME

  HEADER_ALIASES = {
    'year': 'year',
    'author': 'author',
    'authors': 'author',
    'author s': 'author',
    'work': 'title',
    'book': 'title',
    'title': 'title',
  }

  def parse(
      self, html, base_url, name, category, category_aliases=(),
      tied_winner_years=()):
    rows = self.parse_rows(html, base_url, category, tied_winner_years)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url, category, tied_winner_years=()):
    root = self.html_root(html)
    tied_winner_counts = {
      int(year): count
      for year, count in dict(tied_winner_years or {}).items()
    }
    for table in root.xpath('//table'):
      header_map = self.header_map(table)
      if self.has_required_columns(header_map):
        return self.rows_from_table(
          table, header_map, base_url, category, tied_winner_counts)
    return []

  def rows_from_table(
      self, table, header_map, base_url, category, tied_winner_counts):
    rows = []
    current_year = None
    row_count_by_year = {}
    no_award_years = set()
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
      if title_cell is None:
        continue
      if self.is_no_award(self.clean_cell_text(title_cell)):
        no_award_years.add(year)
        continue
      if author_cell is None:
        continue

      title = self.clean_title(self.clean_cell_text(title_cell))
      author = self.clean_author(self.clean_cell_text(author_cell))
      if not title or not author:
        continue

      year_row_count = row_count_by_year.get(year, 0)
      winner_count = tied_winner_counts.get(year, 1)
      result = (
        RESULT_NOMINEE
        if year in no_award_years or year_row_count >= winner_count
        else RESULT_WINNER
      )
      row_count_by_year[year] = year_row_count + 1
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

  def clean_cell_text(self, cell):
    if cell is None:
      return ''
    text = normalize_line(' '.join(
      text.strip()
      for text in cell.xpath(
        './/text()[not(ancestor::sup or ancestor::style or ancestor::script)]')
      if text.strip()))
    text = re.sub(r'\s*\[\s*[a-z0-9]+\s*\]\s*', ' ', text, flags=re.I)
    text = re.sub(r'\s*\(\s*posthumously\s*\)\s*', ' ', text, flags=re.I)
    return normalize_line(text)

  def clean_title(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def year_from_text(self, value):
    match = re.search(r'(19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def is_no_award(self, value):
    text = normalize_heading(value)
    return text.startswith('not awarded') or text.startswith('no award')

  def html_root(self, html):
    return lxml_html.fromstring(html or '<html></html>')

  def first_link_url(self, cell, base_url):
    hrefs = cell.xpath('(.//a[@href])[1]/@href')
    return urljoin(base_url, hrefs[0]) if hrefs else ''

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


class PulitzerBritannicaParser(AwardParserBase):
  """
  Parse Britannica Pulitzer winner tables as a final winner-only fallback.
  """

  AWARD_NAME = AWARD_NAME

  HEADER_ALIASES = {
    'year': 'year',
    'title': 'title',
    'work': 'title',
    'book': 'title',
    'author': 'author',
    'authors': 'author',
  }

  def parse(
      self, html, base_url, name, category, category_aliases=(),
      table_heading=''):
    rows = self.parse_rows(html, base_url, category, table_heading)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=['Britannica fallback is winner-only; finalists are not available.'])

  def parse_rows(self, html, base_url, category, table_heading=''):
    root = self.html_root(html)
    for table in self.candidate_tables(root, table_heading):
      header_map = self.header_map(table)
      if self.has_required_columns(header_map):
        rows = self.rows_from_table(table, header_map, base_url, category)
        if rows:
          return rows
    return []

  def candidate_tables(self, root, table_heading):
    if not table_heading:
      return root.xpath('//table')
    accepted = normalize_heading(table_heading)
    matches = []
    for table in root.xpath('//table'):
      context = normalize_heading(' '.join(
        self.node_text(node)
        for node in table.xpath(
          '(preceding::h1|preceding::h2|preceding::h3|preceding::h4|.//caption)[position() > last() - 4]')))
      if accepted in context:
        matches.append(table)
    return matches or root.xpath('//table')

  def rows_from_table(self, table, header_map, base_url, category):
    rows = []
    current_year = None
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
      title_text = self.clean_cell_text(title_cell)
      if normalize_heading(title_text).startswith('no award'):
        continue
      title = self.clean_title(title_text)
      author = self.clean_author(self.clean_cell_text(author_cell))
      if not title or not author:
        continue
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': RESULT_WINNER,
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

  def clean_cell_text(self, cell):
    if cell is None:
      return ''
    text = normalize_line(' '.join(
      text.strip()
      for text in cell.xpath(
        './/text()[not(ancestor::sup or ancestor::style or ancestor::script)]')
      if text.strip()))
    text = re.sub(r'\*+', '', text)
    return normalize_line(text)

  def clean_title(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def year_from_text(self, value):
    match = re.search(r'(19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def html_root(self, html):
    return lxml_html.fromstring(html or '<html></html>')

  def node_text(self, node):
    return normalize_line(' '.join(
      text.strip()
      for text in node.xpath('.//text()[not(ancestor::style or ancestor::script)]')
      if text.strip()))

  def first_link_url(self, cell, base_url):
    hrefs = cell.xpath('(.//a[@href])[1]/@href')
    return urljoin(base_url, hrefs[0]) if hrefs else ''

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
      entries.extend(assign_positions(
        award_rows,
        int(year),
        tied_winners_share_position=True))
    return entries
