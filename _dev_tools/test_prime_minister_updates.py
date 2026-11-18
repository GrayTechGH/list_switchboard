import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError,ImportCancelledError
from storage import build_import_cache_data
from url_fetcher import prime_ministers_literary_awards as pmla


RECIPES=(pmla.UrlFetcherPrimeMinistersLiteraryAwardsFiction,pmla.UrlFetcherPrimeMinistersLiteraryAwardsNonfiction,
  pmla.UrlFetcherPrimeMinistersLiteraryAwardsAustralianHistory,pmla.UrlFetcherPrimeMinistersLiteraryAwardsYoungAdultLiterature,
  pmla.UrlFetcherPrimeMinistersLiteraryAwardsChildrensLiterature)


class PrimeMinisterUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=RECIPES[0]()
    self.years=[2023,2024,2025]
    self.current=2026
    self.calls,self.failures,self.pages=[],{},{}
    self.winnerless=set()
    self.clock=patch('parser.prime_ministers_literary_awards.datetime')
    self.dates=self.clock.start()
    self.dates.datetime.now.return_value.year=self.current
    self.addCleanup(self.clock.stop)

  def url(self,year):
    return f'https://creative.gov.au/{year}-pmla-winners-shortlist-and-judges'

  def cards(self,year,current=False):
    rows=[]
    for cls in RECIPES:
      category=cls().CATEGORY
      winner='[WINNER] ' if current else 'WINNER: '
      if year in self.winnerless:winner=''
      rows.append(f'<h2>{category}</h2><p class="card-portrait--content-title">{winner}Work {year} {category} by Writer One</p><p class="card-portrait--content-title">Other {year} {category} by Writer Two</p>')
    return ''.join(rows)+'<h2>Poetry</h2><p class="card-portrait--content-title">Wrong by Other Writer</p>'

  def fetch(self,url):
    self.calls.append(url)
    if url in self.failures:raise self.failures[url]
    if url==self.recipe.URL:
      return f'<p>Prime Minister\u2019s Literary Awards {self.current}</p>'+''.join(f'<a href="{self.url(y)}">{y}</a>' for y in self.years)+f'<a href="/news-events/news/announcing-winners-{self.current}-prime-ministers-literary-awards">News {self.current}</a>'+self.cards(self.current,True)
    year=int(url.rsplit('/',1)[-1].split('-',1)[0])
    return self.pages.get(year,f'<title>{year} PMLA winners and shortlist</title><h1>{year} PMLA</h1>'+self.cards(year))

  def parse(self,old=None):
    return self.recipe.fetch_and_parse(self.fetch,source_choice=0,cached_parsed=old,incremental_update=old is not None)

  def cache(self,parsed):
    return build_import_cache_data(self.recipe.source_id,parsed)

  def test_all_categories_current_cards_missing_year_recovery_and_repeat(self):
    for cls in RECIPES:
      self.recipe=cls()
      self.calls.clear()
      full=self.parse()
      self.assertEqual(8,len(full['entries']))
      self.assertEqual(4,len(self.calls))
      self.assertEqual(4,sum(r['result']=='winner' for r in full['entries']))
      old=without_unit(self.cache(full),self.url(2025))
      self.calls.clear()
      update=self.parse(old)
      self.assertEqual(full['entries'],update['entries'])
      self.assertEqual([self.recipe.URL,self.url(2025)],self.calls)
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])
      self.assertEqual([self.recipe.URL],self.calls)

  def test_added_year_and_removed_history_follow_new_manifest(self):
    old=self.cache(self.parse())
    self.current=2027
    self.dates.datetime.now.return_value.year=2027
    self.years=[2024,2025,2026]
    self.calls.clear()
    update=self.parse(old)
    self.assertEqual([self.recipe.URL,self.url(2026)],self.calls)
    self.assertEqual(self.parse()['entries'],update['entries'])

  def test_failed_empty_and_conflicting_year_units_retain_old_rows_pending(self):
    full=self.parse()
    old=self.cache(full)
    old['incremental_state']['units'][self.url(2024)]['complete']=False
    for mode in ('failure','empty','wrong-year'):
      self.failures.clear()
      self.pages.clear()
      if mode=='failure':self.failures[self.url(2024)]=OSError('offline')
      elif mode=='empty':self.pages[2024]='<h1>Access denied</h1>'
      else:self.pages[2024]='<title>2020 PMLA winners</title>'+self.cards(2020)
      pending=self.parse(old)
      self.assertEqual(full['entries'],pending['entries'])
      self.assertFalse(pending['incremental_state']['units'][self.url(2024)]['complete'])
      self.assertTrue(pending['notes'])
    self.pages.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(pending))['entries'])

  def test_winnerless_history_stays_fresh(self):
    self.winnerless.add(2024)
    old=self.cache(self.parse())
    self.calls.clear()
    self.parse(old)
    self.assertEqual([self.recipe.URL,self.url(2024)],self.calls)

  def test_verified_absent_category_is_reusable_but_missing_category_rows_are_not(self):
    self.pages[2023]='<title>2023 PMLA</title><h1>2023 PMLA winners</h1><h2>Non-fiction</h2><p class="card-portrait--content-title">Winner: Other by Other Writer</p>'
    full=self.parse()
    self.assertTrue(full['incremental_state']['units'][self.url(2023)]['complete'])
    self.calls.clear()
    self.parse(self.cache(full))
    self.assertNotIn(self.url(2023),self.calls)
    self.pages[2023]='<title>2023 PMLA</title><h1>2023 PMLA winners</h1><h2>Fiction</h2>'
    parsed=self.parse()
    self.assertFalse(parsed['incremental_state']['units'][self.url(2023)]['complete'])

  def test_legacy_configuration_and_critical_failures(self):
    full=self.parse()
    wrong=self.cache(full)
    wrong['incremental_state']['source_key']='other category'
    for old in ({'entries':full['entries']},wrong,['invalid cache']):
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(old)['entries'])
      self.assertEqual(4,len(self.calls))
    for error in (ImportCancelledError('stop'),CamoufoxRequiredError('required')):
      self.failures[self.url(2025)]=error
      old=self.cache(full)
      old['incremental_state']['units'][self.url(2025)]['complete']=False
      with self.assertRaises(type(error)):self.parse(old)

  def test_current_year_requires_explicit_award_label_and_bracketed_winner_is_result(self):
    parser=self.recipe.create_official_parser()
    html='<p>Archived article 2040</p><p>Prime Minister\u2019s Literary Awards 2026</p>'+self.cards(2026,True)
    rows=parser.page_rows(html,self.recipe.URL)
    self.assertEqual({'2026'},{r['award_year'] for r in rows})
    self.assertEqual(1,sum(r['result']=='winner' for r in rows))
    self.assertTrue(all('[WINNER]' not in r['title'] for r in rows))


if __name__=='__main__':
  unittest.main()
