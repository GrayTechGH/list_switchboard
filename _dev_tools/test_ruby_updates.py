import copy
import json
import unittest

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError,ImportCancelledError
from parser.romance_writers_australia import RomanceWritersAustraliaRubyParser,RWAUS_RUBY_CDX_URL
from storage import build_import_cache_data
from url_fetcher.romance_writers_australia import UrlFetcherRomanceWritersAustraliaRubyAwards


class RubyUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=UrlFetcherRomanceWritersAustraliaRubyAwards()
    self.calls,self.failures,self.overrides=[],{},{}
    self.timestamp='20210101000000'
    self.digest='abc'
    self.title='Current Book'
    self.tracker='one'
    self.article_year=2022
    self.archive_title='Historical Book'

  def snapshot(self):
    return f'https://web.archive.org/web/{self.timestamp}id_/http://romanceaustralia.com/ruby'

  def search(self):
    return json.dumps({'resources':{'results':{'articles':[{'title':f'RUBY finalists {self.article_year}',
      'url':f'/blogs/blog/ruby-{self.article_year}?_psid={self.tracker}&_pos=1&_ss=e',
      'body':f'<h4>Romantic Suspense</h4><p><strong>Current Writer</strong> - {self.title}</p>'}]}}})

  def archive(self):
    return f'''<div class="entry-content"><table><tr><th>Year</th><th>Category</th><th>Title</th><th>Author</th></tr>
      <tr><td>2020</td><td>Romantic Suspense</td><td>{self.archive_title}</td><td>Historic Writer</td></tr></table></div>'''

  def fetch(self,url):
    self.calls.append(url)
    if url in self.failures:raise self.failures[url]
    if url in self.overrides:return self.overrides[url]
    if url==self.recipe.URL:return self.search()
    if url==RWAUS_RUBY_CDX_URL:return json.dumps([['timestamp','original','statuscode','mimetype','digest'],
      [self.timestamp,'http://romanceaustralia.com/ruby','200','text/html',self.digest]])
    if url==self.snapshot():return self.archive()
    raise AssertionError(url)

  def parse(self,old=None,incremental=None):
    return self.recipe.fetch_and_parse(self.fetch,cached_parsed=old,
      incremental_update=(old is not None) if incremental is None else incremental)

  def cache(self,parsed):
    return build_import_cache_data(self.recipe.source_id,parsed)

  def test_missing_current_entries_recovered_and_repeated_update_skips_capture(self):
    full=self.parse()
    self.assertEqual(3,len(self.calls))
    old=without_unit(self.cache(full),'shopify')
    self.assertLess(len(old['entries']),len(full['entries']))
    self.calls.clear()
    update=self.parse(old)
    self.assertEqual(full['entries'],update['entries'])
    self.assertEqual([self.recipe.URL,RWAUS_RUBY_CDX_URL],self.calls)
    self.calls.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])
    self.assertEqual(2,len(self.calls))

  def test_missing_archive_refetches_capture(self):
    full=self.parse()
    old=without_unit(self.cache(full),'archive')
    self.calls.clear()
    self.assertEqual(full['entries'],self.parse(old)['entries'])
    self.assertIn(self.snapshot(),self.calls)

  def test_changed_capture_and_digest_replace_old_results(self):
    old=self.cache(self.parse())
    for change in ('timestamp','digest'):
      if change=='timestamp':self.timestamp='20220101000000'
      else:self.digest='changed'
      self.archive_title+=' Corrected'
      self.calls.clear()
      update=self.parse(old)
      self.assertIn(self.snapshot(),self.calls)
      self.assertEqual(self.parse()['entries'],update['entries'])
      self.assertNotIn('Historical Book',[r['title'] for r in update['entries']])
      old=self.cache(update)

  def test_fresh_article_corrections_removals_and_new_year_replace_snapshot(self):
    old=self.cache(self.parse())
    self.title='Corrected Current Book';self.article_year=2023
    update=self.parse(old)
    self.assertEqual(self.parse()['entries'],update['entries'])
    self.assertNotIn('Current Book',[r['title'] for r in update['entries']])
    self.overrides[self.recipe.URL]=json.dumps({'resources':{'results':{'articles':[]}}})
    update=self.parse(self.cache(update))
    self.assertEqual(['Historical Book'],[r['title'] for r in update['entries']])

  def test_search_tracking_does_not_change_provenance(self):
    full=self.parse();self.tracker='two'
    self.assertEqual(full['entries'],self.parse(self.cache(full))['entries'])
    self.assertTrue(all('_psid' not in r['source']['url'] for r in full['entries']))

  def test_archive_and_index_failures_preserve_history_pending_retry(self):
    full=self.parse()
    old=self.cache(full)
    for target in (RWAUS_RUBY_CDX_URL,self.snapshot()):
      self.digest='new'
      self.failures={target:RuntimeError('offline')}
      update=self.parse(old)
      self.assertEqual(full['entries'],update['entries'])
      self.assertFalse(update['incremental_state']['units']['archive']['complete'])
      self.failures.clear()
      self.calls.clear()
      repaired=self.parse(self.cache(update))
      self.assertTrue(repaired['incremental_state']['units']['archive']['complete'])
      self.assertIn(self.snapshot(),self.calls)

  def test_invalid_sources_retain_units_without_certifying_them(self):
    full=self.parse();old=self.cache(full)
    for bad in ('[]','{}','<html>Access denied</html>'):
      self.overrides[self.recipe.URL]=bad
      self.overrides[RWAUS_RUBY_CDX_URL]=bad
      update=self.parse(old)
      self.assertEqual(full['entries'],update['entries'])
      self.assertFalse(update['incremental_state']['units']['archive']['complete'])
      self.assertFalse(update['incremental_state']['units']['shopify']['complete'])
    self.overrides.clear();self.digest='new'
    self.overrides[self.snapshot()]='<html>Challenge</html>'
    self.assertEqual(full['entries'],self.parse(old)['entries'])

  def test_legacy_wrong_scope_and_complete_refresh_read_capture(self):
    old=self.cache(self.parse())
    legacy=copy.deepcopy(old);legacy.pop('incremental_state')
    wrong=copy.deepcopy(old);wrong['incremental_state']['source_key']='other'
    for candidate,incremental in ((legacy,True),(wrong,True),(old,False)):
      self.calls.clear()
      self.parse(candidate,incremental)
      self.assertIn(self.snapshot(),self.calls)

  def test_cancellation_and_browser_requirements_propagate(self):
    for target in (RWAUS_RUBY_CDX_URL,self.snapshot()):
      for cls in (ImportCancelledError,CamoufoxRequiredError):
        self.failures={target:cls('stop')}
        with self.assertRaises(cls):self.parse()

  def test_cdx_rejects_unrelated_hosts_and_non_http_captures(self):
    parser=RomanceWritersAustraliaRubyParser()
    for original in ('https://example.org/ruby','file:///C:/ruby','javascript:alert(1)'):
      self.assertFalse(parser.snapshot_from_cdx(json.dumps([['timestamp','original'],['20200101000000',original]])))

  def test_year_placing_tables_keep_finalists_winners_and_category_boundaries(self):
    html='''<div class="entry-content"><table>
      <tr><td>Year</td><td>Placing</td><td>Author</td><td>Title</td></tr>
      <tr><td>2014</td><td></td><td></td><td></td></tr>
      <tr><td colspan="2">Long Romance</td><td></td><td></td></tr>
      <tr><td></td><td>Finalist</td><td>Writer One</td><td>Finalist Book</td></tr>
      <tr><td></td><td>WINNER</td><td>Writer Two</td><td>Winning Book</td></tr>
      <tr><td>2013</td><td></td><td></td><td></td></tr>
      <tr><td></td><td>WINNER</td><td>Writer Three</td><td>Outside Category</td></tr>
      <tr><td>Short Sweet</td><td></td><td></td><td></td></tr>
      <tr><td></td><td>WINNER</td><td>Writer Four</td><td>Earlier Book</td></tr>
      <tr><td></td><td>Finalist</td><td></td><td>Missing Author</td></tr></table></div>
      <aside><h2>2019</h2><h3>Recent Posts</h3><p>Not a Book by Blogger</p></aside>'''
    rows=RomanceWritersAustraliaRubyParser().parse_archived_winner_rows(html,'https://example.org')
    self.assertEqual([('2014','Finalist Book','shortlisted'),('2014','Winning Book','winner'),('2013','Earlier Book','winner')],
      [(r['award_year'],r['title'],r['result']) for r in rows])

  def test_inline_rosters_respect_award_year_title_by_and_ella_boundary(self):
    html='''<div class="entry-content">
      <p>RWA congratulates the finalists in the Romantic Book of The Year 2018, for books published in 2017.</p>
      <div><strong>Long Romance</strong></div><ul><li>Tempted By The Wrong Twin – Rachel Bailey – WINNER</li></ul>
      <div>OVERALL RUBY</div><p>Tempted By The Wrong Twin – Rachel Bailey</p>
      <div class="x-accordion-group"><div class="x-accordion-heading"><a>RUBY 2017</a></div>
      <div class="x-accordion-inner"><p><strong>Long Romance</strong></p>
      <ul><li>Earlier Book by Avril Tremayne – Publisher – WINNER</li></ul></div></div>
      <div class="x-accordion-heading"><a>RUBY and ELLA 2015</a></div>
      <p>Long Romance:<br><strong>Old Book – Writer – Publisher – WINNER</strong><br>Other Book – Other Writer – Publisher</p>
      <p><strong>Ella</strong></p><p>Excluded – Another Writer – EQUAL WINNER</p></div>'''
    rows=RomanceWritersAustraliaRubyParser().parse_archived_winner_rows(html,'https://example.org')
    self.assertEqual([('2018','Tempted By The Wrong Twin','Rachel Bailey','winner'),
      ('2018','Tempted By The Wrong Twin','Rachel Bailey','winner'),('2017','Earlier Book','Avril Tremayne','winner'),
      ('2015','Old Book','Writer','winner'),('2015','Other Book','Other Writer','shortlisted')],
      [(r['award_year'],r['title'],r['author'],r['result']) for r in rows])

  def test_profiles_and_rules_are_excluded_from_aggregate_rosters(self):
    parser=RomanceWritersAustraliaRubyParser()
    for title in ('The RUBY Monologues | Writer','2019 RUBY CONTEST RULES & CONDITIONS'):
      self.assertFalse(parser.accept_shopify_article({'title':title,'body':'<p>We interviewed a RUBY finalist.</p><h4>Other Books</h4><p>Writer - Unrelated Title</p>'}))

  def test_cache_contains_only_parsed_projections(self):
    old=self.cache(self.parse())
    self.assertNotIn('<table>',json.dumps(old))
    self.assertTrue(all(unit['complete'] for unit in old['incremental_state']['units'].values()))
