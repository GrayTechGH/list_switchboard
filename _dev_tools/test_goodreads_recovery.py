"""Isolated fake-runtime tests for Goodreads matching transport and ownership."""

import io
import json
import types
import unittest
from email.message import Message
from urllib.error import HTTPError
from unittest.mock import Mock, patch

from _dev_tools import test_import_matching as fixtures
from transport.camoufox import browser_operation
from errors import ImportCancelledError, CamoufoxFetchError
from goodreads.recovery_transport import validate_recovery_payload

main = fixtures.main


class GoodreadsRecoveryTest(unittest.TestCase):

  setUp = fixtures.CamoufoxPilotTest.setUp
  capability = fixtures.CamoufoxPilotTest.capability
  BOOK = 'https://www.goodreads.com/book/show/123'
  SOURCE = 'https://www.goodreads.com/series/123-example'

  def book_html(self, series=True):
    book = {'__typename': 'Book', 'title': 'Example Book'}
    if series:
      book['bookSeries'] = [{'__typename': 'Series', 'title': 'Example Series'}]
    return '<html><title>Example Book | Goodreads</title><h1 id="bookTitle">Example Book</h1><script id="__NEXT_DATA__" type="application/json">' + json.dumps(book) + '</script></html>'

  def source_html(self):
    return '<html><title>Example Series | Goodreads</title><h1>Example Series</h1><div><a href="/book/show/123">Example Book</a><a href="/author/show/9">Example Writer</a></div></html>'

  def setup_transport(self, browser=None, legacy=None):
    self.capability()
    self.enterContext(patch.object(main, 'CalibreBrowser', object()))
    self.enterContext(patch.object(main, 'urlopen', side_effect=AssertionError('Unit tests must not access the network')))
    factory = self.enterContext(patch.object(main, 'CamoufoxTransport'))
    factory.return_value.fetch.side_effect = browser or (lambda url, **kw: self.book_html() if '/book/show/' in url else self.source_html())
    self.core.calibre_browser = Mock()

    def response(url, **kw):
      result = legacy(url, **kw) if legacy else (self.book_html() if '/book/show/' in url else self.source_html())
      value = io.BytesIO(result.encode('utf-8'))
      value.headers = Message()
      value.headers['Content-Type'] = 'text/html; charset=utf-8'
      return value

    self.core.calibre_browser.return_value.open.side_effect = response
    self.core.sleep_with_events = Mock()
    return factory

  def lookup(self, role):
    return self.core.fetch_goodreads_series_names('123') if role == 'book' else self.core.fetch_goodreads_source_data(self.SOURCE)

  def expected(self, role):
    return ['Example Series'] if role == 'book' else {
      'series_names': ['Example Series'], 'books': [{'title': 'Example Book', 'author': 'Example Writer'}]}

  def test_both_roles_and_every_stage(self):
    for role in ('book', 'source'):
      for stage in (0, 1, 2):
        with self.subTest(role=role, stage=stage):
          main.prefs['debug_browser_fallback_level'] = stage
          factory = self.setup_transport()
          with patch.object(main, 'camoufox_capability', return_value=(True, (9, 17, 0), 'API')) as capability:
            self.assertEqual(self.expected(role), self.lookup(role))
            if stage == 2:
              factory.assert_not_called()
              capability.assert_not_called()
            else:
              factory.assert_called_once()
              factory.return_value.close.assert_called_once()
              self.core.calibre_browser.assert_not_called()

  def test_older_versions_and_missing_api_use_legacy_without_prompt(self):
    factory = self.setup_transport()
    for version in ((6, 0, 0), (9, 15, 0), (9, 17, 0)):
      for role in ('book', 'source'):
        with patch.object(main, 'camoufox_capability', return_value=(False, version, 'missing')):
          with patch.object(main, 'question_dialog') as prompt:
            self.assertEqual(self.expected(role), self.lookup(role))
            prompt.assert_not_called()
    factory.assert_not_called()

  def test_consent_accept_and_decline_across_nested_phases(self):
    factory = self.setup_transport()
    for accept in (False, True):
      main.prefs['camoufox_first_use_confirmed'] = False
      with patch.object(main, 'question_dialog', return_value=accept) as prompt:
        with browser_operation(self.core):
          self.assertEqual(self.expected('book'), self.lookup('book'))
          self.assertEqual(self.expected('source'), self.lookup('source'))
        prompt.assert_called_once()
      self.assertEqual(accept, main.prefs['camoufox_first_use_confirmed'])
    factory.assert_called_once()

  def test_browser_failure_or_rejection_recovers_and_suppresses_once(self):
    factory = self.setup_transport()
    for rejected in ('', '<h1>Sign in to Goodreads</h1>', '<h1>Verify you are human</h1>',
        '<h1>Random heading</h1>', '<script id="__NEXT_DATA__">{broken</script>', CamoufoxFetchError('response exceeds 10 MiB')):
      factory.return_value.fetch.reset_mock()
      factory.return_value.close.reset_mock()
      factory.return_value.fetch.side_effect = rejected if isinstance(rejected, Exception) else lambda *a, **kw: rejected
      with browser_operation(self.core):
        self.assertEqual(self.expected('book'), self.lookup('book'))
        self.assertEqual(self.expected('source'), self.lookup('source'))
      factory.return_value.fetch.assert_called_once()
      factory.return_value.close.assert_called_once()
    self.assertTrue(any('using legacy' in line for line in self.logs))

  def test_both_transports_fail_best_effort_without_caching_across_imports(self):
    factory = self.setup_transport(browser=lambda *a, **kw: '', legacy=lambda *a, **kw: '<h1>Sign in</h1>')
    for _attempt in range(2):
      with browser_operation(self.core):
        self.assertEqual([], self.lookup('book'))
        self.assertEqual({'series_names': [], 'books': []}, self.lookup('source'))
      self.assertEqual({}, self.core.goodreads_series_cache)
    self.assertEqual(2, factory.call_count)

  def test_valid_book_without_series_bypasses_legacy(self):
    factory = self.setup_transport(browser=lambda *a, **kw: self.book_html(series=False))
    self.assertEqual([], self.lookup('book'))
    self.core.calibre_browser.assert_not_called()
    factory.return_value.close.assert_called_once()

  def test_structural_validation_rejects_misleading_heading_and_json(self):
    for html in ('', '<h1>Example Series</h1>', '<h1>JavaScript is disabled</h1>', '<html><title>Sign In | Goodreads</title><h1>Example</h1><a href="/book/show/1">Book</a></html>',
        '<h1>Example</h1><script id="__NEXT_DATA__">not JSON</script><a href="/book/show/1">Book</a>'):
      for url in (self.BOOK, self.SOURCE):
        with self.subTest(html=html, url=url), self.assertRaises(ValueError):
          validate_recovery_payload(html, url)

  def test_legacy_timeout_retries_not_applied_to_browser(self):
    def legacy(url, **kw):
      if self.core.calibre_browser.return_value.open.call_count < 4:
        raise main.URLError(TimeoutError('timed out'))
      return self.book_html()
    factory = self.setup_transport(browser=Mock(side_effect=TimeoutError('timed out')), legacy=legacy)
    self.assertEqual(self.expected('book'), self.lookup('book'))
    self.assertEqual(1, factory.return_value.fetch.call_count)
    self.assertEqual(4, self.core.calibre_browser.return_value.open.call_count)
    self.assertTrue(all(call.kwargs['timeout'] == 60 for call in self.core.calibre_browser.return_value.open.call_args_list))

  def test_permanent_legacy_errors_are_not_retried(self):
    self.setup_transport(browser=Mock(side_effect=CamoufoxFetchError('blocked')),
      legacy=Mock(side_effect=HTTPError(self.BOOK, 403, 'Forbidden', {}, None)))
    self.assertEqual([], self.lookup('book'))
    self.assertEqual(1, self.core.calibre_browser.return_value.open.call_count)

  def test_cache_reused_inside_operation_and_reset_for_next_import(self):
    factory = self.setup_transport()
    for _attempt in range(2):
      with browser_operation(self.core):
        self.assertEqual(self.expected('book'), self.lookup('book'))
        self.assertEqual(self.expected('book'), self.lookup('book'))
        self.assertEqual(self.expected('source'), self.lookup('source'))
        self.assertEqual(self.expected('source'), self.lookup('source'))
        self.assertEqual(2, len(self.core.goodreads_series_cache))
      self.assertEqual({}, self.core.goodreads_series_cache)
    self.assertEqual(2, factory.call_count)
    self.assertEqual(4, factory.return_value.fetch.call_count)
    self.assertTrue(any('cache hit' in line for line in self.logs))

  def test_nested_fetch_and_recovery_reuse_browser_then_close_before_review(self):
    factory = self.setup_transport()
    recipe = types.SimpleNamespace(fetch_and_parse=lambda fetch, **kw: fetch(self.url, transport='camoufox'))
    with browser_operation(self.core):
      self.core.fetch_and_parse_recipe(recipe)
      self.assertTrue(factory.return_value.check_challenges)
      factory.return_value.close.assert_not_called()
      self.assertEqual(self.expected('source'), self.lookup('source'))
      self.assertFalse(factory.return_value.check_challenges)
      self.assertEqual('Goodreads', factory.return_value.source_name)
      self.assertIn('goodreads.com', factory.call_args.kwargs['warmup_excluded_domains'])
      import import_flow
      with patch.object(import_flow, 'ImportReportDialog', side_effect=RuntimeError('review opens')):
        with self.assertRaisesRegex(RuntimeError, 'review opens'):
          self.core.review_import_matches('Test', None, 0, 0, [], [])
      factory.return_value.close.assert_called_once()
    self.assertEqual(1, factory.call_count)
    self.assertEqual(2, factory.return_value.fetch.call_count)
    factory.return_value.close.assert_called_once()

  def test_failure_in_fetch_phase_suppresses_matching_phase(self):
    factory = self.setup_transport()
    recipe = types.SimpleNamespace(fetch_and_parse=lambda fetch, **kw: self.core.reject_camoufox_payload('rejected ballot'))
    with browser_operation(self.core):
      self.core.fetch_and_parse_recipe(recipe)
      self.assertEqual(self.expected('book'), self.lookup('book'))
    factory.assert_not_called()

  def test_standalone_fetch_and_matching_always_cleanup(self):
    factory = self.setup_transport()
    recipe = types.SimpleNamespace(fetch_and_parse=lambda fetch, **kw: fetch(self.BOOK, transport='camoufox'))
    self.core.fetch_and_parse_recipe(recipe)
    factory.return_value.close.assert_called_once()
    self.core.match_imported_entries_for_list = lambda *a, **kw: self.lookup('book')
    self.assertEqual(self.expected('book'), self.core.match_imported_entries([]))
    self.assertEqual(2, factory.call_count)
    self.assertEqual(2, factory.return_value.close.call_count)

  def test_cancellation_from_browser_or_legacy_is_never_swallowed_or_cached(self):
    factory = self.setup_transport()
    for transport in ('browser', 'legacy'):
      for role in ('book', 'source'):
        main.prefs['debug_browser_fallback_level'] = 2 if transport == 'legacy' else 0
        if transport == 'browser':
          factory.return_value.fetch.side_effect = ImportCancelledError('cancelled timeout')
        else:
          self.core.calibre_browser.return_value.open.side_effect = ImportCancelledError('cancelled timeout')
        with browser_operation(self.core):
          with self.assertRaises(ImportCancelledError):
            self.lookup(role)
          self.assertEqual({}, self.core.goodreads_series_cache)
    self.assertEqual(2, self.core.calibre_browser.return_value.open.call_count)

  def test_cancel_during_throttle_progress_and_extraction(self):
    factory = self.setup_transport()
    for point in ('throttle', 'progress', 'extract'):
      with browser_operation(self.core):
        if point == 'throttle':
          self.core.last_goodreads_lookup_time = __import__('time').time()
          target = 'sleep_with_events'
        else:
          target = 'update_import_progress' if point == 'progress' else 'extract_goodreads_series_names'
        with patch.object(self.core, target, side_effect=ImportCancelledError('cancelled')):
          with self.assertRaises(ImportCancelledError):
            self.lookup('book')
          self.assertEqual({}, self.core.goodreads_series_cache)
    self.assertEqual(1, factory.return_value.fetch.call_count)

  def test_cancellation_stops_matching_and_no_writes_follow(self):
    self.setup_transport(browser=Mock(side_effect=ImportCancelledError('cancelled')))
    writes = Mock()
    self.core.match_imported_entries_for_list = lambda *a, **kw: (self.lookup('book'), writes())
    with self.assertRaises(ImportCancelledError):
      self.core.match_imported_entries([])
    writes.assert_not_called()
    self.assertIsNone(self.core.camoufox_transport)

  def test_non_goodreads_hosts_never_fetch_even_with_goodreads_in_path(self):
    factory = self.setup_transport()
    for url in ('https://evil.test/goodreads.com/series/1', 'https://goodreads.com.evil.test/book/show/1', 'file:///goodreads.com/book/show/1', 'https://[', None, 123):
      self.assertEqual({'series_names': [], 'books': []}, self.core.fetch_goodreads_source_data(url))
    factory.assert_not_called()
    self.core.calibre_browser.assert_not_called()

  def test_throttle_is_shared_between_book_and_source(self):
    self.setup_transport()
    with browser_operation(self.core):
      self.lookup('book')
      self.lookup('source')
    self.core.sleep_with_events.assert_called_once()
    self.assertGreater(self.core.sleep_with_events.call_args.args[0], 0)
    self.assertLessEqual(self.core.sleep_with_events.call_args.args[0], 1.5)

  def matching_core(self, title='Project Hail Mary'):
    core = fixtures.ImportMatchingTest().import_list_review_auto_core(
      {1: title}, {1: ['Andy Weir']})
    del core.__dict__['fetch_goodreads_source_data']
    core.debug_log = lambda *a, **kw: None
    core.debug_camoufox = self.logs.append
    core.sleep_with_events = Mock()
    core.update_import_progress = Mock()
    return core

  def test_real_matching_uses_recovery_without_loosening_title_or_author_rules(self):
    for title, author, matched in (
        ('Project: Hail Mary', 'Andy Weir', {1: '1'}),
        ('Project Hail Mary', 'Andy Weir', {}),
        ('Project: Hail Mary', 'Someone Else', {})):
      self.core = self.matching_core()
      factory = self.setup_transport(browser=lambda *a, **kw:
        f'<h1>List</h1><div><a href="/book/show/123">{title}</a><a href="/author/show/1">{author}</a></div>')
      entry = {'position': '1', 'title': 'Hail Mary', 'authors': ['Andy Weir'], 'source': {'url': self.SOURCE}}
      self.assertEqual(matched, self.core.match_imported_entries([entry])[0])
      factory.return_value.close.assert_called_once()

  def test_cached_list_matching_and_exact_id_shortcuts_do_not_fetch(self):
    self.core = self.matching_core()
    factory = self.setup_transport()
    entry = {'position': '1', 'title': 'Unknown', 'authors': ['Andy Weir'], 'source': {'url': self.BOOK}}
    self.core.match_imported_entries([entry], allow_goodreads_recovery=False)
    factory.assert_not_called()
    self.core.goodreads_id_for_book = lambda book_id: '123'
    self.assertEqual({1: '1'}, self.core.match_imported_entries([entry])[0])
    factory.assert_not_called()
    self.core.calibre_browser.assert_not_called()

  def test_actual_matching_cancel_cannot_offer_cache_or_apply_writes(self):
    self.core = self.matching_core()
    factory = self.setup_transport(browser=Mock(side_effect=ImportCancelledError('cancelled')))
    entry = {'position': '1', 'title': 'Hail Mary', 'authors': ['Andy Weir'], 'source': {'url': self.SOURCE}}
    self.core.should_fallback_to_cached_import = Mock()
    self.core.write_fields = Mock()
    with self.assertRaises(ImportCancelledError):
      self.core.match_imported_entries([entry])
    self.core.should_fallback_to_cached_import.assert_not_called()
    self.core.write_fields.assert_not_called()
    factory.return_value.close.assert_called_once()

  def test_outer_import_cancellation_closes_shared_browser(self):
    factory = self.setup_transport()
    self.core.ensure_configured = lambda: True
    self.core.create_import_progress = lambda *_a: None
    self.core.close_import_progress = Mock()
    self.core.clear_import_progress_phase = Mock()
    self.core.debug_recipe_start = Mock()
    self.core.show_import_progress_start = Mock()
    self.core.log_recipe_output = Mock()
    self.core.status_message = Mock()
    self.core.show_exception = Mock()
    self.core.load_or_fetch_recipe = lambda *a, **kw: self.lookup('book')
    self.core.import_recipe_result = Mock(side_effect=ImportCancelledError('cancelled'))
    self.core.import_recipe(types.SimpleNamespace(NAME='Test'))
    self.core.status_message.assert_called_once_with('cancelled')
    self.core.show_exception.assert_not_called()
    factory.return_value.close.assert_called_once()
    self.assertEqual({}, self.core.goodreads_series_cache)

  def test_oversized_legacy_response_is_not_retried(self):
    main.prefs['debug_browser_fallback_level'] = 2
    self.setup_transport(legacy=lambda *a, **kw: 'x' * (10 * 1024 * 1024 + 1))
    self.assertEqual([], self.lookup('book'))
    self.assertEqual(1, self.core.calibre_browser.return_value.open.call_count)


if __name__ == '__main__':
  unittest.main()
