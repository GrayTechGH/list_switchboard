#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Title, series, and imported-entry matching.

Maintenance notes:
- This module is intentionally not generic. The important constraint is text
  normalization, not a TypeVar relationship.
- Matching keys strip punctuation, case, leading articles through Calibre's
  title_sort(), and some single-letter initials for relaxed matching.
- The relaxed key is guarded by RELAXED_MATCH_MIN_NON_INITIAL_CHARS so short
  titles like "A B.C." do not collapse into overly broad matches.
"""

import re
import unicodedata
from collections import OrderedDict

from calibre.ebooks.metadata import title_sort


SERIES_SUFFIX_WORDS = frozenset([
  'cycle', 'saga', 'series', 'trilogy', 'universe', 'world'
])
RELAXED_MATCH_MIN_NON_INITIAL_CHARS = 6
FIND_MODE_IDENTICAL = 'identical'
FIND_MODE_SIMILAR = 'similar'
FIND_MODE_SOUNDEX = 'soundex'
FIND_MODE_FUZZY = 'fuzzy'
FIND_MODE_IGNORE = 'ignore'
FIND_MATCH_MODES = (
  FIND_MODE_IDENTICAL, FIND_MODE_SIMILAR, FIND_MODE_SOUNDEX, FIND_MODE_FUZZY,
  FIND_MODE_IGNORE,
)
FIND_MATCH_TITLE_SOUNDEX_LENGTH_DEFAULT = 6
FIND_MATCH_AUTHOR_SOUNDEX_LENGTH_DEFAULT = 8
AUTHOR_SUFFIX_WORDS = frozenset(['jr', 'sr', 'ii', 'iii', 'iv', 'v'])
ALT_TITLE_JOIN_RE = re.compile(r'\s+(and|or|aka|also known as)\s+.*$', re.I)
PARENTHETICAL_RE = re.compile(r'[\(\[\{].*?[\)\]\}]')
SUBTITLE_RE = re.compile(r'\s*[:;]\s+.*$')
ENTRY_AUTHOR_KEY_SEPARATOR = '\x1f'


def normalize_key(name):
  return clean_name(name).casefold()


POSITION_SUFFIX = re.compile(r'^(.*?)\s*\[([0-9]+(?:\.[0-9]+)?)\]\s*$')
GOODREADS_BOOK_URL = re.compile(r'goodreads\.com/book/show/([0-9]+)', re.I)


def split_position_suffix(name):
  name = (name or '').strip()
  match = POSITION_SUFFIX.match(name)
  if match is None:
    return name, None
  return match.group(1).strip(), match.group(2)


def clean_name(name):
  name, _position = split_position_suffix(name)
  return name


def normalize_match_text(value):
  if value is None:
    value = ''
  elif isinstance(value, (list, tuple, set)):
    value = ' '.join(str(item) for item in value)
  else:
    value = str(value)
  value = clean_name(value).casefold()
  return re.sub(r'[^a-z0-9]+', ' ', value).strip()


def imported_author_list(entry):
  if not isinstance(entry, dict):
    return []
  authors = entry.get('authors', [])
  if authors is None:
    authors = []
  elif isinstance(authors, str):
    authors = [authors] if authors.strip() else []
  elif isinstance(authors, (list, tuple, set)):
    authors = list(authors)
  else:
    authors = [authors]
  cleaned = []
  for author in authors:
    text = str(author or '').strip()
    if text and text not in cleaned:
      cleaned.append(text)
  return cleaned


def imported_author_search_text(entry):
  return ' '.join(imported_author_list(entry))


def imported_author_display_value(entry):
  if not isinstance(entry, dict):
    return ''
  return imported_author_list(entry)


def imported_author_key(entry):
  return ENTRY_AUTHOR_KEY_SEPARATOR.join(
    normalize_match_text(author)
    for author in imported_author_list(entry)
  )


def imported_entry_source_url(entry):
  if not isinstance(entry, dict):
    return ''
  source = entry.get('source')
  if isinstance(source, dict):
    return str(source.get('url') or '')
  return ''


def strip_accents(value):
  value = str(value or '')
  return ''.join(
    char for char in unicodedata.normalize('NFKD', value)
    if not unicodedata.combining(char)
  )


def find_similar_title_key(value):
  return normalize_match_text(title_sort_without_article(strip_accents(value)))


def find_identical_title_key(value):
  return normalize_match_text(strip_accents(value))


def find_fuzzy_title_key(value):
  value = strip_accents(value)
  value = PARENTHETICAL_RE.sub(' ', value)
  value = SUBTITLE_RE.sub('', value)
  value = ALT_TITLE_JOIN_RE.sub('', value)
  return find_similar_title_key(value)


def author_tokens(value):
  text = normalize_match_text(strip_accents(value))
  tokens = [token for token in text.split() if token not in AUTHOR_SUFFIX_WORDS]
  return [token for token in tokens if token]


def find_similar_author_key(value):
  tokens = author_tokens(value)
  if len(tokens) > 1 and ',' in str(value or ''):
    tokens = tokens[1:] + tokens[:1]
  tokens = [token for token in tokens if len(token) > 1]
  return ' '.join(tokens)


def find_identical_author_key(value):
  return normalize_match_text(strip_accents(value))


def find_fuzzy_author_key(value):
  tokens = author_tokens(value)
  if not tokens:
    return ''
  surname = tokens[0] if len(tokens) == 1 else tokens[-1]
  first_initial = tokens[0][:1] if len(tokens) > 1 else ''
  return ' '.join(part for part in (first_initial, surname) if part)


def soundex_token(value):
  value = re.sub(r'[^a-z]+', '', strip_accents(value).casefold())
  if not value:
    return ''
  groups = {
    'b': '1', 'f': '1', 'p': '1', 'v': '1',
    'c': '2', 'g': '2', 'j': '2', 'k': '2', 'q': '2', 's': '2', 'x': '2', 'z': '2',
    'd': '3', 't': '3',
    'l': '4',
    'm': '5', 'n': '5',
    'r': '6',
  }
  first = value[0].upper()
  previous = groups.get(value[0], '')
  digits = []
  for char in value[1:]:
    digit = groups.get(char, '')
    if digit and digit != previous:
      digits.append(digit)
    previous = digit
  return (first + ''.join(digits) + '000')[:4]


def soundex_key(value, length):
  tokens = normalize_match_text(value).split()
  codes = [soundex_token(token) for token in tokens]
  return ''.join(code for code in codes if code)[:int(length or 0)]


def title_find_key(value, mode, soundex_length=FIND_MATCH_TITLE_SOUNDEX_LENGTH_DEFAULT):
  if mode == FIND_MODE_IGNORE:
    return ''
  if mode == FIND_MODE_IDENTICAL:
    return find_identical_title_key(value)
  if mode == FIND_MODE_FUZZY:
    return find_fuzzy_title_key(value)
  if mode == FIND_MODE_SOUNDEX:
    return soundex_key(find_similar_title_key(value), soundex_length)
  return find_similar_title_key(value)


def author_find_key(value, mode, soundex_length=FIND_MATCH_AUTHOR_SOUNDEX_LENGTH_DEFAULT):
  if mode == FIND_MODE_IGNORE:
    return ''
  if mode == FIND_MODE_IDENTICAL:
    return find_identical_author_key(value)
  if mode == FIND_MODE_FUZZY:
    return find_fuzzy_author_key(value)
  if mode == FIND_MODE_SOUNDEX:
    return soundex_key(find_similar_author_key(value), soundex_length)
  return find_similar_author_key(value)


def append_unique(values, value):
  if value and value not in values:
    values.append(value)
  return values


def author_find_keys(value, mode, soundex_length=FIND_MATCH_AUTHOR_SOUNDEX_LENGTH_DEFAULT):
  keys = []
  append_unique(keys, author_find_key(value, mode, soundex_length))
  if isinstance(value, (list, tuple, set)):
    for item in value:
      append_unique(keys, author_find_key(item, mode, soundex_length))
  return keys


def validate_find_match_modes(title_mode, author_mode):
  if title_mode not in FIND_MATCH_MODES:
    raise ValueError(f'Unsupported title match mode: {title_mode}')
  if author_mode not in FIND_MATCH_MODES:
    raise ValueError(f'Unsupported author match mode: {author_mode}')
  if title_mode == FIND_MODE_IGNORE and author_mode == FIND_MODE_IGNORE:
    raise ValueError('Title and author cannot both be ignored.')
  if title_mode == FIND_MODE_IDENTICAL and author_mode == FIND_MODE_IDENTICAL:
    raise ValueError('Title and author cannot both be identical.')


def title_sort_without_article(value):
  value = clean_name(value)
  if not value:
    return ''
  try:
    sorted_value = title_sort(value)
  except Exception:
    sorted_value = value
  if ',' in sorted_value:
    sorted_value = sorted_value.rsplit(',', 1)[0]
  if normalize_match_text(sorted_value) == normalize_match_text(value):
    sorted_value = re.sub(r'^\s*(a|an|the)\s+', '', sorted_value, flags=re.IGNORECASE)
  return sorted_value.strip()


def remove_single_letter_tokens(key):
  return ' '.join(token for token in key.split() if len(token) > 1)


def enough_non_initial_characters(key):
  return sum(len(token) for token in key.split() if len(token) > 1) >= RELAXED_MATCH_MIN_NON_INITIAL_CHARS


def match_keys(value):
  keys = []
  for candidate in (value, title_sort_without_article(value)):
    key = normalize_match_text(candidate)
    if key and key not in keys:
      keys.append(key)
    relaxed_key = remove_single_letter_tokens(key)
    if relaxed_key and relaxed_key not in keys and enough_non_initial_characters(key):
      keys.append(relaxed_key)
  return keys


def entry_key_for_saved_match(entry, position_scoped=False):
  key = '|'.join([
    normalize_match_text(entry.get('title', '')),
    imported_author_key(entry),
  ])
  if position_scoped:
    position = str(entry.get('position', '') or '').strip().casefold()
    if position:
      return f'{key}|position:{position}'
  return key


def import_entry_priority(entry):
  if imported_entry_source_url(entry) and not (entry.get('votes') or entry.get('percent')):
    return 2
  return 1


def imported_entry_preferred(new_entry, old_entry):
  return import_entry_priority(new_entry) > import_entry_priority(old_entry or {})


def goodreads_book_id_from_url(url):
  match = GOODREADS_BOOK_URL.search(url or '')
  return match.group(1) if match is not None else ''


def relaxed_series_key(value):
  parts = normalize_match_text(value).split()
  while parts and parts[-1] in SERIES_SUFFIX_WORDS:
    parts.pop()
  return ' '.join(parts)


def series_match_keys(value):
  keys = []
  for key in match_keys(value):
    if key and key not in keys:
      keys.append(key)
    relaxed_key = relaxed_series_key(key)
    if relaxed_key and relaxed_key not in keys:
      keys.append(relaxed_key)
    for article_key in match_keys(relaxed_key):
      if article_key and article_key not in keys:
        keys.append(article_key)
  return keys


IMPORT_LIST_REVIEW_AUTO_MATCH_NONE = 'none'
IMPORT_LIST_REVIEW_AUTO_MATCH_PARTIAL = 'partial'
IMPORT_LIST_REVIEW_AUTO_MATCH_EXACT = 'exact'
IMPORT_LIST_REVIEW_AUTO_AUTHOR_SUFFIXES = frozenset([
  'jr', 'sr', 'ii', 'iii', 'iv', 'v',
])
IMPORT_LIST_REVIEW_AUTO_TITLE_BOUNDARY_RE = re.compile(
  r'\s*[:;]\s*|\s+[\u2013\u2014]\s+'
)
IMPORT_LIST_REVIEW_AUTO_QUOTED_TITLE_RES = (
  re.compile(r'"([^"]+)"'),
  re.compile(r'\u201c([^\u201d]+)\u201d'),
  re.compile(r'\u2018([^\u2019]+)\u2019'),
)
IMPORT_LIST_REVIEW_AUTO_TRAILING_QUALIFIER_RES = (
  re.compile(r'^(.*?)\s*\([^()]+\)\s*$'),
)


def import_list_review_auto_title_components(value):
  """Return structural title components only for Import List Review auto-match.

  Refactor warning:
  This rule family belongs exclusively to automatic Import List Review
  preparation. Do not combine it with or call it from cached Active Add button
  matching, Find Match, generic import helpers, or saved-match reconciliation.
  """
  raw = clean_name(str(value or '')).strip()
  components = []

  def import_list_review_auto_append_title_component(component):
    key = normalize_match_text(component)
    if key and key not in components:
      components.append(key)
    without_article = re.sub(r'^(?:a|an|the)\s+', '', key).strip()
    if without_article and without_article not in components:
      components.append(without_article)

  import_list_review_auto_append_title_component(raw)
  for component in IMPORT_LIST_REVIEW_AUTO_TITLE_BOUNDARY_RE.split(raw):
    import_list_review_auto_append_title_component(component)
  for quoted_re in IMPORT_LIST_REVIEW_AUTO_QUOTED_TITLE_RES:
    for match in quoted_re.finditer(raw):
      import_list_review_auto_append_title_component(match.group(1))
  for qualifier_re in IMPORT_LIST_REVIEW_AUTO_TRAILING_QUALIFIER_RES:
    match = qualifier_re.match(raw)
    if match is not None:
      import_list_review_auto_append_title_component(match.group(1))
  return tuple(components)


def import_list_review_auto_title_match_kind(left_title, right_title):
  """Classify title evidence only for Import List Review auto-match."""
  left_key = normalize_match_text(left_title)
  right_key = normalize_match_text(right_title)
  if not left_key or not right_key:
    return IMPORT_LIST_REVIEW_AUTO_MATCH_NONE
  if left_key == right_key:
    return IMPORT_LIST_REVIEW_AUTO_MATCH_EXACT
  left_components = set(import_list_review_auto_title_components(left_title))
  right_components = set(import_list_review_auto_title_components(right_title))
  if left_components & right_components:
    return IMPORT_LIST_REVIEW_AUTO_MATCH_PARTIAL
  return IMPORT_LIST_REVIEW_AUTO_MATCH_NONE


def import_list_review_auto_entry_title_values(entry):
  """Return an imported row's title and aliases for Import Review auto-match."""
  if not isinstance(entry, dict):
    return ()
  values = [entry.get('title', '')]
  aliases = entry.get('aliases') or []
  if isinstance(aliases, str):
    aliases = [aliases]
  values.extend(aliases)
  result = []
  for value in values:
    text = str(value or '').strip()
    if text and text not in result:
      result.append(text)
  return tuple(result)


def import_list_review_auto_author_name_parts(value):
  """Parse one name only for Import List Review automatic matching."""
  raw = str(value or '').strip()
  if not raw:
    return {
      'canonical': '', 'surname': '', 'single_name': '',
      'given_full': (), 'given_initials': (),
    }
  comma_parts = [part.strip() for part in raw.split(',') if part.strip()]
  if len(comma_parts) > 1:
    surname_tokens = normalize_match_text(comma_parts[0]).split()
    given_tokens = normalize_match_text(' '.join(comma_parts[1:])).split()
    tokens = given_tokens + surname_tokens
  else:
    tokens = normalize_match_text(raw).split()
    surname_tokens = []
    given_tokens = []

  suffixes = []
  while tokens and tokens[-1] in IMPORT_LIST_REVIEW_AUTO_AUTHOR_SUFFIXES:
    suffixes.insert(0, tokens.pop())
  if len(comma_parts) > 1:
    while given_tokens and given_tokens[-1] in IMPORT_LIST_REVIEW_AUTO_AUTHOR_SUFFIXES:
      suffixes.insert(0, given_tokens.pop())
    surname = surname_tokens[-1] if surname_tokens else ''
    given = list(given_tokens)
    single_name = ''
  elif tokens and all(len(token) == 1 for token in tokens):
    surname = ''
    single_name = ''
    given = list(tokens)
  elif len(tokens) == 1:
    surname = ''
    single_name = tokens[0]
    given = []
  elif tokens:
    surname = tokens[-1]
    single_name = ''
    given = list(tokens[:-1])
  else:
    surname = ''
    single_name = ''
    given = []

  given_full = tuple(token for token in given if len(token) > 1)
  given_initials = tuple(dict.fromkeys(token[0] for token in given if token))
  canonical_parts = (
    list(given) + ([surname or single_name] if surname or single_name else [])
    + suffixes)
  return {
    'canonical': ' '.join(canonical_parts),
    'surname': surname,
    'single_name': single_name,
    'given_full': given_full,
    'given_initials': given_initials,
  }


def import_list_review_auto_author_parts_are_partial_match(left, right):
  """Compare parsed names only for Import List Review automatic matching."""
  left_surname = left['surname']
  right_surname = right['surname']
  if left_surname and right_surname:
    if left_surname != right_surname:
      return False
    left_full = set(left['given_full'])
    right_full = set(right['given_full'])
    if left_full and right_full:
      return left['given_full'][0] == right['given_full'][0]
    left_initials = set(left['given_initials'])
    right_initials = set(right['given_initials'])
    if left_full and right_initials:
      return bool({name[0] for name in left_full} & right_initials)
    if right_full and left_initials:
      return bool({name[0] for name in right_full} & left_initials)
    if left_initials and right_initials:
      return bool(left_initials & right_initials)
    return True

  if left['single_name'] and right_surname:
    return left['single_name'] == right_surname
  if right['single_name'] and left_surname:
    return right['single_name'] == left_surname

  left_full = set(left['given_full'])
  right_full = set(right['given_full'])
  if left['single_name']:
    left_full.add(left['single_name'])
  if right['single_name']:
    right_full.add(right['single_name'])
  if left_full and right_full:
    left_first = left['given_full'][0] if left['given_full'] else left['single_name']
    right_first = right['given_full'][0] if right['given_full'] else right['single_name']
    return left_first == right_first
  left_initials = set(left['given_initials'])
  right_initials = set(right['given_initials'])
  if left_full and right_initials:
    return bool({name[0] for name in left_full} & right_initials)
  if right_full and left_initials:
    return bool({name[0] for name in right_full} & left_initials)
  return bool(left_initials and right_initials and left_initials & right_initials)


def import_list_review_auto_author_match_kind(book_authors, imported_authors):
  """Classify author evidence only for Import List Review auto-match."""
  if isinstance(book_authors, str):
    book_authors = [book_authors]
  if isinstance(imported_authors, str):
    imported_authors = [imported_authors]
  book_parts = [
    import_list_review_auto_author_name_parts(author)
    for author in (book_authors or [])
  ]
  imported_parts = [
    import_list_review_auto_author_name_parts(author)
    for author in (imported_authors or [])
  ]
  book_parts = [parts for parts in book_parts if parts['canonical']]
  imported_parts = [parts for parts in imported_parts if parts['canonical']]
  if not book_parts or not imported_parts:
    return IMPORT_LIST_REVIEW_AUTO_MATCH_NONE
  if any(
      left['canonical'] == right['canonical']
      for left in book_parts for right in imported_parts):
    return IMPORT_LIST_REVIEW_AUTO_MATCH_EXACT
  if any(
      import_list_review_auto_author_parts_are_partial_match(left, right)
      for left in book_parts for right in imported_parts):
    return IMPORT_LIST_REVIEW_AUTO_MATCH_PARTIAL
  return IMPORT_LIST_REVIEW_AUTO_MATCH_NONE


def import_list_review_auto_candidate_evidence(entry, book_title, book_authors):
  """Build tight title/author evidence only for Import Review auto-match."""
  title_kind = IMPORT_LIST_REVIEW_AUTO_MATCH_NONE
  for imported_title in import_list_review_auto_entry_title_values(entry):
    candidate_kind = import_list_review_auto_title_match_kind(
      book_title, imported_title)
    if candidate_kind == IMPORT_LIST_REVIEW_AUTO_MATCH_EXACT:
      title_kind = candidate_kind
      break
    if candidate_kind == IMPORT_LIST_REVIEW_AUTO_MATCH_PARTIAL:
      title_kind = candidate_kind
  author_kind = import_list_review_auto_author_match_kind(
    book_authors, imported_author_list(entry))
  return {
    'title': title_kind,
    'author': author_kind,
    'auto_eligible': (
      title_kind != IMPORT_LIST_REVIEW_AUTO_MATCH_NONE
      and author_kind != IMPORT_LIST_REVIEW_AUTO_MATCH_NONE),
  }


def import_list_review_auto_dedupe_candidate_groups(groups):
  """Deduplicate equal book sets only for Import Review auto-match."""
  deduped = []
  seen = set()
  for group in groups:
    identity = tuple(group.get('book_ids', ()))
    if identity and identity not in seen:
      seen.add(identity)
      deduped.append(group)
  return deduped


def import_list_review_auto_resolve_candidates(candidate_groups, reserved_book_ids=()):
  """Resolve Import Review candidates globally, including cross-row conflicts.

  ``candidate_groups`` maps row keys to a sequence of groups. Each group must
  contain ``book_ids``; one title/Goodreads candidate has one ID while one
  required-series candidate may contain several IDs.
  """
  reserved = set(reserved_book_ids or ())
  book_rows = {}
  for row_key, groups in candidate_groups.items():
    for group in groups:
      for book_id in group.get('book_ids', ()):
        book_rows.setdefault(book_id, set()).add(row_key)
  conflicted = {
    book_id for book_id, row_keys in book_rows.items() if len(row_keys) > 1
  }
  resolved = {}
  for row_key, groups in candidate_groups.items():
    if len(groups) != 1:
      continue
    group = groups[0]
    book_ids = tuple(group.get('book_ids', ()))
    if not book_ids or any(
        book_id in reserved or book_id in conflicted for book_id in book_ids):
      continue
    resolved[row_key] = group
  return resolved


class MatchingMixin:
  """
  Matches parsed recipe entries to local Calibre books.

  Type constraints:
  - self.db.new_api must expose all_field_for().
  - self.all_book_ids(), all_local_series_values(), Goodreads helpers, and debug
    helpers are expected on self through the facade composition.

  Invariants:
  - match_imported_entries() returns (matched, missing_entries), where matched is
    an OrderedDict of book_id -> imported position.
  - A book_id is matched at most once per import.
  - Series matches are tried before title matches when match_series is true.

  Refactor warning:
  - Do not replace OrderedDict de-duplication with a set where ordering matters;
    import reports and write order should follow recipe/local lookup order.
  """

  def __getattr__(self, name):
    if name.startswith('debug_import_'):
      return self._debug_import_noop
    raise AttributeError(name)

  def _debug_import_noop(self, *_args, **_kwargs):
    pass

  def author_matches(self, book_authors, imported_author):
    imported = normalize_match_text(imported_author)
    if not imported:
      return True
    book_text = normalize_match_text(book_authors)
    if not book_text:
      return True
    imported_parts = {part for part in imported.split() if len(part) > 1}
    book_parts = {part for part in book_text.split() if len(part) > 1}
    return bool(imported_parts & book_parts)

  def import_match_indexes(self, ids, titles, series):
    by_title = {}
    by_series = {}
    for book_id in ids:
      for title_key in match_keys(titles.get(book_id, '')):
        by_title.setdefault(title_key, []).append(book_id)
      for series_value in series.get(book_id, []):
        for series_key in series_match_keys(series_value):
          by_series.setdefault(series_key, []).append(book_id)
    return by_title, by_series

  def import_match_library_index(self):
    db = self.db.new_api
    ids = self.all_book_ids()
    titles = db.all_field_for('title', ids, default_value='')
    series = self.all_local_series_values(ids)
    authors = db.all_field_for('authors', ids, default_value='')
    by_title, by_series = self.import_match_indexes(ids, titles, series)
    return {
      'ids': ids,
      'titles': titles,
      'series': series,
      'authors': authors,
      'by_title': by_title,
      'by_series': by_series,
    }

  def import_list_review_auto_library_index(self):
    """Build the library index only for Import List Review auto-match.

    Refactor warning:
    Keep this index independent from cached Active Add button, Find Match, the
    generic direct matcher, and saved-match reconciliation indexes.
    """
    db = self.db.new_api
    ids = self.all_book_ids()
    titles = db.all_field_for('title', ids, default_value='')
    series = self.all_local_series_values(ids)
    authors = db.all_field_for('authors', ids, default_value='')
    by_title_component = {}
    by_exact_series = {}
    for book_id in ids:
      for component in import_list_review_auto_title_components(
          titles.get(book_id, '')):
        by_title_component.setdefault(component, []).append(book_id)
      series_values = series.get(book_id, [])
      if isinstance(series_values, str):
        series_values = [series_values]
      for series_value in (series_values or []):
        series_key = normalize_match_text(series_value)
        if series_key:
          by_exact_series.setdefault(series_key, []).append(book_id)
    return {
      'ids': ids,
      'titles': titles,
      'series': series,
      'authors': authors,
      'by_title_component': by_title_component,
      'by_exact_series': by_exact_series,
    }

  def import_list_review_auto_candidates_for_entry(
      self, entry, match_index=None, requires_series_matching=False):
    """Return tight candidate groups only for Import Review auto-match."""
    match_index = match_index or self.import_list_review_auto_library_index()
    titles = match_index['titles']
    authors = match_index['authors']
    by_title_component = match_index['by_title_component']
    by_exact_series = match_index['by_exact_series']

    possible_title_ids = []
    for imported_title in import_list_review_auto_entry_title_values(entry):
      for component in import_list_review_auto_title_components(imported_title):
        possible_title_ids.extend(by_title_component.get(component, ()))
    possible_title_ids = list(OrderedDict(
      (book_id, None) for book_id in possible_title_ids).keys())
    groups = []
    for book_id in possible_title_ids:
      evidence = import_list_review_auto_candidate_evidence(
        entry, titles.get(book_id, ''), authors.get(book_id, ''))
      if evidence['auto_eligible']:
        groups.append({
          'book_ids': (book_id,),
          'source': 'automatic',
          'kind': 'title',
          'evidence': evidence,
        })

    if requires_series_matching:
      imported_authors = imported_author_list(entry)
      for series_key in OrderedDict(
          (normalize_match_text(value), None)
          for value in import_list_review_auto_entry_title_values(entry)):
        if not series_key:
          continue
        qualifying_ids = []
        for book_id in by_exact_series.get(series_key, ()):
          author_kind = import_list_review_auto_author_match_kind(
            authors.get(book_id, ''), imported_authors)
          if author_kind != IMPORT_LIST_REVIEW_AUTO_MATCH_NONE:
            qualifying_ids.append(book_id)
        if qualifying_ids:
          groups.append({
            'book_ids': tuple(qualifying_ids),
            'source': 'automatic',
            'kind': 'required series',
            'series_key': series_key,
            'evidence': {
              'title': IMPORT_LIST_REVIEW_AUTO_MATCH_NONE,
              'author': IMPORT_LIST_REVIEW_AUTO_MATCH_PARTIAL,
              'series': IMPORT_LIST_REVIEW_AUTO_MATCH_EXACT,
              'auto_eligible': True,
            },
          })
    return import_list_review_auto_dedupe_candidate_groups(groups)

  def import_list_review_auto_goodreads_candidates_for_entry(
      self, entry, match_index=None, requires_series_matching=False):
    """Return Goodreads recovery groups only for Import Review auto-match."""
    match_index = match_index or self.import_list_review_auto_library_index()
    titles = match_index['titles']
    authors = match_index['authors']
    by_title_component = match_index['by_title_component']
    by_exact_series = match_index['by_exact_series']
    entry_source_url = imported_entry_source_url(entry)
    exact_groups = self.import_list_review_auto_goodreads_id_candidates_for_entry(
      entry, match_index=match_index)
    if exact_groups:
      return exact_groups

    data = self.fetch_goodreads_source_data(entry_source_url)
    groups = []
    for source_book in data.get('books', []):
      source_title = source_book.get('title', '')
      source_author = source_book.get('author', '')
      recovery_authors = (
        [source_author] if source_author else imported_author_list(entry))
      source_entry_evidence = import_list_review_auto_candidate_evidence(
        entry, source_title, recovery_authors)
      if not source_entry_evidence['auto_eligible']:
        continue
      possible_ids = []
      for component in import_list_review_auto_title_components(source_title):
        possible_ids.extend(by_title_component.get(component, ()))
      for book_id in OrderedDict((book_id, None) for book_id in possible_ids):
        recovery_entry = {
          'title': source_title,
          'authors': recovery_authors,
        }
        evidence = import_list_review_auto_candidate_evidence(
          recovery_entry, titles.get(book_id, ''), authors.get(book_id, ''))
        if evidence['auto_eligible']:
          groups.append({
            'book_ids': (book_id,),
            'source': 'Goodreads/deep recovery',
            'kind': 'Goodreads title',
            'evidence': evidence,
          })

    if requires_series_matching:
      imported_authors = imported_author_list(entry)
      for series_name in data.get('series_names', []):
        series_key = normalize_match_text(series_name)
        qualifying_ids = []
        for book_id in by_exact_series.get(series_key, ()):
          author_kind = import_list_review_auto_author_match_kind(
            authors.get(book_id, ''), imported_authors)
          if author_kind != IMPORT_LIST_REVIEW_AUTO_MATCH_NONE:
            qualifying_ids.append(book_id)
        if qualifying_ids:
          groups.append({
            'book_ids': tuple(qualifying_ids),
            'source': 'Goodreads/deep recovery',
            'kind': 'Goodreads required series',
            'series_key': series_key,
            'evidence': {
              'series': IMPORT_LIST_REVIEW_AUTO_MATCH_EXACT,
              'author': IMPORT_LIST_REVIEW_AUTO_MATCH_PARTIAL,
              'auto_eligible': True,
            },
          })

    return import_list_review_auto_dedupe_candidate_groups(groups)

  def import_list_review_auto_goodreads_id_candidates_for_entry(
      self, entry, match_index=None):
    """Return exact Goodreads-ID groups only for Import Review auto-match."""
    match_index = match_index or self.import_list_review_auto_library_index()
    source_goodreads_id = goodreads_book_id_from_url(
      imported_entry_source_url(entry))
    if not source_goodreads_id:
      return []
    exact_ids = [
      book_id for book_id in match_index['ids']
      if self.goodreads_id_for_book(book_id) == source_goodreads_id
    ]
    return [{
      'book_ids': (book_id,),
      'source': 'Goodreads/deep recovery',
      'kind': 'Goodreads ID',
      'evidence': {'goodreads_id': IMPORT_LIST_REVIEW_AUTO_MATCH_EXACT},
    } for book_id in exact_ids]

  def import_list_review_auto_match_source_for_candidate(
      self, entry, book_id, list_id=None, allow_goodreads_recovery=True,
      match_index=None, requires_series_matching=False, entry_key=''):
    """Classify a review selection using only Import Review auto rules."""
    if book_id is None:
      return 'manual find'
    match_index = match_index or getattr(
      self, '_import_list_review_auto_match_index', None)
    match_index = match_index or self.import_list_review_auto_library_index()
    if book_id in self.saved_override_candidates_for_entry(
        entry, list_id, match_index['ids'], entry_key=entry_key):
      return 'saved/manual override'

    saved_resolution_by_id = getattr(
      self, '_import_list_review_auto_resolved_source_by_entry_id', {})
    resolved = saved_resolution_by_id.get(id(entry))
    processed_entry_ids = getattr(
      self, '_import_list_review_auto_processed_entry_ids', set())
    if resolved is None and id(entry) not in processed_entry_ids:
      saved_resolution = getattr(
        self, '_import_list_review_auto_resolved_source_by_entry_key', {})
      resolved = saved_resolution.get(entry_key_for_saved_match(entry))
    if resolved and book_id in resolved.get('book_ids', ()):
      return resolved.get('source', 'automatic')
    if id(entry) in processed_entry_ids:
      return 'manual find'

    groups = self.import_list_review_auto_candidates_for_entry(
      entry, match_index=match_index,
      requires_series_matching=requires_series_matching)
    if not groups and allow_goodreads_recovery:
      groups = self.import_list_review_auto_goodreads_candidates_for_entry(
        entry, match_index=match_index,
        requires_series_matching=requires_series_matching)
    resolved = import_list_review_auto_resolve_candidates({'entry': groups})
    group = resolved.get('entry')
    if group and book_id in group.get('book_ids', ()):
      return group.get('source', 'automatic')
    return 'manual find'

  def direct_match_candidates_for_entry(
      self, entry, by_title=None, by_series=None, authors=None, match_series=True):
    if by_title is None or by_series is None or authors is None:
      db = self.db.new_api
      ids = self.all_book_ids()
      titles = db.all_field_for('title', ids, default_value='')
      series = self.all_local_series_values(ids)
      authors = db.all_field_for('authors', ids, default_value='')
      by_title, by_series = self.import_match_indexes(ids, titles, series)

    title_candidates = []
    series_candidates = []
    for entry_key in self.import_entry_keys(entry):
      title_candidates.extend(by_title.get(entry_key, []))
      series_candidates.extend(by_series.get(entry_key, []))
    candidates = title_candidates + (series_candidates if match_series else [])
    candidates = list(OrderedDict((book_id, None) for book_id in candidates).keys())
    imported_author = imported_author_search_text(entry)
    return [
      book_id for book_id in candidates
      if self.author_matches(authors.get(book_id, ''), imported_author)
    ]

  def saved_override_candidates_for_entry(
      self, entry, list_id, ids, entry_key=''):
    if not list_id:
      return []
    overrides = self.saved_match_overrides(list_id)
    base_key = entry_key_for_saved_match(entry)
    override = overrides.get(entry_key or base_key)
    if override is None and entry_key and entry_key != base_key:
      override = overrides.get(base_key)
    if not override:
      return []
    return self.saved_override_book_ids(override, available_ids=ids)

  def saved_override_book_ids(self, override, available_ids=None):
    raw_book_ids = override.get('matched_book_ids')
    if raw_book_ids is None:
      raw_book_ids = [override.get('matched_book_id')]
    if not isinstance(raw_book_ids, (list, tuple)):
      raw_book_ids = [raw_book_ids]
    available_ids = set(available_ids) if available_ids is not None else None
    book_ids = []
    for raw_book_id in raw_book_ids:
      try:
        book_id = int(raw_book_id)
      except Exception:
        continue
      if (
          (available_ids is None or book_id in available_ids)
          and book_id not in book_ids):
        book_ids.append(book_id)
    return book_ids

  def matched_book_details(self, book_ids, titles, authors):
    details = []
    for book_id in book_ids or []:
      book_authors = authors.get(book_id, '')
      details.append({
        'matched_book_id': book_id,
        'matched_title': titles.get(book_id, '') or '',
        'matched_authors': book_authors or '',
      })
    return details

  def find_import_match_candidates(
      self, entry, title_mode=FIND_MODE_SIMILAR, author_mode=FIND_MODE_SIMILAR,
      title_soundex_length=FIND_MATCH_TITLE_SOUNDEX_LENGTH_DEFAULT,
      author_soundex_length=FIND_MATCH_AUTHOR_SOUNDEX_LENGTH_DEFAULT,
      excluded_book_ids=None, match_series=False):
    validate_find_match_modes(title_mode, author_mode)
    index = self.find_match_library_index(
      title_mode=title_mode,
      author_mode=author_mode,
      title_soundex_length=title_soundex_length,
      author_soundex_length=author_soundex_length,
      match_series=match_series)
    return self.find_import_match_candidates_from_index(
      entry, index, excluded_book_ids=excluded_book_ids)

  def find_match_library_index(
      self, title_mode=FIND_MODE_SIMILAR, author_mode=FIND_MODE_SIMILAR,
      title_soundex_length=FIND_MATCH_TITLE_SOUNDEX_LENGTH_DEFAULT,
      author_soundex_length=FIND_MATCH_AUTHOR_SOUNDEX_LENGTH_DEFAULT,
      match_series=False):
    validate_find_match_modes(title_mode, author_mode)
    db = self.db.new_api
    ids = self.all_book_ids()
    titles = db.all_field_for('title', ids, default_value='')
    authors = db.all_field_for('authors', ids, default_value='')
    try:
      series = self.all_local_series_values(ids)
    except Exception:
      series = {book_id: [] for book_id in ids}
    by_title = {}
    by_author = {}
    by_title_author = {}
    by_series_title = {}
    by_series_title_author = {}
    for book_id in ids:
      title_key = title_find_key(titles.get(book_id, ''), title_mode, title_soundex_length)
      author_keys = author_find_keys(authors.get(book_id, ''), author_mode, author_soundex_length)
      if title_mode != FIND_MODE_IGNORE and title_key:
        by_title.setdefault(title_key, []).append(book_id)
      if author_mode != FIND_MODE_IGNORE:
        for author_key in author_keys:
          by_author.setdefault(author_key, []).append(book_id)
      if (
          title_mode != FIND_MODE_IGNORE and author_mode != FIND_MODE_IGNORE
          and title_key):
        for author_key in author_keys:
          by_title_author.setdefault((title_key, author_key), []).append(book_id)
      if match_series and title_mode != FIND_MODE_IGNORE:
        for series_key in self.find_series_title_keys(
            series.get(book_id, []), title_mode, title_soundex_length):
          by_series_title.setdefault(series_key, []).append(book_id)
          if author_mode != FIND_MODE_IGNORE:
            for author_key in author_keys:
              by_series_title_author.setdefault((series_key, author_key), []).append(book_id)
    return {
      'title_mode': title_mode,
      'author_mode': author_mode,
      'title_soundex_length': title_soundex_length,
      'author_soundex_length': author_soundex_length,
      'match_series': bool(match_series),
      'ids': ids,
      'titles': titles,
      'authors': authors,
      'series': series,
      'by_title': by_title,
      'by_author': by_author,
      'by_title_author': by_title_author,
      'by_series_title': by_series_title,
      'by_series_title_author': by_series_title_author,
    }

  def find_series_title_keys(self, value, mode, soundex_length):
    if isinstance(value, str):
      values = [value] if value else []
    else:
      values = list(value or [])
    keys = []
    for series_value in values:
      candidates = [series_value]
      if mode != FIND_MODE_IDENTICAL:
        candidates.extend(series_match_keys(series_value))
      for candidate in candidates:
        key = title_find_key(candidate, mode, soundex_length)
        if key and key not in keys:
          keys.append(key)
    return keys

  def find_import_match_candidates_from_index(self, entry, index, excluded_book_ids=None):
    excluded_book_ids = set(excluded_book_ids or [])
    title_mode = index.get('title_mode', FIND_MODE_SIMILAR)
    author_mode = index.get('author_mode', FIND_MODE_SIMILAR)
    title_soundex_length = index.get(
      'title_soundex_length', FIND_MATCH_TITLE_SOUNDEX_LENGTH_DEFAULT)
    author_soundex_length = index.get(
      'author_soundex_length', FIND_MATCH_AUTHOR_SOUNDEX_LENGTH_DEFAULT)
    validate_find_match_modes(title_mode, author_mode)
    titles = index.get('titles') or {}
    authors = index.get('authors') or {}
    series = index.get('series') or {}
    match_series = bool(index.get('match_series'))
    entry_title_key = title_find_key(entry.get('title', ''), title_mode, title_soundex_length)
    entry_author_keys = author_find_keys(
      imported_author_list(entry), author_mode, author_soundex_length)
    if title_mode != FIND_MODE_IGNORE and not entry_title_key:
      return []
    if author_mode != FIND_MODE_IGNORE and not entry_author_keys:
      return []

    if title_mode == FIND_MODE_IGNORE:
      ids = []
      for entry_author_key in entry_author_keys:
        ids.extend(index.get('by_author', {}).get(entry_author_key, []))
    elif author_mode == FIND_MODE_IGNORE:
      title_ids = index.get('by_title', {}).get(entry_title_key, [])
      series_ids = (
        index.get('by_series_title', {}).get(entry_title_key, [])
        if match_series else [])
      ids = title_ids + series_ids
    else:
      title_ids = []
      series_ids = []
      for entry_author_key in entry_author_keys:
        title_ids.extend(
          index.get('by_title_author', {}).get((entry_title_key, entry_author_key), []))
        if match_series:
          series_ids.extend(
            index.get('by_series_title_author', {}).get(
              (entry_title_key, entry_author_key), []))
      ids = title_ids + series_ids
    title_id_set = set(index.get('by_title', {}).get(entry_title_key, []))
    series_id_set = set(
      index.get('by_series_title', {}).get(entry_title_key, [])
    ) if match_series else set()

    candidates = []
    for book_id in ids:
      if book_id in excluded_book_ids:
        continue
      title_matched = title_mode != FIND_MODE_IGNORE and book_id in title_id_set
      series_matched = title_mode != FIND_MODE_IGNORE and book_id in series_id_set
      author_matched = author_mode != FIND_MODE_IGNORE
      book_authors = authors.get(book_id, '')
      book_series = series.get(book_id, [])
      if isinstance(book_series, str):
        book_series = [book_series] if book_series else []
      candidates.append({
        'book_id': book_id,
        'matched_book_id': book_id,
        'title': titles.get(book_id, '') or '',
        'matched_title': titles.get(book_id, '') or '',
        'authors': book_authors or '',
        'matched_authors': book_authors or '',
        'series': list(book_series or []),
        'matched_series': list(book_series or []),
        'source': 'manual find',
        'reason': self.find_match_reason(
          title_mode, author_mode, title_matched, author_matched,
          series_matched=series_matched),
        'title_matched': bool(title_matched and title_mode != FIND_MODE_IGNORE),
        'series_matched': bool(series_matched and title_mode != FIND_MODE_IGNORE),
        'author_matched': bool(author_matched and author_mode != FIND_MODE_IGNORE),
      })
    return self.sorted_find_candidates(candidates)

  def find_match_reason(
      self, title_mode, author_mode, title_matched, author_matched,
      series_matched=False):
    parts = []
    if title_matched and title_mode != FIND_MODE_IGNORE:
      parts.append(f'title {title_mode}')
    if series_matched and title_mode != FIND_MODE_IGNORE:
      parts.append(f'series {title_mode}')
    if author_matched and author_mode != FIND_MODE_IGNORE:
      parts.append(f'author {author_mode}')
    return ', '.join(parts)

  def sorted_find_candidates(self, candidates):
    by_id = OrderedDict()
    for candidate in candidates or []:
      book_id = candidate.get('book_id', candidate.get('matched_book_id'))
      if book_id is None or book_id in by_id:
        continue
      candidate = dict(candidate)
      candidate['book_id'] = book_id
      candidate.setdefault('matched_book_id', book_id)
      by_id[book_id] = candidate
    return sorted(
      by_id.values(),
      key=lambda item: (
        0 if (
          (item.get('title_matched') or item.get('series_matched'))
          and item.get('author_matched')
        ) else 1,
        normalize_match_text(item.get('title') or item.get('matched_title') or ''),
        item.get('book_id'),
      ))

  def import_review_row(
      self, entry, entry_key='', matched=False, book_ids=None, matched_books=None,
      match_source='never matched', directive=None):
    book_ids = list(book_ids or [])
    matched_books = list(matched_books or [])
    previous_book_ids = []
    previous_books = []
    previous_match_source = ''
    ignored = False
    if directive:
      ignored = bool(directive.get('ignored'))
      previous_book_ids = list(directive.get('previous_matched_book_ids') or [])
      if not previous_book_ids and directive.get('previous_matched_book_id') is not None:
        previous_book_ids = [directive.get('previous_matched_book_id')]
      previous_books = list(directive.get('previous_matched_books') or [])
      previous_match_source = directive.get('previous_match_source', '')
    return {
      'entry': entry,
      'entry_key': entry_key or entry_key_for_saved_match(entry),
      'imported_position': entry.get('position', ''),
      'imported_title': entry.get('title', ''),
      'imported_author': imported_author_display_value(entry),
      'matched': bool(matched),
      'original_matched': bool(matched),
      'ignored': ignored,
      'original_ignored': ignored,
      'book_ids': book_ids,
      'original_book_ids': list(book_ids),
      'matched_books': matched_books,
      'original_matched_books': list(matched_books),
      'previous_book_ids': previous_book_ids,
      'previous_matched_books': previous_books,
      'previous_match_source': previous_match_source,
      'match_source': match_source,
      'original_match_source': match_source,
      'can_toggle_on': bool(matched or previous_book_ids or ignored),
    }

  def match_imported_entries(
      self, entries, match_series=True, list_id=None, allow_goodreads_recovery=True,
      return_details=False, award_winners_only=False,
      requires_series_matching=False):
    return self.match_imported_entries_for_list(
      entries,
      match_series=match_series,
      list_id=list_id,
      allow_goodreads_recovery=allow_goodreads_recovery,
      return_details=return_details,
      award_winners_only=award_winners_only,
      requires_series_matching=requires_series_matching)

  def match_imported_entries_for_list(
      self, entries, match_series=True, list_id=None, allow_goodreads_recovery=True,
      return_details=False, award_winners_only=False,
      requires_series_matching=False):
    """Prepare Import List Review with its isolated, conflict-aware matcher.

    Refactor warning:
    ``match_series`` remains a Find Match preference. It must not enable this
    automatic path; only ``requires_series_matching`` may do that.
    """
    match_index = self.import_list_review_auto_library_index()
    self._import_list_review_auto_match_index = match_index
    ids = match_index['ids']
    titles = match_index['titles']
    series = match_index['series']
    authors = match_index['authors']
    unmatched_overrides = self.saved_unmatched_overrides(list_id) if list_id else {}
    saved_overrides = self.saved_match_overrides(list_id) if list_id else {}
    self.debug_import_match_start(
      list_id, requires_series_matching, len(ids), len(entries),
      len(match_index['by_title_component']),
      len(match_index['by_exact_series']))

    states = []
    candidate_groups = {}
    base_entry_keys = [
      entry_key_for_saved_match(entry) for entry in entries
    ]
    base_entry_key_counts = {}
    for base_entry_key in base_entry_keys:
      base_entry_key_counts[base_entry_key] = (
        base_entry_key_counts.get(base_entry_key, 0) + 1)
    total_entries = len(entries)
    for entry_index, entry in enumerate(entries, start=1):
      row_key = entry_index - 1
      base_entry_key = base_entry_keys[row_key]
      saved_entry_key = entry_key_for_saved_match(
        entry, position_scoped=base_entry_key_counts.get(base_entry_key, 0) > 1)
      row = self.import_review_row(entry, entry_key=saved_entry_key)
      state = {
        'row_key': row_key,
        'entry': entry,
        'row': row,
        'saved_override': None,
        'saved_book_ids': [],
        'skip_auto': False,
      }
      states.append(state)
      self.update_import_match_progress(
        entry_index - 1,
        total_entries,
        f'Matching {entry_index} of {total_entries}: {entry.get("title", "")}')
      if award_winners_only and entry.get('result') and entry.get('result') != 'winner':
        state['skip_auto'] = True
        self.update_import_match_progress(
          entry_index,
          total_entries,
          f'Matched {entry_index} of {total_entries} recipe entries...')
        continue
      entry_titles = import_list_review_auto_entry_title_values(entry)
      if not entry_titles:
        self.debug_import_empty_entry(entry)
        state['skip_auto'] = True
        self.update_import_match_progress(
          entry_index,
          total_entries,
          f'Matched {entry_index} of {total_entries} recipe entries...')
        continue
      unmatched_override = unmatched_overrides.get(saved_entry_key)
      if unmatched_override is None and saved_entry_key != base_entry_key:
        unmatched_override = unmatched_overrides.get(base_entry_key)
      if unmatched_override:
        override_source = 'ignored' if unmatched_override.get('ignored') else 'explicit unmatched'
        row.update(self.import_review_row(
          entry, entry_key=saved_entry_key, match_source=override_source,
          directive=unmatched_override))
        state['skip_auto'] = True
        self.update_import_match_progress(
          entry_index,
          total_entries,
          f'Matched {entry_index} of {total_entries} recipe entries...')
        continue
      saved_override = saved_overrides.get(saved_entry_key)
      if saved_override is None and saved_entry_key != base_entry_key:
        saved_override = saved_overrides.get(base_entry_key)
      if saved_override is not None:
        state['saved_override'] = saved_override
        saved_book_ids = self.saved_override_book_ids(saved_override, available_ids=ids)
        state['saved_book_ids'] = saved_book_ids
        previous_book_ids = self.saved_override_book_ids(saved_override)
        previous_matched_books = list(saved_override.get('matched_books') or [])
        if not previous_matched_books and saved_override.get('matched_book_id') is not None:
          previous_matched_books = [{
            'matched_book_id': saved_override.get('matched_book_id'),
            'matched_title': saved_override.get('matched_title', ''),
            'matched_authors': saved_override.get('matched_authors', []),
          }]
        row['previous_book_ids'] = previous_book_ids
        row['previous_matched_books'] = previous_matched_books
        row['previous_match_source'] = 'saved/manual override'
        row['match_source'] = 'saved/manual override'
        row['original_match_source'] = 'saved/manual override'
        row['can_toggle_on'] = bool(saved_book_ids)
        self.debug_import_saved_override_lookup(entry, list_id, saved_book_ids)
        state['skip_auto'] = True
        self.update_import_match_progress(
          entry_index,
          total_entries,
          f'Matched {entry_index} of {total_entries} recipe entries...')
        continue

      groups = []
      if allow_goodreads_recovery:
        groups = self.import_list_review_auto_goodreads_id_candidates_for_entry(
          entry, match_index=match_index)
      if not groups:
        groups = self.import_list_review_auto_candidates_for_entry(
          entry, match_index=match_index,
          requires_series_matching=requires_series_matching)
      if not groups and allow_goodreads_recovery:
        self.update_import_match_step_progress(
          entry_index,
          total_entries,
          0.35,
          f'Checking Goodreads for {entry_index} of {total_entries}: {entry.get("title", "")}')
        progress = lambda fraction, message: self.update_import_match_step_progress(
          entry_index, total_entries, fraction, message)
        groups = self.import_list_review_auto_goodreads_candidates_for_entry(
          entry, match_index=match_index,
          requires_series_matching=requires_series_matching)
        progress(0.6, f'Checked Goodreads source for: {entry.get("title", "")}')
        self.debug_import_goodreads_candidates(entry, [
          book_id for group in groups for book_id in group.get('book_ids', ())
        ])
      candidate_groups[row_key] = groups
      self.debug_import_match_entry(entry, [
        book_id for group in groups for book_id in group.get('book_ids', ())
      ])
      self.update_import_match_progress(
        entry_index,
        total_entries,
        f'Matched {entry_index} of {total_entries} recipe entries...')

    reserved_book_ids = {
      book_id for state in states for book_id in state['saved_book_ids']
    }
    saved_owner_by_book_id = {}
    for state in states:
      for book_id in state['saved_book_ids']:
        previous_state = saved_owner_by_book_id.get(book_id)
        if (
            previous_state is None
            or imported_entry_preferred(state['entry'], previous_state['entry'])):
          saved_owner_by_book_id[book_id] = state

    resolved_groups = import_list_review_auto_resolve_candidates(
      candidate_groups, reserved_book_ids=reserved_book_ids)
    self._import_list_review_auto_resolved_source_by_entry_id = {
      id(states[row_key]['entry']): group
      for row_key, group in resolved_groups.items()
    }
    self._import_list_review_auto_processed_entry_ids = {
      id(state['entry']) for state in states
    }
    self._import_list_review_auto_resolved_source_by_entry_key = {
      entry_key_for_saved_match(states[row_key]['entry']): group
      for row_key, group in resolved_groups.items()
    }

    matched = OrderedDict()
    for state in states:
      entry = state['entry']
      row = state['row']
      selected_book_ids = []
      source = row.get('match_source', '')
      if state['saved_override'] is not None:
        selected_book_ids = [
          book_id for book_id in state['saved_book_ids']
          if saved_owner_by_book_id.get(book_id) is state
        ]
        source = 'saved/manual override'
      elif not state['skip_auto']:
        group = resolved_groups.get(state['row_key'])
        if group is not None:
          selected_book_ids = list(group.get('book_ids', ()))
          source = group.get('source', 'automatic')

      if selected_book_ids:
        row['book_ids'] = list(selected_book_ids)
        row['matched_books'] = self.matched_book_details(
          selected_book_ids, titles, authors)
        row['matched'] = True
        row['original_matched'] = True
        row['original_book_ids'] = list(selected_book_ids)
        row['original_matched_books'] = list(row['matched_books'])
        row['match_source'] = source
        row['original_match_source'] = source
        row['can_toggle_on'] = True
        for book_id in selected_book_ids:
          matched[book_id] = entry.get('position', '')
          self.debug_import_matched_book(source, book_id, entry, titles, series)

    review_rows = [state['row'] for state in states]
    missing_entries = [
      state['entry'] for state in states if not state['row'].get('matched')
    ]
    if return_details:
      return matched, missing_entries, review_rows
    return matched, missing_entries
