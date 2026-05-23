#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Hugo Awards parser for official history pages.

Maintenance notes:
- The official Hugo history page links to one page per award year; each year
  page contains category headings followed by finalist bullet lists.
- This parser intentionally handles only normal Hugo Award years. Retro-Hugo
  pages are skipped so they can become a separate import recipe later.
- Best Novel finalists are assumed to be listed with the winner first after the
  award year is complete.
- When the official page lists only finalists (no winner marked), an SFADB
  fallback fetch is attempted to identify the winner.
"""

import re
import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.base import ListParserBase
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .base import ListParserBase
  from .generic import position_sort_key


YEAR_LINK = re.compile(r'^(\d{4})\s+Hugo Awards$', re.I)
CATEGORY_TEXT = re.compile(r'^Best\s+.+', re.I)
HUGO_CATEGORY_BOUNDARIES = {
  'novella',
  'novelette',
  'short fiction',
  'short story',
  'professional magazine',
  'professional artist',
  'dramatic presentation',
  'fan magazine',
  'fanzine',
  'fan writer',
  'fan artist',
}
INCOMPLETE_PAGE_TEXT = (
  'will be presented',
  'to be presented',
  'finalists were announced',
  'finalists have been announced',
)


class HugoAwardsCategoryParser(ListParserBase):
  """
  Parses one configured Hugo/Lodestar category from official year pages.

  Invariants:
  - Winner position is the award year.
  - Nominee positions are year + a two-digit fractional suffix in listed order.
  - Retro-Hugo pages are out of scope and skipped at discovery time.
  """

  NAME = 'Hugo Awards - Novel'
  AWARD_NAME = 'Hugo Award'
  CATEGORY = 'Best Novel'
  CATEGORY_ALIASES = ('best novel',)
  APPLY_SFADB_WINNER_FALLBACK = False

  def parse(self, history_html, base_url, fetch_url=None, log=None, progress=None):
    soup = BeautifulSoup(history_html, 'html.parser')
    year_links = _hugo_year_links(soup, base_url)
    entries = []
    notes = []
    _progress(progress, 0, len(year_links), f'Preparing {self.NAME} year pages...')
    for index, year_link in enumerate(year_links, start=1):
      year = year_link['year']
      url = year_link['url']
      _progress(progress, index, len(year_links), f'Fetching Hugo Awards {year}...')
      try:
        html = fetch_url(url) if fetch_url is not None else ''
      except Exception as err:
        notes.append(f'Hugo Awards {year} could not be fetched: {err}')
        _log(log, 'fetch-failed', {'year': year, 'url': url, 'error': str(err)})
        continue
      year_entries = _parse_hugo_year_category_entries(
        year, url, html, self.AWARD_NAME, self.CATEGORY, self.CATEGORY_ALIASES)
      if not year_entries:
        _log(log, 'year-skipped', {'year': year, 'url': url})
        continue
      if (
          self.APPLY_SFADB_WINNER_FALLBACK
          and fetch_url is not None
          and not any(e['result'] == 'winner' for e in year_entries)):
        _apply_sfadb_winner_fallback(year_entries, year, fetch_url, log, notes)
      entries.extend(year_entries)
      _log(log, 'year-parsed', {'year': year, 'url': url, 'entries': len(year_entries)})
    return {
      'name': self.NAME,
      'url': base_url,
      'entries': sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      'notes': notes,
      'match_series': False,
    }


class HugoAwardsNovelParser(HugoAwardsCategoryParser):

  NAME = 'Hugo Awards - Novel'
  AWARD_NAME = 'Hugo Award'
  CATEGORY = 'Best Novel'
  CATEGORY_ALIASES = ('best novel',)
  APPLY_SFADB_WINNER_FALLBACK = True


class HugoAwardsNovellaParser(HugoAwardsCategoryParser):

  NAME = 'Hugo Awards - Novella'
  AWARD_NAME = 'Hugo Award'
  CATEGORY = 'Best Novella'
  CATEGORY_ALIASES = ('best novella',)


class HugoAwardsSeriesParser(HugoAwardsCategoryParser):

  NAME = 'Hugo Awards - Series'
  AWARD_NAME = 'Hugo Award'
  CATEGORY = 'Best Series'
  CATEGORY_ALIASES = ('best series',)


class HugoAwardsGraphicStoryParser(HugoAwardsCategoryParser):

  NAME = 'Hugo Awards - Graphic Story or Comic'
  AWARD_NAME = 'Hugo Award'
  CATEGORY = 'Best Graphic Story or Comic'
  CATEGORY_ALIASES = ('best graphic story or comic', 'best graphic story')


class HugoAwardsRelatedWorkParser(HugoAwardsCategoryParser):

  NAME = 'Hugo Awards - Related Work'
  AWARD_NAME = 'Hugo Award'
  CATEGORY = 'Best Related Work'
  CATEGORY_ALIASES = ('best related work',)


class LodestarAwardParser(HugoAwardsCategoryParser):

  NAME = 'Lodestar Award - Young Adult Book'
  AWARD_NAME = 'Lodestar Award'
  CATEGORY = 'Best Young Adult Book'
  CATEGORY_ALIASES = (
    'lodestar award for best young adult book',
    'best young adult book',
  )


def _hugo_year_links(soup, base_url):
  links = []
  seen = set()
  for link in soup.find_all('a', href=True):
    text = link.get_text(' ', strip=True)
    if 'Retro' in text:
      continue
    match = YEAR_LINK.match(text)
    if not match:
      continue
    year = int(match.group(1))
    url = urljoin(base_url, link['href'])
    if year in seen:
      continue
    seen.add(year)
    links.append({'year': year, 'url': url})
  return sorted(links, key=lambda item: item['year'])


def _parse_hugo_year_category_entries(year, source_url, html, award_name, category, aliases):
  soup = BeautifulSoup(html, 'html.parser')
  if not _completed_hugo_year_page(soup, aliases):
    return []
  items = _category_items(soup, aliases)
  all_nominees = 'finalists were announced' in html.casefold()
  entries = []
  for index, item in enumerate(items):
    parsed = _parse_hugo_novel_item(item)
    if parsed is None:
      continue
    if all_nominees:
      position = f'{year}.{index + 1:02d}'
      result = 'nominee'
    else:
      position = str(year) if index == 0 else f'{year}.{index:02d}'
      result = 'winner' if index == 0 else 'nominee'
    entries.append({
      'position': position,
      'title': parsed['title'],
      'author': parsed['author'],
      'source_url': source_url,
      'award_year': str(year),
      'award': award_name,
      'category': category,
      'result': result,
    })
  return entries


def _apply_sfadb_winner_fallback(entries, year, fetch_url, log, notes):
  current_year = datetime.datetime.now().year
  _log_fallback(log, f'checking year={year} current_year={current_year}')
  if year > current_year:
    _log_fallback(log, f'skipped year={year}; award year is in the future')
    return
  try:
    sfadb_url = f'https://www.sfadb.com/Hugo_Awards_{year}'
    _log_fallback(log, f'fetching {sfadb_url}')
    html = fetch_url(sfadb_url)
    winner_title = _parse_sfadb_hugo_novel_winner_title(html)
    if not winner_title:
      _log_fallback(log, f'no SFADB Novel winner found for {year}')
      return
    _log_fallback(log, f'SFADB Novel winner title={winner_title!r}')
    for entry in entries:
      if _same_hugo_title(winner_title, entry.get('title', '')):
        entry['result'] = 'winner'
        entry['position'] = str(year)
        entry['source_url'] = sfadb_url
        _log_fallback(log, f'marked winner year={year} title={entry["title"]!r}')
        return
    _log_fallback(log, f'winner title did not match parsed official entries for {year}')
  except Exception as err:
    _log_fallback(log, f'failed year={year}: {err}')
    notes.append(f'Hugo Awards {year} SFADB winner fallback failed: {err}')


def _parse_sfadb_hugo_novel_winner_title(html):
  soup = BeautifulSoup(html, 'html.parser')
  in_novel = False
  first_winner_title = ''
  for raw_line in _sfadb_hugo_text_lines(soup):
    normalized = _normalize_hugo_text(raw_line)
    if normalized in ('novel', 'best novel'):
      in_novel = True
      continue
    if in_novel and _sfadb_hugo_category_boundary(normalized):
      return ''
    if not normalized.lstrip('* ').startswith('winner:'):
      continue
    winner_text = raw_line.lstrip('* ').split(':', 1)[1].strip()
    title, _author = _split_hugo_title_author(winner_text)
    title = _strip_hugo_publication_notes(title).strip(' \"\u201c\u201d,')
    if in_novel:
      return title
    if not first_winner_title:
      first_winner_title = title
  return first_winner_title


def _sfadb_hugo_text_lines(soup):
  lines = []
  for node in soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'li']):
    line = re.sub(r'\s+', ' ', node.get_text(' ', strip=True)).strip()
    if line:
      lines.append(line)
  if lines:
    return lines
  return [
    re.sub(r'\s+', ' ', line).strip()
    for line in soup.get_text('\n', strip=True).splitlines()
    if re.sub(r'\s+', ' ', line).strip()
  ]


def _sfadb_hugo_category_boundary(normalized):
  if normalized in ('novella', 'best novella'):
    return True
  if not normalized or normalized.startswith('winner:') or ',' in normalized:
    return False
  return bool(re.match(r'^[a-z][a-z /:-]+$', normalized))


def _completed_hugo_year_page(soup, aliases):
  text = soup.get_text(' ', strip=True).casefold()
  first_alias = aliases[0]
  intro, _, _ = text.partition(first_alias.casefold())
  if any(marker in intro for marker in INCOMPLETE_PAGE_TEXT):
    return False
  return bool(_category_items(soup, aliases))


def _category_items(soup, aliases):
  heading = _find_category_heading(soup, aliases)
  if heading is None:
    return []
  items = []
  for sibling in heading.find_all_next():
    if sibling is heading:
      continue
    if _is_category_boundary(sibling):
      break
    if sibling.name == 'li':
      text = sibling.get_text(' ', strip=True)
      if text:
        items.append(text)
  return items


def _find_category_heading(soup, aliases):
  normalized_aliases = {_normalize_hugo_text(alias) for alias in aliases}
  for node in soup.find_all(string=True):
    if _normalize_hugo_text(str(node)) not in normalized_aliases:
      continue
    parent = node.parent
    while parent is not None and parent.name not in (
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'div'):
      parent = parent.parent
    return parent or node.parent
  return None


def _is_category_boundary(node):
  if node.name not in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'div'):
    return False
  text = _normalize_hugo_text(node.get_text(' ', strip=True))
  if not text:
    return False
  if bool(CATEGORY_TEXT.match(text)):
    return True
  return text in HUGO_CATEGORY_BOUNDARIES


def _normalize_hugo_text(value):
  return re.sub(r'\s+', ' ', value or '').strip().casefold()


def _parse_hugo_novel_item(text):
  text = _strip_hugo_publication_notes(text)
  text = _strip_hugo_translator_credit(text)
  title, author = _split_hugo_title_author(text)
  if not title or not author:
    return None
  title = _strip_hugo_publication_notes(title).strip(' \"\u201c\u201d,')
  author = _strip_hugo_publication_notes(author)
  author = re.sub(r'\s*,\s*translated\s+by\s+.+$', '', author, flags=re.I).strip()
  if not title or not author:
    return None
  return {'title': title, 'author': author}


def _strip_hugo_translator_credit(value):
  value = re.sub(r'\s+', ' ', value or '').strip()
  value = re.sub(r'\s*,\s*translated\s+by\s+[^,]+$', '', value, flags=re.I).strip()
  value = re.sub(r'\s*,\s*[^,]+?\s+translator\s*$', '', value, flags=re.I).strip()
  return value


def _split_hugo_title_author(text):
  match = re.match(r'^(.*?)\s*,?\s+by\s+(.+)$', text, re.I)
  if match is not None:
    return match.groups()
  parts = [part.strip() for part in text.rsplit(',', 1)]
  if len(parts) == 2 and all(parts):
    return parts[0], parts[1]
  return '', ''


def _strip_hugo_publication_notes(value):
  value = re.sub(r'\s+', ' ', value or '').strip()
  while True:
    stripped = re.sub(r'\s*(?:\([^()]*\)|\[[^\[\]]*\])\s*$', '', value).strip()
    if stripped == value:
      return value
    value = stripped


def _same_hugo_title(left, right):
  return _normalize_match_title(left) == _normalize_match_title(right)


def _normalize_match_title(value):
  value = _strip_hugo_publication_notes(value)
  value = re.sub(r'[\u2018\u2019]', "'", value)
  value = re.sub(r'[\u201c\u201d]', '"', value)
  value = re.sub(r'[^a-z0-9]+', ' ', value.casefold())
  return re.sub(r'\s+', ' ', value).strip()


def _log(log, label, data):
  if log is not None:
    log(f'Hugo Awards Novel {label}: {data}')


def _log_fallback(log, message):
  if log is not None:
    log(f'[HUGO-FALLBACK] {message}')


def _progress(progress, done, total, message):
  if progress is not None:
    progress(done, total, message)


# ---------------------------------------------------------------------------
# Module-level entry point for backward compatibility with existing callers
# ---------------------------------------------------------------------------

def parse_hugo_awards_novel(history_html, base_url, fetch_url=None, log=None, progress=None):
  return HugoAwardsNovelParser().parse(
    history_html, base_url, fetch_url=fetch_url, log=log, progress=progress)
