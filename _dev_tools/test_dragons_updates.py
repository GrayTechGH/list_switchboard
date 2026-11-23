from datetime import date
from urllib.parse import parse_qs,urlparse
import unittest

from _dev_tools.test_import_matching import dragons_jetpacks_page,dragons_jetpacks_row
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError
from parser.dragons_and_jetpacks import DragonsJetpacksParser,SHELF_URL
from storage import build_import_cache_data
from url_fetcher.dragons_and_jetpacks import UrlFetcherDragonsJetpacks


class DragonsUpdateTests(unittest.TestCase):

  def setUp(self):
    self.parser=DragonsJetpacksParser()
    self.ids=list(range(8,0,-1))
    self.calls=[]
    self.with_counter=True

  def page(self,n):
    ids=self.ids[(n-1)*2:n*2]
    rows=[]
    for key in ids:
      start,end=('2026/11/01','2026/12/31') if key>=7 else ('2020/01/01','2020/01/31')
      rows.append(dragons_jetpacks_row(key,f'Novel {key}',['Writer, One'],
        ['group-read','fantasy','2020'],start,end))
    link=SHELF_URL+f'&page={n+1}' if n*2<len(self.ids) else ''
    html=dragons_jetpacks_page(rows,link)
    if self.with_counter:
      html=html.replace('</body>',f'<span class="smallText">Showing {(n-1)*2+1}-{min(n*2,len(self.ids))} of {len(self.ids)}</span></body>')
    return html

  def fetch(self,url):
    self.calls.append(url)
    return self.page(int(parse_qs(urlparse(url).query)['page'][0]))

  def parse(self,cache=None):
    return self.parser.parse(self.page(1),SHELF_URL,fetch_url=self.fetch,
      cached_parsed=cache,incremental_update=cache is not None,today=date(2026,11,16))

  def cache(self,parsed):
    return build_import_cache_data('dragons',parsed)

  def test_update_reuses_verified_history_after_refreshed_current_prefix(self):
    full=self.parse(); self.assertEqual(3,len(self.calls))
    self.calls=[]
    updated=self.parse(self.cache(full))
    self.assertEqual(full['entries'],updated['entries'])
    self.assertEqual([],self.calls)
    self.assertTrue(updated['incremental_state']['discovery']['complete_snapshot'])

  def test_new_books_shift_page_boundaries_without_losing_cached_tail(self):
    old=self.cache(self.parse())
    self.ids.insert(0,9)
    self.calls=[]
    updated=self.parse(old)
    self.assertEqual(1,len(self.calls))
    self.assertEqual(self.parse()['entries'],updated['entries'])
    self.assertEqual(9,len(updated['entries']))

  def test_deletion_or_order_change_requires_full_reconciliation(self):
    old=self.cache(self.parse())
    self.ids.remove(3)
    self.calls=[]
    updated=self.parse(old)
    self.assertEqual(3,len(self.calls))
    self.assertEqual(self.parse()['entries'],updated['entries'])
    self.ids=[8,6,7,5,4,2,1]
    self.calls=[]
    updated=self.parse(self.cache(updated))
    self.assertEqual(3,len(self.calls))
    self.assertEqual(self.parse()['entries'],updated['entries'])

  def test_missing_current_record_is_recovered_but_missing_old_record_is_not_skipped(self):
    full=self.parse()
    self.calls=[]
    updated=self.parse(without_unit(self.cache(full),'8'))
    self.assertEqual([],self.calls)
    self.assertEqual(full['entries'],updated['entries'])
    self.calls=[]
    updated=self.parse(without_unit(self.cache(full),'1'))
    self.assertEqual(3,len(self.calls))
    self.assertEqual(full['entries'],updated['entries'])

  def test_older_unfinished_read_is_rechecked_even_outside_first_page(self):
    full=self.parse(); old=self.cache(full)
    del old['entries'][0]['discussion_end_date']
    self.calls=[]
    updated=self.parse(old)
    self.assertEqual(3,len(self.calls))
    self.assertEqual(full['entries'],updated['entries'])

  def test_missing_counts_or_legacy_state_disables_shortcut(self):
    full=self.parse()
    self.with_counter=False
    self.calls=[]
    updated=self.parse(self.cache(full))
    self.assertEqual(3,len(self.calls))
    self.assertEqual(full['entries'],updated['entries'])
    self.with_counter=True
    self.calls=[]
    self.parse({'entries':full['entries']})
    self.assertEqual(3,len(self.calls))

  def test_fetcher_requests_explicit_order_and_required_browser_does_not_fall_back(self):
    recipe=UrlFetcherDragonsJetpacks()
    query=parse_qs(urlparse(recipe.primary_urls()[0]).query)
    self.assertEqual(['date_added'],query['sort'])
    self.assertEqual(['d'],query['order'])
    def blocked(url,**kwargs): raise CamoufoxRequiredError('required')
    with self.assertRaises(CamoufoxRequiredError): recipe.fetch_and_parse(blocked)


if __name__=='__main__':
  unittest.main()
