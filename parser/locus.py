#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Locus Poll Awards parser for SFADB pages.

Maintenance notes:
- SFADB year pages render as plain category headings followed by ranked lines.
- The overview page provides the year links; each annual recipe selects one
  configured novel category from those pages.
- All-time poll pages are single citation pages with ranked 'Author, Title (...)'
  rows — author before title, opposite of every other SFADB parser.
- Two separate classes are provided because annual and all-time awards have
  entirely different page structures and entry shapes. A shared base class would
  require overriding so much that it would add indirection without removing code.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    is_author_suffix, split_title_author,
  )
  from calibre_plugins.list_switchboard.parser.base import (
    entry_source_object, imported_entry, parsed_source, ListParserBase)
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import is_author_suffix, split_title_author
  from .base import entry_source_object, imported_entry, parsed_source, ListParserBase
  from .generic import position_sort_key


LOCUS_AWARD = 'Locus Poll Award'
LOCUS_POLL = 'Locus Poll'
YEAR_LINK = re.compile(r'^(19|20)\d{2}$')
YEAR_PAGE_URL = re.compile(r'/Locus_Awards_(\d{4})$')
RANKED_LINE = re.compile(r'^\s*(\d+)\.\s+(.+)$')
ANNUAL_BOUNDARY = frozenset({
  'sf novel', 'novel', 'fantasy novel', 'horror novel', 'horror/dark fantasy novel',
  'dark fantasy horror novel', 'young adult novel', 'young adult book',
  'first novel', 'translated novel', 'novella', 'novelette', 'short story',
  'short fiction', 'collection', 'anthology', 'non fiction', 'nonfiction',
  'illustrated and art book', 'art book', 'editor', 'magazine', 'publisher',
  'artist',
})
ROLE_AWARE_CATEGORIES = frozenset({
  'illustrated and art book', 'art book', 'non fiction', 'nonfiction',
  'translated novel',
})
CONTRIBUTOR_ROLE_PREFIX = re.compile(
  r'\b(?:'
  r'art(?:\s+and\s+adaptation)?|adapted|compiled|edited|illustrated|'
  r'translated|retold|written(?:\s+and\s+illustrated)?'
  r')\s+by\s+',
  re.I)
CONTRIBUTOR_TRAILING_ROLE = re.compile(
  r'\s+(?:eds?\.?|editors?|text|art|artist|illustrator|'
  r'trans(?:lators?)?\d*)\.?$',
  re.I)
CONTRIBUTOR_ROLE_ONLY = re.compile(
  r'^(?:eds?\.?|editors?|text|art|artist|illustrator|'
  r'trans(?:lators?)?\d*)$',
  re.I)


class LocusAnnualAwardsParser(ListParserBase):
  """
  Parses Locus Poll annual award winners and nominees from SFADB year pages.

  Invariants:
  - Winner position is the award year; all other rows get year.NN suffixes.
  - Winner status is carried by a 'Winner:' prefix on the ranked line, not by
    rank number; rank 1 is not assumed to be the winner.
  - Category selection uses the same heading/boundary model as SFADB parsers,
    but ranked lines (1. ...) are never treated as boundaries even when their
    text matches a category name.
  """

  def parse(self, overview_html, base_url, name, category, category_aliases,
            fetch_url=None, log=None, progress=None):
    soup = BeautifulSoup(overview_html, 'html.parser')
    year_links = _locus_year_links(soup, base_url)
    entries = []
    notes = []
    _progress(progress, 0, len(year_links), f'Preparing {name} year pages...')
    for index, year_link in enumerate(year_links, start=1):
      year = year_link['year']
      url = year_link['url']
      _progress(progress, index, len(year_links), f'Fetching Locus Awards {year}...')
      try:
        html = fetch_url(url) if fetch_url is not None else ''
      except Exception as err:
        notes.append(f'Locus Awards {year} could not be fetched: {err}')
        _log(log, 'fetch-failed', {'year': year, 'url': url, 'error': str(err)})
        continue
      year_entries = self.parse_year(html, url, year, category, category_aliases, log=log)
      if year_entries:
        entries.extend(year_entries)
        _log(log, 'year-parsed', {'year': year, 'url': url, 'entries': len(year_entries)})
      else:
        _log(log, 'year-skipped', {'year': year, 'url': url, 'category': category})
    return {
      'name': name,
      'source': parsed_source(name, base_url),
      'entries': sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      'notes': notes,
      'match_series': False,
    }

  def parse_year(self, html, source_url, year, category, category_aliases, log=None):
    return _parse_annual_year(
      html, source_url, year, category, category_aliases, log=log)


class LocusAllTimeAwardsParser(ListParserBase):
  """
  Parses Locus Poll all-time award rankings from a single SFADB citation page.

  Invariants:
  - All entries receive numeric rank positions directly from the page ('1', '2'...).
  - All-time rows are 'Author, Title (publisher)' — author before title, opposite
    of annual rows and every other SFADB parser. SFADB's HTML separates the
    author link text from the following comma, so the parser prefers that
    structural separator to avoid splitting title commas into the author field.
  - All entries carry result='ranked'; there is no winner/nominee distinction.
  """

  def parse(self, html, url, name, poll_year, category, log=None, progress=None):
    _progress(progress, 1, 1, f'Parsing {name}...')
    soup = BeautifulSoup(html, 'html.parser')
    entries = []
    for line in _locus_text_lines(soup):
      match = RANKED_LINE.match(line)
      if match is None:
        continue
      parsed = _parse_all_time_item(match.group(2))
      if parsed is None:
        continue
      entries.append(imported_entry(
        match.group(1),
        parsed['title'],
        parsed['author'],
        source=entry_source_object(url),
        poll_year=str(poll_year),
        award=LOCUS_POLL,
        category=category,
        result='ranked'))
    _log(log, 'all-time-parsed', {'url': url, 'entries': len(entries)})
    return {
      'name': name,
      'source': parsed_source(name, url),
      'entries': sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      'notes': [],
      'match_series': False,
    }


def _locus_year_links(soup, base_url):
  links = []
  seen = set()
  for link in soup.find_all('a', href=True):
    text = link.get_text(' ', strip=True)
    if not YEAR_LINK.match(text):
      continue
    url = urljoin(base_url, link['href'])
    match = YEAR_PAGE_URL.search(url)
    if match is None:
      continue
    year = int(match.group(1))
    if year in seen:
      continue
    seen.add(year)
    links.append({'year': year, 'url': url})
  return sorted(links, key=lambda item: item['year'])


def _parse_annual_year(html, source_url, year, category, category_aliases, log=None):
  soup = BeautifulSoup(html, 'html.parser')
  rows = _structured_annual_rows(soup, category, category_aliases)
  if rows is None:
    lines = _locus_text_lines(soup)
    category_lines = _annual_category_lines(lines, category_aliases)
    rows = []
    for line in category_lines:
      match = RANKED_LINE.match(line)
      item_text = match.group(2) if match is not None else line
      parsed = _parse_annual_item(item_text)
      if parsed is None:
        continue
      rows.append(parsed)

  entries = []
  suffix_index = 0
  winner_seen = False
  for row in rows:
    if row['result'] == 'winner' and not winner_seen:
      position = str(year)
      winner_seen = True
    else:
      suffix_index += 1
      position = f'{year}.{suffix_index:02d}'
    entries.append(imported_entry(
      position,
      row['title'],
      row.get('authors', row['author']),
      source=entry_source_object(source_url),
      award_year=str(year),
      award=LOCUS_AWARD,
      category=category,
      result=row['result']))
  return entries


def _structured_annual_rows(soup, category, aliases):
  """
  Parse SFADB's category blocks while preserving linked multi-author credits.

  Some annual rows separate three or more authors with both commas and an
  ampersand. The generic text splitter cannot distinguish the first author
  comma from a comma inside a title. SFADB's bold title and linked-person nodes
  provide that boundary; malformed/plain-text pages continue through the
  existing text fallback.
  """
  normalized_aliases = {_normalize_heading(alias) for alias in aliases}
  parse_contributor_roles = _normalize_heading(category) in ROLE_AWARE_CATEGORIES
  for block in soup.find_all('div', class_='categoryblock'):
    heading = block.find('div', class_='category')
    if heading is None:
      continue
    if _normalize_heading(heading.get_text(' ', strip=True)) not in normalized_aliases:
      continue
    rows = []
    for item in block.find_all('li'):
      parsed = _parse_annual_item(item.get_text(' ', strip=True))
      if parsed is None:
        continue
      if parse_contributor_roles:
        parsed = _restore_role_aware_contributors(item, parsed)
      else:
        parsed = _restore_structured_authors(item, parsed)
      rows.append(parsed)
    return rows
  return None


def _restore_role_aware_contributors(item, parsed):
  """
  Use the SFADB title node to isolate role-rich contributor credits.

  Locus Non-Fiction, Art Book, and Translated Novel rows can mix writers,
  editors, adapters, translators, artists, and illustrators. The import schema
  intentionally stores their names rather than roles, so each becomes a
  canonical author while role labels and ``et al.`` are discarded.
  """
  title_node = item.find('b')
  if title_node is None:
    return parsed
  title = _normalize_line(title_node.get_text(' ', strip=True))
  item_text = _strip_publication_notes(
    _normalize_line(item.get_text(' ', strip=True)))
  _, separator, credit = item_text.partition(title)
  if not title or not separator:
    return parsed
  authors = _split_role_aware_contributors(credit.lstrip(' ,'))
  if not authors:
    return parsed
  parsed['title'] = title.strip(' "\u201c\u201d,')
  parsed['authors'] = authors
  return parsed


def _split_role_aware_contributors(value):
  value = CONTRIBUTOR_ROLE_PREFIX.sub('; ', value)
  value = re.sub(r'\bwith\s+', '; ', value, flags=re.I)
  value = re.sub(
    r'(?:^|[;,])\s*(?:artist|illustrator)\s+(?=\S)',
    '; ',
    value,
    flags=re.I)
  authors = []
  for raw_group in re.split(r'\s*[,;]\s*', value):
    group = CONTRIBUTOR_TRAILING_ROLE.sub('', raw_group).strip(' ,;.')
    if not group or CONTRIBUTOR_ROLE_ONLY.fullmatch(group):
      continue
    if re.match(r'^et\s+al\.?$', group, re.I):
      continue
    if is_author_suffix(group) and authors:
      authors[-1] = f'{authors[-1]}, {group}'
      continue
    group = _expand_shared_contributor_surname(group)
    for author in re.split(r'\s+(?:&|and)\s+', group, flags=re.I):
      author = author.strip(' ,;.')
      if author and author not in authors:
        authors.append(author)
  return authors


def _expand_shared_contributor_surname(value):
  match = re.fullmatch(r'([^,&;]+?)\s+(?:&|and)\s+([^,&;]+)', value, re.I)
  if match is None:
    return value
  left, right = (part.strip() for part in match.groups())
  right_words = right.split()
  if len(left.split()) == 1 and len(right_words) > 1:
    return f'{left} {right_words[-1]} & {right}'
  return value


def _restore_structured_authors(item, parsed):
  title_node = item.find('b')
  first_author_link = item.find('a')
  if title_node is None or first_author_link is None:
    return parsed
  descendants = list(item.descendants)
  if descendants.index(title_node) > descendants.index(first_author_link):
    return parsed

  title = _normalize_line(title_node.get_text(' ', strip=True))
  if not title or title == parsed['title']:
    return parsed
  authors = [
    _normalize_line(link.get_text(' ', strip=True))
    for link in item.find_all('a')
  ]
  authors = [author for author in authors if author]
  if len(authors) < 2:
    return parsed

  # Only accept a structurally recovered credit when removing the linked names
  # leaves punctuation/conjunctions. This excludes illustrator/editor role
  # links from changing the established text-parser behavior.
  item_text = _strip_publication_notes(
    _normalize_line(item.get_text(' ', strip=True)))
  _, separator, credit = item_text.partition(title)
  if not separator:
    return parsed
  remainder = credit.lstrip(' ,')
  for author in authors:
    remainder = remainder.replace(author, '', 1)
  if not re.fullmatch(r'[\s,&]*(?:(?:and)[\s,&]*)*', remainder, re.I):
    return parsed

  parsed['title'] = title.strip(' "\u201c\u201d,')
  parsed['authors'] = authors
  return parsed


def _annual_category_lines(lines, aliases):
  normalized_aliases = {_normalize_heading(alias) for alias in aliases}
  in_category = False
  selected = []
  for line in lines:
    heading = _normalize_heading(line)
    if heading in normalized_aliases:
      in_category = True
      continue
    if in_category and _is_annual_boundary(line):
      break
    if in_category:
      selected.append(line)
  return selected


def _is_annual_boundary(line):
  # Ranked lines are data rows, not boundaries, even if their text matches a
  # category heading after normalization.
  if RANKED_LINE.match(line):
    return False
  heading = _normalize_heading(line)
  if not heading:
    return False
  if heading.startswith('special award'):
    return True
  return heading in ANNUAL_BOUNDARY


def _parse_annual_item(text):
  text = _normalize_line(text)
  result = 'nominee'
  text = _strip_tie_marker(text)
  if text.casefold().startswith('winner:'):
    result = 'winner'
    text = text.split(':', 1)[1].strip()
  title, author = _split_title_author(text)
  if not title or not author:
    return None
  return {
    'title': _strip_publication_notes(title).strip(' \"\u201c\u201d,'),
    'author': _strip_publication_notes(author).strip(),
    'result': result,
  }


def _parse_all_time_item(text):
  """
  Parse one ranked all-time line.

  All-time lines are 'Author, Title (publisher)' — author before title,
  opposite of annual rows. Prefer the spaced comma produced by
  _ordered_list_item_line() so title commas stay in the title while author
  suffix commas, such as 'Jr.', stay in the author.
  """
  text = _strip_tie_marker(_normalize_line(text))
  work_text = _strip_publication_notes(text)
  author, title = _split_all_time_author_title(work_text)
  if not title or not author:
    return None
  return {
    'title': _strip_publication_notes(title).strip(' \"\u201c\u201d,'),
    'author': _strip_publication_notes(author).strip(),
  }


def _split_all_time_author_title(text):
  if ' , ' in text:
    return [part.strip() for part in text.split(' , ', 1)]
  if ',' not in text:
    return '', ''
  return [part.strip() for part in text.split(',', 1)]


def _split_title_author(text):
  return split_title_author(text)


def _locus_text_lines(soup):
  """
  Locus text extraction with numbered-list awareness.

  ol/li elements are numbered explicitly so RANKED_LINE can match them after
  BeautifulSoup flattens the DOM. Falls back to plain text when no ranked lines
  appear in block-tag output.
  """
  block_lines = []
  for node in soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'li']):
    if node.name == 'li' and node.find_parent('ol') is not None:
      line = _ordered_list_item_line(node)
    else:
      line = _normalize_line(node.get_text(' ', strip=True))
    block_lines.append(line)
  block_lines = [line for line in block_lines if line]
  if any(RANKED_LINE.match(line) for line in block_lines):
    full_text_lines = _full_text_lines(soup)
    if _has_annual_category_heading(full_text_lines) and not _has_annual_category_heading(block_lines):
      return full_text_lines
    return block_lines
  return _full_text_lines(soup)


def _has_annual_category_heading(lines):
  return any(_normalize_heading(line) in ANNUAL_BOUNDARY for line in lines)


def _full_text_lines(soup):
  for br in soup.find_all('br'):
    br.replace_with('\n')
  text = soup.get_text(' ')
  text = re.sub(r'\s*\n\s*', '\n', text)
  return [_normalize_line(line) for line in text.splitlines() if _normalize_line(line)]


def _ordered_list_item_line(node):
  """
  Return one ranked line from SFADB's malformed citation-page lists.

  SFADB all-time citation pages omit closing </li> tags, so BeautifulSoup's
  html.parser nests the rest of the ordered list inside the first item. Reading
  only direct content before a nested li/br keeps each rank separate.
  """
  parts = []
  for child in node.contents:
    if isinstance(child, NavigableString):
      parts.append(str(child))
      continue
    if not isinstance(child, Tag):
      continue
    if child.name in ('br', 'li'):
      break
    parts.append(child.get_text(' ', strip=True))
  line = _normalize_line(' '.join(parts))
  if not line:
    return ''
  rank = _normalize_line(node.get('value') or '')
  if not rank:
    rank = str(sum(
      1 for sibling in node.find_previous_siblings('li')
      if sibling.parent is node.parent) + 1)
  return f'{rank}. {line}'


def _strip_publication_notes(value):
  value = _normalize_line(value)
  while True:
    stripped = _strip_trailing_balanced_note(value)
    if stripped == value:
      return value
    value = stripped


def _strip_trailing_balanced_note(value):
  pairs = {')': '(', ']': '['}
  closing = value[-1:] if value else ''
  opening = pairs.get(closing)
  if opening is None:
    return value
  depth = 0
  for index in range(len(value) - 1, -1, -1):
    character = value[index]
    if character == closing:
      depth += 1
    elif character == opening:
      depth -= 1
      if depth == 0:
        return value[:index].rstrip()
  return value


def _strip_tie_marker(value):
  value = re.sub(r'^\s*\(tie\)\s*:?\s*', '', value, flags=re.I)
  value = re.sub(r'\s*\(tie\)\s*$', '', value, flags=re.I)
  return value.strip()


def _normalize_line(value):
  return re.sub(r'\s+', ' ', value or '').strip()


def _normalize_heading(value):
  value = _normalize_line(value).casefold()
  value = value.replace('&', ' and ')
  value = re.sub(r'[^a-z0-9/]+', ' ', value)
  return re.sub(r'\s+', ' ', value).strip()


def _log(log, label, data):
  if log is not None:
    log(f'Locus Awards {label}: {data}')


def _progress(progress, done, total, message):
  if progress is not None:
    progress(done, total, message)


def parse_locus_annual_awards(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=None, log=None, progress=None):
  return LocusAnnualAwardsParser().parse(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=fetch_url, log=log, progress=progress)


def parse_locus_all_time_awards(html, url, name, poll_year, category, log=None, progress=None):
  return LocusAllTimeAwardsParser().parse(
    html, url, name, poll_year, category, log=log, progress=progress)
