import copy
import json
import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError,ImportCancelledError
from parser.newbery import NewberyMedalParser,PDF_URL,yma_awards_url
from storage import build_import_cache_data
from url_fetcher.newbery import UrlFetcherJohnNewberyMedal


class NewberyUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=UrlFetcherJohnNewberyMedal()
    self.year=1924;self.pdf_last=1924;self.pdf_url=PDF_URL
    self.calls,self.failures,self.overrides=[],{},{}
    self.revised=False

  def pdf(self):
    return '\n'.join(f'{year} Medal Winner\nMedal Tale {year}'+(' Corrected' if self.revised and year==1922 else '')+f' by Writer {year} (Publisher)\n{year} Honor Books\nRecognized Tale {year} by Other Writer (Publisher)' for year in range(1922,self.pdf_last+1))

  def fetch(self,url):
    self.calls.append(url)
    if url in self.failures:raise self.failures[url]
    if url in self.overrides:return self.overrides[url]
    if url==self.recipe.URL:return f'<a href="{self.pdf_url}">Newbery Medal and Honor Books, 1922-present complete list PDF</a>'
    if url==self.pdf_url:return self.pdf()
    year=int(url.split('/news/')[1][:4])
    return f'<h1>American Library Association announces {year} Youth Media Award winners</h1><h2>John Newbery Medal</h2><p>"Current {year}," written by Current Writer and published by Publisher.</p><h3>Newbery Honor Books</h3><p>"Honor {year}," written by Another Writer and published by Publisher.</p><h2>Randolph Caldecott Medal</h2><p>"Excluded" by Artist</p>'

  def parse(self,old=None,incremental=None):
    with patch('parser.newbery.date') as clock:
      clock.today.return_value.year=self.year
      return self.recipe.fetch_and_parse(self.fetch,cached_parsed=old,
        incremental_update=(old is not None) if incremental is None else incremental)

  def cache(self,parsed):return build_import_cache_data(self.recipe.source_id,parsed)

  def test_whole_pdf_recovery_and_ordinary_updates_have_separate_costs(self):
    full=self.parse();self.assertEqual(6,len(full['entries']));self.assertEqual(2,len(self.calls))
    stale=without_unit(self.cache(full),'pdf');self.assertFalse(stale['entries'])
    self.calls.clear();recovered=self.parse(stale)
    self.assertEqual(full['entries'],recovered['entries']);self.assertEqual(2,len(self.calls))
    self.calls.clear();updated=self.parse(self.cache(recovered))
    self.assertEqual(full['entries'],updated['entries']);self.assertEqual([self.recipe.URL],self.calls)
    self.calls.clear();self.assertEqual(full['entries'],self.parse(self.cache(updated))['entries'])
    self.assertEqual([self.recipe.URL],self.calls)

  def test_calendar_rollover_refetches_same_pdf_url(self):
    old=self.cache(self.parse());self.year=1925;self.pdf_last=1925
    self.calls.clear();update=self.parse(old)
    self.assertEqual([self.recipe.URL,self.pdf_url],self.calls)
    self.assertEqual(self.parse()['entries'],update['entries'])

  def test_new_pdf_link_and_complete_refresh_apply_historical_corrections(self):
    old=self.cache(self.parse());self.pdf_url='https://www.ala.org/newbery-revised.pdf';self.revised=True
    update=self.parse(old)
    self.assertIn('Medal Tale 1922 Corrected',[r['title'] for r in update['entries']])
    self.assertEqual(self.parse()['entries'],update['entries'])
    self.calls.clear();self.parse(self.cache(update),False)
    self.assertIn(self.pdf_url,self.calls)

  def test_lagging_pdf_preserves_annual_yma_and_refreshes_current_results(self):
    self.year=1926
    full=self.parse();self.assertEqual(10,len(full['entries']));self.assertEqual(4,len(self.calls))
    self.calls.clear();update=self.parse(self.cache(full))
    self.assertEqual(full['entries'],update['entries']);self.assertEqual(3,len(self.calls))
    self.assertNotIn(yma_awards_url(1925),self.calls);self.assertIn(yma_awards_url(1926),self.calls)

  def test_failed_pdf_replacement_retains_original_history_pending_retry(self):
    full=self.parse();old=self.cache(full);self.pdf_url='https://www.ala.org/newbery-new.pdf'
    self.failures[self.pdf_url]=RuntimeError('offline')
    update=self.parse(old)
    self.assertEqual(full['entries'],update['entries']);self.assertFalse(update['incremental_state']['units']['pdf']['complete'])
    self.failures.clear();self.assertTrue(self.parse(self.cache(update))['incremental_state']['units']['pdf']['complete'])

  def test_partial_and_challenged_pdf_cannot_certify_history(self):
    full=self.parse();old=self.cache(full);self.year=1925
    for bad in ('<html>Challenge</html>','1924 Medal Winner\nPartial by A Writer (Publisher)'):
      self.overrides[self.pdf_url]=bad
      update=self.parse(old)
      self.assertFalse(update['incremental_state']['units']['pdf']['complete'])
      self.assertTrue({r['title'] for r in full['entries']}.issubset({r['title'] for r in update['entries']}))

  def test_failed_or_wrong_year_yma_retains_prior_supplement(self):
    self.year=1925;full=self.parse();old=self.cache(full);url=yma_awards_url(1925)
    for bad in (RuntimeError('offline'),'<h1>American Library Association announces 1926 Youth Media Award winners</h1><h2>John Newbery Medal</h2><p>"Wrong" by Other Writer</p>'):
      self.failures.clear();self.overrides.clear()
      if isinstance(bad,Exception):self.failures[url]=bad
      else:self.overrides[url]=bad
      update=self.parse(old)
      self.assertEqual(full['entries'],update['entries']);self.assertFalse(update['incremental_state']['units']['1925']['complete'])

  def test_missing_pdf_link_forces_refresh_and_keeps_discovery_pending(self):
    full=self.parse();self.overrides[self.recipe.URL]='<html>Challenge</html>'
    self.calls.clear();update=self.parse(self.cache(full))
    self.assertIn(self.pdf_url,self.calls);self.assertFalse(update['incremental_state']['units']['pdf']['complete'])

  def test_legacy_or_incompatible_cache_and_explicit_refresh_download_pdf(self):
    old=self.cache(self.parse());legacy=copy.deepcopy(old);legacy.pop('incremental_state')
    wrong=copy.deepcopy(old);wrong['incremental_state']['source_key']='other'
    for candidate,incremental in ((legacy,True),(wrong,True),(old,False)):
      self.calls.clear();self.parse(candidate,incremental);self.assertEqual(2,len(self.calls))

  def test_cancellation_and_browser_requirements_propagate(self):
    for target in (self.pdf_url,yma_awards_url(1925)):
      self.year=1925
      for error in (ImportCancelledError,CamoufoxRequiredError):
        self.failures={target:error('stop')}
        with self.assertRaises(error):self.parse()

  def test_wrapped_authors_publishers_and_title_by_are_preserved(self):
    text='''2017 Medal Winner\nThe Girl Who Drank the Moon by Kelly Barnhill (Publisher)\n2017 Honor Books
Freedom Over Me: Dreams Brought to Life by Ashley Bryan by Ashley
Bryan (Publisher)
The Inquisitor's Tale written by Adam Gidwitz,
illustrated by Hatem Aly (Publisher)
Other Tale by Long Writer (An imprint of Penguin
Random House)
Last Tale by Last Writer (Unclosed Publisher
Next Tale by Next Writer (Publisher)'''
    rows=NewberyMedalParser().rows_from_text(text,PDF_URL)
    self.assertEqual([('The Girl Who Drank the Moon','Kelly Barnhill'),
      ('Freedom Over Me: Dreams Brought to Life by Ashley Bryan','Ashley Bryan'),
      ("The Inquisitor's Tale",'Adam Gidwitz, illustrated by Hatem Aly'),
      ('Other Tale','Long Writer'),('Last Tale','Last Writer'),('Next Tale','Next Writer')],
      [(r['title'],r['author']) for r in rows])

  def test_complete_pdf_requires_every_medal_year_since_1922(self):
    parser=NewberyMedalParser();rows=parser.rows_from_text(self.pdf(),self.pdf_url)
    self.assertTrue(parser.complete_pdf_rows(rows))
    self.assertFalse(parser.complete_pdf_rows([r for r in rows if r['award_year']!='1923']))
    self.assertFalse(parser.complete_pdf_rows(rows+[rows[0]]))

  def test_cache_contains_parsed_entries_without_pdf_payload(self):
    old=self.cache(self.parse());self.assertNotIn('%PDF-',json.dumps(old))
    used={i for u in old['incremental_state']['units'].values() for i in u['entry_indexes']}
    self.assertEqual(set(range(len(old['entries']))),used)
