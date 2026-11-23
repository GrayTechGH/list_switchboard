import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError, ImportCancelledError
from storage import build_import_cache_data
from url_fetcher.royal_society import UrlFetcherRoyalSocietyScienceBookPrize
from url_fetcher.royal_society_transport import RoyalSocietyFetchPolicy


class RoyalSocietyUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=UrlFetcherRoyalSocietyScienceBookPrize()
    self.years=[2026,2025,2024]
    self.calls,self.failures,self.details=[],{},{}
    self.winnerless=set()
    self.clock=patch('parser.royal_society.datetime')
    self.dates=self.clock.start()
    self.dates.datetime.now.return_value.year=2026
    self.addCleanup(self.clock.stop)

  def url(self,year,kind):
    return f'https://www.royalsociety.org/medals-and-prizes/science-book-prize/books/{year}/{kind}/'

  def landing(self):
    cards=[]
    for year in self.years:
      for kind in ('winner','other'):
        author='Writer One' if kind=='winner' else 'Writer Two'
        cards.append(f'<div class="card"><a href="{self.url(year,kind)}"><h4 class="card__title">Book {year} {kind}</h4><div class="card__meta"><span class="card__meta-item">{author}</span></div><span>{year} - Shortlist</span></a></div>')
    return '<h1>Science Book Prize</h1>'+''.join(cards)

  def fetch(self,url):
    self.calls.append(url)
    if url in self.failures: raise self.failures[url]
    if url==self.recipe.URL: return self.landing()
    year,kind=url.strip('/').split('/')[-2:]
    stage='Winner' if kind=='winner' and int(year) not in self.winnerless else 'Shortlist'
    author='Writer One' if kind=='winner' else 'Writer Two'
    return self.details.get(url,f'<header><h1>Book {year} {kind}</h1><h4>{stage}: {year}</h4><p>Author: <strong>{author}</strong></p></header>')

  def parse(self,old=None):
    return self.recipe.fetch_and_parse(self.fetch,source_choice=0,cached_parsed=old,incremental_update=old is not None)

  def cache(self,parsed):
    return build_import_cache_data(self.recipe.source_id,parsed)

  def test_missing_year_recovery_repeat_and_promoted_winners(self):
    full=self.parse()
    self.assertEqual(7,len(self.calls))
    self.assertEqual(3,sum(r['result']=='winner' for r in full['entries']))
    old=without_unit(self.cache(full),'2024')
    self.calls.clear()
    update=self.parse(old)
    self.assertEqual(full['entries'],update['entries'])
    self.assertEqual([self.recipe.URL,self.url(2026,'winner'),self.url(2026,'other'),self.url(2024,'winner'),self.url(2024,'other')],self.calls)
    self.calls.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])
    self.assertEqual(3,len(self.calls))

  def test_new_year_manifest_and_removed_years(self):
    old=self.cache(self.parse())
    self.years=[2027,2026,2025]
    self.dates.datetime.now.return_value.year=2027
    self.calls.clear()
    update=self.parse(old)
    self.assertEqual([self.recipe.URL,self.url(2027,'winner'),self.url(2027,'other')],self.calls)
    self.assertNotIn('2024',{r['award_year'] for r in update['entries']})
    self.assertEqual(self.parse()['entries'],update['entries'])

  def test_changed_archive_identity_refreshes_only_affected_history(self):
    old=self.cache(self.parse())
    original=self.landing
    with patch.object(self,'landing',lambda:original().replace('Book 2025 other','Corrected title')):
      self.calls.clear()
      self.parse(old)
    self.assertIn(self.url(2025,'other'),self.calls)
    self.assertNotIn(self.url(2024,'other'),self.calls)

  def test_winnerless_and_latest_history_refresh(self):
    self.winnerless.add(2024)
    old=self.cache(self.parse())
    self.dates.datetime.now.return_value.year=2028
    self.calls.clear()
    self.parse(old)
    self.assertIn(self.url(2026,'winner'),self.calls)
    self.assertIn(self.url(2024,'winner'),self.calls)
    self.assertNotIn(self.url(2025,'winner'),self.calls)

  def test_failed_detail_retains_whole_ballot_pending_and_recovers(self):
    full=self.parse()
    old=self.cache(full)
    old['incremental_state']['units']['2025']['complete']=False
    self.failures[self.url(2025,'winner')]=OSError('offline')
    pending=self.parse(old)
    self.assertEqual(full['entries'],pending['entries'])
    self.assertFalse(pending['incremental_state']['units']['2025']['complete'])
    self.failures.clear()
    self.calls.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(pending))['entries'])
    self.assertIn(self.url(2025,'winner'),self.calls)

  def test_incomplete_full_falls_back_to_actual_card_metadata_and_remains_pending(self):
    self.failures[self.url(2025,'winner')]=OSError('offline')
    parsed=self.parse()
    self.assertEqual(6,len(parsed['entries']))
    self.assertEqual(['Writer One'],next(r for r in parsed['entries'] if r['title']=='Book 2025 winner')['authors'])
    self.assertFalse(parsed['incremental_state']['units']['2025']['complete'])
    self.assertTrue(parsed['notes'])

  def test_wrong_year_detail_cannot_promote_another_ballot(self):
    self.details[self.url(2026,'winner')]='<header><h1>Wrong year</h1><h4>Winner: 2020</h4><p>Author: Writer</p></header>'
    parsed=self.parse()
    self.assertNotIn('2020',{r['award_year'] for r in parsed['entries']})
    self.assertFalse(parsed['incremental_state']['units']['2026']['complete'])

  def test_legacy_scope_and_critical_errors(self):
    full=self.parse()
    wrong=self.cache(full)
    wrong['incremental_state']['source_key']='another source'
    for old in ({'entries':full['entries']},wrong,['invalid container']):
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(old)['entries'])
      self.assertEqual(7,len(self.calls))
    for error in (ImportCancelledError('stop'),CamoufoxRequiredError('required')):
      self.failures[self.url(2026,'winner')]=error
      with self.assertRaises(type(error)): self.parse(self.cache(full))

  def test_browser_is_validated_before_same_url_legacy_recovery(self):
    calls=[]
    def browser(url,**kwargs):calls.append(('browser',url));return '<html><h1>Verify you are human</h1></html>'
    def legacy(url):calls.append(('legacy',url));return self.landing()
    policy=RoyalSocietyFetchPolicy(browser,legacy,self.recipe.parser())
    self.assertEqual(self.landing(),policy.fetch(self.recipe.URL))
    self.assertEqual(self.landing(),policy.fetch(self.recipe.URL))
    self.assertEqual([('browser',self.recipe.URL),('legacy',self.recipe.URL),('legacy',self.recipe.URL)],calls)

  def test_browser_accepts_own_roster_with_background_challenge_script(self):
    html=self.landing()+'<script src="/cdn-cgi/challenge-platform/script.js"></script>'
    def browser(url,**kwargs):return html
    def legacy(url):self.fail('valid browser payload should not use legacy')
    policy=RoyalSocietyFetchPolicy(browser,legacy,self.recipe.parser())
    self.assertEqual(html,policy.fetch(self.recipe.URL))

  def test_wikipedia_keeps_legacy_and_critical_browser_errors_propagate(self):
    calls=[]
    def legacy(url):calls.append(url);return 'Wikipedia data'
    for error in (ImportCancelledError('stop'),CamoufoxRequiredError('required')):
      def browser(*args,**kwargs):raise error
      policy=RoyalSocietyFetchPolicy(browser,legacy,self.recipe.parser())
      self.assertEqual('Wikipedia data',policy.fetch('https://en.wikipedia.org/wiki/Royal_Society_Science_Book_Prize'))
      with self.assertRaises(type(error)):policy.fetch(self.recipe.URL)
    self.assertEqual(2,len(calls))


if __name__=='__main__':
  unittest.main()
