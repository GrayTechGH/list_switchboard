import unittest
from copy import deepcopy
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError, CamoufoxRequiredError
from parser.hugo import (
  HugoAwardsNovelParser, HugoAwardsNovellaParser, HugoAwardsSeriesParser,
  HugoAwardsGraphicStoryParser, HugoAwardsRelatedWorkParser, LodestarAwardParser,
)
from storage import build_import_cache_data


class HugoUpdateTests(unittest.TestCase):

  def setUp(self):
    self.parser = HugoAwardsNovelParser()
    self.root = 'https://www.thehugoawards.org/hugo-history/'
    self.years = [2022, 2023, 2024]
    self.calls = []
    self.unsettled = set()
    self.failures = {}
    self.titles = {}
    self.no_category = set()

  def url(self, year):
    return f'{self.root}{year}-hugo-awards/'

  def page(self, year):
    intro = '<p>Finalists were announced; awards will be presented.</p>' if year in self.unsettled else ''
    category = 'Best Novel' if year not in self.no_category else 'Best Short Story'
    return f'<h1 class="entry-title">{year} Hugo Awards</h1><div class="entry-content">{intro}'\
      f'<h2>{category}</h2><ul><li>{self.titles.get(year, "Winner")} by Writer One</li>'\
      '<li>Finalist by Writer Two</li></ul><h2>Best Novella</h2>'\
      '<ul><li>Shorter by Writer Three</li></ul></div>'

  def fetch(self, url):
    self.calls.append(url)
    if url in self.failures:
      value = self.failures[url]
      if isinstance(value, Exception):
        raise value
      return value
    return self.page(next(y for y in self.years if url == self.url(y)))

  def parse(self, cache=None):
    history = ''.join(f'<a href="{self.url(y)}">{y} Hugo Awards</a>' for y in self.years)
    return self.parser.parse(history, self.root, fetch_url=self.fetch,
      cached_parsed=cache, incremental_update=cache is not None)

  def cache(self, parsed):
    return build_import_cache_data('hugo', parsed)

  def test_closed_years_reused_and_latest_refreshed(self):
    full = self.parse()
    self.assertEqual(3, len(self.calls))
    self.calls = []
    update = self.parse(self.cache(full))
    self.assertEqual(full['entries'], update['entries'])
    self.assertEqual([self.url(2024)], self.calls)
    self.calls = []
    self.assertEqual(full['entries'], self.parse(self.cache(update))['entries'])
    self.assertEqual([self.url(2024)], self.calls)

  def test_missing_history_and_added_year_are_discovered(self):
    full = self.parse()
    old = without_unit(self.cache(full), self.url(2022))
    self.years.append(2025)
    self.calls = []
    update = self.parse(old)
    self.assertEqual([self.url(2022), self.url(2025)], self.calls)
    self.assertEqual(self.parse()['entries'], update['entries'])
    self.assertEqual(8, len(update['entries']))

  def test_unsettled_old_ballot_is_rechecked_and_winner_replaced(self):
    self.unsettled.add(2023)
    full = self.parse()
    self.unsettled.clear()
    self.titles[2023] = 'Promoted Winner'
    self.calls = []
    update = self.parse(self.cache(full))
    self.assertEqual([self.url(2023), self.url(2024)], self.calls)
    self.assertEqual(self.parse()['entries'], update['entries'])
    self.assertIn('Promoted Winner', [e['title'] for e in update['entries']])

  def test_fetch_failure_or_wrong_page_retains_history_and_retries(self):
    for failure in (OSError('offline'), '<h1>Verify you are human</h1>'):
      with self.subTest(failure=failure):
        full = self.parse()
        old = self.cache(full)
        old['incremental_state']['units'][self.url(2022)]['complete'] = False
        self.failures[self.url(2022)] = failure
        update = self.parse(old)
        self.assertEqual(full['entries'], update['entries'])
        self.assertFalse(update['incremental_state']['units'][self.url(2022)]['complete'])
        self.assertTrue(update['notes'])
        self.failures.clear()
        self.calls = []
        self.assertEqual(full['entries'], self.parse(self.cache(update))['entries'])
        self.assertIn(self.url(2022), self.calls)

  def test_absent_category_in_verified_year_is_cached_as_empty(self):
    self.no_category.add(2022)
    full = self.parse()
    self.calls = []
    update = self.parse(self.cache(full))
    self.assertEqual(full['entries'], update['entries'])
    self.assertNotIn(self.url(2022), self.calls)

  def test_empty_discovery_cannot_erase_cached_list(self):
    full = self.parse()
    with self.assertRaises(ValueError):
      self.parser.parse('<h1>Unavailable</h1>', self.root, fetch_url=self.fetch,
        cached_parsed=self.cache(full), incremental_update=True)

  def test_current_year_refreshed_even_with_future_discovery(self):
    self.years = [2024, 2025, 2026, 2027]
    full = self.parse()
    self.calls = []
    with patch('parser.hugo.datetime') as dates:
      dates.datetime.now.return_value.year = 2026
      self.parse(self.cache(full))
    self.assertEqual([self.url(2026), self.url(2027)], self.calls)

  def test_legacy_malformed_and_cross_category_caches_rebuild(self):
    full = self.parse()
    caches = [{'entries': full['entries']}, self.cache(full), self.cache(full)]
    caches[1]['incremental_state']['source_key'] = 'another category'
    caches[2]['incremental_state']['units'][self.url(2022)]['entry_indexes'] = [9999]
    for cache in caches:
      with self.subTest(cache=cache):
        self.calls = []
        self.assertEqual(full['entries'], self.parse(cache)['entries'])
        self.assertEqual(3, len(self.calls))

  def test_cancellation_and_browser_requirement_propagate(self):
    for exception in (ImportCancelledError('stop'), CamoufoxRequiredError('required')):
      with self.subTest(exception=exception):
        self.failures[self.url(2022)] = exception
        with self.assertRaises(type(exception)):
          self.parse()

  def test_sfadb_correction_failure_is_pending_and_cancellation_propagates(self):
    from parser.hugo import _apply_sfadb_winner_fallback
    full = self.parse()
    entry = deepcopy(full['entries'][0])
    entry.update(result='nominee', position='2022.01')
    notes = []
    def fail(_url):
      raise OSError('offline')
    self.assertFalse(_apply_sfadb_winner_fallback([entry], 2022, fail, None, notes))
    self.assertTrue(notes)
    def cancel(_url):
      raise ImportCancelledError('stop')
    with self.assertRaises(ImportCancelledError):
      _apply_sfadb_winner_fallback([entry], 2022, cancel, None, [])

  def test_all_categories_forward_cache_and_keep_series_contract(self):
    from url_fetcher import hugo
    classes = (
      (hugo.UrlFetcherHugoAwardsNovel, HugoAwardsNovelParser),
      (hugo.UrlFetcherHugoAwardsNovella, HugoAwardsNovellaParser),
      (hugo.UrlFetcherHugoAwardsSeries, HugoAwardsSeriesParser),
      (hugo.UrlFetcherHugoAwardsGraphicStory, HugoAwardsGraphicStoryParser),
      (hugo.UrlFetcherHugoAwardsRelatedWork, HugoAwardsRelatedWorkParser),
      (hugo.UrlFetcherLodestarAward, LodestarAwardParser),
    )
    for fetcher_class, parser_class in classes:
      with self.subTest(fetcher=fetcher_class):
        fetcher = fetcher_class()
        with patch.object(parser_class, 'parse', return_value={'entries': []}) as parse:
          cache = {'entries': []}
          parsed = fetcher.parse('root', cached_parsed=cache, incremental_update=True)
          self.assertIs(cache, parse.call_args.kwargs['cached_parsed'])
          self.assertTrue(parse.call_args.kwargs['incremental_update'])
          self.assertEqual(fetcher_class is hugo.UrlFetcherHugoAwardsSeries,
            parsed.get('match_series', False))


if __name__ == '__main__':
  unittest.main()
