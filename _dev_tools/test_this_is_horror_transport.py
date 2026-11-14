"""This Is Horror diagnostic recovery must leave official ballots authoritative."""
import json
import unittest
from html import escape
from _dev_tools import test_import_matching as fixtures
from errors import CamoufoxSkippedError, ImportCancelledError
from parser.this_is_horror import (
  EXPECTED_BALLOT_COUNTS, OFFICIAL_BALLOTS, OFFICIAL_RESULTS,
  GOODREADS_URL, OFFICIAL_AWARDS_API_URL, OFFICIAL_RESULT_POSTS_API_URL,
  OFFICIAL_RESULT_PAGES_API_URL, ThisIsHorrorParser)
from url_fetcher import this_is_horror as recipes
from url_fetcher.this_is_horror_transport import ThisIsHorrorFetchPolicy


FETCHERS = [getattr(recipes, 'UrlFetcherThisIsHorror' + name) for name in (
  'Novel', 'Novella', 'ShortStoryCollection', 'Anthology')]
NEXT = GOODREADS_URL + '?page=2'


def row(title, category='Novel', year=2021, winner=False):
  return (f'<tr itemtype="http://schema.org/Book"><td>'
    f'<a class="bookTitle" href="/book/show/100">{escape(title)}</a>'
    f'<a class="authorName">Fixture Writer</a><i>This is Horror Award '
    f'{"" if winner else "Nominee "}for {category} ({year})</i></td></tr>')


def page(rows, next_url=''):
  return '<table>' + ''.join(rows) + '</table>' + (
    f'<a href="{escape(next_url)}">next</a>' if next_url else '')


def work(category, year, index):
  return f'{category} {year} work {index}'


def document(year, url, html):
  return {'title': {'rendered': f'This Is Horror Awards {year}'},
    'link': url, 'content': {'rendered': html}}


class ThisIsHorrorTransportTests(unittest.TestCase):
  def setUp(self):
    self.parser = ThisIsHorrorParser()
    ballots, results = [], {'posts': [], 'pages': []}
    for year, _id, url in OFFICIAL_BALLOTS:
      html = []
      for factory in FETCHERS:
        category = factory.CATEGORY
        count = EXPECTED_BALLOT_COUNTS[category.lower()].get(year, 0)
        if count:
          html.append(f'<h2>{category} of the Year</h2><ol>' + ''.join(
            f'<li>{work(category, year, i)} by Fixture Writer</li>' for i in range(count)) + '</ol>')
      ballots.append(document(year, url, ''.join(html)))
    for year, kind, _id, url in OFFICIAL_RESULTS:
      html = []
      for factory in FETCHERS:
        category = factory.CATEGORY
        if year in EXPECTED_BALLOT_COUNTS[category.lower()]:
          html.append(f'<h2>{category} of the Year</h2>'
            f'<p>Winner: {work(category, year, 0)} by Fixture Writer</p>'
            f'<p>Runner-up: {work(category, year, 1)} by Fixture Writer</p>')
      results[kind].append(document(year, url, ''.join(html)))
    self.pages = {
      OFFICIAL_AWARDS_API_URL: json.dumps(ballots),
      OFFICIAL_RESULT_POSTS_API_URL: json.dumps(results['posts']),
      OFFICIAL_RESULT_PAGES_API_URL: json.dumps(results['pages']),
      GOODREADS_URL: page([row(work(f.CATEGORY, 2021, 2), f.CATEGORY, winner=True) for f in FETCHERS], NEXT),
      NEXT: page([row('Diagnostic gap work ' + f.CATEGORY, f.CATEGORY, 2022) for f in FETCHERS])}

  def run_recipe(self, factory=FETCHERS[0], failures=None):
    recipe, calls, progress = factory(), [], []
    def fetch(url, **kwargs):
      browser = kwargs.get('transport') == 'camoufox'
      calls.append((url, browser, kwargs))
      value = (failures or {}).get((url, browser), self.pages[url])
      if isinstance(value, Exception):
        raise value
      return value
    result = recipe.fetch_and_parse(fetch, progress=lambda *a: progress.append(a))
    self.assertIsNone(recipe._this_is_horror_fetch_policy)
    self.assertIsNone(recipe._this_is_horror_progress)
    self.assertTrue(all(isinstance(a[1], int) and a[1] > 0 for a in progress))
    return result, calls

  def test_all_four_categories_parity_and_official_authority(self):
    for factory in FETCHERS:
      with self.subTest(category=factory.CATEGORY):
        browser, calls = self.run_recipe(factory)
        legacy, _ = self.run_recipe(factory, {(GOODREADS_URL, True): CamoufoxSkippedError('disabled')})
        self.assertEqual(browser, legacy)
        expected = EXPECTED_BALLOT_COUNTS[factory.CATEGORY.lower()]
        self.assertEqual(len(browser['entries']), sum(expected.values()))
        self.assertFalse(browser['match_series'])
        self.assertFalse(any('goodreads' in e['source']['url'] for e in browser['entries']))
        self.assertFalse(any(e['award_year'] in ('2022', '2023') for e in browser['entries']))
        for year in expected:
          entries = [e for e in browser['entries'] if e['award_year'] == str(year)]
          self.assertEqual(next(e['title'] for e in entries if e['result'] == 'winner'), work(factory.CATEGORY, year, 0))
          self.assertEqual(next(e['title'] for e in entries if e['position'] == f'{year}.01'), work(factory.CATEGORY, year, 1))
        official = [(u, b, kw) for u, b, kw in calls if u not in (GOODREADS_URL, NEXT)]
        self.assertTrue(all(not b and kw.get('timeout') != 60 for _, b, kw in official))

  def test_recovery_preserves_complete_schema_and_notes(self):
    expected, _ = self.run_recipe()
    for url in (GOODREADS_URL, NEXT):
      result, calls = self.run_recipe(failures={(url, True): 'challenge'})
      self.assertEqual(result, expected)
      self.assertIn((url, False), [(u, b) for u, b, _ in calls])
      if url == GOODREADS_URL:
        self.assertNotIn((NEXT, True), [(u, b) for u, b, _ in calls])

  def test_failed_diagnostic_is_optional_but_never_partial(self):
    expected, _ = self.run_recipe()
    for url in (GOODREADS_URL, NEXT):
      result, _ = self.run_recipe(failures={(url, True): 'challenge', (url, False): 'challenge'})
      self.assertEqual(result['entries'], expected['entries'])
      self.assertTrue(any('diagnostic supplement failed:' in n for n in result['notes']))
      self.assertNotIn('Goodreads overlaps were excluded in favor of official ballot rows.', result['notes'])

  def test_official_ballot_failure_is_not_replaced_by_goodreads(self):
    recipe, calls = FETCHERS[0](), []
    def fetch(url, **kwargs):
      calls.append(url)
      return '[]' if url == OFFICIAL_AWARDS_API_URL else self.pages[url]
    with self.assertRaisesRegex(ValueError, 'ballot coverage is incomplete'):
      recipe.fetch_and_parse(fetch)
    self.assertEqual(calls, [OFFICIAL_AWARDS_API_URL])
    self.assertIsNone(recipe._this_is_horror_fetch_policy)

  def test_official_result_completeness_is_unchanged(self):
    with self.assertRaisesRegex(ValueError, 'result coverage is incomplete'):
      self.run_recipe(failures={(OFFICIAL_RESULT_POSTS_API_URL, False): '[]',
        (OFFICIAL_RESULT_PAGES_API_URL, False): '[]'})

  def test_callback_compatibility(self):
    result = FETCHERS[0]().fetch_and_parse(lambda url: self.pages[url])
    self.assertEqual(len(result['entries']), sum(EXPECTED_BALLOT_COUNTS['novel'].values()))

  def test_cancellation_all_network_boundaries(self):
    for url, browser in ((OFFICIAL_AWARDS_API_URL, False),
        (OFFICIAL_RESULT_POSTS_API_URL, False), (OFFICIAL_RESULT_PAGES_API_URL, False),
        (GOODREADS_URL, True), (NEXT, True), (GOODREADS_URL, False), (NEXT, False)):
      with self.subTest(url=url, browser=browser):
        recipe, calls = FETCHERS[0](), []
        def fetch(target, **kwargs):
          using_browser = kwargs.get('transport') == 'camoufox'
          calls.append((target, using_browser))
          if (target, using_browser) == (url, browser):
            raise ImportCancelledError('cancel')
          if not browser and using_browser:
            raise CamoufoxSkippedError('disabled')
          return self.pages[target]
        with self.assertRaises(ImportCancelledError):
          recipe.fetch_and_parse(fetch)
        self.assertEqual(calls[-1], (url, browser))
        self.assertIsNone(recipe._this_is_horror_fetch_policy)

  def test_legacy_timeout_retry_progress(self):
    recipe, attempts, progress = FETCHERS[0](), [], []
    def fetch(url, **kwargs):
      if kwargs.get('transport'):
        raise CamoufoxSkippedError('disabled')
      if url == GOODREADS_URL:
        attempts.append(kwargs)
        if len(attempts) < 4:
          raise TimeoutError('timed out')
      return self.pages[url]
    recipe.fetch_and_parse(fetch, progress=lambda *a: progress.append(a))
    self.assertEqual(len(attempts), 4)
    self.assertTrue(all(kw['timeout'] == 60 for kw in attempts))
    self.assertEqual(sum('retry' in a[-1] for a in progress), 3)

  def test_table_line_and_category_free_validation(self):
    self.assertTrue(self.parser.validate_goodreads_page(page([row('Book', 'Short Fiction')]), NEXT))
    html = '<p>Book</p><p>by</p><p>Writer</p><p>This is Horror Award Nominee for Novel (finalist) (2024)</p>'
    self.assertTrue(self.parser.validate_goodreads_page(html, NEXT))
    for invalid in ('<h1>This is Horror Award</h1>', 'challenge', page([row('Book')]).replace('This is Horror', 'Other')):
      with self.assertRaises(ValueError):
        self.parser.validate_goodreads_page(invalid)

  def test_explicit_wrong_page_and_award(self):
    for marker in ('<title>Sign In</title>', '<form action="/user/sign_in"></form>',
        '<title>This Is Horror Award Winners Page 3 out of 4</title>',
        '<div class="pagination"><span class="current">1</span></div>',
        '<link rel="canonical" href="https://www.goodreads.com/award/show/999-other">',
        '<meta property="og:url" content="' + GOODREADS_URL + '?page=1">'):
      with self.subTest(marker=marker), self.assertRaises(ValueError):
        self.parser.validate_goodreads_page(page([row('Book')]) + marker, NEXT)

  def test_repeated_page_recovery_and_boundary_overlap(self):
    expected, _ = self.run_recipe()
    result, _ = self.run_recipe(failures={(NEXT, True): self.pages[GOODREADS_URL]})
    self.assertEqual(expected, result)
    result, _ = self.run_recipe(failures={(NEXT, True): self.pages[GOODREADS_URL], (NEXT, False): self.pages[GOODREADS_URL]})
    self.assertTrue(any('diagnostic supplement failed:' in n for n in result['notes']))
    policy = ThisIsHorrorFetchPolicy(None, None, self.parser)
    policy.validate(page([row('One'), row('Two')]), GOODREADS_URL)
    policy.validate(page([row('Two'), row('Three')]), NEXT)

  def test_normalized_bounded_same_award_pagination(self):
    links = ''.join(f'<a href="{escape(url)}">next</a>' for url in (
      GOODREADS_URL + '?page=01', NEXT, NEXT + '&extra=1',
      '//evil.test/award/show/23539-this-is-horror-award?page=3',
      'https://www.goodreads.com/award/show/999-other?page=3'))
    self.assertEqual(self.parser.discover_goodreads_page_urls(links), (GOODREADS_URL, NEXT))
    for suffix in ('?page=11', '?page=0', '?page=bad', '?page=2&page=3'):
      with self.subTest(suffix=suffix), self.assertRaises(ValueError):
        self.parser.discover_goodreads_page_urls(f'<a href="{GOODREADS_URL}{suffix}">next</a>')
    self.pages[NEXT] += f'<a href="{GOODREADS_URL}?page=11">next</a>'
    result, _ = self.run_recipe()
    self.assertTrue(any('diagnostic supplement failed:' in n for n in result['notes']))

  def test_owner_rejection_and_operation_reset(self):
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
      self.assertIsNone(recipe._this_is_horror_fetch_policy)
    self.assertEqual(len(owner.rejected), 2)


if __name__ == '__main__':
  unittest.main()
