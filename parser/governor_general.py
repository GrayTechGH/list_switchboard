#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Governor General's Literary Awards official JSON parser.

Maintenance notes:
- GGBooks renders the visible archive from a versioned static JSON file named
  by the archive component JavaScript. The HTML page itself is only the shell.
- V1 recipes cover fiction, nonfiction, and young people's literature book
  categories; translation, poetry, and drama remain out of scope.
"""

import json
import re

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


AWARD_NAME = "Governor General's Literary Award"
RESULT_ORDER = {
  RESULT_WINNER: 0,
  RESULT_SHORTLISTED: 1,
}
SUPPLEMENT_RESULT_ALIASES = {
  'winner': RESULT_WINNER,
  'won': RESULT_WINNER,
  'shortlist': RESULT_SHORTLISTED,
  'shortlisted': RESULT_SHORTLISTED,
  'finalist': RESULT_SHORTLISTED,
  'finalists': RESULT_SHORTLISTED,
  'nominee': RESULT_SHORTLISTED,
  'nominees': RESULT_SHORTLISTED,
}
HEADER_ALIASES = {
  'author': 'author',
  'authors': 'author',
  'category': 'category',
  'recipient': 'author',
  'recipients': 'author',
  'writer': 'author',
  'title': 'title',
  'book': 'title',
  'work': 'title',
  'winner': 'winner',
  'won': 'winner',
  'nominated': 'nominated',
  'nominees': 'nominated',
  'shortlist': 'nominated',
  'shortlisted': 'nominated',
  'finalists': 'nominated',
  'result': 'result',
  'status': 'result',
  'outcome': 'result',
}
LOCATION_HINTS = {
  'alberta', 'british columbia', 'manitoba', 'new brunswick',
  'newfoundland', 'northwest territories', 'nova scotia', 'nunavut',
  'ontario', 'prince edward island', 'quebec', 'québec', 'saskatchewan',
  'yukon', 'canada', 'united states',
}


class GovernorGeneralAwardsParser(AwardParserBase):
  """
  Parse the official GGBooks archive JSON for one configured recipe.

  Invariants:
  - Category selection uses official JSON category keys, not display labels.
  - Language selection is explicit because the same category key can contain
    English and French records after 1959.
  """

  AWARD_NAME = AWARD_NAME

  def __init__(
      self, category, category_keys, language='en', award_name=AWARD_NAME,
      *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.award_name = award_name
    self.category = category
    self.category_keys = tuple(category_keys)
    self.language = language

  def parse(self, data, base_url, name, category=None, **_kwargs):
    rows = self.parse_rows(data, base_url, category or self.category)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, data, base_url, category):
    payload = self.load_payload(data)
    rows = []
    for year in sorted(payload, key=lambda value: int(value)):
      year_data = payload.get(year) or {}
      for category_key in self.category_keys:
        category_data = year_data.get(category_key) or {}
        language_data = category_data.get(self.language) or {}
        for item in language_data.get('finalists') or ():
          title = self.clean_title(item.get('title', ''))
          author = self.clean_author(item.get('author', ''))
          if not title or not author:
            continue
          rows.append({
            'award_year': str(year),
            'title': title,
            'author': author,
            'result': RESULT_WINNER if item.get('winner') is True else RESULT_SHORTLISTED,
            'source_url': base_url,
            'category': category,
          })
    return rows

  def load_payload(self, data):
    if isinstance(data, bytes):
      data = data.decode('utf-8-sig')
    if isinstance(data, str):
      return json.loads(data or '{}')
    return data or {}

  def clean_title(self, value):
    text = normalize_line(value)
    return strip_publication_notes(text).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    text = normalize_line(value)
    while self.has_location_suffix(text):
      text = text[:text.rfind(' (')].strip()
    return strip_publication_notes(text).strip(' "\u201c\u201d,')

  def has_location_suffix(self, value):
    start = value.rfind(' (')
    if start < 0 or not value.endswith(')'):
      return False
    suffix = normalize_heading(value[start + 2:-1])
    return any(hint in suffix for hint in LOCATION_HINTS) or ' both' in suffix

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


class GovernorGeneralSupplementParser(GovernorGeneralAwardsParser):
  """Parse a bounded annual Wikipedia/current-year supplement."""

  def parse(self, html, base_url, name, category=None, year='2025',
            winner_html='', **_kwargs):
    rows = self.parse_wikipedia_rows(
      html, base_url, category or self.category, str(year))
    winner_titles = self.winner_titles_from_press(winner_html)
    if winner_titles:
      for row in rows:
        if normalize_heading(row['title']) in winner_titles:
          row['result'] = RESULT_WINNER
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_wikipedia_rows(self, html, base_url, category, year):
    root = self.html_root(html)
    rows = self.rows_from_annual_language_tables(root, base_url, category, year)
    for heading, table in self.category_tables(root, category):
      header_map = self.header_map(table)
      if not self.has_required_columns(header_map):
        continue
      rows.extend(self.rows_from_table(table, header_map, base_url, category, year))
    return rows

  def rows_from_annual_language_tables(self, root, base_url, category, year):
    rows = []
    for table in self.language_tables(root):
      header_map = self.header_map(table)
      if not self.has_annual_columns(header_map):
        continue
      for tr in table.xpath('.//tr'):
        cells = tr.xpath('./td|./th')
        if not cells or self.row_matches_header(cells, header_map):
          continue
        category_cell = self.cell_for_key(cells, header_map, 'category')
        if category_cell is None or not self.matches_supplement_category(
            self.clean_cell_text(category_cell), category):
          continue
        rows.extend(self.rows_from_candidate_cell(
          self.cell_for_key(cells, header_map, 'winner'),
          base_url,
          category,
          year,
          RESULT_WINNER))
        rows.extend(self.rows_from_candidate_cell(
          self.cell_for_key(cells, header_map, 'nominated'),
          base_url,
          category,
          year,
          RESULT_SHORTLISTED))
    return rows

  def language_tables(self, root):
    language_heading = 'french' if self.language == 'fr' else 'english'
    for heading in root.xpath('//h2|//h3'):
      if normalize_heading(self.node_text(heading)) != language_heading:
        continue
      for table in heading.xpath('following::table[1]'):
        yield table

  def matches_supplement_category(self, label, category):
    text = normalize_heading(label)
    target = normalize_heading(category)
    aliases = {target}
    if 'illustrated' in target or 'illustration' in target:
      aliases.update((
        'children s illustration',
        'childrens illustration',
        'children s illustrated books',
        'childrens illustrated books',
      ))
    elif 'young people' in target and 'text' in target:
      aliases.update((
        'children s literature',
        'childrens literature',
        'children s writing',
        'childrens writing',
      ))
    return text in aliases or any(alias in text for alias in aliases)

  def rows_from_candidate_cell(self, cell, base_url, category, year, result):
    if cell is None:
      return []
    rows = []
    for text in self.cell_candidate_lines(cell):
      author, title = self.split_candidate_text(text)
      title = self.clean_title(title)
      author = self.clean_author(author)
      if not title or not author:
        continue
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': base_url,
        'category': category,
      })
    return rows

  def split_candidate_text(self, text):
    text = normalize_line(text)
    if ',' not in text:
      return '', text
    author, title = text.split(',', 1)
    return author, title

  def cell_candidate_lines(self, cell):
    lines = []
    current = []

    def add_text(text):
      text = normalize_line(text or '')
      if text:
        current.append(text)

    def flush():
      text = normalize_line(' '.join(current))
      if text:
        lines.append(text)
      current[:] = []

    def visit(node):
      add_text(node.text)
      for child in node:
        if child.tag.lower() == 'br':
          flush()
        else:
          visit(child)
        add_text(child.tail)

    visit(cell)
    flush()
    return lines

  def category_tables(self, root, category):
    target = normalize_heading(category)
    for heading in root.xpath('//h2|//h3|//h4'):
      text = normalize_heading(self.node_text(heading))
      if target not in text and text not in target:
        continue
      for table in heading.xpath('following::table[1]'):
        yield heading, table

  def rows_from_table(self, table, header_map, base_url, category, year):
    rows = []
    row_count = 0
    for tr in table.xpath('.//tr'):
      cells = tr.xpath('./td|./th')
      if not cells or self.row_matches_header(cells, header_map):
        continue
      title_cell = self.cell_for_key(cells, header_map, 'title')
      author_cell = self.cell_for_key(cells, header_map, 'author')
      if title_cell is None or author_cell is None:
        continue
      title = self.clean_title(self.clean_cell_text(title_cell))
      author = self.clean_author(self.clean_cell_text(author_cell))
      if not title or not author:
        continue
      result = self.result_from_cell(self.cell_for_key(cells, header_map, 'result'))
      if result is None:
        result = RESULT_WINNER if row_count == 0 else RESULT_SHORTLISTED
      row_count += 1
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': self.first_link_url(title_cell, base_url) or base_url,
        'category': category,
      })
    return rows

  def winner_titles_from_press(self, html):
    if not html:
      return set()
    text = normalize_heading(self.node_text(self.html_root(html)))
    titles = set()
    for category_key in (normalize_heading(self.category),):
      pattern = r'%s.{0,240}?winner.{0,80}?([a-z0-9][a-z0-9 ]+)' % re.escape(category_key)
      match = re.search(pattern, text)
      if match is not None:
        titles.add(normalize_heading(match.group(1)))
    return titles

  def header_map(self, table):
    for tr in table.xpath('.//tr'):
      mapped = {}
      for index, cell in enumerate(tr.xpath('./th|./td')):
        key = HEADER_ALIASES.get(normalize_heading(self.clean_cell_text(cell)))
        if key is not None and key not in mapped:
          mapped[key] = index
      if self.has_required_columns(mapped) or self.has_annual_columns(mapped):
        return mapped
    return {}

  def has_required_columns(self, header_map):
    return all(key in header_map for key in ('title', 'author'))

  def has_annual_columns(self, header_map):
    return all(key in header_map for key in ('category', 'winner', 'nominated'))

  def row_matches_header(self, cells, header_map):
    for key, index in header_map.items():
      if index >= len(cells):
        return False
      if HEADER_ALIASES.get(normalize_heading(self.clean_cell_text(cells[index]))) != key:
        return False
    return True

  def cell_for_key(self, cells, header_map, key):
    index = header_map.get(key)
    if index is None or index >= len(cells):
      return None
    return cells[index]

  def result_from_cell(self, cell):
    if cell is None:
      return None
    text = normalize_heading(self.clean_cell_text(cell))
    if not text:
      return None
    if text in SUPPLEMENT_RESULT_ALIASES:
      return SUPPLEMENT_RESULT_ALIASES[text]
    for alias, result in SUPPLEMENT_RESULT_ALIASES.items():
      if text.startswith(alias + ' '):
        return result
    return None

  def clean_cell_text(self, cell):
    text = normalize_line(' '.join(
      text.strip()
      for text in cell.xpath(
        './/text()[not(ancestor::sup or ancestor::style or ancestor::script)]')
      if text.strip()))
    text = re.sub(r'\s*\[\s*\d+\s*\]\s*', ' ', text)
    return normalize_line(text)

  def first_link_url(self, cell, base_url):
    hrefs = cell.xpath('(.//a[@href])[1]/@href')
    if not hrefs:
      return ''
    from urllib.parse import urljoin
    return urljoin(base_url, hrefs[0])

  def html_root(self, html):
    return lxml_html.fromstring(html or '<html></html>')

  def node_text(self, node):
    if node is None:
      return ''
    return normalize_line(' '.join(
      text.strip()
      for text in node.xpath('.//text()[not(ancestor::script or ancestor::style)]')
      if text.strip()))
