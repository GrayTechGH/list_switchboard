import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError,ImportCancelledError
from storage import build_import_cache_data
from url_fetcher import nero_book_awards as nero


RECIPES=(nero.UrlFetcherNeroBookAwardsFiction,nero.UrlFetcherNeroBookAwardsDebutFiction,
  nero.UrlFetcherNeroBookAwardsNonfiction,nero.UrlFetcherNeroBookAwardsChildrensFiction,
  nero.UrlFetcherNeroBookAwardsGoldPrize)


class NeroBookUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=RECIPES[0]()
    self.years=[2025,2024,2023]
    self.calls,self.failures,self.pages=[],{},{}
    self.winner=0
    self.clock=patch('parser.nero_book_awards.datetime')
    self.dates=self.clock.start()
    self.dates.datetime.now.return_value.year=2026
    self.addCleanup(self.clock.stop)

  def url(self,kind,year):
    return f'https://nerobookawards.com/{year}-{kind}/'

  def landing(self):
    return ''.join(f'<a href="{self.url(kind,y)}">{y} {label}</a>' for y in self.years for kind,label in
      (('shortlist','Shortlist'),('winners','Category Winners'),('gold','Nero Gold Prize')))

  def book(self,category,year,index):
    return f'{category} Book {year} {index} by Writer {index}'

  def page(self,kind,year):
    if kind=='shortlist':
      return '<div class="entry-content">'+''.join(f'<h2>{cls().CATEGORY}</h2>'+''.join(f'<p>{self.book(cls().CATEGORY,year,i)}</p>' for i in range(4)) for cls in RECIPES[:4])+'</div>'
    if kind=='winners':
      return '<div class="entry-content">'+''.join(f'<h5>{self.book(cls().CATEGORY,year,self.winner)}</h5>' for cls in RECIPES[:4])+'</div>'
    return f'<div class="entry-content"><h5>{self.book("Gold",year,self.winner)}</h5><h2>Other books shortlisted</h2><p>Excluded by Other Writer</p></div>'

  def fetch(self,url):
    self.calls.append(url)
    if url in self.failures:raise self.failures[url]
    if url==self.recipe.URL:return self.landing()
    year,kind=url.strip('/').rsplit('/',1)[-1].split('-')
    return self.pages.get(url,self.page(kind,int(year)))

  def parse(self,old=None):
    return self.recipe.fetch_and_parse(self.fetch,source_choice=0,cached_parsed=old,incremental_update=old is not None)

  def cache(self,parsed):
    return build_import_cache_data(self.recipe.source_id,parsed)

  def test_all_five_categories_missing_year_recovery_and_repeat(self):
    for cls in RECIPES:
      self.recipe=cls()
      self.calls.clear()
      full=self.parse()
      gold=cls==RECIPES[-1]
      self.assertEqual(3 if gold else 12,len(full['entries']))
      self.assertEqual(4 if gold else 7,len(self.calls))
      old=without_unit(self.cache(full),'2025')
      self.calls.clear()
      update=self.parse(old)
      self.assertEqual(full['entries'],update['entries'])
      self.assertEqual(2 if gold else 3,len(self.calls))
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])
      self.assertEqual(2 if gold else 3,len(self.calls))

  def test_new_year_and_removed_history_follow_fresh_navigation(self):
    old=self.cache(self.parse())
    self.years=[2026,2025,2024]
    self.calls.clear()
    update=self.parse(old)
    self.assertEqual(3,len(self.calls))
    self.assertEqual({'2026','2025','2024'},{r['award_year'] for r in update['entries']})
    self.assertEqual(self.parse()['entries'],update['entries'])

  def test_changed_source_url_refetches_only_its_year(self):
    old=self.cache(self.parse())
    original=self.url
    with patch.object(self,'url',lambda k,y:original(k,y)+'?changed' if y==2024 else original(k,y)):
      original_fetch=self.fetch
      def fetch(url):
        if '?' in url:
          self.calls.append(url)
          year,kind=url.split('?',1)[0].strip('/').rsplit('/',1)[-1].split('-')
          return self.page(kind,int(year))
        return original_fetch(url)
      self.calls.clear()
      self.recipe.fetch_and_parse(fetch,source_choice=0,cached_parsed=old,incremental_update=True)
      self.assertEqual(5,len(self.calls))
      self.assertFalse(any('/2023-' in url for url in self.calls))

  def test_current_winner_changes_promote_and_demote_original_shortlist_rows(self):
    full=self.parse()
    self.winner=1
    updated=self.parse(self.cache(full))
    current=[r for r in updated['entries'] if r['award_year']=='2025']
    self.assertEqual('Fiction Book 2025 1',next(r['title'] for r in current if r['result']=='winner'))
    self.assertEqual('shortlisted',next(r['result'] for r in current if r['title']=='Fiction Book 2025 0'))
    self.assertNotEqual(full['entries'],updated['entries'])

  def test_failed_and_partial_years_retain_whole_cached_ballot_pending(self):
    full=self.parse()
    old=self.cache(full)
    old['incremental_state']['units']['2024']['complete']=False
    url=self.url('shortlist',2024)
    for partial in (False,True):
      if partial:
        self.failures.clear()
        self.pages[url]=self.page('shortlist',2024).replace('<p>Fiction Book 2024 3 by Writer 3</p>','')
      else:self.failures[url]=OSError('offline')
      pending=self.parse(old)
      self.assertEqual(full['entries'],pending['entries'])
      self.assertFalse(pending['incremental_state']['units']['2024']['complete'])
      self.assertTrue(pending['notes'])
    self.pages.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(pending))['entries'])

  def test_missing_winner_or_mismatched_winner_set_never_settles(self):
    self.pages[self.url('winners',2024)]='<div class="entry-content"><h5>Unrelated Book by Other Writer</h5></div>'
    full=self.parse()
    self.assertFalse(full['incremental_state']['units']['2024']['complete'])
    self.calls.clear()
    self.parse(self.cache(full))
    self.assertIn(self.url('winners',2024),self.calls)

  def test_legacy_configuration_and_critical_failures(self):
    full=self.parse()
    wrong=self.cache(full)
    wrong['incremental_state']['source_key']='another category'
    for old in ({'entries':full['entries']},wrong,['invalid cache']):
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(old)['entries'])
      self.assertEqual(7,len(self.calls))
    for error in (ImportCancelledError('stop'),CamoufoxRequiredError('required')):
      self.failures[self.url('shortlist',2025)]=error
      with self.assertRaises(type(error)):self.parse(self.cache(full))


if __name__=='__main__':
  unittest.main()
