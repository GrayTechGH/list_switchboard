import unittest

from _dev_tools import test_import_matching
from errors import ImportCancelledError, CamoufoxRequiredError
from storage import build_import_cache_data
from url_fetcher.generic import UrlFetcherError
from url_fetcher.national_book_award import (
  UrlFetcherNationalBookAwardFiction, UrlFetcherNationalBookAwardNonfiction,
  UrlFetcherNationalBookAwardYoungPeoplesLiterature,
)


RECIPES = (UrlFetcherNationalBookAwardFiction, UrlFetcherNationalBookAwardNonfiction,
  UrlFetcherNationalBookAwardYoungPeoplesLiterature)


class NationalBookAwardSupplementTests(unittest.TestCase):

  def setUp(self):
    self.recipe = UrlFetcherNationalBookAwardFiction()
    self.calls = []
    self.failed = {2023}
    self.wiki_error = OSError('Wikipedia offline')
    self.wiki_html = self.wikipedia()

  def year_url(self, year):
    return f'https://www.nationalbook.org/awards-prizes/national-book-awards-{year}/?cat={self.recipe.CATEGORY_SLUG}'

  def wikipedia(self, years=(2023,2024)):
    return '<table><tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>'+''.join(
      f'<tr><td>{year}</td><td>Supplement Writer</td><td>Wikipedia {year}</td><td>Winner</td></tr>'
      for year in years)+'</table>'

  def fetch(self, url):
    self.calls.append(url)
    if url == self.recipe.URL:
      return ''.join(f'<a href="https://www.nationalbook.org/awards-prizes/national-book-awards-{year}/">{year}</a>' for year in (2023,2024))
    if url == self.recipe.WIKIPEDIA_URL:
      if self.wiki_error is not None:
        raise self.wiki_error
      return self.wiki_html
    year = next(year for year in (2023,2024) if url == self.year_url(year))
    if year in self.failed:
      raise OSError(f'Foundation {year} offline')
    return f'<title>National Book Awards {year}</title><div class="winner-book"><div class="winner-book-item"><div class="book-data"><h1><a href="/books/official-{year}/">Official {year}</a></h1><h2>Foundation Writer</h2></div></div></div>'

  def parse(self, **kwargs):
    return self.recipe.fetch_and_parse(self.fetch, **kwargs)

  def test_wikipedia_network_failure_keeps_usable_foundation_in_all_three_recipes(self):
    for cls in RECIPES:
      with self.subTest(recipe=cls.source_id):
        self.recipe = cls()
        parsed = self.parse()
        self.assertEqual(['Official 2024'], [e['title'] for e in parsed['entries']])
        self.assertEqual(self.recipe.URL, parsed['source']['url'])
        self.assertTrue(any('Wikipedia supplement unavailable' in note for note in parsed['notes']))

  def test_empty_or_invalid_wikipedia_response_is_nonfatal(self):
    self.wiki_error = None
    for payload in ('', '<html><title>Access denied</title></html>'):
      with self.subTest(payload=payload):
        self.wiki_html = payload
        parsed = self.parse()
        self.assertEqual(['Official 2024'], [e['title'] for e in parsed['entries']])
        self.assertTrue(any('supplement unavailable' in note for note in parsed['notes']))

  def test_successful_supplement_only_fills_failed_years_with_own_provenance(self):
    self.wiki_error = None
    parsed = self.parse()
    self.assertEqual(['Wikipedia 2023','Official 2024'], [e['title'] for e in parsed['entries']])
    self.assertEqual(self.recipe.WIKIPEDIA_URL, parsed['entries'][0]['source']['url'])
    self.assertEqual('https://www.nationalbook.org/books/official-2024/', parsed['entries'][1]['source']['url'])
    self.assertEqual(self.recipe.URL, parsed['source']['url'])
    self.assertFalse(parsed['incremental_state']['units'][self.year_url(2023)]['complete'])

  def test_successful_supplement_cache_roundtrip_retains_rows_during_later_outage(self):
    self.wiki_error = None
    full = self.parse()
    self.wiki_error = OSError('Wikipedia offline again')
    self.calls.clear()
    updated = self.parse(cached_parsed=build_import_cache_data(self.recipe.source_id, full), incremental_update=True)
    self.assertEqual(full['entries'], updated['entries'])
    self.assertIn(self.year_url(2023), self.calls)
    self.assertFalse(updated['incremental_state']['units'][self.year_url(2023)]['complete'])
    self.assertTrue(any('supplement unavailable' in note for note in updated['notes']))

  def test_recovered_foundation_year_replaces_supplement_without_requesting_wikipedia(self):
    self.wiki_error = None
    full = self.parse()
    self.failed.clear()
    self.wiki_error = OSError('Wikipedia is still unavailable')
    self.calls.clear()
    updated = self.parse(cached_parsed=build_import_cache_data(self.recipe.source_id,full),incremental_update=True)
    self.assertEqual(['Official 2023','Official 2024'],[e['title'] for e in updated['entries']])
    self.assertTrue(updated['incremental_state']['units'][self.year_url(2023)]['complete'])
    self.assertNotIn(self.recipe.WIKIPEDIA_URL,self.calls)

  def test_explicit_foundation_also_survives_supplement_failure(self):
    parsed = self.parse(source_choice=0)
    self.assertEqual(['Official 2024'], [e['title'] for e in parsed['entries']])
    self.assertEqual(1, self.calls.count(self.recipe.WIKIPEDIA_URL))

  def test_disabled_fallbacks_skip_wikipedia_and_keep_partial_foundation(self):
    parsed = self.parse(disable_fallbacks=True)
    self.assertEqual(['Official 2024'], [e['title'] for e in parsed['entries']])
    self.assertNotIn(self.recipe.WIKIPEDIA_URL, self.calls)

  def test_complete_foundation_does_not_request_supplement(self):
    self.failed.clear()
    parsed = self.parse()
    self.assertEqual(['Official 2023','Official 2024'], [e['title'] for e in parsed['entries']])
    self.assertNotIn(self.recipe.WIKIPEDIA_URL, self.calls)

  def test_wikipedia_has_no_requested_year_without_overriding_good_foundation(self):
    self.wiki_error = None
    self.wiki_html = self.wikipedia(years=(2024,))
    parsed = self.parse()
    self.assertEqual(['Official 2024'], [e['title'] for e in parsed['entries']])
    self.assertTrue(any('no supplement' in note and '2023' in note for note in parsed['notes']))

  def test_wikipedia_cancellation_and_required_browser_errors_propagate(self):
    for error in (ImportCancelledError('stop'),CamoufoxRequiredError('required')):
      with self.subTest(error=type(error).__name__):
        self.wiki_error = error
        with self.assertRaises(type(error)):
          self.parse()

  def test_no_usable_foundation_uses_existing_whole_source_fallback(self):
    self.failed = {2023,2024}
    self.wiki_error = None
    parsed = self.parse()
    self.assertEqual(['Wikipedia 2023','Wikipedia 2024'], [e['title'] for e in parsed['entries']])
    self.assertEqual(self.recipe.WIKIPEDIA_URL, parsed['source']['url'])
    self.assertEqual(1, self.calls.count(self.recipe.WIKIPEDIA_URL))

  def test_total_failure_still_reports_both_sources(self):
    self.failed = {2023,2024}
    with self.assertRaisesRegex(UrlFetcherError,'Wikipedia offline'):
      self.parse()

  def test_explicit_wikipedia_does_not_fetch_foundation(self):
    self.wiki_error = None
    parsed = self.parse(source_choice=1)
    self.assertEqual([self.recipe.WIKIPEDIA_URL], self.calls)
    self.assertEqual(self.recipe.WIKIPEDIA_URL, parsed['source']['url'])

  def test_cached_foundation_year_survives_both_source_failures(self):
    self.failed.clear()
    full = self.parse()
    cached = build_import_cache_data(self.recipe.source_id,full)
    cached['incremental_state']['units'][self.year_url(2023)]['complete'] = False
    self.failed = {2023}
    updated = self.parse(cached_parsed=cached,incremental_update=True)
    self.assertEqual(full['entries'],updated['entries'])
    self.assertFalse(updated['incremental_state']['units'][self.year_url(2023)]['complete'])


if __name__ == '__main__':
  unittest.main()
