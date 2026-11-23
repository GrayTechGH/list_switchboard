import unittest

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from storage import build_import_cache_data
from url_fetcher import available_url_fetchers


class DitmarUpdateTests(unittest.TestCase):

  def test_missing_year_new_year_and_historical_category_boundaries(self):
    recipes = [r for r in available_url_fetchers() if r.source_id.startswith('ditmar_')]
    self.assertEqual(3, len(recipes))
    for recipe in recipes:
      with self.subTest(recipe=recipe.source_id):
        years, calls = [1978, 1979, 2024], []
        def fetch(url):
          calls.append(url)
          if url == recipe.URL:
            return ''.join(f'<a href="{recipe.URL}_{y}">{y}</a>' for y in years)
          year = next(y for y in years if url == f'{recipe.URL}_{y}')
          # Mixed-length historical labels belong only to Novella/Novelette.
          categories = ['Australian SF' if year == 1978 else 'Australian Fiction',
            'Novel', 'Novella Or Novelette', 'Collected Work']
          return f'<title>sfadb: Ditmar Awards {year}</title>' + ''.join(
            f'<div class="categoryblock"><div class="category">{category}</div><ul>'
            f'<li>Winner: <b>{category} {year}</b>, <a href="One">Writer One</a></li>'
            '</ul></div>' for category in categories)
        full = recipe.fetch_and_parse(fetch, source_choice=0)
        self.assertEqual(4, len(calls))
        old = without_unit(build_import_cache_data(recipe.source_id, full), f'{recipe.URL}_1978')
        calls.clear()
        update = recipe.fetch_and_parse(fetch, source_choice=0,
          cached_parsed=old, incremental_update=True)
        self.assertEqual(full['entries'], update['entries'])
        self.assertEqual([recipe.URL, f'{recipe.URL}_1978', f'{recipe.URL}_2024'], calls)
        mixed = [e for e in update['entries'] if e['title'].startswith('Australian')]
        self.assertEqual(2 if recipe.source_id.endswith('novella_novelette') else 0, len(mixed))
        old = build_import_cache_data(recipe.source_id, update)
        years.append(2025)
        calls.clear()
        update = recipe.fetch_and_parse(fetch, source_choice=0,
          cached_parsed=old, incremental_update=True)
        self.assertEqual([recipe.URL, f'{recipe.URL}_2025'], calls)
        self.assertEqual(recipe.fetch_and_parse(fetch, source_choice=0)['entries'], update['entries'])
        primary, fallback = recipe.source_attempts()
        self.assertTrue(primary.supports_incremental)
        self.assertFalse(fallback.supports_incremental)
        self.assertFalse(update['match_series'])


if __name__ == '__main__':
  unittest.main()
