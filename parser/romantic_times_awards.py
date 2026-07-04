#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Romantic Times Reviewers' Choice Awards parser for archived RT pages.

Maintenance notes:
- RT Book Reviews closed in 2018, so this recipe uses Wayback snapshots of
  official RT article pages instead of the dead live site.
- LibraryThing is intentionally not a runtime source here because its award
  pages can be CloudFront-challenge gated.
- V1 imports rows only from archived official winner/nominee pages that are
  discoverable from the seed manifest below. Nominee coverage is therefore
  archive-dependent and should not be treated as complete shortlists.
"""

import html as html_lib
import json
import re
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, RESULT_NOMINEE, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_NOMINEE, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key


RT_REVIEWERS_CHOICE_AWARD_NAME = (
  "Romantic Times Reviewers' Choice Awards - Romance Categories")
RT_ORIGINAL_SITE_ROOT = 'http://www.rtbookreviews.com'
RT_WAYBACK_ROOT = 'https://web.archive.org'
RT_SEED_PATHS = (
  '/blog/86292/2015-rt-reviewers-choice-award-nominees-mysterysuspensethriller-and-romantic-suspense',
  '/blog/86293',
  '/blog/86294/2015-rt-reviewers-choice-award-nominees-inspirational-young-adult-new-adult-and',
  '/blog/86295/2015-rt-reviewers-choice-award-nominees-science-fictionfantasyparanormal',
  '/blog/86296/2015-rt-reviewers-choice-award-nominees-series-romance',
)
RT_CDX_DISCOVERY_URLS = tuple(
  'https://web.archive.org/cdx?url=www.rtbookreviews.com'
  + quote(path, safe='/')
  + '&output=json&fl=timestamp,original,statuscode,mimetype,digest'
    '&filter=statuscode:200&collapse=digest&limit=8'
  for path in RT_SEED_PATHS
)
RT_PRIMARY_CDX_URL = RT_CDX_DISCOVERY_URLS[0]

RESULT_PRIORITY = {RESULT_WINNER: 0, RESULT_NOMINEE: 1}


class RomanticTimesReviewersChoiceParser(AwardParserBase):

  AWARD_NAME = RT_REVIEWERS_CHOICE_AWARD_NAME

  def parse(
      self, source, base_url=RT_PRIMARY_CDX_URL,
      name=RT_REVIEWERS_CHOICE_AWARD_NAME, fetch_url=None):
    notes = []
    rows = []
    if self.looks_like_cdx(source):
      rows.extend(self.fetch_seed_rows(source, base_url, fetch_url, notes))
    else:
      rows.extend(self.parse_article_rows(source, base_url))
    rows = self.dedupe_rows(rows)
    if not rows:
      raise ValueError('Could not parse Romantic Times awards from archived source.')
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def fetch_seed_rows(self, initial_cdx, initial_url, fetch_url, notes):
    if fetch_url is None:
      return []
    rows = []
    cdx_sources = [(initial_url, initial_cdx)]
    for cdx_url in RT_CDX_DISCOVERY_URLS:
      if cdx_url == initial_url:
        continue
      try:
        cdx_sources.append((cdx_url, fetch_url(cdx_url)))
      except Exception as err:
        notes.append(f'RT Wayback CDX page could not be fetched: {cdx_url}: {err}')
    seen_snapshots = set()
    for cdx_url, cdx_source in cdx_sources:
      snapshot_url = self.first_snapshot_url(cdx_source)
      if not snapshot_url or snapshot_url in seen_snapshots:
        continue
      seen_snapshots.add(snapshot_url)
      try:
        rows.extend(self.parse_article_rows(fetch_url(snapshot_url), snapshot_url))
      except Exception as err:
        notes.append(f'RT archived award page could not be fetched: {snapshot_url}: {err}')
    return rows

  def looks_like_cdx(self, source):
    text = self.source_text(source).lstrip()
    if not text.startswith('['):
      return False
    try:
      data = json.loads(text)
    except Exception:
      return False
    return isinstance(data, list) and bool(data) and isinstance(data[0], list)

  def first_snapshot_url(self, source):
    try:
      data = json.loads(self.source_text(source) or '[]')
    except Exception:
      return ''
    if not isinstance(data, list) or len(data) < 2:
      return ''
    rows = data[1:]
    for row in rows:
      if not isinstance(row, list) or len(row) < 2:
        continue
      timestamp, original = row[0], row[1]
      if timestamp and original:
        return f'{RT_WAYBACK_ROOT}/web/{timestamp}id_/{original}'
    return ''

  def parse_article_rows(self, source, page_url):
    soup = BeautifulSoup(self.source_text(source), 'html.parser')
    title = self.article_title(soup)
    result = self.result_from_title(title)
    year = self.year_from_title(title)
    if result is None or year is None:
      return []
    article_category = self.category_from_title(title)
    body = self.article_body(soup)
    if body is None:
      return []
    rows = []
    category = article_category
    for node in self.body_nodes(body):
      node_category = self.category_from_node(node)
      if node_category:
        category = node_category
        continue
      if not category or not self.is_romance_category(category):
        continue
      if node.name == 'table':
        rows.extend(self.table_rows(node, page_url, year, category, result, len(rows)))
      elif node.name in ('p', 'li'):
        rows.extend(self.text_rows(node, page_url, year, category, result, len(rows)))
    return rows

  def source_text(self, source):
    if isinstance(source, bytes):
      return source.decode('utf-8', 'replace')
    return source or ''

  def article_title(self, soup):
    heading = soup.find('h1', class_=lambda value: value and 'title' in value)
    if heading is None:
      heading = soup.find('h1')
    if heading is not None:
      return normalize_line(heading.get_text(' ', strip=True))
    title = soup.find('title')
    if title is not None:
      return normalize_line(title.get_text(' ', strip=True).split('|')[0])
    return ''

  def result_from_title(self, title):
    heading = normalize_heading(title)
    if 'winner' in heading:
      return RESULT_WINNER
    if 'nominee' in heading or 'finalist' in heading:
      return RESULT_NOMINEE
    return None

  def year_from_title(self, title):
    match = re.search(r'\b(19|20)\d{2}\b', title or '')
    return int(match.group(0)) if match is not None else None

  def category_from_title(self, title):
    match = re.search(
      r'Award\s+(?:Winners|Nominees|Finalists)\s*[—-]\s*(.+?)(?:\s*\|\s*RT Book Reviews)?$',
      title or '',
      re.I)
    if match is None:
      return ''
    return self.clean_category(match.group(1))

  def article_body(self, soup):
    body = soup.select_one('.field-name-body .field-item')
    if body is not None:
      return body
    body = soup.select_one('.field-name-body')
    if body is not None:
      return body
    article = soup.find('article')
    return article

  def body_nodes(self, body):
    return [
      node for node in body.children
      if getattr(node, 'name', None) in ('h2', 'h3', 'p', 'table', 'ul', 'ol', 'li')
    ]

  def category_from_node(self, node):
    if node.name not in ('h2', 'h3', 'p'):
      return ''
    strong = node.find('strong')
    if strong is None and node.name == 'p':
      return ''
    text = normalize_line((strong or node).get_text(' ', strip=True))
    if not text:
      return ''
    if len(text) > 90:
      return ''
    if re.search(r'\b(?:by|congratulations|nominees?|winners?)\b', text, re.I):
      return ''
    return self.clean_category(text)

  def table_rows(self, table, page_url, year, category, result, source_order_start):
    rows = []
    for cell in table.find_all(['td', 'th']):
      parsed = self.title_author_from_cell(cell)
      if parsed is None:
        continue
      title, author = parsed
      rows.append(self.row(
        title, author, page_url, year, category, result,
        source_order_start + len(rows)))
    return rows

  def text_rows(self, node, page_url, year, category, result, source_order_start):
    parsed = self.title_author_from_text(node.get_text(' ', strip=True))
    if parsed is None:
      return []
    title, author = parsed
    return [self.row(title, author, page_url, year, category, result, source_order_start)]

  def title_author_from_cell(self, cell):
    image = cell.find('img', alt=True)
    if image is not None:
      parsed = self.title_author_from_alt(image.get('alt', ''))
      if parsed is not None:
        return parsed
    return self.title_author_from_text(cell.get_text(' ', strip=True))

  def title_author_from_alt(self, value):
    value = normalize_line(html_lib.unescape(value or ''))
    for separator in (',', ':'):
      if separator in value:
        author, title = value.split(separator, 1)
        return self.clean_pair(title, author)
    match = re.match(r'^([A-Z0-9][A-Z0-9\'&: -]{3,})\s+([A-Z][A-Za-z\'.-]+(?:\s+[A-Z][A-Za-z\'.-]+)+)$', value)
    if match is not None:
      return self.clean_pair(match.group(1), match.group(2))
    return None

  def title_author_from_text(self, value):
    value = normalize_line(html_lib.unescape(value or ''))
    if not value or value == '\xa0':
      return None
    match = re.match(r'^(.+?)\s+by\s+(.+)$', value, re.I)
    if match is not None:
      return self.clean_pair(match.group(1), match.group(2))
    match = re.match(r'^(.+?)\s+[—-]\s+(.+)$', value)
    if match is not None:
      return self.clean_pair(match.group(1), match.group(2))
    return None

  def clean_pair(self, title, author):
    title = self.clean_title(title)
    author = self.clean_author(author)
    if not title or not author:
      return None
    return title, author

  def row(self, title, author, page_url, year, category, result, source_order):
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': page_url,
      'category': category,
      '_source_order': source_order,
    }

  def clean_title(self, value):
    value = strip_publication_notes(normalize_line(value))
    return value.strip(' "\'\u2018\u2019\u201c\u201d,:')

  def clean_author(self, value):
    value = re.sub(r'\s*\([^()]*\)\s*$', '', normalize_line(value))
    return value.strip(' "\'\u2018\u2019\u201c\u201d,:')

  def clean_category(self, value):
    value = normalize_line(html_lib.unescape(value or ''))
    value = re.sub(r'\s+And\s+', ' and ', value)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,:')

  def is_romance_category(self, category):
    heading = normalize_heading(category)
    if not heading:
      return False
    excluded = (
      'author', 'writer', 'career', 'certificate', 'k i s s', 'no category',
      'mystery', 'thriller', 'science fiction', 'fantasy', 'young adult',
      'new adult',
    )
    if any(word in heading for word in excluded):
      return 'romantic suspense' in heading or 'romance' in heading
    included = (
      'romance', 'romantic', 'harlequin', 'silhouette', 'love inspired',
      'steeple hill', 'kimani', 'inspirational',
    )
    return any(word in heading for word in included)

  def dedupe_rows(self, rows):
    chosen = {}
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['category']),
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      current = chosen.get(key)
      if current is None or self.row_priority(row) < self.row_priority(current):
        chosen[key] = row
    return sorted(chosen.values(), key=lambda item: (
      int(item['award_year']),
      RESULT_PRIORITY.get(item.get('result'), 99),
      item.get('_source_order', 0),
      normalize_heading(item.get('category', '')),
    ))

  def row_priority(self, row):
    return (
      RESULT_PRIORITY.get(row.get('result'), 99),
      row.get('_source_order', 0),
    )

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      award_rows = []
      for row in sorted(by_year[year], key=lambda item: (
          RESULT_PRIORITY.get(item.get('result'), 99),
          item.get('_source_order', 0))):
        entry_row = {key: value for key, value in row.items() if not key.startswith('_')}
        award_rows.append(self.build_award_entry(
          entry_row, row['source_url'], year, row['category']))
      entries.extend(assign_positions(award_rows, int(year)))
    return entries


def parse_romantic_times_awards(
    source, base_url=RT_PRIMARY_CDX_URL, name=RT_REVIEWERS_CHOICE_AWARD_NAME,
    fetch_url=None):
  return RomanticTimesReviewersChoiceParser().parse(
    source, base_url, name, fetch_url=fetch_url)
