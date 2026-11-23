#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
James Tait Black Prize parser for official winner archives and shortlist posts.

Maintenance notes:
- The official winner pages list rows by publication year, not ceremony or
  announcement year. Positions and award_year intentionally use that year.
- Shortlist history is not a complete archive, so configured official shortlist
  posts are parsed as supplements rather than replacement fallback sources.
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
    split_title_author_byline,
  )
  from calibre_plugins.list_switchboard.parser.base import author_list
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
  from calibre_plugins.list_switchboard.parser.incremental import ParsedUnitCache,project_source_rows,restore_source_rows
  from calibre_plugins.list_switchboard.errors import ImportCancelledError,CamoufoxRequiredError
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
    split_title_author_byline,
  )
  from .base import author_list
  from .generic import position_sort_key
  from .incremental import ParsedUnitCache,project_source_rows,restore_source_rows
  from errors import ImportCancelledError,CamoufoxRequiredError


AWARD_NAME = 'James Tait Black Prize'
FICTION_URL = 'https://james-tait-black.ed.ac.uk/winners/fiction'
BIOGRAPHY_URL = 'https://james-tait-black.ed.ac.uk/winners/biography'
SHORTLIST_URL_2026 = 'https://james-tait-black.ed.ac.uk/indie-talent-shines-on-book-prize-shortlist'
SHORTLIST_URL_2024 = 'https://www.ed.ac.uk/news/2024/love-and-loss-illuminates-book-prize-shortlist'


def _category_key(value):
  return normalize_heading(value).replace('non fiction', 'nonfiction')


def work_identity(row):
  return (str(row['award_year']), normalize_heading(row['title']),
    tuple(sorted(normalize_heading(a) for a in author_list(row.get('authors', row.get('author', ''))))))


class JamesTaitBlackOfficialParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def __init__(self, category, shortlist_heading_aliases=()):
    self.category = category
    self.shortlist_heading_aliases = tuple(shortlist_heading_aliases or (category,))
    self.shortlist_heading_keys = {
      _category_key(alias) for alias in self.shortlist_heading_aliases
    }

  def parse(
      self, html, base_url, name, fetch_url=None, shortlist_urls=(),
      shortlist_pages=(), log=None, progress=None,cached_parsed=None,incremental_update=False,
      shortlist_specs=None):
    rows, notes = self.winner_rows(html, base_url)
    shortlist_specs = shortlist_specs or {}
    cache=ParsedUnitCache('james-tait-closed-shortlists-v2',json.dumps([
      base_url,name,self.category,self.shortlist_heading_aliases,shortlist_urls,shortlist_specs], sort_keys=True),cached_parsed,incremental_update)
    winners_complete = bool(rows) and not notes
    if not winners_complete:
      try:
        previous = restore_source_rows(cache.previous('winners'),
          (cache.old_units.get('winners') or {}).get('metadata') or {})
      except (ValueError, TypeError):
        previous = []
      if previous:
        rows = previous
        notes.append('James Tait Black winner archive was incomplete; retained the complete cached archive pending retry.')
    units={'winners':(list(rows),None,winners_complete)}
    winners={int(row['award_year']) for row in rows}
    latest=max(winners,default=0)
    archive_rows = list(rows)

    pages = list(shortlist_pages or ())
    if fetch_url is not None:
      total = len(shortlist_urls or ())
      for index, url in enumerate(shortlist_urls or (), 1):
        old=cache.old_units.get(url) or {}
        previous=[]
        try:
          previous=restore_source_rows(cache.previous(url),old.get('metadata') or {})
        except (ValueError,TypeError):
          pass
        years={int(row['award_year']) for row in previous}
        required_winners = {work_identity(row) for row in archive_rows if int(row['award_year']) in years}
        prior_works = {work_identity(row) for row in previous}
        spec = shortlist_specs.get(url, {})
        expected_count = (spec.get('counts') or {}).get(self.category)
        if (winners_complete and old.get('complete') is True and old.get('revision')==url and len(years)==1 and
            years.issubset(winners) and max(years)<min(latest,datetime.datetime.now().year) and
            required_winners and required_winners.issubset(prior_works) and
            (not expected_count or len(prior_works) == expected_count) and
            (not spec.get('year') or years == {spec['year']})):
          rows.extend(previous)
          units[url]=(previous,url,True)
          continue
        try:
          if progress is not None:
            progress(index, total, f'Fetching {name} shortlist page {index} of {total}')
          source_rows=self.shortlist_rows(fetch_url(url),url)
          if not source_rows:
            raise ValueError('Official shortlist post had no usable category entries.')
          if expected_count and len({work_identity(row) for row in source_rows}) != expected_count:
            raise ValueError('Official shortlist post did not expose its complete configured category roster.')
          if spec.get('year') and {int(row['award_year']) for row in source_rows} != {spec['year']}:
            raise ValueError('Official shortlist post has a conflicting publication year.')
          rows.extend(source_rows)
          units[url]=(source_rows,url,True)
        except (ImportCancelledError,CamoufoxRequiredError):
          raise
        except Exception as err:
          rows.extend(previous)
          units[url]=(previous,url,False)
          notes.append(f'{name} shortlist page could not be fetched: {url}: {err}')
          if log is not None:
            log(f'{name} shortlist page failed: {url}: {err}')

    for url, page_html in pages:
      source_rows=self.shortlist_rows(page_html,url)
      rows.extend(source_rows)
      units[url]=(source_rows,url,bool(source_rows))

    rows = self.dedupe_rows(rows)
    entries = self.entries_from_rows(rows)
    entries=sorted(entries,key=lambda item:position_sort_key(item.get('position','')))
    for url,(source_rows,revision,complete) in units.items():
      projected,metadata=project_source_rows(source_rows,entries,
        work_identity)
      cache.put(url,projected,revision=revision,complete=complete,metadata=metadata)
    parsed=self.parsed_result(
      name,
      base_url,
      entries,
      notes=notes)
    parsed['incremental_state']=cache.state(entries)
    parsed['incremental_state']['discovery']={'refresh_units':['winners']}
    return parsed

  def winner_rows(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    notes = []
    for item in soup.find_all('li'):
      text = self.clean_text(item)
      if not text:
        continue
      item_rows = self.parse_winner_item(
        text, self.first_link_url(item, base_url) or base_url)
      if not item_rows and self.last_year_match(text) is not None and ' - ' in text:
        notes.append(f'{self.category} winner row could not be parsed: {text}')
      rows.extend(item_rows)
    return rows, notes

  def parse_winner_item(self, text, source_url):
    year_match = self.last_year_match(text)
    if year_match is None:
      return []
    year = int(year_match.group(0))
    work_text = text[:year_match.start()].rstrip(' -\u2013\u2014(').strip()
    work_text = re.sub(r'\s*\(\s*winner\s*\)\s*$', '', work_text, flags=re.I).strip()
    joint_label = bool(re.match(r'^joint award\s*:', work_text, re.I))
    work_text = re.sub(r'^joint award\s*:\s*', '', work_text, flags=re.I).strip()
    if year==2002 and work_text=='Jenny Uglow The Lunar Men: The Friends Who Made the Future 1730-1810 (Faber)':
      work_text=work_text.replace('Jenny Uglow ','Jenny Uglow - ',1)

    rows = []
    for segment in self.split_joint_segments(work_text, joint_label):
      parsed = self.parse_author_title_segment(segment)
      if parsed is None:
        continue
      author, title = parsed
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': RESULT_WINNER,
        'source_url': source_url,
        'category': self.category,
      })
    return rows

  def split_joint_segments(self, value, joint_label=False):
    if not value:
      return ()
    if joint_label:
      parts = re.split(r'\s+and\s+(?=[^-]+?\s+-\s+)', value)
      return tuple(part.strip() for part in parts if part.strip())

    parts = []
    remaining = value
    pattern = re.compile(r'\)\s+and\s+(?=[^()]+?\s+-\s+)')
    while True:
      match = pattern.search(remaining)
      if match is None:
        break
      parts.append(remaining[:match.start() + 1].strip())
      remaining = remaining[match.end():].strip()
    parts.append(remaining.strip())
    return tuple(part for part in parts if part)

  def parse_author_title_segment(self, value):
    if ' - ' not in value:
      return None
    author, title = value.split(' - ', 1)
    author = self.clean_author(author)
    title = self.clean_title(title)
    if not author or not title:
      return None
    return author, title

  def shortlist_rows(self, html, page_url):
    soup = BeautifulSoup(html, 'html.parser')
    soup = soup.find('main') or soup
    article_year = self.article_year(soup, page_url)
    if article_year is None:
      return []
    award_year = article_year - 1
    rows = []
    for heading in soup.find_all(['h2', 'h3']):
      if not self.shortlist_heading_matches(self.clean_text(heading)):
        continue
      for node in self.section_nodes(heading):
        if getattr(node, 'name', None) != 'p':
          continue
        declared = self.declared_shortlist_rows(self.clean_text(node), award_year, page_url)
        if declared is not None:
          rows.extend(declared)
          continue
        parsed = self.parse_shortlist_paragraph(self.clean_text(node))
        if parsed is None:
          continue
        author, title = parsed
        rows.append({
          'award_year': str(award_year),
          'title': title,
          'author': author,
          'result': RESULT_SHORTLISTED,
          'source_url': self.first_link_url(node, page_url) or page_url,
          'category': self.category,
        })
    return rows

  def declared_shortlist_rows(self, text, award_year, page_url):
    """Read the official 2024 paragraph's explicit semicolon-delimited roster."""
    match = re.match(r'^The\s+(four|six|\d+)\s+(novels|biographies)\s+shortlisted\b.*?\bare:\s*(.+)$', text, re.I)
    if match is None:
      return None
    declared = {'four': 4, 'six': 6}.get(match[1].casefold())
    if declared is None:
      declared = int(match[1])
    rows = []
    for fragment in match[3].split(';'):
      fragment = re.sub(r'^\s*and\s+', '', fragment.strip(), flags=re.I).rstrip('.')
      fragment = re.sub(r',?\s+translated by\s+.+$', '', fragment, flags=re.I)
      title, author = split_title_author_byline(strip_publication_notes(fragment))
      if not title or not author:
        raise ValueError('Official James Tait Black declared roster has an incomplete book byline.')
      rows.append({'award_year': str(award_year), 'title': self.clean_title(title),
        'author': self.clean_author(author), 'result': RESULT_SHORTLISTED,
        'source_url': page_url, 'category': self.category})
    if len({work_identity(row) for row in rows}) != declared:
      raise ValueError('Official James Tait Black declared roster is incomplete.')
    return rows

  def parse_shortlist_paragraph(self, text):
    if not text:
      return None
    matches = list(re.finditer(
      r"([A-Z][A-Za-zÀ-ÖØ-öø-ÿ .'\-]+?)(?:'s|\u2019s)\s+([^()]+?)\s*\(",
      text))
    if not matches:
      return None
    match = matches[0]
    author = self.clean_shortlist_author(match.group(1))
    title = self.clean_title(match.group(2))
    if not author or not title:
      return None
    return author, title

  def clean_shortlist_author(self, value):
    value = normalize_line(value)
    lowered = value.casefold()
    for marker in (' category, ', ' features ', ' of '):
      index = lowered.rfind(marker)
      if index >= 0:
        value = value[index + len(marker):]
        lowered = value.casefold()
    value = re.sub(r'^\s*in\s+', '', value, flags=re.I)
    return self.clean_author(value)

  def section_nodes(self, heading):
    for node in heading.find_all_next():
      if node is heading:
        continue
      if getattr(node, 'name', None) in {'h2', 'h3'}:
        break
      yield node

  def shortlist_heading_matches(self, value):
    return _category_key(value) in self.shortlist_heading_keys

  def article_year(self, soup, page_url):
    for text_node in soup.find_all(string=re.compile(r'This article was published', re.I)):
      date=text_node.parent.find('time')
      if date:
        year=self.year_from_text(date.get('datetime') or self.clean_text(date))
        if year is not None:
          return year
      year = self.year_from_text(str(text_node))
      if year is not None:
        return year
    return self.year_from_text(page_url)

  def clean_text(self, node):
    if node is None:
      return ''
    node = BeautifulSoup(str(node), 'html.parser')
    for removable in node.find_all(['script', 'style', 'sup']):
      removable.decompose()
    return normalize_line(node.get_text(' ', strip=True).replace('\xa0', ' '))

  def clean_author(self, value):
    value = normalize_line(value)
    value = re.sub(r'\s*,?\s*translated by .+$', '', value, flags=re.I)
    value = strip_publication_notes(value)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def clean_title(self, value):
    value = normalize_line(value)
    value = re.sub(r'\s*,?\s*translated by .+$', '', value, flags=re.I)
    value = strip_publication_notes(value)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True) if node is not None else None
    return urljoin(base_url, link['href']) if link is not None else ''

  def last_year_match(self, value):
    matches = list(re.finditer(r'(?:19|20)\d{2}', value or ''))
    return matches[-1] if matches else None

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

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
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in by_year[year]
      ]
      entries.extend(assign_positions(
        year_rows, int(year), tied_winners_share_position=True))
    return entries


def parse_james_tait_black_official(
    html, base_url=FICTION_URL, name='James Tait Black Prize - Fiction',
    category='Fiction', shortlist_heading_aliases=(), fetch_url=None,
    shortlist_urls=(), shortlist_pages=(), log=None, progress=None):
  return JamesTaitBlackOfficialParser(
    category, shortlist_heading_aliases).parse(
      html,
      base_url,
      name,
      fetch_url=fetch_url,
      shortlist_urls=shortlist_urls,
      shortlist_pages=shortlist_pages,
      log=log,
      progress=progress)
