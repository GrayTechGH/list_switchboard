#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Lambda Literary Awards parser for official romance-category Lammy pages.

Maintenance notes:
- The official Lammys Directory states that it contains finalists and winners
  back to 1988 and that its year is the publication year, not the ceremony
  year. The public page currently embeds Airtable data, so this parser accepts
  parseable directory table/JSON exports but does not depend on an unofficial
  Airtable endpoint.
- The official current finalists page is a shortlist source. Lambda uses
  "finalists" wording there; import entries record those rows as shortlisted.
"""

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key


LAMBDA_AWARD_NAME = 'Lambda Literary Awards'
LAMBDA_ROMANCE_AWARD_NAME = 'Lambda Literary Awards - Romance Categories'
LAMBDA_DIRECTORY_URL = (
  'https://lambdaliterary.org/awards/lammys-directory-1988-present/')
LAMBDA_AIRTABLE_EMBED_RE = re.compile(r'https://airtable\.com/embed/[^"\']+')
LAMBDA_CURRENT_FINALISTS_URL = 'https://lambdaliterary.org/awards/current-finalists/'
LAMBDA_CURRENT_WINNERS_URL = 'https://lambdaliterary.org/awards/2026-winners/'
LAMBDA_CURRENT_URLS = (LAMBDA_CURRENT_FINALISTS_URL, LAMBDA_CURRENT_WINNERS_URL)

ROMANCE_CATEGORY_ALIASES = {
  'gay romance',
  'lesbian romance',
  'lgbt romance',
  'lgbtq romance',
  'lgbtq romance and erotica',
  'lgbtq romance erotica',
  'lgbtq+ romance',
  'lgbtq+ romance and erotica',
  'lgbtq+ romance erotica',
  'romance',
}

HEADER_ALIASES = {
  'award': 'award',
  'award category': 'category',
  'award year': 'year',
  'author': 'author',
  'authors': 'author',
  'book': 'title',
  'category': 'category',
  'finalist winner': 'result',
  'finalist/winner': 'result',
  'result': 'result',
  'status': 'result',
  'title': 'title',
  'work': 'title',
  'year': 'year',
}


class LambdaLiteraryAwardsRomanceParser(AwardParserBase):

  AWARD_NAME = LAMBDA_AWARD_NAME

  def parse(
      self, html, base_url=LAMBDA_DIRECTORY_URL, name=LAMBDA_ROMANCE_AWARD_NAME,
      fetch_url=None, current_pages=()):
    notes = []
    rows = []
    directory_rows = self.parse_directory_rows(html, base_url)
    rows.extend(directory_rows)

    if not directory_rows and self.has_airtable_embed(html):
      notes.append(
        'Lambda Lammys Directory embeds Airtable data; no parseable '
        'server-rendered directory rows were available from the fetched page.')

    pages = list(current_pages or ())
    if fetch_url is not None and not pages:
      for url in LAMBDA_CURRENT_URLS:
        try:
          pages.append((url, fetch_url(url)))
        except Exception as err:
          notes.append(f'Lambda current award page could not be fetched: {url}: {err}')

    for url, page_html in pages:
      if 'winner' in url.lower():
        rows.extend(self.parse_current_winners_page(page_html, url))
      else:
        rows.extend(self.parse_current_finalists_page(page_html, url))

    rows = self.dedupe_rows(rows)
    if not rows:
      raise ValueError('Could not parse Lambda Literary Awards romance rows from source.')
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def parse_directory_rows(self, source, base_url):
    rows = []
    rows.extend(self.parse_json_rows(source, base_url))
    rows.extend(self.parse_html_table_rows(source, base_url))
    return rows

  def parse_json_rows(self, source, base_url):
    try:
      data = json.loads(source)
    except Exception:
      return []
    records = self.find_json_records(data)
    rows = []
    for record in records:
      fields = record.get('fields') if isinstance(record, dict) else None
      if not isinstance(fields, dict):
        fields = record if isinstance(record, dict) else {}
      row = self.row_from_mapping(fields, base_url)
      if row:
        rows.append(row)
    return rows

  def find_json_records(self, data):
    records = []
    if isinstance(data, dict):
      maybe_records = data.get('records') or data.get('rows')
      if isinstance(maybe_records, list):
        records.extend([
          item for item in maybe_records
          if isinstance(item, dict)
        ])
      for value in data.values():
        records.extend(self.find_json_records(value))
    elif isinstance(data, list):
      for item in data:
        records.extend(self.find_json_records(item))
    return records

  def row_from_mapping(self, mapping, base_url):
    values = {}
    for key, value in mapping.items():
      mapped = HEADER_ALIASES.get(normalize_heading(str(key)))
      if mapped and mapped not in values:
        values[mapped] = self.scalar_text(value)
    year = self.year_from_text(values.get('year', ''))
    category = self.clean_category(values.get('category', ''))
    title = self.clean_title(values.get('title', ''))
    author = self.clean_author(values.get('author', ''))
    result = self.result_from_text(values.get('result', ''))
    if year is None or not self.is_romance_category(category) or not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': base_url,
      'category': category,
    }

  def parse_html_table_rows(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for table in soup.find_all('table'):
      header_map = self.header_map(table)
      if not self.has_required_columns(header_map):
        continue
      rows.extend(self.table_rows(table, header_map, base_url))
    return rows

  def header_map(self, table):
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      mapped = {}
      for index, cell in enumerate(cells):
        key = HEADER_ALIASES.get(normalize_heading(self.clean_node_text(cell)))
        if key and key not in mapped:
          mapped[key] = index
      if self.has_required_columns(mapped):
        return mapped
    return {}

  def has_required_columns(self, header_map):
    return all(key in header_map for key in ('year', 'category', 'title', 'author'))

  def table_rows(self, table, header_map, base_url):
    rows = []
    last_year = None
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      if not cells or self.is_header_row(cells):
        continue
      year_text = self.cell_text(cells, header_map, 'year')
      year = self.year_from_text(year_text) or last_year
      category = self.clean_category(self.cell_text(cells, header_map, 'category'))
      title_cell = self.cell_for_key(cells, header_map, 'title')
      title = self.clean_title(self.clean_node_text(title_cell))
      author = self.clean_author(self.cell_text(cells, header_map, 'author'))
      result = self.result_from_text(self.cell_text(cells, header_map, 'result'))
      if year is None or not self.is_romance_category(category) or not title or not author:
        continue
      last_year = year
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': self.first_link_url(title_cell, base_url) or base_url,
        'category': category,
      })
    return rows

  def parse_current_finalists_page(self, html, url):
    soup = BeautifulSoup(html, 'html.parser')
    year = self.current_publication_year(soup, url)
    if year is None:
      return []
    rows = []
    for heading in soup.find_all(['h2', 'h3']):
      category = self.clean_category(self.clean_node_text(heading))
      if not self.is_romance_category(category):
        continue
      for sibling in heading.find_next_siblings():
        if sibling.name in {'h1', 'h2', 'h3'}:
          break
        for node in self.item_nodes(sibling):
          row = self.current_finalist_row(node, year, category, url)
          if row:
            rows.append(row)
    return rows

  def current_finalist_row(self, node, year, category, page_url):
    text = self.clean_node_text(node)
    if '//' not in text:
      return None
    title_text, remainder = re.split(r'\s*//\s*', text, 1)
    title_link = node.find('a', href=True) if hasattr(node, 'find') else None
    if title_link is not None:
      title_text = self.clean_node_text(title_link)
    author_text = remainder.rsplit('. ', 1)[0] if '. ' in remainder else remainder
    title = self.clean_title(title_text)
    author = self.clean_author(author_text)
    if not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': RESULT_SHORTLISTED,
      'source_url': urljoin(page_url, title_link['href']) if title_link is not None else page_url,
      'category': category,
    }

  def parse_current_winners_page(self, html, url):
    soup = BeautifulSoup(html, 'html.parser')
    year = self.current_publication_year(soup, url)
    if year is None:
      return []
    rows = []
    pending_category = None
    pending_title = None
    pending_url = url
    for node in soup.find_all(['h2', 'h3', 'h4', 'h5', 'h6', 'p']):
      text = self.clean_node_text(node)
      if not text:
        continue
      category = self.clean_category(text)
      if node.name in {'h2', 'h3'} and self.is_romance_category(category):
        pending_category = category
        pending_title = None
        pending_url = url
        continue
      if pending_category is None:
        continue
      if pending_title is None and node.name in {'h2', 'h3', 'h4'}:
        if self.is_romance_category(category):
          continue
        pending_title = self.clean_title(text)
        link = node.find('a', href=True)
        pending_url = urljoin(url, link['href']) if link is not None else url
        continue
      author = self.clean_author(text)
      if pending_title and author:
        rows.append({
          'award_year': str(year),
          'title': pending_title,
          'author': author,
          'result': RESULT_WINNER,
          'source_url': pending_url,
          'category': pending_category,
        })
        pending_category = None
        pending_title = None
        pending_url = url
    return rows

  def item_nodes(self, node):
    items = node.find_all('li') if hasattr(node, 'find_all') else []
    if items:
      return items
    if getattr(node, 'name', '') in {'li', 'p'}:
      return [node]
    return node.find_all('p') if hasattr(node, 'find_all') else []

  def cell_for_key(self, cells, header_map, key):
    index = header_map.get(key)
    if index is None or index >= len(cells):
      return None
    return cells[index]

  def cell_text(self, cells, header_map, key):
    return self.clean_node_text(self.cell_for_key(cells, header_map, key))

  def clean_node_text(self, node):
    if node is None:
      return ''
    clone = BeautifulSoup(str(node), 'html.parser')
    for child in clone.find_all(['script', 'style', 'sup']):
      child.decompose()
    text = clone.get_text(' ', strip=True).replace('\xa0', ' ')
    text = re.sub(r'\s*\[\s*\d+\s*\]\s*', ' ', text)
    return normalize_line(text)

  def scalar_text(self, value):
    if isinstance(value, dict):
      for key in ('text', 'name', 'title', 'value'):
        if key in value:
          return self.scalar_text(value[key])
      return ''
    if isinstance(value, list):
      return ' & '.join(self.scalar_text(item) for item in value if self.scalar_text(item))
    return normalize_line(str(value)) if value is not None else ''

  def clean_category(self, value):
    return normalize_line(value).strip(' "\'\u2018\u2019\u201c\u201d,:')

  def clean_title(self, value):
    value = strip_publication_notes(normalize_line(value))
    value = re.sub(r'^\s*(?:winner|finalist)\s*:?\s*', '', value, flags=re.I)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def clean_author(self, value):
    value = normalize_line(value)
    value = re.sub(r'^\s*by\s+', '', value, flags=re.I)
    value = strip_publication_notes(value)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def current_publication_year(self, soup, url):
    url_year = self.year_from_text(url)
    title_text = self.clean_node_text(soup.find('title'))
    if url_year is not None:
      title_year = self.year_from_text(title_text)
      if title_year is not None and title_year == url_year - 1:
        return title_year
      return url_year - 1
    heading_text = ' '.join(
      self.clean_node_text(node) for node in soup.find_all(['h1', 'h2'])[:3])
    heading_year = self.year_from_text(heading_text)
    if heading_year is not None and re.search(
        r'\b(?:lammy|lammys|lambda literary award).*(?:finalist|winner)',
        heading_text,
        re.I):
      return heading_year - 1
    return self.year_from_text(title_text)

  def result_from_text(self, value):
    normalized = normalize_heading(value)
    if 'winner' in normalized or normalized == 'win':
      return RESULT_WINNER
    return RESULT_SHORTLISTED

  def is_romance_category(self, category):
    normalized = normalize_heading(category)
    return normalized in {
      normalize_heading(value) for value in ROMANCE_CATEGORY_ALIASES
    }

  def is_header_row(self, cells):
    headings = {normalize_heading(self.clean_node_text(cell)) for cell in cells}
    return {'year', 'category', 'title', 'author'}.issubset(headings)

  def first_link_url(self, cell, base_url):
    link = cell.find('a', href=True) if cell is not None else None
    return urljoin(base_url, link['href']) if link is not None else ''

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def has_airtable_embed(self, html):
    return bool(LAMBDA_AIRTABLE_EMBED_RE.search(html or ''))

  def dedupe_rows(self, rows):
    best_rows = {}
    order = []
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['category']),
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      if key not in best_rows:
        order.append(key)
        best_rows[key] = row
        continue
      if best_rows[key].get('result') != RESULT_WINNER and row.get('result') == RESULT_WINNER:
        best_rows[key] = row
    return [best_rows[key] for key in order]

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      award_rows = sorted(
        by_year[year],
        key=lambda row: (
          0 if row.get('result') == RESULT_WINNER else 1,
          normalize_heading(row.get('category', '')),
          normalize_heading(row.get('title', '')),
          normalize_heading(row.get('author', ''))))
      award_entries = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in award_rows
      ]
      entries.extend(assign_positions(award_entries, int(year)))
    return entries


def parse_lambda_literary_awards_romance(
    html, base_url=LAMBDA_DIRECTORY_URL, name=LAMBDA_ROMANCE_AWARD_NAME,
    fetch_url=None):
  return LambdaLiteraryAwardsRomanceParser().parse(
    html, base_url, name, fetch_url=fetch_url)
