"""ISFDB transport order and linked-page recovery without source replacement."""

import unittest
from unittest.mock import Mock
from urllib.error import HTTPError

from _dev_tools import test_import_matching as support
from errors import CamoufoxSkippedError, ImportCancelledError
from url_fetcher.aurealis import UrlFetcherAurealisSFNovel
from url_fetcher.isfdb_transport import ISFDBSourceAttempt
from url_fetcher.locus import UrlFetcherLocusAnnualSFNovel
from url_fetcher.seiun import (
  UrlFetcherSeiunComic, UrlFetcherSeiunJapaneseLongWork, UrlFetcherSeiunNonfiction,
  UrlFetcherSeiunTranslatedNovel,
)


class ISFDBTransportTest(unittest.TestCase):

  def test_nonfiction_uses_complete_isfdb_category_without_original_work_resolution(self):
    fetcher = UrlFetcherSeiunNonfiction()
    self.assertEqual('https://www.isfdb.org/cgi-bin/award_category.cgi?638+1', fetcher.URL)
    self.assertEqual([('ISFDB', fetcher.URL, 0)], [
      (attempt.label, attempt.url, attempt.source_rank) for attempt in fetcher.source_attempts()])
    self.assertFalse(fetcher.RESOLVE_ISFDB_ORIGINAL_WORKS)
    self.assertFalse(fetcher.create_isfdb_parser().CAPTURE_ORIGINAL_WORK)
    self.assertTrue(UrlFetcherSeiunTranslatedNovel().RESOLVE_ISFDB_ORIGINAL_WORKS)

  def test_nonfiction_includes_2021_winner_and_keeps_supplied_titles_and_credits(self):
    fetcher = UrlFetcherSeiunNonfiction()
    calls = []
    def fetch(url, **options):
      calls.append((url, options))
      self.assertEqual(fetcher.URL, url)
      return '''<table><tr><td colspan="3">2021</td></tr>
        <tr><td>Win</td><td><a href="/cgi-bin/title.cgi?3632181">\u65e5\u672c\u8a9e\u306e\u672c</a>
        (translation of <a href="/cgi-bin/title.cgi?3570">An Original Work</a>)</td>
        <td>\u702c\u540d\u79c0\u660e</td></tr>
        <tr><td>Nomination</td><td>Another Nonfiction Work</td><td>Another Writer</td></tr>
        <tr><td colspan="3">--- Finalists ---</td></tr>
        <tr><td>*</td><td>Finalist Nonfiction Work</td><td>Finalist Writer</td></tr></table>'''
    parsed = fetcher.fetch_and_parse(fetch, disable_fallbacks=True)
    self.assertEqual([(fetcher.URL, {'transport': 'camoufox'})], calls)
    self.assertEqual('\u65e5\u672c\u8a9e\u306e\u672c', parsed['entries'][0]['title'])
    self.assertEqual(['\u702c\u540d\u79c0\u660e'], parsed['entries'][0]['authors'])
    self.assertEqual(('2021', 'winner'),
      (parsed['entries'][0]['award_year'], parsed['entries'][0]['result']))
    self.assertEqual(3, len(parsed['entries']))
    self.assertEqual(['winner', 'nominee', 'nominee'], [e['result'] for e in parsed['entries']])
    self.assertTrue(all('original_work' not in entry for entry in parsed['entries']))
    self.assertEqual([], parsed['notes'])
    self.assertFalse(parsed['match_series'])

  def test_shared_year_fetch_progress_advances_after_success_and_failure(self):
    fetcher = UrlFetcherLocusAnnualSFNovel()
    progress = []
    def fetch(url):
      if url.endswith('2024'):
        raise RuntimeError('unavailable')
      return '''<table><tr><th>Year</th><th>Level</th><th>Title</th><th>Author</th></tr>
        <tr><td>2025</td><td>Win</td><td>A Work</td><td>A Writer</td></tr></table>'''
    parsed = fetcher.parse_isfdb_award_type(
      '<a href="/cgi-bin/ay.cgi?28+2024">2024</a>'
      '<a href="/cgi-bin/ay.cgi?28+2025">2025</a>', fetcher.isfdb_url(),
      fetch_url=fetch, progress=lambda *args: progress.append(args))
    self.assertEqual([(0, 2), (1, 2), (1, 2), (2, 2)], [row[:2] for row in progress])
    self.assertIn('2024 (1 of 2 years)', progress[0][2])
    self.assertIn('2025 (2 of 2 years)', progress[2][2])
    self.assertEqual(1, len(parsed['notes']))
    self.assertEqual(['A Work'], [row['title'] for row in parsed['entries']])

  def test_shared_year_progress_cancellation_does_not_start_request(self):
    fetcher = UrlFetcherLocusAnnualSFNovel()
    fetch = Mock()
    def cancelled(*args):
      raise ImportCancelledError('cancelled')
    with self.assertRaises(ImportCancelledError):
      fetcher.parse_isfdb_award_type('<a href="/cgi-bin/ay.cgi?28+2024">2024</a>',
        fetcher.isfdb_url(), fetch_url=fetch, progress=cancelled)
    fetch.assert_not_called()

  def test_seiun_comic_uses_isfdb_as_sole_primary(self):
    comic = UrlFetcherSeiunComic()
    self.assertEqual([('ISFDB', comic.URL, 0)], [
      (a.label, a.url, a.source_rank) for a in comic.source_attempts()])
    self.assertIsInstance(comic.source_attempts()[0], ISFDBSourceAttempt)
    self.assertEqual('https://www.isfdb.org/cgi-bin/award_category.cgi?1236+1', comic.URL)
    self.assertNotIn('SFADB', [choice['label'] for choice in comic.source_choices()])

  def test_comic_year_finalists_require_section_and_reset_at_category_boundaries(self):
    fetcher = UrlFetcherSeiunComic()
    year = 'https://www.isfdb.org/cgi-bin/ay.cgi?61+2022'
    def fetch(url, **options):
      if url == fetcher.URL:
        return '<a href="/cgi-bin/ay.cgi?61+2022">2022</a>'
      return '''<title>2022 Seiun Awards</title><table>
        <tr><td colspan="3"><a href="/cgi-bin/award_category.cgi?1236">Best Comics</a></td></tr>
        <tr><td>*</td><td>Unclassified Comic</td><td>A Writer</td></tr>
        <tr><td>Win</td><td>Comic Winner</td><td>A Writer</td></tr>
        <tr><td colspan="3">--- Finalists -------</td></tr>
        <tr><td><a href="/cgi-bin/award_details.cgi?1">*</a><div class="tooltip">
          <sup class="mouseover">&#9432;</sup><span class="tooltiptext">For the manga series.</span>
          </div></td><td>Comic Finalist</td><td>Another Writer</td></tr>
        <tr><td colspan="3">--- Not a Result Section ---</td></tr>
        <tr><td>*</td><td>Unknown Status</td><td>A Writer</td></tr>
        <tr><td colspan="3"><a href="/cgi-bin/award_category.cgi?625">Best Japanese Long Story</a></td></tr>
        <tr><td>Win</td><td>Japanese Work</td><td>A Writer</td></tr>
        <tr><td colspan="3">--- Finalists -------</td></tr>
        <tr><td>*</td><td>Japanese Finalist</td><td>A Writer</td></tr>
        <tr><td colspan="3"><a href="/cgi-bin/award_category.cgi?1236">Best Comics</a></td></tr>
        <tr><td>*</td><td>Leaked Status</td><td>A Writer</td></tr></table>'''
    parsed = fetcher.create_isfdb_parser().parse(
      fetch(year), year, fetcher.NAME, fetcher.CATEGORY, fetcher.isfdb_category_aliases())
    self.assertEqual([('Comic Winner', 'winner'), ('Comic Finalist', 'nominee')], [
      (row['title'], row['result']) for row in parsed['entries']])
    self.assertEqual([], parsed['notes'])
    self.assertEqual([['A Writer'], ['Another Writer']], [r['authors'] for r in parsed['entries']])

  def test_comic_complete_category_import_never_fetches_year_navigation(self):
    fetcher = UrlFetcherSeiunComic()
    calls = []
    progress = []
    def fetch(url, **options):
      calls.append((url, options))
      return '''<a href="/cgi-bin/ay.cgi?61+2022">2022</a><table>
        <tr><td colspan="3">2021</td></tr>
        <tr><td>Win</td><td>Comic Winner</td><td>A Writer</td></tr>
        <tr><td colspan="3">2022</td></tr>
        <tr><td colspan="3">--- Finalists ---</td></tr>
        <tr><td>*</td><td>Comic Finalist</td><td>Another Writer</td></tr></table>'''
    parsed = fetcher.fetch_and_parse(fetch, disable_fallbacks=True,
      progress=lambda *args: progress.append(args))
    self.assertEqual([(fetcher.URL, {'transport': 'camoufox'})], calls)
    self.assertEqual(['Comic Winner', 'Comic Finalist'], [r['title'] for r in parsed['entries']])
    self.assertEqual([], parsed['notes'])
    self.assertFalse(parsed['match_series'])
    self.assertEqual(fetcher.URL, parsed['source']['url'])
    self.assertEqual((1, 1), progress[-1][:2])

  def test_seiun_japanese_primary_is_isfdb_and_translated_sources_stay_unchanged(self):
    japanese = UrlFetcherSeiunJapaneseLongWork()
    self.assertEqual([('ISFDB', japanese.URL, 0)], [
      (a.label, a.url, a.source_rank) for a in japanese.source_attempts()])
    self.assertIsInstance(japanese.source_attempts()[0], ISFDBSourceAttempt)
    self.assertEqual(('https://www.isfdb.org/cgi-bin/awardtype.cgi?61',), japanese.FETCH_URLS)
    self.assertEqual([('SFADB', 0), ('ISFDB (original works)', 1)], [
      (a.label, a.source_rank) for a in UrlFetcherSeiunTranslatedNovel().source_attempts()])
    self.assertNotIn('SFADB', [choice['label'] for choice in japanese.source_choices()])

  def test_seiun_translated_resolves_originals_for_explicit_and_automatic_selection(self):
    fetcher = UrlFetcherSeiunTranslatedNovel()
    def fetch(url, **options):
      if 'sfadb.com' in url:
        raise RuntimeError('SFADB unavailable')
      if url == fetcher.isfdb_url():
        return '''<table><tr><td colspan="3">1970</td></tr>
        <tr><td>Win</td><td><a href="/cgi-bin/title.cgi?2043710">\u7d50\u6676\u4e16\u754c</a>
        (translation of <a href="/cgi-bin/title.cgi?3570">The Crystal World</a>)</td>
        <td>J\u30fbG\u30fb\u30d0\u30e9\u30fc\u30c9</td></tr></table>'''
      return '''<div class="ContentBox"><b>Title:</b> The Crystal World
        <span class="recordID"><b>Title Record # </b>3570</span><br/>
        <b>Author:</b><a href="/cgi-bin/ea.cgi?259">J. G. Ballard</a><br/>
        <b>Language:</b>English</div>'''
    for choice in (1, 'automatic'):
      with self.subTest(choice=choice):
        parsed = fetcher.fetch_and_parse(fetch, source_choice=choice)
        self.assertEqual('The Crystal World', parsed['entries'][0]['title'])
        self.assertEqual(['J. G. Ballard'], parsed['entries'][0]['authors'])
        self.assertEqual('\u7d50\u6676\u4e16\u754c', parsed['entries'][0]['translated_editions'][0]['title'])
        self.assertEqual([] if choice == 1 else ['SFADB failed: SFADB unavailable'], parsed['notes'])
    self.assertIn({'label': 'ISFDB (original works)', 'value': 1}, fetcher.source_choices())

  def test_seiun_japanese_primary_fetches_linked_year_and_filters_other_categories(self):
    fetcher = UrlFetcherSeiunJapaneseLongWork()
    year = 'https://www.isfdb.org/cgi-bin/ay.cgi?61+2025'
    calls = []
    def fetch(url, **options):
      calls.append((url, options))
      if url == fetcher.URL:
        return '<a href="/cgi-bin/ay.cgi?61+2025">2025</a>'
      return '''<title>2025 Seiun Awards</title><table>
        <tr><td colspan="3"><a href="/cgi-bin/award_category.cgi?1">Best Japanese Long Story</a></td></tr>
        <tr><td>Win</td><td><a href="/cgi-bin/ea.cgi?1">Japanese Work</a></td><td>A Writer</td></tr>
        <tr><td colspan="3"><a href="/cgi-bin/award_category.cgi?2">Best Translated Long Story</a></td></tr>
        <tr><td>Win</td><td>Foreign Work</td><td>Another Writer</td></tr></table>'''
    parsed = fetcher.fetch_and_parse(fetch, disable_fallbacks=True)
    self.assertEqual(['Japanese Work'], [row['title'] for row in parsed['entries']])
    self.assertEqual([], parsed['notes'])
    self.assertFalse(parsed['match_series'])
    self.assertEqual(fetcher.URL, parsed['source']['url'])
    self.assertEqual([(url, {'transport': 'camoufox'}) for url in (fetcher.URL, year)], calls)

  def test_seiun_japanese_browser_failure_retries_legacy_without_fetching_sfadb(self):
    fetcher = UrlFetcherSeiunJapaneseLongWork()
    year = 'https://www.isfdb.org/cgi-bin/ay.cgi?61+2025'
    calls = []
    def fetch(url, **options):
      calls.append((url, options))
      if options:
        raise CamoufoxSkippedError('disabled')
      if url == fetcher.URL:
        return '<a href="/cgi-bin/ay.cgi?61+2025">2025</a>'
      return '''<table><tr><th>Year</th><th>Level</th><th>Title</th><th>Author</th></tr>
        <tr><td>2025</td><td>Win</td><td>Japanese Work</td><td>A Writer</td></tr></table>'''
    parsed = fetcher.fetch_and_parse(fetch, source_choice=0)
    self.assertEqual(['Japanese Work'], [row['title'] for row in parsed['entries']])
    self.assertEqual([(url, options) for url in (fetcher.URL, year)
      for options in ({'transport': 'camoufox'}, {})], calls)

  def test_seiun_japanese_cancellation_propagates_without_legacy_retry(self):
    calls = []
    def fetch(url, **options):
      calls.append((url, options))
      raise ImportCancelledError('cancelled')
    with self.assertRaises(ImportCancelledError):
      UrlFetcherSeiunJapaneseLongWork().fetch_and_parse(fetch)
    self.assertEqual(1, len(calls))

  def test_browser_failure_retries_same_url_with_legacy(self):
    calls = []

    def fetch(url, **options):
      calls.append((url, options))
      if options:
        raise RuntimeError('browser failed')
      return 'award page'

    attempt = ISFDBSourceAttempt('ISFDB', 'url', None)
    self.assertEqual('award page', attempt.fetch_url(fetch)('url'))
    self.assertEqual([('url', {'transport': 'camoufox'}), ('url', {})], calls)

  def test_disabled_browser_and_legacy_403_remain_failure(self):
    calls = []
    blocked = HTTPError('url', 403, 'Forbidden', {}, None)

    def fetch(url, **options):
      calls.append(options)
      if options:
        raise CamoufoxSkippedError('disabled in configuration')
      raise blocked

    with self.assertRaises(HTTPError) as caught:
      ISFDBSourceAttempt('ISFDB', 'url', None).fetch_url(fetch)('url')
    self.assertIs(blocked, caught.exception)
    self.assertEqual([{'transport': 'camoufox'}, {}], calls)

  def test_invalid_rendered_page_retries_legacy_and_suppresses_browser(self):
    class Owner:
      def __init__(self):
        self.calls = []
        self.rejected = []

      def fetch(self, url, **options):
        self.calls.append(options)
        return 'challenge' if options else 'award page'

      def reject_camoufox_payload(self, reason):
        self.rejected.append(reason)

    owner = Owner()
    attempt = ISFDBSourceAttempt(
      'ISFDB', 'url', None, page_validator=lambda payload, url: payload == 'award page')
    self.assertEqual('award page', attempt.fetch_url(owner.fetch)('url'))
    self.assertEqual([{'transport': 'camoufox'}, {}], owner.calls)
    self.assertEqual(1, len(owner.rejected))

  def test_cancelled_browser_never_retries_legacy(self):
    calls = []

    def fetch(url, **options):
      calls.append(options)
      raise ImportCancelledError('cancelled')

    with self.assertRaises(ImportCancelledError):
      ISFDBSourceAttempt('ISFDB', 'url', None).fetch_url(fetch)('url')
    self.assertEqual([{'transport': 'camoufox'}], calls)

  def test_aurealis_browser_rejection_recovers_every_category(self):
    fetcher = UrlFetcherAurealisSFNovel()
    fetcher.ISFDB_CATEGORY_IDS = (50, 51)
    urls = fetcher.isfdb_urls()
    calls = []

    def fetch(url, **options):
      calls.append((url, options))
      if options:
        return '<html><title>Verification required</title></html>'
      index = urls.index(url) + 1
      return f'''<table><tr><th>Year</th><th>Level</th><th>Title</th><th>Author</th></tr>
        <tr><td>2025</td><td>Win</td><td>Book {index}</td><td>Writer</td></tr></table>'''

    parsed = fetcher.fetch_and_parse(fetch, source_choice=1)
    self.assertEqual(['Book 1', 'Book 2'], [row['title'] for row in parsed['entries']])
    self.assertEqual([], parsed['notes'])
    self.assertEqual([
      item for url in urls for item in ((url, {'transport': 'camoufox'}), (url, {}))
    ], calls)

  def test_shared_isfdb_attempt_wraps_overview_and_linked_year(self):
    fetcher = UrlFetcherLocusAnnualSFNovel()
    overview = fetcher.isfdb_url()
    year = 'https://www.isfdb.org/cgi-bin/ay.cgi?28+2025'
    calls = []

    def fetch(url, **options):
      calls.append((url, options))
      if url == overview:
        return '<a href="/cgi-bin/ay.cgi?28+2025">2025</a>'
      return '''<table><tr><th>Year</th><th>Level</th><th>Title</th><th>Author</th></tr>
        <tr><td>2025</td><td>Win</td><td>A Book</td><td>A Writer</td></tr></table>'''

    parsed = fetcher.fetch_and_parse(fetch, source_choice=1)
    self.assertEqual(['A Book'], [row['title'] for row in parsed['entries']])
    self.assertEqual([(url, {'transport': 'camoufox'}) for url in (overview, year)], calls)

  def test_shared_year_cancellation_does_not_return_partial_import(self):
    fetcher = UrlFetcherLocusAnnualSFNovel()

    def fetch(url):
      raise ImportCancelledError('cancelled during year fetch')

    with self.assertRaises(ImportCancelledError):
      fetcher.parse_isfdb_award_type(
        '<a href="/cgi-bin/ay.cgi?28+2025">2025</a>', fetcher.isfdb_url(), fetch_url=fetch)

  def test_isfdb_browser_uses_correct_label_and_excludes_site_from_warmup(self):
    core = support.main.ListSwitchboardCore(None, lambda **kwargs: None)
    with support.patch.dict(support.main.prefs, {
        'debug_browser_fallback_level': 0, 'camoufox_first_use_confirmed': True}), \
        support.patch.object(support.main, 'camoufox_capability',
          return_value=(True, (9, 18, 0), 'API available')), \
        support.patch.object(support.main, 'CamoufoxTransport') as factory:
      factory.return_value.fetch.return_value = 'award page'
      self.assertEqual('award page', core.fetch_url(
        'https://www.isfdb.org/cgi-bin/award_category.cgi?50+1', transport='camoufox'))
      self.assertEqual('ISFDB', factory.call_args.kwargs['source_name'])
      self.assertFalse(factory.call_args.kwargs['check_challenges'])
      self.assertIn('isfdb.org', factory.call_args.kwargs['warmup_excluded_domains'])
      core.close_camoufox_transport()
      factory.return_value.close.assert_called_once()


if __name__ == '__main__':
  unittest.main()
