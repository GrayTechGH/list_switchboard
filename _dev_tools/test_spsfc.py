"""SPSFC source parsing, browser order and cancellation regressions."""

import unittest

from _dev_tools import test_import_matching as support
from errors import CamoufoxSkippedError, ImportCancelledError
from parser.spsfc import (
  FILE770_FINALISTS, OFFICIAL_RESULT, SPSFCAwardsParser, SPSFC_SOURCE_PAGES, _merge_rows,
)
from url_fetcher.generic import UrlFetcherError
from url_fetcher.spsfc import UrlFetcherSPSFCNovelFinalists
from url_fetcher.spsfc_transport import SPSFCFetchPolicy


PLACES = ('Winner', 'Second Place', 'Third Place', 'Fourth Place', 'Fifth Place', 'Sixth Place')
LATEST = (
  ('Our Simulated Selves', 'Nikki Null'), ('ab initio', 'Jacob Terracina'),
  ('Generations', 'Noam Josephides'), ('Artificial Selection', 'Marianne Pickles'),
  ('FrostByte', 'N.S. Chaudhury'), ('Time Traitors', 'Eli Donovan'),
)


def result_html(competition=5):
  books = LATEST if competition == 5 else (
    ('Saint Elspeth', 'Wick Welker'),
    *[(f'Competition Four Book {index}', f'Writer {index}') for index in range(2, 7)])
  sections = ''.join(
    f'<h3>{place}</h3><h4>{title} by {author}</h4>'
    f'<p><a href="https://www.goodreads.com/book/show/{competition}{index}">Goodreads</a></p>'
    for index, (place, (title, author)) in enumerate(zip(PLACES, books), 1))
  return (f'<html><title>SPSFC {competition} Winner</title><article>'
    '<div class="entry-content">' + sections + '</div></article>'
    '<aside><h2 class="wp-block-post-title">SPSFC 6 Now Accepting Entries</h2></aside></html>')


def source_html(page):
  competition = int(page['competition'].split()[-1])
  if page['kind'] == OFFICIAL_RESULT:
    return result_html(competition)
  if competition == 4:
    books = [('Saint Elspeth', 'Wick Welker'),
      *[(f'Competition Four Book {index}', f'Writer {index}') for index in range(2, 7)]]
  else:
    winner = {1: ('Iron Truth', 'S.A. Tholin'),
      2: ('The Last Gifts of the Universe', 'Rory August'), 3: ('Kenai', 'Dave Dobson')}[competition]
    books = [winner, *[(f'Book {competition} {index}', f'Writer {index}')
      for index in range(1, 6 if competition == 3 else 7)]]
  return '<article><div class="entry-content"><ul>' + ''.join(
    f'<li>{title} by {author}</li>' for title, author in books) + '</ul></div></article>'


class SPSFCTest(unittest.TestCase):

  def fixture_fetch(self, calls, browser_error=None):
    pages = {page['url']: page for page in SPSFC_SOURCE_PAGES}

    def fetch(url, **options):
      calls.append((url, options))
      if options.get('transport') == 'camoufox' and browser_error is not None:
        raise browser_error
      return source_html(pages[url])

    return fetch

  def test_full_import_includes_spsfc5_and_preserves_older_competitions(self):
    calls = []
    parsed = UrlFetcherSPSFCNovelFinalists().fetch_and_parse(self.fixture_fetch(calls))
    self.assertEqual(32, len(parsed['entries']))
    self.assertEqual([], parsed['notes'])
    latest = [row for row in parsed['entries'] if row['competition'] == 'SPSFC 5']
    self.assertEqual([title for title, _author in LATEST], [row['title'] for row in latest])
    self.assertEqual(['2026', *[f'2026.0{i}' for i in range(1, 6)]], [r['position'] for r in latest])
    self.assertEqual(['winner', *['runner-up'] * 5], [r['result'] for r in latest])
    self.assertEqual(list(range(1, 7)), [r['placement'] for r in latest])
    self.assertEqual([['Nikki Null'], ['Jacob Terracina'], ['Noam Josephides'],
      ['Marianne Pickles'], ['N.S. Chaudhury'], ['Eli Donovan']], [r['authors'] for r in latest])
    self.assertEqual(6, len(calls))
    self.assertTrue(all(options == {'transport': 'camoufox'} for _url, options in calls[:3]))
    self.assertTrue(all(not options for _url, options in calls[3:]))
    self.assertTrue(all('file770.com' in url for url, _options in calls[3:]))
    self.assertTrue(all(r['award_source_url'] == SPSFC_SOURCE_PAGES[0]['url'] for r in latest))

  def test_browser_failure_falls_back_at_same_url_and_disables_later_browser_requests(self):
    calls = []
    parsed = UrlFetcherSPSFCNovelFinalists().fetch_and_parse(
      self.fixture_fetch(calls, browser_error=RuntimeError('browser failed')))
    self.assertEqual(32, len(parsed['entries']))
    self.assertEqual([], parsed['notes'])
    self.assertEqual([(SPSFC_SOURCE_PAGES[0]['url'], {'transport': 'camoufox'}),
      (SPSFC_SOURCE_PAGES[0]['url'], {})], calls[:2])
    self.assertTrue(all(not options for _url, options in calls[1:]))

  def test_disabled_browser_uses_only_random_agent_legacy_callback(self):
    calls = []
    parsed = UrlFetcherSPSFCNovelFinalists().fetch_and_parse(
      self.fixture_fetch(calls, browser_error=CamoufoxSkippedError('disabled')))
    self.assertEqual(32, len(parsed['entries']))
    self.assertTrue(all('user_agent' not in options for _url, options in calls))
    self.assertEqual(1, sum(bool(options) for _url, options in calls))

  def test_browser_challenge_or_wrong_competition_retries_legacy(self):
    for rejected in ('<title>Just a moment...</title>', result_html(4)):
      with self.subTest(payload=rejected[:45]):
        calls = []
        delegate = self.fixture_fetch(calls)

        def fetch(url, **options):
          if options:
            calls.append((url, options))
            return rejected
          return delegate(url, **options)

        parsed = UrlFetcherSPSFCNovelFinalists().fetch_and_parse(fetch)
        self.assertEqual(32, len(parsed['entries']))
        self.assertEqual([], parsed['notes'])
        self.assertEqual(1, sum(bool(options) for _url, options in calls))

  def test_cancelled_initial_browser_request_does_not_retry_or_return_curated_rows(self):
    calls = []
    with self.assertRaises(ImportCancelledError):
      UrlFetcherSPSFCNovelFinalists().fetch_and_parse(
        self.fixture_fetch(calls, browser_error=ImportCancelledError('cancelled')))
    self.assertEqual(1, len(calls))

  def test_cancelled_linked_page_does_not_return_partial_history(self):
    parser = SPSFCAwardsParser()

    def fetch(url):
      raise ImportCancelledError('cancelled linked page')

    with self.assertRaises(ImportCancelledError):
      parser.parse(result_html(), SPSFC_SOURCE_PAGES[0]['url'], 'SPSFC', fetch_url=fetch)

  def test_empty_both_transports_fail_instead_of_returning_packaged_winners(self):
    with self.assertRaises(UrlFetcherError):
      UrlFetcherSPSFCNovelFinalists().fetch_and_parse(lambda _url, **_kw: '<html>blocked</html>')

  def test_unconfigured_status_or_allocation_page_is_not_fetched(self):
    calls = []
    policy = SPSFCFetchPolicy(lambda url, **kw: calls.append(url), SPSFCAwardsParser())
    with self.assertRaises(ValueError):
      policy.fetch('https://spsfc.space/spsfc-6-allocations/')
    self.assertEqual([], calls)

  def test_official_result_reader_ignores_sidebar_and_comments(self):
    html = result_html().replace('</article>',
      '<div id="comments"><h3>Winner</h3><h4>Comment Book by Someone</h4></div></article>')
    rows = SPSFCAwardsParser().parse_source_page(html, SPSFC_SOURCE_PAGES[0])
    self.assertEqual([title for title, _author in LATEST], [r['title'] for r in rows])

  def test_archival_finalist_reader_ignores_unrelated_lists(self):
    page = next(p for p in SPSFC_SOURCE_PAGES if p['kind'] == FILE770_FINALISTS)
    html = source_html(page).replace('</article>',
      '<aside><ul><li>Sidebar Book by Someone</li><li>Other Book by Someone</li></ul></aside></article>')
    rows = SPSFCAwardsParser().parse_source_page(html, page)
    self.assertEqual(6, len(rows))
    self.assertFalse(any(r['title'] == 'Sidebar Book' for r in rows))

  def test_title_by_delimiter_and_merge_use_canonical_author_identity(self):
    parser = SPSFCAwardsParser()
    html = result_html().replace('Our Simulated Selves by Nikki Null', 'Day by Day by Nikki Null')
    rows = parser.parse_source_page(html, SPSFC_SOURCE_PAGES[0])
    self.assertEqual('Day by Day', rows[0]['title'])
    self.assertEqual(['Nikki Null'], rows[0]['authors'])
    same = dict(rows[0], authors=['Another Writer'])
    self.assertEqual(2, len(_merge_rows([rows[0]], [same])))
    self.assertEqual(1, len(_merge_rows([rows[0]], [dict(rows[0])])))

  def test_browser_uses_spsfc_label_and_shared_setting_boundaries(self):
    main = support.main
    core = main.ListSwitchboardCore(None, lambda **_kwargs: None)
    with support.patch.dict(main.prefs, {
        'debug_browser_fallback_level': 0, 'camoufox_first_use_confirmed': True}), \
        support.patch.object(main, 'camoufox_capability', return_value=(True, (9, 18, 0), 'API')), \
        support.patch.object(main, 'CamoufoxTransport') as factory:
      core.fetch_url(SPSFC_SOURCE_PAGES[0]['url'], transport='camoufox')
      self.assertEqual('SPSFC', factory.call_args.kwargs['source_name'])
      self.assertIn('spsfc.space', factory.call_args.kwargs['warmup_excluded_domains'])
      self.assertFalse(factory.call_args.kwargs['check_challenges'])
      core.close_camoufox_transport()
      factory.return_value.close.assert_called_once()


if __name__ == '__main__':
  unittest.main()
