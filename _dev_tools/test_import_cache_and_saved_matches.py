#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path


if globals().get('__file__') and __file__ != '<string>':
  ROOT = Path(__file__).resolve().parents[1]
else:
  ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))


qt = types.ModuleType('qt')
qt_core = types.ModuleType('qt.core')
qt_core.QDialog = type('QDialog', (), {'Accepted': 1})
sys.modules.setdefault('qt', qt)
sys.modules.setdefault('qt.core', qt_core)

calibre = types.ModuleType('calibre')
calibre_constants = types.ModuleType('calibre.constants')
calibre_constants.config_dir = None
calibre_ebooks = types.ModuleType('calibre.ebooks')
calibre_ebooks_metadata = types.ModuleType('calibre.ebooks.metadata')
calibre_ebooks_metadata.title_sort = lambda value: (
  value[4:] + ', The' if str(value).startswith('The ') else str(value))
sys.modules.setdefault('calibre', calibre)
sys.modules.setdefault('calibre.constants', calibre_constants)
sys.modules.setdefault('calibre.ebooks', calibre_ebooks)
sys.modules.setdefault('calibre.ebooks.metadata', calibre_ebooks_metadata)


import storage
from _dev_tools import generate_import_caches


class FakeStorage(storage.StorageMixin):

  def __init__(self, root):
    self._storage_root = root
    self.status_messages = []
    self.invalidated = []

  def status_message(self, message):
    self.status_messages.append(message)

  def invalidate_cached_active_add_import_map(self, list_id):
    self.invalidated.append(list_id)


class FakeFetcher:

  def __init__(self, source_id, name, url, parsed=None, error=None):
    self.source_id = source_id
    self.NAME = name
    self.URL = url
    self._parsed = parsed or {'name': name, 'entries': []}
    self._error = error
    self.calls = 0

  def fetch_and_parse(self, fetch_source, **_kwargs):
    self.calls += 1
    if self._error is not None:
      raise self._error
    fetched = fetch_source(self.URL)
    parsed = dict(self._parsed)
    parsed.setdefault('source_url', self.URL)
    parsed.setdefault('notes', [])
    parsed['fetched_body'] = fetched
    return parsed


class StorageHelpersTest(unittest.TestCase):

  def test_safe_list_id_normalizes_names(self):
    self.assertEqual(
      'crime_writers_of_canada_best_novel',
      storage.safe_list_id('Crime Writers of Canada: Best Novel'))

  def test_build_import_cache_data_uses_recipe_metadata(self):
    recipe = types.SimpleNamespace(
      NAME='Example Award',
      URL='https://example.com/award',
      source_id='example_award')
    parsed = {
      'name': 'Example Award',
      'entries': [{'position': '1', 'title': 'Book', 'author': 'Author'}],
      'notes': ['note'],
      'match_series': False,
      'source_revision': 'rev-1',
    }

    data = storage.build_import_cache_data('Example Award', parsed, recipe=recipe)

    self.assertEqual('example_award', data['list_id'])
    self.assertEqual('Example Award', data['list_name'])
    self.assertEqual('https://example.com/award', data['source_url'])
    self.assertEqual('example_award', data['parser'])
    self.assertEqual(False, data['match_series'])
    self.assertEqual('rev-1', data['append_state']['source_revision'])

  def test_repaired_translator_credit_entry_repairs_stale_cache_shape(self):
    repaired = storage.repaired_translator_credit_entry({
      'title': 'Solaris, Stanislaw Lem',
      'author': 'translated by Bill Johnston',
    })

    self.assertEqual('Solaris', repaired['title'])
    self.assertEqual('Stanislaw Lem', repaired['author'])


class StorageMixinTest(unittest.TestCase):

  def setUp(self):
    self.temp_dir = tempfile.mkdtemp()
    self.mixin = FakeStorage(self.temp_dir)

  def tearDown(self):
    shutil.rmtree(self.temp_dir)

  def test_write_and_read_import_cache_round_trip(self):
    parsed = {
      'name': 'Example List',
      'entries': [{'position': '1', 'title': 'Book', 'author': 'Author'}],
      'notes': ['cached'],
    }

    written = self.mixin.write_import_cache('Example List', parsed)
    loaded = self.mixin.read_import_cache('Example List')

    self.assertEqual(written['list_id'], loaded['list_id'])
    self.assertEqual('Example List', loaded['list_name'])
    self.assertEqual(['cached'], loaded['notes'])
    self.assertEqual(['example_list'], self.mixin.invalidated)

  def test_import_cache_for_active_list_matches_list_name(self):
    self.mixin.write_import_cache('Example List', {
      'name': 'Example List',
      'entries': [{'position': '1', 'title': 'Book', 'author': 'Author'}],
    })

    loaded = self.mixin.import_cache_for_active_list('example list')

    self.assertEqual('example_list', loaded['list_id'])

  def test_cached_import_to_parsed_repairs_entries(self):
    cache = self.mixin.write_import_cache('Example List', {
      'name': 'Example List',
      'entries': [{
        'position': '1',
        'title': 'Solaris, Stanislaw Lem',
        'author': 'translated by Bill Johnston',
      }],
      'notes': ['cached'],
    })

    parsed = self.mixin.cached_import_to_parsed(cache)

    self.assertEqual('Solaris', parsed['entries'][0]['title'])
    self.assertEqual('Stanislaw Lem', parsed['entries'][0]['author'])
    self.assertEqual(True, parsed['from_cache'])

  def test_merge_append_import_cache_appends_when_prefix_matches(self):
    old_cache = self.mixin.write_import_cache('Example List', {
      'name': 'Example List',
      'entries': [{'position': '1', 'title': 'Book 1', 'author': 'Author'}],
    })
    merged = self.mixin.merge_append_import_cache('Example List', old_cache, {
      'name': 'Example List',
      'entries': [
        {'position': '1', 'title': 'Book 1', 'author': 'Author'},
        {'position': '2', 'title': 'Book 2', 'author': 'Author'},
      ],
    })

    self.assertEqual(2, len(merged['entries']))
    self.assertEqual('Book 2', merged['entries'][1]['title'])

  def test_merge_append_import_cache_replaces_when_prefix_changes(self):
    old_cache = self.mixin.write_import_cache('Example List', {
      'name': 'Example List',
      'entries': [{'position': '1', 'title': 'Old', 'author': 'Author'}],
    })
    merged = self.mixin.merge_append_import_cache('Example List', old_cache, {
      'name': 'Example List',
      'entries': [{'position': '1', 'title': 'New', 'author': 'Author'}],
    })

    self.assertEqual('New', merged['entries'][0]['title'])

  def test_write_and_read_match_cache_round_trip(self):
    self.mixin.write_match_cache('Example List', [{
      'entry_key': 'book|author',
      'matched_book_id': 7,
    }])

    loaded = self.mixin.read_match_cache('Example List')

    self.assertEqual('example_list', loaded['list_id'])
    self.assertEqual(7, loaded['matches'][0]['matched_book_id'])

  def test_saved_match_overrides_skip_unmatched_rows(self):
    self.mixin.write_match_cache('Example List', [
      {'entry_key': 'book|author', 'matched_book_id': 7},
      {'entry_key': 'book2|author2', 'matched_book_id': 8, 'unmatched': True},
    ])

    overrides = self.mixin.saved_match_overrides('Example List')

    self.assertEqual(['book|author'], sorted(overrides))

  def test_saved_unmatched_overrides_only_include_unmatched_rows(self):
    self.mixin.write_match_cache('Example List', [
      {'entry_key': 'book|author', 'matched_book_id': 7},
      {'entry_key': 'book2|author2', 'matched_book_id': 8, 'unmatched': True},
    ])

    overrides = self.mixin.saved_unmatched_overrides('Example List')

    self.assertEqual(['book2|author2'], sorted(overrides))

  def test_apply_import_review_match_changes_saves_explicit_unmatched(self):
    rows = [{
      'entry': {'title': 'Book', 'author': 'Author', 'position': '1'},
      'entry_key': 'book|author',
      'matched': False,
      'original_matched': True,
      'book_ids': [],
      'original_book_ids': [7],
      'matched_books': [],
      'original_matched_books': [],
      'match_source': 'automatic',
      'original_match_source': 'automatic',
    }]

    result = self.mixin.apply_import_review_match_changes('Example List', rows)
    loaded = self.mixin.read_match_cache('Example List')

    self.assertEqual(1, result['saved_unmatched'])
    self.assertEqual(True, loaded['matches'][0]['unmatched'])

  def test_apply_import_review_match_changes_removes_explicit_unmatched_when_reenabled(self):
    self.mixin.write_match_cache('Example List', [{
      'entry_key': 'book|author',
      'unmatched': True,
      'previous_matched_book_id': 7,
    }])
    rows = [{
      'entry': {'title': 'Book', 'author': 'Author', 'position': '1'},
      'entry_key': 'book|author',
      'matched': True,
      'original_matched': False,
      'book_ids': [7],
      'original_book_ids': [],
      'matched_books': [],
      'original_matched_books': [],
      'match_source': 'explicit unmatched',
      'original_match_source': 'explicit unmatched',
    }]

    result = self.mixin.apply_import_review_match_changes('Example List', rows)
    loaded = self.mixin.read_match_cache('Example List')

    self.assertEqual(1, result['removed'])
    self.assertEqual([], loaded['matches'])


class GenerateImportCachesTest(unittest.TestCase):

  def setUp(self):
    self.temp_dir = tempfile.mkdtemp()

  def tearDown(self):
    shutil.rmtree(self.temp_dir)

  def test_recipe_matches_source_id_and_name(self):
    fetcher = FakeFetcher('example_award', 'Example Award', 'source-a')

    self.assertTrue(generate_import_caches.recipe_matches(fetcher, ['example_award']))
    self.assertTrue(generate_import_caches.recipe_matches(fetcher, ['Example Award']))
    self.assertFalse(generate_import_caches.recipe_matches(fetcher, ['Other Award']))

  def test_generate_import_caches_writes_expected_filename_and_schema(self):
    fetcher = FakeFetcher(
      'example_award',
      'Example Award',
      'source-a',
      parsed={'name': 'Example Award', 'entries': [{'position': '1', 'title': 'Book', 'author': 'Author'}]})

    results, failures, _cache = generate_import_caches.generate_import_caches(
      [fetcher],
      self.temp_dir,
      load_source=lambda source: f'html:{source}',
      emit=lambda *_args: None)

    self.assertEqual([], failures)
    self.assertEqual('written', results[0]['status'])
    output_path = Path(self.temp_dir) / 'import_example_award.json'
    self.assertTrue(output_path.exists())
    written = json.loads(output_path.read_text(encoding='utf-8'))
    self.assertEqual('example_award', written['list_id'])
    self.assertEqual('Example Award', written['list_name'])
    self.assertEqual('source-a', written['source_url'])

  def test_generate_import_caches_memoizes_shared_sources(self):
    fetcher_a = FakeFetcher('award_a', 'Award A', 'shared-source')
    fetcher_b = FakeFetcher('award_b', 'Award B', 'shared-source')
    calls = []

    def load_source(source):
      calls.append(source)
      return f'html:{source}'

    results, failures, cache = generate_import_caches.generate_import_caches(
      [fetcher_a, fetcher_b],
      self.temp_dir,
      load_source=load_source,
      emit=lambda *_args: None)

    self.assertEqual([], failures)
    self.assertEqual(2, len(results))
    self.assertEqual(['shared-source'], calls)
    self.assertEqual({'shared-source': 'html:shared-source'}, cache)

  def test_generate_import_caches_respects_recipe_filters(self):
    fetcher_a = FakeFetcher('award_a', 'Award A', 'source-a')
    fetcher_b = FakeFetcher('award_b', 'Award B', 'source-b')

    results, failures, _cache = generate_import_caches.generate_import_caches(
      [fetcher_a, fetcher_b],
      self.temp_dir,
      recipe_filters=['award_b'],
      load_source=lambda source: f'html:{source}',
      emit=lambda *_args: None)

    self.assertEqual([], failures)
    self.assertEqual(1, len(results))
    self.assertEqual('Award B', results[0]['fetcher'].NAME)

  def test_generate_import_caches_skips_existing_file_without_force(self):
    output_path = Path(self.temp_dir) / 'import_example_award.json'
    output_path.write_text('{}\n', encoding='utf-8')
    fetcher = FakeFetcher('example_award', 'Example Award', 'source-a')

    results, failures, _cache = generate_import_caches.generate_import_caches(
      [fetcher],
      self.temp_dir,
      load_source=lambda source: f'html:{source}',
      emit=lambda *_args: None)

    self.assertEqual([], failures)
    self.assertEqual('skipped', results[0]['status'])
    self.assertEqual(0, fetcher.calls)

  def test_generate_import_caches_force_overwrites_existing_file(self):
    output_path = Path(self.temp_dir) / 'import_example_award.json'
    output_path.write_text('{"old": true}\n', encoding='utf-8')
    fetcher = FakeFetcher(
      'example_award',
      'Example Award',
      'source-a',
      parsed={'name': 'Example Award', 'entries': [{'position': '1', 'title': 'Book', 'author': 'Author'}]})

    results, failures, _cache = generate_import_caches.generate_import_caches(
      [fetcher],
      self.temp_dir,
      force=True,
      load_source=lambda source: f'html:{source}',
      emit=lambda *_args: None)

    self.assertEqual([], failures)
    self.assertEqual('written', results[0]['status'])
    self.assertEqual(1, fetcher.calls)
    written = json.loads(output_path.read_text(encoding='utf-8'))
    self.assertIn('entries', written)

  def test_generate_import_caches_collects_failures_when_not_fail_fast(self):
    bad = FakeFetcher('bad_award', 'Bad Award', 'bad-source', error=RuntimeError('boom'))
    good = FakeFetcher('good_award', 'Good Award', 'good-source')

    results, failures, _cache = generate_import_caches.generate_import_caches(
      [bad, good],
      self.temp_dir,
      load_source=lambda source: f'html:{source}',
      emit=lambda *_args: None)

    self.assertEqual(1, len(failures))
    self.assertEqual('Good Award', results[0]['fetcher'].NAME)

  def test_generate_import_caches_fail_fast_raises(self):
    bad = FakeFetcher('bad_award', 'Bad Award', 'bad-source', error=RuntimeError('boom'))

    with self.assertRaises(RuntimeError):
      generate_import_caches.generate_import_caches(
        [bad],
        self.temp_dir,
        fail_fast=True,
        load_source=lambda source: f'html:{source}',
        emit=lambda *_args: None)


if __name__ == '__main__':
  unittest.main()
