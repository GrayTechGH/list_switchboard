import copy
import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import CamoufoxRequiredError, ImportCancelledError
from parser.cbca_book_of_the_year import CBCABookOfTheYearParser, PDF_URL, AWARDS_URL
from parser.cbca_2022 import SHORTLIST_URL, NOTABLES_URL, shortlist_links, shortlist_rows, review_creator
from parser.cbca_updates import ANNUAL_PDFS, NO_WINNER, merge_year, history_complete
from storage import build_import_cache_data
from url_fetcher.cbca_book_of_the_year import UrlFetcherCBCABookOfTheYearOlderReaders


class CBCAIncrementalTests(unittest.TestCase):

  def setUp(self):
    self.recipe = UrlFetcherCBCABookOfTheYearOlderReaders()
    self.calls, self.errors, self.overrides = [], {}, {}
    self.years = [2024, 2025, 2026]
    self.winner, self.writer = 0, 'Author'
    self.clock = patch('parser.cbca_updates.date')
    self.clock.start().today.return_value.year = 2026
    self.addCleanup(self.clock.stop)
    mocked_pdf = patch.object(CBCABookOfTheYearParser, 'pdf_rows', lambda _p, payload, source_url: self.pdf(payload, source_url))
    mocked_pdf.start()
    self.addCleanup(mocked_pdf.stop)

  def rows(self, year, count=6, winner=False):
    return [{'award_year': str(year), 'category': 'Older Readers',
      'title': f'Book {year} {i}', 'author': f'Author {i}',
      'result': 'winner' if winner and i == 0 else 'shortlisted',
      'source_url': f'https://cbca.org.au/{year}-shortlist/'} for i in range(count)]

  def pdf(self, payload, url):
    if url == PDF_URL:
      return [{'award_year': str(y), 'category': 'Older Readers', 'title': f'History {y}',
        'author': 'History Writer', 'result': 'winner', 'source_url': url}
        for y in range(1946, 2022) if y not in NO_WINNER['Older Readers']]
    year = int(url.split('/BookOfTheYear/')[1][:4])
    return self.rows(year, 6 if 'Shortlist' in url else 3, winner='Shortlist' not in url)

  def panel(self, year):
    rows = []
    for i in range(6):
      winner = self.winner if year == 2025 else 0
      stage = 'Winner' if i == winner else 'Shortlist'
      writer = self.writer if year == 2025 else 'Author'
      rows.append(f'<p>{stage} | <i>Book {year} {i}</i>, {writer} {i}</p>')
    return f'<details><summary>{year}</summary><h3>Older Readers</h3>'+''.join(rows)+'</details>'

  def archive(self):
    return f'<main><h1>CBCA Book of the Year Award through history</h1><a href="{PDF_URL}">PDF of all prior winners</a>'+''.join(self.panel(y) for y in self.years)+'</main>'

  def awards(self):
    links = ''.join(f'<a href="https://cbca.org.au/{y}-{kind}/">{y} {kind}</a>'
      for y in (2025, max(self.years)) for kind in ('shortlist', 'winners'))
    return '<main><h1>Book of the Year Awards</h1>'+links+'</main>'

  def current(self, year, kind):
    rows = self.rows(year, 6 if kind == 'shortlist' else 3, winner=kind == 'winners')
    return f'<main><h1>{year} Book of the Year Awards - {kind.title()}</h1><h2>Older Readers</h2>'+''.join(
      f'<p>{"Winner | " if r["result"] == "winner" else "Honour | " if kind == "winners" else ""}<i>{r["title"]}</i>, {r["author"]}</p>' for r in rows)+'</main>'

  def shortlist(self):
    return '<article><h1>Announcing the 2022 Book of the Year Awards Shortlist</h1><h2>Older Readers</h2><h2>Reviews</h2>'+''.join(f'<p><a href="/book-{i}/">Book 2022 {i}</a></p>' for i in range(6))+'</article>'

  def notables(self):
    return '<article><h1>Announcing the 2022 CBCA Notable Books</h1><h4>Book of the Year: Older Readers</h4><table><tr><th>Author</th><th>Illustrator</th><th>Title</th><th>ISBN</th><th>Publisher</th></tr>'+''.join(f'<tr><td>Author {i}</td><td></td><td>Book 2022 {i}</td><td>9781234567890</td><td>Publisher</td></tr>' for i in range(7))+'</table></article>'

  def fetch(self, url, **kwargs):
    self.calls.append((url, kwargs.get('transport')))
    if url in self.errors:
      raise self.errors[url]
    if url in self.overrides:
      return self.overrides[url]
    if url == self.recipe.URL:
      return self.archive()
    if url == AWARDS_URL:
      return self.awards()
    if url == SHORTLIST_URL:
      return self.shortlist()
    if url == NOTABLES_URL:
      return self.notables()
    if url == PDF_URL or url in sum(ANNUAL_PDFS.values(), ()):
      return 'pdf'
    tail = url.rstrip('/').rsplit('/', 1)[1]
    year, kind = tail.split('-')
    return self.current(int(year), kind)

  def parse(self, cached=None, incremental=None):
    return self.recipe.fetch_and_parse(self.fetch, cached_parsed=cached,
      incremental_update=(cached is not None) if incremental is None else incremental)

  def cache(self, parsed):
    return build_import_cache_data(self.recipe.source_id, parsed)

  def test_missing_current_books_recover_with_savings_and_repeat_after_reload(self):
    full = self.parse()
    self.assertEqual(12, len(self.calls))
    self.assertTrue(all(u['complete'] for u in full['incremental_state']['units'].values()))
    stale = without_unit(self.cache(full), 'year:2026')
    self.assertEqual(len(full['entries']) - 6, len(stale['entries']))
    self.calls.clear()
    updated = self.parse(stale)
    self.assertEqual(full['entries'], updated['entries'])
    self.assertEqual(4, len(self.calls))
    self.calls.clear()
    repeated = self.parse(self.cache(updated))
    self.assertEqual(full['entries'], repeated['entries'])
    self.assertEqual(4, len(self.calls))
    self.assertEqual(updated['incremental_state'], repeated['incremental_state'])

  def test_missing_historical_year_restores_actual_six_books(self):
    full = self.parse()
    stale = without_unit(self.cache(full), 'year:2022')
    self.assertEqual(len(full['entries']) - 6, len(stale['entries']))
    self.calls.clear()
    self.assertEqual(full['entries'], self.parse(stale)['entries'])
    self.assertEqual(7, len(self.calls))

  def test_missing_pdf_restores_history_with_measured_fetch(self):
    full = self.parse()
    self.calls.clear()
    updated = self.parse(without_unit(self.cache(full), 'pdf'))
    self.assertEqual(full['entries'], updated['entries'])
    self.assertEqual(5, len(self.calls))

  def test_legacy_cache_source_scope_and_complete_refresh_fetch_all(self):
    full = self.parse()
    corrupt = self.cache(full)
    corrupt['incremental_state']['source_key'] = 'different-source'
    for cached, incremental in (({'entries': full['entries']}, True), (corrupt, True), (self.cache(full), False)):
      self.calls.clear()
      self.assertEqual(full['entries'], self.parse(cached, incremental)['entries'])
      self.assertEqual(12, len(self.calls))

  def test_fresh_archive_winner_change_replaces_promotion_and_author(self):
    full = self.parse()
    self.winner, self.writer = 1, 'Corrected Writer'
    self.calls.clear()
    changed = self.parse(self.cache(full))
    rows = [r for r in changed['entries'] if r['award_year'] == '2025']
    self.assertEqual(['Book 2025 1'], [r['title'] for r in rows if r['result'] == 'winner'])
    self.assertEqual(6, len(rows))
    self.assertEqual(6, len(self.calls))
    self.winner, self.writer = 0, 'Author'
    restored = self.parse(self.cache(changed))
    self.assertEqual(full['entries'], restored['entries'])

  def test_failed_annual_refresh_retains_whole_year_and_retries(self):
    full = self.parse()
    self.errors['https://cbca.org.au/2026-shortlist/'] = RuntimeError('unavailable')
    failed = self.parse(self.cache(full))
    self.assertEqual(full['entries'], failed['entries'])
    self.assertFalse(failed['incremental_state']['units']['year:2026']['complete'])
    self.assertTrue(any('retained whole' in n for n in failed['notes']))
    self.errors.clear()
    recovered = self.parse(self.cache(failed))
    self.assertEqual(full['entries'], recovered['entries'])
    self.assertTrue(all(u['complete'] for u in recovered['incremental_state']['units'].values()))

  def test_failed_pdf_retains_whole_history_pending_retry(self):
    full = self.parse()
    broken = self.cache(full)
    broken['incremental_state']['units']['pdf']['complete'] = False
    self.errors[PDF_URL] = RuntimeError('unavailable')
    failed = self.parse(broken)
    self.assertEqual(full['entries'], failed['entries'])
    self.assertFalse(failed['incremental_state']['units']['pdf']['complete'])

  def test_critical_errors_propagate_through_linked_fetches(self):
    for url in (PDF_URL, AWARDS_URL, SHORTLIST_URL, NOTABLES_URL):
      for error in (ImportCancelledError, CamoufoxRequiredError):
        self.errors = {url: error('stop')}
        with self.subTest(url=url, error=error), self.assertRaises(error):
          self.parse()

  def test_notable_only_book_is_not_a_nominee(self):
    full = self.parse()
    self.assertNotIn('Book 2022 6', [r['title'] for r in full['entries']])

  def test_partial_shortlist_cannot_certify_year(self):
    full = self.parse()
    missing = without_unit(self.cache(full), 'year:2022')
    self.overrides[SHORTLIST_URL] = self.shortlist().replace('<p><a href="/book-5/">Book 2022 5</a></p>', '')
    parsed = self.parse(missing)
    self.assertFalse(parsed['incremental_state']['units']['year:2022']['complete'])
    self.assertTrue(any('six distinct' in n for n in parsed['notes']))

  def test_review_uses_only_own_bibliographic_header(self):
    html = '<article><h1>A Book</h1><h2>Real Creator, <em>A Book</em>, Publisher, ISBN 9781234567890</h2><p>Reviewed by Different Person</p><h2>Related Posts</h2></article>'
    self.assertEqual('Real Creator', review_creator(html, 'A Book'))
    with self.assertRaises(ValueError):
      review_creator(html.replace('ISBN 9781234567890', ''), 'A Book')

  def test_calendar_rollover_discovers_new_year_without_losing_history(self):
    full = self.parse()
    self.years.append(2027)
    self.calls.clear()
    updated = self.parse(self.cache(full))
    self.assertEqual(len(full['entries']) + 6, len(updated['entries']))
    self.assertIn('year:2027', updated['incremental_state']['units'])
    self.assertEqual(4, len(self.calls))

  def test_open_new_year_keeps_nominees_and_refreshes_them_on_repeat(self):
    full = self.parse()
    self.years.append(2027)
    original = self.panel
    self.panel = lambda year: original(year).replace('Winner |', 'Shortlist |') if year == 2027 else original(year)
    self.overrides[AWARDS_URL] = '<main><h1>Book of the Year Awards</h1><a href="/2027-shortlist/">2027 Shortlist</a></main>'
    self.calls.clear()
    updated = self.parse(self.cache(full))
    rows = [r for r in updated['entries'] if r['award_year'] == '2027']
    self.assertEqual(6, len(rows))
    self.assertTrue(all(r['result'] == 'shortlisted' for r in rows))
    self.assertTrue(updated['incremental_state']['units']['year:2027']['complete'])
    self.calls.clear()
    repeated = self.parse(self.cache(updated))
    self.assertEqual(updated['entries'], repeated['entries'])
    self.assertIn(('https://cbca.org.au/2027-shortlist/', 'camoufox'), self.calls)

  def test_shortlist_typo_matches_only_its_exact_metadata_review_url(self):
    source = self.shortlist().replace('Book 2022 0', 'Printed Typo')
    notable = self.notables().replace('<td>Book 2022 0</td>', '<td><a href="/book-0/">Book 2022 0</a><p>Another review label</p></td>')
    rows = shortlist_rows(self.recipe.parser(), source, lambda url: notable if url == NOTABLES_URL else self.fail(url))
    self.assertEqual('Book 2022 0', rows[0]['title'])
    self.assertEqual('Printed Typo', rows[0]['source_title'])
    self.assertEqual(NOTABLES_URL, rows[0]['title_source_url'])

  def test_wrong_notable_year_is_rejected_even_when_slug_looks_right(self):
    with self.assertRaises(ValueError):
      shortlist_rows(self.recipe.parser(), self.shortlist(), lambda _url: self.notables().replace('2022 CBCA', '2021 CBCA'))

  def test_duplicate_reviews_do_not_duplicate_nominees(self):
    source = self.shortlist().replace('</article>', '<p><a href="/book-0-second-review/">Book 2022 0 review by Someone Else</a></p></article>')
    self.assertEqual(6, len(shortlist_links(self.recipe.parser(), source)))

  def test_browser_rejection_recovers_same_url_and_resets_next_import(self):
    def callback(url, **kwargs):
      if kwargs.get('transport') == 'camoufox':
        self.calls.append((url, 'rejected-browser'))
        return '<html>Challenge page</html>'
      return self.fetch(url, **kwargs)
    recovered = self.recipe.fetch_and_parse(callback)
    self.assertTrue(recovered['entries'])
    self.assertEqual((self.recipe.URL, 'rejected-browser'), self.calls[0])
    self.assertEqual((self.recipe.URL, None), self.calls[1])
    self.assertEqual(1, sum(transport == 'rejected-browser' for _, transport in self.calls))
    self.calls.clear()
    fresh = self.parse()
    self.assertEqual(recovered['entries'], fresh['entries'])
    self.assertEqual((self.recipe.URL, 'camoufox'), self.calls[0])

  def test_pdf_sources_never_use_browser_transport(self):
    self.parse()
    self.assertTrue(all(transport is None for url, transport in self.calls if url == PDF_URL or url.endswith('.pdf')))

  def test_corrupt_source_projection_forces_its_historical_reload(self):
    full = self.parse()
    cached = self.cache(full)
    cached['incremental_state']['units']['pdf']['metadata']['rows'][0]['reference'] = 999999
    self.calls.clear()
    self.assertEqual(full['entries'], self.parse(cached)['entries'])
    self.assertIn((PDF_URL, None), self.calls)

  def test_failed_discovery_retains_books_but_cannot_certify_complete_state(self):
    full = self.parse()
    self.errors[AWARDS_URL] = RuntimeError('discovery unavailable')
    updated = self.parse(self.cache(full))
    self.assertEqual(full['entries'], updated['entries'])
    self.assertFalse(updated['incremental_state']['units']['awards']['complete'])

  def test_complete_shortlist_replaces_stale_archive_nominee_but_keeps_winner(self):
    archive = self.rows(2026, winner=True)
    archive[5]['title'] = 'Wrong Earlier Book'
    for r in archive:
      r['source_url'] = self.recipe.URL
    shortlist = self.rows(2026)
    rows = merge_year(archive, shortlist)
    self.assertEqual(6, len(rows))
    self.assertNotIn('Wrong Earlier Book', [r['title'] for r in rows])
    self.assertEqual(['Book 2026 0'], [r['title'] for r in rows if r['result'] == 'winner'])

  def test_unique_same_creator_main_title_corrects_subtitle_without_mutating_sources(self):
    shortlist = self.rows(2023)
    shortlist[0]['title'] = 'DEEP: Delve into Hidden Worlds'
    winner = dict(shortlist[0], title='DEEP: Dive into Hidden Worlds', result='winner', source_url='https://cbca.org.au/2023-winners/')
    original = copy.deepcopy(shortlist)
    merged = merge_year([], shortlist + [winner])
    self.assertEqual(6, len(merged))
    row = next(r for r in merged if r['result'] == 'winner')
    self.assertEqual(winner['title'], row['title'])
    self.assertEqual(original[0]['title'], row['source_title'])
    self.assertEqual(original, shortlist)
    with self.assertRaises(ValueError):
      merge_year([], shortlist + [dict(winner, author='Different Writer')])

  def test_picture_history_accepts_source_proven_no_award_years(self):
    parser = CBCABookOfTheYearParser('Picture Book')
    rows = [dict(award_year=str(y), category='Picture Book', title=f'History {y}', author='Writer',
      result='shortlisted' if y in NO_WINNER['Picture Book'] else 'winner') for y in range(1955, 2022)]
    self.assertTrue(history_complete(parser, rows))
    self.assertFalse(history_complete(parser, [r for r in rows if r['award_year'] != '1974']))


if __name__ == '__main__':
  unittest.main()
