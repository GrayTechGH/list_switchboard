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

  def test_fetch_url_adds_ssl_diagnostics_for_certificate_failures(self):
    core = object.__new__(main.ListSwitchboardCore)
    logged = []
    core.debug_log = lambda message, section='general': logged.append((section, message))
    original_urlopen = main.urlopen

    def fail_urlopen(_request, timeout=30):
      raise main.URLError(main.ssl.SSLCertVerificationError(
        1,
        '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: '
        'certificate has expired (_ssl.c:1081)'))

    main.urlopen = fail_urlopen
    try:
      with self.assertRaises(RuntimeError) as caught:
        core.fetch_url('https://en.wikipedia.org/wiki/Nommo_Awards')
    finally:
      main.urlopen = original_urlopen

    message = str(caught.exception)
    self.assertIn('SSL fetch diagnostics:', message)
    self.assertIn('transport=urllib', message)
    self.assertIn('openssl=', message)
    self.assertIn('default cafile=', message)
    self.assertIn('calibre browser available=', message)
    self.assertTrue(any('SSL fetch diagnostics:' in item[1] for item in logged))

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
    self.assertEqual(365, len(names))
    self.assertIn('Theakston Old Peculier Crime Novel of the Year', names)
    self.assertIn('Hammett Prize', names)
    self.assertIn('Nero Award', names)
    self.assertIn('Strand Critics Award - Mystery Novel', names)
    self.assertIn('Strand Critics Award - Debut Mystery', names)
    self.assertIn('Pulitzer Prize - Fiction', names)
    self.assertIn('Pulitzer Prize - General Nonfiction', names)
    self.assertIn('National Book Award - Fiction', names)
    self.assertIn('National Book Award - Nonfiction', names)
    self.assertIn("National Book Award - Young People's Literature", names)
    self.assertIn('Baillie Gifford Prize', names)
    self.assertIn('PEN/John Kenneth Galbraith Award for Nonfiction', names)
    self.assertIn(
      'PEN/Diamonstein-Spielvogel Award for the Art of the Essay',
      names)
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
    self.assertIn(
      "Governor General's Literary Award - English Non-fiction",
      names)
    self.assertIn(
      "Governor General's Literary Award - English Young People's Literature - Text",
      names)
    self.assertIn(
      "Governor General's Literary Award - English Young People's Literature - Illustrated Books",
      names)
    self.assertIn(
      "Governor General's Literary Award - French Young People's Literature - Text",
      names)
    self.assertIn(
      "Governor General's Literary Award - French Young People's Literature - Illustrated Books",
      names)
    self.assertIn('Costa/Whitbread Book Award - Novel', names)
    self.assertIn('Costa/Whitbread Book Award - First Novel', names)
    self.assertIn('Costa/Whitbread Book Award - Biography', names)
    self.assertIn("Costa/Whitbread Book Award - Children's Book", names)
    self.assertIn('Costa/Whitbread Book of the Year', names)
    self.assertIn('Giller Prize', names)
    self.assertIn("Folio/Writers' Prize - Book of the Year", names)
    self.assertIn("Folio/Writers' Prize - Fiction", names)
    self.assertIn("Folio/Writers' Prize - Non-Fiction", names)
    self.assertIn('Goldsmiths Prize', names)
    self.assertIn('National Book Critics Circle Award - Fiction', names)
    self.assertIn('National Book Critics Circle Award - Nonfiction', names)
    self.assertIn('National Book Critics Circle Award - Biography', names)
    self.assertIn('National Book Critics Circle Award - Memoir/Autobiography', names)
    self.assertIn('National Book Critics Circle Award - Poetry', names)
    self.assertIn('National Book Critics Circle Award - Criticism', names)
    self.assertIn('National Book Critics Circle Award - John Leonard Prize', names)
    self.assertIn(
      'National Book Critics Circle Award - Gregg Barrios Book in Translation Prize',
      names)
    self.assertIn('Dublin Literary Award', names)
    self.assertIn('Center for Fiction First Novel Prize', names)
    self.assertIn('Walter Scott Prize', names)
    self.assertIn('James Tait Black Prize - Fiction', names)
    self.assertIn('James Tait Black Prize - Biography', names)
    self.assertIn('Miles Franklin Literary Award', names)
    self.assertIn('Nero Book Awards - Fiction', names)
    self.assertIn('Nero Book Awards - Debut Fiction', names)
    self.assertIn('Nero Book Awards - Non-Fiction', names)
    self.assertIn("Nero Book Awards - Children's Fiction", names)
    self.assertIn('Nero Gold Prize / Book of the Year', names)
    self.assertIn('Stella Prize', names)
    self.assertIn("Prime Minister's Literary Awards - Fiction", names)
    self.assertIn("Prime Minister's Literary Awards - Australian History", names)
    self.assertIn("Victorian Premier's Literary Awards - Fiction", names)
    self.assertIn("Victorian Premier's Literary Awards - Indigenous Writing", names)
    self.assertIn("NSW Premier's Literary Awards - Christina Stead Prize for Fiction", names)
    self.assertIn("NSW Premier's Literary Awards - Book of the Year", names)
    self.assertIn("NSW Premier's Literary Awards - People's Choice Award", names)
    self.assertIn("South Australian Literary Awards - Premier's Award", names)
    self.assertIn("South Australian Literary Awards - Fiction", names)
    self.assertIn("South Australian Literary Awards - Non-Fiction", names)
    self.assertIn("South Australian Literary Awards - Children's Literature", names)
    self.assertIn("South Australian Literary Awards - Young Adult Fiction", names)
    self.assertIn('ACT Book of the Year Award', names)
    self.assertIn('RWA RITA Awards', names)
    self.assertIn('RWA Vivian Awards', names)
    self.assertIn('RNA Joan Hessayon Award for New Writers', names)
    self.assertIn('Ripped Bodice Awards for Excellence in Romance Fiction', names)
    self.assertIn("Romantic Times Reviewers' Choice Awards - Romance Categories", names)
    self.assertIn('Lambda Literary Awards - Romance Categories', names)
    self.assertIn('Romance Writers of Australia RUBY Awards', names)
    self.assertIn('Australian Romance Readers Awards', names)
    self.assertIn('HOLT Medallion', names)
    self.assertIn("Booksellers' Best Award", names)
    self.assertIn('Goodreads Choice Awards - Romance', names)
    self.assertIn('Goodreads Choice Awards - Romantasy', names)
    self.assertIn('Goodreads Choice Awards - Horror', names)
    self.assertIn('Goodreads Choice Awards - Graphic Novels & Comics (discontinued)', names)
    self.assertIn('William C. Morris YA Debut Award', names)
    self.assertIn('YALSA Award for Excellence in Nonfiction for Young Adults', names)
    self.assertIn('Michael L. Printz Award', names)
    self.assertIn('Carnegie Medal for Writing', names)
    self.assertIn('John Newbery Medal', names)
    self.assertIn('CBCA Book of the Year - Older Readers', names)
    self.assertIn('CBCA Book of the Year - Younger Readers', names)
    self.assertIn('CBCA Book of the Year - Middle Readers', names)
    self.assertIn('CBCA Book of the Year - Early Childhood', names)
    self.assertIn('CBCA Book of the Year - Picture Book', names)
    self.assertIn('CBCA Book of the Year - Eve Pownall', names)
    self.assertIn('CBCA Book of the Year - New Illustrator', names)
    self.assertIn("Writers' Trust - Atwood Gibson Fiction Prize", names)
    self.assertIn("Writers' Trust - Hilary Weston Nonfiction Prize", names)
    self.assertIn('British Fantasy - Horror Novel', names)
    self.assertIn('British Fantasy - Fantasy Novel', names)
    self.assertIn('British Fantasy - Best Novel (pre-2012 August Derleth)', names)
    self.assertIn('International Horror Guild - Novel', names)
    self.assertIn('International Horror Guild - Illustrated Narrative', names)
    self.assertIn('Australasian Shadows - Novel', names)
    self.assertIn('Australasian Shadows - Non-Fiction', names)
    self.assertIn('This Is Horror - Novel', names)
    self.assertIn('This Is Horror - Anthology', names)
    self.assertIn('Splatterpunk - Novel', names)
    self.assertIn('Splatterpunk - Anthology', names)

  def test_core_can_discover_recipes_before_gui_current_db_exists(self):
    class StartupGui:
      pass

    core = main.ListSwitchboardCore(StartupGui(), lambda: None)
    names = [recipe.NAME for recipe in core.available_import_recipes()]

    self.assertIn('r/Fantasy Top Novels 2025', names)

  def test_world_fantasy_fetchers_are_available_under_fantasy_and_horror(self):
    from parser.base import CATEGORY_FANTASY, CATEGORY_HORROR_DARK_FICTION
    from url_fetcher import available_url_fetchers

    expected_ids = {
      'world_fantasy_novel',
      'world_fantasy_novella',
      'world_fantasy_anthology',
      'world_fantasy_collection',
      'world_fantasy_collection_anthology',
    }
    fetchers = [
      fetcher for fetcher in available_url_fetchers()
      if fetcher.source_id in expected_ids
    ]

    self.assertEqual(expected_ids, {fetcher.source_id for fetcher in fetchers})
    for fetcher in fetchers:
      filters = [item['label'] for item in fetcher.get_filter_list()]
      self.assertIn(CATEGORY_FANTASY, filters)
      self.assertIn(CATEGORY_HORROR_DARK_FICTION, filters)

  def test_british_fantasy_parser_merges_official_and_sfadb_shortlists(self):
    from parser.british_fantasy import (
      BFS_WINNERS_URL, BritishFantasyParser, SFADB_URL,
    )

    parser = BritishFantasyParser()
    winners_html = '''
      <h1>BFA Winners</h1>
      <p>2025</p>
      <ul>
        <li>The August Derleth Award for Best Horror Novel:
            My Darling Beautiful Thing by Johanna Van Veen</li>
      </ul>
      <p>2012</p>
      <ul>
        <li>Horror Novel (the August Derleth Award): The Ritual, Adam Nevill (Pan Books)</li>
      </ul>
    '''
    shortlist_html = '''
      <h1>The British Fantasy Awards 2026 Shortlists!</h1>
      <h2>Best Horror Novel (The August Derleth Award)</h2>
      <ul>
        <li>Witchcraft for Wayward Girls, Grady Hendrix (Tor Nightfire)</li>
        <li>The Buffalo Hunter Hunter, Stephen Graham Jones (Titan Books)</li>
      </ul>
    '''
    sfadb_overview = '''
      <a href="/British_Fantasy_Awards_2025">2025</a>
      <a href="/British_Fantasy_Awards_2012">2012</a>
    '''
    sfadb_pages = {
      'https://www.sfadb.com/British_Fantasy_Awards_2025': '''
        <div class="categoryblock">
          <div class="category">Horror Novel (august Derleth Award)</div>
          <ul>
            <li>Winner: My Darling Dreadful Thing, Johanna van Veen (Poisoned Pen)</li>
            <li>Among the Living, Tim Lebbon (Titan)</li>
            <li>Bury Your Gays, Chuck Tingle (Titan)</li>
          </ul>
        </div>
      ''',
      'https://www.sfadb.com/British_Fantasy_Awards_2012': '''
        <div class="categoryblock">
          <div class="category">August Derleth Award (horror Novel)</div>
          <ul>
            <li>Winner: The Ritual, Adam Nevill (Pan)</li>
          </ul>
        </div>
      ''',
    }

    winners = parser.parse_bfs_winners(
      winners_html,
      BFS_WINNERS_URL,
      'British Fantasy - Horror Novel',
      'Horror Novel',
      ('best horror novel', 'august derleth award horror novel'),
      min_year=2012)
    shortlist = parser.parse_bfs_shortlist(
      shortlist_html,
      'https://britishfantasysociety.org/the-british-fantasy-awards-2026-shortlists/',
      'British Fantasy - Horror Novel',
      'Horror Novel',
      ('best horror novel', 'horror novel the august derleth award'),
      min_year=2012)
    sfadb = parser.parse_sfadb(
      sfadb_overview,
      SFADB_URL,
      'British Fantasy - Horror Novel',
      'Horror Novel',
      ('horror novel', 'august derleth award horror novel'),
      fetch_url=lambda url: sfadb_pages[url],
      min_year=2012)

    parsed = parser.combine_results(
      'British Fantasy - Horror Novel',
      BFS_WINNERS_URL,
      winners,
      shortlist,
      sfadb)

    rows = {
      (entry['award_year'], entry['title']): entry
      for entry in parsed['entries']
    }
    self.assertEqual('winner', rows[('2025', 'My Darling Dreadful Thing')]['result'])
    self.assertEqual('2025', rows[('2025', 'My Darling Dreadful Thing')]['position'])
    self.assertEqual('shortlisted', rows[('2025', 'Among the Living')]['result'])
    self.assertEqual('shortlisted', rows[('2026', 'Witchcraft for Wayward Girls')]['result'])
    self.assertEqual('2026.01', rows[('2026', 'Witchcraft for Wayward Girls')]['position'])
    self.assertNotIn(('2025', 'My Darling Beautiful Thing'), rows)
    self.assertTrue(any('current-cycle only' in note for note in parsed['notes']))
    self.assertTrue(any('Corrected 2025' in note for note in parsed['notes']))

  def test_british_fantasy_best_novel_stops_before_2012_split(self):
    from parser.british_fantasy import BFS_WINNERS_URL, BritishFantasyParser

    parser = BritishFantasyParser()
    winners_html = '''
      <p>2012</p>
      <ul>
        <li>Horror Novel (the August Derleth Award): The Ritual, Adam Nevill (Pan Books)</li>
      </ul>
      <p>2010</p>
      <ul>
        <li>Novel: One, Conrad Williams (Virgin Books)</li>
      </ul>
      <p>2011</p>
      <ul>
        <li>Novel: No award</li>
      </ul>
    '''

    parsed = parser.parse_bfs_winners(
      winners_html,
      BFS_WINNERS_URL,
      'British Fantasy - Best Novel (pre-2012 August Derleth)',
      'Best Novel',
      ('novel', 'best novel'),
      max_year=2011)

    self.assertEqual(['One'], [entry['title'] for entry in parsed['entries']])
    self.assertEqual('2010', parsed['entries'][0]['position'])
    self.assertTrue(any('2011 Best Novel has no award row' in note for note in parsed['notes']))

  def test_british_fantasy_fetchers_are_registered_with_expected_metadata(self):
    from parser.base import (
      CATEGORY_FANTASY, CATEGORY_HORROR_DARK_FICTION, CATEGORY_NONFICTION,
    )
    from url_fetcher import available_url_fetchers

    expected_ids = {
      'british_fantasy_horror_novel',
      'british_fantasy_fantasy_novel',
      'british_fantasy_best_novel',
      'british_fantasy_novella',
      'british_fantasy_anthology',
      'british_fantasy_collection',
      'british_fantasy_nonfiction',
    }
    fetchers = [
      fetcher for fetcher in available_url_fetchers()
      if fetcher.source_id in expected_ids
    ]

    self.assertEqual(expected_ids, {fetcher.source_id for fetcher in fetchers})
    self.assertTrue(all(fetcher.options['match_series'] is False for fetcher in fetchers))
    self.assertEqual(
      ({'label': 'Automatic', 'value': 'automatic'},),
      fetchers[0].source_choices())
    filters_by_id = {
      fetcher.source_id: [item['label'] for item in fetcher.get_filter_list()]
      for fetcher in fetchers
    }
    self.assertEqual([CATEGORY_HORROR_DARK_FICTION],
                     filters_by_id['british_fantasy_horror_novel'])
    self.assertEqual([CATEGORY_FANTASY],
                     filters_by_id['british_fantasy_fantasy_novel'])
    self.assertIn(CATEGORY_NONFICTION,
                  filters_by_id['british_fantasy_nonfiction'])

  def test_international_horror_guild_official_parser_reads_mixed_shapes(self):
    from parser.international_horror_guild import (
      OFFICIAL_FINAL_URL, InternationalHorrorGuildParser,
    )

    parser = InternationalHorrorGuildParser()
    official_html = '''
      <p>The INTERNATIONAL HORROR GUILD AWARDS for WORKS from 2007</p>
      <font><b>NOVEL</b></font>
      <p><font><b><i>The Terror</i>. Dan Simmons (Little, Brown)</b></font></p>
      <p>Also nominated:</p>
      <ul>
        <li><i>Grin of the Dark</i>. Ramsey Campbell (PS Publishing)</li>
      </ul>
      <font><b>SHORT FICTION</b></font>
      <p><font><b>"Honey in the Wound". Nancy Etchemendy</b></font></p>
      <p>2006</p>
      <b>NOVEL</b><br>
      <b><font>Conrad Williams. <i>The Unblemished</i> (Earthling)</font></b>
      <p><i>Other Nominees:</i></p>
      <ul>
        <li>Keith Donohue. <i>The Stolen Child</i> (Doubleday)</li>
      </ul>
      <p>2004</p>
      <font><b>NOVEL: Ramsey Campbell. THE OVERNIGHT (PS Publishing)</b></font>
      <font><b><i>Also nominated:</i></b></font>
      <ul>
        <li>Elizabeth Hand. MORTAL LOVE (William Morrow)</li>
      </ul>
      <p>1997</p>
      <p>No nominations are listed due to the changeover in administration.</p>
      <ul><li><b>NOVEL: Nazareth Hill by Ramsey Campbell</b></li></ul>
      <p>1996</p>
      <p>No nominations are available.</p>
      <ul><li><b>NOVEL: The 37th Mandala by Marc Laidlaw</b></li></ul>
    '''

    parsed = parser.parse_official_page(
      official_html,
      OFFICIAL_FINAL_URL,
      'International Horror Guild - Novel',
      'Novel',
      ('novel',))
    rows = {
      (entry['award_year'], entry['title']): entry
      for entry in parsed['entries']
    }

    self.assertEqual('winner', rows[('2007', 'The Terror')]['result'])
    self.assertEqual('shortlisted', rows[('2007', 'Grin of the Dark')]['result'])
    self.assertEqual('winner', rows[('2006', 'The Unblemished')]['result'])
    self.assertEqual('shortlisted', rows[('2006', 'The Stolen Child')]['result'])
    self.assertEqual('THE OVERNIGHT', rows[('2004', 'THE OVERNIGHT')]['title'])
    self.assertEqual('shortlisted', rows[('2004', 'MORTAL LOVE')]['result'])
    self.assertEqual('winner', rows[('1997', 'Nazareth Hill')]['result'])
    self.assertEqual('winner', rows[('1996', 'The 37th Mandala')]['result'])
    self.assertFalse(any(entry['title'] == 'Honey in the Wound'
                         for entry in parsed['entries']))
    self.assertTrue(any('1997 page states nominations are not listed' in note
                        for note in parsed['notes']))
    self.assertTrue(any('1996 page states' in note for note in parsed['notes']))

  def test_international_horror_guild_official_parser_preserves_tied_winners(self):
    from parser.international_horror_guild import (
      OFFICIAL_PREVIOUS_URL, InternationalHorrorGuildParser,
    )

    parser = InternationalHorrorGuildParser()
    official_html = '''
      <p>2006</p>
      <b>COLLECTION (Single Author)</b> [TIE]<br>
      <b><font>Terry Dowling. <i>Basic Black</i> (CD Publications)<br>
      Glen Hirshberg. <i>American Morons</i> (Earthling)</font></b>
      <p><i>Other Nominees:</i></p>
      <ul>
        <li>Joel Lane. <i>The Lost District and Other Stories</i> (Night Shade)</li>
      </ul>
    '''

    parsed = parser.parse_official_page(
      official_html,
      OFFICIAL_PREVIOUS_URL,
      'International Horror Guild - Collection',
      'Collection',
      ('collection', 'collection single author', 'fiction collection'))
    rows = {
      entry['title']: entry
      for entry in parsed['entries']
    }

    self.assertEqual('winner', rows['Basic Black']['result'])
    self.assertEqual('2006', rows['Basic Black']['position'])
    self.assertEqual('winner', rows['American Morons']['result'])
    self.assertEqual('2006', rows['American Morons']['position'])
    self.assertEqual('shortlisted', rows['The Lost District and Other Stories']['result'])

  def test_international_horror_guild_sfadb_uses_eligibility_year(self):
    from parser.international_horror_guild import (
      InternationalHorrorGuildParser, SFADB_URL,
    )

    parser = InternationalHorrorGuildParser()
    overview = '<a href="/International_Horror_Guild_Awards_2008">2008</a>'
    pages = {
      'https://www.sfadb.com/International_Horror_Guild_Awards_2008': '''
        <div class="AwYrTimePlace"><b>Eligibility Year</b>: 2007</div>
        <div class="categoryblock">
          <div class="category">Novel</div>
          <ul>
            <li><span class="winner">Winner:</span> <b>The Terror</b>, Dan Simmons (Little, Brown)</li>
            <li><b>Generation Loss</b>, Elizabeth Hand (Small Beer Press)</li>
          </ul>
        </div>
      ''',
    }

    parsed = parser.parse_sfadb(
      overview,
      SFADB_URL,
      'International Horror Guild - Novel',
      'Novel',
      ('novel',),
      fetch_url=lambda url: pages[url])
    rows = {entry['title']: entry for entry in parsed['entries']}

    self.assertEqual('2007', rows['The Terror']['award_year'])
    self.assertEqual('2007', rows['The Terror']['position'])
    self.assertEqual('shortlisted', rows['Generation Loss']['result'])
    self.assertTrue(any('replacement fallback' in note for note in parsed['notes']))

  def test_international_horror_guild_fetchers_metadata_fallback_and_registry(self):
    from parser.base import CATEGORY_HORROR_DARK_FICTION, CATEGORY_NONFICTION
    from parser.international_horror_guild import (
      OFFICIAL_FINAL_URL, SFADB_URL,
    )
    from url_fetcher import available_url_fetchers

    expected_ids = {
      'international_horror_guild_novel',
      'international_horror_guild_first_novel',
      'international_horror_guild_long_fiction',
      'international_horror_guild_mid_length_fiction',
      'international_horror_guild_collection',
      'international_horror_guild_anthology',
      'international_horror_guild_nonfiction',
      'international_horror_guild_illustrated_narrative',
    }
    fetchers = [
      fetcher for fetcher in available_url_fetchers()
      if fetcher.source_id in expected_ids
    ]

    self.assertEqual(expected_ids, {fetcher.source_id for fetcher in fetchers})
    self.assertTrue(all(fetcher.options['match_series'] is False for fetcher in fetchers))
    self.assertEqual([
      {'label': 'Automatic', 'value': 'automatic'},
      {'label': 'International Horror Guild', 'value': 0},
      {'label': 'SFADB', 'value': 1},
    ], list(fetchers[0].source_choices()))

    filters_by_id = {
      fetcher.source_id: [item['label'] for item in fetcher.get_filter_list()]
      for fetcher in fetchers
    }
    self.assertEqual([CATEGORY_HORROR_DARK_FICTION],
                     filters_by_id['international_horror_guild_novel'])
    self.assertIn(CATEGORY_NONFICTION,
                  filters_by_id['international_horror_guild_nonfiction'])

    sfadb_overview = '<a href="/International_Horror_Guild_Awards_2008">2008</a>'
    sfadb_page = '''
      <div class="AwYrTimePlace"><b>Eligibility Year</b>: 2007</div>
      <div class="categoryblock">
        <div class="category">Novel</div>
        <ul><li><span class="winner">Winner:</span> <b>The Terror</b>, Dan Simmons</li></ul>
      </div>
    '''
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if url == SFADB_URL:
        return sfadb_overview
      if url == 'https://www.sfadb.com/International_Horror_Guild_Awards_2008':
        return sfadb_page
      if url == OFFICIAL_FINAL_URL:
        return '<html></html>'
      raise AssertionError(url)

    parsed = [
      fetcher for fetcher in fetchers
      if fetcher.source_id == 'international_horror_guild_novel'
    ][0].fetch_and_parse(fetch_url, source_choice=1)

    self.assertEqual('The Terror', parsed['entries'][0]['title'])
    self.assertEqual('2007', parsed['entries'][0]['award_year'])
    self.assertNotIn(OFFICIAL_FINAL_URL, fetched)

    registry_ids = [fetcher.source_id for fetcher in available_url_fetchers()]
    self.assertLess(
      registry_ids.index('british_fantasy_nonfiction'),
      registry_ids.index('international_horror_guild_novel'))
    self.assertLess(
      registry_ids.index('international_horror_guild_illustrated_narrative'),
      registry_ids.index('arthur_c_clarke_award_novel'))

  def test_australasian_shadows_official_current_finalists(self):
    from parser.australasian_shadows import (
      OFFICIAL_CURRENT_API_URL, AustralasianShadowsParser,
    )

    parser = AustralasianShadowsParser()
    current_json = json.dumps([{
      'title': {'rendered': 'Australasian Shadows Awards'},
      'content': {'rendered': '''
        <h2>2025 Australasian Shadows Awards finalists</h2>
        <p><strong>Novel</strong></p>
        <ul>
          <li>A. G. Slatter - The Crimson Road</li>
          <li>Madeleine D'Este - Black Soil White Bread</li>
        </ul>
        <p><strong>Edited Work</strong></p>
        <p>No shortlist, but a winner will be announced at the presentation.</p>
        <p><strong>Short Fiction</strong></p>
        <ul><li>Short Story by Someone</li></ul>
      '''},
    }])

    parsed = parser.parse_official_document(
      current_json,
      OFFICIAL_CURRENT_API_URL,
      'Australasian Shadows - Novel',
      'Novel',
      ('novel',))
    rows = {entry['title']: entry for entry in parsed['entries']}

    self.assertEqual('shortlisted', rows['The Crimson Road']['result'])
    self.assertEqual('A. G. Slatter', rows['The Crimson Road']['author'])
    self.assertEqual('2025.01', rows['The Crimson Road']['position'])
    self.assertEqual('shortlisted', rows['Black Soil White Bread']['result'])
    self.assertNotIn('Short Story', rows)

    edited = parser.parse_official_document(
      current_json,
      OFFICIAL_CURRENT_API_URL,
      'Australasian Shadows - Edited Work',
      'Edited Work',
      ('edited work',))
    self.assertEqual([], edited['entries'])
    self.assertTrue(any('No shortlist' in note for note in edited['notes']))

  def test_australasian_shadows_official_winners_shortlists_and_ties(self):
    from parser.australasian_shadows import (
      OFFICIAL_2024_WINNERS_API_URL, AustralasianShadowsParser,
    )

    parser = AustralasianShadowsParser()
    winners_json = json.dumps([{
      'title': {'rendered': '2024 Australasian Shadows Awards Winners'},
      'content': {'rendered': '''
        <h2>Novel</h2>
        <p>Winner: The Dead Spot by Caroline Angel</p>
        <p>Shortlist:</p>
        <ul>
          <li>The Briar Book of the Dead by Angela Slatter</li>
          <li>The Underhistory by Kaaron Warren</li>
        </ul>
        <h2>Graphic novel or comic</h2>
        <p>Midnight by Pat Grant / The Shadow Line by Jane Doe</p>
        <p>No shortlist.</p>
      '''},
    }])

    novel = parser.parse_official_document(
      winners_json,
      OFFICIAL_2024_WINNERS_API_URL,
      'Australasian Shadows - Novel',
      'Novel',
      ('novel',))
    novel_rows = {entry['title']: entry for entry in novel['entries']}
    self.assertEqual('winner', novel_rows['The Dead Spot']['result'])
    self.assertEqual('2024', novel_rows['The Dead Spot']['position'])
    self.assertEqual('shortlisted', novel_rows['The Underhistory']['result'])

    graphic = parser.parse_official_document(
      winners_json,
      OFFICIAL_2024_WINNERS_API_URL,
      'Australasian Shadows - Graphic Novel/Comic',
      'Graphic Novel/Comic',
      ('graphic novel or comic',))
    graphic_rows = {entry['title']: entry for entry in graphic['entries']}
    self.assertEqual('winner', graphic_rows['Midnight']['result'])
    self.assertEqual('2024', graphic_rows['Midnight']['position'])
    self.assertEqual('winner', graphic_rows['The Shadow Line']['result'])
    self.assertEqual('2024', graphic_rows['The Shadow Line']['position'])
    self.assertTrue(any('No shortlist' in note for note in graphic['notes']))

  def test_australasian_shadows_wikipedia_fallback_and_category_filtering(self):
    from parser.australasian_shadows import (
      WIKIPEDIA_URL, AustralasianShadowsParser,
    )

    parser = AustralasianShadowsParser()
    wiki_html = '''
      <h2>2024</h2>
      <h3>Novel</h3>
      <p>Winner: The Dead Spot by Caroline Angel</p>
      <p>Nominees:</p>
      <ul><li>The Underhistory by Kaaron Warren</li></ul>
      <h3>Short Fiction</h3>
      <p>Winner: Tiny Horror by Story Writer</p>
      <h2>2008</h2>
      <h3>Novels, anthologies, and short stories</h3>
      <p>Winner: Mixed Bag by Mixed Writer</p>
    '''

    parsed = parser.parse_wikipedia(
      wiki_html,
      WIKIPEDIA_URL,
      'Australasian Shadows - Novel',
      'Novel',
      ('novel',))
    rows = {entry['title']: entry for entry in parsed['entries']}

    self.assertEqual('winner', rows['The Dead Spot']['result'])
    self.assertEqual('shortlisted', rows['The Underhistory']['result'])
    self.assertNotIn('Tiny Horror', rows)
    self.assertNotIn('Mixed Bag', rows)
    self.assertTrue(any('replacement fallback' in note for note in parsed['notes']))

  def test_australasian_shadows_fetchers_metadata_fallback_and_registry(self):
    from parser.australasian_shadows import (
      OFFICIAL_CURRENT_API_URL, WIKIPEDIA_URL,
    )
    from parser.base import (
      CATEGORY_HORROR_DARK_FICTION, CATEGORY_NONFICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
    )
    from url_fetcher import available_url_fetchers

    expected_ids = {
      'australasian_shadows_novel',
      'australasian_shadows_long_fiction',
      'australasian_shadows_collected_work',
      'australasian_shadows_edited_work',
      'australasian_shadows_graphic_novel',
      'australasian_shadows_nonfiction',
    }
    fetchers = [
      fetcher for fetcher in available_url_fetchers()
      if fetcher.source_id in expected_ids
    ]

    self.assertEqual(expected_ids, {fetcher.source_id for fetcher in fetchers})
    self.assertTrue(all(fetcher.options['match_series'] is False for fetcher in fetchers))
    self.assertEqual([
      {'label': 'Automatic', 'value': 'automatic'},
      {'label': 'Australasian Horror Writers Association', 'value': 0},
      {'label': 'Wikipedia', 'value': 1},
    ], list(fetchers[0].source_choices()))

    filters_by_id = {
      fetcher.source_id: [item['label'] for item in fetcher.get_filter_list()]
      for fetcher in fetchers
    }
    self.assertEqual(
      [CATEGORY_HORROR_DARK_FICTION, CATEGORY_REGIONAL_NATIONAL_AWARDS],
      filters_by_id['australasian_shadows_novel'])
    self.assertIn(CATEGORY_NONFICTION,
                  filters_by_id['australasian_shadows_nonfiction'])

    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if url == WIKIPEDIA_URL:
        return '''
          <h2>2024</h2>
          <h3>Novel</h3>
          <p>Winner: The Dead Spot by Caroline Angel</p>
        '''
      raise AssertionError(url)

    parsed = [
      fetcher for fetcher in fetchers
      if fetcher.source_id == 'australasian_shadows_novel'
    ][0].fetch_and_parse(fetch_url, source_choice=1)

    self.assertEqual('The Dead Spot', parsed['entries'][0]['title'])
    self.assertNotIn(OFFICIAL_CURRENT_API_URL, fetched)

    registry_ids = [fetcher.source_id for fetcher in available_url_fetchers()]
    self.assertLess(
      registry_ids.index('international_horror_guild_illustrated_narrative'),
      registry_ids.index('australasian_shadows_novel'))
    self.assertLess(
      registry_ids.index('australasian_shadows_nonfiction'),
      registry_ids.index('arthur_c_clarke_award_novel'))

  def test_this_is_horror_official_current_ballot_and_filtering(self):
    from parser.this_is_horror import (
      OFFICIAL_AWARDS_API_URL, OFFICIAL_AWARDS_URL, ThisIsHorrorParser,
    )

    parser = ThisIsHorrorParser()
    current_json = json.dumps([
      {
        'title': {'rendered': 'Awards'},
        'link': 'https://www.thisishorror.co.uk/about/awards/',
        'content': {'rendered': '<p>Unrelated awards page</p>'},
      },
      {
        'title': {'rendered': 'Awards'},
        'link': OFFICIAL_AWARDS_URL,
        'content': {'rendered': '''
          <h1>This Is Horror Awards 2024 are now open</h1>
          <h2>Novel of the Year</h2>
          <ol>
            <li>All the Fiends of Hell by Adam Nevill</li>
            <li>American Rapture by CJ Leede</li>
          </ol>
          <h2>Fiction Podcast of the Year</h2>
          <ol><li>Podcast Row by Audio Host</li></ol>
          <h2>Previous Winners</h2>
        '''},
      },
    ])

    parsed = parser.parse_official_current(
      current_json,
      OFFICIAL_AWARDS_API_URL,
      'This Is Horror - Novel',
      'Novel',
      ('novel', 'novel of the year'))
    rows = {entry['title']: entry for entry in parsed['entries']}

    self.assertEqual(['All the Fiends of Hell', 'American Rapture'], list(rows))
    self.assertEqual('2024.01', rows['All the Fiends of Hell']['position'])
    self.assertEqual('shortlisted', rows['American Rapture']['result'])
    self.assertEqual('Adam Nevill', rows['All the Fiends of Hell']['author'])
    self.assertNotIn('Podcast Row', rows)
    self.assertTrue(any('current ballot' in note for note in parsed['notes']))
    self.assertTrue(any('no official 2025' in note for note in parsed['notes']))

  def test_this_is_horror_official_winners_runner_up_and_award_year(self):
    from parser.this_is_horror import OFFICIAL_AWARDS_URL, ThisIsHorrorParser

    parser = ThisIsHorrorParser()
    winners_json = json.dumps([{
      'title': {'rendered': 'This Is Horror Awards 2021: The Winners'},
      'link': 'https://www.thisishorror.co.uk/awards/this-is-horror-awards-2021-the-winners/',
      'date': '2023-08-10T10:00:00',
      'content': {'rendered': '''
        <h1>This Is Horror Awards 2021: The Winners</h1>
        <h2>Novel of the Year</h2>
        <p><strong>Winner:</strong> My Heart Is a Chainsaw by Stephen Graham Jones
        <strong>Runner-up:</strong> This Thing Between Us by Gus Moreno.</p>
        <h2>Anthology of the Year</h2>
        <p>Winner: When Things Get Dark, edited by Ellen Datlow
        Runner-up: There Is No Death, There Are No Dead, edited by Aaron J. French and Jess Landry</p>
        <h2>Publisher of the Year</h2>
        <p>Winner: Example Press by Press Team</p>
      '''},
    }])

    novel = parser.parse_official_winners(
      winners_json,
      OFFICIAL_AWARDS_URL,
      'This Is Horror - Novel',
      'Novel',
      ('novel', 'novel of the year'))
    anthology = parser.parse_official_winners(
      winners_json,
      OFFICIAL_AWARDS_URL,
      'This Is Horror - Anthology',
      'Anthology',
      ('anthology', 'anthology of the year'))

    novel_rows = {entry['title']: entry for entry in novel['entries']}
    anthology_rows = {entry['title']: entry for entry in anthology['entries']}

    self.assertEqual('2021', novel_rows['My Heart Is a Chainsaw']['award_year'])
    self.assertEqual('2021', novel_rows['My Heart Is a Chainsaw']['position'])
    self.assertEqual('winner', novel_rows['My Heart Is a Chainsaw']['result'])
    self.assertEqual('2021.01', novel_rows['This Thing Between Us']['position'])
    self.assertEqual('shortlisted', novel_rows['This Thing Between Us']['result'])
    self.assertEqual('Ellen Datlow', anthology_rows['When Things Get Dark']['author'])
    self.assertEqual(
      'Aaron J. French and Jess Landry',
      anthology_rows['There Is No Death, There Are No Dead']['author'])
    self.assertTrue(any('runner-up rows' in note for note in novel['notes']))

  def test_this_is_horror_goodreads_supplement_and_category_filtering(self):
    from parser.this_is_horror import GOODREADS_URL, ThisIsHorrorParser

    parser = ThisIsHorrorParser()
    goodreads_html = '''
      <h2>Winners</h2>
      <div>A Head Full of Ghosts</div><div>by</div><div>Paul Tremblay</div>
      <div>This is Horror Award for Novel (2015)</div>
      <div>Bad Comic</div><div>by</div><div>Panel Writer</div>
      <div>This is Horror Award for Comic (2015)</div>
      <h2>nominees</h2>
      <div>Lost Girl</div><div>by</div><div>Adam L.G. Nevill</div>
      <div>This is Horror Award Nominee for Novel (Runner-Up) (2015)</div>
      <div>Short Piece</div><div>by</div><div>Short Writer</div>
      <div>This is Horror Award Nominee for Short Fiction (finalist) (2015)</div>
    '''

    parsed = parser.parse_goodreads(
      goodreads_html,
      GOODREADS_URL,
      'This Is Horror - Novel',
      'Novel',
      ('novel',))
    rows = {entry['title']: entry for entry in parsed['entries']}

    self.assertEqual('winner', rows['A Head Full of Ghosts']['result'])
    self.assertEqual('2015', rows['A Head Full of Ghosts']['position'])
    self.assertEqual('shortlisted', rows['Lost Girl']['result'])
    self.assertEqual('2015.01', rows['Lost Girl']['position'])
    self.assertNotIn('Bad Comic', rows)
    self.assertNotIn('Short Piece', rows)
    self.assertTrue(any('historical nominee' in note for note in parsed['notes']))

  def test_this_is_horror_fetchers_metadata_merge_and_registry(self):
    from parser.base import CATEGORY_HORROR_DARK_FICTION
    from parser.this_is_horror import (
      GOODREADS_URL,
      OFFICIAL_AWARDS_API_URL,
      OFFICIAL_AWARDS_URL,
      OFFICIAL_WINNERS_SEARCH_API_URL,
    )
    from url_fetcher import available_url_fetchers

    expected_ids = {
      'this_is_horror_novel',
      'this_is_horror_novella',
      'this_is_horror_short_story_collection',
      'this_is_horror_anthology',
    }
    fetchers = [
      fetcher for fetcher in available_url_fetchers()
      if fetcher.source_id in expected_ids
    ]

    self.assertEqual(expected_ids, {fetcher.source_id for fetcher in fetchers})
    self.assertTrue(all(fetcher.options['match_series'] is False for fetcher in fetchers))
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},),
                     fetchers[0].source_choices())
    for fetcher in fetchers:
      filters = [item['label'] for item in fetcher.get_filter_list()]
      self.assertIn(CATEGORY_HORROR_DARK_FICTION, filters)

    winner_api_url = 'https://www.thisishorror.co.uk/wp-json/wp/v2/posts/43497'
    by_url = {
      OFFICIAL_AWARDS_API_URL: json.dumps([{
        'title': {'rendered': 'Awards'},
        'link': OFFICIAL_AWARDS_URL,
        'content': {'rendered': '''
          <h1>This Is Horror Awards 2024 are now open</h1>
          <h2>Novel of the Year</h2>
          <ol><li>Small Town Horror by Ronald Malfi</li></ol>
          <h2>Previous Winners</h2>
        '''},
      }]),
      OFFICIAL_WINNERS_SEARCH_API_URL: json.dumps([{
        'title': 'This Is Horror Awards 2024: The Winners',
        '_links': {'self': [{'href': winner_api_url}]},
      }]),
      winner_api_url: json.dumps([{
        'title': {'rendered': 'This Is Horror Awards 2024: The Winners'},
        'link': 'https://www.thisishorror.co.uk/this-is-horror-awards-2024-the-winners/',
        'content': {'rendered': '''
          <h1>This Is Horror Awards 2024: The Winners</h1>
          <h2>Novel of the Year</h2>
          <p>Winner: Small Town Horror by Ronald Malfi
          Runner-up: American Rapture by CJ Leede</p>
        '''},
      }]),
      GOODREADS_URL: '''
        <div>Small Town Horror</div><div>by</div><div>Ronald Malfi</div>
        <div>This is Horror Award for Novel (2024)</div>
        <div>All the Fiends of Hell</div><div>by</div><div>Adam Nevill</div>
        <div>This is Horror Award Nominee for Novel (finalist) (2024)</div>
      ''',
    }
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      return by_url[url]

    novel = [
      fetcher for fetcher in fetchers
      if fetcher.source_id == 'this_is_horror_novel'
    ][0]
    parsed = novel.fetch_and_parse(fetch_url)
    rows = {entry['title']: entry for entry in parsed['entries']}

    self.assertEqual('winner', rows['Small Town Horror']['result'])
    self.assertEqual('2024', rows['Small Town Horror']['position'])
    self.assertEqual('shortlisted', rows['American Rapture']['result'])
    self.assertEqual('shortlisted', rows['All the Fiends of Hell']['result'])
    self.assertFalse(parsed['match_series'])
    self.assertIn(OFFICIAL_AWARDS_API_URL, fetched)
    self.assertIn(GOODREADS_URL, fetched)

    registry_ids = [fetcher.source_id for fetcher in available_url_fetchers()]
    self.assertLess(
      registry_ids.index('australasian_shadows_nonfiction'),
      registry_ids.index('this_is_horror_novel'))
    self.assertLess(
      registry_ids.index('this_is_horror_anthology'),
      registry_ids.index('arthur_c_clarke_award_novel'))

  def test_splatterpunk_official_current_nominees_and_filtering(self):
    from parser.splatterpunk import (
      OFFICIAL_AWARDS_API_URL, OFFICIAL_AWARDS_URL, SplatterpunkParser,
    )

    parser = SplatterpunkParser()
    current_json = json.dumps([{
      'title': {'rendered': '2026 Splatterpunk Awards'},
      'link': OFFICIAL_AWARDS_URL,
      'content': {'rendered': '''
        <h1>2026 Splatterpunk Awards</h1>
        <p>We are pleased to announce the 2026 Splatterpunk Award nominees.</p>
        <h4>BEST NOVEL</h4>
        <p>-- <em>At Dark, I Become Loathsome</em> by Eric LaRocca (Blackstone Publishing)</p>
        <p>-- <em>The Home</em> by Judith Sonnet (Madness Heart Press)</p>
        <h4>BEST SHORT STORY</h4>
        <p>-- "Story Row" by Short Writer (from Some Book)</p>
        <h4>BEST ANTHOLOGY</h4>
        <p>-- <em>Full Throttle</em> edited by Candace Nola (Uncomfortably Dark)</p>
        <p>J. F. GONZALEZ LIFETIME ACHIEVEMENT AWARD*</p>
        <p>-- Person Only</p>
      '''},
    }])

    novel = parser.parse_official_current(
      current_json,
      OFFICIAL_AWARDS_API_URL,
      'Splatterpunk - Novel',
      'Novel',
      ('novel', 'best novel'))
    anthology = parser.parse_official_current(
      current_json,
      OFFICIAL_AWARDS_API_URL,
      'Splatterpunk - Anthology',
      'Anthology',
      ('anthology', 'best anthology'))

    novel_rows = {entry['title']: entry for entry in novel['entries']}
    anthology_rows = {entry['title']: entry for entry in anthology['entries']}

    self.assertEqual('shortlisted', novel_rows['At Dark, I Become Loathsome']['result'])
    self.assertEqual('2026.01', novel_rows['At Dark, I Become Loathsome']['position'])
    self.assertEqual('Eric LaRocca', novel_rows['At Dark, I Become Loathsome']['author'])
    self.assertNotIn('Story Row', novel_rows)
    self.assertNotIn('Person Only', novel_rows)
    self.assertEqual('Candace Nola', anthology_rows['Full Throttle']['author'])
    self.assertTrue(any('current-cycle nominees' in note for note in novel['notes']))

  def test_splatterpunk_official_winners_origin_and_tied_winners(self):
    from parser.splatterpunk import (
      OFFICIAL_PAST_WINNERS_API_URL, OFFICIAL_PAST_WINNERS_URL,
      SplatterpunkParser,
    )

    parser = SplatterpunkParser()
    winners_json = json.dumps([{
      'title': {'rendered': 'Past Award Winners'},
      'link': OFFICIAL_PAST_WINNERS_URL,
      'content': {'rendered': '''
        <p><strong>BEST NOVEL</strong></p>
        <ul>
          <li>2025 - <em>The Old Lady</em> by Kristopher Triana (Bad Dream Books)</li>
          <li>2018 - White Trash Gothic by Edward Lee</li>
        </ul>
        <p><strong>BEST SHORT STORY</strong></p>
        <ul><li>2024 - "My Octopus Master" by Stephen Kozeniewski</li></ul>
        <p><strong>BEST ANTHOLOGY</strong></p>
        <ul>
          <li>2022 - Body Shocks edited by Ellen Datlow (Tachyon Publications)</li>
          <li>2022 - Baker's Dozen edited by Candace Nola (Uncomfortably Dark)</li>
        </ul>
      '''},
    }])

    novel = parser.parse_official_winners(
      winners_json,
      OFFICIAL_PAST_WINNERS_API_URL,
      'Splatterpunk - Novel',
      'Novel',
      ('novel', 'best novel'))
    anthology = parser.parse_official_winners(
      winners_json,
      OFFICIAL_PAST_WINNERS_API_URL,
      'Splatterpunk - Anthology',
      'Anthology',
      ('anthology', 'best anthology'))

    novel_rows = {entry['title']: entry for entry in novel['entries']}
    anthology_rows = {entry['title']: entry for entry in anthology['entries']}

    self.assertEqual('winner', novel_rows['The Old Lady']['result'])
    self.assertEqual('2025', novel_rows['The Old Lady']['position'])
    self.assertEqual('2018', novel_rows['White Trash Gothic']['position'])
    self.assertNotIn('My Octopus Master', novel_rows)
    self.assertEqual('winner', anthology_rows['Body Shocks']['result'])
    self.assertEqual('2022', anthology_rows['Body Shocks']['position'])
    self.assertEqual('winner', anthology_rows["Baker's Dozen"]['result'])
    self.assertEqual('2022', anthology_rows["Baker's Dozen"]['position'])
    self.assertTrue(any('winner-only' in note for note in novel['notes']))

  def test_splatterpunk_goodreads_pagination_and_mixed_labels(self):
    from parser.splatterpunk import GOODREADS_URL, SplatterpunkParser

    parser = SplatterpunkParser()
    page_one = '''
      <table>
        <tr itemscope itemtype="http://schema.org/Book">
          <td>
            <a class="bookTitle" href="/book/show/1"><span>We're Here: An Anthology of LGBTQ+ Horror</span></a>
            <a class="authorName"><span>James G. Carlson</span></a>
            <i>Splatterpunk Award for Best Anthology (2024)</i>
          </td>
        </tr>
        <tr itemscope itemtype="http://schema.org/Book">
          <td>
            <a class="bookTitle" href="/book/show/2"><span>Y'All Ain't Right: Southern Extreme Horror</span></a>
            <a class="authorName"><span>Edward Lee</span></a>
            <i>Splatterpunk Award Nominee for Best Short Story for "Genital Grinder 2.5" and Best Anthology (2025)</i>
          </td>
        </tr>
        <tr itemscope itemtype="http://schema.org/Book">
          <td>
            <a class="bookTitle" href="/book/show/3"><span>The Home</span></a>
            <a class="authorName"><span>Judith Sonnet</span></a>
            <i>Splatterpunk Award Nominee for Best Novel (2025)</i>
          </td>
        </tr>
      </table>
      <a rel="next" href="/award/show/38981-splatterpunk-award?page=2">next</a>
    '''
    page_two = '''
      <table>
        <tr itemscope itemtype="http://schema.org/Book">
          <td>
            <a class="bookTitle" href="/book/show/4"><span>Baker's Dozen</span></a>
            <a class="authorName"><span>Candace Nola</span></a>
            <i>Splatterpunk Award for Best Anthology (2022)</i>
          </td>
        </tr>
      </table>
    '''

    first = parser.parse_goodreads(
      page_one,
      GOODREADS_URL,
      'Splatterpunk - Anthology',
      'Anthology',
      ('anthology', 'best anthology'))
    second = parser.parse_goodreads(
      page_two,
      GOODREADS_URL + '?page=2',
      'Splatterpunk - Anthology',
      'Anthology',
      ('anthology', 'best anthology'))
    combined = parser.combine_results(
      'Splatterpunk - Anthology',
      GOODREADS_URL,
      first,
      second)
    rows = {entry['title']: entry for entry in combined['entries']}

    self.assertIn(GOODREADS_URL + '?page=2',
                  parser.discover_goodreads_page_urls(page_one, GOODREADS_URL))
    self.assertEqual('winner', rows["We're Here: An Anthology of LGBTQ+ Horror"]['result'])
    self.assertEqual('shortlisted', rows["Y'All Ain't Right: Southern Extreme Horror"]['result'])
    self.assertEqual('winner', rows["Baker's Dozen"]['result'])
    self.assertNotIn('The Home', rows)
    self.assertTrue(any('Goodreads coverage' in note for note in combined['notes']))

  def test_splatterpunk_fetchers_metadata_merge_and_registry(self):
    from parser.base import CATEGORY_HORROR_DARK_FICTION
    from parser.splatterpunk import (
      GOODREADS_URL,
      OFFICIAL_AWARDS_API_URL,
      OFFICIAL_AWARDS_URL,
      OFFICIAL_PAST_WINNERS_API_URL,
      OFFICIAL_PAST_WINNERS_URL,
    )
    from url_fetcher import available_url_fetchers

    expected_ids = {
      'splatterpunk_novel',
      'splatterpunk_novella',
      'splatterpunk_collection',
      'splatterpunk_anthology',
    }
    fetchers = [
      fetcher for fetcher in available_url_fetchers()
      if fetcher.source_id in expected_ids
    ]

    self.assertEqual(expected_ids, {fetcher.source_id for fetcher in fetchers})
    self.assertTrue(all(fetcher.options['match_series'] is False for fetcher in fetchers))
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},),
                     fetchers[0].source_choices())
    for fetcher in fetchers:
      self.assertIn(CATEGORY_HORROR_DARK_FICTION,
                    [item['label'] for item in fetcher.get_filter_list()])

    page_two = GOODREADS_URL + '?page=2'
    by_url = {
      OFFICIAL_AWARDS_API_URL: json.dumps([{
        'title': {'rendered': '2026 Splatterpunk Awards'},
        'link': OFFICIAL_AWARDS_URL,
        'content': {'rendered': '''
          <h1>2026 Splatterpunk Awards</h1>
          <p>We are pleased to announce the 2026 Splatterpunk Award nominees.</p>
          <h4>BEST NOVEL</h4>
          <p>-- The Buffalo Hunter Hunter by Stephen Graham Jones (Saga Press)</p>
        '''},
      }]),
      OFFICIAL_PAST_WINNERS_API_URL: json.dumps([{
        'title': {'rendered': 'Past Award Winners'},
        'link': OFFICIAL_PAST_WINNERS_URL,
        'content': {'rendered': '''
          <p><strong>BEST NOVEL</strong></p>
          <ul><li>2025 - The Old Lady by Kristopher Triana (Bad Dream Books)</li></ul>
        '''},
      }]),
      GOODREADS_URL: '''
        <table>
          <tr itemscope itemtype="http://schema.org/Book">
            <td>
              <a class="bookTitle"><span>The Old Lady</span></a>
              <a class="authorName"><span>Kristopher Triana</span></a>
              <i>Splatterpunk Award Nominee for Best Novel (2025)</i>
            </td>
          </tr>
        </table>
        <a rel="next" href="/award/show/38981-splatterpunk-award?page=2">next</a>
      ''',
      page_two: '''
        <table>
          <tr itemscope itemtype="http://schema.org/Book">
            <td>
              <a class="bookTitle"><span>American Rapture</span></a>
              <a class="authorName"><span>C.J. Leede</span></a>
              <i>Splatterpunk Award Nominee for Best Novel (2025)</i>
            </td>
          </tr>
        </table>
      ''',
    }
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      return by_url[url]

    novel = [
      fetcher for fetcher in fetchers
      if fetcher.source_id == 'splatterpunk_novel'
    ][0]
    parsed = novel.fetch_and_parse(fetch_url)
    rows = {entry['title']: entry for entry in parsed['entries']}

    self.assertEqual('winner', rows['The Old Lady']['result'])
    self.assertEqual('2025', rows['The Old Lady']['position'])
    self.assertEqual('shortlisted', rows['American Rapture']['result'])
    self.assertEqual('shortlisted', rows['The Buffalo Hunter Hunter']['result'])
    self.assertFalse(parsed['match_series'])
    self.assertIn(OFFICIAL_AWARDS_API_URL, fetched)
    self.assertIn(OFFICIAL_PAST_WINNERS_API_URL, fetched)
    self.assertIn(page_two, fetched)

    registry_ids = [fetcher.source_id for fetcher in available_url_fetchers()]
    self.assertLess(
      registry_ids.index('this_is_horror_anthology'),
      registry_ids.index('splatterpunk_novel'))
    self.assertLess(
      registry_ids.index('splatterpunk_anthology'),
      registry_ids.index('arthur_c_clarke_award_novel'))

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
    self.assertEqual(365, len(source_ids))
    self.assertIn('hammett_prize', source_ids)
    self.assertIn('nero_award', source_ids)
    self.assertIn('strand_critics_award_mystery_novel', source_ids)
    self.assertIn('strand_critics_award_debut_mystery', source_ids)
    self.assertIn('pulitzer_prize_fiction', source_ids)
    self.assertIn('pulitzer_prize_general_nonfiction', source_ids)
    self.assertIn('national_book_award_fiction', source_ids)
    self.assertIn('national_book_award_nonfiction', source_ids)
    self.assertIn('national_book_award_young_peoples_literature', source_ids)
    self.assertIn('william_c_morris_award', source_ids)
    self.assertIn('british_fantasy_horror_novel', source_ids)
    self.assertIn('british_fantasy_fantasy_novel', source_ids)
    self.assertIn('british_fantasy_best_novel', source_ids)
    self.assertIn('international_horror_guild_novel', source_ids)
    self.assertIn('international_horror_guild_illustrated_narrative', source_ids)
    self.assertIn('this_is_horror_novel', source_ids)
    self.assertIn('this_is_horror_anthology', source_ids)
    self.assertIn('splatterpunk_novel', source_ids)
    self.assertIn('splatterpunk_anthology', source_ids)
    self.assertIn('yalsa_excellence_nonfiction_young_adults', source_ids)
    self.assertIn('baillie_gifford_prize', source_ids)
    self.assertIn('pen_galbraith_award_nonfiction', source_ids)
    self.assertIn('pen_diamonstein_spielvogel_award_essay', source_ids)
    self.assertIn('pen_jean_stein_book_award', source_ids)
    self.assertIn('pen_open_book_award', source_ids)
    self.assertIn('pen_faulkner_award_fiction', source_ids)
    self.assertIn('pen_hemingway_award_debut_novel', source_ids)
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
    self.assertIn(
      'governor_general_literary_award_english_young_peoples_illustrated_books',
      source_ids)
    self.assertIn(
      'governor_general_literary_award_french_young_peoples_text',
      source_ids)
    self.assertIn(
      'governor_general_literary_award_french_young_peoples_illustrated_books',
      source_ids)
    self.assertIn('costa_whitbread_novel', source_ids)
    self.assertIn('walter_scott_prize', source_ids)
    self.assertIn('costa_whitbread_first_novel', source_ids)
    self.assertIn('costa_whitbread_biography', source_ids)
    self.assertIn('costa_whitbread_childrens_book', source_ids)
    self.assertIn('costa_whitbread_book_of_the_year', source_ids)
    self.assertIn('james_tait_black_fiction', source_ids)
    self.assertIn('james_tait_black_biography', source_ids)
    self.assertIn('theakston_old_peculier_crime_novel_of_the_year', source_ids)
    self.assertIn('giller_prize', source_ids)
    self.assertIn('folio_writers_prize_book_of_the_year', source_ids)
    self.assertIn('folio_writers_prize_fiction', source_ids)
    self.assertIn('folio_writers_prize_nonfiction', source_ids)
    self.assertIn('nero_book_awards_fiction', source_ids)
    self.assertIn('nero_book_awards_debut_fiction', source_ids)
    self.assertIn('nero_book_awards_nonfiction', source_ids)
    self.assertIn('nero_book_awards_childrens_fiction', source_ids)
    self.assertIn('nero_book_awards_gold_prize', source_ids)
    self.assertIn('goldsmiths_prize', source_ids)
    self.assertIn('national_book_critics_circle_fiction', source_ids)
    self.assertIn('national_book_critics_circle_nonfiction', source_ids)
    self.assertIn('national_book_critics_circle_biography', source_ids)
    self.assertIn('national_book_critics_circle_memoir_autobiography', source_ids)
    self.assertIn('national_book_critics_circle_poetry', source_ids)
    self.assertIn('national_book_critics_circle_criticism', source_ids)
    self.assertIn('national_book_critics_circle_john_leonard', source_ids)
    self.assertIn('national_book_critics_circle_gregg_barrios_translation', source_ids)
    self.assertIn('dublin_literary_award', source_ids)
    self.assertIn('center_for_fiction_first_novel_prize', source_ids)
    self.assertIn('miles_franklin_literary_award', source_ids)
    self.assertIn('stella_prize', source_ids)
    self.assertIn('prime_ministers_literary_awards_fiction', source_ids)
    self.assertIn('prime_ministers_literary_awards_childrens_literature', source_ids)
    self.assertIn('victorian_premiers_literary_awards_fiction', source_ids)
    self.assertIn('victorian_premiers_literary_awards_nonfiction', source_ids)
    self.assertIn('victorian_premiers_literary_awards_writing_for_young_adults', source_ids)
    self.assertIn('victorian_premiers_literary_awards_childrens_literature', source_ids)
    self.assertIn('victorian_premiers_literary_awards_indigenous_writing', source_ids)
    self.assertIn('south_australian_literary_awards_premiers_award', source_ids)
    self.assertIn('south_australian_literary_awards_fiction', source_ids)
    self.assertIn('south_australian_literary_awards_nonfiction', source_ids)
    self.assertIn('south_australian_literary_awards_childrens', source_ids)
    self.assertIn('south_australian_literary_awards_young_adult', source_ids)
    self.assertIn('act_book_of_the_year_award', source_ids)
    self.assertIn('rwa_rita_awards', source_ids)
    self.assertIn('rwa_vivian_awards', source_ids)
    self.assertIn('rna_joan_hessayon_award', source_ids)
    self.assertIn('ripped_bodice_awards', source_ids)
    self.assertIn('romantic_times_reviewers_choice_romance', source_ids)
    self.assertIn('lambda_literary_awards_romance', source_ids)
    self.assertIn('romance_writers_australia_ruby_awards', source_ids)
    self.assertIn('holt_medallion', source_ids)
    self.assertIn('booksellers_best_award', source_ids)
    self.assertIn('goodreads_choice_awards_romance', source_ids)
    self.assertIn('goodreads_choice_awards_romantasy', source_ids)
    self.assertIn('goodreads_choice_awards_horror', source_ids)
    self.assertIn('goodreads_choice_awards_graphic_novels_comics', source_ids)
    self.assertIn('michael_l_printz_award', source_ids)
    self.assertIn('john_newbery_medal', source_ids)
    self.assertIn('writers_trust_atwood_gibson_fiction', source_ids)
    self.assertIn('writers_trust_hilary_weston_nonfiction', source_ids)
    self.assertIn('writers_trust_balsillie_public_policy', source_ids)
    self.assertIn('writers_trust_shaughnessy_cohen_political_writing', source_ids)

  def test_goodreads_choice_awards_discovers_category_urls(self):
    from parser.goodreads_choice_awards import GoodreadsChoiceAwardsParser

    html = '''
      <main>
        <a href="/choiceawards/readers-favorite-fiction-books-2025">
          Fiction  ✓ view results →
        </a>
        <a href="/choiceawards/readers-favorite-romance-books-2025">
          Romance  ✓ view results →
        </a>
        <a href="/choiceawards/best-books-2024">2024 Awards</a>
      </main>
    '''

    links = GoodreadsChoiceAwardsParser(
      'Romance', ('Romance',)).discover_category_links(
        html, 'https://www.goodreads.com/choiceawards/best-books-2025')

    self.assertEqual([{
      'year': 2025,
      'category': 'Romance',
      'url': 'https://www.goodreads.com/choiceawards/readers-favorite-romance-books-2025',
    }], list(links))

  def test_goodreads_choice_awards_category_page_parses_cards_and_roles(self):
    from parser.goodreads_choice_awards import GoodreadsChoiceAwardsParser

    html = '''
      <main>
        <h1>Readers' Favorite Fiction</h1>
        <section>
          <span>WINNER  167,509 votes</span>
          <a href="/book/show/1.My_Friends">
            <img alt="My Friends by Fallback Writer" />
          </a>
          <a href="/book/show/1.My_Friends">My Friends</a>
          <p>by
            <a href="/author/show/1.Fredrik_Backman">Fredrik Backman</a>
            (Goodreads Author),
            <a href="/author/show/2.Neil_Smith">Neil Smith</a> (Translator)
          </p>
        </section>
        <h2>All Nominees •</h2>
        <div>
          <span>167,509 votes</span>
          <a href="/book/show/1.My_Friends">
            <img alt="My Friends by Fredrik Backman" />
          </a>
        </div>
        <div>
          <span>107,486 votes</span>
          <a href="/book/show/2.Wild_Dark_Shore">
            <img alt="Wild Dark Shore by Charlotte McConaghy" />
          </a>
        </div>
        <div>
          <span>41,827 votes</span>
          <img alt="The Correspondent by Virginia Evans" />
        </div>
      </main>
    '''

    parsed = GoodreadsChoiceAwardsParser('Fiction').parse(
      '',
      'https://www.goodreads.com/choiceawards/best-books-2025',
      'Goodreads Choice Awards - Fiction',
      category_pages=(
        ('https://www.goodreads.com/choiceawards/readers-favorite-fiction-books-2025', html),
      ))

    self.assertEqual([
      ('2025', 'My Friends', 'Fredrik Backman', 'winner'),
      ('2025.01', 'Wild Dark Shore', 'Charlotte McConaghy', 'nominee'),
      ('2025.02', 'The Correspondent', 'Virginia Evans', 'nominee'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertEqual(
      'https://www.goodreads.com/book/show/1.My_Friends',
      parsed['entries'][0]['source_url'])
    self.assertEqual('167509', parsed['entries'][0]['votes'])
    self.assertTrue(all(entry['award'] == 'Goodreads Choice Awards' for entry in parsed['entries']))
    self.assertTrue(all(entry['category'] == 'Fiction' for entry in parsed['entries']))
    self.assertFalse(parsed['match_series'])

  def test_goodreads_choice_awards_parser_accepts_legacy_category_aliases(self):
    from parser.goodreads_choice_awards import GoodreadsChoiceAwardsParser

    overview_2023 = '''
      <a href="/choiceawards/readers-favorite-memoir-autobiography-books-2023">
        Memoir & Autobiography  ✓ view results →
      </a>
    '''
    overview_2025 = '''
      <a href="/choiceawards/readers-favorite-memoir-books-2025">
        Memoir  ✓ view results →
      </a>
    '''
    pages = {
      'https://www.goodreads.com/choiceawards/readers-favorite-memoir-autobiography-books-2023': '''
        <main>
          <h1>Readers' Favorite Memoir & Autobiography</h1>
          <p>WINNER  80,000 votes</p>
          <a href="/book/show/2023.Memoir">
            <img alt="Legacy Memoir by Older Writer" />
          </a>
          <h2>All Nominees</h2>
        </main>
      ''',
      'https://www.goodreads.com/choiceawards/readers-favorite-memoir-books-2025': '''
        <main>
          <h1>Readers' Favorite Memoir</h1>
          <p>WINNER  90,000 votes</p>
          <a href="/book/show/2025.Memoir">
            <img alt="Current Memoir by New Writer" />
          </a>
          <h2>All Nominees</h2>
        </main>
      ''',
    }

    parsed = GoodreadsChoiceAwardsParser(
      'Memoir',
      ('Memoir', 'Memoir & Autobiography')).parse(
        '',
        'https://www.goodreads.com/choiceawards/best-books-2025',
        'Goodreads Choice Awards - Memoir',
        fetch_url=lambda url: pages[url],
        overview_pages=(
          ('https://www.goodreads.com/choiceawards/best-books-2023', overview_2023),
          ('https://www.goodreads.com/choiceawards/best-books-2025', overview_2025),
        ))

    self.assertEqual([
      ('2023', 'Legacy Memoir', 'Memoir & Autobiography'),
      ('2025', 'Current Memoir', 'Memoir'),
    ], [
      (entry['position'], entry['title'], entry['category'])
      for entry in parsed['entries']
    ])

  def test_goodreads_choice_awards_fetchers_metadata_and_registry(self):
    from datetime import date

    from parser.base import (
      CATEGORY_FANTASY,
      CATEGORY_HORROR_DARK_FICTION,
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_ROMANCE,
      CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    )
    from parser.goodreads_choice_awards import (
      goodreads_choice_candidate_years,
      goodreads_choice_overview_url,
    )
    from url_fetcher import available_url_fetchers
    from url_fetcher.goodreads_choice_awards import (
      UrlFetcherGoodreadsChoiceAwardsGraphicNovelsComics,
      UrlFetcherGoodreadsChoiceAwardsRomance,
      UrlFetcherGoodreadsChoiceAwardsRomantasy,
      UrlFetcherGoodreadsChoiceAwardsYoungAdultFantasyScienceFiction,
    )

    current = UrlFetcherGoodreadsChoiceAwardsRomance()
    discontinued = UrlFetcherGoodreadsChoiceAwardsGraphicNovelsComics()
    romantasy = UrlFetcherGoodreadsChoiceAwardsRomantasy()
    ya_speculative = UrlFetcherGoodreadsChoiceAwardsYoungAdultFantasyScienceFiction()

    self.assertEqual('Goodreads Choice Awards - Romance', current.NAME)
    self.assertEqual(
      'Goodreads Choice Awards - Graphic Novels & Comics (discontinued)',
      discontinued.NAME)
    self.assertFalse(current.options['match_series'])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), current.source_choices())
    self.assertEqual(
      [2009, 2010, 2011],
      list(goodreads_choice_candidate_years(date(2011, 7, 1))))
    self.assertIn(CATEGORY_ROMANCE, [item['label'] for item in current.get_filter_list()])
    self.assertIn(CATEGORY_LITERARY_GENERAL_FICTION, [
      item['label'] for item in discontinued.get_filter_list()
    ])
    self.assertIn(CATEGORY_FANTASY, [item['label'] for item in romantasy.get_filter_list()])
    self.assertIn(CATEGORY_ROMANCE, [item['label'] for item in romantasy.get_filter_list()])
    self.assertIn(CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE, [
      item['label'] for item in ya_speculative.get_filter_list()
    ])

    overview = '''
      <a href="/choiceawards/readers-favorite-romance-books-2025">
        Romance ✓ view results →
      </a>
    '''
    category = '''
      <main>
        <h1>Readers' Favorite Romance</h1>
        <p>WINNER  10,000 votes</p>
        <a href="/book/show/1.Winning_Romance">
          <img alt="Winning Romance by Romance Writer" />
        </a>
        <h2>All Nominees</h2>
      </main>
    '''
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if url == current.URL:
        return overview
      if url.endswith('/readers-favorite-romance-books-2025'):
        return category
      if url.startswith('https://www.goodreads.com/choiceawards/best-books-'):
        return '<main></main>'
      self.fail(url)

    parsed = current.fetch_and_parse(fetch_url)

    self.assertEqual('Goodreads Choice Awards - Romance', parsed['name'])
    self.assertEqual(['Winning Romance'], [entry['title'] for entry in parsed['entries']])
    self.assertEqual('winner', parsed['entries'][0]['result'])
    self.assertEqual('Romance', parsed['entries'][0]['category'])
    self.assertFalse(parsed['match_series'])
    self.assertIn(goodreads_choice_overview_url(2009), fetched)
    self.assertIn(
      'https://www.goodreads.com/choiceawards/readers-favorite-romance-books-2025',
      fetched)

    registry_ids = [fetcher.source_id for fetcher in available_url_fetchers()]
    expected_ids = {
      'goodreads_choice_awards_romance',
      'goodreads_choice_awards_romantasy',
      'goodreads_choice_awards_horror',
      'goodreads_choice_awards_graphic_novels_comics',
      'goodreads_choice_awards_young_adult_fantasy_science_fiction',
    }
    self.assertTrue(expected_ids.issubset(set(registry_ids)))
    self.assertLess(
      registry_ids.index('booksellers_best_award'),
      registry_ids.index('goodreads_choice_awards_fiction'))
    self.assertLess(
      registry_ids.index('goodreads_choice_awards_best_of_the_best'),
      registry_ids.index('michael_l_printz_award'))
    self.assertLess(
      registry_ids.index('michael_l_printz_award'),
      registry_ids.index('writers_trust_atwood_gibson_fiction'))
    self.assertIn(CATEGORY_HORROR_DARK_FICTION, [
      item['label']
      for item in [
        fetcher for fetcher in available_url_fetchers()
        if fetcher.source_id == 'goodreads_choice_awards_horror'
      ][0].get_filter_list()
    ])

  def test_lodestar_parser_accepts_2018_young_adult_heading(self):
    from parser.hugo import LodestarAwardParser

    history = '''
      <a href="/hugo-history/2018-hugo-awards/">2018 Hugo Awards</a>
    '''
    page = '''
      <main>
        <p>There are two other Awards administered by Worldcon 76 that are not Hugo Awards:</p>
        <p>Award for Best Young Adult Book</p>
        <ul>
          <li>Akata Warrior, by Nnedi Okorafor (Viking)</li>
          <li>The Book of Dust: La Belle Sauvage, by Philip Pullman (Knopf)</li>
        </ul>
        <p>John W. Campbell Award for Best New Writer</p>
        <ul>
          <li>Rebecca Roanhorse</li>
        </ul>
      </main>
    '''

    parsed = LodestarAwardParser().parse(
      history,
      'https://www.thehugoawards.org/hugo-history/',
      fetch_url=lambda url: page)

    self.assertEqual([
      ('2018', 'Akata Warrior', 'Nnedi Okorafor', 'winner'),
      ('2018.01', 'The Book of Dust: La Belle Sauvage', 'Philip Pullman', 'nominee'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertTrue(all(entry['award'] == 'Lodestar Award' for entry in parsed['entries']))
    self.assertTrue(all(entry['category'] == 'Best Young Adult Book' for entry in parsed['entries']))
    self.assertFalse(parsed['match_series'])
    self.assertNotIn('Rebecca Roanhorse', [entry['title'] for entry in parsed['entries']])

  def test_lodestar_parser_imports_current_shortlist_without_winner(self):
    from parser.hugo import LodestarAwardParser

    history = '''
      <a href="/hugo-history/2025-hugo-awards/">2025 Hugo Awards</a>
      <a href="/hugo-history/2026-hugo-awards/">2026 Hugo Awards</a>
    '''
    pages = {
      'https://www.thehugoawards.org/hugo-history/2025-hugo-awards/': '''
        <main>
          <p>Presented at: Seattle Worldcon 2025, Seattle, Washington, USA, August 16, 2025</p>
          <p>Lodestar Award for Best Young Adult Book</p>
          <ul>
            <li>Sheine Lende by Darcie Little Badger (Levine Querido)</li>
            <li>Heavenly Tyrant by Xiran Jay Zhao (Tundra Books)</li>
            <li>Moonstorm by Yoon Ha Lee (Delacorte Press)</li>
          </ul>
          <p>268 ballots cast for 175 nominees, finalists range 18 to 52.</p>
          <p>Yoon Ha Lee withdrew Moonstorm from consideration after the finalists were announced.</p>
          <p>Astounding Award for Best New Writer</p>
          <ul>
            <li>Moniquill Blackgoose (2nd year of eligibility)</li>
          </ul>
          <p>Disqualifications and Withdrawals</p>
          <ul>
            <li>Declined nomination row outside the Lodestar finalist list</li>
          </ul>
        </main>
      ''',
      'https://www.thehugoawards.org/hugo-history/2026-hugo-awards/': '''
        <main>
          <p>The 2026 Hugo Awards, the Lodestar Award, and the Astounding Award will be presented on August 30, 2026.</p>
          <p>Voting on the final ballot will open in early May 2026.</p>
          <p>Lodestar Award for Best YA Book</p>
          <ul>
            <li>Among Ghosts by Rachel Hartman (Random House Books for Young Readers)</li>
            <li>Coffeeshop in an Alternate Universe by C.B. Lee (Feiwel &amp; Friends)</li>
            <li>Holy Terrors by Margaret Owen (Henry Holt; Hodderscape UK)</li>
            <li>Oathbound by Tracy Deonn (Simon &amp; Schuster Books for Young Readers)</li>
            <li>Sunrise on the Reaping by Suzanne Collins (Scholastic Press)</li>
            <li>They Bloom at Night by Trang Thanh Tran (Bloomsbury US; Bloomsbury UK)</li>
          </ul>
          <p>244 ballots cast for 169 nominees. Finalists range 12-48.</p>
          <p>Astounding Award for Best New Writer</p>
          <ul>
            <li>Sophie Burnham (2nd year of eligibility)</li>
          </ul>
        </main>
      ''',
    }

    parsed = LodestarAwardParser().parse(
      history,
      'https://www.thehugoawards.org/hugo-history/',
      fetch_url=lambda url: pages[url])

    self.assertEqual([
      ('2025', 'Sheine Lende', 'Darcie Little Badger', 'winner'),
      ('2025.01', 'Heavenly Tyrant', 'Xiran Jay Zhao', 'nominee'),
      ('2025.02', 'Moonstorm', 'Yoon Ha Lee', 'nominee'),
      ('2026.01', 'Among Ghosts', 'Rachel Hartman', 'nominee'),
      ('2026.02', 'Coffeeshop in an Alternate Universe', 'C.B. Lee', 'nominee'),
      ('2026.03', 'Holy Terrors', 'Margaret Owen', 'nominee'),
      ('2026.04', 'Oathbound', 'Tracy Deonn', 'nominee'),
      ('2026.05', 'Sunrise on the Reaping', 'Suzanne Collins', 'nominee'),
      ('2026.06', 'They Bloom at Night', 'Trang Thanh Tran', 'nominee'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertFalse(any(entry['position'] == '2026' for entry in parsed['entries']))
    self.assertNotIn('Moniquill Blackgoose', [entry['title'] for entry in parsed['entries']])
    self.assertNotIn('Declined nomination row outside the Lodestar finalist list', [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertTrue(any('no separate public longlist' in note for note in parsed['notes']))
    self.assertTrue(any('Moonstorm' in note and 'withdrawal' in note for note in parsed['notes']))

  def test_lodestar_fetcher_metadata_and_registry(self):
    from parser.base import (
      CATEGORY_FANTASY,
      CATEGORY_SCIENCE_FICTION,
      CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    )
    from url_fetcher import available_url_fetchers
    from url_fetcher.hugo import UrlFetcherLodestarAward

    fetcher = UrlFetcherLodestarAward()

    self.assertEqual('lodestar_award_young_adult_book', fetcher.source_id)
    self.assertEqual('Lodestar Award - Young Adult Book', fetcher.NAME)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())
    filter_labels = [item['label'] for item in fetcher.get_filter_list()]
    self.assertIn(CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE, filter_labels)
    self.assertIn(CATEGORY_SCIENCE_FICTION, filter_labels)
    self.assertIn(CATEGORY_FANTASY, filter_labels)

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertIn('lodestar_award_young_adult_book', registry_ids)
    self.assertLess(
      registry_ids.index('hugo_awards_related_work'),
      registry_ids.index('lodestar_award_young_adult_book'))
    self.assertLess(
      registry_ids.index('lodestar_award_young_adult_book'),
      registry_ids.index('nebula_awards_novel'))

  def test_andre_norton_official_parser_follows_pagination_and_keeps_nominees(self):
    from parser.nebula import NebulaAndreNortonParser

    page_1 = '''
      <main>
        <h2>2025</h2>
        <ul>
          <li><a href="/work/the-tower">The Tower, by David Anaxagoras (Recorded Books)</a>.
            Nominated for <a>Andre Norton Nebula Award for Middle Grade and Young Adult Fiction</a>
            in <a>2025</a></li>
          <li><a href="/work/into-the-wild-magic">Into the Wild Magic, by Michelle Knudsen (Candlewick)</a>.
            Winner, <a>Andre Norton Nebula Award for Middle Grade and Young Adult Fiction</a>
            in <a>2025</a></li>
        </ul>
        <h2>2012</h2>
        <ul>
          <li><a href="/work/fair-coin">Fair Coin</a> by <a>E.C. Myers</a>,
            published by <a>Pyr</a>. Winner,
            <a>Andre Norton Nebula Award for Middle Grade and Young Adult Fiction</a>
            in <a>2012</a></li>
          <li><a href="/work/iron-hearted-violet">Iron Hearted Violet</a> by <a>Kelly Barnhill</a>,
            published by <a>Little, Brown</a>. Nominated for
            <a>Andre Norton Nebula Award for Middle Grade and Young Adult Fiction</a>
            in <a>2012</a></li>
        </ul>
        <a href="/award/andre-norton-award/page/2/">Next &raquo;</a>
      </main>
    '''
    page_2 = '''
      <main>
        <h2>2012</h2>
        <ul>
          <li><a href="/work/black-heart">Black Heart</a> by <a>Holly Black</a>,
            published by <a>Victor Gollancz Ltd</a>. Nominated for
            <a>Andre Norton Nebula Award for Middle Grade and Young Adult Fiction</a>
            in <a>2012</a></li>
          <li><a href="/work/seraphina">Seraphina</a> by <a>Rachel Hartman</a>,
            published by <a>Random House</a>. Nominated for
            <a>Andre Norton Nebula Award for Middle Grade and Young Adult Fiction</a>
            in <a>2012</a></li>
        </ul>
      </main>
    '''

    parsed = NebulaAndreNortonParser().parse(
      page_1,
      'https://nebulas.sfwa.org/award/andre-norton-award/',
      fetch_url=lambda url: page_2)

    self.assertEqual([
      ('2012', 'Fair Coin', 'E.C. Myers', 'winner'),
      ('2012.01', 'Iron Hearted Violet', 'Kelly Barnhill', 'nominee'),
      ('2012.02', 'Black Heart', 'Holly Black', 'nominee'),
      ('2012.03', 'Seraphina', 'Rachel Hartman', 'nominee'),
      ('2025', 'Into the Wild Magic', 'Michelle Knudsen', 'winner'),
      ('2025.01', 'The Tower', 'David Anaxagoras', 'nominee'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertTrue(all(
      entry['award'] == 'Andre Norton Nebula Award for Middle Grade and Young Adult Fiction'
      for entry in parsed['entries']))
    self.assertIn('no separate public shortlist or longlist', parsed['notes'][0])
    self.assertEqual(
      'https://nebulas.sfwa.org/work/into-the-wild-magic',
      [entry for entry in parsed['entries'] if entry['title'] == 'Into the Wild Magic'][0]['source_url'])
    self.assertFalse(parsed['match_series'])

  def test_andre_norton_fetcher_metadata_source_choices_and_sfadb_fallback(self):
    from parser.base import CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE
    from url_fetcher import available_url_fetchers
    from url_fetcher.nebula import UrlFetcherNebulaAndreNorton

    fetcher = UrlFetcherNebulaAndreNorton()

    self.assertEqual('nebula_andre_norton_middle_grade_young_adult', fetcher.source_id)
    self.assertEqual('Nebula Awards - Andre Norton Middle Grade/YA', fetcher.NAME)
    self.assertFalse(fetcher.options['match_series'])
    self.assertIn(CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE, [
      item['label'] for item in fetcher.get_filter_list()
    ])
    self.assertEqual((
      {'label': 'Automatic', 'value': 'automatic'},
      {'label': 'Official SFWA', 'value': 0},
      {'label': 'SFADB', 'value': 1},
    ), fetcher.source_choices())

    sfadb_overview = '''
      <a href="/Nebula_Awards_2025">2025</a>
    '''
    sfadb_year = '''
      <div class="categoryblock">
        <div class="category">Andre Norton Middle Grade and Young Adult Fiction</div>
        <ul>
          <li>Winner: Into the Wild Magic, Michelle Knudsen (Candlewick)</li>
          <li>The Tower, David Anaxagoras (Recorded Books)</li>
        </ul>
      </div>
    '''
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if url == fetcher.URL:
        raise RuntimeError('official unavailable')
      if url == fetcher.SFADB_URL:
        return sfadb_overview
      if url == 'https://www.sfadb.com/Nebula_Awards_2025':
        return sfadb_year
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual([
      ('2025', 'Into the Wild Magic', 'Michelle Knudsen', 'winner'),
      ('2025.01', 'The Tower', 'David Anaxagoras', 'nominee'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertIn('Official SFWA failed: official unavailable', parsed['notes'])
    self.assertTrue(any('no separate public shortlist or longlist' in note for note in parsed['notes']))
    self.assertEqual([fetcher.URL, fetcher.SFADB_URL, 'https://www.sfadb.com/Nebula_Awards_2025'], fetched)

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertIn('nebula_andre_norton_middle_grade_young_adult', registry_ids)
    self.assertLess(
      registry_ids.index('lodestar_award_young_adult_book'),
      registry_ids.index('nebula_andre_norton_middle_grade_young_adult'))
    self.assertLess(
      registry_ids.index('nebula_andre_norton_middle_grade_young_adult'),
      registry_ids.index('nebula_awards_comics'))

  def test_morris_history_parser_imports_official_finalists(self):
    from parser.morris import MorrisAwardParser

    html = '''
      <main>
        <h2>2022</h2>
        <p>Winner: Firekeeper's Daughter written by Angeline Boulley and published by Henry Holt Books for Young Readers, 13-978-1250766564.</p>
        <p>Finalists: Ace of Spades written by Faridah Abike-Iyimide, Vampires, Hearts, &amp; Other Dead Things written by Margie Fuston, Me (Moth) written by Amber McBride, What Beauty There Is written by Cory Anderson</p>
        <h2>2009</h2>
        <p>Winner: A Curse Dark As Gold by Elizabeth C. Bunce</p>
        <p>Finalists: Graceling by Kristin Cashore, Absolute Brightness by James Lecesne, Madapple by Christina Meldrum, and Me, the Missing, and the Dead by Jenny Valentine.</p>
      </main>
    '''

    parsed = MorrisAwardParser().parse(html)

    self.assertEqual([
      ('2009', 'A Curse Dark As Gold', 'Elizabeth C. Bunce', 'winner'),
      ('2009.01', 'Graceling', 'Kristin Cashore', 'shortlisted'),
      ('2009.02', 'Absolute Brightness', 'James Lecesne', 'shortlisted'),
      ('2009.03', 'Madapple', 'Christina Meldrum', 'shortlisted'),
      ('2009.04', 'Me, the Missing, and the Dead', 'Jenny Valentine', 'shortlisted'),
      ('2022', "Firekeeper's Daughter", 'Angeline Boulley', 'winner'),
      ('2022.01', 'Ace of Spades', 'Faridah Abike-Iyimide', 'shortlisted'),
      ('2022.02', 'Vampires, Hearts, & Other Dead Things', 'Margie Fuston', 'shortlisted'),
      ('2022.03', 'Me (Moth)', 'Amber McBride', 'shortlisted'),
      ('2022.04', 'What Beauty There Is', 'Cory Anderson', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertTrue(all(entry['award'] == 'William C. Morris YA Debut Award' for entry in parsed['entries']))
    self.assertTrue(all(entry['category'] == 'Young Adult Literature' for entry in parsed['entries']))
    self.assertFalse(parsed['match_series'])
    self.assertIn('official public shortlists', parsed['notes'][0])

  def test_morris_annual_and_yma_supplements_recent_years(self):
    from parser.morris import MorrisAwardParser, yma_awards_url

    history_html = '''
      <main>
        <h2>2022</h2>
        <p>Winner: Firekeeper's Daughter written by Angeline Boulley.</p>
      </main>
    '''
    annual_2023 = '''
      <main>
        <h2>2023 Winner</h2>
        <p>The Life and Crimes of Hoodie Rosen written by Isaac Blum and published by Philomel Books.</p>
        <h2>2023 Finalists</h2>
        <p>The Summer of Bitter and Sweet written by Jen Ferguson and published by Heartdrum.</p>
        <p>Wake the Bones written by Elizabeth Kilcoyne and published by Wednesday Books.</p>
        <p>The Lesbiana's Guide to Catholic School written by Sonora Reyes and published by Balzer + Bray.</p>
        <p>Hell Followed With Us written by Andrew Joseph White and published by Peachtree Teen.</p>
      </main>
    '''
    yma_2026 = '''
      <main>
        <h2>William C. Morris Award</h2>
        <p>William C. Morris Award for a debut book published by a first-time author writing for teens: "All the Noise at Once," written by DeAndra Davis and published by Atheneum Books for Young Readers.</p>
        <h3>William C. Morris Award Finalists</h3>
        <p>"First Love Language," written by Stefany Valentine and published by Penguin Workshop; "Love, Misha," written and illustrated by Askel Aden and published by First Second; "Red Flags and Butterflies," written by Sheryl Azzam and published by DCB Young Readers; and "You and Me on Repeat," written and illustrated by Mary Shyne and published by Henry Holt Books for Young Readers.</p>
        <h2>Award for Excellence in Nonfiction for Young Adults</h2>
      </main>
    '''
    current_page = '''
      <main>
        <h2>2026 Morris Award Winner</h2>
        <p>"All the Noise at Once," written by DeAndra Davis, was named the 2026 winner of the William C. Morris YA Debut Award. The book is published by Atheneum Books for Young Readers.</p>
      </main>
    '''

    parsed = MorrisAwardParser().parse(
      history_html,
      current_year=2026,
      current_page=current_page,
      supplement_pages=(
        ('https://www.ala.org/yalsa/2023-morris-award-0', annual_2023),
        (yma_awards_url(2026), yma_2026),
      ))

    by_year = {}
    for entry in parsed['entries']:
      by_year.setdefault(entry['award_year'], []).append(entry)

    self.assertEqual([
      ('2023', 'The Life and Crimes of Hoodie Rosen', 'Isaac Blum', 'winner'),
      ('2023.01', 'The Summer of Bitter and Sweet', 'Jen Ferguson', 'shortlisted'),
      ('2023.02', 'Wake the Bones', 'Elizabeth Kilcoyne', 'shortlisted'),
      ('2023.03', "The Lesbiana's Guide to Catholic School", 'Sonora Reyes', 'shortlisted'),
      ('2023.04', 'Hell Followed With Us', 'Andrew Joseph White', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in by_year['2023']
    ])
    self.assertEqual([
      ('2026', 'All the Noise at Once', 'DeAndra Davis', 'winner'),
      ('2026.01', 'First Love Language', 'Stefany Valentine', 'shortlisted'),
      ('2026.02', 'Love, Misha', 'Askel Aden', 'shortlisted'),
      ('2026.03', 'Red Flags and Butterflies', 'Sheryl Azzam', 'shortlisted'),
      ('2026.04', 'You and Me on Repeat', 'Mary Shyne', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in by_year['2026']
    ])
    self.assertEqual({'winner', 'shortlisted'}, {
      entry['result'] for entry in parsed['entries']
    })

  def test_morris_fetcher_metadata_registry_and_missing_supplement_notes(self):
    from parser.base import CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE
    from parser.morris import CURRENT_URL, yma_awards_url
    from url_fetcher import available_url_fetchers
    from url_fetcher.morris import UrlFetcherWilliamCMorrisAward

    fetcher = UrlFetcherWilliamCMorrisAward()

    self.assertEqual('william_c_morris_award', fetcher.source_id)
    self.assertEqual('William C. Morris YA Debut Award', fetcher.NAME)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual(
      [CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE],
      [item['label'] for item in fetcher.get_filter_list()])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())

    history_html = '''
      <main>
        <h2>2024</h2>
        <p>Winner: Rez Ball written by Byron Graves.</p>
      </main>
    '''
    current_html = '''
      <main>
        <a href="/news/2025/01/not-other-girls-wins-2025-william-c-morris-award">2025 Morris Award</a>
      </main>
    '''
    annual_2025 = '''
      <main>
        <h1>Not Like Other Girls wins 2025 William C. Morris Award</h1>
        <p>"Not Like Other Girls," written by Meredith Adamo, has been named the 2025 winner of the William C. Morris YA Debut Award. The book is published by Bloomsbury YA.</p>
        <p>The 2025 Morris Award finalists, announced in December, include:</p>
        <p>"Aisle Nine," written by Ian X. Cho, published by HarperCollins Children's Books.</p>
      </main>
    '''
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if url == fetcher.URL:
        return history_html
      if url == CURRENT_URL:
        return current_html
      if url.endswith('/news/2025/01/not-other-girls-wins-2025-william-c-morris-award'):
        return annual_2025
      if url == yma_awards_url(2026):
        raise RuntimeError('not posted')
      self.fail(url)

    parsed = fetcher.parse(
      history_html,
      fetch_url=fetch_url,
      current_year=2026)

    self.assertEqual(['Rez Ball', 'Not Like Other Girls', 'Aisle Nine'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual([
      CURRENT_URL,
      'https://www.ala.org/news/2025/01/not-other-girls-wins-2025-william-c-morris-award',
      yma_awards_url(2026),
    ], fetched)
    self.assertIn('could not be fetched', parsed['notes'][0])

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertIn('william_c_morris_award', registry_ids)
    self.assertLess(
      registry_ids.index('goodreads_choice_awards_best_of_the_best'),
      registry_ids.index('william_c_morris_award'))
    self.assertLess(
      registry_ids.index('william_c_morris_award'),
      registry_ids.index('michael_l_printz_award'))

  def test_yalsa_nonfiction_history_parser_imports_official_finalists(self):
    from parser.yalsa_nonfiction import YALSANonfictionAwardParser

    html = '''
      <main>
        <h2>2022</h2>
        <p>Winner: "Ambushed!: The Assassination Plot Against President Garfield" written by Gail Jarrow and published by Calkins Creek, 978-1684378142.</p>
        <p>Finalists:</p>
        <p>"The 1619 Project: Born on the Water," written by Nikole Hannah-Jones and Renee Watson, illustrated by Nikkolas Smith, and published by Kokila.</p>
        <p>In the Shadow of the Fallen Towers: The Seconds, Minutes, Hours, Days, Weeks, Months, and Years after the 9/11 Attacks written and illustrated by Don Brown.</p>
        <h2>2010</h2>
        <p>Winner: Charles and Emma: The Darwins' Leap of Faith by Deborah Heiligman</p>
        <p>Finalists: Almost Astronauts: 13 Women Who Dared to Dream by Tanya Lee Stone, Claudette Colvin: Twice Toward Justice by Phillip Hoose, The Great and Only Barnum: The Tremendous, Stupendous Life of Showman P. T. Barnum by Candace Fleming, and Written in Bone: Buried Lives of Jamestown and Colonial Maryland by Sally M. Walker.</p>
      </main>
    '''

    parsed = YALSANonfictionAwardParser().parse(html)

    self.assertEqual([
      ('2010', "Charles and Emma: The Darwins' Leap of Faith", 'Deborah Heiligman', 'winner'),
      ('2010.01', 'Almost Astronauts: 13 Women Who Dared to Dream', 'Tanya Lee Stone', 'shortlisted'),
      ('2010.02', 'Claudette Colvin: Twice Toward Justice', 'Phillip Hoose', 'shortlisted'),
      ('2010.03', 'The Great and Only Barnum: The Tremendous, Stupendous Life of Showman P. T. Barnum', 'Candace Fleming', 'shortlisted'),
      ('2010.04', 'Written in Bone: Buried Lives of Jamestown and Colonial Maryland', 'Sally M. Walker', 'shortlisted'),
      ('2022', 'Ambushed!: The Assassination Plot Against President Garfield', 'Gail Jarrow', 'winner'),
      ('2022.01', 'The 1619 Project: Born on the Water', 'Nikole Hannah-Jones and Renee Watson, illustrated by Nikkolas Smith', 'shortlisted'),
      ('2022.02', 'In the Shadow of the Fallen Towers: The Seconds, Minutes, Hours, Days, Weeks, Months, and Years after the 9/11 Attacks', 'Don Brown', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertTrue(all(
      entry['award'] == 'YALSA Award for Excellence in Nonfiction for Young Adults'
      for entry in parsed['entries']))
    self.assertTrue(all(entry['category'] == 'Young Adult Nonfiction' for entry in parsed['entries']))
    self.assertFalse(parsed['match_series'])
    self.assertIn('official public shortlists', parsed['notes'][0])
    self.assertIn('nomination lists are excluded', parsed['notes'][0])

  def test_yalsa_nonfiction_annual_and_yma_supplements_recent_years(self):
    from parser.yalsa_nonfiction import YALSANonfictionAwardParser, yma_awards_url

    history_html = '''
      <main>
        <h2>2022</h2>
        <p>Winner: Ambushed!: The Assassination Plot Against President Garfield written by Gail Jarrow.</p>
      </main>
    '''
    annual_2023 = '''
      <main>
        <h2>2023 Winner</h2>
        <p>Victory. Stand!: Raising My Fist for Justice, by Tommie Smith, Derrick Barnes, and illustrated by Dawud Anyabwile, published by Norton Young Readers.</p>
        <h2>2023 Finalists</h2>
        <p>Abuela, Don't Forget Me by Rex Ogle.</p>
        <p>American Murderer: The Parasite That Haunted the South by Gail Jarrow.</p>
      </main>
    '''
    annual_2025 = '''
      <main>
        <h1>Rising from the Ashes wins 2025 YALSA Excellence in Nonfiction Award</h1>
        <p>"Rising from the Ashes: Los Angeles, 1992. Edward Jae Song Lee, Latasha Harlins, Rodney King, and a City on Fire," written by Paula Yoo, has been named the 2025 winner of the YALSA Award for Excellence in Nonfiction for Young Adults.</p>
        <p>The 2025 Nonfiction finalists, announced in December, include:</p>
        <ul>
          <li>"A Greater Goal: The Epic Battle for Equal Pay in Women's Soccer - and Beyond," written by Elizabeth Rusch and published by Greenwillow Books.</li>
        </ul>
      </main>
    '''
    yma_2026 = '''
      <main>
        <h2>Award for Excellence in Nonfiction for Young Adults</h2>
        <p>Award for Excellence in Nonfiction for Young Adults: "Death in the Jungle: Murder, Betrayal, and the Lost Dream of Jonestown," written by Candace Fleming and published by Anne Schwartz Books.</p>
        <h3>Award for Excellence in Nonfiction for Young Adults Finalists</h3>
        <p>"American Spirits: The Famous Fox Sisters and the Mysterious Fad That Haunted a Nation," written by Barb Rosenstock and published by Calkins Creek; "White House Secrets: True Stories from the World's Most Famous Residence," written by Gail Jarrow and published by Calkins Creek; "A World Without Summer: A Volcano Erupts, a Creature Awakens, and the Sun Goes Out," written by Nicholas Day, illustrated by Yas Imamura and published by Random House Studio.</p>
        <h2>American Indian Youth Literature Awards</h2>
        <p>Not Imported by Someone Else.</p>
      </main>
    '''

    parsed = YALSANonfictionAwardParser().parse(
      history_html,
      current_year=2026,
      supplement_pages=(
        ('https://www.ala.org/yalsa/2023-nonfiction-award', annual_2023),
        ('https://www.ala.org/news/2025/01/rising-ashes-los-angeles-1992', annual_2025),
        (yma_awards_url(2026), yma_2026),
      ))

    by_year = {}
    for entry in parsed['entries']:
      by_year.setdefault(entry['award_year'], []).append(entry)

    self.assertEqual([
      ('2023', 'Victory. Stand!: Raising My Fist for Justice', 'Tommie Smith, Derrick Barnes, and illustrated by Dawud Anyabwile', 'winner'),
      ('2023.01', "Abuela, Don't Forget Me", 'Rex Ogle', 'shortlisted'),
      ('2023.02', 'American Murderer: The Parasite That Haunted the South', 'Gail Jarrow', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in by_year['2023']
    ])
    self.assertEqual([
      ('2025', 'Rising from the Ashes: Los Angeles, 1992. Edward Jae Song Lee, Latasha Harlins, Rodney King, and a City on Fire', 'Paula Yoo', 'winner'),
      ('2025.01', "A Greater Goal: The Epic Battle for Equal Pay in Women's Soccer - and Beyond", 'Elizabeth Rusch', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in by_year['2025']
    ])
    self.assertEqual([
      ('2026', 'Death in the Jungle: Murder, Betrayal, and the Lost Dream of Jonestown', 'Candace Fleming', 'winner'),
      ('2026.01', 'American Spirits: The Famous Fox Sisters and the Mysterious Fad That Haunted a Nation', 'Barb Rosenstock', 'shortlisted'),
      ('2026.02', "White House Secrets: True Stories from the World's Most Famous Residence", 'Gail Jarrow', 'shortlisted'),
      ('2026.03', 'A World Without Summer: A Volcano Erupts, a Creature Awakens, and the Sun Goes Out', 'Nicholas Day, illustrated by Yas Imamura', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in by_year['2026']
    ])
    self.assertNotIn('Not Imported', [entry['title'] for entry in parsed['entries']])

  def test_yalsa_nonfiction_fetcher_metadata_registry_and_missing_supplement_notes(self):
    from parser.base import CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE
    from parser.yalsa_nonfiction import CURRENT_URL, yma_awards_url
    from url_fetcher import available_url_fetchers
    from url_fetcher.yalsa_nonfiction import UrlFetcherYALSAExcellenceNonfictionYoungAdults

    fetcher = UrlFetcherYALSAExcellenceNonfictionYoungAdults()

    self.assertEqual('yalsa_excellence_nonfiction_young_adults', fetcher.source_id)
    self.assertEqual('YALSA Award for Excellence in Nonfiction for Young Adults', fetcher.NAME)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual(
      [CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE],
      [item['label'] for item in fetcher.get_filter_list()])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())

    history_html = '''
      <main>
        <h2>2024</h2>
        <p>Winner: Accountable: The True Story of a Racist Social Media Account and the Teenagers Whose Lives It Changed written by Dashka Slater.</p>
      </main>
    '''
    current_html = '''
      <main>
        <a href="/news/2025/01/rising-ashes-los-angeles-1992">2025 Nonfiction Award</a>
      </main>
    '''
    annual_2025 = '''
      <main>
        <h1>Rising from the Ashes wins 2025 YALSA Nonfiction Award</h1>
        <p>"Rising from the Ashes: Los Angeles, 1992," written by Paula Yoo, has been named the 2025 winner of the YALSA Award for Excellence in Nonfiction for Young Adults.</p>
        <p>The 2025 Nonfiction finalists, announced in December, include:</p>
        <p>"Homebody," written and illustrated by Theo Parish and published by HarperAlley.</p>
      </main>
    '''
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if url == fetcher.URL:
        return history_html
      if url == CURRENT_URL:
        return current_html
      if url.endswith('/news/2025/01/rising-ashes-los-angeles-1992'):
        return annual_2025
      if url == yma_awards_url(2026):
        raise RuntimeError('not posted')
      self.fail(url)

    parsed = fetcher.parse(
      history_html,
      fetch_url=fetch_url,
      current_year=2026)

    self.assertEqual([
      'Accountable: The True Story of a Racist Social Media Account and the Teenagers Whose Lives It Changed',
      'Rising from the Ashes: Los Angeles, 1992',
      'Homebody',
    ], [entry['title'] for entry in parsed['entries']])
    self.assertEqual([
      CURRENT_URL,
      'https://www.ala.org/news/2025/01/rising-ashes-los-angeles-1992',
      yma_awards_url(2026),
    ], fetched)
    self.assertIn('could not be fetched', parsed['notes'][0])

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertIn('yalsa_excellence_nonfiction_young_adults', registry_ids)
    self.assertLess(
      registry_ids.index('william_c_morris_award'),
      registry_ids.index('yalsa_excellence_nonfiction_young_adults'))
    self.assertLess(
      registry_ids.index('yalsa_excellence_nonfiction_young_adults'),
      registry_ids.index('michael_l_printz_award'))

  def test_printz_history_parser_maps_honor_books_to_shortlisted(self):
    from parser.printz import PrintzAwardParser

    html = '''
      <main>
        <h2>2000</h2>
        <p>Winner:</p>
        <p>Monster, by Walter Dean Myers</p>
        <p>Honor Books:</p>
        <p>Skellig, by David Almond</p>
        <p>Speak, by Laurie Halse Anderson</p>
        <p>Hard Love, by Ellen Wittlinger</p>
      </main>
    '''

    parsed = PrintzAwardParser().parse(html)

    self.assertEqual([
      ('2000', 'Monster', 'Walter Dean Myers', 'winner'),
      ('2000.01', 'Skellig', 'David Almond', 'shortlisted'),
      ('2000.02', 'Speak', 'Laurie Halse Anderson', 'shortlisted'),
      ('2000.03', 'Hard Love', 'Ellen Wittlinger', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertTrue(all(entry['award'] == 'Michael L. Printz Award' for entry in parsed['entries']))
    self.assertTrue(all(entry['category'] == 'Young Adult Literature' for entry in parsed['entries']))
    self.assertFalse(parsed['match_series'])
    self.assertIn('Honor Books are imported as shortlisted', parsed['notes'][0])

  def test_printz_history_parser_preserves_creator_credit_shapes(self):
    from parser.printz import PrintzAwardParser

    html = '''
      <main>
        <h2>2024</h2>
        <p>Winner: The Collectors: Stories, edited by A.S. King. Written by King and others.</p>
        <p>Honor Books: Fire from the Sky, by Moa Backe Astot, translated by Eva Apelqvist; Gather by Kenneth M. Cadow; Salt the Water by Candice Iloh</p>
      </main>
    '''

    parsed = PrintzAwardParser().parse(html)

    self.assertEqual([
      ('2024', 'The Collectors: Stories', 'A.S. King', 'winner'),
      ('2024.01', 'Fire from the Sky', 'Moa Backe Astot, translated by Eva Apelqvist', 'shortlisted'),
      ('2024.02', 'Gather', 'Kenneth M. Cadow', 'shortlisted'),
      ('2024.03', 'Salt the Water', 'Candice Iloh', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])

  def test_printz_youth_media_awards_supplements_recent_years(self):
    from parser.printz import PrintzAwardParser, yma_awards_url

    history_html = '''
      <main>
        <h2>2024</h2>
        <p>Winner: The Collectors: Stories, edited by A.S. King.</p>
      </main>
    '''
    yma_2025 = '''
      <main>
        <h2>Michael L. Printz Award for Excellence in Young Adult Literature</h2>
        <p>"Brownstone," written by Samuel Teer, illustrated by Mar Julia and co-published by Versify and HarperAlley.</p>
        <h3>Four Printz Honor Books</h3>
        <p>"Bright Red Fruit," written by Safia Elhillo and published by Make Me a World; "Compound Fracture," written by Andrew Joseph White and published by Peachtree Teen; "The Deep Dark," written by Molly Knox Ostertag and published by Graphix; and "Road Home," written by Rex Ogle and published by Norton Young Readers.</p>
        <h2>Schneider Family Book Award</h2>
      </main>
    '''
    yma_2026 = '''
      <main>
        <h2>Michael L. Printz Award for Excellence in Young Adult Literature</h2>
        <p>The Michael L. Printz Award honoring the best book written for teens, based entirely on its literary merit: "Legendary Frybread Drive-In: Intertribal Stories," edited by Cynthia Leitich Smith, and published by Heartdrum.</p>
        <h3>Printz Honor Books</h3>
        <p>"Cope Field," written by T.L. Simpson and published by Flux; "The House No One Sees," written by Adina King and published by Feiwel and Friends; "Sisters in the Wind," written by Angeline Boulley and published by Henry Holt Books for Young Readers; and "Song of a Blackbird," written and illustrated by Maria van Lieshout and published by First Second.</p>
        <h2>Schneider Family Book Award</h2>
      </main>
    '''
    current_page = '''
      <main>
        <h2>2026 Michael L. Printz Award Winner: LEGENDARY FRYBREAD DRIVE-IN</h2>
        <p>"Legendary Frybread Drive-In: Intertribal Stories," edited by Cynthia Leitich Smith and published by Heartdrum.</p>
      </main>
    '''

    parsed = PrintzAwardParser().parse(
      history_html,
      current_year=2026,
      current_page=current_page,
      supplement_pages=(
        (yma_awards_url(2025), yma_2025),
        (yma_awards_url(2026), yma_2026),
      ))

    by_year = {}
    for entry in parsed['entries']:
      by_year.setdefault(entry['award_year'], []).append(entry)

    self.assertEqual([
      ('2025', 'Brownstone', 'Samuel Teer, illustrated by Mar Julia', 'winner'),
      ('2025.01', 'Bright Red Fruit', 'Safia Elhillo', 'shortlisted'),
      ('2025.02', 'Compound Fracture', 'Andrew Joseph White', 'shortlisted'),
      ('2025.03', 'The Deep Dark', 'Molly Knox Ostertag', 'shortlisted'),
      ('2025.04', 'Road Home', 'Rex Ogle', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in by_year['2025']
    ])
    self.assertEqual([
      ('2026', 'Legendary Frybread Drive-In: Intertribal Stories', 'Cynthia Leitich Smith', 'winner'),
      ('2026.01', 'Cope Field', 'T.L. Simpson', 'shortlisted'),
      ('2026.02', 'The House No One Sees', 'Adina King', 'shortlisted'),
      ('2026.03', 'Sisters in the Wind', 'Angeline Boulley', 'shortlisted'),
      ('2026.04', 'Song of a Blackbird', 'Maria van Lieshout', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in by_year['2026']
    ])
    self.assertEqual({'winner', 'shortlisted'}, {
      entry['result'] for entry in parsed['entries']
    })

  def test_printz_fetcher_metadata_registry_and_missing_supplement_notes(self):
    from parser.base import CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE
    from parser.printz import CURRENT_URL, yma_awards_url
    from url_fetcher import available_url_fetchers
    from url_fetcher.printz import UrlFetcherMichaelLPrintzAward

    fetcher = UrlFetcherMichaelLPrintzAward()

    self.assertEqual('michael_l_printz_award', fetcher.source_id)
    self.assertEqual('Michael L. Printz Award', fetcher.NAME)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual(
      [CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE],
      [item['label'] for item in fetcher.get_filter_list()])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())

    history_html = '''
      <main>
        <h2>2024</h2>
        <p>Winner: The Collectors: Stories, edited by A.S. King.</p>
      </main>
    '''
    yma_2025 = '''
      <main>
        <h2>Michael L. Printz Award for Excellence in Young Adult Literature</h2>
        <p>"Brownstone," written by Samuel Teer, illustrated by Mar Julia and co-published by Versify and HarperAlley.</p>
        <h3>Four Printz Honor Books</h3>
        <p>"Bright Red Fruit," written by Safia Elhillo and published by Make Me a World.</p>
        <h2>Schneider Family Book Award</h2>
      </main>
    '''
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if url == fetcher.URL:
        return history_html
      if url == CURRENT_URL:
        return '<main></main>'
      if url == yma_awards_url(2025):
        return yma_2025
      if url == yma_awards_url(2026):
        raise RuntimeError('not posted')
      self.fail(url)

    parsed = fetcher.parse(
      history_html,
      fetch_url=fetch_url,
      current_year=2026)

    self.assertEqual(['The Collectors: Stories', 'Brownstone', 'Bright Red Fruit'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual([CURRENT_URL, yma_awards_url(2025), yma_awards_url(2026)], fetched)
    self.assertIn('could not be fetched', parsed['notes'][0])

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertIn('michael_l_printz_award', registry_ids)
    self.assertLess(
      registry_ids.index('goodreads_choice_awards_best_of_the_best'),
      registry_ids.index('michael_l_printz_award'))
    self.assertLess(
      registry_ids.index('michael_l_printz_award'),
      registry_ids.index('writers_trust_atwood_gibson_fiction'))

  def test_carnegie_medal_winner_archive_skips_withheld_years(self):
    from parser.carnegie_medal import CarnegieMedalParser

    html = '''
      <main>
        <h1>Medal for Writing Winners</h1>
        <p>Before 2007, the year refers to the publication year.</p>
        <p>1936: Pigeon Post by Arthur Ransome</p>
        <p>1943: No award</p>
        <p>1945: Award withheld</p>
        <p>1966: No award was made</p>
        <p>1967: The Owl Service, Alan Garner</p>
      </main>
    '''

    parsed = CarnegieMedalParser().parse(html)

    self.assertEqual([
      ('1936', 'Pigeon Post', 'Arthur Ransome', 'winner'),
      ('1967', 'The Owl Service', 'Alan Garner', 'winner'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertEqual({'1936', '1967'}, {entry['award_year'] for entry in parsed['entries']})
    self.assertTrue(all(entry['award'] == 'Carnegie Medal for Writing' for entry in parsed['entries']))
    self.assertTrue(all(entry['category'] == 'Writing' for entry in parsed['entries']))
    self.assertFalse(parsed['match_series'])
    self.assertTrue(any('1943' in note and 'withheld' in note for note in parsed['notes']))
    self.assertTrue(any('pre-2010 history is winner-only' in note for note in parsed['notes']))

  def test_carnegie_medal_aggregate_shortlists_stop_before_greenaway(self):
    from parser.carnegie_medal import (
      SHORTLIST_ARCHIVE_2010_2015_URL, CarnegieMedalParser,
    )

    html = '''
      <main>
        <h2>2010</h2>
        <h3>CILIP Carnegie Medal</h3>
        <ul>
          <li>Chains by Laurie Halse Anderson (Bloomsbury)</li>
          <li>Fever Crumb by Philip Reeve</li>
        </ul>
        <h3>CILIP Kate Greenaway Medal</h3>
        <ul><li>Illustration Title by Artist Name</li></ul>
        <h2>2015</h2>
        <h3>CILIP Carnegie Medal</h3>
        <p>Buffalo Soldier by Tanya Landman</p>
        <h3>Kate Greenaway Medal</h3>
        <p>Another Illustration by Artist Two</p>
      </main>
    '''

    parsed = CarnegieMedalParser().parse(
      '<p>2015: Buffalo Soldier by Tanya Landman</p>',
      shortlist_pages=((SHORTLIST_ARCHIVE_2010_2015_URL, html),))

    self.assertEqual([
      ('2010.01', 'Chains', 'Laurie Halse Anderson', 'shortlisted'),
      ('2010.02', 'Fever Crumb', 'Philip Reeve', 'shortlisted'),
      ('2015', 'Buffalo Soldier', 'Tanya Landman', 'winner'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertNotIn('Illustration Title', [entry['title'] for entry in parsed['entries']])

  def test_carnegie_medal_yearly_shortlist_page_shapes(self):
    from parser.carnegie_medal import CarnegieMedalParser, shortlist_archive_url

    shortlist_2016 = '''
      <main>
        <h2>CILIP Carnegie Medal</h2>
        <ul>
          <li>One by Sarah Crossan</li>
          <li>The Lie Tree by Frances Hardinge</li>
        </ul>
        <h2>CILIP Kate Greenaway Medal</h2>
        <p>Illustration Row by Artist</p>
      </main>
    '''
    shortlist_2025 = '''
      <main>
        <p>The 2025 Carnegie Medal for Writing shortlist is:</p>
        <ul>
          <li>Chronicles of a Lizard Nobody by Patrick Ness, illustrated by Tim Miller (Walker Books)</li>
          <li>Steady for This by Nathanael Lessore, published by Hot Key Books</li>
        </ul>
        <h2>The Carnegie Medal for Illustration shortlist is:</h2>
        <p>Wrong Row by Artist</p>
      </main>
    '''

    parsed = CarnegieMedalParser().parse(
      '<p>2025: Steady for This by Nathanael Lessore</p>',
      shortlist_pages=(
        (shortlist_archive_url(2016), shortlist_2016),
        (shortlist_archive_url(2025), shortlist_2025),
      ))

    by_title = {entry['title']: entry for entry in parsed['entries']}
    self.assertEqual(('2016.01', 'Sarah Crossan', 'shortlisted'), (
      by_title['One']['position'], by_title['One']['author'], by_title['One']['result']))
    self.assertEqual(
      'Patrick Ness, illustrated by Tim Miller',
      by_title['Chronicles of a Lizard Nobody']['author'])
    self.assertEqual('winner', by_title['Steady for This']['result'])
    self.assertNotIn('Wrong Row', by_title)

  def test_carnegie_medal_2026_shortlist_winner_and_excluded_public_stages(self):
    from parser.carnegie_medal import (
      CarnegieMedalParser, current_shortlist_url, winner_news_url,
    )

    shortlist_html = '''
      <main>
        <h1>The 2026 Carnegie Medal for Writing shortlist is:</h1>
        <ul>
          <li>Ghostlines by Katya Balen</li>
          <li>Not Going to Plan by Tia Fisher</li>
          <li>Popcorn by Rob Harrell</li>
          <li>The Boy I Love by William Hussey</li>
          <li>Chronicles of a Lizard Nobody by Patrick Ness, illustrated by Tim Miller</li>
          <li>Wolf Siren by Beth O'Brien</li>
          <li>Twenty-Four Seconds from Now by Jason Reynolds</li>
          <li>Birdie by J. P. Rose</li>
        </ul>
        <h2>Carnegie Medal for Illustration</h2>
        <p>Illustration Book by Artist</p>
      </main>
    '''
    winner_html = '''
      <article>
        <h1>2026 winners announced</h1>
        <p>Beth O'Brien won both the Carnegie Medal for Writing and Shadowers' Choice Award for Writing for Wolf Siren (HarperCollins Children's Books).</p>
        <p>Kate Rolfe won the Carnegie Medal for Illustration for Varmints.</p>
      </article>
    '''
    longlist_html = '<main><h1>Writing Longlist 2026</h1><p>Longlist Book by Writer</p></main>'
    nominated_html = '<main><h1>Writing Nominated Titles 2026</h1><p>Nominee Book by Writer</p></main>'

    parsed = CarnegieMedalParser().parse(
      '<p>2025: Steady for This by Nathanael Lessore</p>',
      supplement_pages=(
        (current_shortlist_url(2026), shortlist_html),
        (winner_news_url(2026), winner_html),
        ('https://carnegies.co.uk/writing-longlist-2026/', longlist_html),
        ('https://carnegies.co.uk/writing-nominated-titles-2026/', nominated_html),
      ))

    entries_2026 = [entry for entry in parsed['entries'] if entry['award_year'] == '2026']
    by_title = {entry['title']: entry for entry in entries_2026}

    self.assertEqual(8, len(entries_2026))
    self.assertEqual(('2026', 'winner'), (
      by_title['Wolf Siren']['position'], by_title['Wolf Siren']['result']))
    self.assertEqual({'winner', 'shortlisted'}, {entry['result'] for entry in entries_2026})
    self.assertNotIn('Longlist Book', by_title)
    self.assertNotIn('Nominee Book', by_title)
    self.assertTrue(any('nominated-title and longlist pages are public but excluded' in note for note in parsed['notes']))

  def test_carnegie_medal_fetcher_metadata_fetch_flow_and_registry(self):
    from parser.base import CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE
    from parser.carnegie_medal import (
      SHORTLIST_ARCHIVE_2010_2015_URL, current_shortlist_url,
      current_winners_url, shortlist_archive_url, shortlist_news_url,
      winner_news_url,
    )
    from url_fetcher import available_url_fetchers
    from url_fetcher.carnegie_medal import UrlFetcherCarnegieMedalForWriting

    fetcher = UrlFetcherCarnegieMedalForWriting()

    self.assertEqual('carnegie_medal_for_writing', fetcher.source_id)
    self.assertEqual('Carnegie Medal for Writing', fetcher.NAME)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual(
      [CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE],
      [item['label'] for item in fetcher.get_filter_list()])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())

    history_html = '<main><p>2015: Buffalo Soldier by Tanya Landman</p></main>'
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if url == SHORTLIST_ARCHIVE_2010_2015_URL:
        return '''
          <main>
            <h2>2015</h2>
            <h3>CILIP Carnegie Medal</h3>
            <p>Five Children on the Western Front by Kate Saunders</p>
            <h3>Kate Greenaway Medal</h3>
          </main>
        '''
      if url == shortlist_archive_url(2016):
        return '<main><h2>CILIP Carnegie Medal</h2><p>One by Sarah Crossan</p></main>'
      if url == winner_news_url(2016):
        return '<article><p>Sarah Crossan won the Carnegie Medal for Writing for One.</p></article>'
      if url in {current_shortlist_url(2016), shortlist_news_url(2016), current_winners_url(2016)}:
        raise RuntimeError('not available')
      self.fail(url)

    parsed = fetcher.parse(history_html, fetch_url=fetch_url, current_year=2016)

    self.assertEqual('Carnegie Medal for Writing', parsed['name'])
    self.assertFalse(parsed['match_series'])
    self.assertEqual([
      'Buffalo Soldier',
      'Five Children on the Western Front',
      'One',
    ], [entry['title'] for entry in parsed['entries']])
    self.assertEqual([
      SHORTLIST_ARCHIVE_2010_2015_URL,
      shortlist_archive_url(2016),
      current_shortlist_url(2016),
      shortlist_news_url(2016),
      winner_news_url(2016),
      current_winners_url(2016),
    ], fetched)
    self.assertTrue(any('could not be fetched' in note for note in parsed['notes']))

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertIn('carnegie_medal_for_writing', registry_ids)
    self.assertLess(
      registry_ids.index('michael_l_printz_award'),
      registry_ids.index('carnegie_medal_for_writing'))
    self.assertLess(
      registry_ids.index('carnegie_medal_for_writing'),
      registry_ids.index('writers_trust_atwood_gibson_fiction'))

  def test_newbery_pdf_parser_maps_honor_books_to_shortlisted(self):
    from parser.newbery import NewberyMedalParser

    text = '''
      John Newbery Medal and Honor Books
      1922 Medal Winner
      The Story of Mankind, by Hendrik Willem van Loon (Liveright)
      1922 Honor Books
      The Great Quest, by Charles Boardman Hawes (Little, Brown)
      Cedric the Forester, by Bernard Marshall (Appleton)
      The Old Tobacco Shop: A True Account of What Befell a Little Boy in Search of Adventure,
      by William Bowen (Macmillan)
    '''

    parsed = NewberyMedalParser().parse(text)

    self.assertEqual([
      ('1922', 'The Story of Mankind', 'Hendrik Willem van Loon', 'winner'),
      ('1922.01', 'Cedric the Forester', 'Bernard Marshall', 'shortlisted'),
      ('1922.02', 'The Great Quest', 'Charles Boardman Hawes', 'shortlisted'),
      ('1922.03', 'The Old Tobacco Shop: A True Account of What Befell a Little Boy in Search of Adventure', 'William Bowen', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertTrue(all(entry['award'] == 'John Newbery Medal' for entry in parsed['entries']))
    self.assertTrue(all(entry['category'] == "Children's Literature" for entry in parsed['entries']))
    self.assertFalse(parsed['match_series'])
    self.assertTrue(any('Honor Books are imported as shortlisted' in note for note in parsed['notes']))

  def test_newbery_pdf_parser_skips_none_recorded_honors_and_wraps_rows(self):
    from parser.newbery import NewberyMedalParser

    text = '''
      1923 Medal Winner
      The Voyages of Doctor Dolittle, by Hugh Lofting (Stokes)
      1923 Honor Books
      [None recorded]
      2024 Medal Winner
      The Eyes and the Impossible,
      by Dave Eggers (Knopf)
      2024 Honor Book
      Eagle Drums, written and illustrated by Nasugraq Rainey Hopson
      (Roaring Brook Press)
    '''

    parsed = NewberyMedalParser().parse(text)

    self.assertEqual([
      ('1923', 'The Voyages of Doctor Dolittle', 'Hugh Lofting', 'winner'),
      ('2024', 'The Eyes and the Impossible', 'Dave Eggers', 'winner'),
      ('2024.01', 'Eagle Drums', 'Nasugraq Rainey Hopson', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertEqual({'winner', 'shortlisted'}, {entry['result'] for entry in parsed['entries']})

  def test_newbery_youth_media_awards_supplement_stops_before_caldecott(self):
    from parser.newbery import NewberyMedalParser, yma_awards_url

    pdf_text = '''
      2025 Medal Winner
      The First State of Being, by Erin Entrada Kelly (Greenwillow Books)
    '''
    yma_2026 = '''
      <main>
        <h2>John Newbery Medal</h2>
        <p>The John Newbery Medal for the most outstanding contribution to children's literature: "The Last Dragon on Mars," written by Scott Reintgen and published by Aladdin.</p>
        <h3>Newbery Honor Books</h3>
        <p>"Across So Many Seas," written by Ruth Behar and published by Nancy Paulsen Books; "Magnolia Wu Unfolds It All," written by Chanel Miller and published by Philomel Books; "One Big Open Sky," written by Lesa Cline-Ransome and published by Holiday House; and "The Wrong Way Home," written by Kate O'Shaughnessy and published by Knopf Books for Young Readers.</p>
        <h2>Randolph Caldecott Medal</h2>
        <p>"A Caldecott Book," illustrated by Artist Name.</p>
      </main>
    '''

    parsed = NewberyMedalParser().parse(
      pdf_text,
      supplement_pages=((yma_awards_url(2026), yma_2026),))

    by_year = {}
    for entry in parsed['entries']:
      by_year.setdefault(entry['award_year'], []).append(entry)

    self.assertEqual([
      ('2026', 'The Last Dragon on Mars', 'Scott Reintgen', 'winner'),
      ('2026.01', 'Across So Many Seas', 'Ruth Behar', 'shortlisted'),
      ('2026.02', 'Magnolia Wu Unfolds It All', 'Chanel Miller', 'shortlisted'),
      ('2026.03', 'One Big Open Sky', 'Lesa Cline-Ransome', 'shortlisted'),
      ('2026.04', 'The Wrong Way Home', "Kate O'Shaughnessy", 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in by_year['2026']
    ])
    self.assertNotIn('A Caldecott Book', [entry['title'] for entry in parsed['entries']])
    self.assertEqual({'winner', 'shortlisted'}, {entry['result'] for entry in parsed['entries']})

  def test_newbery_fetcher_discovers_pdf_supplements_lag_and_registry(self):
    from parser.base import CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE
    from parser.newbery import PDF_URL, yma_awards_url
    from url_fetcher import available_url_fetchers
    from url_fetcher.newbery import UrlFetcherJohnNewberyMedal

    fetcher = UrlFetcherJohnNewberyMedal()

    self.assertEqual('john_newbery_medal', fetcher.source_id)
    self.assertEqual('John Newbery Medal', fetcher.NAME)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual(
      [CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE],
      [item['label'] for item in fetcher.get_filter_list()])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())

    landing_html = f'''
      <main>
        <a href="{PDF_URL}">Newbery Medal and Honor Books, 1922-present PDF</a>
      </main>
    '''
    pdf_text = '''
      2025 Medal Winner
      The First State of Being, by Erin Entrada Kelly (Greenwillow Books)
    '''
    yma_2026 = '''
      <main>
        <h2>John Newbery Medal</h2>
        <p>"The Last Dragon on Mars," written by Scott Reintgen and published by Aladdin.</p>
        <h3>Newbery Honor Books</h3>
        <p>"Across So Many Seas," written by Ruth Behar and published by Nancy Paulsen Books.</p>
        <h2>Randolph Caldecott Medal</h2>
      </main>
    '''
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if url == PDF_URL:
        return pdf_text
      if url == yma_awards_url(2026):
        return yma_2026
      self.fail(url)

    parsed = fetcher.parse(landing_html, fetch_url=fetch_url, current_year=2026)

    self.assertEqual([
      'The First State of Being',
      'The Last Dragon on Mars',
      'Across So Many Seas',
    ], [entry['title'] for entry in parsed['entries']])
    self.assertEqual([PDF_URL, yma_awards_url(2026)], fetched)
    self.assertFalse(parsed['match_series'])

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertIn('john_newbery_medal', registry_ids)
    self.assertLess(
      registry_ids.index('carnegie_medal_for_writing'),
      registry_ids.index('john_newbery_medal'))
    self.assertLess(
      registry_ids.index('john_newbery_medal'),
      registry_ids.index('writers_trust_atwood_gibson_fiction'))

  def test_cbca_archive_parser_imports_winner_honour_and_shortlist_rows(self):
    from parser.cbca_book_of_the_year import (
      CATEGORY_OLDER_READERS, CBCABookOfTheYearParser,
    )

    html = '''
      <main>
        <h1>CBCA Book of the Year Award through history</h1>
        <p>2025</p>
        <h3>Book of the Year Award for Older Readers</h3>
        <p>Winner | I’m Not Really Here, Gary Lonesborough (Allen &amp; Unwin)</p>
        <p>Honour | Into the Mouth of the Wolf, Erin Gough (Hardie Grant Children’s Publishing)</p>
        <p>Honour | Birdy, Sharon Kernot (Text)</p>
        <p>Shortlist | Comes the Night, Isobelle Carmody (Allen &amp; Unwin)</p>
        <p>Shortlist | A Wreck of Seabirds, Karleah Olson (Fremantle)</p>
      </main>
    '''

    parsed = CBCABookOfTheYearParser(CATEGORY_OLDER_READERS).parse(
      html, current_year=2025)

    self.assertEqual([
      ('2025', 'I’m Not Really Here', 'Gary Lonesborough', 'winner'),
      ('2025.01', 'A Wreck of Seabirds', 'Karleah Olson', 'shortlisted'),
      ('2025.02', 'Birdy', 'Sharon Kernot', 'shortlisted'),
      ('2025.03', 'Comes the Night', 'Isobelle Carmody', 'shortlisted'),
      ('2025.04', 'Into the Mouth of the Wolf', 'Erin Gough', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertTrue(all(entry['award'] == 'CBCA Book of the Year' for entry in parsed['entries']))
    self.assertTrue(all(entry['category'] == CATEGORY_OLDER_READERS for entry in parsed['entries']))
    self.assertFalse(parsed['match_series'])
    self.assertTrue(any('Honour Books and official shortlists' in note for note in parsed['notes']))

  def test_cbca_2026_shortlist_page_imports_shortlist_only(self):
    from parser.cbca_book_of_the_year import (
      CATEGORY_YOUNGER_READERS, CBCABookOfTheYearParser, shortlist_url,
    )

    html = '''
      <main>
        <h1>2026 Book of the Year Awards - Shortlist</h1>
        <h2>Older Readers</h2>
        <p>Of Flame and Fury, Mikayla Bridge (Macmillan Australia)</p>
        <h2>Younger Readers</h2>
        <p>Run, Sarah Armstrong (Hardie Grant Children’s Publishing)</p>
        <p>Something Terrible: Tim Tie-Your-Shoelaces, Sally Barton, illustrated by Christopher Nielsen (Walker Books Australia)</p>
        <p>Little Bones, Sandy Bigna (University of Queensland Press)</p>
      </main>
    '''

    parsed = CBCABookOfTheYearParser(CATEGORY_YOUNGER_READERS).parse(
      html, shortlist_url(2026), current_year=2026)

    self.assertEqual([
      ('2026.01', 'Little Bones', 'Sandy Bigna', 'shortlisted'),
      ('2026.02', 'Run', 'Sarah Armstrong', 'shortlisted'),
      ('2026.03', 'Something Terrible: Tim Tie-Your-Shoelaces',
       'Sally Barton, illustrated by Christopher Nielsen', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertEqual({'shortlisted'}, {entry['result'] for entry in parsed['entries']})
    self.assertTrue(any('shortlist rows only' in note for note in parsed['notes']))

  def test_cbca_pdf_parser_imports_historical_and_recent_rows(self):
    from parser.cbca_book_of_the_year import (
      CATEGORY_EARLY_CHILDHOOD, CATEGORY_OLDER_READERS,
      CBCABookOfTheYearParser,
    )

    text = '''
      THE CHILDREN'S BOOK COUNCIL OF AUSTRALIA
      BOOK OF THE YEAR AWARD 1946 - 1981
      1946 - WINNER REES, Leslie Karrawingi the Emu John Sands
      SHORT LIST BARNETT, Gillian The Inside Hedge Story Oxford University Press
      BOOK OF THE YEAR AWARD: EARLY CHILDHOOD
      2021 - WINNER FREEMAN, Pamela Dry to Dry: The Seasons of Kakadu Walker
    '''

    older = CBCABookOfTheYearParser(CATEGORY_OLDER_READERS).parse(text)
    early = CBCABookOfTheYearParser(CATEGORY_EARLY_CHILDHOOD).parse(text)

    self.assertEqual([
      ('1946', 'Karrawingi the Emu', 'Leslie Rees', 'winner'),
      ('1946.01', 'The Inside Hedge Story', 'Gillian Barnett', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in older['entries']
    ])
    self.assertEqual([
      ('2021', 'Dry to Dry: The Seasons of Kakadu', 'Pamela Freeman', 'winner'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in early['entries']
    ])
    self.assertTrue(any('Historical CBCA non-winner labels' in note for note in older['notes']))

  def test_cbca_fetchers_filter_each_configured_category(self):
    from parser.base import (
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
      CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    )
    from url_fetcher.cbca_book_of_the_year import (
      UrlFetcherCBCABookOfTheYearEarlyChildhood,
      UrlFetcherCBCABookOfTheYearEvePownall,
      UrlFetcherCBCABookOfTheYearMiddleReaders,
      UrlFetcherCBCABookOfTheYearNewIllustrator,
      UrlFetcherCBCABookOfTheYearOlderReaders,
      UrlFetcherCBCABookOfTheYearPictureBook,
      UrlFetcherCBCABookOfTheYearYoungerReaders,
    )

    html = '''
      <main>
        <p>2027</p>
        <h2>Older Readers</h2><p>Winner | Older Book, Older Author (Publisher)</p>
        <h2>Younger Readers</h2><p>Winner | Younger Book, Younger Author (Publisher)</p>
        <h2>Middle Readers</h2><p>Winner | Middle Book, Middle Author (Publisher)</p>
        <h2>Early Childhood</h2><p>Winner | Early Book, Early Author (Publisher)</p>
        <h2>Picture Book of the Year</h2><p>Winner | Picture Book, Picture Author (Publisher)</p>
        <h2>Eve Pownall Award</h2><p>Winner | Eve Book, Eve Author (Publisher)</p>
        <h2>New Illustrator</h2><p>Winner | Illustrator Book, Illustrator Author (Publisher)</p>
      </main>
    '''
    fetchers = (
      UrlFetcherCBCABookOfTheYearOlderReaders(),
      UrlFetcherCBCABookOfTheYearYoungerReaders(),
      UrlFetcherCBCABookOfTheYearMiddleReaders(),
      UrlFetcherCBCABookOfTheYearEarlyChildhood(),
      UrlFetcherCBCABookOfTheYearPictureBook(),
      UrlFetcherCBCABookOfTheYearEvePownall(),
      UrlFetcherCBCABookOfTheYearNewIllustrator(),
    )

    for fetcher in fetchers:
      with self.subTest(fetcher=fetcher.source_id):
        parsed = fetcher.parse(html, current_year=2027)
        self.assertEqual([fetcher.CATEGORY], [
          entry['category'] for entry in parsed['entries']
        ])
        filters = [item['label'] for item in fetcher.get_filter_list()]
        self.assertIn(CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE, filters)
        self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
        self.assertFalse(fetcher.options['match_series'])
        self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())

  def test_cbca_future_year_fetch_flow_tolerates_missing_winner_page(self):
    from parser.cbca_book_of_the_year import (
      AWARDS_URL, PDF_URL, shortlist_url, winners_url,
    )
    from url_fetcher.cbca_book_of_the_year import (
      UrlFetcherCBCABookOfTheYearMiddleReaders,
    )

    fetcher = UrlFetcherCBCABookOfTheYearMiddleReaders()
    archive_html = f'''
      <main>
        <a href="{PDF_URL}">Download a PDF of all prior winners</a>
      </main>
    '''
    awards_html = '<main><a href="/2027-shortlist/">2027 Book of the Year Awards - Shortlist</a></main>'
    shortlist_html = '''
      <main>
        <h1>2027 Book of the Year Awards - Shortlist</h1>
        <h2>Middle Readers</h2>
        <p>Future Middle Book, Future Author (Example Press)</p>
      </main>
    '''
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if url == PDF_URL:
        return 'THE CHILDREN’S BOOK COUNCIL OF AUSTRALIA'
      if url == AWARDS_URL:
        return awards_html
      if url == shortlist_url(2027):
        return shortlist_html
      if url == winners_url(2027):
        raise RuntimeError('winner page not posted yet')
      self.fail(url)

    parsed = fetcher.parse(archive_html, fetch_url=fetch_url, current_year=2027)

    self.assertEqual([
      ('2027.01', 'Future Middle Book', 'Future Author', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertEqual([PDF_URL, AWARDS_URL, shortlist_url(2027), winners_url(2027)], fetched)
    self.assertTrue(any('winner page not posted yet' in note for note in parsed['notes']))
    self.assertTrue(any('shortlist rows only' in note for note in parsed['notes']))

  def test_cbca_fetcher_metadata_and_registry_order(self):
    from url_fetcher import available_url_fetchers
    from url_fetcher.cbca_book_of_the_year import (
      UrlFetcherCBCABookOfTheYearEarlyChildhood,
      UrlFetcherCBCABookOfTheYearEvePownall,
      UrlFetcherCBCABookOfTheYearMiddleReaders,
      UrlFetcherCBCABookOfTheYearNewIllustrator,
      UrlFetcherCBCABookOfTheYearOlderReaders,
      UrlFetcherCBCABookOfTheYearPictureBook,
      UrlFetcherCBCABookOfTheYearYoungerReaders,
    )

    fetchers = (
      UrlFetcherCBCABookOfTheYearOlderReaders(),
      UrlFetcherCBCABookOfTheYearYoungerReaders(),
      UrlFetcherCBCABookOfTheYearMiddleReaders(),
      UrlFetcherCBCABookOfTheYearEarlyChildhood(),
      UrlFetcherCBCABookOfTheYearPictureBook(),
      UrlFetcherCBCABookOfTheYearEvePownall(),
      UrlFetcherCBCABookOfTheYearNewIllustrator(),
    )

    self.assertEqual([
      'cbca_book_of_the_year_older_readers',
      'cbca_book_of_the_year_younger_readers',
      'cbca_book_of_the_year_middle_readers',
      'cbca_book_of_the_year_early_childhood',
      'cbca_book_of_the_year_picture_book',
      'cbca_book_of_the_year_eve_pownall',
      'cbca_book_of_the_year_new_illustrator',
    ], [fetcher.source_id for fetcher in fetchers])
    self.assertEqual(list(range(264, 271)), [fetcher.order for fetcher in fetchers])

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    for fetcher in fetchers:
      self.assertIn(fetcher.source_id, registry_ids)
    self.assertLess(
      registry_ids.index('john_newbery_medal'),
      registry_ids.index('cbca_book_of_the_year_older_readers'))
    self.assertLess(
      registry_ids.index('cbca_book_of_the_year_new_illustrator'),
      registry_ids.index('writers_trust_atwood_gibson_fiction'))

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

  def test_write_fields_bulk_writes_multi_book_active_series_values(self):
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

      def set_field(self, field, updates):
        set_field_calls.append((field, updates))

    class FakeDb:
      new_api = FakeApi()

      def set_custom(self, *args, **kwargs):
        set_custom_calls.append((args, kwargs))

    core.db = FakeDb()

    core.write_fields(
      active_updates={7: 'Philip K. Dick Award - Novel', 8: 'Philip K. Dick Award - Novel'},
      active_index_updates={7: 1983.03, 8: 2011.5},
      progress_callback=lambda count, message: progress.append((count, message)))

    self.assertEqual([
      ('#reading_series', {
        7: 'Philip K. Dick Award - Novel [1983.03]',
        8: 'Philip K. Dick Award - Novel [2011.5]',
      })
    ], set_field_calls)
    self.assertEqual([], set_custom_calls)
    self.assertEqual([(2, 'Finished Active List metadata updates...')], progress)
    self.assertEqual([{7, 8}], refreshed)

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

  def test_manage_active_list_review_writes_accepted_cached_review_changes(self):
    core = object.__new__(main.ListSwitchboardCore)
    writes = []
    statuses = []
    entries = [
      {'position': '1', 'title': 'First Book', 'author': 'Author One'},
      {'position': '2', 'title': 'Second Book', 'author': 'Author Two'},
    ]
    review_rows = [core.import_review_row(entry) for entry in entries]
    core.ensure_configured = lambda: True
    core.current_active = lambda: 'Example List'
    core.import_cache_for_active_list = lambda _active: {
      'list_name': 'Example List',
      'list_id': 'example_list',
      'entries': entries,
      'match_series': False,
      'notes': [],
      'source_url': 'https://example.invalid/list',
    }
    core.match_imported_entries = lambda *_args, **_kwargs: ({1: '1'}, [], review_rows)
    core.reconcile_review_rows_with_active_list = lambda _name, rows, active_name=None: (rows, [])
    core.accepted_import_review_rows = lambda rows: ({1: '1'}, [entries[1]], rows)
    core.review_import_matches = lambda *_args, **_kwargs: ({2: '2'}, [entries[0]], review_rows)
    core.active_book_ids_for_list = lambda _name: [1, 99]
    core.active_review_positions_by_book = lambda _ids: {1: '1', 99: '99'}
    core.write_fields_with_progress = lambda *args, **kwargs: writes.append((args, kwargs))
    core.status_message = lambda message: statuses.append(message)

    core.manage_active_list_review()

    self.assertEqual(1, len(writes))
    _args, kwargs = writes[0]
    self.assertEqual({1: '', 2: 'Example List'}, kwargs['active_updates'])
    self.assertEqual({2: 2.0}, kwargs['active_index_updates'])
    self.assertIn('Updated Active List "Example List".', statuses)

  def test_current_active_list_position_problems_reports_cache_missing_positions(self):
    core = object.__new__(main.ListSwitchboardCore)
    entries = [{'position': '1', 'title': 'First Book', 'author': 'Author One'}]
    core.ensure_configured = lambda: True
    core.current_active = lambda: 'Example List'
    core.import_cache_for_active_list = lambda _active: {
      'list_name': 'Example List',
      'list_id': 'example_list',
      'entries': entries,
    }
    core.active_book_ids_for_list = lambda _name: [1, 8]
    core.active_review_positions_by_book = lambda _ids: {1: '1', 8: '9'}
    core.review_book_details = lambda _ids: {
      8: {
        'matched_title': 'Unknown Position Book',
        'matched_authors': 'Unknown Author',
      },
    }

    self.assertEqual([{
      'book_id': 8,
      'position': '9',
      'title': 'Unknown Position Book',
      'author': 'Unknown Author',
    }], core.current_active_list_position_problems())


class ImportReportDialogStateTest(unittest.TestCase):

  class FakeMatchTable:
    def __init__(self, row=0):
      self._row = row
      self.selected = []
      self.items = {}
      self.widths = {}

    def currentRow(self):
      return self._row

    def setCurrentCell(self, row, _column):
      self._row = row
      self.selected.append(row)

    def setRowCount(self, _count):
      pass

    def setItem(self, row, column, item):
      self.items[(row, column)] = item

    def fontMetrics(self):
      class Metrics:
        def horizontalAdvance(self, text):
          return len(str(text))
      return Metrics()

    def setColumnWidth(self, column, width):
      self.widths[column] = width

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

  def test_table_display_compacts_multiple_ids_with_full_tooltip(self):
    original_item = import_report_module.QTableWidgetItem

    class FakeItem:
      def __init__(self, text):
        self.text = text
        self.tooltip = ''

      def setToolTip(self, text):
        self.tooltip = text

    row = {
      'matched': True,
      'ignored': False,
      'book_ids': [30890, 31244, 31245, 31248],
      'possible_matches': [],
      'imported_position': '2014.03',
      'imported_title': 'The Wheel of Time',
      'imported_author': 'Robert Jordan and Brandon Sanderson',
      'match_source': 'saved/manual override',
    }
    dialog = self.build_dialog(row)
    dialog.csv_values_for_row = ImportReportDialog.csv_values_for_row.__get__(dialog)
    dialog.display_values_for_row = ImportReportDialog.display_values_for_row.__get__(dialog)
    dialog.tooltip_for_table_cell = ImportReportDialog.tooltip_for_table_cell.__get__(dialog)
    dialog.book_id_text_values = ImportReportDialog.book_id_text_values.__get__(dialog)
    dialog.book_ids_full_text = ImportReportDialog.book_ids_full_text.__get__(dialog)
    dialog.book_ids_display_text = ImportReportDialog.book_ids_display_text.__get__(dialog)

    import_report_module.QTableWidgetItem = FakeItem
    try:
      dialog.update_table_for_row(row)
    finally:
      import_report_module.QTableWidgetItem = original_item

    self.assertEqual('30890; +3 more', dialog.match_table.items[(0, 3)].text)
    self.assertEqual(
      '30890; 31244; 31245; 31248',
      dialog.match_table.items[(0, 3)].tooltip)
    self.assertEqual(
      '30890; 31244; 31245; 31248',
      dialog.csv_values_for_row(row)[3])

  def test_id_column_width_is_capped_to_single_id_hint_width(self):
    row = {
      'matched': True,
      'ignored': False,
      'book_ids': [30890, 31244, 31245, 31248],
      'possible_matches': [],
      'imported_position': '2014.03',
      'imported_title': 'The Wheel of Time',
      'imported_author': 'Robert Jordan and Brandon Sanderson',
      'match_source': 'saved/manual override',
    }
    dialog = object.__new__(ImportReportDialog)
    dialog.match_table = self.FakeMatchTable()
    dialog.review_rows = [row]
    dialog.display_values_for_row = ImportReportDialog.display_values_for_row.__get__(dialog)
    dialog.csv_values_for_row = ImportReportDialog.csv_values_for_row.__get__(dialog)
    dialog.book_id_text_values = ImportReportDialog.book_id_text_values.__get__(dialog)
    dialog.book_ids_full_text = ImportReportDialog.book_ids_full_text.__get__(dialog)
    dialog.book_ids_display_text = ImportReportDialog.book_ids_display_text.__get__(dialog)
    dialog.stable_width_rows = ImportReportDialog.stable_width_rows.__get__(dialog)
    dialog.fixed_column_width_values = ImportReportDialog.fixed_column_width_values.__get__(dialog)
    dialog.apply_stable_fixed_column_widths = ImportReportDialog.apply_stable_fixed_column_widths.__get__(dialog)
    dialog.max_id_column_content_width = ImportReportDialog.max_id_column_content_width.__get__(dialog)
    dialog.text_width = ImportReportDialog.text_width.__get__(dialog)

    dialog.apply_stable_fixed_column_widths()

    full_width = len('30890; +3 more') + 28
    self.assertLess(dialog.match_table.widths[3], full_width)
    self.assertEqual(int(len('30890') * 1.75) + 28, dialog.match_table.widths[3])

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

  def test_locus_annual_parser_preserves_suffix_before_coauthor(self):
    from parser.locus import LocusAnnualAwardsParser

    html = '''
      Sf Novel
      1. Winner: Forever Peace, Joe Haldeman (Ace)
      2. Jack Faust, Michael Swanwick (Avon)
      3. The Cassini Division, Ken MacLeod (Legend)
      4. Saint Leibowitz and the Wild Horse Woman, Walter M. Miller, Jr., with Terry Bisson (Bantam Spectra)
      5. Example Continuation, Example Author, Sr. & Second Author (Example)
    '''
    overview = '<a href="/Locus_Awards_1998">1998</a>'

    parsed = LocusAnnualAwardsParser().parse(
      overview,
      'https://www.sfadb.com/Locus_Awards',
      'Locus - Annual SF Novel',
      'SF Novel',
      ('novel', 'sf novel'),
      fetch_url=lambda _url: html)

    self.assertEqual('1998.03', parsed['entries'][3]['position'])
    self.assertEqual(
      'Saint Leibowitz and the Wild Horse Woman',
      parsed['entries'][3]['title'])
    self.assertEqual(
      'Walter M. Miller, Jr. & Terry Bisson',
      parsed['entries'][3]['author'])
    self.assertEqual('Example Continuation', parsed['entries'][4]['title'])
    self.assertEqual(
      'Example Author, Sr. & Second Author',
      parsed['entries'][4]['author'])

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

  def test_philip_k_dick_parser_reads_sfadb_category_blocks(self):
    from parser.philip_k_dick import PhilipKDickParser

    overview = '<a href="Philip_K_Dick_Award_2026">2026</a>'
    html = '''
      <div class="AwYrTimePlace">
        <b>Where and When</b>: Norwescon 48
      </div>
      <div class="categoryblock">
        <div class="category"><span class="winner">Winner</span></div>
        <ul>
          <li><b>Outlaw Planet</b>, <a href="M_R_Carey">M. R. Carey</a> (Orbit UK; Orbit US)</li>
        </ul>
      </div>
      <div class="categoryblock">
        <div class="category"><span class="winner">Special Citation</span></div>
        <ul>
          <li><b>Uncertain Sons and Other Stories</b>, <a href="Thomas_Ha">Thomas Ha</a> (Undertow)</li>
        </ul>
      </div>
      <div class="categoryblock">
        <div class="category">Finalists</div>
        <ul>
          <li><b>Casual</b>, <a href="Koji_A_Dae">Koji A. Dae</a> (Tenebrous)</li>
          <li><b>City of All Seasons</b>, <a href="Oliver_K_Langmead">Oliver K. Langmead</a> & <a href="Aliya_Whiteley">Aliya Whiteley</a> (Titan)</li>
        </ul>
      </div>
    '''

    parsed = PhilipKDickParser().parse(
      overview,
      'https://www.sfadb.com/Philip_K_Dick_Award',
      fetch_url=lambda _url: html)

    self.assertEqual([
      ('2026', 'Outlaw Planet', 'M. R. Carey', 'winner'),
      ('2026.01', 'Casual', 'Koji A. Dae', 'nominee'),
      ('2026.02', 'City of All Seasons',
       'Oliver K. Langmead & Aliya Whiteley', 'nominee'),
      ('2026.5', 'Uncertain Sons and Other Stories', 'Thomas Ha',
       'special-citation'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])

  def test_philip_k_dick_parser_strips_editor_and_translator_credits(self):
    from parser.philip_k_dick import PhilipKDickParser

    overview = '''
      <a href="Philip_K_Dick_Award_1983">1983</a>
      <a href="Philip_K_Dick_Award_2011">2011</a>
      <a href="Philip_K_Dick_Award_2022">2022</a>
      <a href="Philip_K_Dick_Award_2025">2025</a>
    '''
    pages = {
      '1983': '''
        <div class="categoryblock">
          <div class="category">Finalists</div>
          <ul>
            <li><b>Aurelia</b>, <a>R. A. Lafferty</a> (Starblaze)</li>
            <li><b>Roderick</b>, <a>John Sladek</a> (Timescape)</li>
            <li><b>The Umbral Anthology of Science Fiction Poetry</b>, <a>Steve Rasnic Tem</a>, ed. (Umbral)</li>
          </ul>
        </div>
      ''',
      '2011': '''
        <div class="categoryblock">
          <div class="category">Special Citation</div>
          <ul>
            <li><b>Harmony</b>, <a>Project Itoh</a>, translated by <a>Alexander O. Smith</a> (Haikasoru)</li>
          </ul>
        </div>
      ''',
      '2022': '''
        <div class="categoryblock">
          <div class="category">Finalists</div>
          <ul>
            <li><b>Bug</b>, <a>Giacomo Sartori</a>, translated by <a>Frederika Randall</a> (Restless)</li>
          </ul>
        </div>
      ''',
      '2025': '''
        <div class="categoryblock">
          <div class="category">Finalists</div>
          <ul>
            <li><b>Alien Clay</b>, <a>Adrian Tchaikovsky</a> (Orbit)</li>
            <li><b>The Practice, the Horizon, and the Chain</b>, <a>Sofia Samatar</a> (Tordotcom)</li>
            <li><b>Triangulum</b>, <a>Subodhana Wijeyeratne</a> (Rosarium)</li>
            <li><b>Your Utopia: Stories</b>, <a>Bora Chung</a>, translated by <a>Anton Hur</a> (Algonquin)</li>
          </ul>
        </div>
      ''',
    }

    def fetch_url(url):
      year = url.rsplit('_', 1)[-1]
      return pages[year]

    parsed = PhilipKDickParser().parse(
      overview,
      'https://www.sfadb.com/Philip_K_Dick_Award',
      fetch_url=fetch_url)
    entries = {entry['title']: entry for entry in parsed['entries']}

    self.assertEqual(
      ('1983.03', 'Steve Rasnic Tem'),
      (entries['The Umbral Anthology of Science Fiction Poetry']['position'],
       entries['The Umbral Anthology of Science Fiction Poetry']['author']))
    self.assertEqual(
      ('2011.5', 'Project Itoh'),
      (entries['Harmony']['position'], entries['Harmony']['author']))
    self.assertEqual(
      ('2022.01', 'Giacomo Sartori'),
      (entries['Bug']['position'], entries['Bug']['author']))
    self.assertEqual(
      ('2025.04', 'Bora Chung'),
      (entries['Your Utopia: Stories']['position'],
       entries['Your Utopia: Stories']['author']))

  def test_nommo_parser_uses_wikipedia_table_headers_for_title_author(self):
    from parser.nommo import NommoAwardsParser

    html = '''
      <h3>Novel</h3>
      <table>
        <tr><th>Year</th><th>Author</th><th>Novel</th><th>Publisher</th></tr>
        <tr><td>2017</td><td>Tade Thompson*</td><td>Rosewater</td><td>Orbit</td></tr>
        <tr><td>A. Igoni Barrett</td><td>Blackass</td><td>Graywolf Press</td></tr>
      </table>
    '''

    parsed = NommoAwardsParser().parse(
      html,
      'https://en.wikipedia.org/wiki/Nommo_Awards',
      'Nommo - Novel',
      'Novel',
      fetch_url=None)

    self.assertEqual([
      ('2017', 'Rosewater', 'Tade Thompson', 'winner'),
      ('2017.01', 'Blackass', 'A. Igoni Barrett', 'nominee'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])

  def test_nommo_fetcher_falls_back_to_wikimedia_page_html(self):
    from url_fetcher.nommo import (
      NOMMO_AWARDS_URL, NOMMO_WIKIMEDIA_HTML_URL, UrlFetcherNommoNovel,
    )

    fetcher = UrlFetcherNommoNovel()
    calls = []
    html = '''
      <h3>Novel</h3>
      <table>
        <tr><th>Year</th><th>Author</th><th>Novel</th><th>Publisher</th></tr>
        <tr><td>2017</td><td>Tade Thompson*</td><td>Rosewater</td><td>Orbit</td></tr>
      </table>
    '''

    def fetch_url(url):
      calls.append(url)
      if url == NOMMO_AWARDS_URL:
        raise RuntimeError('certificate verify failed: certificate has expired')
      if url == NOMMO_WIKIMEDIA_HTML_URL:
        return html
      return '<html></html>'

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual([NOMMO_AWARDS_URL, NOMMO_WIKIMEDIA_HTML_URL], calls[:2])
    self.assertEqual(['Rosewater'], [entry['title'] for entry in parsed['entries']])
    self.assertEqual(['Tade Thompson'], [entry['author'] for entry in parsed['entries']])

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

  def test_governor_general_young_peoples_fetchers_parse_language_buckets(self):
    from parser.base import (
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
      CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    )
    from url_fetcher.governor_general import (
      UrlFetcherGovernorGeneralEnglishYoungPeoplesIllustratedBooks,
      UrlFetcherGovernorGeneralFrenchYoungPeoplesText,
    )

    data = json.dumps({
      '2024': {
        'youngPeoplesLiteratureText': {
          'en': {'finalists': [{
            'title': 'Crash Landing',
            'author': 'Li Charmaine Anne',
            'winner': True,
          }]},
          'fr': {'finalists': [{
            'title': 'Une bulle en dehors du temps',
            'author': 'Stefani Meunier',
            'winner': True,
          }, {
            'title': 'Carreaute Kid',
            'author': 'Marc-Andre Dufour-Labbe',
            'winner': False,
          }]},
        },
        'youngPeoplesLiteratureIllustratedBooks': {
          'en': {'finalists': [{
            'title': 'This Land Is a Lullaby',
            'author': 'Tonya Simpson, Delree Dumont',
            'winner': True,
          }]},
          'fr': {'finalists': [{
            'title': 'Le premier arbre de Noel',
            'author': 'Ovila Fontaine, Charlotte Parent',
            'winner': True,
          }]},
        },
      },
    })

    french_text = UrlFetcherGovernorGeneralFrenchYoungPeoplesText()
    english_illustrated = UrlFetcherGovernorGeneralEnglishYoungPeoplesIllustratedBooks()

    parsed_text = french_text.parse(data)
    parsed_illustrated = english_illustrated.parse(data)
    filters = [item['label'] for item in french_text.get_filter_list()]

    self.assertEqual([
      ('2024', 'Une bulle en dehors du temps', 'Stefani Meunier', 'winner'),
      ('2024.01', 'Carreaute Kid', 'Marc-Andre Dufour-Labbe', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed_text['entries']
    ])
    self.assertEqual(['This Land Is a Lullaby'], [
      entry['title'] for entry in parsed_illustrated['entries']
    ])
    self.assertTrue(all(
      entry['category'] == "French Young People's Literature - Text"
      for entry in parsed_text['entries']))
    self.assertIn(CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE, filters)
    self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
    self.assertFalse(french_text.options['match_series'])

  def test_governor_general_supplement_parses_annual_language_tables(self):
    from parser.governor_general import GovernorGeneralSupplementParser

    html = '''
      <h2>English</h2>
      <table>
        <tr><th>Category</th><th>Winner</th><th>Nominated</th></tr>
        <tr>
          <td>Children's illustration</td>
          <td>Tonya Simpson and Delree Dumont, This Land Is a Lullaby</td>
          <td>Guojing, Oasis<br />Sid Sharp, Bog Myrtle</td>
        </tr>
      </table>
      <h2>French</h2>
      <table>
        <tr><th>Category</th><th>Winner</th><th>Nominated</th></tr>
        <tr>
          <td>Children's illustration</td>
          <td>Stephane Laporte and Jacques Goldstyn, Un cadeau de Noel en novembre</td>
          <td>Jocelyn Boisvert and Enzo, Le livre aspirateur<br />Charlotte Parent, Murielle et le mystere</td>
        </tr>
      </table>
    '''

    parsed = GovernorGeneralSupplementParser(
      "French Young People's Literature - Illustrated Books",
      ('youngPeoplesLiteratureIllustratedBooks',),
      'fr').parse(
        html,
        'https://en.wikipedia.org/wiki/2025_Governor_General%27s_Awards',
        "Governor General's Literary Award - French Young People's Literature - Illustrated Books",
        year='2025')

    self.assertEqual([
      ('2025', 'Un cadeau de Noel en novembre', 'Stephane Laporte and Jacques Goldstyn', 'winner'),
      ('2025.01', 'Le livre aspirateur', 'Jocelyn Boisvert and Enzo', 'shortlisted'),
      ('2025.02', 'Murielle et le mystere', 'Charlotte Parent', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertTrue(all(
      entry['category'] == "French Young People's Literature - Illustrated Books"
      for entry in parsed['entries']))

  def test_giller_wikipedia_parser_imports_winners_and_shortlists_only(self):
    from parser.giller import GillerWikipediaParser

    html = '''
      <table>
        <tr><th>Year</th><th>Jury</th><th>Author</th><th>Book</th><th>Result</th><th>Ref.</th></tr>
        <tr>
          <td rowspan="8">2024</td>
          <td rowspan="8">Juror One<br />Juror Two</td>
          <td><a href="/wiki/Anne_Michaels">Anne Michaels</a></td>
          <td><a href="/wiki/Held">Held</a></td>
          <td>Winner</td>
          <td>[1]</td>
        </tr>
        <tr>
          <td>Conor Kerr</td>
          <td>Prairie Edge</td>
          <td rowspan="2">Shortlist</td>
          <td>[2]</td>
        </tr>
        <tr>
          <td>Anne Fleming</td>
          <td>Curiosities</td>
          <td>[2]</td>
        </tr>
        <tr>
          <td>Author Long</td>
          <td>Longlisted Book</td>
          <td>Longlist</td>
          <td>[3]</td>
        </tr>
        <tr>
          <td>Author Also Long</td>
          <td>Another Longlisted Book</td>
          <td>[3]</td>
        </tr>
      </table>
    '''

    parsed = GillerWikipediaParser().parse(
      html, 'https://en.wikipedia.org/wiki/Giller_Prize')

    self.assertEqual(['Held', 'Prairie Edge', 'Curiosities'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['winner', 'shortlisted', 'shortlisted'], [
      entry['result'] for entry in parsed['entries']
    ])
    self.assertEqual(['2024', '2024.01', '2024.02'], [
      entry['position'] for entry in parsed['entries']
    ])
    self.assertTrue(all(entry['category'] == 'Fiction' for entry in parsed['entries']))

  def test_giller_wikipedia_parser_preserves_tied_winner_positions(self):
    from parser.giller import GillerWikipediaParser

    html = '''
      <table>
        <tr><th>Year</th><th>Jury</th><th>Author</th><th>Book</th><th>Result</th><th>Ref.</th></tr>
        <tr>
          <td rowspan="3">2000</td>
          <td rowspan="3">Juror One</td>
          <td>Michael Ondaatje</td>
          <td>Anil's Ghost</td>
          <td rowspan="2">Winner</td>
          <td>[1]</td>
        </tr>
        <tr>
          <td>David Adams Richards</td>
          <td>Mercy Among the Children</td>
          <td>[1]</td>
        </tr>
        <tr>
          <td>Alan Cumyn</td>
          <td>Burridge Unbound</td>
          <td>Shortlist</td>
          <td>[2]</td>
        </tr>
      </table>
    '''

    parsed = GillerWikipediaParser().parse(
      html, 'https://en.wikipedia.org/wiki/Giller_Prize')

    self.assertEqual(
      ['Anil\'s Ghost', 'Mercy Among the Children', 'Burridge Unbound'],
      [entry['title'] for entry in parsed['entries']])
    self.assertEqual(['2000', '2000', '2000.01'], [
      entry['position'] for entry in parsed['entries']
    ])

  def test_giller_fetcher_metadata_and_parse_smoke(self):
    from parser.base import (
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
    )
    from url_fetcher.giller import UrlFetcherGillerPrize

    fetcher = UrlFetcherGillerPrize()
    html = '''
      <table>
        <tr><th>Year</th><th>Jury</th><th>Author</th><th>Book</th><th>Result</th><th>Ref.</th></tr>
        <tr>
          <td>2024</td>
          <td>Juror One</td>
          <td>Anne Michaels</td>
          <td>Held</td>
          <td>Winner</td>
          <td>[1]</td>
        </tr>
      </table>
    '''

    parsed = fetcher.fetch_and_parse(lambda url: html)
    filters = [item['label'] for item in fetcher.get_filter_list()]

    self.assertEqual('Giller Prize', parsed['name'])
    self.assertEqual(['Held'], [entry['title'] for entry in parsed['entries']])
    self.assertFalse(parsed['match_series'])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())
    self.assertIn(CATEGORY_LITERARY_GENERAL_FICTION, filters)
    self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)

  def test_goldsmiths_official_parser_discovers_modern_and_legacy_archive_pages(self):
    from parser.goldsmiths import OFFICIAL_URL, GoldsmithsOfficialParser

    index_html = '''
      <h2>2025 winner: We Live Here Now by C.D. Rose</h2>
      <p><a href="/goldsmiths-prize/archive/prize-2025/">More about 2025</a></p>
      <h2>2013 winner: A Girl is a Half-formed Thing by Eimear McBride</h2>
      <p><a href="/goldsmiths-prize/prize2013/">More about 2013</a></p>
    '''
    modern_url = 'https://www.gold.ac.uk/goldsmiths-prize/archive/prize-2025/'
    legacy_url = 'https://www.gold.ac.uk/goldsmiths-prize/prize2013/'
    pages = {
      modern_url: '''
        <article class="prize-teaser media">
          <a href="/goldsmiths-prize/archive/prize-2025/we-live-here-now/">
            <h3 class="book_name teaser-title"><span>We Live Here Now</span></h3>
            <div class="book_author"><p>C. D. Rose</p></div>
            <div class="book_publisher"><p>Melville House</p></div>
          </a>
        </article>
        <article class="prize-teaser media">
          <h3 class="book_name teaser-title"><span>We Pretty Pieces of Flesh</span></h3>
          <div class="book_author"><p>Colwill Brown</p></div>
          <div class="book_publisher"><p>Chatto &amp; Windus</p></div>
        </article>
      ''',
      legacy_url: '''
        <html><head><title>The Goldsmiths Prize 2013</title></head><body>
          <article class="prize-teaser media">
            <h3 class="book_name teaser-title">A Girl is a Half-formed Thing</h3>
            <div class="book_author"><p>Eimear McBride</p></div>
            <div class="book_publisher"><p>Galley Beggar Press</p></div>
          </article>
          <article class="prize-teaser media">
            <h3 class="book_name teaser-title">Harvest</h3>
            <div class="book_author"><p>Jim Crace</p></div>
            <div class="book_publisher"><p>Picador</p></div>
          </article>
        </body></html>
      ''',
    }
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      return pages[url]

    parsed = GoldsmithsOfficialParser().parse(
      index_html, OFFICIAL_URL, fetch_url=fetch_url)

    self.assertEqual([legacy_url, modern_url], fetched)
    self.assertEqual([
      ('2013', 'A Girl is a Half-formed Thing', 'Eimear McBride', 'winner'),
      ('2013.01', 'Harvest', 'Jim Crace', 'shortlisted'),
      ('2025', 'We Live Here Now', 'C. D. Rose', 'winner'),
      ('2025.01', 'We Pretty Pieces of Flesh', 'Colwill Brown', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertTrue(all(entry['category'] == 'Novel' for entry in parsed['entries']))
    self.assertTrue(all('publisher' not in entry for entry in parsed['entries']))

  def test_goldsmiths_official_parser_notes_individual_year_page_failures(self):
    from parser.goldsmiths import GoldsmithsOfficialParser

    index_html = '''
      <h2>2025 winner: We Live Here Now by C.D. Rose</h2>
      <p><a href="/goldsmiths-prize/archive/prize-2025/">More about 2025</a></p>
      <h2>2024 winner: The Vulnerables by Sigrid Nunez</h2>
      <p><a href="/goldsmiths-prize/archive/prize-2024/">More about 2024</a></p>
    '''
    ok_url = 'https://www.gold.ac.uk/goldsmiths-prize/archive/prize-2025/'

    def fetch_url(url):
      if url == ok_url:
        return '''
          <article class="prize-teaser media">
            <h3 class="book_name teaser-title">We Live Here Now</h3>
            <div class="book_author"><p>C.D. Rose</p></div>
          </article>
        '''
      raise RuntimeError('HTTP 500')

    parsed = GoldsmithsOfficialParser().parse(
      index_html,
      'https://www.gold.ac.uk/goldsmiths-prize/archive/',
      fetch_url=fetch_url)

    self.assertIn('We Live Here Now', [entry['title'] for entry in parsed['entries']])
    self.assertTrue(any(
      'archive page could not be fetched' in note and 'prize-2024' in note
      for note in parsed['notes']))

  def test_goldsmiths_wikipedia_parser_reads_rowspanned_highlighted_winners(self):
    from parser.goldsmiths import GoldsmithsWikipediaParser

    html = '''
      <table>
        <caption>Shortlisted and winning books (2013-2025)</caption>
        <tr><th>Year</th><th>Author</th><th>Novel</th><th>Publisher</th><th>Notes</th></tr>
        <tr>
          <th rowspan="2">2025</th>
          <td style="background:lightyellow">CD Rose</td>
          <td style="background:lightyellow"><i><a href="/wiki/We_Live_Here_Now">We Live Here Now</a></i></td>
          <td style="background:lightyellow">Melville House</td>
          <td rowspan="2">Winner marked with ribbon.</td>
        </tr>
        <tr>
          <td>Colwill Brown</td>
          <td><i>We Pretty Pieces of Flesh</i></td>
          <td>Chatto &amp; Windus</td>
        </tr>
      </table>
    '''

    parsed = GoldsmithsWikipediaParser().parse(
      html, 'https://en.wikipedia.org/wiki/Goldsmiths_Prize')

    self.assertEqual([
      ('2025', 'We Live Here Now', 'CD Rose', 'winner'),
      ('2025.01', 'We Pretty Pieces of Flesh', 'Colwill Brown', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])

  def test_goldsmiths_fetcher_metadata_and_fallback(self):
    from parser.base import (
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
    )
    from url_fetcher.goldsmiths import UrlFetcherGoldsmithsPrize

    fetcher = UrlFetcherGoldsmithsPrize()
    official_html = '<html><title>Goldsmiths Prize archive</title></html>'
    wiki_html = '''
      <table>
        <caption>Shortlisted and winning books</caption>
        <tr><th>Year</th><th>Author</th><th>Novel</th><th>Publisher</th><th>Notes</th></tr>
        <tr style="background:lightyellow">
          <td>2025</td><td>CD Rose</td><td>We Live Here Now</td><td>Melville House</td><td></td>
        </tr>
      </table>
    '''
    calls = []

    def fetch_url(url):
      calls.append(url)
      if url == fetcher.URL:
        return official_html
      if url == fetcher.WIKIPEDIA_URL:
        return wiki_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)
    filters = [item['label'] for item in fetcher.get_filter_list()]

    self.assertEqual('Goldsmiths Prize', fetcher.NAME)
    self.assertEqual('goldsmiths_prize', fetcher.source_id)
    self.assertEqual(242, fetcher.order)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual((
      {'label': 'Automatic', 'value': 'automatic'},
      {'label': 'Goldsmiths', 'value': 0},
      {'label': 'Wikipedia', 'value': 1},
    ), fetcher.source_choices())
    self.assertIn(CATEGORY_LITERARY_GENERAL_FICTION, filters)
    self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
    self.assertEqual(['We Live Here Now'], [entry['title'] for entry in parsed['entries']])
    self.assertEqual([fetcher.URL, fetcher.WIKIPEDIA_URL], calls)
    self.assertFalse(parsed['match_series'])
    with self.assertRaises(Exception):
      fetcher.fetch_and_parse(fetch_url, disable_fallbacks=True)

  def test_national_book_critics_circle_official_parser_categories_and_scope(self):
    from parser.national_book_critics_circle import (
      NationalBookCriticsCircleOfficialParser,
    )

    html = '''
      <main>
        <h1>2025 NBCC Awards</h1>
        <h2>Fiction</h2>
        <h3>Winner</h3>
        <p>Percival Everett <a href="/books/james">James</a></p>
        <h3>Finalists</h3>
        <p>Rachel Kushner <a href="/books/creation-lake">Creation Lake</a></p>
        <h3>Longlist</h3>
        <p>Long Writer <a href="/books/long-fiction">Long Fiction</a></p>
        <h2>Nonfiction</h2>
        <h3>Winner</h3>
        <p>Adam Higginbotham <a href="/books/challenger">Challenger</a></p>
        <h2>Biography</h2>
        <h3>Winner</h3>
        <p>Jonathan Eig <a href="/books/king">King: A Life</a></p>
        <h2>Memoir/Autobiography</h2>
        <h3>Winner</h3>
        <p>Safiya Sinclair <a href="/books/how-to-say-babylon">How to Say Babylon</a></p>
        <h2>Poetry</h2>
        <h3>Winner</h3>
        <p>Craig Santos Perez <a href="/books/from-unincorporated-territory">from unincorporated territory [åmot]</a></p>
        <h2>Criticism</h2>
        <h3>Winner</h3>
        <p>Lauren Michele Jackson <a href="/books/white-negroes">White Negroes</a></p>
        <h2>John Leonard Prize</h2>
        <h3>Winner</h3>
        <p>Isabella Hammad <a href="/books/the-parisian">The Parisian</a></p>
        <h2>Gregg Barrios Book in Translation Prize</h2>
        <h3>Winner</h3>
        <p>Jon Fosse <a href="/books/a-new-name">A New Name</a></p>
        <h2>Lifetime Achievement Award</h2>
        <p>Person Only <a href="/people/person-only">Person Only Honor</a></p>
      </main>
    '''
    configs = {
      'Fiction': ('Fiction', ('Fiction',)),
      'Nonfiction': ('Nonfiction', ('Nonfiction', 'Non-fiction')),
      'Biography': ('Biography', ('Biography',)),
      'Memoir/Autobiography': (
        'Memoir/Autobiography',
        ('Memoir/Autobiography', 'Memoir and Autobiography', 'Autobiography', 'Memoir')),
      'Poetry': ('Poetry', ('Poetry',)),
      'Criticism': ('Criticism', ('Criticism',)),
      'John Leonard Prize': ('John Leonard Prize', ('John Leonard Prize', 'Best First Book')),
      'Gregg Barrios Book in Translation Prize': (
        'Gregg Barrios Book in Translation Prize',
        ('Gregg Barrios Book in Translation Prize', 'Book in Translation')),
    }
    expected = {
      'Fiction': [
        ('2025', 'James', 'Percival Everett', 'winner'),
        ('2025.01', 'Creation Lake', 'Rachel Kushner', 'shortlisted'),
      ],
      'Nonfiction': [('2025', 'Challenger', 'Adam Higginbotham', 'winner')],
      'Biography': [('2025', 'King: A Life', 'Jonathan Eig', 'winner')],
      'Memoir/Autobiography': [('2025', 'How to Say Babylon', 'Safiya Sinclair', 'winner')],
      'Poetry': [('2025', 'from unincorporated territory', 'Craig Santos Perez', 'winner')],
      'Criticism': [('2025', 'White Negroes', 'Lauren Michele Jackson', 'winner')],
      'John Leonard Prize': [('2025', 'The Parisian', 'Isabella Hammad', 'winner')],
      'Gregg Barrios Book in Translation Prize': [('2025', 'A New Name', 'Jon Fosse', 'winner')],
    }

    for label, (category, aliases) in configs.items():
      with self.subTest(category=label):
        parsed = NationalBookCriticsCircleOfficialParser(category, aliases).parse(
          html, 'https://www.bookcritics.org/past-awards/2025/')
        self.assertEqual(expected[label], [
          (entry['position'], entry['title'], entry['author'], entry['result'])
          for entry in parsed['entries']
        ])
        self.assertTrue(all(entry['category'] == category for entry in parsed['entries']))
        self.assertNotIn('Long Fiction', [entry['title'] for entry in parsed['entries']])
        self.assertNotIn('Person Only Honor', [entry['title'] for entry in parsed['entries']])

  def test_national_book_critics_circle_official_parser_discovers_year_links(self):
    from parser.national_book_critics_circle import (
      NationalBookCriticsCircleOfficialParser,
    )

    index_html = '''
      <main>
        <a href="/past-awards/2024/">2024 Awards</a>
        <a href="https://www.bookcritics.org/past-awards/2025/">2025 Awards</a>
      </main>
    '''
    pages = {
      'https://www.bookcritics.org/past-awards/2024/': '''
        <main>
          <h1>2024 Awards</h1>
          <h2>Fiction</h2>
          <h3>Winner</h3>
          <p>Fiction Author <a href="/book/fiction-winner">Fiction Winner</a></p>
        </main>
      ''',
      'https://www.bookcritics.org/past-awards/2025/': '''
        <main>
          <h1>2025 Awards</h1>
          <h2>Fiction</h2>
          <h3>Finalists</h3>
          <p>Another Author <a href="/book/border-book">Border Book</a></p>
        </main>
      ''',
    }
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      return pages[url]

    parsed = NationalBookCriticsCircleOfficialParser('Fiction', ('Fiction',)).parse(
      index_html, 'https://www.bookcritics.org/past-awards/', fetch_url=fetch_url)

    self.assertEqual([
      'https://www.bookcritics.org/past-awards/2024/',
      'https://www.bookcritics.org/past-awards/2025/',
    ], fetched)
    self.assertEqual([
      ('2024', 'Fiction Winner', 'winner'),
      ('2025.01', 'Border Book', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['result'])
      for entry in parsed['entries']
    ])

  def test_national_book_critics_circle_wikipedia_parser_rowspans_and_gregg_barrios(self):
    from parser.national_book_critics_circle import (
      NationalBookCriticsCircleWikipediaParser,
    )

    fiction_html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr><td rowspan="4">2024</td><td>Percival Everett</td><td><a href="/wiki/James">James</a></td><td>Winner</td></tr>
        <tr><td>Rachel Kushner</td><td>Creation Lake</td><td>Finalist</td></tr>
        <tr><td>Miranda July</td><td>All Fours</td><td></td></tr>
        <tr><td>Long Writer</td><td>Longlisted Novel</td><td>Longlist</td></tr>
      </table>
    '''
    fiction = NationalBookCriticsCircleWikipediaParser('Fiction', ('Fiction',)).parse(
      fiction_html,
      'https://en.wikipedia.org/wiki/National_Book_Critics_Circle_Award_for_Fiction')

    self.assertEqual([
      ('2024', 'James', 'Percival Everett', 'winner'),
      ('2024.01', 'Creation Lake', 'Rachel Kushner', 'shortlisted'),
      ('2024.02', 'All Fours', 'Miranda July', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in fiction['entries']
    ])
    self.assertNotIn('Longlisted Novel', [entry['title'] for entry in fiction['entries']])

    translation_html = '''
      <table>
        <tr>
          <th>Year</th><th>Title</th><th>Author</th>
          <th>Translator</th><th>Language</th><th>Result</th>
        </tr>
        <tr>
          <td>2025</td><td>Absolution</td><td>Alice McDermott</td>
          <td>Not Imported</td><td>French</td><td>Winner</td>
        </tr>
      </table>
    '''
    translation = NationalBookCriticsCircleWikipediaParser(
      'Gregg Barrios Book in Translation Prize',
      ('Gregg Barrios Book in Translation Prize', 'Book in Translation')).parse(
        translation_html,
        'https://en.wikipedia.org/wiki/Gregg_Barrios_Book_in_Translation_Prize')

    self.assertEqual([
      ('2025', 'Absolution', 'Alice McDermott', 'winner'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in translation['entries']
    ])

  def test_national_book_critics_circle_fetchers_metadata_fallback_and_registry(self):
    from parser.base import (
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_NONFICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
    )
    from url_fetcher import available_url_fetchers
    from url_fetcher.national_book_critics_circle import (
      UrlFetcherNationalBookCriticsCircleBiography,
      UrlFetcherNationalBookCriticsCircleCriticism,
      UrlFetcherNationalBookCriticsCircleFiction,
      UrlFetcherNationalBookCriticsCircleGreggBarriosTranslation,
      UrlFetcherNationalBookCriticsCircleJohnLeonard,
      UrlFetcherNationalBookCriticsCircleMemoirAutobiography,
      UrlFetcherNationalBookCriticsCircleNonfiction,
      UrlFetcherNationalBookCriticsCirclePoetry,
    )

    fetchers = (
      (UrlFetcherNationalBookCriticsCircleFiction(), CATEGORY_LITERARY_GENERAL_FICTION),
      (UrlFetcherNationalBookCriticsCircleNonfiction(), CATEGORY_NONFICTION),
      (UrlFetcherNationalBookCriticsCircleBiography(), CATEGORY_NONFICTION),
      (UrlFetcherNationalBookCriticsCircleMemoirAutobiography(), CATEGORY_NONFICTION),
      (UrlFetcherNationalBookCriticsCirclePoetry(), None),
      (UrlFetcherNationalBookCriticsCircleCriticism(), CATEGORY_NONFICTION),
      (UrlFetcherNationalBookCriticsCircleJohnLeonard(), None),
      (UrlFetcherNationalBookCriticsCircleGreggBarriosTranslation(), None),
    )
    expected_ids = {
      'national_book_critics_circle_fiction',
      'national_book_critics_circle_nonfiction',
      'national_book_critics_circle_biography',
      'national_book_critics_circle_memoir_autobiography',
      'national_book_critics_circle_poetry',
      'national_book_critics_circle_criticism',
      'national_book_critics_circle_john_leonard',
      'national_book_critics_circle_gregg_barrios_translation',
    }

    self.assertEqual(expected_ids, {fetcher.source_id for fetcher, _filter in fetchers})
    for fetcher, expected_filter in fetchers:
      with self.subTest(fetcher=fetcher.source_id):
        filters = [item['label'] for item in fetcher.get_filter_list()]
        self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
        if expected_filter is not None:
          self.assertIn(expected_filter, filters)
        self.assertFalse(fetcher.options['match_series'])
        self.assertEqual((
          {'label': 'Automatic', 'value': 'automatic'},
          {'label': 'NBCC', 'value': 0},
          {'label': 'Wikipedia', 'value': 1},
        ), fetcher.source_choices())

    fetcher = UrlFetcherNationalBookCriticsCircleFiction()
    official_html = '<main><h1>NBCC Awards</h1></main>'
    wikipedia_html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr><td>2024</td><td>Percival Everett</td><td>James</td><td>Winner</td></tr>
      </table>
    '''
    calls = []

    def fetch_url(url):
      calls.append(url)
      if url == fetcher.URL:
        return official_html
      if url == fetcher.WIKIPEDIA_URL:
        return wikipedia_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual(['James'], [entry['title'] for entry in parsed['entries']])
    self.assertEqual([fetcher.URL, fetcher.WIKIPEDIA_URL], calls)
    self.assertIn('NBCC failed', parsed['notes'][0])
    self.assertFalse(parsed['match_series'])
    with self.assertRaises(Exception):
      fetcher.fetch_and_parse(fetch_url, disable_fallbacks=True)

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    for source_id in expected_ids:
      self.assertIn(source_id, registry_ids)
    self.assertLess(
      registry_ids.index('goldsmiths_prize'),
      registry_ids.index('national_book_critics_circle_fiction'))
    self.assertLess(
      registry_ids.index('national_book_critics_circle_gregg_barrios_translation'),
      registry_ids.index('walter_scott_prize'))

  def test_dublin_literary_award_official_parser_winners_shortlist_and_scope(self):
    from parser.dublin_literary_award import DublinLiteraryAwardOfficialParser

    html = '''
      <main>
        <h1>2026 Dublin Literary Award</h1>
        <h2>2026 Winner</h2>
        <h3><a href="/books/gliff">Gliff</a></h3>
        <h4>Ali Smith</h4>
        <h2>SHORTLIST</h2>
        <h3><a href="/books/gliff">Gliff</a></h3>
        <h4>Ali Smith</h4>
        <h3>Perspective(s)</h3>
        <h4>Laurent Binet</h4>
        <p>Translated by Sam Taylor</p>
        <h3>In Late Summer</h3>
        <h4>Luigi Garlando</h4>
        <h3>Live Fast</h3>
        <h4>Brigitte Giraud</h4>
        <h3>The Emperor of Gladness</h3>
        <h4>Ocean Vuong</h4>
        <h3>What I Know About You</h3>
        <h4>Éric Chacour</h4>
        <h2>LONGLIST</h2>
        <h3>Creation Lake</h3>
        <h4>Rachel Kushner</h4>
        <h2>NOMINATED</h2>
        <h3>1985: A Novel</h3>
        <h4>Anthony Burgess</h4>
      </main>
    '''

    parsed = DublinLiteraryAwardOfficialParser().parse(
      html, 'https://dublinliteraryaward.ie/the-library/prize-years/2026/')

    self.assertEqual([
      ('2026', 'Gliff', 'Ali Smith', 'winner'),
      ('2026.01', 'Perspective(s)', 'Laurent Binet', 'shortlisted'),
      ('2026.02', 'In Late Summer', 'Luigi Garlando', 'shortlisted'),
      ('2026.03', 'Live Fast', 'Brigitte Giraud', 'shortlisted'),
      ('2026.04', 'The Emperor of Gladness', 'Ocean Vuong', 'shortlisted'),
      ('2026.05', 'What I Know About You', 'Éric Chacour', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertNotIn('Creation Lake', [entry['title'] for entry in parsed['entries']])
    self.assertNotIn('1985: A Novel', [entry['title'] for entry in parsed['entries']])
    self.assertTrue(all(entry['award'] == 'Dublin Literary Award' for entry in parsed['entries']))
    self.assertTrue(all(entry['category'] == 'Novel' for entry in parsed['entries']))
    self.assertFalse(parsed['match_series'])

  def test_dublin_literary_award_official_parser_handles_translation_lines(self):
    from parser.dublin_literary_award import DublinLiteraryAwardOfficialParser

    html = '''
      <main>
        <h1>2024 Dublin Literary Award</h1>
        <h2>Winner</h2>
        <h3>Solenoid</h3>
        <h4>Mircea Cărtărescu</h4>
        <p>Translated by Sean Cotter</p>
        <h2>SHORTLIST</h2>
        <p><a href="/books/the-birthday-party">The Birthday Party</a> by Laurent Mauvignier</p>
      </main>
    '''

    parsed = DublinLiteraryAwardOfficialParser().parse(
      html, 'https://dublinliteraryaward.ie/the-library/prize-years/2024/')

    self.assertEqual([
      ('2024', 'Solenoid', 'Mircea Cărtărescu', 'winner'),
      ('2024.01', 'The Birthday Party', 'Laurent Mauvignier', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])

  def test_dublin_literary_award_official_parser_discovers_year_links(self):
    from parser.dublin_literary_award import DublinLiteraryAwardOfficialParser

    index_html = '''
      <main>
        <a href="/the-library/prize-years/2025/">2025 Prize Year</a>
        <a href="https://dublinliteraryaward.ie/the-library/prize-years/2026/">2026 Prize Year</a>
      </main>
    '''
    pages = {
      'https://dublinliteraryaward.ie/the-library/prize-years/2025/': '''
        <main>
          <h1>2025 Dublin Literary Award</h1>
          <h2>Winner</h2>
          <h3>The Coast Road</h3>
          <h4>Alan Murrin</h4>
        </main>
      ''',
      'https://dublinliteraryaward.ie/the-library/prize-years/2026/': '''
        <main>
          <h1>2026 Dublin Literary Award</h1>
          <h2>SHORTLIST</h2>
          <h3>Gliff</h3>
          <h4>Ali Smith</h4>
        </main>
      ''',
    }
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      return pages[url]

    parsed = DublinLiteraryAwardOfficialParser().parse(
      index_html,
      'https://dublinliteraryaward.ie/the-library/prize-years/',
      fetch_url=fetch_url)

    self.assertEqual([
      'https://dublinliteraryaward.ie/the-library/prize-years/2025/',
      'https://dublinliteraryaward.ie/the-library/prize-years/2026/',
    ], fetched)
    self.assertEqual([
      ('2025', 'The Coast Road', 'winner'),
      ('2026.01', 'Gliff', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['result'])
      for entry in parsed['entries']
    ])

  def test_dublin_literary_award_wikipedia_parser_handles_rowspans_and_results(self):
    from parser.dublin_literary_award import DublinLiteraryAwardWikipediaParser

    html = '''
      <table>
        <tr>
          <th>Year</th><th>Author</th><th>Title</th>
          <th>Translator</th><th>Language</th><th>Result</th><th>Ref.</th>
        </tr>
        <tr>
          <td rowspan="3">1996</td><td>David Malouf</td>
          <td><a href="/wiki/Remembering_Babylon">Remembering Babylon</a></td>
          <td></td><td>English</td><td>Winner</td><td>[1]</td>
        </tr>
        <tr>
          <td>John Banville</td><td>Ghosts</td>
          <td></td><td>English</td><td>Shortlist</td><td>[1]</td>
        </tr>
        <tr>
          <td>Jane Urquhart</td><td>Away</td>
          <td></td><td>English</td><td></td><td>[1]</td>
        </tr>
        <tr>
          <td>2024</td><td>Mircea Cărtărescu</td><td>Solenoid</td>
          <td>Sean Cotter</td><td>Romanian</td><td>Winner</td><td>[2]</td>
        </tr>
      </table>
    '''

    parsed = DublinLiteraryAwardWikipediaParser().parse(html)

    self.assertEqual([
      ('1996', 'Remembering Babylon', 'David Malouf', 'winner'),
      ('1996.01', 'Ghosts', 'John Banville', 'shortlisted'),
      ('1996.02', 'Away', 'Jane Urquhart', 'shortlisted'),
      ('2024', 'Solenoid', 'Mircea Cărtărescu', 'winner'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])

  def test_dublin_literary_award_fetcher_metadata_fallback_and_registry(self):
    from parser.base import (
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
    )
    from url_fetcher import available_url_fetchers
    from url_fetcher.dublin_literary_award import UrlFetcherDublinLiteraryAward

    fetcher = UrlFetcherDublinLiteraryAward()
    official_html = '<main><h1>Prize Years</h1></main>'
    wiki_html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr><td>2026</td><td>Ali Smith</td><td>Gliff</td><td>Winner</td></tr>
      </table>
    '''
    calls = []

    def fetch_url(url):
      calls.append(url)
      if url == fetcher.URL:
        return official_html
      if url == fetcher.WIKIPEDIA_URL:
        return wiki_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)
    filters = [item['label'] for item in fetcher.get_filter_list()]

    self.assertEqual('dublin_literary_award', fetcher.source_id)
    self.assertEqual('Dublin Literary Award', fetcher.NAME)
    self.assertFalse(fetcher.options['match_series'])
    self.assertIn(CATEGORY_LITERARY_GENERAL_FICTION, filters)
    self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
    self.assertEqual((
      {'label': 'Automatic', 'value': 'automatic'},
      {'label': 'Dublin Literary Award', 'value': 0},
      {'label': 'Wikipedia', 'value': 1},
    ), fetcher.source_choices())
    self.assertEqual(['Gliff'], [entry['title'] for entry in parsed['entries']])
    self.assertEqual([fetcher.URL, fetcher.WIKIPEDIA_URL], calls)
    self.assertFalse(parsed['match_series'])
    with self.assertRaises(Exception):
      fetcher.fetch_and_parse(fetch_url, disable_fallbacks=True)

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertIn('dublin_literary_award', registry_ids)
    self.assertLess(
      registry_ids.index('national_book_critics_circle_gregg_barrios_translation'),
      registry_ids.index('dublin_literary_award'))
    self.assertLess(
      registry_ids.index('dublin_literary_award'),
      registry_ids.index('walter_scott_prize'))

  def test_center_for_fiction_official_parser_discovers_and_parses_year_pages(self):
    from parser.center_for_fiction import CenterForFictionFirstNovelOfficialParser

    index_html = '''
      <main>
        <h2>Browse All Winners &amp; Finalists</h2>
        <a href="/book-recs/2025-first-novel-prize/">2025 First Novel Prize</a>
        <a href="/book-recs/2024-first-novel-prize/">2024 First Novel Prize</a>
        <a href="/book-recs/2006-first-novel-prize/">2006 First Novel Prize</a>
      </main>
    '''
    pages = {
      'https://centerforfiction.org/book-recs/2025-first-novel-prize/': '''
        <main>
          <h1>2025 First Novel Prize</h1>
          <h3><a href="/book-recs/natch/">Natch</a></h3>
          <p>By Darrell Kinsey</p>
          <p>Published by Tin House</p>
          <p>Winner</p>
          <h3>We Pretty Pieces of Flesh</h3><p>By Colwill Brown</p><p>Shortlisted</p>
          <h3>The Devil Three Times</h3><p>By Rickey Fayne</p><p>Shortlisted</p>
          <h3>Ibis</h3><p>By Justin Haynes</p><p>Shortlisted</p>
          <h3>Loca</h3><p>By Alejandro Heredia</p><p>Shortlisted</p>
          <h3>Liquid</h3><p>By Mariam Rahmani</p><p>Shortlisted</p>
          <h3>Optional Practical Training</h3><p>By Shubha Sunder</p><p>Shortlisted</p>
          <h3>Good Girl</h3><p>By Aria Aber</p><p>Longlisted</p>
          <h3>Crown</h3><p>By Natasha Brown</p><p>Longlisted</p>
          <h3>Dominion</h3><p>By Addie E. Citchens</p><p>Longlisted</p>
        </main>
      ''',
      'https://centerforfiction.org/book-recs/2024-first-novel-prize/': '''
        <main>
          <h1>2024 First Novel Prize</h1>
          <h3>God Bless You, Otis Spunkmeyer</h3>
          <p>By Joseph Earl Thomas</p>
          <p>Winner</p>
          <h3>Headshot</h3>
          <p>By Rita Bullwinkel</p>
          <p>Shortlisted</p>
        </main>
      ''',
      'https://centerforfiction.org/book-recs/2006-first-novel-prize/': '''
        <main>
          <h1>2006 First Novel Prize</h1>
          <h2>Winner</h2>
          <ul><li>Special Topics in Calamity Physics by Marisha Pessl (Viking)</li></ul>
          <h2>Shortlist</h2>
          <ul>
            <li>Cellophane by Marie Arana (Dial Press)</li>
            <li>Send Me by Patrick Ryan (Dial Press)</li>
          </ul>
        </main>
      ''',
    }
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      return pages[url]

    parsed = CenterForFictionFirstNovelOfficialParser().parse(
      index_html,
      'https://centerforfiction.org/grants-awards/the-first-novel-prize/',
      fetch_url=fetch_url)

    self.assertEqual([
      'https://centerforfiction.org/book-recs/2006-first-novel-prize/',
      'https://centerforfiction.org/book-recs/2024-first-novel-prize/',
      'https://centerforfiction.org/book-recs/2025-first-novel-prize/',
    ], fetched)
    self.assertEqual([
      ('2006', 'Special Topics in Calamity Physics', 'Marisha Pessl', 'winner'),
      ('2006.01', 'Cellophane', 'Marie Arana', 'shortlisted'),
      ('2006.02', 'Send Me', 'Patrick Ryan', 'shortlisted'),
      ('2024', 'God Bless You, Otis Spunkmeyer', 'Joseph Earl Thomas', 'winner'),
      ('2024.01', 'Headshot', 'Rita Bullwinkel', 'shortlisted'),
      ('2025', 'Natch', 'Darrell Kinsey', 'winner'),
      ('2025.01', 'We Pretty Pieces of Flesh', 'Colwill Brown', 'shortlisted'),
      ('2025.02', 'The Devil Three Times', 'Rickey Fayne', 'shortlisted'),
      ('2025.03', 'Ibis', 'Justin Haynes', 'shortlisted'),
      ('2025.04', 'Loca', 'Alejandro Heredia', 'shortlisted'),
      ('2025.05', 'Liquid', 'Mariam Rahmani', 'shortlisted'),
      ('2025.06', 'Optional Practical Training', 'Shubha Sunder', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertNotIn('Good Girl', [entry['title'] for entry in parsed['entries']])
    self.assertNotIn('Crown', [entry['title'] for entry in parsed['entries']])
    self.assertNotIn('Dominion', [entry['title'] for entry in parsed['entries']])
    self.assertTrue(all(
      entry['award'] == 'Center for Fiction First Novel Prize'
      for entry in parsed['entries']))
    self.assertTrue(all(entry['category'] == 'First Novel' for entry in parsed['entries']))
    self.assertFalse(parsed['match_series'])

  def test_center_for_fiction_wikipedia_parser_handles_rowspans_and_longlists(self):
    from parser.center_for_fiction import CenterForFictionFirstNovelWikipediaParser

    html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th><th>Ref.</th></tr>
        <tr><td rowspan="4">2025</td><td>Darrell Kinsey</td><td><a href="/wiki/Natch">Natch</a></td><td>Winner</td><td>[1]</td></tr>
        <tr><td>Colwill Brown</td><td>We Pretty Pieces of Flesh</td><td>Shortlisted</td><td>[1]</td></tr>
        <tr><td>Rickey Fayne</td><td>The Devil Three Times</td><td></td><td>[1]</td></tr>
        <tr><td>Aria Aber</td><td>Good Girl</td><td>Longlisted</td><td>[1]</td></tr>
        <tr><td>2024</td><td>Joseph Earl Thomas</td><td>God Bless You, Otis Spunkmeyer</td><td></td><td>[2]</td></tr>
      </table>
    '''

    parsed = CenterForFictionFirstNovelWikipediaParser().parse(html)

    self.assertEqual([
      ('2024', 'God Bless You, Otis Spunkmeyer', 'Joseph Earl Thomas', 'winner'),
      ('2025', 'Natch', 'Darrell Kinsey', 'winner'),
      ('2025.01', 'We Pretty Pieces of Flesh', 'Colwill Brown', 'shortlisted'),
      ('2025.02', 'The Devil Three Times', 'Rickey Fayne', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])

  def test_center_for_fiction_fetcher_metadata_fallback_and_registry(self):
    from parser.base import (
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
    )
    from url_fetcher import available_url_fetchers
    from url_fetcher.center_for_fiction import UrlFetcherCenterForFictionFirstNovelPrize
    from url_fetcher.generic import UrlFetcherError

    fetcher = UrlFetcherCenterForFictionFirstNovelPrize()

    self.assertEqual('center_for_fiction_first_novel_prize', fetcher.source_id)
    self.assertEqual('Center for Fiction First Novel Prize', fetcher.NAME)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual([
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
    ], [item['label'] for item in fetcher.get_filter_list()])
    self.assertEqual((
      {'label': 'Automatic', 'value': 'automatic'},
      {'label': 'Center for Fiction', 'value': 0},
      {'label': 'Wikipedia', 'value': 1},
    ), fetcher.source_choices())

    official_html = '<main><h1>The First Novel Prize</h1></main>'
    wiki_html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr><td>2025</td><td>Darrell Kinsey</td><td>Natch</td><td>Winner</td></tr>
      </table>
    '''
    calls = []

    def fetch_url(url):
      calls.append(url)
      if url == fetcher.URL:
        return official_html
      if url == fetcher.WIKIPEDIA_URL:
        return wiki_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)
    self.assertEqual(['Natch'], [entry['title'] for entry in parsed['entries']])
    self.assertEqual([fetcher.URL, fetcher.WIKIPEDIA_URL], calls)
    self.assertIn('Center for Fiction failed', parsed['notes'][0])
    self.assertFalse(parsed['match_series'])

    calls.clear()
    parsed_wiki = fetcher.fetch_and_parse(fetch_url, source_choice=1)
    self.assertEqual(['Natch'], [entry['title'] for entry in parsed_wiki['entries']])
    self.assertEqual([fetcher.WIKIPEDIA_URL], calls)

    calls.clear()
    with self.assertRaises(UrlFetcherError):
      fetcher.fetch_and_parse(fetch_url, disable_fallbacks=True)
    self.assertEqual([fetcher.URL], calls)

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertIn('center_for_fiction_first_novel_prize', registry_ids)
    self.assertLess(
      registry_ids.index('dublin_literary_award'),
      registry_ids.index('center_for_fiction_first_novel_prize'))
    self.assertLess(
      registry_ids.index('center_for_fiction_first_novel_prize'),
      registry_ids.index('walter_scott_prize'))

  def test_costa_whitbread_novel_parser_reads_rowspanned_results(self):
    from parser.costa_whitbread import CostaWhitbreadCategoryParser

    html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th><th>Ref.</th></tr>
        <tr style="background:lightyellow">
          <th rowspan="3">1995</th>
          <td>Salman Rushdie</td>
          <td><i><a href="/wiki/The_Moor%27s_Last_Sigh">The Moor's Last Sigh</a></i></td>
          <td>Winner</td><td></td>
        </tr>
        <tr>
          <td>Martin Amis</td><td><i>The Information</i></td>
          <td rowspan="2">Shortlist</td><td></td>
        </tr>
        <tr><td>Pat Barker</td><td><i>The Ghost Road</i></td><td></td></tr>
        <tr style="background:lightyellow">
          <th>2000</th><td>Matthew Kneale</td>
          <td><i>English Passengers</i> <img alt="Blue ribbon" /></td>
          <td>Winner</td><td></td>
        </tr>
      </table>
    '''

    parsed = CostaWhitbreadCategoryParser(
      'Costa/Whitbread Book Award - Novel',
      'Novel').parse(html, 'https://en.wikipedia.org/wiki/Costa_Book_Award_for_Novel')

    self.assertEqual([
      ('1995', "The Moor's Last Sigh", 'Salman Rushdie', 'winner'),
      ('1995.01', 'The Information', 'Martin Amis', 'shortlisted'),
      ('1995.02', 'The Ghost Road', 'Pat Barker', 'shortlisted'),
      ('2000', 'English Passengers', 'Matthew Kneale', 'winner'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertTrue(all(entry['category'] == 'Novel' for entry in parsed['entries']))

  def test_costa_whitbread_first_novel_parser_reads_split_eras_and_skips_no_award(self):
    from parser.costa_whitbread import CostaWhitbreadCategoryParser

    html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th></th><th>Ref.</th></tr>
        <tr style="background:#cddeff">
          <th>1975</th><td>Ruth Spalding</td>
          <td><i>The Improbable Puritan</i></td><td>Winner</td><td></td>
        </tr>
        <tr><td colspan="3"><i>No award presented 1976-1980</i></td><td></td><td></td></tr>
      </table>
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th><th>Ref.</th></tr>
        <tr style="background:#cddeff">
          <th rowspan="4">2021</th><td>Caleb Azumah Nelson</td>
          <td><i>Open Water</i></td><td>Winner</td><td></td>
        </tr>
        <tr><td>A. K. Blakemore</td><td><i>The Manningtree Witches</i></td><td rowspan="3">Shortlist</td><td></td></tr>
        <tr><td>Emily Itami</td><td><i>Fault Lines</i></td><td></td></tr>
        <tr><td>Kate Sawyer</td><td><i>The Stranding</i></td><td></td></tr>
      </table>
    '''

    parsed = CostaWhitbreadCategoryParser(
      'Costa/Whitbread Book Award - First Novel',
      'First Novel').parse(
        html, 'https://en.wikipedia.org/wiki/Costa_Book_Award_for_First_Novel')

    self.assertEqual([
      ('1975', 'The Improbable Puritan', 'Ruth Spalding', 'winner'),
      ('2021', 'Open Water', 'Caleb Azumah Nelson', 'winner'),
      ('2021.01', 'The Manningtree Witches', 'A. K. Blakemore', 'shortlisted'),
      ('2021.02', 'Fault Lines', 'Emily Itami', 'shortlisted'),
      ('2021.03', 'The Stranding', 'Kate Sawyer', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertNotIn('No award presented 1976-1980', [
      entry['title'] for entry in parsed['entries']
    ])

  def test_costa_whitbread_biography_parser_handles_subject_column_and_blank_shortlists(self):
    from parser.costa_whitbread import CostaWhitbreadCategoryParser

    html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Subject</th><th>Result</th><th>Ref.</th></tr>
        <tr style="background:lightyellow">
          <th rowspan="3">1995</th><td>Roy Jenkins</td><td><i>Gladstone</i></td>
          <td>William Gladstone</td><td>Winner</td><td></td>
        </tr>
        <tr><td>Paul Berry and Mark Bostridge</td><td><i>Vera Brittain - A Life</i></td><td>Vera Brittain</td><td></td><td></td></tr>
        <tr><td>Gitta Sereny</td><td><i>Albert Speer: His Battle with Truth</i></td><td>Albert Speer</td><td></td><td></td></tr>
        <tr style="background:lightyellow">
          <th rowspan="2">2011</th><td>Matthew Hollis</td>
          <td><i>Now All Roads Lead to France</i></td><td>Edward Thomas</td><td>Winner</td><td></td>
        </tr>
        <tr><td>Julia Blackburn</td><td><i>Thin Paths</i></td><td></td><td>Shortlist</td><td></td></tr>
      </table>
    '''

    parsed = CostaWhitbreadCategoryParser(
      'Costa/Whitbread Book Award - Biography',
      'Biography').parse(
        html, 'https://en.wikipedia.org/wiki/Costa_Book_Award_for_Biography')

    self.assertEqual([
      ('1995', 'Gladstone', 'Roy Jenkins', 'winner'),
      ('1995.01', 'Vera Brittain - A Life', 'Paul Berry and Mark Bostridge', 'shortlisted'),
      ('1995.02', 'Albert Speer: His Battle with Truth', 'Gitta Sereny', 'shortlisted'),
      ('2011', 'Now All Roads Lead to France', 'Matthew Hollis', 'winner'),
      ('2011.01', 'Thin Paths', 'Julia Blackburn', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])

  def test_costa_whitbread_childrens_book_parser_preserves_multiple_winners(self):
    from parser.costa_whitbread import CostaWhitbreadCategoryParser

    html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th><th>Ref.</th></tr>
        <tr style="background:lightyellow">
          <th rowspan="2">1974</th>
          <td>Russell Hoban and Quentin Blake</td>
          <td><i>How Tom Beat Captain Najork and His Hired Sportsmen</i></td>
          <td>Winner</td><td></td>
        </tr>
        <tr style="background:lightyellow">
          <td>Jill Paton Walsh</td><td><i>The Emperor's Winding Sheet</i></td>
          <td>Winner</td><td></td>
        </tr>
        <tr><th rowspan="2">1995</th><td>Michael Morpurgo</td><td><i>The Wreck of the Zanzibar</i></td><td>Winner</td><td></td></tr>
        <tr><td>Elizabeth Arnold</td><td><i>The Parsley Parcel</i></td><td>Shortlist</td><td></td></tr>
      </table>
    '''

    parsed = CostaWhitbreadCategoryParser(
      "Costa/Whitbread Book Award - Children's Book",
      "Children's Book").parse(
        html, 'https://en.wikipedia.org/wiki/Costa_Book_Award_for_Children%27s_Book')

    self.assertEqual([
      ('1974', 'How Tom Beat Captain Najork and His Hired Sportsmen',
       'Russell Hoban and Quentin Blake', 'winner'),
      ('1974', "The Emperor's Winding Sheet", 'Jill Paton Walsh', 'winner'),
      ('1995', 'The Wreck of the Zanzibar', 'Michael Morpurgo', 'winner'),
      ('1995.01', 'The Parsley Parcel', 'Elizabeth Arnold', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])

  def test_costa_whitbread_book_of_the_year_parser_reads_main_table(self):
    from parser.costa_whitbread import CostaWhitbreadBookOfTheYearParser

    html = '''
      <table>
        <tr>
          <th>Year</th><th>Novel</th><th>First novel</th>
          <th>Children's book</th><th>Poetry</th><th>Biography</th><th>Short story</th>
        </tr>
        <tr>
          <td>1980</td>
          <td><b>David Lodge<br /><i><a href="/wiki/How_Far_Can_You_Go">How Far Can You Go?</a></i></b> <img alt="Blue ribbon" /></td>
          <td></td><td></td><td></td><td></td><td></td>
        </tr>
        <tr>
          <td>1987</td><td></td><td></td><td></td><td></td>
          <td><b>Christopher Nolan<br /><i>Under the Eye of the Clock</i></b></td><td></td>
        </tr>
        <tr>
          <td>2001</td><td></td><td></td>
          <td><b>Philip Pullman<br /><i>The Amber Spyglass</i></b></td><td></td><td></td><td></td>
        </tr>
        <tr>
          <td>2013</td><td></td>
          <td><b>Nathan Filer, <i>The Shock of the Fall</i></b></td>
          <td></td><td></td><td></td><td></td>
        </tr>
        <tr>
          <td>2021</td><td></td><td></td><td></td>
          <td><b>Hannah Lowe<br /><i>The Kids</i></b></td><td></td><td></td>
        </tr>
      </table>
    '''

    parsed = CostaWhitbreadBookOfTheYearParser().parse(
      html, 'https://en.wikipedia.org/wiki/Costa_Book_Awards')

    self.assertEqual([
      ('1980', 'How Far Can You Go?', 'David Lodge', 'Novel'),
      ('1987', 'Under the Eye of the Clock', 'Christopher Nolan', 'Biography'),
      ('2001', 'The Amber Spyglass', 'Philip Pullman', "Children's Book"),
      ('2013', 'The Shock of the Fall', 'Nathan Filer', 'First Novel'),
      ('2021', 'The Kids', 'Hannah Lowe', 'Poetry'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['category'])
      for entry in parsed['entries']
    ])
    self.assertTrue(all(entry['result'] == 'winner' for entry in parsed['entries']))

  def test_costa_whitbread_fetcher_metadata_and_parse_smoke(self):
    from parser.base import (
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_NONFICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
      CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    )
    from url_fetcher.costa_whitbread import (
      UrlFetcherCostaWhitbreadBiography,
      UrlFetcherCostaWhitbreadBookOfTheYear,
      UrlFetcherCostaWhitbreadChildrensBook,
      UrlFetcherCostaWhitbreadFirstNovel,
      UrlFetcherCostaWhitbreadNovel,
    )

    fetchers = (
      (
        UrlFetcherCostaWhitbreadNovel(),
        'costa_whitbread_novel',
        CATEGORY_LITERARY_GENERAL_FICTION,
      ),
      (
        UrlFetcherCostaWhitbreadFirstNovel(),
        'costa_whitbread_first_novel',
        CATEGORY_LITERARY_GENERAL_FICTION,
      ),
      (
        UrlFetcherCostaWhitbreadBiography(),
        'costa_whitbread_biography',
        CATEGORY_NONFICTION,
      ),
      (
        UrlFetcherCostaWhitbreadChildrensBook(),
        'costa_whitbread_childrens_book',
        CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
      ),
      (
        UrlFetcherCostaWhitbreadBookOfTheYear(),
        'costa_whitbread_book_of_the_year',
        CATEGORY_LITERARY_GENERAL_FICTION,
      ),
    )
    for fetcher, source_id, expected_filter in fetchers:
      with self.subTest(fetcher=source_id):
        filters = [item['label'] for item in fetcher.get_filter_list()]
        self.assertEqual(source_id, fetcher.source_id)
        self.assertEqual(243, fetcher.order)
        self.assertFalse(fetcher.options['match_series'])
        self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())
        self.assertIn(expected_filter, filters)
        self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)

    overall_filters = [
      item['label']
      for item in UrlFetcherCostaWhitbreadBookOfTheYear().get_filter_list()
    ]
    self.assertIn(CATEGORY_NONFICTION, overall_filters)
    self.assertIn(CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE, overall_filters)

    html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th><th>Ref.</th></tr>
        <tr><th>2021</th><td>Claire Fuller</td><td><i>Unsettled Ground</i></td><td>Winner</td><td></td></tr>
      </table>
    '''
    parsed = UrlFetcherCostaWhitbreadNovel().fetch_and_parse(lambda _url: html)

    self.assertEqual('Costa/Whitbread Book Award - Novel', parsed['name'])
    self.assertEqual(['Unsettled Ground'], [entry['title'] for entry in parsed['entries']])
    self.assertFalse(parsed['match_series'])

  def test_rwa_rita_awards_parser_reads_winner_table_and_ignores_vivian(self):
    from parser.rwa_awards import RWARITAAwardsParser

    html = '''
      <h2><span>RITA Award winners</span><span>[edit]</span></h2>
      <table>
        <tr>
          <th>Year</th><th>Category</th><th>Sorting Category</th>
          <th>Title</th><th>Author</th>
        </tr>
        <tr>
          <td>1982</td><td>Category Contemporary Romance</td>
          <td>Contemporary Romance</td>
          <td><i><a href="/wiki/Winner_Take_All">Winner Take All</a></i></td>
          <td>Brooke Hastings</td>
        </tr>
        <tr>
          <td>1982</td><td>Mainstream Contemporary Romance</td>
          <td>Contemporary Romance</td>
          <td><i>The Sun Dancers</i></td><td>Barbara Faith</td>
        </tr>
        <tr>
          <td>2014</td><td>Romantic Suspense</td><td></td>
          <td><i>Off the Edge</i></td>
          <td>Carolyn Crane (first self-published winner)<sup>[1]</sup></td>
        </tr>
      </table>
      <h2>Vivian Award winners</h2>
      <h3>Best First Book</h3>
      <ul><li>2021: Love Me Like a Love Song by Annmarie Boyle</li></ul>
    '''

    parsed = RWARITAAwardsParser().parse(
      html, 'https://en.wikipedia.org/wiki/RITA_Award')

    self.assertEqual('RWA RITA Awards', parsed['name'])
    self.assertFalse(parsed['match_series'])
    self.assertEqual([
      ('1982', 'Winner Take All', 'Brooke Hastings',
       'Category Contemporary Romance', 'winner'),
      ('1982.01', 'The Sun Dancers', 'Barbara Faith',
       'Mainstream Contemporary Romance', 'winner'),
      ('2014', 'Off the Edge', 'Carolyn Crane', 'Romantic Suspense', 'winner'),
    ], [
      (
        entry['position'],
        entry['title'],
        entry['author'],
        entry['category'],
        entry['result'],
      )
      for entry in parsed['entries']
    ])
    self.assertEqual(
      'https://en.wikipedia.org/wiki/Winner_Take_All',
      parsed['entries'][0]['source_url'])
    self.assertNotIn('Love Me Like a Love Song', [
      entry['title'] for entry in parsed['entries']
    ])

  def test_rwa_rita_awards_fetcher_metadata_parse_and_registry(self):
    from parser.base import CATEGORY_REGIONAL_NATIONAL_AWARDS, CATEGORY_ROMANCE
    from url_fetcher import available_url_fetchers
    from url_fetcher.rwa_awards import UrlFetcherRWARITAAwards, UrlFetcherRWAVivianAwards

    fetcher = UrlFetcherRWARITAAwards()
    vivian = UrlFetcherRWAVivianAwards()
    filters = [item['label'] for item in fetcher.get_filter_list()]
    vivian_filters = [item['label'] for item in vivian.get_filter_list()]

    self.assertEqual('rwa_rita_awards', fetcher.source_id)
    self.assertEqual('RWA RITA Awards', fetcher.NAME)
    self.assertEqual('https://en.wikipedia.org/wiki/RITA_Award', fetcher.URL)
    self.assertEqual(247, fetcher.order)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())
    self.assertIn(CATEGORY_ROMANCE, filters)
    self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
    self.assertEqual('rwa_vivian_awards', vivian.source_id)
    self.assertEqual('RWA Vivian Awards', vivian.NAME)
    self.assertEqual('https://en.wikipedia.org/wiki/RITA_Award', vivian.URL)
    self.assertEqual(248, vivian.order)
    self.assertFalse(vivian.options['match_series'])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), vivian.source_choices())
    self.assertIn(CATEGORY_ROMANCE, vivian_filters)
    self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, vivian_filters)

    html = '''
      <table>
        <tr>
          <th>Year</th><th>Category</th><th>Sorting Category</th>
          <th>Title</th><th>Author</th>
        </tr>
        <tr>
          <td>2019</td><td>Best First Book</td><td></td>
          <td><i>Lady in Waiting</i></td><td>Marie Tremayne</td>
        </tr>
      </table>
    '''
    parsed = fetcher.fetch_and_parse(lambda _url: html)

    self.assertEqual('RWA RITA Awards', parsed['name'])
    self.assertEqual(['Lady in Waiting'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertFalse(parsed['match_series'])

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertIn('rwa_rita_awards', registry_ids)
    self.assertLess(
      registry_ids.index('act_book_of_the_year_award'),
      registry_ids.index('rwa_rita_awards'))
    self.assertLess(
      registry_ids.index('rwa_rita_awards'),
      registry_ids.index('rwa_vivian_awards'))
    self.assertLess(
      registry_ids.index('rwa_vivian_awards'),
      registry_ids.index('writers_trust_atwood_gibson_fiction'))

  def test_rwa_vivian_awards_parser_reads_winner_section_only(self):
    from parser.rwa_awards import RWAVivianAwardsParser

    html = '''
      <h2>RITA Award winners</h2>
      <table>
        <tr><th>Year</th><th>Category</th><th>Title</th><th>Author</th></tr>
        <tr><td>2019</td><td>Best First Book</td><td>Lady in Waiting</td><td>Marie Tremayne</td></tr>
      </table>
      <h2><span>Vivian Award winners</span><span class="mw-editsection">[edit]</span></h2>
      <h3>Best First Book</h3>
      <p>2021: <a href="/wiki/Love_Me_Like_a_Love_Song">Love Me Like a Love Song</a>
        by <a href="/wiki/Annmarie_Boyle">Annmarie Boyle</a><sup>[1]</sup></p>
      <h3>Contemporary Romance</h3>
      <ul>
        <li>Long Contemporary Romance: 2021: The Intimacy Experiment by Rosie Danan</li>
        <li>Mid-Length Contemporary Romance: 2021: Take a Hint, Dani Brown by Talia Hibbert</li>
      </ul>
      <h3>Inspirational Romance</h3>
      <ul>
        <li>Romance with Religious or Spiritual Elements: 2021:
          At Love's Command by Karen Witemeyer (award rescinded)</li>
      </ul>
      <h2>References</h2>
    '''

    parsed = RWAVivianAwardsParser().parse(
      html, 'https://en.wikipedia.org/wiki/RITA_Award')

    self.assertEqual('RWA Vivian Awards', parsed['name'])
    self.assertFalse(parsed['match_series'])
    self.assertEqual([
      ('2021', 'Love Me Like a Love Song', 'Annmarie Boyle',
       'Best First Book', 'winner'),
      ('2021.01', 'The Intimacy Experiment', 'Rosie Danan',
       'Long Contemporary Romance', 'winner'),
      ('2021.02', 'Take a Hint, Dani Brown', 'Talia Hibbert',
       'Mid-Length Contemporary Romance', 'winner'),
      ('2021.03', "At Love's Command", 'Karen Witemeyer',
       'Romance with Religious or Spiritual Elements', 'winner'),
    ], [
      (
        entry['position'],
        entry['title'],
        entry['author'],
        entry['category'],
        entry['result'],
      )
      for entry in parsed['entries']
    ])
    self.assertEqual(
      'https://en.wikipedia.org/wiki/Love_Me_Like_a_Love_Song',
      parsed['entries'][0]['source_url'])
    self.assertNotIn('Lady in Waiting', [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertIn('winner-only', parsed['notes'][0])
    self.assertTrue(any('rescinded' in note for note in parsed['notes']))

  def test_rna_romantic_novel_awards_parser_reads_archive_and_shortlists(self):
    from parser.rna_awards import RNARomanticNovelAwardsParser

    archive_html = '''
      <h1>Past winners</h1>
      <h2><a href="/winners/love-me">Love Me Till Wednesday</a></h2>
      <h2>Suzanne Lissaman</h2>
      <ul>
        <li>Self-published</li>
        <li><a href="/award/romantic-novel-of-the-year">Romantic Novel of the Year</a></li>
        <li><a href="/award-category/romantic-comedy">Romantic Comedy</a></li>
        <li><a href="/year/2025">2025</a></li>
      </ul>
      <h2><a href="/winners/jha-book">Things We Do for Love and Science</a></h2>
      <h2>Ruth Kramer</h2>
      <ul>
        <li>Champagne Book Group</li>
        <li><a href="/award/joan-hessayon">Joan Hessayon</a></li>
        <li><a href="/award-category/joan-hessayon">Joan Hessayon</a></li>
        <li><a href="/year/2025">2025</a></li>
      </ul>
      <h2><a href="/winners/industry-person">Jane Agent</a></h2>
      <ul>
        <li><a href="/award/industry">RNA Industry</a></li>
        <li><a href="/award-category/agent">Agent of the Year</a></li>
        <li><a href="/year/2025">2025</a></li>
      </ul>
    '''
    shortlist_json = json.dumps({
      'link': 'https://romanticnovelistsassociation.org/news/shortlists-2025',
      'title': {
        'rendered': 'PRESS RELEASE: The Romantic Novelists Association reveals shortlists for Romantic Novel of the Year Awards 2025',
      },
      'content': {'rendered': '''
        <p><strong><u>The Joan Hessayon Award for New Writers</u></strong></p>
        <p><em>Things We Do for Love and Science</em> by Ruth Kramer (Champagne Book Group)</p>
        <p><strong><u>The Romantic Comedy Award</u></strong></p>
        <p><em>Exposure!</em> by Julia Boggio (Self Published)</p>
        <p><em>Love Me Till Wednesday</em> by Suzanne Lissaman (Self Published)</p>
        <p><strong><u>The Popular Romantic Fiction Novel Award</u></strong></p>
        <p><em>All the Painted Stars</em> by Emma Denny (HQ)</p>
      '''},
    })

    parsed = RNARomanticNovelAwardsParser().parse(
      archive_html,
      'https://romanticnovelistsassociation.org/past-winners',
      shortlist_pages=(('https://romanticnovelistsassociation.org/wp-json/wp/v2/news/1',
                        shortlist_json),))

    self.assertEqual('RNA Romantic Novel of the Year Awards', parsed['name'])
    self.assertFalse(parsed['match_series'])
    self.assertEqual([
      ('2025', 'Love Me Till Wednesday', 'Suzanne Lissaman', 'Romantic Comedy', 'winner'),
      ('2025.01', 'Exposure!', 'Julia Boggio', 'Romantic Comedy', 'shortlisted'),
      ('2025.02', 'All the Painted Stars', 'Emma Denny',
       'Popular Romantic Fiction Novel', 'shortlisted'),
    ], [
      (
        entry['position'],
        entry['title'],
        entry['author'],
        entry['category'],
        entry['result'],
      )
      for entry in parsed['entries']
    ])
    self.assertNotIn('Things We Do for Love and Science', [
      entry['title'] for entry in parsed['entries']
    ])

  def test_rna_romantic_novel_awards_fetcher_discovers_pages_and_shortlists(self):
    from parser.base import CATEGORY_REGIONAL_NATIONAL_AWARDS, CATEGORY_ROMANCE
    from parser.rna_awards import RNA_SHORTLIST_SEARCH_URLS
    from url_fetcher import available_url_fetchers
    from url_fetcher.rna_awards import UrlFetcherRNARomanticNovelAwards

    fetcher = UrlFetcherRNARomanticNovelAwards()
    filters = [item['label'] for item in fetcher.get_filter_list()]

    self.assertEqual('rna_romantic_novel_awards', fetcher.source_id)
    self.assertEqual('RNA Romantic Novel of the Year Awards', fetcher.NAME)
    self.assertEqual('https://romanticnovelistsassociation.org/past-winners', fetcher.URL)
    self.assertEqual(248, fetcher.order)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())
    self.assertIn(CATEGORY_ROMANCE, filters)
    self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)

    archive_html = '''
      <h1>Past winners</h1>
      <h2><a href="/winners/cover-story">Cover Story</a></h2>
      <h2>Mhairi McFarlane</h2>
      <ul>
        <li>HarperCollins</li>
        <li><a href="/award/romantic-novel-of-the-year">Romantic Novel of the Year</a></li>
        <li><a href="/award-category/romantic-comedy">Romantic Comedy</a></li>
        <li><a href="/year/2026">2026</a></li>
      </ul>
      <a href="https://romanticnovelistsassociation.org/past-winners/page/2/">2</a>
    '''
    page_two_html = '''
      <h2><a href="/winners/all-painted">All the Painted Stars</a></h2>
      <h2>Emma Denny</h2>
      <ul>
        <li>HQ</li>
        <li><a href="/award/romantic-novel-of-the-year">Romantic Novel of the Year</a></li>
        <li><a href="/award-category/popular">Popular Romantic Fiction</a></li>
        <li><a href="/year/2025">2025</a></li>
      </ul>
    '''
    search_json = json.dumps([{
      'title': {
        'rendered': 'The RNA announces the 2026 shortlists for the Romantic Novel of the Year Awards',
      },
      '_links': {'self': [{'href': 'https://romanticnovelistsassociation.org/wp-json/wp/v2/news/101382'}]},
    }, {
      'title': {'rendered': 'ROMANTIC NOVELISTS ASSOCIATION ROMANCE INDUSTRY AWARDS 2025 SHORTLISTS ANNOUNCED'},
      '_links': {'self': [{'href': 'https://romanticnovelistsassociation.org/wp-json/wp/v2/news/industry'}]},
    }])
    shortlist_json = json.dumps({
      'link': 'https://romanticnovelistsassociation.org/news/ronas2026-finalists',
      'title': {'rendered': 'The RNA announces the 2026 shortlists for the Romantic Novel of the Year Awards'},
      'content': {'rendered': '''
        <section class="accordion">
          <h2>Debut Romance Novel Award</h2>
          <div class="panel">
            <h3>Any Trope But You by Victoria Lavine</h3>
            <ul><li>Publisher: Zaffre</li></ul>
          </div>
          <h2>The Joan Hessayon Award for New Writers (JHA)</h2>
          <div class="panel">
            <h3>Love &amp; Other Liabilities by Fiona McCann</h3>
          </div>
        </section>
      '''},
    })
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if url == fetcher.URL:
        return archive_html
      if url == 'https://romanticnovelistsassociation.org/past-winners/page/2/':
        return page_two_html
      if url in RNA_SHORTLIST_SEARCH_URLS:
        return search_json
      if url == 'https://romanticnovelistsassociation.org/wp-json/wp/v2/news/101382':
        return shortlist_json
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual([
      ('2025', 'All the Painted Stars', 'winner'),
      ('2026', 'Cover Story', 'winner'),
      ('2026.01', 'Any Trope But You', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertNotIn('Love & Other Liabilities', [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertIn('https://romanticnovelistsassociation.org/past-winners/page/2/', fetched)

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertIn('rna_romantic_novel_awards', registry_ids)
    self.assertLess(
      registry_ids.index('rwa_rita_awards'),
      registry_ids.index('rna_romantic_novel_awards'))
    self.assertLess(
      registry_ids.index('rna_romantic_novel_awards'),
      registry_ids.index('writers_trust_atwood_gibson_fiction'))

  def test_rna_joan_hessayon_parser_reads_archive_and_available_contenders(self):
    from parser.rna_awards import RNAJoanHessayonAwardParser

    archive_html = '''
      <h1>Past winners</h1>
      <h2><a href="/winners/love-liabilities">Love &amp; Other Liabilities</a></h2>
      <h2>Fiona McCann</h2>
      <ul>
        <li>Poolbeg Press</li>
        <li><a href="/award/joan-hessayon">Joan Hessayon</a></li>
        <li><a href="/award-category/joan-hessayon">Joan Hessayon</a></li>
        <li><a href="/year/2026">2026</a></li>
      </ul>
      <h2><a href="/winners/love-rebooted">Love Rebooted</a></h2>
      <h2>Katy Summers</h2>
      <ul>
        <li>Audible Originals</li>
        <li><a href="/award/joan-hessayon">Joan Hessayon</a></li>
        <li><a href="/award-category/joan-hessayon">Joan Hessayon</a></li>
        <li><a href="/year/2025">2025</a></li>
      </ul>
      <h2><a href="/winners/wedding-hitch">The Wedding Hitch</a></h2>
      <h2>Claire McCauley</h2>
      <ul>
        <li>Joffe Books</li>
        <li><a href="/award/joan-hessayon">Joan Hessayon</a></li>
        <li><a href="/award-category/joan-hessayon">Joan Hessayon</a></li>
        <li><a href="/year/2024">2024</a></li>
      </ul>
      <h2><a href="/winners/rona-book">Cover Story</a></h2>
      <h2>Mhairi McFarlane</h2>
      <ul>
        <li>HarperCollins</li>
        <li><a href="/award/romantic-novel-of-the-year">Romantic Novel of the Year</a></li>
        <li><a href="/award-category/romantic-comedy">Romantic Comedy</a></li>
        <li><a href="/year/2026">2026</a></li>
      </ul>
      <h2><a href="/winners/industry-person">Jane Agent</a></h2>
      <ul>
        <li><a href="/award/industry">RNA Industry</a></li>
        <li><a href="/award-category/agent">Agent of the Year</a></li>
        <li><a href="/year/2025">2025</a></li>
      </ul>
      <a href="https://romanticnovelistsassociation.org/past-winners/page/2/">2</a>
    '''
    page_two_html = '''
      <h2><a href="/winners/foreign-land">In This Foreign Land</a></h2>
      <h2>Suzie Hull</h2>
      <ul>
        <li>Orion Dash</li>
        <li><a href="/award/joan-hessayon">Joan Hessayon</a></li>
        <li><a href="/award-category/joan-hessayon">Joan Hessayon</a></li>
        <li><a href="/year/2022">2022</a></li>
      </ul>
    '''
    combined_2026 = json.dumps({
      'link': 'https://romanticnovelistsassociation.org/news/ronas2026-finalists',
      'title': {'rendered': 'The RNA announces the 2026 shortlists for the Romantic Novel of the Year Awards and the contenders JHA'},
      'content': {'rendered': '''
        <section class="accordion">
          <h2>Debut Romance Novel Award</h2>
          <div class="panel">
            <h3>Any Trope But You by Victoria Lavine</h3>
          </div>
          <h2>The Joan Hessayon Award for New Writers (JHA)</h2>
          <div class="panel">
            <h3>A New Hope in the Highlands by Rachel Debrave</h3>
            <h3>Love &amp; Other Liabilities by Fiona McCann</h3>
          </div>
        </section>
      '''},
    })
    finalist_2025 = json.dumps({
      'link': 'https://romanticnovelistsassociation.org/news/finalists-the-joan-hessayon-award-for-new-writers-2025',
      'title': {'rendered': 'Finalists: The Joan Hessayon Award for New Writers 2025'},
      'content': {'rendered': '''
        <section class="text-block">
          <p><strong><em>The Beat of Our Hearts</em> by Amanda Giles (D C Thompson):</strong></p>
          <p>Delighted to be a contender.</p>
        </section>
        <section class="text-block">
          <p><strong><em>Love Rebooted</em> by Katy Summers (Audible)</strong></p>
        </section>
      '''},
    })
    contenders_2024 = json.dumps({
      'link': 'https://romanticnovelistsassociation.org/news/rna-joan-hessayon-award-for-new-writers-2024-six-contenders-announced',
      'title': {'rendered': 'RNA Joan Hessayon Award for New Writers 2024 - Six Contenders Announced'},
      'content': {'rendered': '''
        <p>The contenders for 2024 are as follows:</p>
        <ul>
          <li>Helen Hawkins, <em>A Concert for Christmas</em>, Allison &amp; Busby</li>
          <li>Claire McCauley, <em>The Wedding Hitch</em>, Joffe Books</li>
        </ul>
      '''},
    })
    contenders_2022 = json.dumps({
      'link': 'https://romanticnovelistsassociation.org/news/contenders-announced-romantic-novelists-association-joan-hessayon-award-2022',
      'title': {'rendered': 'Contenders Announced: Romantic Novelists Association Joan Hessayon Award 2022'},
      'content': {'rendered': '''
        <p><strong>The contenders for 2022 are as follows:</strong></p>
        <p>Jennifer Bibby, <em>The Cornish Hideaway</em>, Simon &amp; Schuster UK</p>
        <p>Suzie Hull, <em>In This Foreign Land</em>, Orion Dash</p>
      '''},
    })

    parsed = RNAJoanHessayonAwardParser().parse(
      archive_html,
      'https://romanticnovelistsassociation.org/past-winners',
      fetch_url=lambda url: page_two_html,
      shortlist_pages=(
        ('https://romanticnovelistsassociation.org/wp-json/wp/v2/news/101382', combined_2026),
        ('https://romanticnovelistsassociation.org/wp-json/wp/v2/news/90777', finalist_2025),
        ('https://romanticnovelistsassociation.org/wp-json/wp/v2/news/82583', contenders_2024),
        ('https://romanticnovelistsassociation.org/wp-json/wp/v2/news/48477', contenders_2022),
      ))

    self.assertEqual('RNA Joan Hessayon Award for New Writers', parsed['name'])
    self.assertFalse(parsed['match_series'])
    self.assertEqual([
      ('2022', 'In This Foreign Land', 'Suzie Hull', 'winner'),
      ('2022.01', 'The Cornish Hideaway', 'Jennifer Bibby', 'shortlisted'),
      ('2024', 'The Wedding Hitch', 'Claire McCauley', 'winner'),
      ('2024.01', 'A Concert for Christmas', 'Helen Hawkins', 'shortlisted'),
      ('2025', 'Love Rebooted', 'Katy Summers', 'winner'),
      ('2025.01', 'The Beat of Our Hearts', 'Amanda Giles', 'shortlisted'),
      ('2026', 'Love & Other Liabilities', 'Fiona McCann', 'winner'),
      ('2026.01', 'A New Hope in the Highlands', 'Rachel Debrave', 'shortlisted'),
    ], [
      (
        entry['position'],
        entry['title'],
        entry['author'],
        entry['result'],
      )
      for entry in parsed['entries']
    ])
    self.assertTrue(all(entry['category'] == 'Joan Hessayon' for entry in parsed['entries']))
    self.assertNotIn('Cover Story', [entry['title'] for entry in parsed['entries']])
    self.assertIn('official-news dependent', parsed['notes'][0])

  def test_rna_joan_hessayon_fetcher_discovers_aggregate_contender_posts(self):
    from parser.base import CATEGORY_REGIONAL_NATIONAL_AWARDS, CATEGORY_ROMANCE
    from parser.rna_awards import RNA_JOAN_HESSAYON_SEARCH_URLS
    from url_fetcher import available_url_fetchers
    from url_fetcher.rna_awards import (
      UrlFetcherRNAJoanHessayonAward,
      UrlFetcherRNARomanticNovelAwards,
    )

    fetcher = UrlFetcherRNAJoanHessayonAward()
    rona = UrlFetcherRNARomanticNovelAwards()
    filters = [item['label'] for item in fetcher.get_filter_list()]

    self.assertEqual('rna_joan_hessayon_award', fetcher.source_id)
    self.assertEqual('RNA Joan Hessayon Award for New Writers', fetcher.NAME)
    self.assertEqual('https://romanticnovelistsassociation.org/past-winners', fetcher.URL)
    self.assertEqual(248, fetcher.order)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())
    self.assertIn(CATEGORY_ROMANCE, filters)
    self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)

    archive_html = '''
      <h1>Past winners</h1>
      <h2><a href="/winners/love-liabilities">Love &amp; Other Liabilities</a></h2>
      <h2>Fiona McCann</h2>
      <ul>
        <li>Poolbeg Press</li>
        <li><a href="/award/joan-hessayon">Joan Hessayon</a></li>
        <li><a href="/award-category/joan-hessayon">Joan Hessayon</a></li>
        <li><a href="/year/2026">2026</a></li>
      </ul>
      <a href="https://romanticnovelistsassociation.org/past-winners/page/2/">2</a>
    '''
    page_two_html = '''
      <h2><a href="/winners/love-rebooted">Love Rebooted</a></h2>
      <h2>Katy Summers</h2>
      <ul>
        <li>Audible Originals</li>
        <li><a href="/award/joan-hessayon">Joan Hessayon</a></li>
        <li><a href="/award-category/joan-hessayon">Joan Hessayon</a></li>
        <li><a href="/year/2025">2025</a></li>
      </ul>
    '''
    search_json = json.dumps([{
      'title': {'rendered': 'Finalists: The Joan Hessayon Award for New Writers 2025'},
      '_links': {'self': [{'href': 'https://romanticnovelistsassociation.org/wp-json/wp/v2/news/90777'}]},
    }, {
      'title': {'rendered': 'RNA Joan Hessayon Award Contender: Person - Book'},
      '_links': {'self': [{'href': 'https://romanticnovelistsassociation.org/wp-json/wp/v2/news/profile'}]},
    }, {
      'title': {'rendered': 'The Historical Romantic Novel Award - Finalists'},
      '_links': {'self': [{'href': 'https://romanticnovelistsassociation.org/wp-json/wp/v2/news/rona'}]},
    }, {
      'title': {'rendered': 'RNA Industry Awards 2025 Shortlists Announced'},
      '_links': {'self': [{'href': 'https://romanticnovelistsassociation.org/wp-json/wp/v2/news/industry'}]},
    }, {
      'title': {'rendered': 'Joan Hessayon Award Members log in to request submission'},
      '_links': {'self': [{'href': 'https://romanticnovelistsassociation.org/wp-json/wp/v2/pages/member'}]},
    }])
    finalist_json = json.dumps({
      'link': 'https://romanticnovelistsassociation.org/news/finalists-the-joan-hessayon-award-for-new-writers-2025',
      'title': {'rendered': 'Finalists: The Joan Hessayon Award for New Writers 2025'},
      'content': {'rendered': '''
        <p><strong><em>The Beat of Our Hearts</em> by Amanda Giles (D C Thompson):</strong></p>
      '''},
    })
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if url == fetcher.URL:
        return archive_html
      if url == 'https://romanticnovelistsassociation.org/past-winners/page/2/':
        return page_two_html
      if url in RNA_JOAN_HESSAYON_SEARCH_URLS:
        return search_json
      if url == 'https://romanticnovelistsassociation.org/wp-json/wp/v2/news/90777':
        return finalist_json
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual([
      ('2025', 'Love Rebooted', 'winner'),
      ('2025.01', 'The Beat of Our Hearts', 'shortlisted'),
      ('2026', 'Love & Other Liabilities', 'winner'),
    ], [
      (entry['position'], entry['title'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertIn('https://romanticnovelistsassociation.org/past-winners/page/2/', fetched)
    self.assertIn('https://romanticnovelistsassociation.org/wp-json/wp/v2/news/90777', fetched)
    self.assertNotIn('https://romanticnovelistsassociation.org/wp-json/wp/v2/news/profile', fetched)
    self.assertNotIn('https://romanticnovelistsassociation.org/wp-json/wp/v2/news/industry', fetched)

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertIn('rna_joan_hessayon_award', registry_ids)
    self.assertLess(
      registry_ids.index(rona.source_id),
      registry_ids.index('rna_joan_hessayon_award'))
    self.assertLess(
      registry_ids.index('rna_joan_hessayon_award'),
      registry_ids.index('ripped_bodice_awards'))

  def test_ripped_bodice_awards_parser_reads_wikitext_json_and_grouped_titles(self):
    from parser.ripped_bodice_awards import RippedBodiceAwardsParser

    wikitext = """
== Description ==
This section should not be imported. ''[[Not a Romance Award]]'' by Someone.

== Romance Awards ==
In February 2020, the Ripped Bodice announced the first winners of their newly
established awards for romance. The contest is titled The Ripped Bodice's
Awards for Excellence in Romance Fiction and acknowledges the chosen best
romance titles for 2019.<ref name="bookriot2019" /> The winners included
''[[Xeni]]'' by [[Rebekah Weatherspoon]], ''[[Mrs. Martin's Incomparable Adventure]]''
by [[Courtney Milan]], ''[[Get a Life, Chloe Brown]]'' by [[Talia Hibbert]],
''[[A Prince on Paper]]''; ''[[One Ghosted, Twice Shy]]''; and
''[[An Unconditional Freedom]]'' by [[Alyssa Cole]], ''[[American Love Story]]''
by [[Adriana Herrera]], ''[[Trashed]]'' by [[Mia Hopkins]], and
''[[The Austen Playbook]]'' by [[Lucy Parker]]. The 2020 winners were
''[[Go Deep]]'' by [[Rilzy Adams]], ''[[Harbor]]'' by [[Rebekah Weatherspoon]],
''[[Spoiler Alert]]'' by [[Olivia Dade]], ''[[Take a Hint, Dani Brown]]'' by
[[Talia Hibbert]], ''[[The Care and Feeding of Waspish Widows]]'' by
[[Olivia Waite]], ''[[The Duke Who Didn't]]'' by [[Courtney Milan]],
''[[The Rakess]]'' by [[Scarlett Peckham]], ''[[The Roommate]]'' by
[[Rosie Danan]], ''[[The Worst Best Man]]'' by [[Mia Sosa]],
''[[You Had Me at Hola]]'' by [[Alexis Daria]], ''[[You Should See Me in a Crown]]''
by [[Leah Johnson]], and ''[[Written in the Stars]]'' by [[Alexandria Bellefleur]].

== References ==
"""
    source_json = json.dumps({'parse': {'wikitext': wikitext}})

    parsed = RippedBodiceAwardsParser().parse(source_json)

    self.assertEqual(
      'Ripped Bodice Awards for Excellence in Romance Fiction',
      parsed['name'])
    self.assertFalse(parsed['match_series'])
    self.assertEqual(21, len(parsed['entries']))
    self.assertEqual([
      ('2019', 'Xeni', 'Rebekah Weatherspoon', 'Romance Fiction', 'winner'),
      ('2019.01', "Mrs. Martin's Incomparable Adventure", 'Courtney Milan',
       'Romance Fiction', 'winner'),
      ('2019.02', 'Get a Life, Chloe Brown', 'Talia Hibbert',
       'Romance Fiction', 'winner'),
      ('2019.03', 'A Prince on Paper', 'Alyssa Cole', 'Romance Fiction', 'winner'),
      ('2019.04', 'One Ghosted, Twice Shy', 'Alyssa Cole',
       'Romance Fiction', 'winner'),
      ('2019.05', 'An Unconditional Freedom', 'Alyssa Cole',
       'Romance Fiction', 'winner'),
      ('2019.06', 'American Love Story', 'Adriana Herrera',
       'Romance Fiction', 'winner'),
      ('2019.07', 'Trashed', 'Mia Hopkins', 'Romance Fiction', 'winner'),
      ('2019.08', 'The Austen Playbook', 'Lucy Parker',
       'Romance Fiction', 'winner'),
      ('2020', 'Go Deep', 'Rilzy Adams', 'Romance Fiction', 'winner'),
      ('2020.01', 'Harbor', 'Rebekah Weatherspoon', 'Romance Fiction', 'winner'),
      ('2020.02', 'Spoiler Alert', 'Olivia Dade', 'Romance Fiction', 'winner'),
      ('2020.03', 'Take a Hint, Dani Brown', 'Talia Hibbert',
       'Romance Fiction', 'winner'),
      ('2020.04', 'The Care and Feeding of Waspish Widows', 'Olivia Waite',
       'Romance Fiction', 'winner'),
      ('2020.05', "The Duke Who Didn't", 'Courtney Milan',
       'Romance Fiction', 'winner'),
      ('2020.06', 'The Rakess', 'Scarlett Peckham', 'Romance Fiction', 'winner'),
      ('2020.07', 'The Roommate', 'Rosie Danan', 'Romance Fiction', 'winner'),
      ('2020.08', 'The Worst Best Man', 'Mia Sosa', 'Romance Fiction', 'winner'),
      ('2020.09', 'You Had Me at Hola', 'Alexis Daria',
       'Romance Fiction', 'winner'),
      ('2020.10', 'You Should See Me in a Crown', 'Leah Johnson',
       'Romance Fiction', 'winner'),
      ('2020.11', 'Written in the Stars', 'Alexandria Bellefleur',
       'Romance Fiction', 'winner'),
    ], [
      (
        entry['position'],
        entry['title'],
        entry['author'],
        entry['category'],
        entry['result'],
      )
      for entry in parsed['entries']
    ])
    self.assertEqual(
      'https://en.wikipedia.org/wiki/Xeni',
      parsed['entries'][0]['source_url'])
    self.assertNotIn('Not a Romance Award', [
      entry['title'] for entry in parsed['entries']
    ])

  def test_ripped_bodice_awards_parser_accepts_raw_wikitext_and_fails_empty(self):
    from parser.ripped_bodice_awards import RippedBodiceAwardsParser

    raw_wikitext = """
== Romance Awards ==
The winners included ''Sample Title'' by Sample Author. The 2020 winners were
''Other Title'' by Other Author.
"""

    parsed = RippedBodiceAwardsParser().parse(raw_wikitext)

    self.assertEqual(['Sample Title', 'Other Title'], [
      entry['title'] for entry in parsed['entries']
    ])
    with self.assertRaises(ValueError):
      RippedBodiceAwardsParser().parse('== Description ==\nNo awards here.')

  def test_ripped_bodice_awards_fetcher_metadata_parse_and_registry(self):
    from parser.base import CATEGORY_REGIONAL_NATIONAL_AWARDS, CATEGORY_ROMANCE
    from url_fetcher import available_url_fetchers
    from url_fetcher.ripped_bodice_awards import UrlFetcherRippedBodiceAwards

    fetcher = UrlFetcherRippedBodiceAwards()
    filters = [item['label'] for item in fetcher.get_filter_list()]

    self.assertEqual('ripped_bodice_awards', fetcher.source_id)
    self.assertEqual(
      'Ripped Bodice Awards for Excellence in Romance Fiction',
      fetcher.NAME)
    self.assertEqual(
      'https://en.wikipedia.org/wiki/The_Ripped_Bodice',
      fetcher.display_url)
    self.assertEqual(249, fetcher.order)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())
    self.assertIn(CATEGORY_ROMANCE, filters)
    self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)

    source_json = json.dumps({
      'parse': {
        'wikitext': """
== Romance Awards ==
The winners included ''[[Xeni]]'' by [[Rebekah Weatherspoon]]. The 2020 winners
were ''[[Go Deep]]'' by [[Rilzy Adams]].
"""
      }
    })
    parsed = fetcher.fetch_and_parse(lambda _url: source_json)

    self.assertEqual(['Xeni', 'Go Deep'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertFalse(parsed['match_series'])

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertIn('ripped_bodice_awards', registry_ids)
    self.assertLess(
      registry_ids.index('rna_romantic_novel_awards'),
      registry_ids.index('ripped_bodice_awards'))
    self.assertLess(
      registry_ids.index('ripped_bodice_awards'),
      registry_ids.index('writers_trust_atwood_gibson_fiction'))

  def test_romantic_times_awards_parser_reads_archived_winner_and_nominee_pages(self):
    from parser.romantic_times_awards import RomanticTimesReviewersChoiceParser

    winner_url = (
      'https://web.archive.org/web/20160301010101id_/'
      'http://www.rtbookreviews.com/blog/90001/2015-rt-reviewers-choice-award-winners-historical-romance')
    winner_html = '''
      <article>
        <h1 class="title">2015 RT Reviewers' Choice Award Winners — Historical Romance</h1>
        <div class="field field-name-body">
          <div class="field-item even">
            <p><strong>Historical Romance</strong></p>
            <p><em>The Rogue Not Taken</em> by Sarah MacLean</p>
            <p><strong>Fantasy Novel</strong></p>
            <p><em>Uprooted</em> by Naomi Novik</p>
          </div>
        </div>
      </article>
    '''
    nominee_url = (
      'https://web.archive.org/web/20160105213619id_/'
      'http://www.rtbookreviews.com/blog/86296/2015-rt-reviewers-choice-award-nominees-series-romance')
    nominee_html = '''
      <article>
        <h1 class="title">2015 RT Reviewers' Choice Award Nominees — Series Romance</h1>
        <div class="field field-name-body">
          <div class="field-item even">
            <p><strong>Harlequin American</strong></p>
            <table>
              <tr>
                <td>
                  <a href="http://www.rtbookreviews.com/book-review/mistletoe-rodeo">
                    <img alt="Amanda Renee, Mistletoe Rodeo" />
                  </a>
                </td>
                <td><img alt="Marin Thomas: A Cowboy's Redemption" /></td>
              </tr>
            </table>
            <p><strong>Mystery Novel</strong></p>
            <table><tr><td><img alt="Naomi Novik, Uprooted" /></td></tr></table>
          </div>
        </div>
      </article>
    '''

    winner_parsed = RomanticTimesReviewersChoiceParser().parse(winner_html, winner_url)
    nominee_parsed = RomanticTimesReviewersChoiceParser().parse(nominee_html, nominee_url)

    self.assertEqual(
      [('2015', 'The Rogue Not Taken', 'Sarah MacLean', 'Historical Romance', 'winner')],
      [
        (
          entry['position'],
          entry['title'],
          entry['author'],
          entry['category'],
          entry['result'],
        )
        for entry in winner_parsed['entries']
      ])
    self.assertEqual(winner_url, winner_parsed['entries'][0]['source_url'])
    self.assertNotIn('Uprooted', [entry['title'] for entry in winner_parsed['entries']])

    self.assertEqual([
      ('2015.01', 'Mistletoe Rodeo', 'Amanda Renee', 'Harlequin American', 'nominee'),
      ('2015.02', "A Cowboy's Redemption", 'Marin Thomas', 'Harlequin American', 'nominee'),
    ], [
      (
        entry['position'],
        entry['title'],
        entry['author'],
        entry['category'],
        entry['result'],
      )
      for entry in nominee_parsed['entries']
    ])
    self.assertEqual(nominee_url, nominee_parsed['entries'][0]['source_url'])
    with self.assertRaises(ValueError):
      RomanticTimesReviewersChoiceParser().parse(
        '<h1>2015 RT Reviewers Choice Award Nominees — Fantasy Novel</h1>'
        '<div class="field-name-body"><div class="field-item">'
        '<p><strong>Fantasy Novel</strong></p><p>Uprooted by Naomi Novik</p>'
        '</div></div>',
        nominee_url)

  def test_romantic_times_awards_fetcher_uses_wayback_and_registry_order(self):
    from parser.base import CATEGORY_REGIONAL_NATIONAL_AWARDS, CATEGORY_ROMANCE
    from parser.romantic_times_awards import RT_CDX_DISCOVERY_URLS
    from url_fetcher import available_url_fetchers
    from url_fetcher.romantic_times_awards import (
      UrlFetcherRomanticTimesReviewersChoiceRomance,
    )

    fetcher = UrlFetcherRomanticTimesReviewersChoiceRomance()
    filters = [item['label'] for item in fetcher.get_filter_list()]
    snapshot_url = (
      'https://web.archive.org/web/20160105213619id_/'
      'http://www.rtbookreviews.com/blog/86296/2015-rt-reviewers-choice-award-nominees-series-romance')
    cdx_json = json.dumps([
      ['timestamp', 'original', 'statuscode', 'mimetype', 'digest'],
      [
        '20160105213619',
        'http://www.rtbookreviews.com/blog/86296/2015-rt-reviewers-choice-award-nominees-series-romance',
        '200',
        'text/html',
        'abc',
      ],
    ])
    article_html = '''
      <article>
        <h1 class="title">2015 RT Reviewers' Choice Award Nominees — Series Romance</h1>
        <div class="field field-name-body">
          <div class="field-item even">
            <p><strong>Kimani Romance</strong></p>
            <table><tr><td><img alt="Sherelle Green, Beautiful Surrender" /></td></tr></table>
          </div>
        </div>
      </article>
    '''
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if 'librarything.com' in url.lower():
        self.fail('LibraryThing should not be fetched for Romantic Times')
      if url == fetcher.URL:
        return cdx_json
      if url in RT_CDX_DISCOVERY_URLS:
        return '[]'
      if url == snapshot_url:
        return article_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual('romantic_times_reviewers_choice_romance', fetcher.source_id)
    self.assertEqual(
      "Romantic Times Reviewers' Choice Awards - Romance Categories",
      fetcher.NAME)
    self.assertEqual(250, fetcher.order)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())
    self.assertIn(CATEGORY_ROMANCE, filters)
    self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
    self.assertEqual(['Beautiful Surrender'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(snapshot_url, parsed['entries'][0]['source_url'])
    self.assertFalse(parsed['match_series'])
    self.assertFalse(any('librarything.com' in url.lower() for url in fetched))

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertIn('romantic_times_reviewers_choice_romance', registry_ids)
    self.assertLess(
      registry_ids.index('ripped_bodice_awards'),
      registry_ids.index('romantic_times_reviewers_choice_romance'))
    self.assertLess(
      registry_ids.index('romantic_times_reviewers_choice_romance'),
      registry_ids.index('writers_trust_atwood_gibson_fiction'))
    self.assertEqual(365, len(registry_ids))

  def test_lambda_literary_awards_parser_reads_directory_and_current_shortlists(self):
    from parser.lambda_literary_awards import (
      LAMBDA_CURRENT_FINALISTS_URL,
      LAMBDA_CURRENT_WINNERS_URL,
      LambdaLiteraryAwardsRomanceParser,
    )

    directory_json = json.dumps({
      'records': [{
        'fields': {
          'Year': 2024,
          'Category': 'Gay Romance',
          'Title': 'A Novel Love',
          'Author': 'Casey Author',
          'Status': 'Winner',
        },
      }, {
        'fields': {
          'Year': 2024,
          'Category': 'Lesbian Romance',
          'Title': 'Last Call at the Moonlight',
          'Author': 'Riley Writer',
          'Status': 'Finalist',
        },
      }, {
        'fields': {
          'Year': 2024,
          'Category': 'Gay Erotica',
          'Title': 'Not Imported',
          'Author': 'Erotica Author',
          'Status': 'Winner',
        },
      }],
    })
    finalist_html = '''
      <main>
        <h1>2026 Lammy Award finalist titles</h1>
        <h2>LGBTQ+ Romance and Erotica</h2>
        <ul>
          <li><a href="/books/shore">A Shore Thing</a> // Joanna Lowell. Publisher</li>
          <li>Under the Same Stars // Anita Kelly. Publisher</li>
        </ul>
        <h2>LGBTQ+ Erotica</h2>
        <ul><li>Not a Romance Row // Other Writer. Publisher</li></ul>
      </main>
    '''
    winner_html = '''
      <html>
        <head><title>2025 Lambda Literary Award Winners</title></head>
        <body>
          <main>
            <h2>LGBTQ+ Romance and Erotica</h2>
            <h2><a href="/books/shore">A Shore Thing</a></h2>
            <h4>Joanna Lowell</h4>
            <h2>LGBTQ+ Erotica</h2>
            <h2>Not a Romance Row</h2>
            <h4>Other Writer</h4>
          </main>
        </body>
      </html>
    '''

    parsed = LambdaLiteraryAwardsRomanceParser().parse(
      directory_json,
      current_pages=(
        (LAMBDA_CURRENT_FINALISTS_URL, finalist_html),
        (LAMBDA_CURRENT_WINNERS_URL, winner_html),
      ))

    self.assertEqual('Lambda Literary Awards - Romance Categories', parsed['name'])
    self.assertFalse(parsed['match_series'])
    self.assertEqual([
      ('2024', 'A Novel Love', 'Casey Author', 'Gay Romance', 'winner'),
      ('2024.01', 'Last Call at the Moonlight', 'Riley Writer',
       'Lesbian Romance', 'shortlisted'),
      ('2025', 'A Shore Thing', 'Joanna Lowell', 'LGBTQ+ Romance and Erotica',
       'winner'),
      ('2025.01', 'Under the Same Stars', 'Anita Kelly',
       'LGBTQ+ Romance and Erotica', 'shortlisted'),
    ], [
      (
        entry['position'],
        entry['title'],
        entry['author'],
        entry['category'],
        entry['result'],
      )
      for entry in parsed['entries']
    ])
    self.assertNotIn('Not Imported', [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertNotIn('Not a Romance Row', [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(
      'https://lambdaliterary.org/books/shore',
      parsed['entries'][2]['source_url'])

  def test_lambda_literary_awards_fetcher_metadata_parse_and_registry(self):
    from parser.base import (
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
      CATEGORY_ROMANCE,
    )
    from parser.lambda_literary_awards import (
      LAMBDA_CURRENT_FINALISTS_URL,
      LAMBDA_CURRENT_WINNERS_URL,
    )
    from url_fetcher import available_url_fetchers
    from url_fetcher.lambda_literary_awards import UrlFetcherLambdaLiteraryAwardsRomance

    fetcher = UrlFetcherLambdaLiteraryAwardsRomance()
    filters = [item['label'] for item in fetcher.get_filter_list()]
    directory_html = '''
      <iframe src="https://airtable.com/embed/appu8PIf1Vu0s7g1E/shrMKDUyEN6S80ndL"></iframe>
    '''
    finalist_html = '''
      <main>
        <h1>2026 Lammy Award finalist titles</h1>
        <h2>Lesbian Romance</h2>
        <p>The First Bright Thing // J. R. Dawson. Tor Books</p>
      </main>
    '''
    winner_html = '''
      <main>
        <h2>Lesbian Romance</h2>
        <h2>The First Bright Thing</h2>
        <h4>J. R. Dawson</h4>
      </main>
    '''
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if url == fetcher.URL:
        return directory_html
      if url == LAMBDA_CURRENT_FINALISTS_URL:
        return finalist_html
      if url == LAMBDA_CURRENT_WINNERS_URL:
        return winner_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual('lambda_literary_awards_romance', fetcher.source_id)
    self.assertEqual('Lambda Literary Awards - Romance Categories', fetcher.NAME)
    self.assertEqual(251, fetcher.order)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())
    self.assertIn(CATEGORY_ROMANCE, filters)
    self.assertIn(CATEGORY_LITERARY_GENERAL_FICTION, filters)
    self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
    self.assertEqual([
      (fetcher.URL),
      (LAMBDA_CURRENT_FINALISTS_URL),
      (LAMBDA_CURRENT_WINNERS_URL),
    ], fetched)
    self.assertEqual([
      ('2025', 'The First Bright Thing', 'winner'),
    ], [
      (entry['position'], entry['title'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertIn('Airtable data', parsed['notes'][0])
    self.assertFalse(parsed['match_series'])

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertIn('lambda_literary_awards_romance', registry_ids)
    self.assertLess(
      registry_ids.index('romantic_times_reviewers_choice_romance'),
      registry_ids.index('lambda_literary_awards_romance'))
    self.assertLess(
      registry_ids.index('lambda_literary_awards_romance'),
      registry_ids.index('romance_writers_australia_ruby_awards'))

  def test_romance_writers_australia_ruby_parser_reads_shopify_finalists(self):
    from parser.romance_writers_australia import RomanceWritersAustraliaRubyParser

    source_json = json.dumps({
      'resources': {'results': {'articles': [{
        'title': 'Ruby Finalists Announced!',
        'handle': 'ruby-finalists-announced',
        'published_at': '2020-07-17T04:00:00.000Z',
        'tags': ['Ruby', 'Contests'],
        'url': '/blogs/blog/ruby-finalists-announced',
        'body': '''
          <h3>And the finalists are...</h3>
          <h4>Romantic Suspense</h4>
          <p><strong>Leah Ashton</strong> - Out Run the Night (previously 'Defiant')</p>
          <p><strong>Claire Boston</strong> - Nothing to Lose</p>
          <h4>Contemporary</h4>
          <p><strong>Amy Andrews</strong> - Nothing But Trouble</p>
        ''',
      }]}}
    })

    parsed = RomanceWritersAustraliaRubyParser().parse(
      source_json,
      'https://romanceaustralia.com/search/suggest.json?q=RUBY')

    self.assertEqual('Romance Writers of Australia RUBY Awards', parsed['name'])
    self.assertFalse(parsed['match_series'])
    self.assertEqual([
      ('2020.01', 'Out Run the Night', 'Leah Ashton', 'Romantic Suspense', 'shortlisted'),
      ('2020.02', 'Nothing to Lose', 'Claire Boston', 'Romantic Suspense', 'shortlisted'),
      ('2020.03', 'Nothing But Trouble', 'Amy Andrews', 'Contemporary', 'shortlisted'),
    ], [
      (
        entry['position'],
        entry['title'],
        entry['author'],
        entry['category'],
        entry['result'],
      )
      for entry in parsed['entries']
    ])
    self.assertIn('Official migrated RWAus finalist/nominee posts', parsed['notes'][0])

  def test_romance_writers_australia_ruby_parser_reads_2023_dash_rows(self):
    from parser.romance_writers_australia import RomanceWritersAustraliaRubyParser

    source_json = json.dumps({
      'resources': {'results': {'articles': [{
        'title': 'Romantic Book of the Year 2023',
        'handle': 'romantic-book-of-the-year-2023',
        'published_at': '2023-07-11T04:00:00.000Z',
        'tags': ['Category_RWA News'],
        'url': '/blogs/blog/romantic-book-of-the-year-2023',
        'body': '''
          <p>Please put your hands together for the Romance Writers of Australia
          Romantic Book of the Year finalists for 2023!</p>
          <h3>And the finalists are...</h3>
          <h4>Contemporary – LONG</h4>
          <p><strong>Francis Cowie </strong>– Hampton Lane</p>
          <h4>Contemporary – SHORT</h4>
          <p><strong>Amy Andrews </strong>– Nurse's Outback Temptation</p>
        ''',
      }]}}
    })

    parsed = RomanceWritersAustraliaRubyParser().parse(source_json)

    self.assertEqual([
      ('2023.01', 'Hampton Lane', 'Francis Cowie', 'Contemporary - LONG'),
      ('2023.02', "Nurse's Outback Temptation", 'Amy Andrews', 'Contemporary - SHORT'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['category'])
      for entry in parsed['entries']
    ])

  def test_romance_writers_australia_ruby_parser_normalizes_nominees(self):
    from parser.romance_writers_australia import RomanceWritersAustraliaRubyParser

    source_json = json.dumps({
      'resources': {'results': {'articles': [{
        'title': 'Shout Out to the Ruby Nominees!',
        'handle': 'shout-out-to-the-ruby-nominees',
        'published_at': '2022-08-07T04:00:00.000Z',
        'tags': ['Ruby'],
        'url': '/blogs/blog/shout-out-to-the-ruby-nominees',
        'body': '''
          <p>Please put your hands together for the Romance Writers of Australia
          Romantic Book of the Year finalists for 2022!</p>
          <h4>Romantic Elements</h4>
          <p><strong>Lee Christine</strong> - Crackenback</p>
        ''',
      }]}}
    })

    parsed = RomanceWritersAustraliaRubyParser().parse(source_json)

    self.assertEqual([
      ('2022.01', 'Crackenback', 'Lee Christine', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])

  def test_romance_writers_australia_ruby_parser_fetches_archived_winners(self):
    from parser.romance_writers_australia import (
      RWAUS_RUBY_CDX_URL,
      RomanceWritersAustraliaRubyParser,
    )

    cdx_json = json.dumps([
      ['timestamp', 'original', 'statuscode', 'mimetype', 'digest'],
      [
        '20181107042249',
        'http://romanceaustralia.com:80/awards/romantic-book-of-the-year-ruby-2/',
        '200',
        'text/html',
        'abc',
      ],
    ])
    snapshot_url = (
      'https://web.archive.org/web/20181107042249id_/'
      'http://romanceaustralia.com:80/awards/romantic-book-of-the-year-ruby-2/')
    archive_html = '''
      <table>
        <tr><th>Year</th><th>Category</th><th>Title</th><th>Author</th></tr>
        <tr><td>2014</td><td>Short Category</td><td>Her Favourite Rival</td><td>Sarah Mayberry</td></tr>
        <tr><td>2020</td><td>Romantic Suspense</td><td>Out Run the Night</td><td>Leah Ashton</td></tr>
      </table>
    '''
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if url == RWAUS_RUBY_CDX_URL:
        return cdx_json
      if url == snapshot_url:
        return archive_html
      self.fail(url)

    parsed = RomanceWritersAustraliaRubyParser().parse('{}', fetch_url=fetch_url)

    self.assertEqual([RWAUS_RUBY_CDX_URL, snapshot_url], fetched)
    self.assertEqual([
      ('2014', 'Her Favourite Rival', 'Sarah Mayberry', 'Short Category', 'winner'),
      ('2020', 'Out Run the Night', 'Leah Ashton', 'Romantic Suspense', 'winner'),
    ], [
      (
        entry['position'],
        entry['title'],
        entry['author'],
        entry['category'],
        entry['result'],
      )
      for entry in parsed['entries']
    ])

  def test_romance_writers_australia_ruby_parser_promotes_explicit_winner(self):
    from parser.romance_writers_australia import RomanceWritersAustraliaRubyParser

    source_json = json.dumps({
      'resources': {'results': {'articles': [{
        'title': 'Ruby Finalists Announced!',
        'handle': 'ruby-finalists-announced',
        'published_at': '2020-07-17T04:00:00.000Z',
        'tags': ['Ruby'],
        'url': '/blogs/blog/ruby-finalists-announced',
        'body': '''
          <h4>Romantic Suspense</h4>
          <p><strong>Leah Ashton</strong> - Out Run the Night</p>
          <p><strong>Claire Boston</strong> - Shelter</p>
        ''',
      }]}}
    })
    archive_html = '''
      <table>
        <tr><th>Year</th><th>Category</th><th>Title</th><th>Author</th></tr>
        <tr><td>2020</td><td>Romantic Suspense</td><td>Out Run the Night</td><td>Leah Ashton</td></tr>
      </table>
    '''

    parsed = RomanceWritersAustraliaRubyParser().parse(
      source_json,
      archived_pages=(('https://web.archive.org/web/2020id_/ruby', archive_html),))

    self.assertEqual([
      ('2020', 'Out Run the Night', 'winner'),
      ('2020.01', 'Shelter', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['result'])
      for entry in parsed['entries']
    ])

  def test_romance_writers_australia_ruby_fetcher_metadata_and_registry(self):
    from parser.base import CATEGORY_REGIONAL_NATIONAL_AWARDS, CATEGORY_ROMANCE
    from parser.romance_writers_australia import RWAUS_RUBY_CDX_URL
    from url_fetcher import available_url_fetchers
    from url_fetcher.romance_writers_australia import (
      UrlFetcherRomanceWritersAustraliaRubyAwards,
    )

    fetcher = UrlFetcherRomanceWritersAustraliaRubyAwards()
    filters = [item['label'] for item in fetcher.get_filter_list()]
    cdx_json = json.dumps([
      ['timestamp', 'original', 'statuscode', 'mimetype', 'digest'],
      ['20181107042249', 'http://romanceaustralia.com/ruby', '200', 'text/html', 'abc'],
    ])
    snapshot_url = 'https://web.archive.org/web/20181107042249id_/http://romanceaustralia.com/ruby'
    search_json = json.dumps({
      'resources': {'results': {'articles': [{
        'title': 'Ruby Finalists Announced!',
        'handle': 'ruby-finalists-announced',
        'published_at': '2021-07-01T04:00:00.000Z',
        'tags': ['Ruby'],
        'url': '/blogs/blog/ruby-finalists-announced-2',
        'body': '<h4>Historical</h4><p><strong>Amy Rose Bennett</strong> - How to Catch a Sinful Marquess</p>',
      }]}}
    })
    archive_html = '''
      <table>
        <tr><th>Year</th><th>Category</th><th>Title</th><th>Author</th></tr>
        <tr><td>2014</td><td>Short Category</td><td>Her Favourite Rival</td><td>Sarah Mayberry</td></tr>
      </table>
    '''

    def fetch_url(url):
      if url == fetcher.URL:
        return search_json
      if url == RWAUS_RUBY_CDX_URL:
        return cdx_json
      if url == snapshot_url:
        return archive_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual('romance_writers_australia_ruby_awards', fetcher.source_id)
    self.assertEqual('Romance Writers of Australia RUBY Awards', fetcher.NAME)
    self.assertEqual(252, fetcher.order)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())
    self.assertIn(CATEGORY_ROMANCE, filters)
    self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
    self.assertEqual([
      ('2014', 'Her Favourite Rival', 'winner'),
      ('2021.01', 'How to Catch a Sinful Marquess', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertFalse(parsed['match_series'])

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertIn('romance_writers_australia_ruby_awards', registry_ids)
    self.assertLess(
      registry_ids.index('lambda_literary_awards_romance'),
      registry_ids.index('romance_writers_australia_ruby_awards'))
    self.assertLess(
      registry_ids.index('romance_writers_australia_ruby_awards'),
      registry_ids.index('writers_trust_atwood_gibson_fiction'))

  def test_australian_romance_readers_parser_reads_2025_official_lists(self):
    from parser.australian_romance_readers import AustralianRomanceReadersAwardsParser

    page_html = '''
      <p>The winners for the 2025 awards were announced. They are highlighted
      below in pink bold, with runners-up in pink.</p>
      <table><tr><td>
        <p><span style="color: #000000;"><strong>Favourite Paranormal Romance 2025</strong></span></p>
        <ul>
          <li><strong><span style="color: #ff00ff;"><em>Atonement Sky</em> by Nalini Singh</span></strong></li>
          <li><em>Because the Night</em> by Kylie Scott</li>
          <li><span style="color: #ff00ff;"><em>Poison Ivy</em> by Shannon Curtis</span></li>
        </ul>
        <p><span style="color: #000000;"><strong>Favourite Continuing Romance Series 2025</strong></span></p>
        <ul><li><strong><span style="color: #ff00ff;">Hope Creek series by Alyssa J Montgomery</span></strong></li></ul>
      </td><td>
        <p><strong><span style="color: #000000;">Favourite Australian-set romance 2025</span></strong></p>
        <ul>
          <li><em>An Academic Affair</em> by Jodi McAlister</li>
          <li><span style="color: #ff00ff;"><strong><em>In the Long Run</em> by Emma Mugglestone</strong></span></li>
        </ul>
        <p><strong><span style="color: #000000;">Favourite romance couple 2025</span></strong></p>
        <ul><li><strong><span style="color: #ff00ff;"><em>Sharing Forever in Hope Creek</em> by Alyssa J Montgomery (Callie and Jack)</span></strong></li></ul>
      </td></tr></table>
    '''

    parsed = AustralianRomanceReadersAwardsParser().parse(
      '',
      year_pages=(('https://australianromancereaders.com.au/awards/2025-2/', page_html),))

    self.assertEqual('Australian Romance Readers Awards', parsed['name'])
    self.assertFalse(parsed['match_series'])
    self.assertEqual([
      ('2025', 'Atonement Sky', 'Nalini Singh', 'Favourite Paranormal Romance', 'winner'),
      ('2025.01', 'In the Long Run', 'Emma Mugglestone', 'Favourite Australian-set romance', 'winner'),
      ('2025.02', 'Because the Night', 'Kylie Scott', 'Favourite Paranormal Romance', 'shortlisted'),
      ('2025.03', 'Poison Ivy', 'Shannon Curtis', 'Favourite Paranormal Romance', 'shortlisted'),
      ('2025.04', 'An Academic Affair', 'Jodi McAlister', 'Favourite Australian-set romance', 'shortlisted'),
    ], [
      (
        entry['position'],
        entry['title'],
        entry['author'],
        entry['category'],
        entry['result'],
      )
      for entry in parsed['entries']
    ])
    self.assertIn('Official ARRA nominee/shortlist-style category lists', parsed['notes'][0])
    self.assertIn('reference-only', parsed['notes'][-1])

  def test_australian_romance_readers_parser_reads_legacy_br_rows(self):
    from parser.australian_romance_readers import AustralianRomanceReadersAwardsParser

    page_html = '''
      <h2><span style="color: #666699;"><strong>2015 award winners</strong></span></h2>
      <p><span style="color: #666699;"><strong>Favourite Sci Fi, Fantasy or Futuristic Romance</strong></span><br/>
      1916-ish by Ebony McKenna<br/>
      <span style="color: #ff00ff;"><strong>Base by Cathleen Ross</strong></span><br/>
      Chaos Broken by Rebekah Turner</p>
      <p><span style="color: #666699;"><strong>Favourite New Romance Author for 2015</strong></span><br/>
      Abbie Jackson<br/>
      <span style="color: #ff00ff;"><strong>Kerrie Paterson</strong></span></p>
      <p><span style="color: #666699;"><strong>Favourite Cover from a romance published in 2015</strong></span><br/>
      Northern Heat by Helene Young (Penguin)<br/>
      <strong><span style="color: #ff00ff;">The Horse Thief by Tea Cooper (Escape)</span></strong></p>
    '''

    parsed = AustralianRomanceReadersAwardsParser().parse(
      '',
      year_pages=(('https://australianromancereaders.com.au/awards/2015-2/', page_html),))

    self.assertEqual([
      ('2015', 'Base', 'Cathleen Ross', 'Favourite Sci Fi, Fantasy or Futuristic Romance', 'winner'),
      ('2015.01', 'The Horse Thief', 'Tea Cooper', 'Favourite Cover from a romance published in 2015', 'winner'),
      ('2015.02', '1916-ish', 'Ebony McKenna', 'Favourite Sci Fi, Fantasy or Futuristic Romance', 'shortlisted'),
      ('2015.03', 'Chaos Broken', 'Rebekah Turner', 'Favourite Sci Fi, Fantasy or Futuristic Romance', 'shortlisted'),
      ('2015.04', 'Northern Heat', 'Helene Young', 'Favourite Cover from a romance published in 2015', 'shortlisted'),
    ], [
      (
        entry['position'],
        entry['title'],
        entry['author'],
        entry['category'],
        entry['result'],
      )
      for entry in parsed['entries']
    ])

  def test_australian_romance_readers_parser_marks_winner_only_pages(self):
    from parser.australian_romance_readers import AustralianRomanceReadersAwardsParser

    page_html = '''
      <p>Winners for 2008, presented at ARRC09 in February 2009, were:</p>
      <p><span style="color: #666699;"><b>Favourite Paranormal Romance for 2008</b></span></p>
      <ul><li><em>Acheron</em> by Sherrilyn Kenyon</li></ul>
      <div><span style="color: #666699;"><b>Favourite Category/Series Romance for 2008</b></span></div>
      <ul><li><em>The Marciano Love-Child</em> by Melanie Milburne</li></ul>
      <div><span style="color: #666699;"><b>Favourite Australian Romance Author for 2008</b></span></div>
      <ul><li>Stephanie Laurens</li></ul>
    '''

    parsed = AustralianRomanceReadersAwardsParser().parse(
      '',
      year_pages=(('https://australianromancereaders.com.au/awards/2008-2/', page_html),))

    self.assertEqual([
      ('2008', 'Acheron', 'Sherrilyn Kenyon', 'Favourite Paranormal Romance', 'winner'),
      ('2008.01', 'The Marciano Love-Child', 'Melanie Milburne', 'Favourite Category/Series Romance', 'winner'),
    ], [
      (
        entry['position'],
        entry['title'],
        entry['author'],
        entry['category'],
        entry['result'],
      )
      for entry in parsed['entries']
    ])
    self.assertIn('winner-only pages were parsed for: 2008', parsed['notes'][0])

  def test_australian_romance_readers_fetcher_metadata_and_registry(self):
    from parser.base import CATEGORY_REGIONAL_NATIONAL_AWARDS, CATEGORY_ROMANCE
    from parser.australian_romance_readers import ARRA_REST_PAGE_URL
    from url_fetcher import available_url_fetchers
    from url_fetcher.australian_romance_readers import (
      UrlFetcherAustralianRomanceReadersAwards,
    )

    fetcher = UrlFetcherAustralianRomanceReadersAwards()
    index_html = '<a href="https://australianromancereaders.com.au/awards/2025-2/">2025</a>'
    page_html = '''
      <p><strong>Favourite Historical Romance 2025</strong></p>
      <ul>
        <li><strong><span style="color: #ff00ff;"><em>The Nanny's Handbook</em> by Amy Rose Bennett</span></strong></li>
        <li><em>Sir Hugo Seeks a Wife</em> by Anna Campbell</li>
      </ul>
    '''
    rest_json = json.dumps([{
      'link': 'https://australianromancereaders.com.au/awards/2025-2/',
      'content': {'rendered': page_html},
    }])
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if url == fetcher.URL:
        return index_html
      if url == ARRA_REST_PAGE_URL.format(slug='2025-2'):
        return rest_json
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)
    filters = [item['label'] for item in fetcher.get_filter_list()]

    self.assertEqual('australian_romance_readers_awards', fetcher.source_id)
    self.assertEqual('Australian Romance Readers Awards', fetcher.NAME)
    self.assertEqual(253, fetcher.order)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())
    self.assertIn(CATEGORY_ROMANCE, filters)
    self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
    self.assertEqual([
      fetcher.URL,
      ARRA_REST_PAGE_URL.format(slug='2025-2'),
    ], fetched)
    self.assertEqual([
      ('2025', "The Nanny's Handbook", 'Amy Rose Bennett', 'winner'),
      ('2025.01', 'Sir Hugo Seeks a Wife', 'Anna Campbell', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertIn('australian_romance_readers_awards', registry_ids)
    self.assertLess(
      registry_ids.index('romance_writers_australia_ruby_awards'),
      registry_ids.index('australian_romance_readers_awards'))
    self.assertLess(
      registry_ids.index('australian_romance_readers_awards'),
      registry_ids.index('writers_trust_atwood_gibson_fiction'))

  def test_holt_medallion_parser_reads_modern_finalist_lists(self):
    from parser.holt_medallion import HOLTMedallionParser

    page_html = '''
      <h3><strong>Congratulations to all of the finalists!</strong></h3>
      <p>Winners will be announced in June.</p>
      <h4>Short Contemporary</h4>
      <ul>
        <li><em><strong>No Excuses</strong></em> &#8211; Andrea Jenelle</li>
        <li><em><strong>The Maverick's Christmas Countdown</strong></em> &#8211; Heatherly Bell</li>
      </ul>
      <h4>Best Book By a Virginia Author</h4>
      <ul>
        <li><strong><em>A Great and Terrible Darkness</em></strong> -Linda J. White</li>
      </ul>
    '''

    parsed = HOLTMedallionParser().parse(
      '',
      pages=(('https://virginiaromancewriters.com/2025-holt-medallion-finalists/', page_html),))

    self.assertEqual('HOLT Medallion', parsed['name'])
    self.assertFalse(parsed['match_series'])
    self.assertEqual([
      ('2025.01', 'No Excuses', 'Andrea Jenelle', 'Short Contemporary', 'shortlisted'),
      (
        '2025.02',
        "The Maverick's Christmas Countdown",
        'Heatherly Bell',
        'Short Contemporary',
        'shortlisted',
      ),
      (
        '2025.03',
        'A Great and Terrible Darkness',
        'Linda J. White',
        'Best Book By a Virginia Author',
        'shortlisted',
      ),
    ], [
      (
        entry['position'],
        entry['title'],
        entry['author'],
        entry['category'],
        entry['result'],
      )
      for entry in parsed['entries']
    ])
    self.assertIn('finalist/shortlist-style rows were parsed for: 2025', parsed['notes'][0])
    self.assertIn('reference-only', parsed['notes'][-1])

  def test_holt_medallion_parser_reads_legacy_heading_and_table_shapes(self):
    from parser.holt_medallion import HOLTMedallionParser

    heading_html = '''
      <h1>CONGRATULATIONS 2018 FINALISTS</h1>
      <h2><strong><em>Best First Book</em></strong></h2>
      <h5><em>Under Her Skin</em> &#8211; Adriana Anders*</h5>
      <h5><em>Snapdragon</em> &#8211; Kilby Blades</h5>
    '''
    table_html = '''
      <h1>CONGRATULATIONS FINALISTS!</h1>
      <table>
        <tr><td><h5><strong>Short Contemporary</strong></h5></td><td><h5><strong>Author</strong></h5></td></tr>
        <tr><td><strong>T</strong>hree Day Fiancee</td><td>Marissa Clarke</td></tr>
        <tr><td>The Marine's Secret Daughter</td><td>Carrie Nichols</td></tr>
      </table>
    '''

    parsed = HOLTMedallionParser().parse('', pages=(
      ('https://virginiaromancewriters.com/holt-medallion/2018-holt-medallion-finalists-wi/', heading_html),
      ('https://virginiaromancewriters.com/holt-medallion/2019-holt-medallion-for-excellence-in-writing/', table_html),
    ))

    self.assertEqual([
      ('2018.01', 'Under Her Skin', 'Adriana Anders', 'Best First Book'),
      ('2018.02', 'Snapdragon', 'Kilby Blades', 'Best First Book'),
      ('2019.01', 'Three Day Fiancee', 'Marissa Clarke', 'Short Contemporary'),
      ('2019.02', "The Marine's Secret Daughter", 'Carrie Nichols', 'Short Contemporary'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['category'])
      for entry in parsed['entries']
    ])

  def test_holt_medallion_parser_reads_past_winners_and_award_of_merit_finalists(self):
    from parser.holt_medallion import HOLTMedallionParser

    page_html = '''
      <div>
        <strong>2017 HOLT Medallion Winners &amp; Award of Merit Finalists<br></strong>
        <table>
          <tbody>
            <tr><th>Best First Book</th></tr>
            <tr><td><strong>Winner<br><em>Highland Deception&nbsp;</em>&#8211; Lori Ann Bailey</strong><br>
              <strong>Award of Merit Finalists</strong>
              <ul>
                <li><em>To Steal a Heart &#8211;</em>&nbsp;K. C. Bateman</li>
                <li><em>A Family for the Farmer &#8211;&nbsp;</em>Laurel Blount</li>
              </ul>
            </td></tr>
          </tbody>
        </table>
        <hr>
        <h4 id="2016">2016 Winners and Award of Merit Finalists</h4>
        <strong>Short Contemporary<br>Winner<br></strong>
        <em>Three Nights Before Christmas &#8211;&nbsp;</em>Kat Latham
        <p><strong>Award of Merit Finalists</strong></p>
        <ul>
          <li><em>One Night Before Christmas &#8211; </em>Susan Carlisle</li>
        </ul>
      </div>
    '''

    parsed = HOLTMedallionParser().parse(
      '',
      pages=(('https://virginiaromancewriters.com/holt-medallion/holt-medallion-past-winners/', page_html),))

    self.assertEqual([
      ('2016', 'Three Nights Before Christmas', 'Kat Latham', 'Short Contemporary', 'winner'),
      ('2016.01', 'One Night Before Christmas', 'Susan Carlisle', 'Short Contemporary', 'shortlisted'),
      ('2017', 'Highland Deception', 'Lori Ann Bailey', 'Best First Book', 'winner'),
      ('2017.01', 'To Steal a Heart', 'K. C. Bateman', 'Best First Book', 'shortlisted'),
      ('2017.02', 'A Family for the Farmer', 'Laurel Blount', 'Best First Book', 'shortlisted'),
    ], [
      (
        entry['position'],
        entry['title'],
        entry['author'],
        entry['category'],
        entry['result'],
      )
      for entry in parsed['entries']
    ])
    self.assertIn('winner rows were parsed for: 2016, 2017', parsed['notes'][1])

  def test_holt_medallion_parser_reads_awards_pages_and_notes_video_only_winners(self):
    from parser.holt_medallion import HOLTMedallionParser

    search_json = json.dumps([
      {
        'title': '2025 HOLT Medallion Awards',
        'url': 'https://virginiaromancewriters.com/2025-holt-medallion-awards/',
        '_links': {'self': [{'href': 'https://virginiaromancewriters.com/wp-json/wp/v2/pages/2809'}]},
      },
      {
        'title': '2026 HOLT Medallion Awards',
        'url': 'https://virginiaromancewriters.com/2026-holt-medallion-awards/',
        '_links': {'self': [{'href': 'https://virginiaromancewriters.com/wp-json/wp/v2/pages/2937'}]},
      },
    ])
    winner_html = '''
      <h3>Romantic Suspense</h3>
      <figure><img src="cover.jpg" /></figure>
      <p><strong><em>Hunting Justice</em></strong> by Sami A. Abrams</p>
    '''
    video_html = '''
      <div><video><source src="https://example.com/HOLT-Video-2026.mp4" /></video></div>
    '''
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if url.endswith('search?search=HOLT&per_page=100'):
        return search_json
      if url.endswith('/pages/2809'):
        return json.dumps({
          'link': 'https://virginiaromancewriters.com/2025-holt-medallion-awards/',
          'title': {'rendered': '2025 HOLT Medallion Awards'},
          'content': {'rendered': winner_html},
        })
      if url.endswith('/pages/2937'):
        return json.dumps({
          'link': 'https://virginiaromancewriters.com/2026-holt-medallion-awards/',
          'title': {'rendered': '2026 HOLT Medallion Awards'},
          'content': {'rendered': video_html},
        })
      self.fail(url)

    parsed = HOLTMedallionParser().parse(
      '<a href="https://virginiaromancewriters.com/2025-holt-medallion-awards/">Awards</a>',
      fetch_url=fetch_url)

    self.assertEqual([
      'https://virginiaromancewriters.com/wp-json/wp/v2/search?search=HOLT&per_page=100',
      'https://virginiaromancewriters.com/wp-json/wp/v2/pages/2809',
      'https://virginiaromancewriters.com/wp-json/wp/v2/pages/2937',
    ], fetched)
    self.assertEqual([
      ('2025', 'Hunting Justice', 'Sami A. Abrams', 'Romantic Suspense', 'winner'),
    ], [
      (
        entry['position'],
        entry['title'],
        entry['author'],
        entry['category'],
        entry['result'],
      )
      for entry in parsed['entries']
    ])
    self.assertTrue(any('2026 awards page did not expose text winner rows' in note
                        for note in parsed['notes']))

  def test_holt_medallion_fetcher_metadata_and_registry(self):
    from parser.base import CATEGORY_REGIONAL_NATIONAL_AWARDS, CATEGORY_ROMANCE
    from parser.holt_medallion import HOLT_SEARCH_URL
    from url_fetcher import available_url_fetchers
    from url_fetcher.holt_medallion import UrlFetcherHOLTMedallion

    fetcher = UrlFetcherHOLTMedallion()
    landing_html = '''
      <a href="https://virginiaromancewriters.com/2025-holt-medallion-finalists/">
        2025 HOLT Medallion Finalists
      </a>
      <a href="https://virginiaromancewriters.com/holt-medallion/holt-payment/">Payment</a>
    '''
    search_json = json.dumps([{
      'title': '2025 HOLT Medallion Finalists',
      'url': 'https://virginiaromancewriters.com/2025-holt-medallion-finalists/',
      '_links': {'self': [{'href': 'https://virginiaromancewriters.com/wp-json/wp/v2/pages/2793'}]},
    }])
    finalist_html = '''
      <h4>Historical</h4>
      <ul><li><em><strong>Snowbound with the Scoundrel</strong></em> &#8211; Courtney McCaskill</li></ul>
    '''
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if url == fetcher.URL:
        return landing_html
      if url == HOLT_SEARCH_URL:
        return search_json
      if url.endswith('/pages/2793'):
        return json.dumps({
          'link': 'https://virginiaromancewriters.com/2025-holt-medallion-finalists/',
          'title': {'rendered': '2025 HOLT Medallion Finalists'},
          'content': {'rendered': finalist_html},
        })
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)
    filters = [item['label'] for item in fetcher.get_filter_list()]

    self.assertEqual('holt_medallion', fetcher.source_id)
    self.assertEqual('HOLT Medallion', fetcher.NAME)
    self.assertEqual(254, fetcher.order)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())
    self.assertIn(CATEGORY_ROMANCE, filters)
    self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
    self.assertEqual([
      fetcher.URL,
      HOLT_SEARCH_URL,
      'https://virginiaromancewriters.com/wp-json/wp/v2/pages/2793',
    ], fetched)
    self.assertEqual([
      ('2025.01', 'Snowbound with the Scoundrel', 'Courtney McCaskill', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertFalse(parsed['match_series'])

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertIn('holt_medallion', registry_ids)
    self.assertLess(
      registry_ids.index('australian_romance_readers_awards'),
      registry_ids.index('holt_medallion'))
    self.assertLess(
      registry_ids.index('holt_medallion'),
      registry_ids.index('writers_trust_atwood_gibson_fiction'))

  def test_booksellers_best_parser_reads_2012_archived_finalist_page(self):
    from parser.booksellers_best import BooksellersBestAwardParser

    page_html = '''
      <html><head><title>2012 Booksellers' Best Award</title></head><body>
      <h3>2012 Booksellers' Best Award</h3>
      <h1>FINALISTS</h1>
      <p>The Greater Detroit RWA is pleased to announce the finalists.</p>
      <h4>SINGLE TITLE</h4>
      <p class="newsdate">Whisper Falls - Toni Blake<br/>
        The Strangers on Montagu Street - Karen White</p>
      <h4>ROMANTIC SUSPENSE</h4>
      <p class="newsdate">Riptide - Cherry Adair<br/>
        If You Hear Her - Shiloh Walker</p>
      <h4>BEST FIRST BOOK</h4>
      <p class="newsdate">Forever Freed - Laura Kaye<br/>
        Beach Rental - Grace Greene</p>
      </body></html>
    '''

    parsed = BooksellersBestAwardParser().parse(
      '',
      pages=((
        'https://web.archive.org/web/20120627055544id_/http://www.gdrwa.org/contests.html',
        page_html,
      ),))

    self.assertEqual("Booksellers' Best Award", parsed['name'])
    self.assertFalse(parsed['match_series'])
    self.assertEqual([
      ('2012.01', 'Whisper Falls', 'Toni Blake', 'Single Title', 'shortlisted'),
      (
        '2012.02',
        'The Strangers on Montagu Street',
        'Karen White',
        'Single Title',
        'shortlisted',
      ),
      ('2012.03', 'Riptide', 'Cherry Adair', 'Romantic Suspense', 'shortlisted'),
      ('2012.04', 'If You Hear Her', 'Shiloh Walker', 'Romantic Suspense', 'shortlisted'),
      ('2012.05', 'Forever Freed', 'Laura Kaye', 'Best First Book', 'shortlisted'),
      ('2012.06', 'Beach Rental', 'Grace Greene', 'Best First Book', 'shortlisted'),
    ], [
      (
        entry['position'],
        entry['title'],
        entry['author'],
        entry['category'],
        entry['result'],
      )
      for entry in parsed['entries']
    ])
    self.assertIn('finalist/shortlist-style rows were parsed for: 2012', parsed['notes'][0])
    self.assertIn('reference-only', parsed['notes'][-1])

  def test_booksellers_best_parser_reads_2004_legacy_finalist_paragraphs(self):
    from parser.booksellers_best import BooksellersBestAwardParser

    page_html = '''
      <html><head><title>Bookseller's Best Award Finalists</title></head><body>
      <h2>A Published Authors' Contest for Books Published in 2003</h2>
      <p><font color="#FF0000" size="+3">Finalists</font></p>
      <p align="center"><font color="#FF0000" size="5"><i><strong>Traditional</strong></i></font><br/>
        <strong>THE ITALIAN MILLIONAIRES MARRIAGE</strong> - <em>LUCY GORDON</em><br/>
        <strong>THE VIRGIN'S PROPOSAL</strong> - <em>SHIRLEY JUMP</em></p>
      <p align="center"><font color="#FF0000" size="5"><i><strong>Paranormal/TT/Futuristic</strong></i></font><br/>
        <strong>DANCE WITH THE DEVIL</strong> - <em>SHERRILYN KENYON</em></p>
      </body></html>
    '''

    parsed = BooksellersBestAwardParser().parse(
      '',
      pages=((
        'https://web.archive.org/web/20041021163620id_/http://www.gdrwa.org/bbafinals04.html',
        page_html,
      ),))

    self.assertEqual([
      ('2004.01', 'THE ITALIAN MILLIONAIRES MARRIAGE', 'LUCY GORDON', 'Traditional'),
      ('2004.02', "THE VIRGIN'S PROPOSAL", 'SHIRLEY JUMP', 'Traditional'),
      (
        '2004.03',
        'DANCE WITH THE DEVIL',
        'SHERRILYN KENYON',
        'Paranormal/Time Travel/Futuristic',
      ),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['category'])
      for entry in parsed['entries']
    ])

  def test_booksellers_best_parser_reads_archived_winner_pages(self):
    from parser.booksellers_best import BooksellersBestAwardParser

    page_2016 = '''
      <html><head><title>2016 BOOKSELLERS' BEST AWARD</title></head><body>
      <h1>2016 BOOKSELLERS' BEST AWARD</h1>
      <p><img alt="Latest News" src="images/title_winners.gif" /></p>
      <h4>HISTORICAL ROMANCE</h4>
      <p class="newsdate"><em>At His Command</em>-Historical Romance Version, Ruth Kaufman and
        <em>A Pirate's Command</em>, Meg Hennessy</p>
      <h4>SINGLE TITLE</h4>
      <p class="newsdate"><em>Ransom Canyon</em>, Jodi Thomas</p>
      <h4>THE PATTI SHENBERGER AWARD FOR BEST BOOK</h4>
      <p class="newsdate"><em>At His Command</em>-Historical Romance Version, Ruth Kaufman</p>
      </body></html>
    '''
    page_2017 = '''
      <html><head><title>2017 BOOKSELLERS' BEST AWARD</title></head><body>
      <h1>2017 BOOKSELLERS' BEST AWARD</h1>
      <h4>EROTIC ROMANCE</h4>
      <p class="newsdate"><em>Breaking His Rules</em> by R.C. Matthews</p>
      <h4>PARNORMAL ROMANCE</h4>
      <p class="newsdate"><em>Viking Warrior Rebel</em> by Asa Maria Bradley</p>
      <h4>ROMANIC SUSPENSE</h4>
      <p><span class="newsdate"><em>Finding Lyla</em> by Cate Beauman</span></p>
      </body></html>
    '''

    parsed = BooksellersBestAwardParser().parse('', pages=(
      (
        'https://web.archive.org/web/20170607135748id_/http://www.gdrwa.org/winners2016.html',
        page_2016,
      ),
      (
        'https://web.archive.org/web/20171211023748id_/http://www.gdrwa.org/winners2017.html',
        page_2017,
      ),
    ))

    self.assertEqual([
      ('2016', 'At His Command', 'Ruth Kaufman', 'Historical Romance', 'winner'),
      ('2016.01', "A Pirate's Command", 'Meg Hennessy', 'Historical Romance', 'winner'),
      ('2016.02', 'Ransom Canyon', 'Jodi Thomas', 'Single Title', 'winner'),
      (
        '2016.03',
        'At His Command',
        'Ruth Kaufman',
        'The Patti Shenberger Award for Best Book',
        'winner',
      ),
      ('2017', 'Breaking His Rules', 'R.C. Matthews', 'Erotic Romance', 'winner'),
      ('2017.01', 'Viking Warrior Rebel', 'Asa Maria Bradley', 'Paranormal Romance', 'winner'),
      ('2017.02', 'Finding Lyla', 'Cate Beauman', 'Romantic Suspense', 'winner'),
    ], [
      (
        entry['position'],
        entry['title'],
        entry['author'],
        entry['category'],
        entry['result'],
      )
      for entry in parsed['entries']
    ])
    self.assertIn('winner-only years were parsed for: 2016, 2017', parsed['notes'][1])

  def test_booksellers_best_parser_skips_entry_rules_and_non_book_content(self):
    from parser.booksellers_best import BooksellersBestAwardParser

    page_html = '''
      <html><head><title>2018 BOOKSELLERS' BEST AWARD</title></head><body>
      <h1>2018 BOOKSELLERS' BEST AWARD</h1>
      <p>A Published Authors' Contest for Books Published in 2017</p>
      <h2>TO ENTER THE 2018 BOOKSELLERS' BEST AWARD:</h2>
      <p><strong>SHORT CONTEMPORARY ROMANCE</strong> category description.</p>
      <h2>2018 BBA Category Coordinators:</h2>
      <p><em>Short Contemporary Romance Coordinator</em><br/>Coordinator Name</p>
      <p>The Greater Detroit RWA is pleased to announce the winners of the
      2011 Between the Sheets Contest.</p>
      <p>1st Place - <em>Breeders</em> by Lisa Nicole Fenley</p>
      </body></html>
    '''

    parsed = BooksellersBestAwardParser().parse(
      '',
      pages=((
        'https://web.archive.org/web/20171009105938id_/http://www.gdrwa.org/contests.html',
        page_html,
      ),))

    self.assertEqual([], parsed['entries'])
    self.assertTrue(any('entry/rules text' in note for note in parsed['notes']))
    self.assertIn('No Booksellers', parsed['notes'][-2])

  def test_booksellers_best_fetcher_metadata_delegation_and_registry(self):
    from parser.base import CATEGORY_REGIONAL_NATIONAL_AWARDS, CATEGORY_ROMANCE
    from parser.booksellers_best import BOOKSELLERS_BEST_CDX_URLS
    from url_fetcher import available_url_fetchers
    from url_fetcher.booksellers_best import UrlFetcherBooksellersBestAward

    fetcher = UrlFetcherBooksellersBestAward()
    snapshot_url = 'https://web.archive.org/web/20120627055544id_/http://www.gdrwa.org/contests.html'
    cdx_json = json.dumps([
      ['timestamp', 'original', 'statuscode', 'mimetype', 'digest'],
      ['20120627055544', 'http://www.gdrwa.org/contests.html', '200', 'text/html', 'abc'],
    ])
    empty_cdx_json = json.dumps([
      ['timestamp', 'original', 'statuscode', 'mimetype', 'digest'],
    ])
    page_html = '''
      <html><head><title>2012 Booksellers' Best Award</title></head><body>
      <h3>2012 Booksellers' Best Award</h3>
      <h1>FINALISTS</h1>
      <h4>TRADITIONAL</h4>
      <p>How A Cowboy Stole Her Heart - Donna Alward</p>
      </body></html>
    '''
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if url == fetcher.URL:
        return cdx_json
      if url in BOOKSELLERS_BEST_CDX_URLS[1:]:
        return empty_cdx_json
      if url == snapshot_url:
        return page_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)
    filters = [item['label'] for item in fetcher.get_filter_list()]

    self.assertEqual('booksellers_best_award', fetcher.source_id)
    self.assertEqual("Booksellers' Best Award", fetcher.NAME)
    self.assertEqual(255, fetcher.order)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())
    self.assertEqual(
      'https://web.archive.org/web/*/http://www.gdrwa.org/contests.html',
      fetcher.display_url)
    self.assertIn(CATEGORY_ROMANCE, filters)
    self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
    self.assertEqual([
      fetcher.URL,
      BOOKSELLERS_BEST_CDX_URLS[1],
      BOOKSELLERS_BEST_CDX_URLS[2],
      snapshot_url,
    ], fetched)
    self.assertEqual([
      ('2012.01', 'How A Cowboy Stole Her Heart', 'Donna Alward', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertFalse(parsed['match_series'])

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertIn('booksellers_best_award', registry_ids)
    self.assertLess(
      registry_ids.index('holt_medallion'),
      registry_ids.index('booksellers_best_award'))
    self.assertLess(
      registry_ids.index('booksellers_best_award'),
      registry_ids.index('writers_trust_atwood_gibson_fiction'))

  def test_miles_franklin_wikipedia_parser_reads_winner_tables(self):
    from parser.miles_franklin import MilesFranklinWikipediaParser

    html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Publisher</th><th>Ref</th></tr>
        <tr><td>1973</td><td colspan="4">Award withheld after the judges decided that none of the novels entered was good enough</td></tr>
        <tr><td>1987</td><td>Glenda Adams</td><td>Dancing on Coral</td><td>Viking Press</td><td>[1]</td></tr>
      </table>
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Publisher</th><th>Ref</th></tr>
        <tr><td>1989</td><td>Peter Carey</td><td>Oscar and Lucinda</td><td>University of Queensland Press</td><td>[2]</td></tr>
      </table>
    '''

    parsed = MilesFranklinWikipediaParser().parse(
      html, 'https://en.wikipedia.org/wiki/Miles_Franklin_Award')

    self.assertEqual(['Dancing on Coral', 'Oscar and Lucinda'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['1987', '1989'], [
      entry['position'] for entry in parsed['entries']
    ])
    self.assertNotIn('1988', [entry['award_year'] for entry in parsed['entries']])

  def test_miles_franklin_wikipedia_parser_preserves_tied_winner_positions(self):
    from parser.miles_franklin import MilesFranklinWikipediaParser

    html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Publisher</th><th>Ref</th></tr>
        <tr><td rowspan="2">2000</td><td>Thea Astley</td><td>Drylands</td><td>Penguin Books</td><td>[1]</td></tr>
        <tr><td>Kim Scott</td><td>Benang</td><td>Fremantle Press</td><td>[1]</td></tr>
      </table>
    '''

    parsed = MilesFranklinWikipediaParser().parse(
      html, 'https://en.wikipedia.org/wiki/Miles_Franklin_Award')

    self.assertEqual(['Drylands', 'Benang'], [
      entry['title'] for entry in parsed['entries']
    ])
    self.assertEqual(['2000', '2000'], [
      entry['position'] for entry in parsed['entries']
    ])

  def test_miles_franklin_wikipedia_parser_dedupes_winner_from_shortlist(self):
    from parser.miles_franklin import MilesFranklinWikipediaParser

    html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Publisher</th><th>Ref</th></tr>
        <tr><td>2025</td><td>Siang Lu</td><td>Ghost Cities</td><td>University of Queensland Press</td><td>[1]</td></tr>
      </table>
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr><td rowspan="4">2025</td><td>Siang Lu</td><td>Ghost Cities</td><td>Winner</td></tr>
        <tr><td>Jason Chong</td><td>Chinese Postman</td><td rowspan="3">Shortlist</td></tr>
        <tr><td>Michelle de Kretser</td><td>Theory &amp; Practice</td></tr>
        <tr><td>Sam Elkin</td><td>Detachable Penis</td></tr>
      </table>
    '''

    parsed = MilesFranklinWikipediaParser().parse(
      html, 'https://en.wikipedia.org/wiki/Miles_Franklin_Award')

    self.assertEqual([
      ('2025', 'Ghost Cities', 'winner'),
      ('2025.01', 'Chinese Postman', 'shortlisted'),
      ('2025.02', 'Theory & Practice', 'shortlisted'),
      ('2025.03', 'Detachable Penis', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['result'])
      for entry in parsed['entries']
    ])

  def test_miles_franklin_wikipedia_parser_accepts_current_shortlist_only(self):
    from parser.miles_franklin import MilesFranklinWikipediaParser

    html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr><td rowspan="3">2026</td><td>Steve MinOn</td><td>First Name Second Name</td><td rowspan="3">Shortlist</td></tr>
        <tr><td>Omar Musa</td><td>Fierceland</td></tr>
        <tr><td>Josephine Rowe</td><td>Little World</td></tr>
      </table>
    '''

    parsed = MilesFranklinWikipediaParser().parse(
      html, 'https://en.wikipedia.org/wiki/Miles_Franklin_Award')

    self.assertEqual(['2026.01', '2026.02', '2026.03'], [
      entry['position'] for entry in parsed['entries']
    ])
    self.assertTrue(all(
      entry['result'] == 'shortlisted' for entry in parsed['entries']))

  def test_miles_franklin_wikipedia_parser_ignores_longlisted_rows(self):
    from parser.miles_franklin import MilesFranklinWikipediaParser

    html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr><td>2024</td><td>Alexis Wright</td><td>Praiseworthy</td><td>Winner</td></tr>
        <tr><td>2024</td><td>Long Listed</td><td>Long Book</td><td>Longlist</td></tr>
      </table>
      <h2>Longlisted works</h2>
      <ul><li>Another Long Book, Another Author</li></ul>
    '''

    parsed = MilesFranklinWikipediaParser().parse(
      html, 'https://en.wikipedia.org/wiki/Miles_Franklin_Award')

    self.assertEqual(['Praiseworthy'], [
      entry['title'] for entry in parsed['entries']
    ])

  def test_miles_franklin_fetcher_metadata_and_parse_smoke(self):
    from parser.base import (
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
    )
    from url_fetcher.miles_franklin import UrlFetcherMilesFranklinLiteraryAward

    fetcher = UrlFetcherMilesFranklinLiteraryAward()
    html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Publisher</th><th>Ref</th></tr>
        <tr><td>2025</td><td>Siang Lu</td><td>Ghost Cities</td><td>University of Queensland Press</td><td>[1]</td></tr>
      </table>
    '''

    parsed = fetcher.fetch_and_parse(lambda url: html)
    filters = [item['label'] for item in fetcher.get_filter_list()]

    self.assertEqual('Miles Franklin Literary Award', parsed['name'])
    self.assertEqual(['Ghost Cities'], [entry['title'] for entry in parsed['entries']])
    self.assertFalse(parsed['match_series'])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())
    self.assertIn(CATEGORY_LITERARY_GENERAL_FICTION, filters)
    self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)

  def test_stella_official_parser_reads_winners_shortlists_and_skips_longlists(self):
    from parser.stella import StellaOfficialParser

    html = '''
      <article class="prize-card">
        <p>The 2024 Stella Prize Winner</p>
        <h3 class="book-title"><a href="/books/praiseworthy">Praiseworthy</a></h3>
        <p class="book-author">Alexis Wright</p>
        <p>Fiction</p>
      </article>
      <article class="prize-card">
        <p>The 2024 Stella Prize Shortlist</p>
        <h3 class="book-title">Hospital</h3>
        <p class="book-author">Sanya Rushdi</p>
        <p>Non-Fiction</p>
      </article>
      <article class="prize-card">
        <p>The 2024 Stella Prize Longlist</p>
        <h3 class="book-title">Long Book</h3>
        <p class="book-author">Long Author</p>
      </article>
    '''

    parsed = StellaOfficialParser().parse(
      html, 'https://stella.org.au/past-prize-winners/')

    self.assertEqual([
      ('2024', 'Praiseworthy', 'Alexis Wright', 'winner'),
      ('2024.01', 'Hospital', 'Sanya Rushdi', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertTrue(all(entry['award'] == 'Stella Prize' for entry in parsed['entries']))
    self.assertTrue(all(entry['category'] == 'All genres' for entry in parsed['entries']))

  def test_stella_official_parser_rejects_advertised_partial_card_stream(self):
    from parser.stella import StellaOfficialParser

    html = '''
      <p>1 Winner</p>
      <p>2 Shortlisted</p>
      <article>
        <p>The 2025 Stella Prize Winner</p>
        <h3 class="book-title">Stone Yard Devotional</h3>
        <p class="book-author">Charlotte Wood</p>
      </article>
      <article>
        <p>The 2025 Stella Prize Shortlist</p>
        <h3 class="book-title">Theory &amp; Practice</h3>
        <p class="book-author">Michelle de Kretser</p>
      </article>
    '''

    with self.assertRaises(ValueError) as caught:
      StellaOfficialParser().parse(html)

    self.assertIn('official archive appears incomplete', str(caught.exception))
    self.assertIn('shortlisted: expected 2, parsed 1', str(caught.exception))

  def test_stella_wikipedia_parser_handles_rowspans_and_skips_longlists(self):
    from parser.stella import StellaWikipediaParser

    html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr>
          <td rowspan="5">2024</td>
          <td>Alexis Wright</td>
          <td><i><a href="/wiki/Praiseworthy">Praiseworthy</a></i></td>
          <td>Winner</td>
        </tr>
        <tr>
          <td>Sanya Rushdi</td>
          <td>Hospital</td>
          <td rowspan="2">Shortlist</td>
        </tr>
        <tr>
          <td>Shankari Chandran</td>
          <td>Chai Time at Cinnamon Gardens</td>
        </tr>
        <tr>
          <td>Long Author</td>
          <td>Long Book</td>
          <td rowspan="2">Longlist</td>
        </tr>
        <tr>
          <td>Another Long Author</td>
          <td>Another Long Book</td>
        </tr>
      </table>
    '''

    parsed = StellaWikipediaParser().parse(
      html, 'https://en.wikipedia.org/wiki/Stella_Prize')

    self.assertEqual([
      ('2024', 'Praiseworthy', 'winner'),
      ('2024.01', 'Hospital', 'shortlisted'),
      ('2024.02', 'Chai Time at Cinnamon Gardens', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertNotIn('Long Book', [entry['title'] for entry in parsed['entries']])

  def test_stella_fetcher_metadata_and_fallback(self):
    from parser.base import (
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_NONFICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
    )
    from url_fetcher.stella import UrlFetcherStellaPrize

    fetcher = UrlFetcherStellaPrize()
    official_html = '<html><p>1 Winner</p><p>1 Shortlisted</p></html>'
    wiki_html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr><td>2024</td><td>Alexis Wright</td><td>Praiseworthy</td><td>Winner</td></tr>
      </table>
    '''
    calls = []

    def fetch_url(url):
      calls.append(url)
      if url == fetcher.URL:
        return official_html
      if url == fetcher.WIKIPEDIA_URL:
        return wiki_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)
    filters = [item['label'] for item in fetcher.get_filter_list()]

    self.assertEqual('Stella Prize', fetcher.NAME)
    self.assertEqual('stella_prize', fetcher.source_id)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual((
      {'label': 'Automatic', 'value': 'automatic'},
      {'label': 'Stella', 'value': 0},
      {'label': 'Wikipedia', 'value': 1},
    ), fetcher.source_choices())
    self.assertIn(CATEGORY_LITERARY_GENERAL_FICTION, filters)
    self.assertIn(CATEGORY_NONFICTION, filters)
    self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
    self.assertEqual(['Praiseworthy'], [entry['title'] for entry in parsed['entries']])
    self.assertEqual([fetcher.URL, fetcher.WIKIPEDIA_URL], calls)
    self.assertFalse(parsed['match_series'])
    with self.assertRaises(Exception):
      fetcher.fetch_and_parse(fetch_url, disable_fallbacks=True)

  def test_prime_ministers_literary_awards_official_discovers_archive_pages(self):
    from parser.prime_ministers_literary_awards import (
      PrimeMinistersLiteraryAwardsOfficialParser,
    )

    index_html = '''
      <html><head><title>Prime Minister's Literary Awards 2025</title></head>
      <body>
        <h2>Fiction</h2>
        <p class="card-portrait--content-title">WINNER: Theory &amp; Practice by Michelle de Kretser</p>
        <p class="card-portrait--content-title">Translations by Jumaana Abdu</p>
        <h3>Previous shortlist &amp; recipients: 2008 to 2024</h3>
        <h3>2024</h3>
        <a href="/2024-pmla-winners-shortlist-and-judges">Find the 2024 winners, shortlistees and judges here</a>
      </body></html>
    '''
    year_html = '''
      <h2>Fiction</h2>
      <p class="card-portrait--content-title">WINNER: 'Anam', André Dao</p>
      <h3>Anam</h3>
      <p><strong>André Dao</strong></p>
      <p><strong>Shortlist year:</strong> 2024</p>
      <p><strong>Shortlist category:</strong> Fiction</p>
      <h3>Restless Dolly Maunder</h3>
      <p><strong>Kate Grenville</strong></p>
      <p><strong>Shortlist year:</strong> 2024</p>
      <p><strong>Shortlist category:</strong> Fiction</p>
    '''
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      return year_html

    parsed = PrimeMinistersLiteraryAwardsOfficialParser(
      'Fiction', ('Fiction',)).parse(
        index_html,
        'https://creative.gov.au/news-events/events/prime-ministers-literary-awards',
        fetch_url=fetch_url)

    self.assertEqual([
      'https://creative.gov.au/2024-pmla-winners-shortlist-and-judges',
    ], fetched)
    self.assertEqual([
      ('2024', 'Anam', 'winner'),
      ('2024.01', 'Restless Dolly Maunder', 'shortlisted'),
      ('2025', 'Theory & Practice', 'winner'),
      ('2025.01', 'Translations', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['result'])
      for entry in parsed['entries']
    ])

  def test_prime_ministers_literary_awards_official_category_start_years(self):
    from parser.prime_ministers_literary_awards import (
      PrimeMinistersLiteraryAwardsOfficialParser,
    )

    html = '''
      <html><head><title>2008 PMLA winners, shortlist and judges</title></head>
      <body>
        <h2>Non-fiction</h2>
        <p class="card-portrait--content-title">WINNER: Ochre and Rust: Artefacts and Encounters on Australian Frontiers – Philip Jones</p>
        <h2>Fiction</h2>
        <p class="card-portrait--content-title">WINNER: The Zoo Keeper's War – Steven Conte</p>
      </body></html>
    '''

    nonfiction = PrimeMinistersLiteraryAwardsOfficialParser(
      'Non-fiction', ('Non-fiction', 'Nonfiction')).parse(html)
    young_adult = PrimeMinistersLiteraryAwardsOfficialParser(
      'Young Adult Literature',
      ('Young Adult Literature', 'Young adult fiction')).parse(html)

    self.assertEqual(['Ochre and Rust: Artefacts and Encounters on Australian Frontiers'], [
      entry['title'] for entry in nonfiction['entries']
    ])
    self.assertEqual([], young_adult['entries'])

  def test_prime_ministers_literary_awards_official_handles_core_categories(self):
    from parser.prime_ministers_literary_awards import (
      PrimeMinistersLiteraryAwardsOfficialParser,
    )

    html = '''
      <html><head><title>2024 PMLA winners, shortlist and judges</title></head>
      <body>
        <h2>Children's literature</h2>
        <p class="card-portrait--content-title">WINNER: Tamarra: A Story of Termites on Gurindji Country by Violet Wadrill</p>
        <h2>Young adult literature</h2>
        <p class="card-portrait--content-title">WINNER: We Could Be Something by Will Kostakis</p>
        <h2>Australian history</h2>
        <p class="card-portrait--content-title">WINNER: Donald Horne: A Life in the Lucky Country by Ryan Cropp</p>
        <p class="card-portrait--content-title">Bee Miles by Rose Ellis</p>
        <h2>Poetry</h2>
        <p class="card-portrait--content-title">WINNER: The Cyprian by Amy Crutchfield</p>
      </body></html>
    '''

    history = PrimeMinistersLiteraryAwardsOfficialParser(
      'Australian History', ('Australian History',)).parse(html)
    children = PrimeMinistersLiteraryAwardsOfficialParser(
      "Children's Literature",
      ("Children's Literature", "Children's literature")).parse(html)
    young_adult = PrimeMinistersLiteraryAwardsOfficialParser(
      'Young Adult Literature',
      ('Young Adult Literature', 'Young adult literature')).parse(html)

    self.assertEqual([
      ('Donald Horne: A Life in the Lucky Country', 'winner'),
      ('Bee Miles', 'shortlisted'),
    ], [(entry['title'], entry['result']) for entry in history['entries']])
    self.assertEqual(['Tamarra: A Story of Termites on Gurindji Country'], [
      entry['title'] for entry in children['entries']
    ])
    self.assertEqual(['We Could Be Something'], [
      entry['title'] for entry in young_adult['entries']
    ])
    self.assertNotIn('The Cyprian', [
      entry['title'] for entry in history['entries'] + children['entries'] + young_adult['entries']
    ])

  def test_prime_ministers_literary_awards_official_preserves_tied_winners(self):
    from parser.prime_ministers_literary_awards import (
      PrimeMinistersLiteraryAwardsOfficialParser,
    )

    html = '''
      <html><head><title>2016 PMLA winners, shortlist and judges</title></head>
      <body><h2>Fiction</h2>
      <p class="card-portrait--content-title">WINNER: The Natural Way of Things – Charlotte Wood</p>
      <p class="card-portrait--content-title">WINNER: The Life of Houses – Lisa Gorton</p>
      <p class="card-portrait--content-title">Forever Young – Steven Carroll</p>
      <h3>The Natural Way of Things</h3>
      <p>WINNER</p>
      <p><strong>Shortlist year:</strong> 2016</p>
      <p><strong>Shortlist category:</strong> Fiction</p>
      <h3>The Life of Houses</h3>
      <p>WINNER</p>
      <p><strong>Shortlist year:</strong> 2016</p>
      <p><strong>Shortlist category:</strong> Fiction</p>
      <h3>Forever Young</h3>
      <p>Steven Carroll</p>
      <p><strong>Shortlist year:</strong> 2016</p>
      <p><strong>Shortlist category:</strong> Fiction</p>
      </body></html>
    '''

    parsed = PrimeMinistersLiteraryAwardsOfficialParser(
      'Fiction', ('Fiction',)).parse(html)

    self.assertEqual(['2016', '2016', '2016.01'], [
      entry['position'] for entry in parsed['entries']
    ])

  def test_prime_ministers_literary_awards_wikipedia_parser(self):
    from parser.prime_ministers_literary_awards import (
      PrimeMinistersLiteraryAwardsWikipediaParser,
    )

    html = '''
      <h3>Fiction</h3>
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr><td rowspan="3">2024</td><td>André Dao</td><td>Anam</td><td>Winner</td></tr>
        <tr><td>Kate Grenville</td><td>Restless Dolly Maunder</td><td rowspan="2">Finalist</td></tr>
        <tr><td>Charlotte Wood</td><td>Stone Yard Devotional</td></tr>
      </table>
      <h3>Poetry</h3>
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr><td>2024</td><td>Amy Crutchfield</td><td>The Cyprian</td><td>Winner</td></tr>
      </table>
    '''

    parsed = PrimeMinistersLiteraryAwardsWikipediaParser(
      'Fiction', ('Fiction',)).parse(html)

    self.assertEqual([
      ('2024', 'Anam', 'winner'),
      ('2024.01', 'Restless Dolly Maunder', 'shortlisted'),
      ('2024.02', 'Stone Yard Devotional', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertNotIn('The Cyprian', [entry['title'] for entry in parsed['entries']])

  def test_prime_ministers_literary_awards_fetchers_metadata_and_fallback(self):
    from parser.base import (
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_NONFICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
      CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    )
    from url_fetcher.prime_ministers_literary_awards import (
      UrlFetcherPrimeMinistersLiteraryAwardsAustralianHistory,
      UrlFetcherPrimeMinistersLiteraryAwardsChildrensLiterature,
      UrlFetcherPrimeMinistersLiteraryAwardsFiction,
      UrlFetcherPrimeMinistersLiteraryAwardsNonfiction,
      UrlFetcherPrimeMinistersLiteraryAwardsYoungAdultLiterature,
    )

    fetchers = (
      (UrlFetcherPrimeMinistersLiteraryAwardsFiction(), CATEGORY_LITERARY_GENERAL_FICTION),
      (UrlFetcherPrimeMinistersLiteraryAwardsNonfiction(), CATEGORY_NONFICTION),
      (UrlFetcherPrimeMinistersLiteraryAwardsAustralianHistory(), CATEGORY_NONFICTION),
      (
        UrlFetcherPrimeMinistersLiteraryAwardsYoungAdultLiterature(),
        CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
      ),
      (
        UrlFetcherPrimeMinistersLiteraryAwardsChildrensLiterature(),
        CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
      ),
    )

    for fetcher, expected_filter in fetchers:
      with self.subTest(fetcher=fetcher.source_id):
        filters = [item['label'] for item in fetcher.get_filter_list()]
        self.assertIn(expected_filter, filters)
        self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
        self.assertFalse(fetcher.options['match_series'])
        self.assertEqual((
          {'label': 'Automatic', 'value': 'automatic'},
          {'label': 'Creative Australia', 'value': 0},
          {'label': 'Wikipedia', 'value': 1},
        ), fetcher.source_choices())

    fetcher = UrlFetcherPrimeMinistersLiteraryAwardsFiction()
    official_html = '<html><title>Prime Minister Literary Awards 2024</title><h2>Poetry</h2></html>'
    wiki_html = '''
      <h3>Fiction</h3>
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr><td>2024</td><td>André Dao</td><td>Anam</td><td>Winner</td></tr>
      </table>
    '''
    calls = []

    def fetch_url(url):
      calls.append(url)
      if url == fetcher.URL:
        return official_html
      if url == fetcher.WIKIPEDIA_URL:
        return wiki_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual(['Anam'], [entry['title'] for entry in parsed['entries']])
    self.assertEqual([fetcher.URL, fetcher.WIKIPEDIA_URL], calls)
    self.assertFalse(parsed['match_series'])
    with self.assertRaises(Exception):
      fetcher.fetch_and_parse(fetch_url, disable_fallbacks=True)

  def test_victorian_premiers_literary_awards_discovers_archive_pages(self):
    from parser.victorian_premiers_literary_awards import (
      VictorianPremiersLiteraryAwardsOfficialParser,
    )

    html = '''
      <a href="/victorian-premier-s-literary-awards/past-awards/2025-victorian-premier-s-literary-awards">
        2025 Victorian Premier's Literary Awards
      </a>
      <a href="/victorian-premier-s-literary-awards/2026-victorian-premier-s-literary-awards">
        2026 Victorian Premier's Literary Awards
      </a>
      <a href="/victorian-premier-s-literary-awards/past-awards/2010-victorian-premier-s-literary-awards">
        2010 Victorian Premier's Literary Awards
      </a>
      <a href="/victorian-premier-s-literary-awards/about-the-awards">About the Awards</a>
    '''

    links = VictorianPremiersLiteraryAwardsOfficialParser(
      'Fiction',
      ('Prize for Fiction', 'Fiction')).archive_links(
        html,
        'https://www.wheelercentre.com/victorian-premier-s-literary-awards/past-awards')

    self.assertEqual((
      'https://www.wheelercentre.com/victorian-premier-s-literary-awards/past-awards/2025-victorian-premier-s-literary-awards',
      'https://www.wheelercentre.com/victorian-premier-s-literary-awards/2026-victorian-premier-s-literary-awards',
    ), links)

  def test_victorian_premiers_literary_awards_reads_winners_shortlists_and_skips_other_sections(self):
    from parser.victorian_premiers_literary_awards import (
      VictorianPremiersLiteraryAwardsOfficialParser,
    )

    html = '''
      <html><head><title>2025 Victorian Premier's Literary Awards</title></head>
      <body><main>
        <h2>WINNERS</h2>
        <h3>Victorian Prize for Literature</h3>
        <article><h4>Overall Winner</h4><p>Overall Author</p></article>
        <h3>Prize for Fiction</h3>
        <article>
          <h4><a href="/books/orbital">Orbital</a></h4>
          <p>Samantha Harvey</p>
          <p>Vintage</p>
          <a href="/books/orbital">Learn More</a>
        </article>
        <h3>Prize for Poetry</h3>
        <article><h4>The Cyprian</h4><p>Amy Crutchfield</p></article>
        <h2>HIGHLY COMMENDED</h2>
        <h3>Prize for Fiction</h3>
        <article><h4>Highly Regarded</h4><p>Hidden Author</p></article>
        <h2>SHORTLIST</h2>
        <h3>Prize for Fiction</h3>
        <article><h4>Restless Dolly Maunder</h4><p>Kate Grenville</p></article>
        <article><h4>Stone Yard Devotional by Charlotte Wood</h4></article>
        <h3>Prize for an Unpublished Manuscript</h3>
        <article><h4>Draft Work</h4><p>Emerging Writer</p></article>
        <h3>Prize for Drama</h3>
        <article><h4>Stage Work</h4><p>Playwright</p></article>
        <h3>Prize for Humour Writing</h3>
        <article><h4>Funny Book</h4><p>Comic Writer</p></article>
      </main></body></html>
    '''

    parsed = VictorianPremiersLiteraryAwardsOfficialParser(
      'Fiction',
      ('Prize for Fiction', 'Fiction')).parse(
        html,
        'https://www.wheelercentre.com/victorian-premier-s-literary-awards/past-awards/2025-victorian-premier-s-literary-awards')

    self.assertEqual([
      ('2025', 'Orbital', 'Samantha Harvey', 'winner'),
      ('2025.01', 'Restless Dolly Maunder', 'Kate Grenville', 'shortlisted'),
      ('2025.02', 'Stone Yard Devotional', 'Charlotte Wood', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertTrue(all(
      entry['award'] == "Victorian Premier's Literary Awards"
      for entry in parsed['entries']))
    self.assertTrue(all(entry['category'] == 'Fiction' for entry in parsed['entries']))
    self.assertFalse(parsed['match_series'])
    skipped_titles = {entry['title'] for entry in parsed['entries']}
    self.assertNotIn('Highly Regarded', skipped_titles)
    self.assertNotIn('Overall Winner', skipped_titles)
    self.assertNotIn('Draft Work', skipped_titles)
    self.assertNotIn('Stage Work', skipped_titles)
    self.assertNotIn('Funny Book', skipped_titles)

  def test_victorian_premiers_literary_awards_category_aliases(self):
    from parser.victorian_premiers_literary_awards import (
      VictorianPremiersLiteraryAwardsOfficialParser,
    )

    html = '''
      <html><head><title>2026 Victorian Premier's Literary Awards</title></head>
      <body><main>
        <h2>WINNERS</h2>
        <h3>Prize for Nonfiction</h3>
        <article><h4>Nonfiction Winner</h4><p>Essay Writer</p></article>
        <h3>John Marsden Prize for Writing for Young Adults</h3>
        <article><h4>YA Winner</h4><p>YA Writer</p></article>
        <h3>Prize for Children's Literature</h3>
        <article><h4>Children's Winner</h4><p>Children's Writer</p></article>
        <h3>Prize for Indigenous Writing</h3>
        <article><h4>Indigenous Winner</h4><p>Indigenous Writer</p></article>
      </main></body></html>
    '''

    cases = (
      (
        'Non-fiction',
        ('Prize for Non-fiction', 'Prize for Nonfiction', 'Non-fiction', 'Nonfiction'),
        'Nonfiction Winner',
      ),
      (
        'Writing for Young Adults',
        ('Prize for Writing for Young Adults', 'John Marsden Prize for Writing for Young Adults'),
        'YA Winner',
      ),
      (
        "Children's Literature",
        ("Prize for Children's Literature", "Children's Literature"),
        "Children's Winner",
      ),
      (
        'Indigenous Writing',
        ('Prize for Indigenous Writing', 'Indigenous Writing'),
        'Indigenous Winner',
      ),
    )

    for category, aliases, title in cases:
      with self.subTest(category=category):
        parsed = VictorianPremiersLiteraryAwardsOfficialParser(
          category,
          aliases).parse(html)
        self.assertEqual([title], [entry['title'] for entry in parsed['entries']])
        self.assertEqual(category, parsed['entries'][0]['category'])

  def test_victorian_premiers_literary_awards_fetchers_metadata_and_parse_flow(self):
    from parser.base import (
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_NONFICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
      CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    )
    from url_fetcher.victorian_premiers_literary_awards import (
      UrlFetcherVictorianPremiersLiteraryAwardsChildrensLiterature,
      UrlFetcherVictorianPremiersLiteraryAwardsFiction,
      UrlFetcherVictorianPremiersLiteraryAwardsIndigenousWriting,
      UrlFetcherVictorianPremiersLiteraryAwardsNonfiction,
      UrlFetcherVictorianPremiersLiteraryAwardsWritingForYoungAdults,
    )

    fetchers = (
      (UrlFetcherVictorianPremiersLiteraryAwardsFiction(), CATEGORY_LITERARY_GENERAL_FICTION),
      (UrlFetcherVictorianPremiersLiteraryAwardsNonfiction(), CATEGORY_NONFICTION),
      (
        UrlFetcherVictorianPremiersLiteraryAwardsWritingForYoungAdults(),
        CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
      ),
      (
        UrlFetcherVictorianPremiersLiteraryAwardsChildrensLiterature(),
        CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
      ),
      (UrlFetcherVictorianPremiersLiteraryAwardsIndigenousWriting(), None),
    )

    expected_ids = {
      'victorian_premiers_literary_awards_fiction',
      'victorian_premiers_literary_awards_nonfiction',
      'victorian_premiers_literary_awards_writing_for_young_adults',
      'victorian_premiers_literary_awards_childrens_literature',
      'victorian_premiers_literary_awards_indigenous_writing',
    }
    self.assertEqual(expected_ids, {fetcher.source_id for fetcher, _filter in fetchers})

    for fetcher, expected_filter in fetchers:
      with self.subTest(fetcher=fetcher.source_id):
        filters = [item['label'] for item in fetcher.get_filter_list()]
        if expected_filter is not None:
          self.assertIn(expected_filter, filters)
        self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
        self.assertFalse(fetcher.options['match_series'])
        self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())

    fetcher = UrlFetcherVictorianPremiersLiteraryAwardsFiction()
    year_url = (
      'https://www.wheelercentre.com/victorian-premier-s-literary-awards/'
      'past-awards/2025-victorian-premier-s-literary-awards')
    index_html = f'<a href="{year_url}">2025 Victorian Premier\'s Literary Awards</a>'
    year_html = '''
      <html><head><title>2025 Victorian Premier's Literary Awards</title></head>
      <body><main>
        <h2>WINNERS</h2>
        <h3>Prize for Fiction</h3>
        <article><h4>Orbital</h4><p>Samantha Harvey</p></article>
      </main></body></html>
    '''
    calls = []

    def fetch_url(url):
      calls.append(url)
      if url == fetcher.URL:
        return index_html
      if url == year_url:
        return year_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual(['Orbital'], [entry['title'] for entry in parsed['entries']])
    self.assertEqual([fetcher.URL, year_url], calls)
    self.assertEqual("Victorian Premier's Literary Awards - Fiction", fetcher.NAME)
    self.assertFalse(parsed['match_series'])

  def test_folio_writers_prize_official_archive_and_category_pages(self):
    from parser.folio_writers_prize import FolioWritersPrizeOfficialParser

    root_html = '''
      <main>
        <a href="/2024-prize/">2024</a>
        <a href="/2024-fiction-shortlist/">The Fiction Shortlist</a>
        <a href="/2024-nonfiction-shortlist/">The Non-Fiction Shortlist</a>
        <a href="/2023-prize/">2023 Prize</a>
        <a href="/2016-prize/">2016 Prize</a>
        <a href="/2024-judges/">2024 Judges</a>
        <a href="https://uk.bookshop.org/lists/writers-prize-shortlist-2024">Bookshop list</a>
      </main>
    '''
    fiction_2024 = '''
      <main>
        <h1>The 2024 Fiction Shortlist</h1>
        <h2>CATEGORY WINNER</h2>
        <h2>The Wren, The Wren</h2>
        <h3>Anne Enright</h3>
        <p>Read more</p>
        <h2>The Bee Sting</h2>
        <h3>Paul Murray</h3>
        <h2>The Fraud</h2>
        <h3>Zadie Smith</h3>
      </main>
    '''
    main_2024 = '''
      <main>
        <h2>Fiction</h2>
        <p>CATEGORY WINNER: The Wren, The Wren by Anne Enright</p>
        <h2>Non-Fiction</h2>
        <p>CATEGORY WINNER: Thunderclap by Laura Cumming</p>
        <h2>Poetry</h2>
        <p>CATEGORY WINNER / BOOK OF THE YEAR: The Home Child by Liz Berry</p>
      </main>
    '''
    page_2023 = '''
      <main>
        <h2>Non-Fiction</h2>
        <p>The Passengers by Will Ashon</p>
        <p>Constructing a Nervous System by Margo Jefferson - WINNER, NON-FICTION CATEGORY & BOOK OF THE YEAR</p>
        <h2>Fiction</h2>
        <p>Scary Monsters by Michelle de Kretser - WINNER, FICTION CATEGORY</p>
        <p>Maps of Our Spectacular Bodies by Maddie Mortimer</p>
        <h2>Poetry</h2>
        <p>Quiet by Victoria Adukwei Bulley - WINNER, POETRY CATEGORY</p>
      </main>
    '''
    calls = []

    def fetch_url(url):
      calls.append(url)
      if url == 'https://thewritersprize.com/2024-fiction-shortlist/':
        return fiction_2024
      if url == 'https://thewritersprize.com/2024-prize/':
        return main_2024
      if url == 'https://thewritersprize.com/2023-prize/':
        return page_2023
      self.fail(url)

    parsed = FolioWritersPrizeOfficialParser('Fiction').parse(
      root_html,
      'https://thewritersprize.com/',
      "Folio/Writers' Prize - Fiction",
      fetch_url=fetch_url)

    self.assertEqual([
      ('2023', 'Scary Monsters', 'Michelle de Kretser', 'winner'),
      ('2023.01', 'Maps of Our Spectacular Bodies', 'Maddie Mortimer', 'shortlisted'),
      ('2024', 'The Wren, The Wren', 'Anne Enright', 'winner'),
      ('2024.01', 'The Bee Sting', 'Paul Murray', 'shortlisted'),
      ('2024.02', 'The Fraud', 'Zadie Smith', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertNotIn('Thunderclap', [entry['title'] for entry in parsed['entries']])
    self.assertNotIn('Quiet', [entry['title'] for entry in parsed['entries']])
    self.assertEqual([
      'https://thewritersprize.com/2023-prize/',
      'https://thewritersprize.com/2024-fiction-shortlist/',
      'https://thewritersprize.com/2024-prize/',
    ], calls)
    self.assertFalse(parsed['match_series'])

  def test_folio_writers_prize_book_of_year_includes_overall_poetry_winner(self):
    from parser.folio_writers_prize import FolioWritersPrizeOfficialParser

    root_html = '''
      <main>
        <a href="/2024-prize/">2024</a>
        <a href="/2023-prize/">2023 Prize</a>
        <a href="/12692-2-2/">2014</a>
      </main>
    '''
    page_2024 = '''
      <main>
        <h2>Fiction</h2>
        <p>CATEGORY WINNER: The Wren, The Wren by Anne Enright</p>
        <h2>Poetry</h2>
        <p>CATEGORY WINNER / BOOK OF THE YEAR: The Home Child by Liz Berry</p>
      </main>
    '''
    page_2023 = '''
      <main>
        <h2>Non-Fiction</h2>
        <p>The Passengers by Will Ashon</p>
        <p>Constructing a Nervous System by Margo Jefferson - WINNER, NON-FICTION CATEGORY & BOOK OF THE YEAR</p>
        <h2>Fiction</h2>
        <p>Scary Monsters by Michelle de Kretser - WINNER, FICTION CATEGORY</p>
      </main>
    '''
    page_2014 = '''
      <main>
        <p>The 2014 winner was George Saunders, for Tenth of December.</p>
        <h2>Rathbones Folio Prize 2014 Shortlist</h2>
        <h1>Red Doc</h1><h2>Anne Carson</h2>
        <h1>Tenth of December</h1><h2>George Saunders</h2>
        <h1>How to Get Filthy Rich in Rising Asia</h1><h2>Mohsin Hamid</h2>
      </main>
    '''

    def fetch_url(url):
      if url == 'https://thewritersprize.com/2024-prize/':
        return page_2024
      if url == 'https://thewritersprize.com/2023-prize/':
        return page_2023
      if url == 'https://thewritersprize.com/12692-2-2/':
        return page_2014
      self.fail(url)

    parsed = FolioWritersPrizeOfficialParser('Book of the Year').parse(
      root_html,
      'https://thewritersprize.com/',
      "Folio/Writers' Prize - Book of the Year",
      fetch_url=fetch_url)

    self.assertEqual([
      ('2014', 'Tenth of December', 'George Saunders', 'winner'),
      ('2014.01', 'Red Doc', 'Anne Carson', 'shortlisted'),
      ('2014.02', 'How to Get Filthy Rich in Rising Asia', 'Mohsin Hamid', 'shortlisted'),
      ('2023', 'Constructing a Nervous System', 'Margo Jefferson', 'winner'),
      ('2023.01', 'The Passengers', 'Will Ashon', 'shortlisted'),
      ('2023.02', 'Scary Monsters', 'Michelle de Kretser', 'shortlisted'),
      ('2024', 'The Home Child', 'Liz Berry', 'winner'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertTrue(all(entry['category'] == 'Book of the Year' for entry in parsed['entries']))

  def test_folio_writers_prize_older_shortlist_marker_handling(self):
    from parser.folio_writers_prize import FolioWritersPrizeOfficialParser

    html = '''
      <main>
        <p>The 2022 winner is Colm Toibin, for his novel The Magician.</p>
        <h2>The Rathbones Folio Prize 2022 Longlist</h2>
        <h4>A Little Devil in America - Hanif Abdurraqib (Allen Lane, Non-fiction)</h4>
        <h4>Checkout 19 - Claire-Louise Bennett (Cape, Fiction)</h4>
        <h4>***SHORTLISTED***</h4>
        <h4>The Magician - Colm Toibin (Viking, Fiction)</h4>
        <h4>***SHORTLISTED***</h4>
        <h2>Judges</h2>
        <p>News prose mentions another title by another writer.</p>
      </main>
    '''

    parsed = FolioWritersPrizeOfficialParser('Book of the Year').parse(
      html,
      'https://thewritersprize.com/2022-2/',
      "Folio/Writers' Prize - Book of the Year")

    self.assertEqual([
      ('2022', 'The Magician', 'Colm Toibin', 'winner'),
      ('2022.01', 'Checkout 19', 'Claire-Louise Bennett', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertNotIn('A Little Devil in America', [entry['title'] for entry in parsed['entries']])

  def test_folio_writers_prize_wikipedia_fallback_table(self):
    from parser.folio_writers_prize import FolioWritersPrizeWikipediaParser

    html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr>
          <td rowspan="5">2024</td>
          <td>Liz Berry</td><td>The Home Child (Chatto & Windus)</td>
          <td>Book of the Year winner</td>
        </tr>
        <tr><td>Anne Enright</td><td>The Wren, The Wren</td><td>Fiction winner</td></tr>
        <tr><td>Paul Murray</td><td>The Bee Sting</td><td>Fiction shortlist</td></tr>
        <tr><td>Laura Cumming</td><td>Thunderclap</td><td>Non-Fiction winner</td></tr>
        <tr><td>Poet Name</td><td>Poetry Book</td><td>Poetry winner</td></tr>
        <tr><td>2023</td><td>Margo Jefferson</td><td>Constructing a Nervous System</td><td>Winner</td></tr>
        <tr><td></td><td>Will Ashon</td><td>The Passengers</td><td>Shortlist</td></tr>
        <tr><td></td><td>Another Writer</td><td>Another Shortlisted Book</td><td></td></tr>
      </table>
    '''

    fiction = FolioWritersPrizeWikipediaParser('Fiction').parse(html)
    nonfiction = FolioWritersPrizeWikipediaParser('Non-Fiction').parse(html)
    overall = FolioWritersPrizeWikipediaParser('Book of the Year').parse(html)

    self.assertEqual([
      ('2024', 'The Wren, The Wren', 'Anne Enright', 'winner'),
      ('2024.01', 'The Bee Sting', 'Paul Murray', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in fiction['entries']
    ])
    self.assertEqual(
      [('Thunderclap', 'Laura Cumming')],
      [(entry['title'], entry['author']) for entry in nonfiction['entries']])
    self.assertEqual(
      [('Constructing a Nervous System', 'Margo Jefferson'),
       ('The Passengers', 'Will Ashon'),
       ('Another Shortlisted Book', 'Another Writer'),
       ('The Home Child', 'Liz Berry')],
      [(entry['title'], entry['author']) for entry in overall['entries']])
    self.assertNotIn('Poetry Book', [entry['title'] for entry in fiction['entries']])

  def test_folio_writers_prize_fetchers_metadata_and_fallback(self):
    from parser.base import (
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_NONFICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
    )
    from url_fetcher.folio_writers_prize import (
      UrlFetcherFolioWritersPrizeBookOfTheYear,
      UrlFetcherFolioWritersPrizeFiction,
      UrlFetcherFolioWritersPrizeNonfiction,
    )

    fetchers = (
      (UrlFetcherFolioWritersPrizeBookOfTheYear(), None),
      (UrlFetcherFolioWritersPrizeFiction(), CATEGORY_LITERARY_GENERAL_FICTION),
      (UrlFetcherFolioWritersPrizeNonfiction(), CATEGORY_NONFICTION),
    )
    expected_ids = {
      'folio_writers_prize_book_of_the_year',
      'folio_writers_prize_fiction',
      'folio_writers_prize_nonfiction',
    }
    self.assertEqual(expected_ids, {fetcher.source_id for fetcher, _filter in fetchers})

    for fetcher, expected_filter in fetchers:
      with self.subTest(fetcher=fetcher.source_id):
        filters = [item['label'] for item in fetcher.get_filter_list()]
        if expected_filter is not None:
          self.assertIn(expected_filter, filters)
        self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
        self.assertFalse(fetcher.options['match_series'])
        self.assertEqual((
          {'label': 'Automatic', 'value': 'automatic'},
          {'label': "The Writers' Prize", 'value': 0},
          {'label': 'Wikipedia', 'value': 1},
        ), fetcher.source_choices())

    fetcher = UrlFetcherFolioWritersPrizeFiction()
    wiki_html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr><td>2024</td><td>Anne Enright</td><td>The Wren, The Wren</td><td>Fiction winner</td></tr>
      </table>
    '''
    calls = []

    def fetch_url(url):
      calls.append(url)
      if url == fetcher.URL:
        return '<main><p>2025 key dates only.</p></main>'
      if url == fetcher.WIKIPEDIA_URL:
        return wiki_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual(['The Wren, The Wren'], [entry['title'] for entry in parsed['entries']])
    self.assertEqual([fetcher.URL, fetcher.WIKIPEDIA_URL], calls)
    self.assertFalse(parsed['match_series'])
    with self.assertRaises(Exception):
      fetcher.fetch_and_parse(fetch_url, disable_fallbacks=True)

  def test_nero_book_awards_official_archive_discovery_and_winner_promotion(self):
    from parser.nero_book_awards import NeroBookAwardsOfficialParser

    root_html = '''
      <main>
        <a href="/a-family-matter-claire-lynch/">NERO GOLD PRIZE - 2025</a>
        <a href="/2025-category-winners/">2025 CATEGORY WINNERS</a>
        <a href="/2025-shortlist/">2025 SHORTLIST</a>
        <a href="/2025-category-judges/">2025 CATEGORY JUDGES</a>
        <a href="/new-writers-prize/">NEW WRITERS PRIZE</a>
      </main>
    '''
    shortlist_html = '''
      <main>
        <h3>CHILDREN'S FICTION</h3>
        <p>Dragonborn by Struan Murray</p>
        <h3>FICTION</h3>
        <p><a href="/cursed">Cursed Daughters by Oyinkan Braithwaite</a></p>
        <p><a href="/sea">We Came by Sea by Horatio Clare</a></p>
        <h3>NON-FICTION</h3>
        <p>Craftland by James Fox</p>
      </main>
    '''
    winners_html = '''
      <main>
        <p>We Came by Sea by Horatio Clare</p>
        <p>Craftland by James Fox</p>
        <p>Dragonborn by Struan Murray</p>
      </main>
    '''
    calls = []

    def fetch_url(url):
      calls.append(url)
      if url == 'https://nerobookawards.com/2025-shortlist/':
        return shortlist_html
      if url == 'https://nerobookawards.com/2025-category-winners/':
        return winners_html
      self.fail(url)

    parsed = NeroBookAwardsOfficialParser('Fiction').parse(
      root_html,
      'https://nerobookawards.com/key-dates/',
      'Nero Book Awards - Fiction',
      fetch_url=fetch_url)

    self.assertEqual([
      ('2025', 'We Came by Sea', 'Horatio Clare', 'winner'),
      ('2025.01', 'Cursed Daughters', 'Oyinkan Braithwaite', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertEqual([
      'https://nerobookawards.com/2025-category-winners/',
      'https://nerobookawards.com/2025-shortlist/',
    ], calls)
    self.assertNotIn('Craftland', [entry['title'] for entry in parsed['entries']])
    self.assertFalse(parsed['match_series'])

  def test_nero_book_awards_gold_prize_official_detail_page(self):
    from parser.nero_book_awards import NeroBookAwardsOfficialParser

    root_html = '''
      <main>
        <a href="/a-family-matter-claire-lynch/">NERO GOLD PRIZE - 2025</a>
        <a href="/2025-shortlist/">2025 SHORTLIST</a>
      </main>
    '''
    gold_html = '''
      <main>
        <h5>A Family Matter by Claire Lynch</h5>
        <p>Judges praised the book.</p>
        <h5>Claire Lynch</h5>
        <h5>Other books shortlisted in this category :</h5>
        <p>The Expansion Project by Ben Pester</p>
      </main>
    '''

    parsed = NeroBookAwardsOfficialParser('Nero Gold Prize').parse(
      root_html,
      'https://nerobookawards.com/key-dates/',
      'Nero Gold Prize / Book of the Year',
      fetch_url=lambda url: gold_html)

    self.assertEqual([
      ('2025', 'A Family Matter', 'Claire Lynch', 'winner'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertEqual('Nero Gold Prize', parsed['entries'][0]['category'])

  def test_nero_book_awards_wikipedia_category_and_gold_rows(self):
    from parser.nero_book_awards import NeroBookAwardsWikipediaParser

    html = '''
      <table>
        <tr>
          <th>Year</th><th>Title</th><th>Author</th>
          <th>Publisher</th><th>Result</th>
        </tr>
        <tr>
          <td rowspan="5">2025</td>
          <td>A Family Matter</td><td>Claire Lynch</td>
          <td>Hutchinson Heinemann</td><td>Overall winner</td>
        </tr>
        <tr>
          <td>Seascraper</td><td>Benjamin Wood</td>
          <td>Viking</td><td>Fiction winner</td>
        </tr>
        <tr>
          <td>The Two Roberts</td><td>Damian Barr</td>
          <td>Canongate</td><td>Fiction shortlist</td>
        </tr>
        <tr>
          <td>The Twelve (Pushkin Children's Books)</td>
          <td>Liz Hyder (illustrated by Tom De Freston)</td>
          <td>Pushkin</td><td>Children's Fiction winner</td>
        </tr>
        <tr>
          <td>Poetry Book</td><td>Poet Name</td>
          <td>Small Press</td><td>Poetry winner</td>
        </tr>
      </table>
    '''

    fiction = NeroBookAwardsWikipediaParser('Fiction').parse(html)
    gold = NeroBookAwardsWikipediaParser('Nero Gold Prize').parse(html)
    childrens = NeroBookAwardsWikipediaParser("Children's Fiction").parse(html)

    self.assertEqual([
      ('2025', 'Seascraper', 'Benjamin Wood', 'winner'),
      ('2025.01', 'The Two Roberts', 'Damian Barr', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in fiction['entries']
    ])
    self.assertEqual(
      [('A Family Matter', 'Claire Lynch')],
      [(entry['title'], entry['author']) for entry in gold['entries']])
    self.assertEqual(
      [('The Twelve', 'Liz Hyder')],
      [(entry['title'], entry['author']) for entry in childrens['entries']])
    self.assertNotIn('Poetry Book', [entry['title'] for entry in fiction['entries']])

  def test_nero_book_awards_fetchers_metadata_and_fallback(self):
    from parser.base import (
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_NONFICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
      CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    )
    from url_fetcher.nero_book_awards import (
      UrlFetcherNeroBookAwardsChildrensFiction,
      UrlFetcherNeroBookAwardsDebutFiction,
      UrlFetcherNeroBookAwardsFiction,
      UrlFetcherNeroBookAwardsGoldPrize,
      UrlFetcherNeroBookAwardsNonfiction,
    )

    fetchers = (
      (UrlFetcherNeroBookAwardsFiction(), CATEGORY_LITERARY_GENERAL_FICTION),
      (UrlFetcherNeroBookAwardsDebutFiction(), CATEGORY_LITERARY_GENERAL_FICTION),
      (UrlFetcherNeroBookAwardsNonfiction(), CATEGORY_NONFICTION),
      (
        UrlFetcherNeroBookAwardsChildrensFiction(),
        CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
      ),
      (UrlFetcherNeroBookAwardsGoldPrize(), None),
    )
    expected_ids = {
      'nero_book_awards_fiction',
      'nero_book_awards_debut_fiction',
      'nero_book_awards_nonfiction',
      'nero_book_awards_childrens_fiction',
      'nero_book_awards_gold_prize',
    }
    self.assertEqual(expected_ids, {fetcher.source_id for fetcher, _filter in fetchers})

    for fetcher, expected_filter in fetchers:
      with self.subTest(fetcher=fetcher.source_id):
        filters = [item['label'] for item in fetcher.get_filter_list()]
        if expected_filter is not None:
          self.assertIn(expected_filter, filters)
        self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
        self.assertFalse(fetcher.options['match_series'])
        self.assertEqual((
          {'label': 'Automatic', 'value': 'automatic'},
          {'label': 'Nero Book Awards', 'value': 0},
          {'label': 'Wikipedia', 'value': 1},
        ), fetcher.source_choices())

    fetcher = UrlFetcherNeroBookAwardsFiction()
    wiki_html = '''
      <table>
        <tr><th>Year</th><th>Title</th><th>Author</th><th>Result</th></tr>
        <tr><td>2025</td><td>Seascraper</td><td>Benjamin Wood</td><td>Fiction winner</td></tr>
      </table>
    '''
    calls = []

    def fetch_url(url):
      calls.append(url)
      if url == fetcher.URL:
        return '<main><p>2026 key dates only.</p></main>'
      if url == fetcher.WIKIPEDIA_URL:
        return wiki_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual(['Seascraper'], [entry['title'] for entry in parsed['entries']])
    self.assertEqual([fetcher.URL, fetcher.WIKIPEDIA_URL], calls)
    self.assertFalse(parsed['match_series'])
    with self.assertRaises(Exception):
      fetcher.fetch_and_parse(fetch_url, disable_fallbacks=True)

  def test_nsw_premiers_literary_awards_official_cards_and_skips_noise(self):
    from parser.nsw_premiers_literary_awards import (
      NSWPremiersLiteraryAwardsOfficialParser,
    )

    html = '''
      <html><head><title>Christina Stead Prize for Fiction</title></head>
      <body><main>
        <h2>2026 winner and shortlist</h2>
        <div class="slnsw-card">
          <span class="slnsw-d10-badges__badge__text">Winner</span>
          <h5><a href="/awards/christina-stead-prize-fiction/2026-winner-night-blue">Night Blue</a></h5>
          <div class="award-entry-author">Angela O'Keeffe</div>
          <div class="award-entry-publisher">UQP</div>
        </div>
        <div class="slnsw-card">
          <span class="slnsw-d10-badges__badge__text">Shortlisted</span>
          <h5><a href="/awards/christina-stead-prize-fiction/2026-shortlisted-stone">Stone Yard Devotional</a></h5>
          <div class="award-entry-author">Charlotte Wood</div>
          <div class="award-entry-publisher">Allen &amp; Unwin</div>
        </div>
        <div class="award-judges-card">
          <h5>Judge Biography</h5>
          <p>Includes references to several books but is not an award row.</p>
        </div>
        <h2>Past winners</h2>
        <div class="slnsw-card">
          <span class="slnsw-d10-badges__badge__text">Winner</span>
          <h5><a href="/awards/christina-stead-prize-fiction/2025-winner-highway-13">Highway 13</a></h5>
          <div class="award-entry-author">Fiona McFarlane</div>
        </div>
      </main></body></html>
    '''

    parsed = NSWPremiersLiteraryAwardsOfficialParser(
      'Christina Stead Prize for Fiction',
      ('Christina Stead Prize for Fiction', 'Fiction')).parse(
        html,
        'https://www.sl.nsw.gov.au/awards/nsw-literary-awards/christina-stead-prize-fiction')

    self.assertEqual([
      ('2025', 'Highway 13', 'Fiona McFarlane', 'winner'),
      ('2026', 'Night Blue', "Angela O'Keeffe", 'winner'),
      ('2026.01', 'Stone Yard Devotional', 'Charlotte Wood', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertTrue(all(
      entry['award'] == "NSW Premier's Literary Awards"
      for entry in parsed['entries']))
    self.assertTrue(all(
      entry['category'] == 'Christina Stead Prize for Fiction'
      for entry in parsed['entries']))
    self.assertNotIn('Judge Biography', [entry['title'] for entry in parsed['entries']])
    self.assertFalse(parsed['match_series'])

  def test_nsw_premiers_literary_awards_announcement_sections(self):
    from parser.nsw_premiers_literary_awards import (
      NSWPremiersLiteraryAwardsOfficialParser,
    )

    html = '''
      <html><head><title>2025 NSW Literary Awards announcement</title></head>
      <body><main>
        <h2>Christina Stead Prize for Fiction</h2>
        <ul>
          <li>WINNER: Theory &amp; Practice by Michelle de Kretser</li>
          <li>Rapture by Emily Maguire</li>
        </ul>
        <h2>Kenneth Slessor Prize for Poetry</h2>
        <ul><li>WINNER: The Cyprian by Amy Crutchfield</li></ul>
        <h2>Nick Enright Prize for Playwriting</h2>
        <p>WINNER: Stage Work by Playwright</p>
      </main></body></html>
    '''

    parsed = NSWPremiersLiteraryAwardsOfficialParser(
      'Christina Stead Prize for Fiction',
      ('Christina Stead Prize for Fiction', 'Fiction')).parse(
        html,
        'https://www.sl.nsw.gov.au/awards/nsw-literary-awards/2025-nsw-literary-awards-announcement')

    self.assertEqual([
      ('2025', 'Theory & Practice', 'Michelle de Kretser', 'winner'),
      ('2025.01', 'Rapture', 'Emily Maguire', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertNotIn('The Cyprian', [entry['title'] for entry in parsed['entries']])
    self.assertNotIn('Stage Work', [entry['title'] for entry in parsed['entries']])

  def test_nsw_premiers_literary_awards_wikipedia_rollup_winners(self):
    from parser.nsw_premiers_literary_awards import (
      NSWPremiersLiteraryAwardsWikipediaParser,
    )

    html = '''
      <h2>Book of the Year</h2>
      <table>
        <tr><th>Year</th><th>Title</th><th>Author</th><th>Result</th></tr>
        <tr><td rowspan="2">2024</td><td>She is the Earth</td><td>Ali Cobby Eckermann</td><td>Winner</td></tr>
        <tr><td>Another Book</td><td>Another Author</td><td>Shortlisted</td></tr>
        <tr><td>2023</td><td>We Come With This Place</td><td>Debra Dank</td><td>Winner</td></tr>
      </table>
      <h2>Kenneth Slessor Prize for Poetry</h2>
      <table>
        <tr><th>Year</th><th>Title</th><th>Author</th><th>Result</th></tr>
        <tr><td>2024</td><td>The Cyprian</td><td>Amy Crutchfield</td><td>Winner</td></tr>
      </table>
    '''

    parsed = NSWPremiersLiteraryAwardsWikipediaParser(
      'Book of the Year',
      ('Book of the Year',)).parse(html)

    self.assertEqual([
      ('2023', 'We Come With This Place', 'Debra Dank', 'winner'),
      ('2024', 'She is the Earth', 'Ali Cobby Eckermann', 'winner'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertNotIn('Another Book', [entry['title'] for entry in parsed['entries']])
    self.assertNotIn('The Cyprian', [entry['title'] for entry in parsed['entries']])

  def test_nsw_premiers_literary_awards_fetchers_metadata_and_fallback(self):
    from parser.base import (
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_NONFICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
      CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    )
    from url_fetcher.nsw_premiers_literary_awards import (
      UrlFetcherNSWPremiersLiteraryAwardsBookOfTheYear,
      UrlFetcherNSWPremiersLiteraryAwardsChristinaSteadFiction,
      UrlFetcherNSWPremiersLiteraryAwardsDouglasStewartNonfiction,
      UrlFetcherNSWPremiersLiteraryAwardsEthelTurnerYoungPeople,
      UrlFetcherNSWPremiersLiteraryAwardsGlendaAdamsNewWriting,
      UrlFetcherNSWPremiersLiteraryAwardsIndigenousWriters,
      UrlFetcherNSWPremiersLiteraryAwardsMulticulturalNSW,
      UrlFetcherNSWPremiersLiteraryAwardsPatriciaWrightsonChildrens,
      UrlFetcherNSWPremiersLiteraryAwardsPeoplesChoice,
    )

    fetchers = (
      (UrlFetcherNSWPremiersLiteraryAwardsChristinaSteadFiction(), CATEGORY_LITERARY_GENERAL_FICTION),
      (UrlFetcherNSWPremiersLiteraryAwardsDouglasStewartNonfiction(), CATEGORY_NONFICTION),
      (
        UrlFetcherNSWPremiersLiteraryAwardsPatriciaWrightsonChildrens(),
        CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
      ),
      (
        UrlFetcherNSWPremiersLiteraryAwardsEthelTurnerYoungPeople(),
        CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
      ),
      (UrlFetcherNSWPremiersLiteraryAwardsIndigenousWriters(), None),
      (UrlFetcherNSWPremiersLiteraryAwardsGlendaAdamsNewWriting(), CATEGORY_LITERARY_GENERAL_FICTION),
      (UrlFetcherNSWPremiersLiteraryAwardsMulticulturalNSW(), CATEGORY_NONFICTION),
      (UrlFetcherNSWPremiersLiteraryAwardsBookOfTheYear(), CATEGORY_NONFICTION),
      (UrlFetcherNSWPremiersLiteraryAwardsPeoplesChoice(), None),
    )
    expected_ids = {
      'nsw_premiers_literary_awards_christina_stead_fiction',
      'nsw_premiers_literary_awards_douglas_stewart_nonfiction',
      'nsw_premiers_literary_awards_patricia_wrightson_childrens',
      'nsw_premiers_literary_awards_ethel_turner_young_people',
      'nsw_premiers_literary_awards_indigenous_writers',
      'nsw_premiers_literary_awards_glenda_adams_new_writing',
      'nsw_premiers_literary_awards_multicultural_nsw',
      'nsw_premiers_literary_awards_book_of_the_year',
      'nsw_premiers_literary_awards_peoples_choice',
    }
    self.assertEqual(expected_ids, {fetcher.source_id for fetcher, _filter in fetchers})

    for fetcher, expected_filter in fetchers:
      with self.subTest(fetcher=fetcher.source_id):
        filters = [item['label'] for item in fetcher.get_filter_list()]
        if expected_filter is not None:
          self.assertIn(expected_filter, filters)
        self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
        self.assertFalse(fetcher.options['match_series'])

    self.assertEqual(
      ({'label': 'Automatic', 'value': 'automatic'},),
      UrlFetcherNSWPremiersLiteraryAwardsChristinaSteadFiction().source_choices())
    self.assertEqual((
      {'label': 'Automatic', 'value': 'automatic'},
      {'label': 'State Library NSW', 'value': 0},
      {'label': 'Wikipedia', 'value': 1},
    ), UrlFetcherNSWPremiersLiteraryAwardsBookOfTheYear().source_choices())

    fetcher = UrlFetcherNSWPremiersLiteraryAwardsBookOfTheYear()
    official_html = '<html><title>Book of the Year</title><p>No entries yet.</p></html>'
    wiki_html = '''
      <h2>Book of the Year</h2>
      <table>
        <tr><th>Year</th><th>Title</th><th>Author</th><th>Result</th></tr>
        <tr><td>2024</td><td>She is the Earth</td><td>Ali Cobby Eckermann</td><td>Winner</td></tr>
      </table>
    '''
    calls = []

    def fetch_url(url):
      calls.append(url)
      if url == fetcher.URL:
        return official_html
      if url == fetcher.WIKIPEDIA_URL:
        return wiki_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual(['She is the Earth'], [entry['title'] for entry in parsed['entries']])
    self.assertEqual([fetcher.URL, fetcher.WIKIPEDIA_URL], calls)
    self.assertFalse(parsed['match_series'])
    with self.assertRaises(Exception):
      fetcher.fetch_and_parse(fetch_url, disable_fallbacks=True)

  def test_queensland_literary_awards_official_largest_prizes(self):
    from parser.queensland_literary_awards import (
      QueenslandLiteraryAwardsOfficialParser,
    )

    html = '''
      <main>
        <h2>2025 Queensland Literary Awards</h2>
        <h3>Queensland Premier's Award for a Work of State Significance</h3>
        <h4>Winner</h4>
        <p><a href="/qla/black-witness">Black Witness (UQP</a></p>
        <p>written by Amy McQuire</p>
        <h4>Finalists</h4>
        <p>The Knowledge Gene by Lynne Kelly (Allen &amp; Unwin)</p>
        <h3>The University of Queensland Fiction Book Award</h3>
        <h4>Winner</h4>
        <p>The Jaguar written by Sarah Holland-Batt (UQP)</p>
        <h3>The University of Queensland Non-Fiction Book Award</h3>
        <h4>Winner</h4>
        <p>Personal Score by Ellen van Neerven</p>
        <h3>Children's Book Award</h3>
        <h4>Winner</h4>
        <p>Scar Town by Tristan Bancks</p>
        <h3>Young Adult Book Award</h3>
        <h4>Winner</h4>
        <p>Completely Normal (and Other Lies) by Biffy James</p>
        <h3>People's Choice Queensland Book of the Year Award</h3>
        <h4>Winner</h4>
        <p>Edenglassie by Melissa Lucashenko</p>
        <h3>Queensland Writers Fellowship</h3>
        <h4>Winner</h4>
        <p>Person Only by Not A Book</p>
        <h3>David Unaipon Award</h3>
        <h4>Winner</h4>
        <p>Unpublished Manuscript by Future Author</p>
        <h3>Glendower Award for an Emerging Queensland Writer</h3>
        <h4>Winner</h4>
        <p>Emerging Person by Person Name</p>
      </main>
    '''

    cases = (
      (
        'Work of State Significance',
        ('Queensland Premier\'s Award for a Work of State Significance',),
        [
          ('2025', 'Black Witness', 'Amy McQuire', 'winner'),
          ('2025.01', 'The Knowledge Gene', 'Lynne Kelly', 'shortlisted'),
        ],
      ),
      (
        'Fiction',
        ('The University of Queensland Fiction Book Award', 'Fiction'),
        [('2025', 'The Jaguar', 'Sarah Holland-Batt', 'winner')],
      ),
      (
        'Non-Fiction',
        ('The University of Queensland Non-Fiction Book Award', 'Non-Fiction'),
        [('2025', 'Personal Score', 'Ellen van Neerven', 'winner')],
      ),
      (
        "Children's Book",
        ("Children's Book Award",),
        [('2025', 'Scar Town', 'Tristan Bancks', 'winner')],
      ),
      (
        'Young Adult Book',
        ('Young Adult Book Award',),
        [('2025', 'Completely Normal (and Other Lies)', 'Biffy James', 'winner')],
      ),
      (
        "People's Choice",
        ("People's Choice Queensland Book of the Year Award",),
        [('2025', 'Edenglassie', 'Melissa Lucashenko', 'winner')],
      ),
    )

    for category, aliases, expected in cases:
      with self.subTest(category=category):
        parsed = QueenslandLiteraryAwardsOfficialParser(
          category, aliases).parse(html)
        self.assertEqual(expected, [
          (entry['position'], entry['title'], entry['author'], entry['result'])
          for entry in parsed['entries']
        ])
        self.assertTrue(all(
          entry['award'] == 'Queensland Literary Awards'
          for entry in parsed['entries']))
        self.assertTrue(all(entry['category'] == category for entry in parsed['entries']))
        self.assertNotIn('Person Only', [entry['title'] for entry in parsed['entries']])
        self.assertFalse(parsed['match_series'])

  def test_queensland_literary_awards_official_historical_aliases(self):
    from parser.queensland_literary_awards import (
      QueenslandLiteraryAwardsOfficialParser,
    )

    html = '''
      <main>
        <h2>2018 Queensland Literary Awards</h2>
        <h3>Queensland Premier's Award for a Work of State Signiﬁcance</h3>
        <h4>Winner</h4>
        <p>Tracker by Alexis Wright</p>
        <h3>Griffith University Children's Book Award</h3>
        <h4>Winner</h4>
        <p>Nevermoor by Jessica Townsend</p>
        <h3>Griffith University Young Adult Book Award</h3>
        <h4>Winner</h4>
        <p>Changing Gear by Scot Gardner</p>
      </main>
    '''

    state = QueenslandLiteraryAwardsOfficialParser(
      'Work of State Significance',
      ('Queensland Premier\'s Award for a Work of State Significance',)).parse(html)
    children = QueenslandLiteraryAwardsOfficialParser(
      "Children's Book",
      ("Griffith University Children's Book Award",)).parse(html)
    young_adult = QueenslandLiteraryAwardsOfficialParser(
      'Young Adult Book',
      ('Griffith University Young Adult Book Award',)).parse(html)

    self.assertEqual(['Tracker'], [entry['title'] for entry in state['entries']])
    self.assertEqual(['Nevermoor'], [entry['title'] for entry in children['entries']])
    self.assertEqual(['Changing Gear'], [entry['title'] for entry in young_adult['entries']])

  def test_queensland_literary_awards_wikipedia_and_fetcher_fallback(self):
    from parser.queensland_literary_awards import (
      QueenslandLiteraryAwardsWikipediaParser,
    )
    from url_fetcher.queensland_literary_awards import (
      UrlFetcherQueenslandLiteraryAwardsFiction,
    )

    wiki_html = '''
      <table>
        <tr><th>Year</th><th>Category</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr><td>2024</td><td>Fiction</td><td>Sarah Holland-Batt</td><td>The Jaguar</td><td>Winner</td></tr>
        <tr><td>2024</td><td>Fiction</td><td>Another Writer</td><td>Other Novel</td><td>Finalist</td></tr>
        <tr><td>2024</td><td>Fiction</td><td>Third Writer</td><td>Third Novel</td><td></td></tr>
        <tr><td>2024</td><td>Poetry</td><td>Poet Name</td><td>Poetry Book</td><td>Winner</td></tr>
      </table>
    '''

    parsed = QueenslandLiteraryAwardsWikipediaParser(
      'Fiction',
      ('Fiction', 'The University of Queensland Fiction Book Award')).parse(wiki_html)

    self.assertEqual([
      ('2024', 'The Jaguar', 'Sarah Holland-Batt', 'winner'),
      ('2024.01', 'Other Novel', 'Another Writer', 'shortlisted'),
      ('2024.02', 'Third Novel', 'Third Writer', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertNotIn('Poetry Book', [entry['title'] for entry in parsed['entries']])

    fetcher = UrlFetcherQueenslandLiteraryAwardsFiction()
    calls = []

    def fetch_url(url):
      calls.append(url)
      if url == fetcher.URL:
        return '<main><h2>2025</h2><p>No entries yet.</p></main>'
      if url == fetcher.WIKIPEDIA_URL:
        return wiki_html
      self.fail(url)

    fallback_parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual(['The Jaguar', 'Other Novel', 'Third Novel'], [
      entry['title'] for entry in fallback_parsed['entries']
    ])
    self.assertEqual([fetcher.URL, fetcher.WIKIPEDIA_URL], calls)
    self.assertFalse(fallback_parsed['match_series'])
    with self.assertRaises(Exception):
      fetcher.fetch_and_parse(fetch_url, disable_fallbacks=True)

  def test_queensland_literary_awards_fetchers_metadata_and_registry(self):
    from parser.base import (
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_NONFICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
      CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    )
    from url_fetcher import available_url_fetchers
    from url_fetcher.queensland_literary_awards import (
      UrlFetcherQueenslandLiteraryAwardsChildrens,
      UrlFetcherQueenslandLiteraryAwardsFiction,
      UrlFetcherQueenslandLiteraryAwardsNonfiction,
      UrlFetcherQueenslandLiteraryAwardsPeoplesChoice,
      UrlFetcherQueenslandLiteraryAwardsStateSignificance,
      UrlFetcherQueenslandLiteraryAwardsYoungAdult,
    )

    fetchers = (
      (UrlFetcherQueenslandLiteraryAwardsStateSignificance(), None),
      (UrlFetcherQueenslandLiteraryAwardsFiction(), CATEGORY_LITERARY_GENERAL_FICTION),
      (UrlFetcherQueenslandLiteraryAwardsNonfiction(), CATEGORY_NONFICTION),
      (
        UrlFetcherQueenslandLiteraryAwardsChildrens(),
        CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
      ),
      (
        UrlFetcherQueenslandLiteraryAwardsYoungAdult(),
        CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
      ),
      (UrlFetcherQueenslandLiteraryAwardsPeoplesChoice(), None),
    )
    expected_ids = {
      'queensland_literary_awards_state_significance',
      'queensland_literary_awards_fiction',
      'queensland_literary_awards_nonfiction',
      'queensland_literary_awards_childrens',
      'queensland_literary_awards_young_adult',
      'queensland_literary_awards_peoples_choice',
    }
    self.assertEqual(expected_ids, {fetcher.source_id for fetcher, _filter in fetchers})

    for fetcher, expected_filter in fetchers:
      with self.subTest(fetcher=fetcher.source_id):
        filters = [item['label'] for item in fetcher.get_filter_list()]
        if expected_filter is not None:
          self.assertIn(expected_filter, filters)
        self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
        self.assertFalse(fetcher.options['match_series'])
        self.assertEqual((
          {'label': 'Automatic', 'value': 'automatic'},
          {'label': 'State Library of Queensland', 'value': 0},
          {'label': 'Wikipedia', 'value': 1},
        ), fetcher.source_choices())

    registry_ids = [fetcher.source_id for fetcher in available_url_fetchers()]
    self.assertTrue(expected_ids.issubset(set(registry_ids)))
    self.assertLess(
      registry_ids.index('nsw_premiers_literary_awards_peoples_choice'),
      registry_ids.index('queensland_literary_awards_state_significance'))
    self.assertLess(
      registry_ids.index('queensland_literary_awards_peoples_choice'),
      registry_ids.index('writers_trust_atwood_gibson_fiction'))

  def test_western_australian_premiers_book_awards_current_tables(self):
    from parser.western_australian_premiers_book_awards import (
      WesternAustralianPremiersBookAwardsWikipediaParser,
    )

    html = '''
      <table>
        <tr><th>Year</th><th>Category</th><th>Author</th><th>Title</th><th>Publisher</th><th>Result</th></tr>
        <tr><td rowspan="3">2024</td><td>Book of the Year</td><td>Stephen Daisley</td><td>A Better Place</td><td>Text</td><td>Winner</td></tr>
        <tr><td>Emerging Writer</td><td>Michael Thomas</td><td>The Map of William</td><td>Fremantle Press</td><td>Winner</td></tr>
        <tr><td>Poetry</td><td>Poet Name</td><td>Poetry Book</td><td>Example</td><td>Winner</td></tr>
        <tr><td rowspan="6">2025</td><td rowspan="3">Fiction Book of the Year</td><td>Fiction Winner</td><td>Fiction Winner Book</td><td>Example</td><td>Winner</td></tr>
        <tr><td>Fiction Finalist</td><td>Fiction Finalist Book</td><td>Example</td><td>Shortlist</td></tr>
        <tr><td>Fiction Blank</td><td>Fiction Blank Book</td><td>Example</td><td></td></tr>
        <tr><td>Nonfiction Book of the Year</td><td>Nonfiction Writer</td><td>Nonfiction Book</td><td>Example</td><td>Winner</td></tr>
        <tr><td>Children's Book of the Year</td><td>Children's Writer</td><td>Children's Book Title</td><td>Example</td><td>Winner</td></tr>
        <tr><td>Young Adult Book of the Year</td><td>YA Writer</td><td>YA Book Title</td><td>Example</td><td>Winner</td></tr>
      </table>
    '''

    cases = (
      (
        'Book of the Year',
        ('Book of the Year',),
        [('2024', 'A Better Place', 'Stephen Daisley', 'winner')],
      ),
      (
        'Emerging Writer',
        ('Emerging Writer',),
        [('2024', 'The Map of William', 'Michael Thomas', 'winner')],
      ),
      (
        'Fiction',
        ('Fiction Book of the Year', 'Fiction'),
        [
          ('2025', 'Fiction Winner Book', 'Fiction Winner', 'winner'),
          ('2025.01', 'Fiction Finalist Book', 'Fiction Finalist', 'shortlisted'),
          ('2025.02', 'Fiction Blank Book', 'Fiction Blank', 'shortlisted'),
        ],
      ),
      (
        'Nonfiction',
        ('Nonfiction Book of the Year', 'Nonfiction'),
        [('2025', 'Nonfiction Book', 'Nonfiction Writer', 'winner')],
      ),
      (
        "Children's Book",
        ("Children's Book of the Year", "Children's Book"),
        [('2025', "Children's Book Title", "Children's Writer", 'winner')],
      ),
      (
        'Young Adult Book',
        ('Young Adult Book of the Year', 'Writing for Young Adults'),
        [('2025', 'YA Book Title', 'YA Writer', 'winner')],
      ),
    )

    for category, aliases, expected in cases:
      with self.subTest(category=category):
        parsed = WesternAustralianPremiersBookAwardsWikipediaParser(
          category, aliases).parse(html)
        self.assertEqual(expected, [
          (entry['position'], entry['title'], entry['author'], entry['result'])
          for entry in parsed['entries']
        ])
        self.assertTrue(all(
          entry['award'] == "Western Australian Premier's Book Awards"
          for entry in parsed['entries']))
        self.assertTrue(all(entry['category'] == category for entry in parsed['entries']))
        self.assertFalse(parsed['match_series'])

  def test_western_australian_premiers_book_awards_historical_aliases(self):
    from parser.western_australian_premiers_book_awards import (
      WesternAustralianPremiersBookAwardsWikipediaParser,
    )

    html = '''
      <table>
        <tr><th>Year</th><th>Award</th><th>Writer</th><th>Work</th><th>Status</th></tr>
        <tr><td>2010</td><td>Overall</td><td>Overall Writer</td><td>Overall Book</td><td>Winner</td></tr>
        <tr><td>2011</td><td>Fiction</td><td>Fiction Writer</td><td>Old Fiction</td><td>Winner</td></tr>
        <tr><td>2012</td><td>Non-fiction</td><td>Nonfiction Writer</td><td>Old Nonfiction</td><td>Winner</td></tr>
        <tr><td>2013</td><td>Children's book</td><td>Children's Writer</td><td>Old Children's</td><td>Winner</td></tr>
        <tr><td>2014</td><td>Writing for Young Adults</td><td>YA Writer</td><td>Old YA</td><td>Winner</td></tr>
      </table>
    '''

    self.assertEqual(
      ['Overall Book'],
      [entry['title'] for entry in WesternAustralianPremiersBookAwardsWikipediaParser(
        'Book of the Year', ('Overall', 'Premier\'s Prize')).parse(html)['entries']])
    self.assertEqual(
      ['Old Fiction'],
      [entry['title'] for entry in WesternAustralianPremiersBookAwardsWikipediaParser(
        'Fiction', ('Fiction',)).parse(html)['entries']])
    self.assertEqual(
      ['Old Nonfiction'],
      [entry['title'] for entry in WesternAustralianPremiersBookAwardsWikipediaParser(
        'Nonfiction', ('Non-fiction', 'Nonfiction')).parse(html)['entries']])
    self.assertEqual(
      ["Old Children's"],
      [entry['title'] for entry in WesternAustralianPremiersBookAwardsWikipediaParser(
        "Children's Book", ("Children's book",)).parse(html)['entries']])
    self.assertEqual(
      ['Old YA'],
      [entry['title'] for entry in WesternAustralianPremiersBookAwardsWikipediaParser(
        'Young Adult Book', ('Writing for Young Adults',)).parse(html)['entries']])

  def test_western_australian_premiers_book_awards_skips_out_of_scope_categories(self):
    from parser.western_australian_premiers_book_awards import (
      WesternAustralianPremiersBookAwardsWikipediaParser,
    )

    html = '''
      <table>
        <tr><th>Year</th><th>Category</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr><td>2025</td><td>WA Writer's Fellowship</td><td>Fellow Name</td><td>Fellow Work</td><td>Winner</td></tr>
        <tr><td>2025</td><td>Daisy Utemorrah Award</td><td>Manuscript Writer</td><td>Unpublished Work</td><td>Winner</td></tr>
        <tr><td>2025</td><td>Poetry</td><td>Poet Name</td><td>Poetry Book</td><td>Winner</td></tr>
        <tr><td>2025</td><td>Script</td><td>Script Writer</td><td>Script Work</td><td>Winner</td></tr>
        <tr><td>2025</td><td>Digital Narrative</td><td>Digital Writer</td><td>Digital Work</td><td>Winner</td></tr>
        <tr><td>2025</td><td>Special Award</td><td>Person Name</td><td>Person Work</td><td>Winner</td></tr>
        <tr><td>2025</td><td>WA History</td><td>History Writer</td><td>History Work</td><td>Winner</td></tr>
      </table>
    '''

    parsed = WesternAustralianPremiersBookAwardsWikipediaParser(
      'Excluded',
      (
        'WA Writer\'s Fellowship',
        'Daisy Utemorrah Award',
        'Poetry',
        'Script',
        'Digital Narrative',
        'Special Award',
        'WA History',
      )).parse(html)

    self.assertEqual([], parsed['entries'])

  def test_western_australian_premiers_book_awards_fetchers_metadata_and_registry(self):
    from parser.base import (
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_NONFICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
      CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    )
    from url_fetcher import available_url_fetchers
    from url_fetcher.western_australian_premiers_book_awards import (
      UrlFetcherWesternAustralianPremiersBookAwardsBookOfTheYear,
      UrlFetcherWesternAustralianPremiersBookAwardsChildrens,
      UrlFetcherWesternAustralianPremiersBookAwardsEmergingWriter,
      UrlFetcherWesternAustralianPremiersBookAwardsFiction,
      UrlFetcherWesternAustralianPremiersBookAwardsNonfiction,
      UrlFetcherWesternAustralianPremiersBookAwardsYoungAdult,
    )

    fetchers = (
      (UrlFetcherWesternAustralianPremiersBookAwardsBookOfTheYear(), None),
      (UrlFetcherWesternAustralianPremiersBookAwardsFiction(), CATEGORY_LITERARY_GENERAL_FICTION),
      (UrlFetcherWesternAustralianPremiersBookAwardsNonfiction(), CATEGORY_NONFICTION),
      (UrlFetcherWesternAustralianPremiersBookAwardsEmergingWriter(), None),
      (
        UrlFetcherWesternAustralianPremiersBookAwardsChildrens(),
        CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
      ),
      (
        UrlFetcherWesternAustralianPremiersBookAwardsYoungAdult(),
        CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
      ),
    )
    expected_ids = {
      'western_australian_premiers_book_awards_book_of_the_year',
      'western_australian_premiers_book_awards_fiction',
      'western_australian_premiers_book_awards_nonfiction',
      'western_australian_premiers_book_awards_emerging_writer',
      'western_australian_premiers_book_awards_childrens',
      'western_australian_premiers_book_awards_young_adult',
    }
    self.assertEqual(expected_ids, {fetcher.source_id for fetcher, _filter in fetchers})

    for fetcher, expected_filter in fetchers:
      with self.subTest(fetcher=fetcher.source_id):
        filters = [item['label'] for item in fetcher.get_filter_list()]
        if expected_filter is not None:
          self.assertIn(expected_filter, filters)
        self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
        self.assertFalse(fetcher.options['match_series'])
        self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())

    registry_ids = [fetcher.source_id for fetcher in available_url_fetchers()]
    self.assertTrue(expected_ids.issubset(set(registry_ids)))
    self.assertLess(
      registry_ids.index('queensland_literary_awards_peoples_choice'),
      registry_ids.index('western_australian_premiers_book_awards_book_of_the_year'))
    self.assertLess(
      registry_ids.index('western_australian_premiers_book_awards_young_adult'),
      registry_ids.index('writers_trust_atwood_gibson_fiction'))

  def test_south_australian_literary_awards_official_winners(self):
    from parser.south_australian_literary_awards import (
      SouthAustralianLiteraryAwardsOfficialParser,
    )

    html = '''
      <main>
        <h2>2024 winners</h2>
        <h3>Premier's Award</h3>
        <ul>
          <li><a href="/premiers-award">2024 - Childhood, Shannon Burns (Text Publishing)</a></li>
        </ul>
        <h3>Fiction Award</h3>
        <p>2024 - Permafrost, SJ Norman (University of Queensland Press)</p>
        <h3>Non-Fiction Award</h3>
        <p>2024 - Childhood, Shannon Burns (Text Publishing)</p>
        <h3>Children's Literature Award</h3>
        <p>2024 - Scar Town by Tristan Bancks (Puffin)</p>
        <h3>Young Adult Fiction Award</h3>
        <p>2024 - Completely normal (and other lies), Biffy James (Hardie Grant)</p>
      </main>
    '''
    cases = (
      (
        "Premier's Award",
        ("Premier's Award",),
        [('2024', 'Childhood', 'Shannon Burns')],
      ),
      (
        'Fiction',
        ('Fiction Award', 'Fiction'),
        [('2024', 'Permafrost', 'SJ Norman')],
      ),
      (
        'Non-Fiction',
        ('Non-Fiction Award', 'Non-Fiction'),
        [('2024', 'Childhood', 'Shannon Burns')],
      ),
      (
        "Children's Literature",
        ("Children's Literature Award",),
        [('2024', 'Scar Town', 'Tristan Bancks')],
      ),
      (
        'Young Adult Fiction',
        ('Young Adult Fiction Award',),
        [('2024', 'Completely normal (and other lies)', 'Biffy James')],
      ),
    )

    for category, aliases, expected in cases:
      with self.subTest(category=category):
        parsed = SouthAustralianLiteraryAwardsOfficialParser(
          category, aliases).parse(html)
        self.assertEqual(expected, [
          (entry['position'], entry['title'], entry['author'])
          for entry in parsed['entries']
        ])
        self.assertTrue(all(entry['result'] == 'winner' for entry in parsed['entries']))
        self.assertTrue(all(
          entry['award'] == 'South Australian Literary Awards'
          for entry in parsed['entries']))
        self.assertTrue(all(entry['category'] == category for entry in parsed['entries']))
        self.assertFalse(parsed['match_series'])

  def test_south_australian_literary_awards_official_historical_aliases(self):
    from parser.south_australian_literary_awards import (
      SouthAustralianLiteraryAwardsOfficialParser,
    )

    html = '''
      <main>
        <h3>Premier's Award for the Best Overall Published Work</h3>
        <p>2020 - Joint winners: First Overall, A. Writer (Press); Second Overall by B. Writer</p>
        <h3>Fiction</h3>
        <p>2018 - Old Fiction by Fiction Writer (Publisher)</p>
        <h3>Nonfiction Award</h3>
        <p>2017 - Old Nonfiction, Nonfiction Writer (Publisher)</p>
        <h3>Young Adult Award</h3>
        <p>2016 - Old YA, YA Writer (Publisher)</p>
      </main>
    '''

    overall = SouthAustralianLiteraryAwardsOfficialParser(
      "Premier's Award",
      ("Premier's Award for the Best Overall Published Work",)).parse(html)
    fiction = SouthAustralianLiteraryAwardsOfficialParser(
      'Fiction',
      ('Fiction Award', 'Fiction')).parse(html)
    nonfiction = SouthAustralianLiteraryAwardsOfficialParser(
      'Non-Fiction',
      ('Nonfiction Award', 'Non-Fiction')).parse(html)
    young_adult = SouthAustralianLiteraryAwardsOfficialParser(
      'Young Adult Fiction',
      ('Young Adult Award', 'Young Adult Fiction')).parse(html)

    self.assertEqual([
      ('2020', 'First Overall', 'A. Writer'),
      ('2020', 'Second Overall', 'B. Writer'),
    ], [
      (entry['position'], entry['title'], entry['author'])
      for entry in overall['entries']
    ])
    self.assertEqual(['Old Fiction'], [entry['title'] for entry in fiction['entries']])
    self.assertEqual(['Old Nonfiction'], [entry['title'] for entry in nonfiction['entries']])
    self.assertEqual(['Old YA'], [entry['title'] for entry in young_adult['entries']])

  def test_south_australian_literary_awards_official_skips_out_of_scope_sections(self):
    from parser.south_australian_literary_awards import (
      SouthAustralianLiteraryAwardsOfficialParser,
    )

    html = '''
      <main>
        <h3>Fiction Award</h3>
        <p>2024 - No winner</p>
        <h3>John Bray Poetry Award</h3>
        <p>2024 - Poetry Book, Poet Name</p>
        <h3>Jill Blewett Playwright's Award</h3>
        <p>2024 - Play Script, Playwright Name</p>
        <h3>Unpublished Manuscript Award</h3>
        <p>2024 - Manuscript, Future Author</p>
        <h3>Barbara Hanrahan Fellowship</h3>
        <p>2024 - Fellow Name, Fellowship Project</p>
        <h3>Max Fatchen Fellowship</h3>
        <p>2024 - Fellow Name, Fellowship Project</p>
        <h3>Tangkanungku Pintyanthi Fellowship</h3>
        <p>2024 - Fellow Name, Fellowship Project</p>
        <h3>Innovation Award</h3>
        <p>2024 - Innovative Work, Innovator Name</p>
        <h3>Multimedia Award</h3>
        <p>2024 - Media Work, Media Maker</p>
      </main>
    '''

    parsed = SouthAustralianLiteraryAwardsOfficialParser(
      'Fiction',
      ('Fiction Award', 'Fiction')).parse(html)

    self.assertEqual([], parsed['entries'])

  def test_south_australian_literary_awards_wikipedia_fallback(self):
    from parser.south_australian_literary_awards import (
      SouthAustralianLiteraryAwardsWikipediaParser,
    )
    from url_fetcher.south_australian_literary_awards import (
      UrlFetcherSouthAustralianLiteraryAwardsFiction,
    )

    wiki_html = '''
      <table>
        <tr><th>Year</th><th>Category</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr><td>2024</td><td>Fiction Award</td><td>SJ Norman</td><td>Permafrost</td><td>Winner</td></tr>
        <tr><td></td><td>Fiction Award</td><td>Shortlisted Author</td><td>Short Book</td><td>Shortlist</td></tr>
        <tr><td>2024</td><td>John Bray Poetry Award</td><td>Poet</td><td>Poem Book</td><td>Winner</td></tr>
      </table>
    '''

    parsed = SouthAustralianLiteraryAwardsWikipediaParser(
      'Fiction',
      ('Fiction Award', 'Fiction')).parse(wiki_html)

    self.assertEqual([
      ('2024', 'Permafrost', 'SJ Norman', 'winner'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])

    fetcher = UrlFetcherSouthAustralianLiteraryAwardsFiction()
    calls = []

    def fetch_url(url):
      calls.append(url)
      if url == fetcher.URL:
        return '<main><h3>Fiction Award</h3><p>No winner</p></main>'
      if url == fetcher.WIKIPEDIA_URL:
        return wiki_html
      self.fail(url)

    fallback = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual(['Permafrost'], [entry['title'] for entry in fallback['entries']])
    self.assertEqual([fetcher.URL, fetcher.WIKIPEDIA_URL], calls)
    self.assertFalse(fallback['match_series'])
    with self.assertRaises(Exception):
      fetcher.fetch_and_parse(fetch_url, disable_fallbacks=True)

  def test_south_australian_literary_awards_fetchers_metadata_and_registry(self):
    from parser.base import (
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_NONFICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
      CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    )
    from url_fetcher import available_url_fetchers
    from url_fetcher.south_australian_literary_awards import (
      UrlFetcherSouthAustralianLiteraryAwardsChildrens,
      UrlFetcherSouthAustralianLiteraryAwardsFiction,
      UrlFetcherSouthAustralianLiteraryAwardsNonfiction,
      UrlFetcherSouthAustralianLiteraryAwardsPremiersAward,
      UrlFetcherSouthAustralianLiteraryAwardsYoungAdult,
    )

    fetchers = (
      (UrlFetcherSouthAustralianLiteraryAwardsPremiersAward(), None),
      (UrlFetcherSouthAustralianLiteraryAwardsFiction(), CATEGORY_LITERARY_GENERAL_FICTION),
      (UrlFetcherSouthAustralianLiteraryAwardsNonfiction(), CATEGORY_NONFICTION),
      (
        UrlFetcherSouthAustralianLiteraryAwardsChildrens(),
        CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
      ),
      (
        UrlFetcherSouthAustralianLiteraryAwardsYoungAdult(),
        CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
      ),
    )
    expected_ids = {
      'south_australian_literary_awards_premiers_award',
      'south_australian_literary_awards_fiction',
      'south_australian_literary_awards_nonfiction',
      'south_australian_literary_awards_childrens',
      'south_australian_literary_awards_young_adult',
    }
    self.assertEqual(expected_ids, {fetcher.source_id for fetcher, _filter in fetchers})

    for fetcher, expected_filter in fetchers:
      with self.subTest(fetcher=fetcher.source_id):
        filters = [item['label'] for item in fetcher.get_filter_list()]
        if expected_filter is not None:
          self.assertIn(expected_filter, filters)
        self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
        self.assertFalse(fetcher.options['match_series'])
        self.assertEqual((
          {'label': 'Automatic', 'value': 'automatic'},
          {'label': 'State Library of South Australia', 'value': 0},
          {'label': 'Wikipedia', 'value': 1},
        ), fetcher.source_choices())

    registry_ids = [fetcher.source_id for fetcher in available_url_fetchers()]
    self.assertTrue(expected_ids.issubset(set(registry_ids)))
    self.assertLess(
      registry_ids.index('western_australian_premiers_book_awards_young_adult'),
      registry_ids.index('south_australian_literary_awards_premiers_award'))
    self.assertLess(
      registry_ids.index('south_australian_literary_awards_young_adult'),
      registry_ids.index('writers_trust_atwood_gibson_fiction'))

  def test_act_book_of_the_year_official_parser_fetches_year_pages(self):
    from parser.act_book_of_the_year import ACTBookOfTheYearOfficialParser

    index_html = '''
      <main>
        <a href="/find/history/frequentlyaskedquestions/Events/literaryawards/book_of_the_year/2024">2024 ACT Book of the Year</a>
        <a href="/find/history/frequentlyaskedquestions/Events/literaryawards/book_of_the_year_2001">2001 ACT Book of the Year</a>
      </main>
    '''
    pages = {
      'https://www.library.act.gov.au/find/history/frequentlyaskedquestions/Events/literaryawards/book_of_the_year/2024': '''
        <main>
          <h1>2024 ACT Book of the Year</h1>
          <h2>Winner</h2>
          <p>Chris Hammer <a href="/catalogue/the-seven">The Seven</a></p>
          <h2>Highly Commended</h2>
          <p>Ayesha Inoon <a href="/catalogue/untethered">Untethered</a></p>
          <h2>Shortlist</h2>
          <p>Jackie French <a href="/catalogue/gallipoli">The Great Gallipoli Escape</a></p>
        </main>
      ''',
      'https://www.library.act.gov.au/find/history/frequentlyaskedquestions/Events/literaryawards/book_of_the_year_2001': '''
        <main>
          <h1>2001 ACT Book of the Year</h1>
          <h2>Joint Winners</h2>
          <p>Writer One <a href="/catalogue/joint-one">Joint Book One</a></p>
          <p>Writer Two <a href="/catalogue/joint-two">Joint Book Two</a></p>
        </main>
      ''',
    }
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      return pages[url]

    parsed = ACTBookOfTheYearOfficialParser().parse(
      index_html,
      'https://www.library.act.gov.au/find/history/frequentlyaskedquestions/Events/literaryawards/book_of_the_year',
      fetch_url=fetch_url)

    self.assertEqual([
      'https://www.library.act.gov.au/find/history/frequentlyaskedquestions/Events/literaryawards/book_of_the_year_2001',
      'https://www.library.act.gov.au/find/history/frequentlyaskedquestions/Events/literaryawards/book_of_the_year/2024',
    ], fetched)
    self.assertEqual([
      ('2001', 'Joint Book One', 'Writer One', 'winner'),
      ('2001', 'Joint Book Two', 'Writer Two', 'winner'),
      ('2024', 'The Seven', 'Chris Hammer', 'winner'),
      ('2024.01', 'Untethered', 'Ayesha Inoon', 'shortlisted'),
      ('2024.02', 'The Great Gallipoli Escape', 'Jackie French', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertTrue(all(entry['award'] == 'ACT Book of the Year Award' for entry in parsed['entries']))
    self.assertTrue(all(entry['category'] == 'Book of the Year' for entry in parsed['entries']))
    self.assertFalse(parsed['match_series'])

  def test_act_book_of_the_year_wikipedia_parser_handles_rowspans_and_results(self):
    from parser.act_book_of_the_year import ACTBookOfTheYearWikipediaParser

    html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Publisher</th><th>Result</th><th>Ref.</th></tr>
        <tr><td rowspan="2">2025</td><td>Darren Rix &amp; Craig Cormick</td><td><a href="/wiki/Warra_Warra_Wai">Warra Warra Wai</a></td><td>Publisher</td><td>Winner</td><td>[1]</td></tr>
        <tr><td>Sarah Ayoub</td><td>Lebanon Days</td><td>Publisher</td><td>Highly Commended</td><td>[1]</td></tr>
        <tr><td rowspan="2">2001</td><td>Writer One</td><td>Joint Book One</td><td>Publisher</td><td rowspan="2">Joint winners</td><td>[2]</td></tr>
        <tr><td>Writer Two</td><td>Joint Book Two</td><td>Publisher</td><td>[2]</td></tr>
        <tr><td>1998</td><td>Older Writer</td><td>Older Book</td><td>Publisher</td><td></td><td>[3]</td></tr>
      </table>
    '''

    parsed = ACTBookOfTheYearWikipediaParser().parse(html)

    self.assertEqual([
      ('1998', 'Older Book', 'Older Writer', 'winner'),
      ('2001', 'Joint Book One', 'Writer One', 'winner'),
      ('2001', 'Joint Book Two', 'Writer Two', 'winner'),
      ('2025', 'Warra Warra Wai', 'Darren Rix & Craig Cormick', 'winner'),
      ('2025.01', 'Lebanon Days', 'Sarah Ayoub', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])

  def test_act_book_of_the_year_fetcher_supplements_missing_official_winner(self):
    from url_fetcher.act_book_of_the_year import UrlFetcherACTBookOfTheYearAward

    fetcher = UrlFetcherACTBookOfTheYearAward()
    official_index = '''
      <main>
        <a href="/find/history/frequentlyaskedquestions/Events/literaryawards/book_of_the_year/2025">2025 ACT Book of the Year</a>
      </main>
    '''
    official_2025 = '''
      <main>
        <h1>2025 ACT Book of the Year</h1>
        <h2>Shortlist</h2>
        <p>Sarah Ayoub <a href="/catalogue/lebanon-days">Lebanon Days</a></p>
      </main>
    '''
    wiki_html = '''
      <table>
        <tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr>
        <tr><td>2025</td><td>Darren Rix &amp; Craig Cormick</td><td>Warra Warra Wai</td><td>Winner</td></tr>
        <tr><td></td><td>Sarah Ayoub</td><td>Lebanon Days</td><td>Highly Commended</td></tr>
      </table>
    '''
    calls = []

    def fetch_url(url):
      calls.append(url)
      if url == fetcher.URL:
        return official_index
      if url.endswith('/2025'):
        return official_2025
      if url == fetcher.WIKIPEDIA_URL:
        return wiki_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual([
      ('2025', 'Warra Warra Wai', 'winner'),
      ('2025.01', 'Lebanon Days', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertEqual([fetcher.URL, fetcher.URL + '/2025', fetcher.WIKIPEDIA_URL], calls)
    self.assertFalse(parsed['match_series'])

    calls.clear()
    official_only = fetcher.fetch_and_parse(fetch_url, source_choice=0)
    self.assertEqual(['Lebanon Days'], [entry['title'] for entry in official_only['entries']])
    self.assertEqual([fetcher.URL, fetcher.URL + '/2025'], calls)

    calls.clear()
    disabled = fetcher.fetch_and_parse(fetch_url, disable_fallbacks=True)
    self.assertEqual(['Lebanon Days'], [entry['title'] for entry in disabled['entries']])
    self.assertEqual([fetcher.URL, fetcher.URL + '/2025'], calls)

    calls.clear()
    wikipedia = fetcher.fetch_and_parse(fetch_url, source_choice=1)
    self.assertEqual(['Warra Warra Wai', 'Lebanon Days'], [
      entry['title'] for entry in wikipedia['entries']
    ])
    self.assertEqual([fetcher.WIKIPEDIA_URL], calls)

  def test_act_book_of_the_year_fetcher_metadata_and_registry(self):
    from parser.base import CATEGORY_REGIONAL_NATIONAL_AWARDS
    from url_fetcher import available_url_fetchers
    from url_fetcher.act_book_of_the_year import UrlFetcherACTBookOfTheYearAward

    fetcher = UrlFetcherACTBookOfTheYearAward()

    self.assertEqual('act_book_of_the_year_award', fetcher.source_id)
    self.assertEqual('ACT Book of the Year Award', fetcher.NAME)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual(
      [CATEGORY_REGIONAL_NATIONAL_AWARDS],
      [item['label'] for item in fetcher.get_filter_list()])
    self.assertEqual((
      {'label': 'Automatic', 'value': 'automatic'},
      {'label': 'Libraries ACT', 'value': 0},
      {'label': 'Wikipedia', 'value': 1},
    ), fetcher.source_choices())

    registry_ids = [recipe.source_id for recipe in available_url_fetchers()]
    self.assertIn('act_book_of_the_year_award', registry_ids)
    self.assertLess(
      registry_ids.index('south_australian_literary_awards_young_adult'),
      registry_ids.index('act_book_of_the_year_award'))
    self.assertLess(
      registry_ids.index('act_book_of_the_year_award'),
      registry_ids.index('writers_trust_atwood_gibson_fiction'))

  def test_james_tait_black_fiction_winner_archive(self):
    from parser.james_tait_black import JamesTaitBlackOfficialParser

    html = '''
      <ul>
        <li><a href="/winners/fiction/headshot">Rita Bullwinkel - Headshot (Daunt Books) - 2024</a></li>
        <li>Jenny Erpenbeck, translated by Michael Hofmann - Kairos (Granta) - 2023</li>
        <li>Joint Award: Graham Swift - Last Orders (Picador Macmillan) and Alice Thompson - Justine (Canongate) - 1996</li>
      </ul>
    '''

    parsed = JamesTaitBlackOfficialParser(
      'Fiction', ('Leading fiction', 'Fiction')).parse(
        html,
        'https://james-tait-black.ed.ac.uk/winners/fiction',
        'James Tait Black Prize - Fiction')

    self.assertEqual([
      ('1996', 'Last Orders', 'Graham Swift', 'winner'),
      ('1996', 'Justine', 'Alice Thompson', 'winner'),
      ('2023', 'Kairos', 'Jenny Erpenbeck', 'winner'),
      ('2024', 'Headshot', 'Rita Bullwinkel', 'winner'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertTrue(all(entry['category'] == 'Fiction' for entry in parsed['entries']))

  def test_james_tait_black_biography_winner_archive_splits_joint_rows(self):
    from parser.james_tait_black import JamesTaitBlackOfficialParser

    html = '''
      <ul>
        <li>Iman Mersal, translated by Robin Moger - Traces of Enayat (And Other Stories) and Ian Penman - Fassbinder: Thousands of Mirrors (Fitzcarraldo Editions) - 2023</li>
        <li>Andrea Wulf - Magnificent Rebels (John Murray) - 2022</li>
      </ul>
    '''

    parsed = JamesTaitBlackOfficialParser(
      'Biography', ('Lives reimagined', 'Biography')).parse(
        html,
        'https://james-tait-black.ed.ac.uk/winners/biography',
        'James Tait Black Prize - Biography')

    self.assertEqual([
      ('2022', 'Magnificent Rebels', 'Andrea Wulf'),
      ('2023', 'Traces of Enayat', 'Iman Mersal'),
      ('2023', 'Fassbinder: Thousands of Mirrors', 'Ian Penman'),
    ], [
      (entry['position'], entry['title'], entry['author'])
      for entry in parsed['entries']
    ])
    self.assertTrue(all(entry['result'] == 'winner' for entry in parsed['entries']))

  def test_james_tait_black_official_shortlist_supplement(self):
    from parser.james_tait_black import (
      SHORTLIST_URL_2026,
      JamesTaitBlackOfficialParser,
    )

    winner_html = '''
      <ul>
        <li>Nell Stevens - The Original (Scribner) - 2025</li>
      </ul>
    '''
    shortlist_html = '''
      <html><body>
        <p>This article was published on Wednesday 18 March 2026</p>
        <h2>Leading fiction</h2>
        <p>In the fiction category, Claire-Louise Bennett’s Big Kiss, Bye Bye (Fitzcarraldo Editions) follows a woman on a journey.</p>
        <p>In Jackie Ess’s Darryl (Divided Publishing), a protagonist heads west.</p>
        <p>An East London housing office is the setting of Shady Lewis’s On the Greenwich Line (Peirene Press), translated by Katharine Halls.</p>
        <p>Vivek Shanbhag’s Sakina's Kiss, translated by Srinath Perur (Faber &amp; Faber), follows two families.</p>
        <p>Nell Stevens’s The Original (Scribner) tells a story about art.</p>
        <h2>Lives reimagined</h2>
        <p>The Biography shortlist features Marlene Daut’s The First and Last King of Haiti (Yale University Press), a revolutionary life.</p>
      </body></html>
    '''

    fiction = JamesTaitBlackOfficialParser(
      'Fiction', ('Leading fiction', 'Fiction')).parse(
        winner_html,
        'https://james-tait-black.ed.ac.uk/winners/fiction',
        'James Tait Black Prize - Fiction',
        shortlist_pages=((SHORTLIST_URL_2026, shortlist_html),))
    biography = JamesTaitBlackOfficialParser(
      'Biography', ('Lives reimagined', 'Biography')).parse(
        '<ul></ul>',
        'https://james-tait-black.ed.ac.uk/winners/biography',
        'James Tait Black Prize - Biography',
        shortlist_pages=((SHORTLIST_URL_2026, shortlist_html),))

    self.assertEqual([
      ('2025', 'The Original', 'Nell Stevens', 'winner'),
      ('2025.01', 'Big Kiss, Bye Bye', 'Claire-Louise Bennett', 'shortlisted'),
      ('2025.02', 'Darryl', 'Jackie Ess', 'shortlisted'),
      ('2025.03', 'On the Greenwich Line', 'Shady Lewis', 'shortlisted'),
      ('2025.04', "Sakina's Kiss", 'Vivek Shanbhag', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in fiction['entries']
    ])
    self.assertEqual([
      ('2025.01', 'The First and Last King of Haiti', 'Marlene Daut', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in biography['entries']
    ])

  def test_james_tait_black_fetchers_metadata_and_parse_smoke(self):
    from parser.base import (
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_NONFICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
    )
    from url_fetcher.james_tait_black import (
      SHORTLIST_URL_2026,
      UrlFetcherJamesTaitBlackBiography,
      UrlFetcherJamesTaitBlackFiction,
    )

    fiction = UrlFetcherJamesTaitBlackFiction()
    biography = UrlFetcherJamesTaitBlackBiography()

    self.assertEqual('james_tait_black_fiction', fiction.source_id)
    self.assertEqual('james_tait_black_biography', biography.source_id)
    self.assertFalse(fiction.options['match_series'])
    self.assertFalse(biography.options['match_series'])
    self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fiction.source_choices())

    fiction_filters = [item['label'] for item in fiction.get_filter_list()]
    biography_filters = [item['label'] for item in biography.get_filter_list()]
    self.assertIn(CATEGORY_LITERARY_GENERAL_FICTION, fiction_filters)
    self.assertIn(CATEGORY_NONFICTION, biography_filters)
    self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, fiction_filters)
    self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, biography_filters)

    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if url == fiction.URL:
        return '<ul><li>Rita Bullwinkel - Headshot (Daunt Books) - 2024</li></ul>'
      if url == SHORTLIST_URL_2026:
        return '<p>This article was published on Wednesday 18 March 2026</p>'
      self.fail(url)

    parsed = fiction.fetch_and_parse(fetch_url)

    self.assertEqual('James Tait Black Prize - Fiction', parsed['name'])
    self.assertEqual(['Headshot'], [entry['title'] for entry in parsed['entries']])
    self.assertFalse(parsed['match_series'])
    self.assertEqual([fiction.URL, SHORTLIST_URL_2026], fetched)

  def test_writers_trust_history_parser_handles_author_and_translator_shapes(self):
    from parser.writers_trust import WritersTrustOfficialParser

    html = '''
      <main>
        <h3>2023</h3>
        <h4>Finalists</h4>
        <h5><a href="/books/standing-heavy">Standing Heavy</a></h5>
        <h6>GauZ'</h6>
        <p>Translated by Frank Wynne</p>
        <h3>2024</h3>
        <h4>Winner</h4>
        <h5><a href="/books/fire-weather">Fire Weather</a></h5>
        <h6>John Vaillant</h6>
        <h4>Finalists</h4>
        <h5><a href="/books/ordinary-notes">Ordinary Notes</a></h5>
        <h6>Christina Sharpe</h6>
        <h5><a href="/books/rediscovery">The Rediscovery of America</a></h5>
        <h6>Ned Blackhawk</h6>
        <h6>Rita Wong</h6>
        <p>Published by Example Press</p>
      </main>
    '''

    parsed = WritersTrustOfficialParser(
      "Hilary Weston Writers' Trust Prize for Nonfiction",
      'Nonfiction',
      ('Nonfiction', 'Non-fiction')).parse(
        html,
        'https://www.writerstrust.com/writers-books/awards/hilary-weston',
        "Writers' Trust - Hilary Weston Nonfiction Prize")

    self.assertEqual([
      ('2023.01', 'Standing Heavy', "GauZ'", 'shortlisted'),
      ('2024', 'Fire Weather', 'John Vaillant', 'winner'),
      ('2024.01', 'Ordinary Notes', 'Christina Sharpe', 'shortlisted'),
      ('2024.02', 'The Rediscovery of America', 'Ned Blackhawk & Rita Wong', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertTrue(all(entry['category'] == 'Nonfiction' for entry in parsed['entries']))
    self.assertTrue(all(
      entry['award'] == "Hilary Weston Writers' Trust Prize for Nonfiction"
      for entry in parsed['entries']))

  def test_writers_trust_current_page_ignores_future_date_sections(self):
    from parser.writers_trust import WritersTrustOfficialParser

    html = '''
      <main>
        <h2>2026 Important Dates</h2>
        <p>Finalists announced on September 16, 2026.</p>
        <h2>2025 Winner</h2>
        <h3><a href="/books/old-school">Old School, New World</a></h3>
        <p>Kevin Hardcastle</p>
        <h2>2025 Finalists</h2>
        <h3><a href="/books/black-sea">Black Sea</a></h3>
        <p>David A. Robertson</p>
      </main>
    '''

    parsed = WritersTrustOfficialParser(
      "Atwood Gibson Writers' Trust Fiction Prize",
      'Fiction',
      ('Fiction',)).parse(
        html,
        'https://www.writerstrust.com/awards/atwood-gibson-writers-trust-fiction-prize',
        "Writers' Trust - Atwood Gibson Fiction Prize")

    self.assertEqual([
      ('2025', 'Old School, New World', 'Kevin Hardcastle', 'winner'),
      ('2025.01', 'Black Sea', 'David A. Robertson', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])
    self.assertEqual({'2025'}, {entry['award_year'] for entry in parsed['entries']})

  def test_writers_trust_current_page_supplement_dedupes_winner(self):
    from parser.writers_trust import WritersTrustOfficialParser

    history_html = '''
      <h3>2026</h3>
      <h4>Finalists</h4>
      <h5><a href="/books/a-good-war">A Good War</a></h5>
      <h6>Seth Klein</h6>
    '''
    current_html = '''
      <h2>2026 Winner</h2>
      <h3><a href="/books/a-good-war">A Good War</a></h3>
      <p>Seth Klein</p>
      <h2>2026 Finalists</h2>
      <h3><a href="/books/the-common-good">The Common Good</a></h3>
      <p>Jane Doe &amp; John Roe</p>
    '''

    parsed = WritersTrustOfficialParser(
      'Shaughnessy Cohen Prize for Political Writing',
      'Political Writing',
      ('Political Writing',),
      current_url='https://www.writerstrust.com/awards/shaughnessy').parse(
        history_html,
        'https://www.writerstrust.com/writers-books/awards/shaughnessy',
        "Writers' Trust - Shaughnessy Cohen Political Writing Prize",
        current_pages=(('https://www.writerstrust.com/awards/shaughnessy', current_html),))

    self.assertEqual([
      ('2026', 'A Good War', 'Seth Klein', 'winner'),
      ('2026.01', 'The Common Good', 'Jane Doe & John Roe', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])

  def test_writers_trust_tied_winners_share_base_position(self):
    from parser.writers_trust import WritersTrustOfficialParser

    html = '''
      <h3>2024</h3>
      <h4>Winners</h4>
      <h5><a href="/books/policy-one">Policy One</a></h5>
      <h6>Alex Writer</h6>
      <h5><a href="/books/policy-two">Policy Two</a></h5>
      <h6>Blair Writer</h6>
      <h4>Finalists</h4>
      <h5><a href="/books/policy-three">Policy Three</a></h5>
      <h6>Casey Writer</h6>
    '''

    parsed = WritersTrustOfficialParser(
      'Balsillie Prize for Public Policy',
      'Public Policy',
      ('Public Policy',)).parse(
        html,
        'https://www.writerstrust.com/writers-books/awards/balsillie',
        "Writers' Trust - Balsillie Prize for Public Policy")

    self.assertEqual([
      ('2024', 'Policy One', 'winner'),
      ('2024', 'Policy Two', 'winner'),
      ('2024.01', 'Policy Three', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['result'])
      for entry in parsed['entries']
    ])

  def test_writers_trust_fetchers_metadata_and_parse_smoke(self):
    from parser.base import (
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_NONFICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
    )
    from url_fetcher.writers_trust import (
      UrlFetcherWritersTrustAtwoodGibsonFiction,
      UrlFetcherWritersTrustBalsilliePublicPolicy,
      UrlFetcherWritersTrustHilaryWestonNonfiction,
      UrlFetcherWritersTrustShaughnessyCohenPoliticalWriting,
    )

    fetchers = (
      (UrlFetcherWritersTrustAtwoodGibsonFiction(), CATEGORY_LITERARY_GENERAL_FICTION),
      (UrlFetcherWritersTrustHilaryWestonNonfiction(), CATEGORY_NONFICTION),
      (UrlFetcherWritersTrustBalsilliePublicPolicy(), CATEGORY_NONFICTION),
      (UrlFetcherWritersTrustShaughnessyCohenPoliticalWriting(), CATEGORY_NONFICTION),
    )

    expected_ids = {
      'writers_trust_atwood_gibson_fiction',
      'writers_trust_hilary_weston_nonfiction',
      'writers_trust_balsillie_public_policy',
      'writers_trust_shaughnessy_cohen_political_writing',
    }
    self.assertEqual(expected_ids, {fetcher.source_id for fetcher, _filter in fetchers})

    for fetcher, expected_filter in fetchers:
      with self.subTest(fetcher=fetcher.source_id):
        filters = [item['label'] for item in fetcher.get_filter_list()]
        self.assertIn(expected_filter, filters)
        self.assertIn(CATEGORY_REGIONAL_NATIONAL_AWARDS, filters)
        self.assertFalse(fetcher.options['match_series'])
        self.assertEqual(({'label': 'Automatic', 'value': 'automatic'},), fetcher.source_choices())

    fetcher = UrlFetcherWritersTrustAtwoodGibsonFiction()
    history_html = '''
      <h3>2025</h3>
      <h4>Winner</h4>
      <h5><a href="/books/history-winner">History Winner</a></h5>
      <h6>A. Writer</h6>
    '''
    fetched = []

    def fail_current(url):
      fetched.append(url)
      if url == fetcher.URL:
        return history_html
      if url == fetcher.CURRENT_URL:
        raise RuntimeError('current page unavailable')
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fail_current)

    self.assertEqual("Writers' Trust - Atwood Gibson Fiction Prize", parsed['name'])
    self.assertEqual(['History Winner'], [entry['title'] for entry in parsed['entries']])
    self.assertFalse(parsed['match_series'])
    self.assertEqual([fetcher.URL, fetcher.CURRENT_URL], fetched)
    self.assertIn('current award page could not be fetched', parsed['notes'][0])

  def test_walter_scott_official_pdf_text_parses_smoke_years(self):
    from parser.walter_scott import WalterScottOfficialParser

    text = '''
      2010
      Winner
      Wolf Hall by Hilary Mantel (Fourth Estate)
      Shortlist
      The Glass Room by Simon Mawer (Little, Brown)

      2021
      Winner
      The Mirror and the
      Light by Hilary Mantel (Fourth Estate)
      Shortlist
      The Dictionary of Lost Words by Pip Williams (Chatto & Windus)

      2024 Winner Hungry Ghosts by Kevin Jared Hosein (Bloomsbury)
      Shortlist
      Act of Oblivion by Robert Harris (Hutchinson Heinemann)

      2025
      Winner
      The Land in Winter by Andrew Miller (Sceptre)
      Longlist
      This Should Not Import by Long List Author (Example Press)
    '''

    parsed = WalterScottOfficialParser().parse(text)

    by_title = {entry['title']: entry for entry in parsed['entries']}
    self.assertEqual('winner', by_title['Wolf Hall']['result'])
    self.assertEqual('2010', by_title['Wolf Hall']['position'])
    self.assertEqual('Hilary Mantel', by_title['Wolf Hall']['author'])
    self.assertEqual('The Mirror and the Light', by_title['The Mirror and the Light']['title'])
    self.assertEqual('Hilary Mantel', by_title['The Mirror and the Light']['author'])
    self.assertEqual('Kevin Jared Hosein', by_title['Hungry Ghosts']['author'])
    self.assertEqual('Andrew Miller', by_title['The Land in Winter']['author'])
    self.assertNotIn('This Should Not Import', by_title)
    self.assertTrue(all(entry['category'] == 'Historical Fiction' for entry in parsed['entries']))
    self.assertTrue(all(entry['award'] == 'Walter Scott Prize' for entry in parsed['entries']))

  def test_walter_scott_current_pages_promote_2026_winner(self):
    from parser.walter_scott import (
      RESULT_SHORTLISTED,
      RESULT_WINNER,
      SHORTLIST_URL_2026,
      WINNER_URL_2026,
      WalterScottOfficialParser,
    )

    shortlist_html = '''
      <main>
        <h1>The 2026 Shortlist</h1>
        <p>Benbecula by Graeme Macrae Burnet (Contraband)</p>
        <p>The Matchbox Girl by Alice Jolly (Bloomsbury)</p>
        <p>The Pretender by Jo Harkin (Duckworth)</p>
        <p>The Stone Door by Leonora Nattrass (Viper)</p>
        <p>The Restless Republic by Anna Keay (William Collins)</p>
      </main>
    '''
    winner_html = '''
      <article>
        <h1>Alice Jolly wins 2026 Walter Scott Prize</h1>
        <p>The Matchbox Girl by Alice Jolly (Bloomsbury)</p>
      </article>
    '''

    parsed = WalterScottOfficialParser().parse(
      '',
      current_pages=(
        (SHORTLIST_URL_2026, RESULT_SHORTLISTED, shortlist_html),
        (WINNER_URL_2026, RESULT_WINNER, winner_html),
      ))

    self.assertEqual(5, len(parsed['entries']))
    self.assertEqual([
      ('2026', 'The Matchbox Girl', 'Alice Jolly', 'winner'),
      ('2026.01', 'Benbecula', 'Graeme Macrae Burnet', 'shortlisted'),
      ('2026.02', 'The Pretender', 'Jo Harkin', 'shortlisted'),
      ('2026.03', 'The Stone Door', 'Leonora Nattrass', 'shortlisted'),
      ('2026.04', 'The Restless Republic', 'Anna Keay', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])

  def test_walter_scott_wikipedia_parser_accepts_table_fixture(self):
    from parser.walter_scott import WalterScottWikipediaParser

    html = '''
      <table>
        <tr><th>Year</th><th>Title</th><th>Author</th><th>Result</th></tr>
        <tr><td>2025</td><td>The Land in Winter</td><td>Andrew Miller</td><td>Winner</td></tr>
        <tr><td></td><td>The Voyage Home</td><td>Pat Barker</td><td>Shortlist</td></tr>
        <tr><td></td><td>Longlist Book</td><td>Other Author</td><td>Longlist</td></tr>
      </table>
    '''

    parsed = WalterScottWikipediaParser().parse(
      html, 'https://en.wikipedia.org/wiki/Walter_Scott_Prize')

    self.assertEqual([
      ('2025', 'The Land in Winter', 'Andrew Miller', 'winner'),
      ('2025.01', 'The Voyage Home', 'Pat Barker', 'shortlisted'),
    ], [
      (entry['position'], entry['title'], entry['author'], entry['result'])
      for entry in parsed['entries']
    ])

  def test_walter_scott_fetcher_metadata_source_choices_and_parse_smoke(self):
    from parser.base import (
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
    )
    from url_fetcher.walter_scott import UrlFetcherWalterScottPrize

    fetcher = UrlFetcherWalterScottPrize()

    self.assertEqual('walter_scott_prize', fetcher.source_id)
    self.assertEqual('Walter Scott Prize', fetcher.NAME)
    self.assertFalse(fetcher.options['match_series'])
    self.assertEqual([
      CATEGORY_LITERARY_GENERAL_FICTION,
      CATEGORY_REGIONAL_NATIONAL_AWARDS,
    ], [item['label'] for item in fetcher.get_filter_list()])
    self.assertEqual((
      {'label': 'Automatic', 'value': 'automatic'},
      {'label': 'Walter Scott', 'value': 0},
      {'label': 'Wikipedia', 'value': 1},
    ), fetcher.source_choices())

    official_text = '''
      2025
      Winner
      The Land in Winter by Andrew Miller (Sceptre)
    '''
    shortlist_html = '<p>The Matchbox Girl by Alice Jolly (Bloomsbury)</p>'
    winner_html = '<p>The Matchbox Girl by Alice Jolly (Bloomsbury)</p>'
    fetched = []

    def fetch_url(url):
      fetched.append(url)
      if url == fetcher.URL:
        return official_text
      if url.endswith('/the-2026-shortlist/'):
        return shortlist_html
      if 'alice-jolly-wins-2026' in url:
        return winner_html
      self.fail(url)

    parsed = fetcher.fetch_and_parse(fetch_url)

    self.assertEqual('Walter Scott Prize', parsed['name'])
    self.assertFalse(parsed['match_series'])
    self.assertIn('The Land in Winter', [entry['title'] for entry in parsed['entries']])
    self.assertIn('The Matchbox Girl', [entry['title'] for entry in parsed['entries']])
    self.assertEqual(fetcher.URL, fetched[0])

    wiki_html = '''
      <table>
        <tr><th>Year</th><th>Title</th><th>Author</th><th>Result</th></tr>
        <tr><td>2024</td><td>Hungry Ghosts</td><td>Kevin Jared Hosein</td><td>Winner</td></tr>
      </table>
    '''
    parsed_wiki = fetcher.fetch_and_parse(
      lambda url: wiki_html if url == fetcher.WIKIPEDIA_URL else self.fail(url),
      source_choice=1)

    self.assertEqual(['Hungry Ghosts'], [entry['title'] for entry in parsed_wiki['entries']])

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
