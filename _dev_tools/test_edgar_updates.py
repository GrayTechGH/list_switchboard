import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError, CamoufoxRequiredError
from storage import build_import_cache_data
from url_fetcher.edgar import UrlFetcherEdgarNovel


class EdgarUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe, self.calls, self.failures = UrlFetcherEdgarNovel(), [], {}
    self.rows = [(year, f'{status} {year}', status) for year in (2024, 2023, 2022)
      for status in ('Winner', 'Other')]
    self.size = patch('parser.edgar.PAGE_SIZE', 4)
    self.size.start()
    self.addCleanup(self.size.stop)

  def fetch(self, url):
    self.calls.append(url)
    if url in self.failures:
      raise self.failures[url]
    number = 1 if url == self.recipe.URL else int(url.rsplit('=', 1)[-1])
    rows = self.rows[(number-1)*4:number*4]
    return f'<p>Total Records Found: {len(self.rows)}</p><table>'\
      '<tr><th>Award Year</th><th>Award Category</th><th>Title</th><th>Author\'s Name</th></tr>' + ''.join(
        f'<tr class="{"edgar-winner" if status == "Winner" else ""}"><td>{year}</td><td>Best Novel</td>'
        f'<td>{title}</td><td>Writer One &amp; Writer Two</td></tr>' for year,title,status in rows) + '</table>'

  def parse(self, old=None):
    return self.recipe.fetch_and_parse(self.fetch, source_choice=0,
      cached_parsed=old, incremental_update=old is not None)

  def cache(self, parsed):
    return build_import_cache_data(self.recipe.source_id, parsed)

  def test_missing_latest_recovered_and_insert_shifts_page_provenance(self):
    full = self.parse()
    self.assertEqual(2, len(self.calls))
    old = without_unit(self.cache(full), '2024')
    self.calls.clear()
    self.assertEqual(full['entries'], self.parse(old)['entries'])
    self.assertEqual([self.recipe.URL], self.calls)
    self.rows.insert(0, (2025, 'New Winner', 'Winner'))
    self.calls.clear()
    update = self.parse(self.cache(full))
    self.assertEqual([self.recipe.URL], self.calls)
    self.assertEqual(self.parse()['entries'], update['entries'])
    shifted = next(row for row in update['entries'] if row['title'] == 'Other 2023')
    self.assertIn('listpage=2', shifted['source']['url'])
    self.assertEqual(['Writer One', 'Writer Two'], shifted['authors'])

  def test_count_mismatch_reorder_and_missing_historical_unit_force_complete_crawl(self):
    full = self.parse()
    old = self.cache(full)
    missing = without_unit(old, '2022')
    self.calls.clear()
    self.assertEqual(full['entries'], self.parse(missing)['entries'])
    self.assertEqual(2, len(self.calls))
    # A historical deletion changes the count without changing the front.
    self.rows.pop()
    self.calls.clear()
    update = self.parse(old)
    self.assertEqual(2, len(self.calls))
    self.assertEqual(self.parse()['entries'], update['entries'])
    self.rows[0], self.rows[2] = self.rows[2], self.rows[0]
    self.calls.clear()
    update = self.parse(old)
    self.assertEqual(2, len(self.calls))
    self.assertEqual(self.parse()['entries'], update['entries'])

  def test_failed_pending_and_unsettled_history_retries(self):
    self.rows[-2] = (2022, 'Unsettled', 'Other')
    full = self.parse()
    self.calls.clear()
    self.assertEqual(full['entries'], self.parse(self.cache(full))['entries'])
    self.assertEqual(2, len(self.calls))
    self.failures[self.recipe.parser().page_url(self.recipe.URL,2)] = OSError('offline')
    update = self.parse(self.cache(full))
    self.assertEqual(full['entries'], update['entries'])
    self.assertTrue(update['notes'])
    self.assertTrue(all(not u['complete'] for u in update['incremental_state']['units'].values()))
    self.failures.clear()
    self.assertEqual(full['entries'], self.parse(self.cache(update))['entries'])

  def test_legacy_changed_scope_and_cancellation(self):
    full = self.parse()
    wrong = self.cache(full)
    wrong['incremental_state']['source_key'] = 'another category'
    for old in ({'entries':full['entries']},wrong):
      self.calls.clear()
      self.assertEqual(full['entries'], self.parse(old)['entries'])
      self.assertEqual(2, len(self.calls))
    for error in (ImportCancelledError('stop'), CamoufoxRequiredError('required')):
      self.failures[self.recipe.parser().page_url(self.recipe.URL,2)] = error
      with self.assertRaises(type(error)):
        self.parse()
    official, alternative = self.recipe.source_attempts()
    self.assertTrue(official.supports_incremental)
    self.assertFalse(alternative.supports_incremental)

  def test_failed_shifted_page_retains_a_whole_boundary_ballot(self):
    full = self.parse()
    old = self.cache(full)
    self.rows.insert(0,(2025,'New Winner','Winner'))
    self.rows[3] = (2023,'Changed Boundary Winner','Winner')
    self.failures[self.recipe.parser().page_url(self.recipe.URL,2)] = OSError('offline')
    # Missing historical data forces a full crawl instead of the overlap cutoff.
    old['incremental_state']['units']['2022']['complete'] = False
    pending = self.parse(old)
    before = [e for e in full['entries'] if e['award_year']=='2023']
    after = [e for e in pending['entries'] if e['award_year']=='2023']
    self.assertEqual(before,after)
    self.assertEqual(1,len([e for e in after if e['result']=='winner']))
    self.assertIn('New Winner',[e['title'] for e in pending['entries']])


if __name__ == '__main__':
  unittest.main()
