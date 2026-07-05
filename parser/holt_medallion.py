#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
HOLT Medallion parser.

Maintenance notes:
- Virginia Romance Writers' official WordPress pages are the canonical source.
- Official shortlist coverage is uneven but parseable where VRW exposes
  finalist pages: 2018-2023 and 2025-2026 via discovered pages, plus 2013-2017
  Award of Merit finalists on the Past Winners page.
- LibraryThing has sparse HOLT data and is intentionally reference-only.
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


HOLT_AWARD_NAME = 'HOLT Medallion'
HOLT_URL = 'https://virginiaromancewriters.com/holt-medallion/'
HOLT_SEARCH_URL = (
  'https://virginiaromancewriters.com/wp-json/wp/v2/search?search=HOLT&per_page=100')

RESULT_PRIORITY = {RESULT_WINNER: 0, RESULT_SHORTLISTED: 1}


class HOLTMedallionParser(AwardParserBase):

  AWARD_NAME = HOLT_AWARD_NAME

  def parse(
      self, html, base_url=HOLT_URL, name=HOLT_AWARD_NAME, fetch_url=None,
      pages=None):
    notes = []
    if pages is None:
      page_refs = self.discover_page_refs(html, base_url, fetch_url, notes)
      rows = self.fetch_page_rows(page_refs, fetch_url, notes) if fetch_url else []
      if not rows:
        rows = self.parse_content_page(html, base_url, '')
    else:
      rows = []
      for page_url, page_html in pages:
        rows.extend(self.parse_content_page(page_html, page_url, ''))

    rows = self.dedupe_rows(self.with_source_order(rows))
    entries = self.entries_from_rows(rows)
    self.add_coverage_notes(rows, notes)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def discover_page_refs(self, html, base_url, fetch_url, notes):
    refs = []
    refs.extend(self.refs_from_landing_page(html, base_url))
    if fetch_url is not None:
      try:
        refs.extend(self.refs_from_search_json(fetch_url(HOLT_SEARCH_URL)))
      except Exception as err:
        notes.append(f'Official VRW HOLT search endpoint could not be fetched: {err}')
    return self.dedupe_refs(refs)

  def refs_from_landing_page(self, html, base_url):
    soup = BeautifulSoup(html or '', 'html.parser')
    refs = []
    for link in soup.find_all('a', href=True):
      text = normalize_line(link.get_text(' ', strip=True))
      href = urljoin(base_url, link['href'])
      if self.accept_page_title(text, href):
        refs.append({'title': text, 'url': href, 'rest_url': ''})
    return refs

  def refs_from_search_json(self, value):
    try:
      data = json.loads(value or '[]')
    except Exception:
      return []
    refs = []
    for item in data if isinstance(data, list) else []:
      if not isinstance(item, dict):
        continue
      title = normalize_line(item.get('title') or '')
      url = item.get('url') or ''
      if not self.accept_page_title(title, url):
        continue
      rest_url = ''
      links = item.get('_links') if isinstance(item.get('_links'), dict) else {}
      self_links = links.get('self') if isinstance(links.get('self'), list) else []
      if self_links and isinstance(self_links[0], dict):
        rest_url = self_links[0].get('href') or ''
      refs.append({'title': title, 'url': url, 'rest_url': rest_url})
    return refs

  def accept_page_title(self, title, url):
    text = normalize_heading(f'{title} {url}')
    if 'holt' not in text:
      return False
    if any(skip in text for skip in (
        'payment', 'score sheet', 'judge', 'contest time', 'time running',
        'about us', 'welcome')):
      return False
    return any(word in text for word in (
      'finalist', 'finalists', 'winner', 'winners', 'awards', 'past winners'))

  def dedupe_refs(self, refs):
    deduped = []
    index_by_url = {}
    for ref in refs:
      url = ref.get('url') or ref.get('rest_url') or ''
      if not url:
        continue
      existing_index = index_by_url.get(url)
      if existing_index is not None:
        if ref.get('rest_url') and not deduped[existing_index].get('rest_url'):
          deduped[existing_index] = ref
        continue
      index_by_url[url] = len(deduped)
      deduped.append(ref)
    return tuple(sorted(deduped, key=self.ref_sort_key))

  def ref_sort_key(self, ref):
    year = self.year_from_text(ref.get('title') or ref.get('url') or '') or 0
    title = normalize_heading(ref.get('title') or '')
    kind_order = 0
    if 'past winners' in title:
      kind_order = -1
    elif 'finalist' in title:
      kind_order = 0
    elif 'winner' in title or 'award' in title:
      kind_order = 1
    return (year, kind_order, title)

  def fetch_page_rows(self, page_refs, fetch_url, notes):
    rows = []
    for ref in page_refs:
      rest_url = ref.get('rest_url') or ref.get('url') or ''
      try:
        content_html, source_url, title = self.rest_page_content(
          fetch_url(rest_url), ref.get('url') or rest_url, ref.get('title') or '')
      except Exception as err:
        notes.append(f'Official VRW HOLT page could not be fetched: {ref.get("url")}: {err}')
        continue
      page_rows = self.parse_content_page(content_html, source_url, title)
      if not page_rows and self.video_only_awards_page(content_html, title, source_url):
        year = self.year_from_text(title or source_url)
        if year is not None:
          notes.append(
            f'Official VRW HOLT {year} awards page did not expose text winner rows; '
            'it appears to be video-only.')
      rows.extend(page_rows)
    return rows

  def rest_page_content(self, rest_html, fallback_url, fallback_title):
    try:
      data = json.loads(rest_html or '{}')
    except Exception:
      return rest_html or '', fallback_url, fallback_title
    if isinstance(data, list) and data:
      data = data[0]
    if not isinstance(data, dict):
      return '', fallback_url, fallback_title
    content = data.get('content') if isinstance(data.get('content'), dict) else {}
    title = data.get('title') if isinstance(data.get('title'), dict) else {}
    return (
      content.get('rendered') or '',
      data.get('link') or fallback_url,
      title.get('rendered') or fallback_title,
    )

  def video_only_awards_page(self, html, title, source_url):
    text = normalize_heading(f'{title} {source_url}')
    if 'finalist' in text:
      return False
    if 'award' not in text and 'winner' not in text:
      return False
    soup = BeautifulSoup(html or '', 'html.parser')
    return soup.find('video') is not None and not self.parse_award_winner_sections(
      soup, source_url, self.year_from_text(title or source_url) or 0)

  def parse_content_page(self, html, source_url, title=''):
    soup = BeautifulSoup(html or '', 'html.parser')
    title_text = normalize_line(BeautifulSoup(title or '', 'html.parser').get_text(' ', strip=True))
    page_text = normalize_heading(f'{title_text} {source_url}')
    html_text = normalize_heading(html[:2000])
    if 'past winners' in page_text:
      return self.parse_past_winners_page(soup, source_url)

    year = self.year_from_text(title_text) or self.year_from_text(source_url) or self.year_from_text(html)
    if year is None:
      return []
    if 'finalist' in page_text or 'finalist' in html_text:
      rows = []
      rows.extend(self.parse_list_sections(soup, source_url, year))
      rows.extend(self.parse_table_finalists(soup, source_url, year, len(rows)))
      rows.extend(self.parse_heading_rows(soup, source_url, year, len(rows)))
      return self.dedupe_rows(rows)
    if 'award' in page_text or 'winner' in page_text:
      rows = self.parse_award_winner_sections(soup, source_url, year)
      if rows:
        return self.dedupe_rows(rows)
    rows = self.parse_list_sections(soup, source_url, year)
    return self.dedupe_rows(rows)

  def parse_list_sections(self, soup, source_url, year):
    rows = []
    for item_list in soup.find_all('ul'):
      if item_list.find_parent('li') is not None:
        continue
      category = self.find_category_before(item_list)
      if not category:
        continue
      for item in item_list.find_all('li', recursive=False):
        parsed = self.title_author_from_node(item)
        if parsed is None:
          continue
        title, author = parsed
        rows.append(self.row(
          year, title, author, category, RESULT_SHORTLISTED, source_url, len(rows)))
    return rows

  def parse_heading_rows(self, soup, source_url, year, source_order_start=0):
    rows = []
    headings = soup.find_all(['h2', 'h3', 'h4'])
    for heading in headings:
      category = self.category_from_node(heading)
      if not category:
        continue
      for sibling in heading.next_siblings:
        if getattr(sibling, 'name', None) in {'h1', 'h2', 'h3', 'h4', 'ul', 'table'}:
          break
        if getattr(sibling, 'name', None) not in {'h5', 'p', 'div'}:
          continue
        parsed = self.title_author_from_node(sibling)
        if parsed is None:
          continue
        title, author = parsed
        rows.append(self.row(
          year, title, author, category, RESULT_SHORTLISTED, source_url,
          source_order_start + len(rows)))
    return rows

  def parse_table_finalists(self, soup, source_url, year, source_order_start=0):
    rows = []
    for table in soup.find_all('table'):
      current_category = ''
      for tr in table.find_all('tr'):
        cells = tr.find_all(['td', 'th'], recursive=False)
        if not cells:
          continue
        row_text = normalize_line(' '.join(cell.get_text(' ', strip=True) for cell in cells))
        category = self.category_from_text(cells[0].get_text(' ', strip=True))
        if category and (len(cells) == 1 or normalize_heading(cells[-1].get_text(' ', strip=True)) == 'author'):
          current_category = category
          continue
        if not current_category or len(cells) < 2:
          continue
        title = self.clean_title(self.inline_text(cells[0]))
        author = self.clean_author(self.inline_text(cells[1]))
        if title and author and not self.skip_row_text(title):
          rows.append(self.row(
            year, title, author, current_category, RESULT_SHORTLISTED, source_url,
            source_order_start + len(rows)))
    return rows

  def parse_award_winner_sections(self, soup, source_url, year):
    rows = []
    for heading in soup.find_all(['h2', 'h3', 'h4']):
      category = self.category_from_node(heading)
      if not category:
        continue
      for sibling in heading.next_siblings:
        if getattr(sibling, 'name', None) in {'hr', 'h1', 'h2', 'h3', 'h4'}:
          break
        if getattr(sibling, 'name', None) not in {'p', 'li', 'h5', 'div'}:
          continue
        parsed = self.title_author_from_node(sibling)
        if parsed is None:
          continue
        title, author = parsed
        rows.append(self.row(
          year, title, author, category, RESULT_WINNER, source_url, len(rows)))
        break
    return rows

  def parse_past_winners_page(self, soup, source_url):
    rows = []
    container = soup.find('div') or soup
    current_year = None
    current_category = ''
    current_result = None
    handled_tables = set()

    for child in container.children:
      if not getattr(child, 'name', None):
        text = normalize_line(str(child))
        parsed = self.title_author_from_text(text)
        if current_year and current_category and current_result and parsed is not None:
          rows.append(self.row(
            current_year, parsed[0], parsed[1], current_category, current_result,
            source_url, len(rows)))
        continue

      if child.name == 'table':
        handled_tables.add(id(child))
        rows.extend(self.parse_past_table(
          child, source_url, current_year, len(rows)))
        continue

      text = normalize_line(child.get_text(' ', strip=True))
      year = self.past_year_from_text(text)
      if year is not None:
        current_year = year
        current_category = ''
        current_result = None
        continue

      if child.name == 'ul':
        if current_year and current_category:
          rows.extend(self.parse_past_list(
            child, source_url, current_year, current_category, len(rows)))
        current_result = None
        continue

      category = self.category_from_text(text)
      if category:
        current_category = category
        if re.search(r'\bwinner\b', text, re.I):
          current_result = RESULT_WINNER
        continue

      if self.is_winner_marker(text):
        current_result = RESULT_WINNER
        continue
      if self.is_merit_marker(text):
        current_result = RESULT_SHORTLISTED
        continue

      parsed = self.title_author_from_node(child)
      if current_year and current_category and current_result and parsed is not None:
        rows.append(self.row(
          current_year, parsed[0], parsed[1], current_category, current_result,
          source_url, len(rows)))
        if current_result == RESULT_WINNER:
          current_result = None

    for table in container.find_all('table'):
      if id(table) not in handled_tables:
        rows.extend(self.parse_past_table(table, source_url, current_year, len(rows)))
    rows.extend(self.parse_past_lines(container, source_url, len(rows)))
    return self.dedupe_rows(rows)

  def parse_past_table(self, table, source_url, current_year, source_order_start=0):
    rows = []
    category = ''
    for tr in table.find_all('tr'):
      header = tr.find('th')
      if header is not None:
        category = self.clean_category(header.get_text(' ', strip=True))
        continue
      td = tr.find('td')
      if td is None or not current_year or not category:
        continue
      text = normalize_line(td.get_text(' ', strip=True))
      winner_match = re.search(
        r'\bWinner\b\s+(.+?)(?:\s+Award of Merit Finalists?|$)', text, re.I)
      if winner_match is not None:
        parsed = self.title_author_from_text(winner_match.group(1))
        if parsed is not None:
          rows.append(self.row(
            current_year, parsed[0], parsed[1], category, RESULT_WINNER, source_url,
            source_order_start + len(rows)))
      for item in td.find_all('li'):
        parsed = self.title_author_from_node(item)
        if parsed is None:
          continue
        rows.append(self.row(
          current_year, parsed[0], parsed[1], category, RESULT_SHORTLISTED, source_url,
          source_order_start + len(rows)))
    return rows

  def parse_past_lines(self, container, source_url, source_order_start=0):
    rows = []
    current_year = None
    current_category = ''
    current_result = None
    for line in self.block_lines(container):
      year = self.past_year_from_text(line)
      if year is not None:
        current_year = year
        current_category = ''
        current_result = None
        continue
      category = self.category_from_text(line)
      if category:
        current_category = category
        current_result = RESULT_WINNER if re.search(r'\bwinner\b', line, re.I) else None
        continue
      if self.is_winner_marker(line):
        current_result = RESULT_WINNER
        continue
      if self.is_merit_marker(line):
        current_result = RESULT_SHORTLISTED
        continue
      parsed = self.title_author_from_text(line)
      if current_year and current_category and current_result and parsed is not None:
        rows.append(self.row(
          current_year, parsed[0], parsed[1], current_category, current_result,
          source_url, source_order_start + len(rows)))
        if current_result == RESULT_WINNER:
          current_result = None
    return rows

  def parse_past_list(self, item_list, source_url, year, category, source_order_start=0):
    rows = []
    for item in item_list.find_all('li', recursive=False):
      parsed = self.title_author_from_node(item)
      if parsed is None:
        continue
      rows.append(self.row(
        year, parsed[0], parsed[1], category, RESULT_SHORTLISTED, source_url,
        source_order_start + len(rows)))
    return rows

  def find_category_before(self, node):
    for previous in node.find_all_previous(['h1', 'h2', 'h3', 'h4', 'h5', 'p', 'strong', 'b']):
      if previous.find_parent('li') is not None:
        continue
      category = self.category_from_node(previous)
      if category:
        return category
    return ''

  def category_from_node(self, node):
    if not getattr(node, 'name', None):
      return ''
    return self.category_from_text(node.get_text(' ', strip=True))

  def category_from_text(self, value):
    text = self.clean_category(value)
    if self.looks_like_category(text):
      return text
    return ''

  def clean_category(self, value):
    value = normalize_line(value)
    value = re.sub(r'\b(?:Winner|Award of Merit Finalists?)\b', '', value, flags=re.I)
    value = re.sub(r'\b(?:19|20)\d{2}\b', '', value)
    value = value.replace('\u2013', '-').replace('\u2014', '-')
    return normalize_line(value).strip(' "\'\u2018\u2019\u201c\u201d,:-/')

  def looks_like_category(self, value):
    heading = normalize_heading(value)
    if not heading:
      return False
    if any(skip in heading for skip in (
        'congratulations', 'winners announced', 'thank you', 'alphabetical',
        'holt medallion', 'award of merit finalist')):
      return False
    return any(word in heading for word in (
      'book', 'contemporary', 'historical', 'inspirational', 'romantic',
      'romance', 'novella', 'paranormal', 'speculative', 'fantasy', 'erotic',
      'spicy', 'mainstream', 'single title', 'suspense', 'young adult',
      'dark'))

  def title_author_from_node(self, node):
    return self.title_author_from_text(self.node_text(node))

  def node_text(self, node):
    return normalize_line(node.get_text(' ', strip=True))

  def inline_text(self, node):
    return normalize_line(node.get_text('', strip=True))

  def title_author_from_text(self, value):
    value = self.clean_row_text(value)
    if not value or self.skip_row_text(value):
      return None
    quoted = re.match(
      r'^[\u201c\u201d"\'](.+?)[\u201c\u201d"\']\s+in\s+.+?\s+[-\u2013\u2014]\s*(.+)$',
      value,
      re.I)
    if quoted is not None:
      title = self.clean_title(quoted.group(1))
      author = self.clean_author(quoted.group(2))
      return (title, author) if title and author else None
    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', value, re.I)
    if by_match is not None:
      title = self.clean_title(by_match.group(1))
      author = self.clean_author(by_match.group(2))
      return (title, author) if title and author else None
    dash_match = re.match(r'^(.+?)\s*[-\u2013\u2014]\s*(.+)$', value)
    if dash_match is None:
      return None
    title = self.clean_title(dash_match.group(1))
    author = self.clean_author(dash_match.group(2))
    return (title, author) if title and author else None

  def clean_row_text(self, value):
    value = normalize_line(value).replace('\xa0', ' ')
    value = re.sub(r'\bAward of Merit Finalists?\b.*$', '', value, flags=re.I)
    value = re.sub(r'^\s*Winner\s*:?\s*', '', value, flags=re.I)
    value = re.sub(r'\s*\*\s*$', '', value)
    return value.strip()

  def clean_title(self, value):
    value = strip_publication_notes(normalize_line(value))
    value = re.sub(r'^\s*Winner\s*:?\s*', '', value, flags=re.I)
    value = re.sub(r'\s*\*\s*$', '', value)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,:')

  def clean_author(self, value):
    value = strip_publication_notes(normalize_line(value))
    value = re.sub(r'\s*\*\s*$', '', value)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,:')

  def skip_row_text(self, value):
    heading = normalize_heading(value)
    return (
      not heading
      or heading == 'author'
      or heading.startswith('winner')
      or heading.startswith('award of merit')
      or heading.startswith('winners announced')
      or heading.startswith('thank you'))

  def block_lines(self, block):
    copied = BeautifulSoup(str(block), 'html.parser')
    for br in copied.find_all('br'):
      br.replace_with('\n')
    text = copied.get_text('\n', strip=True)
    raw_lines = [normalize_line(line) for line in text.splitlines() if normalize_line(line)]
    combined = []
    index = 0
    while index < len(raw_lines):
      line = raw_lines[index]
      if re.search(r'[-\u2013\u2014]\s*$', line) and index + 1 < len(raw_lines):
        combined.append(normalize_line(f'{line} {raw_lines[index + 1]}'))
        index += 2
        continue
      if re.match(r'^[-\u2013\u2014]\s*', line) and combined:
        combined[-1] = normalize_line(f'{combined[-1]} {line}')
        index += 1
        continue
      combined.append(line)
      index += 1
    return combined

  def is_winner_marker(self, value):
    return normalize_heading(value) in {'winner', 'winners'}

  def is_merit_marker(self, value):
    return 'award of merit finalist' in normalize_heading(value)

  def past_year_from_text(self, value):
    match = re.search(r'\b(201[3-7])\b.*(?:winner|finalist)', value or '', re.I)
    return int(match.group(1)) if match is not None else None

  def year_from_text(self, value):
    match = re.search(r'\b(?:19|20)\d{2}\b', value or '')
    return int(match.group(0)) if match is not None else None

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

  def with_source_order(self, rows):
    ordered = []
    for index, row in enumerate(rows):
      copy = dict(row)
      copy['_source_order'] = index
      ordered.append(copy)
    return ordered

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
          normalize_heading(row.get('title', ''))))
      award_rows = []
      for row in year_rows:
        entry_row = {key: value for key, value in row.items() if not key.startswith('_')}
        award_rows.append(self.build_award_entry(
          entry_row, row['source_url'], year, row['category']))
      entries.extend(assign_positions(award_rows, int(year)))
    return entries

  def add_coverage_notes(self, rows, notes):
    if not rows:
      notes.append('No HOLT Medallion rows were parsed from official VRW pages.')
      return
    by_year = {}
    for row in rows:
      by_year.setdefault(int(row['award_year']), []).append(row)
    shortlist_years = [
      year for year, year_rows in sorted(by_year.items())
      if any(row.get('result') == RESULT_SHORTLISTED for row in year_rows)
    ]
    winner_years = [
      year for year, year_rows in sorted(by_year.items())
      if any(row.get('result') == RESULT_WINNER for row in year_rows)
    ]
    if shortlist_years:
      notes.append(
        'Official VRW HOLT finalist/shortlist-style rows were parsed for: ' +
        ', '.join(str(year) for year in shortlist_years) + '.')
    if winner_years:
      notes.append(
        'Official VRW HOLT winner rows were parsed for: ' +
        ', '.join(str(year) for year in winner_years) + '.')
    if 2023 in by_year and 2025 in by_year and 2024 not in by_year:
      notes.append('No official VRW HOLT text page was discovered for 2024.')
    if min(by_year) > 1995:
      notes.append(
        'Pre-2013 HOLT history is not imported in V1 unless an official text '
        'source is discovered.')
    notes.append('LibraryThing and FictionDB are reference-only for this recipe.')


def parse_holt_medallion(html, base_url=HOLT_URL, name=HOLT_AWARD_NAME, fetch_url=None, pages=None):
  return HOLTMedallionParser().parse(
    html, base_url, name, fetch_url=fetch_url, pages=pages)
