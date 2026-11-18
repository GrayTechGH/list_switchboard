import unittest

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError, ImportCancelledError
from storage import build_import_cache_data
from url_fetcher.national_book_award import (UrlFetcherNationalBookAwardFiction,
  UrlFetcherNationalBookAwardNonfiction, UrlFetcherNationalBookAwardYoungPeoplesLiterature)
from url_fetcher.baillie_gifford import UrlFetcherBaillieGiffordPrize
from url_fetcher.generic import UrlFetcherError


class OfficialAnnualUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe = UrlFetcherNationalBookAwardFiction()
    self.years, self.calls, self.failures = [2022, 2023, 2024], [], {}
    self.open_years, self.empty_years = set(), set()

  def url(self, year):
    if isinstance(self.recipe, UrlFetcherBaillieGiffordPrize):
      return f'{self.recipe.URL}/{year}'
    return f'https://www.nationalbook.org/awards-prizes/national-book-awards-{year}/'

  def unit(self, year):
    if isinstance(self.recipe, UrlFetcherBaillieGiffordPrize):
      return self.url(year)
    return self.recipe.category_url(self.url(year))

  def fetch(self, url):
    self.calls.append(url)
    if url in self.failures:
      raise self.failures[url]
    if url == self.recipe.URL:
      return ''.join(f'<a href="{self.url(y)}">{y}</a>' for y in self.years)
    if '/books-and-authors/' in url:
      year = url.rsplit('/',1)[-1]
      return f'<header><h1>Detail {year}</h1><p class="author">Writer One</p></header>'
    year = next(y for y in self.years if self.unit(y) == url)
    if isinstance(self.recipe, UrlFetcherBaillieGiffordPrize):
      stage = 'The shortlist' if year in self.open_years else 'The winner'
      return f'<section><h2>{stage}</h2><a href="/books-and-authors/{year}">'\
        f'<span class="listing__title">Fallback {year}</span><span class="listing__sub">Writer One</span></a></section>'
    if year in self.empty_years:
      return f'<title>National Book Awards {year} - National Book Foundation</title><div class="finalists-wrapper"></div>'
    tag, item = ('finalists-wrapper','winner-list') if year in self.open_years else ('winner-book','winner-book-item')
    return f'<div class="{tag}"><figure class="{item}"><a class="img" href="/books/{year}"></a>'\
      f'<h1><a href="/books/{year}">Book {year}</a></h1>'\
      '<h2><div>Writer One</div></h2></figure></div>'

  def parse(self, old=None):
    return self.recipe.fetch_and_parse(self.fetch, source_choice=0,
      cached_parsed=old, incremental_update=old is not None)

  def cache(self, parsed):
    return build_import_cache_data(self.recipe.source_id, parsed)

  def test_all_three_national_categories_missing_history_repeat_and_new_year(self):
    for cls in (UrlFetcherNationalBookAwardFiction,UrlFetcherNationalBookAwardNonfiction,
        UrlFetcherNationalBookAwardYoungPeoplesLiterature):
      with self.subTest(recipe=cls.source_id):
        self.recipe, self.years, self.calls = cls(), [2022,2023,2024], []
        full = self.parse()
        self.assertEqual(4,len(self.calls))
        old = without_unit(self.cache(full),self.unit(2022))
        self.calls.clear()
        update = self.parse(old)
        self.assertEqual(full['entries'],update['entries'])
        self.assertEqual([self.recipe.URL,self.unit(2022),self.unit(2024)],self.calls)
        self.years.append(2025)
        self.calls.clear()
        update = self.parse(self.cache(update))
        self.assertEqual([self.recipe.URL,self.unit(2025)],self.calls)
        self.assertEqual(self.parse()['entries'],update['entries'])
        primary,alternate = self.recipe.source_attempts()
        self.assertTrue(primary.supports_incremental)
        self.assertFalse(alternate.supports_incremental)

  def test_winnerless_ballot_and_verified_empty_category(self):
    self.open_years.add(2023)
    self.empty_years.add(2022)
    old = self.cache(self.parse())
    self.open_years.clear()
    self.calls.clear()
    update = self.parse(old)
    self.assertEqual([self.recipe.URL,self.unit(2023),self.unit(2024)],self.calls)
    self.assertEqual('winner',update['entries'][0]['result'])
    self.assertTrue(update['incremental_state']['units'][self.unit(2022)]['complete'])

  def test_full_failure_reaches_replacement_but_update_retains_pending_history(self):
    full = self.parse()
    old = self.cache(full)
    old['incremental_state']['units'][self.unit(2022)]['complete'] = False
    self.failures[self.unit(2022)] = OSError('offline')
    update = self.parse(old)
    self.assertEqual(full['entries'],update['entries'])
    self.assertFalse(update['incremental_state']['units'][self.unit(2022)]['complete'])
    with self.assertRaises(UrlFetcherError):
      self.parse()
    self.failures.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])

  def test_legacy_changed_scope_and_cancellation(self):
    full = self.parse()
    wrong = self.cache(full)
    wrong['incremental_state']['source_key'] = 'another category'
    for old in ({'entries':full['entries']},wrong):
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(old)['entries'])
      self.assertEqual(4,len(self.calls))
    for error in (ImportCancelledError('stop'),CamoufoxRequiredError('required')):
      self.failures[self.unit(2022)] = error
      with self.assertRaises(type(error)):
        self.parse()

  def test_baillie_reuses_year_with_details_and_retries_failed_detail_snapshot(self):
    self.recipe = UrlFetcherBaillieGiffordPrize()
    full = self.parse()
    self.assertEqual(7,len(self.calls))
    old = without_unit(self.cache(full),self.unit(2022))
    self.calls.clear()
    update = self.parse(old)
    self.assertEqual(full['entries'],update['entries'])
    self.assertEqual(5,len(self.calls))
    self.assertNotIn(self.unit(2023),self.calls)
    old = self.cache(update)
    old['incremental_state']['units'][self.unit(2022)]['complete'] = False
    detail = 'https://www.thebailliegiffordprize.co.uk/books-and-authors/2022'
    self.failures[detail] = OSError('offline')
    pending = self.parse(old)
    self.assertEqual(full['entries'],pending['entries'])
    self.assertFalse(pending['incremental_state']['units'][self.unit(2022)]['complete'])
    self.failures.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(pending))['entries'])
    for error in (ImportCancelledError('stop'),CamoufoxRequiredError('required')):
      self.failures[detail] = error
      with self.assertRaises(type(error)):
        self.parse()

  def test_national_real_card_boundaries_keep_finalists_and_exclude_longlist(self):
    from parser.national_book_award import NationalBookAwardParser
    html = '<div class="winner-book"><div class="winner-book-item"><a class="img" href="/books/winner"></a>'\
      '<div class="book-data"><h1><a href="/books/winner">Winner Title</a></h1><h2>Winner Writer</h2></div></div></div>'\
      '<div class="finalists-wrapper"><figure class="winner-list"><a class="img" href="/books/nominee"></a>'\
      '<h1><a href="/books/nominee">Nominee Title</a></h1><h2><div>Nominee Writer</div></h2></figure></div>'\
      '<div class="longlist-wrapper"><figure class="winner-list"><h1><a href="/books/longlist">Excluded</a></h1><h2>Other Writer</h2></figure></div>'
    result = NationalBookAwardParser().parse(html,self.unit(2024),'NBA','Fiction')
    self.assertEqual(['Winner Title','Nominee Title'],[e['title'] for e in result['entries']])
    self.assertEqual([['Winner Writer'],['Nominee Writer']],[e['authors'] for e in result['entries']])
    self.assertEqual(['winner','nominee'],[e['result'] for e in result['entries']])

  def test_national_gateway_retries_are_bounded_scoped_and_never_swallow_cancellation(self):
    from urllib.error import HTTPError,URLError
    from unittest.mock import Mock
    url=self.unit(2024)
    fetch=Mock(side_effect=[HTTPError(url,502,'Bad Gateway',None,None),
      URLError('[SSL: UNEXPECTED_EOF_WHILE_READING] EOF'), 'page'])
    self.assertEqual('page',self.recipe.fetch_url(fetch,url))
    self.assertEqual(3,fetch.call_count)
    for error in (HTTPError(url,403,'Forbidden',None,None),
        URLError('CERTIFICATE_VERIFY_FAILED'),ImportCancelledError('stop'),CamoufoxRequiredError('required')):
      fetch=Mock(side_effect=error)
      with self.assertRaises(type(error)):
        self.recipe.fetch_url(fetch,url)
      self.assertEqual(1,fetch.call_count)
    error=HTTPError(url,502,'Bad Gateway',None,None)
    fetch=Mock(side_effect=error)
    with self.assertRaises(HTTPError):
      self.recipe.fetch_url(fetch,url)
    self.assertEqual(3,fetch.call_count)
    fetch=Mock(side_effect=error)
    with self.assertRaises(HTTPError):
      self.recipe.fetch_url(fetch,'https://en.wikipedia.org/wiki/Award')
    self.assertEqual(1,fetch.call_count)


if __name__ == '__main__':
  unittest.main()
