import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError,ImportCancelledError
from storage import build_import_cache_data
from url_fetcher.james_tait_black import (
  SHORTLIST_URL_2024, SHORTLIST_URL_2026,
  UrlFetcherJamesTaitBlackFiction,UrlFetcherJamesTaitBlackBiography,
)


def one_post_recipe(cls=UrlFetcherJamesTaitBlackFiction):
  recipe = cls()
  recipe.SHORTLIST_URLS = ('https://james-tait-black.ed.ac.uk/test-shortlist',)
  recipe.SHORTLIST_SPECS = {}
  return recipe


class JamesTaitUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=one_post_recipe()
    self.calls,self.failures=[],{}
    self.years=[2023,2024,2025]
    self.published=2025
    self.clock=patch('parser.james_tait_black.datetime')
    self.dates=self.clock.start()
    self.dates.datetime.now.return_value.year=2026
    self.addCleanup(self.clock.stop)

  def fetch(self,url,**kwargs):
    self.calls.append(url)
    if url in self.failures: raise self.failures[url]
    if url==self.recipe.URL:
      return '<ul>'+''.join(f'<li>Writer One - Winner {year} (Publisher) - {year}</li>' for year in self.years)+'</ul>'
    return f'<h1>Indie talent</h1><h2>{self.recipe.CATEGORY}</h2><p>Writer One\u2019s Winner {self.published-1} (Publisher)</p><p>Writer Two\u2019s Other {self.published-1} (Publisher)</p><h2>Another Category</h2><p>Excluded Writer\u2019s Wrong Book (Publisher)</p><div><p>This article was published on <time datetime="{self.published}-03-18T12:00:00Z">Wednesday 18 March {self.published}</time></p></div>'

  def parse(self,old=None):
    return self.recipe.fetch_and_parse(self.fetch,cached_parsed=old,incremental_update=old is not None)

  def cache(self,parsed):
    return build_import_cache_data(self.recipe.source_id,parsed)

  def test_both_categories_closed_post_and_missing_archive_entries_recover_in_one_request(self):
    for cls in (UrlFetcherJamesTaitBlackFiction,UrlFetcherJamesTaitBlackBiography):
      self.recipe=one_post_recipe(cls)
      self.calls.clear()
      full=self.parse()
      self.assertEqual(4,len(full['entries']))
      self.assertEqual(2,len(self.calls))
      old=without_unit(self.cache(full),'winners')
      self.calls.clear()
      update=self.parse(old)
      self.assertEqual(full['entries'],update['entries'])
      self.assertEqual([self.recipe.URL],self.calls)
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])
      self.assertEqual([self.recipe.URL],self.calls)

  def test_current_unsettled_and_latest_cycle_post_stays_fresh(self):
    for published,years in ((2026,[2023,2024]),(2026,[2023,2024,2025]),(2027,[2023,2024,2025])):
      self.published,self.years=published,years
      old=self.cache(self.parse())
      self.calls.clear()
      self.parse(old)
      self.assertEqual([self.recipe.URL,self.recipe.SHORTLIST_URLS[0]],self.calls)

  def test_new_winner_cycle_does_not_invalidate_closed_post_reuse(self):
    old=self.cache(self.parse())
    self.years.append(2026)
    self.dates.datetime.now.return_value.year=2027
    self.calls.clear()
    update=self.parse(old)
    self.assertEqual([self.recipe.URL],self.calls)
    self.assertEqual(self.parse()['entries'],update['entries'])

  def test_failed_post_retains_original_rows_pending_and_recovers(self):
    full=self.parse()
    old=self.cache(full)
    url=self.recipe.SHORTLIST_URLS[0]
    old['incremental_state']['units'][url]['complete']=False
    self.failures[url]=OSError('offline')
    pending=self.parse(old)
    self.assertEqual(full['entries'],pending['entries'])
    self.assertFalse(pending['incremental_state']['units'][url]['complete'])
    self.assertTrue(pending['notes'])
    self.failures.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(pending))['entries'])

  def test_legacy_wrong_scope_and_critical_errors(self):
    full=self.parse()
    wrong=self.cache(full)
    wrong['incremental_state']['source_key']='other category'
    for old in ({'entries':full['entries']},wrong,['invalid cache']):
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(old)['entries'])
      self.assertEqual(2,len(self.calls))
    for error in (ImportCancelledError('stop'),CamoufoxRequiredError('required')):
      self.failures[self.recipe.SHORTLIST_URLS[0]]=error
      old=self.cache(full)
      old['incremental_state']['units'][self.recipe.SHORTLIST_URLS[0]]['complete']=False
      with self.assertRaises(type(error)):self.parse(old)

  def test_modern_time_markup_and_exact_malformed_biography_row(self):
    parser=UrlFetcherJamesTaitBlackBiography().create_parser()
    rows,notes=parser.winner_rows('<li>Jenny Uglow The Lunar Men: The Friends Who Made the Future 1730-1810 (Faber) - 2002</li>',self.recipe.URL)
    self.assertEqual([],notes)
    self.assertEqual([('2002','The Lunar Men: The Friends Who Made the Future 1730-1810','Jenny Uglow')],[(r['award_year'],r['title'],r['author']) for r in rows])
    current=self.parse()
    self.assertIn('2024',{r['award_year'] for r in current['entries']})
    self.assertNotIn('Wrong Book',{r['title'] for r in current['entries']})

  def configured_fetch(self, recipe, failed=None, historical=None):
    def fetch(url, **_kwargs):
      self.calls.append(url)
      if url == failed:
        raise OSError('unavailable')
      if url == recipe.URL:
        return '<main><ul><li>Writer One - Historic Winner (Publisher) - 2023</li><li>Current Writer - Archive Book (Publisher) - 2024</li></ul></main>'
      if url == SHORTLIST_URL_2024:
        if historical is not None:
          return historical
        count, label = (4, 'novels') if recipe.CATEGORY == 'Fiction' else (6, 'biographies')
        heading = 'Contemporary writing' if recipe.CATEGORY == 'Fiction' else 'Illuminating biographies'
        books = ['Historic Winner by Writer One (Publisher)'] + [f'Historic Candidate {i} by Historical Writer {i} (Publisher)' for i in range(count - 1)]
        return f'<main><h2>{heading}</h2><p>The {count} {label} shortlisted for the prize are: '+ '; '.join(books) + '.</p><p>This article was published on <time datetime="2024-03-26">26 March 2024</time></p></main>'
      return f'<main><h2>{recipe.CATEGORY}</h2>'+''.join(f'<p>Current Writer {chr(65+i)}’s Current Book {i} (Publisher)</p>' for i in range(5))+'<p>This article was published on <time datetime="2026-03-18">18 March 2026</time></p></main>'
    return fetch

  def test_configured_current_and_historical_rosters_reduce_three_requests_to_two(self):
    for cls in (UrlFetcherJamesTaitBlackFiction, UrlFetcherJamesTaitBlackBiography):
      recipe = cls()
      self.assertEqual((SHORTLIST_URL_2026, SHORTLIST_URL_2024), recipe.SHORTLIST_URLS)
      fetch = self.configured_fetch(recipe)
      self.calls.clear()
      full = recipe.fetch_and_parse(fetch)
      self.assertEqual(3, len(self.calls))
      self.assertTrue(all(u['complete'] for u in full['incremental_state']['units'].values()))
      cached = build_import_cache_data(recipe.source_id, full)
      stale = without_unit(cached, 'winners')
      self.assertLess(len(stale['entries']), len(full['entries']))
      self.calls.clear()
      updated = recipe.fetch_and_parse(fetch, cached_parsed=stale, incremental_update=True)
      self.assertEqual(full['entries'], updated['entries'])
      self.assertEqual([recipe.URL, SHORTLIST_URL_2026], self.calls)
      self.calls.clear()
      repeat = recipe.fetch_and_parse(fetch, cached_parsed=build_import_cache_data(recipe.source_id, updated), incremental_update=True)
      self.assertEqual(full['entries'], repeat['entries'])
      self.assertEqual([recipe.URL, SHORTLIST_URL_2026], self.calls)

  def test_missing_older_roster_fetches_it_and_restores_nonwinners(self):
    recipe = UrlFetcherJamesTaitBlackFiction()
    fetch = self.configured_fetch(recipe)
    full = recipe.fetch_and_parse(fetch)
    stale = without_unit(build_import_cache_data(recipe.source_id, full), SHORTLIST_URL_2024)
    self.assertEqual(len(full['entries']) - 3, len(stale['entries']))
    self.calls.clear()
    updated = recipe.fetch_and_parse(fetch, cached_parsed=stale, incremental_update=True)
    self.assertEqual(full['entries'], updated['entries'])
    self.assertEqual(3, len(self.calls))

  def test_declared_historical_roster_checks_count_and_excludes_neighbouring_sections(self):
    recipe = UrlFetcherJamesTaitBlackFiction()
    html = self.configured_fetch(recipe)(SHORTLIST_URL_2024)
    rows = recipe.parser().shortlist_rows(html + '<h2>Other prizes</h2><p>Other Writer’s Wrong Book (Publisher)</p>', SHORTLIST_URL_2024)
    self.assertEqual(4, len(rows))
    self.assertTrue(all(r['award_year'] == '2023' for r in rows))
    with self.assertRaises(ValueError):
      recipe.parser().shortlist_rows(html.replace('; Historic Candidate 2 by Historical Writer 2 (Publisher)', ''), SHORTLIST_URL_2024)

  def test_declared_title_by_author_preserves_title_by_and_author_suffix(self):
    parser = UrlFetcherJamesTaitBlackFiction().parser()
    rows = parser.declared_shortlist_rows('The 1 novels shortlisted for the prize are: Never Judge by Its Cover by Writer, Jr. (Publisher).', 2023, SHORTLIST_URL_2024)
    self.assertEqual(('Never Judge by Its Cover', 'Writer, Jr.'), (rows[0]['title'], rows[0]['author']))

  def test_configured_wrong_year_or_partial_current_roster_stays_pending(self):
    recipe = UrlFetcherJamesTaitBlackFiction()
    base = self.configured_fetch(recipe)
    for change in ('partial', 'year'):
      def fetch(url, **kwargs):
        text = base(url, **kwargs)
        if url == SHORTLIST_URL_2026:
          return text.replace('<p>Current Writer E’s Current Book 4 (Publisher)</p>', '') if change == 'partial' else text.replace('2026-03-18', '2025-03-18')
        return text
      parsed = recipe.fetch_and_parse(fetch)
      self.assertFalse(parsed['incremental_state']['units'][SHORTLIST_URL_2026]['complete'])

  def test_changed_post_configuration_invalidates_cached_source_scope(self):
    recipe = UrlFetcherJamesTaitBlackFiction()
    fetch = self.configured_fetch(recipe)
    full = recipe.fetch_and_parse(fetch)
    recipe.SHORTLIST_URLS = (SHORTLIST_URL_2026,)
    self.calls.clear()
    changed = recipe.fetch_and_parse(fetch, cached_parsed=build_import_cache_data(recipe.source_id, full), incremental_update=True)
    self.assertEqual([recipe.URL, SHORTLIST_URL_2026], self.calls)
    self.assertNotIn('Historic Candidate 0', [r['title'] for r in changed['entries']])

  def test_failed_winner_archive_retains_complete_cached_history_and_recovers(self):
    recipe = UrlFetcherJamesTaitBlackFiction()
    fetch = self.configured_fetch(recipe)
    full = recipe.fetch_and_parse(fetch)
    def incomplete(url, **kwargs):
      return '<main>Archive temporarily unavailable</main>' if url == recipe.URL else fetch(url, **kwargs)
    cached = build_import_cache_data(recipe.source_id, full)
    pending = recipe.fetch_and_parse(incomplete, cached_parsed=cached, incremental_update=True)
    self.assertEqual(full['entries'], pending['entries'])
    self.assertFalse(pending['incremental_state']['units']['winners']['complete'])
    self.assertTrue(any('retained the complete cached archive' in n for n in pending['notes']))
    recovered = recipe.fetch_and_parse(fetch, cached_parsed=build_import_cache_data(recipe.source_id, pending), incremental_update=True)
    self.assertEqual(full['entries'], recovered['entries'])
    self.assertTrue(recovered['incremental_state']['units']['winners']['complete'])

  def test_closed_post_refreshes_if_fresh_winner_is_outside_cached_roster(self):
    recipe = UrlFetcherJamesTaitBlackFiction()
    fetch = self.configured_fetch(recipe)
    full = recipe.fetch_and_parse(fetch)
    def changed(url, **kwargs):
      text = fetch(url, **kwargs)
      return text.replace('Writer One - Historic Winner', 'Different Writer - Changed Winner') if url == recipe.URL else text
    self.calls.clear()
    recipe.fetch_and_parse(changed, cached_parsed=build_import_cache_data(recipe.source_id, full), incremental_update=True)
    self.assertIn(SHORTLIST_URL_2024, self.calls)

  def test_failed_historical_post_keeps_original_nominees_and_retries(self):
    recipe = UrlFetcherJamesTaitBlackFiction()
    fetch = self.configured_fetch(recipe)
    full = recipe.fetch_and_parse(fetch)
    cached = build_import_cache_data(recipe.source_id, full)
    cached['incremental_state']['units'][SHORTLIST_URL_2024]['complete'] = False
    pending = recipe.fetch_and_parse(self.configured_fetch(recipe, failed=SHORTLIST_URL_2024), cached_parsed=cached, incremental_update=True)
    self.assertEqual(full['entries'], pending['entries'])
    self.assertFalse(pending['incremental_state']['units'][SHORTLIST_URL_2024]['complete'])
    recovered = recipe.fetch_and_parse(fetch, cached_parsed=build_import_cache_data(recipe.source_id, pending), incremental_update=True)
    self.assertEqual(full['entries'], recovered['entries'])
    self.assertTrue(recovered['incremental_state']['units'][SHORTLIST_URL_2024]['complete'])


if __name__=='__main__':
  unittest.main()
