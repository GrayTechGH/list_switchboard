#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Romance Writers of Australia RUBY award parser.

Maintenance notes:
- The current RWAus Shopify site exposes migrated finalist posts through search
  suggestion JSON, but not a complete result archive.
- Historical official winners are parsed from archived copies of the old RUBY
  page. Do not infer missing shortlists from author pages, social posts, or
  contest rules pages.
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


RWAUS_RUBY_AWARD_NAME = 'Romance Writers of Australia RUBY Awards'
RWAUS_RUBY_SEARCH_URL = (
  'https://romanceaustralia.com/search/suggest.json?q=RUBY'
  '&resources%5Btype%5D=article,page&resources%5Blimit%5D=50')
RWAUS_RUBY_OLD_URL = (
  'http://romanceaustralia.com/awards/romantic-book-of-the-year-ruby-2/')
RWAUS_RUBY_CDX_URL = (
  'https://web.archive.org/cdx?url=romanceaustralia.com/awards/'
  'romantic-book-of-the-year-ruby-2/&output=json'
  '&fl=timestamp,original,statuscode,mimetype,digest'
  '&filter=statuscode:200&collapse=digest&limit=20')

RESULT_PRIORITY = {RESULT_WINNER: 0, RESULT_SHORTLISTED: 1}


class RomanceWritersAustraliaRubyParser(AwardParserBase):

  AWARD_NAME = RWAUS_RUBY_AWARD_NAME

  def parse(
      self, html, base_url=RWAUS_RUBY_SEARCH_URL, name=RWAUS_RUBY_AWARD_NAME,
      fetch_url=None, archived_pages=None):
    notes = []
    rows = []
    rows.extend(self.parse_shopify_rows(html, base_url))
    if archived_pages is not None:
      rows.extend(self.parse_archived_pages(archived_pages))
    elif fetch_url is not None:
      rows.extend(self.fetch_archived_rows(fetch_url, notes))
    rows = self.dedupe_rows(rows)
    entries = self.entries_from_rows(rows)
    self.add_coverage_notes(rows, notes)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def parse_shopify_rows(self, html, base_url):
    data = self.load_json(html)
    articles = self.shopify_articles(data)
    rows = []
    for article in articles:
      if not self.accept_shopify_article(article):
        continue
      source_url = urljoin(base_url, article.get('url') or '')
      year = self.article_year(article)
      if year is None:
        continue
      rows.extend(self.parse_finalist_article(article.get('body') or '', source_url, year))
    return rows

  def load_json(self, value):
    try:
      return json.loads(value or '{}')
    except Exception:
      return {}

  def shopify_articles(self, data):
    resources = data.get('resources') if isinstance(data, dict) else {}
    results = resources.get('results') if isinstance(resources, dict) else {}
    articles = results.get('articles') if isinstance(results, dict) else []
    return articles if isinstance(articles, list) else []

  def accept_shopify_article(self, article):
    if not isinstance(article, dict):
      return False
    text = ' '.join([
      article.get('title') or '',
      article.get('handle') or '',
      ' '.join(article.get('tags') or ()),
      BeautifulSoup(article.get('body') or '', 'html.parser').get_text(' ', strip=True),
    ])
    heading = normalize_heading(text)
    if 'ruby' not in heading and 'romantic book of the year' not in heading:
      return False
    return any(word in heading for word in ('finalist', 'finalists', 'nominee', 'nominees'))

  def article_year(self, article):
    for value in (article.get('title'), article.get('body'), article.get('published_at')):
      year = self.year_from_text(value)
      if year is not None:
        return year
    return None

  def parse_finalist_article(self, body_html, source_url, year):
    soup = BeautifulSoup(body_html or '', 'html.parser')
    rows = []
    category = None
    for node in soup.find_all(['h2', 'h3', 'h4', 'p', 'li']):
      if node.name in {'h2', 'h3', 'h4'}:
        category = self.category_from_heading(node)
        continue
      if category is None:
        continue
      parsed = self.title_author_from_finalist_node(node)
      if parsed is None:
        continue
      title, author = parsed
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': RESULT_SHORTLISTED,
        'source_url': source_url,
        'category': category,
        '_source_order': len(rows),
      })
    return rows

  def category_from_heading(self, node):
    text = self.clean_category(node.get_text(' ', strip=True))
    heading = normalize_heading(text)
    if not text or heading in {
        'and the finalists are',
        'and the finalists are...',
        'and the finalists are ...',
      }:
      return None
    if 'finalist' in heading or 'nominee' in heading:
      return None
    if any(skip in heading for skip in ('congratulations', 'good luck')):
      return None
    return text

  def title_author_from_finalist_node(self, node):
    strong = node.find('strong')
    text = normalize_line(node.get_text(' ', strip=True))
    if strong is not None:
      author = self.clean_author(strong.get_text(' ', strip=True))
      remainder = text
      strong_text = normalize_line(strong.get_text(' ', strip=True))
      if strong_text and strong_text in remainder:
        remainder = remainder.split(strong_text, 1)[1]
      title = self.title_after_separator(remainder)
      if title and author:
        return title, author
    match = re.match(r'^(.+?)\s+[-\u2013\u2014]\s+(.+)$', text)
    if match is None:
      return None
    author = self.clean_author(match.group(1))
    title = self.clean_title(match.group(2))
    if not author or not title:
      return None
    return title, author

  def title_after_separator(self, value):
    value = normalize_line(value)
    value = re.sub(r'^\s*[-\u2013\u2014]\s*', '', value)
    return self.clean_title(value)

  def fetch_archived_rows(self, fetch_url, notes):
    rows = []
    try:
      cdx_html = fetch_url(RWAUS_RUBY_CDX_URL)
    except Exception as err:
      notes.append(f'RWAus archived RUBY winner index could not be fetched: {err}')
      return rows
    snapshot_url = self.snapshot_url_from_cdx(cdx_html)
    if not snapshot_url:
      notes.append('RWAus archived RUBY winner index did not expose a usable snapshot.')
      return rows
    try:
      archive_html = fetch_url(snapshot_url)
    except Exception as err:
      notes.append(f'RWAus archived RUBY winner page could not be fetched: {err}')
      return rows
    return self.parse_archived_pages(((snapshot_url, archive_html),))

  def snapshot_url_from_cdx(self, cdx_html):
    try:
      data = json.loads(cdx_html or '[]')
    except Exception:
      return ''
    rows = data if isinstance(data, list) else []
    snapshots = []
    for row in rows[1:]:
      if not isinstance(row, list) or len(row) < 2:
        continue
      timestamp, original = row[0], row[1]
      if timestamp and original:
        snapshots.append((timestamp, original))
    if not snapshots:
      return ''
    timestamp, original = sorted(snapshots)[-1]
    return f'https://web.archive.org/web/{timestamp}id_/{original}'

  def parse_archived_pages(self, pages):
    rows = []
    for page_url, page_html in pages:
      rows.extend(self.parse_archived_winner_rows(page_html, page_url))
    return rows

  def parse_archived_winner_rows(self, html, source_url):
    soup = BeautifulSoup(html or '', 'html.parser')
    rows = []
    for table in soup.find_all('table'):
      header_map = self.header_map(table)
      if self.has_required_columns(header_map):
        rows.extend(self.archived_table_rows(table, header_map, source_url))
    if rows:
      return rows
    return self.archived_text_rows(soup, source_url)

  def header_map(self, table):
    aliases = {
      'year': 'year',
      'award year': 'year',
      'category': 'category',
      'section': 'category',
      'title': 'title',
      'book': 'title',
      'work': 'title',
      'author': 'author',
      'authors': 'author',
      'winner': 'title',
      'winning book': 'title',
    }
    for tr in table.find_all('tr'):
      mapped = {}
      for index, cell in enumerate(tr.find_all(['td', 'th'], recursive=False)):
        key = aliases.get(normalize_heading(self.clean_cell_text(cell)))
        if key is not None and key not in mapped:
          mapped[key] = index
      if self.has_required_columns(mapped):
        return mapped
    return {}

  def has_required_columns(self, header_map):
    return all(key in header_map for key in ('year', 'category', 'title', 'author'))

  def archived_table_rows(self, table, header_map, source_url):
    rows = []
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      if not cells or self.row_is_header(cells):
        continue
      year = self.year_from_text(self.cell_text(cells, header_map, 'year'))
      category = self.clean_category(self.cell_text(cells, header_map, 'category'))
      title = self.clean_title(self.cell_text(cells, header_map, 'title'))
      author = self.clean_author(self.cell_text(cells, header_map, 'author'))
      if year is None or not category or not title or not author:
        continue
      rows.append(self.winner_row(year, title, author, category, source_url))
    return rows

  def row_is_header(self, cells):
    headings = {normalize_heading(self.clean_cell_text(cell)) for cell in cells}
    return 'year' in headings and ('title' in headings or 'winner' in headings)

  def cell_text(self, cells, header_map, key):
    index = header_map.get(key)
    if index is None or index >= len(cells):
      return ''
    return self.clean_cell_text(cells[index])

  def archived_text_rows(self, soup, source_url):
    rows = []
    current_year = None
    current_category = None
    for node in soup.find_all(['h2', 'h3', 'h4', 'p', 'li']):
      text = normalize_line(node.get_text(' ', strip=True))
      if not text:
        continue
      year = self.year_from_text(text)
      if year is not None and len(text) <= 30:
        current_year = year
        current_category = None
        continue
      category = self.category_from_heading(node)
      if node.name in {'h2', 'h3', 'h4'} and category:
        current_category = category
        continue
      if current_year is None or current_category is None:
        continue
      parsed = self.title_author_from_winner_text(text)
      if parsed is None:
        continue
      title, author = parsed
      rows.append(self.winner_row(current_year, title, author, current_category, source_url))
    return rows

  def title_author_from_winner_text(self, value):
    value = re.sub(r'^\s*winner\s*:?\s*', '', normalize_line(value), flags=re.I)
    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', value, flags=re.I)
    if by_match is not None:
      title = self.clean_title(by_match.group(1))
      author = self.clean_author(by_match.group(2))
      return (title, author) if title and author else None
    dash_match = re.match(r'^(.+?)\s+[-\u2013\u2014]\s+(.+)$', value)
    if dash_match is None:
      return None
    title = self.clean_title(dash_match.group(1))
    author = self.clean_author(dash_match.group(2))
    return (title, author) if title and author else None

  def winner_row(self, year, title, author, category, source_url):
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': RESULT_WINNER,
      'source_url': source_url,
      'category': category,
      '_source_order': 0,
    }

  def clean_cell_text(self, cell):
    cell = BeautifulSoup(str(cell), 'html.parser')
    for node in cell.find_all(['sup', 'style', 'script']):
      node.decompose()
    text = cell.get_text(' ', strip=True).replace('\xa0', ' ')
    text = re.sub(r'\s*\[\s*\d+\s*\]\s*', ' ', text)
    return normalize_line(text)

  def clean_category(self, value):
    value = normalize_line(value).replace('\u2013', '-').replace('\u2014', '-')
    value = re.sub(r'\s+', ' ', value)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,:')

  def clean_title(self, value):
    value = strip_publication_notes(normalize_line(value))
    value = re.sub(r'\s*\(\s*previously[^)]*\)\s*$', '', value, flags=re.I).strip()
    return value.strip(' "\'\u2018\u2019\u201c\u201d,:')

  def clean_author(self, value):
    value = strip_publication_notes(normalize_line(value))
    return value.strip(' "\'\u2018\u2019\u201c\u201d,:')

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def dedupe_rows(self, rows):
    deduped = []
    index_by_key = {}
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['category']),
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      existing_index = index_by_key.get(key)
      if existing_index is None:
        index_by_key[key] = len(deduped)
        deduped.append(row)
        continue
      existing = deduped[existing_index]
      if RESULT_PRIORITY.get(row.get('result'), 99) < RESULT_PRIORITY.get(
          existing.get('result'), 99):
        deduped[existing_index] = row
    return deduped

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      year_rows = sorted(
        by_year[year],
        key=lambda row: (
          RESULT_PRIORITY.get(row.get('result'), 99),
          row.get('_source_order', 0),
          normalize_heading(row.get('category', '')),
          normalize_heading(row.get('title', '')),
        ))
      award_rows = []
      for row in year_rows:
        entry_row = {key: value for key, value in row.items() if not key.startswith('_')}
        award_rows.append(self.build_award_entry(
          entry_row, row['source_url'], year, row['category']))
      entries.extend(assign_positions(award_rows, int(year)))
    return entries

  def add_coverage_notes(self, rows, notes):
    if not rows:
      notes.append(
        'No RUBY rows were parsed; the current RWAus site does not expose a '
        'complete public result archive.')
      return
    years = {int(row['award_year']) for row in rows if row.get('award_year')}
    shortlist_years = sorted({
      int(row['award_year']) for row in rows
      if row.get('result') == RESULT_SHORTLISTED
    })
    winner_years = sorted({
      int(row['award_year']) for row in rows
      if row.get('result') == RESULT_WINNER
    })
    if shortlist_years:
      notes.append(
        'Official migrated RWAus finalist/nominee posts were parsed for: ' +
        ', '.join(str(year) for year in shortlist_years) + '.')
    if winner_years:
      notes.append(
        'Archived official RUBY winner rows were parsed for: ' +
        ', '.join(str(year) for year in winner_years) + '.')
    if years:
      notes.append(
        'Shortlists are partial: no stable official source was confirmed for '
        '2015-2019, 2024, 2025, or 2026 during implementation.')


def parse_romance_writers_australia_ruby(
    html, base_url=RWAUS_RUBY_SEARCH_URL, name=RWAUS_RUBY_AWARD_NAME,
    fetch_url=None, archived_pages=None):
  return RomanceWritersAustraliaRubyParser().parse(
    html, base_url, name, fetch_url=fetch_url, archived_pages=archived_pages)
