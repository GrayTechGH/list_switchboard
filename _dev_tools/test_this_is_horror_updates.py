import unittest
from unittest.mock import patch

from _dev_tools import test_this_is_horror_transport as transport_fixtures
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError
from parser.this_is_horror import (
  OFFICIAL_AWARDS_API_URL, OFFICIAL_RESULT_POSTS_API_URL, GOODREADS_URL,
)
from storage import build_import_cache_data


class ThisIsHorrorUpdateTests(unittest.TestCase):

  def setUp(self):
    fixtures = transport_fixtures.ThisIsHorrorTransportTests()
    fixtures.setUp()
    self.pages = fixtures.pages
    self.recipe = transport_fixtures.FETCHERS[0]()
    self.calls = []
    self.failures = {}

  def fetch(self, url, **kwargs):
    self.calls.append(url)
    if url in self.failures:
      raise self.failures[url]
    return self.pages[url]

  def parse(self, cache=None):
    return self.recipe.fetch_and_parse(self.fetch, cached_parsed=cache,
      incremental_update=cache is not None)

  def cache(self, parsed):
    return build_import_cache_data(self.recipe.source_id, parsed)

  def test_all_active_categories_recover_missing_ballots_and_reuse_validated_results(self):
    for factory in transport_fixtures.FETCHERS[:3]:
      with self.subTest(recipe=factory.source_id):
        self.recipe = factory()
        self.calls = []
        full = self.parse()
        full_calls = len(self.calls)
        old = without_unit(self.cache(full), OFFICIAL_AWARDS_API_URL)
        self.assertLess(len(old['entries']), len(full['entries']))
        self.calls = []
        update = self.parse(old)
        self.assertEqual(full['entries'], update['entries'])
        self.assertEqual(full['notes'], update['notes'])
        self.assertLess(len(self.calls), full_calls)
        self.assertNotIn(OFFICIAL_RESULT_POSTS_API_URL, self.calls)
        self.assertIn(OFFICIAL_AWARDS_API_URL, self.calls)
        self.assertIn(GOODREADS_URL, self.calls)
        self.calls = []
        self.assertEqual(full['entries'], self.parse(self.cache(update))['entries'])
        self.assertNotIn(OFFICIAL_RESULT_POSTS_API_URL, self.calls)

  def test_changed_ballot_and_result_refresh_required_results_before_validation(self):
    old = self.cache(self.parse())
    title = transport_fixtures.work(self.recipe.CATEGORY, 2024, 0)
    self.pages[OFFICIAL_AWARDS_API_URL] = self.pages[OFFICIAL_AWARDS_API_URL].replace(title, 'Corrected Winner')
    self.pages[OFFICIAL_RESULT_POSTS_API_URL] = self.pages[OFFICIAL_RESULT_POSTS_API_URL].replace(title, 'Corrected Winner')
    self.calls = []
    update = self.parse(old)
    self.assertIn(OFFICIAL_RESULT_POSTS_API_URL, self.calls)
    self.assertEqual(self.parse()['entries'], update['entries'])

  def test_missing_result_unit_is_refetched_and_mandatory_failure_still_raises(self):
    full = self.parse()
    old = self.cache(full)
    old['incremental_state']['units'][OFFICIAL_RESULT_POSTS_API_URL]['complete'] = False
    self.failures[OFFICIAL_RESULT_POSTS_API_URL] = OSError('offline')
    with self.assertRaises(OSError):
      self.parse(old)
    self.assertIsNone(self.recipe._this_is_horror_fetch_policy)
    self.failures.clear()
    self.assertEqual(full['entries'], self.parse(old)['entries'])

  def test_current_result_year_is_not_frozen(self):
    full = self.parse()
    self.calls = []
    with patch('url_fetcher.this_is_horror.datetime') as dates:
      dates.datetime.now.return_value.year = 2024
      self.assertEqual(full['entries'], self.parse(self.cache(full))['entries'])
    self.assertIn(OFFICIAL_RESULT_POSTS_API_URL, self.calls)

  def test_legacy_scope_change_and_malformed_projection_rebuild_results(self):
    full = self.parse()
    wrong = self.cache(full)
    wrong['incremental_state']['source_key'] = 'changed manifest or category'
    bad = self.cache(full)
    bad['incremental_state']['units'][OFFICIAL_RESULT_POSTS_API_URL]['metadata'] = {}
    for old in ({'entries': full['entries']}, wrong, bad):
      self.calls = []
      self.assertEqual(full['entries'], self.parse(old)['entries'])
      self.assertIn(OFFICIAL_RESULT_POSTS_API_URL, self.calls)

  def test_required_browser_failure_does_not_become_a_diagnostic_note(self):
    self.failures[GOODREADS_URL] = CamoufoxRequiredError('required')
    with self.assertRaises(CamoufoxRequiredError):
      self.parse()
    self.assertIsNone(self.recipe._this_is_horror_fetch_policy)


if __name__ == '__main__':
  unittest.main()
