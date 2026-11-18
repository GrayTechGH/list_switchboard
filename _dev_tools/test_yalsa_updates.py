import copy
import json
import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError,ImportCancelledError
from parser.morris import MorrisAwardParser
from parser.yalsa_nonfiction import YALSANonfictionAwardParser
from parser.yalsa_base import yma_awards_url
from storage import build_import_cache_data
from url_fetcher.morris import UrlFetcherWilliamCMorrisAward
from url_fetcher.yalsa_nonfiction import UrlFetcherYALSAExcellenceNonfictionYoungAdults
from url_fetcher.printz import UrlFetcherMichaelLPrintzAward


RECIPES=(UrlFetcherWilliamCMorrisAward,UrlFetcherYALSAExcellenceNonfictionYoungAdults,UrlFetcherMichaelLPrintzAward)


class YALSAUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=RECIPES[0]()
    self.history_year=2022
    self.current_year=2026
    self.calls,self.failures,self.overrides=[],{},{}
    self.links={}
    self.winner=0

  def stages(self):
    if self.recipe.source_id=='william_c_morris_award':return 'William C. Morris Award','William C. Morris Award Finalists','Morris Award'
    if self.recipe.source_id=='yalsa_excellence_nonfiction_young_adults':
      return 'Award for Excellence in Nonfiction for Young Adults','Award for Excellence in Nonfiction for Young Adults Finalists','Nonfiction Award'
    return 'Michael L. Printz Award','Printz Honor Books','Michael L. Printz Award'

  def title(self,year,index):
    return f'Tale {year} {index}'

  def history(self):
    stage='Honor Books' if self.recipe.source_id=='michael_l_printz_award' else 'Finalists'
    return ''.join(f'<h2>{year}</h2><h3>Winner</h3><p>"{self.title(year,0)}" by Writer Zero</p><h3>{stage}</h3><p>"{self.title(year,1)}" by Writer One</p>'
      for year in range(2022,self.history_year+1))

  def current(self):
    prefix=self.stages()[2]
    return f'<h2>{self.current_year} {prefix} Winner: "{self.title(self.current_year,self.winner)}" by Writer {"Zero" if self.winner==0 else "One"}</h2>'+''.join(
      f'<a href="{url}">{year} {prefix}</a>' for year,url in self.links.items())

  def annual(self,year):
    first,second,_prefix=self.stages()
    other=1-self.winner
    return f'<h2>{first}</h2><p>"{self.title(year,self.winner)}" by Writer {"Zero" if self.winner==0 else "One"}</p><h3>{second}</h3><p>"{self.title(year,other)}" by Writer {"Zero" if other==0 else "One"}</p><h2>Schneider Family Book Award</h2><p>"Excluded" by Other Person</p>'

  def fetch(self,url):
    self.calls.append(url)
    if url in self.failures:raise self.failures[url]
    if url in self.overrides:return self.overrides[url]
    if url==self.recipe.URL:return self.history()
    if url==self.recipe.parser().CURRENT_URL:return self.current()
    year=next((y for y,u in self.links.items() if u==url),None)
    if year is None:year=int(url.split('/news/')[1][:4])
    return self.annual(year)

  def parse(self,old=None,incremental=None):
    with patch('parser.yalsa_base.date') as clock,patch('parser.printz.date') as printz_clock:
      clock.today.return_value.year=self.current_year
      printz_clock.today.return_value.year=self.current_year
      return self.recipe.fetch_and_parse(self.fetch,cached_parsed=old,
        incremental_update=(old is not None) if incremental is None else incremental)

  def cache(self,parsed):
    return build_import_cache_data(self.recipe.source_id,parsed)

  def test_all_three_recipes_recover_actual_missing_history_and_repeat(self):
    for cls in RECIPES:
      self.recipe=cls();self.calls.clear()
      full=self.parse()
      self.assertEqual(10,len(full['entries']))
      self.assertEqual(6,len(self.calls))
      old=without_unit(self.cache(full),'2025')
      self.assertEqual(8,len(old['entries']))
      self.calls.clear();update=self.parse(old)
      self.assertEqual(full['entries'],update['entries'])
      self.assertEqual(4,len(self.calls))
      self.calls.clear();repeat=self.parse(self.cache(update))
      self.assertEqual(full['entries'],repeat['entries'])
      self.assertEqual(3,len(self.calls))
      self.assertNotIn(yma_awards_url(2025),self.calls)

  def test_new_year_and_advancing_history_follow_fresh_sources(self):
    old=self.cache(self.parse());self.current_year=2027;self.history_year=2023
    self.calls.clear();update=self.parse(old)
    self.assertEqual(3,len(self.calls))
    self.assertNotIn('2023',update['incremental_state']['units'])
    self.assertEqual(self.parse()['entries'],update['entries'])

  def test_current_winner_change_retains_original_supplement_results(self):
    old=self.cache(self.parse());self.winner=1
    update=self.parse(old)
    current=[r for r in update['entries'] if r['award_year']=='2026']
    self.assertEqual({'Tale 2026 1':'winner','Tale 2026 0':'shortlisted'},
      {r['title']:r['result'] for r in current})
    self.assertEqual([r for r in self.parse()['entries'] if r['award_year']=='2026'],current)

  def test_changed_annual_link_refetches_its_closed_source(self):
    old=self.cache(self.parse())
    url='https://www.ala.org/yalsa/2025-morris-award-changed'
    self.links[2025]=url
    self.overrides[url]='<h2>2025 Winner</h2><p>"Changed Title" by Changed Writer</p><h2>2025 Finalists</h2><p>"Another Title" by Another Writer</p>'
    self.calls.clear();update=self.parse(old)
    self.assertIn(url,self.calls)
    self.assertEqual(self.parse()['entries'],update['entries'])

  def test_failed_wrong_year_or_challenged_supplement_retains_prior_unit(self):
    full=self.parse();old=self.cache(full);url=yma_awards_url(2026)
    for failure in (RuntimeError('offline'),'<html>Challenge</html>',
        '<h1>American Library Association announces 2025 Youth Media Award winners</h1>'+self.annual(2025)):
      self.failures.clear();self.overrides.clear()
      if isinstance(failure,Exception):self.failures[url]=failure
      else:self.overrides[url]=failure
      update=self.parse(old)
      self.assertEqual(full['entries'],update['entries'])
      self.assertFalse(update['incremental_state']['units']['2026']['complete'])
    self.overrides.clear()
    self.assertTrue(self.parse(self.cache(update))['incremental_state']['units']['2026']['complete'])

  def test_failed_current_page_preserves_prior_rows_and_annual_discovery(self):
    full=self.parse();url=self.recipe.parser().CURRENT_URL
    self.failures[url]=RuntimeError('offline')
    update=self.parse(self.cache(full))
    self.assertEqual(full['entries'],update['entries'])
    self.assertFalse(update['incremental_state']['units']['current']['complete'])

  def test_failed_full_supplement_preserves_partial_import_and_notes(self):
    self.failures[yma_awards_url(2025)]=RuntimeError('offline')
    full=self.parse()
    self.assertEqual(8,len(full['entries']))
    self.assertFalse(full['incremental_state']['units']['2025']['complete'])
    self.assertTrue(any('offline' in n for n in full['notes']))

  def test_winnerless_historical_supplement_stays_fresh(self):
    self.overrides[yma_awards_url(2025)]='<h2>William C. Morris Award</h2><h3>William C. Morris Award Finalists</h3><p>"Pending Tale" by Pending Writer</p><h2>Schneider Family Book Award</h2>'
    old=self.cache(self.parse())
    self.assertTrue(old['incremental_state']['units']['2025']['complete'])
    self.calls.clear();self.parse(old)
    self.assertIn(yma_awards_url(2025),self.calls)

  def test_legacy_wrong_scope_and_complete_refresh_fetch_all_supplements(self):
    old=self.cache(self.parse())
    legacy=copy.deepcopy(old);legacy.pop('incremental_state')
    wrong=copy.deepcopy(old);wrong['incremental_state']['source_key']='other'
    for candidate,incremental in ((legacy,True),(wrong,True),(old,False)):
      self.calls.clear();self.parse(candidate,incremental)
      self.assertEqual(6,len(self.calls))

  def test_cancellation_and_browser_requirements_propagate_for_each_parser(self):
    for cls in RECIPES:
      self.recipe=cls()
      for target in (self.recipe.parser().CURRENT_URL,yma_awards_url(2026)):
        for error in (ImportCancelledError,CamoufoxRequiredError):
          self.failures={target:error('stop')}
          with self.assertRaises(error):self.parse()
      self.failures.clear()

  def test_migrated_story_heading_proves_award_year_independently_of_route(self):
    for parser,label in ((MorrisAwardParser(),'William C. Morris'),(YALSANonfictionAwardParser(),'Excellence in Nonfiction')):
      html=f'<h1>Book wins 2024 {label} Award</h1><p>"A Tale" has been named the 2024 winner of the {label} Award, written by A Writer.</p>'
      year=parser.annual_page_year(html,'https://www.ala.org/news/2011/11/migrated',parser.text_lines(html))
      self.assertEqual(2024,year)
      other=html.replace('wins 2024','wins 2023')
      self.assertEqual(2023,parser.annual_page_year(other,'https://www.ala.org/news/2011/11/migrated',parser.text_lines(other)))

  def test_current_year_mismatch_does_not_relabel_supplement(self):
    url='https://www.ala.org/yalsa/migrated-2025-morris'
    self.links[2024]=url
    self.overrides[url]='<h2>2025 Winner</h2><p>"Other Tale" by Other Writer</p>'
    full=self.parse()
    self.assertFalse(full['incremental_state']['units']['2024']['complete'])
    self.assertNotIn('Other Tale',[r['title'] for r in full['entries']])

  def test_cache_covers_all_entries_and_stores_no_raw_pages(self):
    full=self.parse();old=self.cache(full)
    used={i for u in old['incremental_state']['units'].values() for i in u['entry_indexes']}
    self.assertEqual(set(range(len(old['entries']))),used)
    self.assertNotIn('<h2>',json.dumps(old))
    self.assertEqual(full['notes'],self.parse(old)['notes'])
