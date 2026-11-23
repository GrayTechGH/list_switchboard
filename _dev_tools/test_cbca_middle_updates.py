"""Future-year fixtures exercise Middle Readers; no current live pass claimed."""
import json
import unittest

from _dev_tools import test_cbca_incremental as fixtures
from _dev_tools.verify_import_updates import without_unit
from parser.cbca_book_of_the_year import AWARDS_URL, PDF_URL, winners_url
from url_fetcher.cbca_book_of_the_year import UrlFetcherCBCABookOfTheYearMiddleReaders


class CBCAMiddleUpdateTests(unittest.TestCase):

  def setUp(self):
    self.fixture = fixtures.CBCAIncrementalTests()
    self.fixture.setUp()
    self.addCleanup(self.fixture.doCleanups)
    self.fixture.recipe = UrlFetcherCBCABookOfTheYearMiddleReaders()
    from parser import cbca_updates
    cbca_updates.date.today.return_value.year = 2029
    self.fixture.years = [2027, 2028, 2029]
    self.fixture.overrides.update({winners_url(year): self.fixture.current(year, 'winners')
      for year in self.fixture.years})
    original_fetch = self.fixture.fetch
    def fetch(url, **kwargs):
      payload = original_fetch(url, **kwargs)
      if url == AWARDS_URL:
        payload = '<main><h1>Book of the Year Awards</h1>' + ''.join(
          f'<a href="https://cbca.org.au/{year}-{kind}/">{year} {kind}</a>'
          for year in [2025] + self.fixture.years for kind in ('shortlist', 'winners')) + '</main>'
      return payload.replace('Older Readers', 'Middle Readers')
    self.fixture.fetch = fetch
    self.parse = lambda old=None: self.fixture.recipe.fetch_and_parse(fetch,
      cached_parsed=old, incremental_update=old is not None)

  def cache(self, parsed):
    return json.loads(json.dumps(self.fixture.cache(parsed)))

  def test_missing_real_year_future_fixture_recovers_with_savings(self):
    full = self.parse()
    self.assertEqual(18, len(full['entries']))
    self.assertEqual(8, len(self.fixture.calls))
    stale = without_unit(self.cache(full), 'year:2027')
    self.assertEqual(12, len(stale['entries']))
    self.fixture.calls.clear()
    updated = self.parse(stale)
    self.assertEqual(full['entries'], updated['entries'])
    self.assertEqual(6, len(self.fixture.calls))
    self.fixture.calls.clear()
    repeated = self.parse(self.cache(updated))
    self.assertEqual(full['entries'], repeated['entries'])
    self.assertEqual(4, len(self.fixture.calls))
    self.assertTrue(all(unit['complete'] for unit in repeated['incremental_state']['units'].values()))
    self.assertFalse(self.fixture.recipe.SUPPORTS_INCREMENTAL_UPDATE)

  def test_pre_category_pdf_and_annual_links_are_not_requested(self):
    full = self.parse()
    urls = [url for url, _transport in self.fixture.calls]
    self.assertNotIn(PDF_URL, urls)
    self.assertFalse(any('/2025-' in url or '/2026-' in url or '/2022-' in url for url in urls))
    self.assertEqual([2027, 2028, 2029], sorted({int(row['award_year']) for row in full['entries']}))

  def test_pre_2027_roster_is_rejected_without_relabelling(self):
    self.fixture.years = [2026]
    with self.assertRaisesRegex(Exception, 'first 2027 award'):
      self.parse()

  def test_current_no_results_does_not_create_empty_verification_baseline(self):
    self.fixture.years = []
    self.fixture.overrides[self.fixture.recipe.URL] = f'<main><a href="{PDF_URL}">PDF of all prior winners</a><details><summary>2026</summary><h3>Younger Readers</h3></details></main>'
    with self.assertRaisesRegex(Exception, 'no available results'):
      self.parse()

  def test_pre_2027_category_absence_is_expected_and_fetches_no_other_years(self):
    from parser import cbca_updates
    cbca_updates.date.today.return_value.year = 2026
    self.fixture.years = []
    self.fixture.overrides[self.fixture.recipe.URL] = f'<main><a href="{PDF_URL}">PDF of all prior winners</a><details><summary>2026</summary><h3>Younger Readers</h3></details></main>'
    parsed = self.parse()
    self.assertEqual([], parsed['entries'])
    self.assertEqual([self.fixture.recipe.URL], [url for url, _transport in self.fixture.calls])
    self.assertTrue(any('2027 Awards' in note for note in parsed['notes']))
    self.assertFalse(self.fixture.recipe.SUPPORTS_INCREMENTAL_UPDATE)

  def test_failed_annual_year_retains_its_complete_roster_pending_retry(self):
    full = self.parse()
    self.fixture.errors['https://cbca.org.au/2029-shortlist/'] = OSError('unavailable')
    failed = self.parse(self.cache(full))
    self.assertEqual(full['entries'], failed['entries'])
    self.assertFalse(failed['incremental_state']['units']['year:2029']['complete'])
    self.fixture.errors.clear()
    recovered = self.parse(self.cache(failed))
    self.assertEqual(full['entries'], recovered['entries'])
    self.assertTrue(recovered['incremental_state']['units']['year:2029']['complete'])

  def test_archive_paging_gap_recovers_annual_history_from_2027(self):
    self.fixture.years = [2029]
    full = self.parse()
    self.assertEqual(18, len(full['entries']))
    urls = [url for url, _transport in self.fixture.calls]
    self.assertIn('https://cbca.org.au/2027-shortlist/', urls)
    self.assertIn(winners_url(2028), urls)
    self.assertNotIn('https://cbca.org.au/2026-shortlist/', urls)


if __name__ == '__main__':
  unittest.main()
