#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Australasian Shadows Awards parser for official AHWA pages and Wikipedia.

Maintenance notes:
- The official Australasian Horror Writers Association pages are WordPress
  content. The fetcher uses REST endpoints where possible because rendered
  content is much cleaner than the themed public HTML.
- Official historical shortlist coverage is useful but uneven. Preserve "No
  shortlist" and "No award" statements as parser notes instead of inventing
  rows.
- Wikipedia is a replacement fallback only. ISFDB remains a reference source
  for category history, not a live parser input.
"""

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, UnicodeDammit

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, split_title_author, strip_editor_marker,
    strip_publication_notes, strip_square_notes, strip_tie_marker,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, split_title_author, strip_editor_marker,
    strip_publication_notes, strip_square_notes, strip_tie_marker,
  )
  from .generic import position_sort_key


AWARD_NAME = 'Australasian Shadows Award'
OFFICIAL_CURRENT_URL = 'https://australasianhorror.com/australian-shadows-awards/'
OFFICIAL_PAST_WINNERS_URL = (
  'https://australasianhorror.com/australian-shadows-awards/past-winners/')
OFFICIAL_2024_WINNERS_URL = (
  'https://australasianhorror.com/2024-australasian-shadows-awards-winners/')
OFFICIAL_CURRENT_API_URL = (
  'https://australasianhorror.com/wp-json/wp/v2/pages'
  '?slug=australian-shadows-awards')
OFFICIAL_PAST_WINNERS_API_URL = (
  'https://australasianhorror.com/wp-json/wp/v2/pages?slug=past-winners')
OFFICIAL_2024_WINNERS_API_URL = (
  'https://australasianhorror.com/wp-json/wp/v2/posts'
  '?slug=2024-australasian-shadows-awards-winners')
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Australasian_Shadows_Awards'

YEAR_RE = re.compile(r'(?:19|20)\d{2}')
SEMANTIC_TAGS = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li')

CATEGORY_BOUNDARIES = frozenset({
  'artwork', 'collection', 'collected work', 'comic', 'comics',
  'edited publication', 'edited work', 'graphic novel',
  'graphic novel comic', 'graphic novel comics', 'graphic novel or comic',
  'graphic novels comic', 'graphic novels comics', 'long fiction', 'novel',
  'novels anthologies and short stories',
  'paul haines award for long fiction', 'poetry',
  'rocky wood award for non fiction and criticism',
  'rocky wood award for nonfiction and criticism', 'short fiction',
})

EXCLUDED_CATEGORY_KEYS = frozenset({
  'artwork',
  'novels anthologies and short stories',
  'poetry',
  'short fiction',
})

NO_SHORTLIST_RE = re.compile(r'\bno\s+shortlist\b', re.I)
NO_AWARD_RE = re.compile(r'\bno\s+award(?:\s+will\s+be\s+presented)?\b', re.I)


def category_key(value):
  return normalize_heading(value).replace('non fiction', 'nonfiction')


def clean_source_text(value):
  value = normalize_line(value).replace('\x00', ' ').replace('\xa0', ' ')
  replacements = {
    '\u2018': "'",
    '\u2019': "'",
    '\u201c': '"',
    '\u201d': '"',
    '\u2013': '-',
    '\u2014': '-',
    '\u2026': '...',
  }
  for old, new in replacements.items():
    value = value.replace(old, new)
  return normalize_line(value)


class AustralasianShadowsParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def parse_official(
      self, html, base_url, name, category, category_aliases=(),
      fetch_url=None, log=None, progress=None):
    parsed_results = [
      self.parse_official_document(html, base_url, name, category, category_aliases)
    ]
    if fetch_url is not None:
      for url in self.official_supplement_urls(base_url):
        try:
          parsed_results.append(self.parse_official_document(
            fetch_url(url), url, name, category, category_aliases))
        except Exception as err:
          note = f'Australasian Shadows official supplement failed: {url}: {err}'
          parsed_results.append({'entries': (), 'notes': [note]})
          if log is not None:
            log(note)
    notes = [
      'Official AHWA current awards page exposes current-cycle finalists only.',
      'Official AHWA past-winners page includes many historical shortlists, '
      'but not uniformly for every category/year.',
      'Official annual posts supplement recent winner/shortlist gaps.',
      'Wikipedia is a replacement fallback only; ISFDB is reference-only in V1.',
    ]
    rows = []
    for parsed in parsed_results:
      rows.extend(parsed.get('entries', ()))
      notes.extend(parsed.get('notes', ()))
    parsed = self.parsed_from_rows(name, OFFICIAL_CURRENT_URL, rows, notes)
    return parsed

  def parse_wikipedia(
      self, html, base_url, name, category, category_aliases=(),
      fetch_url=None, log=None, progress=None):
    parsed = self.parse_lines(
      self.semantic_lines(html),
      base_url,
      name,
      category,
      category_aliases,
      default_result=RESULT_SHORTLISTED,
      source_label='Wikipedia')
    notes = list(parsed.get('notes', ()))
    notes.append(
      'Wikipedia is used as a replacement fallback for Australasian Shadows '
      'winner/nominee rows when official AHWA parsing is unavailable.')
    parsed['notes'] = self.unique_notes(notes)
    return parsed

  def parse_official_document(
      self, source, base_url, name, category, category_aliases=()):
    documents = self.source_documents(source)
    rows = []
    notes = []
    for content_html, title in documents:
      parsed = self.parse_lines(
        self.semantic_lines(content_html),
        self.public_url(base_url),
        name,
        category,
        category_aliases,
        default_result=self.default_result_for_title(title),
        source_label='Official AHWA',
        fallback_year=self.year_from_text(title))
      rows.extend(parsed.get('entries', ()))
      notes.extend(parsed.get('notes', ()))
    return self.parsed_from_rows(name, self.public_url(base_url), rows, notes)

  def parse_lines(
      self, lines, base_url, name, category, category_aliases=(),
      default_result=RESULT_SHORTLISTED, source_label='source',
      fallback_year=None):
    current_year = fallback_year
    current_category = None
    target_category = False
    section_result_mode = default_result
    result_mode = default_result
    rows = []
    notes = []
    for line in lines:
      text = clean_source_text(line)
      if not text:
        continue
      heading_year = self.heading_year(text)
      if heading_year is not None:
        current_year = heading_year
        current_category = None
        target_category = False
        section_result_mode = self.result_mode_for_heading(text, default_result)
        result_mode = section_result_mode
        continue
      if self.is_result_marker(text):
        result_mode = self.result_for_marker(text, default_result)
        continue
      if self.is_no_shortlist_or_award(text):
        if target_category and current_year is not None:
          notes.append(
            f'{source_label} {current_year} {category} states {text.rstrip(".")}.')
        continue
      category_text, remainder = self.category_and_remainder(text)
      if category_text is not None:
        category_text = self.clean_category_label(category_text)
        category_key_text = category_key(category_text)
        current_category = category_text
        target_category = self.category_matches(
          category_text, category, category_aliases)
        if category_key_text in EXCLUDED_CATEGORY_KEYS:
          target_category = False
        result_mode = self.result_mode_for_heading(text, section_result_mode)
        if target_category and remainder:
          rows.extend(self.rows_from_work_text(
            remainder, base_url, current_year, category, result_mode, notes,
            source_label))
        continue
      result_text, result = self.work_text_from_result_line(text)
      if result_text is not None:
        result_mode = result
        if target_category:
          rows.extend(self.rows_from_work_text(
            result_text, base_url, current_year, category, result, notes,
            source_label))
        continue
      if not target_category or current_year is None:
        continue
      rows.extend(self.rows_from_work_text(
        text, base_url, current_year, category, result_mode, notes,
        source_label))
    return self.parsed_from_rows(name, base_url, rows, notes)

  def rows_from_work_text(
      self, text, source_url, year, category, result, notes, source_label):
    if year is None:
      return []
    rows = []
    for work_text in self.split_work_text(text):
      parsed = self.parse_work_text(work_text, result)
      if parsed is None:
        if self.is_parseable_noise(work_text):
          continue
        notes.append(
          f'{source_label} {year} {category} row could not be parsed: {work_text}')
        continue
      rows.append(self.build_award_entry(parsed, source_url, year, category))
    return rows

  def parse_work_text(self, text, result):
    text = self.clean_work_text(text)
    if not text or self.is_no_shortlist_or_award(text):
      return None
    parsed = self.parse_by(text)
    if parsed is None:
      parsed = self.parse_parenthetical_author(text)
    if parsed is None:
      parsed = self.parse_dash_author_title(text)
    if parsed is None:
      parsed = self.parse_comma(text)
    if parsed is None:
      return None
    title, author = parsed
    title = self.clean_title(title)
    author = self.clean_author(author)
    if not title or not author:
      return None
    return {'title': title, 'author': author, 'result': result}

  def parse_by(self, text):
    match = re.match(r'^(.*?)\s+(?:edited\s+)?by\s+(.+)$', text, re.I)
    if match is None:
      return None
    return match.group(1), match.group(2)

  def parse_parenthetical_author(self, text):
    match = re.match(r'^(.*?)\s+\((?:by\s+)?([^()]+)\)$', text, re.I)
    if match is None:
      return None
    return match.group(1), match.group(2)

  def parse_dash_author_title(self, text):
    match = re.match(r'^(.+?)\s+-\s+(.+)$', text)
    if match is None:
      return None
    first, second = match.group(1), match.group(2)
    if self.looks_like_title(first) and not self.looks_like_title(second):
      return first, second
    return second, first

  def parse_comma(self, text):
    title, author = split_title_author(text)
    if title and author:
      return title, author
    return None

  def clean_work_text(self, text):
    text = strip_tie_marker(strip_square_notes(clean_source_text(text)))
    text = re.sub(r'^\s*(?:winner|shortlist|shortlisted|finalist|nominee)s?\s*:\s*',
                  '', text, flags=re.I)
    text = re.sub(r'^\s*(?:[-*]|\u2022)\s*', '', text)
    text = re.sub(r'\s*\((?:winner|joint winner|tie)\)\s*$', '', text, flags=re.I)
    return normalize_line(text.strip(' "\'.,;'))

  def clean_title(self, value):
    value = strip_publication_notes(clean_source_text(value))
    return value.strip(' "\'.,;')

  def clean_author(self, value):
    value = clean_source_text(value)
    value = re.sub(r'^\s*(?:by|edited\s+by)\s+', '', value, flags=re.I)
    value = re.sub(r'\s*,?\s*(?:eds?|editors?)\.?$', '', value, flags=re.I)
    return strip_editor_marker(strip_publication_notes(value)).strip(' "\'.,;')

  def source_documents(self, source):
    text = self.decode_source(source)
    parsed = self.parse_json_source(text)
    if parsed is None:
      return ((text, ''),)
    if isinstance(parsed, dict):
      parsed = (parsed,)
    documents = []
    for item in parsed:
      if not isinstance(item, dict):
        continue
      content = item.get('content') or {}
      title = item.get('title') or {}
      content_html = content.get('rendered') if isinstance(content, dict) else ''
      title_html = title.get('rendered') if isinstance(title, dict) else ''
      title_text = self.html_text(title_html)
      if content_html:
        documents.append((content_html, title_text))
    return tuple(documents) or ((text, ''),)

  def parse_json_source(self, text):
    stripped = (text or '').lstrip()
    if not stripped.startswith(('[', '{')):
      return None
    try:
      return json.loads(stripped)
    except Exception:
      return None

  def decode_source(self, source):
    if isinstance(source, bytes):
      return UnicodeDammit(source).unicode_markup
    return source or ''

  def semantic_lines(self, html):
    soup = BeautifulSoup(self.decode_source(html), 'html.parser')
    for removable in soup.find_all(['script', 'style', 'sup']):
      removable.decompose()
    for br in soup.find_all('br'):
      br.replace_with('\n')
    lines = []
    for node in soup.find_all(SEMANTIC_TAGS):
      text = self.node_text(node)
      if text:
        lines.extend(self.split_embedded_lines(text))
    if lines:
      return lines
    return self.split_embedded_lines(soup.get_text('\n'))

  def node_text(self, node):
    return clean_source_text(node.get_text(' ', strip=True))

  def split_embedded_lines(self, text):
    parts = []
    for part in re.split(r'\s*(?:\n|\u2022)\s*', text or ''):
      part = clean_source_text(part)
      if part:
        parts.append(part)
    return parts

  def html_text(self, html):
    return self.node_text(BeautifulSoup(html or '', 'html.parser'))

  def official_supplement_urls(self, base_url):
    urls = [
      OFFICIAL_PAST_WINNERS_API_URL,
      OFFICIAL_2024_WINNERS_API_URL,
    ]
    return tuple(url for url in urls if url != base_url)

  def public_url(self, url):
    api_map = {
      OFFICIAL_CURRENT_API_URL: OFFICIAL_CURRENT_URL,
      OFFICIAL_PAST_WINNERS_API_URL: OFFICIAL_PAST_WINNERS_URL,
      OFFICIAL_2024_WINNERS_API_URL: OFFICIAL_2024_WINNERS_URL,
    }
    return api_map.get(url, url)

  def heading_year(self, text):
    match = YEAR_RE.search(text)
    if match is None:
      return None
    if self.category_and_remainder(text)[0] is not None:
      return None
    heading = category_key(text)
    if (
        'winner' in heading or 'shortlist' in heading or 'finalist' in heading or
        heading == match.group(0)):
      return int(match.group(0))
    return None

  def year_from_text(self, text):
    match = YEAR_RE.search(text or '')
    return int(match.group(0)) if match is not None else None

  def result_mode_for_heading(self, text, default_result):
    heading = category_key(text)
    if 'winner' in heading:
      return RESULT_WINNER
    if 'shortlist' in heading or 'finalist' in heading or 'nominee' in heading:
      return RESULT_SHORTLISTED
    return default_result

  def default_result_for_title(self, title):
    title_key = category_key(title)
    if 'winner' in title_key and 'shortlist' not in title_key:
      return RESULT_WINNER
    return RESULT_SHORTLISTED

  def is_result_marker(self, text):
    return category_key(text) in {
      'winner', 'winners', 'shortlist', 'shortlisted', 'shortlisted works',
      'finalist', 'finalists', 'nominee', 'nominees',
    }

  def result_for_marker(self, text, default_result):
    heading = category_key(text)
    if heading in {'winner', 'winners'}:
      return RESULT_WINNER
    if heading in {
        'shortlist', 'shortlisted', 'shortlisted works', 'finalist',
        'finalists', 'nominee', 'nominees'}:
      return RESULT_SHORTLISTED
    return default_result

  def work_text_from_result_line(self, text):
    match = re.match(
      r'^(winner|winners|shortlist|shortlisted|finalist|finalists|'
      r'nominee|nominees)\s*:\s*(.+)$',
      text,
      re.I)
    if match is None:
      return None, None
    result = RESULT_WINNER if match.group(1).casefold().startswith('winner') else RESULT_SHORTLISTED
    return match.group(2), result

  def category_and_remainder(self, text):
    if ':' in text:
      left, right = text.split(':', 1)
      if self.is_category_boundary(left):
        return left, normalize_line(right)
    if self.is_category_boundary(text):
      return text, ''
    return None, ''

  def clean_category_label(self, label):
    label = clean_source_text(label)
    label = re.sub(r'\s*\([^)]*\)\s*$', '', label)
    return normalize_line(label.strip(' :'))

  def is_category_boundary(self, label):
    return category_key(self.clean_category_label(label)) in CATEGORY_BOUNDARIES

  def category_matches(self, label, category, category_aliases):
    label_key = category_key(self.clean_category_label(label))
    aliases = {category, *(category_aliases or ())}
    alias_keys = {category_key(alias) for alias in aliases if alias}
    return label_key in alias_keys

  def is_no_shortlist_or_award(self, text):
    return bool(NO_SHORTLIST_RE.search(text) or NO_AWARD_RE.search(text))

  def is_parseable_noise(self, text):
    key = category_key(text)
    return (
      not key or key in CATEGORY_BOUNDARIES or self.is_result_marker(text) or
      key.startswith('the australasian shadows awards') or
      key.startswith('australasian shadows awards'))

  def split_work_text(self, text):
    text = self.clean_work_text(text)
    if not text:
      return []
    return [
      normalize_line(part)
      for part in re.split(r'\s*(?:;|\s+/\s+)\s*', text)
      if normalize_line(part)
    ]

  def looks_like_title(self, value):
    key = category_key(value)
    return (
      key.startswith(('the ', 'a ', 'an ')) or
      any(word in key.split() for word in {
        'book', 'dead', 'death', 'horror', 'house', 'night', 'road', 'shadow'})
    )

  def parsed_from_rows(self, name, base_url, rows, notes):
    rows = self.dedupe_rows(rows)
    by_year = {}
    for row in rows:
      year = str(row.get('award_year', ''))
      if not year:
        continue
      clean_row = dict(row)
      clean_row.pop('position', None)
      by_year.setdefault(year, []).append(clean_row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      year_rows = sorted(
        by_year[year],
        key=lambda row: 0 if row.get('result') == RESULT_WINNER else 1)
      entries.extend(assign_positions(
        year_rows, int(year), tied_winners_share_position=True))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=self.unique_notes(notes))

  def dedupe_rows(self, rows):
    ordered = []
    by_key = {}
    for row in rows:
      key = self.row_key(row)
      existing = by_key.get(key)
      if existing is None:
        by_key[key] = row
        ordered.append(row)
        continue
      if existing.get('result') != RESULT_WINNER and row.get('result') == RESULT_WINNER:
        existing.update(row)
    return ordered

  def row_key(self, row):
    return (
      str(row.get('award_year', '')),
      category_key(row.get('category', '')),
      category_key(row.get('title', '')),
      category_key(row.get('author', '')),
    )

  def unique_notes(self, notes):
    unique = []
    for note in notes:
      if note and note not in unique:
        unique.append(note)
    return unique


def parse_australasian_shadows_official(
    html, base_url, name, category, category_aliases, fetch_url=None,
    log=None, progress=None):
  return AustralasianShadowsParser().parse_official(
    html,
    base_url,
    name,
    category,
    category_aliases,
    fetch_url=fetch_url,
    log=log,
    progress=progress)


def parse_australasian_shadows_wikipedia(
    html, base_url, name, category, category_aliases, fetch_url=None,
    log=None, progress=None):
  return AustralasianShadowsParser().parse_wikipedia(
    html,
    base_url,
    name,
    category,
    category_aliases,
    fetch_url=fetch_url,
    log=log,
    progress=progress)
