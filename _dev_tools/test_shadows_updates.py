import json
import unittest

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError, CamoufoxRequiredError
from parser.australasian_shadows import (
  OFFICIAL_CURRENT_API_URL, OFFICIAL_PAST_WINNERS_API_URL, OFFICIAL_2024_WINNERS_API_URL,
)
from storage import build_import_cache_data
from url_fetcher.australasian_shadows import UrlFetcherAustralasianShadowsNovel


class ShadowsUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe = UrlFetcherAustralasianShadowsNovel()
    self.calls, self.failures = [], {}
    self.current_year = 2025

  def response(self, title, html):
    return json.dumps([{'title': {'rendered': title}, 'content': {'rendered': html}}])

  def fetch(self, url):
    self.calls.append(url)
    if url in self.failures:
      raise self.failures[url]
    category = self.recipe.CATEGORY_ALIASES[0]
    if url == OFFICIAL_CURRENT_API_URL:
      return self.response(f'{self.current_year} Australasian Shadows Awards Finalists',
        f'<h2>{self.current_year} Finalists</h2><h3>{category}</h3>'
        '<ul><li>Current Book by Current Writer</li></ul>')
    if url == OFFICIAL_PAST_WINNERS_API_URL:
      return self.response('Past Winners',
        f'<h2>2023 Winners</h2><h3>{category}</h3><ul><li>Historical Book by Older Writer</li></ul>'
        f'<h2>2024 Finalists</h2><h3>{category}</h3><ul><li>Promoted Book by Winner Writer</li>'
        '<li>Historical Finalist by Other Writer</li></ul>')
    if url == OFFICIAL_2024_WINNERS_API_URL:
      return self.response('2024 Australasian Shadows Awards Winners',
        f'<h2>2024 Winners</h2><h3>{category}</h3><ul><li>Promoted Book by Winner Writer</li></ul>')
    raise AssertionError(url)

  def parse(self, cache=None):
    return self.recipe.fetch_and_parse(self.fetch, source_choice=0,
      cached_parsed=cache, incremental_update=cache is not None)

  def cache(self, parsed):
    return build_import_cache_data(self.recipe.source_id, parsed)

  def test_missing_live_history_recovered_while_closed_source_is_reused(self):
    full = self.parse()
    self.assertEqual(3, len(self.calls))
    old = without_unit(self.cache(full), OFFICIAL_PAST_WINNERS_API_URL)
    self.assertLess(len(old['entries']), len(full['entries']))
    self.calls = []
    update = self.parse(old)
    self.assertEqual(full['entries'], update['entries'])
    self.assertEqual([OFFICIAL_CURRENT_API_URL, OFFICIAL_PAST_WINNERS_API_URL], self.calls)
    self.calls = []
    self.assertEqual(full['entries'], self.parse(self.cache(update))['entries'])
    self.assertEqual(2, len(self.calls))

  def test_source_projection_preserves_promoted_winner_and_new_year_positions(self):
    full = self.parse()
    winner = next(e for e in full['entries'] if e['title'] == 'Promoted Book')
    self.assertEqual('winner', winner['result'])
    self.assertIn('2024-australasian-shadows-awards-winners', winner['source']['url'])
    self.current_year = 2026
    update = self.parse(self.cache(full))
    self.assertEqual(self.parse()['entries'], update['entries'])
    self.assertEqual('2026', next(e['award_year'] for e in update['entries'] if e['title'] == 'Current Book'))

  def test_failed_live_or_closed_source_retains_original_projected_rows_pending(self):
    full = self.parse()
    for url in (OFFICIAL_PAST_WINNERS_API_URL, OFFICIAL_2024_WINNERS_API_URL):
      with self.subTest(url=url):
        old = self.cache(full)
        old['incremental_state']['units'][url]['complete'] = False
        self.failures[url] = OSError('offline')
        update = self.parse(old)
        self.assertEqual(full['entries'], update['entries'])
        self.assertFalse(update['incremental_state']['units'][url]['complete'])
        self.assertTrue(any('failed' in note for note in update['notes']))
        self.failures.clear()
        self.calls = []
        self.assertEqual(full['entries'], self.parse(self.cache(update))['entries'])
        self.assertIn(url, self.calls)

  def test_legacy_changed_scope_and_bad_projection_refetch_closed_source(self):
    full = self.parse()
    wrong = self.cache(full)
    wrong['incremental_state']['source_key'] = 'different category'
    malformed = self.cache(full)
    malformed['incremental_state']['units'][OFFICIAL_2024_WINNERS_API_URL]['metadata'] = {}
    for old in ({'entries': full['entries']}, wrong, malformed):
      self.calls = []
      self.assertEqual(full['entries'], self.parse(old)['entries'])
      self.assertEqual(3, len(self.calls))

  def test_cancellation_and_browser_requirement_do_not_become_supplement_notes(self):
    for url in (OFFICIAL_PAST_WINNERS_API_URL, OFFICIAL_2024_WINNERS_API_URL):
      for error in (ImportCancelledError('stop'), CamoufoxRequiredError('required')):
        self.failures[url] = error
        with self.assertRaises(type(error)):
          self.parse()
        self.failures.clear()

  def test_all_six_categories_keep_source_scope_and_wikipedia_remains_full_refresh(self):
    from url_fetcher import available_url_fetchers
    recipes = [r for r in available_url_fetchers() if r.source_id.startswith('australasian_shadows_')]
    self.assertEqual(6, len(recipes))
    for self.recipe in recipes:
      with self.subTest(recipe=self.recipe.source_id):
        full = self.parse()
        self.calls = []
        update = self.parse(self.cache(full))
        self.assertEqual(full['entries'], update['entries'])
        self.assertEqual(4, len(update['entries']))
        self.assertEqual(2, len(self.calls))
        official, wikipedia = self.recipe.source_attempts()
        self.assertTrue(official.supports_incremental)
        self.assertFalse(wikipedia.supports_incremental)


if __name__ == '__main__':
  unittest.main()
