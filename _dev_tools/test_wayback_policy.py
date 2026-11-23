"""Site-wide timing across source paths, transports, redirects and imports."""
from datetime import datetime, timezone
from email.utils import format_datetime
from io import BytesIO
from email.message import Message
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import BaseHandler, HTTPHandler, Request, build_opener
from urllib.response import addinfourl

from _dev_tools import test_import_matching
import main
from transport import wayback as policy
from url_fetcher import booksellers_best


URL = 'https://web.archive.org/web/20090101000000id_/http://example.org/'


class WaybackPolicyTests(unittest.TestCase):

  def setUp(self):
    self.now = 0.0
    self.delays = []
    self.clock = policy.WaybackRequestClock(interval=3, clock=lambda: self.now, wall_clock=lambda: 1000)
    mock = patch.object(policy, 'REQUEST_CLOCK', self.clock)
    mock.start()
    self.addCleanup(mock.stop)

  def pause(self, delay):
    self.delays.append(delay)
    self.now += delay

  def test_default_spacing_is_conservative_after_live_rate_limit(self):
    clock = policy.WaybackRequestClock(clock=lambda: self.now)
    clock.wait(URL, self.pause)
    clock.wait(URL, self.pause)
    self.assertEqual([10], self.delays)

  def test_exact_host_and_scheme_only(self):
    self.assertTrue(policy.is_wayback_url(URL))
    self.assertTrue(policy.is_wayback_url('http://WEB.ARCHIVE.ORG/cdx'))
    self.assertTrue(policy.is_wayback_url('https://web.archive.org./web/123/'))
    for url in ('https://archive.org/', 'https://web.archive.org.evil.example/',
        'https://example.com/web.archive.org/', 'ftp://web.archive.org/a'):
      policy.wait_for_wayback(url, self.pause)
    self.assertEqual([], self.delays)
    self.assertEqual(0, self.clock.next_request)

  def test_different_sources_and_new_imports_share_one_clock(self):
    for url in (URL, 'https://web.archive.org/cdx/search/cdx?url=gdrwa.org',
        'http://web.archive.org/web/123/http://reddit.com/', URL):
      policy.wait_for_wayback(url, self.pause)
    self.assertEqual([3, 3, 3], self.delays)

  def test_native_failure_and_legacy_fallback_are_separate_paced_attempts(self):
    recipe = booksellers_best.UrlFetcherBooksellersBestAward()
    recipe._wayback_sleep = self.pause
    calls = []
    def native(url, **kwargs):
      calls.append(('native', self.now))
      self.assertEqual(0, kwargs['max_redirects'])
      raise OSError('failed')
    def legacy(url):
      calls.append(('legacy', self.now))
      return 'page'
    with patch.object(booksellers_best, 'calibre_https_fetch', native), \
        patch.object(booksellers_best, 'random_user_agent', return_value='Calibre Agent'):
      self.assertEqual('page', recipe.fetch_url(legacy, URL))
    self.assertEqual([('native', 0), ('legacy', 3)], calls)

  def test_core_and_native_fallback_share_clock_without_double_reservation(self):
    calls = []
    class Reply(BytesIO):
      headers = {}
    class Browser:
      def add_handler(inner, handler): inner.handler = handler
      def open(inner, url, timeout=30):
        inner.handler.https_request(Request(url))
        calls.append(('legacy', self.now))
        return Reply(b'<html>OK</html>')
    browser = Browser()
    core = object.__new__(main.ListSwitchboardCore)
    core.calibre_browser = lambda _headers: browser
    core.sleep_with_events = lambda seconds, _message: self.pause(seconds)
    def native(url, **kwargs):
      calls.append(('native', self.now))
      raise OSError('failed')
    with patch.object(main, 'CalibreBrowser', object), \
        patch.object(booksellers_best, 'calibre_https_fetch', native), \
        patch.object(booksellers_best, 'random_user_agent', return_value='Calibre Agent'):
      core.fetch_url(URL)
      booksellers_best.UrlFetcherBooksellersBestAward().fetch_url(core.fetch_url, URL)
    self.assertEqual([('legacy', 0), ('native', 3), ('legacy', 6)], calls)

  def test_cancelled_wait_does_not_reserve_or_send_request(self):
    policy.wait_for_wayback(URL, self.pause)
    def cancel(delay): raise main.ImportCancelledError('cancel')
    with self.assertRaises(main.ImportCancelledError):
      policy.wait_for_wayback(URL, cancel)
    self.assertEqual(3, self.clock.next_request)
    policy.wait_for_wayback(URL, self.pause)
    self.assertEqual(3, self.now)

  def test_reentrant_ui_wait_rechecks_clock_after_nested_request(self):
    policy.wait_for_wayback(URL, self.pause)
    nested = []
    def pump(delay):
      self.now += delay
      if not nested:
        nested.append(True)
        policy.wait_for_wayback(URL, self.pause)
    policy.wait_for_wayback(URL, pump)
    self.assertEqual(6, self.now)

  def test_retry_after_seconds_carries_between_transports(self):
    error = HTTPError(URL, 429, 'Limited', {'retry-after': '120'}, None)
    policy.note_wayback_error(URL, error)
    policy.wait_for_wayback(URL, self.pause)
    self.assertEqual([120], self.delays)

  def test_retry_after_date_and_invalid_headers(self):
    for value, expected in ((format_datetime(datetime.fromtimestamp(1100, timezone.utc)), 100),
        ('invalid', 60), ('NaN', 60), ('-1', 60), ('0', 6)):
      with self.subTest(value=value):
        self.now = 0
        self.clock.next_request = 0
        self.clock.interval = 3
        self.clock.limited(URL, {'Retry-After': value})
        self.clock.wait(URL, self.pause)
        self.assertEqual(expected, self.now)

  def test_repeated_429s_double_gap_across_sources_and_imports(self):
    clock = policy.WaybackRequestClock(clock=lambda: self.now)
    gaps = []
    for url in (URL, 'https://web.archive.org/cdx/search/cdx?url=gdrwa.org', URL):
      clock.limited(url, {'Retry-After': '0'})
      clock.wait(url, self.pause)
      gaps.append(clock.interval)
      before = self.now
      clock.wait(URL, self.pause)
      self.assertEqual(clock.interval, self.now - before)
    self.assertEqual([20, 40, 80], gaps)

  def test_retry_after_cannot_shorten_expanded_gap(self):
    clock = policy.WaybackRequestClock(interval=40, clock=lambda: self.now)
    clock.limited(URL, {'Retry-After': '1'})
    clock.wait(URL, self.pause)
    self.assertEqual(80, self.now)
    clock.limited(URL, {'Retry-After': '300'})
    clock.wait(URL, self.pause)
    self.assertEqual(380, self.now)
    self.assertEqual(160, clock.interval)

  def test_core_does_not_count_response_429_twice(self):
    class Browser:
      def add_handler(inner, handler): inner.handler = handler
      def open(inner, url, timeout=30):
        inner.handler.https_request(Request(url))
        error = HTTPError(url, 429, 'Limited', {'Retry-After': '0'}, None)
        inner.handler.https_response(Request(url), error)
        raise error
    browser = Browser()
    core = object.__new__(main.ListSwitchboardCore)
    core.calibre_browser = lambda _headers: browser
    core.sleep_with_events = lambda seconds, _message: self.pause(seconds)
    with patch.object(main, 'CalibreBrowser', object):
      with self.assertRaises(HTTPError):
        core.fetch_url(URL)
    self.assertEqual(6, self.clock.interval)

  def test_other_hosts_errors_do_not_defer_wayback(self):
    policy.note_wayback_error('https://example.org/', HTTPError(URL, 429, '', {}, None))
    policy.note_wayback_error(URL, HTTPError(URL, 503, '', {}, None))
    self.assertEqual(0, self.clock.next_request)

  def test_standard_redirect_processing_paces_each_hop_without_network(self):
    calls = []
    class Server(HTTPHandler):
      def http_open(inner, request):
        url = request.get_full_url()
        calls.append((url, self.now))
        headers = Message()
        code = 200
        if url.endswith('/first'):
          headers['Location'] = 'http://web.archive.org/second'
          code = 302
        response = addinfourl(BytesIO(b'OK'), headers, url, code)
        response.msg = 'Found' if code == 302 else 'OK'
        return response
    opener = build_opener(policy.pacing_handler(BaseHandler, self.pause), Server())
    with opener.open('http://web.archive.org/first') as response:
      self.assertEqual(b'OK', response.read())
    self.assertEqual([0, 3], [when for url, when in calls])

  def test_browser_hook_is_installed_once_and_handles_redirect_requests(self):
    class Browser:
      def __init__(inner): inner.handlers = []
      def add_handler(inner, handler): inner.handlers.append(handler)
    browser = Browser()
    self.assertTrue(policy.install_browser_pacing(browser, self.pause))
    self.assertTrue(policy.install_browser_pacing(browser, self.pause))
    self.assertEqual(1, len(browser.handlers))
    handler = browser.handlers[0]
    handler.http_request(Request(URL))
    handler.https_request(Request(URL + 'other'))
    self.assertEqual([3], self.delays)

  def test_response_hook_applies_shared_cooldown(self):
    handler = policy.pacing_handler(BaseHandler, self.pause)
    class Limited:
      code = 429
      headers = {'Retry-After': '90'}
    handler.http_response(Request(URL), Limited())
    policy.wait_for_wayback(URL, self.pause)
    self.assertEqual(90, self.now)

  def test_parallel_callers_cannot_reserve_same_request_time(self):
    clock = policy.WaybackRequestClock(interval=0.03)
    barrier = threading.Barrier(3)
    times = []
    def run():
      barrier.wait()
      clock.wait(URL)
      times.append(time.monotonic())
    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads: thread.start()
    barrier.wait()
    for thread in threads:
      thread.join(2)
      self.assertFalse(thread.is_alive())
    self.assertGreaterEqual(abs(times[1] - times[0]), 0.025)


if __name__ == '__main__':
  unittest.main()
