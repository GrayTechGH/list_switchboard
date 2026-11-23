import unittest

from _dev_tools import test_import_matching
from errors import ImportCancelledError, CamoufoxRequiredError
from parser.national_book_award import NationalBookAwardParser
from parser.national_book_award_official import category_routes, read_year


BASE = 'https://www.nationalbook.org/awards-prizes/national-book-awards-1980/'


def card(title, author='Writer', result='winner'):
  if result == 'winner':
    return f'<div class="winner-book"><div class="winner-book-item"><div class="book-data"><h1><a href="https://www.nationalbook.org/books/book/">{title}</a></h1><h2>{author}</h2></div></div></div>'
  return f'<div class="finalists-wrapper"><figure class="winner-list"><h1><a href="https://www.nationalbook.org/books/book/">{title}</a></h1><h2>{author}</h2></figure></div>'


def link(label, query, active=False, child=False):
  classes = ('sub-category-winners' if child else 'category-winner') + (' is-active' if active else '')
  return f'<a class="{classes}" href="{BASE}?{query}">{label}</a>'


class NationalBookAwardOfficialTests(unittest.TestCase):

  def setUp(self):
    self.parser = NationalBookAwardParser()

  def test_current_replacement_sources_do_not_advertise_incremental_savings(self):
    from url_fetcher.national_book_award import (
      UrlFetcherNationalBookAwardFiction, UrlFetcherNationalBookAwardNonfiction,
      UrlFetcherNationalBookAwardYoungPeoplesLiterature,
    )
    for cls in (UrlFetcherNationalBookAwardFiction,UrlFetcherNationalBookAwardNonfiction,
        UrlFetcherNationalBookAwardYoungPeoplesLiterature):
      with self.subTest(recipe=cls.source_id):
        self.assertFalse(cls.SUPPORTS_INCREMENTAL_UPDATE)

  def test_hardcover_and_paperback_follow_advertised_routes_not_default_books(self):
    hardcover, paperback = BASE+'?cat=fiction-hc', BASE+'?cat=autobiography&sub-cat=fiction-pb'
    default = BASE+'?cat=fiction'
    nav = link('Autobiography - Hardcover', 'cat=autobiography', True) + link('Fiction - Hardcover', 'cat=fiction-hc') + link('Fiction - Paperback', 'cat=autobiography&sub-cat=fiction-pb', child=True)
    pages = {
      hardcover: link('Fiction - Hardcover', 'cat=fiction-hc', True) + card('Hardcover Winner'),
      paperback: nav + card('Paperback Winner') + card('Paperback Finalist', result='nominee'),
    }
    calls=[]
    def fetch(url):
      calls.append(url)
      return pages[url]
    parsed = read_year(self.parser, nav+card('Wrong Autobiography'), default, 'NBA', 'Fiction', fetch)
    self.assertEqual([hardcover,paperback], calls)
    self.assertEqual([('1980','Hardcover Winner'),('1980','Paperback Winner'),('1980.01','Paperback Finalist')],
      [(e['position'],e['title']) for e in parsed['entries']])

  def test_historical_nonfiction_subcategory_owns_its_label_under_fiction_parent(self):
    url=BASE+'?cat=fiction&sub-cat=history'
    nav=link('Fiction','cat=fiction',True)+link('HISTORY','cat=fiction&sub-cat=history',child=True)
    parsed=read_year(self.parser,nav+card('Wrong Fiction'),BASE+'?cat=nonfiction','NBA','Nonfiction',
      lambda target: nav+card('History Winner'))
    self.assertEqual([('History Winner','History')],[(e['title'],e['category']) for e in parsed['entries']])
    self.assertEqual('History Winner',self.parser.parse(nav+card('History Winner'),url,'NBA','HISTORY')['entries'][0]['title'])

  def test_split_format_fiction_with_childrens_winner_is_not_accepted(self):
    nav=link('Fiction - Hardcover','cat=fiction-hc',True)
    with self.assertRaisesRegex(ValueError,'mixes award categories'):
      read_year(self.parser,nav+card('Adult Winner')+card('Childrens Winner'),
        BASE+'?cat=fiction-hc','NBA','Fiction',lambda url:self.fail(url))

  def test_specific_nonfiction_dedupe_does_not_collapse_child_book_genres(self):
    nav=link('Nonfiction','cat=nonfiction',True)+link('HISTORY','cat=nonfiction&sub-cat=history',child=True)
    parsed=read_year(self.parser,nav+card('Shared Book'),BASE+'?cat=nonfiction','NBA','Nonfiction',lambda url:nav+card('Shared Book'))
    self.assertEqual(['History'],[e['category'] for e in parsed['entries']])
    nav=link("Children's Books - Fiction, Hardcover",'cat=child-fiction',True)+link("Children's Books - Nonfiction",'cat=child-fiction&sub-cat=child-nonfiction',child=True)
    parsed=read_year(self.parser,nav+card('Shared Book'),BASE+'?cat=child-fiction','NBA',"Young People's Literature",lambda url:nav+card('Shared Book'))
    self.assertEqual(['Fiction','Nonfiction'],[e['category'] for e in parsed['entries']])

  def test_young_people_alias_and_absent_year_do_not_import_default_fiction(self):
    nav=link('Fiction','cat=fiction',True)+link("Children's Books",'cat=childrens-books')
    page=link("Children's Books",'cat=childrens-books',True)+card('Child Winner')
    parsed=read_year(self.parser,nav+card('Wrong Fiction'),BASE+'?cat=ypl','NBA',"Young People's Literature",lambda url:page)
    self.assertEqual(["Children's Books"],[e['category'] for e in parsed['entries']])
    absent='<title>National Book Awards 1980</title>'+link('Fiction','cat=fiction',True)+'<div class="finalists-wrapper"></div>'
    self.assertEqual([],read_year(self.parser,absent,BASE+'?cat=ypl','NBA',"Young People's Literature",lambda url:self.fail(url))['entries'])

  def test_empty_advertised_category_cannot_certify_a_complete_year(self):
    nav=link('Fiction','cat=fiction',True)+link("Children's Books - Picture Books - Paperback",'cat=fiction&sub-cat=childrens-picture-pb',child=True)
    with self.assertRaisesRegex(ValueError,'no usable roster'):
      read_year(self.parser,nav,BASE+'?cat=ypl','NBA',"Young People's Literature",lambda url:nav)

  def test_route_validation_rejects_foreign_host_year_or_query(self):
    for href in ('https://example.com/?cat=fiction',BASE.replace('1980','1981')+'?cat=fiction',BASE+'?cat=fiction&unexpected=1'):
      with self.subTest(href=href),self.assertRaisesRegex(ValueError,'Foundation category link'):
        category_routes(self.parser,self.parser.html_root(f'<a class="category-winner" href="{href}">Fiction</a>'),BASE,'Fiction')

  def test_direct_and_subcategory_alias_of_same_slug_is_fetched_once(self):
    nav=link('Fiction - Paperback','cat=fiction-pb')+link('FICTION - PAPERBACK','cat=other&sub-cat=fiction-pb',child=True)+link('Science Fiction','cat=science-fiction')+link('First Novel','cat=first-novel')
    routes=category_routes(self.parser,self.parser.html_root(nav),BASE,'Fiction')
    self.assertEqual([BASE+'?cat=fiction-pb'],[r['url'] for r in routes])

  def test_subcategory_requires_advertised_link_and_selected_parent(self):
    url=BASE+'?cat=fiction&sub-cat=history'
    for nav in (link('Poetry','cat=poetry',True)+link('History','cat=fiction&sub-cat=history',child=True),link('Fiction','cat=fiction',True)):
      with self.subTest(nav=nav),self.assertRaisesRegex(ValueError,'subcategory'):
        self.parser.parse(nav+card('Wrong Book'),url,'NBA','History')

  def test_authorless_book_uses_matching_official_cover_credit_only(self):
    for title,alt,expected in (
        ('Fortune Smiles: Stories','Fortune Smiles: Stories by Adam Johnson book cover, 2015',['Adam Johnson']),
        ('The Late Great Creature','cover of The Late Great Creature by Brock Brower',['Brock Brower']),
    ):
      with self.subTest(title=title):
        detail=f'<h1>{title}</h1><img alt="{alt}"><img alt="Different Book by Wrong Writer">'
        calls=[]
        parsed=self.parser.parse(card(title,''),BASE+'?cat=fiction','NBA','Fiction',fetch_url=lambda url:(calls.append(url) or detail))
        self.assertEqual(['https://www.nationalbook.org/books/book/'],calls)
        self.assertEqual(expected,parsed['entries'][0]['authors'])
    with self.assertRaisesRegex(ValueError,'another title'):
      self.parser.author_from_book_page('<h1>Different Book</h1><img alt="Book by Wrong Writer">','Book')

  def test_missing_author_detail_failures_and_cancellation_are_not_silently_dropped(self):
    for error in (ImportCancelledError('stop'),CamoufoxRequiredError('required'),OSError('offline')):
      def fail(url):raise error
      with self.subTest(error=type(error).__name__),self.assertRaises(type(error)):
        self.parser.parse(card('Book',''),BASE+'?cat=fiction','NBA','Fiction',fetch_url=fail)
    with self.assertRaisesRegex(ValueError,'no usable author credit'):
      self.parser.parse(card('Book',''),BASE+'?cat=fiction','NBA','Fiction',fetch_url=lambda url:'<h1>Book</h1>')

  def test_historical_finalist_placeholder_is_not_a_book(self):
    parsed=self.parser.parse(card('1964 Nonfiction Finalists','',result='nominee'),BASE+'?cat=nonfiction','NBA','Nonfiction',fetch_url=lambda url:self.fail(url))
    self.assertEqual([],parsed['entries'])

  def test_wrong_annual_document_year_is_rejected(self):
    with self.assertRaisesRegex(ValueError,'another award year'):
      self.parser.parse('<title>National Book Awards 1981</title>'+card('Wrong Year'),BASE,'NBA','Fiction')

  def test_routed_annual_cache_reuses_whole_history_and_recovers_missing_year(self):
    from storage import build_import_cache_data
    from _dev_tools.verify_import_updates import without_unit
    from url_fetcher.national_book_award import UrlFetcherNationalBookAwardFiction

    recipe=UrlFetcherNationalBookAwardFiction()
    years=(2022,2023,2024)
    calls=[]
    def year_url(year):return BASE.replace('1980',str(year))
    def fetch(url):
      calls.append(url)
      if url==recipe.URL:return ''.join(f'<a href="{year_url(year)}">{year}</a>' for year in years)
      year=next(year for year in years if year_url(year) in url)
      nav=(link('Autobiography - Hardcover','cat=autobiography',True)+link('Fiction - Hardcover','cat=fiction-hc')+
        link('Fiction - Paperback','cat=autobiography&sub-cat=fiction-pb',child=True)).replace(BASE,year_url(year))
      if url.endswith('cat=fiction-hc'):
        return link('Fiction - Hardcover','cat=fiction-hc',True).replace(BASE,year_url(year))+card(f'Hardcover {year}')
      return nav+card(f'Paperback {year}')
    full=recipe.fetch_and_parse(fetch,source_choice=0)
    self.assertEqual(6,len(full['entries']))
    self.assertEqual(10,len(calls))
    saved=build_import_cache_data(recipe.source_id,full)
    calls.clear()
    updated=recipe.fetch_and_parse(fetch,source_choice=0,cached_parsed=saved,incremental_update=True)
    self.assertEqual(full['entries'],updated['entries'])
    self.assertEqual(4,len(calls))
    removed=without_unit(saved,recipe.category_url(year_url(2022)))
    self.assertEqual(4,len(removed['entries']))
    calls.clear()
    recovered=recipe.fetch_and_parse(fetch,source_choice=0,cached_parsed=removed,incremental_update=True)
    self.assertEqual(full['entries'],recovered['entries'])
    self.assertEqual(7,len(calls))

  def test_failed_child_route_retains_complete_old_year_without_partial_writes(self):
    from storage import build_import_cache_data
    from url_fetcher.national_book_award import UrlFetcherNationalBookAwardFiction

    recipe=UrlFetcherNationalBookAwardFiction()
    nav=link('Autobiography - Hardcover','cat=autobiography',True)+link('Fiction - Hardcover','cat=fiction-hc')+link('Fiction - Paperback','cat=autobiography&sub-cat=fiction-pb',child=True)
    fail=False
    def fetch(url):
      if url==recipe.URL:return f'<a href="{BASE}">1980</a>'
      if url.endswith('cat=fiction-hc'):
        return link('Fiction - Hardcover','cat=fiction-hc',True)+card('Changed Hardcover' if fail else 'Old Hardcover')
      if 'sub-cat' in url:
        if fail:raise OSError('offline')
        return nav+card('Old Paperback')
      return nav
    full=recipe.fetch_and_parse(fetch,source_choice=0)
    fail=True
    updated=recipe.fetch_and_parse(fetch,source_choice=0,cached_parsed=build_import_cache_data(recipe.source_id,full),incremental_update=True)
    self.assertEqual(full['entries'],updated['entries'])
    self.assertTrue(updated['notes'])
    self.assertFalse(updated['incremental_state']['units'][recipe.category_url(BASE)]['complete'])


class NationalBookAwardTransportTests(unittest.TestCase):

  CHALLENGE = ('<html><head><meta http-equiv="refresh" '
    'content="0;/.well-known/sgcaptcha/?r=%2Fnational-book-awards%2Fyears%2F'
    '&amp;y=ipr:test"></head></html>')

  def setUp(self):
    from url_fetcher.national_book_award import UrlFetcherNationalBookAwardYoungPeoplesLiterature
    self.recipe = UrlFetcherNationalBookAwardYoungPeoplesLiterature()

  def test_blocked_discovery_and_annual_pages_recover_within_selected_foundation(self):
    from url_fetcher.national_book_award import (
      UrlFetcherNationalBookAwardFiction, UrlFetcherNationalBookAwardNonfiction,
      UrlFetcherNationalBookAwardYoungPeoplesLiterature,
    )
    for cls in (UrlFetcherNationalBookAwardFiction, UrlFetcherNationalBookAwardNonfiction,
        UrlFetcherNationalBookAwardYoungPeoplesLiterature):
      with self.subTest(recipe=cls.source_id):
        recipe = cls()
        calls = []
        year_url = recipe.category_url(BASE)

        def fetch(url, transport='default'):
          calls.append((url, transport))
          if transport == 'default':
            return self.CHALLENGE
          if url == recipe.URL:
            return f'<a href="{BASE}">1980</a>'
          self.assertEqual(year_url, url)
          return card('Official Winner')

        parsed = recipe.fetch_and_parse(fetch, source_choice=0, disable_fallbacks=True)
        self.assertEqual(['Official Winner'], [e['title'] for e in parsed['entries']])
        self.assertEqual(recipe.URL, parsed['source']['url'])
        self.assertEqual([], parsed['notes'])
        self.assertEqual([(recipe.URL, 'default'), (recipe.URL, 'camoufox'),
          (year_url, 'default'), (year_url, 'camoufox')], calls)

  def test_healthy_legacy_page_does_not_start_browser(self):
    calls = []
    def fetch(url):
      calls.append(url)
      return card('Official Winner')
    self.assertEqual(card('Official Winner'), self.recipe.fetch_url(fetch, BASE))
    self.assertEqual([BASE], calls)

  def test_linked_author_detail_uses_same_transport_recovery(self):
    detail_url = 'https://www.nationalbook.org/books/book/'
    calls = []
    def fetch(url, transport='default'):
      calls.append((url, transport))
      if url == self.recipe.URL:
        return f'<a href="{BASE}">1980</a>'
      if url == self.recipe.category_url(BASE):
        return card('Official Winner', author='')
      self.assertEqual(detail_url, url)
      if transport == 'default':
        return self.CHALLENGE
      return '<h1>Official Winner</h1><img alt="Official Winner by Verified Writer">'
    parsed = self.recipe.fetch_and_parse(fetch, source_choice=0)
    self.assertEqual(['Verified Writer'], parsed['entries'][0]['authors'])
    self.assertEqual([(detail_url, 'default'), (detail_url, 'camoufox')], calls[-2:])

  def test_two_challenges_report_verification_instead_of_missing_years(self):
    from url_fetcher.generic import UrlFetcherError
    calls = []
    def fetch(url, transport='default'):
      calls.append(transport)
      return self.CHALLENGE
    with self.assertRaisesRegex(UrlFetcherError, 'browser response still requires bot verification'):
      self.recipe.fetch_and_parse(fetch, source_choice=0)
    self.assertEqual(['default', 'camoufox'], calls)

  def test_disabled_browser_reports_original_challenge_too(self):
    from errors import CamoufoxSkippedError
    from url_fetcher.generic import UrlFetcherError
    def fetch(url, transport='default'):
      if transport == 'camoufox':
        raise CamoufoxSkippedError('Camoufox disabled')
      return self.CHALLENGE
    with self.assertRaisesRegex(UrlFetcherError, 'bot-verification.*Camoufox disabled'):
      self.recipe.fetch_url(fetch, BASE)

  def test_cancellation_and_required_browser_errors_propagate_from_either_transport(self):
    from errors import ImportCancelledError, CamoufoxRequiredError
    for error in (ImportCancelledError('cancelled'), CamoufoxRequiredError('required')):
      for stage in ('default', 'camoufox'):
        with self.subTest(error=type(error).__name__, stage=stage):
          calls = []
          def fetch(url, transport='default'):
            calls.append(transport)
            if transport == stage:
              raise error
            return self.CHALLENGE
          with self.assertRaises(type(error)) as raised:
            self.recipe.fetch_url(fetch, BASE)
          self.assertIs(error, raised.exception)
          self.assertEqual(['default'] if stage == 'default' else ['default','camoufox'], calls)

  def test_wikipedia_transport_is_unchanged(self):
    calls = []
    def fetch(url):
      calls.append(url)
      return self.CHALLENGE
    self.assertEqual(self.CHALLENGE, self.recipe.fetch_url(fetch, self.recipe.WIKIPEDIA_URL))
    self.assertEqual([self.recipe.WIKIPEDIA_URL], calls)

  def test_transient_official_retry_still_finishes_before_browser_fallback(self):
    from urllib.error import HTTPError
    calls = []
    def fetch(url):
      calls.append(url)
      if len(calls) < 3:
        raise HTTPError(url, 503, 'temporary', {}, None)
      return card('Official Winner')
    self.assertEqual(card('Official Winner'), self.recipe.fetch_url(fetch, BASE))
    self.assertEqual([BASE] * 3, calls)


if __name__=='__main__':unittest.main()
