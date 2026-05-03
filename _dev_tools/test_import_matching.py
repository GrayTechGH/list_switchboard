#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

import json
import sys
import types
import unittest
from pathlib import Path


if globals().get('__file__') and __file__ != '<string>':
  ROOT = Path(__file__).resolve().parents[1]
else:
  ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))


class Dummy:

  def __init__(self, *args, **kwargs):
    pass

  def __getattr__(self, _name):
    return Dummy()

  def __call__(self, *args, **kwargs):
    return Dummy()


qt = types.ModuleType('qt')
qt_core = types.ModuleType('qt.core')
for name in (
    'QApplication', 'QCheckBox', 'QDialog', 'QDialogButtonBox', 'QHBoxLayout',
    'QHeaderView', 'QInputDialog', 'QLabel', 'QListWidget', 'QMessageBox',
    'QProgressDialog', 'QPushButton', 'QTableWidget', 'QTableWidgetItem',
    'QSizePolicy', 'QVBoxLayout'):
  setattr(qt_core, name, Dummy)
sys.modules.setdefault('qt', qt)
sys.modules.setdefault('qt.core', qt_core)

calibre = types.ModuleType('calibre')
calibre_gui2 = types.ModuleType('calibre.gui2')
calibre_gui2.error_dialog = Dummy()
calibre_gui2.question_dialog = Dummy()
sys.modules.setdefault('calibre', calibre)
sys.modules.setdefault('calibre.gui2', calibre_gui2)

plugin_package = types.ModuleType('calibre_plugins')
list_switchboard_package = types.ModuleType('calibre_plugins.list_switchboard')
config_module = types.ModuleType('calibre_plugins.list_switchboard.config')
config_module.prefs = {}
sys.modules.setdefault('calibre_plugins', plugin_package)
sys.modules.setdefault('calibre_plugins.list_switchboard', list_switchboard_package)
sys.modules.setdefault('calibre_plugins.list_switchboard.config', config_module)

import main


def build_lookup(values):
  lookup = {}
  for book_id, value in values.items():
    for key in main.match_keys(value):
      lookup.setdefault(key, []).append(book_id)
  return lookup


class ImportMatchingTest(unittest.TestCase):

  def test_recipe_preserves_goodreads_source_url(self):
    try:
      import recipe_parser
    except ModuleNotFoundError as err:
      if err.name == 'bs4':
        self.skipTest('BeautifulSoup is not available in this Python environment')
      raise

    def load_recipe(name):
      path = ROOT / 'recipes' / name
      return main.JsonRecipe(json.loads(path.read_text(encoding='utf-8')), name)

    top_novels = load_recipe('r_fantasy_top_novels_2025.json')
    standalone_recipe = load_recipe('r_fantasy_top_standalone_novels_2024.json')
    self_published_recipe = load_recipe('r_fantasy_top_self_published_novels_2024.json')
    sword_laser_recipe = load_recipe('sword_and_laser_book_list.json')
    html = '''
      <table>
        <tr><th>Rank</th><th>Series</th><th>Votes</th><th>Author</th><th>Rank Change</th></tr>
        <tr>
          <td>1</td>
          <td><a href="https://www.goodreads.com/series/66175-middle-earth">Middle-Earth Universe</a></td>
          <td>404</td>
          <td>J.R.R. Tolkien</td>
          <td>1</td>
        </tr>
      </table>
    '''
    parsed = recipe_parser.parse_recipe_html(top_novels, html)

    self.assertEqual('r/Fantasy Top Novels 2025', parsed['name'])
    self.assertEqual('Middle-Earth Universe', parsed['entries'][0]['title'])
    self.assertEqual(
      'https://www.goodreads.com/series/66175-middle-earth',
      parsed['entries'][0]['source_url'])

    standalone = recipe_parser.parse_recipe_html(standalone_recipe, '''
      <table>
        <tr><th>Rank</th><th>Title</th><th>Author</th><th>Votes</th><th>Rank change</th></tr>
        <tr>
          <td>2</td>
          <td><a href="https://www.goodreads.com/book/show/5907.The_Hobbit">The Hobbit</a></td>
          <td>J.R.R. Tolkien</td>
          <td>65</td>
          <td>+1</td>
        </tr>
      </table>
    ''')

    self.assertEqual('r/Fantasy Top Standalone Novels 2024', standalone['name'])
    self.assertEqual('The Hobbit', standalone['entries'][0]['title'])
    self.assertEqual('J.R.R. Tolkien', standalone['entries'][0]['author'])
    self.assertEqual('65', standalone['entries'][0]['votes'])

    self_published = recipe_parser.parse_recipe_html(self_published_recipe, '''
      <table>
        <tr>
          <th>Rank / Change</th><th>Book/series</th><th>Author</th>
          <th>Number of Votes</th><th>GR ratings (the first book in the series)</th>
        </tr>
        <tr>
          <td>2 / +1</td>
          <td><a href="https://www.goodreads.com/series/192821-cradle">Cradle</a></td>
          <td>Will Wight</td>
          <td>30</td>
          <td>47 367</td>
        </tr>
      </table>
    ''')

    self.assertEqual('r/Fantasy Top Self-Published Novels 2024', self_published['name'])
    self.assertEqual('2', self_published['entries'][0]['position'])
    self.assertEqual('+1', self_published['entries'][0]['rank_change'])
    self.assertEqual('Cradle', self_published['entries'][0]['title'])
    self.assertEqual('Will Wight', self_published['entries'][0]['author'])
    self.assertEqual('30', self_published['entries'][0]['votes'])

    sword_laser = recipe_parser.parse_recipe_html(sword_laser_recipe, '''
      <table>
        <tr><th>Title</th><th>Author(s)</th><th>Publisher</th><th>Month Read</th><th>Seq</th></tr>
        <tr>
          <td><a href="/wiki/Dungeon_Crawler_Carl">Dungeon Crawler Carl</a></td>
          <td>Matt Dinniman</td>
          <td>Dandy House</td>
          <td>Apr 2025</td>
          <td>190</td>
        </tr>
        <tr>
          <td><a href="/wiki/Finding_Baba_Yaga">Finding Baba Yaga</a> (Alternate Pick)</td>
          <td>Jane Yolen</td>
          <td>Tor Books</td>
          <td>Dec 2020</td>
          <td>139a</td>
        </tr>
      </table>
    ''')

    self.assertEqual('Sword and Laser', sword_laser['name'])
    self.assertEqual('190', sword_laser['entries'][1]['position'])
    self.assertEqual('139.5', sword_laser['entries'][0]['position'])
    self.assertEqual('Finding Baba Yaga', sword_laser['entries'][0]['title'])

  def test_sword_and_laser_march_madness_flag_controls_sublist_fetching(self):
    import recipe_parser

    data = json.loads(
      (ROOT / 'recipes' / 'sword_and_laser_book_list.json').read_text(encoding='utf-8'))
    data['options']['include_march_madness'] = False
    recipe = main.JsonRecipe(data, 'sword_and_laser_book_list.json')
    html = '''
      <table>
        <tr><th>Title</th><th>Author(s)</th><th>Publisher</th><th>Month Read</th><th>Seq</th></tr>
        <tr>
          <td><a href="/wiki/Dungeon_Crawler_Carl">Dungeon Crawler Carl</a></td>
          <td>Matt Dinniman</td>
          <td>Dandy House</td>
          <td>Apr 2025</td>
          <td>190</td>
        </tr>
      </table>
    '''

    parsed = recipe_parser.parse_recipe_html(
      recipe, html,
      fetch_url=lambda _url: self.fail('sublist should not be fetched when flag is false'))

    self.assertEqual(['Dungeon Crawler Carl'], [entry['title'] for entry in parsed['entries']])

  def test_sword_and_laser_march_madness_failed_sublist_is_reported(self):
    import recipe_parser

    data = json.loads(
      (ROOT / 'recipes' / 'sword_and_laser_book_list.json').read_text(encoding='utf-8'))
    data['options']['include_march_madness'] = True
    recipe = main.JsonRecipe(data, 'sword_and_laser_book_list.json')
    failures = []
    html = '''
      <table>
        <tr><th>Title</th><th>Author(s)</th><th>Publisher</th><th>Month Read</th><th>Seq</th></tr>
        <tr>
          <td><a href="/wiki/Dungeon_Crawler_Carl">Dungeon Crawler Carl</a></td>
          <td>Matt Dinniman</td>
          <td>Dandy House</td>
          <td>Apr 2025</td>
          <td>190</td>
        </tr>
      </table>
    '''

    def fail_fetch(url):
      raise RuntimeError('HTTP Error 403: Forbidden')

    parsed = recipe_parser.parse_recipe_html(
      recipe, html,
      fetch_url=fail_fetch,
      fetch_error=lambda url, err, entry: failures.append((url, str(err), entry.get('title', ''))))

    self.assertEqual(['Dungeon Crawler Carl'], [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      [('https://swordandlaser.fandom.com/wiki/Dungeon_Crawler_Carl',
        'HTTP Error 403: Forbidden', 'Dungeon Crawler Carl')],
      failures)
    self.assertEqual(1, len(parsed['march_madness_unavailable_pages']))
    self.assertIn(
      'March Madness details were unavailable for 1 linked page',
      parsed['notes'][1])
    self.assertIn('Dungeon Crawler Carl', parsed['notes'][1])

  def test_sword_and_laser_march_madness_success_adds_nominations(self):
    import recipe_parser

    data = json.loads(
      (ROOT / 'recipes' / 'sword_and_laser_book_list.json').read_text(encoding='utf-8'))
    data['options']['include_march_madness'] = True
    data['options']['fetch_delay_seconds'] = 0
    recipe = main.JsonRecipe(data, 'sword_and_laser_book_list.json')
    html = '''
      <table>
        <tr><th>Title</th><th>Author(s)</th><th>Publisher</th><th>Month Read</th><th>Seq</th></tr>
        <tr>
          <td><a href="/wiki/Dungeon_Crawler_Carl">Dungeon Crawler Carl</a></td>
          <td>Matt Dinniman</td>
          <td>Dandy House</td>
          <td>Apr 2025</td>
          <td>190</td>
        </tr>
      </table>
    '''
    march_html = '''
      How/Why was this book chosen: It won a March Madness style knockout poll.
      Round 1 Match 1
      150  65.8%  Dungeon Crawler Carl  Matt Dinnaman
      78  34.2%  Kill the Farm Boy  Delilah S. Dawson & Kevin Hearne
      228  Total
    '''

    logs = []
    progress = []
    parsed = recipe_parser.parse_recipe_html(
      recipe, html,
      fetch_url=lambda url: march_html if url.endswith('/Dungeon_Crawler_Carl') else self.fail(url),
      log=logs.append,
      progress=lambda done, total, message: progress.append((done, total, message)))

    self.assertEqual(
      ['Dungeon Crawler Carl', 'Dungeon Crawler Carl', 'Kill the Farm Boy'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(['190', '190.01', '190.02'], [entry['position'] for entry in parsed['entries']])
    self.assertEqual(1, parsed['march_madness_summary']['fetched_pages'])
    self.assertEqual(2, parsed['march_madness_summary']['nominations_found'])
    self.assertEqual(2, parsed['march_madness_summary']['entries_added'])
    self.assertIn('March Madness checked 1 of 1 linked pages', parsed['notes'][0])
    self.assertTrue(any('fetch-linked-page' in message for message in logs))
    self.assertTrue(any('finished' in message for message in logs))
    self.assertTrue(any(
      done == 1 and total == 1 and 'Fetching March Madness page 1 of 1' in message
      for done, total, message in progress))

  def test_sword_and_laser_parser_accepts_fandom_api_parse_json(self):
    import recipe_parser

    recipe = main.JsonRecipe(json.loads(
      (ROOT / 'recipes' / 'sword_and_laser_book_list.json').read_text(encoding='utf-8')),
      'sword_and_laser_book_list.json')
    html = json.dumps({
      'parse': {
        'text': {
          '*': '''
            <table>
              <tr><th>Title</th><th>Author(s)</th><th>Publisher</th><th>Month Read</th><th>Seq</th></tr>
              <tr>
                <td><a href="/wiki/Dungeon_Crawler_Carl">Dungeon Crawler Carl</a></td>
                <td>Matt Dinniman</td>
                <td>Dandy House</td>
                <td>Apr 2025</td>
                <td>190</td>
              </tr>
            </table>
          '''
        }
      }
    })

    parsed = recipe_parser.parse_recipe_html(recipe, html)

    self.assertEqual('Dungeon Crawler Carl', parsed['entries'][0]['title'])
    self.assertEqual('190', parsed['entries'][0]['position'])

  def test_fandom_fallback_fetch_urls_use_api_and_export(self):
    core = object.__new__(main.ListSwitchboardCore)
    core.debug_fallback_urls = lambda _url, _urls: None

    urls = core.fallback_fetch_urls('https://swordandlaser.fandom.com/wiki/Book_List')

    self.assertEqual(
      'https://swordandlaser.fandom.com/wiki/Book_List?action=raw',
      urls[0])
    self.assertEqual(
      'https://swordandlaser.fandom.com/api.php?action=parse&page=Book_List&prop=text&format=json',
      urls[1])
    self.assertEqual(
      'https://swordandlaser.fandom.com/wiki/Special:Export/Book_List',
      urls[2])

  def test_fallback_debug_section_can_be_enabled_alone(self):
    self.assertIn(('fallback', 'Fallback activity only'), main.DEBUG_SECTIONS)

  def test_fallback_fetch_urls_logs_only_when_fallback_urls_exist(self):
    core = object.__new__(main.ListSwitchboardCore)
    logged = []
    core.debug_fallback_urls = lambda url, urls: logged.append((url, urls))

    self.assertEqual((), core.fallback_fetch_urls('https://example.com/books'))
    self.assertEqual([], logged)

    urls = core.fallback_fetch_urls('https://swordandlaser.fandom.com/wiki/Book_List')

    self.assertEqual(1, len(logged))
    self.assertEqual('https://swordandlaser.fandom.com/wiki/Book_List', logged[0][0])
    self.assertEqual(urls, logged[0][1])

  def test_sword_and_laser_parser_accepts_raw_wikitext_table(self):
    import recipe_parser

    recipe = main.JsonRecipe(json.loads(
      (ROOT / 'recipes' / 'sword_and_laser_book_list.json').read_text(encoding='utf-8')),
      'sword_and_laser_book_list.json')
    parsed = recipe_parser.parse_recipe_html(recipe, '''
      {| class="wikitable"
      ! Title !! Author(s) !! Publisher !! Month Read !! Seq
      |-
      | [[Dungeon Crawler Carl]] || [https://example.com Matt Dinniman] || Dandy House || Apr 2025 || 190
      |}
    ''')

    self.assertEqual('Dungeon Crawler Carl', parsed['entries'][0]['title'])
    self.assertEqual('Matt Dinniman', parsed['entries'][0]['author'])
    self.assertEqual('190', parsed['entries'][0]['position'])
    self.assertEqual(
      'https://swordandlaser.fandom.com/wiki/Dungeon_Crawler_Carl',
      parsed['entries'][0]['source_url'])

  def test_sword_and_laser_march_madness_parser_numbers_nominations(self):
    import recipe_parser
    from bs4 import BeautifulSoup

    soup = BeautifulSoup('''
      How/Why was this book chosen: It won a March Madness style knockout poll.
      Round 1 Match 1
      150  65.8%  Dungeon Crawler Carl  Matt Dinnaman
      78  34.2%  Kill the Farm Boy  Delilah S. Dawson & Kevin Hearne
      228  Total
      Match 2
      86  40%  She Who Became the Sun  Shelley Parker-Chan
      129  60%  The Adventures of Amina-al-Sirafi  Shannon Chakraborty
      Round 2 Match 1
      142  56.1%  Dungeon Crawler Carl  Matt Dinnaman
    ''', 'html.parser')

    nominations = recipe_parser.parse_sword_and_laser_march_page(
      soup, {'position': '190', 'title': 'Dungeon Crawler Carl', 'author': 'Matt Dinniman'})

    self.assertEqual(
      [('190.01', 'Dungeon Crawler Carl'), ('190.02', 'Kill the Farm Boy'),
       ('190.03', 'She Who Became the Sun'), ('190.04', 'The Adventures of Amina-al-Sirafi')],
      [(entry['position'], entry['title']) for entry in nominations])

  def test_recipe_folder_contains_only_json_files(self):
    recipe_files = [path.name for path in (ROOT / 'recipes').iterdir() if path.is_file()]

    self.assertTrue(recipe_files)
    self.assertTrue(all(path.endswith('.json') for path in recipe_files))

  def test_available_import_recipes_are_loaded_from_json_folder(self):
    core = object.__new__(main.ListSwitchboardCore)
    core.debug_log = lambda *_args, **_kwargs: None

    names = [recipe.NAME for recipe in core.available_import_recipes()]

    self.assertEqual([
      'r/Fantasy Top Novels 2025',
      'r/Fantasy Top Standalone Novels 2024',
      'r/Fantasy Top Self-Published Novels 2024',
      'Sword and Laser',
    ], names)

  def test_core_can_discover_recipes_before_gui_current_db_exists(self):
    class StartupGui:
      pass

    core = main.ListSwitchboardCore(StartupGui(), lambda: None)
    names = [recipe.NAME for recipe in core.available_import_recipes()]

    self.assertIn('r/Fantasy Top Novels 2025', names)

  def test_recipe_sources_can_load_from_calibre_plugin_resources(self):
    class PluginBase:
      def load_resources(self, names):
        self.names = names
        return {
          'recipes/sword_and_laser_book_list.json': (
            ROOT / 'recipes' / 'sword_and_laser_book_list.json').read_bytes()
        }

    core = object.__new__(main.ListSwitchboardCore)
    plugin_base = PluginBase()
    core.plugin_base = plugin_base

    sources = core.calibre_recipe_json_sources()

    self.assertEqual(main.RECIPE_RESOURCE_NAMES, plugin_base.names)
    self.assertEqual('sword_and_laser_book_list.json', sources[0][0])
    self.assertIn('"Sword and Laser"', sources[0][1])

  def test_goodreads_series_source_matches_relaxed_local_series_name(self):
    core = object.__new__(main.ListSwitchboardCore)
    core.debug_log = lambda _message, section='general': None
    core.fetch_goodreads_source_data = lambda _url: {
      'series_names': ['Middle Earth Series'],
      'books': [
        {'title': 'The Hobbit', 'author': 'J.R.R. Tolkien'},
        {'title': 'The Fellowship of the Ring', 'author': 'J.R.R. Tolkien'},
      ],
    }

    titles = {
      2456: 'The Fellowship of the Ring',
      2457: 'The Hobbit',
      2458: 'The Return of the King',
      2459: 'The Two Towers',
    }
    series = {book_id: 'Middle-earth' for book_id in titles}
    authors = {book_id: ['J. R. R. Tolkien'] for book_id in titles}
    candidates = core.goodreads_source_recovery_candidates(
      {
        'title': 'Middle-Earth Universe',
        'author': 'J.R.R. Tolkien',
        'source_url': 'https://www.goodreads.com/series/66175-middle-earth',
      },
      titles, series, authors, build_lookup(titles), build_lookup(series))

    self.assertEqual([2456, 2457, 2458, 2459], candidates)

  def test_import_writes_previous_active_to_stored_field(self):
    core = object.__new__(main.ListSwitchboardCore)
    captured = {}
    core.current_active = lambda: 'Sword and Laser'
    core.update_import_progress = lambda *args, **kwargs: None
    core.match_imported_entries = lambda _entries: ({101: '1'}, [])
    core.debug_import_target = lambda _list_name, _active: None
    core.debug_import_summary = lambda _matched, _missing, _entries: None
    core.active_to_stored_updates = lambda _active: ({201: ''}, {201: 'Sword and Laser [24]'})
    core.active_list_value_matches = lambda _book_id, _list_name, _position: False
    core.write_fields = lambda **kwargs: captured.update(kwargs)
    core.status_message = lambda _message: None
    core.show_import_report = lambda *_args, **_kwargs: None
    core.import_progress = None

    core.import_recipe_result({
      'name': 'r/Fantasy Top Novels 2025',
      'entries': [{'position': '1', 'title': 'Middle-Earth Universe'}],
    })

    self.assertEqual({201: 'Sword and Laser [24]'}, captured.get('stored_updates'))
    self.assertEqual(
      {201: '', 101: 'r/Fantasy Top Novels 2025'},
      captured.get('active_updates'))
    self.assertEqual({101: 1.0}, captured.get('active_index_updates'))

  def test_import_skips_unchanged_matched_book_write(self):
    core = object.__new__(main.ListSwitchboardCore)
    captured = {}
    core.current_active = lambda: 'r/Fantasy Top Novels 2025'
    core.update_import_progress = lambda *args, **kwargs: None
    core.update_import_match_progress = lambda *args, **kwargs: None
    core.match_imported_entries = lambda _entries: ({101: '1', 102: '2'}, [])
    core.debug_import_target = lambda _list_name, _active: None
    core.debug_import_summary = lambda _matched, _missing, _entries: None
    core.active_list_value_matches = lambda book_id, _list_name, _position: book_id == 101
    core.write_fields = lambda **kwargs: captured.update(kwargs)
    core.status_message = lambda _message: None
    core.show_import_report = lambda *_args, **_kwargs: None
    core.import_progress = None

    core.import_recipe_result({
      'name': 'r/Fantasy Top Novels 2025',
      'entries': [{'position': '1', 'title': 'Middle-Earth Universe'}],
    })

    self.assertEqual({102: 'r/Fantasy Top Novels 2025'}, captured.get('active_updates'))
    self.assertEqual({102: 2.0}, captured.get('active_index_updates'))

  def test_import_progress_splits_matching_and_writes(self):
    core = object.__new__(main.ListSwitchboardCore)
    values = []
    core.update_import_progress = lambda value=None, message=None: values.append(value)

    core.update_import_match_progress(1, 2, 'Matching')
    core.update_import_write_progress(1, 2, 'Writing')
    core.update_import_write_progress(2, 2, 'Writing')

    self.assertEqual([250, 750, 1000], values)

  def test_import_progress_start_shows_matching_at_zero(self):
    core = object.__new__(main.ListSwitchboardCore)
    values = []
    core.update_import_progress = lambda value=None, message=None: values.append((value, message))

    core.show_import_progress_start({'entries': [{}, {}, {}]})

    self.assertEqual([(0, 'Matching 0 of 3 recipe entries...')], values)

  def test_operation_write_progress_uses_full_progress_range(self):
    core = object.__new__(main.ListSwitchboardCore)
    values = []
    core.update_import_progress = lambda value=None, message=None: values.append(value)

    core.update_operation_write_progress(1, 2, 'Writing')
    core.update_operation_write_progress(2, 2, 'Writing')

    self.assertEqual([500, 1000], values)

  def test_import_match_step_progress_advances_within_entry(self):
    core = object.__new__(main.ListSwitchboardCore)
    values = []
    core.update_import_progress = lambda value=None, message=None: values.append(value)

    core.update_import_match_step_progress(2, 4, 0.5, 'Checking Goodreads')

    self.assertEqual([188], values)

  def test_close_import_progress_closes_active_progress_dialog(self):
    core = object.__new__(main.ListSwitchboardCore)
    closed = []

    class FakeProgress:

      def close(self):
        closed.append(True)

    core.import_progress = FakeProgress()

    core.close_import_progress()

    self.assertEqual([True], closed)
    self.assertIsNone(core.import_progress)

  def test_parse_stored_lists_accepts_calibre_multiple_values(self):
    self.assertEqual(
      ['Sword and Laser [24]', 'r/Fantasy Top Novels 2025 [1]'],
      main.parse_stored_lists((' Sword and Laser [24] ', 'r/Fantasy Top Novels 2025 [1]')))

  def test_stored_write_updates_converts_to_multiple_values(self):
    core = object.__new__(main.ListSwitchboardCore)
    core.stored_field_is_multiple = lambda: True

    self.assertEqual(
      {42: ('Sword and Laser [24]', 'Discworld [8]')},
      core.stored_write_updates({42: 'Sword and Laser [24], Discworld [8]'}))

  def test_write_fields_skips_unchanged_active_values(self):
    core = object.__new__(main.ListSwitchboardCore)
    set_field_calls = []
    refreshed = []
    main.prefs['active_list_field'] = '#reading_series'
    core.active_list_value_matches = lambda _book_id, _value, _position: True
    core.active_field_is_series = lambda: False
    core.refresh_books = lambda ids: refreshed.append(ids)
    core.debug_writes_finished = lambda *_args: None

    class FakeApi:

      def set_field(self, field, updates):
        set_field_calls.append((field, updates))

    class FakeDb:
      new_api = FakeApi()

    core.db = FakeDb()

    core.write_fields(active_updates={7: 'The Wheel of Time'})

    self.assertEqual([], set_field_calls)
    self.assertEqual([set()], refreshed)

  def test_match_keys_include_calibre_article_normalized_title(self):
    self.assertIn('hobbit', main.match_keys('The Hobbit'))
    self.assertIn('memory called empire', main.match_keys('A Memory Called Empire'))
    self.assertIn('wheel of time', main.match_keys('The Wheel of Time'))

  def test_series_match_keys_ignore_leading_articles_and_series_suffixes(self):
    self.assertIn('wheel of time', main.series_match_keys('The Wheel of Time Series'))

  def test_match_keys_include_relaxed_initial_removed_key(self):
    self.assertIn(
      'the empire trilogy by raymond feist',
      main.match_keys('The Empire Trilogy by Raymond E. Feist'))

  def test_match_keys_skip_relaxed_initial_key_for_short_values(self):
    self.assertNotIn('bc', main.match_keys('A B.C.'))

  def test_import_entry_keys_ignore_leading_articles(self):
    core = object.__new__(main.ListSwitchboardCore)

    self.assertIn('dresden files', core.import_entry_keys({'title': 'The Dresden Files'}))

  def test_normal_import_matches_all_local_series_books_ignoring_leading_article(self):
    core = object.__new__(main.ListSwitchboardCore)
    core.update_import_match_progress = lambda *args, **kwargs: None
    core.update_import_match_step_progress = lambda *args, **kwargs: None
    core.import_entry_keys = main.ListSwitchboardCore.import_entry_keys.__get__(core)
    core.author_matches = main.ListSwitchboardCore.author_matches.__get__(core)
    core.all_local_series_values = lambda _ids: {
      7: ['The Wheel of Time'],
      8: ['The Wheel of Time'],
      9: ['The Wheel of Time'],
    }
    core.debug_import_match_entry = lambda *_args: None
    core.debug_import_empty_entry = lambda *_args: None
    core.debug_import_goodreads_candidates = lambda *_args: None
    core.debug_import_matched_book = lambda *_args: None
    core.goodreads_source_recovery_candidates = lambda *_args: self.fail(
      'direct series match should not need Goodreads recovery')

    class FakeApi:

      def all_field_for(self, field, ids, default_value=''):
        if field == 'title':
          return {
            7: 'The Eye of the World',
            8: 'The Great Hunt',
            9: 'The Dragon Reborn',
          }
        if field == 'authors':
          return {
            7: ['Robert Jordan'],
            8: ['Robert Jordan'],
            9: ['Robert Jordan'],
          }
        return {book_id: default_value for book_id in ids}

    class FakeDb:
      new_api = FakeApi()

    core.db = FakeDb()
    core.all_book_ids = lambda: [7, 8, 9]

    matched, missing = core.match_imported_entries([
      {'position': '7', 'title': 'Wheel of Time', 'author': 'Robert Jordan'},
    ])

    self.assertEqual({7: '7', 8: '7', 9: '7'}, matched)
    self.assertEqual([], missing)

  def test_goodreads_source_series_matches_without_article_and_series_suffix(self):
    core = object.__new__(main.ListSwitchboardCore)
    core.fetch_goodreads_source_data = lambda _url: {
      'series_names': ['The Wheel of Time Series'],
      'books': [],
    }
    core.debug_import_goodreads_source_candidates = lambda *_args: None

    candidates = core.goodreads_source_recovery_candidates(
      {
        'title': 'Wheel of Time',
        'author': 'Robert Jordan',
        'source_url': 'https://www.goodreads.com/series/41526-the-wheel-of-time',
      },
      {7: 'The Eye of the World'},
      {7: ['The Wheel of Time']},
      {7: ['Robert Jordan']},
      {},
      build_lookup({7: 'The Wheel of Time'}))

    self.assertEqual([7], candidates)

  def test_local_series_fields_use_configured_similar_series_key(self):
    core = object.__new__(main.ListSwitchboardCore)

    class FakePrefs:

      def get(self, key):
        return 'my_series_group' if key == 'similar_series_search_key' else None

    class FakeFieldMetadata:

      def search_term_to_field_key(self, search_term):
        if search_term == 'my_series_group':
          return ['series', '#subseries']
        if search_term == 'series':
          return 'series'
        return None

    class FakeDb:
      prefs = FakePrefs()
      field_metadata = FakeFieldMetadata()

    core.db = FakeDb()

    self.assertEqual(['series', '#subseries'], core.local_series_fields())

  def test_normal_import_matching_does_not_use_deep_goodreads_fallback(self):
    core = object.__new__(main.ListSwitchboardCore)
    core.update_import_match_progress = lambda *args, **kwargs: None
    core.update_import_match_step_progress = lambda *args, **kwargs: None
    core.import_entry_keys = main.ListSwitchboardCore.import_entry_keys.__get__(core)
    core.debug_import_match_entry = lambda *_args: None
    core.debug_import_empty_entry = lambda *_args: None
    core.debug_import_goodreads_candidates = lambda *_args: None
    core.debug_import_matched_book = lambda *_args: None
    core.goodreads_source_recovery_candidates = lambda *_args: []
    core.goodreads_recovery_candidates = lambda *_args, **_kwargs: self.fail(
      'normal import should not run deep Goodreads fallback')

    class FakeApi:

      def all_field_for(self, field, ids, default_value=''):
        return {book_id: '' for book_id in ids}

    class FakeDb:
      new_api = FakeApi()

    core.db = FakeDb()
    core.all_book_ids = lambda: [1, 2]

    matched, missing = core.match_imported_entries([
      {'position': '1', 'title': 'Missing Series', 'author': 'Nobody'},
    ])

    self.assertEqual({}, matched)
    self.assertEqual('Missing Series', missing[0]['title'])

  def test_deep_recovery_uses_goodreads_fallback(self):
    core = object.__new__(main.ListSwitchboardCore)
    core.update_import_match_progress = lambda *args, **kwargs: None
    core.update_import_match_step_progress = lambda *args, **kwargs: None
    core.debug_import_goodreads_candidates = lambda *_args: None
    core.debug_import_matched_book = lambda *_args: None
    core.goodreads_recovery_candidates = lambda *_args, **_kwargs: [2]

    class FakeApi:

      def all_field_for(self, field, ids, default_value=''):
        if field == 'title':
          return {2: 'Matched Book'}
        if field == 'series':
          return {2: ''}
        if field == 'authors':
          return {2: ['Nobody']}
        return {}

    class FakeDb:
      new_api = FakeApi()

    core.db = FakeDb()
    core.all_book_ids = lambda: [2]

    matched, missing = core.match_deep_recovery_entries([
      {'position': '7', 'title': 'Missing Series', 'author': 'Nobody'},
    ])

    self.assertEqual({2: '7'}, matched)
    self.assertEqual([], missing)

  def test_deep_recovery_skips_books_matched_by_shallow_search(self):
    core = object.__new__(main.ListSwitchboardCore)
    looked_up = []
    core.goodreads_source_recovery_candidates = lambda *_args: []
    core.author_matches = main.ListSwitchboardCore.author_matches.__get__(core)

    def goodreads_id_for_book(book_id):
      looked_up.append(book_id)
      return str(book_id)

    core.goodreads_id_for_book = goodreads_id_for_book
    core.fetch_goodreads_series_names = lambda _goodreads_id: ['Missing Series']

    candidates = core.goodreads_recovery_candidates(
      {'position': '1', 'title': 'Missing Series', 'author': 'Same Author'},
      [1, 2],
      {1: 'Already Matched', 2: 'Recovery Candidate'},
      {1: ['Already Matched Series'], 2: ['Other Series']},
      {1: ['Same Author'], 2: ['Same Author']},
      {},
      {},
      excluded_book_ids={1})

    self.assertEqual([2], looked_up)
    self.assertEqual([2], candidates)


if __name__ == '__main__':
  unittest.main()
