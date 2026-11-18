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
- A capture can contain next-year entry rules above older results. Bound each
  annual award section and its winner/finalist stages before assigning metadata.
"""

import json
import re
from copy import deepcopy

from bs4 import BeautifulSoup, UnicodeDammit

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes, is_author_suffix,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes, is_author_suffix,
  )
  from .generic import position_sort_key


BOOKSELLERS_BEST_AWARD_NAME = "Booksellers' Best Award"
BOOKSELLERS_BEST_CDX_URL = (
  'https://web.archive.org/cdx/search/cdx?url=www.gdrwa.org/contests.html'
  '&output=json&fl=timestamp,original,statuscode,mimetype,digest'
  '&filter=statuscode:200&collapse=digest&gzip=false')
BOOKSELLERS_BEST_DISPLAY_URL = (
  'https://web.archive.org/web/*/http://www.gdrwa.org/contests.html')
BOOKSELLERS_BEST_CDX_URLS = (
  BOOKSELLERS_BEST_CDX_URL,
  'https://web.archive.org/cdx/search/cdx?url=www.gdrwa.org/bba*&output=json'
  '&fl=timestamp,original,statuscode,mimetype,digest&filter=statuscode:200'
  '&collapse=urlkey&limit=200&gzip=false',
  'https://web.archive.org/cdx/search/cdx?url=www.gdrwa.org/winners*&output=json'
  '&fl=timestamp,original,statuscode,mimetype,digest&filter=statuscode:200'
  '&collapse=urlkey&limit=200&gzip=false',
)

RESULT_PRIORITY = {RESULT_WINNER: 0, RESULT_SHORTLISTED: 1}

CATEGORY_ALIASES = {
  'traditional': 'Traditional',
  'traditional/sweet': 'Traditional',
  'best traditional romance': 'Traditional',
  'short contemporary': 'Short Contemporary Romance',
  'short contemporary romance': 'Short Contemporary Romance',
  'mid contemporary romance': 'Mid Contemporary Romance',
  'long contemporary': 'Long Contemporary Romance',
  'long contemporary romance': 'Long Contemporary Romance',
  'single title': 'Single Title',
  'single title/mainstream': 'Single Title',
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
  'erotic': 'Erotic Romance',
  'paranormal/time travel/futuristic': 'Paranormal/Time Travel/Futuristic',
  'paranormal/tt/futuristic': 'Paranormal/Time Travel/Futuristic',
  'paranormal / tt / futuristic': 'Paranormal/Time Travel/Futuristic',
  'paranormal romance': 'Paranormal Romance',
  'paranormal': 'Paranormal Romance',
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
      name=BOOKSELLERS_BEST_AWARD_NAME, fetch_url=None, pages=None,
      cached_parsed=None, incremental_update=False):
    if fetch_url is not None and pages is None and self.looks_like_cdx(html):
      from .booksellers_best_updates import fetch_booksellers_best
      return fetch_booksellers_best(self,fetch_url,base_url,name,cached_parsed,
        incremental_update,initial_source=html)
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
    return self.result_from_rows(rows,base_url,name,notes)

  def result_from_rows(self,rows,base_url,name,notes):
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
    return [row for section in self.award_sections(soup)
      for row in self.parse_section_rows(section, source_url, notes)]

  def award_sections(self, soup):
    """Entry rules for a new cycle can precede a previous year's results."""
    soup = self.booksellers_section(soup)
    headings = [node for node in soup.find_all(['h1', 'h2', 'h3', 'h4'])
      if re.search(r'\bbookseller(?:s| s)? best\b', normalize_heading(node.get_text(' ', strip=True)))
      and self.year_from_text(node.get_text(' ', strip=True)) is not None]
    if len(headings) < 2:
      return [soup]
    sections = []
    for heading in headings:
      section = BeautifulSoup('<html><body></body></html>', 'html.parser')
      section.body.append(deepcopy(heading))
      for node in heading.next_siblings:
        if any(node is boundary for boundary in headings):
          break
        section.body.append(deepcopy(node))
      sections.append(section)
    return sections

  def parse_section_rows(self, soup, source_url, notes):
    page_text = normalize_heading(soup.get_text(' ', strip=True)[:3000])
    url_text = normalize_heading(source_url)
    if not self.is_booksellers_page(page_text, url_text):
      return []
    image_only = self.known_image_roster(soup)
    result = self.result_for_page(soup, source_url)
    if result is None:
      if image_only:
        notes.append('The archived 2017 Booksellers Best finalist roster is image-only; '
          'this HTML recipe cannot import those finalists. Official HTML winners remain available.')
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
    rows.extend(self.parse_inline_category_rows(soup, source_url, year, result, len(rows)))
    if not rows and self.is_entry_or_rules_page(page_text):
      notes.append(
        f'Official GDRW archived {year} page exposed entry/rules text but no '
        'winner or finalist rows.')
    if not rows and image_only:
      notes.append('The archived 2017 Booksellers Best finalist roster is image-only; '
        'this HTML recipe cannot import those finalists. Official HTML winners remain available.')
    return rows

  def known_image_roster(self, soup):
    return (self.year_for_page(soup, '') == 2017 and
      any(str(image.get('src', '')) == 'images/finalists2017.gif' for image in soup.find_all('img')) and
      not any(self.category_from_text(node.get_text(' ', strip=True))
        for node in soup.find_all(['h3', 'h4', 'h5'])))

  def booksellers_section(self, soup):
    if 'between the sheets' not in normalize_heading(soup.get_text(' ', strip=True)):
      return soup
    heading = next((node for node in soup.find_all(['h1', 'h2', 'h3', 'h4'])
      if re.search(r'\bbookseller(?:s| s)? best\b', normalize_heading(node.get_text(' ', strip=True)))), None)
    if heading is None:
      return soup
    section = BeautifulSoup('<html><body></body></html>', 'html.parser')
    section.body.append(deepcopy(heading))
    for node in heading.next_siblings:
      if getattr(node, 'name', None) in ('h1', 'h2', 'h3'):
        text = normalize_heading(node.get_text(' ', strip=True))
        if 'between the sheets' in text or ('contest' in text and 'bookseller' not in text):
          break
      section.body.append(deepcopy(node))
    return section

  def is_booksellers_page(self, page_text, url_text):
    combined = f'{page_text} {url_text}'
    return (
      'booksellers best' in combined
      or 'bookseller s best' in combined
      or 'bba' in url_text
      or 'winners' in url_text
    )

  def result_for_page(self, soup, source_url):
    soup = self.booksellers_section(soup)
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
    result_years = set()
    for node in soup.find_all('p'):
      text = normalize_heading(node.get_text(' ', strip=True))
      if (len(text) <= 350 and re.search(r'\bbookseller(?:s| s)? best\b', text)
          and re.search(r'\b(?:finalists?|winners?)\b', text)):
        years = {int(value) for value in re.findall(r'\b(?:19|20)\d{2}\b', text)}
        if len(years) == 1:
          result_years.update(years)
    if len(result_years) == 1:
      return result_years.pop()
    for heading in soup.find_all(['h1', 'h2', 'h3', 'title']):
      text = normalize_line(heading.get_text(' ', strip=True))
      if re.search(r'booksellers|book sellers|bba', text, re.I):
        year = self.year_from_text(text)
        if year is not None:
          return year
    years = set()
    for node in soup.find_all(['p', 'td']):
      text = normalize_heading(node.get_text(' ', strip=True))
      if len(text) > 350 or not re.search(r'\bbookseller(?:s| s)? best\b', text):
        continue
      match = re.search(r'\b(?:finalists?|winners?)\s+(?:for|of)\s+(?:the\s+)?((?:19|20)\d{2})\b', text)
      if match:
        years.add(int(match.group(1)))
    if len(years) == 1:
      return years.pop()
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
      section_result = self.result_before_node(heading, result)
      section_year = self.year_before_node(heading, year)
      section_has_rows = False
      for node in heading.next_siblings:
        name = getattr(node, 'name', None)
        if name in {'h1', 'h2', 'h3', 'h4', 'h5'}:
          break
        if name not in {'p', 'div', 'ul', 'ol', 'h6'}:
          continue
        parsed_rows = self.rows_from_node(node, source_url, section_year, category, section_result, len(rows))
        rows.extend(parsed_rows)
        if not parsed_rows and section_has_rows:
          break
        section_has_rows = section_has_rows or bool(parsed_rows)
    return rows

  def result_before_node(self, node, default):
    # One annual section can show winners followed by the full finalist roster.
    for previous in node.previous_elements:
      name = getattr(previous, 'name', None)
      if name not in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p'):
        continue
      text = normalize_heading(previous.get_text(' ', strip=True))
      if len(text) > 220:
        continue
      label = (name != 'p' or previous.find(['strong', 'b']) is not None)
      match = re.search(r'\b(winners?|finalists?)$', text) if label else None
      if match is None:
        match = re.search(r'\bannounce(?:s)? (?:the )?(winners?|finalists?)\b', text)
      if match is not None:
        return RESULT_WINNER if match.group(1).startswith('winner') else RESULT_SHORTLISTED
    return default

  def year_before_node(self, node, default):
    for previous in node.previous_elements:
      if getattr(previous, 'name', None) not in ('h1', 'h2', 'h3', 'h4', 'h5', 'p'):
        continue
      text = normalize_heading(previous.get_text(' ', strip=True))
      if (len(text) <= 350 and re.search(r'\bbookseller(?:s| s)? best\b', text)
          and re.search(r'\b(?:finalists?|winners?)\b', text)):
        years = {int(value) for value in re.findall(r'\b(?:19|20)\d{2}\b', text)}
        if len(years) == 1:
          return years.pop()
    return default

  def parse_legacy_paragraphs(self, soup, source_url, year, result, source_order_start=0):
    rows = []
    for paragraph in soup.find_all('p'):
      category = self.category_from_paragraph(paragraph)
      if not category:
        continue
      section_result = self.result_before_node(paragraph, result)
      section_year = self.year_before_node(paragraph, year)
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
          section_year, title, author, category, section_result, source_url,
          source_order_start + len(rows)))
    return rows

  def category_from_paragraph(self, paragraph):
    for fragment in paragraph.find_all(['font', 'strong', 'b', 'i', 'em']):
      category = self.category_from_text(fragment.get_text(' ', strip=True))
      if category:
        return category
    lines = self.paragraph_lines(paragraph)
    return self.category_from_text(lines[0]) if lines else ''

  def parse_inline_category_rows(self, soup, source_url, year, result, source_order_start=0):
    rows = []
    for paragraph in soup.find_all('p'):
      for line in self.paragraph_lines(paragraph):
        match = re.match(r'^(.+?)\s+[-\u2013\u2014]\s+(.+)$', line)
        category = self.category_from_text(match.group(1)) if match else ''
        if not category:
          continue
        credit = re.split(r',\s*Editor\s+', match.group(2), maxsplit=1, flags=re.I)[0]
        credit = re.sub(r'\s+\ufffd\s+', ' - ', credit)
        parsed = self.title_author_from_text(credit)
        row_year = self.year_before_node(paragraph, year)
        # This single official 2013 row omits its title/byline separator.
        if row_year == 2013 and category == 'Traditional' and credit == 'The Nanny Who Saved Christmas Michelle Douglas':
          parsed = ('The Nanny Who Saved Christmas', 'Michelle Douglas')
        if parsed is not None:
          rows.append(self.row(row_year, *parsed, category,
            self.result_before_node(paragraph, result), source_url, source_order_start + len(rows)))
    return rows

  def paragraph_lines(self, node):
    fragment = BeautifulSoup(str(node), 'html.parser')
    # Source formatting newlines are HTML whitespace; only BR splits entries.
    for text in fragment.find_all(string=True):
      text.replace_with(re.sub(r'\s+', ' ', str(text)))
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
      author = self.author_before_emphasis(emphasis) or self.author_after_emphasis(emphasis)
      if author:
        rows.append((title, author))
    return tuple(rows)

  def author_before_emphasis(self, emphasis):
    parts = []
    for sibling in emphasis.previous_siblings:
      if getattr(sibling, 'name', None) == 'em':
        break
      if getattr(sibling, 'name', None) == 'br' and any(part.strip(' ,') for part in parts):
        break
      parts.append(sibling.get_text(' ', strip=True) if hasattr(sibling, 'get_text') else str(sibling))
    text = normalize_line(' '.join(reversed(parts)))
    if not text.endswith(',') or len(text) > 160:
      return ''
    author = self.clean_author(text[:-1])
    return '' if normalize_heading(author) in ('winner', 'finalist', 'shortlist') else author

  def author_after_emphasis(self, emphasis):
    parts = []
    for sibling in emphasis.next_siblings:
      if getattr(sibling, 'name', None) == 'em':
        break
      parts.append(sibling.get_text(' ', strip=True) if hasattr(sibling, 'get_text') else str(sibling))
    text = normalize_line(' '.join(parts))
    text = re.sub(r'^(?:by|[-\u2013\u2014,])\s*', '', text, flags=re.I).strip()
    if ',' in text and not is_author_suffix(text.rsplit(',',1)[-1]):
      text = text.rsplit(',', 1)[-1].strip()
    text = re.sub(r'^\s*(?:and|&)\s+', '', text, flags=re.I).strip()
    text = re.sub(r'\s+(?:and|&)\s*$', '', text, flags=re.I).strip()
    return self.clean_author(text)

  def title_author_from_text(self, text):
    text = normalize_line(text)
    if (not text or self.category_from_text(text) or
        (text.startswith('(') and text.endswith(')'))):
      return None
    reverse = re.match(r'^(.+?),\s*["\u201c](.+?)["\u201d]\s*$', text)
    if reverse is not None:
      return self.clean_title(reverse.group(2)), self.clean_author(reverse.group(1))
    # The 2014 roster puts its separating comma inside the quoted title.
    match = re.match(r'^["\u201c](.+?)["\u201d]\s*,?\s+(.+)$', text)
    if match is None and self.skip_line(text):
      return None
    if match is None:
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
    value = re.sub(r'\s*\*+$', '', value).strip()
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
      return UnicodeDammit(source).unicode_markup or ''
    return source or ''


def parse_booksellers_best(
    html, base_url=BOOKSELLERS_BEST_CDX_URL,
    name=BOOKSELLERS_BEST_AWARD_NAME, fetch_url=None, pages=None):
  return BooksellersBestAwardParser().parse(
    html, base_url, name, fetch_url=fetch_url, pages=pages)
