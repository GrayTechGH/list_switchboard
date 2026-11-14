"""LOHF per-page transport, complete-history and cancellation regressions."""
import unittest
from html import escape
from _dev_tools import test_import_matching as fixtures
from errors import ImportCancelledError, CamoufoxSkippedError
from parser.ladies_of_horror_fiction import (
  ALL_CATEGORIES, EXPECTED_COVERAGE, GOODREADS_URL, FILE770_2021_WINNERS_URL,
  LadiesOfHorrorFictionParser, LOHFPaginationError)
from url_fetcher import ladies_of_horror_fiction as recipes
from url_fetcher.ladies_of_horror_fiction_transport import LadiesOfHorrorFictionFetchPolicy


FETCHERS = [getattr(recipes, 'UrlFetcherLadiesOfHorrorFiction' + name) for name in (
  'Novel', 'Novella', 'Collection', 'Debut', 'YoungAdult', 'MiddleGrade',
  'PoetryCollection', 'GraphicNovel')]
NEXT = GOODREADS_URL + '?page=2'


def row(title, category='Novel', year=2020, winner=False):
  label = f'Ladies of Horror Fiction Award {"" if winner else "Nominee "}for {category} ({year})'
  return (f'<tr itemscope itemtype="http://schema.org/Book"><td>'
    f'<a class="bookTitle" href="/book/show/100">{escape(title)}</a>'
    f'<a class="authorName">Fixture Writer</a><i>{label}</i></td></tr>')


def page(rows, next_url=''):
  return '<table>' + ''.join(rows) + '</table>' + (
    f'<a rel="next" href="{escape(next_url)}">next</a>' if next_url else '')


class LOHFTransportTests(unittest.TestCase):
  def setUp(self):
    self.parser = LadiesOfHorrorFictionParser()
    all_rows = []
    supplement = []
    for category, years in EXPECTED_COVERAGE.items():
      for year, (count, winners) in years.items():
        for index in range(count):
          title = f'{category} {year} work {index}'
          all_rows.append(row(title, category, year, year != 2021 and index < winners))
          if year == 2021 and index < winners:
            supplement.append(f'<h2>LOHF Award for Best {category}</h2><ul><li>{title} by Fixture Writer</li></ul>')
    self.pages = {GOODREADS_URL: page(all_rows[::2], NEXT), NEXT: page(all_rows[1::2]),
      FILE770_2021_WINNERS_URL: '<article>' + ''.join(supplement) + '</article>'}

  def run_recipe(self, factory=FETCHERS[0], failures=None):
    recipe = factory()
    calls, progress = [], []
    def fetch(url, **kwargs):
      browser = kwargs.get('transport') == 'camoufox'
      calls.append((url, browser, kwargs))
      failure = (failures or {}).get((url, browser))
      if isinstance(failure, Exception):
        raise failure
      return self.pages[url] if failure is None else failure
    result = recipe.fetch_and_parse(fetch, progress=lambda *args: progress.append(args))
    self.assertIsNone(recipe._lohf_fetch_policy)
    self.assertTrue(all(isinstance(a[1], int) and a[1] > 0 for a in progress))
    return result, calls

  def test_all_eight_categories_full_schema_parity_and_supplement_transport(self):
    for factory in FETCHERS:
      with self.subTest(category=factory.CATEGORY):
        browser, calls = self.run_recipe(factory)
        self.assertEqual([(u, b) for u, b, _ in calls],
          [(GOODREADS_URL, True), (NEXT, True), (FILE770_2021_WINNERS_URL, False)])
        legacy, _ = self.run_recipe(factory, {(GOODREADS_URL, True): CamoufoxSkippedError('disabled')})
        self.assertEqual(browser, legacy)
        expected = EXPECTED_COVERAGE[factory.CATEGORY.lower()]
        self.assertEqual(len(browser['entries']), sum(n for n, _ in expected.values()))
        self.assertFalse(browser['match_series'])
        if factory.CATEGORY != 'Graphic Novel':
          self.assertTrue(any(e['source']['url'] == FILE770_2021_WINNERS_URL for e in browser['entries']))

  def test_later_recovery_does_not_add_failure_notes(self):
    expected, _ = self.run_recipe()
    recovered, calls = self.run_recipe(failures={(NEXT, True): '<title>Sign in</title>'})
    self.assertEqual(expected, recovered)
    self.assertEqual([(u, b) for u, b, _ in calls][1:3], [(NEXT, True), (NEXT, False)])

  def test_initial_recovery_suppresses_remaining_browser_requests(self):
    _, calls = self.run_recipe(failures={(GOODREADS_URL, True): 'challenge'})
    self.assertEqual([(u, b) for u, b, _ in calls], [(GOODREADS_URL, True),
      (GOODREADS_URL, False), (NEXT, False), (FILE770_2021_WINNERS_URL, False)])

  def test_no_partial_history_from_supplement(self):
    for failed_url in (GOODREADS_URL, NEXT):
      with self.subTest(url=failed_url), self.assertRaisesRegex(recipes.UrlFetcherError, 'incomplete'):
        self.run_recipe(failures={(failed_url, True): 'challenge', (failed_url, False): 'challenge'})

  def test_unsupported_callback(self):
    result = FETCHERS[0]().fetch_and_parse(lambda url: self.pages[url])
    self.assertEqual(len(result['entries']), 16)

  def test_cancellation_at_all_boundaries(self):
    for url, browser in ((GOODREADS_URL, True), (NEXT, True),
        (GOODREADS_URL, False), (NEXT, False), (FILE770_2021_WINNERS_URL, False)):
      with self.subTest(url=url, browser=browser):
        recipe, calls = FETCHERS[0](), []
        def fetch(target, **kwargs):
          using_browser = kwargs.get('transport') == 'camoufox'
          calls.append((target, using_browser))
          if target == url and using_browser == browser:
            raise ImportCancelledError('cancel')
          if not browser and using_browser:
            raise CamoufoxSkippedError('disabled')
          return self.pages[target]
        with self.assertRaises(ImportCancelledError):
          recipe.fetch_and_parse(fetch)
        self.assertEqual(calls[-1], (url, browser))
        self.assertIsNone(recipe._lohf_fetch_policy)

  def test_timeout_retries_and_progress(self):
    recipe, calls, progress = FETCHERS[0](), [], []
    def fetch(url, **kwargs):
      if kwargs.get('transport'):
        raise CamoufoxSkippedError('disabled')
      calls.append((url, kwargs))
      if len(calls) < 4:
        raise TimeoutError('timed out')
      return self.pages[url]
    recipe.fetch_and_parse(fetch, progress=lambda *a: progress.append(a))
    self.assertEqual(sum(url == GOODREADS_URL for url, _ in calls), 4)
    self.assertTrue(all(kw.get('timeout') == 60 for url, kw in calls if url != FILE770_2021_WINNERS_URL))
    self.assertEqual(sum('retry' in a[-1] for a in progress), 3)

  def test_payload_identity_and_challenges(self):
    valid = page([row('Book')])
    markers = ('<title>Access denied</title>', '<form action="/user/sign_in"></form>',
      '<title>Ladies of Horror Fiction Award Winners Page 3 out of 4</title>',
      '<link rel="canonical" href="https://www.goodreads.com/award/show/999-other">',
      '<meta property="og:url" content="' + GOODREADS_URL + '?page=1">',
      '<div class="pagination"><em class="current">1</em></div>')
    for marker in markers:
      with self.subTest(marker=marker), self.assertRaises(ValueError):
        self.parser.validate_goodreads_payload(valid + marker, NEXT)
    for html in ('<h1>Another Award</h1>', valid.replace('Ladies of Horror Fiction', 'Other')):
      with self.assertRaises(ValueError):
        self.parser.validate_goodreads_payload(html, GOODREADS_URL)

  def test_other_category_short_fiction_and_line_shape_accepted(self):
    for category in ('Graphic Novel', 'Short Fiction'):
      self.assertTrue(self.parser.validate_goodreads_payload(page([row('Book', category)]), NEXT))
    self.assertTrue(self.parser.validate_goodreads_payload(
      '<p>Book</p><p>by</p><p>Writer</p><p>Ladies of Horror Fiction Award for Novel (2020)</p>', NEXT))

  def test_repeated_pages_recover_and_overlap_allowed(self):
    result, _ = self.run_recipe(failures={(NEXT, True): self.pages[GOODREADS_URL]})
    self.assertEqual(len(result['entries']), 16)
    with self.assertRaisesRegex(recipes.UrlFetcherError, 'incomplete'):
      self.run_recipe(failures={(NEXT, True): self.pages[GOODREADS_URL], (NEXT, False): self.pages[GOODREADS_URL]})
    policy = LadiesOfHorrorFictionFetchPolicy(None, None, self.parser)
    policy.validate(page([row('One'), row('Two')]), GOODREADS_URL)
    policy.validate(page([row('Two'), row('Three')]), NEXT)

  def test_pagination_normalized_bounded_and_same_award(self):
    links = ''.join(f'<a href="{escape(u)}">next</a>' for u in (
      GOODREADS_URL + '?page=01', NEXT + '&other=1', NEXT, '//evil.test' + GOODREADS_URL.split('.com')[1] + '?page=3',
      'https://www.goodreads.com/award/show/999-other?page=3'))
    self.assertEqual(self.parser.discover_goodreads_page_urls(links), (GOODREADS_URL, NEXT))
    for suffix in ('?page=9', '?page=0', '?page=bad', '?page=2&page=3'):
      with self.subTest(suffix=suffix), self.assertRaises(LOHFPaginationError):
        self.parser.discover_goodreads_page_urls(f'<a href="{GOODREADS_URL}{suffix}">next</a>')

  def test_safety_bound_not_hidden_by_complete_results(self):
    self.pages[NEXT] += f'<a href="{GOODREADS_URL}?page=9">next</a>'
    with self.assertRaises(LOHFPaginationError):
      self.run_recipe()

  def test_discovery_from_later_page(self):
    third = GOODREADS_URL + '?page=3'
    self.pages[NEXT] += f'<a href="{third}">next</a>'
    self.pages[third] = page([row('Extra excluded work', 'Short Fiction')])
    result, calls = self.run_recipe()
    self.assertEqual(len(result['entries']), 16)
    self.assertIn((third, True), [(u, b) for u, b, _ in calls])

  def test_owner_rejection_and_policy_reset(self):
    class Owner:
      def __init__(owner):
        owner.rejected = []
      def reject_camoufox_payload(owner, reason):
        owner.rejected.append(reason)
      def fetch(owner, url, **kwargs):
        return 'challenge' if kwargs.get('transport') else self.pages[url]
    owner, recipe = Owner(), FETCHERS[0]()
    for _ in range(2):
      recipe.fetch_and_parse(owner.fetch)
      self.assertIsNone(recipe._lohf_fetch_policy)
    self.assertEqual(len(owner.rejected), 2)


if __name__ == '__main__':
  unittest.main()
