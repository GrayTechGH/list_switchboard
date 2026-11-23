"""Independent validation for official REST and historical supplement transport."""
import json
import unittest
from html import escape
from _dev_tools import test_import_matching as fixtures
from errors import CamoufoxSkippedError, ImportCancelledError
from parser.splatterpunk import (
  GOODREADS_URL, OFFICIAL_AWARDS_API_URL, OFFICIAL_PAST_WINNERS_API_URL,
  OFFICIAL_AWARDS_URL, OFFICIAL_PAST_WINNERS_URL, SplatterpunkParser)
from url_fetcher import splatterpunk as recipes
from url_fetcher.splatterpunk_transport import SplatterpunkFetchPolicy


FETCHERS = [getattr(recipes, 'UrlFetcherSplatterpunk' + name)
  for name in ('Novel', 'Novella', 'Collection', 'Anthology')]
NEXT = GOODREADS_URL + '?page=2'


def row(title, category='Novel', year=2019, winner=False):
  return (f'<tr itemtype="http://schema.org/Book"><td>'
    f'<a class="bookTitle" href="/book/show/100">{escape(title)}</a>'
    f'<a class="authorName">Fixture Writer</a><i>Splatterpunk Award '
    f'{"" if winner else "Nominee "}for Best {category} ({year})</i></td></tr>')


def page(rows, next_url=''):
  return '<table>' + ''.join(rows) + '</table>' + (
    f'<a href="{escape(next_url)}">next</a>' if next_url else '')


def official(title, html):
  return json.dumps([{'title': {'rendered': title},
    'link': OFFICIAL_PAST_WINNERS_URL if title == 'Past Winners' else OFFICIAL_AWARDS_URL,
    'content': {'rendered': html}}])


class SplatterpunkTransportTests(unittest.TestCase):
  def setUp(self):
    self.parser = SplatterpunkParser()
    current, history, first, second = [], [], [], []
    for factory in FETCHERS:
      category = factory.CATEGORY
      current.append(f'<h3>BEST {category}</h3><p>Current {category} by Fixture Writer</p>')
      history.append(f'<h3>BEST {category}</h3><ul>' + ''.join(
        f'<li>{year} - Official {category} {year} by Fixture Writer</li>'
        for year in range(2018, 2026)) + '</ul>')
      first.extend([row(f'Historical {category} One', category),
        row(f'Official {category} 2018', category, 2018, True)])
      second.append(row(f'Historical {category} Two', category, 2020))
    self.pages = {
      OFFICIAL_AWARDS_API_URL: official('2026 Splatterpunk Awards', ''.join(current)),
      OFFICIAL_PAST_WINNERS_API_URL: official('Past Winners', ''.join(history)),
      GOODREADS_URL: page(first, NEXT), NEXT: page(second)}

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
    self.assertIsNone(recipe._splatterpunk_fetch_policy)
    self.assertIsNone(recipe._splatterpunk_progress)
    self.assertTrue(all(isinstance(a[1], int) and a[1] > 0 for a in progress))
    return result, calls

  def test_all_four_categories_full_schema_parity_and_official_transport(self):
    for factory in FETCHERS:
      with self.subTest(category=factory.CATEGORY):
        browser, calls = self.run_recipe(factory)
        legacy, _ = self.run_recipe(factory, {(GOODREADS_URL, True): CamoufoxSkippedError('disabled')})
        self.assertEqual(browser, legacy)
        self.assertEqual(len(browser['entries']), 11)
        self.assertFalse(browser['match_series'])
        self.assertEqual([(u, b) for u, b, _ in calls], [
          (OFFICIAL_AWARDS_API_URL, True), (OFFICIAL_PAST_WINNERS_API_URL, True),
          (GOODREADS_URL, True), (NEXT, True)])
        self.assertTrue(all(kw.get('timeout') == 60 for _u, _b, kw in calls))
        winner = next(e for e in browser['entries'] if e['title'] == f'Official {factory.CATEGORY} 2018')
        self.assertEqual(winner['result'], 'winner')
        self.assertNotIn('goodreads', winner['source']['url'])

  def test_initial_and_later_recovery_are_note_free(self):
    expected, _ = self.run_recipe()
    for url in (GOODREADS_URL, NEXT):
      with self.subTest(url=url):
        recovered, calls = self.run_recipe(failures={(url, True): '<title>Sign In</title>'})
        self.assertEqual(expected, recovered)
        self.assertIn((url, False), [(u, b) for u, b, _ in calls])
        if url == GOODREADS_URL:
          self.assertNotIn((NEXT, True), [(u, b) for u, b, _ in calls])

  def test_failure_discards_entire_supplement_and_keeps_official_results(self):
    for url in (GOODREADS_URL, NEXT):
      result, _ = self.run_recipe(failures={(url, True): 'challenge', (url, False): 'challenge'})
      self.assertEqual(len(result['entries']), 9)
      self.assertFalse(any(e['title'].startswith('Historical') for e in result['entries']))
      self.assertTrue(any('historical supplement failed' in note for note in result['notes']))

  def test_callback_compatibility(self):
    result = FETCHERS[0]().fetch_and_parse(lambda url: self.pages[url])
    self.assertEqual(len(result['entries']), 11)

  def test_cancellation_all_network_boundaries(self):
    for url, browser in ((OFFICIAL_AWARDS_API_URL, True),(OFFICIAL_AWARDS_API_URL, False),
        (OFFICIAL_PAST_WINNERS_API_URL, True),(OFFICIAL_PAST_WINNERS_API_URL, False), (GOODREADS_URL, True), (NEXT, True),
        (GOODREADS_URL, False), (NEXT, False)):
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
        self.assertIsNone(recipe._splatterpunk_fetch_policy)

  def test_legacy_timeout_retries_and_progress(self):
    recipe, calls, progress = FETCHERS[0](), [], []
    def fetch(url, **kwargs):
      if kwargs.get('transport'):
        raise CamoufoxSkippedError('disabled')
      if url == GOODREADS_URL:
        calls.append(kwargs)
        if len(calls) < 4:
          raise TimeoutError('timed out')
      return self.pages[url]
    recipe.fetch_and_parse(fetch, progress=lambda *a: progress.append(a))
    self.assertEqual(len(calls), 4)
    self.assertTrue(all(kw['timeout'] == 60 for kw in calls))
    self.assertEqual(sum('retry' in a[-1] for a in progress), 3)

  def test_explicit_wrong_page_and_award_identity(self):
    valid = page([row('Book')])
    for marker in ('<title>Access denied</title>',
        '<title>Splatterpunk Award Winners Page 3 out of 4</title>',
        '<form action="/user/sign_in"></form>',
        '<link rel="canonical" href="https://www.goodreads.com/award/show/999-other">',
        '<meta property="og:url" content="' + GOODREADS_URL + '?page=1">',
        '<div class="pagination"><span class="current">1</span></div>'):
      with self.subTest(marker=marker), self.assertRaises(ValueError):
        self.parser.validate_goodreads_page(valid + marker, NEXT)
    for invalid in ('challenge', valid.replace('Splatterpunk Award', 'Other Award')):
      with self.assertRaises(ValueError):
        self.parser.validate_goodreads_page(invalid)

  def test_record_validation_is_category_independent(self):
    self.assertTrue(self.parser.validate_goodreads_page(page([row('Story', 'Short Story')]), NEXT))
    with self.assertRaises(ValueError):
      self.parser.validate_goodreads_page(page([row('Book')]).replace('Fixture Writer', ''))

  def test_repeated_pages_recover_or_discard_supplement(self):
    result, _ = self.run_recipe(failures={(NEXT, True): self.pages[GOODREADS_URL]})
    self.assertEqual(len(result['entries']), 11)
    result, _ = self.run_recipe(failures={(NEXT, True): self.pages[GOODREADS_URL],
      (NEXT, False): self.pages[GOODREADS_URL]})
    self.assertEqual(len(result['entries']), 9)
    policy = SplatterpunkFetchPolicy(None, None, self.parser)
    policy.validate(page([row('One'), row('Two')]), GOODREADS_URL)
    policy.validate(page([row('Two'), row('Three')]), NEXT)

  def test_normalized_bounded_same_award_pagination(self):
    links = ''.join(f'<a href="{escape(url)}">next</a>' for url in (
      GOODREADS_URL + '?page=01', NEXT, NEXT + '&extra=1',
      '//evil.test/award/show/38981-splatterpunk-award?page=3',
      'https://www.goodreads.com/award/show/999-other?page=3'))
    self.assertEqual(self.parser.discover_goodreads_page_urls(links), (GOODREADS_URL, NEXT))
    for suffix in ('?page=26', '?page=0', '?page=bad', '?page=2&page=3'):
      with self.subTest(suffix=suffix), self.assertRaises(ValueError):
        self.parser.discover_goodreads_page_urls(f'<a href="{GOODREADS_URL}{suffix}">next</a>')
    self.pages[NEXT] += f'<a href="{GOODREADS_URL}?page=26">next</a>'
    result, _ = self.run_recipe()
    self.assertEqual(len(result['entries']), 9)

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
      self.assertIsNone(recipe._splatterpunk_fetch_policy)
    self.assertEqual(len(owner.rejected), 4)


if __name__ == '__main__':
  unittest.main()
