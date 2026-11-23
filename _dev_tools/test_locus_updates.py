import unittest

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError, CamoufoxRequiredError
from storage import build_import_cache_data
from url_fetcher.locus import UrlFetcherLocusAnnualSFNovel


class LocusUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe = UrlFetcherLocusAnnualSFNovel()
    self.years = [2022, 2023, 2024]
    self.calls = []
    self.unsettled = set()
    self.failures = {}
    self.changed = set()

  def url(self, year):
    return f'{self.recipe.URL}_{year}'

  def fetch(self, url):
    self.calls.append(url)
    if url == self.recipe.URL:
      return ''.join(f'<a href="{self.url(y)}">{y}</a>' for y in self.years)
    if url in self.failures:
      value = self.failures[url]
      if isinstance(value, Exception):
        raise value
      return value
    year = next(y for y in self.years if url == self.url(y))
    winner = '' if year in self.unsettled else 'Winner:'
    title = 'Corrected' if year in self.changed else 'Winner'
    return f'<title>sfadb: Locus Awards {year}</title><div class="categoryblock">'\
      f'<div class="category">{self.recipe.CATEGORY}</div><ol>'\
      f'<li>{winner} <b>{title} {year}</b>, <a>Alice Writer</a> &amp; <a>Bob Writer</a> (Publisher)</li>'\
      f'<li><b>Finalist {year}</b>, <a>Writer Three</a> (Publisher)</li></ol></div>'

  def parse(self, cache=None):
    return self.recipe.fetch_and_parse(self.fetch, source_choice=0,
      cached_parsed=cache, incremental_update=cache is not None)

  def cache(self, parsed):
    return build_import_cache_data(self.recipe.source_id, parsed)

  def test_all_annual_categories_preserve_ranked_rows_and_reuse_closed_years(self):
    from url_fetcher import available_url_fetchers
    recipes = [r for r in available_url_fetchers() if r.source_id.startswith('locus_annual_')]
    self.assertEqual(11, len(recipes))
    for self.recipe in recipes:
      with self.subTest(recipe=self.recipe.source_id):
        self.calls = []
        full = self.parse()
        self.assertEqual(4, len(self.calls))
        self.calls = []
        update = self.parse(self.cache(full))
        self.assertEqual(full['entries'], update['entries'])
        self.assertEqual([self.recipe.URL, self.url(2024)], self.calls)
        self.assertEqual(6, len(update['entries']))
        self.assertEqual(['Alice Writer', 'Bob Writer'], update['entries'][0]['authors'])
        self.assertEqual('winner', update['entries'][0]['result'])
        self.assertEqual('2022', update['entries'][0]['position'])
        self.assertFalse(update['match_series'])
        self.assertTrue(self.recipe.source_attempts()[0].supports_incremental)
        for fallback in self.recipe.source_attempts()[1:]:
          self.assertFalse(fallback.supports_incremental)

  def test_missing_year_and_added_year_recovered_with_history_intact(self):
    old = without_unit(self.cache(self.parse()), self.url(2022))
    self.years.append(2025)
    self.calls = []
    update = self.parse(old)
    self.assertEqual([self.recipe.URL, self.url(2022), self.url(2025)], self.calls)
    self.assertEqual(self.parse()['entries'], update['entries'])

  def test_unsettled_ballot_promoted_and_corrected(self):
    self.unsettled.add(2023)
    old = self.cache(self.parse())
    self.unsettled.clear()
    self.changed.add(2023)
    self.calls = []
    update = self.parse(old)
    self.assertEqual([self.recipe.URL, self.url(2023), self.url(2024)], self.calls)
    self.assertEqual(self.parse()['entries'], update['entries'])

  def test_failed_history_retained_pending_and_retried(self):
    for failure in (OSError('offline'), '<html>Wrong page</html>'):
      with self.subTest(failure=failure):
        full = self.parse()
        old = self.cache(full)
        old['incremental_state']['units'][self.url(2022)]['complete'] = False
        self.failures[self.url(2022)] = failure
        update = self.parse(old)
        self.assertEqual(full['entries'], update['entries'])
        self.assertFalse(update['incremental_state']['units'][self.url(2022)]['complete'])
        self.failures.clear()
        self.calls = []
        self.assertEqual(full['entries'], self.parse(self.cache(update))['entries'])
        self.assertIn(self.url(2022), self.calls)

  def test_changed_category_or_legacy_cache_requires_full_refresh(self):
    full = self.parse()
    wrong = self.cache(full)
    wrong['incremental_state']['source_key'] = 'Different category'
    for old in ({'entries': full['entries']}, wrong):
      self.calls = []
      self.assertEqual(full['entries'], self.parse(old)['entries'])
      self.assertEqual(4, len(self.calls))

  def test_cancel_and_required_browser_propagate_without_fallback(self):
    for error in (ImportCancelledError('stop'), CamoufoxRequiredError('required')):
      self.failures[self.url(2022)] = error
      with self.assertRaises(type(error)):
        self.parse()


if __name__ == '__main__':
  unittest.main()
