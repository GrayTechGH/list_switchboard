from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError,CamoufoxRequiredError
from parser.bookbrowse import BookBrowseOnlineBookClubParser,LEGACY_URL,CATEGORIES_URL,COMMUNITY_URL
from storage import build_import_cache_data
from url_fetcher.bookbrowse import UrlFetcherBookBrowseOnlineBookClub


class BookBrowseUpdateTests(unittest.TestCase):

  def setUp(self):
    self.parser=BookBrowseOnlineBookClubParser()
    self.root='https://www.bookbrowse.com/onlinebookclub/'
    self.calls=[]
    self.categories=[self.category(20,'Modern Story'),self.category(21,'Recent Story')]
    self.landing='<h1>The BookBrowse Book Club</h1><h3>Discussions Coming Soon</h3><ul></ul>'
    self.legacy='<h1>2024 Book Discussions</h1><h2><a href="threads.cfm?forumid=24">Archived Story by Alice Writer</a></h2>'\
      '<h1>2011 Book Discussions</h1><h2><a href="threads.cfm?forumid=11">Early Story by Early Writer</a></h2>'

  def category(self,n,title):
    return {'id':n,'parent_category_id':5,'slug':f'discussion-{n}','name':title,
      'description_text':f'Please join BookBrowse for a discussion of {title} by Current Writer.',
      'topic_url':f'/t/about-{n}/{n*10}'}

  def fetch(self,url):
    self.calls.append(url)
    if url==LEGACY_URL: return self.legacy
    if url==CATEGORIES_URL: return json.dumps({'categories':self.categories})
    return json.dumps({'post_stream':{'posts':[{'created_at':'2026-07-16T14:00:00Z'}]}})

  def parse(self,cache=None,fetch=None):
    return self.parser.parse(self.landing,self.root,fetch_url=fetch or self.fetch,
      cached_parsed=cache,incremental_update=cache is not None)

  def cache(self,parsed):
    return build_import_cache_data('bookbrowse',parsed)

  def test_full_update_reuses_legacy_and_immutable_topic_creation_dates(self):
    full=self.parse(); self.assertEqual(4,len(self.calls))
    self.calls=[]
    updated=self.parse(self.cache(full))
    self.assertEqual(full['entries'],updated['entries'])
    self.assertEqual([CATEGORIES_URL],self.calls)

  def test_missing_current_rows_recover_from_fresh_index_with_historical_reuse(self):
    full=self.parse(); old=without_unit(self.cache(full),'fresh-identities')
    self.calls=[]
    updated=self.parse(old)
    self.assertEqual(full['entries'],updated['entries'])
    self.assertEqual([CATEGORIES_URL],self.calls)

  def test_added_and_removed_categories_are_reflected_without_stale_entries(self):
    old=self.cache(self.parse())
    self.categories.pop(0)
    self.categories.append(self.category(22,'Newest Story'))
    updated=self.parse(old)
    self.assertEqual(self.parse()['entries'],updated['entries'])
    self.assertNotIn('Modern Story',{e['title'] for e in updated['entries']})

  def test_corrupt_legacy_order_and_topic_date_metadata_are_rebuilt(self):
    old=self.cache(self.parse())
    old['incremental_state']['units']['legacy']['metadata']['source_order']={}
    for value in old['incremental_state']['discovery']['topic_dates'].values():
      value['date']='invalid'
    self.calls=[]
    updated=self.parse(old)
    self.assertIn(LEGACY_URL,self.calls)
    self.assertEqual(self.parse()['entries'],updated['entries'])

  def test_missing_topic_metadata_is_retried_after_optional_failure_without_losing_books(self):
    full=self.parse(); old=self.cache(full)
    topic=COMMUNITY_URL+'/t/about-21/210.json'
    del old['incremental_state']['discovery']['topic_dates'][topic]
    def fail(url):
      if url==topic: raise OSError('throttled')
      return self.fetch(url)
    updated=self.parse(old,fetch=fail)
    self.assertEqual(4,len(updated['entries']))
    self.assertTrue(updated['notes'])
    self.calls=[]
    retry=self.parse(self.cache(updated))
    self.assertIn(topic,self.calls)
    self.assertEqual(full['entries'],retry['entries'])

  def test_legacy_cache_and_cross_era_merge_preserve_full_parser_behavior(self):
    full=self.parse()
    self.calls=[]
    self.assertEqual(full['entries'],self.parse({'entries':full['entries']})['entries'])
    self.assertEqual(4,len(self.calls))
    self.categories[0]=self.category(20,'Archived Story')
    self.categories[0]['description_text']='Please join BookBrowse for a discussion of Archived Story by Alice Writer.'
    update=self.parse(self.cache(full))
    self.assertEqual(self.parse()['entries'],update['entries'])

  def test_cancellation_and_required_browser_are_not_native_recovery_or_optional_notes(self):
    recipe=UrlFetcherBookBrowseOnlineBookClub()
    for error in (ImportCancelledError,CamoufoxRequiredError):
      def fail(url,**kwargs): raise error('stop')
      with patch('url_fetcher.bookbrowse.calibre_https_fetch') as native:
        with self.assertRaises(error): recipe.fetch_and_parse(fail)
        native.assert_not_called()
      def topic_fail(url):
        if url.startswith(COMMUNITY_URL+'/t/'): raise error('stop')
        return self.fetch(url)
      with self.assertRaises(error): self.parse(fetch=topic_fail)


if __name__=='__main__':
  unittest.main()
