import copy
import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError, CamoufoxRequiredError
from parser.booker_modern import index_links, valid_empty_year
from storage import build_import_cache_data
from url_fetcher.booker import UrlFetcherBookerPrize, UrlFetcherInternationalBookerPrize


class BookerUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe = UrlFetcherBookerPrize()
    self.recipe.FIRST_YEAR = 2024
    self.years = [2026, 2025, 2024]
    self.pages = [[2026, 2025], [2024]]
    self.calls, self.errors, self.overrides = [], {}, {}
    for module in ('parser.annual_updates.datetime', 'parser.booker_modern.datetime', 'parser.booker_updates.datetime'):
      clock = patch(module)
      clock.start().datetime.now.return_value.year = 2026
      self.addCleanup(clock.stop)

  def url(self, year):
    return self.recipe.URL + ('/international/' if 'international' in self.recipe.source_id else '/') + str(year)

  def index(self, number):
    cards = ''.join(f'<article><a href="{self.url(year)}"><h3>Prize {year}</h3></a></article>' for year in self.pages[number])
    pager = ''.join(f'<a href="?page={n}">{n+1}</a>' for n in range(len(self.pages)))
    return f'<nav><a href="{self.url(2023)}">Global navigation</a></nav><main><h1>Prize years</h1>{cards}<nav class="pager">{pager}</nav></main>'

  def card(self, year, title, winner=False, author=True):
    return f'''<article><a href="/the-booker-library/books/{title.lower()}-{year}"><h3>{title} {year}</h3></a>
      <p>Book description including misleading winner text</p>{'<span class="sr-only">Prize winner</span>' if winner else ''}
      {('<p>By <a href="/the-booker-library/authors/writer">Writer, Jr.</a></p>' if author else '')}
      <p>Translated by <a href="/the-booker-library/authors/translator">Wrong Translator</a></p></article>'''

  def annual(self, year, winner=True):
    award = 'The Bukhman International Booker Prize' if 'international' in self.recipe.source_id else 'The Booker Prize'
    return f'''<main><h1>{award} {year}</h1>
      <nav>{self.card(year,'Winner',True)}</nav>
      <section aria-labelledby="section-section-shortlisted-books-title"><h2>The shortlist</h2><div class="c-booker-grid">
      {self.card(year,'Winner',winner)}{self.card(year,'Other')}</div></section>
      <section><h2>The longlist</h2>{self.card(year,'Wrong Longlist')}</section>
      <section><h2>Read our shortlist news</h2>{self.card(year,'Wrong News')}</section></main>'''

  def fetch(self, url, **kwargs):
    self.calls.append((url, kwargs.get('transport')))
    error = self.errors.get((url, kwargs.get('transport'))) or self.errors.get(url)
    if error:
      raise error
    if url in self.overrides:
      return self.overrides[url]
    if url == self.recipe.WIKIPEDIA_URL:
      return '<table><tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr><tr><td>2026</td><td>Wiki Writer</td><td>Wiki Book</td><td>Winner</td></tr></table>'
    if url.startswith(self.recipe.URL + '?'):
      return self.index(int(url.split('page=')[1]))
    if url == self.recipe.URL:
      return self.index(0)
    return self.annual(int(url.rsplit('/', 1)[1]))

  def parse(self, cached=None, incremental=None, choice=0):
    return self.recipe.fetch_and_parse(self.fetch, source_choice=choice,
      cached_parsed=cached, incremental_update=(cached is not None) if incremental is None else incremental)

  def cache(self, parsed):
    return build_import_cache_data(self.recipe.source_id, parsed)

  def test_both_prizes_restore_missing_history_and_repeat_with_fewer_fetches(self):
    for cls in (UrlFetcherBookerPrize, UrlFetcherInternationalBookerPrize):
      self.recipe = cls(); self.recipe.FIRST_YEAR = 2024; self.calls.clear()
      full = self.parse(); self.assertEqual(6, len(full['entries'])); self.assertEqual(5, len(self.calls))
      stale = without_unit(self.cache(full), self.url(2025)); self.assertEqual(4, len(stale['entries'])); self.calls.clear()
      updated = self.parse(stale); self.assertEqual(full['entries'], updated['entries']); self.assertEqual(4, len(self.calls))
      self.calls.clear(); self.assertEqual(full['entries'], self.parse(self.cache(updated))['entries']); self.assertEqual(3, len(self.calls))

  def test_new_year_and_shifted_pagination_discover_history_without_offset_reuse(self):
    old = self.cache(self.parse()); self.pages = [[2027, 2026], [2025], [2024]]; self.calls.clear()
    updated = self.parse(old)
    self.assertEqual(8, len(updated['entries']))
    self.assertEqual({self.recipe.URL, self.recipe.URL+'?page=1', self.recipe.URL+'?page=2', self.url(2027), self.url(2026)}, {u for u,t in self.calls})

  def test_gapped_history_and_invalid_pagination_fail_instead_of_certifying_partial_archive(self):
    for pages in ([[2026], [2024]],):
      self.pages = pages
      with self.assertRaisesRegex(Exception, 'incomplete or unexpected'):
        self.parse()
    self.pages = [[2026, 2025], []]
    with self.assertRaisesRegex(Exception, 'no rendered prize-year cards'):
      self.parse()
    self.pages = [[2026, 2025], [2024]]
    self.errors[self.recipe.URL+'?page=1'] = RuntimeError('failed index page')
    with self.assertRaisesRegex(Exception, 'failed index page'):
      self.parse()

  def test_truncated_recent_history_is_rejected_even_if_old_years_are_continuous(self):
    self.pages = [[2024]]
    with self.assertRaisesRegex(Exception, 'missing its recent award years'):
      self.parse()

  def test_unrelated_hosts_navigation_options_and_filters_are_not_discovery(self):
    html = self.index(0).replace('</main>', f'''<option value="{self.url(2023)}">2023</option>
      <article><a href="https://example.com/the-booker-library/prize-years/2023">Wrong host</a></article>
      <nav class="pager"><a href="?page=88&amp;prize=other">Wrong filter</a><a href="https://example.com/the-booker-library/prize-years?page=9">Wrong host</a></nav></main>''')
    years, pages = index_links(html, self.recipe.URL, self.recipe.YEAR_URL_PATTERN)
    self.assertEqual([self.url(2026), self.url(2025)], years); self.assertEqual([1], pages)

  def test_longlist_news_navigation_and_translators_are_excluded(self):
    parsed = self.parse()
    self.assertTrue(all(row['authors'] == ['Writer, Jr.'] for row in parsed['entries']))
    self.assertFalse(any('Wrong' in row['title'] for row in parsed['entries']))
    self.assertEqual(3, sum(row['result'] == 'winner' for row in parsed['entries']))

  def test_winner_feature_can_promote_a_shortlist_card_without_adding_a_duplicate(self):
    page = self.annual(2026, winner=False).replace('</main>', f'''<div class="group c-booker-grid">
      <a href="/the-booker-library/books/other-2026"><h2>Other 2026</h2></a><p>Winner of <a href="{self.url(2026)}">The Booker Prize 2026</a></p>
      <dl><div><dt>By</dt><dd>Writer, Jr.</dd></div><div><dt>Translated by</dt><dd>Wrong Translator</dd></div></dl></div></main>''')
    parsed = self.recipe.parser().parse(page, self.url(2026), self.recipe.NAME)
    self.assertEqual(2, len(parsed['entries'])); self.assertEqual('Other 2026', parsed['entries'][0]['title'])
    self.assertEqual('winner', parsed['entries'][0]['result'])

  def test_current_year_refresh_replaces_corrections_and_winner_promotions(self):
    old = self.cache(self.parse())
    self.overrides[self.url(2026)] = self.annual(2026).replace('Prize winner', 'Nominee').replace('Other 2026', 'Corrected 2026')
    updated = self.parse(old)
    self.assertNotIn('Other 2026', [row['title'] for row in updated['entries']])
    self.assertIn('Corrected 2026', [row['title'] for row in updated['entries']])
    self.assertFalse(any(row['award_year'] == '2026' and row['result'] == 'winner' for row in updated['entries']))

  def test_winnerless_history_keeps_refreshing(self):
    self.overrides[self.url(2025)] = self.annual(2025, winner=False)
    old = self.cache(self.parse()); self.calls.clear(); self.parse(old)
    self.assertIn((self.url(2025), 'camoufox'), self.calls)

  def test_failed_annual_update_retains_whole_year_pending_then_recovers(self):
    old = self.cache(self.parse()); self.errors[self.url(2026)] = RuntimeError('temporary failure')
    updated = self.parse(old); self.assertEqual(old['entries'], updated['entries'])
    self.assertFalse(updated['incremental_state']['units'][self.url(2026)]['complete'])
    self.assertTrue(any('temporary failure' in note for note in updated['notes']))
    self.errors.clear(); recovered = self.parse(self.cache(updated)); self.assertTrue(recovered['incremental_state']['units'][self.url(2026)]['complete'])

  def test_legacy_wrong_scope_corrupt_bookkeeping_and_complete_refresh_fetch_all_years(self):
    old = self.cache(self.parse())
    cases = [dict(old, incremental_state={}), copy.deepcopy(old)]
    cases[1]['incremental_state']['source_key'] = 'another recipe'
    for cached in cases:
      self.calls.clear(); self.assertEqual(old['entries'], self.parse(cached)['entries']); self.assertEqual(5, len(self.calls))
    self.calls.clear(); self.parse(old, incremental=False); self.assertEqual(5, len(self.calls))

  def test_wrong_prize_and_year_are_rejected(self):
    for html in (self.annual(2025), self.annual(2026).replace('The Booker Prize', 'The International Booker Prize')):
      with self.assertRaisesRegex(ValueError, 'another award or year'):
        self.recipe.parser().parse(html, self.url(2026), self.recipe.NAME)

  def test_body_of_work_year_is_empty_only_with_a_bounded_winner_author(self):
    url = self.recipe.URL+'/international/2015'
    html = '<main><h1>The Man Booker International Prize 2015</h1><section><h2>Winner</h2><a href="/the-booker-library/authors/writer">Writer</a></section><section><h2>The finalists</h2><a href="/the-booker-library/authors/other">Other</a></section></main>'
    self.assertTrue(valid_empty_year(html, url, 2015))
    self.assertFalse(valid_empty_year(html.replace('Winner', 'Judges'), url, 2015))
    self.assertFalse(valid_empty_year(html.replace('/authors/writer', '/books/book'), url, 2015))
    page = html.replace('</main>', '<section aria-labelledby="section-section-shortlisted-books-title"><h2>Related books</h2>' + self.card(2015, 'Related Book') + '</section></main>')
    parsed = self.recipe.parser().parse(page, url, self.recipe.NAME)
    self.assertFalse(parsed['entries']); self.assertFalse(parsed['notes'])

  def test_intake_year_can_be_empty_but_historical_judges_cannot_certify_missing_results(self):
    for year, expected in ((2027, True), (2024, False)):
      html = f'<main><h1>The Booker Prize {year}</h1><section><h2>The judges</h2><div class="c-booker-grid">Panel</div></section></main>'
      self.assertEqual(expected, valid_empty_year(html, self.url(year), year))

  def test_forthcoming_empty_year_refreshes_after_calendar_rollover(self):
    self.pages = [[2027, 2026], [2025, 2024]]
    self.overrides[self.url(2027)] = '<main><h1>The Booker Prize 2027</h1><section><h2>The 2027 judges</h2><div class="c-booker-grid">Panel</div></section></main>'
    old = self.cache(self.parse())
    self.assertFalse(old['incremental_state']['units'][self.url(2027)]['metadata']['settled'])
    self.pages = [[2028, 2027], [2026, 2025, 2024]]; self.overrides.clear(); self.calls.clear()
    with patch('parser.annual_updates.datetime') as clock:
      clock.datetime.now.return_value.year = 2028
      updated = self.parse(old)
    self.assertIn((self.url(2027), 'camoufox'), self.calls)
    self.assertTrue(any(row['award_year'] == '2027' for row in updated['entries']))

  def test_malformed_current_card_retains_entire_previous_year_pending(self):
    old = self.cache(self.parse())
    self.overrides[self.url(2026)] = self.annual(2026).replace('<h3>Other 2026</h3>', '')
    updated = self.parse(old)
    self.assertEqual(old['entries'], updated['entries'])
    self.assertFalse(updated['incremental_state']['units'][self.url(2026)]['complete'])

  def test_critical_errors_propagate_at_root_pagination_annual_and_detail_boundaries(self):
    for url in (self.recipe.URL, self.recipe.URL+'?page=1', self.url(2026)):
      for cls in (ImportCancelledError, CamoufoxRequiredError):
        self.errors = {url: cls('stop')}
        with self.assertRaises(cls):
          self.parse()
    self.errors.clear()
    for cls in (ImportCancelledError, CamoufoxRequiredError):
      def fail(_url): raise cls('stop')
      with self.assertRaises(cls):
        self.recipe.parser().parse(self.annual(2026).replace('<p>By <a href="/the-booker-library/authors/writer">Writer, Jr.</a></p>', ''), self.url(2026), self.recipe.NAME, fetch_url=fail)

  def test_browser_recovery_is_attempt_local_and_fallback_remains_full_replacement(self):
    self.errors[(self.recipe.URL, 'camoufox')] = RuntimeError('no browser')
    full = self.parse(); self.assertEqual(6, len(full['entries']))
    self.assertEqual([self.recipe.URL, self.recipe.URL], [url for url,t in self.calls[:2]])
    self.assertTrue(all(t is None for u,t in self.calls[1:]))
    self.errors.clear(); self.calls.clear(); self.parse(); self.assertTrue(all(t == 'camoufox' for u,t in self.calls))
    self.calls.clear(); parsed = self.parse(self.cache(full), choice=1)
    self.assertEqual([(self.recipe.WIKIPEDIA_URL, None)], self.calls)
    self.assertEqual('Wiki Book', parsed['entries'][0]['title']); self.assertNotIn('incremental_state', parsed)

  def test_detail_fallback_uses_explicit_work_author_and_retains_pending_on_failure(self):
    html = self.annual(2026).replace('<p>By <a href="/the-booker-library/authors/writer">Writer, Jr.</a></p>', '')
    calls = []
    def detail(url):
      calls.append(url)
      return '<main><h1>Detail Title</h1><dl><div><dt>By</dt><dd>Detail Writer, Jr.</dd></div><div><dt>Translated by</dt><dd>Wrong Translator</dd></div></dl></main>'
    parsed = self.recipe.parser().parse(html, self.url(2026), self.recipe.NAME, fetch_url=detail)
    self.assertEqual(2, len(calls)); self.assertEqual(['Detail Writer, Jr.'], parsed['entries'][0]['authors']); self.assertFalse(parsed['notes'])
    parsed = self.recipe.parser().parse(html, self.url(2026), self.recipe.NAME)
    self.assertFalse(parsed['entries']); self.assertTrue(parsed['notes'])


if __name__ == '__main__':
  unittest.main()
