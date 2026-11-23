import unittest

from _dev_tools import test_import_matching
from parser.lukas import LukasWikipediaParser, MarkLyntonHistoryPrizeWikipediaParser
from url_fetcher.lukas import (
  UrlFetcherJAnthonyLukasBookPrize, UrlFetcherMarkLyntonHistoryPrize,
  LUKAS_WIKIPEDIA_URL, MARK_LYNTON_WIKIPEDIA_URL,
)


class LukasWikipediaTests(unittest.TestCase):

  def parse(self, html):
    return LukasWikipediaParser().parse(html, LUKAS_WIKIPEDIA_URL, 'Lukas')

  def test_year_rowspan_and_separate_refs_keep_titles_authors_and_results(self):
    html='''<table><tr><th>Year</th><th>Author</th><th>Title</th><th>Publisher</th><th>Result</th><th>Ref.</th></tr>
      <tr><th rowspan="3">2011</th><td>Eliza Griswold</td><td>The Tenth Parallel</td><td>Publisher</td><td>Winner</td><td>[1]</td></tr>
      <tr><td>Jefferson Cowie</td><td><i><a href="/wiki/Stayin_Alive">Stayin' Alive: The 1970s and the Last Days of the Working Class</a></i></td><td>New Press</td><td>Finalist</td><td>[2]</td></tr>
      <tr><td>Paul Greenberg</td><td>Four Fish: The Future of the Last Wild Food</td><td>Penguin Press</td><td>Shortlist</td><td>[3]</td></tr></table>'''
    entries=self.parse(html)['entries']
    self.assertEqual([
      ('2011','The Tenth Parallel',['Eliza Griswold'],'winner'),
      ('2011.01',"Stayin' Alive: The 1970s and the Last Days of the Working Class",['Jefferson Cowie'],'finalist'),
      ('2011.02','Four Fish: The Future of the Last Wild Food',['Paul Greenberg'],'shortlisted'),
    ],[(e['position'],e['title'],e['authors'],e['result']) for e in entries])
    self.assertEqual(LUKAS_WIKIPEDIA_URL,entries[1]['source']['url'])

  def test_reordered_columns_expand_independent_year_result_and_reference_spans(self):
    html='''<table><tr><th>Result</th><th>Title</th><th>Year</th><th>Author</th><th>Ref.</th></tr>
      <tr><td>Winner</td><td>Winning Book</td><td rowspan="3">2026</td><td>Winner Writer</td><td rowspan="3">[1]</td></tr>
      <tr><td rowspan="2">Finalist</td><td>First Book</td><td>First Writer</td></tr>
      <tr><td>Second Book</td><td>Second Writer</td></tr></table>'''
    for parser,url in ((LukasWikipediaParser(),LUKAS_WIKIPEDIA_URL),
                       (MarkLyntonHistoryPrizeWikipediaParser(),MARK_LYNTON_WIKIPEDIA_URL)):
      with self.subTest(parser=type(parser).__name__):
        entries=parser.parse(html,url,parser.AWARD_NAME)['entries']
        self.assertEqual(['Winning Book','First Book','Second Book'],[e['title'] for e in entries])
        self.assertEqual([['Winner Writer'],['First Writer'],['Second Writer']],[e['authors'] for e in entries])
        self.assertEqual(['winner','finalist','finalist'],[e['result'] for e in entries])
        self.assertTrue(all(e['category']==parser.CATEGORY for e in entries))

  def test_unicode_coauthors_suffixes_and_title_wording_survive(self):
    html='''<meta charset="utf-8"><table><tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
      <tr><td>2003</td><td>Samantha Power</td><td><i>"A Problem from Hell": America and the Age of Genocide</i></td><td>Winner</td></tr>
      <tr><td>2020</td><td>Emily Bazelon</td><td><i>Charged: The Movement to Transform American Prosecution and End Mass Incarceration</i></td><td>Finalist</td></tr>
      <tr><td>2023</td><td>Robert Samuels and Toluse Olorunnipa</td><td>His Name Is George Floyd: One Man\u2019s Life</td><td>Finalist</td></tr>
      <tr><td>2025</td><td>Pamela Prickett and Stefan Timmermans</td><td><i>The Unclaimed (Volume Two)</i> (about a family)</td><td>Finalist</td></tr>
      <tr><td>2026</td><td>\u00c9va Writer, Jr. and Other Writer</td><td><i>A Book</i> Volume 2</td><td>Winner</td></tr></table>'''
    entries=self.parse(html.encode('utf-8'))['entries']
    self.assertTrue(entries[0]['title'].startswith('"A Problem from Hell":'))
    self.assertTrue(entries[1]['title'].startswith('Charged: The Movement'))
    self.assertEqual(['Robert Samuels','Toluse Olorunnipa'],entries[2]['authors'])
    self.assertIn('Man\u2019s Life',entries[2]['title'])
    self.assertEqual(['Pamela Prickett','Stefan Timmermans'],entries[3]['authors'])
    self.assertEqual('The Unclaimed (Volume Two)',entries[3]['title'])
    self.assertEqual(['\u00c9va Writer, Jr.','Other Writer'],entries[4]['authors'])
    self.assertEqual('A Book Volume 2',entries[4]['title'])

  def test_merged_explanations_and_nonimported_results_are_rejected(self):
    html='''<table><tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
      <tr><td rowspan="3">2025</td><td>Writer</td><td>Real Book</td><td>Winner</td></tr>
      <tr><td colspan="3">No additional finalists announced</td></tr>
      <tr><td>Other Writer</td><td>Excluded Book</td><td>Longlisted</td></tr></table>'''
    self.assertEqual(['Real Book'],[e['title'] for e in self.parse(html)['entries']])

  def test_role_cleanup_cannot_truncate_fred_or_ned(self):
    for parser in (LukasWikipediaParser(),MarkLyntonHistoryPrizeWikipediaParser()):
      with self.subTest(parser=type(parser).__name__):
        self.assertEqual('Fred Anderson',parser.clean_author('Fred Anderson'))
        self.assertEqual('Ned Blackhawk',parser.clean_author('Ned Blackhawk'))
        self.assertEqual('Edward Writer',parser.clean_author('Edward Writer, ed.'))
        self.assertEqual('Writer',parser.clean_author('Writer translated by Translator'))

  def test_resultless_legacy_tables_and_tied_winners_keep_positions(self):
    html='''<table><tr><th>Year</th><th>Title</th><th>Author</th></tr>
      <tr><td rowspan="2">2000</td><td>First Book</td><td>First Writer</td></tr>
      <tr><td>Next Book</td><td>Next Writer</td></tr></table>
      <table><tr><th>Year</th><th>Title</th><th>Author</th><th>Result</th></tr>
      <tr><td rowspan="2">2001</td><td>Tied One</td><td>One Writer</td><td rowspan="2">Winner</td></tr>
      <tr><td>Tied Two</td><td>Two Writer</td></tr></table>'''
    self.assertEqual(['2000','2000.01','2001','2001'],[e['position'] for e in self.parse(html)['entries']])

  def test_explicit_and_automatic_wikipedia_sources_use_aligned_columns(self):
    html='''<table><tr><th>Year</th><th>Author</th><th>Title</th><th>Publisher</th><th>Result</th><th>Ref.</th></tr>
      <tr><td rowspan="2">2025</td><td>Winner Writer</td><td>Winning Book</td><td>Publisher</td><td>Winner</td><td>[1]</td></tr>
      <tr><td>Pamela Prickett and Stefan Timmermans</td><td>The Unclaimed</td><td>Crown</td><td>Finalist</td><td>[2]</td></tr></table>'''
    for factory,url,choice in ((UrlFetcherJAnthonyLukasBookPrize,LUKAS_WIKIPEDIA_URL,2),
                               (UrlFetcherMarkLyntonHistoryPrize,MARK_LYNTON_WIKIPEDIA_URL,1)):
      for selected in (choice,'automatic'):
        calls=[]
        def fetch(target,**kwargs):
          calls.append(target)
          if target!=url:raise OSError('source unavailable')
          return html
        with self.subTest(recipe=factory.__name__,source=selected):
          parsed=factory().fetch_and_parse(fetch,source_choice=selected)
          self.assertEqual(['Winning Book','The Unclaimed'],[e['title'] for e in parsed['entries']])
          self.assertEqual(['Pamela Prickett','Stefan Timmermans'],parsed['entries'][1]['authors'])
          self.assertEqual(url,parsed['source']['url'])
          if selected==choice:self.assertEqual([url],calls)


if __name__=='__main__':
  unittest.main()
