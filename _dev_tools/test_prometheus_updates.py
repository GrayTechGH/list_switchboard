import unittest

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import missing_source_fixture
from parser.prometheus import PrometheusParser
from storage import build_import_cache_data
from url_fetcher.prometheus import (
  UrlFetcherPrometheusNovel, UrlFetcherPrometheusHallOfFame, UrlFetcherPrometheusSpecialAwards,
)


class PrometheusUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe = UrlFetcherPrometheusHallOfFame()
    self.years = [2022, 2023, 2024]
    self.winners = {2022: 'Unique 2022', 2023: 'Unique 2023', 2024: 'Repeated Work'}
    self.calls, self.omit_repeated, self.failures = [], set(), {}
    self.film_winner = False

  def url(self, year):
    return f'{self.recipe.URL}_{year}'

  def fetch(self, url):
    self.calls.append(url)
    if url in self.failures:
      raise self.failures[url]
    if url == self.recipe.URL:
      return ''.join(f'<a href="{self.url(y)}">{y}</a>' for y in self.years)
    year = next(y for y in self.years if url == self.url(y))
    winner = self.winners[year]
    notes = ' (film)' if self.film_winner and year == 2022 else ' (Publisher)'
    rows = f'<li>Winner: <b>{winner}</b>, <a href="Writer">Writer One</a>{notes}</li>'
    for title in (f'Nominee {year}', 'Repeated Work'):
      if title != winner and not (title == 'Repeated Work' and year in self.omit_repeated):
        rows += f'<li><b>{title}</b>, <a href="Writer">Writer One</a> (Publisher)</li>'
    return f'<title>sfadb: Prometheus Awards {year}</title><div class="categoryblock">'\
      f'<div class="category">{self.recipe.CATEGORY}</div><ul>{rows}</ul></div>'

  def parse(self, cache=None):
    return self.recipe.fetch_and_parse(self.fetch, source_choice=0,
      cached_parsed=cache, incremental_update=cache is not None)

  def cache(self, parsed):
    return build_import_cache_data(self.recipe.source_id, parsed)

  def test_hall_of_fame_missing_work_recovered_without_refetching_settled_history(self):
    full = self.parse()
    self.assertEqual(4, len(self.calls))
    old, _removed = missing_source_fixture(self.cache(full))
    self.calls = []
    update = self.parse(old)
    self.assertEqual(full['entries'], update['entries'])
    self.assertLess(len(self.calls), 4)
    self.calls = []
    self.assertEqual(full['entries'], self.parse(self.cache(update))['entries'])
    self.assertEqual([self.recipe.URL, self.url(2024)], self.calls)

  def test_changed_current_winner_recovers_older_nomination_previously_hidden_by_collapse(self):
    old = self.cache(self.parse())
    self.winners[2024] = 'Corrected Winner'
    self.omit_repeated.add(2024)
    update = self.parse(old)
    self.assertEqual(self.parse()['entries'], update['entries'])
    repeated = next(e for e in update['entries'] if e['title'] == 'Repeated Work')
    self.assertEqual(('2023', 'nominee'), (repeated['award_year'], repeated['result']))

  def test_new_year_preserves_past_winner_and_moves_latest_unwon_nominations(self):
    old = self.cache(self.parse())
    self.years.append(2025)
    self.winners[2025] = 'Newest Winner'
    update = self.parse(old)
    self.assertEqual(self.parse()['entries'], update['entries'])
    repeated = next(e for e in update['entries'] if e['title'] == 'Repeated Work')
    self.assertEqual('2024', repeated['award_year'])
    self.assertEqual('winner', repeated['result'])

  def test_filtered_media_winner_still_settles_the_book_ballot(self):
    self.film_winner = True
    full = self.parse()
    self.calls = []
    self.assertEqual(full['entries'], self.parse(self.cache(full))['entries'])
    self.assertNotIn(self.url(2022), self.calls)
    self.assertNotIn('Unique 2022', [e['title'] for e in full['entries']])

  def test_unparseable_book_winner_does_not_certify_a_settled_ballot(self):
    parser = PrometheusParser(books_only=True)
    html = '<div class="categoryblock"><div class="category">Hall of Fame</div>'\
      '<ul><li>Winner: Unparseable winner without author credit</li></ul></div>'
    self.assertFalse(parser.unit_is_settled(html,
      [{'title': 'Nominee', 'result': 'nominee'}], 'Hall of Fame', ('hall of fame',)))

  def test_books_only_configuration_change_refetches_original_years(self):
    self.film_winner = True
    full = self.parse()
    self.calls = []
    root = self.fetch(self.recipe.URL)
    parsed = PrometheusParser(books_only=False).parse(root, self.recipe.URL,
      self.recipe.NAME, self.recipe.CATEGORY, self.recipe.CATEGORY_ALIASES,
      fetch_url=self.fetch, cached_parsed=self.cache(full), incremental_update=True, enable_incremental=True)
    self.assertEqual(4, len(self.calls))
    self.assertIn('Unique 2022', [e['title'] for e in parsed['entries']])

  def test_novel_and_special_awards_keep_existing_source_and_filter_semantics(self):
    for factory in (UrlFetcherPrometheusNovel, UrlFetcherPrometheusSpecialAwards):
      with self.subTest(recipe=factory.source_id):
        self.recipe = factory()
        full = self.parse()
        self.calls = []
        update = self.parse(self.cache(full))
        self.assertEqual(full['entries'], update['entries'])
        self.assertEqual([self.recipe.URL, self.url(2024)], self.calls)


if __name__ == '__main__':
  unittest.main()
