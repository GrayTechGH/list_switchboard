import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError, ImportCancelledError
from parser.nommo import NommoAwardsParser, NOMMO_AWARDS_URL, OFFICIAL_FALLBACK_URLS
from parser.spsfc import SPSFCAwardsParser, SPSFC_SOURCE_PAGES
from storage import build_import_cache_data


class NommoUpdateTests(unittest.TestCase):

  def setUp(self):
    self.calls, self.failures = [], {}
    self.primary = '<h2>Novel</h2><table><tr><td>2025</td><td>Writer*</td><td>Current</td><td>Pub</td></tr></table>'
    self.official = '<h1>2024 Nommo Awards</h1><h2>Novel</h2><p>Closed Book by Older Writer</p>'
    self.parser = NommoAwardsParser()

  def fetch(self, url):
    self.calls.append(url)
    if url in self.failures:
      raise self.failures[url]
    return self.official

  def parse(self, old=None):
    return self.parser.parse(self.primary, NOMMO_AWARDS_URL, 'Nommo Novel', 'Novel',
      fetch_url=self.fetch, cached_parsed=old, incremental_update=old is not None)

  def test_missing_primary_recovered_and_closed_supplement_reused(self):
    full = self.parse()
    self.assertEqual(2, len(full['entries']))
    old = without_unit(build_import_cache_data('nommo', full), NOMMO_AWARDS_URL)
    self.calls.clear()
    self.assertEqual(full['entries'], self.parse(old)['entries'])
    self.assertEqual([], self.calls)
    # New authoritative Wikipedia rows must replace the retained supplement's
    # entire year/category, including titles that no longer appear there.
    self.primary += '<h2>Novel</h2><table><tr><td>2024</td><td>Writer*</td><td>Authoritative</td><td>Pub</td></tr></table>'
    update = self.parse(build_import_cache_data('nommo', full))
    self.assertEqual(['Authoritative', 'Current'], [e['title'] for e in update['entries']])

  def test_failed_supplement_retained_pending_then_refetched_and_required_errors_propagate(self):
    full = self.parse()
    old = build_import_cache_data('nommo', full)
    old['incremental_state']['units'][OFFICIAL_FALLBACK_URLS[0]]['complete'] = False
    self.failures[OFFICIAL_FALLBACK_URLS[0]] = OSError('offline')
    update = self.parse(old)
    self.assertEqual(full['entries'], update['entries'])
    self.assertFalse(update['incremental_state']['units'][OFFICIAL_FALLBACK_URLS[0]]['complete'])
    for error in (ImportCancelledError('stop'), CamoufoxRequiredError('required')):
      self.failures[OFFICIAL_FALLBACK_URLS[0]] = error
      with self.assertRaises(type(error)):
        self.parse(old)
    self.failures.clear()
    self.calls.clear()
    self.assertEqual(full['entries'], self.parse(build_import_cache_data('nommo', update))['entries'])
    self.assertEqual(list(OFFICIAL_FALLBACK_URLS), self.calls)

  def test_malformed_legacy_and_changed_scope_rebuild(self):
    full = self.parse()
    bad = build_import_cache_data('nommo', full)
    bad['incremental_state']['units'][OFFICIAL_FALLBACK_URLS[0]]['metadata'] = {}
    wrong = build_import_cache_data('nommo', full)
    wrong['incremental_state']['source_key'] = 'another category'
    for old in (bad, wrong, {'entries': full['entries']}):
      self.calls.clear()
      self.assertEqual(full['entries'], self.parse(old)['entries'])
      self.assertEqual(list(OFFICIAL_FALLBACK_URLS), self.calls)

  def test_verified_redundant_dated_page_skipped_only_while_primary_covers_year(self):
    self.primary = self.primary.replace('2025', '2024')
    self.official = '<title>2024 Nommo Awards Winners</title><p>Unparsed official shape</p>'
    full = self.parse()
    old = build_import_cache_data('nommo', full)
    self.calls.clear()
    self.assertEqual(full['entries'], self.parse(old)['entries'])
    self.assertEqual([], self.calls)
    self.primary = self.primary.replace('2024', '2025')
    self.parse(old)
    self.assertEqual(list(OFFICIAL_FALLBACK_URLS), self.calls)


class SPSFCUpdateTests(unittest.TestCase):

  def setUp(self):
    self.parser, self.calls, self.failures = SPSFCAwardsParser(), [], {}
    self.pages = list(SPSFC_SOURCE_PAGES)
    self.curated = [{'competition': f'SPSFC {n}', 'award_year': 2021+n,
      'title': f'Winner {n}', 'author': 'Writer One', 'result': 'winner', 'placement': 1} for n in range(1, 4)]

  def page(self, spec):
    n = int(spec['competition'].split()[-1])
    if spec['kind'] == 'official_result':
      return f'<h1>SPSFC {n}</h1><h2>Winner</h2><h4>Winner {n} by Writer One</h4><h2>Second Place</h2><h4>Other {n} by Writer Two</h4>'
    return f'<h1>SPSFC {n}</h1><ul><li>Winner {n} by Writer One</li><li>Other {n} by Writer Two</li></ul>'

  def fetch(self, url):
    self.calls.append(url)
    if url in self.failures:
      raise self.failures[url]
    return self.page(next(p for p in self.pages if p['url'] == url))

  def parse(self, old=None):
    root = self.pages[0]['url']
    return self.parser.parse(self.page(self.pages[0]), root, 'SPSFC', fetch_url=self.fetch,
      source_pages=self.pages, curated_rows=self.curated,
      cached_parsed=old, incremental_update=old is not None)

  def test_missing_latest_recovery_and_historical_winner_promotions(self):
    full = self.parse()
    self.assertEqual(5, len(self.calls))
    old = without_unit(build_import_cache_data('spsfc', full), self.pages[0]['url'])
    self.calls.clear()
    update = self.parse(old)
    self.assertEqual(full['entries'], update['entries'])
    self.assertEqual([], self.calls)
    self.assertEqual(5, len([e for e in update['entries'] if e['result'] == 'winner']))
    self.calls.clear()
    self.assertEqual(full['entries'], self.parse(build_import_cache_data('spsfc', update))['entries'])
    self.assertEqual([], self.calls)

  def test_pending_failure_projection_and_manifest_change(self):
    full = self.parse()
    url = self.pages[-1]['url']
    old = build_import_cache_data('spsfc', full)
    old['incremental_state']['units'][url]['complete'] = False
    self.failures[url] = OSError('offline')
    update = self.parse(old)
    self.assertEqual(full['entries'], update['entries'])
    self.assertFalse(update['incremental_state']['units'][url]['complete'])
    self.failures.clear()
    self.curated[0]['title'] = 'Corrected Winner'
    self.calls.clear()
    update = self.parse(old)
    self.assertEqual(5, len(self.calls))
    self.assertEqual(self.parse()['entries'], update['entries'])

  def test_current_and_unsettled_competitions_refresh_and_cancellation_propagates(self):
    full = self.parse()
    old = build_import_cache_data('spsfc', full)
    self.calls.clear()
    with patch('parser.spsfc.datetime') as clock:
      clock.datetime.now.return_value.year = 2025
      self.assertEqual(full['entries'], self.parse(old)['entries'])
    self.assertEqual([p['url'] for p in self.pages[1:3]], self.calls)
    for error in (ImportCancelledError('stop'), CamoufoxRequiredError('required')):
      self.failures[self.pages[1]['url']] = error
      with self.assertRaises(type(error)):
        self.parse()


if __name__ == '__main__':
  unittest.main()
