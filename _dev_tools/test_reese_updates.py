from copy import deepcopy
import unittest

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError, CamoufoxRequiredError
from parser.reese_book_club import ReeseBookClubParser, ReeseBookClubYAParser
from storage import build_import_cache_data


class ReeseUpdateTests(unittest.TestCase):

  def setUp(self):
    self.url='https://reesesbookclub.com/our-picks/'
    self.calls=[]
    self.books={n:(f'Story {n}',f'Writer {n}',f'January {2020+n} Pick') for n in range(1,7)}
    self.books[4]=('Fable','Adrienne Young','April 2021 Pick')
    self.books[2]=('Seasonal Story','Seasonal Writer','Spring 2023 YA Pick')
    self.ids=[6,5,4,3,2,1]

  def page(self,ids,root=False):
    cards=[]
    for n in ids:
      title,author,label=self.books[n]
      cards.append(f'<li class="wp-block-post book post-{n}"><figure><a href="/book/{n}/">'
        f'<img alt="{title}"></a></figure><div class="taxonomy-book_category">'
        f'{"" if n==6 else label}</div></li>')
    popups=''.join(f'<div class="popup-details" id="post-{n}"><div class="popup-content">'
      f'<h3>{self.books[n][0]}</h3><h4>{self.books[n][1]}</h4></div></div>' for n in self.ids)
    return ''.join(cards)+popups+('<a href="?query-2-page=2">Next</a>' if root else '')

  def fetch(self,url):
    self.calls.append(url)
    if 'query-2-page' in url:
      return self.page(self.ids[4:])
    return '<h2>January 2026 Pick</h2><h1>Story 6</h1><h3 class="mt-0">Writer 6</h3>'

  def parse(self,cache=None,parser=None,fetch=None,html=None):
    return (parser or ReeseBookClubParser()).parse(
      html or self.page(self.ids[:4],True),self.url,fetch_url=fetch or self.fetch,
      cached_parsed=cache,incremental_update=cache is not None)

  def cache(self,parsed):
    return build_import_cache_data('reese',parsed)

  def test_full_update_reuses_history_and_keeps_current_featured_detail_fresh(self):
    full=self.parse(); self.assertEqual(2,len(self.calls))
    self.calls=[]
    updated=self.parse(self.cache(full))
    self.assertEqual(full['entries'],updated['entries'])
    self.assertEqual([self.url.replace('/our-picks/','/book/6/')],self.calls)
    self.assertEqual(updated['entries'],self.parse(self.cache(updated))['entries'])

  def test_missing_root_entry_is_recovered_with_less_fetching(self):
    full=self.parse(); cache=without_unit(self.cache(full),'post-4')
    self.calls=[]
    updated=self.parse(cache)
    self.assertEqual(full['entries'],updated['entries'])
    self.assertEqual(1,len(self.calls))

  def test_new_and_removed_discovered_ids_require_historical_reconciliation(self):
    old=self.cache(self.parse())
    self.books[7]=('Newest Story','New Writer','February 2027 Pick')
    self.ids.insert(0,7)
    self.calls=[]
    updated=self.parse(old)
    self.assertEqual(updated['entries'],self.parse()['entries'])
    self.ids.remove(1)
    updated=self.parse(self.cache(updated))
    self.assertEqual(updated['entries'],self.parse()['entries'])

  def test_changed_historical_popup_invalidates_archive_shortcut(self):
    old=self.cache(self.parse())
    self.books[1]=('Corrected Story','Correct Writer','January 2021 Pick')
    self.calls=[]
    updated=self.parse(old)
    self.assertIn(self.url+'?query-2-page=2',self.calls)
    self.assertEqual(updated['entries'],self.parse()['entries'])

  def test_failed_archive_preserves_history_and_retries_incomplete_units(self):
    old=self.cache(self.parse())
    old['incremental_state']['units']['post-1']['complete']=False
    def failed(url):
      if 'query-2-page' in url: raise OSError('offline')
      return self.fetch(url)
    updated=self.parse(old,fetch=failed)
    self.assertEqual(old['entries'],updated['entries'])
    self.assertFalse(updated['incremental_state']['units']['post-1']['complete'])
    self.calls=[]
    retried=self.parse(self.cache(updated))
    self.assertIn(self.url+'?query-2-page=2',self.calls)
    self.assertEqual(old['entries'],retried['entries'])

  def test_ya_scope_is_separate_and_cannot_reuse_adult_cache(self):
    adult=self.cache(self.parse())
    parser=ReeseBookClubYAParser()
    full=self.parse(parser=parser)
    self.assertEqual({'Fable','Seasonal Story'},{e['title'] for e in full['entries']})
    self.calls=[]
    updated=self.parse(adult,parser=parser)
    self.assertEqual(full['entries'],updated['entries'])
    self.assertEqual(2,len(self.calls))
    self.calls=[]
    self.assertEqual(full['entries'],self.parse(self.cache(full),parser=parser)['entries'])
    self.assertEqual(1,len(self.calls))

  def test_cancellation_and_required_browser_errors_propagate(self):
    for error in (ImportCancelledError, CamoufoxRequiredError):
      def fail(url): raise error('stop')
      with self.assertRaises(error): self.parse(fetch=fail)

  def test_legacy_cache_rebuilds_unit_index(self):
    full=self.parse()
    self.calls=[]
    update=self.parse({'entries':deepcopy(full['entries'])})
    self.assertEqual(2,len(self.calls))
    self.assertTrue(update['incremental_state']['units'])

  def test_unusable_source_cannot_erase_saved_entries(self):
    old=self.cache(self.parse())
    with self.assertRaises(ValueError):
      self.parse(old,html='<h1>Unavailable</h1>')

  def test_malformed_incremental_state_rebuilds_without_losing_rows(self):
    full=self.parse()
    old=self.cache(full)
    old['incremental_state']=['invalid']
    updated=self.parse(old)
    self.assertEqual(full['entries'],updated['entries'])


if __name__=='__main__':
  unittest.main()
