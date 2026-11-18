import unittest

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError, CamoufoxRequiredError
from parser.otherwise_tiptree import (
  OTHERWISE_URL, OTHERWISE_NOMINEES_URL, TIPTREE_URL, TIPTREE_NOMINEES_URL,
)
from storage import build_import_cache_data
from url_fetcher.otherwise_tiptree import UrlFetcherOtherwiseTiptreeBooksAndSeries


class OtherwiseUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe = UrlFetcherOtherwiseTiptreeBooksAndSeries()
    self.calls, self.failures = [], {}
    self.current_year = 2025
    self.promoted = False

  def winners(self, year, title, author):
    return f'<table><tr><td class="winslistleftcol">{year}</td>'\
      f'<td class="winslistrightcol">{title}, {author}</td></tr></table>'

  def nominee(self, year, title, author, result):
    return f'<div class="nomineeblock"><div class="nominee">{author} (1 nomination)</div>'\
      f'<div class="dateleftindent">{year}</div><div class="titlemid">{title} — {result}</div></div>'

  def fetch(self, url):
    self.calls.append(url)
    if url in self.failures:
      raise self.failures[url]
    if url == OTHERWISE_URL:
      return self.winners(self.current_year, 'Current Winner', 'Writer Four')
    if url == TIPTREE_URL:
      return self.winners(2018, 'Legacy Work', 'Writer One')
    if url == OTHERWISE_NOMINEES_URL:
      return self.nominee(self.current_year, 'Current Nominee', 'Writer Three',
        'Winner' if self.promoted else 'Honor List')
    if url == TIPTREE_NOMINEES_URL:
      return self.nominee(2018, 'Legacy Work', 'Writer Two', 'Honor List')
    raise AssertionError(url)

  def parse(self, cache=None):
    return self.recipe.fetch_and_parse(self.fetch, cached_parsed=cache,
      incremental_update=cache is not None)

  def cache(self, parsed):
    return build_import_cache_data(self.recipe.source_id, parsed)

  def test_legacy_pages_reused_and_actual_missing_current_nominee_recovered(self):
    full = self.parse()
    self.assertEqual(4, len(self.calls))
    old = without_unit(self.cache(full), OTHERWISE_NOMINEES_URL)
    self.assertLess(len(old['entries']), len(full['entries']))
    self.calls = []
    update = self.parse(old)
    self.assertEqual(full['entries'], update['entries'])
    self.assertEqual([OTHERWISE_URL, OTHERWISE_NOMINEES_URL], self.calls)
    legacy = next(e for e in update['entries'] if e['title'] == 'Legacy Work')
    self.assertEqual(['Writer One', 'Writer Two'], legacy['authors'])
    self.assertEqual('winner', legacy['result'])
    self.assertEqual(full['entries'], self.parse(self.cache(update))['entries'])

  def test_new_year_and_winner_promotion_keep_tied_winner_positions(self):
    old = self.cache(self.parse())
    self.current_year = 2026
    self.promoted = True
    update = self.parse(old)
    self.assertEqual(self.parse()['entries'], update['entries'])
    current = [e for e in update['entries'] if e['award_year'] == '2026']
    self.assertEqual(['2026', '2026'], [e['position'] for e in current])
    self.assertEqual(['winner', 'winner'], [e['result'] for e in current])

  def test_failed_current_or_legacy_page_retains_raw_author_credits_pending(self):
    full = self.parse()
    for url in (OTHERWISE_NOMINEES_URL, TIPTREE_URL):
      old = self.cache(full)
      old['incremental_state']['units'][url]['complete'] = False
      self.failures[url] = OSError('offline')
      update = self.parse(old)
      self.assertEqual(full['entries'], update['entries'])
      self.assertFalse(update['incremental_state']['units'][url]['complete'])
      self.failures.clear()
      self.calls = []
      self.assertEqual(full['entries'], self.parse(self.cache(update))['entries'])
      self.assertIn(url, self.calls)

  def test_legacy_scope_change_and_invalid_projection_refetch_archive(self):
    full = self.parse()
    wrong = self.cache(full)
    wrong['incremental_state']['source_key'] = 'another archive'
    malformed = self.cache(full)
    malformed['incremental_state']['units'][TIPTREE_URL]['metadata'] = {}
    for old in ({'entries': full['entries']}, wrong, malformed):
      self.calls = []
      self.assertEqual(full['entries'], self.parse(old)['entries'])
      self.assertIn(TIPTREE_URL, self.calls)

  def test_cancellation_and_browser_requirement_propagate_from_linked_pages(self):
    for url in (TIPTREE_URL, OTHERWISE_NOMINEES_URL, TIPTREE_NOMINEES_URL):
      for error in (ImportCancelledError('stop'), CamoufoxRequiredError('required')):
        self.failures[url] = error
        with self.assertRaises(type(error)):
          self.parse()
        self.failures.clear()


if __name__ == '__main__':
  unittest.main()
