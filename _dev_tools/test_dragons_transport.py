"""Recipe transport regressions using the existing representative shelf fixtures."""
import unittest
from errors import ImportCancelledError, CamoufoxSkippedError
from url_fetcher.dragons_and_jetpacks import UrlFetcherDragonsJetpacks
from _dev_tools.test_import_matching import dragons_jetpacks_page, dragons_jetpacks_row


class DragonsTransportTests(unittest.TestCase):
  def setUp(self):
    self.recipe = UrlFetcherDragonsJetpacks()
    self.url = self.recipe.primary_urls()[0]
    self.next = self.url + '&page=2'
    self.row1 = dragons_jetpacks_row('1', 'First', ['Writer, One'], ['group-read', 'fantasy'])
    self.row2 = dragons_jetpacks_row('2', 'Second', ['Writer, Two'], ['group-read', 'sci-fi'])
    self.pages = {self.url: dragons_jetpacks_page([self.row1], self.next),
      self.next: dragons_jetpacks_page([self.row1, self.row2])}

  def run_recipe(self, failures=None):
    calls = []
    def fetch(url, **kwargs):
      browser = kwargs.get('transport') == 'camoufox'
      calls.append((url, browser))
      failure = (failures or {}).get((url, browser))
      if isinstance(failure, Exception):
        raise failure
      return failure if failure is not None else self.pages[url]
    result = self.recipe.fetch_and_parse(fetch)
    self.assertIsNone(self.recipe._dragons_fetch_policy)
    return result, calls

  def test_browser_pagination_overlap_and_full_schema_parity(self):
    browser, calls = self.run_recipe()
    self.assertEqual(calls, [(self.url, True), (self.next, True)])
    legacy, calls = self.run_recipe({(self.url, True): CamoufoxSkippedError('disabled')})
    self.assertEqual(browser, legacy)
    self.assertEqual(len(browser['entries']), 2)
    self.assertEqual(calls, [(self.url, True), (self.url, False), (self.next, False)])

  def test_later_recovery_and_repeated_page(self):
    result, calls = self.run_recipe({(self.next, True): self.pages[self.url]})
    self.assertEqual(len(result['entries']), 2)
    self.assertNotIn('notes', result)
    self.assertEqual(calls[-1], (self.next, False))

  def test_challenge_initial_recovery(self):
    result, calls = self.run_recipe({(self.url, True): '<title>Sign in</title>'})
    self.assertEqual(len(result['entries']), 2)
    self.assertEqual(calls[-1], (self.next, False))

  def test_both_fail_no_partial_result(self):
    with self.assertRaises(Exception):
      self.run_recipe({(self.next, True): 'challenge', (self.next, False): 'challenge'})
    self.assertIsNone(self.recipe._dragons_fetch_policy)

  def test_cancel_never_recovers_or_reports_fetch_error(self):
    calls = []
    def fetch(url, **kwargs):
      calls.append(url)
      raise ImportCancelledError('cancel')
    with self.assertRaises(ImportCancelledError):
      self.recipe.fetch_and_parse(fetch, fetch_error=lambda *a: self.fail('reported cancellation'))
    self.assertEqual(calls, [self.url])
    self.assertIsNone(self.recipe._dragons_fetch_policy)

  def test_unsupported_callback(self):
    result = self.recipe.fetch_and_parse(lambda url: self.pages[url])
    self.assertEqual(len(result['entries']), 2)

  def test_explicit_identity(self):
    parser = self.recipe.parser()
    for marker in ('<div class="pagination"><em class="current">1</em></div>',
        '<link rel="canonical" href="' + self.url + '&amp;page=1">',
        '<meta property="og:url" content="https://www.goodreads.com/group/bookshelf/wrong">',
        '<link rel="canonical" href="' + self.url.replace('group-read', 'other') + '">'):
      with self.subTest(marker=marker), self.assertRaises(ValueError):
        parser.require_real_shelf_page(self.pages[self.next].replace('</body>', marker + '</body>'), self.next)

  def test_owner_rejection_and_operation_reset(self):
    class Owner:
      def __init__(owner):
        owner.calls = []
        owner.rejected = []
      def debug_camoufox(owner, message):
        pass
      def reject_camoufox_payload(owner, reason):
        owner.rejected.append(reason)
      def fetch(owner, url, **kwargs):
        browser = kwargs.get('transport') == 'camoufox'
        owner.calls.append((url, browser))
        return 'challenge' if browser else self.pages[url]
    owner = Owner()
    self.recipe.fetch_and_parse(owner.fetch)
    self.assertEqual(len(owner.rejected), 1)
    self.assertEqual(owner.calls, [(self.url, True), (self.url, False), (self.next, False)])
    self.recipe.fetch_and_parse(owner.fetch)
    self.assertEqual(len(owner.rejected), 2)

  def test_later_cancel_bypasses_error_callback(self):
    calls = []
    def fetch(url, **kwargs):
      calls.append(url)
      if url == self.next:
        raise ImportCancelledError('cancel')
      return self.pages[url]
    with self.assertRaises(ImportCancelledError):
      self.recipe.fetch_and_parse(fetch, fetch_error=lambda *a: self.fail('reported cancellation'))
    self.assertEqual(calls, [self.url, self.next])

  def test_legacy_cancel_and_repeated_payload_fail(self):
    with self.assertRaises(ImportCancelledError):
      self.run_recipe({(self.url, True): CamoufoxSkippedError('disabled'),
        (self.next, False): ImportCancelledError('cancel')})
    with self.assertRaises(Exception):
      self.run_recipe({(self.next, True): self.pages[self.url],
        (self.next, False): self.pages[self.url]})

  def test_legacy_timeout_retry_progress(self):
    calls = []
    progress = []
    def fetch(url, **kwargs):
      if kwargs.get('transport'):
        raise CamoufoxSkippedError('disabled')
      calls.append(url)
      if len(calls) == 1:
        raise TimeoutError('timed out')
      return self.pages[url]
    result = self.recipe.fetch_and_parse(fetch, progress=lambda *a: progress.append(a))
    self.assertEqual(len(result['entries']), 2)
    self.assertTrue(any('retry' in a[-1] for a in progress))


if __name__ == '__main__':
  unittest.main()
