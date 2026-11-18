import unittest

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from storage import build_import_cache_data
from url_fetcher.aurealis import UrlFetcherAurealisSFNovel


class AurealisUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe = UrlFetcherAurealisSFNovel()
    self.years = [2022, 2023, 2024]
    self.calls = []

  def fetch(self, url):
    self.calls.append(url)
    if url == self.recipe.URL:
      return ''.join(f'<a href="{self.recipe.URL}_{y}">{y}</a>' for y in self.years)
    year = next(y for y in self.years if url == f'{self.recipe.URL}_{y}')
    return f'<title>sfadb: Aurealis Awards {year}</title><div class="categoryblock">'\
      f'<div class="category">{self.recipe.CATEGORY_ALIASES[0]}</div><ul>'\
      f'<li>Winner: <b>Book {year}</b>, <a href="One">Writer One</a> &amp; <a href="Two">Writer Two</a> (Publisher)</li>'\
      f'<li><b>&quot;Quoted Story {year}&quot;</b>, <a href="Three">Writer Three</a> (Publisher)</li></ul></div>'

  def parse(self, cache=None):
    return self.recipe.fetch_and_parse(self.fetch, source_choice=0,
      cached_parsed=cache, incremental_update=cache is not None)

  def cache(self, parsed):
    return build_import_cache_data(self.recipe.source_id, parsed)

  def test_twelve_active_scopes_recover_history_preserve_credits_and_series_mode(self):
    from url_fetcher import available_url_fetchers
    recipes = [r for r in available_url_fetchers() if r.source_id.startswith('aurealis_')]
    active = 0
    for self.recipe in recipes:
      with self.subTest(recipe=self.recipe.source_id):
        if not self.recipe.ENABLE_SFADB_INCREMENTAL:
          self.assertFalse(self.recipe.SUPPORTS_INCREMENTAL_UPDATE)
          self.assertFalse(self.recipe.source_attempts()[0].supports_incremental)
          continue
        active += 1
        full = self.parse()
        old = without_unit(self.cache(full), f'{self.recipe.URL}_2022')
        self.calls = []
        update = self.parse(old)
        self.assertEqual(full['entries'], update['entries'])
        self.assertEqual(3, len(self.calls))
        self.assertEqual(self.recipe.options['match_series'], update['match_series'])
        if self.recipe.PREFER_LINKED_CREDITS:
          self.assertEqual(['Writer One', 'Writer Two'], update['entries'][0]['authors'])
        self.calls = []
        self.assertEqual(full['entries'], self.parse(self.cache(update))['entries'])
        self.assertEqual(2, len(self.calls))
        primary, *alternatives = self.recipe.source_attempts()
        self.assertTrue(primary.supports_incremental)
        self.assertTrue(all(not attempt.supports_incremental for attempt in alternatives))
    self.assertEqual(12, active)

  def test_changed_quoted_title_option_refetches_closed_years(self):
    full = self.parse()
    self.assertTrue(any(e['title'].startswith('Quoted') for e in full['entries']))
    old = self.cache(full)
    class ChangedQuoteScope(UrlFetcherAurealisSFNovel):
      SKIP_QUOTED = True
    self.recipe = ChangedQuoteScope()
    self.calls = []
    update = self.parse(old)
    self.assertEqual(4, len(self.calls))
    self.assertFalse(any(e['title'].startswith('Quoted') for e in update['entries']))
    self.assertEqual(self.parse()['entries'], update['entries'])


if __name__ == '__main__':
  unittest.main()
