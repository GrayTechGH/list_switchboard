import unittest

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError, CamoufoxRequiredError
from parser.british_fantasy import BFS_WINNERS_URL, BFS_AWARDS_URL, BFS_LEGACY_SHORTLIST_URL, SFADB_URL
from storage import build_import_cache_data
from url_fetcher.british_fantasy import UrlFetcherBritishFantasyHorrorNovel


class BritishFantasyUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe = UrlFetcherBritishFantasyHorrorNovel()
    self.years = [1972, 1973, 2024, 2025]
    self.calls = []
    self.failures = {}
    self.corrected = False

  def url(self, year):
    return f'{SFADB_URL}_{year}'

  def fetch(self, url):
    self.calls.append(url)
    if url in self.failures:
      raise self.failures[url]
    if url == BFS_WINNERS_URL:
      return ''.join(f'<p>{y}</p><ul><li>{self.recipe.CATEGORY}: '
        f'{"Corrected" if self.corrected and y == 2024 else "Official"} {y}, Writer One</li></ul>'
        for y in self.years if y >= 2024)
    if url == BFS_AWARDS_URL:
      return '<p>British Fantasy Awards information</p>'
    if url == BFS_LEGACY_SHORTLIST_URL:
      return f'<h1>British Fantasy Awards Shortlist 2025</h1><h2>{self.recipe.CATEGORY}</h2>'\
        '<ul><li>Current Finalist by Writer Two</li></ul>'
    if url == SFADB_URL:
      return ''.join(f'<a href="{self.url(y)}">{y}</a>' for y in self.years)
    year = next(y for y in self.years if url == self.url(y))
    category = self.recipe.CATEGORY if year >= 2024 else 'Short Story'
    return f'<title>sfadb: British Fantasy Awards {year}</title><div class="categoryblock">'\
      f'<div class="category">{category}</div><ul>'\
      f'<li>Winner: <b>Official {year}</b>, <a href="Writer_One">Writer One</a> (Publisher)</li>'\
      f'<li><b>Historical Finalist {year}</b>, <a href="Writer_Three">Writer Three</a> (Publisher)</li></ul></div>'

  def parse(self, cache=None):
    return self.recipe.fetch_and_parse(self.fetch, cached_parsed=cache,
      incremental_update=cache is not None)

  def cache(self, parsed):
    return build_import_cache_data(self.recipe.source_id, parsed)

  def test_empty_history_reused_and_missing_real_ballot_recovered(self):
    full = self.parse()
    self.assertEqual(8, len(self.calls))
    old = without_unit(self.cache(full), self.url(2024))
    self.assertLess(len(old['entries']), len(full['entries']))
    self.calls = []
    update = self.parse(old)
    self.assertEqual(full['entries'], update['entries'])
    self.assertEqual(6, len(self.calls))
    self.assertNotIn(self.url(1972), self.calls)
    self.calls = []
    self.assertEqual(full['entries'], self.parse(self.cache(update))['entries'])
    self.assertEqual(6, len(self.calls))

  def test_new_year_and_changed_official_winner_preserve_source_precedence(self):
    old = self.cache(self.parse())
    self.years.append(2026)
    self.corrected = True
    update = self.parse(old)
    self.assertEqual(self.parse()['entries'], update['entries'])
    winners = [e for e in update['entries'] if e['result'] == 'winner' and e['award_year'] == '2024']
    self.assertEqual(['Corrected 2024'], [e['title'] for e in winners])
    self.assertEqual(BFS_WINNERS_URL, winners[0]['source']['url'])

  def test_failed_ballot_and_failed_root_keep_merged_history_pending(self):
    full = self.parse()
    for url in (self.url(2024), SFADB_URL):
      with self.subTest(url=url):
        self.failures[url] = OSError('offline')
        update = self.parse(self.cache(full))
        self.assertEqual(full['entries'], update['entries'])
        self.assertTrue(any(not u['complete'] for u in update['incremental_state']['units'].values()))
        self.failures.clear()
        # A second failed year after root recovery still retains the old rows.
        self.failures[self.url(2024)] = OSError('still offline')
        pending = self.parse(self.cache(update))
        self.assertEqual(full['entries'], pending['entries'])
        self.failures.clear()
        self.assertEqual(full['entries'], self.parse(self.cache(pending))['entries'])

  def test_legacy_or_changed_configuration_rebuilds_empty_year_bookkeeping(self):
    full = self.parse()
    wrong = self.cache(full)
    wrong['incremental_state']['source_key'] = 'different category limits'
    for old in ({'entries': full['entries']}, wrong):
      self.calls = []
      self.assertEqual(full['entries'], self.parse(old)['entries'])
      self.assertEqual(8, len(self.calls))

  def test_cancellation_and_browser_requirement_escape_optional_source_handlers(self):
    for url in (BFS_AWARDS_URL, BFS_LEGACY_SHORTLIST_URL, SFADB_URL, self.url(2024)):
      for error in (ImportCancelledError('stop'), CamoufoxRequiredError('required')):
        with self.subTest(url=url, error=error):
          self.failures[url] = error
          with self.assertRaises(type(error)):
            self.parse()
          self.failures.clear()

  def test_all_six_active_categories_preserve_full_entries(self):
    from url_fetcher import available_url_fetchers
    recipes = [r for r in available_url_fetchers() if r.source_id.startswith('british_fantasy_')
      and 'discontinued' not in r.NAME]
    self.assertEqual(6, len(recipes))
    for self.recipe in recipes:
      with self.subTest(recipe=self.recipe.source_id):
        full = self.parse()
        self.calls = []
        update = self.parse(self.cache(full))
        self.assertEqual(full['entries'], update['entries'])
        self.assertEqual(6, len(self.calls))


if __name__ == '__main__':
  unittest.main()
