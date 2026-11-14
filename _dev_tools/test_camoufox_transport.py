import threading
import unittest
import sys
import types
from unittest.mock import patch

from camoufox_transport import (
  CamoufoxChallengeError,
  CamoufoxFetchError,
  CamoufoxTransport,
)
from errors import ImportCancelledError


class FakeHeaders(dict):

  def get_content_charset(self):
    return 'utf-8'


class FakeResponse:

  def __init__(self, data, url='https://www.librarything.com/final', status=200,
      content_length=None):
    self.data = data
    self.final_url = url
    self.status = status
    self.headers = FakeHeaders()
    if content_length is not None:
      self.headers['Content-Length'] = str(content_length)
    self.closed = False

  def read(self, limit=-1):
    return self.data if limit < 0 else self.data[:limit]

  def geturl(self):
    return self.final_url

  def close(self):
    self.closed = True


class FakeBrowser:

  def __init__(self, response, release=None):
    self.response = response
    self.release = release
    self.open_threads = []
    self.open_calls = []
    self.shutdown_calls = 0

  def open(self, url, timeout=None, as_document=False):
    self.open_threads.append(threading.get_ident())
    self.open_calls.append((url, timeout, as_document))
    if self.release is not None:
      self.release.wait(2)
    return self.response

  def shutdown(self):
    self.shutdown_calls += 1
    if self.release is not None:
      self.release.set()


class CamoufoxTransportTests(unittest.TestCase):

  def test_unreadable_calibre_headers_keep_rendered_body_limit(self):
    class BrokenHeadersResponse:
      status = 200

      @property
      def headers(self):
        raise ValueError('Header values may not contain linefeed or carriage return characters')

      def read(self, limit):
        return b'<html>Goodreads</html>'[:limit]

    for limit in (4, 100):
      browser = FakeBrowser(BrokenHeadersResponse())
      transport = CamoufoxTransport(browser_factory=lambda **kw: browser)
      try:
        if limit == 4:
          with self.assertRaisesRegex(CamoufoxFetchError, 'limit'):
            transport.fetch('https://www.goodreads.com/choiceawards', max_bytes=limit)
        else:
          self.assertEqual('<html>Goodreads</html>', transport.fetch(
            'https://www.goodreads.com/choiceawards', max_bytes=limit))
      finally:
        transport.close()

  def test_shared_stage_migrates_pilot_settings_and_new_setting_wins(self):
    from camoufox_transport import browser_fallback_level
    for previous, expected in (('automatic', 0), ('camoufox', 1), ('old', 2)):
      with self.subTest(previous=previous):
        prefs = {'debug_librarything_transport': previous}
        self.assertEqual(expected, browser_fallback_level(prefs))
        for level in (0, 1, 2):
          prefs['debug_browser_fallback_level'] = level
          self.assertEqual(level, browser_fallback_level(prefs))
    for invalid in ('bad', 3, -1):
      self.assertEqual(0, browser_fallback_level({'debug_browser_fallback_level': invalid}))

  def test_reddit_uses_own_warmup_and_leaves_validation_to_parser(self):
    browser = FakeBrowser(FakeResponse(b'<div class="cf-turnstile"></div>'))
    calls = []

    def factory(**kwargs):
      calls.append(kwargs)
      return browser

    transport = CamoufoxTransport(
      browser_factory=factory, source_name='r/bookclub',
      warmup_excluded_domains=('reddit.com',), check_challenges=False)
    try:
      self.assertIn('cf-turnstile', transport.fetch('https://www.reddit.com/r/bookclub/wiki/previous/'))
      self.assertEqual(('reddit.com',), calls[0]['warmup_excluded_domains'])
    finally:
      transport.close()

  def test_outer_deadline_stops_a_stalled_startup(self):
    release = threading.Event()
    opened = threading.Event()
    browser = FakeBrowser(FakeResponse(b'<html></html>'), release)
    original_open = browser.open

    def open_browser(*args, **kwargs):
      opened.set()
      return original_open(*args, **kwargs)

    browser.open = open_browser
    transport = CamoufoxTransport(
      browser_factory=lambda **_kw: browser,
      wait_callback=lambda _message: opened.wait(1))
    with patch('camoufox_transport.STARTUP_ALLOWANCE_SECONDS', -1):
      with self.assertRaisesRegex(CamoufoxFetchError, 'time limit'):
        transport.fetch('https://www.librarything.com/award/1', timeout=0)
    self.assertTrue(transport.closed)
    self.assertEqual(1, browser.shutdown_calls)

  def test_cloudflare_script_on_usable_award_page_is_not_a_challenge(self):
    from camoufox_transport import is_challenge_payload
    html = '''<title>The Strand Critics Award | LibraryThing</title>
      <h2>Winner</h2><table><tr><th>Work</th><th>Year</th></tr>
      <tr><td><a href="/work/1">Book</a></td><td>2025</td></tr></table>
      <script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>'''
    self.assertFalse(is_challenge_payload(html))
    self.assertTrue(is_challenge_payload('<title>Just a moment...</title>'))
    self.assertTrue(is_challenge_payload('<div class="cf-chl-test"></div>'))

  def test_capability_checks_version_before_optional_import(self):
    import camoufox_transport as module
    for version in ((6, 0, 0), (9, 15, 0)):
      with patch.object(module, 'calibre_version_tuple', return_value=version):
        self.assertFalse(module.camoufox_capability()[0])
    recipes = types.ModuleType('calibre.web.automate.recipes')
    recipes.Browser = FakeBrowser
    with patch.object(module, 'calibre_version_tuple', return_value=(9, 16, 0)):
      with patch.dict(sys.modules, {'calibre.web.automate.recipes': recipes}):
        self.assertIs(FakeBrowser, module.camoufox_capability()[2])
      with patch.dict(sys.modules, {'calibre.web.automate.recipes': None}):
        self.assertFalse(module.camoufox_capability()[0])

  def test_cancel_during_constructor_returns_before_constructor_finishes(self):
    release = threading.Event()
    started = threading.Event()
    finished = threading.Event()
    browser = FakeBrowser(FakeResponse(b'<html></html>'))
    original_shutdown = browser.shutdown

    def shutdown():
      original_shutdown()
      finished.set()

    browser.shutdown = shutdown

    def factory(**_kwargs):
      started.set()
      release.wait(5)
      return browser

    def cancel(_message):
      if started.is_set():
        raise ImportCancelledError('cancelled during startup')

    transport = CamoufoxTransport(
      browser_factory=factory, wait_callback=cancel, poll_interval=0.001)
    try:
      with patch('camoufox_transport.SHUTDOWN_JOIN_SECONDS', 0.01):
        with self.assertRaises(ImportCancelledError):
          transport.fetch('https://www.librarything.com/award/1')
      self.assertFalse(release.is_set())
    finally:
      release.set()
    # The late constructor owns cleanup because cancellation preceded publish.
    self.assertTrue(finished.wait(2))
    self.assertEqual(1, browser.shutdown_calls)

  def test_utf8_final_url_logging_and_stream_size_limit(self):
    response = FakeResponse('caf\u00e9'.encode('utf-8'))
    logs = []
    transport = CamoufoxTransport(
      browser_factory=lambda **_kw: FakeBrowser(response), log=logs.append)
    self.assertEqual('caf\u00e9', transport.fetch('https://www.librarything.com/award/1'))
    self.assertTrue(response.closed)
    self.assertTrue(any('final_url=https://www.librarything.com/final' in log for log in logs))
    transport.close()
    transport = CamoufoxTransport(
      browser_factory=lambda **_kw: FakeBrowser(FakeResponse(b'12345')))
    try:
      with self.assertRaises(CamoufoxFetchError):
        transport.fetch('https://www.librarything.com/award/1', max_bytes=4)
    finally:
      transport.close()

  def test_fetch_runs_off_caller_thread_reuses_browser_and_closes_once(self):
    release = threading.Event()
    browser = FakeBrowser(FakeResponse(b'<html>LibraryThing award</html>'), release)
    factory_calls = []
    wait_threads = []

    def factory(**kwargs):
      factory_calls.append(kwargs)
      return browser

    def wait_callback(_message):
      wait_threads.append(threading.get_ident())
      release.set()

    caller_thread = threading.get_ident()
    transport = CamoufoxTransport(
      browser_factory=factory,
      wait_callback=wait_callback,
      poll_interval=0.001)
    first = transport.fetch('https://www.librarything.com/award/1')
    release.clear()
    second = transport.fetch('https://www.librarything.com/award/2')
    transport.close()
    transport.close()

    self.assertEqual('<html>LibraryThing award</html>', first)
    self.assertEqual(first, second)
    self.assertEqual(1, len(factory_calls))
    self.assertEqual(('librarything.com',), factory_calls[0]['warmup_excluded_domains'])
    self.assertTrue(factory_calls[0]['block_images'])
    self.assertEqual(1, factory_calls[0]['max_tabs'])
    self.assertTrue(wait_threads)
    self.assertTrue(all(thread_id == caller_thread for thread_id in wait_threads))
    self.assertTrue(all(thread_id != caller_thread for thread_id in browser.open_threads))
    self.assertEqual(1, browser.shutdown_calls)

  def test_challenge_and_oversized_payloads_are_rejected(self):
    challenge_browser = FakeBrowser(FakeResponse(
      b'<html><title>Just a moment...</title><div class="cf-chl-test"></div></html>'))
    challenge = CamoufoxTransport(
      browser_factory=lambda **_kwargs: challenge_browser,
      poll_interval=0.001)
    with self.assertRaises(CamoufoxChallengeError):
      challenge.fetch('https://www.librarything.com/award/1')
    challenge.close()

    large_browser = FakeBrowser(FakeResponse(b'12345', content_length=5))
    oversized = CamoufoxTransport(
      browser_factory=lambda **_kwargs: large_browser,
      poll_interval=0.001)
    with self.assertRaises(CamoufoxFetchError):
      oversized.fetch('https://www.librarything.com/award/1', max_bytes=4)
    oversized.close()

  def test_cancellation_shuts_down_in_flight_browser(self):
    release = threading.Event()
    browser = FakeBrowser(FakeResponse(b'<html></html>'), release)

    def cancel(_message):
      raise ImportCancelledError('Import cancelled')

    transport = CamoufoxTransport(
      browser_factory=lambda **_kwargs: browser,
      wait_callback=cancel,
      poll_interval=0.001)
    with self.assertRaises(ImportCancelledError):
      transport.fetch('https://www.librarything.com/award/1')

    self.assertEqual(1, browser.shutdown_calls)
    self.assertTrue(transport.closed)


if __name__ == '__main__':
  unittest.main()
