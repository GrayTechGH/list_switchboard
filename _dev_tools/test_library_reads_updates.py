from copy import deepcopy
import csv
import io
import unittest

from _dev_tools import test_import_cache_and_saved_matches
from errors import ImportCancelledError, CamoufoxRequiredError
from parser.library_reads import SHEET_CSV_URL
from storage import build_import_cache_data
from url_fetcher.generic import UrlFetcherError
from url_fetcher.library_reads import (
  UrlFetcherLibraryReads,UrlFetcherLibraryReadsBonusPicks,UrlFetcherLibraryReadsNotableNonfiction)


class LibraryReadsUpdateTests(unittest.TestCase):

  def setUp(self):
    self.calls=[]
    self.rows=[['2026/1','Monthly Story','Writer, One','Fiction','','','X'],
      ['2026/1','Bonus Story','Writer, Two','Fiction','','X',''],
      ['2026/1','Nonfiction Story','Writer, Three','Nonfiction','','X','']]

  def csv(self):
    stream=io.StringIO(newline='')
    writer=csv.writer(stream)
    writer.writerow(['Month','Title','Author (Last, First)','Genre','HoF','Bonus Pick','Top Pick'])
    writer.writerows(self.rows)
    return stream.getvalue()

  def fetch(self,url):
    self.calls.append(url)
    return self.csv() if url==SHEET_CSV_URL else '<h1>LibraryReads Archive</h1>'

  def test_all_scopes_refresh_data_directly_and_keep_full_entry_schema(self):
    for recipe in (UrlFetcherLibraryReads(),UrlFetcherLibraryReadsBonusPicks(),
        UrlFetcherLibraryReadsNotableNonfiction()):
      with self.subTest(recipe=recipe.source_id):
        self.calls=[]
        full=recipe.fetch_and_parse(self.fetch)
        self.assertEqual(2,len(self.calls))
        cache=build_import_cache_data(recipe.source_id,full,recipe=recipe)
        self.calls=[]
        update=recipe.fetch_and_parse(self.fetch,cached_parsed=cache,incremental_update=True)
        self.assertEqual([SHEET_CSV_URL],self.calls)
        self.assertEqual(full['entries'],update['entries'])
        self.assertEqual(full['notes'],update['notes'])

  def test_new_rows_and_missing_cached_entries_recover_without_archive_bootstrap(self):
    recipe=UrlFetcherLibraryReads()
    cache=build_import_cache_data(recipe.source_id,recipe.fetch_and_parse(self.fetch),recipe=recipe)
    cache['entries']=[]
    self.rows.append(['2026/2','New Monthly Story','Writer, Four','Fiction','','',''])
    self.calls=[]
    update=recipe.fetch_and_parse(self.fetch,cached_parsed=cache,incremental_update=True)
    self.assertEqual(1,len(self.calls))
    self.assertEqual(recipe.fetch_and_parse(self.fetch)['entries'],update['entries'])
    self.assertEqual(2,len(update['entries']))

  def test_legacy_incompatible_scope_and_malformed_state_rebootstrap(self):
    recipe=UrlFetcherLibraryReads()
    full=recipe.fetch_and_parse(self.fetch)
    base=build_import_cache_data(recipe.source_id,full,recipe=recipe)
    malformed=deepcopy(base); malformed['incremental_state']['discovery']=['invalid']
    for cache in ({'entries':full['entries']},malformed,
        {**base,'incremental_state':['invalid']}):
      self.calls=[]
      recipe.fetch_and_parse(self.fetch,cached_parsed=cache,incremental_update=True)
      self.assertEqual(recipe.URL,self.calls[0])
    self.calls=[]
    UrlFetcherLibraryReadsBonusPicks().fetch_and_parse(self.fetch,cached_parsed=base,incremental_update=True)
    self.assertEqual(recipe.URL,self.calls[0])

  def test_stale_endpoint_retries_normal_archive_flow(self):
    recipe=UrlFetcherLibraryReads()
    cache=build_import_cache_data(recipe.source_id,recipe.fetch_and_parse(self.fetch),recipe=recipe)
    self.calls=[]
    def fetch(url):
      if not self.calls:
        self.calls.append(url)
        return '<h1>Endpoint moved</h1>'
      return self.fetch(url)
    update=recipe.fetch_and_parse(fetch,cached_parsed=cache,incremental_update=True)
    self.assertEqual([SHEET_CSV_URL,recipe.URL,SHEET_CSV_URL],self.calls)
    self.assertTrue(update['entries'])

  def test_cancellation_and_browser_requirement_propagate_in_both_paths(self):
    recipe=UrlFetcherLibraryReads()
    cache=build_import_cache_data(recipe.source_id,recipe.fetch_and_parse(self.fetch),recipe=recipe)
    for error in (ImportCancelledError,CamoufoxRequiredError):
      def fetch(url):
        if url==SHEET_CSV_URL: raise error('stop')
        return '<h1>LibraryReads Archive</h1>'
      for cached in (None,cache):
        with self.assertRaises(error):
          recipe.fetch_and_parse(fetch,cached_parsed=cached,incremental_update=True)

  def test_cached_endpoint_does_not_bypass_invalid_source_selection(self):
    recipe=UrlFetcherLibraryReads()
    cache=build_import_cache_data(recipe.source_id,recipe.fetch_and_parse(self.fetch),recipe=recipe)
    with self.assertRaises(UrlFetcherError):
      recipe.fetch_and_parse(self.fetch,cached_parsed=cache,incremental_update=True,source_choice=8)

  def test_empty_endpoint_and_archive_cannot_erase_saved_entries(self):
    recipe=UrlFetcherLibraryReads()
    cache=build_import_cache_data(recipe.source_id,recipe.fetch_and_parse(self.fetch),recipe=recipe)
    self.rows=[]
    with self.assertRaises(ValueError):
      recipe.fetch_and_parse(self.fetch,cached_parsed=cache,incremental_update=True)


if __name__=='__main__':
  unittest.main()
