import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError, ImportCancelledError
from storage import build_import_cache_data
from url_fetcher.andrew_carnegie import UrlFetcherAndrewCarnegieNonfiction
from url_fetcher.generic import UrlFetcherError


class AndrewCarnegieUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe,self.calls,self.failures=UrlFetcherAndrewCarnegieNonfiction(),[],{}
    self.urls=tuple(self.url(y) for y in (2026,2025,2024))
    self.manifest=patch('url_fetcher.andrew_carnegie.ANDREW_CARNEGIE_YEAR_URLS',self.urls)
    self.manifest.start()
    self.addCleanup(self.manifest.stop)
    self.clock=patch('parser.annual_updates.datetime')
    self.dates=self.clock.start()
    self.dates.datetime.now.return_value.year=2026
    self.addCleanup(self.clock.stop)

  def url(self,year):
    return f'https://www.ala.org/carnegie-medals/{year}-winners'

  def fetch(self,url):
    self.calls.append(url)
    if url in self.failures:
      raise self.failures[url]
    year=int(url.rsplit('/',1)[-1].split('-',1)[0])
    return '<h2>Nonfiction Winner</h2>'\
      f'<p><em>Winner {year}</em> by Writer One (Publisher)</p>'\
      '<h2>Nonfiction Finalists</h2>'\
      f'<p><em>Other {year}</em> by Writer Two (Publisher)</p>'\
      '<h2>Fiction Winner</h2><p><em>Excluded</em> by Wrong Writer</p>'

  def parse(self,old=None,**kwargs):
    return self.recipe.fetch_and_parse(self.fetch,cached_parsed=old,
      incremental_update=old is not None,**kwargs)

  def cache(self,parsed):
    return build_import_cache_data(self.recipe.source_id,parsed)

  def test_missing_year_repeat_and_added_configuration_reuse_other_history(self):
    full=self.parse()
    self.assertEqual(3,len(self.calls))
    old=without_unit(self.cache(full),self.url(2024))
    self.calls.clear()
    update=self.parse(old)
    self.assertEqual(full['entries'],update['entries'])
    self.assertEqual([self.url(2026),self.url(2024)],self.calls)
    self.calls.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])
    self.assertEqual([self.url(2026)],self.calls)
    with patch('url_fetcher.andrew_carnegie.ANDREW_CARNEGIE_YEAR_URLS',(self.url(2027),)+self.urls):
      self.dates.datetime.now.return_value.year=2027
      self.recipe.URL=self.url(2027)
      self.calls.clear()
      update=self.parse(self.cache(full))
      self.assertEqual([self.url(2027)],self.calls)
      self.assertEqual(self.parse()['entries'],update['entries'])

  def test_partial_import_and_update_failure_notes_remain_pending_then_recover(self):
    full=self.parse()
    self.failures[self.url(2024)]=OSError('offline')
    partial=self.parse()
    self.assertTrue(partial['notes'][0].startswith('Official ALA Carnegie page failed for'))
    self.assertFalse(partial['incremental_state']['units'][self.url(2024)]['complete'])
    old=self.cache(full)
    old['incremental_state']['units'][self.url(2024)]['complete']=False
    pending=self.parse(old)
    self.assertEqual(full['entries'],pending['entries'])
    self.failures.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(pending))['entries'])
    self.assertEqual(full['entries'],self.parse(self.cache(partial))['entries'])

  def test_incompatible_cache_choice_constraints_and_cancellation(self):
    full=self.parse()
    wrong=self.cache(full)
    wrong['incremental_state']['source_key']='different source'
    for old in ({'entries':full['entries']},wrong,['invalid cache container']):
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(old)['entries'])
      self.assertEqual(3,len(self.calls))
    for options in ({'source_choice':1},{'force_fallback_level':1}):
      with self.assertRaises(UrlFetcherError):
        self.parse(**options)
    for error in (ImportCancelledError('stop'),CamoufoxRequiredError('required')):
      self.failures[self.url(2026)]=error
      with self.assertRaises(type(error)):
        self.parse(self.cache(full))


if __name__=='__main__':
  unittest.main()
