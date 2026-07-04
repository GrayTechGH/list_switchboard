#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Goodreads Choice Awards parser.

Maintenance notes:
- Goodreads is the runtime source for this recipe family. The yearly overview
  pages discover category result pages, and category pages expose winners plus
  an "All Nominees" card stream.
- Wikipedia is useful as category-history reference only; it is winner-focused
  and should not be wired as a replacement fallback for nominee-complete imports.
- Visible import labels may mark discontinued categories, but parsed award
  metadata stores the source category name without that label suffix.
"""

from datetime import date
import re
from urllib.parse import urljoin

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


AWARD_NAME = 'Goodreads Choice Awards'
FIRST_AWARD_YEAR = 2009
CHOICE_AWARDS_URL = 'https://www.goodreads.com/choiceawards'
OVERVIEW_URL_TEMPLATE = 'https://www.goodreads.com/choiceawards/best-books-{year}'


def goodreads_choice_overview_url(year):
  return OVERVIEW_URL_TEMPLATE.format(year=int(year))


def goodreads_choice_candidate_years(today=None):
  today = today or date.today()
  return range(FIRST_AWARD_YEAR, today.year + 1)


def category_key(value):
  key = normalize_heading(value)
  key = key.replace('sci fi', 'science fiction')
  key = key.replace('scifi', 'science fiction')
  key = key.replace('non fiction', 'nonfiction')
  key = key.replace('childrens', 'children s')
  key = key.replace('graphic novel and comics', 'graphic novels and comics')
  key = key.replace('memoir and autobiography', 'memoir')
  key = key.replace('memoir autobiography', 'memoir')
  return re.sub(r'\s+', ' ', key).strip()


def clean_category_text(value):
  value = normalize_line(value)
  value = re.sub(r'\s*[✓✔]\s*', ' ', value)
  value = re.sub(r'\s*(?:view results?|results?)\s*[→>-]*\s*$', '', value, flags=re.I)
  value = re.sub(r'^\s*readers[’\']?\s+favorite\s+', '', value, flags=re.I)
  value = re.sub(r'^\s*best\s+', '', value, flags=re.I)
  value = re.sub(r'\s+books?\s*$', '', value, flags=re.I)
  return normalize_line(value).strip(' "\'\u2018\u2019\u201c\u201d,:')


def year_from_text(value):
  match = re.search(r'(?:19|20)\d{2}', value or '')
  return int(match.group(0)) if match is not None else None


class GoodreadsChoiceAwardsParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def __init__(self, category, category_aliases=()):
    self.category = category
    self.category_aliases = tuple(category_aliases or (category,))
    self.category_keys = {
      category_key(alias)
      for alias in self.category_aliases
    }

  def parse(
      self, html, base_url=CHOICE_AWARDS_URL, name=AWARD_NAME,
      fetch_url=None, log=None, progress=None, overview_pages=None,
      category_pages=None):
    notes = []
    rows = []
    if category_pages is not None:
      rows.extend(self.parse_category_pages(category_pages))
    else:
      pages = (
        tuple(overview_pages)
        if overview_pages is not None
        else self.overview_pages(html, base_url, fetch_url, notes, progress))
      rows.extend(self.fetch_category_rows(pages, fetch_url, notes, log, progress))
    rows = self.dedupe_rows(rows)
    entries = self.entries_from_rows(rows)
    if not entries:
      notes.append(f'No Goodreads Choice Awards rows were parsed for {self.category}.')
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def overview_pages(self, html, base_url, fetch_url, notes, progress):
    if fetch_url is None:
      return ((base_url, html),)
    pages = [(base_url, html)] if html else []
    years = tuple(goodreads_choice_candidate_years())
    total = len(years)
    for index, year in enumerate(years, 1):
      url = goodreads_choice_overview_url(year)
      try:
        if progress is not None:
          progress(index, total, f'Fetching Goodreads Choice Awards {year}')
        page_html = html if self.same_url(url, base_url) else fetch_url(url)
        pages.append((url, page_html))
      except Exception as err:
        notes.append(f'Goodreads Choice Awards overview could not be fetched: {url}: {err}')
    return tuple(pages)

  def same_url(self, left, right):
    return (left or '').rstrip('/') == (right or '').rstrip('/')

  def fetch_category_rows(self, overview_pages, fetch_url, notes, log, progress):
    rows = []
    links = []
    for page_url, page_html in overview_pages:
      links.extend(self.discover_category_links(page_html, page_url))
    total = len(links)
    for index, link in enumerate(links, 1):
      try:
        if fetch_url is None:
          continue
        if progress is not None:
          progress(index, total, f'Fetching {self.category} result page {index} of {total}')
        page_html = fetch_url(link['url'])
        rows.extend(self.parse_category_page(
          page_html,
          link['url'],
          fallback_year=link['year'],
          fallback_category=link['category']))
      except Exception as err:
        notes.append(
          f'Goodreads Choice Awards category page could not be fetched: '
          f'{link["url"]}: {err}')
        if log is not None:
          log(f'Goodreads Choice Awards category page failed: {link["url"]}: {err}')
    return rows

  def discover_category_links(self, html, base_url):
    soup = BeautifulSoup(html or '', 'html.parser')
    fallback_year = year_from_text(base_url) or year_from_text(soup.get_text(' ', strip=True))
    links = []
    seen = set()
    for link in soup.find_all('a', href=True):
      href = urljoin(base_url, link['href'])
      if '/choiceawards/' not in href:
        continue
      link_year = year_from_text(href) or fallback_year
      if link_year is None:
        continue
      text = clean_category_text(link.get_text(' ', strip=True))
      if not text or self.skip_overview_link(text, href):
        continue
      if not self.category_matches(text):
        continue
      key = (link_year, href)
      if key in seen:
        continue
      seen.add(key)
      links.append({
        'year': link_year,
        'category': text,
        'url': href,
      })
    return tuple(sorted(links, key=lambda item: (item['year'], item['url'])))

  def skip_overview_link(self, text, href):
    key = normalize_heading(text)
    href_key = normalize_heading(href)
    if re.fullmatch(r'(?:19|20)\d{2} awards?', key):
      return True
    if key in {'view results', 'rules and eligibility', 'learn more'}:
      return True
    return 'best books' in href_key and not self.category_matches(text)

  def category_matches(self, value):
    return category_key(value) in self.category_keys

  def parse_category_pages(self, pages):
    rows = []
    if isinstance(pages, dict):
      pages = pages.items()
    for page_url, page_html in pages:
      rows.extend(self.parse_category_page(page_html, page_url))
    return rows

  def parse_category_page(
      self, html, page_url, fallback_year=None, fallback_category=None):
    soup = BeautifulSoup(html or '', 'html.parser')
    year = fallback_year or year_from_text(page_url) or year_from_text(self.clean_text(soup.find('title')))
    if year is None:
      return []
    page_category = (
      self.detect_page_category(soup)
      or fallback_category
      or self.category)
    rows = self.book_rows_from_cards(soup, page_url, year, page_category)
    return self.dedupe_rows(rows)

  def detect_page_category(self, soup):
    for node in soup.find_all(['h1', 'h2', 'h3']):
      text = clean_category_text(self.clean_text(node))
      if text and self.category_matches(text):
        return text
    title_text = clean_category_text(self.clean_text(soup.find('title')))
    return title_text if title_text and self.category_matches(title_text) else ''

  def book_rows_from_cards(self, soup, page_url, year, category):
    nodes = list(soup.descendants)
    nominee_marker = self.first_marker_index(nodes, r'\ball nominees\b')
    winner_marker = self.first_marker_index(nodes, r'\bwinner\b')
    rows = []
    for image in soup.find_all(['img']):
      parsed = self.book_from_image(image, page_url)
      if parsed is None:
        continue
      node_index = self.node_index(nodes, image)
      result = self.result_for_node_index(node_index, winner_marker, nominee_marker, rows)
      rows.append(self.row(
        year,
        parsed['title'],
        parsed['author'],
        category,
        result,
        parsed['source_url'],
        len(rows),
        votes=self.votes_near_node(image)))
    return rows

  def first_marker_index(self, nodes, pattern):
    for index, node in enumerate(nodes):
      if not isinstance(node, str):
        continue
      if re.search(pattern, normalize_line(node), re.I):
        return index
    return None

  def node_index(self, nodes, target):
    try:
      return nodes.index(target)
    except ValueError:
      return len(nodes)

  def result_for_node_index(self, node_index, winner_marker, nominee_marker, rows):
    if winner_marker is None:
      return RESULT_WINNER if not rows else RESULT_NOMINEE
    if nominee_marker is None:
      return RESULT_WINNER if node_index > winner_marker and not rows else RESULT_NOMINEE
    if winner_marker < node_index < nominee_marker:
      return RESULT_WINNER
    return RESULT_NOMINEE

  def book_from_image(self, image, page_url):
    alt_title, alt_author = self.title_author_from_alt(image.get('alt') or '')
    if not alt_title or not alt_author:
      return None
    card = self.card_for_image(image)
    title = alt_title
    author = alt_author
    source_url = self.link_for_node(image, page_url)
    explicit = self.explicit_title_author(card, page_url)
    if explicit is not None:
      title, author, source_url = explicit
    title = self.clean_title(title)
    author = self.clean_author(author)
    if not title or not author:
      return None
    return {
      'title': title,
      'author': author,
      'source_url': source_url or page_url,
    }

  def card_for_image(self, image):
    current = image
    for _level in range(5):
      if current is None:
        break
      text = self.clean_text(current)
      if re.search(r'\b\d[\d,]*\s+votes?\b', text, re.I):
        return current
      current = current.parent
    return image.parent or image

  def explicit_title_author(self, card, page_url):
    if card is None:
      return None
    title_link = None
    for link in card.find_all('a', href=True):
      href = link.get('href') or ''
      text = self.clean_text(link)
      if '/book/show/' in href and text and not self.link_text_noise(text):
        title_link = link
        break
    author_links = [
      link for link in card.find_all('a', href=True)
      if '/author/show/' in (link.get('href') or '') and self.clean_text(link)
    ]
    if title_link is None or not author_links:
      return None
    title = self.clean_text(title_link)
    author = self.clean_author_text_from_card(card, author_links)
    return (
      title,
      author,
      urljoin(page_url, title_link.get('href') or ''))

  def clean_author_text_from_card(self, card, author_links):
    text = self.clean_text(card)
    by_match = re.search(r'\bby\s+(.+?)(?:\s{2,}|$)', text, re.I)
    if by_match is not None:
      author = self.clean_author(by_match.group(1))
      if author:
        return author
    return self.clean_author(', '.join(self.clean_text(link) for link in author_links))

  def link_text_noise(self, value):
    key = normalize_heading(value)
    return key in {'open preview', 'preview', 'want to read', 'start now'}

  def title_author_from_alt(self, value):
    text = normalize_line(value)
    match = re.match(r'^(.+?)\s+by\s+(.+)$', text, re.I)
    if match is None:
      return '', ''
    return match.group(1), match.group(2)

  def link_for_node(self, node, page_url):
    current = node
    while current is not None:
      if getattr(current, 'name', None) == 'a' and current.get('href'):
        return urljoin(page_url, current['href'])
      current = current.parent
    return page_url

  def votes_near_node(self, node):
    current = node
    for _level in range(5):
      if current is None:
        break
      match = re.search(r'\b(\d[\d,]*)\s+votes?\b', self.clean_text(current), re.I)
      if match is not None:
        return match.group(1).replace(',', '')
      current = current.parent
    return ''

  def clean_text(self, node):
    if node is None:
      return ''
    return normalize_line(node.get_text(' ', strip=True).replace('\xa0', ' '))

  def clean_title(self, value):
    value = normalize_line(value)
    value = re.sub(r'\s+\((?:[^)]*#[^)]+)\)\s*$', '', value)
    return strip_publication_notes(value).strip(' "\'\u2018\u2019\u201c\u201d,:')

  def clean_author(self, value):
    value = normalize_line(value)
    value = re.sub(r'^\s*by\s+', '', value, flags=re.I)
    parts = [
      part.strip()
      for part in re.split(r'\s*,\s*', value)
      if part.strip()
    ]
    author_parts = [
      part for part in parts
      if re.search(r'\(\s*author\s*\)', part, re.I)
    ]
    if not author_parts:
      author_parts = [
        part for part in parts
        if not re.search(r'\(\s*(?:narrator|translator|illustrator|editor)\s*\)', part, re.I)
      ]
    cleaned = []
    for part in author_parts:
      part = re.sub(r'\s*\(\s*(?:goodreads\s+author|author)\s*\)\s*', '', part, flags=re.I)
      part = re.sub(r'\s*\([^)]*\)\s*$', '', part).strip()
      if part:
        cleaned.append(part)
    if cleaned:
      return ' & '.join(cleaned)
    value = re.sub(r'\s*\([^)]*\)\s*', ' ', value)
    return strip_publication_notes(normalize_line(value)).strip(' "\'\u2018\u2019\u201c\u201d,:')

  def row(self, year, title, author, category, result, source_url, source_order, votes=''):
    row = {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': source_url,
      'category': clean_category_text(category) or self.category,
      '_source_order': source_order,
    }
    if votes:
      row['votes'] = votes
    return row

  def dedupe_rows(self, rows):
    deduped = []
    index_by_key = {}
    for row in rows:
      key = (
        row.get('award_year'),
        category_key(row.get('category', '')),
        normalize_heading(row.get('title', '')),
        normalize_heading(row.get('author', '')),
      )
      if not key[2] or not key[3]:
        continue
      existing_index = index_by_key.get(key)
      if existing_index is None:
        index_by_key[key] = len(deduped)
        deduped.append(row)
        continue
      existing = deduped[existing_index]
      if existing.get('result') != RESULT_WINNER and row.get('result') == RESULT_WINNER:
        deduped[existing_index] = row
    return deduped

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(int(row['award_year']), []).append(row)
    entries = []
    for year in sorted(by_year):
      year_rows = sorted(
        by_year[year],
        key=lambda row: (
          0 if row.get('result') == RESULT_WINNER else 1,
          row.get('_source_order', 0)))
      award_rows = []
      for row in year_rows:
        entry_row = {
          key: value
          for key, value in row.items()
          if not key.startswith('_')
        }
        award_rows.append(self.build_award_entry(
          entry_row, row['source_url'], year, row['category']))
      entries.extend(assign_positions(award_rows, year))
    return entries


def parse_goodreads_choice_awards(
    html, category, category_aliases=(), url=CHOICE_AWARDS_URL,
    name=AWARD_NAME, fetch_url=None, overview_pages=None, category_pages=None):
  return GoodreadsChoiceAwardsParser(category, category_aliases).parse(
    html,
    url,
    name,
    fetch_url=fetch_url,
    overview_pages=overview_pages,
    category_pages=category_pages)
