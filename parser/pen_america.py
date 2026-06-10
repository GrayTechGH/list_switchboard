#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
PEN America literary award parsers.

Maintenance notes:
- PEN America award landing pages preserve winner history; annual finalists
  and winners posts preserve finalist sections. V1 imports winners/finalists
  only and deliberately ignores longlists and withdrawn rows.
- Other PEN America awards can reuse this parser by adding a focused fetcher
  config. PEN/Faulkner Foundation awards use a separate source family.
"""

import re
from urllib.parse import urljoin

from lxml import html as lxml_html

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, RESULT_NOMINEE, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_NOMINEE, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key


class PENAwardConfig:

  def __init__(self, award_name, category, heading_aliases, split_mode='auto'):
    self.award_name = award_name
    self.category = category
    self.heading_aliases = tuple(heading_aliases)
    self.split_mode = split_mode


class PENAmericaAwardParser(AwardParserBase):
  """
  Parse PEN America landing pages and annual finalist/winner posts.

  Invariants:
  - Longlist sections are skipped because the recipe scope is finalist-depth.
  - Withdrawn rows are skipped, with a note, rather than imported as nominees.
  """

  AWARD_NAME = 'PEN America Literary Awards'

  def parse(self, pages, base_url, name, config):
    if isinstance(pages, (str, bytes)):
      pages = ((base_url, pages, 'landing'),)
    rows = []
    notes = []
    for page_url, page_html, page_kind in pages:
      root = self.html_root(page_html)
      page_rows, page_notes = self.parse_page(root, page_url, config, page_kind)
      rows.extend(page_rows)
      notes.extend(page_notes)
    entries = self.entries_from_rows(self.dedupe_rows(rows), config)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes)

  def parse_page(self, root, base_url, config, page_kind):
    if page_kind == 'landing':
      return self.parse_landing(root, base_url, config)
    return self.parse_annual_post(root, base_url, config)

  def parse_landing(self, root, base_url, config):
    rows = []
    notes = []
    for table in root.xpath('//table'):
      rows.extend(self.rows_from_table(table, base_url, config, RESULT_WINNER))
    for node in self.content_nodes(root):
      text = self.node_text(node)
      if not self.accept_landing_line(text, config):
        continue
      row, note = self.row_from_text_node(
        node, base_url, config, RESULT_WINNER, require_year=True)
      if note:
        notes.append(note)
      if row:
        rows.append(row)
    return rows, notes

  def parse_annual_post(self, root, base_url, config):
    rows = []
    notes = []
    for heading in self.award_headings(root, config):
      section_nodes = self.following_section_nodes(heading)
      current_result = None
      skip_section = False
      for node in section_nodes:
        text = self.node_text(node)
        if not text:
          continue
        label_result = (
          self.result_from_heading(text)
          if self.is_heading_node(node)
          else None
        )
        if label_result == 'longlist':
          skip_section = True
          current_result = None
          continue
        if label_result is not None:
          skip_section = False
          current_result = label_result
          continue
        if skip_section or current_result is None:
          continue
        for item in self.row_nodes(node):
          row, note = self.row_from_text_node(
            item, base_url, config, current_result, require_year=False)
          if note:
            notes.append(note)
          if row:
            rows.append(row)
    return rows, notes

  def rows_from_table(self, table, base_url, config, result):
    rows = []
    header_map = self.header_map(table)
    for tr in table.xpath('.//tr'):
      cells = tr.xpath('./td|./th')
      if len(cells) < 2:
        continue
      if self.row_is_header(cells):
        continue
      year = self.year_from_text(self.clean_cell_text(
        cells[header_map.get('year', 0)]))
      if year is None:
        continue
      title_cell = cells[header_map.get('title', 1)]
      author_cell = cells[header_map.get('author', 2)] if len(cells) > 2 else None
      title = self.clean_title(self.clean_cell_text(title_cell))
      author = self.clean_author(self.clean_cell_text(author_cell))
      if not author:
        title, author = self.split_work_text(
          self.clean_cell_text(title_cell), config.split_mode)
      if title and author:
        rows.append(self.row(
          year, title, author, result, self.first_link_url(title_cell, base_url),
          config))
    return rows

  def row_from_text_node(self, node, base_url, config, result, require_year):
    text = self.node_text(node)
    if self.is_withdrawn(text):
      year = self.year_from_text(text)
      label = str(year) if year is not None else 'row'
      return None, 'Skipped withdrawn PEN America %s entry from %s.' % (
        label, base_url)
    year = self.year_from_text(text)
    if year is None:
      year = self.year_from_text(self.node_text(self.nearest_year_heading(node)))
    if year is None:
      year = self.year_from_text(base_url)
    if require_year and year is None:
      return None, None
    work_text = self.strip_year_prefix(text)
    work_text = self.strip_result_prefix(work_text)
    title, author = self.split_work_text(work_text, config.split_mode)
    if not title or not author or self.is_ignored_row(work_text):
      return None, None
    return self.row(
      year, title, author, result, self.first_link_url(node, base_url), config), None

  def row(self, year, title, author, result, source_url, config):
    return {
      'award_year': str(year),
      'title': self.clean_title(title),
      'author': self.clean_author(author),
      'result': result,
      'source_url': source_url,
      'category': config.category,
    }

  def entries_from_rows(self, rows, config):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      award_rows = [
        self.build_award_entry(
          row, row.get('source_url') or '', year, row['category'],
          award=config.award_name)
        for row in by_year[year]
      ]
      entries.extend(assign_positions(
        award_rows, int(year), tied_winners_share_position=True))
    return entries

  def dedupe_rows(self, rows):
    deduped = []
    seen = set()
    for row in rows:
      key = (
        row.get('award_year', ''),
        normalize_heading(row.get('category', '')),
        row.get('result', ''),
        normalize_heading(row.get('title', '')),
        normalize_heading(row.get('author', '')),
      )
      if key in seen:
        continue
      seen.add(key)
      deduped.append(row)
    return deduped

  def award_headings(self, root, config):
    aliases = [normalize_heading(alias) for alias in config.heading_aliases]
    headings = []
    for heading in root.xpath('//h1|//h2|//h3|//h4|//h5|//strong|//p|//li'):
      text = normalize_heading(self.node_text(heading))
      if any(alias and alias in text for alias in aliases):
        headings.append(heading)
    return headings

  def following_section_nodes(self, heading):
    nodes = []
    heading_tag = (heading.tag or '').lower()
    stop_tags = {'h1', 'h2'} if heading_tag in {'h1', 'h2'} else {'h1', 'h2', 'h3'}
    for sibling in heading.itersiblings():
      tag = (sibling.tag or '').lower()
      if tag in stop_tags:
        break
      nodes.append(sibling)
    return nodes

  def content_nodes(self, root):
    return root.xpath('//li|//p|//tr')

  def row_nodes(self, node):
    children = node.xpath('.//li')
    return children or [node]

  def result_from_heading(self, text):
    heading = normalize_heading(text)
    if 'longlist' in heading:
      return 'longlist'
    if 'winner' in heading:
      return RESULT_WINNER
    if 'finalist' in heading or 'shortlist' in heading:
      return RESULT_NOMINEE
    return None

  def is_heading_node(self, node):
    return (node.tag or '').lower() in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}

  def accept_landing_line(self, text, config):
    if self.is_ignored_row(text):
      return False
    if self.year_from_text(text) is None:
      return False
    heading = normalize_heading(text)
    if any(normalize_heading(alias) in heading for alias in config.heading_aliases):
      return False
    return ',' in text or ' by ' in text

  def split_work_text(self, value, split_mode):
    text = strip_publication_notes(normalize_line(value))
    text = re.sub(r'\s+[–-]\s*(?:winner|finalist|finalists)$', '', text, flags=re.I)
    if re.search(r'\s+by\s+', text, re.I):
      title, author = re.split(r'\s+by\s+', text, maxsplit=1, flags=re.I)
      return self.clean_title(title), self.clean_author(author)
    parts = [part.strip() for part in text.split(',') if part.strip()]
    if len(parts) < 2:
      return '', ''
    if split_mode == 'author_title':
      author = parts[0]
      title = ', '.join(parts[1:])
    elif split_mode == 'title_author':
      title = ', '.join(parts[:-1])
      author = parts[-1]
    else:
      title, author = self.auto_split_comma_parts(parts)
    return self.clean_title(title), self.clean_author(author)

  def auto_split_comma_parts(self, parts):
    if len(parts) == 2:
      return parts[0], parts[1]
    if any(word in parts[0].casefold() for word in ('edited', 'translation')):
      return ', '.join(parts[:-1]), parts[-1]
    return parts[1], ', '.join([parts[0]] + parts[2:])

  def strip_year_prefix(self, text):
    return re.sub(r'^\s*(?:winner\s*:)?\s*(?:19|20)\d{2}\s*[:\-–,]\s*', '', text, flags=re.I)

  def strip_result_prefix(self, text):
    return re.sub(
      r'^\s*(?:winner|finalist|finalists|semi-finalist|semi-finalists)\s*:\s*',
      '', text, flags=re.I)

  def is_withdrawn(self, text):
    return 'withdrawn' in normalize_heading(text)

  def is_ignored_row(self, text):
    heading = normalize_heading(text)
    return (
      not heading
      or 'longlist' in heading
      or heading in {'winner', 'winners', 'finalist', 'finalists'})

  def clean_title(self, value):
    return normalize_line(value).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    text = normalize_line(value)
    text = re.sub(r'^\s*by\s+', '', text, flags=re.I)
    return strip_publication_notes(text).strip(' "\u201c\u201d,')

  def html_root(self, html):
    return lxml_html.fromstring(html or '<html></html>')

  def node_text(self, node):
    if node is None:
      return ''
    return normalize_line(' '.join(
      text.strip()
      for text in node.xpath('.//text()[not(ancestor::script or ancestor::style)]')
      if text.strip()))

  def clean_cell_text(self, cell):
    return self.node_text(cell)

  def first_link_url(self, node, base_url):
    hrefs = node.xpath('(.//a[@href])[1]/@href')
    return urljoin(base_url, hrefs[0]) if hrefs else base_url

  def nearest_year_heading(self, node):
    nodes = node.xpath('preceding::*[self::h1 or self::h2 or self::h3][1]')
    return nodes[0] if nodes else None

  def year_from_text(self, value):
    match = re.search(r'(19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def header_map(self, table):
    mapped = {}
    for index, cell in enumerate(table.xpath('.//tr[1]/*')):
      text = normalize_heading(self.clean_cell_text(cell))
      if 'year' in text:
        mapped['year'] = index
      elif 'title' in text or 'book' in text or 'work' in text:
        mapped['title'] = index
      elif 'author' in text or 'writer' in text:
        mapped['author'] = index
    return mapped

  def row_is_header(self, cells):
    return any(normalize_heading(self.clean_cell_text(cell)) == 'year' for cell in cells)
