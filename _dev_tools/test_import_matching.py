#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

import json
import sys
import types
import unittest
from copy import deepcopy
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
    'QApplication', 'QButtonGroup', 'QCheckBox', 'QComboBox', 'QDialog',
    'QDialogButtonBox', 'QGridLayout', 'QGroupBox', 'QHBoxLayout',
    'QHeaderView', 'QInputDialog', 'QLabel', 'QLineEdit', 'QListWidget',
    'QMessageBox', 'QProgressDialog', 'QPushButton', 'QRadioButton',
    'QSizePolicy', 'QSpinBox', 'QTableWidget', 'QTableWidgetItem',
    'QVBoxLayout'):
  setattr(qt_core, name, Dummy)
qt_core.Qt = types.SimpleNamespace(
  AlignmentFlag=types.SimpleNamespace(AlignLeft=0))
sys.modules.setdefault('qt', qt)
sys.modules.setdefault('qt.core', qt_core)

calibre = types.ModuleType('calibre')
calibre_ebooks = types.ModuleType('calibre.ebooks')
calibre_ebooks_metadata = types.ModuleType('calibre.ebooks.metadata')
calibre_ebooks_metadata.title_sort = lambda value: (
  value[4:] + ', The' if value.startswith('The ') else value)
calibre_gui2 = types.ModuleType('calibre.gui2')
calibre_gui2.error_dialog = Dummy()
calibre_gui2.question_dialog = Dummy()
sys.modules.setdefault('calibre', calibre)
sys.modules.setdefault('calibre.ebooks', calibre_ebooks)
sys.modules.setdefault('calibre.ebooks.metadata', calibre_ebooks_metadata)
sys.modules.setdefault('calibre.gui2', calibre_gui2)

plugin_package = types.ModuleType('calibre_plugins')
list_switchboard_package = types.ModuleType('calibre_plugins.list_switchboard')
config_module = types.ModuleType('calibre_plugins.list_switchboard.config')
config_module.prefs = {}
sys.modules.setdefault('calibre_plugins', plugin_package)
sys.modules.setdefault('calibre_plugins.list_switchboard', list_switchboard_package)
sys.modules.setdefault('calibre_plugins.list_switchboard.config', config_module)

import main
import list_state
import dialogs.import_find as import_find_module
import dialogs.import_report as import_report_module
from dialogs.import_find import MatchReviewDialog
from parser.reddit import parse_reddit_results
from parser.sword_and_laser import (
  parse_sword_and_laser_book_list,
  parse_sword_and_laser_march_page,
)
from dialogs.import_report import ImportReportDialog
from url_fetcher.r_fantasy_top_novels_2025 import UrlFetcherRFantasyTopNovels2025
from url_fetcher.r_fantasy_top_self_published_novels_2024 import (
  UrlFetcherRFantasyTopSelfPublishedNovels2024,
)
from url_fetcher.r_fantasy_top_standalone_novels_2024 import (
  UrlFetcherRFantasyTopStandaloneNovels2024,
)
from url_fetcher.sword_and_laser import UrlFetcherSwordAndLaser

SCRAPS_ISFDB_ROOT = ROOT / '_dev_tools' / 'Scraps Cache' / 'isfdb'


def parser_source(fetcher, **options):
  return types.SimpleNamespace(
    NAME=fetcher.NAME,
    URL=fetcher.URL,
    schemas=fetcher.schemas,
    options={**deepcopy(fetcher.options), **options})


def build_lookup(values):
  lookup = {}
  for book_id, value in values.items():
    for key in main.match_keys(value):
      lookup.setdefault(key, []).append(book_id)
  return lookup


def load_text(path):
  return Path(path).read_text(encoding='utf-8', errors='replace')


def isfdb_folder_fetch(folder_name):
  folder = SCRAPS_ISFDB_ROOT / folder_name
  source_urls = json.loads((folder / 'source_urls.json').read_text(encoding='utf-8'))
  by_url = {
    url: folder / filename
    for filename, url in source_urls.items()
  }

  def fetch(url):
    return load_text(by_url[url])

  return folder, source_urls, fetch


class ImportMatchingTest(unittest.TestCase):

  def test_recipe_preserves_goodreads_source_url(self):
    try:
      import bs4  # noqa: F401
    except ModuleNotFoundError as err:
      if err.name == 'bs4':
        self.skipTest('BeautifulSoup is not available in this Python environment')
      raise

    top_novels = UrlFetcherRFantasyTopNovels2025()
    standalone_recipe = UrlFetcherRFantasyTopStandaloneNovels2024()
    self_published_recipe = UrlFetcherRFantasyTopSelfPublishedNovels2024()
    sword_laser_recipe = parser_source(UrlFetcherSwordAndLaser(), include_march_madness=False)
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
    parsed = parse_reddit_results(html, top_novels.NAME, top_novels.URL, top_novels.schemas)

    self.assertEqual('r/Fantasy Top Novels 2025', parsed['name'])
    self.assertEqual('Middle-Earth Universe', parsed['entries'][0]['title'])
    self.assertEqual(
      'https://www.goodreads.com/series/66175-middle-earth',
      parsed['entries'][0]['source_url'])

    standalone = parse_reddit_results(
      '''
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
    ''',
      standalone_recipe.NAME, standalone_recipe.URL, standalone_recipe.schemas)

    self.assertEqual('r/Fantasy Top Standalone Novels 2024', standalone['name'])
    self.assertEqual('The Hobbit', standalone['entries'][0]['title'])
    self.assertEqual('J.R.R. Tolkien', standalone['entries'][0]['author'])
    self.assertEqual('65', standalone['entries'][0]['votes'])

    self_published = parse_reddit_results(
      '''
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
    ''',
      self_published_recipe.NAME, self_published_recipe.URL, self_published_recipe.schemas)

    self.assertEqual('r/Fantasy Top Self-Published Novels 2024', self_published['name'])
    self.assertEqual('2', self_published['entries'][0]['position'])
    self.assertEqual('+1', self_published['entries'][0]['rank_change'])
    self.assertEqual('Cradle', self_published['entries'][0]['title'])
    self.assertEqual('Will Wight', self_published['entries'][0]['author'])
    self.assertEqual('30', self_published['entries'][0]['votes'])

    sword_laser = parse_sword_and_laser_book_list(sword_laser_recipe, '''
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
    recipe = parser_source(UrlFetcherSwordAndLaser(), include_march_madness=False)
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

    parsed = parse_sword_and_laser_book_list(
      recipe, html,
      fetch_url=lambda _url: self.fail('sublist should not be fetched when flag is false'))

    self.assertEqual(['Dungeon Crawler Carl'], [entry['title'] for entry in parsed['entries']])

  def test_sword_and_laser_march_madness_failed_sublist_is_reported(self):
    recipe = parser_source(UrlFetcherSwordAndLaser(), include_march_madness=True)
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

    parsed = parse_sword_and_laser_book_list(
      recipe, html,
      fetch_url=fail_fetch,
      fetch_error=lambda url, err, entry: failures.append((url, str(err), entry.get('title', ''))))

    self.assertEqual(['Dungeon Crawler Carl'], [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      [('https://swordandlaser.fandom.com/wiki/Dungeon_Crawler_Carl',
        'All fallback URLs failed for https://swordandlaser.fandom.com/wiki/Dungeon_Crawler_Carl',
        'Dungeon Crawler Carl')],
      failures)
    self.assertEqual(1, len(parsed['march_madness_unavailable_pages']))
    self.assertIn(
      'March Madness details were unavailable for 1 linked page',
      parsed['notes'][1])
    self.assertIn('Dungeon Crawler Carl', parsed['notes'][1])

  def test_sword_and_laser_march_madness_success_adds_nominations(self):
    recipe = parser_source(
      UrlFetcherSwordAndLaser(),
      include_march_madness=True,
      fetch_delay_seconds=0)
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
    parsed = parse_sword_and_laser_book_list(
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
    recipe = parser_source(UrlFetcherSwordAndLaser(), include_march_madness=False)
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

    parsed = parse_sword_and_laser_book_list(recipe, html)

    self.assertEqual('Dungeon Crawler Carl', parsed['entries'][0]['title'])
    self.assertEqual('190', parsed['entries'][0]['position'])

  def test_fandom_fallback_fetch_urls_use_api_and_export(self):
    core = object.__new__(main.ListSwitchboardCore)
    core.debug_fallback_urls = lambda _url, _urls: None

    urls = core.fallback_fetch_urls('https://swordandlaser.fandom.com/wiki/Book_List')

    self.assertEqual(
      'https://swordandlaser.fandom.com/api.php?action=parse&page=Book_List&prop=text&format=json',
      urls[0])
    self.assertEqual(
      'https://swordandlaser.fandom.com/wiki/Book_List',
      urls[1])
    self.assertEqual(
      'https://swordandlaser.fandom.com/wiki/Book_List?action=raw',
      urls[2])
    self.assertEqual(
      'https://swordandlaser.fandom.com/wiki/Special:Export/Book_List',
      urls[3])

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

  def test_fetch_headers_accept_optional_user_agent(self):
    core = object.__new__(main.ListSwitchboardCore)

    self.assertEqual(main.DEFAULT_USER_AGENT, core.fetch_headers()['User-Agent'])
    self.assertEqual(
      'Custom Agent',
      core.fetch_headers(user_agent='Custom Agent')['User-Agent'])

  def test_isfdb_fallback_attempt_passes_user_agent_to_fetch_url(self):
    from url_fetcher.isfdb_fallback import ISFDB_USER_AGENT
    from url_fetcher.locus import UrlFetcherLocusAnnualSFNovel

    fetcher = UrlFetcherLocusAnnualSFNovel()
    attempt = [
      item for item in fetcher.source_attempts()
      if item.label == 'ISFDB'
    ][0]
    calls = []

    def fetch_url(url, user_agent=None):
      calls.append((url, user_agent))
      return ''

    attempt.fetch_url(fetch_url)('https://www.isfdb.org/cgi-bin/awardtype.cgi?28')

    self.assertEqual([
      ('https://www.isfdb.org/cgi-bin/awardtype.cgi?28', ISFDB_USER_AGENT)
    ], calls)

  def test_sword_and_laser_parser_accepts_raw_wikitext_table(self):
    recipe = parser_source(UrlFetcherSwordAndLaser(), include_march_madness=False)
    parsed = parse_sword_and_laser_book_list(recipe, '''
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

    nominations = parse_sword_and_laser_march_page(
      soup, {'position': '190', 'title': 'Dungeon Crawler Carl', 'author': 'Matt Dinniman'})

    self.assertEqual(
      [('190.01', 'Dungeon Crawler Carl'), ('190.02', 'Kill the Farm Boy'),
       ('190.03', 'She Who Became the Sun'), ('190.04', 'The Adventures of Amina-al-Sirafi')],
      [(entry['position'], entry['title']) for entry in nominations])

  def test_legacy_json_recipe_folder_is_removed(self):
    self.assertFalse((ROOT / 'recipes').exists())

  def test_available_import_recipes_are_loaded_from_url_fetcher_folder(self):
    core = object.__new__(main.ListSwitchboardCore)
    core.debug_log = lambda *_args, **_kwargs: None

    names = [recipe.NAME for recipe in core.available_import_recipes()]

    self.assertEqual([
      'r/Fantasy Top Novels 2025',
      'r/Fantasy Top Standalone Novels 2024',
      'r/Fantasy Top Self-Published Novels 2024',
      'Sword and Laser',
    ], names[:4])
    self.assertEqual(179, len(names))
    self.assertIn('Theakston Old Peculier Crime Novel of the Year', names)

  def test_core_can_discover_recipes_before_gui_current_db_exists(self):
    class StartupGui:
      pass

    core = main.ListSwitchboardCore(StartupGui(), lambda: None)
    names = [recipe.NAME for recipe in core.available_import_recipes()]

    self.assertIn('r/Fantasy Top Novels 2025', names)

  def test_builtin_url_fetchers_load_without_plugin_resources(self):
    core = object.__new__(main.ListSwitchboardCore)

    fetchers = core.builtin_url_fetchers()

    source_ids = [fetcher.source_id for fetcher in fetchers]

    self.assertEqual([
      'r_fantasy_top_novels_2025',
      'r_fantasy_top_standalone_novels_2024',
      'r_fantasy_top_self_published_novels_2024',
      'sword_and_laser_book_list',
    ], source_ids[:4])
    self.assertEqual(179, len(source_ids))
    self.assertIn('theakston_old_peculier_crime_novel_of_the_year', source_ids)

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

  def test_active_to_stored_updates_skips_unchanged_stored_rows(self):
    core = object.__new__(main.ListSwitchboardCore)
    main.prefs['active_list_field'] = '#reading_series'
    main.prefs['stored_lists_field'] = '#stored_lists'
    core.ensure_active_list_can_be_stored = lambda _active: None
    core.all_book_ids = lambda: [1, 2, 3]
    active_values = {
      1: 'Sword and Laser',
      2: '',
      3: '',
    }
    stored_values = {
      1: '',
      2: 'Existing List [4]',
      3: 'Sword and Laser [24]',
    }
    core.read_field = lambda field, book_id: (
      active_values[book_id] if field == main.prefs['active_list_field']
      else stored_values[book_id])
    core.stored_entry_for_active = lambda _book_id, active, require_position=False: (
      f'{active} [24]')

    active_updates, stored_updates = core.active_to_stored_updates('Sword and Laser')

    self.assertEqual({1: ''}, active_updates)
    self.assertEqual({1: 'Sword and Laser [24]'}, stored_updates)

  def test_remove_active_list_skips_unchanged_stored_rows(self):
    core = object.__new__(main.ListSwitchboardCore)
    main.prefs['active_list_field'] = '#reading_series'
    main.prefs['stored_lists_field'] = '#stored_lists'
    captured = {}
    core.gui = None
    core.current_active = lambda: 'Current List'
    core.all_book_ids = lambda: [1, 2, 3]
    active_values = {
      1: 'Current List',
      2: '',
      3: '',
    }
    stored_values = {
      1: 'Current List [1], Other List [3]',
      2: 'Other List [4]',
      3: 'Current List [2]',
    }
    core.read_field = lambda field, book_id: (
      active_values[book_id] if field == main.prefs['active_list_field']
      else stored_values[book_id])
    core.write_fields_with_progress = lambda *_args, **kwargs: captured.update(kwargs)
    core.status_message = lambda _message: None

    original_question_dialog = list_state.question_dialog
    try:
      list_state.question_dialog = lambda *_args, **_kwargs: True
      core.remove_active_list()
    finally:
      list_state.question_dialog = original_question_dialog

    self.assertEqual({1: ''}, captured.get('active_updates'))
    self.assertEqual({
      1: 'Other List [3]',
      3: '',
    }, captured.get('stored_updates'))

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

  def test_add_selected_index_updates_use_next_whole_number_after_current_max(self):
    core = object.__new__(main.ListSwitchboardCore)
    main.prefs['active_list_field'] = '#reading_series'
    core.active_series_index_field = lambda: '#reading_series_index'
    core.all_book_ids = lambda: [1, 2, 3, 4, 5]
    active_values = {
      1: 'Current List',
      2: 'Current List',
      3: 'Other List',
      4: '',
      5: '',
    }
    index_values = {
      1: 5,
      2: 33.05,
      3: 99,
    }
    core.read_field = lambda _field, book_id: active_values.get(book_id, '')
    core.read_series_index = lambda _index_field, book_id: index_values.get(book_id)

    self.assertEqual(
      {4: 34.0, 5: 35.0},
      core.added_active_index_updates('Current List', {4: 'Current List', 5: 'Current List'}))

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
  def test_import_matching_prefers_exact_title_over_series_match(self):
    core = object.__new__(main.ListSwitchboardCore)
    core.update_import_match_progress = lambda *args, **kwargs: None
    core.update_import_match_step_progress = lambda *args, **kwargs: None
    core.import_entry_keys = main.ListSwitchboardCore.import_entry_keys.__get__(core)
    core.debug_import_match_entry = lambda *_args: None
    core.debug_import_empty_entry = lambda *_args: None
    core.debug_import_goodreads_candidates = lambda *_args: None
    core.debug_import_matched_book = lambda *_args: None
    core.goodreads_source_recovery_candidates = lambda *_args: []

    class FakeApi:
      def all_field_for(self, field, ids, default_value=''):
        if field == 'title':
          return {1: 'American Gods', 2: 'Anansi Boys'}
        if field == 'series':
          return {1: ['American Gods'], 2: ['American Gods']}
        if field == 'authors':
          return {1: ['Neil Gaiman'], 2: ['Neil Gaiman']}
        return {book_id: default_value for book_id in ids}

    class FakeDb:
      new_api = FakeApi()

    core.db = FakeDb()
    core.all_book_ids = lambda: [1, 2]

    matched, missing = core.match_imported_entries([
      {'position': '1', 'title': 'American Gods', 'author': 'Neil Gaiman'},
    ], match_series=False)

    self.assertEqual({1: '1'}, matched)
    self.assertEqual([], missing)

  def test_find_match_author_ignore_title_indexes_each_calibre_author(self):
    core = object.__new__(main.ListSwitchboardCore)

    class FakeApi:
      def all_field_for(self, field, ids, default_value=''):
        if field == 'title':
          return {
            1: 'The Knight',
            2: 'Orbit 10',
            3: 'Not Wolfe',
          }
        if field == 'authors':
          return {
            1: ['Gene Wolfe'],
            2: ['Damon Knight', 'Gene Wolfe', 'Edward Bryant'],
            3: ['Bob Shaw'],
          }
        return {book_id: default_value for book_id in ids}

    class FakeDb:
      new_api = FakeApi()

    core.db = FakeDb()
    core.all_book_ids = lambda: [1, 2, 3]
    core.all_local_series_values = lambda _ids: {
      1: ['The Book of the New Sun'],
      2: ['Orbit'],
      3: [],
    }

    index = core.find_match_library_index(
      title_mode=main.FIND_MODE_IGNORE,
      author_mode=main.FIND_MODE_SIMILAR)
    candidates = core.find_import_match_candidates_from_index(
      {'title': 'The Shadow of the Torturer', 'author': 'Gene Wolfe'},
      index)

    self.assertEqual([2, 1], [candidate['book_id'] for candidate in candidates])
    self.assertEqual([['Orbit'], ['The Book of the New Sun']], [
      candidate['series'] for candidate in candidates
    ])

  def test_saved_ignored_directive_suppresses_automatic_match(self):
    core = object.__new__(main.ListSwitchboardCore)
    core.update_import_match_progress = lambda *args, **kwargs: None
    core.update_import_match_step_progress = lambda *args, **kwargs: None
    core.import_entry_keys = main.ListSwitchboardCore.import_entry_keys.__get__(core)
    core.debug_import_match_entry = lambda *_args: None
    core.debug_import_match_entry_detail = lambda *_args: None
    core.debug_import_empty_entry = lambda *_args: None
    core.debug_import_goodreads_candidates = lambda *_args: None
    core.debug_import_matched_book = lambda *_args: None
    core.debug_import_match_start = lambda *_args: None
    core.debug_import_saved_override_lookup = lambda *_args: None
    core.debug_import_candidate_rejected = lambda *_args: None
    core.goodreads_source_recovery_candidates = lambda *_args: []
    core.saved_unmatched_overrides = lambda _list_id: {
      'american gods|neil gaiman': {
        'ignored': True,
        'unmatched': True,
        'previous_matched_book_ids': [1],
        'previous_match_source': 'automatic',
      }
    }
    core.saved_match_overrides = lambda _list_id: {}

    class FakeApi:
      def all_field_for(self, field, ids, default_value=''):
        if field == 'title':
          return {1: 'American Gods'}
        if field == 'authors':
          return {1: ['Neil Gaiman']}
        return {book_id: default_value for book_id in ids}

    class FakeDb:
      new_api = FakeApi()

    core.db = FakeDb()
    core.all_book_ids = lambda: [1]
    core.all_local_series_values = lambda _ids: {1: []}

    matched, missing, review_rows = core.match_imported_entries(
      [{'position': '1', 'title': 'American Gods', 'author': 'Neil Gaiman'}],
      list_id='example_list',
      allow_goodreads_recovery=False,
      return_details=True)

    self.assertEqual({}, matched)
    self.assertEqual(['American Gods'], [entry['title'] for entry in missing])
    self.assertEqual(True, review_rows[0]['ignored'])
    self.assertEqual([1], review_rows[0]['previous_book_ids'])
    self.assertEqual('ignored', review_rows[0]['match_source'])

  def build_active_reconciliation_core(self, active_ids=None, active_positions=None):
    core = object.__new__(main.ListSwitchboardCore)
    main.prefs['active_list_field'] = '#reading_series'
    core.active_book_ids_for_list = lambda _list_name: list(active_ids or [])
    core.active_series_index_field = lambda: '#reading_series_index'
    core.read_field = lambda _field, _book_id: 'Example List'
    core.read_position_display = lambda _index_field, book_id, _fallback: (
      str((active_positions or {}).get(book_id, '')), None)

    class FakeApi:
      def all_field_for(self, field, ids, default_value=''):
        if field == 'title':
          return {
            1: 'First Book',
            2: 'Second Book',
            7: 'Moved Book',
            8: 'Unknown Position Book',
            11: 'Dune',
            12: 'Citizen of the Galaxy',
          }
        if field == 'authors':
          return {
            1: ['Author One'],
            2: ['Author Two'],
            7: ['Move Author'],
            8: ['Unknown Author'],
            11: ['Frank Herbert'],
            12: ['Robert A. Heinlein'],
          }
        return {book_id: default_value for book_id in ids}

    class FakeDb:
      new_api = FakeApi()

    core.db = FakeDb()
    return core

  def test_active_reconciliation_deleted_manual_match_becomes_none(self):
    core = self.build_active_reconciliation_core(active_ids=[])
    row = core.import_review_row(
      {'position': '1', 'title': 'First Book', 'author': 'Author One'},
      matched=True,
      book_ids=[1],
      matched_books=[{
        'matched_book_id': 1,
        'matched_title': 'First Book',
        'matched_authors': 'Author One',
      }],
      match_source='saved/manual override')

    rows, notes = core.reconcile_review_rows_with_active_list(
      'Example List', [row], active_name='Example List')

    self.assertEqual([], notes)
    self.assertEqual(rows, [row])
    self.assertEqual(False, row['matched'])
    self.assertEqual(False, row['ignored'])
    self.assertEqual([], row['book_ids'])
    self.assertEqual('never matched', row['match_source'])
    self.assertEqual([1], row['previous_book_ids'])
    self.assertEqual('saved/manual override', row['previous_match_source'])

  def test_active_reconciliation_deleted_automatic_match_is_reinstated(self):
    core = self.build_active_reconciliation_core(active_ids=[])
    row = core.import_review_row(
      {'position': '1', 'title': 'First Book', 'author': 'Author One'},
      matched=True,
      book_ids=[1],
      matched_books=[{
        'matched_book_id': 1,
        'matched_title': 'First Book',
        'matched_authors': 'Author One',
      }],
      match_source='automatic')

    rows, notes = core.reconcile_review_rows_with_active_list(
      'Example List', [row], active_name='Example List')

    self.assertEqual([], notes)
    self.assertEqual(rows, [row])
    self.assertEqual(True, row['matched'])
    self.assertEqual([1], row['book_ids'])
    self.assertEqual('automatic', row['match_source'])
    self.assertEqual([], row['previous_book_ids'])

  def test_active_reconciliation_changed_index_remaps_book(self):
    core = self.build_active_reconciliation_core(active_ids=[7], active_positions={7: '2'})
    first = core.import_review_row(
      {'position': '1', 'title': 'Moved Book', 'author': 'Move Author'},
      matched=True,
      book_ids=[7],
      matched_books=[{
        'matched_book_id': 7,
        'matched_title': 'Moved Book',
        'matched_authors': 'Move Author',
      }],
      match_source='automatic')
    second = core.import_review_row({
      'position': '2',
      'title': 'Second Book',
      'author': 'Author Two',
    })

    rows, notes = core.reconcile_review_rows_with_active_list(
      'Example List', [first, second], active_name='Example List')

    self.assertEqual([], notes)
    self.assertEqual([first, second], rows)
    self.assertEqual(False, first['matched'])
    self.assertEqual([], first['book_ids'])
    self.assertEqual([7], first['previous_book_ids'])
    self.assertEqual(True, second['matched'])
    self.assertEqual([7], second['book_ids'])
    self.assertEqual('active list/manual edit', second['match_source'])

  def test_active_reconciliation_keeps_ignored_without_active_remap(self):
    core = self.build_active_reconciliation_core(active_ids=[])
    row = core.import_review_row(
      {'position': '1', 'title': 'First Book', 'author': 'Author One'},
      match_source='ignored',
      directive={
        'ignored': True,
        'previous_matched_book_ids': [1],
        'previous_match_source': 'automatic',
      })

    core.reconcile_review_rows_with_active_list(
      'Example List', [row], active_name='Example List')

    self.assertEqual(True, row['ignored'])
    self.assertEqual(False, row['matched'])
    self.assertEqual('ignored', row['match_source'])

  def test_active_reconciliation_active_position_does_not_override_ignored_directive(self):
    core = self.build_active_reconciliation_core(active_ids=[1], active_positions={1: '1'})
    row = core.import_review_row(
      {'position': '1', 'title': 'First Book', 'author': 'Author One'},
      match_source='ignored',
      directive={
        'ignored': True,
        'previous_matched_book_ids': [1],
        'previous_match_source': 'automatic',
      })

    core.reconcile_review_rows_with_active_list(
      'Example List', [row], active_name='Example List')

    self.assertEqual(True, row['ignored'])
    self.assertEqual(False, row['matched'])
    self.assertEqual([], row['book_ids'])
    self.assertEqual('ignored', row['match_source'])

  def test_active_reconciliation_stale_active_position_does_not_override_automatic_match(self):
    core = self.build_active_reconciliation_core(active_ids=[12], active_positions={12: '1'})
    dune = core.import_review_row(
      {'position': '1', 'title': 'Dune', 'author': 'Frank Herbert'},
      matched=True,
      book_ids=[11],
      matched_books=[{
        'matched_book_id': 11,
        'matched_title': 'Dune',
        'matched_authors': 'Frank Herbert',
      }],
      match_source='automatic')
    citizen = core.import_review_row(
      {'position': '75', 'title': 'Citizen of the Galaxy', 'author': 'Robert A. Heinlein'},
      matched=True,
      book_ids=[12],
      matched_books=[{
        'matched_book_id': 12,
        'matched_title': 'Citizen of the Galaxy',
        'matched_authors': 'Robert A. Heinlein',
      }],
      match_source='automatic')

    rows, notes = core.reconcile_review_rows_with_active_list(
      'Example List', [dune, citizen], active_name='Example List')

    self.assertEqual([], notes)
    self.assertEqual([dune, citizen], rows)
    self.assertEqual(True, dune['matched'])
    self.assertEqual([11], dune['book_ids'])
    self.assertEqual('automatic', dune['match_source'])
    self.assertEqual(True, citizen['matched'])
    self.assertEqual([12], citizen['book_ids'])
    self.assertEqual('automatic', citizen['match_source'])

  def test_active_reconciliation_reports_active_positions_missing_from_recipe(self):
    core = self.build_active_reconciliation_core(active_ids=[8], active_positions={8: '9'})
    row = core.import_review_row({
      'position': '1',
      'title': 'First Book',
      'author': 'Author One',
    })

    _rows, notes = core.reconcile_review_rows_with_active_list(
      'Example List', [row], active_name='Example List')

    self.assertEqual(
      ['1 current Active List book(s) use positions not found in the imported recipe.'],
      notes)


class ImportReportDialogStateTest(unittest.TestCase):

  class FakeMatchTable:
    def __init__(self, row=0):
      self._row = row
      self.selected = []

    def currentRow(self):
      return self._row

    def setCurrentCell(self, row, _column):
      self._row = row
      self.selected.append(row)

    def setRowCount(self, _count):
      pass

    def setItem(self, _row, _column, _item):
      pass

    def fontMetrics(self):
      class Metrics:
        def horizontalAdvance(self, text):
          return len(str(text))
      return Metrics()

    def setColumnWidth(self, _column, _width):
      pass

  def build_dialog(self, row):
    dialog = object.__new__(ImportReportDialog)
    dialog.match_table = self.FakeMatchTable()
    dialog.visible_rows = [row]
    dialog.review_rows = [row]
    dialog.current_view_mode = lambda: 'All'
    dialog.rows_for_current_view = lambda: list(dialog.review_rows)
    dialog.apply_stable_fixed_column_widths = lambda: None
    dialog.update_toggle_button = lambda *_args: None
    dialog.select_review_row = ImportReportDialog.select_review_row.__get__(dialog)
    dialog.selected_review_row = ImportReportDialog.selected_review_row.__get__(dialog)
    dialog.update_table_for_row = ImportReportDialog.update_table_for_row.__get__(dialog)
    return dialog

  def test_toggle_selected_match_cycles_matched_to_none_ignored_and_back(self):
    row = {
      'matched': True,
      'ignored': False,
      'book_ids': [7],
      'matched_books': [{'matched_book_id': 7, 'matched_title': 'Book', 'matched_authors': 'Author'}],
      'previous_book_ids': [],
      'previous_matched_books': [],
      'previous_match_source': '',
      'match_source': 'manual find',
      'can_toggle_on': True,
    }
    dialog = self.build_dialog(row)

    dialog.toggle_selected_match()

    self.assertEqual(False, row['matched'])
    self.assertEqual(False, row['ignored'])
    self.assertEqual([], row['book_ids'])
    self.assertEqual([7], row['previous_book_ids'])
    self.assertEqual('never matched', row['match_source'])

    dialog.toggle_selected_match()

    self.assertEqual(False, row['matched'])
    self.assertEqual(True, row['ignored'])
    self.assertEqual([], row['book_ids'])
    self.assertEqual([7], row['previous_book_ids'])
    self.assertEqual('ignored', row['match_source'])

    dialog.toggle_selected_match()

    self.assertEqual(True, row['matched'])
    self.assertEqual(False, row['ignored'])
    self.assertEqual([7], row['book_ids'])
    self.assertEqual('manual find', row['match_source'])

  def test_toggle_selected_match_cycles_unmatched_to_ignored_and_back(self):
    row = {
      'matched': False,
      'ignored': False,
      'book_ids': [],
      'matched_books': [],
      'previous_book_ids': [],
      'previous_matched_books': [],
      'previous_match_source': '',
      'match_source': 'never matched',
      'can_toggle_on': True,
    }
    dialog = self.build_dialog(row)

    dialog.toggle_selected_match()
    self.assertEqual(True, row['ignored'])
    self.assertEqual('ignored', row['match_source'])

    dialog.toggle_selected_match()
    self.assertEqual(False, row['ignored'])
    self.assertEqual(False, row['matched'])
    self.assertEqual('never matched', row['match_source'])

  def test_update_table_preserves_selected_row_in_all_view(self):
    first = {'matched': True, 'ignored': False, 'book_ids': [1], 'possible_matches': [], 'imported_position': '1', 'imported_title': 'A', 'imported_author': 'A', 'match_source': 'automatic'}
    second = {'matched': False, 'ignored': False, 'book_ids': [], 'possible_matches': [], 'imported_position': '2', 'imported_title': 'B', 'imported_author': 'B', 'match_source': 'never matched'}
    dialog = object.__new__(ImportReportDialog)
    dialog.match_table = self.FakeMatchTable(row=1)
    dialog.visible_rows = [first, second]
    dialog.review_rows = [first, second]
    dialog.current_view_mode = lambda: 'All'
    dialog.rows_for_current_view = lambda: list(dialog.review_rows)
    dialog.apply_stable_fixed_column_widths = lambda: None
    dialog.update_toggle_button = lambda *_args: None
    dialog.select_review_row = ImportReportDialog.select_review_row.__get__(dialog)
    dialog.selected_review_row = ImportReportDialog.selected_review_row.__get__(dialog)
    dialog.update_table_for_row = ImportReportDialog.update_table_for_row.__get__(dialog)
    dialog.csv_values_for_row = ImportReportDialog.csv_values_for_row.__get__(dialog)

    dialog.update_table_for_row(second)

    self.assertEqual(1, dialog.match_table.currentRow())

  def test_award_filter_winners_only_includes_only_winners(self):
    winner = {'entry': {'result': 'winner'}, 'matched': True}
    nominee = {'entry': {'result': 'nominee'}, 'matched': True}
    no_result = {'entry': {}, 'matched': True}
    dialog = object.__new__(ImportReportDialog)
    dialog.review_rows = [winner, nominee, no_result]
    dialog.current_view_mode = lambda: 'All'
    dialog.current_award_filter_mode = lambda: 'Winners only'

    self.assertEqual([winner], dialog.rows_for_current_view())

  def test_award_filter_nominees_only_includes_non_winners_and_no_result(self):
    winner = {'entry': {'result': 'winner'}, 'matched': True}
    nominee = {'entry': {'result': 'nominee'}, 'matched': True}
    shortlisted = {'entry': {'result': 'shortlisted'}, 'matched': True}
    finalist = {'entry': {'result': 'finalist'}, 'matched': True}
    ranked = {'entry': {'result': 'ranked'}, 'matched': True}
    no_result = {'entry': {}, 'matched': True}
    dialog = object.__new__(ImportReportDialog)
    dialog.review_rows = [winner, nominee, shortlisted, finalist, ranked, no_result]
    dialog.current_view_mode = lambda: 'All'
    dialog.current_award_filter_mode = lambda: 'Nominees only'

    self.assertEqual(
      [nominee, shortlisted, finalist, ranked, no_result],
      dialog.rows_for_current_view())

  def test_award_filter_combines_with_match_view_filter(self):
    matched_winner = {'entry': {'result': 'winner'}, 'matched': True}
    unmatched_winner = {'entry': {'result': 'winner'}, 'matched': False}
    unmatched_nominee = {'entry': {'result': 'nominee'}, 'matched': False}
    dialog = object.__new__(ImportReportDialog)
    dialog.review_rows = [matched_winner, unmatched_winner, unmatched_nominee]
    dialog.current_view_mode = lambda: 'Unmatched'
    dialog.current_award_filter_mode = lambda: 'Winners only'

    self.assertEqual([unmatched_winner], dialog.rows_for_current_view())

  def test_current_view_csv_uses_award_filter(self):
    winner = {
      'entry': {'result': 'winner'},
      'imported_position': '1',
      'imported_title': 'Winner',
      'imported_author': 'Author',
      'book_ids': [7],
      'matched': True,
      'ignored': False,
      'possible_matches': [],
      'match_source': 'automatic',
    }
    nominee = {
      'entry': {'result': 'nominee'},
      'imported_position': '2',
      'imported_title': 'Nominee',
      'imported_author': 'Author',
      'book_ids': [],
      'matched': False,
      'ignored': False,
      'possible_matches': [],
      'match_source': 'never matched',
    }
    dialog = object.__new__(ImportReportDialog)
    dialog.review_rows = [winner, nominee]
    dialog.current_view_mode = lambda: 'All'
    dialog.current_award_filter_mode = lambda: 'Winners only'
    dialog.rows_for_current_view = ImportReportDialog.rows_for_current_view.__get__(dialog)
    dialog.csv_values_for_row = ImportReportDialog.csv_values_for_row.__get__(dialog)

    csv_text = dialog.current_view_csv()

    self.assertIn('Winner', csv_text)
    self.assertNotIn('Nominee', csv_text)

  def test_update_table_preserves_selected_row_with_award_filter(self):
    winner = {
      'entry': {'result': 'winner'},
      'matched': True,
      'ignored': False,
      'book_ids': [1],
      'possible_matches': [],
      'imported_position': '1',
      'imported_title': 'Winner',
      'imported_author': 'A',
      'match_source': 'automatic',
    }
    nominee = {
      'entry': {'result': 'nominee'},
      'matched': False,
      'ignored': False,
      'book_ids': [],
      'possible_matches': [],
      'imported_position': '2',
      'imported_title': 'Nominee',
      'imported_author': 'B',
      'match_source': 'never matched',
    }
    dialog = object.__new__(ImportReportDialog)
    dialog.match_table = self.FakeMatchTable(row=1)
    dialog.visible_rows = [winner, nominee]
    dialog.review_rows = [winner, nominee]
    dialog.current_view_mode = lambda: 'All'
    dialog.current_award_filter_mode = lambda: 'Nominees only'
    dialog.apply_stable_fixed_column_widths = lambda: None
    dialog.update_toggle_button = lambda *_args: None
    dialog.select_review_row = ImportReportDialog.select_review_row.__get__(dialog)
    dialog.selected_review_row = ImportReportDialog.selected_review_row.__get__(dialog)
    dialog.rows_for_current_view = ImportReportDialog.rows_for_current_view.__get__(dialog)
    dialog.update_table_for_row = ImportReportDialog.update_table_for_row.__get__(dialog)
    dialog.csv_values_for_row = ImportReportDialog.csv_values_for_row.__get__(dialog)

    dialog.update_table_for_row(nominee)

    self.assertEqual(0, dialog.match_table.currentRow())

  def test_csv_values_show_ignored_in_match_column(self):
    dialog = object.__new__(ImportReportDialog)

    values = dialog.csv_values_for_row({
      'imported_position': '1',
      'imported_title': 'Book',
      'imported_author': 'Author',
      'book_ids': [],
      'matched': False,
      'ignored': True,
      'possible_matches': [],
      'match_source': 'ignored',
    })

    self.assertEqual('Ignored', values[4])
    self.assertEqual('Ignored', values[5])

  def test_apply_manual_find_match_uses_callback_source(self):
    row = {
      'matched': False,
      'ignored': False,
      'book_ids': [],
      'matched_books': [],
      'previous_book_ids': [],
      'previous_matched_books': [],
      'previous_match_source': '',
      'match_source': 'never matched',
      'can_toggle_on': True,
    }
    dialog = object.__new__(ImportReportDialog)
    dialog.selected_match_source_callback = lambda _row, _candidate: 'automatic'

    dialog.apply_manual_find_match(row, {
      'book_id': 7,
      'title': 'Book',
      'authors': 'Author',
    })

    self.assertEqual('automatic', row['match_source'])
    self.assertEqual('automatic', row['previous_match_source'])

  def test_apply_manual_find_match_keeps_multiple_selected_books_on_same_position(self):
    row = {
      'matched': False,
      'ignored': False,
      'book_ids': [],
      'matched_books': [],
      'previous_book_ids': [],
      'previous_matched_books': [],
      'previous_match_source': '',
      'match_source': 'never matched',
      'can_toggle_on': True,
    }
    dialog = object.__new__(ImportReportDialog)
    dialog.selected_match_source_callback = lambda _row, _candidate: self.fail(
      'multi-selection should stay a manual find override')

    dialog.apply_manual_find_match(row, [
      {
        'book_id': 7,
        'title': 'Book volume 1',
        'authors': 'Author',
      },
      {
        'matched_book_id': 8,
        'matched_title': 'Book volume 2',
        'matched_authors': 'Author',
      },
    ])

    self.assertEqual(True, row['matched'])
    self.assertEqual([7, 8], row['book_ids'])
    self.assertEqual([7, 8], row['previous_book_ids'])
    self.assertEqual(
      [(7, 'Book volume 1'), (8, 'Book volume 2')],
      [(book['matched_book_id'], book['matched_title'])
       for book in row['matched_books']])
    self.assertEqual('manual find', row['match_source'])

  def test_apply_ignore_match_marks_row_ignored(self):
    row = {
      'matched': False,
      'ignored': False,
      'book_ids': [],
      'matched_books': [],
      'previous_book_ids': [],
      'previous_matched_books': [],
      'previous_match_source': '',
      'match_source': 'never matched',
      'can_toggle_on': True,
    }
    dialog = object.__new__(ImportReportDialog)

    dialog.apply_ignore_match(row)

    self.assertEqual(False, row['matched'])
    self.assertEqual(True, row['ignored'])
    self.assertEqual([], row['book_ids'])
    self.assertEqual([], row['matched_books'])
    self.assertEqual('ignored', row['match_source'])

  def test_guided_candidate_review_reuses_one_dialog_for_next_row(self):
    first = {
      'imported_position': '1',
      'imported_title': 'First',
      'imported_author': 'Author',
      'matched': False,
      'possible_matches': [{'book_id': 1, 'title': 'First match'}],
    }
    second = {
      'imported_position': '2',
      'imported_title': 'Second',
      'imported_author': 'Author',
      'matched': False,
      'possible_matches': [{'book_id': 2, 'title': 'Second match'}],
    }
    parent = object.__new__(ImportReportDialog)
    parent.review_rows = [first, second]
    parent.visible_rows = [first, second]
    parent.select_review_row = lambda row: None
    parent.update_table_for_row = lambda row: None
    parent.show_find_notice = lambda _message: None
    parent.apply_manual_find_match = ImportReportDialog.apply_manual_find_match.__get__(parent)
    parent.candidate_row_from = ImportReportDialog.candidate_row_from.__get__(parent)
    parent.selected_match_source_callback = None
    parent.view_book_callback = None
    dialogs = []

    class FakeGuidedDialog:
      def __init__(
          self, _parent, review_row, view_book_callback=None,
          match_callback=None, ignore_callback=None, previous_callback=None,
          next_callback=None):
        self.review_rows = [review_row]
        self.match_callback = match_callback
        self.ignore_callback = ignore_callback
        self.previous_callback = previous_callback
        self.next_callback = next_callback
        self.closed = False
        dialogs.append(self)

      def set_review_row(self, review_row):
        self.review_rows.append(review_row)

      def exec(self):
        self.match_callback(self.review_rows[-1]['possible_matches'][0])
        return 1

      def accept_dialog(self):
        self.closed = True

    original = import_report_module.MatchReviewDialog
    import_report_module.MatchReviewDialog = FakeGuidedDialog
    try:
      parent.review_candidate_rows(first)
    finally:
      import_report_module.MatchReviewDialog = original

    self.assertEqual(1, len(dialogs))
    self.assertEqual([first, second], dialogs[0].review_rows)
    self.assertEqual(True, first['matched'])
    self.assertEqual(False, second['matched'])

  def test_guided_candidate_review_ignore_advances_to_next_row(self):
    first = {
      'imported_position': '1',
      'imported_title': 'First',
      'imported_author': 'Author',
      'matched': False,
      'ignored': False,
      'book_ids': [],
      'matched_books': [],
      'possible_matches': [{'book_id': 1, 'title': 'First match'}],
      'match_source': 'never matched',
    }
    second = {
      'imported_position': '2',
      'imported_title': 'Second',
      'imported_author': 'Author',
      'matched': False,
      'ignored': False,
      'possible_matches': [{'book_id': 2, 'title': 'Second match'}],
    }
    parent = object.__new__(ImportReportDialog)
    parent.review_rows = [first, second]
    parent.visible_rows = [first, second]
    parent.select_review_row = lambda row: None
    parent.update_table_for_row = lambda row: None
    parent.show_find_notice = lambda _message: None
    parent.apply_ignore_match = ImportReportDialog.apply_ignore_match.__get__(parent)
    parent.candidate_row_from = ImportReportDialog.candidate_row_from.__get__(parent)
    parent.view_book_callback = None
    dialogs = []

    class FakeGuidedDialog:
      def __init__(
          self, _parent, review_row, view_book_callback=None,
          match_callback=None, ignore_callback=None, previous_callback=None,
          next_callback=None):
        self.review_rows = [review_row]
        self.ignore_callback = ignore_callback
        self.closed = False
        dialogs.append(self)

      def set_review_row(self, review_row):
        self.review_rows.append(review_row)

      def exec(self):
        self.ignore_callback()
        return 1

      def accept_dialog(self):
        self.closed = True

    original = import_report_module.MatchReviewDialog
    import_report_module.MatchReviewDialog = FakeGuidedDialog
    try:
      parent.review_candidate_rows(first)
    finally:
      import_report_module.MatchReviewDialog = original

    self.assertEqual(1, len(dialogs))
    self.assertEqual([first, second], dialogs[0].review_rows)
    self.assertEqual(True, first['ignored'])
    self.assertEqual('ignored', first['match_source'])


class MatchReviewDialogStateTest(unittest.TestCase):

  class FakeLabel:
    def __init__(self):
      self.text = ''

    def setText(self, text):
      self.text = text

  class FakeTable:
    def __init__(self, selected_rows=None):
      self._row = 0
      self.items = {}
      self.widths = [10, 20, 30, 40, 50]
      self.selected_rows = list(selected_rows or [])

    def columnCount(self):
      return len(self.widths)

    def columnWidth(self, column):
      return self.widths[column]

    def setColumnWidth(self, column, width):
      self.widths[column] = width

    def setRowCount(self, count):
      self.row_count = count
      self.widths = [1 for _width in self.widths]

    def setItem(self, row, column, item):
      self.items[(row, column)] = item

    def setCurrentCell(self, row, _column):
      self._row = row

    def currentRow(self):
      return self._row

    def selectionModel(self):
      selected_rows = list(self.selected_rows)

      class Selection:
        def selectedRows(self):
          class Index:
            def __init__(self, row):
              self._row = row

            def row(self):
              return self._row

          return [Index(row) for row in selected_rows]

      return Selection()

  class FakeButton:
    def __init__(self):
      self.enabled = None

    def setEnabled(self, enabled):
      self.enabled = enabled

  def build_dialog(self):
    dialog = object.__new__(MatchReviewDialog)
    dialog.review_label = self.FakeLabel()
    dialog.match_table = self.FakeTable()
    dialog.match_button = self.FakeButton()
    dialog.ignore_button = self.FakeButton()
    dialog.view_book_button = self.FakeButton()
    dialog.view_book_callback = None
    dialog.selected_candidate = None
    dialog.navigation_action = None
    dialog.match_callback = None
    dialog.ignore_callback = None
    dialog.previous_callback = None
    dialog.next_callback = None
    return dialog

  def test_set_review_row_updates_label_and_candidates_on_same_dialog(self):
    dialog = self.build_dialog()
    dialog.set_review_row({
      'imported_title': 'First',
      'imported_author': 'Author One',
      'possible_matches': [{'book_id': 1}],
    }, preserve_column_widths=False)
    original_id = id(dialog)

    dialog.set_review_row({
      'imported_title': 'Second',
      'imported_author': 'Author Two',
      'possible_matches': [{'book_id': 2}],
    }, preserve_column_widths=False)

    self.assertEqual(original_id, id(dialog))
    self.assertEqual('Second\nAuthor Two', dialog.review_label.text)
    self.assertEqual([{'book_id': 2}], dialog.candidates)

  def test_set_review_row_preserves_column_widths(self):
    dialog = self.build_dialog()
    dialog.match_table.widths = [44, 55, 66, 77, 88]

    dialog.set_review_row({
      'imported_title': 'Next',
      'possible_matches': [{'book_id': 1}],
    })

    self.assertEqual([44, 55, 66, 77, 88], dialog.match_table.widths)

  def test_match_review_table_places_series_before_reason(self):
    original_item = import_find_module.QTableWidgetItem

    class FakeItem:
      def __init__(self, text):
        self.text = text

    import_find_module.QTableWidgetItem = FakeItem
    try:
      dialog = self.build_dialog()
      dialog.set_review_row({
        'imported_title': 'Entry',
        'possible_matches': [{
          'book_id': 9,
          'title': 'Candidate',
          'authors': 'Writer',
          'series': ['Series A', 'Series B'],
          'reason': 'title similar',
        }],
      }, preserve_column_widths=False)
    finally:
      import_find_module.QTableWidgetItem = original_item

    self.assertEqual('Series A, Series B', dialog.match_table.items[(0, 3)].text)
    self.assertEqual('title similar', dialog.match_table.items[(0, 4)].text)

  def test_match_selected_one_shot_still_accepts_dialog(self):
    dialog = self.build_dialog()
    accepted = []
    dialog.candidates = [{'book_id': 7}]
    dialog.accept_dialog = lambda: accepted.append(True)

    dialog.accept()

    self.assertEqual([True], accepted)
    self.assertEqual('match', dialog.navigation_action)
    self.assertEqual({'book_id': 7}, dialog.selected_candidate)

  def test_match_selected_callback_does_not_close_dialog(self):
    dialog = self.build_dialog()
    accepted = []
    matched = []
    dialog.candidates = [{'book_id': 7}]
    dialog.match_callback = lambda candidate: matched.append(candidate)
    dialog.accept_dialog = lambda: accepted.append(True)

    dialog.accept()

    self.assertEqual([], accepted)
    self.assertEqual([{'book_id': 7}], matched)

  def test_match_selected_callback_receives_all_selected_rows(self):
    dialog = self.build_dialog()
    matched = []
    dialog.match_table = self.FakeTable(selected_rows=[0, 2])
    dialog.candidates = [{'book_id': 7}, {'book_id': 8}, {'book_id': 9}]
    dialog.match_callback = lambda candidate: matched.append(candidate)

    dialog.accept()

    self.assertEqual([[{'book_id': 7}, {'book_id': 9}]], matched)
    self.assertEqual([{'book_id': 7}, {'book_id': 9}], dialog.selected_candidate)

  def test_ignore_one_shot_accepts_dialog(self):
    dialog = self.build_dialog()
    accepted = []
    dialog.accept_dialog = lambda: accepted.append(True)

    dialog.ignore_current()

    self.assertEqual([True], accepted)
    self.assertEqual('ignore', dialog.navigation_action)
    self.assertIsNone(dialog.selected_candidate)

  def test_ignore_callback_does_not_close_dialog(self):
    dialog = self.build_dialog()
    accepted = []
    ignored = []
    dialog.ignore_callback = lambda: ignored.append(True)
    dialog.accept_dialog = lambda: accepted.append(True)

    dialog.ignore_current()

    self.assertEqual([], accepted)
    self.assertEqual([True], ignored)

  def test_view_selected_book_passes_candidate_id_and_dialog_parent(self):
    dialog = self.build_dialog()
    viewed = []
    dialog.candidates = [{'book_id': 7}]
    dialog.view_book_callback = lambda book_id, parent=None: viewed.append((book_id, parent))

    dialog.view_selected_book()

    self.assertEqual([(7, dialog)], viewed)

  def test_view_selected_book_supports_legacy_one_argument_callback(self):
    dialog = self.build_dialog()
    viewed = []
    dialog.candidates = [{'matched_book_id': 8}]
    dialog.view_book_callback = lambda book_id: viewed.append(book_id)

    dialog.view_selected_book()

    self.assertEqual([8], viewed)


class ImportFlowViewBookTest(unittest.TestCase):

  class FakeFocusParent:
    def __init__(self):
      self.calls = []

    def raise_(self):
      self.calls.append('raise')

    def activateWindow(self):
      self.calls.append('activate')

    def setFocus(self):
      self.calls.append('focus')

  def test_open_book_detail_window_uses_modal_book_info_for_candidate(self):
    core = object.__new__(main.ListSwitchboardCore)
    focus_parent = self.FakeFocusParent()
    captured = {}

    class FakeSignal:
      def connect(self, target):
        captured['connected_cover_signal'] = target

    class FakeBookInfo:
      def __init__(self, *args, **kwargs):
        captured['book_info_args'] = args
        captured['book_info_kwargs'] = kwargs
        self.open_cover_with = FakeSignal()

      def exec(self):
        captured['exec_called'] = True

    class FakeDialogNumbers:
      Locked = 'locked'

    book_info_module = types.ModuleType('calibre.gui2.dialogs.book_info')
    book_info_module.BookInfo = FakeBookInfo
    book_info_module.DialogNumbers = FakeDialogNumbers
    dialogs_module = types.ModuleType('calibre.gui2.dialogs')
    old_dialogs = sys.modules.get('calibre.gui2.dialogs')
    old_book_info = sys.modules.get('calibre.gui2.dialogs.book_info')
    sys.modules['calibre.gui2.dialogs'] = dialogs_module
    sys.modules['calibre.gui2.dialogs.book_info'] = book_info_module

    class FakeLibraryView:
      pass

    class FakeBookDetails:
      handle_click_from_popup = object()

    class FakeGui:
      library_view = FakeLibraryView()
      book_details = FakeBookDetails()
      bd_open_cover_with = object()

    core.gui = FakeGui()
    core.library_index_for_book_id = lambda book_id: f'index-{book_id}'
    try:
      result = core.open_book_detail_window(42, parent=focus_parent)
    finally:
      if old_dialogs is None:
        sys.modules.pop('calibre.gui2.dialogs', None)
      else:
        sys.modules['calibre.gui2.dialogs'] = old_dialogs
      if old_book_info is None:
        sys.modules.pop('calibre.gui2.dialogs.book_info', None)
      else:
        sys.modules['calibre.gui2.dialogs.book_info'] = old_book_info

    self.assertEqual(True, result)
    self.assertEqual(core.gui, captured['book_info_args'][0])
    self.assertEqual(core.gui.library_view, captured['book_info_args'][1])
    self.assertEqual('index-42', captured['book_info_args'][2])
    self.assertEqual(42, captured['book_info_kwargs']['book_id'])
    self.assertEqual('locked', captured['book_info_kwargs']['dialog_number'])
    self.assertEqual(True, captured['exec_called'])
    self.assertEqual(core.gui.bd_open_cover_with, captured['connected_cover_signal'])
    self.assertEqual(['raise', 'activate', 'focus'], focus_parent.calls)

  def test_open_book_detail_window_fallback_uses_keyword_book_id(self):
    core = object.__new__(main.ListSwitchboardCore)
    calls = []

    class FakeAction:
      def show_book_info(self, **kwargs):
        calls.append(kwargs)

    class FakeGui:
      iactions = {'Show Book Details': FakeAction()}

    core.gui = FakeGui()
    core.open_modal_book_info = lambda _book_id, focus_parent=None: False

    self.assertEqual(True, core.open_book_detail_window(42))
    self.assertEqual([{'book_id': 42}], calls)

  def test_open_book_detail_window_does_not_call_view_action_as_book_id_api(self):
    core = object.__new__(main.ListSwitchboardCore)
    viewed = []
    selected = []

    class FakeViewAction:
      def view_book(self, book_id):
        viewed.append(book_id)

    class FakeLibraryView:
      def select_rows(self, book_ids):
        selected.append(book_ids)

    class FakeGui:
      iactions = {'View': FakeViewAction()}
      library_view = FakeLibraryView()

    core.gui = FakeGui()
    core.open_modal_book_info = lambda _book_id, focus_parent=None: False

    self.assertEqual(False, core.open_book_detail_window(42))
    self.assertEqual([], viewed)
    self.assertEqual([[42]], selected)


class AwardParserSmokeTest(unittest.TestCase):

  def test_locus_annual_parser_uses_full_text_when_ranked_blocks_omit_category_headings(self):
    from parser.locus import LocusAnnualAwardsParser

    html = '''
      <div>Sf Novel</div><br>
      <p>Winner: The Man Who Saw Seconds, Alexander Boldizar (Clash)</p>
      <p>Rakesfall, Vajra Chandrasekera (Tordotcom)</p>
      <div>Fantasy Novel</div><br>
      <p>1. Winner: A Sorceress Comes to Call, T. Kingfisher (Tor)</p>
    '''

    overview = '<a href="/Locus_Awards_2024">2024</a>'

    parsed = LocusAnnualAwardsParser().parse(
      overview,
      'https://www.sfadb.com/Locus_Awards',
      'Locus - Annual SF Novel',
      'SF Novel',
      ('novel', 'sf novel'),
      fetch_url=lambda _url: html)

    self.assertEqual(['The Man Who Saw Seconds', 'Rakesfall'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['2024', '2024.01'], [
      entry['position'] for entry in parsed['entries']
    ])

  def test_locus_annual_parser_keeps_ranked_rows_supported(self):
    from parser.locus import LocusAnnualAwardsParser

    html = '''
      Sf Novel
      1. Winner: System Collapse, Martha Wells (Tordotcom)
      2. Starter Villain, John Scalzi (Tor)
      Fantasy Novel
      1. Winner: Witch King, Martha Wells (Tordotcom)
    '''
    overview = '<a href="/Locus_Awards_2024">2024</a>'

    parsed = LocusAnnualAwardsParser().parse(
      overview,
      'https://www.sfadb.com/Locus_Awards',
      'Locus - Annual SF Novel',
      'SF Novel',
      ('novel', 'sf novel'),
      fetch_url=lambda _url: html)

    self.assertEqual(['System Collapse', 'Starter Villain'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['winner', 'nominee'], [
      entry['result'] for entry in parsed['entries']
    ])

  def test_locus_annual_parser_preserves_author_suffixes(self):
    from parser.locus import LocusAnnualAwardsParser

    html = '''
      Sf Novel
      Dawn's Uncertain Light, Neal Barrett, Jr. (NAL Signet)
    '''
    overview = '<a href="/Locus_Awards_1988">1988</a>'

    parsed = LocusAnnualAwardsParser().parse(
      overview,
      'https://www.sfadb.com/Locus_Awards',
      'Locus - Annual SF Novel',
      'SF Novel',
      ('novel', 'sf novel'),
      fetch_url=lambda _url: html)

    self.assertEqual("Dawn's Uncertain Light", parsed['entries'][0]['title'])
    self.assertEqual('Neal Barrett, Jr.', parsed['entries'][0]['author'])

  def test_locus_all_time_parser_keeps_malformed_ol_items_separate(self):
    from parser.locus import LocusAllTimeAwardsParser

    html = '''
      <ol>
      <li value="1">
      <a href="Frank_Herbert_Citations">Frank Herbert</a>, <b>Dune</b>
      (Chilton, 1965)
      <br>
      <li value="2">
      <a href="Orson_Scott_Card_Citations">Orson Scott Card</a>, <b>Ender's Game</b>
      (Tor, 1985)
      <br>
      <li value="7">
      <a href="C_S_Lewis_Citations">C. S. Lewis</a>,
      <b>The Lion, the Witch and the Wardrobe</b>
      (Geoffrey Bles, 1950)
      <br>
      <li value="19">
      <a href="Walter_M_Miller_Jr_Citations">Walter M. Miller, Jr.</a>,
      <b>A Canticle for Leibowitz</b>
      (Lippincott, 1959)
      <br>
      <li value="50">
      <a href="Samuel_R_Delany_Citations">Samuel R. Delany</a>, <b>Dhalgren</b>
      (Bantam, 1975)
      <br>
      <li value="50">
      <a href="Daniel_Keyes_Citations">Daniel Keyes</a>, <b>Flowers for Algernon</b>
      (Harcourt, Brace and World, 1966)
      <br>
      <li value="75">
      <a href="Robert_A_Heinlein_Citations">Robert A. Heinlein</a>,
      <b>Citizen of the Galaxy</b>
      (Scribners, 1957)
      <br>
      </ol>
    '''

    parsed = LocusAllTimeAwardsParser().parse(
      html,
      'https://www.sfadb.com/Locus_2012_SF20th',
      'Locus - All-Time 2012 20th Century SF Novel',
      '2012',
      'All-Time 20th Century SF Novel')

    self.assertEqual(7, len(parsed['entries']))
    self.assertEqual(
      [('1', 'Dune', 'Frank Herbert'),
       ('2', "Ender's Game", 'Orson Scott Card'),
       ('7', 'The Lion, the Witch and the Wardrobe', 'C. S. Lewis'),
       ('19', 'A Canticle for Leibowitz', 'Walter M. Miller, Jr.'),
       ('50', 'Dhalgren', 'Samuel R. Delany'),
       ('50', 'Flowers for Algernon', 'Daniel Keyes'),
       ('75', 'Citizen of the Galaxy', 'Robert A. Heinlein')],
      [(entry['position'], entry['title'], entry['author'])
       for entry in parsed['entries']])

  def test_wikipedia_award_table_parser_base_smoke(self):
    from parser.wikipedia_base import WikipediaAwardTableParserBase

    parser = WikipediaAwardTableParserBase()
    parser.AWARD_NAME = 'Smoke Award'
    html = '''
      <table>
        <tr><th>Year</th><th>Title</th><th>Author</th><th>Result</th><th>Category</th></tr>
        <tr>
          <td>2024</td>
          <td><a href="/wiki/Winning_Book">Winning Book</a></td>
          <td>Winner Writer</td>
          <td>Winner</td>
          <td>Novel</td>
        </tr>
        <tr>
          <td></td>
          <td><a href="/wiki/Shortlisted_Book">Shortlisted Book</a></td>
          <td>Short Writer</td>
          <td>Shortlisted</td>
          <td>Novel</td>
        </tr>
      </table>
    '''

    parsed = parser.parse(
      html, 'https://example.com/wiki_award', 'Smoke Award - Novel', 'Novel')

    self.assertEqual(['Winning Book', 'Shortlisted Book'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['2024', '2024.01'], [
      entry['position'] for entry in parsed['entries']
    ])
    self.assertEqual(['winner', 'shortlisted'], [
      entry['result'] for entry in parsed['entries']
    ])

  def test_isfdb_award_parser_base_smoke(self):
    from parser.isfdb_base import ISFDBAwardParserBase

    parser = ISFDBAwardParserBase()
    parser.AWARD_NAME = 'Smoke ISFDB Award'
    html = '''
      <table>
        <tr><td>2024</td></tr>
        <tr>
          <td>Winner</td>
          <td><a href="/cgi-bin/title.cgi?1">Winning Book</a></td>
          <td><a href="/cgi-bin/ea.cgi?1">Winner Writer</a></td>
        </tr>
        <tr>
          <td>Nominee</td>
          <td><a href="/cgi-bin/title.cgi?2">Nominee Book</a></td>
          <td><a href="/cgi-bin/ea.cgi?2">Nominee Writer</a></td>
        </tr>
      </table>
    '''

    parsed = parser.parse(
      html,
      'https://www.isfdb.org/cgi-bin/award_category.cgi?50+1',
      'Smoke ISFDB - Novel',
      'Novel')

    self.assertEqual(['Winning Book', 'Nominee Book'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['winner', 'nominee'], [
      entry['result'] for entry in parsed['entries']
    ])
    self.assertTrue(all(
      entry['source_url'].startswith('https://www.isfdb.org/cgi-bin/title.cgi?')
      for entry in parsed['entries']))

  def test_isfdb_fallback_smoke_uses_saved_scraps(self):
    from url_fetcher.prometheus import UrlFetcherPrometheusNovel

    folder, _source_urls, fetch = isfdb_folder_fetch('prometheus')
    fetcher = UrlFetcherPrometheusNovel()
    parsed = fetcher.parse_isfdb_award_type(
      load_text(folder / 'overview.html'),
      fetcher.isfdb_url(),
      fetch_url=fetch)

    self.assertEqual(fetcher.NAME, parsed['name'])
    self.assertTrue(parsed['entries'])
    self.assertTrue(any(
      entry.get('category') == fetcher.CATEGORY for entry in parsed['entries']))
    self.assertTrue(any(
      'isfdb.org/cgi-bin/title.cgi?' in entry.get('source_url', '')
      for entry in parsed['entries']))

  def test_aurealis_isfdb_category_smoke_uses_saved_scraps(self):
    from url_fetcher.aurealis import UrlFetcherAurealisSFNovel

    fetcher = UrlFetcherAurealisSFNovel()
    folder = SCRAPS_ISFDB_ROOT / 'aurealis_categories'
    path = folder / 'aurealis_sf_novel.html'
    url = 'https://www.isfdb.org/cgi-bin/award_category.cgi?50+1'

    parsed = fetcher.parse_isfdb_pages(
      load_text(path),
      url,
      (url,),
      fetch_url=lambda extra_url: self.fail(f'unexpected extra fetch: {extra_url}'))

    self.assertEqual(fetcher.NAME, parsed['name'])
    self.assertTrue(parsed['entries'])
    self.assertTrue(all(
      entry.get('category') == fetcher.CATEGORY for entry in parsed['entries']))

  def test_crime_writers_of_canada_wikipedia_parser_smoke(self):
    from parser.crime_writers_canada import CrimeWritersOfCanadaWikipediaParser

    html = '''
      <h2>Best Novel</h2>
      <table>
        <tr><th>Year</th><th>Title</th><th>Author</th></tr>
        <tr>
          <td>2024</td>
          <td><a href="/wiki/Everyone_on_This_Train">Everyone on This Train Is a Suspect</a></td>
          <td>Benjamin Stevenson</td>
        </tr>
      </table>
    '''

    parsed = CrimeWritersOfCanadaWikipediaParser().parse(
      html,
      'https://en.wikipedia.org/wiki/Crime_Writers_of_Canada_Award_for_Best_Novel',
      'Crime Writers of Canada Award - Novel',
      'Novel',
      ('Best Novel',))

    self.assertEqual(['Everyone on This Train Is a Suspect'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['winner'], [entry['result'] for entry in parsed['entries']])

  def test_crime_writers_of_canada_aliases_cover_current_wikipedia_headings(self):
    from parser.crime_writers_canada import CrimeWritersOfCanadaWikipediaParser
    from url_fetcher.crime_writers_canada import (
      UrlFetcherCrimeWritersOfCanadaFrenchCrimeBook,
      UrlFetcherCrimeWritersOfCanadaJuvenileYA,
      UrlFetcherCrimeWritersOfCanadaNonfiction,
    )

    parser = CrimeWritersOfCanadaWikipediaParser()
    self.assertTrue(parser.category_matches(
      'Best Crime Nonfiction',
      UrlFetcherCrimeWritersOfCanadaNonfiction.CATEGORY,
      UrlFetcherCrimeWritersOfCanadaNonfiction.CATEGORY_ALIASES))
    self.assertTrue(parser.category_matches(
      'Best Juvenile or Young Adult Crime Book',
      UrlFetcherCrimeWritersOfCanadaJuvenileYA.CATEGORY,
      UrlFetcherCrimeWritersOfCanadaJuvenileYA.CATEGORY_ALIASES))
    self.assertTrue(parser.category_matches(
      'Best Crime Book in French',
      UrlFetcherCrimeWritersOfCanadaFrenchCrimeBook.CATEGORY,
      UrlFetcherCrimeWritersOfCanadaFrenchCrimeBook.CATEGORY_ALIASES))

  def test_davitt_wikipedia_parser_smoke(self):
    from parser.davitt import DavittWikipediaParser

    html = '''
      <table>
        <tr><th>Year</th><th>Title</th><th>Author</th><th>Category</th></tr>
        <tr>
          <td>2024</td>
          <td><a href="/wiki/Exiles">Exiles</a></td>
          <td>Jane Harper</td>
          <td>Adult Fiction</td>
        </tr>
        <tr>
          <td><a href="/wiki/White_Crow">White Crow</a></td>
          <td>Michael Robotham</td>
          <td>Adult Fiction</td>
        </tr>
      </table>
    '''

    parsed = DavittWikipediaParser().parse(
      html,
      'https://en.wikipedia.org/wiki/Davitt_Award',
      'Davitt Award - Adult Novel',
      'Adult Fiction',
      ('Adult Novel',),
      allowed_results=('winner',))

    self.assertEqual(['Exiles', 'White Crow'], [entry['title'] for entry in parsed['entries']])
    self.assertEqual(['2024', '2024'], [entry['award_year'] for entry in parsed['entries']])
    self.assertTrue(all(entry['result'] == 'winner' for entry in parsed['entries']))

  def test_dilys_wikipedia_parser_smoke(self):
    from parser.dilys import DilysWikipediaParser

    html = '''
      <table>
        <tr><th>Year</th><th>Title</th><th>Author</th><th>Result</th></tr>
        <tr>
          <td>2024</td>
          <td><a href="/wiki/The_Tainted_Cup">The Tainted Cup</a></td>
          <td>Robert Jackson Bennett</td>
          <td>Winner</td>
        </tr>
        <tr>
          <td></td>
          <td><a href="/wiki/All_the_Sinners_Bleed">All the Sinners Bleed</a></td>
          <td>S. A. Cosby</td>
          <td>Shortlisted</td>
        </tr>
      </table>
    '''

    parsed = DilysWikipediaParser().parse(
      html,
      'https://en.wikipedia.org/wiki/Dilys_Award',
      'Dilys Award',
      'Dilys Award',
      (),
      allowed_results=('winner', 'shortlisted'))

    self.assertEqual(['winner', 'shortlisted'], [
      entry['result'] for entry in parsed['entries']
    ])

  def test_gumshoe_wikipedia_parser_smoke(self):
    from parser.gumshoe import GumshoeWikipediaParser

    html = '''
      <h2>Best Mystery</h2>
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th></tr>
        <tr>
          <td>2024</td>
          <td>S. J. Rozan</td>
          <td><a href="/wiki/The_Murder_of_Mr._Ma">The Murder of Mr. Ma</a></td>
        </tr>
      </table>
    '''

    parsed = GumshoeWikipediaParser().parse(
      html,
      'https://en.wikipedia.org/wiki/Gumshoe_Awards',
      'Gumshoe Award - Mystery',
      'Mystery',
      ('Best Mystery', 'Best Novel'))

    self.assertEqual(['The Murder of Mr. Ma'], [entry['title'] for entry in parsed['entries']])
    self.assertEqual(['winner'], [entry['result'] for entry in parsed['entries']])

  def test_ned_kelly_wikipedia_parser_smoke(self):
    from parser.ned_kelly import NedKellyWikipediaParser

    html = '''
      <table>
        <tr><th>Year</th><th>Best Crime Novel</th></tr>
        <tr><td>2023</td><td>Stone Town by Margaret Hickey</td></tr>
      </table>
      <h2>Best Crime Novel</h2>
      <table>
        <tr><th>Year</th><th>Title</th><th>Author</th><th>Result</th></tr>
        <tr>
          <td>2024</td>
          <td><a href="/wiki/Black_River">Black River</a></td>
          <td>Matthew Spencer</td>
          <td>Winner</td>
        </tr>
        <tr>
          <td></td>
          <td><a href="/wiki/Other_Finalist">Other Finalist</a></td>
          <td>Another Author</td>
          <td>Shortlisted</td>
        </tr>
      </table>
    '''

    parsed = NedKellyWikipediaParser().parse(
      html,
      'https://en.wikipedia.org/wiki/Ned_Kelly_Awards',
      'Ned Kelly Award - Crime Fiction',
      'Best Crime Novel',
      ('Crime Fiction', 'Best Novel'))

    self.assertEqual(
      {'2023', '2024'},
      {entry['award_year'] for entry in parsed['entries']})
    self.assertTrue(any(entry['title'] == 'Stone Town' for entry in parsed['entries']))
    self.assertTrue(any(entry['title'] == 'Black River' for entry in parsed['entries']))

  def test_ngaio_marsh_wikipedia_parser_smoke(self):
    from parser.ngaio_marsh import NgaioMarshWikipediaParser

    html = '''
      <h3>2024</h3>
      <h4>Crime Novel</h4>
      <ul>
        <li><a href="/wiki/Red_Herring">Red Herring</a> by Jane Smith
          <ul>
            <li><a href="/wiki/Blue_Herring">Blue Herring</a> by John Smith</li>
          </ul>
        </li>
      </ul>
    '''

    parsed = NgaioMarshWikipediaParser().parse(
      html,
      'https://en.wikipedia.org/wiki/Ngaio_Marsh_Awards',
      'Ngaio Marsh Award - Crime Novel',
      'Crime Novel',
      ('Novel',))

    self.assertEqual(['Red Herring', 'Blue Herring'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['winner', 'nominee'], [
      entry['result'] for entry in parsed['entries']
    ])

  def test_theakston_wikipedia_parser_smoke(self):
    from parser.theakston import TheakstonWikipediaParser

    html = '''
      <table>
        <tr><th>Year</th><th>Title</th><th>Author</th><th>Result</th></tr>
        <tr>
          <td>2024</td>
          <td><a href="/wiki/The_Last_Word">The Last Word</a></td>
          <td>Elly Griffiths</td>
          <td>Winner</td>
        </tr>
        <tr>
          <td></td>
          <td><a href="/wiki/Everybody_Knows">Everybody Knows</a></td>
          <td>Jordan Harper</td>
          <td>Shortlisted</td>
        </tr>
      </table>
    '''

    parsed = TheakstonWikipediaParser().parse(
      html,
      'https://en.wikipedia.org/wiki/Theakston_Old_Peculier_Crime_Novel_of_the_Year_Award',
      'Theakston Old Peculier Crime Novel of the Year',
      'Theakston Old Peculier Crime Novel of the Year',
      ('Crime Novel of the Year',),
      allowed_results=('winner', 'shortlisted'))

    self.assertEqual(['The Last Word', 'Everybody Knows'], [
      entry['title'] for entry in parsed['entries']
    ])

  def test_crime_fetcher_falls_back_to_wikipedia_smoke(self):
    from url_fetcher.crime_writers_canada import UrlFetcherCrimeWritersOfCanadaNovel

    fetcher = UrlFetcherCrimeWritersOfCanadaNovel()
    wiki_html = '''
      <h2>Best Novel</h2>
      <table>
        <tr><th>Year</th><th>Title</th><th>Author</th></tr>
        <tr>
          <td>2024</td>
          <td><a href="/wiki/Everyone_on_This_Train">Everyone on This Train Is a Suspect</a></td>
          <td>Benjamin Stevenson</td>
        </tr>
      </table>
    '''

    def fetch_url(url):
      if url == fetcher.URL:
        raise RuntimeError('librarything unavailable')
      if url == fetcher.WIKIPEDIA_URL:
        return wiki_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual(fetcher.NAME, parsed['name'])
    self.assertEqual(['Everyone on This Train Is a Suspect'], [
      entry['title'] for entry in parsed['entries']
    ])

  def test_ngaio_fetcher_falls_back_to_wikipedia_smoke(self):
    from url_fetcher.ngaio_marsh import UrlFetcherNgaioMarshCrimeNovel

    fetcher = UrlFetcherNgaioMarshCrimeNovel()
    wiki_html = '''
      <h3>2024</h3>
      <h4>Crime Novel</h4>
      <ul>
        <li><a href="/wiki/Red_Herring">Red Herring</a> by Jane Smith</li>
      </ul>
    '''

    def fetch_url(url):
      if url == fetcher.URL:
        raise RuntimeError('librarything unavailable')
      if url == fetcher.WIKIPEDIA_URL:
        return wiki_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual(fetcher.NAME, parsed['name'])
    self.assertEqual(['Red Herring'], [entry['title'] for entry in parsed['entries']])

if __name__ == '__main__':
  unittest.main()
