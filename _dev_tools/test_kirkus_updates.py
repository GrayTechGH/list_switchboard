import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError, ImportCancelledError
from storage import build_import_cache_data
from url_fetcher.kirkus import (UrlFetcherKirkusPrizeFiction,
  UrlFetcherKirkusPrizeNonfiction,UrlFetcherKirkusPrizeYoungReadersLiterature)


class KirkusUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe,self.calls,self.failures=UrlFetcherKirkusPrizeFiction(),[],{}
    self.years=[2026,2025,2024]
    self.first=patch('url_fetcher.kirkus.KIRKUS_FIRST_YEAR',2024)
    self.first.start()
    self.addCleanup(self.first.stop)
    self.clock=patch('parser.annual_updates.datetime')
    self.dates=self.clock.start()
    self.dates.datetime.now.return_value.year=2026
    self.addCleanup(self.clock.stop)

  def card(self,category,year,winner=False):
    title=f'{category} {"Winner" if winner else "Other"} {year}'
    return f'<li><p class="book-title"><a href="/book-reviews/{title.replace(" ","-")}/">{title}</a></p><p>By Writer {category}</p></li>'

  def page(self,year):
    winners=[]
    finalists=[]
    for category in ('Fiction','Nonfiction',"Children's"):
      title=f'{category} Winner {year}'
      winners.append(f'<div class="prize-winner"><p class="prize-label">{category}</p><h2><a href="/books/{title.replace(" ","-")}">{title}</a></h2><p class="prize-label">BY Writer {category}</p></div>')
      label="Young Readers' Literature" if category=="Children's" else category
      finalists.append(f'<h2 class="prize-category">{label}</h2><ul>{self.card(category,year)}</ul>')
    return f'<h1>{year} Winners</h1><section class="prize-winners">'+''.join(winners)+ \
      f'</section><section class="prize-finalists"><h1>{year} Finalists</h1>'+''.join(finalists)+'</section>'

  def fetch(self,url):
    self.calls.append(url)
    if url in self.failures:
      raise self.failures[url]
    if url==self.recipe.URL:
      return ''.join(f'<a href="/prize/{year}/">{year}</a>' for year in self.years)
    return self.page(int(url.rstrip('/').rsplit('/',1)[-1]))

  def parse(self,old=None):
    return self.recipe.fetch_and_parse(self.fetch,cached_parsed=old,incremental_update=old is not None)

  def cache(self,parsed):
    return build_import_cache_data(self.recipe.source_id,parsed)

  def test_three_categories_keep_winners_and_exclude_other_categories_during_updates(self):
    for cls in (UrlFetcherKirkusPrizeFiction,UrlFetcherKirkusPrizeNonfiction,UrlFetcherKirkusPrizeYoungReadersLiterature):
      with self.subTest(recipe=cls.source_id):
        self.recipe,self.calls=cls(),[]
        full=self.parse()
        self.assertEqual(4,len(self.calls))
        self.assertEqual(6,len(full['entries']))
        self.assertEqual(3,sum(e['result']=='winner' for e in full['entries']))
        category="Children's" if cls is UrlFetcherKirkusPrizeYoungReadersLiterature else self.recipe.CATEGORY
        self.assertTrue(all(e['title'].startswith(category+' ') for e in full['entries']))
        old=without_unit(self.cache(full),self.recipe.year_url(2026))
        self.calls.clear()
        update=self.parse(old)
        self.assertEqual(full['entries'],update['entries'])
        self.assertEqual([self.recipe.URL,self.recipe.year_url(2026)],self.calls)
        self.calls.clear()
        self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])
        self.assertEqual(2,len(self.calls))

  def test_new_year_uses_fresh_structural_discovery_and_keeps_closed_history(self):
    full=self.parse()
    self.years.insert(0,2027)
    self.dates.datetime.now.return_value.year=2027
    self.calls.clear()
    update=self.parse(self.cache(full))
    self.assertEqual([self.recipe.URL,self.recipe.year_url(2027)],self.calls)
    self.assertEqual(self.parse()['entries'],update['entries'])
    html='<script>var example="/prize/2099/";</script><a href="/prize/2026/">Current</a>'
    self.assertEqual(2026,self.recipe.latest_year_from_landing(html))

  def test_wrong_year_and_failed_year_retain_pending_history_with_notes(self):
    full=self.parse()
    old=self.cache(full)
    url=self.recipe.year_url(2024)
    old['incremental_state']['units'][url]['complete']=False
    self.failures[url]=OSError('offline')
    update=self.parse(old)
    self.assertEqual(full['entries'],update['entries'])
    self.assertFalse(update['incremental_state']['units'][url]['complete'])
    self.assertTrue(update['notes'][0].startswith('Official Kirkus page failed for'))
    self.failures.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])
    with self.assertRaises(ValueError):
      self.recipe.parser().parse(self.page(2025),url,self.recipe.NAME,self.recipe.CATEGORY,self.recipe.CATEGORY_ALIASES)

  def test_legacy_wrong_scope_and_cancellation_rebuild_or_propagate(self):
    full=self.parse()
    wrong=self.cache(full)
    wrong['incremental_state']['source_key']='different category'
    for old in ({'entries':full['entries']},wrong):
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(old)['entries'])
      self.assertEqual(4,len(self.calls))
    for target in (self.recipe.URL,self.recipe.year_url(2026)):
      for error in (ImportCancelledError('stop'),CamoufoxRequiredError('required')):
        self.failures[target]=error
        with self.assertRaises(type(error)):
          self.parse(self.cache(full))
      self.failures.clear()

  def test_legacy_heading_boundaries_also_reset_when_another_category_begins(self):
    html='<h1>2024 Finalists</h1><h2>Fiction</h2><p>Right Book by Right Writer</p>'\
      '<h2>Nonfiction</h2><p>Excluded Book by Wrong Writer</p>'
    parsed=self.recipe.parser().parse(html,self.recipe.year_url(2024),self.recipe.NAME,self.recipe.CATEGORY,self.recipe.CATEGORY_ALIASES)
    self.assertEqual(['Right Book'],[e['title'] for e in parsed['entries']])


if __name__=='__main__':
  unittest.main()
