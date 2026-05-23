#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
SPSFC parser for official finalist/result posts and archival finalist posts.

Maintenance notes:
- SPSFC status/allocation pages are intentionally excluded from this parser.
  They change while a competition is live and include non-finalist statuses.
- Official result pages can provide Goodreads links; those are used as
  source_url for matching recovery, while award_source_url preserves the
  authority page that supplied the award status.
- File 770 is used only as an archival finalist source for older years where a
  stable official finalist page is not configured.
- Narrow winner corrections for older years live in parser/data/spsfc_results.json
  so broad source pages do not need to be scraped for a single fact.
"""

import json
import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, normalize_heading, normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    AwardParserBase, normalize_heading, normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key


AWARD_NAME = 'Self-Published Science Fiction Competition'
CATEGORY = 'Novel'
RESULT_RUNNER_UP = 'runner-up'
RESULT_FINALIST = 'finalist'
OFFICIAL_RESULT = 'official_result'
OFFICIAL_FINALISTS = 'official_finalists'
FILE770_FINALISTS = 'file770_finalists'
CURATED_RESULTS_FILE = 'spsfc_results.json'

SPSFC_SOURCE_PAGES = (
  {
    'url': 'https://spsfc.space/2025/08/07/and-the-spsfc-4-winner-is/',
    'competition': 'SPSFC 4',
    'award_year': 2025,
    'kind': OFFICIAL_RESULT,
  },
  {
    'url': 'https://spsfc.space/2025/06/05/spsfc-4-finalists/',
    'competition': 'SPSFC 4',
    'award_year': 2025,
    'kind': OFFICIAL_FINALISTS,
  },
  {
    'url': 'https://file770.com/self-published-science-fiction-competition-3-finalists/',
    'competition': 'SPSFC 3',
    'award_year': 2024,
    'kind': FILE770_FINALISTS,
  },
  {
    'url': 'https://file770.com/self-published-science-fiction-competition-2-finalists-announced/',
    'competition': 'SPSFC 2',
    'award_year': 2023,
    'kind': FILE770_FINALISTS,
  },
  {
    'url': 'https://file770.com/seven-finalists-announced-in-self-published-science-fiction-competition/',
    'competition': 'SPSFC 1',
    'award_year': 2022,
    'kind': FILE770_FINALISTS,
  },
)

PLACEMENT_HEADINGS = {
  'winner': 1,
  'first place': 1,
  'second place': 2,
  'third place': 3,
  'fourth place': 4,
  'fifth place': 5,
  'sixth place': 6,
  'seventh place': 7,
}


class SPSFCAwardsParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def parse(self, html, base_url, name,
            fetch_url=None, source_pages=None, curated_rows=None, log=None, progress=None):
    pages = tuple(source_pages if source_pages is not None else SPSFC_SOURCE_PAGES)
    rows = self.curated_result_rows(curated_rows)
    notes = []
    self._progress(progress, 0, len(pages), f'Preparing {name} source pages...')
    for index, page in enumerate(pages, start=1):
      url = page['url']
      self._progress(progress, index, len(pages), f'Fetching {page["competition"]}...')
      try:
        page_html = html if _same_url(url, base_url) else fetch_url(url)
      except Exception as err:
        notes.append(f'{page["competition"]} source could not be fetched: {url}: {err}')
        self._log(log, 'fetch-failed', {'url': url, 'error': str(err)})
        continue
      parsed_rows = self.parse_source_page(page_html, page)
      rows = _merge_rows(rows, parsed_rows)
      self._log(log, 'source-parsed', {
        'url': url, 'competition': page['competition'], 'entries': len(parsed_rows),
      })
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes)

  def parse_source_page(self, html, page):
    if page['kind'] == OFFICIAL_RESULT:
      return self.parse_official_result_page(html, page)
    return self.parse_finalist_page(html, page)

  def parse_official_result_page(self, html, page):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for heading in soup.find_all(['h2', 'h3']):
      placement = PLACEMENT_HEADINGS.get(normalize_heading(heading.get_text(' ', strip=True)))
      if placement is None:
        continue
      title_heading = self._next_title_heading(heading)
      if title_heading is None:
        continue
      title, author = _split_title_author(title_heading.get_text(' ', strip=True))
      if not title or not author:
        continue
      goodreads_url = self._goodreads_url_between(heading, title_heading)
      rows.append(self._row(
        title, author, page,
        result='winner' if placement == 1 else RESULT_RUNNER_UP,
        placement=placement,
        source_url=goodreads_url or page['url'],
        award_source_url=page['url']))
    return rows

  def parse_finalist_page(self, html, page):
    soup = BeautifulSoup(html, 'html.parser')
    root = _article_root(soup)
    fallback_single_list = root is soup
    rows = []
    for item_list in root.find_all(['ul', 'ol']):
      if _excluded_context(item_list):
        continue
      list_rows = []
      for item in item_list.find_all('li', recursive=False):
        title, author = _split_title_author(item.get_text(' ', strip=True))
        if not title or not author:
          continue
        list_rows.append(self._row(
          title, author, page,
          result=RESULT_FINALIST,
          source_url=_goodreads_url_in_node(item) or page['url'],
          award_source_url=page['url']))
      if len(list_rows) >= 2 or (fallback_single_list and list_rows):
        rows.extend(list_rows)
    return rows

  def curated_result_rows(self, curated_rows=None):
    rows = curated_rows if curated_rows is not None else load_curated_result_rows()
    return [self.curated_row(row) for row in rows or ()]

  def curated_row(self, row):
    parsed = self.build_award_entry({
      'title': row.get('title', ''),
      'author': row.get('author', ''),
      'result': row.get('result', 'winner'),
      'competition': row.get('competition', ''),
      'award_source_url': row.get('award_source_url') or row.get('source_url', ''),
    }, row.get('source_url') or row.get('award_source_url', ''),
      row.get('award_year'), CATEGORY)
    if row.get('placement') is not None:
      parsed['placement'] = row.get('placement')
    return parsed

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      year_rows = sorted(by_year[year], key=_row_sort_key)
      winner_seen = False
      suffix_index = 0
      for row in year_rows:
        entry = dict(row)
        placement = entry.get('placement')
        if entry.get('result') == 'winner' and not winner_seen:
          entry['position'] = str(year)
          winner_seen = True
        else:
          if placement and placement > 1:
            suffix_index = max(suffix_index + 1, placement - 1)
          else:
            suffix_index += 1
          entry['position'] = f'{year}.{suffix_index:02d}'
        entries.append(entry)
    return entries

  def _row(self, title, author, page, result, source_url, award_source_url, placement=None):
    row = self.build_award_entry({
      'title': title,
      'author': author,
      'result': result,
      'competition': page['competition'],
      'award_source_url': award_source_url,
    }, source_url, page['award_year'], CATEGORY)
    if placement is not None:
      row['placement'] = placement
    return row

  def _next_title_heading(self, heading):
    for node in heading.next_siblings:
      name = getattr(node, 'name', None)
      if name in {'h2', 'h3'}:
        return None
      if name == 'h4':
        return node
    return heading.find_next('h4')

  def _goodreads_url_between(self, heading, title_heading):
    for node in title_heading.next_siblings:
      name = getattr(node, 'name', None)
      if name in {'h2', 'h3'}:
        return ''
      if not hasattr(node, 'find_all'):
        continue
      for link in node.find_all('a', href=True):
        href = link['href']
        if 'goodreads.com' in href.casefold():
          return urljoin('', href)
    return ''

  def _log(self, log, label, data):
    if log is not None:
      log(f'SPSFC {label}: {data}')

  def _progress(self, progress, done, total, message):
    if progress is not None:
      progress(done, total, message)


def _split_title_author(value):
  text = normalize_line(value)
  text = re.sub(r'^\s*(?:[•*\-]\s*)+', '', text).strip()
  match = re.match(r'^(.+?)\s+by\s+(.+)$', text, re.I)
  if match is None:
    return '', ''
  title = strip_publication_notes(match.group(1)).strip(' "\u201c\u201d,')
  author = strip_publication_notes(match.group(2)).strip(' "\u201c\u201d,')
  return title, author


def _goodreads_url_in_node(node):
  for link in node.find_all('a', href=True):
    href = link['href']
    if 'goodreads.com' in href.casefold():
      return urljoin('', href)
  return ''


def _article_root(soup):
  selectors = (
    'article',
    '[class~="entry-content"]',
    '[class~="post-content"]',
    '[class~="post"]',
    '[id~="content"]',
    'main',
  )
  for selector in selectors:
    node = soup.select_one(selector)
    if node is not None:
      return node
  return soup


def _excluded_context(node):
  excluded = {
    'comment', 'comments', 'comment-list', 'commentlist', 'comment-body',
    'pingback', 'trackback', 'sidebar', 'widget', 'navigation', 'nav',
    'menu', 'footer', 'related', 'sharedaddy',
  }
  for parent in [node] + list(node.parents):
    values = []
    node_id = parent.get('id') if hasattr(parent, 'get') else None
    if node_id:
      values.append(node_id)
    classes = parent.get('class') if hasattr(parent, 'get') else None
    if classes:
      values.extend(classes)
    normalized = {normalize_heading(str(value)).replace(' ', '-') for value in values}
    if any(
        value in excluded or any(value.startswith(f'{prefix}-') for prefix in excluded)
        for value in normalized):
      return True
  return False


def _same_url(left, right):
  return (left or '').rstrip('/') == (right or '').rstrip('/')


def load_curated_result_rows():
  try:
    from importlib import resources
    package = 'calibre_plugins.list_switchboard.parser.data'
    text = resources.files(package).joinpath(CURATED_RESULTS_FILE).read_text(encoding='utf-8')
  except Exception:
    path = Path(__file__).with_name('data') / CURATED_RESULTS_FILE
    text = path.read_text(encoding='utf-8')
  data = json.loads(text)
  return tuple(data.get('rows') or ())


def _merge_rows(existing, incoming):
  merged = list(existing)
  for row in incoming:
    key = _row_key(row)
    for index, old_row in enumerate(merged):
      if _row_key(old_row) == key:
        if _row_priority(row) >= _row_priority(old_row):
          merged[index] = row
        break
    else:
      merged.append(row)
  return merged


def _row_key(row):
  return (
    row.get('competition', ''),
    normalize_heading(row.get('title', '')),
    normalize_heading(row.get('author', '')),
  )


def _row_priority(row):
  return 2 if row.get('placement') else 1


def _row_sort_key(row):
  placement = row.get('placement')
  return (
    int(placement) if placement is not None else 99,
    normalize_heading(row.get('title', '')),
    normalize_heading(row.get('author', '')),
  )


def parse_spsfc_awards(
    html, base_url, name='SPSFC - Novel Finalists',
    fetch_url=None, source_pages=None, curated_rows=None, log=None, progress=None):
  return SPSFCAwardsParser().parse(
    html, base_url, name,
    fetch_url=fetch_url, source_pages=source_pages, curated_rows=curated_rows,
    log=log, progress=progress)
