import copy
import json
import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError,ImportCancelledError
from parser.holt_medallion import HOLT_SEARCH_URL
from storage import build_import_cache_data
from url_fetcher.holt_medallion import UrlFetcherHOLTMedallion


class HOLTUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=UrlFetcherHOLTMedallion()
    self.years=[2024,2025,2026]
    self.calls,self.failures,self.overrides=[],{},{}
    self.revised=set()
    self.winner=0
    self.clock=patch('parser.holt_medallion.datetime')
    self.dates=self.clock.start()
    self.dates.datetime.now.return_value.year=2026
    self.addCleanup(self.clock.stop)

  def ref(self,year,kind):
    title='HOLT Medallion Past Winners' if year is None else f'{year} HOLT Medallion {kind.title()}'
    if year in self.revised:title+=' revised'
    slug='past-winners' if year is None else f'{year}-{kind}'
    return {'title':title,'url':f'https://virginiaromancewriters.com/holt-{slug}/',
      'rest_url':f'https://virginiaromancewriters.com/wp-json/wp/v2/pages/{slug}'}

  def refs(self):
    return [self.ref(None,'history')]+[self.ref(y,k) for y in self.years for k in ('finalists','winners')]

  def search(self):
    return json.dumps([{'title':r['title'],'url':r['url'],'_links':{'self':[{'href':r['rest_url']}]}} for r in self.refs()])

  def front(self):
    return ''.join(f'<a href="{r["url"]}">{r["title"]}</a>' for r in self.refs()[:1])

  def page(self,ref):
    if 'past-winners' in ref['url']:
      body='<div><p>2017 Winners and Award of Merit Finalists</p><h3>Contemporary</h3><p>Winner</p><p>An Old Story by First Writer &amp; Second Writer</p></div>'
    elif 'finalists' in ref['url']:
      body='<h3>Contemporary</h3><ul>'+''.join(f'<li>Book {i} by Writer {i}</li>' for i in range(2))+'</ul>'
    else:
      body=f'<h3>Contemporary</h3><p>Book {self.winner} by Writer {self.winner}</p>'
    return json.dumps({'title':{'rendered':ref['title']},'link':ref['url'],'content':{'rendered':body}})

  def fetch(self,url):
    self.calls.append(url)
    if url in self.failures:raise self.failures[url]
    if url in self.overrides:return self.overrides[url]
    if url==self.recipe.URL:return self.front()
    if url==HOLT_SEARCH_URL:return self.search()
    return self.page(next(r for r in self.refs() if r['rest_url']==url))

  def parse(self,old=None,incremental=None):
    return self.recipe.fetch_and_parse(self.fetch,cached_parsed=old,
      incremental_update=(old is not None) if incremental is None else incremental)

  def cache(self,parsed):
    return build_import_cache_data(self.recipe.source_id,parsed)

  def test_missing_annual_ballot_recovered_and_repeat_skips_closed_years(self):
    full=self.parse()
    self.assertEqual(7,len(full['entries']))
    self.assertEqual(9,len(self.calls))
    old=without_unit(self.cache(full),'2025')
    self.assertEqual(5,len(old['entries']))
    self.calls.clear()
    update=self.parse(old)
    self.assertEqual(full['entries'],update['entries'])
    self.assertEqual(7,len(self.calls))
    self.calls.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])
    self.assertEqual(5,len(self.calls))

  def test_coauthor_rows_remain_covered_through_storage_round_trip(self):
    old=self.cache(self.parse())
    used={i for u in old['incremental_state']['units'].values() for i in u['entry_indexes']}
    self.assertEqual(set(range(len(old['entries']))),used)
    self.assertIn(['First Writer','Second Writer'],[r['authors'] for r in old['entries']])
    self.calls.clear();self.parse(old)
    self.assertNotIn(self.ref(2025,'finalists')['rest_url'],self.calls)

  def test_new_removed_and_revised_year_refs_replace_units(self):
    old=self.cache(self.parse())
    self.years=[2025,2026,2027]
    self.revised.add(2025)
    update=self.parse(old)
    self.assertEqual(self.parse()['entries'],update['entries'])
    self.assertNotIn('2024',{r['award_year'] for r in update['entries']})
    self.assertIn(self.ref(2025,'winners')['rest_url'],self.calls)

  def test_current_winner_change_demotes_original_nominee(self):
    old=self.cache(self.parse())
    self.winner=1
    update=self.parse(old)
    expected={r['title']:r['result'] for r in update['entries'] if r['award_year']=='2026'}
    self.assertEqual({'Book 1':'winner','Book 0':'shortlisted'},expected)
    refreshed=self.parse()
    self.assertEqual([r for r in refreshed['entries'] if r['award_year']=='2026'],
      [r for r in update['entries'] if r['award_year']=='2026'])

  def test_winnerless_category_keeps_annual_ballot_fresh(self):
    ref=self.ref(2025,'finalists')
    page=json.loads(self.page(ref));page['content']['rendered']+='<h3>Historical</h3><ul><li>Other Book by Other Writer</li></ul>'
    self.overrides[ref['rest_url']]=json.dumps(page)
    old=self.cache(self.parse())
    self.assertFalse(old['incremental_state']['units']['2025']['metadata']['settled'])
    self.calls.clear();self.parse(old)
    self.assertIn(ref['rest_url'],self.calls)

  def test_failed_or_invalid_member_retains_whole_previous_ballot(self):
    full=self.parse();old=self.cache(full);ref=self.ref(2026,'winners')
    for bad in (RuntimeError('offline'),'<html>Challenge</html>'):
      self.failures.clear();self.overrides.clear()
      if isinstance(bad,Exception):self.failures[ref['rest_url']]=bad
      else:self.overrides[ref['rest_url']]=bad
      update=self.parse(old)
      self.assertEqual(full['entries'],update['entries'])
      self.assertFalse(update['incremental_state']['units']['2026']['complete'])
    self.overrides.clear()
    self.assertTrue(self.parse(self.cache(update))['incremental_state']['units']['2026']['complete'])

  def test_failed_discovery_retains_known_refs_pending_recovery(self):
    full=self.parse()
    self.overrides[HOLT_SEARCH_URL]='{}'
    update=self.parse(self.cache(full))
    self.assertEqual(full['entries'],update['entries'])
    self.assertTrue(all(not u['complete'] for u in update['incremental_state']['units'].values()))
    self.overrides.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])

  def test_known_video_only_winner_page_preserves_note_and_unsettled_state(self):
    ref=self.ref(2026,'winners');page=json.loads(self.page(ref));page['content']['rendered']='<video src="awards.mp4"></video>'
    self.overrides[ref['rest_url']]=json.dumps(page)
    full=self.parse();unit=full['incremental_state']['units']['2026']
    self.assertTrue(unit['complete']);self.assertFalse(unit['metadata']['settled'])
    self.assertTrue(any('video-only' in note for note in full['notes']))
    self.assertEqual(full['notes'],self.parse(self.cache(full))['notes'])

  def test_wrong_year_member_is_pending_and_does_not_relabel_books(self):
    full=self.parse();ref=self.ref(2026,'winners');page=json.loads(self.page(ref));page['title']['rendered']='2025 HOLT Medallion Winners'
    self.overrides[ref['rest_url']]=json.dumps(page)
    update=self.parse(self.cache(full))
    self.assertEqual(full['entries'],update['entries'])
    self.assertFalse(update['incremental_state']['units']['2026']['complete'])

  def test_legacy_scope_changes_and_complete_refresh_fetch_all_refs(self):
    old=self.cache(self.parse())
    legacy=copy.deepcopy(old);legacy.pop('incremental_state')
    wrong=copy.deepcopy(old);wrong['incremental_state']['source_key']='other'
    for candidate,incremental in ((legacy,True),(wrong,True),(old,False)):
      self.calls.clear();self.parse(candidate,incremental)
      self.assertEqual(9,len(self.calls))

  def test_cancellation_and_browser_requirements_propagate(self):
    for target in (HOLT_SEARCH_URL,self.ref(2026,'finalists')['rest_url']):
      for cls in (ImportCancelledError,CamoufoxRequiredError):
        self.failures={target:cls('stop')}
        with self.assertRaises(cls):self.parse()

  def test_cache_contains_parsed_rows_without_raw_pages(self):
    self.assertNotIn('<h3>',json.dumps(self.cache(self.parse())))
