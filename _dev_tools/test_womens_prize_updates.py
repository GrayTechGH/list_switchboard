import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError, ImportCancelledError
from storage import build_import_cache_data
from url_fetcher.womens_prize import UrlFetcherWomensPrizeFiction, UrlFetcherWomensPrizeNonFiction


class WomensPrizeUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=UrlFetcherWomensPrizeFiction()
    self.calls,self.failures,self.details=[],{},{}
    self.years=[2026,2025,2024]
    self.extra=[]
    self.clock=patch('parser.womens_prize.datetime')
    self.dates=self.clock.start()
    self.dates.datetime.now.return_value.year=2026
    self.addCleanup(self.clock.stop)

  def url(self,key):
    return 'https://womensprize.com/library/'+str(key)+'/'

  def landing(self):
    winners=''.join(f'<p><span class="win_year">{y}:</span><a href="{self.url(y)}"><em>Book {y}</em></a><br/>Writer {y}</p>' for y in self.years)
    cards=''.join(f'<a class="book_card" href="{self.url(key)}"><img alt="{title}"/></a>' for key,title in [(self.years[0],f'Book {self.years[0]}'),('other','Other')]+self.extra)
    return f'<h1>Search</h1><div class="previous_winners">{winners}</div><section><h2>The {self.years[0]} {self.recipe.NAME} Shortlist</h2>{cards}</section><section><h2>The {self.years[0]} {self.recipe.NAME} Longlist</h2><a class="book_card" href="{self.url("excluded")}"><img alt="Excluded"/></a></section>'

  def detail(self,key):
    year=int(key) if key.isdigit() else self.years[0]
    title=f'Book {key}' if key.isdigit() else 'Other' if key=='other' else key.title()
    return f'<h1>Search</h1><nav>Longlist {self.recipe.NAME}</nav><div class="book_meta"><h3><strong>{title}</strong><br/>Writer {key}</h3><p>Published: 1900</p></div><div class="book_prize">Shortlisted for the {year} {self.recipe.NAME}</div>'

  def fetch(self,url):
    self.calls.append(url)
    if url in self.failures:
      raise self.failures[url]
    if url==self.recipe.URL:
      return self.landing()
    key=url.strip('/').rsplit('/',1)[-1]
    return self.details.get(url,self.detail(key))

  def parse(self,old=None,**kwargs):
    return self.recipe.fetch_and_parse(self.fetch,source_choice=kwargs.pop('source_choice',0),
      cached_parsed=old,incremental_update=old is not None,**kwargs)

  def cache(self,parsed):
    return build_import_cache_data(self.recipe.source_id,parsed)

  def test_missing_entry_recovery_repeat_and_both_prize_categories(self):
    for cls in (UrlFetcherWomensPrizeFiction,UrlFetcherWomensPrizeNonFiction):
      self.recipe=cls()
      self.calls.clear()
      full=self.parse()
      self.assertEqual(4,len(full['entries']))
      self.assertEqual(5,len(self.calls))
      self.assertEqual(3,sum(r['result']=='winner' for r in full['entries']))
      old=without_unit(self.cache(full),self.url(2024))
      self.calls.clear()
      update=self.parse(old)
      self.assertEqual(full['entries'],update['entries'])
      self.assertEqual([self.recipe.URL,self.url(2026),self.url(2024),self.url('other')],self.calls)
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])
      self.assertEqual([self.recipe.URL,self.url(2026),self.url('other')],self.calls)

  def test_modern_metadata_ignores_search_navigation_and_longlists(self):
    result=self.parse()
    self.assertEqual({'Book 2026','Book 2025','Book 2024','Other'}, {r['title'] for r in result['entries']})
    self.assertNotIn(self.url('excluded'),self.calls)
    self.assertTrue(all(r['award_year']!='1900' for r in result['entries']))

  def test_new_year_retains_history_and_discovers_current_shortlist(self):
    old=self.cache(self.parse())
    self.years.insert(0,2027)
    self.dates.datetime.now.return_value.year=2027
    self.calls.clear()
    update=self.parse(old)
    self.assertEqual([self.recipe.URL,self.url(2027),self.url('other')],self.calls)
    self.assertEqual(self.parse()['entries'],update['entries'])

  def test_changed_landing_identity_refetches_history_and_removed_cards_disappear(self):
    old=self.cache(self.parse())
    self.years.remove(2024)
    original=self.landing
    with patch.object(self,'landing',lambda:original().replace('Book 2025','Corrected 2025')):
      self.calls.clear()
      update=self.parse(old)
      self.assertIn(self.url(2025),self.calls)
      self.assertNotIn('2024',{r['award_year'] for r in update['entries']})

  def test_archive_winner_status_overrides_stale_detail_status(self):
    full=self.parse()
    self.assertEqual('winner',next(r for r in full['entries'] if r['title']=='Book 2026')['result'])
    self.details[self.url('other')]=self.detail('other').replace('Shortlisted','Winner')
    update=self.parse(self.cache(full))
    self.assertEqual('shortlisted',next(r for r in update['entries'] if r['title']=='Other')['result'])

  def test_failure_retains_history_pending_then_recovers(self):
    full=self.parse()
    old=self.cache(full)
    old['incremental_state']['units'][self.url(2025)]['complete']=False
    self.failures[self.url(2025)]=OSError('offline')
    pending=self.parse(old)
    self.assertEqual(full['entries'],pending['entries'])
    self.assertFalse(pending['incremental_state']['units'][self.url(2025)]['complete'])
    self.failures.clear()
    self.calls.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(pending))['entries'])
    self.assertIn(self.url(2025),self.calls)

  def test_sibling_prize_and_wrong_year_never_fall_back_to_card_or_cache(self):
    old=self.cache(self.parse())
    for label in ("Women's Prize for Non-Fiction",self.recipe.NAME):
      year=2026 if label!=self.recipe.NAME else 2020
      self.details[self.url(2026)]=self.detail('2026').replace(f'2026 {self.recipe.NAME}',f'{year} {label}')
      parsed=self.parse(old)
      self.assertNotIn('Book 2026',{r['title'] for r in parsed['entries']})
      self.assertFalse(parsed['incremental_state']['units'][self.url(2026)]['complete'])

  def test_legacy_invalid_and_cross_prize_caches_require_fresh_details(self):
    full=self.parse()
    wrong=self.cache(full)
    wrong['incremental_state']['source_key']='wrong prize'
    for old in ({'entries':full['entries']},wrong,['invalid container']):
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(old)['entries'])
      self.assertEqual(5,len(self.calls))

  def test_critical_failures_propagate(self):
    old=self.cache(self.parse())
    for error in (ImportCancelledError('stop'),CamoufoxRequiredError('required')):
      self.failures[self.url(2026)]=error
      with self.assertRaises(type(error)):
        self.parse(old)

  def test_wikipedia_choice_stays_independent_and_full_refresh(self):
    old=self.cache(self.parse())
    wiki='<table><tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr><tr><td>2026</td><td>Wiki Writer</td><td>Wiki Book</td><td>Winner</td></tr></table>'
    calls=[]
    def fetch(url):
      calls.append(url)
      return wiki
    result=self.recipe.fetch_and_parse(fetch,source_choice=1,cached_parsed=old,incremental_update=True)
    self.assertEqual([self.recipe.WIKIPEDIA_URL],calls)
    self.assertEqual('Wiki Book',result['entries'][0]['title'])
    self.assertNotIn('incremental_state',result)


if __name__=='__main__':
  unittest.main()
