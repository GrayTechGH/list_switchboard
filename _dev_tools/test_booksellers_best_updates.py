import copy
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError,ImportCancelledError
from parser.booksellers_best import BOOKSELLERS_BEST_CDX_URLS
from parser.booksellers_best_updates import capture_index
from storage import build_import_cache_data
from url_fetcher.booksellers_best import UrlFetcherBooksellersBestAward


class BooksellersBestUpdateTests(unittest.TestCase):

  def setUp(self):
    clock = patch('wayback_policy.REQUEST_CLOCK')
    clock.start()
    self.addCleanup(clock.stop)
    native = patch('url_fetcher.booksellers_best.calibre_https_fetch', None)
    native.start()
    self.addCleanup(native.stop)
    self.recipe=UrlFetcherBooksellersBestAward();self.calls=[];self.failures={};self.overrides={}
    self.first='http://www.gdrwa.org/contests.html'
    self.second='http://www.gdrwa.org/winners2012.html'
    self.indexes={BOOKSELLERS_BEST_CDX_URLS[0]:[['20120627055544',self.first,'200','text/html','a']],
      BOOKSELLERS_BEST_CDX_URLS[1]:[],
      BOOKSELLERS_BEST_CDX_URLS[2]:[['20130101000000',self.second,'200','text/html','b']]}
    self.pages={self.url('20120627055544',self.first):self.page('Finalists','Old Book'),
      self.url('20130101000000',self.second):self.page('Winners','Winner Book')}

  def url(self,stamp,original):return f'https://web.archive.org/web/{stamp}id_/{original}'

  def page(self,result,title,author='Example Writer'):
    return f'''<html><head><title>2012 Booksellers' Best Award {result}</title></head>
      <body><h3>2012 Booksellers' Best Award</h3><h1>{result}</h1>
      <h4>Traditional</h4><p>{title} - {author}</p></body></html>'''

  def fetch(self,url):
    self.calls.append(url)
    if url in self.failures:raise self.failures[url]
    if url in self.overrides:return self.overrides[url]
    if url in self.indexes:return json.dumps([['timestamp','original','statuscode','mimetype','digest']]+self.indexes[url])
    return self.pages[url]

  def parse(self,old=None,incremental=None):
    return self.recipe.fetch_and_parse(self.fetch,cached_parsed=old,
      incremental_update=(old is not None) if incremental is None else incremental)

  def cache(self,parsed):return build_import_cache_data(self.recipe.source_id,parsed)

  def test_missing_capture_and_repeat_preserve_entries_with_fewer_fetches(self):
    full=self.parse();self.assertEqual(5,len(self.calls))
    old=without_unit(self.cache(full),next(iter(self.pages)))
    self.assertLess(len(old['entries']),len(full['entries']))
    self.calls.clear();updated=self.parse(old)
    self.assertEqual(full['entries'],updated['entries']);self.assertEqual(4,len(self.calls))
    self.calls.clear();repeated=self.parse(self.cache(updated))
    self.assertEqual(full['entries'],repeated['entries']);self.assertEqual(list(BOOKSELLERS_BEST_CDX_URLS),self.calls)

  def test_changed_digest_replaces_capture_corrections_and_removals(self):
    old=self.cache(self.parse());url=next(iter(self.pages))
    self.indexes[BOOKSELLERS_BEST_CDX_URLS[0]][0][-1]='changed'
    self.pages[url]=self.page('Finalists','Corrected Book')
    self.calls.clear();updated=self.parse(old)
    self.assertIn(url,self.calls);self.assertNotIn('Old Book',[r['title'] for r in updated['entries']])
    self.assertEqual(self.parse()['entries'],updated['entries'])

  def test_added_capture_and_removed_discovery_follow_fresh_indexes(self):
    old=self.cache(self.parse());new=self.url('20140101000000','http://gdrwa.org/winners2013.html')
    self.indexes[BOOKSELLERS_BEST_CDX_URLS[2]].append(['20140101000000','http://gdrwa.org/winners2013.html','200','text/html','c'])
    self.pages[new]=self.page('Winners','New Year Book').replace('2012','2013')
    self.indexes[BOOKSELLERS_BEST_CDX_URLS[0]]=[]
    self.calls.clear();updated=self.parse(old)
    self.assertIn(new,self.calls);self.assertNotIn('Old Book',[r['title'] for r in updated['entries']])
    self.assertEqual(self.parse()['entries'],updated['entries'])

  def test_index_failure_preserves_own_history_pending_then_recovers(self):
    full=self.parse();old=self.cache(full);key=BOOKSELLERS_BEST_CDX_URLS[0]
    self.failures[key]=RuntimeError('offline');self.calls.clear();updated=self.parse(old)
    self.assertEqual(full['entries'],updated['entries']);self.assertEqual([key],updated['incremental_state']['discovery']['pending_indexes'])
    unit=updated['incremental_state']['units'][next(iter(self.pages))]
    self.assertFalse(unit['complete']);self.failures.clear();self.calls.clear()
    self.assertFalse(updated['incremental_state']['units'][key]['complete'])
    repaired=self.parse(self.cache(updated));self.assertIn(next(iter(self.pages)),self.calls)
    self.assertEqual([],repaired['incremental_state']['discovery']['pending_indexes'])

  def test_capture_failure_retains_rows_and_is_retried(self):
    full=self.parse();old=self.cache(full);url=next(iter(self.pages))
    self.indexes[BOOKSELLERS_BEST_CDX_URLS[0]][0][-1]='changed';self.failures[url]=RuntimeError('offline')
    updated=self.parse(old);self.assertEqual(full['entries'],updated['entries'])
    self.assertFalse(updated['incremental_state']['units'][url]['complete'])
    self.failures.clear();self.calls.clear();self.parse(self.cache(updated));self.assertIn(url,self.calls)

  def test_rules_capture_is_reusable_but_challenges_are_pending(self):
    url=next(iter(self.pages));self.pages[url]='<html><body><h1>GDRWA Booksellers Best</h1><p>Entry form and eligibility</p></body></html>'
    full=self.parse();self.assertTrue(full['incremental_state']['units'][url]['complete'])
    self.calls.clear();self.parse(self.cache(full));self.assertNotIn(url,self.calls)
    self.indexes[BOOKSELLERS_BEST_CDX_URLS[0]][0][-1]='changed';self.pages[url]='<html><p>Access denied</p></html>'
    updated=self.parse(self.cache(full));self.assertFalse(updated['incremental_state']['units'][url]['complete'])

  def test_unparseable_result_retains_roster_instead_of_certifying_empty(self):
    full=self.parse();old=self.cache(full);url=next(iter(self.pages))
    self.indexes[BOOKSELLERS_BEST_CDX_URLS[0]][0][-1]='changed'
    self.pages[url]=self.page('Finalists','Unparseable').replace('Unparseable - Example Writer','broken')
    updated=self.parse(old);self.assertEqual(full['entries'],updated['entries'])
    self.assertFalse(updated['incremental_state']['units'][url]['complete'])

  def test_source_projection_restores_finalist_after_winner_capture_removed(self):
    urls=list(self.pages);self.pages[urls[0]]=self.page('Finalists','Shared Book','First Writer and Second Writer')
    self.pages[urls[1]]=self.page('Winners','Shared Book','First Writer and Second Writer')
    full=self.parse();self.assertEqual(1,len(full['entries']));self.assertEqual('winner',full['entries'][0]['result'])
    self.indexes[BOOKSELLERS_BEST_CDX_URLS[2]]=[]
    self.calls.clear();updated=self.parse(self.cache(full))
    self.assertEqual('shortlisted',updated['entries'][0]['result'])
    self.assertEqual(self.parse()['entries'],updated['entries'])

  def test_legacy_wrong_scope_and_complete_refresh_read_captures(self):
    old=self.cache(self.parse());legacy=copy.deepcopy(old);legacy.pop('incremental_state')
    wrong=copy.deepcopy(old);wrong['incremental_state']['source_key']='other'
    for candidate,incremental in ((legacy,True),(wrong,True),(old,False)):
      self.calls.clear();self.parse(candidate,incremental)
      self.assertEqual(5,len(self.calls))

  def test_bad_indexes_retain_history_and_do_not_request_untrusted_hosts(self):
    old=self.cache(self.parse());key=BOOKSELLERS_BEST_CDX_URLS[0]
    for bad in ('[]','{}','<html>challenge</html>',json.dumps([['timestamp','original','statuscode','mimetype','digest'],
        ['20120627055544','http://evil.example/contests.html','200','text/html','a']])):
      self.overrides[key]=bad;self.calls.clear();updated=self.parse(old)
      self.assertEqual(old['entries'],updated['entries']);self.assertIn(key,updated['incremental_state']['discovery']['pending_indexes'])
      self.assertFalse(any('evil' in url for url in self.calls))

  def test_cancellation_and_browser_requirement_propagate_from_indexes_and_captures(self):
    for url in (BOOKSELLERS_BEST_CDX_URLS[0],next(iter(self.pages))):
      for cls in (ImportCancelledError,CamoufoxRequiredError):
        self.failures={url:cls('stop')}
        with self.assertRaises(cls):self.parse()

  def test_no_digest_capture_is_always_refetched(self):
    self.indexes[BOOKSELLERS_BEST_CDX_URLS[0]][0][-1]='-'
    old=self.cache(self.parse());self.calls.clear();self.parse(old)
    self.assertIn(next(iter(self.pages)),self.calls)

  def test_same_capture_across_indexes_is_fetched_once(self):
    self.indexes[BOOKSELLERS_BEST_CDX_URLS[1]]=copy.deepcopy(self.indexes[BOOKSELLERS_BEST_CDX_URLS[0]])
    self.parse();self.assertEqual(1,self.calls.count(next(iter(self.pages))))

  def test_quoted_titles_multiple_paragraphs_and_h6_roster(self):
    first,second=list(self.pages)
    self.pages[first]='''<html><title>2014 Booksellers Best Finalists</title><body>
      <h3>2014 Booksellers Best Award Finalists</h3><h4>TRADITIONAL</h4>
      <p class="newsdate">"Last Chance Proposal," Barbara DeLeo<br/>(Entangled Bliss, Editor Name)</p>
      <p class="newsdate">"Another Book," Second Writer<br/>(Publisher, Editor Name)</p>
      </body></html>'''
    self.pages[second]='''<html><title>2016 Booksellers Best Finalists</title><body>
      <h3>2016 Booksellers Best Award Finalists</h3><h4>SHORT CONTEMPORARY ROMANCE</h4>
      <h6><em>Arresting Developments</em> by Lena Diaz<br/>
      <em>The Engagement Game</em> by Jenny Holiday</h6></body></html>'''
    # The URL year remains authoritative for an explicitly annual winner URL.
    parsed=self.parse();self.assertEqual(4,len(parsed['entries']))
    self.assertEqual({'Last Chance Proposal','Another Book','Arresting Developments','The Engagement Game'},
      {r['title'] for r in parsed['entries']})

  def test_rules_mentions_of_finalists_and_winners_do_not_create_roster(self):
    url=next(iter(self.pages));self.pages[url]='''<html><title>BBA Entry Form</title><body>
      <h1>Booksellers Best Award</h1><p>Entry form and eligibility. Winners and finalists will receive certificates.</p></body></html>'''
    full=self.parse();self.assertTrue(full['incremental_state']['units'][url]['complete'])

  def test_official_wildcard_index_skips_known_pdf_and_word_entry_forms(self):
    key = BOOKSELLERS_BEST_CDX_URLS[1]
    self.indexes[key] = [
      ['20140305064523','http://www.gdrwa.org/BBA_entryform2014.pdf','200','application/pdf','pdf'],
      ['20140305064731','http://www.gdrwa.org/BBA_entryform2014.doc','200','application/msword','doc']]
    parsed = self.parse()
    self.assertEqual(2, len(parsed['entries']))
    self.assertTrue(parsed['incremental_state']['units'][key]['complete'])
    self.assertFalse(any('entryform' in url for url in self.calls))

  def test_non_html_result_and_untrusted_form_hosts_still_reject_index(self):
    header = ['timestamp','original','statuscode','mimetype','digest']
    for original, mime in [('http://www.gdrwa.org/winners2014.pdf', 'application/pdf'),
        ('http://evil.example/BBA_entryform2014.pdf', 'application/pdf')]:
      with self.assertRaises(ValueError):
        capture_index(self.recipe.parser(), json.dumps([header,
          ['20140305064523', original, '200', mime, 'digest']]))

  def test_canonical_cdx_urls_and_fetcher_identity_are_shared(self):
    self.assertEqual(BOOKSELLERS_BEST_CDX_URLS[0], self.recipe.URL)
    self.assertTrue(all('/cdx/search/cdx?' in url and 'gzip=false' in url
      for url in BOOKSELLERS_BEST_CDX_URLS))

  def test_native_https_recovers_same_wayback_capture_with_fresh_agent(self):
    url = next(iter(self.pages))
    def failed(_url): raise ValueError('gzip stream has incorrect magic bytes')
    with patch('url_fetcher.booksellers_best.calibre_https_fetch', return_value=b'<html>GDRWA</html>') as native, \
        patch('url_fetcher.booksellers_best.random_user_agent', side_effect=['Agent One', 'Agent Two']):
      self.assertEqual(b'<html>GDRWA</html>', self.recipe.fetch_url(failed, url))
      self.recipe.fetch_url(failed, url)
      self.assertEqual(url, native.call_args.args[0])
      self.assertEqual('identity', native.call_args.kwargs['headers']['Accept-Encoding'])
      self.assertEqual(['Agent One', 'Agent Two'],
        [call.kwargs['headers']['User-Agent'] for call in native.call_args_list])

  def test_failed_native_transport_recovers_through_same_url_legacy(self):
    with patch('url_fetcher.booksellers_best.calibre_https_fetch', side_effect=OSError('native failed')) as native, \
        patch('url_fetcher.booksellers_best.random_user_agent', return_value='Agent'):
      self.assertEqual('legacy', self.recipe.fetch_url(lambda _url: 'legacy', self.recipe.URL))
      self.assertEqual(self.recipe.URL, native.call_args.args[0])

  def test_cdx_timeout_budget_is_shared_by_native_and_legacy_only_for_indexes(self):
    legacy = []
    def fetch(url, **kwargs):
      legacy.append((url, kwargs))
      return 'page'
    with patch('url_fetcher.booksellers_best.calibre_https_fetch', side_effect=OSError('timeout')) as native, \
        patch('url_fetcher.booksellers_best.random_user_agent', return_value='Agent'):
      self.recipe.fetch_url(fetch, self.recipe.URL)
      self.assertEqual(60, native.call_args.kwargs['timeout'])
      self.assertEqual([(self.recipe.URL, {'timeout': 60})], legacy)
      legacy.clear()
      capture = next(iter(self.pages))
      self.recipe.fetch_url(fetch, capture)
      self.assertEqual(30, native.call_args.kwargs['timeout'])
      self.assertEqual([(capture, {})], legacy)
    self.assertIsNone(self.recipe.request_timeout('https://example.org/cdx/search/cdx'))
    self.assertIsNone(self.recipe.request_timeout('http://web.archive.org/cdx/search/cdx'))

  def test_native_transport_is_scoped_and_propagates_critical_errors(self):
    with patch('url_fetcher.booksellers_best.calibre_https_fetch') as native, \
        patch('url_fetcher.booksellers_best.random_user_agent', return_value='Agent'):
      for error in (ImportCancelledError('cancel'), CamoufoxRequiredError('required')):
        def fail(_url): raise error
        with self.assertRaises(type(error)):
          self.recipe.fetch_url(fail, self.recipe.URL)
      self.assertEqual(2, native.call_count)
      native.reset_mock()
      for url in ('https://example.com/web/page', 'http://web.archive.org/web/page',
          'https://web.archive.org/account/'):
        def fail(_url): raise OSError('failed')
        with self.assertRaises(OSError):
          self.recipe.fetch_url(fail, url)
      native.assert_not_called()

  def test_native_failure_and_oversized_response_do_not_certify_payload(self):
    def fail(_url): raise OSError('legacy failed')
    with patch('url_fetcher.booksellers_best.random_user_agent', return_value='Agent'):
      with patch('url_fetcher.booksellers_best.calibre_https_fetch', side_effect=OSError('native failed')):
        with self.assertRaisesRegex(OSError, 'legacy failed'):
          self.recipe.fetch_url(fail, self.recipe.URL)
      with patch('url_fetcher.booksellers_best.calibre_https_fetch', return_value=b'x'*(16*1024*1024+1)):
        with self.assertRaisesRegex(OSError, 'legacy failed'):
          self.recipe.fetch_url(fail, self.recipe.URL)

  def test_native_critical_errors_do_not_attempt_legacy(self):
    for error in (ImportCancelledError('cancel'), CamoufoxRequiredError('required')):
      with patch('url_fetcher.booksellers_best.calibre_https_fetch', side_effect=error), \
          patch('url_fetcher.booksellers_best.random_user_agent', return_value='Agent'):
        calls = []
        with self.assertRaises(type(error)):
          self.recipe.fetch_url(lambda url: calls.append(url), self.recipe.URL)
        self.assertEqual([], calls)

  def test_archive_requests_and_next_import_share_spacing_with_ui_sleep(self):
    from wayback_policy import WaybackRequestClock
    now = [10.0]
    clock = WaybackRequestClock(clock=lambda: now[0])
    delays = []
    def pause(delay):
      delays.append(delay)
      now[0] += delay
    with patch('wayback_policy.REQUEST_CLOCK', clock):
      parsed = self.recipe.fetch_and_parse(self.fetch, sleep=pause)
    self.assertEqual(2, len(parsed['entries']))
    self.assertEqual([10] * (len(self.calls) - 1), delays)
    delays.clear()
    with patch('wayback_policy.REQUEST_CLOCK', clock):
      self.recipe.fetch_and_parse(self.fetch, sleep=pause,
        cached_parsed=self.cache(parsed), incremental_update=True)
    self.assertEqual([10, 10, 10], delays)

  def test_archive_spacing_cancellation_stops_before_next_network_request(self):
    from wayback_policy import WaybackRequestClock
    def cancel(_delay): raise ImportCancelledError('cancelled during archive delay')
    with patch('wayback_policy.REQUEST_CLOCK', WaybackRequestClock(clock=lambda: 10)):
      with self.assertRaises(ImportCancelledError):
        self.recipe.fetch_and_parse(self.fetch, sleep=cancel)
    self.assertEqual([self.recipe.URL], self.calls)

  def test_native_rate_limit_does_not_attempt_legacy_transport(self):
    failure = HTTPError(self.recipe.URL, 429, 'Too Many Requests', {'Retry-After': '120'}, None)
    calls = []
    with patch('url_fetcher.booksellers_best.calibre_https_fetch', side_effect=failure) as native, \
        patch('url_fetcher.booksellers_best.random_user_agent', return_value='Agent'):
      with self.assertRaises(HTTPError) as raised:
        self.recipe.fetch_url(lambda url: calls.append(url), self.recipe.URL)
    self.assertIs(failure, raised.exception)
    self.assertEqual([], calls)
    self.assertEqual(1, native.call_count)

  def test_rate_limited_index_defers_batch_retains_cache_and_next_import_retries(self):
    full = self.parse()
    self.calls.clear()
    self.failures[self.recipe.URL] = HTTPError(self.recipe.URL, 429, 'Too Many Requests', {}, None)
    limited = self.parse(self.cache(full))
    self.assertEqual(full['entries'], limited['entries'])
    self.assertEqual([self.recipe.URL], self.calls)
    self.assertEqual(list(BOOKSELLERS_BEST_CDX_URLS), limited['incremental_state']['discovery']['pending_indexes'])
    self.assertTrue(all(not unit['complete'] for unit in limited['incremental_state']['units'].values()))
    self.assertTrue(any('deferred' in note for note in limited['notes']))
    self.failures.clear()
    self.calls.clear()
    recovered = self.parse(self.cache(limited))
    self.assertEqual(full['entries'], recovered['entries'])
    self.assertEqual(5, len(self.calls))
    self.assertTrue(all(unit['complete'] for unit in recovered['incremental_state']['units'].values()))

  def test_rate_limited_capture_keeps_whole_rosters_without_further_requests(self):
    full = self.parse()
    for rows in self.indexes.values():
      for row in rows:
        row[-1] += '-changed'
    first = next(iter(self.pages))
    self.failures[first] = URLError(HTTPError(first, 429, 'Too Many Requests', {}, None))
    self.calls.clear()
    limited = self.parse(self.cache(full))
    self.assertEqual(full['entries'], limited['entries'])
    self.assertEqual(list(BOOKSELLERS_BEST_CDX_URLS) + [first], self.calls)
    self.assertTrue(all(not limited['incremental_state']['units'][url]['complete'] for url in self.pages))
    self.assertTrue(all(limited['incremental_state']['units'][url]['complete'] for url in BOOKSELLERS_BEST_CDX_URLS))
    self.failures.clear()
    self.assertEqual(full['entries'], self.parse(self.cache(limited))['entries'])

  def test_calibre_style_rate_limit_and_chained_errors_are_recognized(self):
    from url_fetcher.booksellers_best import archive_rate_limit
    native = ValueError('Calibre HTTP response 429')
    native.code = 429
    wrapped = OSError('outer')
    wrapped.__cause__ = native
    native.__context__ = wrapped
    self.assertIs(native, archive_rate_limit(wrapped))
    self.assertIsNone(archive_rate_limit(ValueError('Book title contains 429')))
    unavailable = HTTPError(self.recipe.URL, 503, 'Unavailable', {}, None)
    self.assertIsNone(archive_rate_limit(unavailable))

  def test_rate_limited_fresh_import_does_not_return_empty_success(self):
    self.failures[self.recipe.URL] = HTTPError(self.recipe.URL, 429, 'Too Many Requests', {}, None)
    with self.assertRaisesRegex(Exception, 'Could not fetch or parse'):
      self.parse()
    self.assertEqual([self.recipe.URL], self.calls)

  def test_mixed_contest_page_reads_only_bounded_booksellers_finalists(self):
    source = '''<html><title>GDRWA</title><body><h3>Between the Sheets</h3>
      <p>Finalists: Wrong Book by Other Writer</p><h4>TRADITIONAL</h4><p>Wrong - Wrong Writer</p>
      <h3>Booksellers' Best Award</h3><p>Books published in 2010</p>
      <table><tr><td>Greater Detroit RWA announces the finalists for the 2009 Booksellers Best Award.</td></tr></table>
      <h4>LONG CONTEMPORARY</h4><p>On My Terms \u2013 Shirley Hailstock</p>
      <h3>Between the Sheets Contest</h3><h4>TRADITIONAL</h4><p>Also Wrong - Other Writer</p>
      </body></html>'''
    rows = self.recipe.parser().parse_page_rows(source, self.recipe.DISPLAY_URL, [])
    self.assertEqual([('On My Terms', 'Shirley Hailstock', '2009', 'shortlisted')],
      [(row['title'], row['author'], row['award_year'], row['result']) for row in rows])

  def test_other_contest_without_booksellers_heading_cannot_supply_nominees(self):
    source = '<html><title>GDRWA Booksellers Best</title><body><h3>Between the Sheets</h3><p>2009 Finalists</p><h4>TRADITIONAL</h4><p>Wrong - Wrong Writer</p></body></html>'
    self.assertEqual([], self.recipe.parser().parse_page_rows(source, self.recipe.DISPLAY_URL, []))

  def mixed_year_page(self, roster='Old Winner - First Writer'):
    return f'''<html><title>GDRWA</title><body>
      <h1>2015 Booksellers' Best Award</h1><p>Entry form for books published in 2014</p>
      <h2>How to enter</h2><p>{'Rules and eligibility. ' * 180}</p>
      <h3>2014 Booksellers' Best Award</h3>
      <p>The Greater Detroit RWA is pleased to announce the winners of the 2014 Booksellers Best Award Contest.</p>
      <table><tr><td><p><strong>2014 Booksellers' Best Award Winners:</strong></p>
      <h4>Traditional</h4><p>{roster}</p></td></tr></table>
      <h5>And here are all of the Finalists:</h5>
      <table><tr><td><h4>Traditional</h4><p>{roster}</p><p>Other Finalist - Second Writer</p></td></tr></table>
      </body></html>'''

  def test_previous_year_results_below_new_year_rules_keep_year_and_stages(self):
    parser = self.recipe.parser()
    rows = parser.dedupe_rows(parser.parse_page_rows(self.mixed_year_page(), self.recipe.DISPLAY_URL, []))
    self.assertEqual({('Old Winner', '2014', 'winner'), ('Other Finalist', '2014', 'shortlisted')},
      {(row['title'], row['award_year'], row['result']) for row in rows})

  def test_malformed_previous_year_roster_cannot_be_certified_as_rules(self):
    from parser.booksellers_best_updates import validated_rows
    source = self.mixed_year_page('broken').replace('<p>Other Finalist - Second Writer</p>', '')
    with self.assertRaisesRegex(ValueError, 'usable roster'):
      validated_rows(self.recipe.parser(), source, self.recipe.DISPLAY_URL, [])

  def test_repaired_mixed_year_capture_invalidates_old_empty_certificate(self):
    old = self.cache(self.parse())
    old['incremental_state']['strategy'] = 'gdrw-immutable-captures-v2'
    url = next(iter(self.pages))
    self.pages[url] = self.mixed_year_page()
    self.calls.clear()
    updated = self.parse(old)
    self.assertIn(url, self.calls)
    self.assertEqual({'Old Winner', 'Other Finalist', 'Winner Book'}, {r['title'] for r in updated['entries']})

  def test_tied_plain_categories_and_wrapped_publishers_preserve_only_books(self):
    source = '''<html><title>2014 Booksellers Best Winners</title><body>
      <h3>2014 Booksellers Best Award</h3><h4>PARANORMAL (TIE)</h4>
      <p>"Midnight's Kiss," Donna Grant<br/>(
      St. Martin's Press Romance, Monique Patterson)</p>
      <p>"Allegiance Sworn," Kylie Griffin<br/>(Berkley Sensation, Leis Pederson)</p>
      <h4>EROTIC</h4><p>"Unforgettable," Alison Kent*<br/>(Berkley Heat, Wendy McCurdy)</p>
      </body></html>'''
    rows = self.recipe.parser().parse_page_rows(source, self.recipe.DISPLAY_URL, [])
    self.assertEqual([("Midnight's Kiss", 'Donna Grant', 'Paranormal Romance'),
      ('Allegiance Sworn', 'Kylie Griffin', 'Paranormal Romance'),
      ('Unforgettable', 'Alison Kent', 'Erotic Romance')],
      [(r['title'], r['author'], r['category']) for r in rows])

  def test_own_result_year_beats_new_cycle_rules_with_inline_winner_credits(self):
    source = '''<html><body><h3>2014 Booksellers' Best Award</h3><p>Entry form for books published in 2013</p>
      <p>The Greater Detroit RWA announces the winners of the 2013 Booksellers Best Award Contest.</p>
      <p><strong>Winners for the 2013 Booksellers Best Award</strong></p>
      <p>Traditional - The Nanny Who Saved Christmas Michelle Douglas, Editor Sally Williamson</p>
      <p>Short Contemporary - Christmas Conspiracy \ufffd Robin Perini, Editor Allison Lyons</p>
      </body></html>'''
    from parser.booksellers_best_updates import validated_rows
    rows = validated_rows(self.recipe.parser(), source, self.recipe.DISPLAY_URL, [])
    self.assertEqual([('The Nanny Who Saved Christmas', 'Michelle Douglas', '2013', 'winner'),
      ('Christmas Conspiracy', 'Robin Perini', '2013', 'winner')],
      [(r['title'], r['author'], r['award_year'], r['result']) for r in rows])

  def test_author_first_quoted_nominees_use_declared_award_year(self):
    source = '''<html><body><h3>Booksellers' Best Award</h3><p>Books published in 2006</p>
      <p><strong>2007 Booksellers' Best Award Finalists:</strong></p>
      <h4>TRADITIONAL/SWEET</h4><p>Nicola Marsh, "Wife and Mother Wanted"</p>
      <h4>SINGLE TITLE/MAINSTREAM</h4><p>Walter M. Miller, Jr., "Example Book"</p>
      <p>Susan Lyons, "Champagne Rules"</p>
      </body></html>'''
    rows = self.recipe.parser().parse_page_rows(source, self.recipe.DISPLAY_URL, [])
    self.assertEqual([('Wife and Mother Wanted', 'Nicola Marsh', '2007', 'shortlisted'),
      ('Example Book', 'Walter M. Miller, Jr.', '2007', 'shortlisted'),
      ('Champagne Rules', 'Susan Lyons', '2007', 'shortlisted')],
      [(r['title'], r['author'], r['award_year'], r['result']) for r in rows])

  def test_known_image_only_finalists_keep_explicit_html_coverage_note_on_reuse(self):
    url = next(iter(self.pages))
    self.pages[url] = '''<html><body><h1>2017 Booksellers Best Award</h1>
      <p>Below are the 2017 Booksellers Best Award finalists.</p>
      <img src="images/finalists2017.gif"/></body></html>'''
    parsed = self.parse()
    self.assertTrue(any('image-only' in note for note in parsed['notes']))
    self.assertNotIn('2017', {r['award_year'] for r in parsed['entries']})
    self.calls.clear()
    updated = self.parse(self.cache(parsed))
    self.assertNotIn(url, self.calls)
    self.assertEqual(parsed['entries'], updated['entries'])
    self.assertTrue(any('image-only' in note for note in updated['notes']))

  def test_author_before_italic_title_is_not_swapped_with_title_or_publisher(self):
    source = '''<html><title>2015 Booksellers Best Winners</title><body>
      <h3>2015 Booksellers Best Award</h3><h4>EROTIC ROMANCE</h4>
      <p>Kate Baum, <em>Funny Girl</em></p>
      <p>Walter M. Miller, Jr., <em>Example Rules</em> (Publisher, Editor)</p>
      <p>Margaret Mallory, <em>Captured by a Laird</em> (The Douglas Legacy)<br/>
      Elizabeth Michels, <em>Must Love Dukes</em></p>
      </body></html>'''
    rows = self.recipe.parser().parse_page_rows(source, self.recipe.DISPLAY_URL, [])
    self.assertEqual([('Funny Girl', 'Kate Baum'), ('Example Rules', 'Walter M. Miller, Jr.'),
      ('Captured by a Laird', 'Margaret Mallory'), ('Must Love Dukes', 'Elizabeth Michels')],
      [(r['title'], r['author']) for r in rows])

  def test_older_winners_and_current_finalists_keep_distinct_years_on_one_page(self):
    source = '''<html><body><h3>2014 Booksellers Best Award</h3>
      <p>We announce the winners of the 2013 Booksellers Best Award.</p>
      <h4>Traditional</h4><p>Older Winner - First Writer</p>
      <p><strong>2014 Booksellers Best Award Finalists:</strong></p>
      <h4>Traditional</h4><p>Current Nominee - Second Writer</p></body></html>'''
    rows = self.recipe.parser().parse_page_rows(source, self.recipe.DISPLAY_URL, [])
    self.assertEqual([('Older Winner', '2013', 'winner'), ('Current Nominee', '2014', 'shortlisted')],
      [(r['title'], r['award_year'], r['result']) for r in rows])


if __name__=='__main__':unittest.main()
