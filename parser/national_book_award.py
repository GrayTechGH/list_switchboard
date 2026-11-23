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
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import UnicodeDammit
from lxml import html as lxml_html

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, RESULT_NOMINEE, RESULT_WINNER, assign_positions,
    is_author_suffix, normalize_heading, normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_NOMINEE, RESULT_WINNER, assign_positions,
    is_author_suffix, normalize_heading, normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key


AWARD_NAME = 'National Book Award'
PLACEHOLDER_TITLES = {
  'finalists not announced',
  'winner not announced',
  'winners not announced',
}
SHARED_SURNAME_CREDITS = {
  normalize_heading(credit): authors for credit, authors in (
    ('Vera and Bill Cleaver', ('Vera Cleaver', 'Bill Cleaver')),
    ("Ingri and Edgar Parin d'Aulaire", ("Ingri d'Aulaire", "Edgar Parin d'Aulaire")),
    ('Alice and Martin Provensen', ('Alice Provensen', 'Martin Provensen')),
  )
}


def clean_author_credit(value):
  """Normalize this source's comma/and credits without splitting name suffixes."""
  text = re.sub(r'^\s*by\s+', '', normalize_line(value), flags=re.I)
  text = strip_publication_notes(text).strip(' "\u201c\u201d,')
  authors = []
  for credit in re.split(r'\s+with\s+|\s+&\s+|\s*,\s*(?:and\s+)?', text, flags=re.I):
    credit = strip_publication_notes(credit.strip())
    # These verified joint credits abbreviate a surname; arbitrary names must
    # not acquire an inferred surname just because they contain "and".
    parts = SHARED_SURNAME_CREDITS.get(normalize_heading(credit))
    if parts is None:
      parts = re.split(r'\s+and\s+', credit, flags=re.I)
    for part in parts:
      part = part.strip()
      if not part:
        continue
      if is_author_suffix(part) and authors:
        authors[-1] += ', ' + part
      elif part not in authors:
        authors.append(part)
  return ' & '.join(authors)


class NationalBookAwardParser(AwardParserBase):
  """
  Parse official National Book Foundation annual category pages.

  Invariants:
  - Winner rows come from `.winner-book`; finalist rows come from
    `.finalists-wrapper`.
  - Longlist rows are ignored even when present on recent archive pages.
  """

  AWARD_NAME = AWARD_NAME

  def parse(self, html, base_url, name, category, category_aliases=(), fetch_url=None):
    rows = self.parse_rows(html, base_url, category, fetch_url=fetch_url)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url, category, fetch_url=None):
    root = self.html_root(html)
    self.validate_category(root, category, base_url)
    year = self.year_from_url(base_url) or self.year_from_text(self.node_text(root))
    if year is None:
      return []
    for title in root.xpath('//title'):
      declared = re.search(r'National Book Awards ((?:19|20)\d{2})', self.node_text(title), re.I)
      if declared and int(declared.group(1)) != year:
        raise ValueError('Foundation annual page identifies another award year.')
    rows = []
    rows.extend(self.rows_from_nodes(
      root.xpath(
        '//div[contains(concat(" ", normalize-space(@class), " "), " winner-book ")]'
        '//*[contains(concat(" ", normalize-space(@class), " "), " winner-book-item ")]'),
      base_url,
      year,
      category,
      RESULT_WINNER, fetch_url))
    rows.extend(self.rows_from_nodes(
      root.xpath(
        '//div[contains(concat(" ", normalize-space(@class), " "), " finalists-wrapper ")]'
        '//figure[contains(concat(" ", normalize-space(@class), " "), " winner-list ")]'),
      base_url,
      year,
      category,
      RESULT_NOMINEE, fetch_url))
    return rows

  def validate_category(self, root, category, base_url=''):
    selected = root.xpath(
      '//a[contains(concat(" ", normalize-space(@class), " "), " sub-category-winners ")'
      ' and contains(concat(" ", normalize-space(@class), " "), " is-active ")]') or root.xpath(
      '//a[contains(concat(" ", normalize-space(@class), " "), " category-winner ")'
      ' and contains(concat(" ", normalize-space(@class), " "), " is-active ")]')
    if not selected:
      return
    query = parse_qs(urlsplit(base_url).query)
    if 'sub-cat' in query:
      parent = root.xpath(
        '//a[contains(concat(" ", normalize-space(@class), " "), " category-winner ")'
        ' and contains(concat(" ", normalize-space(@class), " "), " is-active ")]')
      if not parent or parse_qs(urlsplit(parent[0].get('href') or '').query).get('cat') != query.get('cat'):
        raise ValueError('Foundation historical subcategory selected another parent category.')
      # The site marks only the parent active. An exact advertised child query
      # establishes the child label; never infer it from a default parent.
      selected = [node for node in root.xpath(
        '//a[contains(concat(" ", normalize-space(@class), " "), " sub-category-winners ")]')
        if parse_qs(urlsplit(node.get('href') or '').query) == query]
      if not selected:
        raise ValueError('Foundation historical subcategory was not advertised by the selected page.')
    expected = normalize_heading(category).replace('non fiction', 'nonfiction')
    allowed = {expected}
    if expected == normalize_heading("Young People's Literature"):
      allowed.update(normalize_heading(value) for value in ("Children's Books", "Children's Literature"))
    actual = self.node_text(selected[0])
    if normalize_heading(actual).replace('non fiction', 'nonfiction') not in allowed:
      # Historical ?cat= values can silently select the default Fiction tab.
      # The requested URL alone does not establish the displayed category.
      raise ValueError(f'Official National Book Foundation page selected {actual}; expected {category}.')

  def rows_from_nodes(self, nodes, base_url, year, category, result, fetch_url=None):
    rows = []
    for node in nodes:
      title, author, source_url = self.work_from_node(node, base_url)
      if title and not author and not self.is_placeholder_title(title) and fetch_url is not None:
        target = urlsplit(source_url)
        if (target.scheme != 'https' or target.hostname not in ('nationalbook.org', 'www.nationalbook.org')
            or target.username or target.password or not target.path.startswith('/books/')):
          raise ValueError('Foundation missing-author link is not an official book page.')
        author = self.author_from_book_page(fetch_url(source_url), title)
        if not author:
          raise ValueError(f'Official Foundation book page had no usable author credit for {title}.')
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

  def author_from_book_page(self, html, title):
    root = self.html_root(html)
    if not any(normalize_heading(self.node_text(node)) == normalize_heading(title)
        for node in root.xpath('//h1')):
      raise ValueError('Foundation book page identifies another title.')
    for image in root.xpath('//img[@alt]'):
      credit = normalize_line(image.get('alt'))
      credit = re.sub(r'^(?:cover of|book cover of)\s+', '', credit, flags=re.I)
      match = re.match(re.escape(title) + r'\s+by\s+(.+)$', credit, flags=re.I)
      if match is not None:
        author = re.sub(r'\s+book cover\b.*$', '', match.group(1), flags=re.I)
        return self.clean_author(author)
    return ''

  def work_from_node(self, node, base_url):
    title_node = self.first_title_node(node)
    if title_node is None:
      return '', '', ''
    title = self.clean_title(self.node_text(title_node))
    author = self.clean_author(self.author_text(node))
    return title, author, self.node_href(title_node, base_url)

  def first_title_node(self, node):
    # The cover-image anchor precedes the textual title on current pages.
    # XPath unions sort by document order, losing this intended precedence.
    for selector in (
        './/*[self::h1 or self::h2 or self::h3]//a[@href]',
        './/figcaption//a[@href]',
        './/a[@href][not(ancestor::*[contains(concat(" ", normalize-space(@class), " "), " author ")])]'):
      for candidate in node.xpath(selector):
        if self.node_text(candidate):
          return candidate
    return None

  def author_text(self, node):
    candidates = node.xpath(
      './/*[contains(concat(" ", normalize-space(@class), " "), " book-data ")]//h2'
      '|.//p[contains(concat(" ", normalize-space(@class), " "), " author ")]'
      '|.//*[contains(concat(" ", normalize-space(@class), " "), " author ")]')
    for candidate in candidates:
      text = self.author_node_text(candidate)
      if text:
        return text
    # Finalist figures use a plain h2 immediately after their h1 title, while
    # winner cards wrap the same fields in book-data.
    for candidate in node.xpath('.//h1/following-sibling::h2'):
      text = self.author_node_text(candidate)
      if text:
        return text
    return ''

  def author_node_text(self, node):
    authors = [self.clean_author(self.node_text(child)) for child in node.xpath('./div')]
    return self.clean_author(' & '.join(authors) if authors else self.node_text(node))

  def clean_title(self, value):
    return normalize_line(value).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    return clean_author_credit(value)

  def is_placeholder_title(self, title):
    return (normalize_heading(title) in PLACEHOLDER_TITLES or
      re.fullmatch(r'(?:19|20)\d{2} .+ finalists?', normalize_heading(title)) is not None)

  def html_root(self, html):
    if isinstance(html, bytes):
      html = UnicodeDammit(html, is_html=True).unicode_markup
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

  Expand all inherited cells before reading columns: years, results, references,
  and hardcover/paperback labels can span different numbers of physical rows.
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
    'category': 'category',
  }
  HISTORICAL_CATEGORIES = {
    normalize_heading(value): value for value in (
      'Arts and Letters', 'History and Biography', 'History', 'Biography',
      'Autobiography', 'Biography and Autobiography', 'Autobiography and Biography',
      'Science, Philosophy and Religion', 'Philosophy and Religion',
      'The Sciences', 'Science', 'Contemporary Affairs', 'Current Interest',
      'General Nonfiction', 'General Reference', 'Religion/Inspiration',
    )
  }
  YOUNG_PEOPLE_CATEGORIES = {
    'fiction': 'Fiction',
    'non fiction': 'Nonfiction',
    'nonfiction': 'Nonfiction',
    'picture books': 'Picture Books',
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
      for node in table.xpath('./caption|preceding::h2[1]|preceding::h3[1]|preceding::h4[1]|preceding::h5[1]')))
    return (
      'recipient' in context
      or 'winner' in context
      or 'finalist' in context
      or not context)

  def table_category(self, table, category):
    if normalize_heading(category) == normalize_heading("Young People's Literature"):
      context = normalize_heading(' '.join(self.node_text(node) for node in table.xpath('./caption')))
      if normalize_heading("Children's Books") in context:
        return "Children's Books"
      return category
    if normalize_heading(category) != 'nonfiction':
      return category
    # Only the nearest heading can name this table; earlier sibling sections
    # must not label a later general-nonfiction decade table.
    headings = table.xpath(
      'preceding::*[self::h2 or self::h3 or self::h4 or self::h5 or self::h6][1]')
    if headings:
      label = self.HISTORICAL_CATEGORIES.get(normalize_heading(self.node_text(headings[0])))
      if label:
        return label
    for caption in table.xpath('./caption'):
      text = normalize_heading(self.node_text(caption))
      for key in sorted(self.HISTORICAL_CATEGORIES, key=len, reverse=True):
        if key in text:
          return self.HISTORICAL_CATEGORIES[key]
    return category

  def rows_from_table(self, table, header_map, base_url, category):
    rows = []
    table_category = self.table_category(table, category)
    current_year = None
    row_count_by_year = {}
    for cells in self.table_grid(table):
      if not cells or self.row_matches_header(cells, header_map):
        continue
      year_cell = self.cell_for_key(cells, header_map, 'year')
      year = self.year_from_text(self.clean_cell_text(year_cell))
      if year is None:
        year = current_year
      if year is None:
        continue
      current_year = year

      title_cell = self.cell_for_key(cells, header_map, 'title')
      author_cell = self.cell_for_key(cells, header_map, 'author')
      # Full-width explanations such as "No runners up" are not book rows.
      if title_cell is None or author_cell is None or title_cell is author_cell:
        continue
      title = self.title_from_cell(title_cell)
      author = self.clean_author(self.clean_cell_text(author_cell))
      if not title or not author or self.is_placeholder_title(title):
        continue

      result_cell = self.cell_for_key(cells, header_map, 'result')
      result = self.result_from_cell(result_cell)
      if result is None:
        if self.clean_cell_text(result_cell):
          continue
        row_count = row_count_by_year.get(year, 0)
        result = RESULT_WINNER if row_count == 0 else RESULT_NOMINEE
      row_count_by_year[year] = row_count_by_year.get(year, 0) + 1

      row_category = table_category
      historical_categories = None
      if normalize_heading(category) == 'nonfiction':
        historical_categories = self.HISTORICAL_CATEGORIES
      elif normalize_heading(category) == normalize_heading("Young People's Literature"):
        historical_categories = self.YOUNG_PEOPLE_CATEGORIES
      if historical_categories is not None:
        category_cell = self.cell_for_key(cells, header_map, 'category')
        label = self.clean_cell_text(category_cell)
        label = normalize_line(re.sub(r'\b(?:hardcover|paperback|paper)\b', '', label, flags=re.I)).strip(' ,')
        if label:
          row_category = historical_categories.get(normalize_heading(label), label)
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': self.first_link_url(title_cell, base_url) or base_url,
        'category': row_category,
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

  def cell_for_key(self, cells, header_map, key):
    index = header_map.get(key)
    if index is None:
      return None
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

  def title_from_cell(self, cell):
    text = self.clean_cell_text(cell)
    titles = cell.xpath('.//i|.//em')
    if titles:
      title = self.clean_cell_text(titles[0])
      if title and text.startswith(title):
        remainder = text[len(title):].strip()
        # Wikipedia puts explanatory/edition notes outside the italic title.
        # Parentheses within the work title and trailing volume labels survive.
        if remainder.startswith('(') and remainder.endswith(')'):
          text = title
    return self.clean_title(text)

  def clean_title(self, value):
    return normalize_line(value).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    return clean_author_credit(value)

  def is_placeholder_title(self, title):
    return normalize_heading(title) in PLACEHOLDER_TITLES

  def html_root(self, html):
    if isinstance(html, bytes):
      html = UnicodeDammit(html, is_html=True).unicode_markup
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
