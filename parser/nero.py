#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Nero Award parsers for official, LibraryThing, and Wikipedia sources.

Maintenance notes:
- The official Wolfe Pack source is split across two pages: the finalists page
  carries 2007+ finalist sections, while the chronological winners page fills
  in years not represented on the finalist page.
- The finalists page marks winners with bold text and explicitly notes that
  finalist records were not kept until 2007, so pre-2007 rows stay winner-only.
- LibraryThing remains a replacement fallback only; Wikipedia is the final
  winner-only fallback.
"""

import re
from urllib.parse import urljoin

from lxml import html as lxml_html

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase,
    RESULT_NOMINEE,
    RESULT_WINNER,
    assign_positions,
    is_author_suffix,
    normalize_heading,
    normalize_line,
    strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
  from calibre_plugins.list_switchboard.parser.librarything_base import (
    LibraryThingAwardParserBase,
  )
except ImportError:
  from .award_base import (
    AwardParserBase,
    RESULT_NOMINEE,
    RESULT_WINNER,
    assign_positions,
    is_author_suffix,
    normalize_heading,
    normalize_line,
    strip_publication_notes,
  )
  from .generic import position_sort_key
  from .librarything_base import LibraryThingAwardParserBase


YEAR_HEADING = re.compile(r'^(19|20)\d{2}$')
YEAR_TEXT = re.compile(r'(19|20)\d{2}')
NERO_WINNERS_URL = (
  'https://wp.nerowolfe.org/htm/literary_awards/nero_award/awardees_chron.htm'
)


class NeroAwardOfficialParser(AwardParserBase):

  AWARD_NAME = 'Nero Award'
  WINNERS_URL = NERO_WINNERS_URL

  def parse(
      self, html, base_url, name, category, category_aliases=(),
      fetch_url=None, log=None, progress=None):
    rows = self.parse_finalist_rows(html, base_url, category)
    if not rows:
      raise ValueError('official Wolfe Pack finalist page did not expose Nero finalist rows')

    notes = []
    finalist_years = {row['award_year'] for row in rows}
    if fetch_url is not None:
      try:
        if log is not None:
          log(f'Nero: fetching winners supplement {self.WINNERS_URL}')
        winner_rows = self.parse_winner_rows(
          fetch_url(self.WINNERS_URL), self.WINNERS_URL, category)
        for row in winner_rows:
          if row['award_year'] not in finalist_years:
            rows.append(row)
      except Exception as err:
        notes.append(f'Official Wolfe Pack winners supplement failed: {err}')

    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      entries,
      notes=notes)

  def parse_finalist_rows(self, html, base_url, category):
    root = self.html_root(html)
    heading = self.finalists_heading(root)
    if heading is None:
      return []
    rows = []
    for year, nodes in self.year_sections(heading):
      for node in nodes:
        for item in node.xpath('.//li'):
          row = self.parse_finalist_item(item, year, base_url, category)
          if row is not None:
            rows.append(row)
    return rows

  def finalists_heading(self, root):
    headings = root.xpath('//h1')
    for heading in headings:
      if 'nero award finalists' in normalize_heading(self.node_text(heading)):
        return heading
    return None

  def year_sections(self, heading):
    sections = []
    current_year = None
    current_nodes = []
    for node in heading.itersiblings():
      tag = getattr(node, 'tag', '')
      if tag in {'h3', 'h4'}:
        text = self.node_text(node)
        year = self.year_from_heading(text)
        if year is not None:
          if current_year is not None and current_nodes:
            sections.append((current_year, tuple(current_nodes)))
          current_year = year
          current_nodes = []
          continue
        if current_year is not None and 'black orchid' in normalize_heading(text):
          if current_nodes:
            sections.append((current_year, tuple(current_nodes)))
          break
        if current_year is not None and 'did not keep a record of finalists' in normalize_heading(text):
          break
      if current_year is not None:
        current_nodes.append(node)
    if current_year is not None and current_nodes:
      sections.append((current_year, tuple(current_nodes)))
    return tuple(sections)

  def parse_finalist_item(self, node, year, base_url, category):
    text = self.node_text(node)
    if not text or 'black orchid' in normalize_heading(text):
      return None
    title, author = self.entry_from_node(node, text)
    if not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': RESULT_WINNER if self.is_winner_item(node) else RESULT_NOMINEE,
      'source_url': self.first_link_url(node, base_url) or base_url,
      'category': category,
    }

  def is_winner_item(self, node):
    return bool(node.xpath('.//strong'))

  def parse_winner_rows(self, html, base_url, category):
    root = self.html_root(html)
    table = self.winners_table(root)
    if table is None:
      raise ValueError('official Wolfe Pack winners page did not expose the Nero winners table')
    rows = []
    for tr in table.xpath('.//tr'):
      cells = tr.xpath('./th|./td')
      if len(cells) < 2:
        continue
      year = self.year_from_text(self.node_text(cells[0]))
      if year is None:
        continue
      text = self.node_text(cells[1])
      if not text or 'no award' in normalize_heading(text):
        continue
      title, author = self.entry_from_node(cells[1], text)
      if not title or not author:
        continue
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': RESULT_WINNER,
        'source_url': base_url,
        'category': category,
      })
    return tuple(rows)

  def winners_table(self, root):
    headings = root.xpath('//h1')
    for heading in headings:
      if 'chronological' not in normalize_heading(self.node_text(heading)):
        continue
      tables = heading.xpath('following::table[1]')
      if tables:
        return tables[0]
    tables = root.xpath('//table')
    return tables[0] if tables else None

  def entry_from_node(self, node, text):
    title = self.title_from_node(node)
    if title:
      author = self.author_after_title(text, title)
      if author:
        return title, author
    return self.title_author_from_text(text)

  def title_from_node(self, node):
    emphasis = node.xpath('.//*[self::em or self::i][1]')
    if emphasis:
      return self.clean_title(self.node_text(emphasis[0]))
    return ''

  def author_after_title(self, text, title):
    text = normalize_line(text)
    title_text = normalize_line(title)
    if not text or not title_text:
      return ''
    if text.startswith(title_text):
      remainder = text[len(title_text):].strip()
    else:
      match = re.search(re.escape(title_text), text, re.I)
      remainder = text[match.end():].strip() if match is not None else text
    remainder = re.sub(r'^\s*(?:by|--|—|-|,)\s*', '', remainder, flags=re.I)
    remainder = re.sub(r'\s*(?:--|—)\s*[^,()]+$', '', remainder).strip()
    remainder = strip_publication_notes(remainder)
    parts = [part.strip() for part in remainder.split(',') if part.strip()]
    if not parts:
      return ''
    author = parts[0]
    if len(parts) > 1 and is_author_suffix(parts[1]):
      author = f'{author}, {parts[1]}'
    return self.clean_author(author)

  def title_author_from_text(self, text):
    text = normalize_line(text)
    for pattern in (
        r'^(?P<title>.+?)\s+by\s+(?P<author>.+)$',
        r'^(?P<title>.+?)\s*(?:--|—)\s*(?P<author>.+)$',
        r'^(?P<title>.+?),\s*(?P<author>[^,]+(?:,\s*(?:Jr\.|Sr\.|II|III|IV|V))?)(?:,.*)?$'):
      match = re.match(pattern, text, re.I)
      if match is None:
        continue
      return (
        self.clean_title(match.group('title')),
        self.clean_author(match.group('author')))
    return '', ''

  def clean_title(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def year_from_heading(self, value):
    value = normalize_line(value)
    return int(value) if YEAR_HEADING.match(value or '') else None

  def year_from_text(self, value):
    match = YEAR_TEXT.search(value or '')
    return int(match.group(0)) if match is not None else None

  def first_link_url(self, node, base_url):
    hrefs = node.xpath('.//a[@href and not(.//img)]/@href')
    return urljoin(base_url, hrefs[0]) if hrefs else ''

  def node_text(self, node):
    return normalize_line(' '.join(
      text.strip()
      for text in node.xpath('.//text()[not(ancestor::script) and not(ancestor::style)]')
      if text.strip()))

  def html_root(self, html):
    return lxml_html.fromstring(html or '<html></html>')

  def dedupe_rows(self, rows):
    deduped = []
    seen = set()
    winners = set()
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['category']),
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      if row.get('result') == RESULT_WINNER:
        winners.add(key)
      if key in seen:
        continue
      if row.get('result') != RESULT_WINNER and key in winners:
        continue
      seen.add(key)
      deduped.append(row)
    return deduped

  def entries_from_rows(self, rows):
    by_year = {}
    for index, row in enumerate(rows):
      row = dict(row)
      row['_nero_source_order'] = index
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      award_rows = sorted(
        [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in by_year[year]
        ],
        key=lambda row: (
          row.get('result') != RESULT_WINNER,
          row.get('_nero_source_order', 0)))
      positioned = assign_positions(award_rows, int(year))
      for row in sorted(positioned, key=lambda item: item.get('_nero_source_order', 0)):
        row.pop('_nero_source_order', None)
        entries.append(row)
    return entries


class NeroAwardLibraryThingParser(LibraryThingAwardParserBase):

  AWARD_NAME = 'Nero Award'


class NeroAwardWikipediaParser(AwardParserBase):

  AWARD_NAME = 'Nero Award'

  def parse(self, html, base_url, name, category, category_aliases=()):
    rows = self.parse_rows(html, base_url, category)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url, category):
    root = self.html_root(html)
    table = self.winners_table(root)
    if table is None:
      raise ValueError('Wikipedia Nero Award page did not expose a winners table')
    rows = []
    for tr in table.xpath('.//tr'):
      cells = tr.xpath('./th|./td')
      if len(cells) < 4:
        continue
      year = self.year_from_text(self.clean_cell_text(cells[0]))
      if year is None:
        continue
      title = self.clean_title(self.clean_cell_text(cells[1]))
      author = self.clean_author(self.clean_cell_text(cells[2]))
      if not title or not author or 'no award' in normalize_heading(title):
        continue
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': RESULT_WINNER,
        'source_url': self.first_link_url(cells[1], base_url) or base_url,
        'category': category,
      })
    return tuple(rows)

  def winners_table(self, root):
    headings = root.xpath('//h2')
    for heading in headings:
      if 'winners' not in normalize_heading(self.clean_cell_text(heading)):
        continue
      tables = heading.xpath('following::table[contains(@class, "wikitable")][1]')
      if tables:
        return tables[0]
    tables = root.xpath('//table[contains(@class, "wikitable")]')
    return tables[0] if tables else None

  def html_root(self, html):
    return lxml_html.fromstring(html or '<html></html>')

  def clean_cell_text(self, node):
    return normalize_line(' '.join(
      text.strip()
      for text in node.xpath('.//text()[not(ancestor::script) and not(ancestor::style)]')
      if text.strip()))

  def clean_title(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def year_from_text(self, value):
    match = YEAR_TEXT.search(value or '')
    return int(match.group(0)) if match is not None else None

  def first_link_url(self, node, base_url):
    hrefs = node.xpath('(.//a[@href])[1]/@href')
    return urljoin(base_url, hrefs[0]) if hrefs else ''

  def dedupe_rows(self, rows):
    deduped = []
    seen = set()
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      if key in seen:
        continue
      seen.add(key)
      deduped.append(row)
    return deduped

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in by_year[year]
      ]
      entries.extend(assign_positions(award_rows, int(year)))
    return entries


def parse_nero_award_official(
    html, base_url, name, category, category_aliases=(), fetch_url=None,
    log=None, progress=None):
  return NeroAwardOfficialParser().parse(
    html,
    base_url,
    name,
    category,
    category_aliases,
    fetch_url=fetch_url,
    log=log,
    progress=progress)


def parse_nero_award_librarything(html, base_url, name, category, category_aliases=()):
  return NeroAwardLibraryThingParser().parse(
    html,
    base_url,
    name,
    category,
    category_aliases)


def parse_nero_award_wikipedia(html, base_url, name, category, category_aliases=()):
  return NeroAwardWikipediaParser().parse(
    html,
    base_url,
    name,
    category,
    category_aliases)
