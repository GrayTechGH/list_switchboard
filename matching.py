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


def entry_key_for_saved_match(entry):
  return '|'.join([
    normalize_match_text(entry.get('title', '')),
    imported_author_key(entry),
  ])


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

  def review_match_source_for_candidate(
      self, entry, book_id, list_id=None, match_series=True, allow_goodreads_recovery=True):
    if book_id is None:
      return 'manual find'
    db = self.db.new_api
    ids = self.all_book_ids()
    titles = db.all_field_for('title', ids, default_value='')
    series = self.all_local_series_values(ids)
    authors = db.all_field_for('authors', ids, default_value='')
    by_title, by_series = self.import_match_indexes(ids, titles, series)

    if book_id in self.saved_override_candidates_for_entry(entry, list_id, ids):
      return 'saved/manual override'
    if book_id in self.direct_match_candidates_for_entry(
        entry, by_title=by_title, by_series=by_series, authors=authors,
        match_series=match_series):
      return 'automatic'
    if allow_goodreads_recovery and book_id in self.goodreads_source_recovery_candidates_for_match(
        entry, titles, series, authors, by_title, by_series, match_series=match_series):
      return 'Goodreads/deep recovery'
    return 'manual find'

  def saved_override_candidates_for_entry(self, entry, list_id, ids):
    if not list_id:
      return []
    overrides = self.saved_match_overrides(list_id)
    override = overrides.get(entry_key_for_saved_match(entry))
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
      return_details=False, award_winners_only=False):
    return self.match_imported_entries_for_list(
      entries,
      match_series=match_series,
      list_id=list_id,
      allow_goodreads_recovery=allow_goodreads_recovery,
      return_details=return_details,
      award_winners_only=award_winners_only)

  def match_imported_entries_for_list(
      self, entries, match_series=True, list_id=None, allow_goodreads_recovery=True,
      return_details=False, award_winners_only=False):
    db = self.db.new_api
    ids = self.all_book_ids()
    titles = db.all_field_for('title', ids, default_value='')
    series = self.all_local_series_values(ids)
    authors = db.all_field_for('authors', ids, default_value='')
    by_title, by_series = self.import_match_indexes(ids, titles, series)
    unmatched_overrides = self.saved_unmatched_overrides(list_id) if list_id else {}
    saved_overrides = self.saved_match_overrides(list_id) if list_id else {}
    self.debug_import_match_start(
      list_id, match_series, len(ids), len(entries), len(by_title), len(by_series))

    matched = OrderedDict()
    matched_entries = {}
    matched_sources = {}
    review_rows = []
    rows_by_entry_id = {}
    missing_entries = []
    total_entries = len(entries)
    for entry_index, entry in enumerate(entries, start=1):
      row = self.import_review_row(entry)
      review_rows.append(row)
      rows_by_entry_id[id(entry)] = row
      self.update_import_match_progress(
        entry_index - 1,
        total_entries,
        f'Matching {entry_index} of {total_entries}: {entry.get("title", "")}')
      if award_winners_only and entry.get('result') and entry.get('result') != 'winner':
        missing_entries.append(entry)
        self.update_import_match_progress(
          entry_index,
          total_entries,
          f'Matched {entry_index} of {total_entries} recipe entries...')
        continue
      entry_keys = self.import_entry_keys(entry)
      if not entry_keys:
        self.debug_import_empty_entry(entry)
        missing_entries.append(entry)
        self.update_import_match_progress(
          entry_index,
          total_entries,
          f'Matched {entry_index} of {total_entries} recipe entries...')
        continue
      saved_entry_key = entry_key_for_saved_match(entry)
      unmatched_override = unmatched_overrides.get(saved_entry_key)
      if unmatched_override:
        override_source = 'ignored' if unmatched_override.get('ignored') else 'explicit unmatched'
        row.update(self.import_review_row(
          entry, entry_key=saved_entry_key, match_source=override_source,
          directive=unmatched_override))
        missing_entries.append(entry)
        self.update_import_match_progress(
          entry_index,
          total_entries,
          f'Matched {entry_index} of {total_entries} recipe entries...')
        continue
      saved_override = saved_overrides.get(saved_entry_key)
      authoritative_override = saved_override is not None
      title_candidates = []
      series_candidates = []
      for entry_key in entry_keys:
        title_candidates.extend(by_title.get(entry_key, []))
        series_candidates.extend(by_series.get(entry_key, []))
      candidates = title_candidates + (series_candidates if match_series else [])
      candidates = list(OrderedDict((book_id, None) for book_id in candidates).keys())
      imported_author = imported_author_search_text(entry)
      author_candidates = [
        book_id for book_id in candidates
        if self.author_matches(authors.get(book_id, ''), imported_author)
      ]
      already_matched = [book_id for book_id in candidates if book_id in matched]
      self.debug_import_match_entry_detail(
        entry_index, total_entries, entry, entry_keys,
        list(OrderedDict((book_id, None) for book_id in title_candidates).keys()),
        list(OrderedDict((book_id, None) for book_id in series_candidates).keys()),
        candidates, author_candidates, already_matched)
      self.debug_import_match_entry(entry, candidates)
      entry_matched = False

      def remember_match(book_id, source):
        previous_entry = matched_entries.get(book_id)
        if previous_entry is not None and previous_entry is not entry:
          previous_row = rows_by_entry_id.get(id(previous_entry))
          if previous_row is not None and book_id in previous_row.get('book_ids', []):
            previous_row['book_ids'] = [
              existing_id for existing_id in previous_row.get('book_ids', [])
              if existing_id != book_id
            ]
            previous_row['matched_books'] = [
              book for book in previous_row.get('matched_books', [])
              if book.get('matched_book_id') != book_id
            ]
            previous_row['matched'] = bool(previous_row.get('book_ids'))
            previous_row['original_matched'] = bool(previous_row.get('book_ids'))
            if not previous_row['matched'] and previous_entry not in missing_entries:
              missing_entries.append(previous_entry)
        if book_id not in row['book_ids']:
          row['book_ids'].append(book_id)
          row['matched_books'] = self.matched_book_details(row['book_ids'], titles, authors)
        row['matched'] = True
        row['original_matched'] = True
        row['original_book_ids'] = list(row['book_ids'])
        row['original_matched_books'] = list(row['matched_books'])
        row['match_source'] = source
        row['original_match_source'] = source
        row['can_toggle_on'] = True
        matched_sources[book_id] = source

      if authoritative_override:
        saved_book_ids = self.saved_override_book_ids(saved_override, available_ids=ids)
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
        for book_id in saved_book_ids:
          if book_id in matched:
            previous_source = matched_sources.get(book_id)
            if (
                previous_source != 'saved/manual override'
                or imported_entry_preferred(entry, matched_entries.get(book_id))):
              matched[book_id] = entry.get('position', '')
              remember_match(book_id, 'saved/manual override')
              matched_entries[book_id] = entry
              self.debug_import_matched_book(
                'replaced duplicate saved override match', book_id, entry, titles, series)
              entry_matched = True
            self.debug_import_candidate_rejected(
              'saved override already matched', book_id, entry, titles, authors)
            continue
          matched[book_id] = entry.get('position', '')
          matched_entries[book_id] = entry
          remember_match(book_id, 'saved/manual override')
          entry_matched = True
          self.debug_import_matched_book(
            'saved override matched', book_id, entry, titles, series)

      if not authoritative_override and match_series:
        series_candidates = list(OrderedDict(
          (book_id, None) for book_id in series_candidates).keys())
        for book_id in series_candidates:
          if book_id in matched:
            if matched_sources.get(book_id) == 'saved/manual override':
              self.debug_import_candidate_rejected(
                'authoritative saved override already matched',
                book_id, entry, titles, authors)
              continue
            if imported_entry_preferred(entry, matched_entries.get(book_id)):
              matched[book_id] = entry.get('position', '')
              remember_match(book_id, 'automatic')
              matched_entries[book_id] = entry
              entry_matched = True
              self.debug_import_matched_book('replaced duplicate match', book_id, entry, titles, series)
            self.debug_import_candidate_rejected('already matched', book_id, entry, titles, authors)
            continue
          if self.author_matches(authors.get(book_id, ''), imported_author):
            matched[book_id] = entry.get('position', '')
            matched_entries[book_id] = entry
            remember_match(book_id, 'automatic')
            entry_matched = True
            self.debug_import_matched_book('matched', book_id, entry, titles, series)
          else:
            self.debug_import_candidate_rejected('author mismatch', book_id, entry, titles, authors)
      if not authoritative_override and not entry_matched:
        title_candidates = list(OrderedDict(
          (book_id, None) for book_id in title_candidates).keys())
        for book_id in title_candidates:
          if book_id in matched:
            if matched_sources.get(book_id) == 'saved/manual override':
              self.debug_import_candidate_rejected(
                'authoritative saved override already matched',
                book_id, entry, titles, authors)
              continue
            if imported_entry_preferred(entry, matched_entries.get(book_id)):
              matched[book_id] = entry.get('position', '')
              remember_match(book_id, 'automatic')
              matched_entries[book_id] = entry
              entry_matched = True
              self.debug_import_matched_book('replaced duplicate match', book_id, entry, titles, series)
            self.debug_import_candidate_rejected('already matched', book_id, entry, titles, authors)
            continue
          if self.author_matches(authors.get(book_id, ''), imported_author):
            matched[book_id] = entry.get('position', '')
            matched_entries[book_id] = entry
            remember_match(book_id, 'automatic')
            entry_matched = True
            self.debug_import_matched_book('matched', book_id, entry, titles, series)
            break
          self.debug_import_candidate_rejected('author mismatch', book_id, entry, titles, authors)
      if not authoritative_override and not entry_matched and allow_goodreads_recovery:
        self.update_import_match_step_progress(
          entry_index,
          total_entries,
          0.35,
          f'Checking Goodreads for {entry_index} of {total_entries}: {entry.get("title", "")}')
        progress = lambda fraction, message: self.update_import_match_step_progress(
          entry_index, total_entries, fraction, message)
        goodreads_candidates = self.goodreads_source_recovery_candidates_for_match(
          entry, titles, series, authors, by_title, by_series,
          match_series=match_series)
        progress(0.6, f'Checked Goodreads source for: {entry.get("title", "")}')
        self.debug_import_goodreads_candidates(entry, goodreads_candidates)
        for book_id in goodreads_candidates:
          if book_id in matched:
            if matched_sources.get(book_id) == 'saved/manual override':
              self.debug_import_candidate_rejected(
                'authoritative saved override already matched',
                book_id, entry, titles, authors)
              continue
            if imported_entry_preferred(entry, matched_entries.get(book_id)):
              matched[book_id] = entry.get('position', '')
              remember_match(book_id, 'Goodreads/deep recovery')
              matched_entries[book_id] = entry
              entry_matched = True
              self.debug_import_matched_book('replaced duplicate Goodreads match', book_id, entry, titles, series)
            continue
          matched[book_id] = entry.get('position', '')
          matched_entries[book_id] = entry
          remember_match(book_id, 'Goodreads/deep recovery')
          entry_matched = True
          self.debug_import_matched_book('Goodreads matched', book_id, entry, titles, series)
      if not entry_matched:
        missing_entries.append(entry)
      self.update_import_match_progress(
        entry_index,
        total_entries,
        f'Matched {entry_index} of {total_entries} recipe entries...')
    review_rows = [
      row for row in review_rows
      if row.get('matched') or row.get('ignored')
      or row.get('entry') in missing_entries
    ]
    if return_details:
      return matched, missing_entries, review_rows
    return matched, missing_entries

  def goodreads_source_recovery_candidates_for_match(
      self, entry, titles, series, authors, by_title, by_series, match_series=True):
    try:
      return self.goodreads_source_recovery_candidates(
        entry, titles, series, authors, by_title, by_series,
        match_series=match_series)
    except TypeError as err:
      if 'match_series' not in str(err):
        raise
      return self.goodreads_source_recovery_candidates(
        entry, titles, series, authors, by_title, by_series) if match_series else []

  def goodreads_source_recovery_candidates(
      self, entry, titles, series, authors, by_title, by_series, match_series=True):
    entry_source_url = imported_entry_source_url(entry)
    data = self.fetch_goodreads_source_data(entry_source_url)
    source_goodreads_id = goodreads_book_id_from_url(entry_source_url)
    if source_goodreads_id:
      exact_ids = [
        book_id for book_id in titles
        if self.goodreads_id_for_book(book_id) == source_goodreads_id
      ]
      if exact_ids:
        self.debug_import_goodreads_source_candidates(entry, data, exact_ids)
        return exact_ids

    candidates = []
    if match_series and not source_goodreads_id:
      for series_name in data.get('series_names', []):
        keys = set(series_match_keys(series_name))
        for key in keys:
          candidates.extend(by_series.get(key, []))
    for source_book in data.get('books', []):
      if source_goodreads_id and not self.source_book_matches_entry(source_book, entry):
        continue
      for title_key in match_keys(source_book.get('title', '')):
        for book_id in by_title.get(title_key, []):
          source_author = source_book.get('author', '') or imported_author_search_text(entry)
          if self.author_matches(authors.get(book_id, ''), source_author):
            candidates.append(book_id)

    deduped = []
    seen = set()
    for book_id in candidates:
      if book_id not in seen:
        seen.add(book_id)
        deduped.append(book_id)
    self.debug_import_goodreads_source_candidates(entry, data, deduped)
    return deduped

  def source_book_matches_entry(self, source_book, entry):
    source_keys = set(match_keys(source_book.get('title', '')))
    entry_keys = set(self.import_entry_keys(entry))
    return bool(source_keys & entry_keys)
