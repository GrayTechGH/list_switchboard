#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Booksellers' Best Award parser for archived official GDRW pages.

Maintenance notes:
- The current live gdrwa.org host is not a trusted runtime source for this
  award; V1 uses Wayback captures of the original Greater Detroit Romance
  Writers pages.
- Official finalist/shortlist coverage is archive-dependent. The parser imports
  finalists only from official archived pages that visibly expose finalist rows.
- LibraryThing and FictionDB remain reference-only for this recipe.
"""

import json
import re

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


BOOKSELLERS_BEST_AWARD_NAME = "Booksellers' Best Award"
BOOKSELLERS_BEST_CDX_URL = (
  'https://web.archive.org/cdx?url=www.gdrwa.org/contests.html'
  '&output=json&fl=timestamp,original,statuscode,mimetype,digest'
  '&filter=statuscode:200&collapse=digest')
BOOKSELLERS_BEST_DISPLAY_URL = (
  'https://web.archive.org/web/*/http://www.gdrwa.org/contests.html')
BOOKSELLERS_BEST_CDX_URLS = (
  BOOKSELLERS_BEST_CDX_URL,
  'https://web.archive.org/cdx?url=www.gdrwa.org/bba*&output=json'
  '&fl=timestamp,original,statuscode,mimetype,digest&filter=statuscode:200'
  '&collapse=urlkey&limit=200',
  'https://web.archive.org/cdx?url=www.gdrwa.org/winners*&output=json'
  '&fl=timestamp,original,statuscode,mimetype,digest&filter=statuscode:200'
  '&collapse=urlkey&limit=200',
)

RESULT_PRIORITY = {RESULT_WINNER: 0, RESULT_SHORTLISTED: 1}

CATEGORY_ALIASES = {
  'traditional': 'Traditional',
  'best traditional romance': 'Traditional',
  'short contemporary': 'Short Contemporary Romance',
  'short contemporary romance': 'Short Contemporary Romance',
  'mid contemporary romance': 'Mid Contemporary Romance',
  'long contemporary': 'Long Contemporary Romance',
  'long contemporary romance': 'Long Contemporary Romance',
  'single title': 'Single Title',
  'single title romance': 'Single Title Romance',
  'short historical': 'Short Historical',
  'long historical': 'Long Historical',
  'historical romance': 'Historical Romance',
  'regency': 'Regency',
  'regency category': 'Regency',
  'romantic suspense': 'Romantic Suspense',
  'romanic suspense': 'Romantic Suspense',
  'suspense': 'Romantic Suspense',
  'inspirational': 'Inspirational Romance',
  'inspirational romance': 'Inspirational Romance',
  'erotic romance': 'Erotic Romance',
  'paranormal/time travel/futuristic': 'Paranormal/Time Travel/Futuristic',
  'paranormal/tt/futuristic': 'Paranormal/Time Travel/Futuristic',
  'paranormal / tt / futuristic': 'Paranormal/Time Travel/Futuristic',
  'paranormal romance': 'Paranormal Romance',
  'parnormal romance': 'Paranormal Romance',
  'young adult': 'Young Adult Romance',
  'young adult romance': 'Young Adult Romance',
  'novella': 'Novella',
  'romance novella': 'Romance Novella',
  'best first book': 'Best First Book',
  'the patti shenberger award for best book': (
    'The Patti Shenberger Award for Best Book'),
}

SKIP_HEADING_TERMS = (
  'category coordinator', 'to enter', 'entry', 'judge', 'rules',
  'congratulations', 'published authors contest', 'published author contest',
  'eligibility', 'deadline', 'questions', 'send your entry', 'online entry',
)


class BooksellersBestAwardParser(AwardParserBase):

  AWARD_NAME = BOOKSELLERS_BEST_AWARD_NAME

  def parse(
      self, html, base_url=BOOKSELLERS_BEST_CDX_URL,
      name=BOOKSELLERS_BEST_AWARD_NAME, fetch_url=None, pages=None):
    notes = []
    if pages is not None:
      rows = []
      for page_url, page_html in pages:
        rows.extend(self.parse_page_rows(page_html, page_url, notes))
    elif self.looks_like_cdx(html):
      rows = self.fetch_cdx_rows(html, base_url, fetch_url, notes)
    else:
      rows = self.parse_page_rows(html, base_url, notes)

    rows = self.dedupe_rows(self.with_source_order(rows))
    entries = self.entries_from_rows(rows)
    self.add_coverage_notes(rows, notes)
    if not rows:
      notes.append(
        "No Booksellers' Best Award rows were parsed from official archived "
        'GDRW pages.')
    notes.append(
      "LibraryThing's Bookseller's Best page and FictionDB/news/author pages "
      'are reference-only; no V1 fallback is wired.')
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def fetch_cdx_rows(self, initial_cdx, initial_url, fetch_url, notes):
    if fetch_url is None:
      return []
    cdx_sources = [(initial_url, initial_cdx)]
    for cdx_url in BOOKSELLERS_BEST_CDX_URLS:
      if cdx_url == initial_url:
        continue
      try:
        cdx_sources.append((cdx_url, fetch_url(cdx_url)))
      except Exception as err:
        notes.append(f'Official GDRW Wayback CDX page could not be fetched: {cdx_url}: {err}')

    rows = []
    seen_snapshots = set()
    for _cdx_url, cdx_source in cdx_sources:
      for snapshot_url in self.snapshot_urls(cdx_source):
        if snapshot_url in seen_snapshots:
          continue
        seen_snapshots.add(snapshot_url)
        try:
          page_html = fetch_url(snapshot_url)
        except Exception as err:
          notes.append(f'Official GDRW archived page could not be fetched: {snapshot_url}: {err}')
          continue
        rows.extend(self.parse_page_rows(page_html, snapshot_url, notes))
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

  def snapshot_urls(self, source):
    try:
      data = json.loads(self.source_text(source) or '[]')
    except Exception:
      return ()
    urls = []
    if not isinstance(data, list):
      return ()
    for row in data[1:]:
      if not isinstance(row, list) or len(row) < 2:
        continue
      timestamp, original = row[0], row[1]
      if not timestamp or not original:
        continue
      if self.skip_source_url(original):
        continue
      urls.append(f'https://web.archive.org/web/{timestamp}id_/{original}')
    return tuple(urls)

  def skip_source_url(self, url):
    text = normalize_heading(url)
    return any(skip in text for skip in (
      'entryform', 'entry form', 'judge', 'paypal', 'confirm', 'thanks'))

  def parse_page_rows(self, html, source_url, notes):
    soup = BeautifulSoup(self.source_text(html), 'html.parser')
    page_text = normalize_heading(soup.get_text(' ', strip=True)[:3000])
    url_text = normalize_heading(source_url)
    if not self.is_booksellers_page(page_text, url_text):
      return []
    result = self.result_for_page(soup, source_url)
    if result is None:
      if self.is_entry_or_rules_page(page_text):
        notes.append(
          f'Official GDRW archived page exposed entry/rules text but no winner '
          f'or finalist rows: {source_url}')
      return []
    year = self.year_for_page(soup, source_url)
    if year is None:
      return []

    rows = []
    rows.extend(self.parse_heading_sections(soup, source_url, year, result))
    rows.extend(self.parse_legacy_paragraphs(soup, source_url, year, result, len(rows)))
    if not rows and self.is_entry_or_rules_page(page_text):
      notes.append(
        f'Official GDRW archived {year} page exposed entry/rules text but no '
        'winner or finalist rows.')
    return rows

  def is_booksellers_page(self, page_text, url_text):
    combined = f'{page_text} {url_text}'
    return (
      'booksellers best' in combined
      or 'bookseller s best' in combined
      or 'bba' in url_text
      or 'winners' in url_text
    )

  def result_for_page(self, soup, source_url):
    text = normalize_heading(f'{source_url} {self.title_text(soup)}')
    page_text = normalize_heading(soup.get_text(' ', strip=True)[:3000])
    if 'between the sheets' in page_text:
      return None
    if 'finalist' in text or 'finalist' in page_text[:1800]:
      return RESULT_SHORTLISTED
    if 'winner' in text or 'winner' in page_text[:1800]:
      return RESULT_WINNER
    return None

  def year_for_page(self, soup, source_url):
    url_year = self.year_from_url(source_url)
    if url_year is not None:
      return url_year
    for heading in soup.find_all(['h1', 'h2', 'title']):
      text = normalize_line(heading.get_text(' ', strip=True))
      if re.search(r'booksellers|book sellers|bba', text, re.I):
        year = self.year_from_text(text)
        if year is not None:
          return year
    return None

  def year_from_url(self, url):
    for pattern in (r'winners(19|20)(\d{2})', r'bba\D*(19|20)(\d{2})'):
      match = re.search(pattern, url or '', re.I)
      if match is not None:
        return int(match.group(0)[-4:])
    match = re.search(r'bba(?:finals?|winners?)(\d{2})(?:\D|$)', url or '', re.I)
    if match is not None:
      value = int(match.group(1))
      return 2000 + value if value < 50 else 1900 + value
    return None

  def year_from_text(self, text):
    match = re.search(r'(19|20)\d{2}', text or '')
    return int(match.group(0)) if match is not None else None

  def title_text(self, soup):
    title = soup.find('title')
    return title.get_text(' ', strip=True) if title is not None else ''

  def is_entry_or_rules_page(self, page_text):
    return any(term in page_text for term in (
      'entry form', 'to enter', 'eligibility', 'send your entry',
      'category coordinator', 'books published in'))

  def parse_heading_sections(self, soup, source_url, year, result):
    rows = []
    for heading in soup.find_all(['h3', 'h4', 'h5']):
      category = self.category_from_text(heading.get_text(' ', strip=True))
      if not category:
        continue
      for node in heading.next_siblings:
        name = getattr(node, 'name', None)
        if name in {'h1', 'h2', 'h3', 'h4', 'h5'}:
          break
        if name not in {'p', 'div', 'ul', 'ol'}:
          continue
        parsed_rows = self.rows_from_node(node, source_url, year, category, result, len(rows))
        rows.extend(parsed_rows)
        if parsed_rows:
          break
    return rows

  def parse_legacy_paragraphs(self, soup, source_url, year, result, source_order_start=0):
    rows = []
    for paragraph in soup.find_all('p'):
      category = self.category_from_paragraph(paragraph)
      if not category:
        continue
      lines = self.paragraph_lines(paragraph)
      category_seen = False
      for line in lines:
        if self.category_from_text(line):
          category_seen = True
          continue
        if not category_seen:
          continue
        parsed = self.title_author_from_text(line)
        if parsed is None:
          continue
        title, author = parsed
        rows.append(self.row(
          year, title, author, category, result, source_url,
          source_order_start + len(rows)))
    return rows

  def category_from_paragraph(self, paragraph):
    for fragment in paragraph.find_all(['font', 'strong', 'b', 'i', 'em']):
      category = self.category_from_text(fragment.get_text(' ', strip=True))
      if category:
        return category
    lines = self.paragraph_lines(paragraph)
    return self.category_from_text(lines[0]) if lines else ''

  def paragraph_lines(self, node):
    fragment = BeautifulSoup(str(node), 'html.parser')
    for br in fragment.find_all('br'):
      br.replace_with('\n')
    text = fragment.get_text(' ', strip=False)
    return [normalize_line(line) for line in text.splitlines() if normalize_line(line)]

  def rows_from_node(self, node, source_url, year, category, result, source_order_start):
    rows = []
    for title, author in self.title_author_rows_from_emphasis(node):
      rows.append(self.row(
        year, title, author, category, result, source_url,
        source_order_start + len(rows)))
    if rows:
      return rows
    lines = self.paragraph_lines(node) if getattr(node, 'name', None) != 'li' else [
      normalize_line(node.get_text(' ', strip=True))]
    for line in lines:
      parsed = self.title_author_from_text(line)
      if parsed is None:
        continue
      title, author = parsed
      rows.append(self.row(
        year, title, author, category, result, source_url,
        source_order_start + len(rows)))
    return rows

  def title_author_rows_from_emphasis(self, node):
    emphasized = node.find_all('em')
    if not emphasized:
      return ()
    rows = []
    for emphasis in emphasized:
      title = self.clean_title(emphasis.get_text(' ', strip=True))
      if not title or self.category_from_text(title):
        continue
      author = self.author_after_emphasis(emphasis)
      if author:
        rows.append((title, author))
    return tuple(rows)

  def author_after_emphasis(self, emphasis):
    parts = []
    for sibling in emphasis.next_siblings:
      if getattr(sibling, 'name', None) == 'em':
        break
      parts.append(sibling.get_text(' ', strip=True) if hasattr(sibling, 'get_text') else str(sibling))
    text = normalize_line(' '.join(parts))
    text = re.sub(r'^(?:by|[-\u2013\u2014,])\s*', '', text, flags=re.I).strip()
    if ',' in text:
      text = text.rsplit(',', 1)[-1].strip()
    text = re.sub(r'^\s*(?:and|&)\s+', '', text, flags=re.I).strip()
    text = re.sub(r'\s+(?:and|&)\s*$', '', text, flags=re.I).strip()
    return self.clean_author(text)

  def title_author_from_text(self, text):
    text = normalize_line(text)
    if not text or self.category_from_text(text) or self.skip_line(text):
      return None
    match = re.match(r'^(.+?)\s+by\s+(.+)$', text, re.I)
    if match is None:
      match = re.match(r'^(.+?)\s*[-\u2013\u2014]\s*(.+)$', text)
    if match is None:
      match = re.match(r'^(.+?),\s*([^,]+)$', text)
    if match is None:
      return None
    title = self.clean_title(match.group(1))
    author = self.clean_author(match.group(2))
    if not title or not author or self.skip_line(author):
      return None
    return title, author

  def skip_line(self, text):
    normalized = normalize_heading(text)
    return (
      len(normalized) < 3
      or any(term in normalized for term in SKIP_HEADING_TERMS)
      or normalized.startswith('authors listed alphabetically')
      or normalized.startswith('many many thanks')
    )

  def category_from_text(self, text):
    text = normalize_line(text)
    normalized = normalize_heading(re.sub(r'\s*\([^)]*\)\s*$', '', text))
    if not normalized or any(term in normalized for term in SKIP_HEADING_TERMS):
      return ''
    return CATEGORY_ALIASES.get(normalized, '')

  def clean_title(self, value):
    value = strip_publication_notes(normalize_line(value))
    value = re.sub(r'\s*[-\u2013\u2014]\s*(?:historical romance version|romance version)\s*$', '', value, flags=re.I)
    return value.strip(' "\u201c\u201d,')

  def clean_author(self, value):
    value = strip_publication_notes(normalize_line(value))
    value = re.sub(r'\s+\*+$', '', value).strip()
    return value.strip(' "\u201c\u201d,')

  def row(self, year, title, author, category, result, source_url, source_order):
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'category': category,
      'result': result,
      'source_url': source_url,
      'source_order': source_order,
    }

  def with_source_order(self, rows):
    ordered = []
    for index, row in enumerate(rows):
      item = dict(row)
      item['source_order'] = index
      ordered.append(item)
    return ordered

  def dedupe_rows(self, rows):
    best = {}
    order = []
    for row in rows:
      key = (
        row.get('award_year', ''),
        normalize_heading(row.get('category', '')),
        normalize_heading(row.get('title', '')),
        normalize_heading(row.get('author', '')),
      )
      existing = best.get(key)
      if existing is None:
        best[key] = row
        order.append(key)
        continue
      if RESULT_PRIORITY.get(row.get('result'), 9) < RESULT_PRIORITY.get(existing.get('result'), 9):
        best[key] = row
    return [best[key] for key in order]

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      year_rows = sorted(
        by_year[year],
        key=lambda row: (
          RESULT_PRIORITY.get(row.get('result'), 9),
          row.get('source_order', 0),
          normalize_heading(row.get('category', '')),
        ))
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in year_rows
      ]
      entries.extend(assign_positions(award_rows, int(year)))
    return entries

  def add_coverage_notes(self, rows, notes):
    finalist_years = sorted({
      row['award_year'] for row in rows if row.get('result') == RESULT_SHORTLISTED
    }, key=int)
    winner_years = sorted({
      row['award_year'] for row in rows if row.get('result') == RESULT_WINNER
    }, key=int)
    if finalist_years:
      notes.append(
        'Official archived GDRW finalist/shortlist-style rows were parsed for: ' +
        ', '.join(finalist_years))
    if winner_years:
      notes.append(
        'Official archived GDRW winner rows were parsed for: ' +
        ', '.join(winner_years))
    winner_only = [year for year in winner_years if year not in finalist_years]
    if winner_only:
      notes.append(
        'Official archived GDRW winner-only years were parsed for: ' +
        ', '.join(winner_only))

  def source_text(self, source):
    if isinstance(source, bytes):
      return source.decode('utf-8', 'replace')
    return source or ''


def parse_booksellers_best(
    html, base_url=BOOKSELLERS_BEST_CDX_URL,
    name=BOOKSELLERS_BEST_AWARD_NAME, fetch_url=None, pages=None):
  return BooksellersBestAwardParser().parse(
    html, base_url, name, fetch_url=fetch_url, pages=pages)
