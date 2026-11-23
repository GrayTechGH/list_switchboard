import copy
import json
import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError,ImportCancelledError
from parser.carnegie_medal import (CarnegieMedalParser,SHORTLIST_ARCHIVE_2010_2015_URL,
  shortlist_archive_url,current_shortlist_url,shortlist_news_url,winner_news_url,current_winners_url)
from storage import build_import_cache_data
from url_fetcher.carnegie_medal import UrlFetcherCarnegieMedalForWriting


class CarnegieUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=UrlFetcherCarnegieMedalForWriting()
    self.current_year=2017
    self.calls,self.failures,self.overrides=[],{},{}
    self.winner=0
    self.missing_winner=None

  def title(self,year,index):return f'Tale {year} {index}'

  def front(self):
    lines=[f'{year} Writer {self.winner}, <em>{self.title(year,self.winner)},</em> Publisher'
      for year in range(2010,self.current_year+1) if year!=self.missing_winner]
    return '<nav><p>2027 Fake Book by Blogger</p></nav><h1>Medal for Writing Winners</h1><p>'+'<br>'.join(lines)+'</p>'

  def shortlist(self,year):
    return '<h2>Carnegie Medal for Writing Shortlist</h2><p>'+''.join(
      f'<em>{self.title(year,i)}</em> by Writer {i} (Publisher)<br>' for i in range(2))+'</p><h2>Medal for Illustration</h2><p>Excluded by Artist</p>'

  def fetch(self,url):
    self.calls.append(url)
    if url in self.failures:raise self.failures[url]
    if url in self.overrides:return self.overrides[url]
    if url==self.recipe.URL:return self.front()
    if url==SHORTLIST_ARCHIVE_2010_2015_URL:
      return ''.join(f'<h2>{year} CILIP Carnegie Medal Shortlist</h2><p>'+''.join(f'{self.title(year,i)} by Writer {i} (Publisher)<br>' for i in range(2))+'</p><h2>Kate Greenaway Shortlist</h2><p>Excluded by Artist</p>' for year in range(2010,2016))
    if url in (current_shortlist_url(self.current_year),shortlist_news_url(self.current_year)):
      return self.shortlist(self.current_year)
    if url in (winner_news_url(self.current_year),current_winners_url(self.current_year)):
      return f'<h1>{self.current_year} winners announced</h1><p>Writer {self.winner} won the Carnegie Medal for Writing for {self.title(self.current_year,self.winner)}.</p>'
    year=int(url.split('/archive/')[1][:4])
    return self.shortlist(year)

  def parse(self,old=None,incremental=None):
    with patch('parser.carnegie_medal.date') as clock:
      clock.today.return_value.year=self.current_year
      return self.recipe.fetch_and_parse(self.fetch,cached_parsed=old,
        incremental_update=(old is not None) if incremental is None else incremental)

  def cache(self,parsed):return build_import_cache_data(self.recipe.source_id,parsed)

  def test_missing_closed_shortlist_recovery_and_repeated_update(self):
    full=self.parse()
    self.assertEqual(16,len(full['entries']))
    self.assertEqual(4,len(self.calls))
    old=without_unit(self.cache(full),'2016')
    self.assertLess(len(old['entries']),len(full['entries']))
    self.calls.clear();update=self.parse(old)
    self.assertEqual(full['entries'],update['entries'])
    self.assertEqual(3,len(self.calls))
    self.calls.clear();self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])
    self.assertEqual([self.recipe.URL,shortlist_archive_url(2017)],self.calls)

  def test_new_year_reuses_previous_closed_shortlist(self):
    old=self.cache(self.parse());self.current_year=2018
    self.calls.clear();update=self.parse(old)
    self.assertEqual([self.recipe.URL,shortlist_archive_url(2018)],self.calls)
    self.assertEqual(self.parse()['entries'],update['entries'])

  def test_fresh_archive_promotes_and_demotes_original_cached_nominees(self):
    old=self.cache(self.parse());self.winner=1
    self.calls.clear();update=self.parse(old)
    self.assertNotIn(shortlist_archive_url(2016),self.calls)
    self.assertEqual(self.parse()['entries'],update['entries'])
    self.assertEqual({'Tale 2016 1':'winner','Tale 2016 0':'shortlisted'},
      {r['title']:r['result'] for r in update['entries'] if r['award_year']=='2016'})

  def test_current_fallbacks_run_when_winner_archive_lags(self):
    self.missing_winner=self.current_year
    full=self.parse()
    for url in (current_shortlist_url(self.current_year),shortlist_news_url(self.current_year),winner_news_url(self.current_year),current_winners_url(self.current_year)):
      self.assertIn(url,self.calls)
    self.assertEqual('winner',next(r['result'] for r in full['entries'] if r['title']==self.title(self.current_year,0)))
    self.assertEqual(full['entries'],self.parse(self.cache(full))['entries'])

  def test_missing_historical_winner_prevents_shortlist_reuse(self):
    self.missing_winner=2016
    old=self.cache(self.parse());self.calls.clear();self.parse(old)
    self.assertIn(shortlist_archive_url(2016),self.calls)

  def test_failed_or_challenged_current_source_retains_prior_rows(self):
    full=self.parse();old=self.cache(full);url=shortlist_archive_url(2017)
    for failure in (RuntimeError('offline'),'<html>Challenge</html>'):
      self.failures.clear();self.overrides.clear()
      if isinstance(failure,Exception):self.failures[url]=failure
      else:self.overrides[url]=failure
      update=self.parse(old)
      self.assertFalse(update['incremental_state']['units']['2017']['complete'])
      self.assertEqual({r['title'] for r in full['entries']},{r['title'] for r in update['entries']})
    self.overrides.clear()
    self.assertTrue(self.parse(self.cache(update))['incremental_state']['units']['2017']['complete'])

  def test_partial_aggregate_is_usable_but_pending_and_cannot_replace_history(self):
    full=self.parse()
    self.overrides[SHORTLIST_ARCHIVE_2010_2015_URL]='<h2>2015 CILIP Carnegie Medal Shortlist</h2><p>Tale 2015 0 by Writer 0</p>'
    old=without_unit(self.cache(full),'2010-2015')
    update=self.parse(old)
    self.assertFalse(update['incremental_state']['units']['2010-2015']['complete'])
    self.assertIn('Tale 2015 0',[r['title'] for r in update['entries']])
    update=self.parse(self.cache(full))
    self.assertEqual(full['entries'],update['entries'])

  def test_legacy_wrong_scope_and_complete_refresh_read_all_pages(self):
    old=self.cache(self.parse())
    legacy=copy.deepcopy(old);legacy.pop('incremental_state')
    wrong=copy.deepcopy(old);wrong['incremental_state']['source_key']='other'
    for candidate,incremental in ((legacy,True),(wrong,True),(old,False)):
      self.calls.clear();self.parse(candidate,incremental)
      self.assertEqual(4,len(self.calls))

  def test_cancellation_and_browser_requirements_propagate(self):
    for url in (SHORTLIST_ARCHIVE_2010_2015_URL,shortlist_archive_url(2017)):
      for error in (ImportCancelledError,CamoufoxRequiredError):
        self.failures={url:error('stop')}
        with self.assertRaises(error):self.parse()

  def test_structural_archive_keeps_titles_coauthors_withheld_notes_and_ignores_nav(self):
    html='''<nav><p>2027 Book by Blogger</p></nav><h1>Medal for Writing Winners</h1>
      <p>2022 Katya Balen, <em>October, October, </em>Publisher<br>1970 Leon Garfield &amp; Edward Blishen, <em>The God Beneath the Sea</em>, Publisher</p>
      <p><em>In 1943, 1945 and 1966 the prize was withheld as no book was considered suitable</em></p>'''
    rows,notes=CarnegieMedalParser().winner_archive_rows(html)
    self.assertEqual([('2022','October, October','Katya Balen'),('1970','The God Beneath the Sea','Leon Garfield & Edward Blishen')],
      [(r['award_year'],r['title'],r['author']) for r in rows])
    self.assertEqual(3,len(notes))

  def test_br_separated_shortlists_preserve_inline_word_fragments(self):
    html='''<h2>2011 CILIP Carnegie Medal Shortlist</h2><p><em>W</em><em>hite Crow</em> by Marcus Sedgwick (Publisher)<br>Other Tale by Other Writer</p>
      <h2>2011 CILIP Kate Greenaway Shortlist</h2><p>Excluded by Artist</p>'''
    rows=CarnegieMedalParser().shortlist_page_rows(html,SHORTLIST_ARCHIVE_2010_2015_URL)
    self.assertEqual(['White Crow','Other Tale'],[r['title'] for r in rows])

  def test_modern_cards_and_winner_articles_respect_writing_boundary(self):
    parser=CarnegieMedalParser()
    html='''<h1>Carnegie Medal for Writing Shortlist 2026</h1><p><a href="/books/wolf-siren/"><strong>Wolf Siren</strong><span>Beth O'Brien<br>Publisher</span></a></p>'''
    rows=parser.shortlist_page_rows(html,current_shortlist_url(2026))
    self.assertEqual([('Wolf Siren',"Beth O'Brien")],[(r['title'],r['author']) for r in rows])
    news='''<h1>Winners announced 2026</h1><p>In a shortlist dominated by established names, new talent won applause.</p>
      <p><strong>Carnegie Medal for Writing winner, Beth O'Brien, said:</strong></p>
      <p><em>Wolf Siren</em> by Beth O'Brien (Publisher)</p><p><em>Art Book</em> by Another Artist (Publisher)</p>'''
    self.assertEqual(['Wolf Siren'],[r['title'] for r in parser.winner_page_rows(news,winner_news_url(2026))])

  def test_cache_covers_flat_entries_without_raw_pages(self):
    old=self.cache(self.parse())
    used={i for u in old['incremental_state']['units'].values() for i in u['entry_indexes']}
    self.assertEqual(set(range(len(old['entries']))),used)
    self.assertNotIn('<em>',json.dumps(old))
