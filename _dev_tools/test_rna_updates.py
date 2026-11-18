import copy
import json
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError,ImportCancelledError
from parser.rna_awards import RNARomanticNovelAwardsParser
from storage import build_import_cache_data
from url_fetcher.rna_awards import UrlFetcherRNARomanticNovelAwards,UrlFetcherRNAJoanHessayonAward


RECIPES=(UrlFetcherRNARomanticNovelAwards,UrlFetcherRNAJoanHessayonAward)


class RNAUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=RECIPES[0]()
    self.years=[2026,2025,2024]
    self.calls,self.failures,self.overrides=[],{},{}
    self.winner=0
    self.closed=True
    self.last_page=4
    self.revised=set()
    self.clock=patch('parser.rna_awards.datetime')
    self.dates=self.clock.start()
    self.dates.datetime.now.return_value.year=2026
    self.addCleanup(self.clock.stop)

  def post_url(self,year):
    return f'https://romanticnovelistsassociation.org/wp-json/wp/v2/news/{year}'

  def category(self):
    return 'Joan Hessayon' if self.recipe.source_id=='rna_joan_hessayon_award' else 'Romantic Comedy'

  def book(self,year,index):
    return f'Book {year} {index}'

  def archive_row(self,year,group=None):
    group=group or ('Joan Hessayon' if self.category()=='Joan Hessayon' else 'Romantic Novel of the Year')
    return (f'<h2><a href="/past-winners/{year}">{self.book(year,self.winner)}</a></h2>'
      f'<h2>Writer {self.winner}</h2><ul class="info"><li>Publisher</li></ul>'
      f'<ul class="tags"><li><a>{group}</a></li><li><a>{self.category()}</a></li><li><a>{year}</a></li></ul>')

  def front(self):
    return self.archive_row(2026)+self.archive_row(2025)+f'<a href="/past-winners/page/2/">2</a><a href="/past-winners/page/{self.last_page}">{self.last_page}</a>'

  def search(self):
    return json.dumps([{'title':f'{year} '+('Joan Hessayon finalists' if self.category()=='Joan Hessayon' else 'Romantic Novel Awards shortlists')+(' revised' if year in self.revised else ''),
      '_links':{'self':[{'href':self.post_url(year)}]}} for year in self.years])

  def post(self,year):
    return json.dumps({'title':{'rendered':f'{year} finalists'},'link':f'https://romanticnovelistsassociation.org/news/finalists-{year}',
      'content':{'rendered':f'<h3>The {self.category()} Award</h3>'+''.join(
        f'<p><em>{self.book(year,i)}</em> by Writer {i} (Publisher)</p>' for i in range(2))}})

  def fetch(self,url):
    self.calls.append(url)
    if url in self.failures:raise self.failures[url]
    if url in self.overrides:return self.overrides[url]
    if url==self.recipe.URL:return self.front()
    if '/page/' in url:
      number=int(url.rstrip('/').rsplit('/',1)[-1])
      return self.archive_row(2024) if number==2 and self.closed else self.archive_row(2000+number,'RNA Industry')
    if url in self.recipe.parser().SHORTLIST_SEARCH_URLS:return self.search()
    return self.post(int(url.rsplit('/',1)[-1]))

  def parse(self,old=None,incremental=None):
    return self.recipe.fetch_and_parse(self.fetch,cached_parsed=old,
      incremental_update=(old is not None) if incremental is None else incremental)

  def cache(self,parsed):
    return build_import_cache_data(self.recipe.source_id,parsed)

  def test_both_recipes_recover_missing_entries_and_repeat_with_fewer_fetches(self):
    for cls in RECIPES:
      self.recipe=cls()
      self.calls.clear()
      full=self.parse()
      full_count=len(self.calls)
      self.assertEqual(6,len(full['entries']))
      old=without_unit(self.cache(full),self.post_url(2025))
      self.assertLess(len(old['entries']),len(full['entries']))
      self.calls.clear()
      update=self.parse(old)
      self.assertEqual(full['entries'],update['entries'])
      self.assertEqual(full_count-1,len(self.calls))
      self.calls.clear()
      repeat=self.parse(self.cache(update))
      self.assertEqual(full['entries'],repeat['entries'])
      self.assertEqual(full_count-2,len(self.calls))
      self.assertIn(self.post_url(2026),self.calls)
      self.assertNotIn(self.post_url(2024),self.calls)

  def test_pagination_ellipsis_and_shifted_pages_are_always_fresh(self):
    old=self.cache(self.parse())
    self.last_page=5
    self.calls.clear()
    update=self.parse(old)
    for page in (2,3,4,5):
      self.assertTrue(any(f'/page/{page}' in url for url in self.calls))
    self.assertEqual(self.parse()['entries'],update['entries'])

  def test_archive_correction_promotes_and_demotes_original_nominees(self):
    old=self.cache(self.parse())
    self.winner=1
    self.calls.clear()
    update=self.parse(old)
    self.assertNotIn(self.post_url(2025),self.calls)
    self.assertEqual(self.parse()['entries'],update['entries'])
    results={r['title']:r['result'] for r in update['entries'] if r['award_year']=='2025'}
    self.assertEqual({'Book 2025 0':'shortlisted','Book 2025 1':'winner'},results)

  def test_new_removed_and_reordered_posts_follow_fresh_manifest(self):
    old=self.cache(self.parse())
    self.years=[2023,2026,2025]
    update=self.parse(old)
    self.assertNotIn('Book 2024 1',[r['title'] for r in update['entries']])
    self.assertEqual(self.parse()['entries'],update['entries'])
    self.years.reverse()
    self.assertEqual(self.parse()['entries'],self.parse(self.cache(update))['entries'])

  def test_changed_revision_refetches_closed_post(self):
    old=self.cache(self.parse())
    self.revised.add(2025)
    self.calls.clear()
    self.assertEqual(self.parse(old)['entries'],self.parse()['entries'])
    self.assertEqual(2,self.calls.count(self.post_url(2025)))

  def test_winnerless_category_keeps_post_fresh(self):
    self.closed=False
    old=self.cache(self.parse())
    self.calls.clear()
    self.parse(old)
    self.assertIn(self.post_url(2024),self.calls)
    self.assertNotIn(self.post_url(2025),self.calls)

  def test_failed_and_challenged_posts_retain_entries_pending_retry(self):
    full=self.parse()
    old=self.cache(full)
    url=self.post_url(2026)
    for failure in (RuntimeError('offline'),'<html>Verification required</html>'):
      self.failures.clear();self.overrides.clear()
      if isinstance(failure,Exception):self.failures[url]=failure
      else:self.overrides[url]=failure
      update=self.parse(old)
      self.assertEqual(full['entries'],update['entries'])
      self.assertFalse(update['incremental_state']['units'][url]['complete'])
      self.assertTrue(update['notes'])
    self.overrides.clear()
    self.assertTrue(self.parse(self.cache(update))['incremental_state']['units'][url]['complete'])

  def test_archive_failure_retains_winners_and_disables_closed_reuse(self):
    full=self.parse()
    self.overrides[self.recipe.URL] = '<html>Verification required</html>'
    self.calls.clear()
    update=self.parse(self.cache(full))
    self.assertEqual({r['title'] for r in full['entries']},{r['title'] for r in update['entries']})
    self.assertFalse(update['incremental_state']['units']['archive']['complete'])
    self.assertIn(self.post_url(2025),self.calls)

  def test_failed_search_retains_known_posts_and_leaves_units_pending(self):
    full=self.parse()
    for bad in ('','{}','<html>Blocked</html>'):
      self.overrides[self.recipe.parser().SHORTLIST_SEARCH_URLS[0]]=bad
      self.years=[2026]
      update=self.parse(self.cache(full))
      self.assertEqual(full['entries'],update['entries'])
      self.assertFalse(update['incremental_state']['units'][self.post_url(2025)]['complete'])

  def test_legacy_incompatible_and_complete_refresh_fetch_all_posts(self):
    old=self.cache(self.parse())
    legacy=copy.deepcopy(old);legacy.pop('incremental_state')
    wrong=copy.deepcopy(old);wrong['incremental_state']['source_key']='different source'
    for candidate,incremental in ((legacy,True),(wrong,True),(old,False)):
      self.calls.clear()
      self.parse(candidate,incremental)
      for year in self.years:self.assertIn(self.post_url(year),self.calls)

  def test_cancellation_and_browser_requirements_propagate_at_each_boundary(self):
    for url in (self.recipe.URL+'/page/2/',self.recipe.parser().SHORTLIST_SEARCH_URLS[0],self.post_url(2026)):
      for cls in (ImportCancelledError,CamoufoxRequiredError):
        self.failures={url:cls('stop')}
        with self.assertRaises(cls):self.parse()

  def test_shortlist_source_formats_preserve_commas_suffixes_and_boundaries(self):
    parser=RNARomanticNovelAwardsParser()
    content='''<h4><b>The Libert</b><b>à</b><b> Books Shorter Romantic Novel Award:</b></h4>
      <p><i>Secret Baby, Second Chance</i>, Walter M. Miller, Jr., Publisher</p>
      <p>Plain Title, Other Writer, <em>Publisher</em></p>
      <p><b>THE WINNER OF THE POPULAR ROMANTIC FICTION AWARD:</b></p>
      <p>Winning Title, Winning Writer, Publisher</p>
      <p>ABOUT THE AWARD SPONSORS:</p>
      <p><strong>The Romantic Comedy Award</strong></p>
      <p>Biography, Some Person, Publisher</p>'''
    rows=parser.parse_shortlist_content(content,'https://example.org',2022)
    self.assertEqual([('Secret Baby, Second Chance','Walter M. Miller, Jr.','Shorter Romantic Novel','shortlisted'),
      ('Plain Title','Other Writer','Shorter Romantic Novel','shortlisted'),
      ('Winning Title','Winning Writer','POPULAR ROMANTIC FICTION','winner')],
      [(r['title'],r['author'],r['category'],r['result']) for r in rows])

  def test_narrative_footer_without_heading_and_sponsor_category_are_excluded(self):
    parser=RNARomanticNovelAwardsParser()
    content='''<p><strong>The Romantic Comedy Award</strong></p><p><em>Real Book</em>, Writer, Publisher</p>
      <p>Bestselling historical novelist Alison Weir will present the Awards for 2019, One Whitehall Place, London.</p>
      <p>Commentary, Writer, Publisher</p><p><b>The Romantic Comedy Award</b></p><p>More prose, Writer, Publisher</p>'''
    self.assertEqual(['Real Book'],[r['title'] for r in parser.parse_shortlist_content(content,'https://example.org',2019)])
    heading=BeautifulSoup('<p><b>The Contemporary Romantic Novel Award, and the Historical Romantic Novel Award</b></p>','html.parser').p
    self.assertFalse(parser.is_shortlist_category_node(heading))

  def test_runtime_cache_contains_parsed_projections_without_raw_pages(self):
    old=self.cache(self.parse())
    self.assertNotIn('<h2>',json.dumps(old))
    self.assertNotIn('content',old['incremental_state'])
    self.assertTrue(all(unit['complete'] for unit in old['incremental_state']['units'].values()))
