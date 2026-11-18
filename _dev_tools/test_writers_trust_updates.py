import copy
import json
import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError,CamoufoxRequiredError,CamoufoxSkippedError
from storage import build_import_cache_data
from url_fetcher.writers_trust import (UrlFetcherWritersTrustAtwoodGibsonFiction,UrlFetcherWritersTrustHilaryWestonNonfiction,
  UrlFetcherWritersTrustBalsilliePublicPolicy,UrlFetcherWritersTrustShaughnessyCohenPoliticalWriting)
from url_fetcher.writers_trust_transport import WritersTrustFetchPolicy


RECIPES=(UrlFetcherWritersTrustAtwoodGibsonFiction,UrlFetcherWritersTrustHilaryWestonNonfiction,
  UrlFetcherWritersTrustBalsilliePublicPolicy,UrlFetcherWritersTrustShaughnessyCohenPoliticalWriting)


class WritersTrustUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=RECIPES[0]();self.years=[2024,2025,2026];self.calendar=2026
    self.calls,self.transports,self.failures,self.overrides=[],[],{},{}
    self.winner=0;self.title='A Tale';self.guidelines='';self.author='Writer One &amp; Writer Two'

  def title_for(self,year,index):return f'{self.title} {year} {index}'

  def history(self):
    return '<h1>Writers &amp; Books</h1><div><h3>'+self.recipe.AWARD_NAME+'</h3>'+''.join(
      f'<div><h4>{year}</h4><div>'+''.join(f'<div data-winner="{"winner" if i==self.winner else "finalist"}"><h3 class="book-title">{self.title_for(year,i)}</h3><h4>{self.author}</h4></div>' for i in range(2))+'</div></div>' for year in self.years)+'</div>'

  def current(self):
    year=max(self.years)
    return f'<main><h1>{self.recipe.AWARD_NAME}</h1><p>{self.guidelines}</p>'+''.join(
      f'<h2>{year} {"Winner" if i==self.winner else "Finalists"}</h2><article><div><h3 class="book-title">{self.title_for(year,i)}</h3><h4>{self.author}</h4><h5>Publisher</h5></div></article>' for i in range(2))+'</main>'

  def fetch(self,url,**kwargs):
    self.calls.append(url);self.transports.append(kwargs.get('transport','legacy'))
    if url in self.failures:raise self.failures[url]
    if url in self.overrides:return self.overrides[url]
    return self.history() if url==self.recipe.URL else self.current()

  def parse(self,old=None,incremental=None):
    with patch('parser.writers_trust_updates.datetime') as clock:
      clock.datetime.now.return_value.year=self.calendar
      return self.recipe.fetch_and_parse(self.fetch,cached_parsed=old,
        incremental_update=(old is not None) if incremental is None else incremental)

  def cache(self,parsed):return build_import_cache_data(self.recipe.source_id,parsed)

  def test_all_four_snapshot_recovery_ordinary_update_and_repeat(self):
    for cls in RECIPES:
      self.recipe=cls();self.calls.clear();full=self.parse()
      self.assertEqual(6,len(full['entries']));self.assertEqual(2,len(self.calls))
      stale=without_unit(self.cache(full),'history')
      self.assertLess(len(stale['entries']),len(full['entries']))
      self.calls.clear();recovered=self.parse(stale)
      self.assertEqual(full['entries'],recovered['entries']);self.assertEqual(2,len(self.calls))
      self.calls.clear();update=self.parse(self.cache(recovered))
      self.assertEqual(full['entries'],update['entries']);self.assertEqual([self.recipe.CURRENT_URL],self.calls)
      self.calls.clear();self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])
      self.assertEqual([self.recipe.CURRENT_URL],self.calls)

  def test_roster_changes_replace_removed_books_and_reconcile_winner(self):
    old=self.cache(self.parse());self.title='Corrected Tale';self.winner=1
    self.calls.clear();update=self.parse(old)
    self.assertIn(self.recipe.URL,self.calls);self.assertEqual(self.parse()['entries'],update['entries'])
    self.assertTrue(all(r['title'].startswith('Corrected') for r in update['entries']))

  def test_guideline_changes_and_new_cycle_refresh_history(self):
    old=self.cache(self.parse());self.guidelines='New deadline: 2027'
    self.calls.clear();update=self.parse(old);self.assertIn(self.recipe.URL,self.calls)
    self.assertEqual({'2024','2025','2026'},{r['award_year'] for r in update['entries']})
    self.years=[2025,2026,2027];self.calendar=2027
    self.assertEqual(self.parse()['entries'],self.parse(self.cache(update))['entries'])

  def test_missed_calendar_cycle_does_not_reuse_stale_history(self):
    old=self.cache(self.parse());self.calendar=2027;self.calls.clear();self.parse(old)
    self.assertIn(self.recipe.URL,self.calls)

  def test_current_failure_retains_snapshot_and_refreshes_history(self):
    full=self.parse();self.failures[self.recipe.CURRENT_URL]=RuntimeError('offline')
    self.calls.clear();update=self.parse(self.cache(full))
    self.assertEqual(full['entries'],update['entries']);self.assertIn(self.recipe.URL,self.calls)
    self.assertFalse(update['incremental_state']['units']['current']['complete'])

  def test_failed_history_after_current_correction_retains_pending_history(self):
    full=self.parse();old=self.cache(full);self.guidelines='Changed';self.failures[self.recipe.URL]=RuntimeError('offline')
    update=self.parse(old)
    self.assertEqual(full['entries'],update['entries']);self.assertFalse(update['incremental_state']['units']['history']['complete'])
    self.failures.clear();self.assertTrue(self.parse(self.cache(update))['incremental_state']['units']['history']['complete'])

  def test_incomplete_card_and_wrong_prize_are_rejected(self):
    parser=self.recipe.parser()
    bad=self.history().replace(f'<h4>{self.author}</h4>','',1)
    with self.assertRaisesRegex(ValueError,'incomplete'):parser.validate_fetch_payload(bad,self.recipe.URL)
    other=self.history().replace(self.recipe.AWARD_NAME,'Other Award')
    with self.assertRaises(ValueError):parser.validate_fetch_payload(other,self.recipe.URL)
    bad=self.current().replace(f'<h4>{self.author}</h4>','',1)
    with self.assertRaisesRegex(ValueError,'incomplete'):parser.validate_fetch_payload(bad,self.recipe.CURRENT_URL)

  def test_same_prize_stale_navigation_is_rejected_by_page_role(self):
    parser=self.recipe.parser()
    with self.assertRaisesRegex(ValueError,'archive markup'):parser.validate_fetch_payload(self.history(),self.recipe.CURRENT_URL)
    with self.assertRaisesRegex(ValueError,'current-page markup'):parser.validate_fetch_payload(self.current(),self.recipe.URL)

  def test_jurors_publisher_and_future_guidelines_are_not_books(self):
    parser=self.recipe.parser();html=self.current()+'<h2>Jury</h2><h3>Juror Name</h3><p>Future winner announced in 2027</p>'
    rows=parser.page_rows(html,self.recipe.CURRENT_URL)
    self.assertEqual(2,len(rows));self.assertEqual({'2026'},{r['award_year'] for r in rows})
    self.assertEqual({'Writer One & Writer Two'},{r['author'] for r in rows})

  def test_coauthor_projection_covers_storage_normalized_entries(self):
    old=self.cache(self.parse());used={i for u in old['incremental_state']['units'].values() for i in u['entry_indexes']}
    self.assertEqual(set(range(len(old['entries']))),used)
    self.assertIn(['Writer One','Writer Two'],[r['authors'] for r in old['entries']])
    self.calls.clear();self.parse(old);self.assertNotIn(self.recipe.URL,self.calls)

  def test_legacy_incompatible_cache_and_complete_refresh_read_both_pages(self):
    old=self.cache(self.parse());legacy=copy.deepcopy(old);legacy.pop('incremental_state')
    wrong=copy.deepcopy(old);wrong['incremental_state']['source_key']='other'
    for candidate,incremental in ((legacy,True),(wrong,True),(old,False)):
      self.calls.clear();self.parse(candidate,incremental);self.assertEqual(2,len(self.calls))

  def test_cancellation_and_required_browser_errors_propagate(self):
    for url in (self.recipe.URL,self.recipe.CURRENT_URL):
      for error in (ImportCancelledError,CamoufoxRequiredError):
        self.failures={url:error('stop')}
        with self.assertRaises(error):self.parse()

  def test_browser_rejection_uses_same_url_legacy_and_suppresses_later_browser(self):
    calls=[]
    def browser(url,**kwargs):calls.append(('browser',url));return '<html>Vercel Security Checkpoint</html>'
    def legacy(url):calls.append(('legacy',url));return self.current()
    policy=WritersTrustFetchPolicy(browser,legacy,self.recipe.parser())
    self.assertEqual(self.current(),policy.fetch(self.recipe.CURRENT_URL))
    policy.fetch(self.recipe.CURRENT_URL)
    self.assertEqual([('browser',self.recipe.CURRENT_URL),('legacy',self.recipe.CURRENT_URL),('legacy',self.recipe.CURRENT_URL)],calls)

  def test_browser_skipped_and_non_writer_hosts_keep_legacy_fetching(self):
    calls=[]
    def browser(*a,**kw):raise CamoufoxSkippedError('disabled')
    def legacy(url):calls.append(url);return self.current()
    policy=WritersTrustFetchPolicy(browser,legacy,self.recipe.parser())
    policy.fetch(self.recipe.CURRENT_URL);policy.fetch('https://example.org/reference')
    self.assertEqual([self.recipe.CURRENT_URL,'https://example.org/reference'],calls)

  def test_cache_and_digest_do_not_store_raw_html_or_javascript(self):
    old=self.cache(self.parse());self.assertNotIn('<article>',json.dumps(old))
    self.assertNotIn('innerHTML',json.dumps(old))
