#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Carnegie Medal for Writing parser for official Carnegies pages.

Maintenance notes:
- Official public shortlists are available from 2010 onward. V1 imports
  pre-2010 history as winner-only.
- Official nominated-title and longlist pages are public, but deliberately
  excluded here. The V1 public non-winner stage is the shortlist.
- The official site mixes Writing, Illustration, and Shadowers' Choice content
  on current pages; section boundaries below keep this recipe scoped to Writing.
"""

from datetime import date
from copy import deepcopy
import json
import re

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


AWARD_NAME = 'Carnegie Medal for Writing'
CATEGORY = 'Writing'
WINNERS_URL = 'https://carnegies.co.uk/archive/writing-winners/'
SHORTLIST_ARCHIVE_2010_2015_URL = (
  'https://carnegies.co.uk/archive/2010-2015-shortlist-resources/')
SHORTLIST_ARCHIVE_URL_TEMPLATE = 'https://carnegies.co.uk/archive/{year}-shortlist-resources/'
SHORTLIST_CURRENT_URL_TEMPLATE = 'https://carnegies.co.uk/writing-shortlist-{year}-2/'
SHORTLIST_NEWS_URL_TEMPLATE = 'https://carnegies.co.uk/{year}-shortlists-announced/'
WINNER_NEWS_URL_TEMPLATE = 'https://carnegies.co.uk/{year}-winners-announced/'
WINNERS_CURRENT_URL_TEMPLATE = 'https://carnegies.co.uk/the-{year}-winners/'

SEMANTIC_TAGS = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'td')
YEAR_RE = re.compile(r'\b((?:19|20)\d{2})\b')
WITHHELD_RE = re.compile(r'\b(?:withheld|no\s+award|not\s+awarded)\b', re.I)
PUBLISHER_RE = re.compile(
  r'\s*(?:,?\s+(?:and\s+)?published by|\.?\s+(?:and\s+)?published by)\s+.+$',
  re.I)
ISBN_RE = re.compile(r'\s*(?:ISBN|978[-0-9 ]+|resource pack|available here).+$', re.I)


def shortlist_archive_url(year):
  return SHORTLIST_ARCHIVE_URL_TEMPLATE.format(year=int(year))


def current_shortlist_url(year):
  return SHORTLIST_CURRENT_URL_TEMPLATE.format(year=int(year))


def shortlist_news_url(year):
  return SHORTLIST_NEWS_URL_TEMPLATE.format(year=int(year))


def winner_news_url(year):
  return WINNER_NEWS_URL_TEMPLATE.format(year=int(year))


def current_winners_url(year):
  return WINNERS_CURRENT_URL_TEMPLATE.format(year=int(year))


class CarnegieMedalParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def parse(
      self, html, base_url=WINNERS_URL, name=AWARD_NAME, fetch_url=None,
      current_year=None, shortlist_pages=(), winner_pages=(), supplement_pages=(),
      log=None, progress=None,cached_parsed=None,incremental_update=False):
    if fetch_url is not None and not (shortlist_pages or winner_pages or supplement_pages):
      return self.parse_live_sources(html,base_url,name,fetch_url,int(current_year or date.today().year),
        cached_parsed,incremental_update,log,progress)
    rows, notes = self.winner_archive_rows(html, base_url)
    current_year = int(current_year or date.today().year)

    for page_url, page_html in shortlist_pages or ():
      rows.extend(self.shortlist_page_rows(page_html, page_url))
    for page_url, page_html in winner_pages or ():
      rows.extend(self.winner_page_rows(page_html, page_url))
    for page_url, page_html in supplement_pages or ():
      rows.extend(self.supplement_page_rows(page_html, page_url))

    if fetch_url is not None:
      targets = self.fetch_targets(current_year)
      total = max(1, len(targets))
      for index, (page_url, parser_method) in enumerate(targets, 1):
        try:
          if progress is not None:
            progress(index, total, f'Fetching Carnegie Medal page {index} of {total}')
          rows.extend(parser_method(fetch_url(page_url), page_url))
        except (ImportCancelledError,CamoufoxRequiredError):
          raise
        except Exception as err:
          notes.append(f'Carnegie Medal page could not be fetched: {page_url}: {err}')
          if log is not None:
            log(f'Carnegie Medal page failed: {page_url}: {err}')

    rows = self.dedupe_rows(rows)
    entries = self.entries_from_rows(rows)
    if not entries:
      raise ValueError('No Carnegie Medal for Writing entries found on official Carnegies pages.')
    notes.append(
      'Official Carnegie Medal for Writing shortlists are imported from 2010 onward; '
      'pre-2010 history is winner-only in this recipe.')
    notes.append('Official nominated-title and longlist pages are public but excluded in V1.')
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def parse_live_sources(self,html,base_url,name,fetch_url,current_year,cached_parsed,incremental_update,log,progress):
    cache=ParsedUnitCache('carnegie-writing-shortlists-v1',json.dumps([
      base_url,name,type(self).__name__]),cached_parsed,incremental_update)
    notes=[]
    def previous(key):
      try:return restore_source_rows(cache.previous(key),(cache.old_units.get(key) or {}).get('metadata') or {})
      except (ValueError,TypeError):return []
    archive,source_notes=self.winner_archive_rows(html,base_url)
    notes.extend(source_notes)
    archive_complete=bool(archive)
    if not archive_complete:
      archive=previous('archive')
      notes.append('Official Carnegie Writing archive did not expose usable winner rows; retained cached history.')
    winners={str(r['award_year']):normalize_heading(r['title']) for r in archive if r['result']==RESULT_WINNER}
    units={'archive':(archive,base_url,archive_complete)}
    targets=[('2010-2015',SHORTLIST_ARCHIVE_2010_2015_URL)]+[(str(y),shortlist_archive_url(y)) for y in range(2016,current_year+1)]
    rows=list(archive)
    for index,(key,url) in enumerate(targets,1):
      old=cache.old_units.get(key) or {}
      prior=previous(key)
      years={str(r['award_year']) for r in prior}
      closed=(archive_complete and prior and years and max(map(int,years))<current_year and
        all(year in winners and any(str(r['award_year'])==year and normalize_heading(r['title'])==winners[year] for r in prior) for year in years))
      if old.get('complete') is True and old.get('revision')==url and closed:
        source_rows,complete=prior,True
      else:
        source_rows,complete=prior,False
        try:
          if progress is not None:progress(index,len(targets),f'Fetching Carnegie Writing shortlist {key}')
          found=self.shortlist_page_rows(fetch_url(url),url)
          expected={str(y) for y in range(2010,2016)} if key=='2010-2015' else {key}
          actual={str(r['award_year']) for r in found}
          if not found or not actual.issubset(expected):
            raise ValueError('Official Carnegie shortlist did not expose the requested award years.')
          if actual!=expected:
            if not prior:source_rows=found
            raise ValueError('Official Carnegie shortlist did not expose all requested award years.')
          source_rows,complete=found,True
        except (ImportCancelledError,CamoufoxRequiredError):
          raise
        except Exception as err:
          notes.append(f'Carnegie Medal page could not be fetched: {url}: {err}')
          if log is not None:log(notes[-1])
      units[key]=(source_rows,url,complete)
      rows.extend(source_rows)
    current=units.get(str(current_year),([],None,False))
    current_winner=winners.get(str(current_year))
    if not (current[2] and current_winner and any(normalize_heading(r['title'])==current_winner for r in current[0])):
      supplement=[]
      fallback_targets=self.fetch_targets(current_year)[-4:]
      for url,reader in fallback_targets:
        try:
          supplement.extend(reader(fetch_url(url),url))
        except (ImportCancelledError,CamoufoxRequiredError):
          raise
        except Exception as err:
          notes.append(f'Carnegie Medal page could not be fetched: {url}: {err}')
      rows.extend(supplement)
      units['current-supplements']=(supplement,[u for u,_reader in fallback_targets],bool(supplement))
    entries=sorted(self.entries_from_rows(self.dedupe_rows(rows)),key=lambda item:position_sort_key(item.get('position','')))
    if not entries:raise ValueError('No Carnegie Medal for Writing entries found on official Carnegies pages.')
    for key,(source_rows,revision,complete) in units.items():
      projected,metadata=project_source_rows(source_rows,entries,
        lambda row:(str(row['award_year']),normalize_heading(row['title'])))
      cache.put(key,projected,revision=revision,complete=complete,metadata=metadata)
    notes.extend(['Official Carnegie Medal for Writing shortlists are imported from 2010 onward; pre-2010 history is winner-only in this recipe.',
      'Official nominated-title and longlist pages are public but excluded in V1.'])
    parsed=self.parsed_result(name,base_url,entries,notes=notes)
    parsed['incremental_state']=cache.state(entries)
    parsed['incremental_state']['discovery']={'refresh_units':[str(current_year)]}
    return parsed

  def fetch_targets(self, current_year):
    targets = [(SHORTLIST_ARCHIVE_2010_2015_URL, self.shortlist_page_rows)]
    for year in range(2016, current_year + 1):
      targets.append((shortlist_archive_url(year), self.shortlist_page_rows))
    targets.extend((
      (current_shortlist_url(current_year), self.shortlist_page_rows),
      (shortlist_news_url(current_year), self.shortlist_page_rows),
      (winner_news_url(current_year), self.winner_page_rows),
      (current_winners_url(current_year), self.winner_page_rows),
    ))
    return targets

  def winner_archive_rows(self, html, base_url=WINNERS_URL):
    soup=BeautifulSoup(html or '','html.parser')
    structured=[]
    structured_notes=[]
    for paragraph in soup.find_all('p'):
      paragraph_text=normalize_line(paragraph.get_text(' ',strip=True))
      if len(paragraph_text)<200 and WITHHELD_RE.search(paragraph_text):
        structured_notes.extend(f'Carnegie Medal for Writing {year} was withheld on the official archive.' for year in YEAR_RE.findall(paragraph_text))
      if re.match(r'^(?:19|20)\d{2}\b',paragraph.get_text(' ',strip=True)) is None:
        continue
      fragment=soup.new_tag('div')
      parts=[]
      for child in paragraph.children:
        if getattr(child,'name',None)=='br':
          parts.append(fragment);fragment=soup.new_tag('div')
        else:fragment.append(deepcopy(child))
      parts.append(fragment)
      for part in parts:
        text=normalize_line(part.get_text(' ',strip=True))
        match=re.match(r'^((?:19|20)\d{2})\b\s*(.+)$',text)
        if match is None:continue
        year=int(match.group(1))
        if WITHHELD_RE.search(text):
          structured_notes.append(f'Carnegie Medal for Writing {year} was withheld on the official archive.')
          continue
        titles=part.find_all('em')
        if not titles:continue
        before=[]
        for node in part.descendants:
          if node is titles[0]:break
          if not getattr(node,'name',None):before.append(str(node))
        author=re.sub(r'^(?:19|20)\d{2}\s+','',normalize_line(''.join(before))).strip(' ,')
        title=' '.join(t.get_text(' ',strip=True).strip(' ,') for t in titles)
        row=self.build_row(year,title,author,RESULT_WINNER,base_url)
        if row is not None:structured.append(row)
    if structured:return structured,structured_notes
    rows = []
    notes = []
    current_year = None
    pending_title = None
    for line in self.text_lines(html):
      if self.is_source_note(line):
        continue
      year_match = YEAR_RE.search(line)
      if year_match is not None:
        year = int(year_match.group(1))
        if WITHHELD_RE.search(line):
          notes.append(f'Carnegie Medal for Writing {year} was withheld on the official archive.')
          current_year = None
          pending_title = None
          continue
        remainder = normalize_line(line[:year_match.start()] + ' ' + line[year_match.end():])
        current_year = year
        pending_title = None
        if remainder and not self.is_archive_heading(remainder):
          row = self.row_from_entry_text(year, remainder, RESULT_WINNER, base_url)
          if row is not None:
            rows.append(row)
          else:
            pending_title = self.clean_title(remainder)
        continue

      if current_year is None or self.is_archive_heading(line):
        continue
      row = self.row_from_entry_text(current_year, line, RESULT_WINNER, base_url)
      if row is not None:
        rows.append(row)
        pending_title = None
      elif pending_title:
        author = self.clean_author(line)
        if author and not self.is_archive_heading(author):
          rows.append(self.build_row(current_year, pending_title, author, RESULT_WINNER, base_url))
          pending_title = None
      else:
        pending_title = self.clean_title(line)
    return rows, notes

  def shortlist_page_rows(self, html, base_url):
    if self.is_excluded_public_stage_url(base_url):
      return []
    year = self.year_from_url_or_text(base_url, html)
    if year is None or year < 2010:
      return []
    soup=BeautifulSoup(html or '','html.parser')
    heading=soup.find('h1')
    if heading is not None and self.is_writing_shortlist_start(normalize_heading(heading.get_text(' ',strip=True))):
      heading_year=YEAR_RE.search(heading.get_text(' ',strip=True))
      if heading_year and int(heading_year.group())!=year:return []
      cards=[]
      for link in soup.select('p > a[href*="/books/"]'):
        title=link.find('strong');credit=link.find('span')
        if title is not None and credit is not None:
          row=self.build_row(year,title.get_text(' ',strip=True),next(credit.stripped_strings,''),RESULT_SHORTLISTED,base_url)
          if row is not None:cards.append(row)
      if cards:return self.dedupe_rows(cards)
    lines = self.shortlist_section_lines(html, base_url)
    rows = []
    for line in lines:
      if self.is_shortlist_heading(line) or self.is_non_entry_line(line):
        continue
      row_year = year
      year_match = re.match(r'^((?:19|20)\d{2})\s+',line) if '2010-2015' in base_url else None
      if year_match is not None:
        row_year = int(year_match.group(1))
        line = normalize_line(line[:year_match.start()] + ' ' + line[year_match.end():])
      row = self.row_from_entry_text(row_year, line, RESULT_SHORTLISTED, base_url)
      if row is not None:
        rows.append(row)
    return rows

  def winner_page_rows(self, html, base_url):
    if self.is_excluded_public_stage_url(base_url):
      return []
    year = self.year_from_url_or_text(base_url, html)
    if year is None:
      return []
    soup=BeautifulSoup(html or '','html.parser')
    if soup.find('h1') is not None:
      winner_author=None
      for paragraph in soup.find_all('p'):
        match=re.match(r'^Carnegie Medal for Writing winner,\s*(.+?),\s*said',paragraph.get_text(' ',strip=True),re.I)
        if match:winner_author=normalize_heading(match.group(1));break
      structured=[]
      for paragraph in soup.find_all('p'):
        text=normalize_line(paragraph.get_text(' ',strip=True))
        if re.match(r'^[A-Z][^,.]{1,70}\s+(?:has\s+)?won\s+(?:both\s+)?the Carnegie Medal for Writing\b',text):
          row=self.winner_sentence_row(year,text,base_url)
          if row is not None:structured.append(row)
      for node in soup.find_all(['h2','h3','h4','p']):
        if node.name!='p':continue
        title=node.find('em')
        if title is None:continue
        text=normalize_line(node.get_text())
        marked=normalize_line(title.get_text())
        prefix=text.split(marked,1)[0] if marked in text else text
        credit=text.split(marked,1)[-1] if marked in text else ''
        author=re.match(r'^\s*by\s+(.+)$',credit,re.I)
        if not author or normalize_heading(prefix) not in ('','congratulations to'):continue
        author=self.clean_author(author.group(1).rstrip('!'))
        boundary=node.find_previous(['h2','h3','h4'])
        writing_section=boundary is not None and 'medal for writing' in normalize_heading(boundary.get_text(' ',strip=True)) and 'illustration' not in normalize_heading(boundary.get_text(' ',strip=True))
        if (winner_author and normalize_heading(author)==winner_author) or writing_section:
          row=self.build_row(year,marked,author,RESULT_WINNER,base_url)
          if row is not None:structured.append(row)
      return self.dedupe_rows(structured)
    rows = []
    for line in self.writing_winner_section_lines(html):
      if self.is_non_entry_line(line):
        continue
      row = self.row_from_entry_text(year, line, RESULT_WINNER, base_url)
      if row is not None:
        rows.append(row)
        continue
      row = self.winner_sentence_row(year, line, base_url)
      if row is not None:
        rows.append(row)
    return rows

  def supplement_page_rows(self, html, base_url):
    if self.is_excluded_public_stage_url(base_url):
      return []
    key = normalize_heading(base_url)
    if 'winner' in key:
      return self.winner_page_rows(html, base_url)
    return self.shortlist_page_rows(html, base_url)

  def shortlist_section_lines(self, html, base_url):
    lines = self.text_lines(html)
    if '2010-2015' in (base_url or ''):
      return self.aggregate_shortlist_lines(lines)
    section = []
    in_writing = False
    for line in lines:
      key = normalize_heading(line)
      if self.is_writing_shortlist_start(key):
        in_writing = True
        continue
      if in_writing and self.is_next_non_writing_section(key):
        break
      if in_writing:
        section.append(line)
    return section or lines

  def aggregate_shortlist_lines(self, lines):
    section = []
    current_year = None
    in_writing = False
    for line in lines:
      key = normalize_heading(line)
      year_match = YEAR_RE.search(line)
      if year_match is not None and self.is_writing_shortlist_start(key):
        current_year=int(year_match.group(1))
        in_writing=True
        continue
      if year_match is not None and key == year_match.group(1):
        current_year = int(year_match.group(1))
        in_writing = False
        continue
      if current_year is None:
        continue
      if self.is_writing_shortlist_start(key):
        in_writing = True
        continue
      if in_writing and self.is_next_non_writing_section(key):
        in_writing = False
        continue
      if in_writing:
        section.append(f'{current_year} {line}')
    return section

  def writing_winner_section_lines(self, html):
    lines = self.text_lines(html)
    section = []
    in_writing = False
    for line in lines:
      key = normalize_heading(line)
      if 'medal for writing' in key and 'illustration' not in key:
        in_writing = True
      elif in_writing and self.is_next_non_writing_section(key):
        break
      if in_writing:
        section.append(line)
    return section or [line for line in lines if 'illustration' not in normalize_heading(line)]

  def row_from_entry_text(self, year, text, result, source_url):
    text = self.clean_entry_text(text)
    if not text:
      return None
    text = re.sub(r'^\s*(?:winner|shortlisted?|the shortlist(?:ed)? books?|writing)\s*:?\s*', '', text, flags=re.I)
    quoted = re.match(r'^[“"]([^”"]+)[”"]\s*(?:by|,?\s+by)\s+(.+)$', text, re.I)
    if quoted is not None:
      return self.build_row(
        year, quoted.group(1), self.clean_author(quoted.group(2)), result, source_url)
    match = re.match(r'^(.+?)\s+(?:by|written by)\s+(.+)$', text, re.I)
    if match is not None:
      return self.build_row(
        year, match.group(1), self.clean_author(match.group(2)), result, source_url)
    comma_match = re.match(r'^(.+?),\s+([^,]+(?:\s+[^,]+){0,6})$', text)
    if comma_match is not None:
      return self.build_row(
        year, comma_match.group(1), self.clean_author(comma_match.group(2)), result, source_url)
    return None

  def winner_sentence_row(self, year, text, source_url):
    text = self.clean_entry_text(text)
    author_match = re.search(r'([A-Z][^,.]+?)\s+(?:has\s+)?won\b', text)
    if author_match is None or ' for ' not in text:
      return None
    title = text.rsplit(' for ', 1)[1]
    title = re.sub(r'[.]\s*$', '', title).strip()
    return self.build_row(
      year,
      self.clean_title(title),
      self.clean_author(author_match.group(1)),
      RESULT_WINNER,
      source_url)

  def build_row(self, year, title, author, result, source_url):
    title = self.clean_title(title)
    author = self.clean_author(author)
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

  def clean_entry_text(self, text):
    text = normalize_line(text)
    text = text.replace('’', "'").replace('‘', "'")
    text = re.sub(r'^\s*(?:the\s+)?(?:cilip\s+)?carnegie medal(?: for writing)?\s*:?\s*', '', text, flags=re.I)
    text = re.sub(r'\s+-\s+Carnegie(?: Medal)?(?: for Writing)?.*$', '', text, flags=re.I)
    return normalize_line(text).strip(' -*;:')

  def clean_title(self, text):
    text = strip_publication_notes(normalize_line(text))
    text = re.sub(r'^[“"]|[”"]$', '', text).strip()
    text = ISBN_RE.sub('', text)
    return normalize_line(text).strip(' ,.;:')

  def clean_author(self, text):
    text = normalize_line(text)
    text = PUBLISHER_RE.sub('', text)
    text = ISBN_RE.sub('', text)
    text = re.sub(r'\s+\((?:[^)]*press|[^)]*books?|publisher|isbn)[^)]*\)\s*$', '', text, flags=re.I)
    text = strip_publication_notes(text)
    text = re.sub(r'\s+and\s+$', '', text, flags=re.I)
    return normalize_line(text).strip(' ,.;:')

  def text_lines(self, html):
    soup = BeautifulSoup(html or '', 'html.parser')
    for removable in soup.find_all(['script', 'style', 'sup']):
      removable.decompose()
    lines = []
    for node in soup.find_all(SEMANTIC_TAGS):
      copied=BeautifulSoup(str(node),'html.parser')
      # Paragraphs hold whole annual rosters separated by br; inline emphasis
      # still belongs to its title/byline rather than a separate source line.
      for br in copied.find_all('br'):br.replace_with('__CARNEGIE_BREAK__')
      for fragment in copied.get_text().split('__CARNEGIE_BREAK__'):
        text=normalize_line(fragment)
        if text:lines.append(text)
    if lines:
      return lines
    text = soup.get_text('\n')
    return [normalize_line(line) for line in text.splitlines() if normalize_line(line)]

  def is_writing_shortlist_start(self, key):
    if 'greenaway' in key or 'illustration' in key:
      return False
    return (
      'carnegie medal for writing shortlist' in key
      or 'medal for writing shortlist' in key
      or key in {'cilip carnegie medal', 'carnegie medal'}
      or key.startswith('writing shortlist')
      or key.startswith('the carnegie medal shortlist')
      or re.fullmatch(r'(?:\d{4} )?(?:cilip )?carnegie(?: medal)? shortlist',key) is not None)

  def is_next_non_writing_section(self, key):
    return (
      'greenaway' in key
      or 'illustration' in key
      or key.startswith('shadowers choice and medal for illustration')
      or key.startswith('carnegie shadowers choice and medal for illustration')
      or key.startswith('about the awards')
      or key.startswith('related downloads'))

  def is_shortlist_heading(self, line):
    key = normalize_heading(line)
    return (
      self.is_writing_shortlist_start(key)
      or key in {'shortlist', 'shortlisted books', 'writing'}
      or key.startswith('the ')
      and 'shortlist' in key
      and ' by ' not in key)

  def is_archive_heading(self, line):
    key = normalize_heading(line)
    return (
      key in {'medal for writing winners', 'writing winners', 'winner', 'winners'}
      or key.startswith('before 2007')
      or key.startswith('the year refers')
      or key.startswith('for books published')
      or key.startswith('archive'))

  def is_source_note(self, line):
    key = normalize_heading(line)
    return (
      key.startswith('before 2007')
      or key.startswith('the year refers')
      or key.startswith('books published')
      or key.startswith('please note'))

  def is_non_entry_line(self, line):
    key = normalize_heading(line)
    return (
      not key
      or key in {'writing', 'winner', 'winners', 'shortlist', 'shortlisted'}
      or key.startswith('download')
      or key.startswith('find out more')
      or key.startswith('read more')
      or key.startswith('watch ')
      or key.startswith('image ')
      or key.startswith('isbn')
      or 'nominated titles' in key
      or 'longlist' in key)

  def is_excluded_public_stage_url(self, url):
    key = normalize_heading(url or '')
    return 'nominated' in key or 'longlist' in key

  def year_from_url_or_text(self, url, html):
    match = YEAR_RE.search(url or '')
    if match is not None:
      return int(match.group(1))
    for line in self.text_lines(html):
      match = YEAR_RE.search(line)
      if match is not None:
        return int(match.group(1))
    return None

  def dedupe_rows(self, rows):
    by_key = {}
    for row in rows:
      if row is None:
        continue
      key = (row.get('award_year', ''), normalize_heading(row.get('title', '')))
      current = by_key.get(key)
      if current is None:
        by_key[key] = row
        continue
      if row.get('result') == RESULT_WINNER and current.get('result') != RESULT_WINNER:
        by_key[key] = row
      elif row.get('result') == current.get('result') and len(row.get('author', '')) > len(current.get('author', '')):
        by_key[key] = row
    return list(by_key.values())

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(int(row['award_year']), []).append(row)
    entries = []
    for year in sorted(by_year):
      year_rows = sorted(
        by_year[year],
        key=lambda row: (
          0 if row.get('result') == RESULT_WINNER else 1,
          normalize_heading(row.get('title', ''))))
      positioned = assign_positions(year_rows, year, tied_winners_share_position=True)
      for row in positioned:
        entries.append(self.build_award_entry(
          row,
          row.get('source_url') or WINNERS_URL,
          year,
          row.get('category') or CATEGORY,
          award=AWARD_NAME))
    return entries


def parse_carnegie_medal(html, base_url=WINNERS_URL, name=AWARD_NAME, **kwargs):
  return CarnegieMedalParser().parse(html, base_url, name, **kwargs)
