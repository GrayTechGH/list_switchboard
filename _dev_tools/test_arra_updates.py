import copy
import json
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError,ImportCancelledError
from parser.australian_romance_readers import AustralianRomanceReadersAwardsParser,ARRA_REST_PAGE_URL
from storage import build_import_cache_data
from url_fetcher.australian_romance_readers import UrlFetcherAustralianRomanceReadersAwards
from url_fetcher.generic import UrlFetcherError


class ARRAUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=UrlFetcherAustralianRomanceReadersAwards()
    self.years=[2023,2024,2025]
    self.calls,self.failures,self.overrides=[],{},{}
    self.winners=True
    self.clock=patch('parser.annual_updates.datetime')
    self.dates=self.clock.start()
    self.dates.datetime.now.return_value.year=2026
    self.addCleanup(self.clock.stop)

  def url(self,year):
    return ARRA_REST_PAGE_URL.format(slug=f'{year}-2')

  def front(self):
    return ''.join(f'<a href="{host}/awards/{year}-2/">{year}</a>' for year in self.years
      for host in ('https://australianromancereaders.com.au','http://www.australianromancereaders.com.au'))

  def year_page(self,year):
    winning='<span style="color:#ff00ff"><b>First Book by Writer One</b></span>' if self.winners else 'First Book by Writer One'
    return json.dumps([{'link':f'https://australianromancereaders.com.au/awards/{year}-2/',
      'content':{'rendered':f'<h1>{year}</h1><p><strong>Favourite Paranormal Romance</strong><br><em>proudly sponsored by Galaxy Bookshop</em></p><ul><li>{winning}</li><li>Second Book by Writer Two</li></ul>'}}])

  def fetch(self,url):
    self.calls.append(url)
    if url in self.failures:raise self.failures[url]
    if url in self.overrides:return self.overrides[url]
    if url==self.recipe.URL:return self.front()
    return self.year_page(int(url.split('slug=')[-1][:4]))

  def parse(self,old=None,incremental=None):
    return self.recipe.fetch_and_parse(self.fetch,cached_parsed=old,
      incremental_update=(old is not None) if incremental is None else incremental)

  def cache(self,parsed):
    return build_import_cache_data(self.recipe.source_id,parsed)

  def test_missing_year_recovery_and_repeat_use_fewer_requests(self):
    full=self.parse()
    self.assertEqual(4,len(self.calls))
    self.assertEqual(6,len(full['entries']))
    old=without_unit(self.cache(full),self.url(2024))
    self.assertEqual(4,len(old['entries']))
    self.calls.clear()
    update=self.parse(old)
    self.assertEqual(full['entries'],update['entries'])
    self.assertEqual(3,len(self.calls))
    self.calls.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])
    self.assertEqual([self.recipe.URL,self.url(2025)],self.calls)

  def test_new_and_removed_years_follow_fresh_overview(self):
    old=self.cache(self.parse())
    self.years=[2024,2025,2026]
    self.calls.clear()
    update=self.parse(old)
    self.assertEqual([self.recipe.URL,self.url(2026)],self.calls)
    self.assertEqual(self.parse()['entries'],update['entries'])
    self.assertNotIn('2023',{r['award_year'] for r in update['entries']})

  def test_winnerless_history_is_not_reused(self):
    self.overrides[self.url(2024)]=self.year_page(2024).replace('<span style=\\"color:#ff00ff\\"><b>First Book by Writer One</b></span>','First Book by Writer One')
    old=self.cache(self.parse())
    self.assertFalse(old['incremental_state']['units'][self.url(2024)]['metadata']['settled'])
    self.calls.clear()
    self.parse(old)
    self.assertIn(self.url(2024),self.calls)
    self.assertNotIn(self.url(2023),self.calls)

  def test_failed_wrong_year_and_challenged_pages_retain_pending_history(self):
    full=self.parse();old=self.cache(full);url=self.url(2025)
    for failure in (RuntimeError('offline'),'<html>Verification required</html>',self.year_page(2024)):
      self.failures.clear();self.overrides.clear()
      if isinstance(failure,Exception):self.failures[url]=failure
      else:self.overrides[url]=failure
      update=self.parse(old)
      self.assertEqual(full['entries'],update['entries'])
      self.assertFalse(update['incremental_state']['units'][url]['complete'])
    self.overrides.clear()
    self.assertTrue(self.parse(self.cache(update))['incremental_state']['units'][url]['complete'])

  def test_failed_full_year_keeps_other_years_and_records_availability(self):
    self.failures[self.url(2024)]=RuntimeError('offline')
    full=self.parse()
    self.assertEqual({'2023','2025'},{r['award_year'] for r in full['entries']})
    self.assertFalse(full['incremental_state']['units'][self.url(2024)]['complete'])
    self.assertTrue(any('offline' in note for note in full['notes']))

  def test_legacy_incompatible_and_complete_refresh_fetch_all_years(self):
    old=self.cache(self.parse())
    legacy=copy.deepcopy(old);legacy.pop('incremental_state')
    wrong=copy.deepcopy(old);wrong['incremental_state']['source_key']='other'
    for candidate,incremental in ((legacy,True),(wrong,True),(old,False)):
      self.calls.clear();self.parse(candidate,incremental)
      self.assertEqual(4,len(self.calls))

  def test_cancellation_and_browser_requirements_propagate(self):
    for cls in (ImportCancelledError,CamoufoxRequiredError):
      self.failures={self.url(2024):cls('stop')}
      with self.assertRaises(cls):self.parse()

  def test_no_year_navigation_cannot_certify_an_empty_update(self):
    old=self.cache(self.parse())
    self.overrides[self.recipe.URL]='<html>Challenge</html>'
    with self.assertRaisesRegex(UrlFetcherError,'award years'):self.parse(old)

  def test_sponsor_headers_slash_titles_and_suffixes_preserve_book_fields(self):
    html='''<p><strong>Favourite Paranormal Romance for 2011</strong><br><em>proudly sponsored by Galaxy Bookshop</em></p>
      <ul><li><span style="color:#ff00ff"><b><i>Title / Subtitle</i> / Walter M. Miller, Jr.</b></span></li>
      <li><i>Other Book</i> / Other Writer</li></ul>
      <p><strong>Favourite Australian Romance Author</strong></p><ul><li>A Writer</li></ul>'''
    rows=AustralianRomanceReadersAwardsParser().parse_year_page(html,'https://australianromancereaders.com.au/awards/2011-2/')
    self.assertEqual([('Title / Subtitle',['Walter M. Miller, Jr.'],'winner'),('Other Book',['Other Writer'],'shortlisted')],
      [(r['title'],r['authors'],r['result']) for r in rows])
    self.assertEqual({'Favourite Paranormal Romance'},{r['category'] for r in rows})

  def test_single_book_categories_on_explicit_winner_only_page_are_winners(self):
    html='''<p>Winners for 2008 were:</p><p><b>Favourite Paranormal Romance for 2008</b><br><em>sponsored by Galaxy Bookshop</em></p>
      <ul><li><i>Acheron</i> by Sherrilyn Kenyon</li></ul>
      <p><b>Favourite Historical Romance for 2008</b><br><em>sponsored by Robinsons Books</em></p>
      <ul><li><i>Untouched</i> by Anna Campbell</li></ul>'''
    rows=AustralianRomanceReadersAwardsParser().parse_year_page(html,'https://australianromancereaders.com.au/awards/2008-2/')
    self.assertEqual(2,len(rows))
    self.assertEqual({'winner'},{r['result'] for r in rows})

  def test_runtime_cache_keeps_parsed_entries_and_coverage_notes(self):
    full=self.parse();old=self.cache(full)
    self.assertNotIn('<li>',json.dumps(old))
    self.assertEqual(full['notes'],self.parse(old)['notes'])
    self.assertTrue(all(unit['complete'] for unit in old['incremental_state']['units'].values()))
