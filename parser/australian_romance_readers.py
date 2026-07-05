#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Australian Romance Readers Awards parser.

Maintenance notes:
- The official ARRA WordPress awards pages are the canonical source. The
  LibraryThing award page is sparse and should remain reference-only.
- Shortlist coverage depends on the official yearly page. Recent pages expose
  full category lists; early pages such as 2008 expose winners only.
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


ARRA_AWARD_NAME = 'Australian Romance Readers Awards'
ARRA_AWARDS_URL = 'https://australianromancereaders.com.au/awards/'
ARRA_REST_PAGE_URL = 'https://australianromancereaders.com.au/wp-json/wp/v2/pages?slug={slug}'

RESULT_PRIORITY = {RESULT_WINNER: 0, RESULT_SHORTLISTED: 1}


class AustralianRomanceReadersAwardsParser(AwardParserBase):

  AWARD_NAME = ARRA_AWARD_NAME

  def parse(
      self, html, base_url=ARRA_AWARDS_URL, name=ARRA_AWARD_NAME, fetch_url=None,
      year_pages=None):
    notes = []
    rows = []
    if year_pages is not None:
      rows.extend(self.parse_year_pages(year_pages))
    else:
      year_urls = self.discover_year_urls(html, base_url)
      if fetch_url is not None:
        rows.extend(self.fetch_year_rows(year_urls, fetch_url, notes))
      elif self.page_year(html) is not None:
        rows.extend(self.parse_year_page(html, base_url))
    rows = self.dedupe_rows(rows)
    entries = self.entries_from_rows(rows)
    self.add_coverage_notes(rows, notes)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def discover_year_urls(self, html, base_url):
    soup = BeautifulSoup(html or '', 'html.parser')
    urls = []
    for link in soup.find_all('a', href=True):
      href = urljoin(base_url, link['href'])
      if re.search(r'/awards/(?:19|20)\d{2}-2/?$', href) and href not in urls:
        urls.append(href)
    return tuple(sorted(urls, key=self.year_url_sort_key))

  def year_url_sort_key(self, url):
    year = self.year_from_text(url)
    return year or 0

  def fetch_year_rows(self, year_urls, fetch_url, notes):
    rows = []
    for year_url in year_urls:
      slug = self.slug_from_year_url(year_url)
      try:
        rest_html = fetch_url(ARRA_REST_PAGE_URL.format(slug=slug))
        content_html, source_url = self.rest_page_content(rest_html, year_url)
      except Exception as err:
        notes.append(f'ARRA year page could not be fetched through REST: {year_url}: {err}')
        continue
      rows.extend(self.parse_year_page(content_html, source_url))
    return rows

  def slug_from_year_url(self, url):
    match = re.search(r'/awards/((?:19|20)\d{2}-2)/?$', url or '')
    return match.group(1) if match is not None else ''

  def rest_page_content(self, rest_html, fallback_url):
    try:
      data = json.loads(rest_html or '[]')
    except Exception:
      return rest_html or '', fallback_url
    if isinstance(data, list) and data:
      data = data[0]
    if not isinstance(data, dict):
      return '', fallback_url
    content = data.get('content') if isinstance(data.get('content'), dict) else {}
    return content.get('rendered') or '', data.get('link') or fallback_url

  def parse_year_pages(self, pages):
    rows = []
    for page_url, page_html in pages:
      rows.extend(self.parse_year_page(page_html, page_url))
    return rows

  def parse_year_page(self, html, source_url):
    soup = BeautifulSoup(html or '', 'html.parser')
    year = self.page_year(html) or self.year_from_text(source_url)
    if year is None:
      return []
    rows = []
    rows.extend(self.parse_list_sections(soup, source_url, year))
    rows.extend(self.parse_legacy_blocks(soup, source_url, year, len(rows)))
    rows = self.dedupe_rows(rows)
    self.promote_winner_only_year(rows)
    return rows

  def parse_list_sections(self, soup, source_url, year):
    rows = []
    for item_list in soup.find_all('ul'):
      category = self.find_category_before(item_list)
      if not category or self.skip_category(category):
        continue
      for node in item_list.find_all('li', recursive=False):
        parsed = self.title_author_from_node(node)
        if parsed is None:
          continue
        title, author = parsed
        rows.append(self.row(
          year, title, author, category, self.result_from_node(node),
          source_url, len(rows)))
    return rows

  def find_category_before(self, node):
    parent = node.parent
    current = node.previous_sibling
    while current is not None:
      category = self.category_from_node(current)
      if category:
        return category
      current = current.previous_sibling
    if parent is not None:
      return self.category_from_parent_before(parent, node)
    return ''

  def category_from_parent_before(self, parent, node):
    children = list(parent.children)
    try:
      index = children.index(node)
    except ValueError:
      return ''
    for current in reversed(children[:index]):
      category = self.category_from_node(current)
      if category:
        return category
    return ''

  def category_from_node(self, node):
    if not getattr(node, 'name', None) or node.name in {'ul', 'li', 'table', 'tbody', 'tr', 'td'}:
      return ''
    text = self.clean_category(node.get_text(' ', strip=True))
    return text if self.looks_like_category(text) else ''

  def parse_legacy_blocks(self, soup, source_url, year, source_order_start=0):
    rows = []
    current_category = None
    for block in soup.find_all(['p', 'div', 'h2', 'h3', 'h4']):
      if block.find_parent('li') is not None:
        continue
      if block.name == 'div' and block.find(['p', 'ul', 'table', 'div']):
        continue
      lines = self.block_lines(block)
      if not lines:
        continue
      category = self.category_from_line(lines[0])
      row_lines = lines
      if category:
        current_category = category
        row_lines = lines[1:]
      elif len(lines) == 1 and self.looks_like_category(lines[0]):
        current_category = self.clean_category(lines[0])
        continue
      if not current_category or self.skip_category(current_category):
        continue
      for line in row_lines:
        if self.skip_line(line):
          continue
        parsed = self.title_author_from_text(line)
        if parsed is None:
          continue
        title, author = parsed
        rows.append(self.row(
          year, title, author, current_category,
          self.result_from_text_line(line, block), source_url,
          source_order_start + len(rows)))
    return rows

  def block_lines(self, block):
    copied = BeautifulSoup(str(block), 'html.parser')
    for br in copied.find_all('br'):
      br.replace_with('\n')
    text = copied.get_text('\n', strip=True)
    return [normalize_line(line) for line in text.splitlines() if normalize_line(line)]

  def category_from_line(self, value):
    text = self.clean_category(value)
    return text if self.looks_like_category(text) else ''

  def looks_like_category(self, value):
    heading = normalize_heading(value)
    if not heading:
      return False
    if heading in {'members choice awards'}:
      return False
    if re.fullmatch(r'(?:19|20)\d{2}(?: award winners)?', heading):
      return False
    if any(skip in heading for skip in (
        'sponsored by', 'proudly sponsored', 'winners were announced',
        'winners for', 'nominations for')):
      return False
    return any(word in heading for word in (
      'favourite', 'favorite', 'romance', 'story', 'cover', 'anthology',
      'christmas', 'holiday', 'small town', 'australian set', 'aussie set'))

  def skip_category(self, category):
    heading = normalize_heading(category)
    if 'category series romance' in heading:
      return False
    return any(skip in heading for skip in (
      'continuing romance series',
      'romance author',
      'new romance author',
      'debut romance author',
      'favourite author',
      'favorite author',
      'favourite couple',
      'favorite couple',
      'romance couple',
      'strongest heroine',
      'strongest hero',
    ))

  def skip_line(self, value):
    heading = normalize_heading(value)
    if not heading:
      return True
    return (
      heading == 'members choice categories'
      or heading.startswith('proudly sponsored')
      or heading.startswith('sponsored by')
      or set(heading) == {' '}
      or re.fullmatch(r'\.+', value.strip('. '))
    )

  def title_author_from_node(self, node):
    return self.title_author_from_text(self.row_text(node))

  def row_text(self, node):
    text = node.get_text(' ', strip=True)
    return normalize_line(text)

  def title_author_from_text(self, value):
    value = self.clean_row_text(value)
    if not value:
      return None
    story_match = re.match(
      r'^[\u2018\u2019\'"](.+?)[\u2018\u2019\'"]\s+in\s+.+?\s+by\s+(.+)$',
      value,
      re.I)
    if story_match is not None:
      title = self.clean_title(story_match.group(1))
      author = self.clean_author(story_match.group(2))
      return (title, author) if title and author else None
    match = re.match(r'^(.+?)\s+by\s+(.+)$', value, re.I)
    if match is None:
      return None
    title = self.clean_title(match.group(1))
    author = self.clean_author(match.group(2))
    if not title or not author:
      return None
    return title, author

  def clean_row_text(self, value):
    value = normalize_line(value)
    value = re.sub(r'^\s*(?:winner|runner-up|runners-up)\s*:?\s*', '', value, flags=re.I)
    value = re.sub(r'\s+\((?:self-published|[A-Z][A-Za-z&., ]{2,})\)\s*$', '', value)
    return value.strip()

  def result_from_node(self, node):
    if self.node_has_pink(node) and self.node_has_bold(node):
      return RESULT_WINNER
    return RESULT_SHORTLISTED

  def result_from_text_line(self, line, block):
    if self.line_has_bold_pink(line, block):
      return RESULT_WINNER
    return RESULT_SHORTLISTED

  def line_has_bold_pink(self, line, block):
    normalized_line = normalize_line(line)
    for node in block.find_all(['strong', 'b']):
      if not self.node_or_parent_has_pink(node, block):
        continue
      node_text = normalize_line(node.get_text(' ', strip=True))
      if node_text and (node_text == normalized_line or node_text in normalized_line):
        return True
    return False

  def node_or_parent_has_pink(self, node, stop_node):
    current = node
    while current is not None:
      if self.node_has_pink(current):
        return True
      if current is stop_node:
        return False
      current = current.parent
    return False

  def node_has_pink(self, node):
    for child in [node] + list(node.find_all(True)):
      style = (child.get('style') or '').casefold()
      if '#ff00ff' in style or 'magenta' in style:
        return True
    return False

  def node_has_bold(self, node):
    return node.name in {'strong', 'b'} or node.find(['strong', 'b']) is not None

  def promote_winner_only_year(self, rows):
    by_category = {}
    for row in rows:
      by_category.setdefault(row['category'], []).append(row)
    if not rows or any(row.get('result') == RESULT_WINNER for row in rows):
      return
    if all(len(category_rows) == 1 for category_rows in by_category.values()):
      for row in rows:
        row['result'] = RESULT_WINNER

  def row(self, year, title, author, category, result, source_url, source_order):
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': source_url,
      'category': self.clean_category(category),
      '_source_order': source_order,
    }

  def clean_category(self, value):
    value = normalize_line(value).replace('\u2013', '-').replace('\u2014', '-')
    value = re.sub(r'\s+for\s+(?:19|20)\d{2}$', '', value, flags=re.I)
    if re.search(r'\bpublished\s+in\s+(?:19|20)\d{2}$', value, re.I) is None:
      value = re.sub(r'\s+(?:19|20)\d{2}$', '', value)
    value = re.sub(r'\s+-\s+proudly sponsored by .+$', '', value, flags=re.I)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,:')

  def clean_title(self, value):
    value = normalize_line(value)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,:')

  def clean_author(self, value):
    value = strip_publication_notes(normalize_line(value))
    value = re.sub(r'\s+in\s+.+$', '', value, flags=re.I)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,:')

  def page_year(self, value):
    return self.year_from_text(value)

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
      notes.append('No ARRA rows were parsed from the official awards pages.')
      return
    by_year = {}
    for row in rows:
      by_year.setdefault(int(row['award_year']), []).append(row)
    shortlist_years = [
      year for year, year_rows in sorted(by_year.items())
      if any(row.get('result') == RESULT_SHORTLISTED for row in year_rows)
    ]
    winner_only_years = [
      year for year, year_rows in sorted(by_year.items())
      if year_rows and not any(row.get('result') == RESULT_SHORTLISTED for row in year_rows)
    ]
    if shortlist_years:
      notes.append(
        'Official ARRA nominee/shortlist-style category lists were parsed for: ' +
        ', '.join(str(year) for year in shortlist_years) + '.')
    if winner_only_years:
      notes.append(
        'Official ARRA winner-only pages were parsed for: ' +
        ', '.join(str(year) for year in winner_only_years) + '.')
    notes.append(
      'LibraryThing, FictionDB, news, and social sources are reference-only for this recipe.')


def parse_australian_romance_readers_awards(
    html, base_url=ARRA_AWARDS_URL, name=ARRA_AWARD_NAME, fetch_url=None,
    year_pages=None):
  return AustralianRomanceReadersAwardsParser().parse(
    html, base_url, name, fetch_url=fetch_url, year_pages=year_pages)
