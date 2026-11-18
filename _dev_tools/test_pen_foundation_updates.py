import unittest
from unittest.mock import patch

from _dev_tools import test_import_cache_and_saved_matches
from _dev_tools.verify_import_updates import missing_source_fixture, without_unit
from errors import ImportCancelledError, CamoufoxRequiredError
from parser.pen_foundation_updates import detail_row, history_sources, announcement_rows
from storage import build_import_cache_data
from url_fetcher.pen_faulkner_foundation import UrlFetcherPENFaulknerAward, UrlFetcherPENHemingwayAward


class FoundationUpdateTests(unittest.TestCase):

  def setUp(self):
    self.recipe = UrlFetcherPENFaulknerAward()
    self.years, self.calls, self.failures = [2026,2025,2024], [], {}
    self.changed = False
    self.clock = patch('parser.pen_foundation_updates.datetime')
    self.dates = self.clock.start()
    self.dates.datetime.now.return_value.year = 2026
    self.addCleanup(self.clock.stop)

  def detail_url(self, year, name):
    return f'https://www.penfaulkner.org/{year}/01/01/{name}-{year}/'

  def history(self):
    parts = ['<div class="entry-content">']
    for year in self.years:
      names = ('Other','Winner') if self.changed and year == 2026 else ('Winner','Other')
      parts.append('<div class="et_pb_row"><div class="et_pb_column">'
        f'<h3>{year} Winner</h3><a href="{self.detail_url(year,names[0])}"><img alt="Wrong book reused alt"/></a>'
        '</div><div class="et_pb_column">'
        f'<h3>{year} Finalists</h3><a href="{self.detail_url(year,names[1])}"><img alt="Wrong author reused alt"/></a></div></div>')
    if isinstance(self.recipe,UrlFetcherPENHemingwayAward):
      parts.append('<div class="et_pb_section"><h3>Past Winners</h3><p><b>2023</b> <em>Legacy, Title</em> by Walter M. Miller, Jr.</p></div>')
    else:
      parts.append('<div><h2>2023</h2><p><strong>WINNER:</strong><br/>Walter M. Miller, Jr., <em>Legacy, Title</em></p></div>')
    parts.append('</div><footer><h2>Winner</h2><p>Not a Book by Not a Writer</p></footer>')
    return ''.join(parts)

  def fetch(self,url):
    self.calls.append(url)
    if url in self.failures:
      raise self.failures[url]
    if url == self.recipe.URL:
      return self.history()
    for post_url,kind in self.recipe.POST_URLS:
      if url != post_url:
        continue
      year = int(url.split('/')[3])
      if kind in ('winner_post','current'):
        name = 'Other' if self.changed and year==2026 else 'Winner'
        return '<div class="entry-content"><p>'\
          f'<b>{name} Writer {year}\u2019s</b> <i>{name} {year}</i> (Publisher) has been selected as the winner of the {year} award.</p></div>'
      return '<div class="entry-content"><p>'\
        f'Judges have selected finalists for the {year} award: <i>Winner {year}</i> by Winner Writer {year} (Publisher), '\
        f'and <i>Other {year}</i> by Other Writer {year} (Publisher).</p></div>'
    year = int(url.split('/')[3])
    name = url.rstrip('/').split('/')[-1].rsplit('-',1)[0]
    return '<div class="entry-content"><div class="et_pb_team_member_description">'\
      f'<h2>{name} {year}</h2><p class="et_pb_member_position">by {name} Writer {year}</p>'\
      '<p>Biography with other books and prose, never a separate entry.</p></div></div>'

  def parse(self,old=None):
    return self.recipe.fetch_and_parse(self.fetch,cached_parsed=old,incremental_update=old is not None)

  def cache(self,parsed):
    return build_import_cache_data(self.recipe.source_id,parsed)

  def test_both_recipes_recover_real_missing_entries_and_repeat_with_fewer_requests(self):
    for cls in (UrlFetcherPENFaulknerAward,UrlFetcherPENHemingwayAward):
      with self.subTest(recipe=cls.source_id):
        self.recipe,self.calls = cls(),[]
        full = self.parse()
        full_count = len(self.calls)
        self.assertEqual(7,len(full['entries']))
        old,removed = missing_source_fixture(self.cache(full),
          full['incremental_state']['discovery']['refresh_units'])
        self.assertLess(len(old['entries']),len(full['entries']))
        self.calls.clear()
        update = self.parse(old)
        self.assertEqual(full['entries'],update['entries'])
        self.assertLess(len(self.calls),full_count)
        self.calls.clear()
        self.assertEqual(full['entries'],self.parse(self.cache(update))['entries'])
        self.assertLess(len(self.calls),full_count)
        self.assertNotIn(self.recipe.URL,self.calls)
        self.assertFalse(update['match_series'])
        legacy = next(e for e in update['entries'] if e['award_year']=='2023')
        self.assertEqual('Legacy, Title',legacy['title'])
        self.assertEqual(['Walter M. Miller, Jr.'],legacy['authors'])

  def test_rollover_refreshes_history_and_discovers_new_cycle_without_new_post_configuration(self):
    full = self.parse()
    self.dates.datetime.now.return_value.year = 2027
    self.years.insert(0,2027)
    self.calls.clear()
    update = self.parse(self.cache(full))
    self.assertIn(self.recipe.URL,self.calls)
    self.assertIn(self.detail_url(2027,'Winner'),self.calls)
    self.assertNotIn(self.detail_url(2024,'Winner'),self.calls)
    self.assertEqual(self.parse()['entries'],update['entries'])

  def test_changed_current_winner_forces_history_refresh_and_replaces_prior_status(self):
    full = self.parse()
    self.changed = True
    self.calls.clear()
    update = self.parse(self.cache(full))
    self.assertIn(self.recipe.URL,self.calls)
    self.assertEqual(self.parse()['entries'],update['entries'])
    current = [e for e in update['entries'] if e['award_year']=='2026']
    self.assertEqual([('Other 2026','winner'),('Winner 2026','nominee')],[(e['title'],e['result']) for e in current])

  def test_failed_historical_detail_retains_pending_source_then_recovers(self):
    full = self.parse()
    old = self.cache(full)
    url = self.detail_url(2024,'Winner')
    old['incremental_state']['units'][url]['complete'] = False
    self.failures[url] = OSError('offline')
    pending = self.parse(old)
    self.assertEqual(full['entries'],pending['entries'])
    self.assertFalse(pending['incremental_state']['units'][url]['complete'])
    self.assertTrue(pending['notes'])
    self.failures.clear()
    self.calls.clear()
    self.assertEqual(full['entries'],self.parse(self.cache(pending))['entries'])
    self.assertIn(url,self.calls)

  def test_legacy_changed_scope_and_malformed_projection_refetch(self):
    full = self.parse()
    wrong = self.cache(full)
    wrong['incremental_state']['source_key'] = 'different source or configuration'
    bad = self.cache(full)
    url = self.detail_url(2024,'Winner')
    bad['incremental_state']['units'][url]['metadata'] = {}
    for old in ({'entries':full['entries']},wrong,bad):
      self.calls.clear()
      self.assertEqual(full['entries'],self.parse(old)['entries'])
      self.assertIn(url,self.calls)

  def test_cancellation_and_browser_requirement_propagate_without_pending_output(self):
    full = self.parse()
    old = self.cache(full)
    url = self.detail_url(2024,'Winner')
    old['incremental_state']['units'][url]['complete'] = False
    for error in (ImportCancelledError('stop'),CamoufoxRequiredError('required')):
      self.failures[url] = error
      with self.assertRaises(type(error)):
        self.parse(old)

  def test_detail_uses_explicit_byline_or_bounded_bold_creator_not_cover_alt(self):
    parser = self.recipe.parser()
    spec = {'url':self.detail_url(2026,'Winner'),'year':2026,'result':'winner'}
    html = '<div class="entry-content"><div><h2>Actual Title</h2><div><div><b>Actual Writer</b> was born somewhere.</div></div></div></div><footer><p>Wrong by Writer</p></footer>'
    entry = detail_row(html,spec,parser)
    self.assertEqual(('Actual Title','Actual Writer','winner'),tuple(entry[k] for k in ('title','author','result')))
    with self.assertRaises(ValueError):
      detail_row('<div class="entry-content"><h2>Title</h2></div><footer><p>Someone is an author.</p></footer>',spec,parser)

  def test_bounded_announcement_lists_ignore_biographies_navigation_and_publishers(self):
    parser = self.recipe.parser()
    url,kind = self.recipe.POST_URLS[0]
    html = '<nav><li>Fake by Nobody</li></nav><div class="entry-content"><p>Judges have selected five finalists:</p>'\
      '<ul><li><b><i>Title, with comma</i></b> by Walter M. Miller, Jr. (Publisher)</li></ul>'\
      '<p>Another Book by Some Writer is a biography reference.</p></div>'
    rows = announcement_rows(html,url,kind,parser)
    self.assertEqual(1,len(rows))
    self.assertEqual(('Title, with comma','Walter M. Miller, Jr.'),tuple(rows[0][k] for k in ('title','author')))

  def test_unemphasized_legacy_byline_keeps_author_first_suffix_and_title_commas(self):
    html = '<div class="entry-content"><div><h2>2016</h2><p><b>WINNER:</b><br/>James Hannaham, Delicious Foods</p>'\
      '<p><b>FINALISTS:</b><br/>Walter M. Miller, Jr., A Title, with Commas</p></div></div>'
    rows,links = history_sources(html,self.recipe.URL,self.recipe.parser())
    self.assertEqual([],links)
    self.assertEqual([('James Hannaham','Delicious Foods','winner'),
      ('Walter M. Miller, Jr.','A Title, with Commas','nominee')],[(r['author'],r['title'],r['result']) for r in rows])
    html = '<h2>2003</h2><p><strong>FINALISTS:</strong><br/>Peter Cameron, <em>The City of Your Final</em> <em>Destination</em></p>'
    rows,links = history_sources(html,self.recipe.URL,self.recipe.parser())
    self.assertEqual(('The City of Your Final Destination','Peter Cameron'),(rows[0]['title'],rows[0]['author']))


if __name__=='__main__':
  unittest.main()
