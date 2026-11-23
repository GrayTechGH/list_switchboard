import copy
import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError, ImportCancelledError
from parser.prime_minister_2017 import SHORTLIST_URL, WINNER_URL, transcript_rows
from storage import build_import_cache_data
from url_fetcher.prime_ministers_literary_awards import (
  UrlFetcherPrimeMinistersLiteraryAwardsFiction,
  UrlFetcherPrimeMinistersLiteraryAwardsNonfiction,
)


class PMLA2017Tests(unittest.TestCase):

  def setUp(self):
    self.recipe = UrlFetcherPrimeMinistersLiteraryAwardsFiction()
    self.parser = self.recipe.create_official_parser()
    self.calls, self.errors, self.overrides = [], {}, {}
    self.clock = patch('parser.prime_ministers_literary_awards.datetime')
    self.clock.start().datetime.now.return_value.year = 2026
    self.addCleanup(self.clock.stop)

  def url(self, year):
    return f'https://creative.gov.au/{year}-pmla-winners-shortlist-and-judges'

  def page(self, year, metadata_year=None):
    source_year = metadata_year or year
    count = 5 if year == 2017 else 2
    books = ''.join(f'<h3>Book {source_year} {i}</h3><p>Writer {i}</p>'+
      ('<p>WINNER</p>' if i == 0 else '')+
      f'<p>Shortlist year: {source_year}</p><p>Shortlist category: Fiction</p><p>Published by: Publisher</p>' for i in range(count))
    return f'<title>{year} PMLA</title><h1>{year} PMLA winners</h1><h2>Fiction</h2>'+books

  def transcript(self, shortlist=True, year=2017):
    url = SHORTLIST_URL if shortlist else WINNER_URL
    label = 'shortlist' if shortlist else 'winners'
    books = '<ul>'+''.join(f'<li>Correct {i}, Real Writer {i} (Publisher)</li>' for i in range(5))+'</ul>' if shortlist else '<p>Correct 0, Real Writer 0</p>'
    return f'<html><link rel="canonical" href="{url}"><article class="node--type-transcript"><div class="field--name-body"><p>We announce the {label} for the {year} Prime Minister’s Literary Awards.</p><p>Fiction</p>'+books+'<p>POETRY</p><ul><li>Wrong Category, Wrong Writer</li></ul></div></article></html>'

  def fetch(self, url, **_kwargs):
    self.calls.append(url)
    if url in self.errors:
      raise self.errors[url]
    if url in self.overrides:
      return self.overrides[url]
    if url == self.recipe.URL:
      return '<main>'+''.join(f'<a href="{self.url(y)}">{y}</a>' for y in (2016, 2017, 2018, 2025))+'<p>Prime Minister’s Literary Awards 2026</p><h2>Fiction</h2><p class="card-portrait--content-title">WINNER: New Book by Current Writer</p><p class="card-portrait--content-title">New Finalist by Other Writer</p></main>'
    if url == SHORTLIST_URL:
      return self.transcript()
    if url == WINNER_URL:
      return self.transcript(False)
    year = int(url.rstrip('/').rsplit('/', 1)[1][:4])
    return self.page(year, 2018 if year == 2017 else None)

  def parse(self, cached=None):
    return self.recipe.fetch_and_parse(self.fetch, source_choice=0,
      cached_parsed=cached, incremental_update=cached is not None)

  def cache(self, parsed):
    return build_import_cache_data(self.recipe.source_id, parsed)

  def test_original_official_announcements_replace_only_the_copied_2017_block(self):
    full = self.parse()
    corrected = [r for r in full['entries'] if r['award_year'] == '2017']
    self.assertEqual(5, len(corrected))
    self.assertTrue(all(r['title'].startswith('Correct ') for r in corrected))
    self.assertEqual(['Correct 0'], [r['title'] for r in corrected if r['result'] == 'winner'])
    self.assertEqual(WINNER_URL, corrected[0]['source']['url'])
    self.assertEqual(2, sum(r['award_year'] == '2018' for r in full['entries']))
    self.assertTrue(all(u['complete'] for u in full['incremental_state']['units'].values()))
    self.assertTrue(any('copied 2018' in note for note in full['notes']))

  def test_missing_five_historical_books_recover_with_savings_and_repeat(self):
    full = self.parse()
    self.assertEqual(7, len(self.calls))
    stale = without_unit(self.cache(full), self.url(2017))
    self.assertEqual(len(full['entries']) - 5, len(stale['entries']))
    self.calls.clear()
    updated = self.parse(stale)
    self.assertEqual(full['entries'], updated['entries'])
    self.assertEqual(4, len(self.calls))
    self.calls.clear()
    repeated = self.parse(self.cache(updated))
    self.assertEqual(full['entries'], repeated['entries'])
    self.assertEqual([self.recipe.URL], self.calls)

  def test_a_fixed_2017_creative_page_needs_no_correction_fetch(self):
    self.overrides[self.url(2017)] = self.page(2017)
    full = self.parse()
    self.assertNotIn(SHORTLIST_URL, self.calls)
    self.assertNotIn(WINNER_URL, self.calls)
    self.assertTrue(full['incremental_state']['units'][self.url(2017)]['complete'])

  def test_other_year_conflicts_remain_pending_and_never_use_2017_transcripts(self):
    self.overrides[self.url(2016)] = self.page(2016, 2019)
    full = self.parse()
    self.assertFalse(full['incremental_state']['units'][self.url(2016)]['complete'])
    self.assertTrue(full['incremental_state']['units'][self.url(2017)]['complete'])
    self.assertEqual(1, self.calls.count(SHORTLIST_URL))

  def test_failed_correction_retains_whole_cached_year_pending_retry(self):
    full = self.parse()
    cached = self.cache(full)
    cached['incremental_state']['units'][self.url(2017)]['complete'] = False
    for url in (SHORTLIST_URL, WINNER_URL):
      self.errors = {url: OSError('unavailable')}
      pending = self.parse(copy.deepcopy(cached))
      self.assertEqual(full['entries'], pending['entries'])
      self.assertFalse(pending['incremental_state']['units'][self.url(2017)]['complete'])
    self.errors.clear()
    self.assertEqual(full['entries'], self.parse(self.cache(pending))['entries'])

  def test_critical_errors_propagate_from_both_correction_documents(self):
    for url in (SHORTLIST_URL, WINNER_URL):
      for error in (ImportCancelledError, CamoufoxRequiredError):
        self.errors = {url: error('stop')}
        with self.subTest(url=url, error=error), self.assertRaises(error):
          self.parse()

  def test_partial_shortlist_cannot_certify_2017(self):
    self.overrides[SHORTLIST_URL] = self.transcript().replace('<li>Correct 4, Real Writer 4 (Publisher)</li>', '')
    full = self.parse()
    self.assertFalse(full['incremental_state']['units'][self.url(2017)]['complete'])
    self.assertFalse(any(r['award_year'] == '2017' for r in full['entries']))

  def test_winner_must_match_a_shortlisted_work(self):
    self.overrides[WINNER_URL] = self.transcript(False).replace('Correct 0, Real Writer 0', 'Unknown Work, Unknown Writer')
    self.assertFalse(self.parse()['incremental_state']['units'][self.url(2017)]['complete'])

  def test_transcript_year_kind_canonical_and_category_are_validated(self):
    for html in (self.transcript(year=2018), self.transcript(False),
        self.transcript().replace(SHORTLIST_URL, 'https://example.org/other'),
        self.transcript().replace('<p>Fiction</p>', '<p>Poetry</p>')):
      with self.subTest(html=html[:80]), self.assertRaises(ValueError):
        transcript_rows(self.parser, html, SHORTLIST_URL, True)

  def test_title_commas_and_creator_suffixes_survive_bounded_split(self):
    html = self.transcript().replace('Correct 0, Real Writer 0', 'Title, With Comma, Writer, Jr.')
    row = transcript_rows(self.parser, html, SHORTLIST_URL, True)[0]
    self.assertEqual(('Title, With Comma', 'Writer, Jr.'), (row['title'], row['author']))

  def test_other_category_source_strategy_is_unchanged(self):
    other = UrlFetcherPrimeMinistersLiteraryAwardsNonfiction().create_official_parser()
    self.assertEqual('pmla-annual-source-rows-v1', other.UPDATE_STRATEGY)
    self.assertEqual((), other.EXTRA_SOURCE_SCOPE)
    self.assertNotEqual(other.UPDATE_STRATEGY, self.parser.UPDATE_STRATEGY)

  def test_old_fiction_cache_strategy_forces_full_rebuild(self):
    full = self.parse()
    cached = self.cache(full)
    cached['incremental_state']['strategy'] = 'pmla-annual-source-rows-v1'
    self.calls.clear()
    rebuilt = self.parse(cached)
    self.assertEqual(full['entries'], rebuilt['entries'])
    self.assertEqual(7, len(self.calls))

  def test_unrecognized_partial_copy_cannot_bypass_year_validation(self):
    bad = self.page(2017, 2018)
    start = bad.index('<h3>Book 2018 4</h3>')
    self.overrides[self.url(2017)] = bad[:start]
    full = self.parse()
    self.assertFalse(full['incremental_state']['units'][self.url(2017)]['complete'])
    self.assertNotIn(SHORTLIST_URL, self.calls)

  def test_known_correction_does_not_apply_to_other_hosts(self):
    with self.assertRaises(ValueError):
      self.parser.annual_rows(self.page(2017, 2018),
        'https://example.org/2017-pmla-winners-shortlist-and-judges', 2017, self.fetch)
    self.assertEqual([], self.calls)


if __name__ == '__main__':
  unittest.main()
