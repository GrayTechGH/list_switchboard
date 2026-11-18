import unittest

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError,ImportCancelledError
from storage import build_import_cache_data
from url_fetcher import national_book_critics_circle as nbcc


RECIPES=(nbcc.UrlFetcherNationalBookCriticsCircleFiction,nbcc.UrlFetcherNationalBookCriticsCircleNonfiction,
  nbcc.UrlFetcherNationalBookCriticsCircleBiography,nbcc.UrlFetcherNationalBookCriticsCircleMemoirAutobiography,
  nbcc.UrlFetcherNationalBookCriticsCirclePoetry,nbcc.UrlFetcherNationalBookCriticsCircleCriticism,
  nbcc.UrlFetcherNationalBookCriticsCircleJohnLeonard,nbcc.UrlFetcherNationalBookCriticsCircleGreggBarriosTranslation)


class NBCCUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=RECIPES[0]()
    self.index_years=[2022,2023,2024]
    self.latest=2025
    self.calls,self.failures,self.pages=[],{},{}
    self.winnerless=set()

  def url(self,year):
    return f'https://www.bookcritics.org/past-awards/{year}/'

  def page(self,year):
    groups=[]
    for cls in RECIPES:
      recipe=cls()
      stage='Finalist' if year in self.winnerless else 'Winner'
      groups.append(f'<ul class="award-year-list"><h3>{recipe.CATEGORY}</h3><li class="{stage}">Writer One, <em>{recipe.CATEGORY} Winner {year}</em> (Publisher)</li><li class="Finalist">Writer Two, <em>{recipe.CATEGORY} Other {year}</em> (Publisher)</li><li class="Longlist">Writer Three, <em>Excluded</em> (Publisher)</li></ul>')
    next_link=f'<nav class="post-navigation"><a rel="next" href="{self.url(year+1)}">Next</a></nav>' if year<self.latest else ''
    return f'<div class="award-finalists-inner"><h2 class="entry-title">{year} Winners &amp; Finalists with Longlisted Books</h2><div class="award-year-list-wrapper">'+''.join(groups)+'</div></div>'+next_link

  def fetch(self,url):
    self.calls.append(url)
    if url in self.failures: raise self.failures[url]
    if url==self.recipe.URL:
      return '<select id="award-year-select">'+''.join(f'<option value="{self.url(y)}">{y}</option>' for y in self.index_years)+'</select>'
    year=int(url.strip('/').rsplit('/',1)[-1])
    return self.pages.get(year,self.page(year))

  def parse(self,old=None):
    return self.recipe.fetch_and_parse(self.fetch,source_choice=0,cached_parsed=old,incremental_update=old is not None)

  def cache(self,parsed):
    return build_import_cache_data(self.recipe.source_id,parsed)

  def test_all_eight_categories_missing_ballot_recovery_and_repeat(self):
    for cls in RECIPES:
      self.recipe=cls()
      self.calls.clear()
      full=self.parse()
      self.assertEqual(8,len(full['entries']))
      self.assertTrue(all(r['category']==self.recipe.CATEGORY for r in full['entries']))
      self.assertEqual(5,len(self.calls))
      old=without_unit(self.cache(full),self.url(2022))
      self.calls.clear()
      update=self.parse(old)
      self.assertEqual(full['entries'],update['entries'])
      self.assertEqual([self.recipe.URL,self.url(2024),self.url(2025),self.url(2022)],self.calls)
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])
      self.assertEqual([self.recipe.URL,self.url(2024),self.url(2025)],self.calls)

  def test_lagging_selector_new_year_chain_and_advanced_selector(self):
    old=self.cache(self.parse())
    self.latest=2026
    self.calls.clear()
    update=self.parse(old)
    self.assertEqual([self.recipe.URL,self.url(2024),self.url(2025),self.url(2026)],self.calls)
    self.assertEqual(self.parse()['entries'],update['entries'])
    self.index_years.append(2025)
    self.calls.clear()
    self.assertEqual(update['entries'],self.parse(self.cache(update))['entries'])
    self.assertEqual([self.recipe.URL,self.url(2025),self.url(2026)],self.calls)

  def test_failed_discovery_retains_known_tail_and_recovers(self):
    full=self.parse()
    self.failures[self.url(2024)]=OSError('offline')
    pending=self.parse(self.cache(full))
    self.assertEqual(full['entries'],pending['entries'])
    self.assertFalse(pending['incremental_state']['units'][self.url(2024)]['complete'])
    self.failures.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(pending))['entries'])

  def test_unsettled_history_and_failed_empty_wrong_year_units_are_refreshed(self):
    self.winnerless.add(2022)
    full=self.parse()
    self.calls.clear()
    self.parse(self.cache(full))
    self.assertIn(self.url(2022),self.calls)
    self.winnerless.clear()
    full=self.parse()
    old=self.cache(full)
    old['incremental_state']['units'][self.url(2023)]['complete']=False
    for page in ('<h1>Access denied</h1>',self.page(2023).replace('2023 Winners','2020 Winners')):
      self.pages[2023]=page
      pending=self.parse(old)
      self.assertEqual(full['entries'],pending['entries'])
      self.assertFalse(pending['incremental_state']['units'][self.url(2023)]['complete'])
    self.pages.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(pending))['entries'])

  def test_verified_absent_historical_category_can_be_reused(self):
    self.pages[2022]=self.page(2022).replace('<h3>Fiction</h3>','<h3>Retired Other Category</h3>')
    full=self.parse()
    self.assertTrue(full['incremental_state']['units'][self.url(2022)]['complete'])
    self.calls.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(full))['entries'])
    self.assertNotIn(self.url(2022),self.calls)

  def test_legacy_heading_categories_and_inline_first_year_winner(self):
    parser=self.recipe.create_official_parser()
    page='<h1>1975 Awards</h1><h3>Winners</h3><ul><li>Fiction: E.L. Doctorow, <em>Ragtime</em></li><li>Poetry: Wrong Writer, <em>Excluded</em></li></ul>'
    rows=parser.parse_page_rows(page,self.url(1975))
    self.assertEqual([('Ragtime','E.L. Doctorow','winner')],[(r['title'],r['author'],r['result']) for r in rows])
    page='<h3>Fiction Winner</h3><p>Writer One, <em>Right Title</em> (Publisher)</p><h3>General Nonfiction Winner</h3><p>Wrong Writer, <em>Excluded</em> (Publisher)</p><h3>Poetry Finalists</h3><p>Other Writer, <em>Also Excluded</em></p>'
    rows=parser.parse_page_rows(page,self.url(2020))
    self.assertEqual(['Right Title'],[r['title'] for r in rows])

  def test_marked_titles_preserve_commas_suffixes_split_emphasis_and_drop_translators(self):
    parser=self.recipe.create_official_parser()
    from bs4 import BeautifulSoup
    for line,title,author in (
        ('Walter M. Miller, Jr., <em>Title, With Comma</em> (Publisher)','Title, With Comma','Walter M. Miller, Jr.'),
        ('Bruno Bettelheim, T<em>he Uses of Enchantment</em> (Publisher)','The Uses of Enchantment','Bruno Bettelheim'),
        ('William T. Vollmann, <em>Europe</em> Central (Publisher)','Europe Central','William T. Vollmann'),
        ('Neige Sinno, translated from the French by Natasha Lehrer, <em>Sad Tiger</em> (Publisher)','Sad Tiger','Neige Sinno'),
        ('Pedro Lemebel, translation by Gwendolyn Harper, <em>A Last Supper</em> (Publisher)','A Last Supper','Pedro Lemebel')):
      node=BeautifulSoup('<li>'+line+'</li>','html.parser').li
      actual=parser.parse_node_entry(node,self.url(2024))
      self.assertEqual((title,author),actual[:2])

  def test_legacy_wrong_scope_and_critical_failures(self):
    full=self.parse()
    wrong=self.cache(full)
    wrong['incremental_state']['source_key']='another category'
    for old in ({'entries':full['entries']},wrong,['invalid cache']):
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(old)['entries'])
      self.assertEqual(5,len(self.calls))
    for error in (ImportCancelledError('stop'),CamoufoxRequiredError('required')):
      for year in (2024,2022):
        self.failures[self.url(year)]=error
        old=self.cache(full)
        old['incremental_state']['units'][self.url(2022)]['complete']=False
        with self.assertRaises(type(error)): self.parse(old)
        self.failures.clear()

  def test_year_discovery_ignores_foreign_host_and_non_year_options(self):
    parser=self.recipe.create_official_parser()
    page='<select id="award-year-select"><option value="#">Select</option><option value="https://elsewhere.example/past-awards/2026/">Wrong</option><option value="/past-awards/2025/">Right</option></select>'
    self.assertEqual(((2025,self.url(2025)),),parser.year_links(page,self.recipe.URL))

  def test_old_unmarked_author_first_winners_and_person_name_do_not_confuse_category(self):
    page='<div class="award-finalists-inner"><h2 class="entry-title">2013 Winners &amp; Finalists</h2><div class="content-regular"><h3>Autobiography</h3><ul><li>Amy Wilentz, Farewell, Fred Voodoo (Publisher)</li></ul><h3>Autobiography/Memoir Finalists</h3><ul><li>Other Author, Another Title (Publisher)</li></ul><h3>John Leonard Prize</h3><ul><li>Anthony Marra, A Constellation of Vital Phenomena (Publisher)</li></ul><h3>Ivan Sandrof Winner</h3><ul><li>John Leonard</li></ul></div></div>'
    memoir=nbcc.UrlFetcherNationalBookCriticsCircleMemoirAutobiography().create_official_parser()
    rows=memoir.parse_page_rows(page,self.url(2013))
    self.assertEqual([('Farewell, Fred Voodoo','Amy Wilentz','winner'),('Another Title','Other Author','shortlisted')],[(r['title'],r['author'],r['result']) for r in rows])
    john=nbcc.UrlFetcherNationalBookCriticsCircleJohnLeonard().create_official_parser()
    rows=john.parse_page_rows(page,self.url(2013))
    self.assertEqual([('A Constellation of Vital Phenomena','Anthony Marra','winner')],[(r['title'],r['author'],r['result']) for r in rows])
    absent=page.replace('<h3>John Leonard Prize</h3>','<h3>Another Prize</h3>')
    self.assertTrue(john.valid_empty_year(absent,self.url(2013),2013))


if __name__=='__main__':
  unittest.main()
