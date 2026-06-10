#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Nebula Awards parser for the official Best Novel award page.

Maintenance notes:
- The official award page is already category-filtered and paginated.
- Recent rows use "Title by Author, published by Publisher. Winner..." while
  current/open finalist rows may use "Title, by Author (Publisher) . Nominated...".
- Winner placement is status-driven, not row-order-driven.
"""

import re
from urllib.parse import urljoin

from lxml import html as lxml_html

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    is_author_suffix, parse_winner_prefix, strip_editor_marker,
    strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.base import ListParserBase
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
  from calibre_plugins.list_switchboard.parser.sfadb_base import (
    SFADBParser, StandardItemMixin, normalize_line,
  )
except ImportError:
  from .award_base import (
    is_author_suffix, parse_winner_prefix, strip_editor_marker,
    strip_publication_notes,
  )
  from .base import ListParserBase
  from .generic import position_sort_key
  from .sfadb_base import (
    SFADBParser, StandardItemMixin, normalize_line,
  )


YEAR_HEADING = re.compile(r'^\d{4}$')
AWARD_NAME = 'Nebula Award'
CATEGORY_NAME = 'Best Novel'
SFADB_YEAR_PAGE_URL = re.compile(r'/Nebula_Awards_(\d{4})$')
SFADB_CATEGORY_BOUNDARIES = frozenset({
  'novel', 'best novel', 'novella', 'best novella',
  'andre norton award', 'andre norton', 'middle grade and young adult fiction',
  'best middle grade and young adult fiction',
  'comics', 'best comics', 'graphic story', 'game writing', 'dramatic presentation',
  'script', 'short story', 'novelette',
})


class NebulaSFADBCategoryParser(StandardItemMixin, SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = SFADB_YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = SFADB_CATEGORY_BOUNDARIES


class NebulaAwardsNovelParser(ListParserBase):
  """
  Parses Nebula Best Novel winners and nominees from the paginated official page or SFADB fallback.

  Invariants:
  - Winner position is the award year; all other rows get year.NN suffixes.
  - Winner status is determined by the row text ('Winner, Best Novel in YYYY'),
    not by row order.
  - Pagination is followed automatically when fetch_url is provided.
  - Falls back to SFADB if original site fails.
  """

  # SFADB attributes
  AWARD_NAME = 'Nebula Award'
  CATEGORY_BOUNDARIES = {
    'best novel': 'best novel',
    'novel': 'novel',
  }

  def parse(self, first_page_html, base_url, fetch_url=None, log=None, progress=None):
    if 'sfadb' in first_page_html.lower() or 'sfadb.com' in base_url.lower():
      return self.parse_sfadb(first_page_html, base_url, fetch_url, log, progress)
    return self.parse_official(first_page_html, base_url, fetch_url, log, progress)

  def parse_official(self, first_page_html, base_url, fetch_url=None, log=None, progress=None):
    entries = []
    notes = []
    seen_urls = set()
    url = base_url
    html = first_page_html
    page_index = 0
    while url and url not in seen_urls:
      seen_urls.add(url)
      page_index += 1
      _progress(progress, page_index, 0, f'Parsing Nebula Awards page {page_index}...')
      page_entries, next_url = _parse_nebula_page(html, url)
      entries.extend(page_entries)
      _log(log, 'page-parsed', {
        'url': url, 'entries': len(page_entries), 'next_url': next_url,
      })
      if not next_url or fetch_url is None:
        break
      try:
        html = fetch_url(next_url)
      except Exception as err:
        notes.append(f'Nebula Awards page could not be fetched: {next_url}: {err}')
        _log(log, 'fetch-failed', {'url': next_url, 'error': str(err)})
        break
      url = next_url
    return {
      'name': 'Nebula Awards - Novel',
      'url': base_url,
      'entries': sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      'notes': notes,
      'match_series': False,
    }

  def parse_sfadb(self, html, base_url, fetch_url, log=None, progress=None):
    return NebulaSFADBCategoryParser().parse(
      html, base_url, 'Nebula Awards - Novel', CATEGORY_NAME, ('best novel', 'novel'),
      fetch_url=fetch_url, log=log, progress=progress)

  def parse_item(self, line):
    """
    Parse a line like 'Winner: Title, Author (Publisher)' or 'Title, Author (Publisher)'
    """
    line = line.strip()
    if not line:
      return None

    line, result = parse_winner_prefix(line)
    line = re.sub(r'\s*\([^)]*\)\s*$', '', line).strip()
    line = _strip_nebula_translator_credit(line)
    if ',' not in line:
      return None
    title, author = line.rsplit(',', 1)
    if is_author_suffix(author):
      title, author_base = title.rsplit(',', 1) if ',' in title else ('', title)
      author = f'{author_base.strip()}, {author.strip()}'
    author = re.sub(r'^\[([^\[\]]+)\]$', r'\1', author.strip())
    if not title or not author:
      return None

    return {
      'title': strip_publication_notes(title).strip(' "\u201c\u201d,'),
      'author': strip_editor_marker(strip_publication_notes(author)).strip(),
      'result': result,
    }


def _parse_nebula_page(html, page_url):
  root = lxml_html.fromstring(html or '<html></html>')
  entries = []
  for heading in root.xpath('//h2|//h3'):
    year_text = _node_text(heading)
    if not YEAR_HEADING.match(year_text):
      continue
    entries.extend(_parse_nebula_year_entries(int(year_text), heading, page_url))
  return entries, _next_page_url(root, page_url)


def _parse_nebula_year_entries(year, heading, page_url):
  rows = []
  for node in heading.xpath('following::*'):
    if node.tag in ('h2', 'h3') and YEAR_HEADING.match(_node_text(node)):
      break
    if node.tag == 'li':
      parsed = _parse_nebula_novel_item(_node_text(node), year)
      if parsed is None:
        continue
      hrefs = node.xpath('(.//a[@href])[1]/@href')
      parsed['source_url'] = urljoin(page_url, hrefs[0]) if hrefs else page_url
      rows.append(parsed)

  entries = []
  nominee_index = 0
  for row in rows:
    if row['result'] == 'winner':
      position = str(year)
    else:
      nominee_index += 1
      position = f'{year}.{nominee_index:02d}'
    entries.append({
      'position': position,
      'title': row['title'],
      'author': row['author'],
      'source_url': row['source_url'],
      'award_year': str(year),
      'award': AWARD_NAME,
      'category': CATEGORY_NAME,
      'result': row['result'],
    })
  return entries


def _parse_nebula_novel_item(text, year):
  result = _nebula_result_for_text(text, year)
  if result is None:
    return None
  work_text = re.split(r'\s*\.\s*(?:Winner|Nominated)\b', text, 1, flags=re.I)[0]
  work_text = _strip_nebula_publication_notes(work_text)
  work_text = _strip_nebula_translator_credit(work_text)
  title, author = _split_nebula_title_author(work_text)
  if not title or not author:
    return None
  title = _strip_nebula_publication_notes(title).strip(' \"\u201c\u201d,')
  author = _strip_nebula_publication_notes(author)
  author = re.sub(r'\s*,\s*published\s+by\s+.+$', '', author, flags=re.I).strip()
  author = _strip_nebula_translator_credit(author)
  if not title or not author:
    return None
  return {'title': title, 'author': author, 'result': result}


def _nebula_result_for_text(text, year):
  if re.search(rf'\bWinner,\s*{re.escape(CATEGORY_NAME)}\s+in\s+{year}\b', text, re.I):
    return 'winner'
  if re.search(rf'\bNominated\s+for\b.*\b{re.escape(CATEGORY_NAME)}\s+in\s+{year}\b', text, re.I):
    return 'nominee'
  return None


def _strip_nebula_publication_notes(value):
  value = re.sub(r'\s+', ' ', value or '').strip()
  value = re.sub(r'\s*,?\s*published\s+by\s+.+$', '', value, flags=re.I).strip()
  while True:
    stripped = re.sub(r'\s*(?:\([^()]*\)|\[[^\[\]]*\])\s*$', '', value).strip()
    if stripped == value:
      return value
    value = stripped


def _strip_nebula_translator_credit(value):
  value = re.sub(r'\s+', ' ', value or '').strip()
  value = re.sub(r'\s*,\s*translated\s+by\s+[^,]+$', '', value, flags=re.I).strip()
  value = re.sub(r'\s*,\s*[^,]+?\s+translator\s*$', '', value, flags=re.I).strip()
  return value


def _split_nebula_title_author(text):
  match = re.match(r'^(.*?)\s*,?\s+by\s+(.+)$', text, re.I)
  if match is not None:
    return match.groups()
  parts = [part.strip() for part in text.rsplit(',', 1)]
  if len(parts) == 2 and all(parts):
    return parts[0], parts[1]
  return '', ''


def _node_text(node):
  return normalize_line(' '.join(
    text.strip()
    for text in node.xpath('.//text()[not(ancestor::script) and not(ancestor::style)]')
    if text.strip()))


def _next_page_url(root, page_url):
  for link in root.xpath('//a[@href]'):
    if 'Next' in _node_text(link):
      return urljoin(page_url, link.get('href') or '')
  return None


def _log(log, label, data):
  if log is not None:
    log(f'Nebula Awards Novel {label}: {data}')


def _progress(progress, done, total, message):
  if progress is not None:
    progress(done, total, message)


def parse_nebula_awards_novel(first_page_html, base_url, fetch_url=None, log=None, progress=None):
  return NebulaAwardsNovelParser().parse(
    first_page_html, base_url, fetch_url=fetch_url, log=log, progress=progress)


def parse_nebula_sfadb_category(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=None, log=None, progress=None):
  return NebulaSFADBCategoryParser().parse(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=fetch_url, log=log, progress=progress)
