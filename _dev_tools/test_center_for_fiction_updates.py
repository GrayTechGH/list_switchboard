import copy
import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import without_unit
from errors import ImportCancelledError, CamoufoxRequiredError
from parser.center_for_fiction import CenterForFictionFirstNovelOfficialParser
from parser.center_for_fiction_sources import annual_url, discover_links, WINNERS_URL
from storage import build_import_cache_data
from url_fetcher.center_for_fiction import UrlFetcherCenterForFictionFirstNovelPrize


class CenterForFictionUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe = UrlFetcherCenterForFictionFirstNovelPrize(); self.recipe.FIRST_YEAR = 2024
    self.years, self.winner_years = [2024, 2025, 2026], [2024, 2025]
    self.calls, self.errors, self.overrides = [], {}, {}
    self.promoted, self.changed = set(), ''
    clock = patch('parser.center_for_fiction_updates.datetime')
    clock.start().datetime.now.return_value.year = 2026; self.addCleanup(clock.stop)

  def url(self, year, suffix=''):
    return f'https://centerforfiction.org/book-recs/{year}-first-novel-prize{suffix}/'

  def shell(self, title, content):
    return f'<main><article class="editorial"><header><h1>{title}</h1></header>{content}</article><section><h2>Discover our Book Recs</h2><h3>Wrong Recommendation</h3><p>By Wrong Writer</p><p>Winner</p></section></main>'

  def card(self, year, book, stage, history=False, author='Byron Writer, Jr.'):
    marker = f'<strong>{year} Winner</strong><br><a href="{self.url(year)}">View all shortlisted and longlisted titles from {year}.</a>' if history else f'<strong>{stage}</strong>'
    return f'''<li class="featured-books-item"><h3>{book} {year}{self.changed}</h3><p class="detail">By {author}</p>
      <p class="detail">Published by Press</p><div class="rich-text"><p>{marker}</p>
      <p>Synopsis mentioning a winner</p><p><strong>Winner</strong></p></div></li>'''

  def cards(self, cards, heading=''):
    return f'<div class="featured-books">{f"<h2>{heading}</h2>" if heading else ""}<ol>{cards}</ol></div>'

  def landing(self):
    links = ''.join(f'<a href="{self.url(y)}">{y} First Novel Prize</a>' for y in self.years if y > self.recipe.FIRST_YEAR)
    links += f'<a href="{self.url(max(self.years), "-shortlist")}">Current shortlist</a>'
    return self.shell('First Novel Prize', '<h2>Browse All Winners &amp; Finalists</h2>' + links)

  def history(self):
    return self.shell('First Novel Prize Winners: The Complete List', self.cards(''.join(
      self.card(y, 'Other' if y in self.promoted else 'Book of Hours', 'Winner', history=True) for y in self.winner_years)))

  def annual(self, year, shortlist=False):
    closed = year in self.winner_years
    if not closed and not shortlist:
      return self.shell(f'Announcing {year} First Novel Prize Longlist', self.cards(self.card(year, 'Wrong Longlist', 'Longlisted'), f'{year} Longlist'))
    first = 'shortlisted' if shortlist or not closed or year in self.promoted else 'winner'
    other = 'winner' if closed and not shortlist and year in self.promoted else 'shortlisted'
    cards = self.card(year, 'Book of Hours', first) + self.card(year, 'Other', other)
    return self.shell(f'{year} First Novel Prize' + (' Shortlist' if shortlist else ''), self.cards(cards) +
      '<div class="people"><h2>Meet our judges and finalists</h2><h3>Wrong Biography</h3><p>By Wrong Writer</p><p>Winner</p></div>')

  def fetch(self, url, **kwargs):
    self.calls.append((url, kwargs.get('transport')))
    error = self.errors.get((url, kwargs.get('transport'))) or self.errors.get(url)
    if error: raise error
    if url in self.overrides: return self.overrides[url]
    if url == self.recipe.URL: return self.landing()
    if url == WINNERS_URL: return self.history()
    if url == self.recipe.WIKIPEDIA_URL:
      return '<table><tr><th>Year</th><th>Author</th><th>Title</th><th>Result</th></tr><tr><td>2026</td><td>Wiki Writer</td><td>Wiki Book</td><td>Winner</td></tr></table>'
    year, _canonical = annual_url(url, url)
    return self.annual(year, 'shortlist' in url)

  def parse(self, old=None, incremental=None, choice=0):
    return self.recipe.fetch_and_parse(self.fetch, source_choice=choice, cached_parsed=old,
      incremental_update=(old is not None) if incremental is None else incremental)

  def cache(self, parsed): return build_import_cache_data(self.recipe.source_id, parsed)

  def test_missing_real_historical_entries_are_restored_then_repeat_saves_fetches(self):
    full = self.parse(); self.assertEqual(6, len(full['entries'])); self.assertEqual(6, len(self.calls))
    stale = without_unit(self.cache(full), '2025'); self.assertEqual(4, len(stale['entries'])); self.calls.clear()
    updated = self.parse(stale); self.assertEqual(full['entries'], updated['entries']); self.assertEqual(5, len(self.calls))
    self.calls.clear(); self.assertEqual(full['entries'], self.parse(self.cache(updated))['entries']); self.assertEqual(4, len(self.calls))

  def test_earliest_annual_year_is_discovered_from_fresh_winner_history(self):
    parsed = self.parse(); self.assertTrue(any(row['award_year'] == '2024' for row in parsed['entries']))
    self.assertNotIn(self.url(2024), self.landing()); self.assertIn((self.url(2024), 'camoufox'), self.calls)

  def test_modern_cards_exclude_biographies_recommendations_longlists_and_prose_markers(self):
    parsed = self.parse(); self.assertFalse(any('Wrong' in row['title'] for row in parsed['entries']))
    self.assertTrue(all(row['authors'] == ['Byron Writer, Jr.'] for row in parsed['entries']))
    self.assertEqual(2, sum(row['result'] == 'winner' for row in parsed['entries']))

  def test_legacy_inline_rosters_and_year_labelled_winner_card_deduplicate(self):
    html = self.shell('2024 First Novel Prize', '''<div class="editorial-content-text"><p>Winner</p><ul><li>Book of Hours 2024 by Byron Writer, Jr. (Press)</li></ul>
      <p>Shortlist</p><ul><li>Other 2024 by Other Writer (Press)</li></ul><p>Longlist</p><ul><li>Wrong Book by Wrong Writer</li></ul></div>''' +
      self.cards(self.card(2024, 'Book of Hours', ''), '2024 Winner'))
    parsed = self.recipe.parser().read_official_source(html, self.url(2024))
    self.assertTrue(parsed['complete']); self.assertEqual(2, len(parsed['rows'])); self.assertEqual('Byron Writer, Jr.', parsed['rows'][0]['author'])

  def test_current_announcement_inline_shortlist_supplies_unmarked_cards(self):
    html = self.shell('Announcing 2026 First Novel Prize Shortlist', '''<div class="editorial-content-text"><p>Seven titles were shortlisted by judges.</p>
      <ul><li><a href="https://bookstore.centerforfiction.org/book">Book of Hours 2026</a> by Byron Writer, Jr. (Press)</li></ul></div>''' +
      self.cards(self.card(2026, 'Book of Hours', ''), '2026 Shortlist'))
    parsed = self.recipe.parser().read_official_source(html, self.url(2026, '-shortlist'))
    self.assertTrue(parsed['complete']); self.assertEqual(1, len(parsed['rows'])); self.assertEqual('shortlisted', parsed['rows'][0]['result'])

  def test_old_long_list_named_url_uses_rendered_results_not_its_slug(self):
    parsed = self.recipe.parser().read_official_source(self.annual(2025), self.url(2025, '-the-long-list'))
    self.assertTrue(parsed['complete']); self.assertEqual('winner', parsed['rows'][0]['result'])

  def test_url_aliases_suffixes_and_discovery_scope(self):
    self.assertEqual((2020, self.url(2020, '-the-long-list')), annual_url('http://www.centerforfiction.org/book-recs/2020-first-novel-prize-the-long-list/?x=1#top', self.recipe.URL))
    html = self.landing().replace('</article>', f'<nav><a href="{self.url(2000)}">Navigation</a></nav><a href="https://example.com/book-recs/2000-first-novel-prize/">Wrong host</a></article>')
    self.assertFalse(any(y == 2000 for y,url in discover_links(html, self.recipe.URL)))

  def test_new_year_discovery_and_former_current_winner_promotion(self):
    old = self.cache(self.parse()); self.years.append(2027); self.winner_years.append(2026); self.promoted.add(2026)
    updated = self.parse(old); self.assertEqual(8, len(updated['entries']))
    winner = next(row for row in updated['entries'] if row['award_year'] == '2026' and row['result'] == 'winner')
    self.assertEqual('Other 2026', winner['title'])

  def test_changed_historical_winner_revision_forces_refresh_and_replaces_old_status(self):
    old = self.cache(self.parse()); self.promoted.add(2025); self.calls.clear(); updated = self.parse(old)
    self.assertIn((self.url(2025), 'camoufox'), self.calls)
    winner = next(row for row in updated['entries'] if row['award_year'] == '2025' and row['result'] == 'winner')
    self.assertEqual('Other 2025', winner['title'])

  def test_forthcoming_empty_intake_stays_unsettled_after_rollover(self):
    self.overrides[self.url(2026, '-shortlist')] = self.annual(2026)
    old = self.cache(self.parse()); self.assertFalse(old['incremental_state']['units']['2026']['metadata']['settled'])
    self.overrides.clear(); self.years.append(2027); self.winner_years.append(2026); self.calls.clear()
    with patch('parser.center_for_fiction_updates.datetime') as clock:
      clock.datetime.now.return_value.year = 2027; updated = self.parse(old)
    self.assertIn((self.url(2026), 'camoufox'), self.calls)
    self.assertTrue(any(row['award_year'] == '2026' for row in updated['entries']))

  def test_failed_or_malformed_current_page_retains_whole_year_pending_then_recovers(self):
    old = self.cache(self.parse())
    for malformed in (False, True):
      self.errors.clear(); self.overrides.clear()
      if malformed: self.overrides[self.url(2026, '-shortlist')] = self.annual(2026, True).replace('class="detail">By ', 'class="other">By ')
      else: self.errors[self.url(2026, '-shortlist')] = RuntimeError('temporary failure')
      updated = self.parse(old); self.assertEqual(old['entries'], updated['entries']); self.assertFalse(updated['incremental_state']['units']['2026']['complete'])
    self.overrides.clear(); self.assertTrue(self.parse(self.cache(updated))['incremental_state']['units']['2026']['complete'])

  def test_failed_historical_full_import_remains_partial_and_explicitly_incomplete(self):
    self.errors[self.url(2024)] = RuntimeError('temporary failure'); parsed = self.parse()
    self.assertEqual(4, len(parsed['entries'])); self.assertFalse(parsed['incremental_state']['units']['2024']['complete']); self.assertTrue(parsed['notes'])

  def test_legacy_wrong_scope_and_complete_refresh_fetch_full_history(self):
    old = self.cache(self.parse()); corrupted = copy.deepcopy(old); corrupted['incremental_state']['source_key'] = 'wrong source'
    for cached in (dict(old, incremental_state={}), corrupted):
      self.calls.clear(); self.assertEqual(old['entries'], self.parse(cached)['entries']); self.assertEqual(6, len(self.calls))
    self.calls.clear(); self.parse(old, incremental=False); self.assertEqual(6, len(self.calls))

  def test_corrupted_cached_winner_cannot_be_reused_under_unchanged_metadata(self):
    old = self.cache(self.parse())
    for row in old['entries']:
      if row['award_year'] == '2025' and row['result'] == 'winner': row['title'] = 'Corrupt winner'
    self.calls.clear(); updated = self.parse(old)
    self.assertIn((self.url(2025), 'camoufox'), self.calls); self.assertFalse(any(row['title'] == 'Corrupt winner' for row in updated['entries']))

  def test_wrong_year_articles_and_sections_are_not_certified(self):
    with self.assertRaisesRegex(ValueError, 'another award year'):
      self.recipe.parser().read_official_source(self.annual(2025), self.url(2024))
    with self.assertRaisesRegex(ValueError, 'another award year'):
      self.recipe.parser().read_official_source(self.annual(2025).replace('2025 First Novel Prize', '2025 First Novel Prize: previous 2024 winner'), self.url(2024))
    malformed = self.annual(2024).replace('<div class="featured-books">', '<div class="featured-books"><h2>2025 Shortlist</h2>')
    self.assertFalse(self.recipe.parser().read_official_source(malformed, self.url(2024))['complete'])

  def test_incomplete_history_or_discovery_cannot_certify_dropped_years(self):
    self.overrides[WINNERS_URL] = self.history().replace(self.card(2024, 'Book of Hours', 'Winner', True), '')
    with self.assertRaisesRegex(Exception, 'missing.*award years'):
      self.parse()

  def test_critical_errors_propagate_from_root_history_and_annual_pages(self):
    for url in (self.recipe.URL, WINNERS_URL, self.url(2026, '-shortlist')):
      for error in (ImportCancelledError, CamoufoxRequiredError):
        self.errors = {url: error('stop')}
        with self.assertRaises(error): self.parse()

  def test_browser_recovery_is_attempt_local_and_wikipedia_stays_a_full_replacement(self):
    self.errors[(self.recipe.URL, 'camoufox')] = RuntimeError('browser unavailable')
    full = self.parse(); self.assertTrue(all(t is None for u,t in self.calls[1:])); self.assertEqual(self.recipe.URL, self.calls[1][0])
    self.errors.clear(); self.calls.clear(); self.parse(); self.assertTrue(all(t == 'camoufox' for u,t in self.calls))
    self.calls.clear(); parsed = self.parse(self.cache(full), choice=1)
    self.assertEqual([(self.recipe.WIKIPEDIA_URL, None)], self.calls); self.assertEqual('Wiki Book', parsed['entries'][0]['title']); self.assertNotIn('incremental_state', parsed)

  def test_fetcher_parser_contract_and_plain_name_title_prefixes(self):
    self.assertIsInstance(self.recipe.parser(), CenterForFictionFirstNovelOfficialParser)
    self.assertEqual('Book of Hours', self.recipe.parser().clean_title('Book of Hours'))
    self.assertEqual('Byron Writer, Jr.', self.recipe.parser().clean_author('By Byron Writer, Jr.'))
    self.assertEqual(('Winner Takes All', 'Byron Writer, Jr.'), self.recipe.parser().parse_text_entry('Winner Takes All by Byron Writer, Jr. (Press)'))

  def test_explicit_history_corrects_only_same_year_title_winner_author_and_keeps_source_credit(self):
    self.overrides[self.url(2025)] = self.annual(2025).replace('Byron Writer, Jr.', 'Byorn Writer, Jr.')
    parsed = self.parse()
    winner = next(row for row in parsed['entries'] if row['award_year'] == '2025' and row['result'] == 'winner')
    self.assertEqual(['Byron Writer, Jr.'], winner['authors']); self.assertEqual(WINNERS_URL, winner['author_source_url'])
    self.assertEqual('Byorn Writer, Jr.', winner['source_author_credits'][0]['author'])
    other = next(row for row in parsed['entries'] if row['award_year'] == '2025' and row['result'] == 'shortlisted')
    self.assertEqual(['Byorn Writer, Jr.'], other['authors']); self.assertNotIn('source_author_credits', other)

  def test_official_standalone_status_typo_is_narrow_and_unknown_status_remains_incomplete(self):
    for label, complete in [('Shorlisted', True), ('Unclear Label', False)]:
      html = self.annual(2025).replace('<strong>shortlisted</strong>', f'<strong>{label}</strong>')
      source = self.recipe.parser().read_official_source(html, self.url(2025))
      self.assertEqual(complete, source['complete'])

  def test_fresh_history_promotes_new_winner_and_demotes_stale_annual_winner(self):
    old = self.cache(self.parse()); old_page = self.annual(2025)
    self.promoted.add(2025); self.overrides[self.url(2025)] = old_page
    parsed = self.parse(old)
    year = [row for row in parsed['entries'] if row['award_year'] == '2025']
    self.assertEqual(2, len(year)); self.assertEqual('Other 2025', next(row['title'] for row in year if row['result'] == 'winner'))
    self.assertTrue(all(row['result_source_url'] == WINNERS_URL for row in year))

  def test_explicit_history_winner_missing_from_annual_roster_is_preserved(self):
    self.overrides[self.url(2025)] = self.annual(2025).replace('Book of Hours 2025', 'Different Annual Book 2025')
    parsed = self.parse(); year = [row for row in parsed['entries'] if row['award_year'] == '2025']
    self.assertEqual(3, len(year)); self.assertEqual('Book of Hours 2025', next(row['title'] for row in year if row['result'] == 'winner'))


if __name__ == '__main__': unittest.main()
