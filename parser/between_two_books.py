#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Parsers for the official Between Two Books historical page.

Maintenance notes:
- The page exposes two independent source boundaries: a numbered ``Book list``
  and an unnumbered ``Isolation reading list`` grouped by themed headings.
- Live official HTML is authoritative. The packaged ledger is a whole-result
  replacement only; remote and packaged rows must never be merged.
- The page does not establish a complete dated chronology. Missing dates and
  author credits stay missing rather than being inferred from outside sources.
"""

import json
import re
from importlib import resources

from bs4 import BeautifulSoup, UnicodeDammit
from bs4.element import Tag

try:
  from calibre_plugins.list_switchboard.parser.base import (  # type: ignore
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    imported_entry,
    ListParserBase,
    parsed_source,
  )
  from calibre_plugins.list_switchboard.parser.award_base import normalize_line
except ImportError:
  from .base import (
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    imported_entry,
    ListParserBase,
    parsed_source,
  )
  from .award_base import normalize_line


SOURCE_URL = 'https://betweentwobooks.co.uk/'
CLUB_NAME = 'Between Two Books'
NUMBERED_SOURCE_ID = 'between_two_books_numbered_archive'
ISOLATION_SOURCE_ID = 'between_two_books_isolation_reading_lists'
NUMBERED_BASELINE_COUNT = 54
ISOLATION_BASELINE_COUNT = 55

NUMBERED_NAME = 'Between Two Books - Official Book List'
ISOLATION_NAME = 'Between Two Books - Isolation & Themed Lists'

THEME_LABELS = {
  'compassion': 'Compassion',
  'rebirth': 'Rebirth',
  'art in an emergency': 'Art in an Emergency',
  'magic & medicine': 'Magic & Medicine',
  'community': 'Community',
  'resistance': 'Resistance',
  'comedy': 'Comedy',
  'nourishment': 'Nourishment',
  'love': 'Love',
}

BLOCK_MARKERS = (
  'access denied', 'browser update required', 'captcha', 'cloudflare',
  'just a moment', 'please wait for verification',
)


def decoded_html(payload):
  if isinstance(payload, bytes):
    decoded = UnicodeDammit(payload, is_html=True).unicode_markup
    return decoded or ''
  return str(payload or '')


def reject_blocked_response(markup):
  text = str(markup or '').strip()
  if not text:
    raise ValueError('Between Two Books returned an empty response.')
  lowered = text[:12000].casefold()
  if any(marker in lowered for marker in BLOCK_MARKERS):
    raise ValueError(
      'Between Two Books returned a verification or blocking response.')


def clean_title(value):
  return normalize_line(value).strip(' \t\r\n"\'‘’“”,')


def clean_credit(value):
  return normalize_line(value).strip(' \t\r\n"\'‘’“”,.;:')


def split_authors(value):
  values = re.split(r'\s+(?:&|and)\s+', clean_credit(value), flags=re.I)
  return [clean_credit(part) for part in values if clean_credit(part)]


def recommendation_metadata(value):
  context = normalize_line(value).strip()
  lowered = context.casefold()
  selector = ''
  match = re.search(
    r'guest recommendation\s+(?:from|by)\s+(.+?)(?:\)|$)', context, re.I)
  if match:
    selector = clean_credit(match.group(1))
  if not selector:
    match = re.search(r'recommended by\s+(.+?)(?:\)|$)', context, re.I)
    if match:
      selector = clean_credit(match.group(1))
  if not selector:
    match = re.search(r'recommendation by\s+(.+?)(?:\s+[–-]\s+|\)|$)', context, re.I)
    if match:
      selector = clean_credit(match.group(1))
  if not selector:
    match = re.search(
      r'\(?([^()]+?)\s+recommendatio(?:n)?(?:\s+for\b|\)|$)', context, re.I)
    if match:
      candidate = clean_credit(match.group(1))
      if candidate.casefold() != 'lockdown':
        selector = candidate
  if not selector and re.search(r'\bB2B recommendation\b', context, re.I):
    selector = CLUB_NAME
  if not selector and re.search(r'\(Between Two Books\)', context, re.I):
    selector = CLUB_NAME
  if selector.casefold() == 'b2b':
    selector = CLUB_NAME
  year_match = re.search(r'\b((?:19|20)\d{2})\b', context)
  return {
    'selection_type': 'guest_pick' if 'guest recommendation' in lowered else 'community_pick',
    'advocate_defender_host_selector': selector or None,
    'raw_selection_label': context or None,
    'selection_year': year_match.group(1) if year_match else None,
  }


def split_numbered_row(value):
  raw = normalize_line(value)
  context = ''
  context_at = raw.find('(')
  if context_at >= 0:
    context = raw[context_at:]
    core = raw[:context_at].strip()
  else:
    core = raw
  matches = list(re.finditer(r'\s+by\s+', core, re.I))
  if not matches:
    return '', [], context
  separator = matches[-1]
  title = clean_title(core[:separator.start()])
  authors = split_authors(core[separator.end():])
  return title, authors, context


def normalize_theme(value):
  text = normalize_line(value)
  if not text:
    return 'Isolation reading list'
  return THEME_LABELS.get(text.casefold(), text)


def split_isolation_row(value):
  raw = normalize_line(value)
  if ',' not in raw:
    return clean_title(raw), [], '', None, None
  title, raw_credit = raw.rsplit(',', 1)
  title = clean_title(title)
  raw_credit = clean_credit(raw_credit)
  lowered = raw_credit.casefold()
  contributor_role = None
  credential = None
  credit = raw_credit
  if lowered.startswith('from '):
    return title, [], raw_credit, None, None
  if lowered.startswith('ed. '):
    contributor_role = 'editor'
    credit = clean_credit(credit[4:])
  if re.search(r'\s+PhD$', credit, re.I):
    credential = 'PhD'
    credit = re.sub(r'\s+PhD$', '', credit, flags=re.I)
  return title, split_authors(credit), raw_credit, contributor_role, credential


def load_history_ledger():
  try:
    package = 'calibre_plugins.list_switchboard.parser.data'
    payload = resources.files(package).joinpath(
      'between_two_books_history.json').read_text(encoding='utf-8')
  except (ImportError, ModuleNotFoundError, AttributeError, FileNotFoundError):
    package = 'parser.data'
    payload = resources.files(package).joinpath(
      'between_two_books_history.json').read_text(encoding='utf-8')
  data = json.loads(payload)
  if data.get('schema_version') != 1:
    raise ValueError('Between Two Books packaged history has an unsupported schema.')
  collections = data.get('collections') or {}
  numbered = collections.get('numbered') or ()
  isolation = collections.get('isolation') or ()
  if len(numbered) != NUMBERED_BASELINE_COUNT:
    raise ValueError('Between Two Books packaged numbered history is incomplete.')
  if len(isolation) != ISOLATION_BASELINE_COUNT:
    raise ValueError('Between Two Books packaged isolation history is incomplete.')
  for collection_name, rows in (('numbered', numbered), ('isolation', isolation)):
    for position, row in enumerate(rows, 1):
      if not isinstance(row, list) or len(row) != 6:
        raise ValueError(
          f'Between Two Books packaged {collection_name} row {position} has an '
          'invalid shape.')
      title_index, authors_index = (0, 1) if collection_name == 'numbered' else (1, 2)
      if not clean_title(row[title_index]) or not isinstance(row[authors_index], list):
        raise ValueError(
          f'Between Two Books packaged {collection_name} row {position} has an '
          'invalid title or authors list.')
      if collection_name == 'numbered' and not row[authors_index]:
        raise ValueError(
          f'Between Two Books packaged numbered row {position} has no author.')
  return data


class BetweenTwoBooksParserBase(ListParserBase):

  FILTER_CATEGORIES = (CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,)
  SOURCE_ID = ''
  NAME = ''
  COLLECTION = ''
  RECIPE_SCOPE = ''
  PROGRAM_ERA = ''

  def parsed_result(self, entries, notes=None):
    return {
      'name': self.NAME,
      'source': parsed_source(self.NAME, SOURCE_URL, self.SOURCE_ID),
      'entries': entries,
      'notes': list(notes or ()) + [
        'Historical/incomplete archive: the official page does not establish a '
        'complete dated Between Two Books chronology.'
      ],
      'match_series': False,
    }

  def common_metadata(self, position):
    return {
      'club_name': CLUB_NAME,
      'priority_group': 'A',
      'recipe_scope': self.RECIPE_SCOPE,
      'program_era': self.PROGRAM_ERA,
      'region': 'Global',
      'is_reread': False,
      'source_record_id': f'between-two-books:{self.COLLECTION}:{position}',
    }

  def parse_ledger(self, reason):
    rows = load_history_ledger()['collections'][self.COLLECTION]
    entries = [self.ledger_entry(row, index) for index, row in enumerate(rows, 1)]
    return self.parsed_result(entries, [
      'Packaged history used because the live official page was unavailable or '
      f'incomplete: {normalize_line(reason)}'
    ])

  def ledger_entry(self, row, position):
    raise NotImplementedError


class BetweenTwoBooksNumberedParser(BetweenTwoBooksParserBase):

  SOURCE_ID = NUMBERED_SOURCE_ID
  NAME = NUMBERED_NAME
  COLLECTION = 'numbered'
  RECIPE_SCOPE = 'historical/incomplete numbered list'
  PROGRAM_ERA = 'official numbered archive'

  def parse(self, payload, *_args, **_kwargs):
    markup = decoded_html(payload)
    reject_blocked_response(markup)
    soup = BeautifulSoup(markup, 'html.parser')
    ordered_list = soup.select_one('div.book-list-section > ol')
    if ordered_list is None:
      raise ValueError('Between Two Books did not expose its numbered Book list.')
    rows = ordered_list.find_all('li', recursive=False)
    if len(rows) < NUMBERED_BASELINE_COUNT:
      raise ValueError(
        'Between Two Books numbered Book list was incomplete; expected at least '
        f'{NUMBERED_BASELINE_COUNT} rows and found {len(rows)}.')
    entries = []
    for position, row in enumerate(rows, 1):
      raw = normalize_line(row.get_text(' ', strip=True))
      title, authors, context = split_numbered_row(raw)
      if not title or not authors:
        raise ValueError(
          f'Between Two Books numbered row {position} did not expose a title and author.')
      entries.append(self.build_entry(position, title, authors, context))
    return self.parsed_result(entries)

  def build_entry(self, position, title, authors, context='', row=None):
    metadata = self.common_metadata(position)
    metadata.update({
      'official_sequence': position,
      **recommendation_metadata(context),
    })
    if row:
      for key in (
          'selection_type', 'advocate_defender_host_selector',
          'raw_selection_label', 'selection_year'):
        if key in row and row.get(key) is not None:
          metadata[key] = row.get(key)
    return imported_entry(str(position), title, authors, **metadata)

  def ledger_entry(self, row, position):
    title, authors, selection_type, selector, label, year = row
    metadata = {
      'selection_type': selection_type,
      'advocate_defender_host_selector': selector,
      'raw_selection_label': label,
      'selection_year': year,
    }
    return self.build_entry(position, title, authors, label or '', row=metadata)


class BetweenTwoBooksIsolationParser(BetweenTwoBooksParserBase):

  SOURCE_ID = ISOLATION_SOURCE_ID
  NAME = ISOLATION_NAME
  COLLECTION = 'isolation'
  RECIPE_SCOPE = 'historical/incomplete isolation and themed lists'
  PROGRAM_ERA = 'official isolation archive'

  def parse(self, payload, *_args, **_kwargs):
    markup = decoded_html(payload)
    reject_blocked_response(markup)
    soup = BeautifulSoup(markup, 'html.parser')
    section = soup.select_one('div.isolation-reading-list-section')
    if section is None:
      raise ValueError('Between Two Books did not expose its Isolation reading list.')
    source_rows = []
    theme = 'Isolation reading list'
    for child in section.children:
      if not isinstance(child, Tag):
        continue
      if child.name == 'h2':
        theme = normalize_theme(child.get_text(' ', strip=True))
      elif child.name == 'p':
        for line in child.get_text('\n', strip=True).splitlines():
          line = normalize_line(line)
          if line:
            source_rows.append((theme, line))
    if len(source_rows) < ISOLATION_BASELINE_COUNT:
      raise ValueError(
        'Between Two Books Isolation reading list was incomplete; expected at '
        f'least {ISOLATION_BASELINE_COUNT} rows and found {len(source_rows)}.')
    entries = []
    for position, (theme, raw) in enumerate(source_rows, 1):
      title, authors, raw_credit, contributor_role, credential = split_isolation_row(raw)
      if not title:
        raise ValueError(
          f'Between Two Books Isolation row {position} did not expose a title.')
      entries.append(self.build_entry(
        position, theme, title, authors, raw_credit,
        contributor_role, credential))
    return self.parsed_result(entries)

  def build_entry(
      self, position, theme, title, authors, raw_credit='',
      contributor_role=None, credential=None):
    metadata = self.common_metadata(position)
    metadata.update({
      'theme_or_track': normalize_theme(theme),
      'selection_type': 'themed_recommendation',
      'raw_author_credit': raw_credit or None,
      'contributor_role': contributor_role,
      'author_credential': credential,
    })
    return imported_entry(str(position), title, authors, **metadata)

  def ledger_entry(self, row, position):
    theme, title, authors, raw_credit, contributor_role, credential = row
    return self.build_entry(
      position, theme, title, authors, raw_credit or '', contributor_role, credential)


def parse_between_two_books_numbered(payload):
  return BetweenTwoBooksNumberedParser().parse(payload)


def parse_between_two_books_isolation(payload):
  return BetweenTwoBooksIsolationParser().parse(payload)
