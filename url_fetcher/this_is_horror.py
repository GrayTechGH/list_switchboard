#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

import datetime

try:
  from calibre_plugins.list_switchboard.parser.this_is_horror import (
    GOODREADS_URL,
    OFFICIAL_AWARDS_API_URL,
    OFFICIAL_AWARDS_URL,
    OFFICIAL_RESULTS_API_URLS,
    OFFICIAL_RESULTS,
  )
except ImportError:
  from parser.this_is_horror import (
    GOODREADS_URL,
    OFFICIAL_AWARDS_API_URL,
    OFFICIAL_AWARDS_URL,
    OFFICIAL_RESULTS_API_URLS,
    OFFICIAL_RESULTS,
  )

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError
  from calibre_plugins.list_switchboard.parser.incremental import (
    ParsedUnitCache, project_source_rows, restore_source_rows)
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError
  from parser.incremental import ParsedUnitCache, project_source_rows, restore_source_rows

from .this_is_horror_transport import ThisIsHorrorFetchPolicy

from .generic import (
  CATEGORY_HORROR_DARK_FICTION,
  GoodreadsFetchPolicyMixin,
  UrlFetcherError,
  UrlFetcherGeneric,
  parsed_source,
)

MAX_GOODREADS_PAGES = 10


class UrlFetcherThisIsHorror(GoodreadsFetchPolicyMixin, UrlFetcherGeneric):
  """Keep browser recovery confined to the optional diagnostic supplement.

  Invariants:
  - Official ballot/result validation remains mandatory and legacy-only.
  - Failed diagnostic pagination is discarded in full with its existing note.
  - Closed official results may reuse source projections; ballots stay live and
    merged result validation runs before any updated cache can be returned.
  - Per-import policy and progress state are cleared on every exit.
  """

  URL = OFFICIAL_AWARDS_URL
  FETCH_URLS = ()
  FILTER_CATEGORIES = (CATEGORY_HORROR_DARK_FICTION,)
  order = 92
  options = {'match_series': False}
  AWARD_NAME = 'This Is Horror Award'
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.this_is_horror import (
        ThisIsHorrorParser,
      )
    except ImportError:
      from parser.this_is_horror import ThisIsHorrorParser
    return ThisIsHorrorParser()

  def source_choices(self):
    return ({'label': 'Automatic', 'value': 'automatic'},)

  def fetch_and_parse(
      self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
      before_fetch=None, after_fetch=None, before_parse=None,
      force_fallback_level=0, disable_fallbacks=False, source_choice=None,
      cached_parsed=None, incremental_update=False):
    self._this_is_horror_progress = progress
    self._this_is_horror_fetch_policy = ThisIsHorrorFetchPolicy(
      fetch_url, lambda url: self.legacy_fetch_url(fetch_url, url), self.parser(),
      log=log, progress=progress)
    try:
      return self._fetch_and_parse(
        fetch_url, sleep, fetch_error, log, progress, before_fetch, after_fetch,
        before_parse, force_fallback_level, disable_fallbacks, source_choice,
        cached_parsed, incremental_update)
    finally:
      self._this_is_horror_fetch_policy = None
      self._this_is_horror_progress = None

  def fetch_url(self, fetch_url, url):
    policy = getattr(self, '_this_is_horror_fetch_policy', None)
    if policy is not None and url.startswith(GOODREADS_URL):
      return policy.fetch(url)
    return self.legacy_fetch_url(fetch_url, url)

  def legacy_fetch_url(self, fetch_url, url):
    retries = self.timeout_retries(url)
    for retry in range(retries + 1):
      try:
        return self.fetch_url_once(fetch_url, url)
      except (ImportCancelledError, CamoufoxRequiredError):
        raise
      except Exception as err:
        if retry >= retries or not self.is_timeout_error(err):
          raise
        progress = getattr(self, '_this_is_horror_progress', None)
        if progress is not None:
          progress(0, 1, f'This Is Horror Goodreads timed out; retry {retry + 1} of {retries}: {url}')

  def _fetch_and_parse(
      self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
      before_fetch=None, after_fetch=None, before_parse=None,
      force_fallback_level=0, disable_fallbacks=False, source_choice=None,
      cached_parsed=None, incremental_update=False):
    if source_choice not in (None, 'automatic'):
      raise UrlFetcherError(
        f'No source fallback attempt exists for selected source {source_choice}.')

    fetcher_fetch_url = lambda target_url: self.fetch_url(fetch_url, target_url)
    parser = self.parser()
    notes = []
    cache = ParsedUnitCache('this-is-horror-results-v1',
      f'{self.source_id}|{self.CATEGORY_ALIASES}|{OFFICIAL_AWARDS_API_URL}|'
      f'{OFFICIAL_RESULTS_API_URLS}|{OFFICIAL_RESULTS}', cached_parsed, incremental_update)
    result_units = []

    ballots = self.fetch_parse_ballots(
      parser, fetcher_fetch_url, before_fetch, after_fetch, before_parse)
    result_pages = self.fetch_parse_result_pages(
      parser, fetcher_fetch_url, before_fetch, after_fetch, before_parse,
      cache=cache, source_units=result_units)

    goodreads_pages = []
    try:
      goodreads_pages = self.fetch_parse_goodreads_pages(
        parser, fetcher_fetch_url, before_fetch, after_fetch, before_parse, progress)
    except (ImportCancelledError, CamoufoxRequiredError):
      raise
    except Exception as err:
      note = f'This Is Horror Goodreads diagnostic supplement failed: {err}'
      notes.append(note)
      if log is not None:
        log(note)

    combined = parser.combine_results(
      self.NAME,
      self.URL,
      ballots,
      *result_pages,
      *goodreads_pages,
      {'entries': (), 'notes': notes})
    try:
      parser.validate_combined_result(combined, self.CATEGORY)
    except ValueError:
      if not any(unit['reused'] for unit in result_units):
        raise
      # A changed ballot can invalidate an old result spelling or promotion.
      # Refresh required results before reporting a completeness failure.
      result_units = []
      result_pages = self.fetch_parse_result_pages(
        parser, fetcher_fetch_url, before_fetch, after_fetch, before_parse,
        source_units=result_units)
      combined = parser.combine_results(self.NAME, self.URL, ballots,
        *result_pages, *goodreads_pages, {'entries': (), 'notes': notes})
      parser.validate_combined_result(combined, self.CATEGORY)
    if not combined.get('entries'):
      raise UrlFetcherError('Could not fetch or parse the imported list.')
    combined['match_series'] = self.options.get('match_series', True)
    combined.setdefault('source', parsed_source(self.NAME, self.URL, self.source_id))
    projected, metadata = project_source_rows(ballots['entries'], combined['entries'], parser.row_key)
    metadata['notes'] = list(ballots.get('notes', []))
    cache.put(OFFICIAL_AWARDS_API_URL, projected, metadata=metadata)
    for unit in result_units:
      parsed = unit['parsed']
      projected, metadata = project_source_rows(parsed['entries'], combined['entries'], parser.row_key)
      metadata.update(notes=list(parsed.get('notes', [])), details=unit['details'])
      cache.put(unit['url'], projected, revision=unit['revision'], metadata=metadata)
    combined['incremental_state'] = cache.state(combined['entries'])
    combined['incremental_state']['discovery'] = {'refresh_units': [OFFICIAL_AWARDS_API_URL]}
    return combined

  def fetch_parse_ballots(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse):
    source = self.fetch_page(
      fetch_url, OFFICIAL_AWARDS_API_URL, before_fetch, after_fetch)
    self.before_parse(before_parse, OFFICIAL_AWARDS_API_URL)
    parsed = parser.parse_official_ballots(
      source,
      OFFICIAL_AWARDS_URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES)
    parser.validate_official_ballot_result(parsed, self.CATEGORY)
    return parsed

  def fetch_parse_current(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse):
    """Compatibility wrapper for callers using the former method name."""
    return self.fetch_parse_ballots(
      parser, fetch_url, before_fetch, after_fetch, before_parse)

  def fetch_parse_result_pages(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse,
      cache=None, source_units=None):
    parsed_results = []
    detail_urls = []
    current_year = datetime.datetime.now().year

    def fetch_result(url, years, award_year=None):
      revision = ','.join(str(year) for year in years)
      old_unit = cache.old_units.get(url) if cache is not None else None
      old_unit = old_unit or {}
      parsed, details, reused = None, [], False
      if years and max(years) < current_year and old_unit.get('complete') is True and old_unit.get('revision') == revision:
        try:
          metadata = old_unit.get('metadata', {})
          old_notes, details = metadata.get('notes'), metadata.get('details')
          if (not isinstance(old_notes, list) or any(not isinstance(note, str) for note in old_notes) or
              not isinstance(details, list) or any(not isinstance(item, (tuple, list)) or
              len(item) != 2 or type(item[0]) is not int or not isinstance(item[1], str) for item in details)):
            raise ValueError('Invalid result discovery metadata.')
          parsed = {'entries': restore_source_rows(cache.previous(url), metadata), 'notes': old_notes}
          reused = True
        except ValueError:
          parsed = None
      if parsed is None:
        source = self.fetch_page(fetch_url, url, before_fetch, after_fetch)
        self.before_parse(before_parse, url)
        parsed = parser.parse_official_winners(source,
          url if award_year is not None else OFFICIAL_AWARDS_URL,
          self.NAME, self.CATEGORY, self.CATEGORY_ALIASES, award_year=award_year)
        details = list(parser.discover_result_detail_urls(source, self.CATEGORY, self.CATEGORY_ALIASES)) if award_year is None else []
      if source_units is not None:
        source_units.append({'url': url, 'parsed': parsed, 'revision': revision,
          'details': details, 'reused': reused})
      return parsed, details

    for url in OFFICIAL_RESULTS_API_URLS:
      years = [item[0] for item in OFFICIAL_RESULTS if f'/wp-json/wp/v2/{item[1]}?' in url]
      parsed, details = fetch_result(url, years)
      parsed_results.append(parsed)
      for detail in details:
        detail = tuple(detail)
        if detail not in detail_urls:
          detail_urls.append(detail)
    for year, url in detail_urls:
      parsed, _details = fetch_result(url, [year], award_year=year)
      parsed_results.append(parsed)
    return parsed_results

  def fetch_parse_winner_posts(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse, log=None):
    """Compatibility wrapper for callers using the former method name."""
    return self.fetch_parse_result_pages(
      parser, fetch_url, before_fetch, after_fetch, before_parse)

  def fetch_parse_goodreads_pages(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse, progress=None):
    pending = [GOODREADS_URL]
    seen = set()
    parsed_results = []
    while pending:
      if len(seen) >= MAX_GOODREADS_PAGES:
        raise UrlFetcherError(
          'This Is Horror Goodreads pagination exceeded the '
          f'{MAX_GOODREADS_PAGES}-page safety limit.')
      url = pending.pop(0)
      if url in seen:
        continue
      total = len(seen) + len(pending) + 1
      if progress is not None:
        progress(len(seen), total, f'Fetching This Is Horror Goodreads page {len(seen) + 1} of {total}')
      html = self.fetch_page(fetch_url, url, before_fetch, after_fetch)
      self.before_parse(before_parse, url)
      parser.validate_goodreads_page(html, url)
      if progress is not None:
        progress(len(seen), total, f'Parsing This Is Horror Goodreads page {len(seen) + 1} of {total}')
      seen.add(url)
      parsed_results.append(parser.parse_goodreads(
        html,
        url,
        self.NAME,
        self.CATEGORY,
        self.CATEGORY_ALIASES))
      for discovered_url in parser.discover_goodreads_page_urls(html, url):
        if discovered_url not in seen and discovered_url not in pending:
          pending.append(discovered_url)
      if progress is not None:
        progress(len(seen), len(seen) + len(pending),
          f'Parsed This Is Horror Goodreads page {len(seen)} of {len(seen) + len(pending)}')
    return parsed_results

  def fetch_parse_goodreads(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse):
    """Compatibility wrapper returning the first parsed Goodreads page."""
    pages = self.fetch_parse_goodreads_pages(
      parser, fetch_url, before_fetch, after_fetch, before_parse)
    return pages[0] if pages else {'entries': (), 'notes': ()}

  def fetch_page(self, fetch_url, url, before_fetch, after_fetch):
    if before_fetch is not None:
      before_fetch(url)
    html = fetch_url(url)
    if after_fetch is not None:
      after_fetch(url, html)
    return html

  def before_parse(self, before_parse, url):
    if before_parse is not None:
      before_parse(url)

  def parse(self, html, **_kwargs):
    return self.parser().parse_official_current(
      html,
      OFFICIAL_AWARDS_URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES)


class UrlFetcherThisIsHorrorNovel(UrlFetcherThisIsHorror):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'this_is_horror_novel'
  NAME = 'This Is Horror - Novel'
  CATEGORY = 'Novel'
  CATEGORY_ALIASES = ('novel', 'novel of the year', 'best novel')


class UrlFetcherThisIsHorrorNovella(UrlFetcherThisIsHorror):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'this_is_horror_novella'
  NAME = 'This Is Horror - Novella'
  CATEGORY = 'Novella'
  CATEGORY_ALIASES = ('novella', 'novella of the year', 'best novella')


class UrlFetcherThisIsHorrorShortStoryCollection(UrlFetcherThisIsHorror):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'this_is_horror_short_story_collection'
  NAME = 'This Is Horror - Short Story Collection'
  CATEGORY = 'Short Story Collection'
  CATEGORY_ALIASES = (
    'short story collection',
    'short story collection of the year',
    'collection',
  )


class UrlFetcherThisIsHorrorAnthology(UrlFetcherThisIsHorror):
  source_id = 'this_is_horror_anthology'
  NAME = 'This Is Horror - Anthology (discontinued)'
  CATEGORY = 'Anthology'
  CATEGORY_ALIASES = ('anthology', 'anthology of the year', 'best anthology')
