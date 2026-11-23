"""Settled-ballot reuse without accepting voting rounds as completed results."""

from copy import deepcopy
from datetime import date
import json
import unittest
from unittest.mock import patch

from _dev_tools import test_import_matching
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError, CamoufoxRequiredError
from parser import goodreads_choice_awards as choice
from storage import build_import_cache_data
from url_fetcher.goodreads_choice_awards import UrlFetcherGoodreadsChoiceAwardsFiction, UrlFetcherGoodreadsChoiceAwards


class GoodreadsChoiceUpdateTests(unittest.TestCase):

  def setUp(self):
    self.parser = choice.GoodreadsChoiceAwardsParser('Fiction')
    self.current = 2025
    self.years = [2023, 2024, 2025]
    self.absent, self.open, self.failures = set(), set(), {}
    self.calls, self.detail_failures, self.revised = [], set(), set()
    self.clock = patch.object(choice, 'date')
    self.clock.start().today.side_effect = lambda: date(self.current, 11, 18)
    self.addCleanup(self.clock.stop)
    self.candidates = patch.object(choice, 'goodreads_choice_candidate_years', side_effect=lambda: self.years)
    self.candidates.start()
    self.addCleanup(self.candidates.stop)

  def ballot_url(self, year):
    return f'https://www.goodreads.com/choiceawards/readers-favorite-fiction-books-{year}'

  def overview(self, year):
    category = 'Unrelated Category' if year in self.absent else self.parser.category
    return (f'<title>Goodreads Choice Awards {year}</title>'
      f'<a href="{self.ballot_url(year)}">{category}</a>'
      f'<a href="{choice.goodreads_choice_overview_url(year)}">{year} Awards</a>')

  def ballot(self, year):
    start = '<h2>Opening Round Nominees</h2>' if year in self.open else '<p>WINNER</p>'
    other = 'New' if year in self.revised else 'Second'
    return (f'<title>{self.parser.category} {year} Goodreads Choice Awards</title><h1>{self.parser.category}</h1>{start}'
      f'<div><a href="/book/show/{year}1.First"><img alt="First {year} by Writer One" /></a>100 votes</div>'
      '<h2>All Nominees</h2>'
      f'<div><a href="/book/show/{year}1.First"><img alt="First {year} by Writer One" /></a>100 votes</div>'
      f'<div><a href="/book/show/{year}2.Second"><img alt="{other} {year} by Writer Two" /></a>50 votes</div>')

  def fetch(self, url, **_kwargs):
    self.calls.append(url)
    if url in self.failures:
      raise self.failures[url]
    if url == choice.CHOICE_AWARDS_URL:
      return self.overview(self.current) + ''.join(
        f'<a href="{choice.goodreads_choice_overview_url(y)}">{y} Awards</a>' for y in self.years)
    if '/book/show/' in url:
      if url in self.detail_failures:
        raise ValueError('No usable contributor names')
      return '<div aria-label="List of contributors"><span data-testid="name">Extra Writer</span></div>'
    year = choice.year_from_text(url)
    if '/best-books-' in url:
      return self.overview(year)
    return self.ballot(year)

  def parse(self, old=None, enrich=True):
    return self.parser.parse(self.fetch(choice.CHOICE_AWARDS_URL),
      fetch_url=self.fetch, sleep=lambda _seconds: None, cached_parsed=old,
      incremental_update=old is not None, enrich_contributors=enrich)

  def cache(self, parsed):
    return json.loads(json.dumps(build_import_cache_data('goodreads_choice_awards_fiction', parsed)))

  def test_missing_real_year_roundtrip_and_repeat_reduce_requests(self):
    full = self.parse()
    self.assertEqual(6, len(full['entries']))
    self.assertEqual(9, len(self.calls))
    old = without_unit(self.cache(full), choice.goodreads_choice_overview_url(2024))
    self.assertEqual(4, len(old['entries']))
    self.calls.clear()
    updated = self.parse(old)
    self.assertEqual(full['entries'], updated['entries'])
    self.assertEqual(5, len(self.calls))
    self.calls.clear()
    repeat = self.parse(self.cache(updated))
    self.assertEqual(full['entries'], repeat['entries'])
    self.assertEqual(3, len(self.calls))
    self.assertTrue(all(unit['complete'] for unit in repeat['incremental_state']['units'].values()))

  def test_latest_completed_year_stays_fresh_and_replaces_removed_books(self):
    full = self.parse()
    self.revised.add(2025)
    updated = self.parse(self.cache(full))
    titles = {row['title'] for row in updated['entries']}
    self.assertIn('New 2025', titles)
    self.assertNotIn('Second 2025', titles)
    self.assertIn(self.ballot_url(2025), self.calls)
    self.assertEqual(3, sum(row['result'] == 'winner' for row in updated['entries']))

  def test_open_round_never_certifies_complete_or_deletes_cached_ballot(self):
    full = self.parse()
    self.open.add(2025)
    updated = self.parse(self.cache(full))
    self.assertEqual(full['entries'], updated['entries'])
    unit = updated['incremental_state']['units'][choice.goodreads_choice_overview_url(2025)]
    self.assertFalse(unit['complete'])
    self.assertTrue(any('pending' in note for note in updated['notes']))
    self.parser.validate_fetch_payload(self.ballot(2025), self.ballot_url(2025))
    self.open.clear()
    recovered = self.parse(self.cache(updated))
    self.assertEqual(full['entries'], recovered['entries'])
    self.assertTrue(recovered['incremental_state']['units'][choice.goodreads_choice_overview_url(2025)]['complete'])

  def test_full_open_round_imports_nominees_and_stays_unsettled(self):
    self.open.add(2025)
    full = self.parse()
    self.assertEqual(6, len(full['entries']))
    unit = full['incremental_state']['units'][choice.goodreads_choice_overview_url(2025)]
    self.assertTrue(unit['complete'])
    self.assertFalse(unit['metadata']['settled'])
    self.assertTrue(all(row['result'] == 'nominee' for row in full['entries'] if row['award_year'] == '2025'))
    self.calls.clear()
    self.parse(self.cache(full))
    self.assertNotIn(choice.goodreads_choice_overview_url(2024), self.calls)
    self.assertIn(self.ballot_url(2025), self.calls)

  def test_unsettled_nominees_refresh_until_winner_is_selected(self):
    self.open.add(2025)
    full = self.parse()
    self.calls.clear()
    repeat = self.parse(self.cache(full))
    self.assertEqual(full['entries'], repeat['entries'])
    self.assertIn(self.ballot_url(2025), self.calls)
    self.open.clear()
    selected = self.parse(self.cache(repeat))
    self.assertEqual(self.parse()['entries'], selected['entries'])
    self.assertTrue(selected['incremental_state']['units'][choice.goodreads_choice_overview_url(2025)]['metadata']['settled'])
    self.assertEqual(1, sum(row['result'] == 'winner' for row in selected['entries'] if row['award_year'] == '2025'))

  def test_new_year_discovery_and_rollover_preserve_enriched_history(self):
    full = self.parse()
    self.current = 2026
    self.years.append(2026)
    self.calls.clear()
    updated = self.parse(self.cache(full))
    self.assertEqual(8, len(updated['entries']))
    for row in full['entries']:
      self.assertIn(row, updated['entries'])
    self.assertNotIn(self.ballot_url(2025), self.calls)
    self.assertIn(self.ballot_url(2026), self.calls)

  def test_failed_historical_unit_retains_whole_year_and_retries(self):
    full = self.parse()
    old = self.cache(full)
    key = choice.goodreads_choice_overview_url(2024)
    old['incremental_state']['units'][key]['complete'] = False
    self.failures[self.ballot_url(2024)] = OSError('source unavailable')
    failed = self.parse(old)
    self.assertEqual(full['entries'], failed['entries'])
    self.assertFalse(failed['incremental_state']['units'][key]['complete'])
    self.failures.clear()
    self.calls.clear()
    recovered = self.parse(self.cache(failed))
    self.assertEqual(full['entries'], recovered['entries'])
    self.assertIn(self.ballot_url(2024), self.calls)
    self.assertTrue(recovered['incremental_state']['units'][key]['complete'])

  def test_legacy_wrong_scope_and_malformed_indexes_force_full_refresh(self):
    full = self.parse()
    baseline = len(self.calls)
    old = self.cache(full)
    bad_index = deepcopy(old)
    next(iter(bad_index['incremental_state']['units'].values()))['entry_indexes'] = [9999]
    wrong = deepcopy(old)
    wrong['incremental_state']['source_key'] = 'another category'
    for cache in ({'entries': full['entries']}, bad_index, wrong):
      self.calls.clear()
      self.assertEqual(full['entries'], self.parse(cache)['entries'])
      self.assertEqual(baseline, len(self.calls))

  def test_closed_absence_is_reused_but_latest_absence_refreshes(self):
    self.absent.update((2023, 2025))
    full = self.parse()
    self.assertEqual(2, len(full['entries']))
    self.calls.clear()
    self.parse(self.cache(full))
    self.assertNotIn(choice.goodreads_choice_overview_url(2023), self.calls)
    self.assertIn(choice.goodreads_choice_overview_url(2025), self.calls)
    self.assertNotIn(self.ballot_url(2025), self.calls)

  def test_contributor_failures_retry_and_successes_reuse_by_title_and_url(self):
    failed_url = 'https://www.goodreads.com/book/show/20252.Second'
    self.detail_failures.add(failed_url)
    full = self.parse()
    self.detail_failures.clear()
    self.calls.clear()
    updated = self.parse(self.cache(full))
    details = [url for url in self.calls if '/book/show/' in url]
    self.assertEqual([failed_url], details)
    self.assertNotEqual(full['entries'], updated['entries'])
    self.revised.add(2025)
    self.calls.clear()
    self.parse(self.cache(updated))
    self.assertEqual([failed_url], [url for url in self.calls if '/book/show/' in url])

  def test_critical_failures_propagate_from_overview_and_ballot(self):
    for url in (choice.goodreads_choice_overview_url(2024), self.ballot_url(2024)):
      for error in (ImportCancelledError('cancel'), CamoufoxRequiredError('required')):
        self.failures = {url: error}
        with self.assertRaises(type(error)):
          self.parse()

  def test_stale_year_document_retains_original_unit(self):
    full = self.parse()
    old = self.cache(full)
    key = choice.goodreads_choice_overview_url(2024)
    old['incremental_state']['units'][key]['complete'] = False
    original = self.fetch
    with patch.object(self, 'fetch', side_effect=lambda url, **kw:
        self.overview(2023) if url == key else original(url, **kw)):
      updated = self.parse(old)
    self.assertEqual(full['entries'], updated['entries'])
    self.assertFalse(updated['incremental_state']['units'][key]['complete'])

  def test_fetcher_forwards_cache_and_keeps_support_disabled(self):
    recipe = UrlFetcherGoodreadsChoiceAwardsFiction()
    full = recipe.fetch_and_parse(self.fetch, sleep=lambda _seconds: None)
    self.calls.clear()
    updated = recipe.fetch_and_parse(self.fetch, sleep=lambda _seconds: None,
      cached_parsed=self.cache(full), incremental_update=True)
    self.assertEqual(full['entries'], updated['entries'])
    self.assertEqual(3, len(self.calls))
    self.assertFalse(UrlFetcherGoodreadsChoiceAwards.SUPPORTS_INCREMENTAL_UPDATE)

  def test_all_fifteen_queued_categories_recover_and_reduce_requests(self):
    from _dev_tools.implement_import_updates import load_ledger
    from url_fetcher import available_url_fetchers
    queue = load_ledger()['recipes']
    recipes = [recipe for recipe in available_url_fetchers()
      if recipe.source_id.startswith('goodreads_choice_awards_') and recipe.source_id in queue]
    self.assertEqual(15, len(recipes))
    for recipe in recipes:
      with self.subTest(recipe=recipe.source_id):
        self.parser = recipe.parser()
        self.calls.clear()
        full = self.parse()
        baseline = len(self.calls)
        stale = without_unit(self.cache(full), choice.goodreads_choice_overview_url(2024))
        self.assertLess(len(stale['entries']), len(full['entries']))
        self.calls.clear()
        updated = self.parse(stale)
        self.assertEqual(full['entries'], updated['entries'])
        self.assertLess(len(self.calls), baseline)
        self.calls.clear()
        repeated = self.parse(self.cache(updated))
        self.assertEqual(full['entries'], repeated['entries'])
        self.assertLess(len(self.calls), baseline)
        self.assertFalse(UrlFetcherGoodreadsChoiceAwards.SUPPORTS_INCREMENTAL_UPDATE)

  def test_contributor_cancellation_and_required_browser_errors_propagate(self):
    for error in (ImportCancelledError('cancel'), CamoufoxRequiredError('required')):
      self.failures = {'https://www.goodreads.com/book/show/20251.First': error}
      with self.assertRaises(type(error)):
        self.parse()

  def test_changed_packaged_corrections_invalidate_old_source_scope(self):
    full = self.parse()
    self.parser.contributor_corrections['20241'] = {
      'title': 'First 2024', 'authors': ['Reviewed Writer'], 'categories': ['Fiction']}
    self.calls.clear()
    updated = self.parse(self.cache(full))
    self.assertIn(self.ballot_url(2024), self.calls)
    row = next(row for row in updated['entries'] if row['title'] == 'First 2024')
    self.assertEqual(['Reviewed Writer'], row['authors'])

  def test_invalid_source_projection_and_detail_metadata_are_refetched(self):
    full = self.parse()
    old = self.cache(full)
    key = choice.goodreads_choice_overview_url(2024)
    old['incremental_state']['units'][key]['metadata']['rows'] = [{'reference': 999}]
    old['incremental_state']['discovery']['contributors']['20251'] = ['invalid']
    self.calls.clear()
    updated = self.parse(old)
    self.assertEqual(full['entries'], updated['entries'])
    self.assertIn(self.ballot_url(2024), self.calls)
    self.assertIn('https://www.goodreads.com/book/show/20251.First', self.calls)

  def test_previous_current_year_stays_pending_when_root_navigation_retreats(self):
    full = self.parse()
    root = self.overview(2024)
    original = self.fetch
    with patch.object(self, 'fetch', side_effect=lambda url, **kw:
        root if url == choice.CHOICE_AWARDS_URL else original(url, **kw)):
      self.open.add(2025)
      updated = self.parse(self.cache(full))
    self.assertEqual(full['entries'], updated['entries'])
    self.assertFalse(updated['incremental_state']['units'][choice.goodreads_choice_overview_url(2025)]['complete'])

  def test_corrupt_cached_year_projection_forces_its_full_refresh(self):
    full = self.parse()
    old = self.cache(full)
    key = choice.goodreads_choice_overview_url(2024)
    old['incremental_state']['units'][key]['metadata']['rows'][0]['overrides']['award_year'] = '2023'
    self.calls.clear()
    updated = self.parse(old)
    self.assertEqual(full['entries'], updated['entries'])
    self.assertIn(self.ballot_url(2024), self.calls)

  def test_vote_only_cards_are_bounded_and_match_the_declared_round_count(self):
    def card(index):
      return f'<div class="answerWrapper"><a href="/book/show/{30000+index}.Work"><img alt="Work {index} by Writer {index}" /></a><button>Vote</button></div>'
    page = '<h1>Fiction</h1>'+card(99)+'<h2>Opening Round<br>Nominees</h2>'+''.join(card(i) for i in range(20))+'<h1>2025 Rules &amp; Eligibility</h1><h2>Opening Round: Nov 10-22</h2><p>In the first round there are 20 books in each category.</p>'+card(98)
    rows = self.parser.parse_category_page(page, self.ballot_url(2025))
    self.assertEqual(20, len(rows))
    self.assertTrue(all(row['result'] == 'nominee' for row in rows))
    self.assertNotIn('Work 99', [row['title'] for row in rows])
    self.assertNotIn('Work 98', [row['title'] for row in rows])
    shuffled = page.replace(''.join(card(i) for i in range(20)), ''.join(card(i) for i in reversed(range(20))))
    reordered = self.parser.parse_category_page(shuffled, self.ballot_url(2025))
    self.assertEqual(self.parser.entries_from_rows(rows), self.parser.entries_from_rows(reordered))
    notes = []
    self.assertEqual([], self.parser.parse_category_page(page.replace(card(5), ''), self.ballot_url(2025), notes=notes))
    self.assertTrue(any('rules specify 20' in note for note in notes))

  def test_unlabelled_winnerless_page_is_still_rejected(self):
    page = self.ballot(2025).replace('<p>WINNER</p>', '<h2>Nominees</h2>')
    self.assertEqual([], self.parser.parse_category_page(page, self.ballot_url(2025)))


if __name__ == '__main__':
  unittest.main()
