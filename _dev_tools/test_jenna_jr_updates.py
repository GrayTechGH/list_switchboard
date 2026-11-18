import unittest

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError
from parser.read_with_jenna import ReadWithJennaJuniorParser
from storage import build_import_cache_data


class JennaJuniorUpdateTests(unittest.TestCase):

  def setUp(self):
    self.parser=ReadWithJennaJuniorParser()
    self.root='https://www.today.com/shop/read-with-jenna'
    self.years=[2026,2024,2023]
    self.calls=[]
    self.partial=None

  def url(self,year):
    return f'https://www.today.com/books/read-with-jenna-junior-book-list-{year}-test'

  def page(self,year):
    index=self.years.index(year)
    previous=self.years[index+1] if index+1<len(self.years) else None
    links=f'<a href="{self.url(previous)}">Past list</a>' if previous else ''
    return f'<h1>Read With Jenna Jr. {year}: See All 2 Books</h1>{links}'\
      f'<h2>Picture Books</h2><h3>"Picture {year}" by Writer One</h3>'+\
      (f'<h2>Young Adult</h2><h3>"Older {year}" by Writer Two</h3>' if self.partial!=year else '')

  def fetch(self,url):
    self.calls.append(url)
    return self.page(next(y for y in self.years if self.url(y)==url))

  def parse(self,cache=None,fetch=None):
    return self.parser.parse(f'<a href="{self.url(self.years[0])}">Latest</a>',
      self.root,fetch_url=fetch or self.fetch,cached_parsed=cache,
      incremental_update=cache is not None)

  def cache(self,parsed):
    return build_import_cache_data('jenna-jr',parsed)

  def test_update_preserves_recursive_history_without_refetching_old_articles(self):
    full=self.parse(); self.assertEqual(3,len(self.calls))
    self.calls=[]
    update=self.parse(self.cache(full))
    self.assertEqual(full['entries'],update['entries'])
    self.assertEqual([self.url(2026)],self.calls)
    self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])

  def test_missing_historical_unit_is_recovered_through_cached_discovery_links(self):
    full=self.parse(); old=without_unit(self.cache(full),self.url(2023))
    self.calls=[]
    update=self.parse(old)
    self.assertEqual(full['entries'],update['entries'])
    self.assertEqual([self.url(2026),self.url(2023)],self.calls)

  def test_new_year_and_new_categories_keep_stable_history_and_positions(self):
    old=self.cache(self.parse())
    self.years.insert(0,2027)
    update=self.parse(old)
    self.assertEqual(self.parse()['entries'],update['entries'])
    self.assertEqual(8,len(update['entries']))

  def test_failed_history_keeps_old_unit_pending_and_retries(self):
    old=self.cache(self.parse())
    old['incremental_state']['units'][self.url(2024)]['complete']=False
    def fail(url):
      if url==self.url(2024): raise OSError('offline')
      return self.fetch(url)
    update=self.parse(old,fetch=fail)
    self.assertEqual(old['entries'],update['entries'])
    self.assertTrue(update['notes'])
    self.calls=[]
    retry=self.parse(self.cache(update))
    self.assertIn(self.url(2024),self.calls)
    self.assertEqual(old['entries'],retry['entries'])

  def test_partial_declared_count_does_not_replace_complete_cached_history(self):
    old=self.cache(self.parse())
    old['incremental_state']['units'][self.url(2024)]['complete']=False
    self.partial=2024
    update=self.parse(old)
    self.assertEqual(old['entries'],update['entries'])
    self.assertFalse(update['incremental_state']['units'][self.url(2024)]['complete'])

  def test_legacy_cache_and_missing_link_metadata_rebuild_history(self):
    full=self.parse()
    old=self.cache(full)
    del old['incremental_state']['units'][self.url(2024)]['metadata']
    self.calls=[]
    self.parse(old)
    self.assertIn(self.url(2024),self.calls)
    self.calls=[]
    self.parse({'entries':full['entries']})
    self.assertEqual(3,len(self.calls))

  def test_cancelled_linked_page_propagates(self):
    def cancel(url):
      if url==self.url(2024): raise ImportCancelledError('stop')
      return self.fetch(url)
    with self.assertRaises(ImportCancelledError):
      self.parse(fetch=cancel)


if __name__=='__main__':
  unittest.main()
