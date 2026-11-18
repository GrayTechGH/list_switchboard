import json
import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError,ImportCancelledError
from storage import build_import_cache_data
from url_fetcher import governor_general as gg


RECIPES=(gg.UrlFetcherGovernorGeneralEnglishFiction,gg.UrlFetcherGovernorGeneralEnglishNonfiction,
  gg.UrlFetcherGovernorGeneralEnglishYoungPeoplesText,gg.UrlFetcherGovernorGeneralEnglishYoungPeoplesIllustratedBooks,
  gg.UrlFetcherGovernorGeneralFrenchYoungPeoplesText,gg.UrlFetcherGovernorGeneralFrenchYoungPeoplesIllustratedBooks)


class GovernorGeneralUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=RECIPES[0]()
    self.version='20250923'
    self.endpoint='https://ggbooks.ca/Areas/GGBooks/json/books-2025.json'
    self.calls,self.failures=[],{}
    self.years=[2025,2024,2023]
    self.title_suffix=''
    self.clock=patch('url_fetcher.governor_general.datetime')
    self.dates=self.clock.start()
    self.dates.datetime.now.return_value.year=2026
    self.addCleanup(self.clock.stop)

  def module(self):
    return f'https://ggbooks.ca/Areas/GGBooks/js/Components/Archives{self.version}.js'

  def payload(self):
    return {str(y):{self.recipe.CATEGORY_KEYS[0]:{self.recipe.LANGUAGE:{'finalists':[
      {'title':f'Book {y}'+self.title_suffix,'author':'Writer One','winner':True},
      {'title':f'Other {y}','author':'Writer Two','winner':False}]}}} for y in self.years}

  def fetch(self,url,**options):
    self.calls.append(url)
    failure=self.failures.get(url)
    if failure:
      if isinstance(failure,list):
        item=failure.pop(0)
        if item: raise item
      else: raise failure
    if url==self.recipe.URL:
      return f'<div data-ux-module="Components/Archives{self.version}"></div>'
    if '/Components/' in url:
      return f'$.getJSON("{self.endpoint}", function(data) {{}});'
    if url==self.endpoint:
      return json.dumps(self.payload())
    if url==gg.GOVERNOR_GENERAL_2025_WIKIPEDIA_URL:
      return f'<h2>English</h2><table><tr><th>Category</th><th>Winner</th><th>Nominated</th></tr><tr><td>{self.recipe.CATEGORY}</td><td>Writer One, Book 2025</td><td>Writer Two, Other 2025</td></tr></table>'
    if url==gg.GOVERNOR_GENERAL_2025_PRESS_URL:
      return '<h1>Governor General Winners 2025</h1>'
    raise ValueError(url)

  def parse(self,old=None,**kwargs):
    return self.recipe.fetch_and_parse(self.fetch,cached_parsed=old,incremental_update=old is not None,**kwargs)

  def cache(self,parsed):
    return build_import_cache_data(self.recipe.source_id,parsed)

  def test_all_six_recipes_missing_year_recovery_and_repeat_download_fresh_json(self):
    for cls in RECIPES:
      self.recipe=cls()
      self.calls.clear()
      full=self.parse()
      self.assertEqual(3,len(self.calls))
      old=without_unit(self.cache(full),'official-2025')
      self.calls.clear()
      update=self.parse(old)
      self.assertEqual(full['entries'],update['entries'])
      self.assertEqual([self.recipe.URL,self.endpoint],self.calls)
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])
      self.assertEqual([self.recipe.URL,self.endpoint],self.calls)

  def test_new_module_discovers_new_endpoint_and_new_year_without_stale_json(self):
    old=self.cache(self.parse())
    self.version='20261001'
    self.endpoint='https://ggbooks.ca/Areas/GGBooks/json/books-2026.json'
    self.years.insert(0,2026)
    self.calls.clear()
    update=self.parse(old)
    self.assertEqual([self.recipe.URL,self.module(),self.endpoint],self.calls)
    self.assertEqual(self.parse()['entries'],update['entries'])

  def test_same_endpoint_corrections_and_removals_are_fresh(self):
    old=self.cache(self.parse())
    self.years.remove(2023)
    self.title_suffix=' corrected'
    self.calls.clear()
    update=self.parse(old)
    self.assertEqual(2,len(self.calls))
    self.assertEqual(self.parse()['entries'],update['entries'])

  def test_failed_or_invalid_cached_endpoint_rediscovery_and_pending_retention(self):
    full=self.parse()
    for failure in (OSError('endpoint unavailable'),ValueError('invalid JSON')):
      self.failures[self.endpoint]=[failure,None]
      self.calls.clear()
      update=self.parse(self.cache(full))
      self.assertEqual(full['entries'],update['entries'])
      self.assertEqual([self.recipe.URL,self.endpoint,self.module(),self.endpoint],self.calls)
    self.failures[self.endpoint]=OSError('offline')
    pending=self.parse(self.cache(full))
    self.assertEqual(self.cache(full)['entries'],pending['entries'])
    self.assertTrue(pending['notes'])
    self.assertTrue(all(not u['complete'] for u in pending['incremental_state']['units'].values()))
    self.failures.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(pending))['entries'])

  def test_unversioned_module_and_bad_endpoint_scope_do_not_reuse_mapping(self):
    full=self.parse()
    old=self.cache(full)
    old['incremental_state']['discovery']['json_url']='https://elsewhere.example/books.json'
    self.calls.clear()
    self.parse(old)
    self.assertEqual([self.recipe.URL,self.module(),self.endpoint],self.calls)
    self.version=''
    old=self.cache(self.parse())
    self.calls.clear()
    self.parse(old)
    self.assertEqual([self.recipe.URL,self.module(),self.endpoint],self.calls)

  def test_legacy_wrong_configuration_and_source_constraints(self):
    full=self.parse()
    wrong=self.cache(full)
    wrong['incremental_state']['source_key']='another language'
    for old in ({'entries':full['entries']},wrong,['invalid container']):
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(old)['entries'])
      self.assertEqual(3,len(self.calls))
    for options in ({'source_choice':0},{'force_fallback_level':1}):
      with self.assertRaises(gg.UrlFetcherError): self.parse(**options)

  def test_closed_supplement_reuse_pending_retry_and_official_replacement(self):
    self.years.remove(2025)
    full=self.parse()
    self.assertEqual(5,len(self.calls))
    old=self.cache(full)
    self.calls.clear()
    self.assertEqual(full['entries'],self.parse(old)['entries'])
    self.assertEqual(2,len(self.calls))
    old['incremental_state']['units']['supplement-2025']['complete']=False
    self.failures[gg.GOVERNOR_GENERAL_2025_WIKIPEDIA_URL]=OSError('offline')
    pending=self.parse(old)
    self.assertEqual(full['entries'],pending['entries'])
    self.assertFalse(pending['incremental_state']['units']['supplement-2025']['complete'])
    self.failures.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(pending))['entries'])
    self.years.insert(0,2025)
    self.calls.clear()
    replaced=self.parse(self.cache(full))
    self.assertNotIn(gg.GOVERNOR_GENERAL_2025_WIKIPEDIA_URL,self.calls)
    self.assertNotIn('supplement-2025',replaced['incremental_state']['units'])
    self.assertEqual(self.parse()['entries'],replaced['entries'])

  def test_disabled_supplement_and_current_year_do_not_reuse_closed_supplement(self):
    self.years.remove(2025)
    full=self.parse()
    self.calls.clear()
    parsed=self.parse(self.cache(full),disable_fallbacks=True)
    self.assertNotIn('2025',{r['award_year'] for r in parsed['entries']})
    self.dates.datetime.now.return_value.year=2025
    self.calls.clear()
    self.parse(self.cache(full))
    self.assertIn(gg.GOVERNOR_GENERAL_2025_WIKIPEDIA_URL,self.calls)

  def test_critical_errors_propagate_in_json_and_supplement(self):
    old=self.cache(self.parse())
    for error in (ImportCancelledError('stop'),CamoufoxRequiredError('required')):
      self.failures[self.endpoint]=error
      with self.assertRaises(type(error)): self.parse(old)
      self.failures.clear()
      self.years=[2024]
      self.failures[gg.GOVERNOR_GENERAL_2025_WIKIPEDIA_URL]=error
      with self.assertRaises(type(error)): self.parse()
      self.failures.clear()


if __name__=='__main__':
  unittest.main()
