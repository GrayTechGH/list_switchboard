import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError,ImportCancelledError
from storage import build_import_cache_data
from url_fetcher.goldsmiths import UrlFetcherGoldsmithsPrize


class GoldsmithsUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=UrlFetcherGoldsmithsPrize()
    self.years=[2024,2025,2026]
    self.winners={year:'First' for year in self.years}
    self.calls,self.failures,self.pages=[],{},{}
    self.clock=patch('parser.goldsmiths.datetime')
    self.dates=self.clock.start()
    self.dates.datetime.now.return_value.year=2026
    self.addCleanup(self.clock.stop)

  def url(self,year):
    return f'https://www.gold.ac.uk/goldsmiths-prize/archive/prize-{year}/'

  def fetch(self,url):
    self.calls.append(url)
    if url in self.failures: raise self.failures[url]
    if url==self.recipe.URL:
      return ''.join((f'<h2>{year} Winner: {self.winners[year]} {year} by Writer One</h2>' if year in self.winners else '')+f'<p><a href="{self.url(year)}">Year {year}</a></p>' for year in self.years)
    year=int(url.strip('/').rsplit('-',1)[-1])
    return self.pages.get(year,f'<title>Goldsmiths Prize {year}</title>'+''.join(f'<article class="prize-teaser"><h3 class="book_name">{name} {year}</h3><p class="book_author">Writer One</p></article>' for name in ('First','Other')))

  def parse(self,old=None):
    return self.recipe.fetch_and_parse(self.fetch,source_choice=0,cached_parsed=old,incremental_update=old is not None)

  def cache(self,parsed):
    return build_import_cache_data(self.recipe.source_id,parsed)

  def test_missing_shortlist_entries_repeat_and_winner_projections(self):
    full=self.parse()
    self.assertEqual(6,len(full['entries']))
    old=without_unit(self.cache(full),self.url(2024))
    self.assertLess(len(old['entries']),6)
    self.calls.clear()
    update=self.parse(old)
    self.assertEqual(full['entries'],update['entries'])
    self.assertEqual([self.recipe.URL,self.url(2024),self.url(2026)],self.calls)
    self.calls.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])
    self.assertEqual([self.recipe.URL,self.url(2026)],self.calls)

  def test_rollover_and_archive_removal(self):
    old=self.cache(self.parse())
    self.years=[2025,2026,2027]
    self.winners[2027]='First'
    self.dates.datetime.now.return_value.year=2027
    self.calls.clear()
    update=self.parse(old)
    self.assertEqual([self.recipe.URL,self.url(2027)],self.calls)
    self.assertEqual(self.parse()['entries'],update['entries'])

  def test_changed_historical_winner_refetches_year_and_demotes_old_winner(self):
    old=self.cache(self.parse())
    self.winners[2024]='Other'
    self.calls.clear()
    update=self.parse(old)
    self.assertIn(self.url(2024),self.calls)
    self.assertEqual('winner',next(r for r in update['entries'] if r['title']=='Other 2024')['result'])
    self.assertEqual('shortlisted',next(r for r in update['entries'] if r['title']=='First 2024')['result'])
    self.assertEqual(self.parse()['entries'],update['entries'])

  def test_winnerless_history_and_latest_remain_fresh(self):
    del self.winners[2024]
    old=self.cache(self.parse())
    self.dates.datetime.now.return_value.year=2028
    self.calls.clear()
    self.parse(old)
    self.assertEqual([self.recipe.URL,self.url(2024),self.url(2026)],self.calls)

  def test_failed_empty_and_wrong_year_pages_retain_pending_shortlist(self):
    full=self.parse()
    old=self.cache(full)
    old['incremental_state']['units'][self.url(2024)]['complete']=False
    for mode in ('offline','empty','wrong-year'):
      self.failures.clear()
      if mode=='offline': self.failures[self.url(2024)]=OSError('offline')
      else: self.pages[2024]='<title>Goldsmiths Prize 2020</title>' if mode=='wrong-year' else '<h1>Access denied</h1>'
      parsed=self.parse(old)
      self.assertEqual(full['entries'],parsed['entries'])
      self.assertFalse(parsed['incremental_state']['units'][self.url(2024)]['complete'])
      self.assertTrue(parsed['notes'])
    self.pages.clear()
    self.failures.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(parsed))['entries'])

  def test_legacy_scope_and_critical_errors(self):
    full=self.parse()
    wrong=self.cache(full)
    wrong['incremental_state']['source_key']='another award'
    for old in ({'entries':full['entries']},wrong,['invalid cache']):
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(old)['entries'])
      self.assertEqual(4,len(self.calls))
    for error in (ImportCancelledError('stop'),CamoufoxRequiredError('required')):
      self.failures[self.url(2026)]=error
      with self.assertRaises(type(error)): self.parse(self.cache(full))


if __name__=='__main__':
  unittest.main()
