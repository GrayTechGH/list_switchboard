#!/usr/bin/env python
# Test script for Sword & Laser import with match_series=false and March Madness parsing

import json
import sys
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

# Add the project root to the path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SWORD_LASER_SCRAPS = ROOT / '_dev_tools' / 'Scraps Cache' / 'sword and laser'

# Mock the missing modules
class Dummy:
    def __init__(self, *args, **kwargs):
        pass
    def __getattr__(self, _name):
        return Dummy()
    def __call__(self, *args, **kwargs):
        return Dummy()

import types
qt = types.ModuleType('qt')
qt_core = types.ModuleType('qt.core')
for name in ('QApplication', 'QCheckBox', 'QDialog', 'QDialogButtonBox', 'QHBoxLayout',
             'QHeaderView', 'QInputDialog', 'QLabel', 'QListWidget', 'QMessageBox',
             'QProgressDialog', 'QPushButton', 'QTableWidget', 'QTableWidgetItem',
             'QSizePolicy', 'QVBoxLayout'):
    setattr(qt_core, name, Dummy)
sys.modules.setdefault('qt', qt)
sys.modules.setdefault('qt.core', qt_core)

calibre = types.ModuleType('calibre')
calibre_ebooks = types.ModuleType('calibre.ebooks')
calibre_ebooks_metadata = types.ModuleType('calibre.ebooks.metadata')
calibre_ebooks_metadata.title_sort = lambda x: x
calibre_gui2 = types.ModuleType('calibre.gui2')
calibre_gui2.error_dialog = Dummy()
calibre_gui2.question_dialog = Dummy()
calibre_utils = types.ModuleType('calibre.utils')
calibre_utils_browser = types.ModuleType('calibre.utils.browser')
calibre_utils_browser.Browser = Dummy

sys.modules.setdefault('calibre', calibre)
sys.modules.setdefault('calibre.ebooks', calibre_ebooks)
sys.modules.setdefault('calibre.ebooks.metadata', calibre_ebooks_metadata)
sys.modules.setdefault('calibre.gui2', calibre_gui2)
sys.modules.setdefault('calibre.utils', calibre_utils)
sys.modules.setdefault('calibre.utils.browser', calibre_utils_browser)

plugin_package = types.ModuleType('calibre_plugins')
list_switchboard_package = types.ModuleType('calibre_plugins.list_switchboard')
config_module = types.ModuleType('calibre_plugins.list_switchboard.config')
config_module.prefs = {}
sys.modules.setdefault('calibre_plugins', plugin_package)
sys.modules.setdefault('calibre_plugins.list_switchboard', list_switchboard_package)
sys.modules.setdefault('calibre_plugins.list_switchboard.config', config_module)

# Now import the modules
from parser import sword_and_laser as sword_parser
from url_fetcher.sword_and_laser import UrlFetcherSwordAndLaser


def entry_author(entry):
    return ' & '.join(entry.get('authors') or [])


def source_entry(position, title, author, source_url=''):
    entry = {'position': position, 'title': title, 'authors': [author]}
    if source_url:
        entry['source'] = {'url': source_url}
    return entry


def entry_source_url(entry):
    return (entry.get('source') or {}).get('url', '')


def test_sword_and_laser_position_accepts_decimal_zero():
    """Positions like 2.0 should be treated as whole-number picks instead of missing."""
    print("Testing Sword & Laser position parsing for decimal-zero positions...")

    assert sword_parser.sword_and_laser_position('2.0') == '2'
    assert sword_parser.sword_and_laser_position('2.00') == '2'
    assert sword_parser.sword_and_laser_position('2.') == '2'
    assert sword_parser.sword_and_laser_position('2.06') == '2.06'

    print("PASS: Sword & Laser position decimal-zero parsing test passed!")


def test_sword_and_laser_match_series():
    """Test that Sword & Laser recipe parsing includes all entries (filtering happens during matching)"""
    print("Testing Sword & Laser parsing (match_series affects matching, not parsing)...")

    recipe = UrlFetcherSwordAndLaser()
    recipe.options = {**recipe.options, 'include_march_madness': False}

    # Test HTML with both series and individual books
    html = '''
    <table>
      <tr><th>Title</th><th>Author(s)</th><th>Publisher</th><th>Month Read</th><th>Seq</th></tr>
      <tr>
        <td><a href="/wiki/The_Invisible_Library">The Invisible Library</a></td>
        <td>Genevieve Cogman</td>
        <td>Pan Macmillan</td>
        <td>Apr 2017</td>
        <td>95</td>
      </tr>
      <tr>
        <td><a href="/wiki/American_Gods">American Gods</a></td>
        <td>Neil Gaiman</td>
        <td>William Morrow</td>
        <td>Jun 2011</td>
        <td>1</td>
      </tr>
      <tr>
        <td><a href="/wiki/Anansi_Boys">Anansi Boys</a></td>
        <td>Neil Gaiman</td>
        <td>William Morrow</td>
        <td>Aug 2011</td>
        <td>2</td>
      </tr>
    </table>
    '''

    parsed = sword_parser.parse_sword_and_laser_book_list(recipe, html)

    print(f"Parsed {len(parsed['entries'])} entries:")
    for entry in parsed['entries']:
        print(f"  - {entry['title']} by {entry_author(entry)} (pos: {entry['position']})")

    # Parsing should include all individual books (series filtering happens during matching)
    titles = [entry['title'] for entry in parsed['entries']]
    assert 'The Invisible Library' in titles, "Should include individual book"
    assert 'American Gods' in titles, "Should include individual book"
    assert 'Anansi Boys' in titles, "Should include individual book (matching controlled by match_series flag)"

    # Check that match_series flag is set to false
    assert recipe.options.get('match_series') == False, "match_series should be False"

    print("PASS: Sword & Laser parsing test passed!")


def test_incremental_sword_and_laser_pages_include_new_and_pending():
    """Saved imports should revisit only new and explicitly unfinished linked pages."""
    cached = [
        source_entry('1', 'Old Pick', 'Old Author',
                     'https://swordandlaser.fandom.com/wiki/Old_Pick'),
        source_entry('1.01', 'Old Nominee', 'Old Author'),
    ]
    main_entries = [
        dict(cached[0]),
        source_entry('2', 'New Pick', 'New Author',
                     'https://swordandlaser.fandom.com/wiki/New_Pick'),
    ]

    merged, pages = sword_parser.merge_incremental_sword_and_laser_entries(
        main_entries, cached, {
            'incremental_state': {
                'pending_page_urls': [entry_source_url(cached[0])],
            },
        })

    assert [entry['title'] for entry in merged] == ['Old Pick', 'Old Nominee', 'New Pick']
    assert [entry['title'] for entry in pages] == ['Old Pick', 'New Pick']

    print("PASS: Sword & Laser incremental page selection test passed!")


def test_sword_and_laser_fetcher_passes_incremental_cache_to_parser():
    """The shared fetcher contract must carry the selected cache mode to Sword & Laser."""
    recipe = UrlFetcherSwordAndLaser()
    recipe.options = {**recipe.options, 'include_march_madness': False}
    cached = {
        'entries': [source_entry(
            '1', 'Old Pick', 'Old Author',
            'https://swordandlaser.fandom.com/wiki/Old_Pick')],
    }
    html = '''
    <table>
      <tr><th>Title</th><th>Author(s)</th><th>Publisher</th><th>Month Read</th><th>Seq</th></tr>
      <tr><td><a href="/wiki/Old_Pick">Old Pick</a></td><td>Old Author</td><td>Pub</td><td>Jan 2025</td><td>1</td></tr>
      <tr><td><a href="/wiki/New_Pick">New Pick</a></td><td>New Author</td><td>Pub</td><td>Feb 2025</td><td>2</td></tr>
    </table>
    '''

    parsed = recipe.fetch_and_parse(
        lambda _url: html,
        cached_parsed=cached,
        incremental_update=True)

    assert [entry['title'] for entry in parsed['entries']] == ['Old Pick', 'New Pick']
    print("PASS: Sword & Laser fetcher incremental-cache forwarding test passed!")

def test_march_madness_parsing():
    """Test March Madness parsing with the Invisible Library page"""
    print("\nTesting March Madness parsing...")

    # Load the saved Invisible Library JSON
    json_path = SWORD_LASER_SCRAPS / 'mm.The Invisible Library.json'
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    html = data['parse']['text']['*']
    soup = BeautifulSoup(html, 'html.parser')

    # Create a mock official entry
    official_entry = source_entry('95', 'The Invisible Library', 'Genevieve Cogman')

    nominations = sword_parser.parse_sword_and_laser_march_page(soup, official_entry)

    print(f"Found {len(nominations)} nominations:")
    for nom in nominations[:5]:  # Show first 5
        print(f"  - {nom['title']} by {entry_author(nom)} ({nom['votes']} votes, {nom['percent']})")

    # Should find nominations including "The Invisible Library" itself
    titles = [nom['title'] for nom in nominations]
    assert 'The Invisible Library' in titles, "Should find the main book in nominations"
    assert len(nominations) > 10, f"Should find many nominations, got {len(nominations)}"

    print("PASS: March Madness parsing test passed!")


def test_march_madness_aurora_page():
    """Test March Madness parsing for Aurora-style table rows with bare numeric percentages."""
    print("\nTesting Aurora March Madness table parsing...")

    json_path = SWORD_LASER_SCRAPS / 'mm.Aurora.json'
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    html = data['parse']['text']['*']
    soup = BeautifulSoup(html, 'html.parser')
    rows = sword_parser.parse_sword_and_laser_march_table_rows(soup)

    print(f"Found {len(rows)} rows")
    for row in rows:
        print(f"  - {row}")

    assert len(rows) == 4, f"Expected 4 nomination rows, got {len(rows)}"
    assert any(title == 'Aurora' for _, _, title, _ in rows), "Should include Aurora row"
    assert any(title == 'Planetfall' for _, _, title, _ in rows), "Should include Planetfall row"

    print("PASS: Aurora parsing regression test passed!")

def test_march_madness_childhoods_end():
    """Test March Madness parsing for Childhood's End poll page"""
    print("\nTesting Childhood's End March Madness poll parsing...")

    json_path = SWORD_LASER_SCRAPS / "mm.Childhood's End.json"
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    html = data['parse']['text']['*']
    soup = BeautifulSoup(html, 'html.parser')

    official_entry = source_entry('5', "Childhood's End", 'Arthur C. Clarke')

    nominations = sword_parser.parse_sword_and_laser_march_page(soup, official_entry)

    print(f"Found {len(nominations)} nominations for Childhood's End:")
    for nom in nominations:
        print(f"  - {nom['title']} by {entry_author(nom)}")

    assert len(nominations) == 3
    titles = [nom['title'] for nom in nominations]
    assert 'Rendezvous with Rama' in titles
    assert '2001: A Space Odyssey' in titles
    assert 'The Songs of Distant Earth' in titles
    for nom in nominations:
        assert entry_author(nom) == 'Arthur C. Clarke'

    print("PASS: Childhood's End poll parsing test passed!")


def test_march_madness_the_fifth_season_reassembly():
    """Regression test for The Fifth Season vote line reassembly"""
    print("\nTesting The Fifth Season March Madness reassembly...")

    json_path = SWORD_LASER_SCRAPS / 'mm.The Fifth Season.json'
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    html = data['parse']['text']['*']
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text('\n', strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    vote_lines = sword_parser.first_round_vote_lines(lines)

    print(f"Found {len(vote_lines)} vote lines")
    for line in vote_lines:
        print(f"  - {line}")

    assert len(vote_lines) == 16
    assert vote_lines[0] == '106 votes 51.5% The Fifth Season by N.K. Jemisin'
    assert vote_lines[1] == '100 votes 48.5% Neverwhere by Neil Gaiman'
    assert '110 votes 60.4% The Mirror Empire by Kameron Hurley' in vote_lines
    assert '100 votes 53.8% Prince of Fools by Mark Lawrence' in vote_lines
    assert all(sword_parser.parse_vote_line(line) for line in vote_lines)

    print("PASS: The Fifth Season reassembly test passed!")


def test_march_madness_enders_game_poll_text():
    """Regression test for Ender's Game poll text parsing to avoid false positives"""
    print("\nTesting Ender's Game March Madness poll text parsing...")

    json_path = SWORD_LASER_SCRAPS / 'mm.Ender\'s Game.json'
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    html = data['parse']['text']['*']
    soup = BeautifulSoup(html, 'html.parser')

    official_entry = source_entry('2', "Ender's Game", 'Orson Scott Card')

    nominations = sword_parser.parse_sword_and_laser_march_page(soup, official_entry)

    print(f"Found {len(nominations)} nominations for Ender's Game:")
    for nom in nominations:
        print(f"  - {nom['title']} by {entry_author(nom)}")

    assert len(nominations) == 4
    titles = [nom['title'] for nom in nominations]
    assert 'Childhood\'s End' in titles
    assert 'Dune' in titles
    assert 'Radio Free Albemuth' in titles
    assert 'I, Robot' in titles
    # Ensure no false positives from description text
    for nom in nominations:
        assert 'Ender' not in nom['title']
        assert 'develop a secure defense' not in nom['title']
        assert 'Nebula Award' not in nom['title']

    print("PASS: Ender's Game poll text parsing test passed!")


def test_march_madness_unshapely_things():
    """Test March Madness parsing for Unshapely Things poll page"""
    print("\nTesting Unshapely Things March Madness parsing...")

    json_path = SWORD_LASER_SCRAPS / 'mm.Unshapely Things.json'
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    html = data['parse']['text']['*']
    soup = BeautifulSoup(html, 'html.parser')

    official_entry = source_entry('6', 'Unshapely Things', 'Mark Del Franco')

    nominations = sword_parser.parse_sword_and_laser_march_page(soup, official_entry)

    print(f"Found {len(nominations)} nominations for Unshapely Things")

    assert len(nominations) == 4
    assert nominations[0]['title'] == 'Wicked Lovely'
    assert nominations[1]['title'] == 'Fablehaven'
    assert nominations[2]['title'] == 'War for the Oaks'
    assert nominations[3]['title'] == "Ironside:A Modern Faery's Tale"
    assert entry_author(nominations[0]) == 'Melissa Marr'
    assert entry_author(nominations[1]) == 'Brandon Mull'
    assert entry_author(nominations[2]) == 'Emma Bull'
    assert entry_author(nominations[3]) == 'Holly Black'

    print("PASS: Unshapely Things parsing test passed!")


def test_march_madness_doomsday_book():
    """Test March Madness parsing for Doomsday Book with quoted author placeholders"""
    print("\nTesting Doomsday Book March Madness parsing...")

    json_path = SWORD_LASER_SCRAPS / 'mm.Doomsday Book.json'
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    html = data['parse']['text']['*']
    soup = BeautifulSoup(html, 'html.parser')

    official_entry = source_entry('102', 'Doomsday Book', 'Connie Willis')

    nominations = sword_parser.parse_sword_and_laser_march_page(soup, official_entry)

    print(f"Found {len(nominations)} nominations for Doomsday Book")
    for nom in nominations:
        print(f"  - {nom['title']} by {entry_author(nom)}")

    assert len(nominations) == 4
    assert entry_author(nominations[1]) == 'Connie Willis'
    assert entry_author(nominations[2]) == 'Connie Willis'
    assert entry_author(nominations[3]) == 'Connie Willis'
    assert nominations[1]['title'] == 'To Say Nothing of the Dog'
    assert nominations[2]['title'] == 'Blackout/All Clear'
    assert nominations[3]['title'] == 'Fire Watch'

    print("PASS: Doomsday Book parsing test passed!")


def test_march_madness_dawn():
    """Test March Madness parsing for Dawn with quoted author placeholders"""
    print("\nTesting Dawn March Madness parsing...")

    json_path = SWORD_LASER_SCRAPS / 'mm.Dawn.json'
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    html = data['parse']['text']['*']
    soup = BeautifulSoup(html, 'html.parser')

    official_entry = source_entry('62', 'Dawn', 'Octavia E. Butler')

    nominations = sword_parser.parse_sword_and_laser_march_page(soup, official_entry)

    print(f"Found {len(nominations)} nominations for Dawn")
    for nom in nominations:
        print(f"  - {nom['title']} by {entry_author(nom)}")

    assert len(nominations) == 5
    assert all(entry_author(nom) == 'Octavia E. Butler' for nom in nominations)
    assert nominations[1]['title'] == 'Kindred'
    assert nominations[2]['title'] == 'Parable of the Sower'
    assert nominations[3]['title'] == 'Wild Seed'
    assert nominations[4]['title'] == 'Fledgling'

    print("PASS: Dawn parsing test passed!")

class SwordAndLaserRegressionTests(unittest.TestCase):
    """Keep the historical regression functions discoverable by unittest."""


for _name, _function in tuple(globals().items()):
    if _name.startswith('test_') and callable(_function):
        setattr(SwordAndLaserRegressionTests, _name, staticmethod(_function))
del _name, _function


if __name__ == '__main__':
    unittest.main()
