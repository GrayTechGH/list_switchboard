import copy
import json
import unittest
from unittest.mock import patch

from _dev_tools import test_splatterpunk_transport as fixtures
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError,ImportCancelledError
from parser.splatterpunk import OFFICIAL_AWARDS_API_URL,OFFICIAL_PAST_WINNERS_API_URL,GOODREADS_URL
from storage import build_import_cache_data


class SplatterpunkUpdateTests(unittest.TestCase):

  def setUp(self):
    fixture=fixtures.SplatterpunkTransportTests();fixture.setUp()
    self.pages=fixture.pages;self.recipe=fixtures.FETCHERS[0]();self.calls=[];self.failures={}
    self.clock=patch('parser.splatterpunk_updates.datetime');self.dates=self.clock.start()
    self.addCleanup(self.clock.stop);self.dates.datetime.now.return_value.year=2026
    self.intake()
    self.pages[OFFICIAL_PAST_WINNERS_API_URL]=self.pages[OFFICIAL_PAST_WINNERS_API_URL].replace(
      '</ul>','<li>2026 - Latest Winner by Latest Writer</li></ul>')

  def intake(self,year=2027):
    headings=''.join(f'<h3>BEST {factory.CATEGORY}</h3>' for factory in fixtures.FETCHERS)
    self.pages[OFFICIAL_AWARDS_API_URL]=fixtures.official(f'{year} Splatterpunk Awards',
      f'<p>If you are seeking to nominate works for the {year}, please fill out <a href="https://forms.example/nominate">this form</a>.</p>'+headings)

  def fetch(self,url,**kwargs):
    self.calls.append((url,kwargs.get('transport')))
    failure=self.failures.get((url,kwargs.get('transport'))) or self.failures.get(url)
    if failure:raise failure
    return self.pages[url]

  def parse(self,old=None,incremental=None):
    return self.recipe.fetch_and_parse(self.fetch,cached_parsed=old,
      incremental_update=(old is not None) if incremental is None else incremental)

  def cache(self,parsed):return build_import_cache_data(self.recipe.source_id,parsed)

  def test_all_four_categories_restore_missing_supplement_and_skip_closed_winners(self):
    for factory in fixtures.FETCHERS:
      self.recipe=factory();self.calls.clear();full=self.parse();self.assertEqual(4,len(self.calls))
      old=without_unit(self.cache(full),'goodreads');self.assertLess(len(old['entries']),len(full['entries']))
      self.calls.clear();updated=self.parse(old)
      self.assertEqual(full['entries'],updated['entries']);self.assertEqual(3,len(self.calls))
      self.assertNotIn(OFFICIAL_PAST_WINNERS_API_URL,[url for url,_mode in self.calls])
      self.calls.clear();repeated=self.parse(self.cache(updated))
      self.assertEqual(full['entries'],repeated['entries']);self.assertEqual(3,len(self.calls))

  def test_missing_history_fetches_it_instead_of_losing_winners(self):
    full=self.parse();old=without_unit(self.cache(full),'winners')
    self.calls.clear();updated=self.parse(old)
    self.assertEqual(full['entries'],updated['entries'])
    self.assertIn(OFFICIAL_PAST_WINNERS_API_URL,[url for url,_mode in self.calls])

  def test_calendar_rollover_and_stale_future_cycle_refresh_history(self):
    old=self.cache(self.parse())
    for calendar in (2025,2027,2028):
      self.dates.datetime.now.return_value.year=calendar;self.calls.clear()
      self.parse(old);self.assertIn(OFFICIAL_PAST_WINNERS_API_URL,[url for url,_mode in self.calls])

  def test_active_ballot_always_refreshes_winners_even_with_same_revision(self):
    fixture=fixtures.SplatterpunkTransportTests();fixture.setUp()
    self.pages[OFFICIAL_AWARDS_API_URL]=fixture.pages[OFFICIAL_AWARDS_API_URL]
    old=self.cache(self.parse());self.calls.clear();self.parse(old)
    self.assertIn(OFFICIAL_PAST_WINNERS_API_URL,[url for url,_mode in self.calls])

  def test_changed_intake_refreshes_corrected_winners_and_replaces_old_rows(self):
    old=self.cache(self.parse())
    self.pages[OFFICIAL_AWARDS_API_URL]=self.pages[OFFICIAL_AWARDS_API_URL].replace('this form','the updated form')
    self.pages[OFFICIAL_PAST_WINNERS_API_URL]=self.pages[OFFICIAL_PAST_WINNERS_API_URL].replace('Official Novel 2019','Corrected Novel 2019')
    self.calls.clear();updated=self.parse(old)
    self.assertIn(OFFICIAL_PAST_WINNERS_API_URL,[url for url,_mode in self.calls])
    self.assertEqual(self.parse()['entries'],updated['entries'])
    self.assertNotIn('Official Novel 2019',[r['title'] for r in updated['entries']])

  def test_incomplete_or_lagging_winner_history_is_not_reused(self):
    self.pages[OFFICIAL_PAST_WINNERS_API_URL]=self.pages[OFFICIAL_PAST_WINNERS_API_URL].replace(
      '<li>2026 - Latest Winner by Latest Writer</li>','')
    old=self.cache(self.parse());self.calls.clear();self.parse(old)
    self.assertIn(OFFICIAL_PAST_WINNERS_API_URL,[url for url,_mode in self.calls])

  def test_intake_requires_explicit_form_and_no_work_paragraphs(self):
    original=self.pages[OFFICIAL_AWARDS_API_URL]
    for bad in (original.replace('seeking to nominate works','awaiting information'),
        original.replace('<h3>BEST Novel</h3>','<h3>BEST Novel</h3><p>Actual Nominee by Writer</p>'),
        original.replace('https://killerconatx.com/awards/','https://killerconatx.com/other/')):
      self.pages[OFFICIAL_AWARDS_API_URL]=bad
      if 'Actual Nominee' in bad:
        self.assertFalse(self.recipe.parser().current_phase(bad)['intake'])
      else:
        parsed=self.parse();self.assertFalse(parsed['incremental_state']['units']['current']['complete'])

  def test_failed_history_retains_rows_pending_then_recovers(self):
    full=self.parse();old=self.cache(full);old['incremental_state']['units']['winners']['complete']=False
    self.failures[OFFICIAL_PAST_WINNERS_API_URL]=OSError('offline')
    updated=self.parse(old);self.assertEqual(full['entries'],updated['entries'])
    self.assertFalse(updated['incremental_state']['units']['winners']['complete'])
    self.failures.clear();self.calls.clear();self.parse(self.cache(updated))
    self.assertIn(OFFICIAL_PAST_WINNERS_API_URL,[url for url,_mode in self.calls])

  def test_failed_later_goodreads_page_preserves_entire_previous_supplement(self):
    full=self.parse();self.failures[fixtures.NEXT]=OSError('offline')
    updated=self.parse(self.cache(full));self.assertEqual(full['entries'],updated['entries'])
    self.assertFalse(updated['incremental_state']['units']['goodreads']['complete'])
    self.failures.clear();self.assertEqual(full['entries'],self.parse(self.cache(updated))['entries'])

  def test_current_failure_cannot_freeze_history(self):
    full=self.parse();self.failures[OFFICIAL_AWARDS_API_URL]=OSError('offline');self.calls.clear()
    updated=self.parse(self.cache(full));self.assertEqual(full['entries'],updated['entries'])
    self.assertFalse(updated['incremental_state']['units']['current']['complete'])
    self.assertIn(OFFICIAL_PAST_WINNERS_API_URL,[url for url,_mode in self.calls])

  def test_conflicting_goodreads_winner_stays_excluded_after_official_correction(self):
    title='Official Novel 2018';self.pages[GOODREADS_URL]=fixtures.page([
      fixtures.row(title,'Novel',2018,True),fixtures.row('Unrelated Nominee','Novel',2019)])
    full=self.parse();self.assertEqual(1,sum(r['title']==title for r in full['entries']))
    self.pages[OFFICIAL_AWARDS_API_URL]=self.pages[OFFICIAL_AWARDS_API_URL].replace('this form','changed form')
    self.pages[OFFICIAL_PAST_WINNERS_API_URL]=self.pages[OFFICIAL_PAST_WINNERS_API_URL].replace(title,'Replacement Winner')
    updated=self.parse(self.cache(full));self.assertEqual(self.parse()['entries'],updated['entries'])
    self.assertNotIn(title,[r['title'] for r in updated['entries']])
    self.assertTrue(any('conflicting Goodreads winner' in note for note in updated['notes']))

  def test_reused_history_does_not_retain_old_goodreads_title_aliases(self):
    self.pages[OFFICIAL_PAST_WINNERS_API_URL]=self.pages[OFFICIAL_PAST_WINNERS_API_URL].replace('Official Novel 2018','Header Three')
    self.pages[GOODREADS_URL]=fixtures.page([fixtures.row('Header 3','Novel',2018,True)])
    full=self.parse();winner=next(r for r in full['entries'] if r['title']=='Header Three')
    self.assertEqual(['Header 3'],winner['aliases'])
    self.pages[GOODREADS_URL]=fixtures.page([fixtures.row('Different nominee','Novel',2019)])
    self.calls.clear();updated=self.parse(self.cache(full))
    self.assertNotIn(OFFICIAL_PAST_WINNERS_API_URL,[url for url,_mode in self.calls])
    self.assertNotIn('aliases',next(r for r in updated['entries'] if r['title']=='Header Three'))
    self.assertEqual(self.parse()['entries'],updated['entries'])

  def test_shifted_goodreads_pages_and_new_nominees_refresh_all_pages(self):
    old=self.cache(self.parse())
    self.pages[GOODREADS_URL]=fixtures.page([fixtures.row('New Nominee','Novel',2027),
      fixtures.row('Historical Novel Two','Novel',2020)],fixtures.NEXT)
    self.pages[fixtures.NEXT]=fixtures.page([fixtures.row('Historical Novel One','Novel',2019)])
    self.calls.clear();updated=self.parse(old)
    self.assertIn((GOODREADS_URL,'camoufox'),self.calls)
    self.assertIn((fixtures.NEXT,'camoufox'),self.calls)
    self.assertEqual(1,sum(r['title']=='Historical Novel Two' for r in updated['entries']))
    self.assertEqual(self.parse()['entries'],updated['entries'])

  def test_legacy_wrong_scope_corrupt_projection_and_complete_refresh_rebuild_history(self):
    old=self.cache(self.parse());legacy=copy.deepcopy(old);legacy.pop('incremental_state')
    wrong=copy.deepcopy(old);wrong['incremental_state']['source_key']='other category'
    bad=copy.deepcopy(old);bad['incremental_state']['units']['winners']['metadata']={}
    for candidate,incremental in ((legacy,True),(wrong,True),(bad,True),(old,False)):
      self.calls.clear();self.parse(candidate,incremental)
      self.assertIn(OFFICIAL_PAST_WINNERS_API_URL,[url for url,_mode in self.calls])

  def test_critical_errors_propagate_at_every_source_and_clear_operation_policies(self):
    for url in (OFFICIAL_AWARDS_API_URL,OFFICIAL_PAST_WINNERS_API_URL,GOODREADS_URL,fixtures.NEXT):
      for cls in (ImportCancelledError,CamoufoxRequiredError):
        self.failures={url:cls('stop')}
        with self.assertRaises(cls):self.parse()
        self.assertIsNone(self.recipe._splatterpunk_fetch_policy)
        self.assertIsNone(self.recipe._splatterpunk_official_policy)


if __name__=='__main__':unittest.main()
