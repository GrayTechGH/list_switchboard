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
calibre_gui2.info_dialog = Dummy()
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
import import_flow
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
    self.assertEqual(212, len(names))
    self.assertIn('Pulitzer Prize - Fiction', names)
    self.assertIn('Pulitzer Prize - General Nonfiction', names)
    self.assertIn('National Book Award - Fiction', names)
    self.assertIn('National Book Award - Nonfiction', names)
    self.assertIn("National Book Award - Young People's Literature", names)
    self.assertIn('Baillie Gifford Prize', names)
    self.assertIn('National Book Critics Circle Award - Nonfiction', names)
    self.assertIn('National Book Critics Circle Award - Criticism', names)
    self.assertIn('PEN/John Kenneth Galbraith Award for Nonfiction', names)
    self.assertIn('PEN/Diamonstein-Spielvogel Award for the Art of the Essay', names)
    self.assertIn('PEN/Jean Stein Book Award', names)
    self.assertIn('PEN Open Book Award', names)
    self.assertIn('PEN/Faulkner Award for Fiction', names)
    self.assertIn('PEN/Hemingway Award for Debut Novel', names)
    self.assertIn('J. Anthony Lukas Book Prize', names)
    self.assertIn('Mark Lynton History Prize', names)
    self.assertIn('Orwell Prize for Political Writing', names)
    self.assertIn('Andrew Carnegie Medal for Excellence in Nonfiction', names)
    self.assertIn('Kirkus Prize - Fiction', names)
    self.assertIn('Kirkus Prize - Nonfiction', names)
    self.assertIn("Kirkus Prize - Young Readers' Literature", names)
    self.assertIn("Women's Prize for Non-Fiction", names)
    self.assertIn("Women's Prize for Fiction", names)
    self.assertIn('Royal Society Trivedi Science Book Prize', names)
    self.assertIn('Booker Prize', names)
    self.assertIn('International Booker Prize', names)
    self.assertIn("Governor General's Literary Award - English Fiction", names)
    self.assertIn("Governor General's Literary Award - English Non-fiction", names)
    self.assertIn(
      "Governor General's Literary Award - English Young People's Literature - Text",
      names)
    self.assertIn('Theakston Old Peculier Crime Novel of the Year', names)
    self.assertIn('Hammett Prize', names)
    self.assertIn('Nero Award', names)
    self.assertIn('Strand Critics Award - Mystery Novel', names)
    self.assertIn('Strand Critics Award - Debut Mystery', names)

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
    self.assertEqual(212, len(source_ids))
    self.assertIn('pulitzer_prize_fiction', source_ids)
    self.assertIn('pulitzer_prize_general_nonfiction', source_ids)
    self.assertIn('national_book_award_fiction', source_ids)
    self.assertIn('national_book_award_nonfiction', source_ids)
    self.assertIn('national_book_award_young_peoples_literature', source_ids)
    self.assertIn('baillie_gifford_prize', source_ids)
    self.assertIn('nbcc_award_nonfiction', source_ids)
    self.assertIn('nbcc_award_criticism', source_ids)
    self.assertIn('j_anthony_lukas_book_prize', source_ids)
    self.assertIn('mark_lynton_history_prize', source_ids)
    self.assertIn('orwell_prize_political_writing', source_ids)
    self.assertIn('andrew_carnegie_medal_nonfiction', source_ids)
    self.assertIn('kirkus_prize_fiction', source_ids)
    self.assertIn('kirkus_prize_nonfiction', source_ids)
    self.assertIn('kirkus_prize_young_readers_literature', source_ids)
    self.assertIn('womens_prize_nonfiction', source_ids)
    self.assertIn('womens_prize_fiction', source_ids)
    self.assertIn('royal_society_science_book_prize', source_ids)
    self.assertIn('booker_prize', source_ids)
    self.assertIn('international_booker_prize', source_ids)
    self.assertIn('governor_general_literary_award_english_fiction', source_ids)
    self.assertIn('governor_general_literary_award_english_nonfiction', source_ids)
    self.assertIn(
      'governor_general_literary_award_english_young_peoples_text',
      source_ids)
    self.assertIn('theakston_old_peculier_crime_novel_of_the_year', source_ids)
    self.assertIn('hammett_prize', source_ids)
    self.assertIn('nero_award', source_ids)
    self.assertIn('strand_critics_award_mystery_novel', source_ids)
    self.assertIn('strand_critics_award_debut_mystery', source_ids)

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

  def test_manage_active_list_reviews_cached_import_and_applies_changes(self):
    core = object.__new__(main.ListSwitchboardCore)
    core.ensure_configured = lambda: True
    core.current_active = lambda: 'Example List'
    core.import_cache_for_active_list = lambda _active: {
      'list_id': 'example_list',
      'list_name': 'Example List',
      'entries': [{'position': '1', 'title': 'Book', 'author': 'Author'}],
      'match_series': True,
      'notes': ['cached note'],
    }
    row = core.import_review_row(
      {'position': '1', 'title': 'Book', 'author': 'Author'},
      matched=True,
      book_ids=[7],
      match_source='automatic')
    core.match_imported_entries = lambda entries, **kwargs: ({7: '1'}, [], [row])
    core.reconcile_review_rows_with_active_list = (
      lambda list_name, rows, active_name=None, position_problem_rows=None:
        (rows, ['active note']))
    position_problem_rows = [{
      'position': '9',
      'book_id': 12,
      'title': 'Off Recipe',
      'author': 'Author',
    }]
    core.active_list_position_problem_rows_for_entries = (
      lambda _list_name, _entries: position_problem_rows)
    review_calls = []
    changed_row = core.import_review_row(
      {'position': '1', 'title': 'Book', 'author': 'Author'},
      matched=True,
      book_ids=[8],
      matched_books=[{
        'matched_book_id': 8,
        'matched_title': 'Book',
        'matched_authors': ['Author'],
      }],
      match_source='manual find')

    def review_import_matches(*args, **kwargs):
      review_calls.append((args, kwargs))
      return {8: '1'}, [], [changed_row]

    applied = []
    core.review_import_matches = review_import_matches
    core.apply_managed_active_list_review = (
      lambda list_name, rows: applied.append((list_name, rows)) or 2)
    messages = []
    core.status_message = messages.append

    core.manage_active_list()

    self.assertEqual(1, len(review_calls))
    args, kwargs = review_calls[0]
    self.assertEqual('Example List', args[0])
    self.assertEqual('example_list', args[1])
    self.assertEqual(1, args[2])
    self.assertEqual(1, args[3])
    self.assertEqual(['cached note', 'active note'], kwargs['notes'])
    self.assertEqual(True, kwargs['match_series'])
    self.assertEqual(False, kwargs['allow_goodreads_recovery'])
    self.assertEqual(position_problem_rows, kwargs['position_problem_rows'])
    self.assertEqual([('Example List', [changed_row])], applied)
    self.assertEqual(
      'Managed "Example List". Matched 1 book(s); 0 unmatched; updated 2 Active List book(s).',
      messages[-1])

  def test_show_active_list_position_problems_requires_active_list(self):
    core = object.__new__(main.ListSwitchboardCore)
    core.current_active = lambda: None

    with self.assertRaises(main.ListSwitchboardError):
      core.show_active_list_position_problems_for_current_active_list()

  def test_show_active_list_position_problems_requires_cached_import(self):
    core = object.__new__(main.ListSwitchboardCore)
    core.current_active = lambda: 'Example List'
    core.import_cache_for_active_list = lambda _active: None

    with self.assertRaises(main.ListSwitchboardError):
      core.show_active_list_position_problems_for_current_active_list()

  def test_show_active_list_position_problems_reports_none_found(self):
    core = object.__new__(main.ListSwitchboardCore)
    core.gui = None
    core.current_active = lambda: 'Example List'
    core.import_cache_for_active_list = lambda _active: {
      'list_id': 'example_list',
      'list_name': 'Example List',
      'entries': [{'position': '1', 'title': 'Book', 'author': 'Author'}],
    }
    core.active_list_position_problem_rows_for_entries = lambda _list_name, _entries: []
    dialogs = []
    original_info_dialog = import_flow.info_dialog
    import_flow.info_dialog = (
      lambda parent, title, message, show=False:
        dialogs.append((parent, title, message, show)))

    try:
      core.show_active_list_position_problems_for_current_active_list()
    finally:
      import_flow.info_dialog = original_info_dialog

    self.assertEqual([
      (None, 'Show position problems', 'No position problems found for "Example List".', True),
    ], dialogs)

  def test_show_active_list_position_problems_opens_problem_rows(self):
    core = object.__new__(main.ListSwitchboardCore)
    core.current_active = lambda: 'Example List'
    core.import_cache_for_active_list = lambda _active: {
      'list_id': 'example_list',
      'list_name': 'Example List',
      'entries': [{'position': '1', 'title': 'Book', 'author': 'Author'}],
    }
    rows = [{
      'position': '9',
      'book_id': 8,
      'title': 'Unknown Position Book',
      'author': 'Unknown Author',
    }]
    core.active_list_position_problem_rows_for_entries = lambda _list_name, _entries: rows
    viewed = []
    core.show_active_list_position_problem_rows = (
      lambda list_name, problem_rows: viewed.append((list_name, problem_rows)))

    core.show_active_list_position_problems_for_current_active_list()

    self.assertEqual([('Example List', rows)], viewed)

  def test_apply_managed_active_list_review_updates_visible_active_matches_only(self):
    core = object.__new__(main.ListSwitchboardCore)
    core.active_book_ids_for_list = lambda _list_name: [7, 9, 10]
    core.active_list_value_matches = lambda book_id, _list_name, _position: book_id == 7
    captured = {}
    core.write_fields_with_progress = lambda *args, **kwargs: captured.update({
      'args': args,
      'kwargs': kwargs,
    })
    rows = [
      {
        'entry': {'position': '1', 'title': 'Book', 'author': 'Author'},
        'imported_position': '1',
        'matched': True,
        'book_ids': [8],
        'original_book_ids': [7],
        'previous_book_ids': [7],
      },
      {
        'entry': {'position': '2', 'title': 'Other', 'author': 'Author'},
        'imported_position': '2',
        'matched': False,
        'book_ids': [],
        'original_book_ids': [9],
        'previous_book_ids': [9],
      },
    ]

    updated = core.apply_managed_active_list_review('Example List', rows)

    self.assertEqual(3, updated)
    self.assertEqual('Manage Active List', captured['args'][0])
    self.assertEqual({
      7: '',
      8: 'Example List',
      9: '',
    }, captured['kwargs']['active_updates'])
    self.assertEqual({8: 1.0}, captured['kwargs']['active_index_updates'])
    self.assertEqual(True, captured['kwargs']['assign_series_indexes'])
    self.assertNotIn(10, captured['kwargs']['active_updates'])

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

  def test_write_fields_bulk_writes_active_series_indexes_for_multiple_books(self):
    core = object.__new__(main.ListSwitchboardCore)
    set_field_calls = []
    set_custom_calls = []
    progress = []
    refreshed = []
    main.prefs['active_list_field'] = '#reading_series'
    core.active_list_value_matches = lambda _book_id, _value, _position: False
    core.active_field_is_series = lambda: True
    core.refresh_books = lambda ids: refreshed.append(ids)
    core.debug_writes_active_series_field = lambda *_args: None
    core.debug_writes_finished = lambda *_args: None

    class FakeApi:

      def set_field(self, field, updates, allow_case_change=True):
        set_field_calls.append((field, updates, allow_case_change))

    class FakeDb:
      new_api = FakeApi()

      def set_custom(self, *args, **kwargs):
        set_custom_calls.append((args, kwargs))

    core.db = FakeDb()

    core.write_fields(
      active_updates={7: 'The Wheel of Time', 8: 'The Wheel of Time'},
      active_index_updates={7: 1.0, 8: 2.5},
      progress_callback=lambda count, message: progress.append((count, message)))

    self.assertEqual([
      ('#reading_series', {7: 'The Wheel of Time [1]', 8: 'The Wheel of Time [2.5]'}, True),
    ], set_field_calls)
    self.assertEqual([], set_custom_calls)
    self.assertEqual([(2, 'Finished Active List metadata updates...')], progress)
    self.assertEqual([{7, 8}], refreshed)

  def test_write_fields_bulk_clears_active_series_for_multiple_books(self):
    core = object.__new__(main.ListSwitchboardCore)
    set_field_calls = []
    set_custom_calls = []
    main.prefs['active_list_field'] = '#reading_series'
    core.active_list_value_matches = lambda _book_id, _value, _position: False
    core.active_field_is_series = lambda: True
    core.refresh_books = lambda _ids: None
    core.debug_writes_active_series_field = lambda *_args: None
    core.debug_writes_finished = lambda *_args: None

    class FakeApi:

      def set_field(self, field, updates, allow_case_change=True):
        set_field_calls.append((field, updates, allow_case_change))

    class FakeDb:
      new_api = FakeApi()

      def set_custom(self, *args, **kwargs):
        set_custom_calls.append((args, kwargs))

    core.db = FakeDb()

    core.write_fields(active_updates={7: '', 8: ''}, active_index_updates={})

    self.assertEqual([('#reading_series', {7: '', 8: ''}, True)], set_field_calls)
    self.assertEqual([], set_custom_calls)

  def test_write_fields_keeps_single_active_series_write_on_set_custom(self):
    core = object.__new__(main.ListSwitchboardCore)
    set_field_calls = []
    set_custom_calls = []
    refreshed = []
    main.prefs['active_list_field'] = '#reading_series'
    core.active_list_value_matches = lambda _book_id, _value, _position: False
    core.active_field_is_series = lambda: True
    core.refresh_books = lambda ids: refreshed.append(ids)
    core.debug_writes_active_series_field = lambda *_args: None
    core.debug_writes_finished = lambda *_args: None

    class FakeApi:

      def set_field(self, field, updates, allow_case_change=True):
        set_field_calls.append((field, updates, allow_case_change))

    class FakeDb:
      new_api = FakeApi()

      def set_custom(self, *args, **kwargs):
        set_custom_calls.append((args, kwargs))

    core.db = FakeDb()

    core.write_fields(
      active_updates={7: 'The Wheel of Time'},
      active_index_updates={7: 1.5})

    self.assertEqual([], set_field_calls)
    self.assertEqual([
      ((7, 'The Wheel of Time'), {
        'label': 'reading_series',
        'extra': 1.5,
        'allow_case_change': True,
      }),
    ], set_custom_calls)
    self.assertEqual([{7}], refreshed)

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

  def test_shift_add_reviews_saved_cached_override(self):
    core = object.__new__(main.ListSwitchboardCore)
    core.debug_storage_cached_active_add_decision = lambda *_args, **_kwargs: None
    entry = {
      'position': '1994.22',
      'title': 'Nightside the Long Sun',
      'author': 'Gene Wolfe',
    }
    other_entry = {
      'position': '1994.23',
      'title': 'Timelike Infinity',
      'author': 'Stephen Baxter',
    }
    calls = []

    def chooser(book_id, entries, candidates, default_index, db, **kwargs):
      calls.append((book_id, entries, candidates, default_index, db, kwargs))
      return entry, 1994.22, True

    core._active_add_match_chooser = chooser
    db = object()
    result = core.cached_active_match_for_book(
      38627,
      {
        'entries': [entry, other_entry],
        'override_entries_by_book': {38627: entry},
      },
      12.0,
      db,
      force_match_review=True,
      active_list_name='Locus annual SF novel')

    self.assertEqual((entry, 1994.22, False), result)
    self.assertEqual(1, len(calls))
    self.assertEqual(38627, calls[0][0])
    self.assertEqual([entry, other_entry], calls[0][1])
    self.assertEqual([(0, entry)], calls[0][2])
    self.assertEqual(12.0, calls[0][3])
    self.assertIs(db, calls[0][4])
    self.assertEqual(True, calls[0][5]['initial_show_all'])
    self.assertIs(entry, calls[0][5]['preferred_entry'])
    self.assertIs(entry, calls[0][5]['automatic_entry'])
    self.assertEqual('Locus annual SF novel', calls[0][5]['active_list_name'])

  def test_shift_add_reviews_unique_nonexact_cached_candidate(self):
    core = object.__new__(main.ListSwitchboardCore)
    core.debug_storage_cached_active_add_decision = lambda *_args, **_kwargs: None
    core.debug_storage_cached_active_add_candidates = lambda *_args, **_kwargs: None
    candidate = {
      'position': '1994.22',
      'title': 'Nightside the Long Sun',
      'author': 'Gene Wolfe',
    }
    core.cached_entry_candidates_for_book = (
      lambda *_args, **_kwargs: [(3, candidate)])
    calls = []

    def chooser(book_id, entries, candidates, default_index, db, **kwargs):
      calls.append((book_id, entries, candidates, default_index, db, kwargs))
      return candidate, 1994.22, True

    core._active_add_match_chooser = chooser
    db = object()
    result = core.cached_active_match_for_book(
      38627,
      {
        'entries': [candidate],
        'exact_entries_by_key': {},
        'override_entries_by_book': {},
        'titles': {38627: 'Epiphany of the Long Sun'},
        'authors': {38627: ['Gene Wolfe']},
      },
      12.0,
      db,
      force_match_review=True,
      active_list_name='Locus annual SF novel')

    self.assertEqual((candidate, 1994.22, True), result)
    self.assertEqual(1, len(calls))
    self.assertEqual([(3, candidate)], calls[0][2])
    self.assertEqual(True, calls[0][5]['initial_show_all'])
    self.assertIs(candidate, calls[0][5]['preferred_entry'])
    self.assertIsNone(calls[0][5]['automatic_entry'])
    self.assertEqual('Locus annual SF novel', calls[0][5]['active_list_name'])

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

  def test_active_reconciliation_uses_recipe_positions_for_problem_note(self):
    core = self.build_active_reconciliation_core(active_ids=[8], active_positions={8: '9'})
    row = core.import_review_row({
      'position': '1',
      'title': 'First Book',
      'author': 'Author One',
    })
    position_problem_rows = core.active_list_position_problem_rows_for_entries(
      'Example List',
      [
        {'position': '1', 'title': 'First Book', 'author': 'Author One'},
        {'position': '9', 'title': 'Unknown Position Book', 'author': 'Unknown Author'},
      ])

    _rows, notes = core.reconcile_review_rows_with_active_list(
      'Example List', [row], active_name='Example List',
      position_problem_rows=position_problem_rows)

    self.assertEqual([], position_problem_rows)
    self.assertEqual([], notes)

  def test_active_list_position_problem_rows_include_book_details(self):
    core = self.build_active_reconciliation_core(active_ids=[8], active_positions={8: '9'})

    rows = core.active_list_position_problem_rows_for_entries(
      'Example List',
      [{'position': '1', 'title': 'First Book', 'author': 'Author One'}])

    self.assertEqual([{
      'position': '9',
      'book_id': 8,
      'title': 'Unknown Position Book',
      'author': 'Unknown Author',
    }], rows)


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

  def test_sfadb_parser_base_handles_categoryblock_xpath_dom_variation(self):
    import re
    from parser.sfadb_base import SFADBParser, StandardItemMixin

    class SmokeSFADBParser(StandardItemMixin, SFADBParser):
      AWARD_NAME = 'Smoke SFADB Award'
      YEAR_PAGE_URL = re.compile(r'/Smoke_Awards_(\d{4})$')
      CATEGORY_BOUNDARIES = frozenset({'novella'})

    overview = '''
      <nav>
        <a data-extra="x" href="/Smoke_Awards_2025">
          <span>2025</span>
        </a>
      </nav>
    '''
    year_page = '''
      <section>
        <div class="extra categoryblock">
          <div class="category">Best <span>Novel</span></div>
          <ul>
            <li><strong>Winner:</strong> The <span>Nested <em>Book</em></span>,
                Ada Writer (Press)</li>
            <li>Second <span>Book</span>, Ben Writer (Press)</li>
          </ul>
        </div>
        <div class="categoryblock">
          <div class="category">Novella</div>
          <ul><li>Wrong Length, Wrong Writer</li></ul>
        </div>
      </section>
    '''

    parsed = SmokeSFADBParser().parse(
      overview,
      'https://www.sfadb.com/Smoke_Awards',
      'Smoke SFADB Award - Novel',
      'Best Novel',
      ('best novel',),
      fetch_url=lambda url: year_page if url.endswith('/Smoke_Awards_2025') else self.fail(url))

    self.assertEqual(['The Nested Book', 'Second Book'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['2025', '2025.01'], [
      entry['position'] for entry in parsed['entries']
    ])

  def test_hugo_parser_stops_xpath_category_at_next_award_heading(self):
    from parser.hugo import HugoAwardsNovelParser

    history = '''
      <a href="/2024-hugo-awards/">2024 Hugo Awards</a>
      <a href="/1945-retro-hugo-awards/">1945 Retro Hugo Awards</a>
    '''
    year_page = '''
      <article>
        <h2>Best <span>Novel</span></h2>
        <div><ul>
          <li>The <em>Winning</em> Book by Ada Writer</li>
          <li>Second Book, Ben Writer</li>
        </ul></div>
        <h2>Best Novella</h2>
        <ul><li>Wrong Category by Wrong Writer</li></ul>
      </article>
    '''

    parsed = HugoAwardsNovelParser().parse(
      history,
      'https://www.thehugoawards.org/hugo-history/',
      fetch_url=lambda url: year_page if url.endswith('/2024-hugo-awards/') else self.fail(url))

    self.assertEqual(['The Winning Book', 'Second Book'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['winner', 'nominee'], [
      entry['result'] for entry in parsed['entries']
    ])

  def test_nommo_wikipedia_parser_handles_table_xpath_dom_variation(self):
    from parser.nommo import parse_nommo_awards

    html = '''
      <h2>Novel</h2>
      <table class="wikitable">
        <tr><th>Year</th><th>Title</th><th>Author</th></tr>
        <tr>
          <td>2024</td>
          <td>
            <a data-id="book" href="/wiki/Nested_Book">The
              <span>Nested <em>Book</em></span></a><sup>[1]</sup>
          </td>
          <td><span>Ada Writer</span> *</td>
        </tr>
        <tr>
          <td><a href="/wiki/Second_Book">Second <strong>Book</strong></a></td>
          <td>Ben Writer</td>
        </tr>
      </table>
    '''

    parsed = parse_nommo_awards(
      html,
      'https://en.wikipedia.org/wiki/Nommo_Awards',
      'Nommo Award - Novel',
      'Novel')

    self.assertEqual(['The Nested Book', 'Second Book'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['winner', 'nominee'], [
      entry['result'] for entry in parsed['entries']
    ])
    self.assertEqual(
      'https://en.wikipedia.org/wiki/Nested_Book',
      parsed['entries'][0]['source_url'])

  def test_spsfc_finalist_parser_ignores_excluded_xpath_contexts(self):
    from parser.spsfc import OFFICIAL_FINALISTS, SPSFCAwardsParser

    page = {
      'url': 'https://spsfc.space/finalists/',
      'competition': 'SPSFC X',
      'award_year': 2030,
      'kind': OFFICIAL_FINALISTS,
    }
    html = '''
      <main>
        <article class="entry-content">
          <ul>
            <li><a href="https://www.goodreads.com/book/show/1">Deep Sky</a>
                by Ada Writer</li>
            <li><span>Bright</span> Engines by Ben Writer</li>
          </ul>
          <div class="comments"><ul><li>Comment Book by Wrong Writer</li></ul></div>
        </article>
        <aside class="sidebar"><ul><li>Sidebar Book by Wrong Writer</li></ul></aside>
      </main>
    '''

    rows = SPSFCAwardsParser().parse_finalist_page(html, page)

    self.assertEqual(['Deep Sky', 'Bright Engines'], [row['title'] for row in rows])
    self.assertEqual(
      'https://www.goodreads.com/book/show/1',
      rows[0]['source_url'])

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

  def test_wikipedia_award_table_parser_base_handles_dom_variation(self):
    from parser.wikipedia_base import WikipediaAwardTableParserBase

    parser = WikipediaAwardTableParserBase()
    parser.AWARD_NAME = 'Smoke Award'
    html = '''
      <table class="wikitable">
        <tr>
          <th><span>Award year</span></th>
          <th>Book</th>
          <th>Writer</th>
          <th>Status</th>
          <th>Award category</th>
        </tr>
        <tr>
          <td>2025</td>
          <td>
            <div>
              <a data-sort-value="nested" href="/wiki/Nested_Book">
                The <span>Nested <em>Book</em></span>
              </a>
              <sup>[12]</sup>
              <script>ignored()</script>
            </div>
          </td>
          <td><span>Nested <strong>Writer</strong></span><style>.x{}</style></td>
          <td>Winner</td>
          <td>Novel</td>
        </tr>
      </table>
    '''

    parsed = parser.parse(
      html, 'https://example.com/wiki_award', 'Smoke Award - Novel', 'Novel')

    self.assertEqual(['The Nested Book'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['Nested Writer'], [
      entry['author'] for entry in parsed['entries']
    ])
    self.assertEqual(
      'https://example.com/wiki/Nested_Book',
      parsed['entries'][0]['source_url'])

  def test_booknotification_award_parser_base_smoke(self):
    from parser.booknotification_base import BookNotificationAwardParserBase

    parser = BookNotificationAwardParserBase()
    parser.AWARD_NAME = 'Smoke BookNotification Award'
    html = '''
      <table>
        <tr>
          <th>Year</th><th>Read</th><th>Category</th>
          <th>Author</th><th>Title</th><th>Result</th>
        </tr>
        <tr>
          <td>2024</td>
          <td><input checked></td>
          <td>Best Mystery Novel</td>
          <td>Winner Writer</td>
          <td><a href="/books/winning-book">Winning Book</a></td>
          <td>Won</td>
        </tr>
        <tr>
          <td>2024</td>
          <td><input></td>
          <td>Best Mystery Novel</td>
          <td>Nominee Writer</td>
          <td><a href="/books/nominee-book">Nominee Book</a></td>
          <td>Nominated</td>
        </tr>
        <tr>
          <td>2024</td>
          <td><input></td>
          <td>Best Short Story</td>
          <td>Wrong Writer</td>
          <td>Wrong Story</td>
          <td>Won</td>
        </tr>
      </table>
    '''

    parsed = parser.parse(
      html,
      'https://www.booknotification.com/awards/smoke-award/',
      'Smoke BookNotification Award - Mystery',
      'Best Mystery Novel')

    self.assertEqual(['Winning Book', 'Nominee Book'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['winner', 'nominee'], [
      entry['result'] for entry in parsed['entries']
    ])
    self.assertEqual(['2024', '2024.01'], [
      entry['position'] for entry in parsed['entries']
    ])
    self.assertEqual(
      'https://www.booknotification.com/books/winning-book',
      parsed['entries'][0]['source_url'])

  def test_booknotification_award_parser_base_handles_dom_variation(self):
    from parser.booknotification_base import BookNotificationAwardParserBase

    parser = BookNotificationAwardParserBase()
    parser.AWARD_NAME = 'Smoke BookNotification Award'
    html = '''
      <table data-source="booknotification">
        <tr>
          <th><span>Year</span></th>
          <th>Read</th>
          <th><span>Award Category</span></th>
          <th><span>Writer</span></th>
          <th><span>Book</span></th>
          <th><span>Status</span></th>
        </tr>
        <tr>
          <td>2025</td>
          <td><span><input></span></td>
          <td><div>Best Mystery Novel</div></td>
          <td>
            <span>Nested <strong>Writer</strong></span>
            <script>ignored()</script>
          </td>
          <td>
            <div>
              <a data-book-id="1" href="/books/nested-book">
                The <span>Nested <em>Book</em></span>
              </a>
              <style>.ignored { display: none; }</style>
            </div>
          </td>
          <td><span>Won</span></td>
        </tr>
      </table>
    '''

    parsed = parser.parse(
      html,
      'https://www.booknotification.com/awards/smoke-award/',
      'Smoke BookNotification Award - Mystery',
      'Best Mystery Novel')

    self.assertEqual(['The Nested Book'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['Nested Writer'], [
      entry['author'] for entry in parsed['entries']
    ])
    self.assertEqual(
      'https://www.booknotification.com/books/nested-book',
      parsed['entries'][0]['source_url'])

  def test_booknotification_award_parser_base_filters_blank_title_rows(self):
    from parser.booknotification_base import BookNotificationAwardParserBase

    parser = BookNotificationAwardParserBase()
    parser.AWARD_NAME = 'Smoke BookNotification Award'
    html = '''
      <table>
        <tr>
          <th>Year</th><th>Read</th><th>Category</th>
          <th>Author</th><th>Title</th><th>Result</th>
        </tr>
        <tr>
          <td>1995</td><td></td><td>Grand Master</td>
          <td>Helen McCloy</td><td></td><td>Won</td>
        </tr>
      </table>
    '''

    parsed = parser.parse(
      html,
      'https://www.booknotification.com/awards/smoke-award/',
      'Smoke BookNotification Award - Grand Master',
      'Grand Master')

    self.assertEqual([], parsed['entries'])

    parsed_person_award = parser.parse(
      html,
      'https://www.booknotification.com/awards/smoke-award/',
      'Smoke BookNotification Award - Grand Master',
      'Grand Master',
      require_title=False)

    self.assertEqual(['Helen McCloy'], [
      entry['author'] for entry in parsed_person_award['entries']
    ])
    self.assertEqual([''], [
      entry['title'] for entry in parsed_person_award['entries']
    ])

  def test_booknotification_award_parser_base_handles_known_tie(self):
    from parser.booknotification_base import BookNotificationAwardParserBase

    parser = BookNotificationAwardParserBase()
    parser.AWARD_NAME = 'International Horror Guild Award'
    html = '''
      <table>
        <tr>
          <th>Year</th><th>Read</th><th>Category</th>
          <th>Author</th><th>Title</th><th>Result</th>
        </tr>
        <tr>
          <td>2006</td><td><input></td><td>Best Collection</td>
          <td>Terry Dowling</td>
          <td><a href="/books/basic-black">Basic Black</a></td>
          <td>Won</td>
        </tr>
        <tr>
          <td>2006</td><td><input></td><td>Best Collection</td>
          <td>Glen Hirshberg</td>
          <td><a href="/books/american-morons">American Morons</a></td>
          <td>Won</td>
        </tr>
        <tr>
          <td>2006</td><td><input></td><td>Best Collection</td>
          <td>Wrong Writer</td>
          <td>Other Collection</td>
          <td>Nominated</td>
        </tr>
      </table>
    '''

    parsed = parser.parse(
      html,
      'https://www.booknotification.com/awards/international-horror-guild-awards/',
      'International Horror Guild Award - Collection',
      'Best Collection',
      tied_winners_share_position=True)

    self.assertEqual(
      ['Basic Black', 'American Morons', 'Other Collection'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(['2006', '2006', '2006.01'], [
      entry['position'] for entry in parsed['entries']
    ])

  def test_dilys_booknotification_parser_smoke(self):
    from parser.dilys import DilysBookNotificationParser

    html = '''
      <table>
        <tr>
          <th>Year</th><th>Read</th><th>Category</th>
          <th>Author</th><th>Title</th><th>Result</th>
        </tr>
        <tr>
          <td>2014</td><td><input></td><td>Best Mystery Novel</td>
          <td>William Kent Krueger</td>
          <td><a href="/books/ordinary-grace">Ordinary Grace</a></td>
          <td>Won</td>
        </tr>
        <tr>
          <td>2014</td><td><input></td><td>Best Mystery Novel</td>
          <td>Lyndsay Faye</td>
          <td>Seven for a Secret</td>
          <td>Nominated</td>
        </tr>
      </table>
    '''

    parsed = DilysBookNotificationParser().parse(
      html,
      'https://www.booknotification.com/awards/dilys-awards/',
      'Dilys Award',
      'Best Mystery Novel',
      ('Dilys Award',))

    self.assertEqual(['Ordinary Grace', 'Seven for a Secret'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['winner', 'nominee'], [
      entry['result'] for entry in parsed['entries']
    ])

  def test_hammett_official_parser_smoke(self):
    from parser.hammett import HammettPrizeParser

    html = '''
      <h2>2024</h2>
      <h5>Winner: <a href="/books/god-of-the-woods">God of the Woods</a> by Liz Moore (Riverhead)</h5>
      <p>Nominees:</p>
      <p><a href="/books/the-long-shot-trial">The Long-Shot Trial</a> by William Deverell (ECW Press)</p>
      <p>Broiler by Eli Cranor (Soho)</p>
      <p>Judges:</p>
    '''

    parsed = HammettPrizeParser().parse(
      html,
      'https://www.crimewritersna.org/hammett-prize-past-winners-nominees-j',
      'Hammett Prize',
      'Hammett Prize',
      ('Best Crime Book',))

    self.assertEqual(
      ['God of the Woods', 'The Long-Shot Trial', 'Broiler'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'nominee', 'nominee'],
      [entry['result'] for entry in parsed['entries']])
    self.assertEqual(
      'https://www.crimewritersna.org/books/god-of-the-woods',
      parsed['entries'][0]['source_url'])

  def test_hammett_official_parser_handles_collapsed_heading_text(self):
    from parser.hammett import HammettPrizeParser

    html = '''
      <h2>2018</h2>
      <h5>
        Winner: November Road, by Lou Berney (William Morrow)
        Nominees: Paris in the Dark, by Robert Olen Butler (Mysterious Press)
        The Lonely Witness, by William Boyle (Pegasus)
        Under My Skin, by Lisa Unger (Park Row)
        Judges: Gary Giddins
      </h5>
    '''

    parsed = HammettPrizeParser().parse(
      html,
      'https://www.crimewritersna.org/copy-of-hammett-prize-past-winners-n-2',
      'Hammett Prize',
      'Hammett Prize',
      ('Best Crime Book',))

    self.assertEqual(
      ['November Road', 'Paris in the Dark', 'The Lonely Witness', 'Under My Skin'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'nominee', 'nominee', 'nominee'],
      [entry['result'] for entry in parsed['entries']])

  def test_hammett_official_parser_handles_older_rows_and_ignores_special_mention(self):
    from parser.hammett import HammettPrizeParser

    html = '''
      <h2>1992</h2>
      <h5>Winner: Turtle Moon by Alice Hoffman (Putnam)</h5>
      <p>Special Mention: The Ones You Do by Daniel Woodrell (Holt)</p>
      <p>Nominees:</p>
      <p>Trick of the Eye by Jane Stanton Hitchcock (Dutton)</p>
      <p>White Butterfly by Walter Mosley (Norton)</p>
      <p>Judges:</p>
    '''

    parsed = HammettPrizeParser().parse(
      html,
      'https://www.crimewritersna.org/copy-of-hammett-prize-past-winners-n',
      'Hammett Prize',
      'Hammett Prize',
      ('Best Crime Book',))

    self.assertEqual(
      ['Turtle Moon', 'Trick of the Eye', 'White Butterfly'],
      [entry['title'] for entry in parsed['entries']])
    self.assertNotIn('The Ones You Do', [
      entry['title'] for entry in parsed['entries']
    ])

  def test_hammett_fetcher_parses_overview_and_year_pages(self):
    from url_fetcher.hammett import UrlFetcherHammettPrize

    overview = '''
      <nav>
        <a href="/hammett-prize-past-winners-nominees-j">Hammett 2021 - Present</a>
        <a href="/copy-of-hammett-prize-past-winners-n-2">Hammett 2011 - 2020</a>
      </nav>
    '''
    current = '''
      <h2>2024</h2>
      <h5>Winner: God of the Woods by Liz Moore (Riverhead)</h5>
      <p>Nominees:</p>
      <p>The Long-Shot Trial by William Deverell (ECW Press)</p>
      <p>Judges:</p>
    '''
    previous = '''
      <h2>2018</h2>
      <h5>Winner: November Road, by Lou Berney (William Morrow) Nominees: Paris in the Dark, by Robert Olen Butler (Mysterious Press) Judges: Gary Giddins</h5>
    '''

    def fetch_url(url):
      if url == 'https://www.crimewritersna.org/hammett-prize':
        return overview
      if url.endswith('/hammett-prize-past-winners-nominees-j'):
        return current
      if url.endswith('/copy-of-hammett-prize-past-winners-n-2'):
        return previous
      self.fail(url)

    parsed = UrlFetcherHammettPrize().fetch_and_parse(fetch_url)

    self.assertEqual('Hammett Prize', parsed['name'])
    self.assertEqual(
      ['November Road', 'Paris in the Dark', 'God of the Woods', 'The Long-Shot Trial'],
      [entry['title'] for entry in parsed['entries']])
    self.assertFalse(parsed['match_series'])

  def test_hammett_librarything_fallback_parser_smoke(self):
    from url_fetcher.hammett import UrlFetcherHammettPrize

    html = '''
      <h2>Winner 1</h2>
      <table>
        <tr><th>Work</th><th>Year</th></tr>
        <tr><td><a href="/work/1">Prince of Thieves</a> by <a href="/author/1">Chuck Hogan</a></td><td>2004</td></tr>
      </table>
      <h2>Nominee 1</h2>
      <table>
        <tr><th>Work</th><th>Year</th></tr>
        <tr><td><a href="/work/2">The Madman's Tale</a> by <a href="/author/2">John Katzenbach</a></td><td>2004</td></tr>
      </table>
    '''

    parser = UrlFetcherHammettPrize().create_librarything_parser()
    parsed = parser.parse(
      html,
      'https://www.librarything.com/award/1253/Hammett-Prize',
      'Hammett Prize',
      'Hammett Prize',
      ('Best Crime Book',))

    self.assertEqual(
      ['Prince of Thieves', "The Madman's Tale"],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'nominee'],
      [entry['result'] for entry in parsed['entries']])

  def test_hammett_fetcher_falls_back_to_librarything_when_official_is_unusable(self):
    from url_fetcher.hammett import UrlFetcherHammettPrize

    librarything = '''
      <h2>Winner 1</h2>
      <table>
        <tr><th>Work</th><th>Year</th></tr>
        <tr><td><a href="/work/1">Prince of Thieves</a> by <a href="/author/1">Chuck Hogan</a></td><td>2004</td></tr>
      </table>
      <h2>Nominee 1</h2>
      <table>
        <tr><th>Work</th><th>Year</th></tr>
        <tr><td><a href="/work/2">The Madman's Tale</a> by <a href="/author/2">John Katzenbach</a></td><td>2004</td></tr>
      </table>
    '''

    def fetch_url(url):
      if url == 'https://www.crimewritersna.org/hammett-prize':
        return '<html><body><p>No archive links here.</p></body></html>'
      if url == 'https://www.librarything.com/award/1253/Hammett-Prize':
        return librarything
      self.fail(url)

    parsed = UrlFetcherHammettPrize().fetch_and_parse(fetch_url)

    self.assertEqual(
      ['Prince of Thieves', "The Madman's Tale"],
      [entry['title'] for entry in parsed['entries']])
    self.assertTrue(any(
      'Official IACW failed:' in note for note in parsed.get('notes', ())
    ))

  def test_hammett_fetcher_source_choices_and_filter_category(self):
    from url_fetcher.hammett import UrlFetcherHammettPrize

    fetcher = UrlFetcherHammettPrize()

    self.assertEqual(
      ('Automatic', 'Official IACW', 'LibraryThing'),
      tuple(choice['label'] for choice in fetcher.source_choices()))
    self.assertTrue(any(
      item['label'] == 'Crime, Mystery & Thriller'
      for item in fetcher.get_filter_list()))

  def test_hammett_fetcher_registration_order(self):
    from url_fetcher import available_url_fetchers

    source_ids = [fetcher.source_id for fetcher in available_url_fetchers()]

    self.assertLess(
      source_ids.index('barry_award_british_crime_novel'),
      source_ids.index('hammett_prize'))
    self.assertLess(
      source_ids.index('hammett_prize'),
      source_ids.index('crime_writers_of_canada_award_novel'))

  def test_nero_official_parser_marks_bold_winner_and_ignores_black_orchid_text(self):
    from parser.nero import NeroAwardOfficialParser

    html = '''
      <h1>The Nero Award Finalists</h1>
      <h3>Winners are listed in bold typeface</h3>
      <h3 align="center">2018</h3>
      <ul>
        <li><em>Blood for Wine</em> by Warren C. Easley (Poisoned Pen Press)</li>
        <li><em><strong>August Snow</strong></em><strong> by Stephen Mack Jones (Soho)</strong></li>
      </ul>
      <h3>Black Orchid Novella Award</h3>
      <ul><li><em>Wrong Award</em> by Wrong Writer</li></ul>
      <h4>(Sorry, we did not keep a record of finalists until 2007.)</h4>
    '''

    parsed = NeroAwardOfficialParser().parse(
      html,
      'https://wp.nerowolfe.org/htm/literary_awards/nero_award/Nero_Award_Finalists.htm',
      'Nero Award',
      'Nero Award')

    self.assertEqual(
      ['Blood for Wine', 'August Snow'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['nominee', 'winner'],
      [entry['result'] for entry in parsed['entries']])
    self.assertNotIn('Wrong Award', [
      entry['title'] for entry in parsed['entries']
    ])

  def test_nero_official_parser_adds_pre_2007_winner_only_rows(self):
    from parser.nero import NeroAwardOfficialParser

    finalists = '''
      <h1>The Nero Award Finalists</h1>
      <h3 align="center">2007</h3>
      <ul>
        <li><strong><em>All Mortal Flesh</em> &#8212; Julia Spencer-Fleming</strong></li>
        <li><em>Kidnapped</em> &#8212; Jan Burke</li>
      </ul>
      <h4>(Sorry, we did not keep a record of finalists until 2007.)</h4>
    '''
    winners = '''
      <h1>Wolfe Pack Nero Award Recipients Chronological</h1>
      <table>
        <tr><th>Year</th><th>Winner</th></tr>
        <tr><td>2007</td><td><em>All Mortal Flesh</em> by Julia Spencer-Fleming</td></tr>
        <tr><td>2006</td><td><em>Vanish</em> by Tess Gerritsen</td></tr>
        <tr><td>2005</td><td><em>The Enemy</em> by Lee Child</td></tr>
      </table>
    '''

    parsed = NeroAwardOfficialParser().parse(
      finalists,
      'https://wp.nerowolfe.org/htm/literary_awards/nero_award/Nero_Award_Finalists.htm',
      'Nero Award',
      'Nero Award',
      fetch_url=lambda url: winners)

    self.assertEqual(
      ['The Enemy', 'Vanish', 'All Mortal Flesh', 'Kidnapped'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(['2005', '2006', '2007', '2007.01'], [
      entry['position'] for entry in parsed['entries']
    ])

  def test_nero_official_parser_dedupes_winner_present_in_finalist_and_winner_pages(self):
    from parser.nero import NeroAwardOfficialParser

    finalists = '''
      <h1>The Nero Award Finalists</h1>
      <h3 align="center">2018</h3>
      <ul>
        <li><em>Blood for Wine</em> by Warren C. Easley</li>
        <li><strong><em>August Snow</em> by Stephen Mack Jones</strong></li>
      </ul>
    '''
    winners = '''
      <h1>Wolfe Pack Nero Award Recipients Chronological</h1>
      <table>
        <tr><th>Year</th><th>Winner</th></tr>
        <tr><td>2018</td><td><em>August Snow</em> by Stephen Mack Jones</td></tr>
      </table>
    '''

    parsed = NeroAwardOfficialParser().parse(
      finalists,
      'https://wp.nerowolfe.org/htm/literary_awards/nero_award/Nero_Award_Finalists.htm',
      'Nero Award',
      'Nero Award',
      fetch_url=lambda url: winners)

    self.assertEqual(
      ['Blood for Wine', 'August Snow'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(1, sum(
      1 for entry in parsed['entries']
      if entry['title'] == 'August Snow'))

  def test_nero_official_parser_notes_winner_supplement_failure(self):
    from parser.nero import NeroAwardOfficialParser

    finalists = '''
      <h1>The Nero Award Finalists</h1>
      <h3 align="center">2018</h3>
      <ul>
        <li><em>Blood for Wine</em> by Warren C. Easley</li>
        <li><strong><em>August Snow</em> by Stephen Mack Jones</strong></li>
      </ul>
    '''

    def fetch_url(_url):
      raise RuntimeError('boom')

    parsed = NeroAwardOfficialParser().parse(
      finalists,
      'https://wp.nerowolfe.org/htm/literary_awards/nero_award/Nero_Award_Finalists.htm',
      'Nero Award',
      'Nero Award',
      fetch_url=fetch_url)

    self.assertEqual(
      ['Blood for Wine', 'August Snow'],
      [entry['title'] for entry in parsed['entries']])
    self.assertTrue(any(
      'Official Wolfe Pack winners supplement failed: boom' in note
      for note in parsed.get('notes', ())))

  def test_nero_librarything_fallback_parser_smoke(self):
    from parser.nero import NeroAwardLibraryThingParser

    html = '''
      <h2>Winner 1</h2>
      <table>
        <tr><th>Work</th><th>Year</th></tr>
        <tr><td><a href="/work/1">Vanish</a> by <a href="/author/1">Tess Gerritsen</a></td><td>2006</td></tr>
      </table>
      <h2>Finalist 1</h2>
      <table>
        <tr><th>Work</th><th>Year</th></tr>
        <tr><td><a href="/work/2">Kidnapped</a> by <a href="/author/2">Jan Burke</a></td><td>2007</td></tr>
      </table>
    '''

    parsed = NeroAwardLibraryThingParser().parse(
      html,
      'https://www.librarything.com/bookaward/Nero%2BAward',
      'Nero Award',
      'Nero Award')

    self.assertEqual(
      ['Vanish', 'Kidnapped'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'nominee'],
      [entry['result'] for entry in parsed['entries']])

  def test_nero_wikipedia_fallback_parser_smoke(self):
    from parser.nero import NeroAwardWikipediaParser

    html = '''
      <h2><span id="Winners">Winners</span></h2>
      <table class="wikitable">
        <tr><th>Year</th><th>Title</th><th>Author</th><th>Reference</th></tr>
        <tr>
          <th>2006</th>
          <td><i><a href="/wiki/Vanish_(novel)">Vanish</a></i></td>
          <td><a href="/wiki/Tess_Gerritsen">Tess Gerritsen</a></td>
          <td>[1]</td>
        </tr>
        <tr>
          <th>1988<br>1989<br>1990</th>
          <td colspan="2">no award presented</td>
          <td>[2]</td>
        </tr>
      </table>
    '''

    parsed = NeroAwardWikipediaParser().parse(
      html,
      'https://en.wikipedia.org/wiki/Nero_Award',
      'Nero Award',
      'Nero Award')

    self.assertEqual(['Vanish'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['winner'], [
      entry['result'] for entry in parsed['entries']
    ])
    self.assertEqual(
      'https://en.wikipedia.org/wiki/Vanish_(novel)',
      parsed['entries'][0]['source_url'])

  def test_nero_fetcher_falls_back_to_librarything_when_official_is_unusable(self):
    from url_fetcher.nero import UrlFetcherNeroAward

    librarything = '''
      <h2>Winner 1</h2>
      <table>
        <tr><th>Work</th><th>Year</th></tr>
        <tr><td><a href="/work/1">Vanish</a> by <a href="/author/1">Tess Gerritsen</a></td><td>2006</td></tr>
      </table>
    '''

    def fetch_url(url):
      if url == 'https://wp.nerowolfe.org/htm/literary_awards/nero_award/Nero_Award_Finalists.htm':
        return '<html><body><p>No finalist sections here.</p></body></html>'
      if url == 'https://www.librarything.com/bookaward/Nero%2BAward':
        return librarything
      self.fail(url)

    parsed = UrlFetcherNeroAward().fetch_and_parse(fetch_url)

    self.assertEqual(['Vanish'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertTrue(any(
      'Official Wolfe Pack failed:' in note for note in parsed.get('notes', ())
    ))

  def test_nero_fetcher_falls_through_to_wikipedia_when_official_and_librarything_are_unusable(self):
    from url_fetcher.nero import UrlFetcherNeroAward

    wikipedia = '''
      <h2><span id="Winners">Winners</span></h2>
      <table class="wikitable">
        <tr><th>Year</th><th>Title</th><th>Author</th><th>Reference</th></tr>
        <tr>
          <th>2006</th>
          <td><i><a href="/wiki/Vanish_(novel)">Vanish</a></i></td>
          <td><a href="/wiki/Tess_Gerritsen">Tess Gerritsen</a></td>
          <td>[1]</td>
        </tr>
      </table>
    '''

    def fetch_url(url):
      if url == 'https://wp.nerowolfe.org/htm/literary_awards/nero_award/Nero_Award_Finalists.htm':
        return '<html><body><p>No finalist sections here.</p></body></html>'
      if url == 'https://www.librarything.com/bookaward/Nero%2BAward':
        return '<html><body><p>Blocked</p></body></html>'
      if url == 'https://en.wikipedia.org/wiki/Nero_Award':
        return wikipedia
      self.fail(url)

    parsed = UrlFetcherNeroAward().fetch_and_parse(fetch_url)

    self.assertEqual(['Vanish'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertTrue(any(
      'Official Wolfe Pack failed:' in note for note in parsed.get('notes', ())
    ))
    self.assertTrue(any(
      'LibraryThing failed:' in note for note in parsed.get('notes', ())
    ))

  def test_nero_fetcher_source_choices_and_filter_category(self):
    from url_fetcher.nero import UrlFetcherNeroAward

    fetcher = UrlFetcherNeroAward()

    self.assertEqual(
      ('Automatic', 'Official Wolfe Pack', 'LibraryThing', 'Wikipedia'),
      tuple(choice['label'] for choice in fetcher.source_choices()))
    self.assertTrue(any(
      item['label'] == 'Crime, Mystery & Thriller'
      for item in fetcher.get_filter_list()))

  def test_nero_fetcher_registration_order(self):
    from url_fetcher import available_url_fetchers

    source_ids = [fetcher.source_id for fetcher in available_url_fetchers()]

    self.assertLess(
      source_ids.index('hammett_prize'),
      source_ids.index('nero_award'))
    self.assertLess(
      source_ids.index('nero_award'),
      source_ids.index('crime_writers_of_canada_award_novel'))

  def test_strand_librarything_parser_extracts_mystery_novel_rows(self):
    from parser.strand import StrandLibraryThingParser

    html = '''
    <html><body>
      <h2>Winner</h2>
      <table>
        <tr><th>Work</th><th>Category</th><th>Year</th></tr>
        <tr>
          <td>
            <div class="work">
              <span><a href="/work/chaos-kind">The Chaos Kind</a></span>
              <span>by</span>
              <em><a href="/author/barry-eisler">Barry Eisler</a></em>
            </div>
          </td>
          <td><div><span>Best Mystery Novel</span></div></td>
          <td><span>2023</span></td>
        </tr>
        <tr>
          <td><a href="/work/audio">The Audiobook Pick</a> by <a href="/author/audio">A. Narrator</a></td>
          <td>Best Mystery Audiobook</td>
          <td>2023</td>
        </tr>
      </table>
      <h2>Nominees</h2>
      <table>
        <tr><th>Work</th><th>Category</th><th>Year</th></tr>
        <tr>
          <td>
            <span class="outer"><a data-role="title" href="/work/zero-days">Zero Days</a></span>
            by
            <span class="author"><a href="/author/ruth-ware">Ruth Ware</a></span>
          </td>
          <td><span>Best Novel</span></td>
          <td><span>2023</span></td>
        </tr>
        <tr>
          <td><a href="/work/all-the-sinners">All the Sinners Bleed</a> by <a href="/author/s-a-cosby">S. A. Cosby</a></td>
          <td>Mystery Novel</td>
          <td>2023</td>
        </tr>
      </table>
    </body></html>
    '''

    parsed = StrandLibraryThingParser().parse(
      html,
      'https://www.librarything.com/award/1380/The-Strand-Critics-Award',
      'Strand Critics Award - Mystery Novel',
      'Best Mystery Novel',
      ('Mystery Novel', 'Best Novel'))

    self.assertEqual(
      ['The Chaos Kind', 'Zero Days', 'All the Sinners Bleed'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'nominee', 'nominee'],
      [entry['result'] for entry in parsed['entries']])
    self.assertEqual(
      'https://www.librarything.com/work/chaos-kind',
      parsed['entries'][0]['source_url'])
    self.assertFalse(any(
      entry['title'] == 'The Audiobook Pick' for entry in parsed['entries']))

  def test_strand_librarything_parser_extracts_debut_mystery_rows(self):
    from parser.strand import StrandLibraryThingParser

    html = '''
    <html><body>
      <h2>Winner</h2>
      <table>
        <tr><th>Work</th><th>Category</th><th>Year</th></tr>
        <tr>
          <td>
            <div>
              <a href="/work/sympathy">Sympathy for the Devil</a>
              <span>by</span>
              <a href="/author/michael-m-befeler">Michael M. Befeler</a>
            </div>
          </td>
          <td><span>Best Debut Novel</span><script>ignored()</script></td>
          <td><span>2009</span></td>
        </tr>
      </table>
      <h2>Nominee</h2>
      <table>
        <tr><th>Work</th><th>Category</th><th>Year</th></tr>
        <tr>
          <td><a href="/work/in-the-shadow">In the Shadow of Gotham</a> by <a href="/author/stefanie-pintoff">Stefanie Pintoff</a></td>
          <td><div><span>Best Debut Mystery</span></div></td>
          <td>2009</td>
        </tr>
        <tr>
          <td><a href="/work/child-44">Child 44</a> by <a href="/author/tom-rob-smith">Tom Rob Smith</a></td>
          <td><div><span>Best First Novel</span></div><style>.ignore{}</style></td>
          <td>2009</td>
        </tr>
      </table>
    </body></html>
    '''

    parsed = StrandLibraryThingParser().parse(
      html,
      'https://www.librarything.com/award/1380/The-Strand-Critics-Award',
      'Strand Critics Award - Debut Mystery',
      'Best Debut Mystery',
      ('Best Debut Novel', 'Debut Mystery', 'Debut Novel', 'Best First Novel'))

    self.assertEqual(
      ['Sympathy for the Devil', 'In the Shadow of Gotham', 'Child 44'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['2009', '2009.01', '2009.02'],
      [entry['position'] for entry in parsed['entries']])

  def test_strand_fetchers_use_single_librarything_source_and_crime_filter(self):
    from url_fetcher.strand import (
      UrlFetcherStrandDebutMystery,
      UrlFetcherStrandMysteryNovel,
    )

    mystery_fetcher = UrlFetcherStrandMysteryNovel()
    debut_fetcher = UrlFetcherStrandDebutMystery()

    self.assertEqual(
      ({'label': 'Automatic', 'value': 'automatic'},),
      mystery_fetcher.source_choices())
    self.assertEqual(
      ({'label': 'Automatic', 'value': 'automatic'},),
      debut_fetcher.source_choices())
    self.assertTrue(any(
      item['label'] == 'Crime, Mystery & Thriller'
      for item in mystery_fetcher.get_filter_list()))
    self.assertTrue(any(
      item['label'] == 'Crime, Mystery & Thriller'
      for item in debut_fetcher.get_filter_list()))

  def test_strand_fetcher_parse_returns_match_series_false(self):
    from url_fetcher.strand import UrlFetcherStrandMysteryNovel

    html = '''
    <html><body>
      <h2>Winner</h2>
      <table>
        <tr><th>Work</th><th>Category</th><th>Year</th></tr>
        <tr>
          <td><a href="/work/every-cloak">Every Cloak Rolled in Blood</a> by <a href="/author/james-lee-burke">James Lee Burke</a></td>
          <td>Best Mystery Novel</td>
          <td>2022</td>
        </tr>
      </table>
      <h2>Nominee</h2>
      <table>
        <tr><th>Work</th><th>Category</th><th>Year</th></tr>
        <tr>
          <td><a href="/work/the-fervor">The Fervor</a> by <a href="/author/alma-katsu">Alma Katsu</a></td>
          <td>Best Mystery Novel</td>
          <td>2022</td>
        </tr>
      </table>
    </body></html>
    '''

    parsed = UrlFetcherStrandMysteryNovel().fetch_and_parse(lambda _url: html)

    self.assertFalse(parsed['match_series'])
    self.assertEqual(
      ['Every Cloak Rolled in Blood', 'The Fervor'],
      [entry['title'] for entry in parsed['entries']])

  def test_strand_fetcher_registration_order(self):
    from url_fetcher import available_url_fetchers

    source_ids = [fetcher.source_id for fetcher in available_url_fetchers()]

    self.assertLess(
      source_ids.index('nero_award'),
      source_ids.index('strand_critics_award_mystery_novel'))
    self.assertLess(
      source_ids.index('strand_critics_award_mystery_novel'),
      source_ids.index('strand_critics_award_debut_mystery'))
    self.assertLess(
      source_ids.index('strand_critics_award_debut_mystery'),
      source_ids.index('crime_writers_of_canada_award_novel'))

  def test_pulitzer_parser_extracts_fiction_winners_and_finalists(self):
    from parser.pulitzer import PulitzerAwardParser

    html = '''
    <html><body><main>
      <h1>Fiction</h1>
      <div>2026</div>
      <a href="/winners/2026-fiction">2026</a>
      <h2><a href="/winners/daniel-kraus">Angel Down, by Daniel Kraus (Atria Books)</a></h2>
      <p>A description that should not parse.</p>
      <div>Finalists:</div>
      <a href="/finalists/katie-kitamura">Audition, by Katie Kitamura (Riverhead Books)</a>
      <a href="/finalists/torrey-peters">Stag Dance: A Quartet, by Torrey Peters (Random House)</a>
      <a href="/finalists/katie-kitamura">Audition, by Katie Kitamura (Riverhead Books)</a>
    </main></body></html>
    '''

    parsed = PulitzerAwardParser().parse(
      html,
      'https://www.pulitzer.org/prize-winners-by-category/219',
      'Pulitzer Prize - Fiction',
      'Fiction')

    self.assertEqual(
      ['Angel Down', 'Audition', 'Stag Dance: A Quartet'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'nominee', 'nominee'],
      [entry['result'] for entry in parsed['entries']])
    self.assertEqual(
      'https://www.pulitzer.org/winners/daniel-kraus',
      parsed['entries'][0]['source_url'])

  def test_pulitzer_parser_extracts_general_nonfiction_rows(self):
    from parser.pulitzer import PulitzerAwardParser

    html = '''
    <html><body><main>
      <section>
        <span>2026</span>
        <h2>
          <a href="/winners/brian-goldstone">
            There Is No Place for Us: Working and Homeless in America, by Brian Goldstone (Crown)
          </a>
        </h2>
        <p>Finalists:</p>
        <a href="/finalists/haley-cohen-gilliland">
          A Flower Traveled in My Blood: The Incredible True Story of the Grandmothers Who Fought to Find a Stolen Generation of Children, by Haley Cohen Gilliland (Avid Reader Press/Simon &amp; Schuster)
        </a>
        <a href="/finalists/kevin-sack">
          Mother Emanuel: Two Centuries of Race, Resistance, and Forgiveness in One Charleston Church, by Kevin Sack (Crown)
        </a>
      </section>
    </main></body></html>
    '''

    parsed = PulitzerAwardParser().parse(
      html,
      'https://www.pulitzer.org/prize-winners-by-category/223',
      'Pulitzer Prize - General Nonfiction',
      'General Nonfiction')

    self.assertEqual(
      [
        'There Is No Place for Us: Working and Homeless in America',
        'A Flower Traveled in My Blood: The Incredible True Story of the Grandmothers Who Fought to Find a Stolen Generation of Children',
        'Mother Emanuel: Two Centuries of Race, Resistance, and Forgiveness in One Charleston Church',
      ],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['Brian Goldstone', 'Haley Cohen Gilliland', 'Kevin Sack'],
      [entry['author'] for entry in parsed['entries']])

  def test_pulitzer_parser_handles_tied_winners_and_no_award_finalists(self):
    from parser.pulitzer import PulitzerAwardParser

    html = '''
    <html><body><main>
      <div>2023</div>
      <h2><a href="/winners/hernan-diaz">Trust, by Hernan Diaz (Riverhead Books)</a></h2>
      <h2><a href="/winners/barbara-kingsolver">Demon Copperhead, by Barbara Kingsolver (Harper)</a></h2>
      <p>Finalists:</p>
      <a href="/finalists/vauhini-vara">The Immortal King Rao, by Vauhini Vara (W. W. Norton &amp; Company)</a>
      <div>2012</div>
      <h2>No award</h2>
      <p>Finalists:</p>
      <a href="/finalists/denis-johnson">Train Dreams, by Denis Johnson (Farrar, Straus and Giroux)</a>
      <a href="/finalists/karen-russell">Swamplandia!, by Karen Russell (Alfred A. Knopf)</a>
    </main></body></html>
    '''

    parsed = PulitzerAwardParser().parse(
      html,
      'https://www.pulitzer.org/prize-winners-by-category/219',
      'Pulitzer Prize - Fiction',
      'Fiction')

    by_title = {entry['title']: entry for entry in parsed['entries']}
    self.assertEqual('2023', by_title['Trust']['position'])
    self.assertEqual('2023', by_title['Demon Copperhead']['position'])
    self.assertNotIn('No award', by_title)
    self.assertEqual('nominee', by_title['Train Dreams']['result'])
    self.assertEqual('2012.01', by_title['Train Dreams']['position'])

  def test_pulitzer_wikipedia_parser_handles_ties_no_award_and_links(self):
    from parser.pulitzer import PulitzerWikipediaParser

    html = '''
    <html><body>
      <table class="wikitable">
        <tr><th>Year</th><th>Author(s)</th><th>Work</th></tr>
        <tr>
          <td rowspan="3">2023</td>
          <td>Barbara Kingsolver</td>
          <td><a href="/wiki/Demon_Copperhead">Demon Copperhead</a></td>
        </tr>
        <tr><td>Hernan Diaz</td><td>Trust</td></tr>
        <tr><td>Vauhini Vara</td><td>The Immortal King Rao</td></tr>
        <tr><td>2012</td><td></td><td>Not awarded</td></tr>
        <tr><td>Denis Johnson</td><td>Train Dreams</td></tr>
      </table>
    </body></html>
    '''

    parsed = PulitzerWikipediaParser().parse(
      html,
      'https://en.wikipedia.org/wiki/Pulitzer_Prize_for_Fiction',
      'Pulitzer Prize - Fiction',
      'Fiction',
      tied_winner_years={2023: 2})

    by_title = {entry['title']: entry for entry in parsed['entries']}
    self.assertEqual('winner', by_title['Demon Copperhead']['result'])
    self.assertEqual('winner', by_title['Trust']['result'])
    self.assertEqual('2023', by_title['Demon Copperhead']['position'])
    self.assertEqual('2023', by_title['Trust']['position'])
    self.assertEqual('nominee', by_title['The Immortal King Rao']['result'])
    self.assertEqual('nominee', by_title['Train Dreams']['result'])
    self.assertEqual('2012.01', by_title['Train Dreams']['position'])
    self.assertEqual(
      'https://en.wikipedia.org/wiki/Demon_Copperhead',
      by_title['Demon Copperhead']['source_url'])

  def test_pulitzer_britannica_parser_selects_heading_table_winner_only(self):
    from parser.pulitzer import PulitzerBritannicaParser

    html = '''
    <html><body>
      <h2>Poetry</h2>
      <table>
        <tr><th>Year</th><th>Title</th><th>Author</th></tr>
        <tr><td>2020</td><td>Wrong Table</td><td>Wrong Author</td></tr>
      </table>
      <h2>General Nonfiction</h2>
      <table>
        <tr><th>Year</th><th>Title</th><th>Author</th></tr>
        <tr>
          <td rowspan="2">2020</td>
          <td><a href="/biography/Anne-Boyer">The Undying</a></td>
          <td>Anne Boyer</td>
        </tr>
        <tr><td>The End of the Myth</td><td>Greg Grandin</td></tr>
        <tr><td>2012</td><td>No award</td><td></td></tr>
      </table>
    </body></html>
    '''

    parsed = PulitzerBritannicaParser().parse(
      html,
      'https://www.britannica.com/topic/Pulitzer-Prize',
      'Pulitzer Prize - General Nonfiction',
      'General Nonfiction',
      table_heading='General Nonfiction')

    self.assertEqual(
      ['The Undying', 'The End of the Myth'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'winner'],
      [entry['result'] for entry in parsed['entries']])
    self.assertEqual(
      ['2020', '2020'],
      [entry['position'] for entry in parsed['entries']])
    self.assertIn('winner-only', parsed['notes'][0])
    self.assertEqual(
      'https://www.britannica.com/biography/Anne-Boyer',
      parsed['entries'][0]['source_url'])

  def test_pulitzer_fetchers_metadata_and_source_choices(self):
    from url_fetcher.pulitzer import (
      UrlFetcherPulitzerFiction,
      UrlFetcherPulitzerGeneralNonfiction,
    )

    fiction = UrlFetcherPulitzerFiction()
    nonfiction = UrlFetcherPulitzerGeneralNonfiction()

    self.assertEqual(
      (
        {'label': 'Automatic', 'value': 'automatic'},
        {'label': 'Official Pulitzer', 'value': 0},
        {'label': 'Wikipedia', 'value': 1},
        {'label': 'Britannica', 'value': 2},
      ),
      fiction.source_choices())
    self.assertEqual(
      (
        {'label': 'Automatic', 'value': 'automatic'},
        {'label': 'Official Pulitzer', 'value': 0},
        {'label': 'Wikipedia', 'value': 1},
        {'label': 'Britannica', 'value': 2},
      ),
      nonfiction.source_choices())
    self.assertEqual(
      {'Literary & General Fiction', 'Regional & National Awards'},
      {item['label'] for item in fiction.get_filter_list()})
    self.assertEqual(
      {'Nonfiction', 'Regional & National Awards'},
      {item['label'] for item in nonfiction.get_filter_list()})

  def test_pulitzer_fetcher_parse_returns_match_series_false(self):
    from url_fetcher.pulitzer import UrlFetcherPulitzerFiction

    html = '''
    <html><body><main>
      <div>2025</div>
      <h2><a href="/winners/percival-everett">James, by Percival Everett (Doubleday)</a></h2>
      <p>Finalists:</p>
      <a href="/finalists/gayl-jones">The Unicorn Woman, by Gayl Jones (Beacon Press)</a>
    </main></body></html>
    '''

    parsed = UrlFetcherPulitzerFiction().fetch_and_parse(lambda _url: html)

    self.assertFalse(parsed['match_series'])
    self.assertEqual(
      ['James', 'The Unicorn Woman'],
      [entry['title'] for entry in parsed['entries']])

  def test_pulitzer_fetcher_falls_back_to_wikipedia_on_cloudflare(self):
    from url_fetcher.pulitzer import (
      PULITZER_FICTION_URL,
      PULITZER_FICTION_WIKIPEDIA_URL,
      UrlFetcherPulitzerFiction,
    )

    cloudflare_html = '''
    <html>
      <head><title>Just a moment...</title></head>
      <body><p>Cloudflare</p></body>
    </html>
    '''
    wikipedia_html = '''
    <html><body>
      <table>
        <tr><th>Year</th><th>Author</th><th>Work</th></tr>
        <tr>
          <td>2025</td>
          <td>Percival Everett</td>
          <td><a href="/wiki/James_(novel)">James</a></td>
        </tr>
      </table>
    </body></html>
    '''

    def fetch_url(url):
      if url == PULITZER_FICTION_URL:
        return cloudflare_html
      if url == PULITZER_FICTION_WIKIPEDIA_URL:
        return wikipedia_html
      self.fail('Britannica should not be fetched after usable Wikipedia data')

    parsed = UrlFetcherPulitzerFiction().fetch_and_parse(fetch_url)

    self.assertEqual(['James'], [entry['title'] for entry in parsed['entries']])
    self.assertEqual(PULITZER_FICTION_WIKIPEDIA_URL, parsed['source_url'])
    self.assertIn('Official Pulitzer failed', parsed['notes'][0])
    self.assertFalse(parsed['match_series'])

  def test_pulitzer_fetcher_falls_back_to_britannica_after_unusable_wikipedia(self):
    from url_fetcher.pulitzer import (
      PULITZER_BRITANNICA_URL,
      PULITZER_GENERAL_NONFICTION_URL,
      PULITZER_GENERAL_NONFICTION_WIKIPEDIA_URL,
      UrlFetcherPulitzerGeneralNonfiction,
    )

    cloudflare_html = '''
    <html>
      <head><title>Just a moment...</title></head>
      <body><p>Cloudflare</p></body>
    </html>
    '''
    britannica_html = '''
    <html><body>
      <h2>General Nonfiction</h2>
      <table>
        <tr><th>Year</th><th>Title</th><th>Author</th></tr>
        <tr><td>2026</td><td><a href="/biography/Brian-Goldstone">There Is No Place for Us</a></td><td>Brian Goldstone</td></tr>
      </table>
    </body></html>
    '''

    def fetch_url(url):
      if url == PULITZER_GENERAL_NONFICTION_URL:
        return cloudflare_html
      if url == PULITZER_GENERAL_NONFICTION_WIKIPEDIA_URL:
        return '<html><body><p>No usable table</p></body></html>'
      if url == PULITZER_BRITANNICA_URL:
        return britannica_html
      self.fail('Unexpected Pulitzer fallback URL: %s' % url)

    parsed = UrlFetcherPulitzerGeneralNonfiction().fetch_and_parse(fetch_url)

    self.assertEqual(
      ['There Is No Place for Us'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(PULITZER_BRITANNICA_URL, parsed['source_url'])
    self.assertTrue(any(note.startswith('Official Pulitzer failed') for note in parsed['notes']))
    self.assertTrue(any(note.startswith('Wikipedia failed') for note in parsed['notes']))
    self.assertTrue(any('winner-only' in note for note in parsed['notes']))

  def test_pulitzer_parser_rejects_cloudflare_challenge_page(self):
    from parser.pulitzer import PulitzerAwardParser

    html = '''
    <html>
      <head><title>Just a moment...</title></head>
      <body>
        <script src="/cdn-cgi/challenge-platform/h/g/orchestrate/chl_page/v1"></script>
        <p>Cloudflare</p>
      </body>
    </html>
    '''

    with self.assertRaisesRegex(ValueError, 'Cloudflare challenge'):
      PulitzerAwardParser().parse(
        html,
        'https://www.pulitzer.org/prize-winners-by-category/219',
        'Pulitzer Prize - Fiction',
        'Fiction')

  def test_pulitzer_fetcher_registration_order(self):
    from url_fetcher import available_url_fetchers

    source_ids = [fetcher.source_id for fetcher in available_url_fetchers()]

    self.assertLess(
      source_ids.index('sword_and_laser_book_list'),
      source_ids.index('pulitzer_prize_fiction'))
    self.assertLess(
      source_ids.index('pulitzer_prize_fiction'),
      source_ids.index('pulitzer_prize_general_nonfiction'))
    self.assertLess(
      source_ids.index('pulitzer_prize_general_nonfiction'),
      source_ids.index('hugo_awards_novel'))

  def test_national_book_award_parser_extracts_winners_and_finalists_only(self):
    from parser.national_book_award import NationalBookAwardParser

    html = '''
    <html><body>
      <div class="category-winners">
        <div class="winner-book">
          <article class="winner-book-item">
            <div class="book-data">
              <h1><a href="/books/james/">James</a></h1>
              <h2>by Percival Everett</h2>
            </div>
          </article>
        </div>
        <div class="finalists-wrapper">
          <div class="finalist-books">
            <figure class="winner-list">
              <figcaption>
                <h1><a href="/books/headshot/">Headshot</a></h1>
                <p class="author">by Rita Bullwinkel</p>
              </figcaption>
            </figure>
            <figure class="winner-list">
              <figcaption>
                <h1><a href="/books/finalists-not-announced/">Finalists Not Announced</a></h1>
                <p class="author"></p>
              </figcaption>
            </figure>
            <figure class="winner-list">
              <figcaption>
                <h1><a href="/books/blank-author/">Blank Author</a></h1>
                <p class="author"></p>
              </figcaption>
            </figure>
          </div>
        </div>
        <div class="blue long-list">
          <figure>
            <figcaption>
              <a href="/books/longlist/">A Longlisted Book</a>
              <p class="author">by Someone Else</p>
            </figcaption>
          </figure>
        </div>
      </div>
    </body></html>
    '''

    parsed = NationalBookAwardParser().parse(
      html,
      'https://www.nationalbook.org/awards-prizes/national-book-awards-2024/?cat=fiction',
      'National Book Award - Fiction',
      'Fiction')

    self.assertEqual(
      ['James', 'Headshot'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'nominee'],
      [entry['result'] for entry in parsed['entries']])
    self.assertEqual(
      'https://www.nationalbook.org/books/james/',
      parsed['entries'][0]['source_url'])

  def test_national_book_award_wikipedia_parser_tables_and_nonfiction_filter(self):
    from parser.national_book_award import NationalBookAwardWikipediaParser

    html = '''
    <html><body>
      <h2>Recipients</h2>
      <table class="wikitable">
        <tr><th>Year</th><th>Author</th><th>Book</th><th>Status</th></tr>
        <tr>
          <td rowspan="2">2025</td>
          <td>Omar El Akkad</td>
          <td><a href="/wiki/One_Day,_Everyone_Will_Have_Always_Been_Against_This">One Day, Everyone Will Have Always Been Against This</a></td>
          <td>Winner</td>
        </tr>
        <tr>
          <td>Julia Ioffe</td>
          <td>Motherland</td>
          <td>Finalist</td>
        </tr>
      </table>
      <h3>National Book Award for Nonfiction: History and Biography, winners and finalists</h3>
      <table class="wikitable">
        <tr><th>Year</th><th>Author</th><th>Book</th></tr>
        <tr><td>1975</td><td>Wrong Author</td><td>Wrong Subcategory</td></tr>
      </table>
    </body></html>
    '''

    parsed = NationalBookAwardWikipediaParser().parse(
      html,
      'https://en.wikipedia.org/wiki/National_Book_Award_for_Nonfiction',
      'National Book Award - Nonfiction',
      'Nonfiction')

    self.assertEqual(
      ['One Day, Everyone Will Have Always Been Against This', 'Motherland'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'nominee'],
      [entry['result'] for entry in parsed['entries']])
    self.assertFalse(any(
      entry['title'] == 'Wrong Subcategory' for entry in parsed['entries']))

  def test_national_book_award_fetchers_metadata_source_choices_and_ypl(self):
    from url_fetcher.national_book_award import (
      UrlFetcherNationalBookAwardFiction,
      UrlFetcherNationalBookAwardNonfiction,
      UrlFetcherNationalBookAwardYoungPeoplesLiterature,
    )

    fiction = UrlFetcherNationalBookAwardFiction()
    nonfiction = UrlFetcherNationalBookAwardNonfiction()
    ypl = UrlFetcherNationalBookAwardYoungPeoplesLiterature()

    self.assertEqual(
      (
        {'label': 'Automatic', 'value': 'automatic'},
        {'label': 'Official National Book Foundation', 'value': 0},
        {'label': 'Wikipedia', 'value': 1},
      ),
      fiction.source_choices())
    self.assertEqual(
      {'Literary & General Fiction', 'Regional & National Awards'},
      {item['label'] for item in fiction.get_filter_list()})
    self.assertEqual(
      {'Nonfiction', 'Regional & National Awards'},
      {item['label'] for item in nonfiction.get_filter_list()})
    self.assertEqual(
      {"Young Adult & Children's Literature", 'Regional & National Awards'},
      {item['label'] for item in ypl.get_filter_list()})

  def test_national_book_award_fetcher_discovers_years_and_falls_back(self):
    from url_fetcher.national_book_award import (
      NATIONAL_BOOK_AWARD_FICTION_WIKIPEDIA_URL,
      NATIONAL_BOOK_AWARD_YEARS_URL,
      UrlFetcherNationalBookAwardFiction,
    )

    years_html = '''
    <html><body>
      <a href="https://www.nationalbook.org/awards-prizes/national-book-awards-2024/">2024</a>
      <option value="https://www.nationalbook.org/awards-prizes/national-book-awards-2024/">2024</option>
      <a href="https://www.nationalbook.org/awards-prizes/national-book-awards-2025/">2025</a>
    </body></html>
    '''
    year_html = '''
    <html><body>
      <div class="winner-book">
        <article class="winner-book-item">
          <div class="book-data">
            <h1><a href="/books/the-true-true-story/">The True True Story of Raja the Gullible (and His Mother)</a></h1>
            <h2>by Rabih Alameddine</h2>
          </div>
        </article>
      </div>
    </body></html>
    '''
    wikipedia_html = '''
    <html><body>
      <table>
        <tr><th>Year</th><th>Author</th><th>Book</th></tr>
        <tr><td>2025</td><td>Rabih Alameddine</td><td>The True True Story of Raja the Gullible (and His Mother)</td></tr>
      </table>
    </body></html>
    '''
    calls = []

    def fetch_url(url):
      calls.append(url)
      if url == NATIONAL_BOOK_AWARD_YEARS_URL:
        return years_html
      if url.endswith('/national-book-awards-2024/?cat=fiction'):
        return '<html><body><p>No entries here</p></body></html>'
      if url.endswith('/national-book-awards-2025/?cat=fiction'):
        return year_html
      if url == NATIONAL_BOOK_AWARD_FICTION_WIKIPEDIA_URL:
        return wikipedia_html
      self.fail('Unexpected National Book Award URL: %s' % url)

    parsed = UrlFetcherNationalBookAwardFiction().fetch_and_parse(fetch_url)

    self.assertFalse(parsed['match_series'])
    self.assertEqual(
      ['The True True Story of Raja the Gullible (and His Mother)'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(1, calls.count(
      'https://www.nationalbook.org/awards-prizes/national-book-awards-2024/?cat=fiction'))

    def fallback_fetch(url):
      if url == NATIONAL_BOOK_AWARD_YEARS_URL:
        return '<html><body>No year links</body></html>'
      if url == NATIONAL_BOOK_AWARD_FICTION_WIKIPEDIA_URL:
        return wikipedia_html
      self.fail('Unexpected fallback URL: %s' % url)

    fallback = UrlFetcherNationalBookAwardFiction().fetch_and_parse(fallback_fetch)

    self.assertEqual(NATIONAL_BOOK_AWARD_FICTION_WIKIPEDIA_URL, fallback['source_url'])
    self.assertTrue(any(
      note.startswith('Official National Book Foundation failed')
      for note in fallback['notes']))

  def test_national_book_award_fetcher_registration_order(self):
    from url_fetcher import available_url_fetchers

    source_ids = [fetcher.source_id for fetcher in available_url_fetchers()]

    self.assertLess(
      source_ids.index('pulitzer_prize_general_nonfiction'),
      source_ids.index('national_book_award_fiction'))
    self.assertLess(
      source_ids.index('national_book_award_fiction'),
      source_ids.index('national_book_award_nonfiction'))
    self.assertLess(
      source_ids.index('national_book_award_nonfiction'),
      source_ids.index('national_book_award_young_peoples_literature'))
    self.assertLess(
      source_ids.index('national_book_award_young_peoples_literature'),
      source_ids.index('hugo_awards_novel'))

  def test_baillie_gifford_parser_extracts_winners_and_shortlist_only(self):
    from parser.baillie_gifford import BaillieGiffordPrizeParser

    html = '''
    <html><body>
      <main>
        <section>
          <h2>The winner</h2>
          <a class="winner-box" href="/books-and-authors/how-to-end-a-story-by">
            <h3 class="winner-box__title">
              <p>How to End a Story</p>
              <p>Collected Diaries</p>
            </h3>
            <p class="winner-box__author">Helen Garner</p>
          </a>
        </section>
        <section>
          <h2>The shortlist</h2>
          <article class="listing">
            <a href="/books-and-authors/electric-spark-by-frances-wilson">
              <p class="listing__meta">2025</p>
              <h2 class="listing__title">Electric Spark</h2>
              <p class="listing__sub">Frances Wilson</p>
            </a>
          </article>
        </section>
        <section>
          <h2>The longlist</h2>
          <article class="listing">
            <a href="/books-and-authors/longlisted-book-by">
              <h2 class="listing__title">Longlisted Book</h2>
              <p class="listing__sub">List Author</p>
            </a>
          </article>
        </section>
      </main>
    </body></html>
    '''
    detail_html = '''
    <html><body>
      <main>
        <header>
          <span class="h-3">
            <h1>How to End a Story</h1>
            <p>Collected Diaries</p>
          </span>
          <p class="step-4">Helen Garner</p>
        </header>
      </main>
    </body></html>
    '''
    calls = []

    def fetch_url(url):
      calls.append(url)
      if url.endswith('/how-to-end-a-story-by'):
        return detail_html
      raise RuntimeError('detail unavailable')

    parsed = BaillieGiffordPrizeParser().parse(
      html,
      'https://www.thebailliegiffordprize.co.uk/year-by-year/2025',
      'Baillie Gifford Prize',
      'Non-Fiction',
      fetch_url=fetch_url)

    self.assertEqual(
      ['How to End a Story: Collected Diaries', 'Electric Spark'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'shortlisted'],
      [entry['result'] for entry in parsed['entries']])
    self.assertEqual(['2025', '2025.01'], [entry['position'] for entry in parsed['entries']])
    self.assertFalse(any(entry['title'] == 'Longlisted Book' for entry in parsed['entries']))
    self.assertIn('/books-and-authors/electric-spark-by-frances-wilson', parsed['entries'][1]['source_url'])
    self.assertTrue(any(note.startswith('Baillie Gifford detail page failed') for note in parsed['notes']))

  def test_baillie_gifford_wikipedia_parser_handles_winner_and_shortlist(self):
    from parser.baillie_gifford import BaillieGiffordWikipediaParser

    html = '''
    <html><body>
      <table class="wikitable">
        <tr><th>Year</th><th>Author</th><th>Book</th><th>Result</th></tr>
        <tr>
          <td rowspan="2">1999</td>
          <td>Antony Beevor</td>
          <td><a href="/wiki/Stalingrad_(Beevor_book)">Stalingrad</a></td>
          <td>Winner</td>
        </tr>
        <tr>
          <td>John Diamond</td>
          <td>Because Cowards Get Cancer Too</td>
          <td>Shortlist</td>
        </tr>
      </table>
    </body></html>
    '''

    parsed = BaillieGiffordWikipediaParser().parse(
      html,
      'https://en.wikipedia.org/wiki/Baillie_Gifford_Prize',
      'Baillie Gifford Prize',
      'Non-Fiction')

    self.assertEqual(['Stalingrad', 'Because Cowards Get Cancer Too'], [
      entry['title'] for entry in parsed['entries']])
    self.assertEqual(['winner', 'shortlisted'], [
      entry['result'] for entry in parsed['entries']])
    self.assertEqual(
      'https://en.wikipedia.org/wiki/Stalingrad_(Beevor_book)',
      parsed['entries'][0]['source_url'])

  def test_baillie_gifford_fetcher_discovers_years_and_falls_back(self):
    from url_fetcher.baillie_gifford import (
      BAILLIE_GIFFORD_WIKIPEDIA_URL,
      BAILLIE_GIFFORD_YEARS_URL,
      UrlFetcherBaillieGiffordPrize,
    )

    years_html = '''
    <html><body>
      <a href="/year-by-year/2025">2025</a>
      <a href="/year-by-year/25">Winner of Winners</a>
      <a href="/year-by-year/1999">1999</a>
    </body></html>
    '''
    year_html = '''
    <html><body>
      <section>
        <h2>The winner</h2>
        <a class="winner-box" href="/books-and-authors/stalingrad-by-antony-beevor">
          <h3 class="winner-box__title">Stalingrad</h3>
          <p class="winner-box__author">Antony Beevor</p>
        </a>
      </section>
    </body></html>
    '''
    detail_html = '''
    <html><body>
      <main><header>
        <span class="h-3"><h1>Stalingrad</h1></span>
        <p class="step-4">Antony Beevor</p>
      </header></main>
    </body></html>
    '''
    wikipedia_html = '''
    <html><body>
      <table><tr><th>Year</th><th>Author</th><th>Book</th></tr>
      <tr><td>1999</td><td>Antony Beevor</td><td>Stalingrad</td></tr></table>
    </body></html>
    '''

    def fetch_url(url):
      if url == BAILLIE_GIFFORD_YEARS_URL:
        return years_html
      if url.endswith('/year-by-year/2025'):
        return '<html><body>No entries yet</body></html>'
      if url.endswith('/year-by-year/1999'):
        return year_html
      if url.endswith('/books-and-authors/stalingrad-by-antony-beevor'):
        return detail_html
      if url == BAILLIE_GIFFORD_WIKIPEDIA_URL:
        return wikipedia_html
      self.fail('Unexpected Baillie Gifford URL: %s' % url)

    parsed = UrlFetcherBaillieGiffordPrize().fetch_and_parse(fetch_url)

    self.assertFalse(parsed['match_series'])
    self.assertEqual(['Stalingrad'], [entry['title'] for entry in parsed['entries']])
    self.assertEqual('Non-Fiction', parsed['entries'][0]['category'])

    def fallback_fetch(url):
      if url == BAILLIE_GIFFORD_YEARS_URL:
        return '<html><body>No year links</body></html>'
      if url == BAILLIE_GIFFORD_WIKIPEDIA_URL:
        return wikipedia_html
      self.fail('Unexpected fallback URL: %s' % url)

    fallback = UrlFetcherBaillieGiffordPrize().fetch_and_parse(fallback_fetch)

    self.assertEqual(BAILLIE_GIFFORD_WIKIPEDIA_URL, fallback['source_url'])
    self.assertTrue(any(
      note.startswith('Official Baillie Gifford failed')
      for note in fallback['notes']))

  def test_baillie_gifford_fetcher_metadata_and_registration_order(self):
    from url_fetcher import available_url_fetchers
    from url_fetcher.baillie_gifford import UrlFetcherBaillieGiffordPrize

    fetcher = UrlFetcherBaillieGiffordPrize()

    self.assertEqual(
      (
        {'label': 'Automatic', 'value': 'automatic'},
        {'label': 'Official Baillie Gifford', 'value': 0},
        {'label': 'Wikipedia', 'value': 1},
      ),
      fetcher.source_choices())
    self.assertEqual(
      {'Nonfiction', 'Regional & National Awards'},
      {item['label'] for item in fetcher.get_filter_list()})

    source_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertLess(
      source_ids.index('national_book_award_young_peoples_literature'),
      source_ids.index('baillie_gifford_prize'))
    self.assertLess(
      source_ids.index('baillie_gifford_prize'),
      source_ids.index('hugo_awards_novel'))

  def test_nbcc_official_parser_handles_legacy_general_nonfiction_page(self):
    from parser.nbcc import NBCCAwardParser

    html = '''
    <html><body>
      <div class="content-regular">
        <h3>Fiction Winner</h3>
        <ul><li>Wrong Writer, <em>Wrong Book</em> (Wrong Press)</li></ul>
        <h3>General Nonfiction Winner</h3>
        <ul>
          <li>Maxine Hong Kingston, <em>The Woman Warrior: Memoirs of a Girlhood Among Ghosts</em> (Knopf)</li>
        </ul>
        <h3>General Nonfiction Finalists</h3>
        <ul>
          <li>George Dangerfield, <em>The Damnable Question: A Study in Anglo-Irish Relations</em> (Atlantic-Little, Brown)</li>
          <li>Irving Howe with Kenneth Libo, <em>World of Our Fathers</em> (Harcourt)</li>
        </ul>
        <h3>Criticism Winner</h3>
        <ul><li>Wrong Critic, <em>Wrong Critical Book</em> (Press)</li></ul>
      </div>
    </body></html>
    '''

    parsed = NBCCAwardParser().parse(
      html,
      'https://www.bookcritics.org/past-awards/1976/',
      'National Book Critics Circle Award - Nonfiction',
      'Nonfiction',
      ('General Nonfiction',))

    self.assertEqual(
      ['The Woman Warrior: Memoirs of a Girlhood Among Ghosts',
       'The Damnable Question: A Study in Anglo-Irish Relations',
       'World of Our Fathers'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'nominee', 'nominee'],
      [entry['result'] for entry in parsed['entries']])
    self.assertEqual(['1976', '1976.01', '1976.02'], [
      entry['position'] for entry in parsed['entries']])

  def test_nbcc_official_parser_handles_modern_sections_and_ignores_longlists(self):
    from parser.nbcc import NBCCAwardParser

    html = '''
    <html><body>
      <ul class="award-year-list">
        <h3>Nonfiction</h3>
        <li class="Longlist">Ignored Writer, <em>Ignored Longlist Book</em> (Press)</li>
        <li class="Finalist">Barbara Demick, <em>Daughters of the Bamboo Grove: From China to America, a True Story</em> (Random House)</li>
        <li class="Winner">Greg Grandin, <em>America, América: A New History of the New World</em> (Penguin Press)</li>
      </ul>
      <ul class="award-year-list">
        <h3>Criticism</h3>
        <li class="Finalist">Yoko Tawada, translated from the Japanese by Lisa Hofmann-Kuroda, <em>Exophony: Voyages Outside the Mother Tongue</em> (New Directions)</li>
        <li class="Winner">Quinn Slobodian, <em>Hayek's Bastards: Race, Gold, IQ, and the Capitalism of the Far Right</em> (Zone Books)</li>
        <li class="Longlist">Long Writer, <em>Long Critical Book</em> (Press)</li>
      </ul>
      <ul class="award-year-list">
        <h3>Nona Balakian Citation for Excellence in Reviewing</h3>
        <li class="Winner">Wrong Person</li>
      </ul>
    </body></html>
    '''

    nonfiction = NBCCAwardParser().parse(
      html,
      'https://www.bookcritics.org/past-awards/2025/',
      'National Book Critics Circle Award - Nonfiction',
      'Nonfiction',
      ('General Nonfiction',))
    criticism = NBCCAwardParser().parse(
      html,
      'https://www.bookcritics.org/past-awards/2025/',
      'National Book Critics Circle Award - Criticism',
      'Criticism')

    self.assertEqual(
      ['America, América: A New History of the New World',
       'Daughters of the Bamboo Grove: From China to America, a True Story'],
      [entry['title'] for entry in nonfiction['entries']])
    self.assertEqual(['winner', 'nominee'], [
      entry['result'] for entry in nonfiction['entries']])
    self.assertFalse(any(entry['title'] == 'Ignored Longlist Book'
                         for entry in nonfiction['entries']))
    self.assertEqual(
      ['Hayek\'s Bastards: Race, Gold, IQ, and the Capitalism of the Far Right',
       'Exophony: Voyages Outside the Mother Tongue'],
      [entry['title'] for entry in criticism['entries']])
    self.assertEqual(['Quinn Slobodian', 'Yoko Tawada'], [
      entry['author'] for entry in criticism['entries']])

  def test_nbcc_wikipedia_parser_handles_rowspans_and_links(self):
    from parser.nbcc import NBCCWikipediaParser

    html = '''
    <html><body>
      <table class="wikitable">
        <tr><th>Year</th><th>Author</th><th>Book</th><th>Result</th></tr>
        <tr>
          <td rowspan="2">2025</td>
          <td>Greg Grandin</td>
          <td><a href="/wiki/America,_Am%C3%A9rica">America, América</a></td>
          <td>Winner</td>
        </tr>
        <tr>
          <td>Barbara Demick</td>
          <td>Daughters of the Bamboo Grove</td>
          <td>Finalist</td>
        </tr>
      </table>
    </body></html>
    '''

    parsed = NBCCWikipediaParser().parse(
      html,
      'https://en.wikipedia.org/wiki/National_Book_Critics_Circle_Award_for_Nonfiction',
      'National Book Critics Circle Award - Nonfiction',
      'Nonfiction')

    self.assertEqual(['America, América', 'Daughters of the Bamboo Grove'], [
      entry['title'] for entry in parsed['entries']])
    self.assertEqual(['winner', 'nominee'], [
      entry['result'] for entry in parsed['entries']])
    self.assertEqual(
      'https://en.wikipedia.org/wiki/America,_Am%C3%A9rica',
      parsed['entries'][0]['source_url'])

  def test_nbcc_fetcher_discovers_years_next_links_and_falls_back(self):
    from url_fetcher.nbcc import (
      NBCC_NONFICTION_WIKIPEDIA_URL,
      NBCC_PAST_AWARDS_URL,
      UrlFetcherNBCCNonfiction,
    )

    archive_html = '''
    <html><body>
      <select>
        <option value="https://www.bookcritics.org/past-awards/2024/">2024</option>
      </select>
    </body></html>
    '''
    year_2024 = '''
    <html><body>
      <ul class="award-year-list">
        <h3>Nonfiction</h3>
        <li class="Winner">Alexei Navalny, <em>Patriot: A Memoir</em> (Knopf)</li>
      </ul>
      <nav><a rel="next" href="https://www.bookcritics.org/past-awards/2025/">2025</a></nav>
    </body></html>
    '''
    year_2025 = '''
    <html><body>
      <ul class="award-year-list">
        <h3>Nonfiction</h3>
        <li class="Winner">Greg Grandin, <em>America, América</em> (Penguin)</li>
        <li class="Longlist">Wrong Writer, <em>Wrong Longlist</em> (Press)</li>
      </ul>
    </body></html>
    '''
    wikipedia_html = '''
    <html><body>
      <table><tr><th>Year</th><th>Author</th><th>Book</th></tr>
      <tr><td>2025</td><td>Greg Grandin</td><td>America, América</td></tr></table>
    </body></html>
    '''
    calls = []

    def fetch_url(url):
      calls.append(url)
      if url == NBCC_PAST_AWARDS_URL:
        return archive_html
      if url == 'https://www.bookcritics.org/past-awards/2024/':
        return year_2024
      if url == 'https://www.bookcritics.org/past-awards/2025/':
        return year_2025
      if url == NBCC_NONFICTION_WIKIPEDIA_URL:
        return wikipedia_html
      self.fail('Unexpected NBCC URL: %s' % url)

    parsed = UrlFetcherNBCCNonfiction().fetch_and_parse(fetch_url)

    self.assertFalse(parsed['match_series'])
    self.assertEqual(['Patriot: A Memoir', 'America, América'], [
      entry['title'] for entry in parsed['entries']])
    self.assertIn('https://www.bookcritics.org/past-awards/2025/', calls)
    self.assertFalse(any(entry['title'] == 'Wrong Longlist'
                         for entry in parsed['entries']))

    def fallback_fetch(url):
      if url == NBCC_PAST_AWARDS_URL:
        return '<html><body>No years</body></html>'
      if url == NBCC_NONFICTION_WIKIPEDIA_URL:
        return wikipedia_html
      self.fail('Unexpected fallback URL: %s' % url)

    fallback = UrlFetcherNBCCNonfiction().fetch_and_parse(fallback_fetch)

    self.assertEqual(NBCC_NONFICTION_WIKIPEDIA_URL, fallback['source_url'])
    self.assertTrue(any(
      note.startswith('Official NBCC failed') for note in fallback['notes']))

  def test_nbcc_fetcher_metadata_and_registration_order(self):
    from url_fetcher import available_url_fetchers
    from url_fetcher.nbcc import UrlFetcherNBCCCriticism, UrlFetcherNBCCNonfiction

    nonfiction = UrlFetcherNBCCNonfiction()
    criticism = UrlFetcherNBCCCriticism()

    self.assertEqual(
      (
        {'label': 'Automatic', 'value': 'automatic'},
        {'label': 'Official NBCC', 'value': 0},
        {'label': 'Wikipedia', 'value': 1},
      ),
      nonfiction.source_choices())
    self.assertEqual(
      {'Nonfiction', 'Regional & National Awards'},
      {item['label'] for item in nonfiction.get_filter_list()})
    self.assertEqual(
      {'Nonfiction', 'Regional & National Awards'},
      {item['label'] for item in criticism.get_filter_list()})

    source_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertLess(
      source_ids.index('baillie_gifford_prize'),
      source_ids.index('nbcc_award_nonfiction'))
    self.assertLess(
      source_ids.index('nbcc_award_nonfiction'),
      source_ids.index('nbcc_award_criticism'))
    self.assertLess(
      source_ids.index('nbcc_award_criticism'),
      source_ids.index('hugo_awards_novel'))

  def test_pen_america_parser_handles_landing_and_annual_sections(self):
    from parser.pen_america import PENAwardConfig, PENAmericaAwardParser

    config = PENAwardConfig(
      'PEN/John Kenneth Galbraith Award for Nonfiction',
      'Nonfiction',
      ('PEN/John Kenneth Galbraith Award for Nonfiction',),
      'title_author')
    landing_html = '''
    <html><body>
      <h1>PEN/John Kenneth Galbraith Award for Nonfiction</h1>
      <h2>Current Winner</h2>
      <p><a href="/book/current">2026, The Current History, Ada Writer (Press)</a></p>
      <h2>Previous Winners</h2>
      <table>
        <tr><th>Year</th><th>Title</th><th>Author</th></tr>
        <tr><td>2024</td><td><a href="/book/past">Past Book</a></td><td>Past Author</td></tr>
      </table>
    </body></html>
    '''
    annual_html = '''
    <html><body>
      <h2>PEN/John Kenneth Galbraith Award for Nonfiction</h2>
      <h3>Finalists</h3>
      <ul>
        <li><a href="/book/finalist">Finalist Book, Finalist Author (Press)</a></li>
        <li>Withdrawn Book, Withdrawn Author (withdrawn)</li>
      </ul>
      <h3>Longlist</h3>
      <ul><li>Longlisted Book, Long Author</li></ul>
    </body></html>
    '''

    parsed = PENAmericaAwardParser().parse(
      (
        ('https://pen.org/literary-awards/pen-galbraith-award-for-nonfiction/', landing_html, 'landing'),
        ('https://pen.org/2026-pen-america-literary-awards-finalists/', annual_html, 'annual'),
      ),
      'https://pen.org/literary-awards/pen-galbraith-award-for-nonfiction/',
      'PEN/John Kenneth Galbraith Award for Nonfiction',
      config)

    self.assertEqual(
      ['Past Book', 'The Current History', 'Finalist Book'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(['winner', 'winner', 'nominee'], [
      entry['result'] for entry in parsed['entries']])
    self.assertEqual(['2024', '2026', '2026.01'], [
      entry['position'] for entry in parsed['entries']])
    self.assertIn('/book/finalist', parsed['entries'][2]['source_url'])
    self.assertFalse(any(entry['title'] == 'Longlisted Book'
                         for entry in parsed['entries']))
    self.assertTrue(any('Skipped withdrawn PEN America' in note
                        for note in parsed['notes']))

  def test_pen_america_parser_handles_author_title_history_and_tied_winners(self):
    from parser.pen_america import PENAwardConfig, PENAmericaAwardParser

    config = PENAwardConfig(
      'PEN Open Book Award',
      'Book',
      ('PEN Open Book Award',),
      'author_title')
    html = '''
    <html><body>
      <h1>PEN Open Book Award</h1>
      <p>2025, First Author, Shared Winner One (Press)</p>
      <p>2025, Second Author, Shared Winner Two (Press)</p>
    </body></html>
    '''

    parsed = PENAmericaAwardParser().parse(
      html,
      'https://pen.org/literary-awards/pen-open-book-award/',
      'PEN Open Book Award',
      config)

    self.assertEqual(['Shared Winner One', 'Shared Winner Two'], [
      entry['title'] for entry in parsed['entries']])
    self.assertEqual(['First Author', 'Second Author'], [
      entry['author'] for entry in parsed['entries']])
    self.assertEqual(['2025', '2025'], [
      entry['position'] for entry in parsed['entries']])

  def test_pen_america_annual_parser_supports_configured_awards(self):
    from parser.pen_america import PENAwardConfig, PENAmericaAwardParser

    cases = (
      ('PEN/Diamonstein-Spielvogel Award for the Art of the Essay', 'Essay'),
      ('PEN/Jean Stein Book Award', 'Book'),
      ('PEN Open Book Award', 'Book'),
    )
    for award_name, category in cases:
      config = PENAwardConfig(award_name, category, (award_name,), 'title_author')
      html = '''
      <html><body>
        <h2>%s</h2>
        <h3>Finalists</h3>
        <ul><li>Fixture Title, Fixture Author (Press)</li></ul>
      </body></html>
      ''' % award_name

      parsed = PENAmericaAwardParser().parse(
        (('https://pen.org/2025-pen-america-literary-awards-finalists/', html, 'annual'),),
        'https://pen.org/example/',
        award_name,
        config)

      self.assertEqual(['Fixture Title'], [
        entry['title'] for entry in parsed['entries']])
      self.assertEqual([category], [
        entry['category'] for entry in parsed['entries']])
      self.assertEqual(['nominee'], [
        entry['result'] for entry in parsed['entries']])

  def test_pen_faulkner_parser_handles_history_and_current_posts(self):
    from parser.pen_faulkner_foundation import PENFaulknerAwardParser

    history_html = '''
    <html><body>
      <h2>2024</h2>
      <p>WINNER: Historical Winner by History Author</p>
      <p>FINALISTS: First Finalist by First Author; Second Finalist by Second Author</p>
    </body></html>
    '''
    finalist_html = '''
    <html><body>
      <h1>2026 PEN/Faulkner Award Finalists</h1>
      <h2>Finalists</h2>
      <ul><li><a href="/books/current-finalist">Current Finalist by Current Author (Press)</a></li></ul>
    </body></html>
    '''
    winner_html = '''
    <html><body>
      <h1>2026 PEN/Faulkner Award Winner</h1>
      <p><a href="/books/current-winner">Current Winner by Winner Author</a> has won the award.</p>
      <h2>Finalists</h2>
      <ul>
        <li>Current Winner by Winner Author</li>
        <li>Other Finalist by Other Author</li>
      </ul>
    </body></html>
    '''

    parsed = PENFaulknerAwardParser().parse(
      (
        ('https://www.penfaulkner.org/our-awards/pen-faulkner-award/', history_html, 'history'),
        ('https://www.penfaulkner.org/2026-pen-faulkner-award-finalists/', finalist_html, 'finalist_post'),
        ('https://www.penfaulkner.org/2026-pen-faulkner-award-winner/', winner_html, 'winner_post'),
      ),
      'https://www.penfaulkner.org/our-awards/pen-faulkner-award/',
      'PEN/Faulkner Award for Fiction')

    self.assertEqual(
      ['Historical Winner', 'First Finalist', 'Second Finalist',
       'Current Winner', 'Current Finalist', 'Other Finalist'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'nominee', 'nominee', 'winner', 'nominee', 'nominee'],
      [entry['result'] for entry in parsed['entries']])
    self.assertEqual(['2024', '2024.01', '2024.02', '2026', '2026.01', '2026.02'], [
      entry['position'] for entry in parsed['entries']])
    self.assertEqual(1, len([
      entry for entry in parsed['entries']
      if entry['title'] == 'Current Winner'
    ]))

  def test_pen_hemingway_parser_handles_current_and_history_rows(self):
    from parser.pen_faulkner_foundation import PENHemingwayAwardParser

    current_html = '''
    <html><body>
      <h1>2026 PEN/Hemingway Award</h1>
      <h2>Winner</h2>
      <p><a href="/books/debut-winner">Debut Winner by Debut Author</a></p>
      <h2>Semi-Finalists</h2>
      <ul><li>Semi Book by Semi Author</li></ul>
    </body></html>
    '''
    history_html = '''
    <html><body>
      <h2>2024</h2>
      <p>Winner: Earlier Winner by Earlier Author</p>
      <p>Finalists: Earlier Finalist by Earlier Finalist Author</p>
    </body></html>
    '''

    parsed = PENHemingwayAwardParser().parse(
      (
        ('https://www.penfaulkner.org/pen-hemingway-award-current-winner/', current_html, 'current'),
        ('https://www.penfaulkner.org/our-awards/pen-hemingway-award/', history_html, 'history'),
      ),
      'https://www.penfaulkner.org/our-awards/pen-hemingway-award/',
      'PEN/Hemingway Award for Debut Novel')

    self.assertEqual(
      ['Earlier Winner', 'Earlier Finalist', 'Debut Winner', 'Semi Book'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(['winner', 'nominee', 'winner', 'nominee'], [
      entry['result'] for entry in parsed['entries']])
    self.assertEqual('Debut Novel', parsed['entries'][0]['category'])

  def test_lukas_official_parser_keeps_book_prize_section_and_result_precedence(self):
    from parser.lukas import LukasOfficialParser

    shortlist_html = '''
    <html><body>
      <h1>2026 Lukas Prize Project Shortlists</h1>
      <h2>J. Anthony Lukas Book Prize</h2>
      <ul>
        <li><a href="/book/seeking">Jeff Hobbs, <em>Seeking Shelter</em> (Random House)</a></li>
        <li>Rich Benjamin, <em>Talk to Me</em> (Crown)</li>
        <li>Another Writer, <em>Another Book</em> (Press)</li>
      </ul>
      <h2>Mark Lynton History Prize</h2>
      <ul><li>Wrong Writer, <em>Wrong History Book</em> (Press)</li></ul>
    </body></html>
    '''
    winners_html = '''
    <html><body>
      <h1>2026 J. Anthony Lukas Prize Project Winners</h1>
      <h2>J. Anthony Lukas Book Prize</h2>
      <p>Winner: Jeff Hobbs, <em>Seeking Shelter</em> (Random House)</p>
      <p>Finalist: Rich Benjamin, <em>Talk to Me</em> (Crown)</p>
      <h2>J. Anthony Lukas Work-in-Progress Award</h2>
      <p>Winner: Wrong Person, <em>Wrong Project</em></p>
    </body></html>
    '''

    parsed = LukasOfficialParser().parse(
      (
        ('https://journalism.columbia.edu/news/lukas-shortlists-2026', shortlist_html),
        ('https://journalism.columbia.edu/news/lukas-prize-winners-2026', winners_html),
      ),
      'https://journalism.columbia.edu/lukas',
      'J. Anthony Lukas Book Prize')

    self.assertEqual(
      ['Seeking Shelter', 'Talk to Me', 'Another Book'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'finalist', 'shortlisted'],
      [entry['result'] for entry in parsed['entries']])
    self.assertEqual(['2026', '2026.01', '2026.02'], [
      entry['position'] for entry in parsed['entries']])
    self.assertFalse(any(entry['title'] == 'Wrong History Book'
                         for entry in parsed['entries']))
    self.assertFalse(any(entry['title'] == 'Wrong Project'
                         for entry in parsed['entries']))

  def test_lukas_wikipedia_parser_preserves_finalist_and_shortlist_results(self):
    from parser.lukas import LukasWikipediaParser

    html = '''
    <html><body>
      <table class="wikitable">
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Publisher</th><th>Result</th></tr>
        <tr>
          <td rowspan="3">2026</td>
          <td>Jeff Hobbs</td>
          <td><a href="/wiki/Seeking_Shelter">Seeking Shelter</a></td>
          <td>Random House</td>
          <td>Winner</td>
        </tr>
        <tr><td>Rich Benjamin</td><td>Talk to Me</td><td>Crown</td><td>Finalist</td></tr>
        <tr><td>Another Writer</td><td>Another Book</td><td>Press</td><td>Shortlist</td></tr>
      </table>
    </body></html>
    '''

    parsed = LukasWikipediaParser().parse(
      html,
      'https://en.wikipedia.org/wiki/J._Anthony_Lukas_Book_Prize',
      'J. Anthony Lukas Book Prize')

    self.assertEqual(
      ['Seeking Shelter', 'Talk to Me', 'Another Book'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'finalist', 'shortlisted'],
      [entry['result'] for entry in parsed['entries']])
    self.assertEqual(
      'https://en.wikipedia.org/wiki/Seeking_Shelter',
      parsed['entries'][0]['source_url'])

  def test_mark_lynton_official_parser_keeps_history_prize_section(self):
    from parser.lukas import MarkLyntonHistoryPrizeParser

    shortlist_html = '''
    <html><body>
      <h1>2026 Lukas Prize Project Shortlists</h1>
      <h2>J. Anthony Lukas Book Prize Shortlist</h2>
      <ul><li>Wrong Writer, <em>Wrong Book Prize Book</em> (Press)</li></ul>
      <h2>Mark Lynton History Prize Shortlist</h2>
      <ul>
        <li>Sven Beckert, <em>Capitalism: A Global History</em> (Penguin Press)</li>
        <li>Nicholas Boggs, <em>Baldwin: A Love Story</em> (FSG)</li>
        <li>William Dalrymple, <em>The Golden Road: How Ancient India Transformed the World</em> (Bloomsbury)</li>
        <li>Siddharth Kara, <em>The Zorg: A Tale of Greed and Murder That Inspired the Abolition of Slavery</em> (St. Martin's Press)</li>
      </ul>
      <h2>J. Anthony Lukas Work-in-Progress Prizes Shortlist</h2>
      <ul><li>Wrong Person, <em>Wrong Manuscript</em></li></ul>
    </body></html>
    '''
    winners_html = '''
    <html><body>
      <h1>2026 J. Anthony Lukas Prize Project Winners</h1>
      <h2>J. Anthony Lukas Book Prize</h2>
      <p>Winner: Wrong Writer, <em>Wrong Book Prize Book</em> (Press)</p>
      <h2>Mark Lynton History Prize</h2>
      <p>Winner: William Dalrymple, <em>The Golden Road: How Ancient India Transformed the World</em> (Bloomsbury)</p>
      <p>Finalist: Siddharth Kara, <em>The Zorg: A Tale of Greed and Murder That Inspired the Abolition of Slavery</em> (St. Martin's Press)</p>
      <h2>J. Anthony Lukas Work-in-Progress Award Winners</h2>
      <p>Winner: Wrong Person, <em>Wrong Project</em></p>
    </body></html>
    '''

    parsed = MarkLyntonHistoryPrizeParser().parse(
      (
        ('https://journalism.columbia.edu/news/lukas-shortlists-2026', shortlist_html),
        ('https://journalism.columbia.edu/news/lukas-prize-winners-2026', winners_html),
      ),
      'https://journalism.columbia.edu/lukas',
      'Mark Lynton History Prize')

    self.assertEqual(
      ['The Golden Road: How Ancient India Transformed the World',
       'The Zorg: A Tale of Greed and Murder That Inspired the Abolition of Slavery',
       'Capitalism: A Global History',
       'Baldwin: A Love Story'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'finalist', 'shortlisted', 'shortlisted'],
      [entry['result'] for entry in parsed['entries']])
    self.assertEqual(['2026', '2026.01', '2026.02', '2026.03'], [
      entry['position'] for entry in parsed['entries']])
    self.assertEqual('History Prize', parsed['entries'][0]['category'])
    self.assertFalse(any(entry['title'] == 'Wrong Book Prize Book'
                         for entry in parsed['entries']))
    self.assertFalse(any(entry['title'] == 'Wrong Manuscript'
                         for entry in parsed['entries']))
    self.assertFalse(any(entry['title'] == 'Wrong Project'
                         for entry in parsed['entries']))

  def test_mark_lynton_wikipedia_parser_preserves_history_results(self):
    from parser.lukas import MarkLyntonHistoryPrizeWikipediaParser

    html = '''
    <html><body>
      <table class="wikitable">
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr>
          <td rowspan="3">1999</td>
          <td>Adam Hochschild</td>
          <td><a href="/wiki/King_Leopold%27s_Ghost">King Leopold's Ghost</a></td>
          <td>Winner</td>
        </tr>
        <tr><td>Finalist Writer</td><td>Finalist History</td><td>Finalist</td></tr>
        <tr><td>Shortlist Writer</td><td>Shortlist History</td><td></td></tr>
      </table>
    </body></html>
    '''

    parsed = MarkLyntonHistoryPrizeWikipediaParser().parse(
      html,
      'https://en.wikipedia.org/wiki/Mark_Lynton_History_Prize',
      'Mark Lynton History Prize')

    self.assertEqual(
      ["King Leopold's Ghost", 'Finalist History', 'Shortlist History'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'finalist', 'shortlisted'],
      [entry['result'] for entry in parsed['entries']])
    self.assertEqual(['1999', '1999.01', '1999.02'], [
      entry['position'] for entry in parsed['entries']])
    self.assertEqual('Mark Lynton History Prize', parsed['entries'][0]['award'])
    self.assertEqual(
      'https://en.wikipedia.org/wiki/King_Leopold%27s_Ghost',
      parsed['entries'][0]['source_url'])

  def test_lukas_librarything_parser_preserves_source_result_headings(self):
    from url_fetcher.lukas import UrlFetcherJAnthonyLukasBookPrize

    html = '''
    <html><body>
      <h2>Winner</h2>
      <table>
        <tr><th>Work</th><th>Year</th></tr>
        <tr>
          <td><a href="/work/seeking">Seeking Shelter</a> by <a href="/author/hobbs">Jeff Hobbs</a></td>
          <td>2026</td>
        </tr>
      </table>
      <h2>Finalist</h2>
      <table>
        <tr><th>Work</th><th>Year</th></tr>
        <tr><td><a href="/work/talk">Talk to Me</a> by <a href="/author/benjamin">Rich Benjamin</a></td><td>2026</td></tr>
      </table>
      <h2>Shortlist</h2>
      <table>
        <tr><th>Work</th><th>Year</th></tr>
        <tr><td><a href="/work/another">Another Book</a> by <a href="/author/another">Another Writer</a></td><td>2026</td></tr>
      </table>
    </body></html>
    '''

    fetcher = UrlFetcherJAnthonyLukasBookPrize()
    parsed = fetcher.create_librarything_parser().parse(
      html,
      fetcher.LIBRARYTHING_URL,
      fetcher.NAME,
      fetcher.CATEGORY,
      fetcher.CATEGORY_ALIASES)

    self.assertEqual(
      ['winner', 'finalist', 'shortlisted'],
      [entry['result'] for entry in parsed['entries']])
    self.assertEqual(
      'https://www.librarything.com/work/seeking',
      parsed['entries'][0]['source_url'])

  def test_lukas_fetcher_fallbacks_and_metadata(self):
    from url_fetcher import available_url_fetchers
    from url_fetcher.lukas import (
      LUKAS_LIBRARYTHING_URL,
      LUKAS_OFFICIAL_EXTRA_URLS,
      LUKAS_URL,
      LUKAS_WIKIPEDIA_URL,
      UrlFetcherJAnthonyLukasBookPrize,
    )

    fetcher = UrlFetcherJAnthonyLukasBookPrize()
    official_root = '<html><body><h1>Lukas Prize Project</h1></body></html>'
    official_winner = '''
    <html><body>
      <h2>J. Anthony Lukas Book Prize</h2>
      <p>Winner: Jeff Hobbs, <em>Seeking Shelter</em> (Random House)</p>
    </body></html>
    '''
    official_shortlist = '''
    <html><body>
      <h2>J. Anthony Lukas Book Prize</h2>
      <ul><li>Jeff Hobbs, <em>Seeking Shelter</em> (Random House)</li></ul>
    </body></html>
    '''
    librarything_html = '''
    <html><body>
      <h2>Winner</h2>
      <table><tr><th>Work</th><th>Year</th></tr>
      <tr><td><a href="/work/fallback">Fallback Book</a> by <a href="/author/fallback">Fallback Author</a></td><td>2025</td></tr></table>
    </body></html>
    '''
    wikipedia_html = '''
    <html><body>
      <table><tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
      <tr><td>2024</td><td>Wiki Author</td><td>Wiki Book</td><td>Winner</td></tr></table>
    </body></html>
    '''

    def fetch_url(url):
      if url == LUKAS_URL:
        return official_root
      if url == LUKAS_OFFICIAL_EXTRA_URLS[0]:
        return official_winner
      if url == LUKAS_OFFICIAL_EXTRA_URLS[1]:
        return official_shortlist
      if url == LUKAS_LIBRARYTHING_URL:
        return librarything_html
      if url == LUKAS_WIKIPEDIA_URL:
        return wikipedia_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual(['Seeking Shelter'], [
      entry['title'] for entry in parsed['entries']])
    self.assertEqual(['winner'], [
      entry['result'] for entry in parsed['entries']])
    self.assertFalse(parsed['match_series'])

    def librarything_fetch(url):
      if url == LUKAS_URL or url in LUKAS_OFFICIAL_EXTRA_URLS:
        return '<html><body>No usable official rows</body></html>'
      if url == LUKAS_LIBRARYTHING_URL:
        return librarything_html
      self.fail(url)

    fallback = fetcher.fetch_and_parse(librarything_fetch)

    self.assertEqual(LUKAS_LIBRARYTHING_URL, fallback['source_url'])
    self.assertEqual(['Fallback Book'], [
      entry['title'] for entry in fallback['entries']])
    self.assertTrue(any(note.startswith('Official Columbia failed')
                        for note in fallback['notes']))

    def wikipedia_fetch(url):
      if url == LUKAS_URL or url in LUKAS_OFFICIAL_EXTRA_URLS:
        return '<html><body>No usable official rows</body></html>'
      if url == LUKAS_LIBRARYTHING_URL:
        raise RuntimeError('librarything unavailable')
      if url == LUKAS_WIKIPEDIA_URL:
        return wikipedia_html
      self.fail(url)

    wiki_fallback = fetcher.fetch_and_parse(wikipedia_fetch)

    self.assertEqual(LUKAS_WIKIPEDIA_URL, wiki_fallback['source_url'])
    self.assertEqual(['Wiki Book'], [
      entry['title'] for entry in wiki_fallback['entries']])
    self.assertEqual(
      (
        {'label': 'Automatic', 'value': 'automatic'},
        {'label': 'Official Columbia', 'value': 0},
        {'label': 'LibraryThing', 'value': 1},
        {'label': 'Wikipedia', 'value': 2},
      ),
      fetcher.source_choices())
    self.assertEqual(
      {'Nonfiction', 'Regional & National Awards'},
      {item['label'] for item in fetcher.get_filter_list()})

    source_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertLess(
      source_ids.index('pen_hemingway_award_debut_novel'),
      source_ids.index('j_anthony_lukas_book_prize'))
    self.assertLess(
      source_ids.index('j_anthony_lukas_book_prize'),
      source_ids.index('hugo_awards_novel'))

  def test_mark_lynton_fetcher_uses_official_then_wikipedia(self):
    from url_fetcher import available_url_fetchers
    from url_fetcher.lukas import (
      LUKAS_OFFICIAL_EXTRA_URLS,
      LUKAS_URL,
      MARK_LYNTON_WIKIPEDIA_URL,
      UrlFetcherMarkLyntonHistoryPrize,
    )

    fetcher = UrlFetcherMarkLyntonHistoryPrize()
    official_root = '<html><body><h1>Lukas Prize Project</h1></body></html>'
    official_winner = '''
    <html><body>
      <h2>Mark Lynton History Prize</h2>
      <p>Winner: William Dalrymple, <em>The Golden Road</em> (Bloomsbury)</p>
    </body></html>
    '''
    official_shortlist = '''
    <html><body>
      <h2>Mark Lynton History Prize Shortlist</h2>
      <ul><li>William Dalrymple, <em>The Golden Road</em> (Bloomsbury)</li></ul>
    </body></html>
    '''
    wikipedia_html = '''
    <html><body>
      <table><tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
      <tr><td>1999</td><td>Adam Hochschild</td><td>King Leopold's Ghost</td><td>Winner</td></tr></table>
    </body></html>
    '''

    def fetch_url(url):
      if url == LUKAS_URL:
        return official_root
      if url == LUKAS_OFFICIAL_EXTRA_URLS[0]:
        return official_winner
      if url == LUKAS_OFFICIAL_EXTRA_URLS[1]:
        return official_shortlist
      if url == MARK_LYNTON_WIKIPEDIA_URL:
        return wikipedia_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual(['The Golden Road'], [
      entry['title'] for entry in parsed['entries']])
    self.assertEqual(['winner'], [
      entry['result'] for entry in parsed['entries']])
    self.assertFalse(parsed['match_series'])

    fallback = fetcher.fetch_and_parse(fetch_url, force_fallback_level=1)

    self.assertEqual(MARK_LYNTON_WIKIPEDIA_URL, fallback['source_url'])
    self.assertEqual(["King Leopold's Ghost"], [
      entry['title'] for entry in fallback['entries']])
    self.assertEqual(
      (
        {'label': 'Automatic', 'value': 'automatic'},
        {'label': 'Official Columbia', 'value': 0},
        {'label': 'Wikipedia', 'value': 1},
      ),
      fetcher.source_choices())
    self.assertEqual(
      {'Nonfiction', 'Regional & National Awards'},
      {item['label'] for item in fetcher.get_filter_list()})

    def failed_official_fetch(url):
      if url == LUKAS_URL or url in LUKAS_OFFICIAL_EXTRA_URLS:
        return '<html><body>No usable Mark Lynton rows</body></html>'
      if url == MARK_LYNTON_WIKIPEDIA_URL:
        return wikipedia_html
      self.fail(url)

    with self.assertRaises(Exception):
      fetcher.fetch_and_parse(failed_official_fetch, disable_fallbacks=True)

    source_ids = [recipe.source_id for recipe in available_url_fetchers()]
    expected = ['j_anthony_lukas_book_prize', 'mark_lynton_history_prize']
    self.assertLess(
      source_ids.index('pen_hemingway_award_debut_novel'),
      source_ids.index(expected[0]))
    self.assertLess(
      source_ids.index(expected[-1]),
      source_ids.index('orwell_prize_political_writing'))
    self.assertEqual(expected, source_ids[
      source_ids.index(expected[0]):source_ids.index(expected[-1]) + 1])

  def test_orwell_official_parser_keeps_political_writing_section(self):
    from parser.orwell import OrwellOfficialParser

    finalists_html = '''
    <html><body>
      <h1>Finalists announced for the Orwell Prizes in Political Writing and Political Fiction</h1>
      <h2>2026 Political Writing book prize Finalists</h2>
      <ul>
        <li>The Escape from Kabul | Karen Bartlett, Duckworth Books</li>
        <li>For the Sun After Long Nights | Nilo Tabrizy &amp; Fatemeh Jamalpour, Atlantic Books</li>
        <li>The Wall Dancers | Yi-Ling Liu, Bonnier Books</li>
      </ul>
      <h2>2026 Political Fiction book prize Finalists</h2>
      <ul><li>Wrong Novel | Fiction Writer, Fiction Press</li></ul>
    </body></html>
    '''
    winners_html = '''
    <html><body>
      <h1>2026 Political Writing Book prize winner</h1>
      <h2>The Escape from Kabul</h2>
      <p>Author: Karen Bartlett</p>
      <p>Publisher: Duckworth Books</p>
    </body></html>
    '''

    parsed = OrwellOfficialParser().parse(
      (
        ('https://www.orwellfoundation.com/news/finalists-2026/', finalists_html),
        ('https://www.orwellfoundation.com/book/the-escape-from-kabul/', winners_html),
      ),
      'https://www.orwellfoundation.com/the-orwell-prizes/previous-winners/',
      'Orwell Prize for Political Writing')

    self.assertEqual(
      ['The Escape from Kabul', 'For the Sun After Long Nights', 'The Wall Dancers'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'finalist', 'finalist'],
      [entry['result'] for entry in parsed['entries']])
    self.assertEqual(['2026', '2026.01', '2026.02'], [
      entry['position'] for entry in parsed['entries']])
    self.assertFalse(any(entry['title'] == 'Wrong Novel'
                         for entry in parsed['entries']))

  def test_orwell_official_parser_handles_recent_finalist_row_shapes(self):
    from parser.orwell import OrwellOfficialParser

    html = '''
    <html><body>
      <h2>The Orwell Prize for Political Writing 2025 Finalists</h2>
      <p>Looking at Women, Looking at War - Victoria Amelina (William Collins)</p>
      <p>Autocracy Inc \u2013 Anne Applebaum (Allen Lane)</p>
      <p>The Coming Storm by Gabriel Gatehouse (BBC Books)</p>
      <h2>The Orwell Prize for Political Writing 2024 Shortlist</h2>
      <ul><li>Shortlisted Book | Shortlisted Author, Publisher</li></ul>
    </body></html>
    '''

    parsed = OrwellOfficialParser().parse(
      html,
      'https://www.orwellfoundation.com/news/the-orwell-prizes-2025-finalists-announced/',
      'Orwell Prize for Political Writing')

    self.assertEqual(
      ['Shortlisted Book', 'Looking at Women, Looking at War', 'Autocracy Inc', 'The Coming Storm'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['shortlisted', 'finalist', 'finalist', 'finalist'],
      [entry['result'] for entry in parsed['entries']])
    self.assertEqual('Anne Applebaum', parsed['entries'][2]['author'])

  def test_orwell_wikipedia_parser_uses_only_political_writing_2019_table(self):
    from parser.orwell import OrwellWikipediaParser

    html = '''
    <html><body>
      <h2>The Orwell Prize for Political Writing (2019-present)</h2>
      <table class="wikitable">
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr>
          <td rowspan="3">2026</td>
          <td>Karen Bartlett</td>
          <td><a href="/wiki/The_Escape_from_Kabul">The Escape from Kabul</a></td>
          <td>Shortlist</td>
        </tr>
        <tr><td>Omer Bartov</td><td>Israel: What Went Wrong?</td><td></td></tr>
        <tr><td>Yi-Ling Liu</td><td>The Wall Dancers</td><td></td></tr>
        <tr><td>2025</td><td>Victoria Amelina</td><td>Looking at Women, Looking at War</td><td>Winner</td></tr>
      </table>
      <h2>The Orwell Prize for Political Fiction (2019-present)</h2>
      <table><tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
      <tr><td>2026</td><td>Wrong Writer</td><td>Wrong Novel</td><td>Shortlist</td></tr></table>
      <h2>The Orwell Prize for Books</h2>
      <table><tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
      <tr><td>2018</td><td>Wrong Author</td><td>Wrong Combined Book</td><td>Winner</td></tr></table>
    </body></html>
    '''

    parsed = OrwellWikipediaParser().parse(
      html,
      'https://en.wikipedia.org/wiki/Orwell_Prize',
      'Orwell Prize for Political Writing')

    self.assertEqual(
      ['Looking at Women, Looking at War', 'The Escape from Kabul', 'Israel: What Went Wrong?', 'The Wall Dancers'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'shortlisted', 'shortlisted', 'shortlisted'],
      [entry['result'] for entry in parsed['entries']])
    self.assertEqual(
      'https://en.wikipedia.org/wiki/The_Escape_from_Kabul',
      parsed['entries'][1]['source_url'])
    self.assertFalse(any(entry['title'] == 'Wrong Novel'
                         for entry in parsed['entries']))
    self.assertFalse(any(entry['title'] == 'Wrong Combined Book'
                         for entry in parsed['entries']))

  def test_orwell_fetcher_uses_wikipedia_as_only_fallback(self):
    from url_fetcher import available_url_fetchers
    from url_fetcher.orwell import (
      ORWELL_OFFICIAL_EXTRA_URLS,
      ORWELL_URL,
      ORWELL_WIKIPEDIA_URL,
      UrlFetcherOrwellPrizePoliticalWriting,
    )

    fetcher = UrlFetcherOrwellPrizePoliticalWriting()
    official_root = '<html><body><h1>Previous winners</h1></body></html>'
    official_finalists = '''
    <html><body>
      <h2>2026 Political Writing book prize Finalists</h2>
      <ul><li>The Escape from Kabul | Karen Bartlett, Duckworth Books</li></ul>
    </body></html>
    '''
    wikipedia_html = '''
    <html><body>
      <h2>The Orwell Prize for Political Writing (2019-present)</h2>
      <table><tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
      <tr><td>2025</td><td>Victoria Amelina</td><td>Looking at Women, Looking at War</td><td>Winner</td></tr></table>
    </body></html>
    '''

    def fetch_url(url):
      if url == ORWELL_URL:
        return official_root
      if url == ORWELL_OFFICIAL_EXTRA_URLS[0]:
        return official_finalists
      if url in ORWELL_OFFICIAL_EXTRA_URLS[1:]:
        return '<html><body>No usable extra rows</body></html>'
      if url == ORWELL_WIKIPEDIA_URL:
        return wikipedia_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual(['The Escape from Kabul'], [
      entry['title'] for entry in parsed['entries']])
    self.assertEqual(['finalist'], [
      entry['result'] for entry in parsed['entries']])
    self.assertFalse(parsed['match_series'])

    def wikipedia_fetch(url):
      if url == ORWELL_URL or url in ORWELL_OFFICIAL_EXTRA_URLS:
        return '<html><body>No usable official rows</body></html>'
      if url == ORWELL_WIKIPEDIA_URL:
        return wikipedia_html
      self.fail(url)

    fallback = fetcher.fetch_and_parse(wikipedia_fetch)

    self.assertEqual(ORWELL_WIKIPEDIA_URL, fallback['source_url'])
    self.assertEqual(['Looking at Women, Looking at War'], [
      entry['title'] for entry in fallback['entries']])
    self.assertTrue(any(note.startswith('Official Orwell failed')
                        for note in fallback['notes']))
    self.assertEqual(
      (
        {'label': 'Automatic', 'value': 'automatic'},
        {'label': 'Official Orwell', 'value': 0},
        {'label': 'Wikipedia', 'value': 1},
      ),
      fetcher.source_choices())
    self.assertEqual(
      {'Nonfiction', 'Regional & National Awards'},
      {item['label'] for item in fetcher.get_filter_list()})

    source_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertLess(
      source_ids.index('j_anthony_lukas_book_prize'),
      source_ids.index('orwell_prize_political_writing'))
    self.assertLess(
      source_ids.index('orwell_prize_political_writing'),
      source_ids.index('hugo_awards_novel'))

  def test_andrew_carnegie_parser_keeps_nonfiction_winners_and_finalists(self):
    from parser.andrew_carnegie import AndrewCarnegieOfficialParser

    html = '''
    <html><body>
      <h1>2026 Winners</h1>
      <h2>Nonfiction Winner</h2>
      <article>
        <h3><a href="/carnegie-medals/2026-winner-nf">Things in Nature Merely Grow</a></h3>
        <p>By Yiyun Li</p>
        <p>Farrar, Straus and Giroux</p>
      </article>
      <h2>Nonfiction Finalists</h2>
      <ul>
        <li><a href="/carnegie-medals/barn">The Barn</a> by Wright Thompson</li>
        <li><em>The Message</em>, Ta-Nehisi Coates (One World)</li>
        <li>Challenger by Adam Higginbotham (Avid Reader Press)</li>
      </ul>
      <h2>Fiction Finalists</h2>
      <ul><li><a href="/wrong">Wrong Novel</a> by Fiction Writer</li></ul>
      <h2>Nonfiction Longlist</h2>
      <ul><li><a href="/long">Longlisted Book</a> by Long Writer</li></ul>
    </body></html>
    '''

    parsed = AndrewCarnegieOfficialParser().parse(
      html,
      'https://www.ala.org/carnegie-medals/2026-winners',
      'Andrew Carnegie Medal for Excellence in Nonfiction')

    self.assertEqual(
      ['Things in Nature Merely Grow', 'The Barn', 'The Message', 'Challenger'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'finalist', 'finalist', 'finalist'],
      [entry['result'] for entry in parsed['entries']])
    self.assertEqual(['2026', '2026.01', '2026.02', '2026.03'], [
      entry['position'] for entry in parsed['entries']])
    self.assertFalse(any(entry['title'] == 'Wrong Novel'
                         for entry in parsed['entries']))
    self.assertFalse(any(entry['title'] == 'Longlisted Book'
                         for entry in parsed['entries']))
    self.assertEqual(
      'https://www.ala.org/carnegie-medals/2026-winner-nf',
      parsed['entries'][0]['source_url'])

  def test_andrew_carnegie_parser_handles_no_medal_year_and_old_blocks(self):
    from parser.andrew_carnegie import AndrewCarnegieOfficialParser

    html = '''
    <html><body>
      <h2>NONFICTION WINNER</h2>
      <p>No medal was awarded.</p>
      <h2>NONFICTION FINALISTS</h2>
      <div>
        <p>Author: Sarah Smarsh</p>
        <p>Heartland: A Memoir of Working Hard and Being Broke in the Richest Country on Earth</p>
      </div>
      <div>
        <p>Dopesick: Dealers, Doctors, and the Drug Company that Addicted America</p>
        <p>By Beth Macy</p>
      </div>
      <h2>FICTION WINNER</h2>
      <p>Wrong Book by Wrong Author</p>
    </body></html>
    '''

    parsed = AndrewCarnegieOfficialParser().parse(
      html,
      'https://www.ala.org/carnegie-medals/2018-winners',
      'Andrew Carnegie Medal for Excellence in Nonfiction')

    self.assertEqual(
      [
        'Heartland: A Memoir of Working Hard and Being Broke in the Richest Country on Earth',
        'Dopesick: Dealers, Doctors, and the Drug Company that Addicted America',
      ],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(['finalist', 'finalist'], [
      entry['result'] for entry in parsed['entries']])
    self.assertEqual(['2018.01', '2018.02'], [
      entry['position'] for entry in parsed['entries']])

  def test_andrew_carnegie_fetcher_metadata_and_partial_year_failures(self):
    from url_fetcher import available_url_fetchers
    from url_fetcher.andrew_carnegie import (
      ANDREW_CARNEGIE_YEAR_URLS,
      UrlFetcherAndrewCarnegieNonfiction,
    )

    fetcher = UrlFetcherAndrewCarnegieNonfiction()
    pages = {
      'https://www.ala.org/carnegie-medals/2026-winners': '''
        <html><body>
          <h2>Nonfiction Winner</h2>
          <p><a href="/carnegie-medals/winner">Things in Nature Merely Grow</a> by Yiyun Li</p>
        </body></html>
      ''',
      'https://www.ala.org/carnegie-medals/2025-winners': '''
        <html><body>
          <h2>Nonfiction Finalists</h2>
          <ul><li><a href="/carnegie-medals/finalist">The Wide Wide Sea</a> by Hampton Sides</li></ul>
        </body></html>
      ''',
    }

    def fetch_url(url):
      if url == 'https://www.ala.org/carnegie-medals/2024-winners':
        raise RuntimeError('temporary ALA failure')
      return pages.get(url, '<html><body>No usable Carnegie rows</body></html>')

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual(
      ['The Wide Wide Sea', 'Things in Nature Merely Grow'],
      [entry['title'] for entry in parsed['entries']])
    self.assertTrue(any(
      note.startswith('Official ALA Carnegie page failed')
      for note in parsed['notes']))
    self.assertFalse(parsed['match_series'])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},),
                     fetcher.source_choices())
    self.assertEqual(
      {'Nonfiction', 'Regional & National Awards'},
      {item['label'] for item in fetcher.get_filter_list()})
    self.assertEqual(
      'https://www.ala.org/carnegie-medals/2026-winners',
      ANDREW_CARNEGIE_YEAR_URLS[0])

    source_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertLess(
      source_ids.index('orwell_prize_political_writing'),
      source_ids.index('andrew_carnegie_medal_nonfiction'))
    self.assertLess(
      source_ids.index('andrew_carnegie_medal_nonfiction'),
      source_ids.index('hugo_awards_novel'))

  def test_kirkus_parser_keeps_configured_category_sections(self):
    from parser.kirkus import KirkusPrizeParser

    html = '''
    <html><body>
      <h2>2025 Winners</h2>
      <section>
        <h3>Fiction</h3>
        <article><a href="/book/fiction-winner/">Fiction Winner</a><p>BY Fiction Writer</p></article>
        <h3>Nonfiction</h3>
        <article><a href="/book/nonfiction-winner/">Nonfiction Winner</a><p>BY Nonfiction Writer</p></article>
        <h3>Young Readers' Literature</h3>
        <article><a href="/book/young-winner/">Young Winner</a><p>BY Young Writer</p></article>
      </section>
      <h2>2025 Finalists</h2>
      <section>
        <h3>Fiction</h3>
        <div><a href="/book/fiction-finalist/">Fiction Finalist</a><p>By Other Fiction Writer</p></div>
        <h3>Nonfiction</h3>
        <div><a href="/book/nonfiction-finalist-one/">Nonfiction Finalist One</a><p>By First Nonfiction Writer</p></div>
        <div><a href="/book/nonfiction-finalist-two/">Nonfiction Finalist Two</a><p>By Second Nonfiction Writer</p></div>
        <h3>Young Readers' Literature</h3>
        <div><a href="/book/young-finalist/">Young Finalist</a><p>By Other Young Writer</p></div>
      </section>
    </body></html>
    '''

    parsed = KirkusPrizeParser().parse(
      html,
      'https://www.kirkusreviews.com/prize/2025/',
      'Kirkus Prize - Nonfiction',
      'Nonfiction',
      ('Nonfiction',))

    self.assertEqual(
      ['Nonfiction Winner', 'Nonfiction Finalist One', 'Nonfiction Finalist Two'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(['winner', 'finalist', 'finalist'], [
      entry['result'] for entry in parsed['entries']])
    self.assertEqual(['2025', '2025.01', '2025.02'], [
      entry['position'] for entry in parsed['entries']])
    self.assertEqual(
      'https://www.kirkusreviews.com/book/nonfiction-winner/',
      parsed['entries'][0]['source_url'])
    self.assertFalse(any(entry['title'] == 'Fiction Winner'
                         for entry in parsed['entries']))
    self.assertFalse(any(entry['title'] == 'Young Winner'
                         for entry in parsed['entries']))

  def test_kirkus_parser_handles_old_and_young_reader_category_labels(self):
    from parser.kirkus import KirkusPrizeParser

    html = '''
    <html><body>
      <h2>2014 Winners</h2>
      <section>
        <h3>Children's</h3>
        <p><a href="/book/brown-girl-dreaming/">Brown Girl Dreaming</a> by Jacqueline Woodson</p>
      </section>
      <h2>2014 Finalists</h2>
      <section>
        <h3>Teen</h3>
        <p><a href="/book/young-finalist/">Young Finalist</a> by Teen Writer</p>
        <h3>Fiction</h3>
        <p><a href="/book/wrong/">Wrong Adult Book</a> by Wrong Writer</p>
      </section>
    </body></html>
    '''

    parsed = KirkusPrizeParser().parse(
      html,
      'https://www.kirkusreviews.com/prize/2014/',
      "Kirkus Prize - Young Readers' Literature",
      "Young Readers' Literature",
      ("Young Readers' Literature", "Children's", 'Teen'))

    self.assertEqual(['Brown Girl Dreaming', 'Young Finalist'], [
      entry['title'] for entry in parsed['entries']])
    self.assertEqual(['winner', 'finalist'], [
      entry['result'] for entry in parsed['entries']])
    self.assertEqual(['2014', '2014.01'], [
      entry['position'] for entry in parsed['entries']])

  def test_kirkus_fetcher_metadata_and_partial_year_failures(self):
    from url_fetcher import available_url_fetchers
    from url_fetcher.kirkus import (
      KIRKUS_PRIZE_URL,
      UrlFetcherKirkusPrizeFiction,
      UrlFetcherKirkusPrizeNonfiction,
      UrlFetcherKirkusPrizeYoungReadersLiterature,
    )

    fetcher = UrlFetcherKirkusPrizeNonfiction()
    landing_html = '''
      <a href="/prize/2025/">2025 Kirkus Prize</a>
      <a href="/prize/2024/">2024 Kirkus Prize</a>
    '''
    pages = {
      'https://www.kirkusreviews.com/prize/2025/': '''
        <html><body>
          <h2>2025 Winners</h2>
          <section><h3>Nonfiction</h3>
          <p><a href="/book/nonfiction-winner/">Nonfiction Winner</a> by Nonfiction Writer</p></section>
        </body></html>
      ''',
      'https://www.kirkusreviews.com/prize/2024/': '''
        <html><body>
          <h2>2024 Finalists</h2>
          <section><h3>Nonfiction</h3>
          <p><a href="/book/nonfiction-finalist/">Nonfiction Finalist</a> by Finalist Writer</p></section>
        </body></html>
      ''',
    }

    def fetch_url(url):
      if url == KIRKUS_PRIZE_URL:
        return landing_html
      if url == 'https://www.kirkusreviews.com/prize/2023/':
        raise RuntimeError('temporary Kirkus failure')
      return pages.get(url, '<html><body>No usable Kirkus rows</body></html>')

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual(['Nonfiction Finalist', 'Nonfiction Winner'], [
      entry['title'] for entry in parsed['entries']])
    self.assertTrue(any(
      note.startswith('Official Kirkus page failed')
      for note in parsed['notes']))
    self.assertFalse(parsed['match_series'])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},),
                     fetcher.source_choices())
    self.assertEqual(
      {'Nonfiction', 'Regional & National Awards'},
      {item['label'] for item in fetcher.get_filter_list()})
    self.assertEqual(
      {'Literary & General Fiction', 'Regional & National Awards'},
      {item['label'] for item in UrlFetcherKirkusPrizeFiction().get_filter_list()})
    self.assertEqual(
      {"Young Adult & Children's Literature", 'Regional & National Awards'},
      {item['label'] for item in UrlFetcherKirkusPrizeYoungReadersLiterature().get_filter_list()})

    source_ids = [recipe.source_id for recipe in available_url_fetchers()]
    expected = [
      'kirkus_prize_fiction',
      'kirkus_prize_nonfiction',
      'kirkus_prize_young_readers_literature',
    ]
    self.assertLess(
      source_ids.index('andrew_carnegie_medal_nonfiction'),
      source_ids.index(expected[0]))
    self.assertLess(
      source_ids.index(expected[-1]),
      source_ids.index('hugo_awards_novel'))
    self.assertEqual(expected, source_ids[
      source_ids.index(expected[0]):source_ids.index(expected[-1]) + 1])

  def test_womens_prize_official_parser_uses_detail_pages_and_boundaries(self):
    from parser.womens_prize import WomensPrizeOfficialParser

    landing_html = '''
    <html><body>
      <section>
        <h2>2025 Winner</h2>
        <article><a href="/library/the-story-of-a-heart/">
          <h3>The Story of a Heart</h3><p>By Rachel Clarke</p>
        </a></article>
      </section>
      <section>
        <h2>2025 Shortlist</h2>
        <article><a href="/library/raising-hare/">
          <h3>Raising Hare</h3><p>By Chloe Dalton</p>
        </a></article>
        <article><a href="/library/private-revolutions/">
          <h3>Private Revolutions</h3><p>By Yuan Yang</p>
        </a></article>
      </section>
      <section>
        <h2>2026 Shortlist</h2>
        <article><a href="/library/the-finest-hotel-in-kabul/">
          <h3>The Finest Hotel in Kabul</h3><p>By Lyse Doucet</p>
        </a></article>
      </section>
      <section>
        <h2>2025 Winner</h2>
        <article><a href="/library/the-safekeep/">
          <h3>The Safekeep</h3><p>By Yael van der Wouden</p>
        </a></article>
      </section>
      <section>
        <h2>2026 Longlist</h2>
        <article><a href="/library/longlisted-book/">
          <h3>Longlisted Book</h3><p>By Long Writer</p>
        </a></article>
      </section>
    </body></html>
    '''
    pages = {
      'https://womensprize.com/library/the-story-of-a-heart/': '''
        <html><body><main><h1>The Story of a Heart</h1>
        <p>By Rachel Clarke</p>
        <p>Winner of the 2025 Women's Prize for Non-Fiction</p></main></body></html>
      ''',
      'https://womensprize.com/library/raising-hare/': '''
        <html><body><main><h1>Raising Hare</h1>
        <p>By Chloe Dalton</p>
        <p>Shortlisted for the 2025 Women's Prize for Non-Fiction</p></main></body></html>
      ''',
      'https://womensprize.com/library/private-revolutions/': '''
        <html><body><main><h1>Private Revolutions</h1>
        <p>By Yuan Yang</p>
        <p>Shortlisted for the 2025 Women's Prize for Non-Fiction</p></main></body></html>
      ''',
      'https://womensprize.com/library/the-finest-hotel-in-kabul/': '''
        <html><body><main><h1>The Finest Hotel in Kabul</h1>
        <p>By Lyse Doucet</p>
        <p>Shortlisted for the 2026 Women's Prize for Non-Fiction</p></main></body></html>
      ''',
      'https://womensprize.com/library/the-safekeep/': '''
        <html><body><main><h1>The Safekeep</h1>
        <p>By Yael van der Wouden</p>
        <p>Winner of the 2025 Women's Prize for Fiction</p></main></body></html>
      ''',
    }

    parsed = WomensPrizeOfficialParser(
      "Women's Prize for Non-Fiction",
      'Non-Fiction',
      ("Women's Prize for Non-Fiction", "Women's Prize for Non Fiction"),
    ).parse(
      landing_html,
      'https://womensprize.com/prizes/womens-prize-for-non-fiction/',
      "Women's Prize for Non-Fiction",
      'Non-Fiction',
      fetch_url=lambda url: pages[url])

    self.assertEqual(
      ['The Story of a Heart', 'Raising Hare', 'Private Revolutions',
       'The Finest Hotel in Kabul'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'shortlisted', 'shortlisted', 'shortlisted'],
      [entry['result'] for entry in parsed['entries']])
    self.assertEqual(['2025', '2025.01', '2025.02', '2026.01'], [
      entry['position'] for entry in parsed['entries']])
    self.assertFalse(any(entry['title'] == 'The Safekeep'
                         for entry in parsed['entries']))
    self.assertFalse(any(entry['title'] == 'Longlisted Book'
                         for entry in parsed['entries']))

  def test_womens_prize_official_parser_keeps_landing_fallback_with_note(self):
    from parser.womens_prize import WomensPrizeOfficialParser

    html = '''
    <html><body>
      <section>
        <h2>2026 Shortlist</h2>
        <article><a href="/library/the-mercy-step/">
          <h3>The Mercy Step</h3><p>By Marcia Hutchinson</p>
        </a></article>
      </section>
    </body></html>
    '''

    parsed = WomensPrizeOfficialParser(
      "Women's Prize for Fiction",
      'Fiction',
      ("Women's Prize for Fiction",),
    ).parse(
      html,
      'https://womensprize.com/prizes/womens-prize-for-fiction/',
      "Women's Prize for Fiction",
      'Fiction',
      fetch_url=lambda _url: (_ for _ in ()).throw(RuntimeError('moved page')))

    self.assertEqual(['The Mercy Step'], [
      entry['title'] for entry in parsed['entries']])
    self.assertEqual(['Marcia Hutchinson'], [
      entry['author'] for entry in parsed['entries']])
    self.assertEqual(['shortlisted'], [
      entry['result'] for entry in parsed['entries']])
    self.assertEqual(['2026.01'], [
      entry['position'] for entry in parsed['entries']])
    self.assertTrue(any(note.startswith('Official Women\'s Prize detail page failed')
                        for note in parsed['notes']))

  def test_womens_prize_wikipedia_parser_handles_repeated_years(self):
    from parser.womens_prize import WomensPrizeWikipediaParser

    html = '''
    <html><body>
      <table class="wikitable">
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr>
          <td rowspan="3">2025</td>
          <td>Rachel Clarke</td>
          <td><a href="/wiki/The_Story_of_a_Heart">The Story of a Heart</a></td>
          <td>Winner</td>
        </tr>
        <tr><td>Chloe Dalton</td><td>Raising Hare</td><td>Shortlist</td></tr>
        <tr><td>Yuan Yang</td><td>Private Revolutions</td><td></td></tr>
      </table>
    </body></html>
    '''

    parsed = WomensPrizeWikipediaParser(
      "Women's Prize for Non-Fiction",
      'Non-Fiction',
      ("Women's Prize for Non-Fiction",),
    ).parse(
      html,
      'https://en.wikipedia.org/wiki/Women%27s_Prize_for_Non-Fiction',
      "Women's Prize for Non-Fiction",
      'Non-Fiction')

    self.assertEqual(
      ['The Story of a Heart', 'Raising Hare', 'Private Revolutions'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'shortlisted', 'shortlisted'],
      [entry['result'] for entry in parsed['entries']])
    self.assertEqual(['2025', '2025.01', '2025.02'], [
      entry['position'] for entry in parsed['entries']])
    self.assertEqual(
      'https://en.wikipedia.org/wiki/The_Story_of_a_Heart',
      parsed['entries'][0]['source_url'])

  def test_womens_prize_fetchers_use_official_then_wikipedia(self):
    from url_fetcher import available_url_fetchers
    from url_fetcher.womens_prize import (
      WOMENS_PRIZE_FICTION_URL,
      WOMENS_PRIZE_NONFICTION_URL,
      WOMENS_PRIZE_NONFICTION_WIKIPEDIA_URL,
      UrlFetcherWomensPrizeFiction,
      UrlFetcherWomensPrizeNonFiction,
    )

    nonfiction = UrlFetcherWomensPrizeNonFiction()
    fiction = UrlFetcherWomensPrizeFiction()
    official_html = '''
    <html><body>
      <section><h2>2025 Winner</h2>
      <article><a href="/library/the-story-of-a-heart/">
      <h3>The Story of a Heart</h3><p>By Rachel Clarke</p></a></article>
      </section>
    </body></html>
    '''
    detail_html = '''
    <html><body><main><h1>The Story of a Heart</h1>
    <p>By Rachel Clarke</p>
    <p>Winner of the 2025 Women's Prize for Non-Fiction</p></main></body></html>
    '''
    wikipedia_html = '''
    <html><body><table>
      <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
      <tr><td>2025</td><td>Rachel Clarke</td><td>The Story of a Heart</td><td>Winner</td></tr>
    </table></body></html>
    '''

    def fetch_url(url):
      if url == WOMENS_PRIZE_NONFICTION_URL:
        return official_html
      if url == 'https://womensprize.com/library/the-story-of-a-heart/':
        return detail_html
      if url == WOMENS_PRIZE_NONFICTION_WIKIPEDIA_URL:
        return wikipedia_html
      self.fail(url)

    parsed = nonfiction.fetch_and_parse(fetch_url)

    self.assertEqual(['The Story of a Heart'], [
      entry['title'] for entry in parsed['entries']])
    self.assertFalse(parsed['match_series'])
    self.assertEqual(
      (
        {'label': 'Automatic', 'value': 'automatic'},
        {'label': 'Official Women\'s Prize', 'value': 0},
        {'label': 'Wikipedia', 'value': 1},
      ),
      nonfiction.source_choices())
    self.assertEqual(
      {'Nonfiction', 'Regional & National Awards'},
      {item['label'] for item in nonfiction.get_filter_list()})
    self.assertEqual(
      {'Literary & General Fiction', 'Regional & National Awards'},
      {item['label'] for item in fiction.get_filter_list()})

    fallback = nonfiction.fetch_and_parse(
      fetch_url,
      force_fallback_level=1)

    self.assertEqual(WOMENS_PRIZE_NONFICTION_WIKIPEDIA_URL, fallback['source_url'])
    self.assertEqual(['The Story of a Heart'], [
      entry['title'] for entry in fallback['entries']])

    def failed_official_fetch(url):
      if url == WOMENS_PRIZE_NONFICTION_URL:
        return '<html><body>No usable official rows</body></html>'
      if url == WOMENS_PRIZE_NONFICTION_WIKIPEDIA_URL:
        return wikipedia_html
      self.fail(url)

    with self.assertRaises(Exception):
      nonfiction.fetch_and_parse(failed_official_fetch, disable_fallbacks=True)

    source_ids = [recipe.source_id for recipe in available_url_fetchers()]
    expected = ['womens_prize_nonfiction', 'womens_prize_fiction']
    self.assertLess(
      source_ids.index('kirkus_prize_young_readers_literature'),
      source_ids.index(expected[0]))
    self.assertLess(
      source_ids.index(expected[-1]),
      source_ids.index('royal_society_science_book_prize'))
    self.assertEqual(expected, source_ids[
      source_ids.index(expected[0]):source_ids.index(expected[-1]) + 1])
    self.assertNotEqual(WOMENS_PRIZE_FICTION_URL, WOMENS_PRIZE_NONFICTION_URL)

  def test_royal_society_official_parser_uses_detail_pages_for_winners(self):
    from parser.royal_society import RoyalSocietyScienceBookPrizeParser

    landing_html = '''
    <html><body>
      <section>
        <article><a href="/medals-and-prizes/science-book-prize/books/2025/our-brains-our-selves/">
          <h3>Our Brains, Our Selves</h3>
          <p>Author: Masud Husain</p>
          <p>Shortlist: 2025</p>
        </a></article>
        <article><a href="/medals-and-prizes/science-book-prize/books/2025/adventures-in-volcanoland/">
          <h3>Adventures in Volcanoland</h3>
          <p>Author: Tamsin Mather</p>
          <p>Shortlist: 2025</p>
        </a></article>
        <article><a href="/medals-and-prizes/science-book-prize/books/2024/a-city-on-mars/">
          <h3>A City on Mars</h3>
          <p>Author: Kelly and Zach Weinersmith</p>
          <p>Shortlist: 2024</p>
        </a></article>
        <article><a href="/medals-and-prizes/young-peoples-book-prize/books/2025/not-this-one/">
          <h3>Wrong Prize</h3><p>Author: Wrong Writer</p>
        </a></article>
      </section>
    </body></html>
    '''
    pages = {
      'https://www.royalsociety.org/medals-and-prizes/science-book-prize/books/2025/our-brains-our-selves/': '''
        <html><body><main>
          <h1>Our Brains, Our Selves</h1>
          <p>Author: Masud Husain</p>
          <h2>Winner: 2025</h2>
          <section><h2>Other shortlisted books</h2>
            <a href="/medals-and-prizes/science-book-prize/books/2025/other/">Other Book</a>
          </section>
        </main></body></html>
      ''',
      'https://www.royalsociety.org/medals-and-prizes/science-book-prize/books/2025/adventures-in-volcanoland/': '''
        <html><body><main>
          <h1>Adventures in Volcanoland</h1>
          <p>Author: Tamsin Mather</p>
          <h2>Shortlist: 2025</h2>
        </main></body></html>
      ''',
      'https://www.royalsociety.org/medals-and-prizes/science-book-prize/books/2024/a-city-on-mars/': '''
        <html><body><main>
          <h1>A City on Mars</h1>
          <p>Author: Kelly and Zach Weinersmith</p>
          <h2>Winner: 2024</h2>
        </main></body></html>
      ''',
    }

    parsed = RoyalSocietyScienceBookPrizeParser().parse(
      landing_html,
      'https://www.royalsociety.org/medals-and-prizes/science-book-prize/',
      'Royal Society Trivedi Science Book Prize',
      'Science Book Prize',
      fetch_url=lambda url: pages[url])

    self.assertEqual(
      ['A City on Mars', 'Our Brains, Our Selves', 'Adventures in Volcanoland'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(['winner', 'winner', 'shortlisted'], [
      entry['result'] for entry in parsed['entries']])
    self.assertEqual(['2024', '2025', '2025.01'], [
      entry['position'] for entry in parsed['entries']])
    self.assertEqual('Kelly and Zach Weinersmith', parsed['entries'][0]['author'])
    self.assertFalse(any(entry['title'] == 'Other Book'
                         for entry in parsed['entries']))
    self.assertFalse(any(entry['title'] == 'Wrong Prize'
                         for entry in parsed['entries']))

  def test_royal_society_official_parser_keeps_landing_fallback_with_note(self):
    from parser.royal_society import RoyalSocietyScienceBookPrizeParser

    html = '''
    <html><body>
      <article><a href="/medals-and-prizes/science-book-prize/books/2025/adventures-in-volcanoland/">
        <h3>Adventures in Volcanoland</h3>
        <p>Author: Tamsin Mather</p>
        <p>Shortlist: 2025</p>
      </a></article>
    </body></html>
    '''

    parsed = RoyalSocietyScienceBookPrizeParser().parse(
      html,
      'https://www.royalsociety.org/medals-and-prizes/science-book-prize/',
      'Royal Society Trivedi Science Book Prize',
      'Science Book Prize',
      fetch_url=lambda _url: (_ for _ in ()).throw(RuntimeError('moved page')))

    self.assertEqual(['Adventures in Volcanoland'], [
      entry['title'] for entry in parsed['entries']])
    self.assertEqual(['Tamsin Mather'], [
      entry['author'] for entry in parsed['entries']])
    self.assertEqual(['shortlisted'], [
      entry['result'] for entry in parsed['entries']])
    self.assertEqual(['2025.01'], [
      entry['position'] for entry in parsed['entries']])
    self.assertTrue(any(note.startswith('Official Royal Society detail page failed')
                        for note in parsed['notes']))

  def test_royal_society_wikipedia_parser_handles_historical_tables(self):
    from parser.royal_society import RoyalSocietyScienceBookPrizeWikipediaParser

    html = '''
    <html><body>
      <h2>Rhône-Poulenc Prize for Science Books</h2>
      <table class="wikitable">
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr>
          <td rowspan="2">1988</td>
          <td>Stephen Hawking</td>
          <td><a href="/wiki/A_Brief_History_of_Time">A Brief History of Time</a></td>
          <td>Winner</td>
        </tr>
        <tr><td>James Gleick</td><td>Chaos</td><td>Finalist</td></tr>
      </table>
      <h2>Royal Society Winton Prize for Science Books</h2>
      <table class="wikitable">
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr>
          <td rowspan="3">2015</td>
          <td>Gaia Vince</td>
          <td>Adventures in the Anthropocene</td>
          <td>Winner</td>
        </tr>
        <tr><td>Helen Macdonald</td><td>H is for Hawk</td><td>Finalist</td></tr>
        <tr><td>Henry Marsh</td><td>Do No Harm</td><td></td></tr>
      </table>
    </body></html>
    '''

    parsed = RoyalSocietyScienceBookPrizeWikipediaParser().parse(
      html,
      'https://en.wikipedia.org/wiki/Royal_Society_Science_Book_Prize',
      'Royal Society Trivedi Science Book Prize',
      'Science Book Prize')

    self.assertEqual(
      ['A Brief History of Time', 'Chaos',
       'Adventures in the Anthropocene', 'H is for Hawk', 'Do No Harm'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(
      ['winner', 'shortlisted', 'winner', 'shortlisted', 'shortlisted'],
      [entry['result'] for entry in parsed['entries']])
    self.assertEqual(['1988', '1988.01', '2015', '2015.01', '2015.02'], [
      entry['position'] for entry in parsed['entries']])
    self.assertEqual(
      'Royal Society Trivedi Science Book Prize',
      parsed['entries'][0]['award'])
    self.assertEqual(
      'https://en.wikipedia.org/wiki/A_Brief_History_of_Time',
      parsed['entries'][0]['source_url'])

  def test_royal_society_fetcher_uses_official_then_wikipedia(self):
    from url_fetcher import available_url_fetchers
    from url_fetcher.royal_society import (
      ROYAL_SOCIETY_SCIENCE_BOOK_PRIZE_URL,
      ROYAL_SOCIETY_SCIENCE_BOOK_PRIZE_WIKIPEDIA_URL,
      UrlFetcherRoyalSocietyScienceBookPrize,
    )

    fetcher = UrlFetcherRoyalSocietyScienceBookPrize()
    official_html = '''
    <html><body>
      <article><a href="/medals-and-prizes/science-book-prize/books/2025/our-brains-our-selves/">
        <h3>Our Brains, Our Selves</h3>
        <p>Author: Masud Husain</p><p>Shortlist: 2025</p>
      </a></article>
    </body></html>
    '''
    detail_html = '''
    <html><body><main><h1>Our Brains, Our Selves</h1>
    <p>Author: Masud Husain</p><h2>Winner: 2025</h2></main></body></html>
    '''
    wikipedia_html = '''
    <html><body><table>
      <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
      <tr><td>1988</td><td>Stephen Hawking</td><td>A Brief History of Time</td><td>Winner</td></tr>
    </table></body></html>
    '''

    def fetch_url(url):
      if url == ROYAL_SOCIETY_SCIENCE_BOOK_PRIZE_URL:
        return official_html
      if url == 'https://www.royalsociety.org/medals-and-prizes/science-book-prize/books/2025/our-brains-our-selves/':
        return detail_html
      if url == ROYAL_SOCIETY_SCIENCE_BOOK_PRIZE_WIKIPEDIA_URL:
        return wikipedia_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual(['Our Brains, Our Selves'], [
      entry['title'] for entry in parsed['entries']])
    self.assertEqual(['winner'], [entry['result'] for entry in parsed['entries']])
    self.assertFalse(parsed['match_series'])
    self.assertEqual(
      (
        {'label': 'Automatic', 'value': 'automatic'},
        {'label': 'Official Royal Society', 'value': 0},
        {'label': 'Wikipedia', 'value': 1},
      ),
      fetcher.source_choices())
    self.assertEqual(
      {'Nonfiction', 'Regional & National Awards'},
      {item['label'] for item in fetcher.get_filter_list()})

    fallback = fetcher.fetch_and_parse(fetch_url, force_fallback_level=1)

    self.assertEqual(
      ROYAL_SOCIETY_SCIENCE_BOOK_PRIZE_WIKIPEDIA_URL,
      fallback['source_url'])
    self.assertEqual(['A Brief History of Time'], [
      entry['title'] for entry in fallback['entries']])

    def failed_official_fetch(url):
      if url == ROYAL_SOCIETY_SCIENCE_BOOK_PRIZE_URL:
        return '<html><body>No usable Royal Society rows</body></html>'
      if url == ROYAL_SOCIETY_SCIENCE_BOOK_PRIZE_WIKIPEDIA_URL:
        return wikipedia_html
      self.fail(url)

    with self.assertRaises(Exception):
      fetcher.fetch_and_parse(failed_official_fetch, disable_fallbacks=True)

    source_ids = [recipe.source_id for recipe in available_url_fetchers()]
    expected = [
      'womens_prize_nonfiction',
      'womens_prize_fiction',
      'royal_society_science_book_prize',
      'booker_prize',
      'international_booker_prize',
    ]
    self.assertLess(
      source_ids.index('kirkus_prize_young_readers_literature'),
      source_ids.index(expected[0]))
    self.assertLess(
      source_ids.index(expected[-1]),
      source_ids.index('hugo_awards_novel'))
    self.assertEqual(expected, source_ids[
      source_ids.index(expected[0]):source_ids.index(expected[-1]) + 1])

  def test_booker_official_parser_extracts_winners_shortlist_and_skips_longlist(self):
    from parser.booker import BookerPrizeOfficialParser

    html = '''
    <html><body>
      <main>
        <h2>Winner</h2>
        <article><a href="/the-booker-library/books/orbital">
          <h3>Orbital</h3><p>By Samantha Harvey</p></a></article>
        <h2>Shortlist</h2>
        <article><a href="/the-booker-library/books/orbital">
          <h3>Orbital</h3><p>By Samantha Harvey</p></a></article>
        <article><a href="/the-booker-library/books/james">
          <h3>James</h3><p>By Percival Everett</p></a></article>
        <h2>Longlist</h2>
        <article><a href="/the-booker-library/books/wandering-stars">
          <h3>Wandering Stars</h3><p>By Tommy Orange</p></a></article>
      </main>
    </body></html>
    '''
    pages = {
      'https://thebookerprizes.com/the-booker-library/books/orbital': '''
        <html><body><main><h1>Orbital</h1><p>By Samantha Harvey</p></main></body></html>
      ''',
      'https://thebookerprizes.com/the-booker-library/books/james': '''
        <html><body><main><h1>James</h1><p>By Percival Everett</p></main></body></html>
      ''',
    }

    parsed = BookerPrizeOfficialParser('Booker Prize', 'Fiction').parse(
      html,
      'https://thebookerprizes.com/the-booker-library/prize-years/2024',
      'Booker Prize',
      'Fiction',
      fetch_url=lambda url: pages[url])

    self.assertEqual(['Orbital', 'James'], [
      entry['title'] for entry in parsed['entries']])
    self.assertEqual(['winner', 'shortlisted'], [
      entry['result'] for entry in parsed['entries']])
    self.assertEqual(['2024', '2024.01'], [
      entry['position'] for entry in parsed['entries']])
    self.assertNotIn('Wandering Stars', [
      entry['title'] for entry in parsed['entries']])
    self.assertFalse(parsed['match_series'])

  def test_international_booker_official_parser_strips_translator_credits(self):
    from parser.booker import BookerPrizeOfficialParser

    html = '''
    <html><body>
      <h2>Winner</h2>
      <article><a href="/the-booker-library/books/heart-lamp">
        <h3>Heart Lamp</h3><p>By Banu Mushtaq translated by Deepa Bhasthi</p>
      </a></article>
      <h2>Shortlist</h2>
      <article><a href="/the-booker-library/books/the-book-of-disquiet">
        <h3>The Book of Disquiet</h3><p>Author: Fernando Pessoa | Translated by Margaret Jull Costa</p>
      </a></article>
    </body></html>
    '''

    parsed = BookerPrizeOfficialParser(
      'International Booker Prize',
      'Translated Fiction').parse(
        html,
        'https://thebookerprizes.com/the-booker-library/prize-years/international/2025',
        'International Booker Prize',
        'Translated Fiction')

    self.assertEqual(['Banu Mushtaq', 'Fernando Pessoa'], [
      entry['author'] for entry in parsed['entries']])
    self.assertEqual(['winner', 'shortlisted'], [
      entry['result'] for entry in parsed['entries']])

  def test_booker_wikipedia_parser_maps_shortlists_and_ignores_longlists(self):
    from parser.booker import BookerPrizeWikipediaParser

    html = '''
    <html><body>
      <table class="wikitable">
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr><td rowspan="3">2024</td><td>Samantha Harvey</td><td><a href="/wiki/Orbital">Orbital</a></td><td>Winner</td></tr>
        <tr><td>Percival Everett</td><td>James</td><td>Shortlisted</td></tr>
        <tr><td>Tommy Orange</td><td>Wandering Stars</td><td>Longlisted</td></tr>
      </table>
    </body></html>
    '''

    parsed = BookerPrizeWikipediaParser('Booker Prize', 'Fiction').parse(
      html,
      'https://en.wikipedia.org/wiki/List_of_winners_and_nominated_authors_of_the_Booker_Prize',
      'Booker Prize',
      'Fiction')

    self.assertEqual(['Orbital', 'James'], [
      entry['title'] for entry in parsed['entries']])
    self.assertEqual(['winner', 'shortlisted'], [
      entry['result'] for entry in parsed['entries']])
    self.assertEqual(
      'https://en.wikipedia.org/wiki/Orbital',
      parsed['entries'][0]['source_url'])

  def test_booker_fetchers_discover_years_and_fall_back(self):
    from url_fetcher import available_url_fetchers
    from url_fetcher.booker import (
      BOOKER_PRIZE_WIKIPEDIA_URL,
      BOOKER_PRIZE_YEARS_URL,
      INTERNATIONAL_BOOKER_PRIZE_WIKIPEDIA_URL,
      UrlFetcherBookerPrize,
      UrlFetcherInternationalBookerPrize,
    )

    booker = UrlFetcherBookerPrize()
    international = UrlFetcherInternationalBookerPrize()
    index_html = '''
    <html><body>
      <a href="/the-booker-library/prize-years/2024">2024 Booker</a>
      <a href="/the-booker-library/prize-years/international/2025">2025 International</a>
    </body></html>
    '''
    booker_year_html = '''
    <html><body><h2>Winner</h2>
      <article><a href="/the-booker-library/books/orbital">
      <h3>Orbital</h3><p>By Samantha Harvey</p></a></article>
    </body></html>
    '''
    international_year_html = '''
    <html><body><h2>Winner</h2>
      <article><a href="/the-booker-library/books/heart-lamp">
      <h3>Heart Lamp</h3><p>By Banu Mushtaq translated by Deepa Bhasthi</p></a></article>
    </body></html>
    '''
    wikipedia_html = '''
    <html><body><table>
      <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
      <tr><td>2024</td><td>Samantha Harvey</td><td>Orbital</td><td>Winner</td></tr>
    </table></body></html>
    '''
    international_wikipedia_html = '''
    <html><body><table>
      <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
      <tr><td>2025</td><td>Banu Mushtaq</td><td>Heart Lamp</td><td>Winner</td></tr>
    </table></body></html>
    '''

    def fetch_url(url):
      if url == BOOKER_PRIZE_YEARS_URL:
        return index_html
      if url == 'https://thebookerprizes.com/the-booker-library/prize-years/2024':
        return booker_year_html
      if url == 'https://thebookerprizes.com/the-booker-library/prize-years/international/2025':
        return international_year_html
      if url == 'https://thebookerprizes.com/the-booker-library/books/orbital':
        return '<html><body><main><h1>Orbital</h1><p>By Samantha Harvey</p></main></body></html>'
      if url == 'https://thebookerprizes.com/the-booker-library/books/heart-lamp':
        return '<html><body><main><h1>Heart Lamp</h1><p>By Banu Mushtaq translated by Deepa Bhasthi</p></main></body></html>'
      if url == BOOKER_PRIZE_WIKIPEDIA_URL:
        return wikipedia_html
      if url == INTERNATIONAL_BOOKER_PRIZE_WIKIPEDIA_URL:
        return international_wikipedia_html
      self.fail(url)

    parsed = booker.fetch_and_parse(fetch_url)
    self.assertEqual(['Orbital'], [entry['title'] for entry in parsed['entries']])
    self.assertFalse(parsed['match_series'])
    self.assertEqual(
      (
        {'label': 'Automatic', 'value': 'automatic'},
        {'label': 'Official Booker', 'value': 0},
        {'label': 'Wikipedia', 'value': 1},
      ),
      booker.source_choices())
    self.assertEqual(
      {'Literary & General Fiction', 'Regional & National Awards'},
      {item['label'] for item in booker.get_filter_list()})
    self.assertEqual(
      ['https://thebookerprizes.com/the-booker-library/prize-years/2024'],
      booker.year_urls(index_html, BOOKER_PRIZE_YEARS_URL))
    self.assertEqual(
      ['https://thebookerprizes.com/the-booker-library/prize-years/international/2025'],
      international.year_urls(index_html, BOOKER_PRIZE_YEARS_URL))

    fallback = international.fetch_and_parse(fetch_url, force_fallback_level=1)
    self.assertEqual(INTERNATIONAL_BOOKER_PRIZE_WIKIPEDIA_URL, fallback['source_url'])
    self.assertEqual(['Heart Lamp'], [
      entry['title'] for entry in fallback['entries']])

    source_ids = [recipe.source_id for recipe in available_url_fetchers()]
    expected = [
      'royal_society_science_book_prize',
      'booker_prize',
      'international_booker_prize',
    ]
    self.assertEqual(expected, source_ids[
      source_ids.index(expected[0]):source_ids.index(expected[-1]) + 1])

  def test_governor_general_official_json_parser_handles_core_categories(self):
    from parser.governor_general import GovernorGeneralAwardsParser

    payload = json.dumps({
      '1942': {
        'nonFiction': {
          'en': {
            'finalists': [
              {
                'title': 'The Unknown Country',
                'author': 'Bruce Hutchison',
                'publisher': 'Coward-McCann',
                'winner': True,
              },
              {
                'title': 'The Unguarded Frontier',
                'author': 'Edgar McInnis',
                'publisher': 'Doubleday',
                'winner': True,
              },
            ],
          },
        },
      },
      '1956': {
        'juvenile': {
          'en': {
            'finalists': [
              {
                'title': 'Lost in the Barrens',
                'author': 'Farley Mowat',
                'publisher': 'Little, Brown & Co.',
                'winner': True,
              },
            ],
          },
        },
      },
      '2024': {
        'fiction': {
          'en': {
            'finalists': [
              {
                'title': 'Code Noir',
                'author': 'Canisia Lubrin (Whitby, Ontario)',
                'publisher': 'Knopf Canada',
                'winner': False,
              },
              {
                'title': 'Empty Spaces',
                'author': 'Jordan Abel (Edmonton, Alberta)',
                'publisher': 'McClelland & Stewart',
                'winner': True,
              },
            ],
          },
          'fr': {
            'finalists': [
              {
                'title': 'Lait cru',
                'author': 'Steve Poutré',
                'publisher': 'Éditions Alto',
                'winner': True,
              },
            ],
          },
        },
      },
    })

    fiction = GovernorGeneralAwardsParser('English Fiction', ('fiction',)).parse(
      payload,
      'https://ggbooks.ca/Areas/GGBooks/json/ggbooks-data-compressed.json',
      "Governor General's Literary Award - English Fiction")
    nonfiction = GovernorGeneralAwardsParser(
      'English Non-fiction',
      ('nonFiction',)).parse(
        payload,
        'https://ggbooks.ca/Areas/GGBooks/json/ggbooks-data-compressed.json',
        "Governor General's Literary Award - English Non-fiction")
    juvenile = GovernorGeneralAwardsParser(
      "English Young People's Literature - Text",
      ('youngPeoplesLiteratureText', 'juvenile')).parse(
        payload,
        'https://ggbooks.ca/Areas/GGBooks/json/ggbooks-data-compressed.json',
        "Governor General's Literary Award - English Young People's Literature - Text")

    self.assertEqual(['Empty Spaces', 'Code Noir'], [
      entry['title'] for entry in fiction['entries']])
    self.assertEqual(['Jordan Abel', 'Canisia Lubrin'], [
      entry['author'] for entry in fiction['entries']])
    self.assertEqual(['winner', 'shortlisted'], [
      entry['result'] for entry in fiction['entries']])
    self.assertEqual(['2024', '2024.01'], [
      entry['position'] for entry in fiction['entries']])
    self.assertEqual(['1942', '1942'], [
      entry['position'] for entry in nonfiction['entries']])
    self.assertEqual(['Lost in the Barrens'], [
      entry['title'] for entry in juvenile['entries']])

  def test_governor_general_fetchers_discover_json_and_supplement_current_year(self):
    from url_fetcher import available_url_fetchers
    from url_fetcher.governor_general import (
      DEFAULT_JSON_URL,
      GOVERNOR_GENERAL_2025_PRESS_URL,
      GOVERNOR_GENERAL_2025_WIKIPEDIA_URL,
      GOVERNOR_GENERAL_ARCHIVE_URL,
      UrlFetcherGovernorGeneralEnglishFiction,
      UrlFetcherGovernorGeneralEnglishNonfiction,
      UrlFetcherGovernorGeneralEnglishYoungPeoplesText,
    )

    archive_html = '''
      <html><body>
        <div data-ux-module="Components/Archives20250923"></div>
      </body></html>
    '''
    component_js = '''
      define(["jquery"], function ($) {
        $.getJSON("/Areas/GGBooks/json/ggbooks-data-compressed-2025-09-18.json", function () {});
      });
    '''
    official_json = json.dumps({
      '2024': {
        'fiction': {
          'en': {
            'finalists': [
              {
                'title': 'Empty Spaces',
                'author': 'Jordan Abel (Edmonton, Alberta)',
                'publisher': 'McClelland & Stewart',
                'winner': True,
              },
            ],
          },
        },
      },
    })
    supplement_html = '''
      <html><body>
        <h2>English Fiction</h2>
        <table>
          <tr><th>Author</th><th>Title</th><th>Result</th></tr>
          <tr><td>Kyle Edwards</td><td>Small Ceremonies</td><td>Winner</td></tr>
          <tr><td>Claire Cameron</td><td>How to Survive a Bear Attack</td><td>Finalist</td></tr>
        </table>
      </body></html>
    '''
    press_html = '<html><body><h1>2025 GGBooks winners revealed</h1></body></html>'

    def fetch_url(url):
      if url == GOVERNOR_GENERAL_ARCHIVE_URL:
        return archive_html
      if url == 'https://ggbooks.ca/Areas/GGBooks/js/Components/Archives20250923.js':
        return component_js
      if url == 'https://ggbooks.ca/Areas/GGBooks/json/ggbooks-data-compressed-2025-09-18.json':
        return official_json
      if url == DEFAULT_JSON_URL:
        return official_json
      if url == GOVERNOR_GENERAL_2025_WIKIPEDIA_URL:
        return supplement_html
      if url == GOVERNOR_GENERAL_2025_PRESS_URL:
        return press_html
      self.fail(url)

    fiction = UrlFetcherGovernorGeneralEnglishFiction()
    parsed = fiction.fetch_and_parse(fetch_url)

    self.assertEqual([
      'Empty Spaces',
      'Small Ceremonies',
      'How to Survive a Bear Attack',
    ], [entry['title'] for entry in parsed['entries']])
    self.assertEqual(['2024', '2025', '2025.01'], [
      entry['position'] for entry in parsed['entries']])
    self.assertEqual(
      'https://ggbooks.ca/Areas/GGBooks/json/ggbooks-data-compressed-2025-09-18.json',
      parsed['source_url'])
    self.assertFalse(parsed['match_series'])
    self.assertTrue(any('official GGBooks JSON lacked 2025' in note
                        for note in parsed['notes']))
    self.assertEqual(
      ({'label': 'Automatic', 'value': 'automatic'},),
      fiction.source_choices())

    nonfiction = UrlFetcherGovernorGeneralEnglishNonfiction()
    ypl = UrlFetcherGovernorGeneralEnglishYoungPeoplesText()
    self.assertEqual(
      {'Literary & General Fiction', 'Regional & National Awards'},
      {item['label'] for item in fiction.get_filter_list()})
    self.assertEqual(
      {'Nonfiction', 'Regional & National Awards'},
      {item['label'] for item in nonfiction.get_filter_list()})
    self.assertEqual(
      {"Young Adult & Children's Literature", 'Regional & National Awards'},
      {item['label'] for item in ypl.get_filter_list()})

    source_ids = [recipe.source_id for recipe in available_url_fetchers()]
    expected = [
      'booker_prize',
      'international_booker_prize',
      'governor_general_literary_award_english_fiction',
      'governor_general_literary_award_english_nonfiction',
      'governor_general_literary_award_english_young_peoples_text',
    ]
    self.assertEqual(expected, source_ids[
      source_ids.index(expected[0]):source_ids.index(expected[-1]) + 1])

  def test_pen_fetcher_metadata_and_registration_order(self):
    from url_fetcher import available_url_fetchers
    from url_fetcher.pen_america import (
      UrlFetcherPENDiamonsteinSpielvogelAward,
      UrlFetcherPENGalbraithAward,
      UrlFetcherPENJeanSteinBookAward,
      UrlFetcherPENOpenBookAward,
    )
    from url_fetcher.pen_faulkner_foundation import (
      UrlFetcherPENFaulknerAward,
      UrlFetcherPENHemingwayAward,
    )

    fetchers = (
      UrlFetcherPENGalbraithAward(),
      UrlFetcherPENDiamonsteinSpielvogelAward(),
      UrlFetcherPENJeanSteinBookAward(),
      UrlFetcherPENOpenBookAward(),
      UrlFetcherPENFaulknerAward(),
      UrlFetcherPENHemingwayAward(),
    )

    for fetcher in fetchers:
      self.assertFalse(fetcher.options['match_series'])
      self.assertEqual(
        ({'label': 'Automatic', 'value': 'automatic'},),
        fetcher.source_choices())

    self.assertEqual(
      {'Nonfiction', 'Regional & National Awards'},
      {item['label'] for item in fetchers[0].get_filter_list()})
    self.assertEqual(
      {'Nonfiction', 'Regional & National Awards'},
      {item['label'] for item in fetchers[1].get_filter_list()})
    self.assertEqual(
      {'Nonfiction', 'Literary & General Fiction', 'Regional & National Awards'},
      {item['label'] for item in fetchers[2].get_filter_list()})
    self.assertEqual(
      {'Nonfiction', 'Literary & General Fiction', 'Regional & National Awards'},
      {item['label'] for item in fetchers[3].get_filter_list()})
    self.assertEqual(
      {'Literary & General Fiction', 'Regional & National Awards'},
      {item['label'] for item in fetchers[4].get_filter_list()})

    source_ids = [recipe.source_id for recipe in available_url_fetchers()]
    expected = [
      'pen_galbraith_award_nonfiction',
      'pen_diamonstein_spielvogel_award_essay',
      'pen_jean_stein_book_award',
      'pen_open_book_award',
      'pen_faulkner_award_fiction',
      'pen_hemingway_award_debut_novel',
    ]
    self.assertLess(
      source_ids.index('nbcc_award_criticism'),
      source_ids.index(expected[0]))
    self.assertLess(
      source_ids.index(expected[-1]),
      source_ids.index('hugo_awards_novel'))
    self.assertEqual(expected, source_ids[
      source_ids.index(expected[0]):source_ids.index(expected[-1]) + 1])

  def test_wwend_award_parser_base_handles_link_stream_dom_variation(self):
    from parser.wwend_base import WWEndAwardParserBase

    parser = WWEndAwardParserBase()
    parser.AWARD_NAME = 'Smoke WWEnd Award'
    html = '''
      <nav>
        <a href="#2025">2025</a>
        <a href="#2024">2024</a>
      </nav>
      <section>
        <h2><a href="#year-2025">2025</a></h2>
        <div class="winner">
          <a data-id="title" href="/books/novel.asp?id=100">
            The <span>Nested <em>Winner</em></span>
          </a>
          <span class="wrapper">
            <a href="/authors/author.asp?id=10">Nested <strong>Author</strong></a>
          </span>
        </div>
        <div class="nominee">
          <a href="/books/novel.asp?id=101">Second Book</a>
          <a href="/authors/author.asp?id=11">Second Author</a>
        </div>
      </section>
      <section><a href="#year-2024">2024</a></section>
    '''

    parsed = parser.parse(
      html, 'https://www.worldswithoutend.com/awards.asp',
      'Smoke WWEnd - Novel', 'Novel')

    self.assertEqual(['The Nested Winner', 'Second Book'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['winner', 'nominee'], [
      entry['result'] for entry in parsed['entries']
    ])
    self.assertEqual(
      'https://www.worldswithoutend.com/books/novel.asp?id=100',
      parsed['entries'][0]['source_url'])

  def test_bookbrowse_book_club_parser_base_handles_heading_dom_variation(self):
    from parser.bookbrowse_base import BookBrowseBookClubParserBase

    parser = BookBrowseBookClubParserBase()
    html = '''
      <main>
        <h2>More 2025 Book Club Discussions</h2>
        <div class="wrapper">
          <h3>
            <a data-kind="discussion" href="/bookclubs/discuss-the-nested-book">
              The <span>Nested <em>Novel</em></span>
              by
              <strong>Nested Writer</strong>
            </a>
            : BookBrowse Book Club
          </h3>
        </div>
        <h3>Forum Guidelines</h3>
        <h2>2024 Book Discussions</h2>
        <h3>
          A Title by Somebody by Second Writer Discussion
        </h3>
      </main>
    '''

    parsed = parser.parse(
      html, 'https://www.bookbrowse.com/bookclubs/',
      'BookBrowse Online Book Club')

    self.assertEqual(['The Nested Novel', 'A Title by Somebody'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['Nested Writer', 'Second Writer'], [
      entry['author'] for entry in parsed['entries']
    ])
    self.assertEqual(['2025', '2024'], [
      entry['discussion_year'] for entry in parsed['entries']
    ])
    self.assertEqual(
      'https://www.bookbrowse.com/bookclubs/discuss-the-nested-book',
      parsed['entries'][0]['source_url'])
    self.assertNotIn('source_url', parsed['entries'][1])

  def test_edgar_awards_parser_handles_table_dom_variation(self):
    from parser.edgar import EdgarAwardsParser

    parser = EdgarAwardsParser()
    html = '''
      <p>Total Records Found: 2</p>
      <table class="awards">
        <tr>
          <th><span>Award Year</span></th>
          <th>Award Category</th>
          <th>Title</th>
          <th>Author's Name</th>
        </tr>
        <tr>
          <td>2025</td>
          <td>Best Novel</td>
          <td>
            <strong>
              <span>The <em>Nested</em> Mystery</span>
            </strong>
          </td>
          <td><span>Winner <strong>Writer</strong></span></td>
        </tr>
        <tr>
          <td>2025</td>
          <td>Best Novel</td>
          <td><span>Finalist <em>Book</em></span></td>
          <td>Finalist Writer</td>
        </tr>
      </table>
    '''

    parsed = parser.parse(
      html,
      'https://edgarawards.com/category-list-best-novel/',
      'Edgar Award - Novel',
      'Best Novel')

    self.assertEqual(['The Nested Mystery', 'Finalist Book'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['winner', 'nominee'], [
      entry['result'] for entry in parsed['entries']
    ])
    self.assertEqual(['2025', '2025.01'], [
      entry['position'] for entry in parsed['entries']
    ])

  def test_cwa_dagger_parser_handles_card_dom_variation(self):
    from parser.cwa import CWADaggerParser

    parser = CWADaggerParser()
    html = '''
      <article>
        <a data-award="gold" href="/past-winners/nested-mystery">
          <span class="book-title">The <em>Nested</em> Mystery</span>
          <span class="book-author">Winner Writer tr. Translator Name</span>
          <span>2025 | Winner Gold Dagger</span>
        </a>
      </article>
      <nav><a rel="nofollow next" href="/past-winners/page/2/">Next</a></nav>
    '''

    parsed = parser.parse(
      html,
      'https://thecwa.co.uk/past-winners/?past_winners_awards[]=gold',
      'CWA Dagger - Gold Dagger',
      'Gold Dagger')

    self.assertEqual(['The Nested Mystery'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['Winner Writer'], [
      entry['author'] for entry in parsed['entries']
    ])
    self.assertEqual(['winner'], [
      entry['result'] for entry in parsed['entries']
    ])
    self.assertEqual(
      'https://thecwa.co.uk/past-winners/nested-mystery',
      parsed['entries'][0]['source_url'])
    self.assertEqual(
      'https://thecwa.co.uk/past-winners/page/2/',
      parser.next_page_url(html, 'https://thecwa.co.uk/past-winners/'))

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

  def test_isfdb_award_parser_base_handles_dom_variation(self):
    from parser.isfdb_base import ISFDBAwardParserBase

    parser = ISFDBAwardParserBase()
    parser.AWARD_NAME = 'Smoke ISFDB Award'
    html = '''
      <table>
        <tr>
          <th>Level</th>
          <th><span>Title</span></th>
          <th>Author's Name</th>
          <th>Award Year</th>
        </tr>
        <tr>
          <td>Winner</td>
          <td>
            <div class="record">
              <a data-extra="kept-out-of-title" href="/cgi-bin/title.cgi?99">
                The <span>Nested <em>Book</em></span>
              </a>
              <span class="note">Award Record # 123</span>
            </div>
          </td>
          <td><span>Nested <strong>Writer</strong></span></td>
          <td>2025</td>
        </tr>
      </table>
    '''

    parsed = parser.parse(
      html,
      'https://www.isfdb.org/cgi-bin/awardtype.cgi?1',
      'Smoke ISFDB - Novel',
      'Novel')

    self.assertEqual(['The Nested Book'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['Nested Writer'], [
      entry['author'] for entry in parsed['entries']
    ])
    self.assertEqual(
      'https://www.isfdb.org/cgi-bin/title.cgi?99',
      parsed['entries'][0]['source_url'])

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
