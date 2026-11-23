import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError,ImportCancelledError
from storage import build_import_cache_data
from url_fetcher import victorian_premiers_literary_awards as vpla


RECIPES=(vpla.UrlFetcherVictorianPremiersLiteraryAwardsFiction,vpla.UrlFetcherVictorianPremiersLiteraryAwardsNonfiction,
  vpla.UrlFetcherVictorianPremiersLiteraryAwardsWritingForYoungAdults,vpla.UrlFetcherVictorianPremiersLiteraryAwardsChildrensLiterature,
  vpla.UrlFetcherVictorianPremiersLiteraryAwardsIndigenousWriting)


class VictorianUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=RECIPES[0]()
    self.years=[2024,2025,2026]
    self.calls,self.failures,self.pages=[],{},{}
    self.clock=patch('parser.annual_updates.datetime')
    self.dates=self.clock.start()
    self.dates.datetime.now.return_value.year=2026
    self.addCleanup(self.clock.stop)

  def url(self,year):
    return f'https://www.wheelercentre.com/victorian-premier-s-literary-awards/past-awards/{year}-victorian-premier-s-literary-awards'

  def card(self,heading,lines):
    return '<div class="content-wrapper"><h3 class="content-heading">'+heading+'</h3><div class="content-description"><p>'+'<br/>'.join(lines)+'</p></div><a href="/book/'+heading.replace(' ','-')+'">Learn More</a></div>'

  def page(self,year):
    winners=''.join(self.card(cls().CATEGORY,[f'{cls().CATEGORY} Winner {year}','Writer One','Publisher']) for cls in RECIPES)
    lists=''
    for cls in RECIPES:
      cat=cls().CATEGORY
      lists+=f'<h2>{cat}</h2>'+self.card(f'{cat} Winner {year}',['Writer One','Publisher'])+self.card(f'{cat} Other {year}',['Writer Two','Publisher'])
      lists+='<h2>Highly Commended</h2>'+self.card('Excluded Commendation',['Wrong Writer','Publisher'])
    return f'<title>{year} Victorian Awards</title><main><h1>{year} Victorian Premier Awards</h1><section class="component"><h2>WINNERS</h2>{winners}{lists}<h2>The Judges</h2><h4>Fiction</h4><p>Judge by Impostor Writer</p></section></main>'

  def fetch(self,url):
    self.calls.append(url)
    if url in self.failures:raise self.failures[url]
    if url==self.recipe.URL:
      return ''.join(f'<a href="{self.url(y)}">{y} Victorian Premier Literary Awards</a>' for y in self.years)
    year=int(url.rsplit('/',1)[-1].split('-',1)[0])
    return self.pages.get(year,self.page(year))

  def parse(self,old=None):
    return self.recipe.fetch_and_parse(self.fetch,cached_parsed=old,incremental_update=old is not None)

  def cache(self,parsed):
    return build_import_cache_data(self.recipe.source_id,parsed)

  def test_all_five_categories_missing_year_recovery_repeat_and_publisher_boundaries(self):
    for cls in RECIPES:
      self.recipe=cls()
      self.calls.clear()
      full=self.parse()
      self.assertEqual(6,len(full['entries']))
      self.assertEqual(3,sum(r['result']=='winner' for r in full['entries']))
      self.assertTrue(all(r['authors'] in (['Writer One'],['Writer Two']) for r in full['entries']))
      old=without_unit(self.cache(full),self.url(2026))
      self.calls.clear()
      update=self.parse(old)
      self.assertEqual(full['entries'],update['entries'])
      self.assertEqual([self.recipe.URL,self.url(2026)],self.calls)
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])
      self.assertEqual([self.recipe.URL,self.url(2026)],self.calls)

  def test_added_year_and_removed_history_follow_navigation(self):
    old=self.cache(self.parse())
    self.years=[2025,2026,2027]
    self.dates.datetime.now.return_value.year=2027
    self.calls.clear()
    update=self.parse(old)
    self.assertEqual([self.recipe.URL,self.url(2027)],self.calls)
    self.assertEqual(self.parse()['entries'],update['entries'])

  def test_failed_empty_and_wrong_year_sources_retain_pending_history_then_recover(self):
    full=self.parse()
    old=self.cache(full)
    old['incremental_state']['units'][self.url(2025)]['complete']=False
    for mode in ('offline','empty','wrong-year'):
      self.failures.clear();self.pages.clear()
      if mode=='offline':self.failures[self.url(2025)]=OSError('offline')
      elif mode=='empty':self.pages[2025]='<h1>Access denied</h1>'
      else:self.pages[2025]=self.page(2020)
      pending=self.parse(old)
      self.assertEqual(full['entries'],pending['entries'])
      self.assertFalse(pending['incremental_state']['units'][self.url(2025)]['complete'])
      self.assertTrue(pending['notes'])
    self.pages.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(pending))['entries'])

  def test_verified_absent_category_is_reused_and_present_unparsed_section_is_pending(self):
    self.pages[2024]='<main><h1>2024 Victorian Premier Awards</h1><section class="component"><h2>Winners</h2><h3>Poetry</h3><p>Poem by Poet</p></section></main>'
    full=self.parse()
    self.assertFalse(full['incremental_state']['units'][self.url(2024)]['complete'])
    self.pages[2024]='<main><h1>2024 Victorian Premier Awards</h1><section class="component"><h2>Winners</h2><p><strong>Prize for Non-fiction</strong><br/>Other by Other Writer</p></section></main>'
    full=self.parse()
    self.assertTrue(full['incremental_state']['units'][self.url(2024)]['complete'])
    self.calls.clear()
    self.parse(self.cache(full))
    self.assertNotIn(self.url(2024),self.calls)
    self.pages[2024]='<main><h1>2024 Victorian Premier Awards</h1><section class="component"><h2>Fiction</h2></section></main>'
    parsed=self.parse()
    self.assertFalse(parsed['incremental_state']['units'][self.url(2024)]['complete'])

  def test_legacy_inline_winners_shortlists_young_adult_alias_and_judge_exclusion(self):
    parser=self.recipe.create_parser()
    page='<main><h1>2011 Victorian Awards</h1><section class="component"><h2>Winners of the 2011 Victorian Premier Awards</h2><p><strong>Prize for Fiction</strong><br/><em>That Deadman Dance</em> by Kim Scott</p><h2>The Shortlist</h2><h4>FICTION</h4><p>Five Bells by Gail Jones</p><p>That Deadman Dance by Kim Scott</p><h4>YOUNG ADULTS</h4><p>Teenage Book by Young Writer</p><h2>Highly Commended</h2><h4>FICTION</h4><p>Wrong Book by Other Writer</p><h2>The Judges</h2><h4>FICTION</h4><p>Judge by Impostor Writer</p></section></main>'
    rows=parser.dedupe_rows(parser.page_rows(page,self.url(2011)))
    self.assertEqual([('That Deadman Dance','Kim Scott','winner'),('Five Bells','Gail Jones','shortlisted')],[(r['title'],r['author'],r['result']) for r in rows])
    young=vpla.UrlFetcherVictorianPremiersLiteraryAwardsWritingForYoungAdults().create_parser()
    self.assertEqual(['Teenage Book'],[r['title'] for r in young.page_rows(page,self.url(2011))])

  def test_legacy_configuration_and_critical_failures(self):
    full=self.parse()
    wrong=self.cache(full)
    wrong['incremental_state']['source_key']='other category'
    for old in ({'entries':full['entries']},wrong,['invalid cache']):
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(old)['entries'])
      self.assertEqual(4,len(self.calls))
    for error in (ImportCancelledError('stop'),CamoufoxRequiredError('required')):
      self.failures[self.url(2026)]=error
      with self.assertRaises(type(error)):self.parse(self.cache(full))


if __name__=='__main__':
  unittest.main()
