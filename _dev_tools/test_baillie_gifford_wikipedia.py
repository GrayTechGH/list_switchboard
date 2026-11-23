import unittest

from _dev_tools import test_import_matching
from parser.baillie_gifford import BaillieGiffordWikipediaParser
from url_fetcher.baillie_gifford import (
  BAILLIE_GIFFORD_WIKIPEDIA_URL, UrlFetcherBaillieGiffordPrize,
)


class BaillieGiffordWikipediaTests(unittest.TestCase):

  def parse(self, html):
    return BaillieGiffordWikipediaParser().parse(
      html, BAILLIE_GIFFORD_WIKIPEDIA_URL, 'Baillie Gifford Prize')

  def test_year_rowspan_with_separate_references_preserves_shortlist_columns(self):
    html = '''<table><tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th><th>Ref.</th></tr>
      <tr><th rowspan="3">1999<sup>[a]</sup></th><td>Antony Beevor</td>
        <td><i>Stalingrad</i></td><td>Won</td><td>[1]</td></tr>
      <tr><td>Ian Kershaw</td><td><i>Hitler 1889–1936: Hubris</i> (about Adolf Hitler)</td>
        <td>Shortlisted</td><td>[2]</td></tr>
      <tr><td>Ann Wroe</td><td><i>Pilate: The Biography of an Invented Man</i> (about Pontius Pilate)</td>
        <td>Shortlisted</td><td>[2]</td></tr></table>'''
    entries = self.parse(html)['entries']
    self.assertEqual([
      ('1999', 'Stalingrad', ['Antony Beevor'], 'winner'),
      ('1999.01', 'Hitler 1889–1936: Hubris', ['Ian Kershaw'], 'shortlisted'),
      ('1999.02', 'Pilate: The Biography of an Invented Man', ['Ann Wroe'], 'shortlisted'),
    ], [(e['position'], e['title'], e['authors'], e['result']) for e in entries])
    self.assertTrue(all(e['award_year'] == '1999' for e in entries))

  def test_result_and_reference_spans_work_with_reordered_columns(self):
    html = '''<table><tr><th>Result</th><th>Author</th><th>Year</th><th>Title</th><th>Ref.</th></tr>
      <tr><td>Won</td><td>Winner Writer</td><th rowspan="3">2024</th><td>Winning Work</td><td rowspan="3">[1]</td></tr>
      <tr><td rowspan="2">Shortlisted</td><td>First Writer</td><td>First Work</td></tr>
      <tr><td>Second Writer</td><td>Second Work</td></tr></table>'''
    entries = self.parse(html)['entries']
    self.assertEqual(['Winning Work','First Work','Second Work'], [e['title'] for e in entries])
    self.assertEqual([['Winner Writer'],['First Writer'],['Second Writer']], [e['authors'] for e in entries])
    self.assertEqual(['winner','shortlisted','shortlisted'], [e['result'] for e in entries])

  def test_colspan_explanations_and_longlists_are_not_books(self):
    html = '''<table><tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
      <tr><td rowspan="3">2023</td><td>Winner Writer</td><td>Winning Work</td><td>Won</td></tr>
      <tr><td colspan="3">No additional shortlist announced</td></tr>
      <tr><td>Other Writer</td><td>Longlisted Work</td><td>Longlisted</td></tr></table>'''
    self.assertEqual(['Winning Work'], [e['title'] for e in self.parse(html)['entries']])

  def test_utf8_bytes_and_parentheses_inside_titles_survive(self):
    html = '''<table><tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
      <tr><td>2026</td><td>Éva Writer</td><td><i>A Family’s Story (Volume Two)</i> (about a family)</td><td>Shortlisted</td></tr>
      <tr><td>2025</td><td>Other Writer</td><td><i>Collected Diaries</i> Volume 2</td><td>Won</td></tr></table>'''
    entries = self.parse(html.encode('utf-8'))['entries']
    self.assertEqual(['Collected Diaries Volume 2', 'A Family’s Story (Volume Two)'], [e['title'] for e in entries])
    self.assertEqual(['Éva Writer'], entries[1]['authors'])

  def test_separate_tables_and_resultless_legacy_rows_keep_year_and_provenance(self):
    html = '''<table><tr><th>Year</th><th>Author</th><th>Title</th></tr>
      <tr><td rowspan="2">1999</td><td>First Writer</td><td>First Winner</td></tr>
      <tr><td>Next Writer</td><td>First Shortlist</td></tr></table>
      <table><tr><th>Title</th><th>Author</th><th>Year</th></tr>
      <tr><td><i><a href="/wiki/Second_Winner">Second Winner</a></i></td><td>Last Writer</td><td>2000</td></tr></table>'''
    entries = self.parse(html)['entries']
    self.assertEqual(['1999','1999.01','2000'], [e['position'] for e in entries])
    self.assertEqual(['winner','shortlisted','winner'], [e['result'] for e in entries])
    self.assertTrue(all(e['source']['url'] == BAILLIE_GIFFORD_WIKIPEDIA_URL for e in entries))

  def test_explicit_wikipedia_and_official_failure_use_corrected_replacement(self):
    html = '''<table><tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th><th>Ref.</th></tr>
      <tr><td rowspan="2">2024</td><td>Winner Writer</td><td>Winner</td><td>Won</td><td>[1]</td></tr>
      <tr><td>Shortlist Writer</td><td>Shortlist Work</td><td>Shortlisted</td><td>[2]</td></tr></table>'''
    for source_choice in (1, 'automatic'):
      with self.subTest(source_choice=source_choice):
        recipe = UrlFetcherBaillieGiffordPrize()
        calls = []
        def fetch(url):
          calls.append(url)
          if url == recipe.URL:
            raise OSError('official archive unavailable')
          self.assertEqual(BAILLIE_GIFFORD_WIKIPEDIA_URL, url)
          return html
        parsed = recipe.fetch_and_parse(fetch, source_choice=source_choice)
        self.assertEqual([['Winner Writer'],['Shortlist Writer']], [e['authors'] for e in parsed['entries']])
        self.assertEqual(['Winner','Shortlist Work'], [e['title'] for e in parsed['entries']])
        self.assertEqual(BAILLIE_GIFFORD_WIKIPEDIA_URL, parsed['source']['url'])
        self.assertEqual([BAILLIE_GIFFORD_WIKIPEDIA_URL] if source_choice == 1 else
          [recipe.URL,BAILLIE_GIFFORD_WIKIPEDIA_URL], calls)


if __name__ == '__main__':
  unittest.main()
