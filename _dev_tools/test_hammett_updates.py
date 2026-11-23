import unittest

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError, ImportCancelledError
from storage import build_import_cache_data
from url_fetcher.hammett import UrlFetcherHammettPrize


class HammettUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe, self.calls, self.failures = UrlFetcherHammettPrize(), [], {}
    self.open = 'https://www.crimewritersna.org/hammett-prize-past-winners-nominees-j'
    self.closed = 'https://www.crimewritersna.org/copy-of-hammett-prize-past-winners-n-2'
    self.ranges = {self.open: ('2025 - Present',[2025]), self.closed: ('2023 - 2024',[2023,2024])}

  def fetch(self, url):
    self.calls.append(url)
    if url in self.failures:
      raise self.failures[url]
    if url == self.recipe.URL:
      return ''.join(f'<a href="{u}">Hammett {label}</a>' for u,(label,years) in self.ranges.items())
    return ''.join(f'<h2>{year}</h2><p>Winner: Winner {year} by Writer One</p>'
      f'<p>Nominees:</p><p>Other {year} by Writer Two</p><p>Judges: Person</p>' for year in self.ranges[url][1])

  def parse(self, old=None):
    return self.recipe.fetch_and_parse(self.fetch, source_choice=0,
      cached_parsed=old, incremental_update=old is not None)

  def cache(self, parsed):
    return build_import_cache_data(self.recipe.source_id, parsed)

  def test_closed_ranges_reused_missing_open_recovered_and_new_links_fetched(self):
    full = self.parse()
    self.assertEqual(3, len(self.calls))
    old = without_unit(self.cache(full), self.open)
    self.calls.clear()
    self.assertEqual(full['entries'], self.parse(old)['entries'])
    self.assertEqual([self.recipe.URL,self.open], self.calls)
    new = 'https://www.crimewritersna.org/copy-of-hammett-prize-past-winners-n-1'
    self.ranges[new] = ('2021 - 2022',[2021,2022])
    self.calls.clear()
    update = self.parse(self.cache(full))
    self.assertEqual([self.recipe.URL,self.open,new],self.calls)
    self.assertEqual(self.parse()['entries'],update['entries'])
    self.assertFalse(update['match_series'])

  def test_changed_range_refetches_and_missing_coverage_is_pending(self):
    full = self.parse()
    self.ranges[self.closed] = ('2022 - 2024',[2022,2023,2024])
    self.calls.clear()
    update = self.parse(self.cache(full))
    self.assertIn(self.closed,self.calls)
    self.assertEqual(self.parse()['entries'],update['entries'])
    old = self.cache(update)
    old['incremental_state']['units'][self.closed]['complete'] = False
    self.ranges[self.closed] = ('2022 - 2024',[2023,2024])
    pending = self.parse(old)
    self.assertEqual(update['entries'],pending['entries'])
    self.assertFalse(pending['incremental_state']['units'][self.closed]['complete'])
    self.assertTrue(pending['notes'])

  def test_failed_history_retries_and_cancel_or_browser_requirement_propagates(self):
    full = self.parse()
    old = self.cache(full)
    old['incremental_state']['units'][self.closed]['complete'] = False
    self.failures[self.closed] = OSError('offline')
    pending = self.parse(old)
    self.assertEqual(full['entries'],pending['entries'])
    self.failures.clear()
    self.calls.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(pending))['entries'])
    self.assertIn(self.closed,self.calls)
    for error in (ImportCancelledError('stop'),CamoufoxRequiredError('required')):
      self.failures[self.closed] = error
      with self.assertRaises(type(error)):
        self.parse(old)

  def test_legacy_wrong_scope_and_bad_projection_rebuild(self):
    full = self.parse()
    bad = self.cache(full)
    bad['incremental_state']['units'][self.closed]['metadata'] = {}
    wrong = self.cache(full)
    wrong['incremental_state']['source_key'] = 'different source'
    for old in ({'entries':full['entries']},bad,wrong):
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(old)['entries'])
      self.assertIn(self.closed,self.calls)
    official, replacement = self.recipe.source_attempts()
    self.assertTrue(official.supports_incremental)
    self.assertFalse(replacement.supports_incremental)


if __name__ == '__main__':
  unittest.main()
