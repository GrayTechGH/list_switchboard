import unittest
from unittest.mock import patch

from _dev_tools.test_import_matching import main
from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError,ImportCancelledError
from storage import build_import_cache_data
from url_fetcher.walter_scott import UrlFetcherWalterScottPrize
from parser.walter_scott import RESULT_SHORTLISTED,RESULT_WINNER,WalterScottOfficialParser


class WalterScottUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe=UrlFetcherWalterScottPrize()
    self.calls,self.failures=[],{}
    self.year=2026
    self.shortlist=f'https://www.walterscottprize.co.uk/the-{self.year}-shortlist/'
    self.winner=f'https://www.walterscottprize.co.uk/winner-{self.year}/'
    self.parser=patch.object(WalterScottOfficialParser,'SUPPLEMENT_URLS',((self.shortlist,RESULT_SHORTLISTED),(self.winner,RESULT_WINNER)))
    self.parser.start()
    self.addCleanup(self.parser.stop)
    self.coverage=patch.object(WalterScottOfficialParser,'HISTORY_COUNTS',{y:2 for y in range(2010,2026)})
    self.coverage.start()
    self.addCleanup(self.coverage.stop)
    self.clock=patch('parser.walter_scott.datetime')
    self.dates=self.clock.start()
    self.dates.datetime.now.return_value.year=self.year
    self.addCleanup(self.clock.stop)

  def fetch(self,url,**kwargs):
    self.calls.append(url)
    if url in self.failures: raise self.failures[url]
    if url==self.recipe.URL:
      return '\n'.join(f'{y}\nWinner: Winner {y} by Writer One\nShortlist: Other {y} by Writer Two' for y in range(2010,2026))
    year=WalterScottOfficialParser().year_from_text(url)
    if 'shortlist' in url:
      return f'<div id="content"><h1>The {year} Shortlist</h1><p>The {year} Shortlist comprised:</p><p>Current Winner by Current Author (Publisher)<br/>Current Other by Other Author (Publisher)</p><blockquote><p>Excluded by Quoted Writer</p></blockquote><p>Publisher, Example Press</p></div>'
    return f'<aside>Bad, Sidebar</aside><div id="content"><h1>Current Author wins {year} Walter Scott Prize</h1><p class="date">12th June, {year}</p><p>Current Author has won the Prize for her novel <em>Current Winner</em>, which tells the story by someone else.</p><p>The judges said: long quotation by Quoted Writer.</p></div>'

  def parse(self,old=None,**kwargs):
    return self.recipe.fetch_and_parse(self.fetch,source_choice=0,cached_parsed=old,incremental_update=old is not None,**kwargs)

  def cache(self,parsed):
    return build_import_cache_data(self.recipe.source_id,parsed)

  def test_missing_current_entries_repeat_and_winner_promotion(self):
    full=self.parse()
    self.assertEqual(34,len(full['entries']))
    self.assertEqual(3,len(self.calls))
    old=without_unit(self.cache(full),self.shortlist)
    self.assertEqual(33,len(old['entries']))
    self.calls.clear()
    update=self.parse(old)
    self.assertEqual(full['entries'],update['entries'])
    self.assertEqual([self.shortlist,self.winner],self.calls)
    self.calls.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])
    self.assertEqual([self.shortlist,self.winner],self.calls)

  def test_missing_or_invalid_history_forces_pdf_fetch(self):
    full=self.parse()
    old=without_unit(self.cache(full),'history')
    self.calls.clear()
    self.assertEqual(full['entries'],self.parse(old)['entries'])
    self.assertEqual([self.recipe.URL,self.shortlist,self.winner],self.calls)
    old=self.cache(full)
    old['incremental_state']['units']['history']['complete']=False
    self.calls.clear()
    self.parse(old)
    self.assertIn(self.recipe.URL,self.calls)

  def test_new_announcements_and_rollover_reuse_compatible_history(self):
    old=self.cache(self.parse())
    self.dates.datetime.now.return_value.year=2027
    urls=((self.shortlist,RESULT_SHORTLISTED),(self.winner,RESULT_WINNER),
      ('https://www.walterscottprize.co.uk/the-2027-shortlist/',RESULT_SHORTLISTED),
      ('https://www.walterscottprize.co.uk/winner-2027/',RESULT_WINNER))
    with patch.object(WalterScottOfficialParser,'SUPPLEMENT_URLS',urls):
      self.calls.clear()
      update=self.parse(old)
      self.assertEqual([url for url,result in urls[2:]],self.calls)
      self.assertEqual(self.parse()['entries'],update['entries'])

  def test_failed_announcement_retains_source_rows_pending_then_recovers(self):
    full=self.parse()
    self.failures[self.shortlist]=OSError('offline')
    pending=self.parse(self.cache(full))
    self.assertEqual(full['entries'],pending['entries'])
    self.assertFalse(pending['incremental_state']['units'][self.shortlist]['complete'])
    self.assertTrue(pending['notes'])
    self.failures.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(pending))['entries'])

  def test_legacy_scope_caches_and_critical_failures(self):
    full=self.parse()
    wrong=self.cache(full)
    wrong['incremental_state']['source_key']='other PDF version'
    for old in ({'entries':full['entries']},wrong,['invalid cache']):
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(old)['entries'])
      self.assertEqual(3,len(self.calls))
    for error in (ImportCancelledError('stop'),CamoufoxRequiredError('required')):
      self.failures[self.winner]=error
      with self.assertRaises(type(error)): self.parse(self.cache(full))

  def test_pdf_response_decoding_is_lossless_without_affecting_html(self):
    data=b'%PDF-1.6\r\nstream\r\x00\xff\x8d\x0a\xe3\r\nendstream'
    self.assertEqual(data,main.decode_response_data(data,charset='utf-8').encode('latin-1'))
    self.assertEqual('<p>caf\u00e9</p>',main.decode_response_data('<p>caf\u00e9</p>'.encode('utf-8'),charset='utf-8'))

  def test_pdf_columns_keep_years_and_long_left_titles_together(self):
    def line(y,words):
      return f'<line yMin="{y}">'+''.join(f'<word xMin="{x}">{word}</word>' for x,word in words)+'</line>'
    xml=('<doc><page width="600">'+line(10,[(90,'2025')])+line(10,[(305,'2024')])+
      line(20,[(90,'Winner:'),(140,'Left'),(180,'by'),(200,'LeftWriter')])+
      line(20,[(305,'Winner:'),(350,'Right'),(400,'by'),(425,'RightWriter')])+
      line(30,[(90,'Shortlist:'),(150,'Long'),(190,'Title'),(230,'by'),(280,'Left'),(300,'Surname')])+
      line(30,[(305,'Shortlist:'),(365,'Other'),(410,'by'),(430,'OtherWriter')])+'</page></doc>').encode()
    text=WalterScottOfficialParser().pdf_columns(xml)
    self.assertEqual(['2025','Winner: Left by LeftWriter','Shortlist: Long Title by Left Surname','2024','Winner: Right by RightWriter','Shortlist: Other by OtherWriter'],text.splitlines())

  def test_pdf_coverage_rejects_missing_year_or_winner(self):
    parser=WalterScottOfficialParser()
    rows=parser.parse_pdf_rows(self.fetch(self.recipe.URL),self.recipe.URL)
    self.assertTrue(parser.history_complete(rows,self.recipe.URL))
    self.assertFalse(parser.history_complete([r for r in rows if r['award_year']!='2015'],self.recipe.URL))
    self.assertFalse(parser.history_complete([r for r in rows if not (r['award_year']=='2015' and r['result']=='winner')],self.recipe.URL))

  def test_modern_articles_exclude_prose_dates_quotes_and_publishers(self):
    parsed=self.parse()
    current=[r for r in parsed['entries'] if r['award_year']=='2026']
    self.assertEqual([('Current Winner',['Current Author'],'winner'),('Current Other',['Other Author'],'shortlisted')],[(r['title'],r['authors'],r['result']) for r in current])


if __name__=='__main__':
  unittest.main()
