#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Writers' Trust award parser for official history and current-cycle pages.

Maintenance notes:
- V1 uses Writers' Trust official pages only. Current award pages are parsed as
  supplements to the long Writers & Books history pages, not as replacement
  fallbacks.
- The official pages mix archive blocks with prize guidelines and future
  announcement dates. Only concrete year/result sections should emit entries.
"""

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


AWARD_NAME = "Writers' Trust Award"

SEMANTIC_TAGS = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li')
AUTHOR_PREFIX_RE = re.compile(r'^\s*(?:by|author|authors)\s*:\s*', re.I)


def _category_key(value):
  return normalize_heading(value).replace('non fiction', 'nonfiction')


class WritersTrustOfficialParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def __init__(
      self, award_name=AWARD_NAME, category='', category_aliases=(),
      current_url='', current_page_enabled=True):
    self.award_name = award_name
    self.category = category
    self.category_aliases = tuple(category_aliases or (category,))
    self.category_keys = {_category_key(alias) for alias in self.category_aliases}
    self.current_url = current_url
    self.current_page_enabled = current_page_enabled

  def parse(
      self, html, base_url, name=None, fetch_url=None, current_url=None,
      current_pages=(), log=None, progress=None):
    name = name or self.award_name
    rows = self.page_rows(html, base_url)
    notes = []

    pages = list(current_pages or ())
    supplement_url = current_url if current_url is not None else self.current_url
    if self.current_page_enabled and fetch_url is not None and supplement_url:
      try:
        if progress is not None:
          progress(1, 1, f'Fetching {name} current award page')
        pages.append((supplement_url, fetch_url(supplement_url)))
      except Exception as err:
        notes.append(f'{name} current award page could not be fetched: {supplement_url}: {err}')
        if log is not None:
          log(f'{name} current award page failed: {supplement_url}: {err}')

    for url, page_html in pages:
      rows.extend(self.page_rows(page_html, url))

    if not rows and self.is_security_checkpoint(html):
      raise ValueError('Writers Trust official page returned a security checkpoint.')
    if not rows:
      raise ValueError(f'No {name} entries found on the official Writers Trust pages.')

    rows = self.dedupe_rows(rows)
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def page_rows(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    if soup.select_one('[data-winner]') is not None:
      return self.modern_history_rows(soup,base_url)
    if soup.select_one('.book-title') is not None and self.has_award_heading(soup):
      return self.modern_current_rows(soup,base_url)
    for removable in soup.find_all(['script', 'style', 'sup']):
      removable.decompose()
    nodes = [
      {'node': node, 'text': self.clean_text(node)}
      for node in soup.find_all(SEMANTIC_TAGS)
    ]

    rows = []
    consumed = set()
    current_year = None
    current_result = None

    for index, item in enumerate(nodes):
      if index in consumed:
        continue
      node = item['node']
      text = item['text']
      if not text:
        continue

      boundary = self.boundary_from_text(text)
      if boundary is not None:
        year, result = boundary
        if year is not None:
          current_year = year
          current_result = None
        if result is not None:
          current_result = result
        continue

      if self.is_stop_section(text):
        current_result = None
        continue

      if current_year is None or current_result is None:
        continue

      parsed = self.row_from_node(node, text, index, nodes, consumed, base_url)
      if parsed is None:
        continue
      title, author, source_url, author_indexes = parsed
      consumed.update(author_indexes)
      rows.append({
        'award_year': str(current_year),
        'title': title,
        'author': author,
        'result': current_result,
        'source_url': source_url or base_url,
        'category': self.category,
      })
    return rows

  def has_award_heading(self,soup):
    key=normalize_heading(self.award_name)
    return any(normalize_heading(h.get_text(' ',strip=True))==key for h in soup.find_all(['h1','h2','h3']))

  def modern_history_rows(self,soup,base_url):
    rows=[]
    for card in soup.select('[data-winner]'):
      label=card.get('data-winner')
      if label not in ('winner','finalist'):continue
      group=None;year=None
      for parent in card.parents:
        if not getattr(parent,'find',None):continue
        heading=parent.find('h4',recursive=False)
        if heading is not None and re.fullmatch(r'(?:19|20)\d{2}',self.clean_text(heading)):
          group=parent;year=self.clean_text(heading);break
      if group is None:continue
      award=group.parent.find('h3',recursive=False)
      if award is None or normalize_heading(self.clean_text(award))!=normalize_heading(self.award_name):continue
      title=card.select_one('.book-title')
      authors=list(dict.fromkeys(self.clean_text(h) for h in card.find_all('h4') if self.clean_text(h)))
      if title is None or not authors:continue
      rows.append({'award_year':year,'title':self.clean_title(self.clean_text(title)),
        'author':self.clean_author(' & '.join(authors)),
        'result':RESULT_WINNER if label=='winner' else RESULT_SHORTLISTED,
        'source_url':base_url,'category':self.category})
    return rows

  def modern_current_rows(self,soup,base_url):
    rows=[]
    for title in soup.select('article .book-title'):
      heading=title.find_previous('h2')
      phase=self.boundary_from_text(self.clean_text(heading)) if heading is not None else None
      if phase is None or phase[0] is None or phase[1] is None:continue
      author=title.find_previous_sibling('h3') or title.find_next_sibling('h4')
      if author is None:continue
      rows.append({'award_year':str(phase[0]),'title':self.clean_title(self.clean_text(title)),
        'author':self.clean_author(self.clean_text(author)),'result':phase[1],
        'source_url':base_url,'category':self.category})
    return rows

  def validate_fetch_payload(self,html,url):
    if self.is_security_checkpoint(html):raise ValueError('Writers Trust official page returned a security checkpoint.')
    soup=BeautifulSoup(html or '','html.parser')
    rows=self.page_rows(html,url)
    if not rows:raise ValueError('Official Writers Trust page did not expose award records.')
    if soup.select_one('[data-winner]') is not None:
      if self.current_url and url.rstrip('/')==self.current_url.rstrip('/'):
        raise ValueError('Writers Trust returned archive markup for the current-page request.')
      if not self.has_award_heading(soup):raise ValueError('Official Writers Trust page did not identify this prize.')
      expected=0
      for card in soup.select('[data-winner]'):
        if card.get('data-winner') not in ('winner','finalist'):continue
        group=next((p for p in card.parents if getattr(p,'find',None) and p.find('h4',recursive=False) is not None and
          re.fullmatch(r'(?:19|20)\d{2}',self.clean_text(p.find('h4',recursive=False)))),None)
        award=group.parent.find('h3',recursive=False) if group else None
        if award is not None and normalize_heading(self.clean_text(award))==normalize_heading(self.award_name):expected+=1
      if len(rows)!=expected:raise ValueError('Official Writers Trust archive has incomplete book cards.')
    elif soup.select_one('.book-title') is not None:
      if self.current_url and url.rstrip('/')!=self.current_url.rstrip('/'):
        raise ValueError('Writers Trust returned current-page markup for an archive request.')
      if len(rows)!=len(soup.select('article .book-title')):raise ValueError('Official Writers Trust current roster has incomplete book cards.')
    return rows

  def boundary_from_text(self, text):
    heading = normalize_heading(text)
    if heading in {'winner', 'winners'}:
      return None, RESULT_WINNER
    if heading in {'finalist', 'finalists', 'shortlist', 'shortlisted'}:
      return None, RESULT_SHORTLISTED

    match = re.match(
      r'^\s*((?:19|20)\d{2})(?:\s+(.+?))?\s*$',
      text,
      re.I)
    if match is None:
      return None

    year = int(match.group(1))
    trailing = normalize_heading(match.group(2) or '')
    if not trailing:
      return year, None
    if trailing in {'winner', 'winners'}:
      return year, RESULT_WINNER
    if trailing in {'finalist', 'finalists', 'shortlist', 'shortlisted'}:
      return year, RESULT_SHORTLISTED
    return None

  def is_stop_section(self, text):
    heading = normalize_heading(text)
    if not heading:
      return False
    stop_prefixes = (
      'about the prize',
      'announcement date',
      'announcement dates',
      'important date',
      'important dates',
      'how to apply',
      'jury',
      'jurors',
      'prize history',
      'submission',
      'submissions',
      'winner announced',
      'winners announced',
      'finalists announced',
    )
    stop_fragments = (
      'announcement date',
      'announcement dates',
      'important date',
      'important dates',
      'winner announced',
      'winners announced',
      'finalists announced',
    )
    return (
      any(heading.startswith(prefix) for prefix in stop_prefixes)
      or any(fragment in heading for fragment in stop_fragments))

  def row_from_node(self, node, text, index, nodes, consumed, base_url):
    linked_title = self.linked_title(node, base_url)
    if linked_title is not None:
      title, source_url = linked_title
      author, author_indexes = self.following_authors(index, nodes, consumed)
      if title and author:
        return title, author, source_url, author_indexes

    parsed = self.parse_title_author_text(text)
    if parsed is None:
      return None
    title, author = parsed
    return title, author, self.first_link_url(node, base_url) or base_url, ()

  def linked_title(self, node, base_url):
    link = node.find('a', href=True)
    if link is None:
      return None
    title = self.clean_title(self.clean_text(link))
    if not title or self.is_non_entry_text(title):
      return None
    return title, urljoin(base_url, link['href'])

  def following_authors(self, index, nodes, consumed):
    authors = []
    author_indexes = []
    for next_index in range(index + 1, len(nodes)):
      if next_index in consumed:
        continue
      item = nodes[next_index]
      text = item['text']
      if not text:
        continue
      if self.boundary_from_text(text) is not None or self.is_stop_section(text):
        break
      if authors and self.looks_like_next_title(item['node'], text):
        break
      author = self.clean_author_line(text)
      if author:
        authors.append(author)
        author_indexes.append(next_index)
        if len(authors) >= 3:
          break
        continue
      if self.looks_like_next_title(item['node'], text):
        break
      if not author:
        continue
    return ' & '.join(authors), tuple(author_indexes)

  def looks_like_next_title(self, node, text):
    if self.parse_title_author_text(text) is not None:
      return True
    link = node.find('a', href=True)
    if link is None:
      return False
    link_text = self.clean_text(link)
    return bool(link_text and normalize_heading(link_text) == normalize_heading(text))

  def parse_title_author_text(self, text):
    if self.is_non_entry_text(text):
      return None
    for pattern in (
        r'^(.+?)\s+by\s+(.+)$',
        r'^(.+?)\s+[\u2013\u2014-]\s+(.+)$',
    ):
      match = re.match(pattern, text, re.I)
      if match is None:
        continue
      title = self.clean_title(match.group(1))
      author = self.clean_author(match.group(2))
      if title and author:
        return title, author
    return None

  def clean_author_line(self, value):
    value = normalize_line(value)
    if self.is_non_entry_text(value):
      return ''
    if re.match(r'^\s*translated by\b', value, re.I):
      return ''
    if re.match(r'^\s*(?:published by|publisher)\b', value, re.I):
      return ''
    if len(value) > 120:
      return ''
    value = AUTHOR_PREFIX_RE.sub('', value).strip()
    return self.clean_author(value)

  def is_non_entry_text(self, value):
    heading = normalize_heading(value)
    if not heading:
      return True
    if self.boundary_from_text(value) is not None:
      return True
    if heading in self.category_keys:
      return True
    if heading.startswith('translated by'):
      return True
    if heading.startswith('published by') or heading.startswith('publisher'):
      return True
    blocked = (
      'about',
      'announcement',
      'award',
      'download',
      'finalists announced',
      'important dates',
      'learn more',
      'more info',
      'prize history',
      'read more',
      'submission',
      'winner announced',
    )
    return any(heading.startswith(prefix) or prefix in heading for prefix in blocked)

  def clean_text(self, node):
    if node is None:
      return ''
    return normalize_line(node.get_text(' ', strip=True).replace('\xa0', ' '))

  def clean_title(self, value):
    value = normalize_line(value)
    value = re.sub(r'\s*,?\s*translated by .+$', '', value, flags=re.I)
    value = strip_publication_notes(value)
    return value.strip(' "\u201c\u201d,')

  def clean_author(self, value):
    value = normalize_line(value)
    value = re.sub(r'\s*,?\s*translated by .+$', '', value, flags=re.I)
    value = strip_publication_notes(value)
    return value.strip(' "\u201c\u201d,')

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True) if node is not None else None
    return urljoin(base_url, link['href']) if link is not None else ''

  def is_security_checkpoint(self, html):
    text = (html or '').casefold()
    return (
      'vercel security checkpoint' in text
      or "we're verifying your browser" in text
      or 'enable javascript to continue' in text)

  def dedupe_rows(self, rows):
    deduped = []
    index_by_key = {}
    for row in rows:
      key = (
        row['award_year'],
        _category_key(row['category']),
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      existing_index = index_by_key.get(key)
      if existing_index is None:
        index_by_key[key] = len(deduped)
        deduped.append(row)
        continue
      if (
          deduped[existing_index].get('result') != RESULT_WINNER
          and row.get('result') == RESULT_WINNER):
        deduped[existing_index] = row
    return deduped

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      year_rows = [
        self.build_award_entry(
          row, row['source_url'], year, row['category'], award=self.award_name)
        for row in by_year[year]
      ]
      entries.extend(assign_positions(
        year_rows, int(year), tied_winners_share_position=True))
    return entries


def parse_writers_trust_official(
    html, base_url, name=AWARD_NAME, award_name=AWARD_NAME, category='',
    category_aliases=(), fetch_url=None, current_url='', current_pages=(),
    log=None, progress=None):
  return WritersTrustOfficialParser(
    award_name, category, category_aliases, current_url).parse(
      html,
      base_url,
      name,
      fetch_url=fetch_url,
      current_url=current_url,
      current_pages=current_pages,
      log=log,
      progress=progress)
