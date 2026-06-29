#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  UrlFetcherError,
  UrlFetcherGeneric,
)


OFFICIAL_URL = (
  'https://www.library.act.gov.au/find/history/frequentlyaskedquestions/'
  'Events/literaryawards/book_of_the_year')
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/ACT_Book_of_the_Year_Award'


class UrlFetcherACTBookOfTheYearAward(UrlFetcherGeneric):

  URL = OFFICIAL_URL
  WIKIPEDIA_URL = WIKIPEDIA_URL
  FETCH_URLS = ()
  FILTER_CATEGORIES = (CATEGORY_REGIONAL_NATIONAL_AWARDS,)
  order = 246
  options = {'match_series': False}
  source_id = 'act_book_of_the_year_award'
  NAME = 'ACT Book of the Year Award'

  def create_official_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.act_book_of_the_year import (
        ACTBookOfTheYearOfficialParser,
      )
    except ImportError:
      from parser.act_book_of_the_year import ACTBookOfTheYearOfficialParser
    return ACTBookOfTheYearOfficialParser()

  def create_wikipedia_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.act_book_of_the_year import (
        ACTBookOfTheYearWikipediaParser,
      )
    except ImportError:
      from parser.act_book_of_the_year import ACTBookOfTheYearWikipediaParser
    return ACTBookOfTheYearWikipediaParser()

  def source_choices(self):
    return (
      {'label': 'Automatic', 'value': 'automatic'},
      {'label': 'Libraries ACT', 'value': 0},
      {'label': 'Wikipedia', 'value': 1},
    )

  def fetch_and_parse(
      self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
      before_fetch=None, after_fetch=None, before_parse=None,
      force_fallback_level=0, disable_fallbacks=False, source_choice=None,
      cached_parsed=None, incremental_update=False):
    fetcher_fetch_url = lambda target_url: self.fetch_url(fetch_url, target_url)
    source_choice = 'automatic' if source_choice is None else source_choice
    force_fallback_level = int(force_fallback_level or 0)
    if force_fallback_level > 0 and source_choice == 'automatic' and not disable_fallbacks:
      source_choice = force_fallback_level
    if source_choice not in {'automatic', 0, 1, '0', '1'}:
      raise UrlFetcherError(
        f'No source fallback attempt exists for selected source {source_choice}.')
    if source_choice in {1, '1'}:
      return self.fetch_parse_wikipedia(
        fetcher_fetch_url, before_fetch, after_fetch, before_parse)

    official_error = None
    try:
      official = self.fetch_parse_official(
        fetcher_fetch_url, before_fetch, after_fetch, before_parse)
      if source_choice in {0, '0'} or disable_fallbacks:
        if official.get('entries'):
          return self.with_match_series(official)
        raise UrlFetcherError('Libraries ACT parsed result did not contain usable entries.')
      if official.get('entries'):
        return self.with_match_series(self.supplement_official_winners(
          official, fetcher_fetch_url, before_fetch, after_fetch, before_parse, log))
      official_error = 'Libraries ACT parsed result did not contain usable entries.'
    except Exception as err:
      official_error = str(err) or err.__class__.__name__
      if source_choice in {0, '0'} or disable_fallbacks:
        raise UrlFetcherError(
          'Could not fetch or parse the imported list.\n\nTried:\n- '
          f'Libraries ACT failed: {official_error}')
      if log is not None:
        log(f'Source fallback Libraries ACT failed: {official_error}')
    try:
      wikipedia = self.fetch_parse_wikipedia(
        fetcher_fetch_url, before_fetch, after_fetch, before_parse)
      wikipedia['notes'] = [f'Libraries ACT failed: {official_error}'] + list(
        wikipedia.get('notes', ()))
      return wikipedia
    except Exception as err:
      wikipedia_error = str(err) or err.__class__.__name__
      raise UrlFetcherError(
        'Could not fetch or parse the imported list.\n\nTried:\n- '
        f'Libraries ACT failed: {official_error}\n- Wikipedia failed: {wikipedia_error}')

  def fetch_parse_official(self, fetch_url, before_fetch, after_fetch, before_parse):
    if before_fetch is not None:
      before_fetch(self.URL)
    html = fetch_url(self.URL)
    if after_fetch is not None:
      after_fetch(self.URL, html)
    if before_parse is not None:
      before_parse(self.URL)
    parsed = self.create_official_parser().parse(
      html,
      self.URL,
      self.NAME,
      fetch_url=fetch_url)
    if not parsed.get('entries'):
      raise ValueError('parsed result did not contain usable entries')
    return self.with_match_series(parsed)

  def fetch_parse_wikipedia(self, fetch_url, before_fetch, after_fetch, before_parse):
    if before_fetch is not None:
      before_fetch(self.WIKIPEDIA_URL)
    html = fetch_url(self.WIKIPEDIA_URL)
    if after_fetch is not None:
      after_fetch(self.WIKIPEDIA_URL, html)
    if before_parse is not None:
      before_parse(self.WIKIPEDIA_URL)
    parsed = self.create_wikipedia_parser().parse(
      html,
      self.WIKIPEDIA_URL,
      self.NAME)
    if not parsed.get('entries'):
      raise ValueError('parsed result did not contain usable entries')
    return self.with_match_series(parsed)

  def supplement_official_winners(
      self, official, fetch_url, before_fetch, after_fetch, before_parse, log):
    try:
      wikipedia = self.fetch_parse_wikipedia(
        fetch_url, before_fetch, after_fetch, before_parse)
    except Exception as err:
      note = f'Wikipedia winner supplement failed: {err}'
      official['notes'] = list(official.get('notes', ())) + [note]
      if log is not None:
        log(note)
      return official
    supplemented = self.create_official_parser().supplement_missing_winners(
      official, wikipedia)
    return self.with_match_series(supplemented)

  def with_match_series(self, parsed):
    parsed.setdefault('match_series', self.options.get('match_series', True))
    return parsed

  def parse(self, html, **_kwargs):
    return self.create_official_parser().parse(html, self.URL, self.NAME)
