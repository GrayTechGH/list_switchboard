#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Romance Writers of Australia RUBY award parser.

Maintenance notes:
- The current RWAus Shopify site exposes migrated finalist posts through search
  suggestion JSON, but not a complete result archive.
- Historical official results use the entry-content boundary, RUBY accordion
  sections and year/placing tables. ELLA panels, sidebars, interviews and
  contest rules are outside this roster.
- The current search response and CDX discovery stay fresh. Only parsed rows
  from an unchanged immutable capture are reused; no raw pages are cached.
"""

import json
import re
from urllib.parse import urljoin,urlsplit,parse_qsl,urlencode

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
  from calibre_plugins.list_switchboard.parser.incremental import ParsedUnitCache,project_source_rows,restore_source_rows
  from calibre_plugins.list_switchboard.errors import ImportCancelledError,CamoufoxRequiredError
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key
  from .incremental import ParsedUnitCache,project_source_rows,restore_source_rows
  from errors import ImportCancelledError,CamoufoxRequiredError


RWAUS_RUBY_AWARD_NAME = 'Romance Writers of Australia RUBY Awards'
RWAUS_RUBY_SEARCH_URL = (
  'https://romanceaustralia.com/search/suggest.json?q=RUBY'
  '&resources%5Btype%5D=article,page&resources%5Blimit%5D=50')
RWAUS_RUBY_OLD_URL = (
  'http://romanceaustralia.com/awards/romantic-book-of-the-year-ruby-2/')
RWAUS_RUBY_CDX_URL = (
  'https://web.archive.org/cdx?url=romanceaustralia.com/awards/'
  'romantic-book-of-the-year-ruby-2/&output=json'
  '&fl=timestamp,original,statuscode,mimetype,digest'
  '&filter=statuscode:200&collapse=digest&limit=20')

RESULT_PRIORITY = {RESULT_WINNER: 0, RESULT_SHORTLISTED: 1}


class RomanceWritersAustraliaRubyParser(AwardParserBase):

  AWARD_NAME = RWAUS_RUBY_AWARD_NAME

  def parse(
      self, html, base_url=RWAUS_RUBY_SEARCH_URL, name=RWAUS_RUBY_AWARD_NAME,
      fetch_url=None, archived_pages=None,cached_parsed=None,incremental_update=False):
    if fetch_url is not None and archived_pages is None:
      return self.parse_live_sources(html,base_url,name,fetch_url,cached_parsed,incremental_update)
    notes = []
    rows = []
    rows.extend(self.parse_shopify_rows(html, base_url))
    if archived_pages is not None:
      rows.extend(self.parse_archived_pages(archived_pages))
    elif fetch_url is not None:
      rows.extend(self.fetch_archived_rows(fetch_url, notes))
    rows = self.dedupe_rows(rows)
    entries = self.entries_from_rows(rows)
    self.add_coverage_notes(rows, notes)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def parse_live_sources(self,html,base_url,name,fetch_url,cached_parsed,incremental_update):
    cache=ParsedUnitCache('rwaus-ruby-immutable-capture-v1',json.dumps([
      base_url,name,type(self).__name__,RWAUS_RUBY_CDX_URL]),cached_parsed,incremental_update)
    notes=[]
    def previous(key):
      try:return restore_source_rows(cache.previous(key),(cache.old_units.get(key) or {}).get('metadata') or {})
      except (ValueError,TypeError):return []
    data=self.load_json(html)
    resources=data.get('resources',{}) if isinstance(data,dict) else {}
    results=resources.get('results',{}) if isinstance(resources,dict) else {}
    current_complete=isinstance(results,dict) and isinstance(results.get('articles'),list)
    current=self.parse_shopify_rows(html,base_url) if current_complete else previous('shopify')
    if not current_complete:
      notes.append('RWAus current search did not expose an article result list; retained cached finalist rows.')
    archive,revision,complete=previous('archive'),None,False
    try:
      revision=self.snapshot_from_cdx(fetch_url(RWAUS_RUBY_CDX_URL))
      if not revision:
        raise ValueError('RWAus archived RUBY winner index did not expose a usable snapshot.')
      old=cache.old_units.get('archive') or {}
      if archive and old.get('complete') is True and old.get('revision')==revision:
        complete=True
      else:
        fresh=self.parse_archived_pages(((revision['url'],fetch_url(revision['url'])),))
        if not fresh or not any(r['result']==RESULT_WINNER for r in fresh):
          raise ValueError('RWAus archived RUBY page did not expose a usable result roster.')
        archive,complete=fresh,True
    except (ImportCancelledError,CamoufoxRequiredError):
      raise
    except Exception as err:
      notes.append(f'RWAus archived RUBY results could not be refreshed: {err}')
    rows=self.dedupe_rows(current+archive)
    entries=sorted(self.entries_from_rows(rows),key=lambda item:position_sort_key(item.get('position','')))
    for key,source_rows,rev,done in (('shopify',current,None,current_complete),('archive',archive,revision,complete)):
      projected,metadata=project_source_rows(source_rows,entries,
        lambda row:(str(row['award_year']),normalize_heading(row['category']),normalize_heading(row['title']),normalize_heading(row.get('author',' '.join(row.get('authors',[]))))))
      cache.put(key,projected,revision=rev,complete=done,metadata=metadata)
    self.add_coverage_notes(rows,notes)
    parsed=self.parsed_result(name,base_url,entries,notes=notes)
    parsed['incremental_state']=cache.state(entries)
    parsed['incremental_state']['discovery']={'refresh_units':['shopify']}
    return parsed

  def parse_shopify_rows(self, html, base_url):
    data = self.load_json(html)
    articles = self.shopify_articles(data)
    rows = []
    for article in articles:
      if not self.accept_shopify_article(article):
        continue
      source_url = urljoin(base_url, article.get('url') or '')
      source=urlsplit(source_url)
      source_url=source._replace(query=urlencode([(k,v) for k,v in parse_qsl(source.query,keep_blank_values=True)
        if k not in ('_pos','_psq','_psid','_ss')]),fragment='').geturl()
      year = self.article_year(article)
      if year is None:
        continue
      rows.extend(self.parse_finalist_article(article.get('body') or '', source_url, year))
    return rows

  def load_json(self, value):
    try:
      return json.loads(value or '{}')
    except Exception:
      return {}

  def shopify_articles(self, data):
    resources = data.get('resources') if isinstance(data, dict) else {}
    results = resources.get('results') if isinstance(resources, dict) else {}
    articles = results.get('articles') if isinstance(results, dict) else []
    return articles if isinstance(articles, list) else []

  def accept_shopify_article(self, article):
    if not isinstance(article, dict):
      return False
    text = ' '.join([
      article.get('title') or '',
      article.get('handle') or '',
      ' '.join(article.get('tags') or ()),
      BeautifulSoup(article.get('body') or '', 'html.parser').get_text(' ', strip=True),
    ])
    heading = normalize_heading(text)
    if 'ruby' not in heading and 'romantic book of the year' not in heading:
      return False
    title=normalize_heading(' '.join([article.get('title') or '',article.get('handle') or '']))
    if re.search(r'\b(?:finalists?|nominees?)\b',title):
      return True
    soup=BeautifulSoup(article.get('body') or '','html.parser')
    return any(normalize_heading(h.get_text(' ',strip=True)).startswith('and the finalists are')
      for h in soup.find_all(['h2','h3'])) and bool(soup.find('h4'))

  def article_year(self, article):
    for value in (article.get('title'), article.get('body'), article.get('published_at')):
      year = self.year_from_text(value)
      if year is not None:
        return year
    return None

  def parse_finalist_article(self, body_html, source_url, year):
    soup = BeautifulSoup(body_html or '', 'html.parser')
    rows = []
    category = None
    for node in soup.find_all(['h2', 'h3', 'h4', 'p', 'li']):
      if node.name in {'h2', 'h3', 'h4'}:
        category = self.category_from_heading(node)
        continue
      if category is None:
        continue
      parsed = self.title_author_from_finalist_node(node)
      if parsed is None:
        continue
      title, author = parsed
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': RESULT_SHORTLISTED,
        'source_url': source_url,
        'category': category,
        '_source_order': len(rows),
      })
    return rows

  def category_from_heading(self, node):
    text = self.clean_category(node.get_text(' ', strip=True))
    heading = normalize_heading(text)
    if not text or heading in {
        'and the finalists are',
        'and the finalists are...',
        'and the finalists are ...',
      }:
      return None
    if 'finalist' in heading or 'nominee' in heading:
      return None
    if any(skip in heading for skip in ('congratulations', 'good luck')):
      return None
    return text

  def title_author_from_finalist_node(self, node):
    strong = node.find('strong')
    text = normalize_line(node.get_text(' ', strip=True))
    if strong is not None:
      author = self.clean_author(strong.get_text(' ', strip=True))
      remainder = text
      strong_text = normalize_line(strong.get_text(' ', strip=True))
      if strong_text and strong_text in remainder:
        remainder = remainder.split(strong_text, 1)[1]
      title = self.title_after_separator(remainder)
      if title and author:
        return title, author
    match = re.match(r'^(.+?)\s+[-\u2013\u2014]\s+(.+)$', text)
    if match is None:
      return None
    author = self.clean_author(match.group(1))
    title = self.clean_title(match.group(2))
    if not author or not title:
      return None
    return title, author

  def title_after_separator(self, value):
    value = normalize_line(value)
    value = re.sub(r'^\s*[-\u2013\u2014]\s*', '', value)
    return self.clean_title(value)

  def fetch_archived_rows(self, fetch_url, notes):
    rows = []
    try:
      cdx_html = fetch_url(RWAUS_RUBY_CDX_URL)
    except (ImportCancelledError,CamoufoxRequiredError):
      raise
    except Exception as err:
      notes.append(f'RWAus archived RUBY winner index could not be fetched: {err}')
      return rows
    snapshot_url = self.snapshot_url_from_cdx(cdx_html)
    if not snapshot_url:
      notes.append('RWAus archived RUBY winner index did not expose a usable snapshot.')
      return rows
    try:
      archive_html = fetch_url(snapshot_url)
    except (ImportCancelledError,CamoufoxRequiredError):
      raise
    except Exception as err:
      notes.append(f'RWAus archived RUBY winner page could not be fetched: {err}')
      return rows
    return self.parse_archived_pages(((snapshot_url, archive_html),))

  def snapshot_url_from_cdx(self, cdx_html):
    return self.snapshot_from_cdx(cdx_html).get('url','')

  def snapshot_from_cdx(self,cdx_html):
    try:
      data = json.loads(cdx_html or '[]')
    except Exception:
      return {}
    rows = data if isinstance(data, list) else []
    snapshots = []
    for row in rows[1:]:
      if not isinstance(row, list) or len(row) < 2:
        continue
      timestamp, original = row[0], row[1]
      if (isinstance(timestamp,str) and re.fullmatch(r'\d{14}',timestamp) and isinstance(original,str) and
          urlsplit(original).scheme in ('http','https') and urlsplit(original).hostname in ('romanceaustralia.com','www.romanceaustralia.com') and
          (len(row)<3 or str(row[2])=='200')):
        snapshots.append((timestamp,original,row[4] if len(row)>4 else ''))
    if not snapshots:
      return {}
    timestamp, original,digest = sorted(snapshots)[-1]
    return {'url':f'https://web.archive.org/web/{timestamp}id_/{original}','digest':digest}

  def parse_archived_pages(self, pages):
    rows = []
    for page_url, page_html in pages:
      rows.extend(self.parse_archived_winner_rows(page_html, page_url))
    return rows

  def parse_archived_winner_rows(self, html, source_url):
    soup = BeautifulSoup(html or '', 'html.parser')
    root=soup.select_one('.entry-content') or soup
    rows = []
    for table in root.find_all('table'):
      header_map = self.header_map(table)
      if self.has_required_columns(header_map):
        rows.extend(self.archived_table_rows(table, header_map, source_url))
      else:
        rows.extend(self.archived_placing_table_rows(table,source_url))
    if root is not soup:
      rows.extend(self.archived_roster_rows(root,source_url))
      return rows
    if rows:
      return rows
    return self.archived_text_rows(root, source_url)

  def archived_placing_table_rows(self,table,source_url):
    rows=[]
    year=category=None
    headings=table.find('tr')
    if headings is None or [normalize_heading(self.clean_cell_text(c)) for c in headings.find_all(['th','td'],recursive=False)]!=['year','placing','author','title']:
      return rows
    for tr in table.find_all('tr')[1:]:
      cells=tr.find_all(['th','td'],recursive=False)
      text=[self.clean_cell_text(c) for c in cells]
      if not text:continue
      if re.fullmatch(r'(?:19|20)\d{2}',text[0]):
        year=int(text[0]);category=None
        continue
      if text[0] and all(not value for value in text[1:]):
        category=self.clean_category(text[0])
        continue
      if len(text)!=4 or year is None or not category:continue
      placing=normalize_heading(text[1])
      if placing not in ('winner','finalist') or not text[2] or not text[3]:continue
      row=self.winner_row(year,self.clean_title(text[3]),self.clean_author(text[2]),category,source_url)
      row['result']=RESULT_WINNER if placing=='winner' else RESULT_SHORTLISTED
      rows.append(row)
    return rows

  def archived_roster_rows(self,root,source_url):
    """Read only isolated roster lines; accordion headings own the award year.

    Legacy 2015 paragraphs use br-separated lines, whereas later ballots use
    list items. The mixed 2015 panel switches to the separate ELLA award.
    """
    rows=[]
    year=category=None
    ella=False
    categories={normalize_heading(c):c for c in ('Long Romance','Short Romance','Romantic Elements','Novella','Short Sweet','Short Sexy','Overall RUBY')}
    for node in root.find_all(['div','p','li','h2','h3','h4']):
      if node.find_parent('table') is not None:continue
      if node.name=='div' and node.find(['div','p','li','ul','table']) is not None:continue
      text=normalize_line(node.get_text())
      heading=re.fullmatch(r'RUBY(?: and ELLA)? ((?:19|20)\d{2})',text,re.I)
      if heading:
        year=int(heading.group(1));category=None;ella=False
        continue
      if text.startswith('RWA congratulates') and 'finalists' in text.lower():
        match=re.search(r'\byear ((?:19|20)\d{2})\b',text,re.I)
        if match:year=int(match.group(1));category=None;ella=False
        continue
      if node.name not in ('p','li','div'):continue
      for line in self.roster_lines(node):
        text=normalize_line(line).strip(' :')
        if normalize_heading(text)=='ella':ella=True;category=None;continue
        label=categories.get(normalize_heading(text))
        if label:category=label;continue
        if ella or not category or year is None:continue
        winner=category=='Overall RUBY' or bool(re.search(r'\bWINNER\b',text,re.I))
        text=re.sub(r'\s*[-\u2013\u2014]*\s*(?:EQUAL\s+)?WINNER\s*$', '',text,flags=re.I).strip()
        # The credit marker is lowercase; title words such as "Tempted By The
        # Wrong Twin" precede the dash-delimited author in the 2018 roster.
        by=re.match(r'^(.+?)\s+by\s+(.+)$',text)
        parts=re.split(r'\s*[\u2013\u2014]\s*|\s+-\s+',text)
        if by:
          title=by.group(1)
          author=re.split(r'\s*[\u2013\u2014]\s*|\s+-\s+',by.group(2),maxsplit=1)[0]
          for known in rows:
            if known['award_year']==str(year) and normalize_heading(known['title'])==normalize_heading(title) and author.startswith(known['author']):
              author=known['author'];break
        elif len(parts)>=2:
          title,author=parts[:2]
        else:continue
        title=re.sub(r',\s*republished as .+$','',title,flags=re.I)
        title,author=self.clean_title(title),self.clean_author(author)
        if not title or not author:continue
        row=self.winner_row(year,title,author,category,source_url)
        row['result']=RESULT_WINNER if winner else RESULT_SHORTLISTED
        rows.append(row)
    return rows

  def roster_lines(self,node):
    fragment=BeautifulSoup(str(node),'html.parser')
    for br in fragment.find_all('br'):br.replace_with('\n')
    return fragment.get_text().splitlines()

  def header_map(self, table):
    aliases = {
      'year': 'year',
      'award year': 'year',
      'category': 'category',
      'section': 'category',
      'title': 'title',
      'book': 'title',
      'work': 'title',
      'author': 'author',
      'authors': 'author',
      'winner': 'title',
      'winning book': 'title',
    }
    for tr in table.find_all('tr'):
      mapped = {}
      for index, cell in enumerate(tr.find_all(['td', 'th'], recursive=False)):
        key = aliases.get(normalize_heading(self.clean_cell_text(cell)))
        if key is not None and key not in mapped:
          mapped[key] = index
      if self.has_required_columns(mapped):
        return mapped
    return {}

  def has_required_columns(self, header_map):
    return all(key in header_map for key in ('year', 'category', 'title', 'author'))

  def archived_table_rows(self, table, header_map, source_url):
    rows = []
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      if not cells or self.row_is_header(cells):
        continue
      year = self.year_from_text(self.cell_text(cells, header_map, 'year'))
      category = self.clean_category(self.cell_text(cells, header_map, 'category'))
      title = self.clean_title(self.cell_text(cells, header_map, 'title'))
      author = self.clean_author(self.cell_text(cells, header_map, 'author'))
      if year is None or not category or not title or not author:
        continue
      rows.append(self.winner_row(year, title, author, category, source_url))
    return rows

  def row_is_header(self, cells):
    headings = {normalize_heading(self.clean_cell_text(cell)) for cell in cells}
    return 'year' in headings and ('title' in headings or 'winner' in headings)

  def cell_text(self, cells, header_map, key):
    index = header_map.get(key)
    if index is None or index >= len(cells):
      return ''
    return self.clean_cell_text(cells[index])

  def archived_text_rows(self, soup, source_url):
    rows = []
    current_year = None
    current_category = None
    for node in soup.find_all(['h2', 'h3', 'h4', 'p', 'li']):
      text = normalize_line(node.get_text(' ', strip=True))
      if not text:
        continue
      year = self.year_from_text(text)
      if year is not None and len(text) <= 30:
        current_year = year
        current_category = None
        continue
      category = self.category_from_heading(node)
      if node.name in {'h2', 'h3', 'h4'} and category:
        current_category = category
        continue
      if current_year is None or current_category is None:
        continue
      parsed = self.title_author_from_winner_text(text)
      if parsed is None:
        continue
      title, author = parsed
      rows.append(self.winner_row(current_year, title, author, current_category, source_url))
    return rows

  def title_author_from_winner_text(self, value):
    value = re.sub(r'^\s*winner\s*:?\s*', '', normalize_line(value), flags=re.I)
    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', value, flags=re.I)
    if by_match is not None:
      title = self.clean_title(by_match.group(1))
      author = self.clean_author(by_match.group(2))
      return (title, author) if title and author else None
    dash_match = re.match(r'^(.+?)\s+[-\u2013\u2014]\s+(.+)$', value)
    if dash_match is None:
      return None
    title = self.clean_title(dash_match.group(1))
    author = self.clean_author(dash_match.group(2))
    return (title, author) if title and author else None

  def winner_row(self, year, title, author, category, source_url):
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': RESULT_WINNER,
      'source_url': source_url,
      'category': category,
      '_source_order': 0,
    }

  def clean_cell_text(self, cell):
    cell = BeautifulSoup(str(cell), 'html.parser')
    for node in cell.find_all(['sup', 'style', 'script']):
      node.decompose()
    text = cell.get_text(' ', strip=True).replace('\xa0', ' ')
    text = re.sub(r'\s*\[\s*\d+\s*\]\s*', ' ', text)
    return normalize_line(text)

  def clean_category(self, value):
    value = normalize_line(value).replace('\u2013', '-').replace('\u2014', '-')
    value = re.sub(r'\s+', ' ', value)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,:')

  def clean_title(self, value):
    value = strip_publication_notes(normalize_line(value))
    value = re.sub(r'\s*\(\s*previously[^)]*\)\s*$', '', value, flags=re.I).strip()
    return value.strip(' "\'\u2018\u2019\u201c\u201d,:')

  def clean_author(self, value):
    value = strip_publication_notes(normalize_line(value))
    return value.strip(' "\'\u2018\u2019\u201c\u201d,:')

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
      notes.append(
        'No RUBY rows were parsed; the current RWAus site does not expose a '
        'complete public result archive.')
      return
    years = {int(row['award_year']) for row in rows if row.get('award_year')}
    shortlist_years = sorted({
      int(row['award_year']) for row in rows
      if row.get('result') == RESULT_SHORTLISTED and 'web.archive.org/web/' not in row.get('source_url','')
    })
    winner_years = sorted({
      int(row['award_year']) for row in rows
      if row.get('result') == RESULT_WINNER
    })
    if shortlist_years:
      notes.append(
        'Official migrated RWAus finalist/nominee posts were parsed for: ' +
        ', '.join(str(year) for year in shortlist_years) + '.')
    if winner_years:
      notes.append(
        'Archived official RUBY winner rows were parsed for: ' +
        ', '.join(str(year) for year in winner_years) + '.')
    if years:
      notes.append(
        'Historical records may omit finalists. Migrated posts and archived '
        'RUBY results do not establish complete coverage through the current year.')


def parse_romance_writers_australia_ruby(
    html, base_url=RWAUS_RUBY_SEARCH_URL, name=RWAUS_RUBY_AWARD_NAME,
    fetch_url=None, archived_pages=None):
  return RomanceWritersAustraliaRubyParser().parse(
    html, base_url, name, fetch_url=fetch_url, archived_pages=archived_pages)
