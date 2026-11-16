"""Shared SFADB transport routing without recipe/category policy changes."""

import unittest

from _dev_tools import test_import_matching as support
from errors import CamoufoxFetchError, ImportCancelledError
from sfadb_transport import is_sfadb_url, validate_sfadb_page
from url_fetcher.seiun import UrlFetcherSeiunTranslatedNovel
from url_fetcher.aurealis import UrlFetcherAurealisGraphicNovelIllustratedWork


OVERVIEW = 'https://www.sfadb.com/Seiun_Awards'
YEAR = OVERVIEW + '_2025'


def overview_html(stem='Seiun_Awards'):
  return (f'<title>sfadb : {stem.replace("_", " ")}</title>'
    f'<a href="/{stem}_2025">2025</a>')


def year_html(category='Foreign Novel', stem='Seiun_Awards'):
  return (f'<title>sfadb: {stem.replace("_", " ")} 2025</title>'
    f'<div class="categoryblock"><div class="category">{category}</div><ul>'
    '<li>Winner: <b>A Work</b>, <a href="A_Writer">A Writer</a></li>'
    '<li><b>Another Work</b>, <a href="Another_Writer">Another Writer</a></li></ul></div>')


class SFADBTransportTest(unittest.TestCase):

  def setUp(self):
    self.main = support.main
    self.core = self.main.ListSwitchboardCore(None, lambda **_kwargs: None)
    self.enterContext(support.patch.dict(self.main.prefs, {
      'debug_browser_fallback_level': 0, 'camoufox_first_use_confirmed': True}))

  def test_domain_routing_is_exact(self):
    self.assertTrue(is_sfadb_url(OVERVIEW))
    self.assertTrue(is_sfadb_url('https://sfadb.com/Seiun_Awards'))
    self.assertFalse(is_sfadb_url('https://sfadb.com.example.com/Seiun_Awards'))
    self.assertFalse(is_sfadb_url('https://www.isfdb.org/cgi-bin/awardtype.cgi?61'))

  def test_validator_accepts_overview_and_category_or_legacy_year_shapes(self):
    validate_sfadb_page(overview_html(), OVERVIEW)
    validate_sfadb_page(year_html(), YEAR)
    validate_sfadb_page('<title>sfadb : Seiun Awards 2025</title>'
      '<p>Foreign Novel</p><p>Winner: A Work, A Writer</p>'
      '<a href="/Seiun_Awards_2024">2024</a>', YEAR)

  def test_validator_rejects_challenges_wrong_years_and_empty_branded_pages(self):
    for html in ('<title>Just a moment...</title>',
        year_html().replace('Awards 2025', 'Awards 2024'),
        '<title>sfadb : Seiun Awards 2025</title><p>No data</p>'):
      with self.subTest(html=html[:55]), self.assertRaises(ValueError):
        validate_sfadb_page(html, YEAR)

  def test_ranked_locus_citations_accept_titles_without_poll_year(self):
    for slug in ('Locus_1975', 'Locus_1987_SF'):
      validate_sfadb_page('<title>sfadb: Locus Magazine, Best All-Time SF Novels</title>'
        '<ol><li><a href="Frank_Herbert_Citations">Frank Herbert</a>, <b>Dune</b></li></ol>',
        'https://www.sfadb.com/' + slug)

  def test_ranked_locus_citations_require_actual_ranked_credits(self):
    with self.assertRaises(ValueError):
      validate_sfadb_page('<title>sfadb: Locus Magazine</title><p>No data</p>',
        'https://www.sfadb.com/Locus_1975')

  def test_otherwise_nominee_blocks_are_accepted_without_year_navigation(self):
    validate_sfadb_page('<title>sfadb : Otherwise Award All Nominees</title>'
      '<div class="nomineeblock"><div class="nominee">Writer</div>'
      '<div class="dateleftindent">2025</div><div class="titlemid">Work</div></div>',
      'https://www.sfadb.com/Otherwise_Award_All_Nominees')

  def test_browser_is_first_for_overview_and_linked_year(self):
    with support.patch.object(self.core, 'fetch_camoufox_url',
        side_effect=[overview_html(), year_html()]) as browser, \
        support.patch.object(self.core, 'fetch_legacy_url') as legacy:
      self.assertEqual(overview_html(), self.core.fetch_url(OVERVIEW))
      self.assertEqual(year_html(), self.core.fetch_url(YEAR))
    self.assertEqual([OVERVIEW, YEAR], [call.args[0] for call in browser.call_args_list])
    legacy.assert_not_called()

  def test_invalid_browser_page_retries_same_url_with_original_limits(self):
    with support.patch.object(self.core, 'fetch_camoufox_url', return_value='<title>Blocked</title>'), \
        support.patch.object(self.core, 'fetch_legacy_url', return_value=year_html()) as legacy, \
        support.patch.object(self.core, 'reject_camoufox_payload') as reject:
      self.assertEqual(year_html(), self.core.fetch_url(YEAR, max_bytes=12345, timeout=17))
    legacy.assert_called_once_with(YEAR, user_agent=None, max_bytes=12345, timeout=17)
    self.assertTrue(reject.called)

  def test_legacy_challenge_is_rejected_too(self):
    with support.patch.object(self.core, 'fetch_camoufox_url', side_effect=CamoufoxFetchError('failed')), \
        support.patch.object(self.core, 'fetch_legacy_url', return_value='<title>Blocked</title>'), \
        self.assertRaises(ValueError):
      self.core.fetch_url(OVERVIEW)

  def test_cancellation_does_not_try_legacy(self):
    with support.patch.object(self.core, 'fetch_camoufox_url', side_effect=ImportCancelledError('cancel')), \
        support.patch.object(self.core, 'fetch_legacy_url') as legacy, \
        self.assertRaises(ImportCancelledError):
      self.core.fetch_url(OVERVIEW)
    legacy.assert_not_called()

  def test_disabled_browser_never_checks_capability_and_uses_legacy(self):
    self.main.prefs['debug_browser_fallback_level'] = 2
    with support.patch.object(self.main, 'camoufox_capability') as capability, \
        support.patch.object(self.core, 'fetch_legacy_url', return_value=overview_html()) as legacy:
      self.assertEqual(overview_html(), self.core.fetch_url(OVERVIEW))
    capability.assert_not_called()
    self.assertEqual(1, legacy.call_count)

  def test_unavailable_browser_does_not_prompt_or_import_browser(self):
    with support.patch.object(self.main, 'camoufox_capability',
        return_value=(False, (6, 0, 0), 'unavailable')), \
        support.patch.object(self.main, 'question_dialog') as prompt, \
        support.patch.object(self.main, 'CamoufoxTransport') as factory, \
        support.patch.object(self.core, 'fetch_legacy_url', return_value=overview_html()):
      self.assertEqual(overview_html(), self.core.fetch_url(OVERVIEW))
    prompt.assert_not_called()
    factory.assert_not_called()

  def test_browser_failure_is_suppressed_for_later_year_requests(self):
    with support.patch.object(self.main, 'camoufox_capability', return_value=(True, (9, 18, 0), 'API')), \
        support.patch.object(self.main, 'CamoufoxTransport') as factory, \
        support.patch.object(self.core, 'fetch_legacy_url', side_effect=[overview_html(), year_html()]):
      factory.return_value.fetch.side_effect = CamoufoxFetchError('403')
      self.core.fetch_url(OVERVIEW)
      self.core.fetch_url(YEAR)
      factory.assert_called_once()
      factory.return_value.fetch.assert_called_once()
      factory.return_value.close.assert_called_once()

  def test_shared_routing_covers_multiple_recipe_families_and_preserves_sfadb_selection(self):
    for fetcher, stem, category in (
        (UrlFetcherSeiunTranslatedNovel(), 'Seiun_Awards', 'Foreign Novel'),
        (UrlFetcherAurealisGraphicNovelIllustratedWork(), 'Aurealis_Awards', 'Graphic Novel')):
      with self.subTest(recipe=fetcher.source_id):
        pages = {fetcher.URL: overview_html(stem), fetcher.URL + '_2025': year_html(category, stem)}
        with support.patch.object(self.core, 'fetch_camoufox_url', side_effect=lambda url, **kw: pages[url]) as browser, \
            support.patch.object(self.core, 'fetch_legacy_url') as legacy:
          parsed = fetcher.fetch_and_parse(self.core.fetch_url, source_choice=0)
        self.assertEqual(['A Work', 'Another Work'], [r['title'] for r in parsed['entries']])
        self.assertEqual([], parsed['notes'])
        self.assertEqual([fetcher.URL, fetcher.URL + '_2025'], [c.args[0] for c in browser.call_args_list])
        legacy.assert_not_called()

  def test_non_sfadb_default_requests_keep_existing_legacy_path(self):
    url = 'https://example.com/page'
    with support.patch.object(self.core, 'fetch_camoufox_url') as browser, \
        support.patch.object(self.core, 'fetch_legacy_url', return_value='ordinary page') as legacy:
      self.assertEqual('ordinary page', self.core.fetch_url(url))
    browser.assert_not_called()
    self.assertEqual(url, legacy.call_args.args[0])

  def test_browser_uses_sfadb_label_and_warmup_exclusion(self):
    with support.patch.object(self.main, 'camoufox_capability', return_value=(True, (9, 18, 0), 'API')), \
        support.patch.object(self.main, 'CamoufoxTransport') as factory:
      factory.return_value.fetch.return_value = overview_html()
      self.core.fetch_url(OVERVIEW)
      self.assertEqual('SFADB', factory.call_args.kwargs['source_name'])
      self.assertIn('sfadb.com', factory.call_args.kwargs['warmup_excluded_domains'])
      self.assertFalse(factory.call_args.kwargs['check_challenges'])
      self.core.close_camoufox_transport()


if __name__ == '__main__':
  unittest.main()
