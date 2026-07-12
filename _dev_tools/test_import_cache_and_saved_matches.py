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


class Dummy:
  Accepted = 1

  def __init__(self, *args, **kwargs):
    pass

  def __getattr__(self, _name):
    return Dummy()

  def __call__(self, *args, **kwargs):
    return Dummy()


class FakeQUrl:

  def __init__(self, value=''):
    self.value = value

  def __str__(self):
    return str(self.value)


qt = types.ModuleType('qt')
qt_core = types.ModuleType('qt.core')
for name in (
    'QApplication', 'QButtonGroup', 'QCheckBox', 'QComboBox', 'QDialog',
    'QDialogButtonBox', 'QGridLayout', 'QGroupBox', 'QHBoxLayout',
    'QHeaderView', 'QInputDialog', 'QLabel', 'QLineEdit', 'QListWidget',
    'QMessageBox', 'QProgressDialog', 'QPushButton', 'QRadioButton',
    'QSizePolicy', 'QSpinBox', 'QTableWidget', 'QTableWidgetItem',
    'QVBoxLayout'):
  setattr(qt_core, name, Dummy)
qt_core.QUrl = FakeQUrl
qt_core.Qt = types.SimpleNamespace(
  AlignmentFlag=types.SimpleNamespace(AlignLeft=0))
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

  def __getattr__(self, name):
    if name.startswith('debug_storage_'):
      return lambda *_args, **_kwargs: None
    raise AttributeError(name)


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
    parsed.setdefault('source', {
      'url': self.URL,
      'name': self.NAME,
      'source_id': self.source_id,
    })
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
      'entries': [{'position': '1', 'title': 'Book', 'authors': ['Author']}],
      'notes': ['note'],
      'match_series': False,
      'source_revision': 'rev-1',
    }

    data = storage.build_import_cache_data('Example Award', parsed, recipe=recipe)

    self.assertEqual('example_award', data['list_id'])
    self.assertEqual(2, data['schema_version'])
    self.assertEqual('Example Award', data['list_name'])
    self.assertEqual({
      'url': 'https://example.com/award',
      'name': 'Example Award',
      'source_id': 'example_award',
    }, data['source'])
    self.assertEqual('example_award', data['parser'])
    self.assertEqual(False, data['match_series'])
    self.assertEqual('rev-1', data['append_state']['source_revision'])
    self.assertEqual(['Author'], data['entries'][0]['authors'])
    self.assertNotIn('author', data['entries'][0])

  def test_build_import_cache_data_omits_entry_source_matching_list_source(self):
    recipe = types.SimpleNamespace(
      NAME='Example Award',
      URL='https://example.com/award',
      source_id='example_award')
    data = storage.build_import_cache_data('Example Award', {
      'name': 'Example Award',
      'source': {'url': 'https://example.com/award'},
      'entries': [{
        'position': '1',
        'title': 'Book',
        'authors': ['Author'],
        'source': {'url': 'https://example.com/award'},
      }],
    }, recipe=recipe)

    self.assertNotIn('source', data['entries'][0])

  def test_build_import_cache_data_keeps_different_entry_source(self):
    recipe = types.SimpleNamespace(
      NAME='Example Award',
      URL='https://example.com/award',
      source_id='example_award')
    data = storage.build_import_cache_data('Example Award', {
      'name': 'Example Award',
      'source': {'url': 'https://example.com/award'},
      'entries': [{
        'position': '1',
        'title': 'Book',
        'authors': ['Author One', 'Author Two'],
        'source': {'url': 'https://example.com/book'},
      }],
    }, recipe=recipe)

    self.assertEqual(['Author One', 'Author Two'], data['entries'][0]['authors'])
    self.assertEqual({'url': 'https://example.com/book', 'name': '', 'source_id': ''},
                     data['entries'][0]['source'])

  def test_build_import_cache_data_preserves_incremental_page_state(self):
    data = storage.build_import_cache_data('Example List', {
      'entries': [],
      'incremental_state': {
        'pending_page_urls': ['https://example.com/current-year'],
      },
    })

    self.assertEqual(
      ['https://example.com/current-year'],
      data['incremental_state']['pending_page_urls'])

class StorageMixinTest(unittest.TestCase):

  def setUp(self):
    self.temp_dir = tempfile.mkdtemp()
    self.mixin = FakeStorage(self.temp_dir)

  def tearDown(self):
    shutil.rmtree(self.temp_dir)

  def test_write_and_read_import_cache_round_trip(self):
    parsed = {
      'name': 'Example List',
      'entries': [{'position': '1', 'title': 'Book', 'authors': ['Author']}],
      'notes': ['cached'],
    }

    written = self.mixin.write_import_cache('Example List', parsed)
    loaded = self.mixin.read_import_cache('Example List')

    self.assertEqual(written['list_id'], loaded['list_id'])
    self.assertEqual(2, loaded['schema_version'])
    self.assertEqual('Example List', loaded['list_name'])
    self.assertEqual(['cached'], loaded['notes'])
    self.assertEqual(['Author'], loaded['entries'][0]['authors'])
    self.assertNotIn('author', written['entries'][0])
    self.assertEqual(['example_list'], self.mixin.invalidated)

  def test_atomic_cache_writes_preserve_previous_import_and_match_data(self):
    self.mixin.write_import_cache('Example List', {
      'name': 'Example List',
      'entries': [{'position': '1', 'title': 'Original import', 'authors': ['Author']}],
    })
    self.mixin.write_match_cache('Example List', [{
      'entry_key': 'original import|author', 'matched_book_id': 7,
    }])
    original_replace = storage.os.replace

    def fail_replace(_source, _destination):
      raise OSError('simulated interrupted replace')

    storage.os.replace = fail_replace
    try:
      with self.assertRaises(storage.ListSwitchboardError):
        self.mixin.write_import_cache('Example List', {
          'name': 'Example List',
          'entries': [{'position': '1', 'title': 'Replacement import', 'authors': ['Author']}],
        })
      with self.assertRaises(storage.ListSwitchboardError):
        self.mixin.write_match_cache('Example List', [{
          'entry_key': 'replacement import|author', 'matched_book_id': 8,
        }])
    finally:
      storage.os.replace = original_replace

    self.assertEqual('Original import', self.mixin.read_import_cache('Example List')['entries'][0]['title'])
    self.assertEqual(7, self.mixin.read_match_cache('Example List')['matches'][0]['matched_book_id'])
    self.assertEqual([], list(Path(self.temp_dir).glob('*.tmp')))

  def test_invalid_cache_files_are_preserved_and_warned_once(self):
    import_path = Path(self.temp_dir) / 'import_example_list.json'
    match_path = Path(self.temp_dir) / 'match_example_list.json'
    import_path.write_text('{not valid json', encoding='utf-8')
    match_path.write_text('[not an object]', encoding='utf-8')

    self.assertIsNone(self.mixin.read_import_cache('Example List'))
    self.assertIsNone(self.mixin.read_import_cache('Example List'))
    self.assertEqual([], self.mixin.read_match_cache('Example List')['matches'])
    self.assertEqual([], self.mixin.read_match_cache('Example List')['matches'])

    self.assertTrue(import_path.exists())
    self.assertTrue(match_path.exists())
    self.assertEqual(2, len(self.mixin.status_messages))
    self.assertTrue(any('import cache "example_list"' in message for message in self.mixin.status_messages))
    self.assertTrue(any('saved matches "example_list"' in message for message in self.mixin.status_messages))
    self.assertTrue(all(self.temp_dir not in message for message in self.mixin.status_messages))

  def test_read_import_cache_rejects_v1_author_cache(self):
    path = Path(self.temp_dir) / 'import_example_list.json'
    path.write_text(json.dumps({
      'schema_version': 1,
      'list_id': 'example_list',
      'list_name': 'Example List',
      'source_url': 'https://example.com/list',
      'entries': [{
        'position': '1',
        'title': 'Book',
        'author': 'Author',
        'source_url': 'https://example.com/book',
      }],
      'notes': ['legacy'],
      'match_series': False,
    }), encoding='utf-8')

    loaded = self.mixin.read_import_cache('Example List')

    self.assertIsNone(loaded)

  def test_import_cache_for_active_list_matches_list_name(self):
    self.mixin.write_import_cache('Example List', {
      'name': 'Example List',
      'entries': [{'position': '1', 'title': 'Book', 'authors': ['Author']}],
    })

    loaded = self.mixin.import_cache_for_active_list('example list')

    self.assertEqual('example_list', loaded['list_id'])

  def test_cached_import_to_parsed_keeps_schema2_entries(self):
    cache = self.mixin.write_import_cache('Example List', {
      'name': 'Example List',
      'entries': [{
        'position': '1',
        'title': 'Solaris',
        'authors': ['Stanislaw Lem'],
      }],
      'notes': ['cached'],
    })

    parsed = self.mixin.cached_import_to_parsed(cache)

    self.assertEqual('Solaris', parsed['entries'][0]['title'])
    self.assertEqual(['Stanislaw Lem'], parsed['entries'][0]['authors'])
    self.assertNotIn('source_url', parsed)
    self.assertEqual(True, parsed['from_cache'])

  def test_merge_append_import_cache_appends_when_prefix_matches(self):
    old_cache = self.mixin.write_import_cache('Example List', {
      'name': 'Example List',
      'entries': [{'position': '1', 'title': 'Book 1', 'authors': ['Author']}],
    })
    merged = self.mixin.merge_append_import_cache('Example List', old_cache, {
      'name': 'Example List',
      'entries': [
        {'position': '1', 'title': 'Book 1', 'authors': ['Author']},
        {'position': '2', 'title': 'Book 2', 'authors': ['Author']},
      ],
    })

    self.assertEqual(2, len(merged['entries']))
    self.assertEqual('Book 2', merged['entries'][1]['title'])

  def test_merge_append_import_cache_replaces_when_prefix_changes(self):
    old_cache = self.mixin.write_import_cache('Example List', {
      'name': 'Example List',
      'entries': [{'position': '1', 'title': 'Old', 'authors': ['Author']}],
    })
    merged = self.mixin.merge_append_import_cache('Example List', old_cache, {
      'name': 'Example List',
      'entries': [{'position': '1', 'title': 'New', 'authors': ['Author']}],
    })

    self.assertEqual('New', merged['entries'][0]['title'])

  def test_merge_append_import_cache_replaces_changed_prefix_metadata(self):
    old_cache = self.mixin.write_import_cache('Example Award', {
      'name': 'Example Award',
      'entries': [{
        'position': '2026.01',
        'title': 'Book',
        'authors': ['Author'],
        'result': 'shortlisted',
        'source': {'url': 'https://example.com/shortlist'},
        'aliases': ['Book: A Novel'],
      }],
    })
    refreshed = self.mixin.merge_append_import_cache('Example Award', old_cache, {
      'name': 'Example Award',
      'entries': [
        {
          'position': '2026',
          'title': 'Book',
          'authors': ['Author'],
          'result': 'winner',
          'source': {'url': 'https://example.com/winner'},
          'aliases': ['Book: The Winner'],
        },
        {'position': '2025', 'title': 'Older Book', 'authors': ['Another Author']},
      ],
    })

    self.assertEqual(2, len(refreshed['entries']))
    self.assertEqual('2026', refreshed['entries'][0]['position'])
    self.assertEqual('winner', refreshed['entries'][0]['result'])
    self.assertEqual(['Book: The Winner'], refreshed['entries'][0]['aliases'])
    self.assertEqual(
      {'url': 'https://example.com/winner', 'name': '', 'source_id': ''},
      refreshed['entries'][0]['source'])

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

  def test_saved_unmatched_overrides_include_ignored_rows(self):
    self.mixin.write_match_cache('Example List', [
      {'entry_key': 'book|author', 'matched_book_id': 7, 'ignored': True},
      {'entry_key': 'book2|author2', 'matched_book_id': 8},
    ])

    overrides = self.mixin.saved_unmatched_overrides('Example List')

    self.assertEqual(['book|author'], sorted(overrides))

  def test_apply_import_review_match_changes_saves_explicit_unmatched(self):
    rows = [{
      'entry': {'title': 'Book', 'authors': ['Author'], 'position': '1'},
      'entry_key': 'book|author',
      'matched': False,
      'ignored': True,
      'original_matched': True,
      'original_ignored': False,
      'book_ids': [],
      'original_book_ids': [7],
      'matched_books': [],
      'original_matched_books': [],
      'previous_book_ids': [7],
      'previous_matched_books': [],
      'previous_match_source': 'automatic',
      'match_source': 'ignored',
      'original_match_source': 'automatic',
    }]

    result = self.mixin.apply_import_review_match_changes('Example List', rows)
    loaded = self.mixin.read_match_cache('Example List')

    self.assertEqual(1, result['saved_unmatched'])
    self.assertEqual(True, loaded['matches'][0]['ignored'])
    self.assertEqual(True, loaded['matches'][0]['unmatched'])

  def test_apply_import_review_match_changes_saves_none_state(self):
    rows = [{
      'entry': {'title': 'Book', 'authors': ['Author'], 'position': '1'},
      'entry_key': 'book|author',
      'matched': False,
      'ignored': False,
      'original_matched': True,
      'original_ignored': False,
      'book_ids': [],
      'original_book_ids': [7],
      'matched_books': [],
      'original_matched_books': [],
      'previous_book_ids': [7],
      'previous_matched_books': [],
      'previous_match_source': 'automatic',
      'match_source': 'never matched',
      'original_match_source': 'automatic',
    }]

    result = self.mixin.apply_import_review_match_changes('Example List', rows)
    loaded = self.mixin.read_match_cache('Example List')

    self.assertEqual(1, result['saved_unmatched'])
    self.assertEqual(1, len(loaded['matches']))
    self.assertEqual(True, loaded['matches'][0]['unmatched'])
    self.assertNotIn('ignored', loaded['matches'][0])
    self.assertEqual([7], loaded['matches'][0]['previous_matched_book_ids'])
    self.assertEqual('automatic', loaded['matches'][0]['previous_match_source'])

  def test_apply_import_review_match_changes_saves_none_when_saved_match_removed(self):
    self.mixin.write_match_cache('Example List', [{
      'entry_key': 'book|author',
      'matched_book_id': 7,
    }])
    rows = [{
      'entry': {'title': 'Book', 'authors': ['Author'], 'position': '1'},
      'entry_key': 'book|author',
      'matched': False,
      'ignored': False,
      'original_matched': True,
      'original_ignored': False,
      'book_ids': [],
      'original_book_ids': [7],
      'matched_books': [],
      'original_matched_books': [],
      'previous_book_ids': [7],
      'previous_matched_books': [],
      'previous_match_source': 'saved/manual override',
      'match_source': 'never matched',
      'original_match_source': 'saved/manual override',
    }]

    result = self.mixin.apply_import_review_match_changes('Example List', rows)
    loaded = self.mixin.read_match_cache('Example List')

    self.assertEqual(1, result['saved_unmatched'])
    self.assertEqual(0, result['removed'])
    self.assertEqual(1, len(loaded['matches']))
    self.assertEqual(True, loaded['matches'][0]['unmatched'])
    self.assertNotIn('ignored', loaded['matches'][0])
    self.assertEqual([7], loaded['matches'][0]['previous_matched_book_ids'])
    self.assertEqual('saved/manual override', loaded['matches'][0]['previous_match_source'])

  def test_apply_import_review_match_changes_saves_active_manual_edit(self):
    class FakeApi:
      def field_for(self, field, book_id, default_value=''):
        if field == 'title':
          return {7: 'Book'}.get(book_id, default_value)
        if field == 'authors':
          return {7: ['Author']}.get(book_id, default_value)
        return default_value

    class FakeDb:
      new_api = FakeApi()

    self.mixin.db = FakeDb()
    rows = [{
      'entry': {'title': 'Book', 'authors': ['Author'], 'position': '2'},
      'entry_key': 'book|author',
      'matched': True,
      'ignored': False,
      'original_matched': False,
      'original_ignored': False,
      'book_ids': [7],
      'original_book_ids': [],
      'matched_books': [{
        'matched_book_id': 7,
        'matched_title': 'Book',
        'matched_authors': 'Author',
      }],
      'original_matched_books': [],
      'previous_book_ids': [],
      'previous_matched_books': [],
      'previous_match_source': '',
      'match_source': 'active list/manual edit',
      'original_match_source': 'never matched',
    }]

    result = self.mixin.apply_import_review_match_changes('Example List', rows)
    loaded = self.mixin.read_match_cache('Example List')

    self.assertEqual(0, result['removed'])
    self.assertEqual(7, loaded['matches'][0]['matched_book_id'])
    self.assertEqual([7], loaded['matches'][0]['matched_book_ids'])

  def test_apply_import_review_match_changes_replaces_manual_selection_exactly(self):
    class FakeApi:
      def field_for(self, field, book_id, default_value=''):
        if field == 'title':
          return {7: 'Volume One', 8: 'Volume Two'}.get(book_id, default_value)
        if field == 'authors':
          return {7: ['Author'], 8: ['Author']}.get(book_id, default_value)
        return default_value

    class FakeDb:
      new_api = FakeApi()

    self.mixin.db = FakeDb()
    self.mixin.write_match_cache('Example List', [{
      'entry_key': 'shared saga|author',
      'matched_book_id': 7,
      'matched_book_ids': [7, 8, 9],
      'matched_books': [
        {'matched_book_id': 7},
        {'matched_book_id': 8},
        {'matched_book_id': 9},
      ],
    }])
    rows = [{
      'entry': {'title': 'Shared Saga', 'authors': ['Author'], 'position': '2'},
      'entry_key': 'shared saga|author',
      'matched': True,
      'ignored': False,
      'original_matched': False,
      'original_ignored': False,
      'book_ids': [7, 8],
      'original_book_ids': [],
      'matched_books': [],
      'original_matched_books': [],
      'previous_book_ids': [7, 8, 9],
      'previous_matched_books': [],
      'previous_match_source': 'saved/manual override',
      'match_source': 'manual find',
      'original_match_source': 'explicit unmatched',
    }]

    self.mixin.apply_import_review_match_changes('Example List', rows)
    item = self.mixin.read_match_cache('Example List')['matches'][0]

    self.assertEqual([7, 8], item['matched_book_ids'])
    self.assertEqual([7, 8], [book['matched_book_id'] for book in item['matched_books']])
    self.assertNotIn(9, item['matched_book_ids'])

  def test_apply_import_review_match_changes_converts_ignored_to_none(self):
    self.mixin.write_match_cache('Example List', [{
      'entry_key': 'book|author',
      'ignored': True,
      'unmatched': True,
      'previous_matched_book_id': 7,
    }])
    rows = [{
      'entry': {'title': 'Book', 'authors': ['Author'], 'position': '1'},
      'entry_key': 'book|author',
      'matched': False,
      'ignored': False,
      'original_matched': False,
      'original_ignored': True,
      'book_ids': [],
      'original_book_ids': [],
      'matched_books': [],
      'original_matched_books': [],
      'previous_book_ids': [7],
      'previous_matched_books': [],
      'previous_match_source': 'automatic',
      'match_source': 'never matched',
      'original_match_source': 'ignored',
    }]

    result = self.mixin.apply_import_review_match_changes('Example List', rows)
    loaded = self.mixin.read_match_cache('Example List')

    self.assertEqual(0, result['removed'])
    self.assertEqual(1, len(loaded['matches']))
    self.assertEqual(True, loaded['matches'][0]['unmatched'])
    self.assertNotIn('ignored', loaded['matches'][0])
    self.assertEqual([7], loaded['matches'][0]['previous_matched_book_ids'])

  def test_apply_import_review_match_changes_removes_explicit_unmatched_when_reenabled(self):
    self.mixin.write_match_cache('Example List', [{
      'entry_key': 'book|author',
      'ignored': True,
      'unmatched': True,
      'previous_matched_book_id': 7,
    }])
    rows = [{
      'entry': {'title': 'Book', 'authors': ['Author'], 'position': '1'},
      'entry_key': 'book|author',
      'matched': True,
      'ignored': False,
      'original_matched': False,
      'original_ignored': True,
      'book_ids': [7],
      'original_book_ids': [],
      'matched_books': [],
      'original_matched_books': [],
      'previous_book_ids': [7],
      'previous_matched_books': [],
      'previous_match_source': 'automatic',
      'match_source': 'automatic',
      'original_match_source': 'ignored',
    }]

    result = self.mixin.apply_import_review_match_changes('Example List', rows)
    loaded = self.mixin.read_match_cache('Example List')

    self.assertEqual(1, result['removed'])
    self.assertEqual([], loaded['matches'])

  def configure_save_active_matches_fixture(self):
    class FakeApi:
      def field_for(self, field, book_id, default_value=''):
        if field == 'title':
          return {1: 'Book One', 2: 'Book Two'}.get(book_id, default_value)
        if field == 'authors':
          return {1: ['Author One'], 2: ['Author Two']}.get(book_id, default_value)
        return default_value

      def all_field_for(self, field, ids, default_value=''):
        return {book_id: self.field_for(field, book_id, default_value) for book_id in ids}

    class FakeDb:
      new_api = FakeApi()

    self.mixin.db = FakeDb()
    self.mixin.gui = None
    self.mixin.ensure_configured = lambda: True
    self.mixin.all_book_ids = lambda: [1, 2]
    self.mixin.all_local_series_values = lambda _ids: {1: [], 2: []}
    self.mixin.import_match_indexes = lambda _ids, _titles, _series: ({}, {})
    self.mixin.active_series_index_field = lambda: None
    self.mixin.active_book_ids_for_list = lambda _list_name: [1, 2]
    self.mixin.active_list_field_key = lambda: '#active'
    self.mixin.read_field = lambda _field, _book_id: ''
    self.mixin.read_position_display = lambda _field, _book_id, _fallback: ('1', 1.0)
    self.mixin.normalized_position_text = lambda position: str(position or '').strip()
    self.mixin.author_matches = lambda *_args: False
    self.mixin.direct_match_candidates_for_entry = lambda *_args, **_kwargs: []
    self.mixin.write_import_cache('Example List', {
      'name': 'Example List',
      'entries': [
        {'position': '1', 'title': 'Book One Imported', 'authors': ['Author One']},
        {'position': '1', 'title': 'Book Two Imported', 'authors': ['Author Two']},
      ],
      'match_series': True,
    })
    return types.SimpleNamespace(
      NAME='Example List',
      URL='https://example.com/list',
      source_id='example_list')

  def test_save_active_matches_duplicate_position_skip_continues(self):
    recipe = self.configure_save_active_matches_fixture()
    calls = []

    def chooser(book_id, _position, entries, _db):
      calls.append(book_id)
      if book_id == 1:
        return None
      return entries[1]

    self.mixin._saved_match_entry_chooser = chooser

    self.mixin.save_active_matches_for_recipe(recipe)

    loaded = self.mixin.read_match_cache('Example List')
    self.assertEqual([1, 2], calls)
    self.assertEqual(1, len(loaded['matches']))
    self.assertEqual('book two imported|author two', loaded['matches'][0]['entry_key'])
    self.assertEqual(2, loaded['matches'][0]['matched_book_id'])

  def test_save_active_matches_duplicate_position_uses_series_direct_match(self):
    recipe = self.configure_save_active_matches_fixture()
    self.mixin.write_import_cache('Example List', {
      'name': 'Example List',
      'entries': [
        {'position': '1', 'title': 'Series One', 'authors': ['Author One']},
        {'position': '1', 'title': 'Other Series', 'authors': ['Other Author']},
      ],
      'match_series': True,
    })
    self.mixin.active_book_ids_for_list = lambda _list_name: [1]
    self.mixin.all_local_series_values = lambda _ids: {1: ['Series One']}
    self.mixin.author_matches = lambda book_authors, imported_author: imported_author in ' '.join(book_authors)
    self.mixin.direct_match_candidates_for_entry = (
      lambda entry, **_kwargs: [1] if entry.get('title') == 'Series One' else [])
    self.mixin._saved_match_entry_chooser = lambda *_args: self.fail(
      'exact series match should not require duplicate-position prompting')

    self.mixin.save_active_matches_for_recipe(recipe)

    loaded = self.mixin.read_match_cache('Example List')
    self.assertEqual([], loaded['matches'])
    self.assertEqual(
      'No manual match overrides needed for "Example List". Direct matches will be recomputed.',
      self.mixin.status_messages[-1])

  def test_save_active_matches_duplicate_position_uses_unique_author_match(self):
    recipe = self.configure_save_active_matches_fixture()
    self.mixin.write_import_cache('Example List', {
      'name': 'Example List',
      'entries': [
        {'position': '1', 'title': 'The Banished Lands', 'authors': ['John Gwynne']},
        {'position': '1', 'title': 'Vorkosigan Saga', 'authors': ['Lois McMaster Bujold']},
      ],
      'match_series': True,
    })
    self.mixin.active_book_ids_for_list = lambda _list_name: [2]
    self.mixin.read_position_display = lambda _field, _book_id, _fallback: ('1', 1.0)

    class FakeApi:
      def field_for(self, field, book_id, default_value=''):
        if field == 'title':
          return {2: "Cordelia's Honor (Books 2-3)"}.get(book_id, default_value)
        if field == 'authors':
          return {2: ['Lois McMaster Bujold']}.get(book_id, default_value)
        return default_value

      def all_field_for(self, field, ids, default_value=''):
        return {book_id: self.field_for(field, book_id, default_value) for book_id in ids}

    class FakeDb:
      new_api = FakeApi()

    self.mixin.db = FakeDb()
    self.mixin.author_matches = lambda book_authors, imported_author: imported_author in ' '.join(book_authors)
    self.mixin.direct_match_candidates_for_entry = lambda *_args, **_kwargs: []
    self.mixin._saved_match_entry_chooser = lambda *_args: self.fail(
      'unique tied-position author match should not require prompting')

    self.mixin.save_active_matches_for_recipe(recipe)

    loaded = self.mixin.read_match_cache('Example List')
    self.assertEqual(1, len(loaded['matches']))
    self.assertEqual('vorkosigan saga|lois mcmaster bujold', loaded['matches'][0]['entry_key'])
    self.assertEqual(2, loaded['matches'][0]['matched_book_id'])

  def test_save_active_matches_reuses_existing_tied_position_match(self):
    recipe = self.configure_save_active_matches_fixture()
    self.mixin.active_book_ids_for_list = lambda _list_name: [2]
    self.mixin.write_match_cache('Example List', [{
      'entry_key': 'book two imported|author two',
      'matched_book_id': 2,
      'matched_book_ids': [2],
    }])
    self.mixin._saved_match_entry_chooser = lambda *_args: self.fail(
      'existing tied-position match should not be reconfirmed')

    self.mixin.save_active_matches_for_recipe(recipe)

    loaded = self.mixin.read_match_cache('Example List')
    self.assertEqual(1, len(loaded['matches']))
    self.assertEqual('book two imported|author two', loaded['matches'][0]['entry_key'])
    self.assertEqual(2, loaded['matches'][0]['matched_book_id'])

  def test_save_active_matches_marks_stale_saved_match_unmatched(self):
    recipe = self.configure_save_active_matches_fixture()
    self.mixin.write_import_cache('Example List', {
      'name': 'Example List',
      'entries': [
        {'position': '1', 'title': 'Book One Imported', 'authors': ['Author One']},
      ],
      'match_series': True,
    })
    self.mixin.write_match_cache('Example List', [{
      'entry_key': 'book one imported|author one',
      'matched_book_id': 1,
      'matched_book_ids': [1],
      'matched_books': [{
        'book_id': 1,
        'title': 'Book One',
        'authors': ['Author One'],
      }],
    }])
    self.mixin.active_book_ids_for_list = lambda _list_name: []

    self.mixin.save_active_matches_for_recipe(recipe)

    loaded = self.mixin.read_match_cache('Example List')
    self.assertEqual(1, len(loaded['matches']))
    item = loaded['matches'][0]
    self.assertEqual('book one imported|author one', item['entry_key'])
    self.assertEqual(True, item['unmatched'])
    self.assertNotIn('ignored', item)
    self.assertEqual([1], item['previous_matched_book_ids'])
    self.assertEqual('saved/manual override', item['previous_match_source'])
    self.assertEqual(
      'Saved 1 unmatched directive(s) for "Example List".',
      self.mixin.status_messages[-1])

  def test_save_active_matches_prompts_when_tied_position_is_partially_saved(self):
    recipe = self.configure_save_active_matches_fixture()
    self.mixin.write_match_cache('Example List', [{
      'entry_key': 'book two imported|author two',
      'matched_book_id': 2,
      'matched_book_ids': [2],
    }])
    calls = []

    def chooser(book_id, _position, entries, _db):
      calls.append((book_id, [storage.entry_key(entry) for entry in entries]))
      return entries[0]

    self.mixin._saved_match_entry_chooser = chooser

    self.mixin.save_active_matches_for_recipe(recipe)

    loaded = self.mixin.read_match_cache('Example List')
    by_key = {item['entry_key']: item for item in loaded['matches']}
    self.assertEqual([
      (1, ['book one imported|author one', 'book two imported|author two'])
    ], calls)
    self.assertEqual({'book one imported|author one', 'book two imported|author two'}, set(by_key))
    self.assertEqual(1, by_key['book one imported|author one']['matched_book_id'])
    self.assertEqual(2, by_key['book two imported|author two']['matched_book_id'])

  def test_save_active_matches_saves_prompted_tied_position_direct_match(self):
    recipe = self.configure_save_active_matches_fixture()
    self.mixin.write_import_cache('Example List', {
      'name': 'Example List',
      'entries': [
        {'position': '1', 'title': 'Book One Imported', 'authors': ['Author One']},
        {'position': '1', 'title': 'Book Two Imported', 'authors': ['Author Two']},
        {'position': '1', 'title': 'Book Three Imported', 'authors': ['Author Three']},
      ],
      'match_series': True,
    })
    self.mixin.write_match_cache('Example List', [{
      'entry_key': 'book two imported|author two',
      'matched_book_id': 2,
      'matched_book_ids': [2],
    }])
    self.mixin.direct_match_candidates_for_entry = (
      lambda entry, **_kwargs: [1] if entry.get('title') == 'Book One Imported' else [])
    calls = []

    def chooser(book_id, _position, entries, _db):
      calls.append((book_id, [storage.entry_key(entry) for entry in entries]))
      return entries[0]

    self.mixin._saved_match_entry_chooser = chooser

    self.mixin.save_active_matches_for_recipe(recipe)

    loaded = self.mixin.read_match_cache('Example List')
    by_key = {item['entry_key']: item for item in loaded['matches']}
    self.assertEqual([
      (
        1,
        [
          'book one imported|author one',
          'book two imported|author two',
          'book three imported|author three',
        ],
      )
    ], calls)
    self.assertEqual({'book one imported|author one', 'book two imported|author two'}, set(by_key))
    self.assertEqual(1, by_key['book one imported|author one']['matched_book_id'])

  def test_save_active_matches_reuses_complete_tied_position_matches(self):
    recipe = self.configure_save_active_matches_fixture()
    self.mixin.write_match_cache('Example List', [
      {
        'entry_key': 'book one imported|author one',
        'matched_book_id': 1,
        'matched_book_ids': [1],
      },
      {
        'entry_key': 'book two imported|author two',
        'matched_book_id': 2,
        'matched_book_ids': [2],
      },
    ])
    self.mixin._saved_match_entry_chooser = lambda *_args: self.fail(
      'complete tied-position matches should not be reconfirmed')

    self.mixin.save_active_matches_for_recipe(recipe)

    loaded = self.mixin.read_match_cache('Example List')
    by_key = {item['entry_key']: item for item in loaded['matches']}
    self.assertEqual({'book one imported|author one', 'book two imported|author two'}, set(by_key))
    self.assertEqual(1, by_key['book one imported|author one']['matched_book_id'])
    self.assertEqual(2, by_key['book two imported|author two']['matched_book_id'])

  def test_save_active_matches_treats_direct_rows_as_resolved_for_tied_position(self):
    recipe = self.configure_save_active_matches_fixture()
    self.mixin.write_import_cache('Example List', {
      'name': 'Example List',
      'entries': [
        {'position': '1', 'title': 'Series One', 'authors': ['Author One']},
        {'position': '1', 'title': 'Book Two Imported', 'authors': ['Author Two']},
      ],
      'match_series': True,
    })
    self.mixin.write_match_cache('Example List', [{
      'entry_key': 'book two imported|author two',
      'matched_book_id': 2,
      'matched_book_ids': [2],
    }])
    self.mixin.direct_match_candidates_for_entry = (
      lambda entry, **_kwargs: [1] if entry.get('title') == 'Series One' else [])
    self.mixin._saved_match_entry_chooser = lambda *_args: self.fail(
      'tied position with saved rows plus direct rows should not be reconfirmed')

    self.mixin.save_active_matches_for_recipe(recipe)

    loaded = self.mixin.read_match_cache('Example List')
    self.assertEqual(1, len(loaded['matches']))
    self.assertEqual('book two imported|author two', loaded['matches'][0]['entry_key'])

  def test_save_active_matches_prompts_once_per_partially_saved_tied_position(self):
    recipe = self.configure_save_active_matches_fixture()
    self.mixin.write_import_cache('Example List', {
      'name': 'Example List',
      'entries': [
        {'position': '1', 'title': 'Book One Imported', 'authors': ['Author One']},
        {'position': '1', 'title': 'Book Two Imported', 'authors': ['Author Two']},
        {'position': '1', 'title': 'Book Three Imported', 'authors': ['Author Three']},
      ],
      'match_series': True,
    })
    self.mixin.all_book_ids = lambda: [1, 2, 3]
    self.mixin.active_book_ids_for_list = lambda _list_name: [1, 2, 3]
    self.mixin.write_match_cache('Example List', [{
      'entry_key': 'book one imported|author one',
      'matched_book_id': 1,
      'matched_book_ids': [1],
    }])
    calls = []

    def chooser(book_id, _position, entries, _db):
      calls.append((book_id, [storage.entry_key(entry) for entry in entries]))
      return entries[1]

    self.mixin._saved_match_entry_chooser = chooser

    self.mixin.save_active_matches_for_recipe(recipe)

    loaded = self.mixin.read_match_cache('Example List')
    by_key = {item['entry_key']: item for item in loaded['matches']}
    self.assertEqual([
      (
        2,
        [
          'book one imported|author one',
          'book two imported|author two',
          'book three imported|author three',
        ],
      )
    ], calls)
    self.assertEqual({'book one imported|author one', 'book two imported|author two'}, set(by_key))
    self.assertEqual(1, by_key['book one imported|author one']['matched_book_id'])
    self.assertEqual(2, by_key['book two imported|author two']['matched_book_id'])

  def test_save_active_matches_duplicate_position_accepts_one_row(self):
    recipe = self.configure_save_active_matches_fixture()
    self.mixin.active_book_ids_for_list = lambda _list_name: [1]

    def chooser(book_id, _position, entries, _db):
      self.assertEqual(1, book_id)
      return entries[0]

    self.mixin._saved_match_entry_chooser = chooser

    self.mixin.save_active_matches_for_recipe(recipe)

    loaded = self.mixin.read_match_cache('Example List')
    by_key = {item['entry_key']: item for item in loaded['matches']}
    self.assertEqual({'book one imported|author one'}, set(by_key))
    self.assertEqual(1, by_key['book one imported|author one']['matched_book_id'])

  def test_save_active_matches_duplicate_position_prompt_shows_full_tied_list(self):
    recipe = self.configure_save_active_matches_fixture()
    self.mixin.active_book_ids_for_list = lambda _list_name: [2, 1]
    self.mixin.read_position_display = lambda _field, book_id, _fallback: (
      '2' if book_id == 2 else '1', 2.0 if book_id == 2 else 1.0)
    self.mixin.write_match_cache('Example List', [{
      'entry_key': 'book one imported|author one',
      'matched_book_id': 2,
      'matched_book_ids': [2],
    }])
    calls = []

    def chooser(book_id, _position, entries, _db):
      calls.append((book_id, [storage.entry_key(entry) for entry in entries]))
      return entries[0]

    self.mixin._saved_match_entry_chooser = chooser

    self.mixin.save_active_matches_for_recipe(recipe)

    self.assertEqual([
      (1, ['book one imported|author one', 'book two imported|author two'])
    ], calls)

  def test_save_active_matches_duplicate_position_cancel_aborts(self):
    recipe = self.configure_save_active_matches_fixture()
    self.mixin.write_import_cache('Example List', {
      'name': 'Example List',
      'entries': [
        {'position': '1', 'title': 'Book One Imported', 'authors': ['Author One']},
        {'position': '1', 'title': 'Book Two Imported', 'authors': ['Author Two']},
        {'position': '1', 'title': 'Book Three Imported', 'authors': ['Author Three']},
      ],
      'match_series': True,
    })
    calls = []

    def chooser(book_id, _position, entries, _db):
      calls.append(book_id)
      if book_id == 1:
        return entries[0]
      raise storage.SaveActiveMatchesCancelled()

    self.mixin._saved_match_entry_chooser = chooser

    self.mixin.save_active_matches_for_recipe(recipe)

    loaded = self.mixin.read_match_cache('Example List')
    self.assertEqual([1, 2], calls)
    self.assertEqual([], loaded['matches'])
    self.assertEqual(
      'Save Active List Matches cancelled for "Example List".',
      self.mixin.status_messages[-1])


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
      parsed={'name': 'Example Award', 'entries': [{'position': '1', 'title': 'Book', 'authors': ['Author']}]})

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
    self.assertEqual('source-a', written['source']['url'])
    self.assertEqual(['Author'], written['entries'][0]['authors'])

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
      parsed={'name': 'Example Award', 'entries': [{'position': '1', 'title': 'Book', 'authors': ['Author']}]})

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
