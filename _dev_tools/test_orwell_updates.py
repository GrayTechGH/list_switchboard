import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError, ImportCancelledError
from storage import build_import_cache_data
from url_fetcher.orwell import UrlFetcherOrwellPrizePoliticalWriting, ORWELL_OFFICIAL_EXTRA_URLS


class OrwellUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe, self.calls, self.failures = UrlFetcherOrwellPrizePoliticalWriting(),[],{}
    self.years=[2026,2025,2024]
    self.clock=patch('parser.orwell.datetime')
    self.dates=self.clock.start()
    self.dates.datetime.now.return_value.year=2026
    self.addCleanup(self.clock.stop)

  def book(self,year):
    return f'https://www.orwellfoundation.com/political-writing/winner-{year}/'

  def fetch(self,url):
    self.calls.append(url)
    if url in self.failures:
      raise self.failures[url]
    if url==self.recipe.URL:
      return '<div><h3 class="award-title">Political Writing Book prize (2019-present)</h3>' + ''.join(
        f'<div class="owl-item"><h3><a href="{self.book(year)}">{year}</a></h3></div>' for year in self.years) + \
        '</div><div><h3 class="award-title">Political Fiction Book prize</h3><div class="owl-item"><h3><a href="/fiction">2026</a></h3></div></div>'
    if url==ORWELL_OFFICIAL_EXTRA_URLS[0]:
      return '<header class="article-header"><h1>Finalists announced</h1></header><div class="large-8 columns">'\
        '<h2>Friday 15 May 2026</h2><h2>The Orwell Prize for Political Writing</h2><p>'\
        f'<a href="{self.book(2026)}"><strong>Winner 2026</strong></a> | Writer 2026, <em>Publisher</em><br/>'\
        '<a href="/political-writing/other"><strong>Other 2026</strong></a> | Writer One &amp; Writer Two, <em>Publisher</em></p>'\
        '<blockquote><p>Not a Book, Not a Writer in 2023</p></blockquote><h2>The Orwell Prize for Political Fiction</h2>'\
        '<p><a href="/fiction">Excluded</a> | Wrong Writer</p></div>'
    if url==ORWELL_OFFICIAL_EXTRA_URLS[1]:
      return '<header class="article-header"><h1>2025 Finalists</h1></header><div class="large-8 columns">'\
        '<h2>12 May 2025</h2><p><strong>The Orwell Prize for Political Writing</strong></p><blockquote>Wrong year 2023</blockquote>'\
        '<ul><li><em>Winner 2025</em> – Writer 2025 (Publisher)</li><li><em>Other 2025</em> – Writer Other (Publisher)</li></ul>'\
        '<p><strong>The Orwell Prize for Political Fiction</strong></p><ul><li><em>Excluded</em> – Wrong Writer</li></ul></div>'
    if url==ORWELL_OFFICIAL_EXTRA_URLS[2]:
      return '<header class="article-header"><h1>Winners 2025</h1></header><div class="large-8 columns"><h2>26 June 2025</h2>'\
        '<h2>The Orwell Prize for Political Writing</h2><h3>Writer 2025 – <em>Winner 2025</em> (Publisher)</h3>'\
        '<blockquote><p>A quote about 2023, without another book entry</p></blockquote></div>'
    year=next(year for year in self.years if self.book(year)==url)
    return f'<h1 class="prize-title">{year} Political Writing Book prize winner</h1>'\
      f'<h3>Political Writing book prize winner</h3><div id="mainItemDesc"><h2>Winner {year}</h2>'\
      f'<p class="author">Writer {year}</p><p class="publishedBy">Published by: Publisher</p>'\
      '<p>Blurb with books, authors, and dates never parsed as extra works.</p></div>'

  def parse(self,old=None):
    return self.recipe.fetch_and_parse(self.fetch,source_choice=0,
      cached_parsed=old,incremental_update=old is not None)

  def cache(self,parsed):
    return build_import_cache_data(self.recipe.source_id,parsed)

  def test_missing_current_finalists_recovered_repeat_and_category_boundaries(self):
    full=self.parse()
    self.assertEqual(7,len(self.calls))
    self.assertEqual(5,len(full['entries']))
    old=without_unit(self.cache(full),ORWELL_OFFICIAL_EXTRA_URLS[0])
    self.assertLess(len(old['entries']),len(full['entries']))
    self.calls.clear()
    update=self.parse(old)
    self.assertEqual(full['entries'],update['entries'])
    self.assertEqual([self.recipe.URL,ORWELL_OFFICIAL_EXTRA_URLS[0],self.book(2026)],self.calls)
    self.calls.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])
    self.assertEqual(3,len(self.calls))
    other=next(e for e in update['entries'] if e['title']=='Other 2026')
    self.assertEqual(['Writer One','Writer Two'],other['authors'])
    self.assertTrue(all(len(e['title'])<30 and e['award_year']!='2023' for e in update['entries']))

  def test_new_discovered_winner_and_year_boundary_are_fetched(self):
    old=self.cache(self.parse())
    self.years.insert(0,2027)
    self.dates.datetime.now.return_value.year=2027
    self.calls.clear()
    update=self.parse(old)
    self.assertIn(self.book(2027),self.calls)
    self.assertNotIn(self.book(2024),self.calls)
    self.assertEqual(self.parse()['entries'],update['entries'])

  def test_failed_historical_detail_retains_pending_history_and_recovers(self):
    full=self.parse()
    old=self.cache(full)
    old['incremental_state']['units'][self.book(2024)]['complete']=False
    self.failures[self.book(2024)]=OSError('offline')
    pending=self.parse(old)
    self.assertEqual(full['entries'],pending['entries'])
    self.assertFalse(pending['incremental_state']['units'][self.book(2024)]['complete'])
    self.assertTrue(pending['notes'])
    self.failures.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(pending))['entries'])

  def test_legacy_wrong_scope_bad_projection_and_cancellation(self):
    full=self.parse()
    wrong=self.cache(full)
    wrong['incremental_state']['source_key']='another category'
    bad=self.cache(full)
    bad['incremental_state']['units'][self.book(2024)]['metadata']={}
    for old in ({'entries':full['entries']},wrong,bad):
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(old)['entries'])
      self.assertIn(self.book(2024),self.calls)
    for error in (ImportCancelledError('stop'),CamoufoxRequiredError('required')):
      self.failures[ORWELL_OFFICIAL_EXTRA_URLS[0]]=error
      with self.assertRaises(type(error)):
        self.parse(self.cache(full))
    primary,alternate=self.recipe.source_attempts()
    self.assertTrue(primary.supports_incremental)
    self.assertFalse(alternate.supports_incremental)


if __name__=='__main__':
  unittest.main()
