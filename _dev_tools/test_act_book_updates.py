import copy
import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError, CamoufoxRequiredError
from parser.act_book_sources import discover_archive
from storage import build_import_cache_data
from url_fetcher.act_book_of_the_year import UrlFetcherACTBookOfTheYearAward


class ACTBookUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe = UrlFetcherACTBookOfTheYearAward(); self.recipe.FIRST_YEAR = 2024
    self.years = [2024, 2025, 2026]; self.open_years = set(); self.extra_winner = ''
    self.calls, self.errors, self.overrides = [], {}, {}
    self.cover = ''; self.other = False
    clock = patch('parser.act_book_updates.datetime')
    clock.start().datetime.now.return_value.year = 2026; self.addCleanup(clock.stop)

  def url(self, year):
    return self.recipe.URL + '/' + str(year + 1 if year >= 2025 else year)

  def archive(self):
    links = ''.join(f'<td><a href="{self.url(year)}">{year}</a><img alt="Winner cover {year}{self.cover}" src="/cover-{year}.png"></td>' for year in self.years)
    return '<h1>ACT Book of the Year</h1><div id="main"><h1>ACT Book of the Year Winners</h1><table><tr>'+links+'</tr></table></div>'

  def table(self, title, year, author='Byron Writer, Jr.', label=''):
    return f'<table id="Winner 2011">{f"<thead><tr><th>{label}</th></tr></thead>" if label else ""}<tbody><tr><td>{author}<br><em>{title} {year}</em><br>Publisher</td><td><img alt="Cover"></td></tr></tbody></table>'

  def annual(self, year):
    first = 'Shortlist' if year in self.open_years else 'Winner'
    return f'''<h1>{year}</h1><div id="main"><h1>ACT Book of the Year</h1><h2>{first}</h2>
      {self.table('Book',year)}<h4>JUDGES' CITATION</h4><p>Wrong Writer <em>Wrong Biography</em></p>
      <h2>Shortlist</h2>{self.table('Other',year)}<h4>SYNOPSIS</h4><p>Wrong prose.</p>{self.table('Last',year)}</div>'''

  def wiki(self):
    body = ''.join(f'<tr><td>{year}</td><td>Byron Writer, Jr.</td><td>{self.extra_winner if year==2025 and self.extra_winner else "Other" if year==2025 and self.other else "Book"} {year}</td><td>Winner</td></tr>' for year in self.years)
    return '<table><tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>'+body+'</table>'

  def fetch(self, url, **kwargs):
    self.calls.append((url, kwargs.get('transport')))
    error = self.errors.get((url, kwargs.get('transport'))) or self.errors.get(url)
    if error: raise error
    if url in self.overrides: return self.overrides[url]
    if url == self.recipe.URL: return self.archive()
    if url == self.recipe.WIKIPEDIA_URL: return self.wiki()
    year = next(y for y in self.years if self.url(y) == url)
    return self.annual(year)

  def parse(self, old=None, choice='automatic', incremental=None, **kw):
    return self.recipe.fetch_and_parse(self.fetch, source_choice=choice, cached_parsed=old,
      incremental_update=(old is not None) if incremental is None else incremental, **kw)

  def cache(self, parsed): return build_import_cache_data(self.recipe.source_id, parsed)

  def test_official_and_automatic_recover_missing_real_year_then_repeat_with_savings(self):
    for choice, full_count, update_count, repeat_count in [(0,4,3,2),('automatic',5,4,3)]:
      self.calls.clear(); full = self.parse(choice=choice); self.assertEqual(9,len(full['entries'])); self.assertEqual(full_count,len(self.calls))
      stale = without_unit(self.cache(full),'2025'); self.assertEqual(6,len(stale['entries'])); self.calls.clear()
      updated = self.parse(stale,choice); self.assertEqual(full['entries'],updated['entries']); self.assertEqual(update_count,len(self.calls))
      self.calls.clear(); self.assertEqual(full['entries'],self.parse(self.cache(updated),choice)['entries']); self.assertEqual(repeat_count,len(self.calls))

  def test_archive_year_label_and_own_heading_override_migrated_route_digits(self):
    parsed = self.parse(choice=0)
    self.assertEqual({'2024','2025','2026'},{r['award_year'] for r in parsed['entries']})
    self.assertIn((self.recipe.URL+'/2027','camoufox'),self.calls)

  def test_stage_survives_synopsis_and_citation_headings_without_importing_prose(self):
    source = self.recipe.parser().read_official_year(self.annual(2026),self.url(2026),2026)
    self.assertTrue(source['complete']); self.assertEqual(3,len(source['rows'])); self.assertFalse(any('Wrong' in r['title'] for r in source['rows']))

  def test_table_visible_joint_winner_label_ignores_recycled_id_and_preserves_tied_positions(self):
    html = '<h1>2024</h1><div id="main"><h1>ACT Book of the Year</h1>'+self.table('One',2024,label='JOINT WINNERS')+self.table('Two',2024,label='JOINT WINNERS')+'</div>'
    source = self.recipe.parser().read_official_year(html,self.url(2024),2024)
    rows = self.recipe.parser().entries_from_rows(source['rows']); self.assertEqual(['2024','2024'],[r['position'] for r in rows])

  def test_numeric_heading_legacy_publisher_metadata_and_split_paragraph_byline(self):
    html = '<meta name="dcterms.publisher" content="Libraries ACT"><h1>2024</h1><div id="main"><h2>2024</h2><table><th>Winner</th><tr><td><p>Byron Writer, Jr.</p><p><em>Book 2024</em></p></td></tr></table></div>'
    source = self.recipe.parser().read_official_year(html,self.url(2024),2024)
    self.assertTrue(source['complete']); self.assertEqual('Byron Writer, Jr.',source['rows'][0]['author'])

  def test_explicit_coauthors_split_inside_bounded_credit_and_keep_suffix(self):
    html = '<h1>2024</h1><div id="main"><h1>ACT Book of the Year</h1><h2>Winner</h2>'+self.table('Book',2024,author='One Writer, Jr. and Other Writer')+'</div>'
    source = self.recipe.parser().read_official_year(html,self.url(2024),2024)
    entry = self.recipe.parser().entries_from_rows(source['rows'])[0]
    self.assertEqual(['One Writer, Jr.','Other Writer'],entry['authors'])

  def test_unknown_result_and_incomplete_metadata_do_not_certify_a_partial_year(self):
    for html in (self.annual(2024).replace('<h2>Winner</h2>','<h2>Unclear section</h2>'),self.annual(2024).replace('Byron Writer, Jr.<br>','')):
      self.assertFalse(self.recipe.parser().read_official_year(html,self.url(2024),2024)['complete'])

  def test_wikipedia_promotes_exact_official_nominee_without_duplicate_and_keeps_year_unsettled(self):
    self.open_years.add(2025); full = self.parse(); year = [r for r in full['entries'] if r['award_year']=='2025']
    self.assertEqual(3,len(year)); self.assertEqual(1,sum(r['result']=='winner' for r in year))
    old = self.cache(full); self.calls.clear(); updated = self.parse(old)
    self.assertEqual(full['entries'],updated['entries']); self.assertIn((self.url(2025),'camoufox'),self.calls)
    self.assertIn((self.recipe.WIKIPEDIA_URL,None),self.calls)

  def test_original_official_projection_restores_after_wikipedia_winner_changes(self):
    self.open_years.add(2025); old = self.cache(self.parse()); self.other = True
    parsed = self.parse(old); year = [r for r in parsed['entries'] if r['award_year']=='2025']
    self.assertEqual('Other 2025',next(r['title'] for r in year if r['result']=='winner'))
    self.assertEqual('shortlisted',next(r['result'] for r in year if r['title']=='Book 2025'))

  def test_wikipedia_only_winner_has_unit_ownership_and_is_replaced_on_next_update(self):
    self.open_years.add(2025); self.extra_winner='Wiki Only'; full = self.parse(); old = self.cache(full)
    unit = old['incremental_state']['units']['wikipedia-winners']; self.assertEqual(1,len(unit['entry_indexes']))
    self.extra_winner='Replacement'; parsed = self.parse(old)
    self.assertNotIn('Wiki Only 2025',[r['title'] for r in parsed['entries']]); self.assertIn('Replacement 2025',[r['title'] for r in parsed['entries']])

  def test_wikipedia_failure_retains_official_output_pending_and_retries(self):
    old = self.cache(self.parse()); self.errors[self.recipe.WIKIPEDIA_URL]=RuntimeError('temporary wiki failure')
    parsed = self.parse(old); self.assertEqual(old['entries'],parsed['entries']); self.assertFalse(parsed['incremental_state']['units']['wikipedia-winners']['complete'])
    self.errors.clear(); self.assertTrue(self.parse(self.cache(parsed))['incremental_state']['units']['wikipedia-winners']['complete'])

  def test_changed_source_choice_never_reuses_incompatible_official_or_supplement_projections(self):
    for first,second,count in [(0,'automatic',5),('automatic',0,4)]:
      old = self.cache(self.parse(choice=first)); self.calls.clear(); self.parse(old,second); self.assertEqual(count,len(self.calls))
    self.calls.clear(); wiki = self.parse(old,1); self.assertEqual([(self.recipe.WIKIPEDIA_URL,None)],self.calls); self.assertNotIn('incremental_state',wiki)

  def test_full_refresh_legacy_cache_wrong_scope_and_corrupt_projection_rebuild(self):
    old = self.cache(self.parse()); cases=[dict(old,incremental_state={}),copy.deepcopy(old),copy.deepcopy(old)]
    cases[1]['incremental_state']['source_key']='different scope'
    cases[2]['incremental_state']['units']['2025']['metadata']['rows']='corrupt projection'
    for cached in cases:
      self.calls.clear(); updated = self.parse(cached); self.assertEqual(old['entries'],updated['entries']); self.assertGreaterEqual(len(self.calls),4)
    self.calls.clear(); self.parse(old,incremental=False); self.assertEqual(5,len(self.calls))

  def test_failed_or_wrong_year_current_response_retains_whole_year_pending(self):
    old = self.cache(self.parse(choice=0))
    for wrong_year in [False,True]:
      self.errors.clear(); self.overrides.clear()
      if wrong_year:self.overrides[self.url(2026)]=self.annual(2025)
      else:self.errors[self.url(2026)]=RuntimeError('temporary failure')
      parsed = self.parse(old,0); self.assertEqual(old['entries'],parsed['entries']); self.assertFalse(parsed['incremental_state']['units']['2026']['complete'])
    self.overrides.clear(); self.assertTrue(self.parse(self.cache(parsed),0)['incremental_state']['units']['2026']['complete'])

  def test_new_archive_year_and_changed_cover_revision_refresh_correct_units(self):
    old=self.cache(self.parse(choice=0));self.years.append(2027);self.calls.clear();parsed=self.parse(old,0)
    self.assertEqual(12,len(parsed['entries']));self.assertIn((self.url(2027),'camoufox'),self.calls)
    self.cover=' corrected';self.calls.clear();self.parse(self.cache(parsed),0)
    self.assertIn((self.url(2024),'camoufox'),self.calls)

  def test_gapped_archive_fails_before_certifying_lost_history(self):
    self.years.remove(2025)
    with self.assertRaisesRegex(Exception,'missing or unexpected'):self.parse(choice=0)

  def test_discovery_excludes_navigation_foreign_hosts_and_empty_mislinked_covers(self):
    html=self.archive().replace('</div>',f'<nav><a href="{self.url(2001)}">2001</a></nav><a href="https://example.com{self.recipe.URL.split(".au")[1]}/2002">2002</a><a href="{self.url(2003)}" title="2003 ACT Book of the Year"><img alt="Mislinked cover"></a></div>')
    self.assertEqual(set(self.years),set(discover_archive(html,self.recipe.URL)['years']))

  def test_multiple_advertised_pages_for_one_year_replace_one_whole_unit(self):
    alternate=self.recipe.URL+'/2024/2024-shortlist'
    self.overrides[self.recipe.URL]=self.archive().replace('</tr>',f'<td><a href="{alternate}" title="2024 Shortlist"><img alt="Cover"></a></td></tr>')
    self.overrides[alternate]=self.annual(2024)
    parsed=self.parse(choice=0);self.assertEqual(9,len(parsed['entries']));self.assertEqual(2,len(parsed['incremental_state']['units']['2024']['revision'][0]))

  def test_browser_recovery_is_operation_local_and_wikipedia_uses_original_transport(self):
    self.errors[(self.recipe.URL,'camoufox')]=RuntimeError('no browser');self.parse();self.assertTrue(all(t is None for u,t in self.calls[1:]))
    self.errors.clear();self.calls.clear();self.parse();self.assertTrue(all(t=='camoufox' for u,t in self.calls if u!=self.recipe.WIKIPEDIA_URL))
    self.assertIn((self.recipe.WIKIPEDIA_URL,None),self.calls)

  def test_critical_errors_propagate_from_root_annual_and_fresh_supplement(self):
    for url in (self.recipe.URL,self.url(2026),self.recipe.WIKIPEDIA_URL):
      for error in (ImportCancelledError,CamoufoxRequiredError):
        self.errors={url:error('stop')}
        with self.assertRaises(error):self.parse()

  def test_disabled_fallbacks_omit_wikipedia_and_use_official_cache_scope(self):
    full=self.parse(disable_fallbacks=True);self.calls.clear();updated=self.parse(self.cache(full),disable_fallbacks=True)
    self.assertEqual(full['entries'],updated['entries']);self.assertNotIn((self.recipe.WIKIPEDIA_URL,None),self.calls)

  def test_judges_choice_is_main_winner_and_combined_public_choice_is_shortlisted(self):
    html='<h1>2024</h1><div id="main"><h1>ACT Book of the Year</h1>'+self.table('Main',2024,label="JUDGES' CHOICE")+self.table('Public',2024,label="HIGHLY COMMENDED AND PEOPLE'S CHOICE")+'</div>'
    source=self.recipe.parser().read_official_year(html,self.url(2024),2024)
    self.assertTrue(source['complete']);self.assertEqual(['winner','shortlisted'],[r['result'] for r in source['rows']])

  def test_separate_winner_label_is_not_part_of_author_credit(self):
    html=self.annual(2024).replace('Byron Writer, Jr.<br>','<p>WINNER</p><p>Byron Writer, Jr.<br>',1).replace('<br>Publisher</td>','<br>Publisher</p></td>',1)
    source=self.recipe.parser().read_official_year(html,self.url(2024),2024)
    self.assertEqual('Byron Writer, Jr.',source['rows'][0]['author'])

  def test_legacy_catalogue_host_plain_title_links_are_supported(self):
    html=self.annual(2024).replace('<em>Book 2024</em>','<a href="https://www.librarycatalogue.act.gov.au/catalogue/book">Book 2024</a>')
    source=self.recipe.parser().read_official_year(html,self.url(2024),2024)
    self.assertTrue(source['complete']);self.assertEqual(3,len(source['rows']))


if __name__=='__main__':unittest.main()
