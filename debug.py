#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Debug logging helpers for subsystem mixins.

Maintenance notes:
- Debug helpers are intentionally centralized so feature modules can log without
  importing each other.
- Section names are persisted in prefs['debug_sections']; changing keys is a
  settings migration, not a local rename.
- Logging must stay side-effect-light. These helpers should not repair state or
  trigger UI dialogs.
"""

import traceback

from calibre_plugins.list_switchboard.config import prefs


DEBUG_SECTIONS = (
  ('general', 'General'),
  ('metadata', 'Metadata state and cleanup'),
  ('selection', 'Book selection and series expansion'),
  ('writes', 'Metadata writes'),
  ('recipe', 'Recipe fetch and parsed output'),
  ('fallback', 'Fallback activity only'),
  ('import', 'Import matching and report'),
  ('goodreads', 'Goodreads lookups'),
  ('errors', 'Exceptions and tracebacks'),
)


class DebugMixin:
  """
  Provides structured debug logging by stable section key.

  Type constraints:
  - prefs must behave like Calibre's JSONConfig mapping.
  - Callers may pass arbitrary objects; format inside f-strings only at the call
    site where context is known.

  Refactor warning:
  - Keep debug_exception() gated by debug_enabled('errors') to avoid printing
    tracebacks unless the user opted into error logging.
  """

  def debug_enabled(self, section='general'):
    if prefs.get('debug_logging', False):
      return True
    sections = prefs.get('debug_sections', {}) or {}
    return bool(sections.get(section, False))

  def debug_log(self, message, section='general'):
    if not self.debug_enabled(section):
      return
    print(f'List Switchboard [{section}]: {message}', flush=True)

  def debug_log_preview(self, label, text, limit=3000, section='general'):
    if not self.debug_enabled(section):
      return
    text = (text or '').replace('\r', '\\r').replace('\n', '\\n')
    if len(text) > limit:
      text = f'{text[:limit]}... <truncated {len(text) - limit} chars>'
    self.debug_log(f'{label}: {text}', section=section)

  def debug_metadata_helper_failed(self, field, err):
    self.debug_log(
      f'could not resolve series index field via Calibre helper for {field}: {err}',
      section='metadata')

  def debug_metadata_no_series_index_field(self, field):
    self.debug_log(f'no readable series index field found for {field}', section='metadata')

  def debug_metadata_formatted_read_failed(self, field, book_id, err):
    self.debug_log(
      f'formatted field read failed field={field} book_id={book_id}: {err}',
      section='metadata')

  def debug_metadata_preflight_store(self, book_id, raw_active, formatted_active, index_field, position):
    self.debug_log(
      f'preflight store book_id={book_id} raw_active={raw_active} '
      f'formatted_active={formatted_active} index_field={index_field} position={position}',
      section='metadata')

  def debug_metadata_library_state(self, active_field, stored_field):
    self.debug_log(
      f'configured fields active={active_field} stored={stored_field}',
      section='metadata')

  def debug_metadata_counts(self, active_counts, stored_names):
    self.debug_log(
      f'active counts={dict(active_counts)} stored={list(stored_names.values())}',
      section='metadata')

  def debug_metadata_repair_skipped(self):
    self.debug_log(
      'missing stored position repair skipped; no series index field',
      section='metadata')

  def debug_metadata_repaired_position(self, book_id, name, position):
    self.debug_log(
      f'repaired stored list position book_id={book_id} list={name} position={position}',
      section='metadata')

  def debug_selection_ids(self, ids):
    self.debug_log(f'selected book ids={ids}', section='selection')

  def debug_selection_expanded_series(self, ids, expanded):
    self.debug_log(f'expanded ids {ids} to series ids {sorted(expanded)}', section='selection')

  def debug_writes_store_active(self, book_id, active, raw_active, formatted_active, position):
    self.debug_log(
      f'storing active list book_id={book_id} active={active} raw_active={raw_active} '
      f'formatted_active={formatted_active} position={position}', section='writes')

  def debug_writes_active_field(self, count):
    self.debug_log(
      f'writing active field={prefs["active_list_field"]} count={count}',
      section='writes')

  def debug_writes_stored_field(self, count):
    self.debug_log(
      f'writing stored field={prefs["stored_lists_field"]} count={count}',
      section='writes')

  def debug_writes_finished(self, active_updates, stored_updates, changed):
    self.debug_log(
      f'wrote active_count={len(active_updates or {})} stored_count={len(stored_updates or {})} '
      f'changed_count={len(changed)}', section='writes')

  def debug_writes_active_series_field(self, field, label, active_updates, index_updates):
    self.debug_log(
      f'writing active series field={field} label={label} count={len(active_updates)} '
      f'index_count={len(index_updates or {})}', section='writes')

  def debug_recipe_start(self, recipe):
    self.debug_log(f'import recipe={recipe.NAME} url={recipe.URL}', section='recipe')

  def debug_recipe_fetch_url(self, url):
    self.debug_log(f'import fetch url={url}', section='recipe')

  def debug_recipe_fetched(self, url, html):
    self.debug_log(f'import fetched bytes={len(html)} from {url}', section='recipe')
    self.debug_log_preview('import fetched preview', html, section='recipe')

  def debug_recipe_failed(self, url, err):
    self.debug_log(f'recipe fetch/parse failed for {url}: {err}', section='recipe')

  def debug_fallback_urls(self, url, urls):
    self.debug_log(f'fallback fetch urls for {url}: {urls}', section='fallback')

  def debug_fallback_urllib_fetch(self, url):
    self.debug_log(f'fallback urllib fetch url={url}', section='fallback')

  def debug_recipe_linked_page_failed(self, url, err, entry):
    title = entry.get('title', '') if entry else ''
    self.debug_log(
      f'recipe linked page failed title={title} url={url}: {err}',
      section='recipe')

  def debug_parser_message(self, message):
    self.debug_log(message, section='recipe')

  def debug_recipe_output(self, parsed):
    entries = parsed.get('entries') or []
    self.debug_log(
      f'recipe output name={parsed.get("name", "")} url={parsed.get("url", "")} entries={len(entries)}',
      section='recipe')
    for index, entry in enumerate(entries[:25], start=1):
      self.debug_log(f'recipe entry {index}: {entry}', section='recipe')
    if len(entries) > 25:
      self.debug_log(
        f'recipe entry log truncated; {len(entries) - 25} additional entries',
        section='recipe')

  def debug_import_target(self, list_name, active):
    self.debug_log(f'import target list={list_name} current active={active}', section='import')

  def debug_import_summary(self, matched, missing_entries, entries):
    self.debug_log(
      f'import matched books={len(matched)} missing entries={len(missing_entries)} '
      f'of entries={len(entries)}', section='import')

  def debug_import_missing_entries(self, missing_entries):
    for index, entry in enumerate(missing_entries[:50], start=1):
      self.debug_log(f'import missing entry {index}: {entry}', section='import')
    if len(missing_entries) > 50:
      self.debug_log(
        f'import missing entry log truncated; {len(missing_entries) - 50} additional entries',
        section='import')

  def debug_import_empty_entry(self, entry):
    self.debug_log(f'import skipped empty title entry={entry}', section='import')

  def debug_import_match_entry(self, entry, candidates):
    self.debug_log(
      f'import match entry position={entry.get("position", "")} title={entry.get("title", "")} '
      f'aliases={entry.get("aliases", [])} author={entry.get("author", "")} candidates={candidates}',
      section='import')

  def debug_import_matched_book(self, label, book_id, entry, titles, series):
    self.debug_log(
      f'import {label} book_id={book_id} position={entry.get("position", "")} '
      f'title={titles.get(book_id, "")} series={series.get(book_id, "")}',
      section='import')

  def debug_exception(self):
    if not self.debug_enabled('errors'):
      return
    self.debug_log('exception', section='errors')
    for line in traceback.format_exc().rstrip().splitlines():
      self.debug_log(line, section='errors')

  def debug_general_status_message(self, message):
    self.debug_log(message, section='general')
