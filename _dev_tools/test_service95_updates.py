import unittest

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError
from parser.service95_book_club import Service95BookClubParser
from storage import build_import_cache_data


class Service95UpdateTests(unittest.TestCase):

  def setUp(self):
    self.parser=Service95BookClubParser()
    self.root='https://www.service95.com/book-club'
    self.months={1:'January',2:'February',3:'March',4:'April'}
    self.ids=[3,2,1]
    self.calls=[]

  def url(self,n):
    return f'https://www.service95.com/books/story-{n}'

  def html(self):
    return ''.join(f'<a href="/books/story-{n}"><img alt="Monthly Read for {self.months[n]}: Story {n} by Writer {n} 2026"></a>'
      for n in self.ids)

  def fetch(self,url):
    self.calls.append(url)
    n=int(url.rsplit('-',1)[-1])
    return f'<h1>Story {n}</h1><p>{self.months[n]} 2026</p>'

  def parse(self,cache=None,fetch=None,html=None):
    return self.parser.parse(html or self.html(),self.root,fetch_url=fetch or self.fetch,
      cached_parsed=cache,incremental_update=cache is not None)

  def cache(self,parsed):
    return build_import_cache_data('service95',parsed)

  def test_complete_update_keeps_history_and_refreshes_current_detail(self):
    full=self.parse(); self.assertEqual(3,len(self.calls))
    self.assertEqual(3,len(full['entries']))
    self.calls=[]
    update=self.parse(self.cache(full))
    self.assertEqual(full['entries'],update['entries'])
    self.assertEqual([self.url(3)],self.calls)

  def test_missing_history_and_new_month_both_discovered(self):
    full=self.parse(); old=without_unit(self.cache(full),self.url(1))
    self.calls=[]
    updated=self.parse(old)
    self.assertEqual([self.url(3),self.url(1)],self.calls)
    self.assertEqual(full['entries'],updated['entries'])
    self.ids.insert(0,4)
    new=self.parse(self.cache(updated))
    self.assertEqual(self.parse()['entries'],new['entries'])

  def test_failed_historical_detail_keeps_complete_rows_and_pending_retry(self):
    old=self.cache(self.parse())
    old['incremental_state']['units'][self.url(1)]['complete']=False
    def fail(url):
      if url==self.url(1): raise OSError('offline')
      return self.fetch(url)
    update=self.parse(old,fetch=fail)
    self.assertEqual(old['entries'],update['entries'])
    self.assertFalse(update['incremental_state']['units'][self.url(1)]['complete'])
    self.calls=[]
    self.parse(self.cache(update))
    self.assertIn(self.url(1),self.calls)

  def test_removed_card_is_removed_from_merged_list_and_legacy_cache_refreshes(self):
    old=self.cache(self.parse())
    self.ids.remove(1)
    update=self.parse(old)
    self.assertEqual(self.parse()['entries'],update['entries'])
    self.calls=[]
    self.parse({'entries':old['entries']})
    self.assertEqual(2,len(self.calls))

  def test_cancellation_and_unusable_root_do_not_replace_saved_history(self):
    old=self.cache(self.parse())
    def cancel(url): raise ImportCancelledError('stop')
    with self.assertRaises(ImportCancelledError): self.parse(old,fetch=cancel)
    with self.assertRaises(ValueError): self.parse(old,html='<h1>Unavailable</h1>')


if __name__=='__main__':
  unittest.main()
