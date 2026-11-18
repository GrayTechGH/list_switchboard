from datetime import date
import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError,CamoufoxRequiredError
from parser.big_library_read import LIBBY_ARCHIVE_SPECS,LibbyReadsGlobalParser
from storage import build_import_cache_data
from url_fetcher.big_library_read import UrlFetcherLibbyReadsGlobal


class LibbyUpdateTests(unittest.TestCase):

  def setUp(self):
    self.parser=LibbyReadsGlobalParser()
    self.root='https://www.libbylife.com/libby-reads'
    self.calls=[]
    self.details={
      LIBBY_ARCHIVE_SPECS[1][0]:('Meet the Neighbors','Brandon Keim','March 26 - April 9, 2026'),
      LIBBY_ARCHIVE_SPECS[2][0]:("I See You've Called in Dead",'John Kenney','July 9 - 23, 2026'),
      LIBBY_ARCHIVE_SPECS[3][0]:('Secrets of the Broken House','Taryn Souders','November 24 - December 8, 2026')}

  def fetch(self,url):
    self.calls.append(url)
    title,author,dates=self.details[url]
    return f'<h1>{title}</h1><p>Written by {author}</p><p>LIBBY READS GLOBAL</p><p>{dates}</p>'

  def parse(self,cache=None,fetch=None,html=None,today=date(2026,11,16)):
    return self.parser.parse(html or '<h1>Libby Reads</h1>',self.root,
      fetch_url=fetch or self.fetch,cached_parsed=cache,incremental_update=cache is not None,today=today)

  def cache(self,parsed):
    return build_import_cache_data('libby',parsed)

  def test_update_skips_closed_events_and_keeps_announced_event_fresh(self):
    full=self.parse(); self.assertEqual(3,len(self.calls))
    self.calls=[]
    update=self.parse(self.cache(full))
    self.assertEqual(full['entries'],update['entries'])
    self.assertEqual([LIBBY_ARCHIVE_SPECS[3][0]],self.calls)
    self.assertEqual(40,len(update['entries']))
    self.calls=[]
    self.parse(self.cache(update),today=date(2027,1,1))
    self.assertEqual([],self.calls)

  def test_missing_closed_event_is_recovered_alongside_current_event(self):
    full=self.parse()
    old=without_unit(self.cache(full),LIBBY_ARCHIVE_SPECS[1][0])
    self.calls=[]
    update=self.parse(old)
    self.assertEqual(full['entries'],update['entries'])
    self.assertEqual([LIBBY_ARCHIVE_SPECS[1][0],LIBBY_ARCHIVE_SPECS[3][0]],self.calls)

  def test_new_global_event_is_discovered_and_regional_event_is_excluded(self):
    old=self.cache(self.parse())
    url='https://www.libbylife.com/events/libby-reads-new-global'
    self.details[url]=('New Global Selection','Writer Name','January 5 - 19, 2027')
    html=f'<li><a href="{url}">New Global - Libby Reads GLOBAL</a></li>'\
      '<li><a href="/events/local">Local - Libby Reads US</a></li>'
    update=self.parse(old,html=html)
    self.assertEqual(self.parse(html=html)['entries'],update['entries'])
    self.assertEqual(41,len(update['entries']))

  def test_failed_current_refresh_keeps_remote_cache_unit_pending(self):
    old=self.cache(self.parse())
    def fail(url):
      if url==LIBBY_ARCHIVE_SPECS[3][0]: raise OSError('offline')
      return self.fetch(url)
    update=self.parse(old,fetch=fail)
    self.assertEqual(old['entries'],update['entries'])
    self.assertTrue(update['notes'])
    self.assertFalse(update['incremental_state']['units'][LIBBY_ARCHIVE_SPECS[3][0]]['complete'])
    self.calls=[]
    self.parse(self.cache(update))
    self.assertEqual([LIBBY_ARCHIVE_SPECS[3][0]],self.calls)

  def test_legacy_cache_rebuilds_all_remote_units(self):
    full=self.parse(); self.calls=[]
    self.assertEqual(full['entries'],self.parse({'entries':full['entries']})['entries'])
    self.assertEqual(3,len(self.calls))

  def test_cancellation_and_required_browser_cannot_be_hidden_by_native_or_ledger_fallback(self):
    recipe=UrlFetcherLibbyReadsGlobal()
    for error in (ImportCancelledError,CamoufoxRequiredError):
      def cancel(url,**kwargs): raise error('stop')
      with patch('url_fetcher.big_library_read.calibre_https_fetch') as native:
        with self.assertRaises(error):
          recipe.fetch_and_parse(cancel)
        native.assert_not_called()


if __name__=='__main__':
  unittest.main()
