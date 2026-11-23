import copy
import types
import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError,ImportCancelledError
from storage import build_import_cache_data
from url_fetcher.lukas import (UrlFetcherJAnthonyLukasBookPrize,UrlFetcherMarkLyntonHistoryPrize,
  LUKAS_URL,LUKAS_OFFICIAL_EXTRA_URLS,LUKAS_WIKIPEDIA_URL,MARK_LYNTON_WIKIPEDIA_URL)
from url_fetcher.lukas_transport import LukasOfficialFetchPolicy


FETCHERS=(UrlFetcherJAnthonyLukasBookPrize,UrlFetcherMarkLyntonHistoryPrize)


class LukasUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=FETCHERS[0]();self.calls=[];self.failures={};self.overrides={};self.years=[2025,2026]
    self.changed='';self.advertised='';self.open=False
    self.clock=patch('parser.lukas_updates.datetime');self.dates=self.clock.start();self.addCleanup(self.clock.stop)
    self.dates.datetime.now.return_value.year=2026

  def archive(self):
    rows=[]
    for year in sorted(self.years,reverse=True):
      winner=f'Winner {year}{self.changed}';stage='Shortlist' if self.open and year==max(self.years) else 'Winners'
      rows.extend([f'<tr><td>{year}</td><td>{stage}</td><td>Winner Writer, Jr.</td><td>History Writer</td><td>Excluded Writer</td></tr>',
        f'<tr><td></td><td></td><td>{winner}</td><td>History {year}{self.changed}</td><td>Excluded Work</td></tr>' if stage=='Winners' else '',
        f'<tr><td></td><td>Finalists</td><td>Finalist Writer</td><td>Finalist Historian</td><td></td></tr>',
        f'<tr><td></td><td></td><td>Finalist {year}</td><td>History Finalist {year}</td><td></td></tr>',
        '<tr><td></td><td>Shortlist</td><td>Other Writer</td><td>Other Historian</td><td>Other Excluded</td></tr>',
        '<tr><td></td><td>Jurors</td><td>Judge One, Judge Two</td><td>Other Judge</td><td>Someone Else</td></tr>'])
    return '<html><main><h1>The J. Anthony Lukas Prize Project Awards</h1><h2>2027 entry instructions</h2><p>Pay $75 by January 2027</p>'+f'<h3>Winners since {min(self.years)}</h3>'+'''<table><tr><th></th><th></th><th>Lukas Book Prize</th><th>Lynton History Prize</th><th>Lukas Work-In-Progress Award</th></tr>'''+''.join(rows)+'</table>'+self.advertised+'</main></html>'

  def news(self,year,winners):
    stage='Winner' if winners else 'Shortlist'
    lukas=(f'<li>Winner: Winner Writer, Jr., <em>Winner {year}{self.changed}</em> (Publisher)</li><li>Finalist: Finalist Writer, <em>Finalist {year}</em> (Publisher)</li>' if winners else
      f'<li>Winner Writer, Jr., <em>Winner {year}{self.changed}</em> (Publisher)</li><li>Finalist Writer, <em>Finalist {year}</em> (Publisher)</li><li>Other Writer, <em>Other {year}</em> (Publisher)</li>')
    history=(f'<li>Winner: History Writer, <em>History {year}{self.changed}</em></li><li>Finalist: Finalist Historian, <em>History Finalist {year}</em></li>' if winners else
      f'<li>History Writer, <em>History {year}{self.changed}</em></li><li>Finalist Historian, <em>History Finalist {year}</em></li><li>Other Historian, <em>Other History {year}</em></li>')
    return f'''<html><main><h1>{year} Lukas Prize Project {stage}s</h1>
      <h2>J. Anthony Lukas Work-in-Progress Awards</h2><ul><li>Excluded Writer, <em>Wrong Prize</em></li></ul>
      <h2>J. Anthony Lukas Book Prize</h2><ul>{lukas}</ul><h2>Mark Lynton History Prize</h2><ul>{history}</ul>
      <h2>About the Prizes</h2><h3>J. Anthony Lukas Book Prize</h3><ul><li>Biography Writer, <em>Wrong Biography</em></li></ul></main></html>'''

  def fetch(self,url,**kwargs):
    self.calls.append((url,kwargs.get('transport')))
    error=self.failures.get((url,kwargs.get('transport'))) or self.failures.get(url)
    if error:raise error
    if url in self.overrides:return self.overrides[url]
    if url==LUKAS_URL:return self.archive()
    if url in (LUKAS_WIKIPEDIA_URL,MARK_LYNTON_WIKIPEDIA_URL):return '<table><tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr><tr><td>2026</td><td>Fallback Writer</td><td>Fallback Book</td><td>Winner</td></tr></table>'
    year=self.recipe.parser().year_from_text(url)
    return self.news(year,'winners' in url)

  def parse(self,old=None,incremental=None,choice=0):
    return self.recipe.fetch_and_parse(self.fetch,source_choice=choice,cached_parsed=old,
      incremental_update=(old is not None) if incremental is None else incremental)

  def cache(self,parsed):return build_import_cache_data(self.recipe.source_id,parsed)

  def test_both_prizes_recover_missing_archive_history_and_repeat_in_one_request(self):
    for cls in FETCHERS:
      self.recipe=cls();self.calls.clear();full=self.parse();self.assertEqual(5,len(full['entries']))
      self.assertEqual(3,len(self.calls));old=without_unit(self.cache(full),LUKAS_URL)
      self.assertLess(len(old['entries']),len(full['entries']));self.calls.clear()
      updated=self.parse(old);self.assertEqual(full['entries'],updated['entries'])
      self.assertEqual([(LUKAS_URL,'camoufox')],self.calls);self.calls.clear()
      self.assertEqual(full['entries'],self.parse(self.cache(updated))['entries']);self.assertEqual(1,len(self.calls))

  def test_new_archive_year_and_advertised_news_are_discovered(self):
    old=self.cache(self.parse());self.years.append(2027);self.dates.datetime.now.return_value.year=2027
    new='https://journalism.columbia.edu/news/lukas-shortlists-2027'
    self.advertised=f'<a href="{new}?tracking=one">2027 shortlist</a><a href="https://evil.example/news/lukas-2027">bad</a>'
    self.calls.clear();updated=self.parse(old)
    self.assertIn((new,'camoufox'),self.calls);self.assertFalse(any('evil' in url for url,_ in self.calls))
    self.assertIn('2027',{row['award_year'] for row in updated['entries']});self.assertEqual(self.parse()['entries'],updated['entries'])

  def test_changed_roster_refreshes_news_and_replaces_corrections(self):
    old=self.cache(self.parse());self.changed=' Corrected';self.calls.clear();updated=self.parse(old)
    self.assertIn((LUKAS_OFFICIAL_EXTRA_URLS[0],'camoufox'),self.calls)
    self.assertIn((LUKAS_OFFICIAL_EXTRA_URLS[1],'camoufox'),self.calls)
    self.assertNotIn('Winner 2026',[row['title'] for row in updated['entries']])
    self.assertEqual(self.parse()['entries'],updated['entries'])

  def test_winnerless_current_roster_does_not_certify_news_reuse(self):
    self.open=True;old=self.cache(self.parse());self.calls.clear();self.parse(old)
    self.assertIn((LUKAS_OFFICIAL_EXTRA_URLS[0],'camoufox'),self.calls)

  def test_failed_news_update_preserves_previous_whole_unit_pending_then_recovers(self):
    full=self.parse();old=self.cache(full);old['incremental_state']['units'][LUKAS_OFFICIAL_EXTRA_URLS[1]]['complete']=False
    self.failures[LUKAS_OFFICIAL_EXTRA_URLS[1]]=OSError('offline');updated=self.parse(old)
    self.assertEqual(full['entries'],updated['entries']);self.assertFalse(updated['incremental_state']['units'][LUKAS_OFFICIAL_EXTRA_URLS[1]]['complete'])
    self.failures.clear();self.calls.clear();self.parse(self.cache(updated))
    self.assertIn((LUKAS_OFFICIAL_EXTRA_URLS[1],'camoufox'),self.calls)

  def test_missing_news_unit_is_fetched_even_under_unchanged_archive(self):
    full=self.parse();old=without_unit(self.cache(full),LUKAS_OFFICIAL_EXTRA_URLS[1]);self.calls.clear()
    self.assertEqual(full['entries'],self.parse(old)['entries'])
    self.assertIn((LUKAS_OFFICIAL_EXTRA_URLS[1],'camoufox'),self.calls)

  def test_legacy_wrong_scope_corrupt_projection_and_complete_refresh_read_all_sources(self):
    old=self.cache(self.parse());legacy=copy.deepcopy(old);legacy.pop('incremental_state')
    wrong=copy.deepcopy(old);wrong['incremental_state']['source_key']='another prize'
    bad=copy.deepcopy(old);bad['incremental_state']['units'][LUKAS_OFFICIAL_EXTRA_URLS[0]]['metadata']={}
    for candidate,incremental in ((legacy,True),(wrong,True),(bad,True),(old,False)):
      self.calls.clear();self.parse(candidate,incremental)
      self.assertIn((LUKAS_OFFICIAL_EXTRA_URLS[0],'camoufox'),self.calls)

  def test_archive_pairs_skip_jurors_and_do_not_invent_titles_for_shortlist_names(self):
    parsed=self.parse();titles=[row['title'] for row in parsed['entries']]
    self.assertNotIn('Other Writer',titles);self.assertNotIn('Wrong Prize',titles);self.assertNotIn('Wrong Biography',titles)
    self.assertNotIn('January 2027',titles)
    self.assertEqual(['Winner Writer, Jr.'],next(row for row in parsed['entries'] if row['title']=='Winner 2026')['authors'])
    self.assertTrue(any('names without book titles' in note for note in parsed['notes']))

  def test_historical_finalist_names_cannot_be_paired_as_books(self):
    html='''<main><h1>The J. Anthony Lukas Prize Project Awards</h1>
      <h3>Winners since 2010</h3><table><tr><th></th><th></th>
      <th>Lukas Book Prize</th><th>Lynton History Prize</th></tr>
      <tr><td>2011</td><td>Winners</td><td>Eliza Griswold</td><td>History Writer</td></tr>
      <tr><td></td><td></td><td>The Tenth Parallel</td><td>History Book</td></tr>
      <tr><td></td><td>Finalists</td><td>Jefferson Cowie</td><td>Patrick Wilcken</td></tr>
      <tr><td></td><td></td><td>Paul Greenberg</td><td>Second Historian</td></tr>
      <tr><td></td><td></td><td>Siddartha Mukherjee</td><td></td></tr>
      <tr><td></td><td>Jurors</td><td>Excluded Judge</td><td>Other Judge</td></tr>
      <tr><td>2010</td><td>Winners</td><td>David Finkel</td><td>Older Historian</td></tr>
      <tr><td></td><td></td><td>The Good Soldiers</td><td>Older History Book</td></tr>
      <tr><td></td><td>Finalists</td><td>Patrick Radden Keefe</td><td>Jenny Uglow</td></tr>
      <tr><td></td><td></td><td>Beryl Satter</td><td>Another Historian</td></tr>
      </table></main>'''
    for factory in FETCHERS:
      recipe=factory()
      with self.subTest(recipe=recipe.NAME):
        source=recipe.parser().read_official_source(html,LUKAS_URL,recipe.CATEGORY)
        self.assertTrue(source['complete']);self.assertTrue(source['notes'])
        self.assertEqual(2,len(source['rows']))
        self.assertTrue(all(row['result']=='winner' for row in source['rows']))
        finalists=[r for r in source['rosters'][2011] if r['result']=='finalist']
        self.assertTrue(all(r['title'] is None for r in finalists))
        self.assertEqual(3 if factory is FETCHERS[0] else 2,len(finalists))

  def test_title_bearing_finalists_start_in_2022_and_split_joint_credits(self):
    for year,title,credit,authors in (
        (2022,'Empire of Pain','Patrick Radden Keefe',['Patrick Radden Keefe']),
        (2023,'His Name Is George Floyd','Robert Samuels and Toluse Olorunnipa',['Robert Samuels','Toluse Olorunnipa']),
        (2025,'The Unclaimed','Pamela Prickett and Stefan Timmermans',['Pamela Prickett','Stefan Timmermans'])):
      with self.subTest(year=year):
        self.years=[year]
        html=self.archive().replace('Finalist Writer',credit).replace(f'Finalist {year}',title)
        parsed=self.recipe.parse(html)
        finalist=next(row for row in parsed['entries'] if row['title']==title)
        self.assertEqual(authors,finalist['authors']);self.assertEqual('finalist',finalist['result'])

  def test_official_coauthors_preserve_suffixes_and_cached_news_certification(self):
    credit='Writer One, Jr., Writer Two and Writer Three'
    self.overrides[LUKAS_URL]=self.archive().replace('Winner Writer, Jr.',credit)
    for url in LUKAS_OFFICIAL_EXTRA_URLS:
      self.overrides[url]=self.news(2026,'winners' in url).replace('Winner Writer, Jr.',credit)
    full=self.parse()
    winner=next(row for row in full['entries'] if row['title']=='Winner 2026')
    self.assertEqual(['Writer One, Jr.','Writer Two','Writer Three'],winner['authors'])
    self.calls.clear();updated=self.parse(self.cache(full))
    self.assertEqual([(LUKAS_URL,'camoufox')],self.calls)
    self.assertEqual(full['entries'],updated['entries'])
    self.assertEqual(full['entries'],self.parse(self.cache(updated))['entries'])

  def test_missing_winner_title_marks_archive_pending_and_retains_previous_history(self):
    full=self.parse();self.overrides[LUKAS_URL]=self.archive().replace('<td>Winner 2025</td>','<td></td>')
    updated=self.parse(self.cache(full));self.assertEqual(full['entries'],updated['entries'])
    self.assertFalse(updated['incremental_state']['units'][LUKAS_URL]['complete'])

  def test_gapped_declared_years_and_missing_rendered_archive_are_rejected(self):
    self.years=[2024,2026]
    with self.assertRaises(ValueError):self.recipe.parser().read_official_source(self.archive(),LUKAS_URL,self.recipe.CATEGORY)
    with self.assertRaises(ValueError):self.recipe.parser().read_official_source('<main><h1>The J. Anthony Lukas Prize Project Awards</h1><h2>Entry Instructions</h2></main>',LUKAS_URL,self.recipe.CATEGORY)

  def test_critical_errors_propagate_from_every_official_source(self):
    for url in (LUKAS_URL,)+LUKAS_OFFICIAL_EXTRA_URLS:
      for cls in (ImportCancelledError,CamoufoxRequiredError):
        self.failures={url:cls('stop')}
        with self.assertRaises(cls):self.parse()

  def test_same_url_legacy_recovery_suppresses_browser_only_for_official_attempt(self):
    calls=[]
    def browser(url,**kw):calls.append(('browser',url));return '<h1>Verify you are human</h1>'
    def legacy(url):calls.append(('legacy',url));return self.archive()
    policy=LukasOfficialFetchPolicy(browser,legacy,lambda h,u:self.recipe.parser().read_official_source(h,u,self.recipe.CATEGORY))
    policy.fetch(LUKAS_URL);policy.fetch(LUKAS_URL)
    self.assertEqual([('browser',LUKAS_URL),('legacy',LUKAS_URL),('legacy',LUKAS_URL)],calls)

  def test_wikipedia_choices_ignore_official_cache_and_remain_full_replacements(self):
    for cls,choice,url in ((FETCHERS[0],2,LUKAS_WIKIPEDIA_URL),(FETCHERS[1],1,MARK_LYNTON_WIKIPEDIA_URL)):
      self.recipe=cls();old=self.cache(self.parse());self.calls.clear();parsed=self.parse(old,choice=choice)
      self.assertEqual([(url,None)],self.calls);self.assertEqual(['Fallback Book'],[row['title'] for row in parsed['entries']])
      self.assertNotIn('incremental_state',parsed)

  def test_librarything_fallback_keeps_the_original_fetch_callback(self):
    calls=[];raw_fetch=self.fetch
    parser=types.SimpleNamespace(parse=lambda *args,**kwargs:{'entries':[{'position':'2026','title':'LibraryThing Book','authors':['Writer']}],'notes':[]})
    def librarything(callback,url):calls.append((callback,url));return 'librarything data'
    with patch.object(self.recipe,'create_librarything_parser',return_value=parser),patch.object(self.recipe,'fetch_librarything_url',side_effect=librarything):
      parsed=self.recipe.fetch_and_parse(raw_fetch,source_choice=1)
    self.assertIs(raw_fetch,calls[0][0]);self.assertEqual(self.recipe.LIBRARYTHING_URL,calls[0][1])
    self.assertEqual('LibraryThing Book',parsed['entries'][0]['title'])

  def test_source_attempt_scope_and_operation_policy_cleanup(self):
    attempt,*fallbacks=self.recipe.source_attempts()
    self.assertTrue(attempt.supports_incremental);self.assertTrue(all(not item.supports_incremental for item in fallbacks))
    attempt.execute(self.fetch);self.assertIsNone(attempt._policy)
    self.failures[LUKAS_URL]=ImportCancelledError('stop')
    with self.assertRaises(ImportCancelledError):attempt.execute(self.fetch)
    self.assertIsNone(attempt._policy)

  def test_wrong_news_year_is_rejected_and_legacy_byline_uses_final_by(self):
    with self.assertRaises(ValueError):self.recipe.parser().read_official_source(self.news(2025,False),LUKAS_OFFICIAL_EXTRA_URLS[1],self.recipe.CATEGORY)
    self.assertEqual(('Freedom by Example','Writer, Jr.'),self.recipe.parser().title_author_from_text('Freedom by Example by Writer, Jr.'))

  def test_news_beyond_calendar_year_is_not_frozen(self):
    old=self.cache(self.parse());self.dates.datetime.now.return_value.year=2025;self.calls.clear()
    self.parse(old);self.assertIn((LUKAS_OFFICIAL_EXTRA_URLS[0],'camoufox'),self.calls)
    self.assertIn((LUKAS_OFFICIAL_EXTRA_URLS[1],'camoufox'),self.calls)

  def test_winner_change_demotes_the_previous_winner_using_original_shortlist_rows(self):
    full=self.parse();old=self.cache(full)
    archive=self.archive().replace('<td>Winner Writer, Jr.</td>','<td>Other Writer</td>',1).replace('<td>Winner 2026</td>','<td>Other 2026</td>',1)
    archive=archive.replace('<td>Shortlist</td><td>Other Writer</td>','<td>Shortlist</td><td>Winner Writer, Jr.</td>',1)
    self.overrides[LUKAS_URL]=archive
    self.overrides[LUKAS_OFFICIAL_EXTRA_URLS[0]]=self.news(2026,True).replace('Winner: Winner Writer, Jr., <em>Winner 2026</em>','Winner: Other Writer, <em>Other 2026</em>')
    updated=self.parse(old)
    self.assertEqual('shortlisted',next(row for row in updated['entries'] if row['title']=='Winner 2026')['result'])
    self.assertEqual('winner',next(row for row in updated['entries'] if row['title']=='Other 2026')['result'])
    self.assertEqual(self.parse()['entries'],updated['entries'])

  def test_direct_parser_keeps_archive_coverage_notes(self):
    parsed=self.recipe.parse(self.archive())
    self.assertEqual(4,len(parsed['entries']));self.assertTrue(parsed['notes'])


if __name__=='__main__':unittest.main()
