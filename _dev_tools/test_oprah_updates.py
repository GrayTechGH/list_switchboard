from copy import deepcopy
import json
from urllib.parse import parse_qs, urlsplit
import unittest

from _dev_tools import test_import_cache_and_saved_matches  # Calibre stubs for storage
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError
from parser.oprah_book_club import OprahBookClubParser
from storage import build_import_cache_data
from url_fetcher.oprah_book_club import UrlFetcherOprahBookClub


class OprahUpdateTests(unittest.TestCase):

  def setUp(self):
    self.parser = OprahBookClubParser()
    self.parser.LISTICLE_PAGE_SIZE = 2
    self.url = 'https://www.oprahdaily.com/books/'
    self.calls = []
    self.slides = [self.slide(n) for n in range(6, 0, -1)]

  def slide(self, n):
    return {'media_id': f'm{n}', 'product_id': f'p{n}', 'name': f'Story {n}, by Writer {n}'}

  def html(self, slides=None, listicle='list'):
    slides = self.slides if slides is None else slides
    data = {'props': {'pageProps': {'embeddedListicleId': listicle,
      'embeddedListicleSlideCount': len(slides), 'slides': slides[:2],
      'mediaIdPages': [[s['media_id'] for s in slides[i:i+2]] for i in range(2,len(slides),2)]}}}
    return '<script id="__NEXT_DATA__">' + json.dumps(data) + '</script>'

  def fetch(self, url):
    self.calls.append(url)
    page = int(parse_qs(urlsplit(url).query)['page'][0])
    return json.dumps(self.slides[(page-1)*2:page*2])

  def parse(self, cache=None, html=None, fetch=None):
    return self.parser.parse(html or self.html(),self.url,
      fetch_url=fetch or self.fetch, cached_parsed=cache, incremental_update=cache is not None)

  def cache(self, parsed):
    return build_import_cache_data('oprah',parsed)

  def test_full_update_and_disk_schema_roundtrip_preserve_entries_and_skip_pages(self):
    full=self.parse()
    self.assertEqual(2,len(self.calls))
    cache=json.loads(json.dumps(self.cache(full)))
    self.calls=[]
    update=self.parse(cache)
    self.assertEqual(full['entries'],update['entries'])
    self.assertEqual([],self.calls)
    self.assertEqual(update['entries'],self.parse(self.cache(update))['entries'])

  def test_added_front_book_and_shifted_paging_keep_history(self):
    old=self.cache(self.parse())
    self.slides.insert(0,self.slide(7))
    updated=self.parse(old)
    calls=len(self.calls)
    fresh=self.parse()
    self.assertEqual(fresh['entries'],updated['entries'])
    self.assertEqual(['Story '+str(i) for i in range(1,8)], [e['title'] for e in updated['entries']])
    self.assertEqual(2,calls)  # only the two initial baseline requests

  def test_removed_or_reordered_entries_refetch_changed_rank_units(self):
    old=self.cache(self.parse())
    self.slides=[self.slides[i] for i in (0,1,4,3,2)]
    updated=self.parse(old)
    fresh=self.parse()
    self.assertEqual(fresh['entries'],updated['entries'])

  def test_missing_unit_requires_fetch_and_recovers_real_missing_entries(self):
    old=without_unit(self.cache(self.parse()),'m4')
    self.calls=[]
    updated=self.parse(old)
    self.assertEqual(1,len(self.calls))
    self.assertEqual(self.parse()['entries'],updated['entries'])

  def test_legacy_and_changed_listicle_fetch_all_linked_pages(self):
    old=self.cache(self.parse())
    for cache,html in [({'entries':old['entries']},self.html()),(old,self.html(listicle='new'))]:
      self.calls=[]
      self.parse(cache,html)
      self.assertEqual(2,len(self.calls))

  def test_failed_changed_page_preserves_history_and_remains_retryable(self):
    old=self.cache(self.parse())
    old['incremental_state']['units']['m4']['complete']=False
    def fail(url):
      raise OSError('offline')
    updated=self.parse(old,fetch=fail)
    self.assertEqual(old['entries'],updated['entries'])
    self.assertTrue(updated['notes'])
    self.assertFalse(updated['incremental_state']['units']['m4']['complete'])
    self.calls=[]
    retried=self.parse(self.cache(updated))
    self.assertEqual(1,len(self.calls))
    self.assertEqual(old['entries'],retried['entries'])

  def test_cancellation_propagates(self):
    def cancel(url):
      raise ImportCancelledError('cancelled')
    with self.assertRaises(ImportCancelledError):
      self.parse(fetch=cancel)

  def test_unusable_source_cannot_erase_saved_entries(self):
    old=self.cache(self.parse())
    with self.assertRaises(ValueError):
      self.parse(old,html='<h1>Unavailable</h1>')

  def test_fetcher_forwards_optional_contract(self):
    recipe=UrlFetcherOprahBookClub()
    recipe.create_parser=lambda:self.parser
    result=recipe.parse(self.html(),fetch_url=self.fetch)
    self.assertIn('incremental_state',result)
    self.calls=[]
    update=recipe.parse(self.html(),fetch_url=self.fetch,
      cached_parsed=self.cache(result),incremental_update=True)
    self.assertEqual(result['entries'],update['entries'])
    self.assertEqual([],self.calls)


if __name__ == '__main__':
  unittest.main()
