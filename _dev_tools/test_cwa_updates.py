import unittest
from urllib.parse import parse_qs, urlsplit

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError, CamoufoxRequiredError
from storage import build_import_cache_data
from url_fetcher.cwa import (UrlFetcherCWAGoldDagger, UrlFetcherCWAIanFlemingSteelDagger,
  UrlFetcherCWAHistoricalDagger, UrlFetcherCWACrimeFictionInTranslationDagger)


class CWAUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe = UrlFetcherCWAGoldDagger()
    self.recipe.START_YEAR = 2022
    self.years, self.calls, self.failures = [2022, 2023, 2024], [], {}
    self.open_years, self.promoted = set(), set()

  def card(self, year, result):
    title = f'{result} {year}'
    if year in self.promoted and result == 'Winner':
      title = f'Shortlisted {year}'
    return f'<a href="https://thecwa.co.uk/past-winners/{title.replace(" ", "-")}/">'\
      f'<span class="title">{title}</span><span class="author">Writer One</span>'\
      f'<span>{self.recipe.CATEGORY}</span><span>{year} | {result}</span></a>'

  def fetch(self, url):
    self.calls.append(url)
    q = parse_qs(urlsplit(url).query)
    first = int(q.get('from_year', [str(max(self.years))])[0])
    last = int(q.get('to_year', [str(first)])[0])
    if first in self.failures:
      raise self.failures[first]
    allowed = q.get('past_winners_accolades[]')
    rows = []
    for year in reversed(self.years):
      if not first <= year <= last:
        continue
      for result in ('Winner', 'Shortlisted', 'Longlisted'):
        if year in self.open_years and result == 'Winner':
          continue
        if year in self.promoted and result == 'Shortlisted':
          continue
        if allowed and result.casefold() not in allowed:
          continue
        rows.append(self.card(year, result))
    return ''.join(rows)

  def parse(self, old=None):
    return self.recipe.fetch_and_parse(self.fetch, source_choice=0,
      cached_parsed=old, incremental_update=old is not None)

  def cache(self, parsed):
    return build_import_cache_data(self.recipe.source_id, parsed)

  def test_all_four_categories_recover_missing_latest_and_new_year(self):
    for factory in (UrlFetcherCWAGoldDagger, UrlFetcherCWAIanFlemingSteelDagger,
        UrlFetcherCWAHistoricalDagger, UrlFetcherCWACrimeFictionInTranslationDagger):
      with self.subTest(recipe=factory.source_id):
        self.recipe = factory()
        self.recipe.START_YEAR = 2022
        self.years = [2022, 2023, 2024]
        full = self.parse()
        old = without_unit(self.cache(full), '2024')
        self.calls.clear()
        update = self.parse(old)
        self.assertEqual(full['entries'], update['entries'])
        self.assertEqual(4 if self.recipe.ARCHIVE_BY_ACCOLADE else 2, len(self.calls))
        self.assertTrue(all('from_year=2022' not in url and 'from_year=2023' not in url for url in self.calls))
        self.years.append(2025)
        self.calls.clear()
        update = self.parse(self.cache(full))
        self.assertEqual(4 if self.recipe.ARCHIVE_BY_ACCOLADE else 2, len(self.calls))
        self.assertEqual(self.parse()['entries'], update['entries'])
        self.assertFalse(update['match_series'])
        official, alternate = self.recipe.source_attempts()
        self.assertTrue(official.supports_incremental)
        self.assertFalse(alternate.supports_incremental)

  def test_winnerless_promotion_and_failed_pending_history(self):
    self.open_years.add(2023)
    full = self.parse()
    self.open_years.clear()
    self.promoted.add(2023)
    update = self.parse(self.cache(full))
    self.assertEqual(self.parse()['entries'], update['entries'])
    promoted = [e for e in update['entries'] if e['award_year']=='2023' and e['result']=='winner']
    self.assertEqual('2023', promoted[0]['position'])
    old = self.cache(update)
    old['incremental_state']['units']['2022']['complete'] = False
    self.failures[2022] = OSError('offline')
    pending = self.parse(old)
    self.assertEqual(update['entries'], pending['entries'])
    self.assertFalse(pending['incremental_state']['units']['2022']['complete'])
    self.assertTrue(pending['notes'])
    self.failures.clear()
    self.assertEqual(update['entries'], self.parse(self.cache(pending))['entries'])

  def test_legacy_scope_changes_and_cancellation_rebuild_or_propagate(self):
    full = self.parse()
    wrong = self.cache(full)
    wrong['incremental_state']['source_key'] = 'different category or archive window'
    for old in ({'entries': full['entries']}, wrong):
      self.calls.clear()
      self.assertEqual(full['entries'], self.parse(old)['entries'])
      self.assertTrue(any('from_year=2022' in url for url in self.calls))
    old = self.cache(full)
    old['incremental_state']['units']['2022']['complete'] = False
    for error in (ImportCancelledError('stop'), CamoufoxRequiredError('required')):
      self.failures[2022] = error
      for cache in (None, old):
        with self.subTest(error=type(error).__name__, full=cache is None), self.assertRaises(type(error)):
          self.parse(cache)


if __name__ == '__main__':
  unittest.main()
