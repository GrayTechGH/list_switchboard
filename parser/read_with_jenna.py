#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Parsers for Read With Jenna monthly and annual junior selections.

Maintenance notes:
- TODAY repeats some older picks in an editorial heading and a commerce card.
  The two versions can differ by subtitle, capitalization, or even a typo.
- Valid picks are month-scoped book headings. Descriptions and footer text can
  also contain ``by`` and must not be treated as title/author rows.
- The junior recipe starts from TODAY's stable Jenna hub, follows the current
  annual page, and recursively reads the official past-edition links.
"""

import re

from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .book_club_base import (
  BookClubParserBase, parse_month, parse_year, split_title_author, text_blocks,
)
from .base import parsed_source

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError
except ImportError:
  from errors import ImportCancelledError


ENTRY_CORRECTIONS = {
  'all adults here': ('All Adults Here', 'Emma Straub'),
  'here for it': ('Here for It', 'R. Eric Thomas'),
  'late migrations': ('Late Migrations', 'Margaret Renkl'),
}

JUNIOR_ANNUAL_URL_RE = re.compile(
  r'/read-(?:with-)?jenna-junior-book-list-(20\d{2})(?:-|/|$)', re.I)
JUNIOR_CATEGORY_LABELS = {
  'picture_book': 'Picture Books',
  'middle_grade': 'Middle Grade',
  'young_adult': 'Young Adult',
}
JUNIOR_CATEGORY_ORDER = tuple(JUNIOR_CATEGORY_LABELS)
JUNIOR_KNOWN_COUNT_MISMATCHES = {('2025', 22, 23)}


class ReadWithJennaParser(BookClubParserBase):

  CLUB_NAME = 'Read With Jenna'
  DEFAULT_SCOPE = 'main_monthly'
  DEFAULT_SELECTION_TYPE = 'monthly_pick'

  def entries_from_soup(self, soup, base_url, scope):
    entries = []
    seen = {}
    current_label = ''
    for node, text in text_blocks(soup):
      if parse_month(text) and parse_year(text) and len(text) < 30:
        current_label = text
        continue
      if not self.is_book_heading(node, text):
        continue
      title, author = split_title_author(text)
      if not title or not author or not current_label:
        continue
      title, author = self.corrected_title_author(title, author)
      entry_url = (
        urljoin(base_url, node.get('href'))
        if getattr(node, 'name', '') == 'a' and node.get('href') else base_url)
      entry = self.build_entry({
        'title': title,
        'author': author,
        'selection_label': current_label,
        'selection_year': parse_year(current_label),
        'selection_month': parse_month(current_label),
      }, f'{current_label} {text}', entry_url, scope, len(entries) + 1, base_url=base_url)
      if entry is not None:
        key = self.selection_key(entry)
        if key in seen:
          if entry.get('source'):
            seen[key]['source'] = entry['source']
          continue
        seen[key] = entry
        entries.append(entry)
    return entries or super().entries_from_soup(soup, base_url, scope)

  def is_book_heading(self, node, text):
    return (
      getattr(node, 'name', '') in {'h2', 'h3', 'h4', 'h5'}
      and re.search(r'\s+by\s+', text, re.I) is not None)

  def title_key(self, title):
    title = title.split(':', 1)[0]
    return re.sub(r'[^a-z0-9]+', ' ', title.casefold()).strip()

  def selection_key(self, entry):
    return (
      entry.get('selection_year', ''),
      entry.get('selection_month', ''),
      self.title_key(entry.get('title', '')),
    )

  def corrected_title_author(self, title, author):
    return ENTRY_CORRECTIONS.get(self.title_key(title), (title, author))

  def accept_entry(self, entry, text):
    normalized = f"{text} {entry.get('selection_label', '')}".casefold().replace('.', '')
    return 'jenna jr' not in normalized and 'read with jenna jr' not in normalized

  def complete_entry(self, entry, text):
    lowered = text.casefold()
    if 'classic' in lowered or entry.get('title') == 'Pride and Prejudice':
      entry['selection_type'] = 'classic_pick'
      entry['scope_flags'] = 'classic'
    if 'essay' in lowered or entry.get('title') == 'Here for It':
      entry['selection_type'] = 'special_pick'
      entry['scope_flags'] = 'essay_collection'
    return entry


class ReadWithJennaJuniorParser(BookClubParserBase):
  """Parse TODAY's year/category Read With Jenna Jr. archive pages."""

  CLUB_NAME = 'Read With Jenna Jr.'
  DEFAULT_SCOPE = 'junior_annual'
  DEFAULT_SELECTION_TYPE = 'annual_pick'

  def parse(
      self, html, base_url, name=None, scope=None, fetch_url=None,
      bootstrap_url=''):
    scope = scope or self.DEFAULT_SCOPE
    notes = []
    initial_soup = BeautifulSoup(html or '<html></html>', 'html.parser')
    initial_year = self.page_year(initial_soup, base_url)
    if initial_year:
      initial_url = self.canonical_url(initial_soup, bootstrap_url or base_url)
      first_page = (initial_year, initial_url, html)
    else:
      current_links = self.annual_links(initial_soup, base_url)
      if not current_links:
        raise ValueError(
          'TODAY did not expose a Read With Jenna Jr. annual-list link.')
      current_year, current_url = max(current_links)
      if fetch_url is None:
        raise ValueError(
          'Read With Jenna Jr. annual discovery requires a fetch callback.')
      first_page = (current_year, current_url, fetch_url(current_url))

    pages = self.collect_annual_pages(first_page, fetch_url, notes)
    positioned = []
    for year, page_url, page_html in sorted(pages, key=lambda item: item[0]):
      page_entries, page_notes = self.entries_from_annual_page(
        page_html, page_url, year, scope, base_url)
      notes.extend(page_notes)
      positioned.extend(page_entries)

    positioned.sort(key=lambda item: (item[0], item[1], item[2]))
    entries = []
    for position, item in enumerate(positioned, 1):
      _year, _category_order, _source_order, entry = item
      entry['position'] = str(position)
      entries.append(entry)
    if not entries:
      raise ValueError('No Read With Jenna Jr. annual selections were found.')
    return {
      'name': name or self.CLUB_NAME,
      'source': parsed_source(name or self.CLUB_NAME, base_url),
      'entries': entries,
      'notes': notes,
      'match_series': False,
    }

  def collect_annual_pages(self, first_page, fetch_url, notes):
    pages = []
    queue = [first_page]
    visited = set()
    visited_years = set()
    while queue:
      year, page_url, page_html = queue.pop(0)
      if page_url in visited or year in visited_years:
        continue
      visited.add(page_url)
      visited_years.add(year)
      pages.append((year, page_url, page_html))
      soup = BeautifulSoup(page_html or '<html></html>', 'html.parser')
      for linked_year, linked_url in self.annual_links(soup, page_url):
        queued = any(
          item[0] == linked_year or item[1] == linked_url for item in queue)
        if linked_year in visited_years or linked_url in visited or queued:
          continue
        if fetch_url is None:
          continue
        try:
          linked_html = fetch_url(linked_url)
        except ImportCancelledError:
          raise
        except Exception as err:
          notes.append(
            f'Read With Jenna Jr. {linked_year} page could not be fetched: {err}')
          continue
        queue.append((linked_year, linked_url, linked_html))
    return pages

  def annual_links(self, soup, base_url):
    links = []
    seen = set()
    for link in soup.find_all('a', href=True):
      parsed_url = urlparse(urljoin(base_url, link.get('href')))
      url = parsed_url._replace(fragment='', query='').geturl()
      match = JUNIOR_ANNUAL_URL_RE.search(parsed_url.path)
      if not match or not self.is_today_url(url) or url in seen:
        continue
      seen.add(url)
      links.append((match.group(1), url))
    return links

  def is_today_url(self, url):
    host = urlparse(url).netloc.casefold().split(':', 1)[0]
    return host in {'today.com', 'www.today.com'}

  def canonical_url(self, soup, fallback_url):
    canonical = soup.find('link', rel=lambda value: value and 'canonical' in value)
    url = (
      urljoin(fallback_url, canonical.get('href'))
      if canonical and canonical.get('href') else fallback_url)
    return url if self.is_today_url(url) else fallback_url

  def page_year(self, soup, page_url=''):
    match = JUNIOR_ANNUAL_URL_RE.search(urlparse(page_url).path)
    if match:
      return match.group(1)
    heading = soup.find('h1')
    return parse_year(heading.get_text(' ', strip=True)) if heading is not None else ''

  def entries_from_annual_page(self, html, page_url, year, scope, list_base_url):
    soup = BeautifulSoup(html or '<html></html>', 'html.parser')
    entries = []
    notes = []
    seen = set()
    category = ''
    category_order = {
      value: index for index, value in enumerate(JUNIOR_CATEGORY_ORDER)
    }
    for heading in soup.find_all(['h2', 'h3', 'h4']):
      text = ' '.join(heading.get_text(' ', strip=True).split())
      boundary = self.category_from_heading(text)
      if boundary:
        category = boundary
        continue
      if not category:
        continue
      title, authors = self.title_authors_from_heading(text)
      if not title or not authors:
        continue
      key = (year, self.title_key(title))
      if key in seen:
        continue
      seen.add(key)
      label = f'{year} {JUNIOR_CATEGORY_LABELS[category]}'
      entry = self.build_entry({
        'title': title,
        'authors': authors,
        'selection_year': year,
        'selection_label': label,
        'selection_type': self.DEFAULT_SELECTION_TYPE,
        'scope_flags': category,
      }, f'{label} {text}', page_url, scope, len(entries) + 1, base_url=list_base_url)
      if entry is not None:
        entries.append((year, category_order[category], len(entries), entry))

    declared_count = self.declared_book_count(soup)
    count_mismatch = (year, declared_count, len(entries))
    if (
        declared_count is not None
        and declared_count != len(entries)
        and count_mismatch not in JUNIOR_KNOWN_COUNT_MISMATCHES):
      notes.append(
        f'Read With Jenna Jr. {year} headline declares {declared_count} books; '
        f'{len(entries)} structured book headings were imported.')
    return entries, notes

  def category_from_heading(self, text):
    normalized = text.casefold()
    if 'picture book' in normalized:
      return 'picture_book'
    if 'middle grade' in normalized:
      return 'middle_grade'
    if 'young adult' in normalized:
      return 'young_adult'
    return ''

  def title_authors_from_heading(self, text):
    quoted = re.match(
      r'^\s*["“”\ufffd](.+?)["“”\ufffd],?\s+by\s+(.+?)\s*$', text, re.I)
    if quoted:
      title, author_text = quoted.groups()
    else:
      if re.search(r'\s+by\s+', text, re.I) is None:
        return '', []
      title, author_text = split_title_author(text)
    author_text = re.sub(
      r'\s+(?:and\s+)?illustrated\s+by\s+.+$', '', author_text, flags=re.I)
    authors = [
      author.strip(' ,;')
      for author in re.split(r'\s*,\s*|\s+(?:and|&)\s+', author_text, flags=re.I)
      if author.strip(' ,;')
    ]
    return title.strip(' "“”\ufffd,;'), list(dict.fromkeys(authors))

  def title_key(self, title):
    title = title.split(':', 1)[0]
    return re.sub(r'[^a-z0-9]+', ' ', title.casefold()).strip()

  def declared_book_count(self, soup):
    heading = soup.find('h1')
    if heading is None:
      return None
    match = re.search(
      r'\bsee\s+all\s+(\d+)\s+books?\b', heading.get_text(' ', strip=True), re.I)
    return int(match.group(1)) if match else None
