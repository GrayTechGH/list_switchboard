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
from collections import OrderedDict

from calibre.ebooks.metadata import title_sort


SERIES_SUFFIX_WORDS = frozenset([
  'cycle', 'saga', 'series', 'trilogy', 'universe', 'world'
])
RELAXED_MATCH_MIN_NON_INITIAL_CHARS = 6


def normalize_key(name):
  return clean_name(name).casefold()


POSITION_SUFFIX = re.compile(r'^(.*?)\s*\[([0-9]+(?:\.[0-9]+)?)\]\s*$')


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


def title_sort_without_article(value):
  value = clean_name(value)
  if not value:
    return ''
  try:
    sorted_value = title_sort(value)
  except Exception:
    return ''
  if ',' in sorted_value:
    sorted_value = sorted_value.rsplit(',', 1)[0]
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

  def match_imported_entries(self, entries, match_series=True):
    db = self.db.new_api
    ids = self.all_book_ids()
    titles = db.all_field_for('title', ids, default_value='')
    series = self.all_local_series_values(ids)
    authors = db.all_field_for('authors', ids, default_value='')

    by_title = {}
    by_series = {}
    for book_id in ids:
      for title_key in match_keys(titles.get(book_id, '')):
        by_title.setdefault(title_key, []).append(book_id)
      for series_value in series.get(book_id, []):
        for series_key in series_match_keys(series_value):
          by_series.setdefault(series_key, []).append(book_id)

    matched = OrderedDict()
    missing_entries = []
    total_entries = len(entries)
    for entry_index, entry in enumerate(entries, start=1):
      self.update_import_match_progress(
        entry_index - 1,
        total_entries,
        f'Matching {entry_index} of {total_entries}: {entry.get("title", "")}')
      entry_keys = self.import_entry_keys(entry)
      if not entry_keys:
        self.debug_import_empty_entry(entry)
        missing_entries.append(entry)
        self.update_import_match_progress(
          entry_index,
          total_entries,
          f'Matched {entry_index} of {total_entries} recipe entries...')
        continue
      title_candidates = []
      series_candidates = []
      for entry_key in entry_keys:
        title_candidates.extend(by_title.get(entry_key, []))
        series_candidates.extend(by_series.get(entry_key, []))
      candidates = title_candidates + (series_candidates if match_series else [])
      candidates = list(OrderedDict((book_id, None) for book_id in candidates).keys())
      self.debug_import_match_entry(entry, candidates)
      entry_matched = False
      if match_series:
        series_candidates = list(OrderedDict(
          (book_id, None) for book_id in series_candidates).keys())
        for book_id in series_candidates:
          if book_id in matched:
            continue
          if self.author_matches(authors.get(book_id, ''), entry.get('author', '')):
            matched[book_id] = entry.get('position', '')
            entry_matched = True
            self.debug_import_matched_book('matched', book_id, entry, titles, series)
      if not entry_matched:
        title_candidates = list(OrderedDict(
          (book_id, None) for book_id in title_candidates).keys())
        for book_id in title_candidates:
          if book_id in matched:
            continue
          if self.author_matches(authors.get(book_id, ''), entry.get('author', '')):
            matched[book_id] = entry.get('position', '')
            entry_matched = True
            self.debug_import_matched_book('matched', book_id, entry, titles, series)
            break
      if not entry_matched:
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
            continue
          matched[book_id] = entry.get('position', '')
          entry_matched = True
          self.debug_import_matched_book('Goodreads matched', book_id, entry, titles, series)
      if not entry_matched:
        missing_entries.append(entry)
      self.update_import_match_progress(
        entry_index,
        total_entries,
        f'Matched {entry_index} of {total_entries} recipe entries...')
    return matched, missing_entries

  def match_deep_recovery_entries(self, entries, excluded_book_ids=None, match_series=True):
    excluded_book_ids = set(excluded_book_ids or [])
    db = self.db.new_api
    ids = self.all_book_ids()
    titles = db.all_field_for('title', ids, default_value='')
    series = self.all_local_series_values(ids)
    authors = db.all_field_for('authors', ids, default_value='')

    by_title = {}
    by_series = {}
    for book_id in ids:
      for title_key in match_keys(titles.get(book_id, '')):
        by_title.setdefault(title_key, []).append(book_id)
      for series_value in series.get(book_id, []):
        for series_key in series_match_keys(series_value):
          by_series.setdefault(series_key, []).append(book_id)

    matched = OrderedDict()
    missing_entries = []
    total_entries = len(entries)
    for entry_index, entry in enumerate(entries, start=1):
      self.update_import_match_step_progress(
        entry_index,
        total_entries,
        0.2,
        f'Deep Recovery {entry_index} of {total_entries}: {entry.get("title", "")}')
      progress = lambda fraction, message: self.update_import_match_step_progress(
        entry_index, total_entries, fraction, message)
      candidates = self.goodreads_recovery_candidates(
        entry, ids, titles, series, authors, by_title, by_series, progress,
        excluded_book_ids=excluded_book_ids,
        match_series=match_series)
      self.debug_import_goodreads_candidates(entry, candidates)
      entry_matched = False
      for book_id in candidates:
        if book_id in matched or book_id in excluded_book_ids:
          continue
        matched[book_id] = entry.get('position', '')
        entry_matched = True
        self.debug_import_matched_book('Deep Recovery matched', book_id, entry, titles, series)
      if not entry_matched:
        missing_entries.append(entry)
      self.update_import_match_progress(
        entry_index,
        total_entries,
        f'Deep Recovery checked {entry_index} of {total_entries} recipe entries...')
    return matched, missing_entries

  def goodreads_recovery_candidates(
      self, entry, ids, titles, series, authors, by_title, by_series, progress=None,
      excluded_book_ids=None, match_series=True):
    excluded_book_ids = set(excluded_book_ids or [])
    source_candidates = self.goodreads_source_recovery_candidates_for_match(
      entry, titles, series, authors, by_title, by_series,
      match_series=match_series)
    source_candidates = [
      book_id for book_id in source_candidates
      if book_id not in excluded_book_ids
    ]
    if progress is not None:
      progress(0.6, f'Checked Goodreads source for: {entry.get("title", "")}')
    if source_candidates:
      return source_candidates

    if not match_series:
      return []

    entry_keys = self.import_entry_keys(entry)
    relaxed_entry_keys = set()
    for key in entry_keys:
      relaxed_entry_keys.update(series_match_keys(key))
    relaxed_entry_keys.discard('')
    if not relaxed_entry_keys:
      return []
    candidates = []
    candidate_ids = []
    for book_id in ids:
      if book_id in excluded_book_ids:
        continue
      if not self.author_matches(authors.get(book_id, ''), entry.get('author', '')):
        continue
      goodreads_id = self.goodreads_id_for_book(book_id)
      if not goodreads_id:
        continue
      candidate_ids.append((book_id, goodreads_id))

    total_candidates = max(len(candidate_ids), 1)
    for lookup_index, (book_id, goodreads_id) in enumerate(candidate_ids, start=1):
      if progress is not None:
        fraction = 0.6 + (0.35 * (float(lookup_index - 1) / total_candidates))
        progress(
          fraction,
          f'Checking Goodreads book {lookup_index} of {total_candidates}: {entry.get("title", "")}')
      series_names = self.fetch_goodreads_series_names(goodreads_id)
      for series_name in series_names:
        keys = set(series_match_keys(series_name))
        if keys & relaxed_entry_keys:
          candidates.append(book_id)
          break
    if progress is not None:
      progress(0.95, f'Finished Goodreads checks for: {entry.get("title", "")}')
    return candidates

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
    data = self.fetch_goodreads_source_data(entry.get('source_url', ''))
    candidates = []
    if match_series:
      for series_name in data.get('series_names', []):
        keys = set(series_match_keys(series_name))
        for key in keys:
          candidates.extend(by_series.get(key, []))
    for source_book in data.get('books', []):
      for title_key in match_keys(source_book.get('title', '')):
        for book_id in by_title.get(title_key, []):
          source_author = source_book.get('author', '') or entry.get('author', '')
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
