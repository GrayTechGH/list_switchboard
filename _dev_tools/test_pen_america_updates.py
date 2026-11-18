import copy
import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError,ImportCancelledError
from parser.pen_america import PENAmericaAwardParser
from parser.pen_america_updates import annual_links
from storage import build_import_cache_data
from url_fetcher.pen_america import (UrlFetcherPENGalbraithAward,UrlFetcherPENDiamonsteinSpielvogelAward,
  UrlFetcherPENJeanSteinBookAward,UrlFetcherPENOpenBookAward,PEN_ANNUAL_POST_URLS)
from url_fetcher.pen_america_transport import PENAmericaFetchPolicy


FETCHERS=(UrlFetcherPENGalbraithAward,UrlFetcherPENDiamonsteinSpielvogelAward,
  UrlFetcherPENJeanSteinBookAward,UrlFetcherPENOpenBookAward)
OLD='https://pen.org/announcing-the-2025-pen-america-literary-awards-finalists/'
CURRENT='https://pen.org/2026-pen-america-literary-awards-finalists/'
NEW='https://pen.org/2027-pen-america-literary-awards-finalists/'


def document(title,body):
  return f'<html><head><title>{title} - PEN America</title></head><body><nav><p>2025, Navigation Writer</p></nav><main><h1 class="wp-block-post-title">{title}</h1><div class="wp-block-post-content">{body}</div></main><footer><p>2026, Footer Writer</p></footer></body></html>'


class PENAmericaUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=FETCHERS[0]();self.calls=[];self.failures={};self.overrides={}
    self.clock=patch('parser.pen_america_updates.datetime');self.dates=self.clock.start();self.addCleanup(self.clock.stop)
    self.dates.datetime.now.return_value.year=2026
    self.extra='';self.absent=set();self.changed_title={};self.promoted=False
    self.configure()

  def configure(self):self.recipe.ANNUAL_POST_URLS=((OLD,'annual'),(CURRENT,'annual'))

  def landing(self):
    return document(self.recipe.NAME,f'''<h2>2026 Winner</h2><p>Winner:<em> </em><strong>Current Writer</strong>, <em>Current Winner</em> (Publisher)</p>
      <p>From the judges citation: <strong>Current Writer</strong> has written <em>Current Winner</em>, a beautiful book.</p>
      <h3>Previous Winners</h3><p><strong>2025 Prior Writer, Jr.</strong>, <em>Prior Winner</em> (Publisher)</p>
      <p><strong>2024 Older Writer</strong>, <em>Older Winner</em> (Publisher)</p>
      <h2>Eligibility</h2><p>2026 <strong>Someone</strong>, <em>Not a Book</em></p>{self.extra}''')

  def annual(self,year):
    title=self.changed_title.get(year,'Prior Winner' if year==2025 else 'Current Winner')
    author='Prior Writer, Jr.' if year==2025 else 'Current Writer'
    heading='PEN Unrelated Prize' if year in self.absent else self.recipe.NAME
    return document(f'Announcing the {year} PEN America Literary Awards Finalists',f'''
      <h2>{heading} ($10,000)</h2><p><em>Judges: Judge One, Judge Two</em></p>
      <p><em>{title}</em>, <strong>{author}</strong> (Publisher)<br/><a href="https://bookshop.org/book">Bookshop</a></p>
      <p><em>Other {year} Book</em>, <strong>Other Writer</strong> (Publisher)</p>
      <h2>PEN Another Prize</h2><p><em>Other Category</em>, <strong>Wrong Writer</strong></p>''')

  def fetch(self,url,**kwargs):
    self.calls.append((url,kwargs.get('transport')))
    error=self.failures.get((url,kwargs.get('transport'))) or self.failures.get(url)
    if error:raise error
    if url in self.overrides:return self.overrides[url]
    if url==self.recipe.URL:return self.landing()
    return self.annual(self.recipe.parser().year_from_text(url))

  def parse(self,old=None,incremental=None):
    return self.recipe.fetch_and_parse(self.fetch,cached_parsed=old,
      incremental_update=(old is not None) if incremental is None else incremental)

  def cache(self,parsed):return build_import_cache_data(self.recipe.source_id,parsed)

  def test_all_four_recipes_recover_removed_landing_history_and_skip_closed_post(self):
    for factory in FETCHERS:
      self.recipe=factory();self.configure();self.calls.clear();full=self.parse()
      self.assertEqual(3,len(self.calls));old=without_unit(self.cache(full),self.recipe.URL)
      self.assertLess(len(old['entries']),len(full['entries']));self.calls.clear()
      updated=self.parse(old);self.assertEqual(full['entries'],updated['entries']);self.assertEqual(2,len(self.calls))
      self.assertNotIn(OLD,[url for url,_mode in self.calls]);self.calls.clear()
      self.assertEqual(full['entries'],self.parse(self.cache(updated))['entries']);self.assertEqual(2,len(self.calls))

  def test_new_annual_link_discovers_missing_year_and_ignores_other_hosts_and_grants(self):
    old=self.cache(self.parse());self.extra=f'<a href="{NEW}?tracking=one#section">Finalists</a><a href="https://evil.example/2027-pen-america-literary-awards-finalists/">bad</a><a href="https://pen.org/2027-literary-grant-winners/">grant</a>'
    self.calls.clear();updated=self.parse(old);self.assertIn((NEW,'camoufox'),self.calls)
    self.assertFalse(any('evil' in url or 'grant' in url for url,_mode in self.calls))
    self.assertEqual(self.parse()['entries'],updated['entries'])

  def test_corrected_landing_winner_invalidates_closed_post_authority(self):
    old=self.cache(self.parse());original=self.landing
    self.landing=lambda:original().replace('Prior Winner','Corrected Winner')
    self.changed_title[2025]='Corrected Winner';self.calls.clear();updated=self.parse(old)
    self.assertIn((OLD,'camoufox'),self.calls);self.assertNotIn('Prior Winner',[row['title'] for row in updated['entries']])
    self.assertEqual(self.parse()['entries'],updated['entries'])

  def test_winner_promotion_and_removal_restore_original_nominee(self):
    old=self.cache(self.parse());original=self.landing
    self.landing=lambda:original().replace('Prior Winner','Different Winner')
    updated=self.parse(old)
    self.assertEqual('nominee',next(r for r in updated['entries'] if r['title']=='Prior Winner')['result'])
    self.assertEqual(self.parse()['entries'],updated['entries'])

  def test_current_post_corrections_replace_old_roster(self):
    old=self.cache(self.parse());self.changed_title[2026]='Changed Current Book'
    updated=self.parse(old);self.assertEqual(self.parse()['entries'],updated['entries'])
    self.assertEqual(1,sum(r['title']=='Current Winner' for r in updated['entries']))

  def test_missing_or_incomplete_closed_post_fetches_it_again(self):
    full=self.parse();old=without_unit(self.cache(full),OLD);self.calls.clear()
    self.assertEqual(full['entries'],self.parse(old)['entries']);self.assertIn((OLD,'camoufox'),self.calls)
    old=self.cache(full);old['incremental_state']['units'][OLD]['complete']=False;self.calls.clear();self.parse(old)
    self.assertIn((OLD,'camoufox'),self.calls)

  def test_failed_annual_update_retains_rows_pending_then_recovers(self):
    full=self.parse();self.failures[CURRENT]=OSError('offline')
    updated=self.parse(self.cache(full));self.assertEqual(full['entries'],updated['entries'])
    self.assertFalse(updated['incremental_state']['units'][CURRENT]['complete'])
    self.failures.clear();self.assertEqual(full['entries'],self.parse(self.cache(updated))['entries'])

  def test_failed_landing_forces_history_requests_and_keeps_cached_rows(self):
    full=self.parse();self.failures[self.recipe.URL]=OSError('offline');self.calls.clear()
    updated=self.parse(self.cache(full));self.assertEqual(full['entries'],updated['entries'])
    self.assertFalse(updated['incremental_state']['units'][self.recipe.URL]['complete'])
    self.assertIn(OLD,[url for url,_mode in self.calls])

  def test_full_source_failure_still_raises(self):
    self.failures[CURRENT]=OSError('offline')
    with self.assertRaises(OSError):self.parse()

  def test_validated_category_absence_is_empty_and_reusable(self):
    self.absent.add(2025);full=self.parse();unit=full['incremental_state']['units'][OLD]
    self.assertTrue(unit['complete']);self.assertTrue(unit['metadata']['category_absent'])
    self.calls.clear();self.parse(self.cache(full));self.assertNotIn(OLD,[url for url,_mode in self.calls])

  def test_legacy_wrong_scope_corrupt_projection_and_complete_refresh_rebuild(self):
    old=self.cache(self.parse());legacy=copy.deepcopy(old);legacy.pop('incremental_state')
    wrong=copy.deepcopy(old);wrong['incremental_state']['source_key']='another category'
    bad=copy.deepcopy(old);bad['incremental_state']['units'][OLD]['metadata']={}
    for candidate,incremental in ((legacy,True),(wrong,True),(bad,True),(old,False)):
      self.calls.clear();self.parse(candidate,incremental);self.assertIn(OLD,[url for url,_mode in self.calls])

  def test_browser_rejection_recovers_same_url_then_suppresses_browser(self):
    calls=[]
    def browser(url,**kw):calls.append(('browser',url));return '<h1>Verify you are human</h1>'
    def legacy(url):calls.append(('legacy',url));return self.landing()
    policy=PENAmericaFetchPolicy(browser,legacy,lambda h,u:self.recipe.parser().read_source(h,u,self.recipe.config(),'landing'))
    policy.fetch(self.recipe.URL);policy.fetch(self.recipe.URL)
    self.assertEqual([('browser',self.recipe.URL),('legacy',self.recipe.URL),('legacy',self.recipe.URL)],calls)

  def test_critical_errors_propagate_at_landing_and_annual_boundaries(self):
    for url in (self.recipe.URL,OLD,CURRENT):
      for cls in (ImportCancelledError,CamoufoxRequiredError):
        self.failures={url:cls('stop')}
        with self.assertRaises(cls):self.parse()

  def test_modern_boundaries_publishers_judges_and_author_suffixes(self):
    parsed=self.parse();titles=[row['title'] for row in parsed['entries']]
    self.assertNotIn('Not a Book',titles);self.assertNotIn('Other Category',titles)
    self.assertFalse(any('Navigation' in title or 'citation' in title for title in titles))
    winner=next(row for row in parsed['entries'] if row['title']=='Prior Winner')
    self.assertEqual(['Prior Writer, Jr.'],winner['authors'])

  def test_multiple_cohonorees_in_one_historical_paragraph_are_not_truncated(self):
    html=document(self.recipe.NAME,'''<h3>Previous Winners</h3><p><strong>2010</strong><br/>
      <strong>One Writer</strong>, <em>First Book</em> (Publisher)<br/>
      <strong>Two Writer, Jr.</strong>, <em>Second Book</em> (Publisher)<br/>
      <strong>Third Writer</strong>, editor <em>Third Book</em> (Publisher)</p>''')
    result=self.recipe.parse(html);self.assertEqual(3,len(result['entries']))
    self.assertEqual({'2010'},{row['position'] for row in result['entries']})
    self.assertEqual(['Third Writer'],result['entries'][2]['authors'])

  def test_withdrawn_rows_and_longlist_sections_stay_excluded(self):
    html=document('2026 PEN America Literary Awards Finalists',f'''<h2>{self.recipe.NAME}</h2>
      <p>The following title has been withdrawn: <em>Withdrawn Book</em>, <strong>Withdrawn Writer</strong></p>
      <p><em>Kept Book</em>, <strong>Kept Writer</strong> (Publisher)</p>
      <h3>Longlist</h3><p><em>Longlisted Book</em>, <strong>Other Writer</strong></p><h2>PEN Another Prize</h2>''')
    parsed=self.recipe.parser().read_source(html,CURRENT,self.recipe.config(),'annual')
    self.assertEqual(['Kept Book'],[row['title'] for row in parsed['rows']]);self.assertTrue(parsed['notes'])

  def test_wrong_year_and_wrong_prize_are_rejected(self):
    with self.assertRaises(ValueError):self.recipe.parser().read_source(self.annual(2025),CURRENT,self.recipe.config(),'annual')
    html=self.landing().replace(self.recipe.NAME,'PEN Unrelated Prize')
    with self.assertRaises(ValueError):self.recipe.parser().read_source(html,self.recipe.URL,self.recipe.config(),'landing')

  def test_missing_author_in_a_published_row_retains_previous_unit_pending(self):
    full=self.parse();self.overrides[CURRENT]=self.annual(2026).replace('<strong>Other Writer</strong>','')
    updated=self.parse(self.cache(full))
    self.assertFalse(updated['incremental_state']['units'][CURRENT]['complete'])
    self.assertEqual(full['entries'],updated['entries'])
    self.assertTrue(any('published byline' in note for note in updated['notes']))

  def test_latest_post_stays_fresh_after_calendar_rollover(self):
    old=self.cache(self.parse());self.dates.datetime.now.return_value.year=2027;self.calls.clear()
    self.parse(old);self.assertIn((CURRENT,'camoufox'),self.calls)

  def test_legacy_byline_uses_final_by_and_preserves_comma_suffix(self):
    parser=PENAmericaAwardParser()
    self.assertEqual(('Freedom by Example','Writer, Jr.'),parser.split_work_text('Freedom by Example by Writer, Jr.','title_author'))
    self.assertEqual(('A Title, With Commas','Writer, Jr.'),parser.split_work_text('A Title, With Commas, Writer, Jr.','title_author'))

  def test_legacy_main_boundary_excludes_outer_navigation_and_footer(self):
    html=f'''<html><nav><p>2025: Bogus Book, Menu Writer</p></nav><main><h1>{self.recipe.NAME}</h1>
      <p>2025: Actual Book, Actual Writer</p></main><footer><p>2024: Footer Book, Footer Writer</p></footer></html>'''
    parsed=self.recipe.parse(html);self.assertEqual(['Actual Book'],[row['title'] for row in parsed['entries']])

  def test_comma_inside_title_emphasis_still_separates_author(self):
    url='https://pen.org/2026-literary-awards-winners/'
    html=document('2026 PEN America Literary Awards Winners',f'''<h2>{self.recipe.NAME}</h2>
      <p>Winner: <em>Actual Book, </em><strong>Actual Writer</strong> (Publisher)</p><h2>PEN Other Prize</h2>''')
    parsed=self.recipe.parser().read_source(html,url,self.recipe.config(),'annual')
    self.assertTrue(parsed['complete']);self.assertEqual('Actual Book',parsed['rows'][0]['title'])
    self.assertEqual('Actual Writer',parsed['rows'][0]['author'])

  def test_citation_continuation_starting_with_emphasized_title_is_not_a_byline(self):
    html=self.annual(2026).replace('<h2>PEN Another Prize</h2>',
      '<p><em>Current Winner</em> is rooted in a vivid landscape.</p><p><em>From the judges citation: an excellent book.</em></p><h2>PEN Another Prize</h2>')
    parsed=self.recipe.parser().read_source(html,CURRENT,self.recipe.config(),'annual')
    self.assertTrue(parsed['complete']);self.assertEqual(2,len(parsed['rows']))

  def test_one_broken_cohonoree_marks_entire_history_source_incomplete(self):
    html=document(self.recipe.NAME,'''<h3>Previous Winners</h3><p><strong>2010</strong><br/>
      <strong>Actual Writer</strong>, <em>Actual Book</em> (Publisher)<br/>
      <strong></strong>, <em>Broken Book</em> (Publisher)</p>''')
    parsed=self.recipe.parser().read_source(html,self.recipe.URL,self.recipe.config(),'landing')
    self.assertFalse(parsed['complete']);self.assertEqual(1,len(parsed['rows']))

  def test_final_title_letter_outside_emphasis_is_preserved(self):
    html=document('2026 PEN America Literary Awards Finalists',f'''<h2>{self.recipe.NAME}</h2>
      <p><em>The Devil Three Time</em>s, <strong>Rickey Fayne</strong> (Publisher)</p><h2>PEN Other Prize</h2>''')
    parsed=self.recipe.parser().read_source(html,CURRENT,self.recipe.config(),'annual')
    self.assertTrue(parsed['complete']);self.assertEqual('The Devil Three Times',parsed['rows'][0]['title'])

  def test_subtitle_alias_is_unambiguous_and_does_not_mutate_raw_sources(self):
    parser=self.recipe.parser();config=self.recipe.config()
    rows=[parser.row(2025,'A Book','Writer','winner','landing',config),
      parser.row(2025,'A Book: The Full Title','Writer','nominee','annual',config)]
    original=copy.deepcopy(rows);merged=parser.dedupe_rows(rows)
    self.assertEqual(1,len(merged));self.assertEqual(['A Book: The Full Title'],merged[0]['aliases']);self.assertEqual(original,rows)
    rows.append(parser.row(2025,'A Book: Another Volume','Writer','nominee','annual',config))
    self.assertEqual(3,len(parser.dedupe_rows(rows)))

  def test_source_manifest_and_discovery_remain_official_and_bounded(self):
    urls=[url for url,_kind in PEN_ANNUAL_POST_URLS]
    self.assertIn('https://pen.org/2026-literary-awards-winners/',urls)
    self.assertIn('https://pen.org/announcing-the-2025-pen-america-literary-awards-finalists/',urls)
    self.assertIn('https://pen.org/announcing-the-2023-pen-america-literary-awards-finalists/',urls)
    self.assertNotIn('https://pen.org/announcing-the-2024-pen-america-literary-awards-winners/',urls)
    self.assertEqual([NEW],annual_links(f'<a href="{NEW}?tracking=one">new</a><a href="https://evil.example/2027-literary-awards-winners/">bad</a>',self.recipe.URL))


if __name__=='__main__':unittest.main()
