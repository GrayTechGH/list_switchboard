import unittest

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError, CamoufoxRequiredError
from storage import build_import_cache_data
from url_fetcher.seiun import UrlFetcherSeiunJapaneseLongWork, UrlFetcherSeiunTranslatedNovel


class SeiunUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe = UrlFetcherSeiunJapaneseLongWork()
    self.years, self.calls, self.failures = [2022, 2023, 2024], [], {}
    self.open_years = set()
    self.promoted = set()
    self.payloads = {}

  def url(self, year):
    return f'https://www.isfdb.org/cgi-bin/ay.cgi?61+{year}'

  def fetch(self, url, **options):
    self.calls.append(url)
    if url in self.failures:
      raise self.failures[url]
    if url in self.payloads:
      return self.payloads[url]
    if url == self.recipe.URL:
      return ''.join(f'<a href="{self.url(y)}">{y}</a>' for y in self.years)
    year = next(y for y in self.years if self.url(y) == url)
    level = 'Nomination' if year in self.open_years else 'Win'
    title = 'Promoted' if year in self.promoted else 'Work'
    return f'<title>{year} Seiun Awards</title><table>'\
      '<tr><th>Year</th><th>Level</th><th>Title</th><th>Author</th><th>Category</th></tr>'\
      f'<tr><td>{year}</td><td>{level}</td><td>{title} {year}</td><td>Writer One</td><td>Best Japanese Long Story</td></tr>'\
      f'<tr><td>{year}</td><td>Win</td><td>Excluded Comic</td><td>Other Writer</td><td>Best Comics</td></tr></table>'

  def parse(self, old=None):
    return self.recipe.fetch_and_parse(self.fetch, source_choice=0,
      cached_parsed=old, incremental_update=old is not None)

  def cache(self, parsed):
    return build_import_cache_data(self.recipe.source_id, parsed)

  def test_japanese_missing_year_recovery_repeat_and_new_year(self):
    full = self.parse()
    self.assertEqual(4, len(self.calls))
    old = without_unit(self.cache(full), self.url(2022))
    self.calls.clear()
    update = self.parse(old)
    self.assertEqual(full['entries'], update['entries'])
    self.assertEqual([self.recipe.URL, self.url(2022), self.url(2024)], self.calls)
    self.assertFalse(update['match_series'])
    old = self.cache(update)
    self.calls.clear()
    self.assertEqual(full['entries'], self.parse(old)['entries'])
    self.assertEqual([self.recipe.URL, self.url(2024)], self.calls)
    self.years.append(2025)
    self.calls.clear()
    update = self.parse(old)
    self.assertEqual([self.recipe.URL, self.url(2025)], self.calls)
    self.assertEqual(self.parse()['entries'], update['entries'])
    self.assertTrue(all('Excluded Comic' != row['title'] for row in update['entries']))

  def test_winnerless_historical_year_refreshes_and_promotes_winner(self):
    self.open_years.add(2022)
    old = self.cache(self.parse())
    self.open_years.clear()
    self.promoted.add(2022)
    self.calls.clear()
    update = self.parse(old)
    self.assertEqual([self.recipe.URL, self.url(2022), self.url(2024)], self.calls)
    self.assertEqual(('Promoted 2022', 'winner', '2022'),
      tuple(update['entries'][0][key] for key in ('title','result','position')))

  def test_malformed_and_failed_years_retain_pending_history(self):
    full = self.parse()
    old = self.cache(full)
    old['incremental_state']['units'][self.url(2022)]['complete'] = False
    for failure in (OSError('offline'),):
      self.failures[self.url(2022)] = failure
      update = self.parse(old)
      self.assertEqual(full['entries'], update['entries'])
      self.assertFalse(update['incremental_state']['units'][self.url(2022)]['complete'])
      self.assertTrue(update['notes'])
    self.failures.clear()
    self.assertEqual(full['entries'], self.parse(self.cache(update))['entries'])
    for error in (ImportCancelledError('stop'), CamoufoxRequiredError('required')):
      self.failures[self.url(2022)] = error
      with self.assertRaises(type(error)):
        self.parse(old)

  def test_legacy_scope_mismatch_refetch_and_other_isfdb_recipes_stay_opted_out(self):
    full = self.parse()
    wrong = self.cache(full)
    wrong['incremental_state']['source_key'] = 'foreign category'
    for old in ({'entries': full['entries']}, wrong):
      self.calls.clear()
      self.assertEqual(full['entries'], self.parse(old)['entries'])
      self.assertEqual(4, len(self.calls))
    from url_fetcher import available_url_fetchers
    opted = [r.source_id for r in available_url_fetchers() if getattr(r, 'ENABLE_ISFDB_INCREMENTAL', False)]
    self.assertEqual(['seiun_japanese_long_work'], opted)

  def test_wrong_year_or_challenge_retains_history_but_verified_absence_is_reusable(self):
    full = self.parse()
    old = self.cache(full)
    old['incremental_state']['units'][self.url(2022)]['complete'] = False
    for payload in ('<h1>Verification required</h1>',
        self.fetch(self.url(2022)).replace('<title>2022','<title>2023')):
      self.payloads[self.url(2022)] = payload
      update = self.parse(old)
      self.assertEqual(full['entries'],update['entries'])
      self.assertFalse(update['incremental_state']['units'][self.url(2022)]['complete'])
    self.payloads[self.url(2022)] = '<title>2022 Seiun Awards</title><table><tr><td><a href="/cgi-bin/award_category.cgi?1236">Best Comics</a></td></tr></table>'
    absent = self.parse()
    self.assertTrue(absent['incremental_state']['units'][self.url(2022)]['complete'])
    self.calls.clear()
    self.assertEqual(absent['entries'],self.parse(self.cache(absent))['entries'])
    self.assertNotIn(self.url(2022),self.calls)

  def test_translated_sfadb_reuses_years_without_changing_original_work_fallback(self):
    self.recipe = UrlFetcherSeiunTranslatedNovel()
    def fetch(url, **options):
      self.calls.append(url)
      if url == self.recipe.URL:
        return ''.join(f'<a href="{self.recipe.URL}_{y}">{y}</a>' for y in self.years)
      year = next(y for y in self.years if url == f'{self.recipe.URL}_{y}')
      return f'<title>sfadb: Seiun Awards {year}</title><div class="categoryblock">'\
        f'<div class="category">Foreign Novel</div><ul><li>Winner: <b>Work {year}</b>, '\
        '<a href="Writer">Writer One</a></li></ul></div>'
    full = self.recipe.fetch_and_parse(fetch, source_choice=0)
    old = without_unit(self.cache(full), f'{self.recipe.URL}_2022')
    self.calls.clear()
    update = self.recipe.fetch_and_parse(fetch, source_choice=0,
      cached_parsed=old, incremental_update=True)
    self.assertEqual(full['entries'], update['entries'])
    self.assertEqual(3, len(self.calls))
    self.assertTrue(self.recipe.RESOLVE_ISFDB_ORIGINAL_WORKS)
    primary, fallback = self.recipe.source_attempts()
    self.assertTrue(primary.supports_incremental)
    self.assertFalse(fallback.supports_incremental)


if __name__ == '__main__':
  unittest.main()
