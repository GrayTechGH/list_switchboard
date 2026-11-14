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
- Once a finalist row is structurally split into title and author credit,
  explicit `and`, `&`, and `with` connectors produce canonical author lists;
  commas remain untouched so name suffixes survive.
- Graphic Story rows use a separate role-aware boundary because the official
  source commonly credits writers, artists, colourists, and letterers inline.
- Novella rows prefer a leading quoted-title boundary. This protects titles
  containing `by` and supports bilingual `Latin author / native title, native
  author` credits without leaving either author form in the title.
"""

import re
import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.base import (
    entry_source_object, imported_entry, ListParserBase, parsed_source)
  from calibre_plugins.list_switchboard.parser.award_base import is_author_suffix
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .base import entry_source_object, imported_entry, ListParserBase, parsed_source
  from .award_base import is_author_suffix
  from .generic import position_sort_key


YEAR_LINK = re.compile(r'^(\d{4})\s+Hugo Awards$', re.I)
CATEGORY_TEXT = re.compile(r'^Best\s+.+', re.I)
HUGO_CATEGORY_BOUNDARIES = {
  'astounding award',
  'astounding award for best new writer',
  'disqualifications and withdrawals',
  'editor long form',
  'editor short form',
  'fan artist',
  'fan writer',
  'fancast',
  'fanzine',
  'graphic story',
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
GRAPHIC_STORY_ROLE = re.compile(
  r'(?P<role>'
  r'written/created|pencilled/created|penciled/created|'
  r'written\s+and\s+illustrated|story\s+and\s+art|'
  r'adapted\s+from\s+(?:the\s+)?(?:story|novels?)|'
  r'author|artist|written|created|adapted|illustrated|iillustrated|'
  r'pencilled|penciled|inked|drawn|art|colou?rs?|colou?red|'
  r'letters?|lettered|lettering|cover'
  r')\s*(?:by|:)\s*',
  re.I)
QUOTED_HUGO_TITLE_CREDIT = re.compile(
  r'^[\u201c"](?P<title>.*?)[\u201d"]\s*'
  r'(?:(?:,\s*(?:by\s+)?)|(?:by\s+))(?P<credit>.+)$',
  re.I)
NON_LATIN_HUGO_SCRIPT = re.compile(
  r'[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]')
RELATED_WORK_ROLE_BOUNDARY = re.compile(
  r'\s*(?:,\s*)?'
  r'(?:(?:written\s+and\s+edited|produced\s+and\s+directed|edited|compiled|'
  r'presented)\s+by|a\s+project\s+of|ed\.)\s+',
  re.I)


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
  INCLUDE_INCOMPLETE_FINALISTS = False
  PARSER_NOTES = ()

  def parse(self, history_html, base_url, fetch_url=None, log=None, progress=None):
    soup = BeautifulSoup(history_html, 'html.parser')
    year_links = _hugo_year_links(soup, base_url)
    entries = []
    notes = list(self.PARSER_NOTES)
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
        year, url, html, self.AWARD_NAME, self.CATEGORY, self.CATEGORY_ALIASES,
        include_incomplete_finalists=self.INCLUDE_INCOMPLETE_FINALISTS,
        parse_item=self.parse_item,
        parse_item_node=self.parse_item_node)
      if not year_entries:
        _log(log, 'year-skipped', {'year': year, 'url': url})
        continue
      notes.extend(self.notes_for_year(year, url, html, year_entries))
      if (
          self.APPLY_SFADB_WINNER_FALLBACK
          and fetch_url is not None
          and not any(e['result'] == 'winner' for e in year_entries)):
        _apply_sfadb_winner_fallback(year_entries, year, fetch_url, log, notes)
      entries.extend(year_entries)
      _log(log, 'year-parsed', {'year': year, 'url': url, 'entries': len(year_entries)})
    return {
      'name': self.NAME,
      'source': parsed_source(self.NAME, base_url),
      'entries': sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      'notes': notes,
      'match_series': False,
    }

  def notes_for_year(self, _year, _url, _html, _entries):
    return []

  def parse_item(self, text):
    return _parse_hugo_novel_item(text)

  def parse_item_node(self, node):
    return self.parse_item(node.get_text(' ', strip=True))


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

  def parse_item(self, text):
    return _parse_hugo_novella_item(text)


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

  def parse_item(self, text):
    return _parse_hugo_graphic_story_item(text)


class HugoAwardsRelatedWorkParser(HugoAwardsCategoryParser):

  NAME = 'Hugo Awards - Related Work'
  AWARD_NAME = 'Hugo Award'
  CATEGORY = 'Best Related Work'
  CATEGORY_ALIASES = ('best related work',)

  def parse_item_node(self, node):
    return _parse_hugo_related_work_item(node)


class LodestarAwardParser(HugoAwardsCategoryParser):

  NAME = 'Lodestar Award - Young Adult Book'
  AWARD_NAME = 'Lodestar Award'
  CATEGORY = 'Best Young Adult Book'
  CATEGORY_ALIASES = (
    'lodestar award for best young adult book',
    'lodestar award for best ya book',
    'award for best young adult book',
    'best young adult book',
  )
  INCLUDE_INCOMPLETE_FINALISTS = True
  PARSER_NOTES = (
    'Official Hugo history pages expose Lodestar finalists; finalist rows are '
    'imported as nominees, and no separate public longlist is imported.',
    'The Lodestar Award is administered with the Hugo process but is not itself '
    'a Hugo Award; 2018 was presented as the WSFS Award for Best Young Adult Book.',
  )

  def notes_for_year(self, year, _url, html, entries):
    withdrawn = _withdrawn_finalist_titles(html, entries)
    if not withdrawn:
      return []
    return [
      f'Lodestar Award {year} finalist remained in the official finalist list '
      f'after withdrawal and was imported as nominee: {title}'
      for title in withdrawn
    ]


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


def _parse_hugo_year_category_entries(
    year, source_url, html, award_name, category, aliases,
    include_incomplete_finalists=False, parse_item=None, parse_item_node=None):
  soup = BeautifulSoup(html, 'html.parser')
  completed = _completed_hugo_year_page(soup, aliases)
  if not completed and not include_incomplete_finalists:
    return []
  item_nodes = _category_item_nodes(soup, aliases)
  if not item_nodes:
    return []
  all_nominees = not completed
  parse_item = parse_item or _parse_hugo_novel_item
  entries = []
  for index, item_node in enumerate(item_nodes):
    if parse_item_node is not None:
      parsed = parse_item_node(item_node)
    else:
      parsed = parse_item(item_node.get_text(' ', strip=True))
    parsed = _finalize_hugo_item(parsed)
    if parsed is None:
      continue
    if all_nominees:
      position = f'{year}.{index + 1:02d}'
      result = 'nominee'
    else:
      position = str(year) if index == 0 else f'{year}.{index:02d}'
      result = 'winner' if index == 0 else 'nominee'
    entries.append(imported_entry(
      position,
      parsed['title'],
      parsed['authors'],
      source=entry_source_object(source_url),
      award_year=str(year),
      award=award_name,
      category=category,
      result=result))
  return entries


def _finalize_hugo_item(parsed):
  """Apply category-independent cleanup after source-specific boundary parsing."""
  if not parsed:
    return None
  title = re.sub(r'\s+', ' ', parsed.get('title', '')).strip()
  title = re.sub(r'\s+([,;:!?])', r'\1', title)
  title = re.sub(r'\(\s+', '(', title)
  title = re.sub(r'\s+\)', ')', title)
  authors = []
  seen = set()
  for raw_author in parsed.get('authors', ()):
    raw_author = re.sub(r'\s+', ' ', raw_author or '').strip()
    for author in _split_hugo_parenthesized_name_forms(raw_author):
      key = author.casefold()
      if author and key not in seen:
        seen.add(key)
        authors.append(author)
  return {'title': title, 'authors': authors} if title and authors else None


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
        entry['source'] = entry_source_object(sfadb_url)
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
  alias_positions = [
    position
    for position in (text.find(alias.casefold()) for alias in aliases)
    if position >= 0
  ]
  intro = text[:min(alias_positions)] if alias_positions else text
  if any(marker in intro for marker in INCOMPLETE_PAGE_TEXT):
    return False
  return bool(_category_items(soup, aliases))


def _category_items(soup, aliases):
  return [
    text
    for text in (
      item.get_text(' ', strip=True)
      for item in _category_item_nodes(soup, aliases)
    )
    if text
  ]


def _category_item_nodes(soup, aliases):
  heading = _find_category_heading(soup, aliases)
  if heading is None:
    return []
  for sibling in heading.find_all_next():
    if sibling is heading:
      continue
    if _is_category_boundary(sibling):
      break
    if sibling.name in ('ul', 'ol'):
      return sibling.find_all('li', recursive=False)
    if sibling.name == 'li':
      return [sibling]
  return []


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


def _withdrawn_finalist_titles(html, entries):
  text = re.sub(r'\s+', ' ', BeautifulSoup(html, 'html.parser').get_text(' ', strip=True))
  withdrawn = []
  for entry in entries:
    title = entry.get('title', '')
    if not title:
      continue
    pattern = (
      rf'\b{re.escape(title)}\b[^.]*\bwithdr(?:ew|awn)\b|'
      rf'\bwithdr(?:ew|awn)\b[^.]*\b{re.escape(title)}\b'
    )
    if re.search(pattern, text, re.I):
      withdrawn.append(title)
  return withdrawn


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
  return {'title': title, 'authors': _split_hugo_authors(author)}


def _parse_hugo_novella_item(text):
  """Parse quoted short-work titles before applying the general Hugo split."""
  cleaned = _strip_one_balanced_hugo_note(text)
  cleaned = _strip_hugo_translator_credit(cleaned)
  quoted = QUOTED_HUGO_TITLE_CREDIT.match(cleaned)
  if quoted is not None:
    title = quoted.group('title').strip()
    credit = quoted.group('credit').strip()
  else:
    title, credit = _split_hugo_title_author(cleaned)
    title = title.strip(' \"\u201c\u201d,')
    credit = credit.strip()
  if not title or not credit:
    return None
  bilingual_authors = _split_hugo_bilingual_credit(credit)
  authors = bilingual_authors or _split_hugo_comma_contributors(credit)
  return {'title': title, 'authors': authors} if title and authors else None


def _split_hugo_bilingual_credit(value):
  """Return both author forms from `Latin author / native title, native author`."""
  if '/' not in value:
    return []
  latin_author, native_credit = (part.strip() for part in value.split('/', 1))
  if ',' not in native_credit or not NON_LATIN_HUGO_SCRIPT.search(native_credit):
    return []
  _native_title, native_author = (
    part.strip() for part in native_credit.rsplit(',', 1))
  if not latin_author or not native_author:
    return []
  if latin_author.casefold() == native_author.casefold():
    return [latin_author]
  return [latin_author, native_author]


def _strip_one_balanced_hugo_note(value):
  """Remove one terminal publisher note, including nested parentheses."""
  value = re.sub(r'\s+', ' ', value or '').strip()
  closing = value[-1:] if value else ''
  if closing not in (')', ']'):
    return value
  expected_open = '(' if closing == ')' else '['
  depth = 0
  for index in range(len(value) - 1, -1, -1):
    char = value[index]
    if char == closing:
      depth += 1
    elif char == expected_open:
      depth -= 1
      if depth == 0:
        prefix = value[:index].rstrip()
        if prefix and NON_LATIN_HUGO_SCRIPT.fullmatch(prefix[-1]):
          return value
        return prefix
  return value


def _parse_hugo_related_work_item(node):
  """Parse Related Work rows using the official emphasized title boundary."""
  text = _strip_one_balanced_hugo_note(node.get_text(' ', strip=True))
  title = ''
  credit = ''
  quoted = QUOTED_HUGO_TITLE_CREDIT.match(text)
  if quoted is not None:
    title = quoted.group('title')
    credit = quoted.group('credit')
  else:
    for title_node in node.find_all(['strong', 'em', 'cite', 'i']):
      candidate = re.sub(
        r'\s+', ' ', title_node.get_text(' ', strip=True)).strip(' \"\u201c\u201d')
      if candidate and text.find(candidate) <= 2:
        title = candidate
        credit = text[text.find(candidate) + len(candidate):]
        break

  if title:
    title_tail = re.match(
      r'^\s*,\s*(.+?)\s*,\s*by\s+(.+)$', credit, flags=re.I)
    if title_tail is not None:
      title = f'{title}, {title_tail.group(1)}'
      credit = title_tail.group(2)

  if not title:
    boundary = RELATED_WORK_ROLE_BOUNDARY.search(text)
    if boundary is not None:
      title = text[:boundary.start()]
      credit = text[boundary.end():]
    else:
      title, credit = _split_hugo_title_author(text)
  title = _clean_hugo_related_title(title)
  credit = _clean_hugo_related_credit(credit)
  if _exclude_hugo_related_work(title):
    return None
  if not title or not credit:
    return None
  authors = []
  seen = set()
  for author in _split_hugo_comma_contributors(credit):
    author = _clean_hugo_related_contributor(author)
    key = author.casefold()
    if author and key not in seen:
      seen.add(key)
      authors.append(author)
  return {'title': title, 'authors': authors} if authors else None


def _exclude_hugo_related_work(title):
  """Exclude non-book community activities from the book-oriented recipe."""
  normalized = _normalize_hugo_text(title)
  return (
    normalized.startswith('r/fantasy')
    and '2024 bingo reading challenge' in normalized)


def _clean_hugo_related_title(value):
  value = re.sub(r'\s+', ' ', value or '').strip(' \"\u201c\u201d,')
  value = re.sub(r'\s+([,;:!?])', r'\1', value)
  value = re.sub(r'\(\s+', '(', value)
  value = re.sub(r'\s+\)', ')', value)
  return re.sub(
    r'\s*\(Modern Masters of Science Fiction\)\s*$', '', value, flags=re.I)


def _clean_hugo_related_credit(value):
  value = re.sub(r'\s+', ' ', value or '').strip(' ,;\"\u201d')
  value = re.sub(r'^\([^()]*\)\s*,?\s*', '', value)
  value = re.sub(
    r'\b(?:written\s+and\s+edited|produced\s+and\s+directed|edited|compiled|'
    r'presented)\s+by\s+', '', value, flags=re.I)
  value = re.sub(r'\ba\s+project\s+of\s+(?:the\s+)?', '', value, flags=re.I)
  value = re.sub(r'^the\s+r/Fantasy\s+Bingo\s+team:\s*', '', value, flags=re.I)
  value = re.sub(r'^(?:by|ed\.)\s+', '', value, flags=re.I)
  return value.strip(' ,;')


def _clean_hugo_related_contributor(value):
  value = re.sub(
    r'\s*[\u2013\u2014-]\s*(?:director|senior\s+programming\s+coordinator|'
    r'fiyahcon\s+fringe\s+co-director)\s*$', '', value, flags=re.I)
  value = value.strip(' ,:;')
  value = re.sub(r'\s*\((?:ed\.?|eds\.?|editor)\)\s*$', '', value, flags=re.I)
  suffix = value.rsplit(',', 1)[-1].strip()
  if value.endswith('.') and not is_author_suffix(suffix):
    value = value[:-1].rstrip()
  if re.match(r'^(?:and\s+)?the\s+.+\s+team$', value, re.I):
    return ''
  return value


def _parse_hugo_graphic_story_item(text):
  """Parse official rows whose contributor roles are embedded after the title."""
  text = _strip_hugo_graphic_publication_note(text)
  role_matches = list(GRAPHIC_STORY_ROLE.finditer(text))
  if not role_matches:
    title, contributor_credit = _split_hugo_title_author(text)
    if not title or not contributor_credit:
      return None
    title = _strip_hugo_publication_notes(title).strip(' \"\u201c\u201d,')
    contributor_credit = re.sub(
      r'\s*;\s*as\s+.+$', '', contributor_credit, flags=re.I).strip()
    contributor_credit = _strip_hugo_graphic_publication_note(contributor_credit)
    authors = _split_hugo_comma_contributors(contributor_credit)
    return {'title': title, 'authors': authors} if title and authors else None

  title = text[:role_matches[0].start()].strip(' \"\u201c\u201d,;:')
  title = re.sub(r'\s+([,;:!?])', r'\1', title)
  contributor_credits = []
  for index, match in enumerate(role_matches):
    end = role_matches[index + 1].start() if index + 1 < len(role_matches) else len(text)
    credit = text[match.end():end].strip(' \t\r\n,;:&')
    if credit:
      contributor_credits.append(credit)
  authors = []
  seen = set()
  for credit in contributor_credits:
    for author in _split_hugo_comma_contributors(credit):
      key = author.casefold()
      if key not in seen:
        seen.add(key)
        authors.append(author)
  return {'title': title, 'authors': authors} if title and authors else None


def _strip_hugo_graphic_publication_note(value):
  """Remove one publisher note without consuming a preceding transliteration."""
  value = re.sub(r'\s+', ' ', value or '').strip()
  return re.sub(r'\s*(?:\([^()]*\)|\[[^\[\]]*\])\s*$', '', value).strip()


def _split_hugo_comma_contributors(value):
  """Split a source-bounded comma/connector credit while preserving suffixes."""
  value = re.sub(r'\s+', ' ', value or '').strip(' ,;')
  shared_surname = re.fullmatch(
    r'([^,;/&]+?)\s+(?:and|&)\s+([^,;/&]+)', value, flags=re.I)
  if shared_surname is not None:
    left, right = (part.strip() for part in shared_surname.groups())
    right_words = right.split()
    if len(left.split()) == 1 and len(right_words) > 1:
      value = f'{left} {right_words[-1]} & {right}'

  parts = re.split(
    r'\s*(?:,|;|/|\band\b|&|\bwith\b)\s*', value, flags=re.I)
  authors = []
  for part in parts:
    part = part.strip(' ,;')
    if not part:
      continue
    if is_author_suffix(part) and authors:
      authors[-1] = f'{authors[-1]}, {part}'
    else:
      authors.extend(_split_hugo_parenthesized_name_forms(part))
  return authors


def _split_hugo_parenthesized_name_forms(value):
  """Split `native script (Latin transliteration)` into matchable name forms."""
  match = re.fullmatch(r'(?P<native>.+?)\s*\((?P<latin>[^()]+)\)', value)
  if match is None or not NON_LATIN_HUGO_SCRIPT.search(match.group('native')):
    return [value]
  native = match.group('native').strip()
  latin = match.group('latin').strip()
  return [native, latin] if native and latin else [value]


def _split_hugo_authors(value):
  """Split explicit connectors inside a source-bounded Hugo author credit."""
  authors = []
  for author in re.split(r'\s+(?:and|&|with)\s+', value or '', flags=re.I):
    author = author.strip()
    if author:
      authors.extend(_split_hugo_parenthesized_name_forms(author))
  return authors


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
    match = re.search(r'\s*(?:\([^()]*\)|\[[^\[\]]*\])\s*$', value)
    if match is None:
      return value
    prefix = value[:match.start()].rstrip()
    # A non-Latin name immediately followed by `(Latin form)` is an author
    # transliteration, not a publisher note.
    if prefix and NON_LATIN_HUGO_SCRIPT.fullmatch(prefix[-1]):
      return value
    stripped = prefix
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
