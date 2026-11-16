"""Authoritative original-work identity, cache and failure boundaries."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import Mock
from types import SimpleNamespace

from _dev_tools import test_import_matching as support
from errors import ImportCancelledError, CamoufoxRequiredError
from parser.isfdb_title import original_link, parse_title_record
from storage import build_import_cache_data, StorageMixin
from url_fetcher.isfdb_originals import resolve_original_works
from url_fetcher.seiun import UrlFetcherSeiunTranslatedNovel


URL = 'https://www.isfdb.org/cgi-bin/title.cgi?2036'
NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)


def title_page(record_id='2036', title='Dune', language='English'):
  return f'''<title>Title: {title}</title><div class="ContentBox">
    <b>Title:</b> {title}<span class="recordID"><b>Title Record # </b>{record_id}</span><br/>
    <b>Author:</b><a href="/cgi-bin/ea.cgi?1">Frank Herbert</a><br/>
    <b>Language:</b>{language}<div class="notes">Other names: <a href="/cgi-bin/ea.cgi?2">Wrong Author</a></div>
    </div><a href="/cgi-bin/ea.cgi?3">Sidebar Author</a>'''


def edition(title='Japanese volume 1', year='1974', result='winner', record_id='2036'):
  return {'position': year if result == 'winner' else year + '.01', 'title': title, 'authors': ['Japanese credit'],
    'award_year': year, 'category': 'Translated Novel', 'award': 'Seiun Award',
    'result': result, 'source': {'url': 'https://www.isfdb.org/cgi-bin/title.cgi?999'},
    'original_work': {'id': record_id, 'url': URL.replace('2036', record_id), 'title': 'Dune'}}


class OriginalWorksTest(unittest.TestCase):

  def matching_core(self, saved=None, unmatched=None):
    core = support.main.ListSwitchboardCore(None, lambda **kwargs: None)
    class Api:
      def all_field_for(self, field, ids, default_value=''):
        values = {'title': {7: 'Dune', 8: 'Other Work'},
          'authors': {7: ['Frank Herbert'], 8: ['Other Author']}}.get(field, {})
        return {book_id: values.get(book_id, default_value) for book_id in ids}
    core.db = SimpleNamespace(new_api=Api())
    core.all_book_ids = lambda: [7, 8]
    core.all_local_series_values = lambda ids: {book_id: [] for book_id in ids}
    core.update_import_match_progress = lambda *args, **kwargs: None
    core.update_import_match_step_progress = lambda *args, **kwargs: None
    core.saved_match_overrides = lambda list_id: saved or {}
    core.saved_unmatched_overrides = lambda list_id: unmatched or {}
    return core

  def resolved_entry(self):
    return resolve_original_works({'entries': [edition(),
      edition('Japanese volume 2', result='nominee')], 'notes': []},
      lambda url: title_page(), now=NOW)['entries'][0]

  def test_explicit_link_accepts_tooltip_wrappers_and_rejects_unmarked_or_external_links(self):
    html = '(translation of <div class="tooltip"><a href="/cgi-bin/title.cgi?2036">Dune</a>'
    self.assertEqual('2036', original_link(html, URL)['id'])
    self.assertIsNone(original_link('<a href="/cgi-bin/title.cgi?2036">Dune</a>', URL))
    self.assertIsNone(original_link('(translation of <a href="https://example.com/cgi-bin/title.cgi?2036">Dune</a>', URL))

  def test_metadata_is_bounded_to_labeled_fields_and_requested_id(self):
    record = parse_title_record(title_page(), URL)
    self.assertEqual(['Frank Herbert'], record['authors'])
    self.assertEqual('Dune', record['title'])
    self.assertEqual('English', record['language'])
    for html in (title_page(record_id='99'), '<title>Verification required</title>'):
      with self.assertRaises(ValueError):
        parse_title_record(html, URL)
    wrapped = title_page().replace('<b>Title:</b> Dune', '<b>Title:</b>'
      '<div class="tooltip">Dune<sup class="mouseover">?</sup>'
      '<span class="tooltiptext">A transliteration</span></div>')
    self.assertEqual('Dune', parse_title_record(wrapped, URL)['title'])
    incomplete = title_page().replace('<b>Author:</b>', '<b>Other:</b>')
    self.assertEqual([], parse_title_record(incomplete, URL, require_complete=False)['authors'])
    with self.assertRaises(ValueError):
      parse_title_record(incomplete, URL)

  def test_multiple_author_anchors_preserve_suffix_and_literal_ampersand(self):
    html = title_page().replace('Frank Herbert</a>', 'Writer, Jr.</a> and '
      '<a href="/cgi-bin/ea.cgi?4">Name &amp; Company</a>')
    self.assertEqual(['Writer, Jr.', 'Name & Company'], parse_title_record(html, URL)['authors'])

  def test_split_volumes_collapse_by_id_within_year_and_keep_award_result_and_provenance(self):
    incoming = {'entries': [edition(result='nominee'), edition('Japanese volume 2'),
      edition('Japanese edition next year', year='1975', result='nominee')], 'notes': []}
    original = deepcopy(incoming)
    fetch = Mock(return_value=title_page())
    result = resolve_original_works(incoming, fetch, now=NOW)
    fetch.assert_called_once_with(URL)
    self.assertEqual(incoming, original)
    self.assertEqual(['1974', '1975.01'], [r['position'] for r in result['entries']])
    self.assertEqual(['winner', 'nominee'], [r['result'] for r in result['entries']])
    self.assertEqual(['Dune', 'Dune'], [r['title'] for r in result['entries']])
    self.assertEqual(2, len(result['entries'][0]['translated_editions']))
    self.assertEqual(URL, result['entries'][0]['source']['url'])
    self.assertEqual(['Frank Herbert'], result['entries'][0]['authors'])

  def test_recent_parsed_metadata_reuses_original_without_network_and_stale_cache_refreshes(self):
    incoming = {'entries': [edition()], 'notes': []}
    cached = resolve_original_works(incoming, lambda url: title_page(), now=NOW)
    for age, calls in ((1, 0), (31, 1)):
      with self.subTest(age=age):
        fetch = Mock(return_value=title_page())
        result = resolve_original_works(incoming, fetch, cached=cached,
          now=NOW + timedelta(days=age))
        self.assertEqual(calls, fetch.call_count)
        self.assertEqual('Dune', result['entries'][0]['title'])
    malformed = deepcopy(cached)
    malformed['entries'][0]['original_work']['resolved_at'] = None
    fetch = Mock(return_value=title_page())
    resolve_original_works(incoming, fetch, cached=malformed, now=NOW)
    fetch.assert_called_once_with(URL)

  def test_matching_title_and_author_do_not_collapse_different_original_ids(self):
    incoming = {'entries': [edition(record_id='1'), edition(record_id='2')], 'notes': []}
    result = resolve_original_works(incoming,
      lambda url: title_page(record_id=url.rsplit('?', 1)[-1]), now=NOW)
    self.assertEqual(2, len(result['entries']))
    self.assertEqual(['1', '2'], [e['original_work']['id'] for e in result['entries']])

  def test_failed_resolution_retains_source_edition_and_stops_repeated_outage_requests(self):
    incoming = {'entries': [edition(record_id=str(i)) for i in range(1, 6)], 'notes': []}
    fetch = Mock(side_effect=RuntimeError('403'))
    result = resolve_original_works(incoming, fetch, now=NOW)
    self.assertEqual(3, fetch.call_count)
    self.assertEqual(incoming['entries'], result['entries'])
    self.assertTrue(any('stopped after three' in note for note in result['notes']))

  def test_non_english_original_is_retained_for_review_without_guessed_translation(self):
    result = resolve_original_works({'entries': [edition()], 'notes': []},
      lambda url: title_page(language='French'), now=NOW)
    self.assertEqual('Japanese volume 1', result['entries'][0]['title'])
    self.assertTrue(any('French' in note for note in result['notes']))

  def test_non_english_original_follows_explicit_english_variant_with_matching_provenance(self):
    native = title_page(language='French') + '''<table class="variantscolumn">
      <tr><th>Year</th><th>Language</th><th>Title</th></tr>
      <tr><td>1968</td><td>English</td><td><a href="/cgi-bin/title.cgi?7">English Work</a></td></tr></table>'''
    pages = {URL: native, URL.replace('2036', '7'): title_page(record_id='7', title='English Work')}
    fetch = Mock(side_effect=lambda url: pages[url])
    result = resolve_original_works({'entries': [edition()], 'notes': []}, fetch, now=NOW)
    row = result['entries'][0]
    self.assertEqual('English Work', row['title'])
    self.assertEqual('2036', row['original_work']['id'])
    self.assertEqual('French', row['original_work']['original_language'])
    self.assertEqual(URL.replace('2036', '7'), row['source']['url'])
    self.assertEqual(2, fetch.call_count)

  def test_explicit_english_variants_share_work_identity_and_existing_matching_aliases(self):
    html = title_page(language='French') + '''<table class="variantscolumn">
      <tr><th>Year</th><th>Language</th><th>Title</th></tr>
      <tr><td>1968</td><td>English</td><td><a href="/cgi-bin/title.cgi?7">English Work</a></td></tr>
      <tr><td>1970</td><td>English</td><td><a href="/cgi-bin/title.cgi?8">Another English Title</a></td></tr></table>'''
    fetch = Mock(side_effect=lambda url: html if url == URL
      else title_page(record_id='7', title='English Work'))
    result = resolve_original_works({'entries': [edition()], 'notes': []}, fetch, now=NOW)
    self.assertEqual('English Work', result['entries'][0]['title'])
    self.assertEqual(['Another English Title'], result['entries'][0]['aliases'])
    self.assertEqual(2, fetch.call_count)
    from matching import import_list_review_auto_entry_title_values
    self.assertEqual(('English Work', 'Another English Title'),
      import_list_review_auto_entry_title_values(result['entries'][0]))

  def test_cancel_or_required_browser_never_returns_partial_resolution(self):
    for error in (ImportCancelledError('cancel'), CamoufoxRequiredError('required')):
      with self.assertRaises(type(error)):
        resolve_original_works({'entries': [edition()], 'notes': []}, Mock(side_effect=error), now=NOW)

  def test_progress_counts_unique_work_lookups_and_finishes_once(self):
    progress = []
    resolve_original_works({'entries': [edition(), edition('volume 2')], 'notes': []},
      lambda url: title_page(), progress=lambda *args: progress.append(args), now=NOW)
    self.assertEqual([(1, 2), (1, 1)], [r[:2] for r in progress])

  def test_untranslated_english_row_needs_no_lookup_and_remains_unchanged(self):
    row = edition()
    row.pop('original_work')
    row['title'] = 'An English Work'
    fetch = Mock()
    result = resolve_original_works({'entries': [row], 'notes': []}, fetch, now=NOW)
    fetch.assert_not_called()
    self.assertEqual([row], result['entries'])

  def test_resolved_metadata_and_original_edition_evidence_survive_flat_cache(self):
    fetcher = UrlFetcherSeiunTranslatedNovel()
    parsed = resolve_original_works({'name': fetcher.NAME, 'entries': [edition()], 'notes': []},
      lambda url: title_page(), now=NOW)
    cache = build_import_cache_data(fetcher.source_id, parsed, recipe=fetcher)
    reread = StorageMixin.cached_import_to_parsed(None, cache)
    self.assertEqual(parsed['entries'], reread['entries'])
    fetch = Mock()
    resolve_original_works({'entries': [edition()], 'notes': []}, fetch, cached=cache, now=NOW)
    fetch.assert_not_called()

  def test_complete_refresh_passes_metadata_cache_without_incremental_refresh(self):
    core = support.main.ListSwitchboardCore(None, lambda **kwargs: None)
    fetcher = UrlFetcherSeiunTranslatedNovel()
    cache = {'entries': [], 'list_id': fetcher.source_id}
    core.read_import_cache = Mock(return_value=cache)
    core.choose_cached_import_action = Mock(return_value='refresh')
    core.fetch_and_parse_recipe = Mock(return_value={'name': fetcher.NAME, 'entries': []})
    core.merge_append_import_cache = Mock()
    core.load_or_fetch_recipe(fetcher)
    self.assertIs(cache, core.fetch_and_parse_recipe.call_args.kwargs['original_work_cache'])
    self.assertIsNone(core.fetch_and_parse_recipe.call_args.kwargs['cache'])

  def test_incomplete_genuine_metadata_does_not_disable_browser_for_other_originals(self):
    fetcher = UrlFetcherSeiunTranslatedNovel()
    calls = []
    def fetch(url, **options):
      calls.append((url, options))
      if url == fetcher.isfdb_url():
        return '<table><tr><td colspan="3">1974</td></tr>' + ''.join(
          f'<tr><td>Nomination</td><td>Edition {i} (translation of '
          f'<a href="/cgi-bin/title.cgi?{i}">Work {i}</a>)</td><td>Native name</td></tr>'
          for i in range(1, 5)) + '</table>'
      key = url.rsplit('?', 1)[-1]
      if key != '4':
        return title_page(record_id=key).replace('<b>Author:</b>', '<b>Unknown:</b>')
      return title_page(record_id='4', title='Resolved Work')
    parsed = fetcher.fetch_and_parse(fetch, source_choice=1)
    self.assertEqual('Resolved Work', parsed['entries'][3]['title'])
    self.assertEqual('Edition 1', parsed['entries'][0]['title'])
    self.assertTrue(all(options == {'transport': 'camoufox'} for _, options in calls))
    self.assertEqual(5, len(calls))
    self.assertTrue(any('Could not resolve' in note for note in parsed['notes']))

  def test_prior_edition_saved_choice_remains_exact_after_work_collapse_and_index_change(self):
    from matching import entry_key_for_saved_match
    row = self.resolved_entry()
    old = row['translated_editions'][1]
    key = entry_key_for_saved_match(old, position_scoped=True)
    core = self.matching_core(saved={key: {'matched_book_ids': [8]}})
    matched, missing, rows = core.match_imported_entries([row], match_series=False,
      list_id='test', allow_goodreads_recovery=False, return_details=True)
    self.assertEqual({8: '1974'}, matched)
    self.assertEqual('saved/manual override', rows[0]['match_source'])
    self.assertNotIn(7, matched)

  def test_new_original_saved_choice_precedes_prior_edition_directives(self):
    from matching import entry_key_for_saved_match
    row = self.resolved_entry()
    old_key = entry_key_for_saved_match(row['translated_editions'][0])
    current_key = entry_key_for_saved_match(row)
    core = self.matching_core(saved={current_key: {'matched_book_ids': [7]}},
      unmatched={old_key: {'ignored': True}})
    matched, missing, rows = core.match_imported_entries([row], match_series=False,
      list_id='test', allow_goodreads_recovery=False, return_details=True)
    self.assertEqual({7: '1974'}, matched)
    self.assertFalse(rows[0]['ignored'])

  def test_conflicting_saved_edition_choices_require_review_and_block_active_auto_reassignment(self):
    from matching import entry_key_for_saved_match
    row = self.resolved_entry()
    choices = {entry_key_for_saved_match(edition): {'matched_book_ids': [book_id]}
      for edition, book_id in zip(row['translated_editions'], (7, 8))}
    core = self.matching_core(saved=choices)
    matched, missing, rows = core.match_imported_entries([row], match_series=False,
      list_id='test', allow_goodreads_recovery=False, return_details=True)
    self.assertEqual({}, matched)
    self.assertTrue(rows[0]['saved_choice_conflict'])
    self.assertEqual('saved choices need review', rows[0]['match_source'])
    core.active_book_ids_for_list = lambda name: {7}
    core.active_review_positions_by_book = lambda ids: {7: '1974'}
    core.review_book_details = lambda ids: {7: {'matched_title': 'Dune', 'matched_authors': ['Frank Herbert']}}
    rows, notes = core.reconcile_review_rows_with_active_list('Example', rows, active_name='Example')
    self.assertFalse(rows[0]['matched'])

  def test_ignored_editions_and_ambiguous_shared_old_keys_cannot_create_auto_matches(self):
    from matching import entry_key_for_saved_match
    row = self.resolved_entry()
    key = entry_key_for_saved_match(row['translated_editions'][0])
    core = self.matching_core(unmatched={key: {'ignored': True}})
    matched, missing, rows = core.match_imported_entries([row], match_series=False,
      list_id='test', allow_goodreads_recovery=False, return_details=True)
    self.assertEqual({}, matched)
    self.assertTrue(rows[0]['ignored'])
    other = deepcopy(row)
    other['title'] = 'Other Work'
    other['authors'] = ['Other Author']
    other['original_work']['id'] = '99'
    core = self.matching_core(saved={key: {'matched_book_ids': [8]}})
    matched, missing, rows = core.match_imported_entries([row, other], match_series=False,
      list_id='test', allow_goodreads_recovery=False, return_details=True)
    self.assertEqual({}, matched)
    self.assertTrue(all(row.get('saved_choice_conflict') for row in rows))


if __name__ == '__main__':
  unittest.main()
