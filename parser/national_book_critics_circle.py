#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
National Book Critics Circle Award parsers.

Maintenance notes:
- The official source is the NBCC `past-awards/YYYY/` archive family. It has
  appeared as category sections, winner/finalist subheadings, and card/list
  rows over time, so parsing stays structural but accepts several row shapes.
- Wikipedia is a replacement fallback per configured category. It commonly
  uses rowspans and blank inherited year/result cells.
- V1 imports book-focused winners/finalists only. Longlists and non-book
  honors are intentionally rejected even when present in the same source page.
"""

import re
import json
import unicodedata
from copy import deepcopy
from urllib.parse import urljoin,urlsplit

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, split_title_author, strip_publication_notes,is_author_suffix,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
  from calibre_plugins.list_switchboard.parser.annual_updates import read_annual_pages
  from calibre_plugins.list_switchboard.parser.incremental import ParsedUnitCache
  from calibre_plugins.list_switchboard.errors import ImportCancelledError,CamoufoxRequiredError
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, split_title_author, strip_publication_notes,is_author_suffix,
  )
  from .generic import position_sort_key
  from .annual_updates import read_annual_pages
  from .incremental import ParsedUnitCache
  from errors import ImportCancelledError,CamoufoxRequiredError


AWARD_NAME = 'National Book Critics Circle Award'
OFFICIAL_URL = 'https://www.bookcritics.org/awards/past/'

HEADER_ALIASES = {
  'award': 'category',
  'category': 'category',
  'prize': 'category',
  'author': 'author',
  'authors': 'author',
  'writer': 'author',
  'writers': 'author',
  'title': 'title',
  'book': 'title',
  'work': 'title',
  'winner': 'title',
  'novel': 'title',
  'result': 'result',
  'status': 'result',
  'year': 'year',
}

RESULT_MARKERS = (
  'winner', 'winners', 'winning', 'joint winner', 'joint winners',
  'finalist', 'finalists', 'shortlist', 'shortlisted', 'short list',
  'longlist', 'longlisted', 'long list',
)


def _normalized_text(value):
  value = unicodedata.normalize('NFKC', value or '')
  return value.replace('\xa0', ' ')


def _key(value):
  return normalize_heading(_normalized_text(value)).replace('non fiction', 'nonfiction')


class NationalBookCriticsCircleMixin(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def __init__(self, category, category_aliases=()):
    self.category = category
    self.category_aliases = tuple(category_aliases or (category,))
    self.category_keys = {
      key for alias in self.category_aliases
      for key in (_key(alias), self.heading_category_key(alias))
      if key
    }

  def clean_text(self, node):
    if node is None:
      return ''
    soup = BeautifulSoup(str(node), 'html.parser')
    for removable in soup.find_all(['script', 'style', 'sup']):
      removable.decompose()
    return normalize_line(_normalized_text(soup.get_text(' ', strip=True)))

  def clean_title(self, value):
    value = strip_publication_notes(normalize_line(_normalized_text(value)))
    value = re.sub(r'^\s*(?:title|book|work)\s*:\s*', '', value, flags=re.I)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def clean_author(self, value):
    value = strip_publication_notes(normalize_line(_normalized_text(value)))
    value = re.sub(r'^\s*(?:by\s+|(?:authors?|writers?)\s*:\s*)', '', value, flags=re.I)
    value = re.sub(r'\s+translated\s+by\s+.+$', '', value, flags=re.I).strip()
    value = re.sub(r',?\s+translat(?:ed|ion)\s+(?:from\b.+?\s+)?by\s+.+$', '', value, flags=re.I).strip()
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def category_matches(self, value):
    return self.heading_category_key(value) in self.category_keys

  def heading_category_key(self, value):
    text = _key(value)
    text = re.sub(r'\b(?:national book critics circle|nbcc|award|awards|prize)\b', ' ', text)
    text = re.sub(r'\b(?:' + '|'.join(re.escape(marker) for marker in RESULT_MARKERS) + r')\b', ' ', text)
    text = re.sub(r'\b(?:19|20)\d{2}\b', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

  def result_from_text(self, value):
    key = _key(value)
    if re.search(r'\blong\s*list(?:ed)?\b|\blonglist(?:ed)?\b', key):
      return 'longlisted'
    if re.search(r'\b(?:finalist|finalists|short\s*list|shortlist|shortlisted)\b', key):
      return RESULT_SHORTLISTED
    if re.search(r'\b(?:winner|winners|winning|joint winner|joint winners)\b', key):
      return RESULT_WINNER
    return ''

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def year_from_url(self, value):
    match = re.search(r'/past-awards/((?:19|20)\d{2})(?:/|$)', value or '')
    return int(match.group(1)) if match is not None else None

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True) if node is not None else None
    if link is None and getattr(node, 'name', None) == 'a' and node.get('href'):
      link = node
    return urljoin(base_url, link['href']) if link is not None else ''

  def title_link_text(self, node):
    if node is None:
      return ''
    for link in node.find_all('a', href=True):
      text = self.clean_text(link)
      text_key = _key(text)
      if text and text_key not in self.category_keys:
        if self.year_from_text(text) is None and text_key not in {'read more', 'more'}:
          return text
    return ''

  def strip_entry_prefix(self, text):
    text = normalize_line(_normalized_text(text))
    text = re.sub(r'^\s*(?:winner|winners|joint\s+winners?|finalists?|shortlist(?:ed)?|short\s+list|longlist(?:ed)?)\s*:?\s*', '', text, flags=re.I)
    text = re.sub(
      r'^\s*(?:' + '|'.join(re.escape(alias) for alias in self.category_aliases) +
      r')\s*[:\u2013\u2014-]\s*',
      '',
      text,
      flags=re.I)
    return normalize_line(text)

  def parse_title_author_text(self, text):
    text = self.strip_entry_prefix(text)
    if not text or self.result_from_text(text) == 'longlisted':
      return '', ''
    text = re.sub(r'\s*\[[^\[\]]*\]\s*$', '', text).strip()
    by_match = re.match(r'^(.+?)\s+(?:by|written\s+by|edited\s+by)\s+(.+)$', text, re.I)
    if by_match is not None:
      return self.clean_title(by_match.group(1)), self.clean_author(by_match.group(2))
    dash_match = re.match(r'^(.+?)\s+[\u2013\u2014-]\s+(.+)$', text)
    if dash_match is not None:
      return self.clean_title(dash_match.group(1)), self.clean_author(dash_match.group(2))
    title, author = split_title_author(text)
    if title and author:
      return self.clean_title(title), self.clean_author(author)
    return '', ''

  def parse_node_entry(self, node, base_url):
    marked=node.find(['em','i'])
    if marked is not None:
      before,after=[],[]
      started=False
      for text_node in node.find_all(string=True):
        if text_node.find_parent(['script','style','figure']):
          continue
        if marked in text_node.parents:
          started=True
        (after if started else before).append(str(text_node))
      author=normalize_line(''.join(before)).strip()
      prefix=''
      if author and not author.endswith(',') and ',' in author:
        credit,fragment=author.rsplit(',',1)
        if len(fragment.strip())==1:
          author,prefix=credit,fragment.strip()
      author=self.strip_entry_prefix(author.rstrip(', '))
      title=prefix+normalize_line(''.join(after))
      title=re.sub(r'\)\s*\.$',')',title)
      title,author=self.clean_title(title),self.clean_author(author)
      if title and author:
        return title,author,base_url
    text = self.clean_text(node)
    if node.name=='li' and node.find_parent(class_='content-regular') and ',' in text:
      author,title=self.strip_entry_prefix(text).split(',',1)
      if ',' in title:
        suffix,remainder=title.split(',',1)
        if is_author_suffix(suffix.strip()):
          author,title=author+', '+suffix.strip(),remainder
      title,author=self.clean_title(title),self.clean_author(author)
      if title and author:
        return title,author,base_url
    title = self.title_link_text(node)
    if title:
      remainder = normalize_line(text.replace(title, ' ', 1))
      remainder = self.strip_entry_prefix(remainder)
      by_match = re.search(r'(?:^|\s)(?:by|written\s+by|edited\s+by)\s+(.+)$', remainder, re.I)
      author = self.clean_author(by_match.group(1) if by_match is not None else remainder)
      if author:
        return self.clean_title(title), author, self.first_link_url(node, base_url) or base_url
    title, author = self.parse_title_author_text(text)
    return title, author, self.first_link_url(node, base_url) or base_url

  def row(self, year, title, author, result, source_url):
    if result == 'longlisted' or not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result or RESULT_SHORTLISTED,
      'source_url': source_url,
      'category': self.category,
      'award': self.AWARD_NAME,
    }

  def dedupe_rows(self, rows):
    deduped = []
    index_by_key = {}
    for row in rows:
      if not row:
        continue
      title_key = normalize_heading(row.get('title', ''))
      author_key = normalize_heading(row.get('author', ''))
      if not title_key or not author_key:
        continue
      key = (row.get('award_year'), _key(row.get('category', '')), title_key, author_key)
      existing_index = index_by_key.get(key)
      if existing_index is None:
        index_by_key[key] = len(deduped)
        deduped.append(row)
        continue
      existing = deduped[existing_index]
      if existing.get('result') != RESULT_WINNER and row.get('result') == RESULT_WINNER:
        promoted = dict(existing)
        promoted['result'] = RESULT_WINNER
        promoted['source_url'] = row.get('source_url') or existing.get('source_url')
        deduped[existing_index] = promoted
    return deduped

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      try:
        year = int(row['award_year'])
      except Exception:
        continue
      by_year.setdefault(year, []).append(row)
    entries = []
    for year in sorted(by_year):
      year_rows = sorted(
        by_year[year],
        key=lambda row: 0 if row.get('result') == RESULT_WINNER else 1)
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in year_rows
      ]
      entries.extend(assign_positions(
        award_rows, year, tied_winners_share_position=True))
    return entries

  def parsed_from_rows(self, rows, name, base_url):
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def table_grid(self, table):
    grid = []
    rowspans = {}
    for tr in table.find_all('tr'):
      row = []
      column = 0
      for cell in tr.find_all(['th', 'td'], recursive=False):
        while column in rowspans:
          span_cell, remaining = rowspans[column]
          row.append(span_cell)
          if remaining <= 1:
            del rowspans[column]
          else:
            rowspans[column] = (span_cell, remaining - 1)
          column += 1
        colspan = self.span_value(cell, 'colspan')
        rowspan = self.span_value(cell, 'rowspan')
        for _index in range(colspan):
          row.append(cell)
          if rowspan > 1:
            rowspans[column] = (cell, rowspan - 1)
          column += 1
      while column in rowspans:
        span_cell, remaining = rowspans[column]
        row.append(span_cell)
        if remaining <= 1:
          del rowspans[column]
        else:
          rowspans[column] = (span_cell, remaining - 1)
        column += 1
      if row:
        grid.append(row)
    return grid

  def span_value(self, cell, attr):
    try:
      return max(1, int(cell.get(attr, 1)))
    except Exception:
      return 1

  def header_map(self, grid):
    for index, row in enumerate(grid):
      mapped = {}
      for cell_index, cell in enumerate(row):
        key = HEADER_ALIASES.get(_key(self.clean_text(cell)))
        if key is not None and key not in mapped:
          mapped[key] = cell_index
      if {'year', 'title', 'author'}.issubset(set(mapped)):
        return index, mapped
    return -1, {}

  def cell_at(self, row, header_map, key):
    index = header_map.get(key)
    return row[index] if index is not None and index < len(row) else None


class NationalBookCriticsCircleOfficialParser(NationalBookCriticsCircleMixin):

  def parse(
      self, html, base_url=OFFICIAL_URL, name=AWARD_NAME, fetch_url=None,
      log=None, progress=None,cached_parsed=None,incremental_update=False):
    rows = self.parse_page_rows(html, base_url)
    notes = []
    links = self.year_links(html, base_url)
    if fetch_url is not None and links:
      source_key=json.dumps([base_url,name,self.category,self.category_aliases])
      cache=ParsedUnitCache('official-annual-pages-v1',source_key,cached_parsed,incremental_update)
      prefetched,failed_discovery={},{}
      # The public selector currently lags its latest annual page. Follow only
      # explicit next-year navigation from its newest year, freshly each time.
      if BeautifulSoup(html,'html.parser').select_one('#award-year-select'):
        year,url=links[-1]
        expanded=dict(links)
        while True:
          expanded[year]=url
          try:
            page=fetch_url(url)
          except (ImportCancelledError,CamoufoxRequiredError):
            raise
          except Exception as err:
            failed_discovery[url]=err
            for old_url in cache.old_units:
              old_year=self.year_from_url(old_url)
              if old_year and old_year>year:
                expanded[old_year]=old_url
            break
          prefetched[url]=page
          soup=BeautifulSoup(page,'html.parser')
          next_link=soup.select_one('.post-navigation a[rel~=next]')
          next_url=urljoin(url,next_link['href']) if next_link else ''
          next_year=self.year_from_url(next_url)
          if next_year!=year+1 or urlsplit(next_url).netloc!=urlsplit(base_url).netloc:
            break
          year,url=next_year,next_url
        links=tuple(sorted(expanded.items()))
      def read(page,url):
        year=self.year_from_url(url)
        soup=BeautifulSoup(page,'html.parser')
        label=soup.select_one('.award-finalists-inner > h2.entry-title')
        if label and self.year_from_text(self.clean_text(label))!=year:
          raise ValueError('Official NBCC page identified another award year.')
        return self.parsed_from_rows(self.parse_page_rows(page,url,year),name,url)
      def fetch_year(url):
        if url in failed_discovery:
          raise failed_discovery[url]
        return prefetched[url] if url in prefetched else fetch_url(url)
      refresh_cache=cached_parsed
      if cache.old_units and (prefetched or failed_discovery):
        refresh_cache=deepcopy(cached_parsed)
        for url in set(prefetched)|set(failed_discovery):
          if url in refresh_cache['incremental_state']['units']:
            refresh_cache['incremental_state']['units'][url]['complete']=False
      result=read_annual_pages(source_key,
        [(url,year) for year,url in links],
        fetch_year,read,
        cached_parsed=refresh_cache,incremental_update=incremental_update,
        validate_empty=self.valid_empty_year,progress=progress,allow_partial=True,
        failure_note=lambda url,year,err:f'{name} archive page could not be fetched: {url}: {err}')
      result.update(name=name,source=self.parsed_result(name,base_url,[])['source'])
      return result
    parsed = self.parsed_from_rows(rows, name, base_url)
    parsed['notes'] = notes + parsed.get('notes', [])
    return parsed

  def valid_empty_year(self,html,url,year):
    soup=BeautifulSoup(html,'html.parser')
    block=soup.select_one('.award-finalists-inner')
    label=block.select_one('h2.entry-title') if block else None
    if not label or self.year_from_text(self.clean_text(label))!=year:
      return False
    if not block.select_one('.content-regular, .award-year-list-wrapper'):
      return False
    for node in block.find_all(['h3','li']):
      text=self.clean_text(node)
      if ((node.name=='h3' and self.category_matches(text)) or
          (node.name=='li' and ':' in text and self.category_matches(text.split(':',1)[0]))):
        return False
    return True

  def year_links(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    links = {}
    for link in soup.select('a[href], #award-year-select option[value]'):
      url = urljoin(base_url, link.get('href') or link.get('value'))
      if urlsplit(url).netloc!=urlsplit(base_url).netloc:
        continue
      year = self.year_from_url(url)
      if year is not None:
        links.setdefault(year, url)
    return tuple((year, links[year]) for year in sorted(links))

  def parse_page_rows(self, html, base_url, fallback_year=None):
    soup = BeautifulSoup(html, 'html.parser')
    modern=soup.select('.award-year-list')
    if modern:
      rows=[]
      year=self.year_from_url(base_url) or fallback_year
      for group in modern:
        heading=group.find(['h2','h3'],recursive=False)
        if not heading or not self.category_matches(self.clean_text(heading)):
          continue
        for item in group.find_all('li',recursive=False):
          result=self.result_from_text(' '.join(item.get('class') or []))
          if result not in {RESULT_WINNER,RESULT_SHORTLISTED}:
            continue
          title,author,source=self.parse_node_entry(item,base_url)
          row=self.row(year,title,author,result,source)
          if row:
            rows.append(row)
      return rows
    rows = []
    for table in soup.find_all('table'):
      rows.extend(self.table_rows(table, base_url, fallback_year))
    root = soup.find('main') or soup.find('article') or soup.body or soup
    page_year = (
      self.year_from_url(base_url) or
      self.year_from_text(self.clean_text(soup.find('h1'))) or
      self.year_from_text(self.clean_text(soup.find('title'))) or
      fallback_year)
    current_year = page_year
    current_category = False
    current_result = ''
    for node in root.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li']):
      if node.find_parent(['script', 'style', 'nav', 'header', 'footer', 'table']):
        continue
      text = self.clean_text(node)
      if not text:
        continue
      if node.name in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}:
        node_year = self.year_from_text(text)
        if node_year is not None:
          current_year = node_year
        if self.category_matches(text):
          current_category = True
          current_result = self.result_from_text(text)
          if not current_result and node.find_parent(class_='content-regular'):
            following=node.find_next_sibling(['h2','h3'])
            next_text=self.clean_text(following)
            candidates=node.find_next_sibling('ul')
            if ((self.category_matches(next_text) and self.result_from_text(next_text)==RESULT_SHORTLISTED) or
                (self.heading_category_key(text)=='john leonard' and candidates and
                 len(candidates.find_all('li',recursive=False))==1)):
              current_result=RESULT_WINNER
          continue
        result = self.result_from_text(text)
        if result and not self.heading_category_key(text):
          current_result = result
          continue
        if node.name != 'h1':
          current_category = False
          current_result = ''
        continue
      inline_category=':' in text and self.category_matches(text.split(':',1)[0])
      if (not current_category and not inline_category) or current_year is None:
        continue
      result = self.result_from_text(text) or current_result
      if result == 'longlisted':
        continue
      if result not in {RESULT_WINNER, RESULT_SHORTLISTED}:
        continue
      title, author, source_url = self.parse_node_entry(node, base_url)
      row = self.row(current_year, title, author, result, source_url)
      if row is not None:
        rows.append(row)
    return rows

  def table_rows(self, table, base_url, fallback_year=None):
    grid = self.table_grid(table)
    header_index, header_map = self.header_map(grid)
    if header_index < 0:
      return []
    rows = []
    current_year = fallback_year
    current_result = ''
    for row in grid[header_index + 1:]:
      year_cell = self.cell_at(row, header_map, 'year')
      year = self.year_from_text(self.clean_text(year_cell))
      if year is not None:
        current_year = year
      category_cell = self.cell_at(row, header_map, 'category')
      if category_cell is not None and not self.category_matches(self.clean_text(category_cell)):
        continue
      result_cell = self.cell_at(row, header_map, 'result')
      result_text = self.clean_text(result_cell)
      result = self.result_from_text(result_text)
      if result:
        current_result = result
      else:
        result = current_result or RESULT_SHORTLISTED
      if result == 'longlisted' or current_year is None:
        continue
      title_cell = self.cell_at(row, header_map, 'title')
      author_cell = self.cell_at(row, header_map, 'author')
      title = self.clean_title(self.clean_text(title_cell))
      author = self.clean_author(self.clean_text(author_cell))
      parsed = self.row(
        current_year,
        title,
        author,
        result,
        self.first_link_url(title_cell, base_url) or base_url)
      if parsed is not None:
        rows.append(parsed)
    return rows


class NationalBookCriticsCircleWikipediaParser(NationalBookCriticsCircleMixin):

  def parse(self, html, base_url='', name=AWARD_NAME, **_kwargs):
    rows = self.parse_rows(html, base_url)
    return self.parsed_from_rows(rows, name, base_url)

  def parse_rows(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for table in soup.find_all('table'):
      grid = self.table_grid(table)
      header_index, header_map = self.header_map(grid)
      if header_index < 0:
        continue
      rows.extend(self.table_rows(grid[header_index + 1:], header_map, base_url))
    return rows

  def table_rows(self, grid, header_map, base_url):
    rows = []
    current_year = None
    current_result = ''
    for row in grid:
      year_cell = self.cell_at(row, header_map, 'year')
      year = self.year_from_text(self.clean_text(year_cell))
      if year is not None:
        current_year = year
      category_cell = self.cell_at(row, header_map, 'category')
      if category_cell is not None and not self.category_matches(self.clean_text(category_cell)):
        continue
      result_cell = self.cell_at(row, header_map, 'result')
      result_text = self.clean_text(result_cell)
      result = self.result_from_text(result_text)
      if result:
        current_result = result
      else:
        result = current_result or RESULT_WINNER
      if result == 'longlisted' or current_year is None:
        continue
      title_cell = self.cell_at(row, header_map, 'title')
      author_cell = self.cell_at(row, header_map, 'author')
      title = self.clean_title(self.clean_text(title_cell))
      author = self.clean_author(self.clean_text(author_cell))
      parsed = self.row(
        current_year,
        title,
        author,
        result,
        self.first_link_url(title_cell, base_url) or base_url)
      if parsed is not None:
        rows.append(parsed)
    return rows
