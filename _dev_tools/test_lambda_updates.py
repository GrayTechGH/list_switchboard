import copy
import json
import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError, CamoufoxRequiredError
from parser.lambda_current import read_current
from parser.lambda_updates import DIRECTORY_NOTE, directory_source
from storage import build_import_cache_data
from url_fetcher.lambda_literary_awards import UrlFetcherLambdaLiteraryAwardsRomance


CATEGORIES = ('Gay Romance','Lesbian Romance','LGBTQ+ Romance and Erotica')


class LambdaUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=UrlFetcherLambdaLiteraryAwardsRomance();self.cycle=2026;self.closed=True
    self.calls,self.errors,self.overrides=[],{},{};self.directory_rows=[];self.advertised='';self.corrected=False
    self.clock=patch('parser.lambda_updates.datetime');self.dates=self.clock.start();self.addCleanup(self.clock.stop)
    self.dates.datetime.now.return_value.year=2026

  def title(self,year,category,index=0):return f'Winner Takes All {year} {CATEGORIES.index(category)} {index}'

  def directory(self):
    if self.directory_rows:return json.dumps({'records':[{'fields':row} for row in self.directory_rows]})
    return '<main><h1>Lammys Directory: 1988-Present</h1><iframe src="https://airtable.com/embed/appPublic/shrPublic"></iframe>'+self.advertised+'</main>'

  def article(self,kind,cycle=None):
    cycle=cycle or self.cycle;year=cycle-1
    parts=[]
    for category in CATEGORIES:
      if kind=='finalists':
        items=''.join(f'<li><a href="/books/{year}-{CATEGORIES.index(category)}-{i}"><b>{self.title(year,category,i)}</b></a> // <i>Writer, Jr.</i>. Publisher Inc.</li>' for i in range(5))
        parts.append(f'<section><h2>{category}</h2><img alt="Book covers of five finalists"><ul>{items}</ul></section>')
      else:
        index=1 if self.corrected else 0
        parts.append(f'<section><h2>{category}</h2><h2>{self.title(year,category,index)}</h2><h4>Writer, Jr.</h4><p>Publisher Inc.</p></section>')
    intro='The ceremony took place in June.' if self.closed else 'The ceremony will take place in June.'
    heading='Current Finalists' if kind=='finalists' else f'{cycle} Winners'
    return f'<title>Stale {cycle-1} Lambda title</title><main><h1>{heading}</h1><div class="elementor"><p>Congratulations to the creators of {cycle} Lammy Award {kind} titles. {intro}</p>'+''.join(parts)+'</div><footer><p>2029 Lammy Award winners were announced</p></footer></main>'

  def fetch(self,url,**kw):
    self.calls.append((url,kw.get('transport')))
    error=self.errors.get((url,kw.get('transport'))) or self.errors.get(url)
    if error:raise error
    if url in self.overrides:return self.overrides[url]
    if url==self.recipe.URL:return self.directory()
    if url==self.recipe.FINALISTS_URL:return self.article('finalists')
    return self.article('winners',self.recipe.parser().year_from_text(url))

  def parse(self,old=None,incremental=None):
    return self.recipe.fetch_and_parse(self.fetch,cached_parsed=old,
      incremental_update=(old is not None) if incremental is None else incremental)

  def cache(self,parsed):return build_import_cache_data(self.recipe.source_id,parsed)

  def test_real_missing_nominees_restore_in_two_fetches_and_repeat_keeps_savings(self):
    full=self.parse();self.assertEqual(15,len(full['entries']));self.assertEqual(3,len(self.calls))
    stale=without_unit(self.cache(full),self.recipe.FINALISTS_URL);self.assertEqual(3,len(stale['entries']));self.calls.clear()
    updated=self.parse(stale);self.assertEqual(full['entries'],updated['entries']);self.assertEqual(2,len(self.calls));self.calls.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(updated))['entries']);self.assertEqual(2,len(self.calls))

  def test_directory_coverage_note_is_preserved_without_claiming_embedded_history(self):
    full=self.parse();self.assertIn(DIRECTORY_NOTE,full['notes'])
    self.assertEqual('embedded-history-unavailable',full['incremental_state']['units'][self.recipe.URL]['metadata']['coverage'])
    self.assertFalse(full['incremental_state']['units'][self.recipe.URL]['entry_indexes'])

  def test_marked_authors_keep_initials_and_suffixes_and_exclude_publishers(self):
    page=self.article('finalists').replace('<i>Writer, Jr.</i>','<i>J. R. Writer, Jr.</i>')
    source=read_current(self.recipe.parser(),page,self.recipe.FINALISTS_URL,'finalists')
    self.assertTrue(source['complete']);self.assertTrue(all(r['author']=='J. R. Writer, Jr.' for r in source['rows']))
    self.assertTrue(all(r['title'].startswith('Winner Takes All') for r in source['rows']))

  def test_unlinked_title_and_italic_title_markup_do_not_replace_author(self):
    page=self.article('finalists').replace('<b>','<em>').replace('</b>','</em>')
    title=self.title(2025,CATEGORIES[0]);page=page.replace(f'<a href="/books/2025-0-0"><em>{title}</em></a>',title)
    source=read_current(self.recipe.parser(),page,self.recipe.FINALISTS_URL,'finalists')
    self.assertTrue(source['complete']);self.assertEqual('Writer, Jr.',source['rows'][0]['author']);self.assertEqual(title,source['rows'][0]['title'])

  def test_ceremony_year_comes_from_own_intro_and_headings_not_stale_title_or_footer(self):
    for kind,url in [('finalists',self.recipe.FINALISTS_URL),('winners',self.recipe.WINNER_URLS[0])]:
      source=read_current(self.recipe.parser(),self.article(kind),url,kind)
      self.assertEqual(2025,source['publication_year']);self.assertTrue(all(r['award_year']=='2025' for r in source['rows']))

  def test_open_cycle_cannot_be_closed_by_footer_and_keeps_winner_post_fresh(self):
    self.closed=False;old=self.cache(self.parse());self.calls.clear();self.parse(old)
    self.assertEqual(3,len(self.calls));self.assertIn((self.recipe.WINNER_URLS[0],'camoufox'),self.calls)

  def test_changed_roster_forces_dated_winner_refresh(self):
    old=self.cache(self.parse());page=self.article('finalists').replace(self.title(2025,CATEGORIES[0],4),'Corrected Finalist')
    self.overrides[self.recipe.FINALISTS_URL]=page;self.calls.clear();self.parse(old);self.assertEqual(3,len(self.calls))

  def test_missing_winner_book_in_current_roster_does_not_certify_closed_reuse(self):
    self.overrides[self.recipe.FINALISTS_URL]=self.article('finalists').replace(self.title(2025,CATEGORIES[0]),'Different Work')
    old=self.cache(self.parse());self.calls.clear();self.parse(old);self.assertEqual(3,len(self.calls))

  def test_new_cycle_retains_previous_finalists_when_embedded_history_remains_unavailable(self):
    old=self.cache(self.parse());self.cycle=2027;self.dates.datetime.now.return_value.year=2027
    url='https://lambdaliterary.org/awards/2027-winners/';self.advertised=f'<a href="{url}">2027 Winners</a>'
    parsed=self.parse(old);self.assertEqual(30,len(parsed['entries']));self.assertIn('retained-finalists-2025',parsed['incremental_state']['units'])
    self.assertEqual(15,sum(r['award_year']=='2025' for r in parsed['entries']));self.assertIn((url,'camoufox'),self.calls)
    repeated=self.parse(self.cache(parsed));self.assertEqual(parsed['entries'],repeated['entries'])

  def test_supported_directory_export_replaces_retained_rolling_history(self):
    old=self.cache(self.parse());self.cycle=2027;self.dates.datetime.now.return_value.year=2027
    moved=self.parse(old)
    self.directory_rows=[{'Year':2025,'Category':CATEGORIES[0],'Title':'Directory Replacement','Author':'Writer, Jr.','Status':'Winner'}]
    parsed=self.parse(self.cache(moved));self.assertNotIn('retained-finalists-2025',parsed['incremental_state']['units'])
    self.assertIn('Directory Replacement',[r['title'] for r in parsed['entries']])

  def test_fresh_directory_winner_is_authoritative_over_cached_dated_winner(self):
    old=self.cache(self.parse())
    self.directory_rows=[{'Year':2025,'Category':CATEGORIES[0],'Title':self.title(2025,CATEGORIES[0],1),'Author':'Writer, Jr.','Status':'Winner'}]
    parsed=self.parse(old);category=[r for r in parsed['entries'] if r['category']==CATEGORIES[0]]
    self.assertEqual([self.title(2025,CATEGORIES[0],1)],[r['title'] for r in category if r['result']=='winner'])
    self.assertEqual('shortlisted',next(r['result'] for r in category if r['title']==self.title(2025,CATEGORIES[0])))

  def test_source_projection_restores_original_winner_after_directory_authority_changes(self):
    old=self.cache(self.parse());self.directory_rows=[{'Year':2025,'Category':CATEGORIES[0],'Title':self.title(2025,CATEGORIES[0],1),'Author':'Writer, Jr.','Status':'Winner'}]
    changed=self.parse(old);self.directory_rows=[];self.errors[self.recipe.WINNER_URLS[0]]=RuntimeError('temporary dated source failure')
    parsed=self.parse(self.cache(changed));category=[r for r in parsed['entries'] if r['category']==CATEGORIES[0]]
    self.assertEqual([self.title(2025,CATEGORIES[0])],[r['title'] for r in category if r['result']=='winner'])
    self.assertFalse(parsed['incremental_state']['units'][self.recipe.WINNER_URLS[0]]['complete'])

  def test_invalid_or_incomplete_source_keeps_previous_whole_unit_pending(self):
    old=self.cache(self.parse());self.errors[self.recipe.FINALISTS_URL]=RuntimeError('temporary failure')
    parsed=self.parse(old);self.assertEqual(old['entries'],parsed['entries']);self.assertFalse(parsed['incremental_state']['units'][self.recipe.FINALISTS_URL]['complete'])
    self.errors.clear();self.assertTrue(self.parse(self.cache(parsed))['incremental_state']['units'][self.recipe.FINALISTS_URL]['complete'])

  def test_missing_dated_unit_and_complete_refresh_fetch_winners_again(self):
    old=self.cache(self.parse());old['incremental_state']['units'].pop(self.recipe.WINNER_URLS[0]);self.calls.clear()
    self.parse(old);self.assertEqual(3,len(self.calls));baseline=self.cache(self.parse());self.calls.clear();self.parse(baseline,incremental=False)
    self.assertEqual(3,len(self.calls));self.assertIn((self.recipe.WINNER_URLS[0],'camoufox'),self.calls)

  def test_legacy_wrong_scope_and_corrupt_projection_rebuild_affected_sources(self):
    old=self.cache(self.parse());cases=[dict(old,incremental_state={}),copy.deepcopy(old),copy.deepcopy(old)]
    cases[1]['incremental_state']['source_key']='wrong scope';cases[2]['incremental_state']['units'][self.recipe.WINNER_URLS[0]]['metadata']['rows']='corrupt'
    for cache in cases:
      self.calls.clear();self.assertEqual(old['entries'],self.parse(cache)['entries']);self.assertEqual(3,len(self.calls))

  def test_partial_declared_roster_or_missing_category_cannot_certify_completeness(self):
    page=self.article('finalists')
    for malformed in [page.replace(page[page.index('<li>'):page.index('</li>')+5],'',1),page.replace('<h2>Gay Romance</h2>','<h2>Other Fiction</h2>')]:
      self.assertFalse(read_current(self.recipe.parser(),malformed,self.recipe.FINALISTS_URL,'finalists')['complete'])

  def test_wrong_dated_ceremony_year_is_rejected(self):
    with self.assertRaisesRegex(ValueError,'another ceremony year'):
      read_current(self.recipe.parser(),self.article('winners',2025),self.recipe.WINNER_URLS[0],'winners')

  def test_browser_recovery_is_operation_local_and_critical_errors_propagate(self):
    self.errors[(self.recipe.URL,'camoufox')]=RuntimeError('browser unavailable');self.parse();self.assertTrue(all(t is None for u,t in self.calls[1:]))
    self.errors.clear();self.calls.clear();self.parse();self.assertTrue(all(t=='camoufox' for u,t in self.calls))
    for url in (self.recipe.URL,self.recipe.FINALISTS_URL,self.recipe.WINNER_URLS[0]):
      for error in (ImportCancelledError,CamoufoxRequiredError):
        self.errors={url:error('stop')}
        with self.assertRaises(error):self.parse()

  def test_discovery_ignores_foreign_winner_links_and_embed_mentions_without_iframes(self):
    self.advertised='<a href="https://example.com/awards/2027-winners/">Other site</a>';self.parse()
    self.assertFalse(any('example.com' in url for url,t in self.calls))
    self.assertFalse(self.recipe.parser().has_airtable_embed('<p>https://airtable.com/embed/appExample/shrExample</p>'))

  def test_next_dated_source_can_be_discovered_from_current_page_navigation(self):
    self.cycle=2027;self.dates.datetime.now.return_value.year=2027
    url='https://lambdaliterary.org/awards/2027-winners/'
    self.overrides[self.recipe.FINALISTS_URL]=self.article('finalists')+f'<nav><a href="{url}">Current winners</a></nav>'
    self.parse();self.assertIn((url,'camoufox'),self.calls)

  def test_future_dated_winners_are_not_reused_before_their_calendar_year(self):
    self.dates.datetime.now.return_value.year=2025;old=self.cache(self.parse());self.calls.clear();self.parse(old)
    self.assertEqual(3,len(self.calls))

  def test_publication_year_export_header_is_supported_and_virtual_grid_is_not_a_complete_export(self):
    source=json.dumps({'records':[{'fields':{'Year (Published)':2024,'Title':'Directory Work','Author':'Writer','Category':'Gay Romance','Status':'Winner'}}]})
    self.assertEqual('2024',directory_source(self.recipe.parser(),source,self.recipe.URL)['rows'][0]['award_year'])
    with self.assertRaisesRegex(ValueError,'neither supported rows'):
      directory_source(self.recipe.parser(),'<div role="grid" aria-rowcount="4373"><div role="row">Only visible records</div></div>',self.recipe.URL)


if __name__=='__main__':unittest.main()
