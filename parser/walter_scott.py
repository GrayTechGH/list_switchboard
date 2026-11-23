#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Walter Scott Prize parser for the official PDF/history pages and Wikipedia.

Maintenance notes:
- The official archive is a two-column PDF. Calibre's bundled pdftotext bounds
  words spatially before year parsing; plain text and small offline fixtures
  retain the local extractor. Exact annual counts gate reuse of the dated PDF.
- V1 imports winners and shortlists only. Official longlists are deliberately
  ignored to match adjacent literary-award recipes.
"""

import re
import json
import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
  from calibre_plugins.list_switchboard.parser.pdf_text import extract_pdf_text # pyright: ignore[reportMissingImports]
  from calibre_plugins.list_switchboard.parser.incremental import ParsedUnitCache,project_source_rows,restore_source_rows
  from calibre_plugins.list_switchboard.errors import ImportCancelledError,CamoufoxRequiredError
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key
  from .pdf_text import extract_pdf_text
  from .incremental import ParsedUnitCache,project_source_rows,restore_source_rows
  from errors import ImportCancelledError,CamoufoxRequiredError


AWARD_NAME = 'Walter Scott Prize'
CATEGORY = 'Historical Fiction'
PDF_URL = (
  'https://www.walterscottprize.co.uk/wp-content/uploads/2025/08/'
  'PREVIOUS-WINNERS-OF-THE-WALTER-SCOTT-PRIZE-FOR-HISTORICAL-FICTION.pdf')
SHORTLIST_URL_2026 = 'https://www.walterscottprize.co.uk/the-2026-prize/the-2026-shortlist/'
WINNER_URL_2026 = 'https://www.walterscottprize.co.uk/alice-jolly-wins-2026-walter-scott-prize/'
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Walter_Scott_Prize'


HEADER_ALIASES = {
  'year': 'year',
  'author': 'author',
  'authors': 'author',
  'writer': 'author',
  'writers': 'author',
  'title': 'title',
  'book': 'title',
  'novel': 'title',
  'work': 'title',
  'result': 'result',
  'status': 'result',
  'stage': 'result',
}


class WalterScottParserMixin(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def clean_text(self, node):
    if node is None:
      return ''
    node = BeautifulSoup(str(node), 'html.parser')
    for removable in node.find_all(['script', 'style', 'sup']):
      removable.decompose()
    text = node.get_text(' ', strip=True).replace('\xa0', ' ')
    text = re.sub(r'\s*\[\s*\d+\s*\]\s*', ' ', text)
    return normalize_line(text)

  def clean_title(self, value):
    value = strip_publication_notes(normalize_line(value))
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def clean_author(self, value):
    value = strip_publication_notes(normalize_line(value))
    value = re.sub(r'^\s*(?:by|author|authors)\s*:\s*', '', value, flags=re.I)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True) if node is not None else None
    return urljoin(base_url, link['href']) if link is not None else ''

  def dedupe_rows(self, rows):
    deduped = []
    index_by_key = {}
    for row in rows:
      key = (
        row['award_year'],
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
      year_rows = sorted(
        by_year[year],
        key=lambda row: 0 if row.get('result') == RESULT_WINNER else 1)
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, CATEGORY)
        for row in year_rows
      ]
      entries.extend(assign_positions(
        award_rows, int(year), tied_winners_share_position=True))
    return entries


class WalterScottOfficialParser(WalterScottParserMixin):

  # Verified ballots in the configured August 2025 PDF. A replacement PDF
  # requires a renewed coverage review before its history can be reused.
  HISTORY_COUNTS = dict(zip(range(2010,2026), (8,5,6,6,6,7,6,7,6,6,6,5,4,7,6,6)))

  SUPPLEMENT_URLS = (
    (SHORTLIST_URL_2026, RESULT_SHORTLISTED),
    (WINNER_URL_2026, RESULT_WINNER),
  )

  def parse(
      self, pdf_or_text, base_url=PDF_URL, name=AWARD_NAME, fetch_url=None,
      current_pages=None, log=None, progress=None,cached_parsed=None,incremental_update=False):
    cache=self.update_cache(base_url,name,cached_parsed,incremental_update)
    history=self.reusable_history(base_url,name,cached_parsed,incremental_update)
    if history is None:
      history=list(self.parse_pdf_rows(pdf_or_text,base_url))
    rows=list(history)
    units={'history':(history,base_url,self.history_complete(history,base_url))}
    notes = []
    pages = list(current_pages or ())

    if fetch_url is not None and current_pages is None:
      total = len(self.SUPPLEMENT_URLS)
      for index, (url, result) in enumerate(self.SUPPLEMENT_URLS, 1):
        revision=[result,self.year_from_text(url)]
        old=cache.old_units.get(url) or {}
        previous=[]
        try:
          previous=restore_source_rows(cache.previous(url),old.get('metadata') or {})
        except (ValueError,TypeError):
          pass
        if (revision[1] and revision[1]<datetime.datetime.now().year and
            old.get('complete') is True and old.get('revision')==revision and previous):
          rows.extend(previous)
          units[url]=(previous,revision,True)
          continue
        try:
          if progress is not None:
            progress(index, total, f'Fetching {name} supplement page {index} of {total}')
          source_rows=self.parse_html_rows(fetch_url(url),url,result)
          if not source_rows:
            raise ValueError('Official announcement had no usable prize rows.')
          rows.extend(source_rows)
          units[url]=(source_rows,revision,True)
        except (ImportCancelledError,CamoufoxRequiredError):
          raise
        except Exception as err:
          rows.extend(previous)
          units[url]=(previous,revision,False)
          notes.append(f'{name} supplement page could not be fetched: {url}: {err}')
          if log is not None:
            log(f'{name} supplement page failed: {url}: {err}')

    for page in pages:
      if len(page) == 2:
        url, html = page
        result = RESULT_SHORTLISTED
      else:
        url, result, html = page
      source_rows=self.parse_html_rows(html,url,result)
      rows.extend(source_rows)
      units[url]=(source_rows,[result,self.year_from_text(url)],bool(source_rows))

    entries = self.entries_from_rows(self.dedupe_rows(rows))
    entries=sorted(entries,key=lambda item:position_sort_key(item.get('position','')))
    for url,(source_rows,revision,complete) in units.items():
      projected,metadata=project_source_rows(source_rows,entries,
        lambda row:(str(row['award_year']),normalize_heading(row['title'])))
      cache.put(url,projected,revision=revision,complete=complete,metadata=metadata)
    parsed=self.parsed_result(
      name,
      base_url,
      entries,
      notes=notes)
    parsed['incremental_state']=cache.state(entries)
    parsed['incremental_state']['discovery']={'refresh_units':[url for url in units if url!='history']}
    return parsed

  def update_cache(self,base_url,name,cached_parsed,incremental_update):
    return ParsedUnitCache('walter-scott-parsed-history-v1',json.dumps([
      base_url,name,self.AWARD_NAME,CATEGORY,self.HISTORY_COUNTS]),cached_parsed,incremental_update)

  def reusable_history(self,base_url,name=AWARD_NAME,cached_parsed=None,incremental_update=False):
    cache=self.update_cache(base_url,name,cached_parsed,incremental_update)
    old=cache.old_units.get('history') or {}
    if old.get('complete') is not True or old.get('revision')!=base_url:
      return None
    try:
      rows=restore_source_rows(cache.previous('history'),old.get('metadata') or {})
      if self.history_complete(rows,base_url) and all(int(r['award_year'])<datetime.datetime.now().year for r in rows):
        return rows
    except (ValueError,TypeError,KeyError):
      pass
    return None

  def history_complete(self,rows,base_url):
    version=re.search(r'/uploads/(20\d{2})/\d{2}/',base_url)
    if not version or not rows:
      return False
    years={str(year) for year in range(2010,int(version.group(1))+1)}
    return (set(map(str,self.HISTORY_COUNTS))==years and
      set(str(r.get('award_year')) for r in rows)==years and
      {str(r.get('award_year')) for r in rows if r.get('result')==RESULT_WINNER}==years and
      all(sum(str(r.get('award_year'))==str(year) for r in rows)==count
        for year,count in self.HISTORY_COUNTS.items()) and
      all(r.get('title') and r.get('author') and '\ufffd' not in r['title']+r['author'] for r in rows))

  def parse_pdf_rows(self, pdf_or_text, base_url=PDF_URL):
    text = self.extract_pdf_text(pdf_or_text)
    return self.rows_from_text(text, base_url)

  def extract_pdf_text(self, value):
    if (isinstance(value,bytes) and value.startswith(b'%PDF-')) or str(value).startswith('%PDF-'):
      try:
        from calibre.ebooks.pdf.pdftohtml import PDFTOTEXT,creationflags
      except ImportError:
        pass
      else:
        import subprocess
        import tempfile
        from pathlib import Path
        data=value if isinstance(value,bytes) else value.encode('latin-1')
        with tempfile.TemporaryDirectory(prefix='list-switchboard-walter-pdf-') as folder:
          pdf=Path(folder)/'history.pdf'
          pdf.write_bytes(data)
          result=subprocess.run([PDFTOTEXT,'-bbox-layout','-enc','UTF-8',str(pdf),'-'],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,
            creationflags=creationflags,timeout=45)
          return self.pdf_columns(result.stdout)
    return extract_pdf_text(value)

  def pdf_columns(self,xml):
    """Read the history's two year columns without interleaving their ballots."""
    from lxml import etree
    root=etree.fromstring(xml,parser=etree.XMLParser(resolve_entities=False,no_network=True))
    result=[]
    for page in root.xpath('//*[local-name()="page"]'):
      anchors=[float(word.get('xMin')) for word in page.xpath('.//*[local-name()="word"]')
        if re.fullmatch(r'20\d{2}',word.text or '')]
      if not anchors:
        continue
      right_anchors=[x for x in anchors if x>float(page.get('width'))/2]
      boundary=min(right_anchors)-2 if right_anchors else float(page.get('width'))+1
      lines=page.xpath('.//*[local-name()="line"]')
      for right in (False,True):
        for line in sorted(lines,key=lambda n:float(n.get('yMin'))):
          whole_line=' '.join(word.text or '' for word in line)
          if 'managed by The Abbotsford Trust' in whole_line or 'PREVIOUS WINNERS' in whole_line:
            continue
          words=[word.text or '' for word in line.xpath('./*[local-name()="word"]')
            if (float(word.get('xMin'))>=boundary)==right]
          text=normalize_line(' '.join(words))
          if not text or 'managed by The Abbotsford Trust' in text or 'PREVIOUS WINNERS' in text:
            continue
          result.append(text)
    text='\n'.join(result)
    # The dated PDF joins Carey's wrapped surname to the next book's title.
    return text.replace('A Long Way From Home by Peter\nCarey After The Party',
      'A Long Way From Home by Peter Carey\nAfter The Party')

  def rows_from_text(self, text, base_url):
    rows = []
    current_year = None
    current_result = None
    pending = ''

    for line in self.source_lines(text):
      line_year = self.line_year(line)
      if line_year is not None:
        pending = self.flush_pending(rows, pending, current_year, current_result, base_url)
        current_year = line_year
        current_result = None
        remainder = self.line_without_year(line, line_year)
        if remainder:
          result, remainder = self.result_prefix(remainder, current_result)
          current_result = result or current_result
          pending = self.consume_entry_line(rows, pending, remainder, current_year, current_result, base_url)
        continue

      result, remainder = self.result_prefix(line, current_result)
      if result is not None:
        pending = self.flush_pending(rows, pending, current_year, current_result, base_url)
        current_result = result
        if remainder:
          pending = self.consume_entry_line(rows, pending, remainder, current_year, current_result, base_url)
        continue

      if current_year is not None and current_result in {RESULT_WINNER, RESULT_SHORTLISTED}:
        pending = self.consume_entry_line(rows, pending, line, current_year, current_result, base_url)

    self.flush_pending(rows, pending, current_year, current_result, base_url)
    return rows

  def source_lines(self, text):
    text = (text or '').replace('\r', '\n')
    text = re.sub(r'\b(20[1-2]\d)\s+(Winner|Shortlist|Shortlisted)\b', r'\n\1\n\2', text, flags=re.I)
    text = re.sub(r'\b(Winner|Shortlist|Shortlisted)\s*:?(\s+)', r'\n\1 ', text, flags=re.I)
    text = re.sub(r'\b(Longlist|Longlisted)\s*:?(\s+)', r'\n\1 ', text, flags=re.I)
    lines = []
    for raw_line in re.split(r'[\n;]+', text):
      line = normalize_line(raw_line)
      if not line or self.is_noise_line(line):
        continue
      lines.append(line)
    return lines

  def is_noise_line(self, line):
    heading = normalize_heading(line)
    if not heading:
      return True
    if 'previous winners of the walter scott prize' in heading:
      return True
    if heading in {
        'winner',
        'winners',
        'shortlist',
        'shortlisted',
        'the shortlist',
        'longlist',
        'longlisted',
        'the longlist',
    }:
      return False
    return heading in {
      'walter scott prize',
      'walter scott prize for historical fiction',
      'historical fiction',
      'previous winners and shortlists',
    }

  def line_year(self, line):
    match = re.match(r'^\s*(20[1-2]\d)\b', line)
    if match is None:
      return None
    return int(match.group(1))

  def line_without_year(self, line, year):
    return normalize_line(re.sub(r'^\s*%s\b\s*' % year, '', line))

  def result_prefix(self, line, current_result=None):
    heading = normalize_heading(line)
    if heading in {'winner', 'winners'}:
      return RESULT_WINNER, ''
    if heading in {'shortlist', 'shortlisted', 'the shortlist'}:
      return RESULT_SHORTLISTED, ''
    if heading in {'longlist', 'longlisted', 'the longlist'}:
      return 'longlisted', ''
    match = re.match(
      r'^\s*(winner|winners|shortlist|shortlisted|the shortlist|longlist|longlisted|the longlist)\s*:?\s*(.+)$',
      line,
      re.I)
    if match is None:
      return None, line
    if normalize_heading(match.group(1)) in {'longlist', 'longlisted', 'the longlist'}:
      return 'longlisted', normalize_line(match.group(2))
    result = (
      RESULT_WINNER
      if normalize_heading(match.group(1)) in {'winner', 'winners'}
      else RESULT_SHORTLISTED)
    return result, normalize_line(match.group(2))

  def consume_entry_line(self, rows, pending, line, year, result, source_url):
    pending = normalize_line(f'{pending} {line}' if pending else line)
    parsed = self.row_from_text(pending, year, result, source_url)
    if parsed is None:
      return pending
    rows.append(parsed)
    return ''

  def flush_pending(self, rows, pending, year, result, source_url):
    if pending and year is not None and result in {RESULT_WINNER, RESULT_SHORTLISTED}:
      parsed = self.row_from_text(pending, year, result, source_url)
      if parsed is not None:
        rows.append(parsed)
    return ''

  def row_from_text(self, text, year, result, source_url):
    if year is None or result not in {RESULT_WINNER, RESULT_SHORTLISTED}:
      return None
    parsed = self.title_author_from_text(text)
    if parsed is None:
      return None
    title, author = parsed
    if not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': source_url,
      'category': CATEGORY,
    }

  def title_author_from_text(self, value):
    value = normalize_line(value)
    value = re.sub(r'^\s*[*\-\u2022]\s*', '', value)
    value = re.sub(r'\s+(winner|shortlisted)\s*$', '', value, flags=re.I)
    for title,author in (
        ('The Narrow Land','Christine Dwyer Hickey'),
        ('Miss Boston and Miss Hargreaves','Rachel Malik'),
        ('On Canaan\u2019s Side','Sebastian Barry'),
        ('The Sisters Brothers','Patrick de Witt')):
      if value==title+' '+author:
        return title,author
    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', value, re.I)
    if by_match is not None:
      return (
        self.clean_title(by_match.group(1)),
        self.clean_author(by_match.group(2)))
    dash_match = re.match(r'^(.+?)\s+[\u2013\u2014-]\s+(.+)$', value)
    if dash_match is not None:
      return (
        self.clean_title(dash_match.group(1)),
        self.clean_author(dash_match.group(2)))
    compact = strip_publication_notes(value)
    parts = re.split(r'\s{2,}', compact)
    if len(parts) >= 2:
      return self.clean_title(parts[0]), self.clean_author(parts[1])
    if ',' in compact:
      title, author = compact.rsplit(',', 1)
      return self.clean_title(title), self.clean_author(author)
    return None

  def parse_html_rows(self, html, base_url, result):
    year = self.year_from_text(base_url) or self.year_from_text(html)
    if year is None:
      return []
    soup = BeautifulSoup(html or '', 'html.parser')
    content=soup.select_one('#content')
    if content and content.find('h1'):
      rows=[]
      heading=self.clean_text(content.find('h1'))
      if result==RESULT_WINNER:
        author=re.split(r'\s+(?:wins|has won)\b',heading,maxsplit=1,flags=re.I)[0]
        for p in content.find_all('p',recursive=False):
          if re.search(r'\bhas won\b',self.clean_text(p),re.I):
            title=p.find(['em','i'])
            if title and author and author!=heading:
              rows.append({'award_year':str(year),'title':self.clean_title(self.clean_text(title)),
                'author':self.clean_author(author),'result':result,'source_url':base_url,'category':CATEGORY})
            break
      else:
        for p in content.find_all('p',recursive=False):
          if not re.search(r'\bshortlist\s+comprised\b',self.clean_text(p),re.I):
            continue
          ballot=p.find_next_sibling(['p','ul'])
          if ballot:
            for line in ballot.get_text('\n',strip=True).splitlines():
              if not re.fullmatch(r'.+?\s+by\s+[^.!?]+',line.strip(),re.I):
                continue
              parsed=self.title_author_from_text(line)
              if parsed:
                title,author=parsed
                rows.append({'award_year':str(year),'title':title,'author':author,
                  'result':result,'source_url':base_url,'category':CATEGORY})
          break
      return rows
    rows = []
    for line in self.html_candidate_lines(soup):
      parsed = self.title_author_from_text(line)
      if parsed is None:
        continue
      title, author = parsed
      if not title or not author:
        continue
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': self.line_source_url(soup, line, base_url),
        'category': CATEGORY,
      })
    return rows

  def html_candidate_lines(self, soup):
    candidates = []
    for node in soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'li', 'strong']):
      text = self.clean_text(node)
      if self.title_author_from_text(text) is not None:
        candidates.append(text)
    return candidates

  def line_source_url(self, soup, line, base_url):
    normalized = normalize_heading(line)
    for node in soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'li', 'strong']):
      if normalize_heading(self.clean_text(node)) == normalized:
        return self.first_link_url(node, base_url) or base_url
    return base_url


class WalterScottWikipediaParser(WalterScottParserMixin):

  def parse(self, html, base_url=WIKIPEDIA_URL, name=AWARD_NAME):
    rows = self.dedupe_rows(self.parse_rows(html, base_url))
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for table in soup.find_all('table'):
      header_map = self.header_map(table)
      if not {'year', 'title', 'author'}.issubset(set(header_map)):
        continue
      rows.extend(self.table_rows(table, header_map, base_url))
    return rows

  def header_map(self, table):
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      mapped = {}
      for index, cell in enumerate(cells):
        key = HEADER_ALIASES.get(normalize_heading(self.clean_text(cell)))
        if key is not None and key not in mapped:
          mapped[key] = index
      if {'year', 'title', 'author'}.issubset(set(mapped)):
        return mapped
    return {}

  def table_rows(self, table, header_map, base_url):
    rows = []
    current_year = None
    current_result_by_year = {}
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      if not cells or self.is_header_row(cells, header_map):
        continue
      missing_year_cell = self.row_omits_year(cells, header_map, current_year)
      year_cell = self.cell_for_key(cells, header_map, 'year', missing_year_cell)
      year = current_year
      if year_cell is not None and not missing_year_cell:
        year = self.year_from_text(self.clean_text(year_cell)) or current_year
      if year is None:
        continue
      current_year = year

      result_cell = self.cell_for_key(cells, header_map, 'result', missing_year_cell)
      result = self.result_from_cell(result_cell)
      if result is None:
        result = (
          RESULT_SHORTLISTED
          if current_result_by_year.get(year) == RESULT_SHORTLISTED
          else None)
      if result not in {RESULT_WINNER, RESULT_SHORTLISTED}:
        continue

      title_cell = self.cell_for_key(cells, header_map, 'title', missing_year_cell)
      author_cell = self.cell_for_key(cells, header_map, 'author', missing_year_cell)
      title = self.clean_title(self.clean_text(title_cell))
      author = self.clean_author(self.clean_text(author_cell))
      if not title or not author:
        continue
      current_result_by_year[year] = result
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': self.first_link_url(title_cell, base_url) or base_url,
        'category': CATEGORY,
      })
    return rows

  def is_header_row(self, cells, header_map):
    for key, index in header_map.items():
      if index >= len(cells):
        return False
      if HEADER_ALIASES.get(normalize_heading(self.clean_text(cells[index]))) != key:
        return False
    return True

  def row_omits_year(self, cells, header_map, current_year):
    if current_year is None or header_map.get('year') != 0:
      return False
    if len(cells) > max(header_map.values()):
      return False
    return self.year_from_text(self.clean_text(cells[0])) is None

  def cell_for_key(self, cells, header_map, key, missing_year_cell):
    index = header_map.get(key)
    if index is None:
      return None
    if missing_year_cell and index > header_map['year']:
      index -= 1
    return cells[index] if 0 <= index < len(cells) else None

  def result_from_cell(self, cell):
    text = normalize_heading(self.clean_text(cell))
    if not text:
      return None
    if text.startswith('winner') or text.startswith('won'):
      return RESULT_WINNER
    if text.startswith('shortlist') or text.startswith('finalist'):
      return RESULT_SHORTLISTED
    if text.startswith('longlist'):
      return 'longlisted'
    return None


def parse_walter_scott_official(
    pdf_or_text, base_url=PDF_URL, name=AWARD_NAME, fetch_url=None,
    current_pages=None, log=None, progress=None):
  return WalterScottOfficialParser().parse(
    pdf_or_text,
    base_url,
    name,
    fetch_url=fetch_url,
    current_pages=current_pages,
    log=log,
    progress=progress)


def parse_walter_scott_wikipedia(html, base_url=WIKIPEDIA_URL, name=AWARD_NAME):
  return WalterScottWikipediaParser().parse(html, base_url, name)
