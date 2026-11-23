import unittest

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError, CamoufoxRequiredError
from parser.nebula import NebulaSFADBCategoryParser
from storage import build_import_cache_data


class SFADBUpdateTests(unittest.TestCase):

  def setUp(self):
    self.parser = NebulaSFADBCategoryParser()
    self.root = 'https://www.sfadb.com/Nebula_Awards'
    self.years = [2022, 2023, 2024]
    self.calls = []
    self.open_years = set()
    self.empty_years = set()
    self.failures = {}
    self.changed = set()

  def url(self, year):
    return f'{self.root}_{year}'

  def overview(self):
    return ''.join(f'<a href="{self.url(y)}">{y}</a>' for y in self.years)

  def page(self, year):
    winner = '' if year in self.open_years else '<span class="winner">Winner:</span>'
    category = 'Short Story' if year in self.empty_years else 'Novel'
    title = 'Promoted' if year in self.changed else 'Book'
    return f'<title>sfadb: Nebula Awards {year}</title><div class="categoryblock">'\
      f'<div class="category">{category}</div><ul><li>{winner}<b>{title} {year}</b>, '\
      '<a href="Writer">Writer One</a> (Publisher)</li></ul></div>'

  def fetch(self, url):
    self.calls.append(url)
    if url in self.failures:
      value = self.failures[url]
      if isinstance(value, Exception):
        raise value
      return value
    return self.page(next(y for y in self.years if url == self.url(y)))

  def parse(self, cache=None, enabled=True):
    return self.parser.parse(self.overview(), self.root, 'Nebula Novel', 'Best Novel',
      ('Novel',), fetch_url=self.fetch, cached_parsed=cache,
      incremental_update=cache is not None, enable_incremental=enabled)

  def cache(self, parsed):
    return build_import_cache_data('nebula', parsed)

  def test_reuse_closed_years_and_recover_missing_history(self):
    full = self.parse()
    self.calls = []
    old = without_unit(self.cache(full), self.url(2022))
    update = self.parse(old)
    self.assertEqual(full['entries'], update['entries'])
    self.assertEqual([self.url(2022), self.url(2024)], self.calls)
    self.calls = []
    self.assertEqual(full['entries'], self.parse(self.cache(update))['entries'])
    self.assertEqual([self.url(2024)], self.calls)

  def test_new_year_and_unsettled_winner_promotion(self):
    self.open_years.add(2023)
    old = self.cache(self.parse())
    self.open_years.clear()
    self.changed.add(2023)
    self.years.append(2025)
    self.calls = []
    update = self.parse(old)
    self.assertEqual([self.url(2023), self.url(2025)], self.calls)
    self.assertEqual(self.parse()['entries'], update['entries'])
    promoted = next(e for e in update['entries'] if e['award_year'] == '2023')
    self.assertEqual('winner', promoted['result'])
    self.assertEqual('2023', promoted['position'])

  def test_failed_or_malformed_page_retains_pending_history(self):
    for failure in (OSError('offline'), '<h1>Challenge</h1>', '<html>\x00</html>', self.page(2023)):
      with self.subTest(failure=failure):
        full = self.parse()
        old = self.cache(full)
        old['incremental_state']['units'][self.url(2022)]['complete'] = False
        self.failures[self.url(2022)] = failure
        update = self.parse(old)
        self.assertEqual(full['entries'], update['entries'])
        self.assertFalse(update['incremental_state']['units'][self.url(2022)]['complete'])
        self.assertTrue(update['notes'])
        self.failures.clear()
        self.calls = []
        self.assertEqual(full['entries'], self.parse(self.cache(update))['entries'])
        self.assertIn(self.url(2022), self.calls)

  def test_empty_categories_are_reused_only_for_recognizable_year_pages(self):
    self.empty_years.add(2022)
    full = self.parse()
    self.calls = []
    self.assertEqual(full['entries'], self.parse(self.cache(full))['entries'])
    self.assertNotIn(self.url(2022), self.calls)

  def test_legacy_or_different_source_scope_rebuilds(self):
    full = self.parse()
    wrong = self.cache(full)
    wrong['incremental_state']['source_key'] = 'different category'
    for old in ({'entries': full['entries']}, wrong):
      self.calls = []
      self.assertEqual(full['entries'], self.parse(old)['entries'])
      self.assertEqual(3, len(self.calls))

  def test_non_opted_in_callers_keep_existing_result_shape_and_fetch_all_years(self):
    old = self.cache(self.parse())
    self.calls = []
    parsed = self.parse(old, enabled=False)
    self.assertNotIn('incremental_state', parsed)
    self.assertEqual(3, len(self.calls))

  def test_cancellation_and_browser_requirement_propagate(self):
    for error in (ImportCancelledError('stop'), CamoufoxRequiredError('required')):
      self.failures[self.url(2022)] = error
      with self.assertRaises(type(error)):
        self.parse()

  def test_nebula_fetchers_forward_cache_only_to_sfadb_attempts(self):
    from url_fetcher.nebula import (
      UrlFetcherNebulaAwardsNovel, UrlFetcherNebulaAwardsNovella,
      UrlFetcherNebulaAndreNorton, UrlFetcherNebulaAwardsComics,
    )
    for cls in (UrlFetcherNebulaAwardsNovel, UrlFetcherNebulaAwardsNovella,
                UrlFetcherNebulaAndreNorton, UrlFetcherNebulaAwardsComics):
      with self.subTest(recipe=cls):
        recipe = cls()
        category = recipe.CATEGORY if cls is UrlFetcherNebulaAwardsNovella else recipe.parser().CATEGORY
        def fetch(url):
          if url.startswith('https://nebulas.sfwa.org'):
            raise OSError('official unavailable')
          if url == self.root:
            return self.overview()
          year = next(y for y in self.years if url == self.url(y))
          return self.page(year).replace('>Novel<', f'>{category}<')
        choice = 'automatic' if cls is UrlFetcherNebulaAwardsNovella else 1
        full = recipe.fetch_and_parse(fetch, source_choice=choice)
        cache = self.cache(full)
        update = recipe.fetch_and_parse(fetch, source_choice=choice,
          cached_parsed=cache, incremental_update=True)
        self.assertEqual(full['entries'], update['entries'])
        self.assertEqual(full['notes'], update['notes'])
        self.assertEqual(3, len(full['entries']))
        self.assertFalse(update['match_series'])
        if hasattr(recipe, 'source_attempts'):
          official, sfadb = recipe.source_attempts()
          self.assertFalse(official.supports_incremental)
          self.assertTrue(sfadb.supports_incremental)

  def test_andre_norton_embedded_result_blocks_stop_at_the_next_award(self):
    from parser.nebula import NebulaAndreNortonSFADBParser
    page = '''<div class="category"><a>Andre Norton Award</a>—</div>
      <div class="categoryblock"><div class="category">Winner</div>
        <ul><li><b>The Winner</b>, <a>Writer One</a> (Publisher)</li></ul></div>
      <div class="categoryblock"><div class="category">Finalists</div>
        <ul><li><b>The Finalist</b>, <a>Writer Two</a> (Publisher)</li></ul></div>
      <div class="category">SFWA Grand Master Award—</div>
      <div class="categoryblock"><div class="category">Winner</div>
        <ul><li><b>Unrelated Book</b>, <a>Other Writer</a></li></ul></div>'''
    entries = NebulaAndreNortonSFADBParser().parse_year(page, self.url(2024),
      2024, 'Andre Norton', ('andre norton award',))
    self.assertEqual(['The Winner', 'The Finalist'], [e['title'] for e in entries])
    self.assertEqual(['winner', 'nominee'], [e['result'] for e in entries])
    self.assertEqual(['2024', '2024.01'], [e['position'] for e in entries])

  def test_world_fantasy_categories_recover_history_and_preserve_ties_and_editors(self):
    from url_fetcher import available_url_fetchers
    recipes = [r for r in available_url_fetchers() if r.source_id.startswith('world_fantasy_')]
    for recipe in recipes:
      with self.subTest(recipe=recipe.source_id):
        if recipe.source_id == 'world_fantasy_collection_anthology':
          self.assertFalse(recipe.source_attempts()[0].supports_incremental)
          continue
        calls = []
        def fetch(url):
          calls.append(url)
          if url == recipe.URL:
            return ''.join(f'<a href="{recipe.URL}_{y}">{y}</a>' for y in self.years)
          year = next(y for y in self.years if url == f'{recipe.URL}_{y}')
          return f'<title>sfadb: World Fantasy Awards {year}</title>'\
            f'<div class="categoryblock"><div class="category">{recipe.CATEGORY}</div><ul>'\
            '<li>Winner: <b>Shared Work</b>, <a href="A">Editor One</a>, '\
            '<a href="B">Editor Two</a> &amp; <a href="C">Editor Three</a>, eds. (Publisher)</li>'\
            '<li>Winner: <b>Tied Work</b>, <a href="D">Writer Four</a> (Publisher)</li></ul></div>'
        full = recipe.fetch_and_parse(fetch, source_choice=0)
        self.assertEqual(4, len(calls))
        old = without_unit(build_import_cache_data(recipe.source_id, full), f'{recipe.URL}_2022')
        calls.clear()
        update = recipe.fetch_and_parse(fetch, source_choice=0,
          cached_parsed=old, incremental_update=True)
        self.assertEqual(full['entries'], update['entries'])
        self.assertEqual([recipe.URL, f'{recipe.URL}_2022', f'{recipe.URL}_2024'], calls)
        self.assertEqual(['2022', '2022'], [e['position'] for e in update['entries'][:2]])
        self.assertEqual(['Editor One', 'Editor Two', 'Editor Three'], update['entries'][0]['authors'])

  def test_clarke_reuses_result_section_years_and_preserves_placing_labels(self):
    from url_fetcher.clarke import UrlFetcherArthurCClarkeAwardNovel
    recipe = UrlFetcherArthurCClarkeAwardNovel()
    calls = []
    def fetch(url):
      calls.append(url)
      if url == recipe.SFADB_URL:
        return ''.join(f'<a href="{recipe.SFADB_URL}_{y}">{y}</a>' for y in self.years)
      year = next(y for y in self.years if url == f'{recipe.SFADB_URL}_{y}')
      return f'<title>sfadb: Arthur C Clarke Award {year}</title>' + ''.join(
        f'<div class="categoryblock"><div class="category">{label}</div><ul>'
        f'<li><b>{label} Book</b>, <a href="Writer">Writer One</a> (Publisher)</li></ul></div>'
        for label in ('Winner', 'Runner-up', 'Third Place', 'Shortlist'))
    full = recipe.fetch_and_parse(fetch, source_choice=1)
    self.assertEqual(4, len(calls))
    old = without_unit(build_import_cache_data(recipe.source_id, full), f'{recipe.SFADB_URL}_2022')
    calls.clear()
    update = recipe.fetch_and_parse(fetch, source_choice=1, cached_parsed=old, incremental_update=True)
    self.assertEqual(full['entries'], update['entries'])
    self.assertEqual(3, len(calls))
    self.assertEqual(['winner', 'runner-up', 'third-place', 'nominee'],
      [e['result'] for e in update['entries'][:4]])
    official, sfadb = recipe.source_attempts()
    self.assertFalse(official.supports_incremental)
    self.assertTrue(sfadb.supports_incremental)

  def test_all_bsfa_categories_reuse_years_without_changing_isfdb_fallback(self):
    from url_fetcher import available_url_fetchers
    recipes = [r for r in available_url_fetchers() if r.source_id.startswith('bsfa_')]
    self.assertEqual(5, len(recipes))
    for recipe in recipes:
      with self.subTest(recipe=recipe.source_id):
        calls = []
        def fetch(url):
          calls.append(url)
          if url == recipe.URL:
            return ''.join(f'<a href="{recipe.URL}_{y}">{y}</a>' for y in self.years)
          year = next(y for y in self.years if url == f'{recipe.URL}_{y}')
          return self.page(year).replace('>Novel<', f'>{recipe.CATEGORY_ALIASES[0]}<')
        full = recipe.fetch_and_parse(fetch, source_choice=0)
        calls.clear()
        update = recipe.fetch_and_parse(fetch, source_choice=0,
          cached_parsed=build_import_cache_data(recipe.source_id, full), incremental_update=True)
        self.assertEqual(full['entries'], update['entries'])
        self.assertEqual([recipe.URL, f'{recipe.URL}_2024'], calls)
        self.assertEqual(3, len(update['entries']))
        primary, fallback = recipe.source_attempts()
        self.assertTrue(primary.supports_incremental)
        self.assertFalse(fallback.supports_incremental)

  def test_philip_k_dick_special_citation_positions_survive_updates(self):
    from url_fetcher.philip_k_dick import UrlFetcherPhilipKDickAwardNovel
    recipe, calls = UrlFetcherPhilipKDickAwardNovel(), []
    def fetch(url):
      calls.append(url)
      if url == recipe.URL:
        return ''.join(f'<a href="{recipe.URL}_{y}">{y}</a>' for y in self.years)
      year = next(y for y in self.years if url == f'{recipe.URL}_{y}')
      return f'<title>sfadb: Philip K Dick Award {year}</title>' + ''.join(
        f'<div class="categoryblock"><div class="category">{label}</div><ul>'
        f'<li><b>{label} Book</b>, <a href="Writer">Writer One</a> (Publisher)</li></ul></div>'
        for label in ('Winner', 'Special Citation', 'Finalists'))
    full = recipe.fetch_and_parse(fetch)
    calls.clear()
    update = recipe.fetch_and_parse(fetch,
      cached_parsed=build_import_cache_data(recipe.source_id, full), incremental_update=True)
    self.assertEqual(full['entries'], update['entries'])
    self.assertEqual(2, len(calls))
    citations = [e for e in update['entries'] if e['result'] == 'special-citation']
    self.assertEqual(['2022.5', '2023.5', '2024.5'], [e['position'] for e in citations])

  def test_mythopoeic_active_scopes_reuse_years_and_legacy_fantasy_stays_opted_out(self):
    from url_fetcher import available_url_fetchers
    recipes = [r for r in available_url_fetchers() if r.source_id.startswith('mythopoeic_')]
    self.assertEqual(4, len(recipes))
    for recipe in recipes:
      with self.subTest(recipe=recipe.source_id):
        if recipe.source_id == 'mythopoeic_fantasy':
          self.assertFalse(recipe.source_attempts()[0].supports_incremental)
          continue
        calls = []
        def fetch(url):
          calls.append(url)
          if url == recipe.URL:
            return ''.join(f'<a href="{recipe.URL}_{y}">{y}</a>' for y in self.years)
          year = next(y for y in self.years if url == f'{recipe.URL}_{y}')
          return self.page(year).replace('>Novel<', f'>{recipe.CATEGORY_ALIASES[0]}<')
        full = recipe.fetch_and_parse(fetch)
        calls.clear()
        update = recipe.fetch_and_parse(fetch,
          cached_parsed=build_import_cache_data(recipe.source_id, full), incremental_update=True)
        self.assertEqual(full['entries'], update['entries'])
        self.assertEqual(2, len(calls))
        self.assertEqual(3, len(update['entries']))

  def test_bram_stoker_all_categories_keep_eligibility_year_and_contributor_boundaries(self):
    from url_fetcher import available_url_fetchers
    recipes = [r for r in available_url_fetchers() if r.source_id.startswith('bram_stoker_')]
    self.assertEqual(10, len(recipes))
    for recipe in recipes:
      with self.subTest(recipe=recipe.source_id):
        calls = []
        def fetch(url):
          calls.append(url)
          if url == recipe.URL:
            return ''.join(f'<a href="{recipe.URL}_{y}">{y}</a>' for y in self.years)
          year = next(y for y in self.years if url == f'{recipe.URL}_{y}')
          return f'<title>sfadb: Bram Stoker Awards {year}</title><p>Eligibility Year: {year-1}</p>'\
            f'<div class="categoryblock"><div class="category">{recipe.CATEGORY_ALIASES[0]}</div><ul>'\
            '<li>Winner: <b>Winning Book</b>, <a href="One">Writer One</a> &amp; '\
            '<a href="Two">Writer Two</a> (Publisher)</li></ul></div>'
        full = recipe.fetch_and_parse(fetch, source_choice=0)
        old = without_unit(build_import_cache_data(recipe.source_id, full), f'{recipe.URL}_2022')
        calls.clear()
        update = recipe.fetch_and_parse(fetch, source_choice=0,
          cached_parsed=old, incremental_update=True)
        self.assertEqual(full['entries'], update['entries'])
        self.assertEqual(3, len(calls))
        self.assertEqual(['2021', '2022', '2023'], [e['award_year'] for e in update['entries']])
        self.assertEqual(['Writer One', 'Writer Two'], update['entries'][0]['authors'])

  def test_changed_parser_configuration_rebuilds_years(self):
    args = (self.overview(), self.root, 'Configured award', 'Novel', ('novel',))
    full = self.parser.parse(*args, fetch_url=self.fetch, enable_incremental=True,
      configuration_key={'coverage': 1})
    self.calls = []
    update = self.parser.parse(*args, fetch_url=self.fetch, enable_incremental=True,
      cached_parsed=self.cache(full), incremental_update=True, configuration_key={'coverage': 2})
    self.assertEqual(full['entries'], update['entries'])
    self.assertEqual(3, len(self.calls))

  def test_shirley_jackson_reuse_keeps_exact_packaged_coverage_validation(self):
    from parser.shirley_jackson import load_shirley_jackson_isfdb_supplement, category_key
    from url_fetcher import available_url_fetchers
    from url_fetcher.generic import UrlFetcherError
    coverage = load_shirley_jackson_isfdb_supplement()['coverage']
    recipes = [r for r in available_url_fetchers() if r.source_id.startswith('shirley_jackson_')]
    self.assertEqual(4, len(recipes))
    for recipe in recipes:
      with self.subTest(recipe=recipe.source_id):
        expected, calls, partial = coverage[category_key(recipe.CATEGORY)], [], [False]
        years = sorted(expected, key=int)
        def fetch(url):
          calls.append(url)
          if url == recipe.URL:
            return ''.join(f'<a href="{recipe.URL}_{year}">{year}</a>' for year in years)
          year = next(year for year in years if url == f'{recipe.URL}_{year}')
          total = expected[year]['rows'] - int(partial[0] and year == years[-1])
          return f'<title>sfadb: Shirley Jackson Awards {year}</title>'\
            f'<div class="categoryblock"><div class="category">{recipe.CATEGORY_ALIASES[0]}</div><ul>' + ''.join(
              f'<li>{"Winner:" if i < expected[year]["winners"] else ""}'
              f'<b>Book {year}-{i}</b>, <a href="Writer">Writer One</a> (Publisher)</li>'
              for i in range(total)) + '</ul></div>'
        full = recipe.fetch_and_parse(fetch, source_choice=0)
        full_count = len(calls)
        old = without_unit(build_import_cache_data(recipe.source_id, full), f'{recipe.URL}_{years[0]}')
        calls.clear()
        update = recipe.fetch_and_parse(fetch, source_choice=0, cached_parsed=old, incremental_update=True)
        self.assertEqual(full['entries'], update['entries'])
        self.assertLess(len(calls), full_count)
        partial[0] = True
        with self.assertRaisesRegex(UrlFetcherError, 'incomplete'):
          recipe.fetch_and_parse(fetch, source_choice=0,
            cached_parsed=build_import_cache_data(recipe.source_id, full), incremental_update=True)

  def test_all_aurora_categories_keep_book_filter_scope_and_recover_history(self):
    from url_fetcher import available_url_fetchers
    recipes = [r for r in available_url_fetchers() if r.source_id.startswith('aurora_')]
    self.assertEqual(5, len(recipes))
    for recipe in recipes:
      with self.subTest(recipe=recipe.source_id):
        calls = []
        def fetch(url):
          calls.append(url)
          if url == recipe.URL:
            return ''.join(f'<a href="{recipe.URL}_{y}">{y}</a>' for y in self.years)
          year = next(y for y in self.years if url == f'{recipe.URL}_{y}')
          return self.page(year).replace('>Novel<', f'>{recipe.CATEGORY_ALIASES[0]}<')
        full = recipe.fetch_and_parse(fetch, source_choice=0)
        old = without_unit(build_import_cache_data(recipe.source_id, full), f'{recipe.URL}_2022')
        calls.clear()
        update = recipe.fetch_and_parse(fetch, source_choice=0, cached_parsed=old, incremental_update=True)
        self.assertEqual(full['entries'], update['entries'])
        self.assertEqual(3, len(calls))
        self.assertEqual(3, len(update['entries']))


if __name__ == '__main__':
  unittest.main()
