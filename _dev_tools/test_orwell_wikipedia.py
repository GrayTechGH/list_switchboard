import unittest

from _dev_tools import test_import_matching
from parser.orwell import OrwellWikipediaParser
from url_fetcher.orwell import UrlFetcherOrwellPrizePoliticalWriting, ORWELL_WIKIPEDIA_URL


def table(title='Political Book', author='Political Writer'):
  return f'''<table><tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th><th>Ref.</th></tr>
    <tr><td>2025</td><td>{author}</td><td><i>{title}</i></td><td>Winner</td><td>[1]</td></tr></table>'''


class OrwellWikipediaTests(unittest.TestCase):

  def parse(self, html):
    return OrwellWikipediaParser().parse(html,ORWELL_WIKIPEDIA_URL,'Orwell')

  def test_bare_wrapped_and_parsoid_headings_find_only_political_writing(self):
    heading='<h3>The Orwell Prize for Political Writing (2019\u2013present)</h3>'
    for section in (heading+table(),
                    '<div class="mw-heading mw-heading3">'+heading+'<span>[edit]</span></div>'+table(),
                    '<section><div class="mw-heading">'+heading+'</div><div>'+table()+'</div></section>'):
      with self.subTest(section=section[:100]):
        html='<h3>Political Fiction (2019-present)</h3>'+table('Fiction Book')+section+\
          '<div class="mw-heading"><h3>Combined book category (1994-2018)</h3></div>'+table('Old Book')+\
          '<h3>The Orwell Prize for Journalism (1994-present)</h3>'+table('Journalism Work')
        entries=self.parse(html)['entries']
        self.assertEqual(['Political Book'],[e['title'] for e in entries])
        self.assertEqual('Political Writing',entries[0]['category'])
        self.assertEqual(ORWELL_WIKIPEDIA_URL,entries[0]['source']['url'])

  def test_neighbor_wrapped_headings_bound_nested_table_containers(self):
    html='<div><h3>Political Writing (2019-present)</h3></div><div><div>'+table()+'</div></div>'+\
      '<div><h3>Political Fiction (2019-present)</h3></div><div>'+table('Excluded Fiction')+'</div>'+\
      '<div><h3>Political Writing (1994-2018)</h3></div>'+table('Excluded History')
    self.assertEqual(['Political Book'],[e['title'] for e in self.parse(html)['entries']])

  def test_independent_year_result_and_reference_spans_keep_columns(self):
    html='''<h3>Political Writing (2019-present)</h3><table>
      <tr><th>Result</th><th>Author</th><th>Year</th><th>Title</th><th>Ref.</th></tr>
      <tr><td>Winner</td><td>Winner Writer</td><td rowspan="3">2019</td><td>Winning Book</td><td>[1]</td></tr>
      <tr><td rowspan="2">Shortlist</td><td>Oliver Bullough</td><td>Moneyland</td><td rowspan="2">[2]</td></tr>
      <tr><td>Francisco Cant\u00fa</td><td>The Line Becomes a River</td></tr></table>'''
    entries=self.parse(html)['entries']
    self.assertEqual([
      ('2019','Winning Book',['Winner Writer'],'winner'),
      ('2019.01','Moneyland',['Oliver Bullough'],'shortlisted'),
      ('2019.02','The Line Becomes a River',['Francisco Cant\u00fa'],'shortlisted'),
    ],[(e['position'],e['title'],e['authors'],e['result']) for e in entries])

  def test_bytes_titles_coauthors_and_role_delimiters(self):
    html='<meta charset="utf-8"><h3>Political Writing (2019-present)</h3>'+\
      table('A Family\u2019s Story (Volume Two)','\u00c9va Writer, Jr. and Other Writer')+\
      table('"A Quoted Title": A Study','Fred Anderson')
    entries=self.parse(html.encode('utf-8'))['entries']
    self.assertEqual('A Family\u2019s Story (Volume Two)',entries[0]['title'])
    self.assertEqual(['\u00c9va Writer, Jr.','Other Writer'],entries[0]['authors'])
    self.assertEqual('"A Quoted Title": A Study',entries[1]['title'])
    self.assertEqual(['Fred Anderson'],entries[1]['authors'])
    parser=OrwellWikipediaParser()
    self.assertEqual('Ned Blackhawk',parser.clean_author('Ned Blackhawk'))
    self.assertEqual('Writer',parser.clean_author('Writer, ed.'))

  def test_merged_explanations_and_nonimported_results_are_not_books(self):
    html='''<h3>Political Writing (2019-present)</h3><table>
      <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
      <tr><td rowspan="3">2025</td><td>Writer</td><td>Real Book</td><td>Winner</td></tr>
      <tr><td colspan="3">No additional shortlist announced</td></tr>
      <tr><td>Other Writer</td><td>Excluded Book</td><td>Longlisted</td></tr></table>'''
    self.assertEqual(['Real Book'],[e['title'] for e in self.parse(html)['entries']])

  def test_legacy_result_continuation_and_tied_winners_keep_positions(self):
    html='''<h3>Political Writing (2019-present)</h3><table>
      <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
      <tr><td rowspan="4">2025</td><td>One Writer</td><td>Tied One</td><td>Winner</td></tr>
      <tr><td>Two Writer</td><td>Tied Two</td><td>Winner</td></tr>
      <tr><td>Third Writer</td><td>First Shortlist</td><td>Shortlist</td></tr>
      <tr><td>Last Writer</td><td>Next Shortlist</td><td></td></tr></table>'''
    entries=self.parse(html)['entries']
    self.assertEqual(['2025','2025','2025.01','2025.02'],[e['position'] for e in entries])
    self.assertEqual(['winner','winner','shortlisted','shortlisted'],[e['result'] for e in entries])

  def test_explicit_wikipedia_and_automatic_replacement_use_wrapped_section(self):
    html='<div class="mw-heading"><h3>Political Writing (2019-present)</h3></div>'+table()
    for choice in (1,'automatic'):
      calls=[]
      def fetch(url,**kwargs):
        calls.append(url)
        if url!=ORWELL_WIKIPEDIA_URL:raise OSError('official unavailable')
        return html
      with self.subTest(choice=choice):
        parsed=UrlFetcherOrwellPrizePoliticalWriting().fetch_and_parse(fetch,source_choice=choice)
        self.assertEqual(['Political Book'],[e['title'] for e in parsed['entries']])
        self.assertEqual(ORWELL_WIKIPEDIA_URL,parsed['source']['url'])
        self.assertNotIn('incremental_state',parsed)
        if choice==1:self.assertEqual([ORWELL_WIKIPEDIA_URL],calls)


if __name__=='__main__':
  unittest.main()
