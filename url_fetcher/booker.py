#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .booker_transport import BookerOfficialSourceAttempt

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  UrlFetcherError,
  UrlFetcherGeneric,
  parsed_source,
)

try:
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
  from calibre_plugins.list_switchboard.parser.booker_updates import fetch_booker_years
  from calibre_plugins.list_switchboard.parser.booker_modern import index_links
except ImportError:
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner
  from parser.booker_updates import fetch_booker_years
  from parser.booker_modern import index_links


BOOKER_PRIZE_YEARS_URL = 'https://thebookerprizes.com/the-booker-library/prize-years'
BOOKER_PRIZE_WIKIPEDIA_URL = (
  'https://en.wikipedia.org/wiki/List_of_winners_and_nominated_authors_of_the_Booker_Prize'
)
INTERNATIONAL_BOOKER_PRIZE_WIKIPEDIA_URL = (
  'https://en.wikipedia.org/wiki/International_Booker_Prize'
)


class UrlFetcherBookerPrizeBase(UrlFetcherGeneric):

  URL = BOOKER_PRIZE_YEARS_URL
  FETCH_URLS = (BOOKER_PRIZE_YEARS_URL,)
  order = 181
  options = {'match_series': False}
  AWARD_NAME = ''
  CATEGORY = ''
  YEAR_URL_PATTERN = ''
  WIKIPEDIA_URL = ''
  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.booker import (
        BookerPrizeOfficialParser,
      )
    except ImportError:
      from parser.booker import BookerPrizeOfficialParser
    return BookerPrizeOfficialParser(self.AWARD_NAME, self.CATEGORY)

  def create_wikipedia_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.booker import (
        BookerPrizeWikipediaParser,
      )
    except ImportError:
      from parser.booker import BookerPrizeWikipediaParser
    return BookerPrizeWikipediaParser(self.AWARD_NAME, self.CATEGORY)

  def source_attempts(self):
    return (
      BookerOfficialSourceAttempt(self,
        'Official Booker',
        self.URL,
        lambda html, url, fetch_url=None, cached_parsed=None, incremental_update=False, progress=None, **_kwargs: self.parse_official_years(
          html,
          url,
          fetch_url,
          self.parser(), cached_parsed, incremental_update, progress),
        source_rank=0, supports_incremental=True),
      SourceAttempt(
        'Wikipedia',
        self.WIKIPEDIA_URL,
        lambda html, url, **_kwargs: self.create_wikipedia_parser().parse(
          html,
          url,
          self.NAME,
          self.CATEGORY),
        source_rank=1),
    )

  def source_choices(self):
    return SourceFallbackRunner(self.source_attempts()).source_choices()

  def fetch_and_parse(
      self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
      before_fetch=None, after_fetch=None, before_parse=None,
      force_fallback_level=0, disable_fallbacks=False, source_choice=None,
      cached_parsed=None, incremental_update=False):
    parsed = SourceFallbackRunner(
      self.source_attempts(),
      error_class=UrlFetcherError).run(
        fetch_url,
        log=log,
        progress=progress,
        before_fetch=before_fetch,
        after_fetch=after_fetch,
        before_parse=before_parse,
        force_fallback_level=force_fallback_level,
        disable_fallbacks=disable_fallbacks,
        source_choice=source_choice, cached_parsed=cached_parsed,
        incremental_update=incremental_update)
    parsed.setdefault('match_series', self.options.get('match_series', True))
    return parsed

  def parse(self, html, **_kwargs):
    return self.parse_official_years(html, self.URL, None, self.parser())

  def parse_official_years(self, html, base_url, fetch_url, parser,
      cached_parsed=None, incremental_update=False, progress=None):
    if fetch_url is None:
      return parser.parse(html, base_url, self.NAME, self.CATEGORY)
    parsed = fetch_booker_years(self, parser, html, base_url, fetch_url,
      cached_parsed, incremental_update, progress)
    if not parsed.get('entries'):
      raise UrlFetcherError('Official Booker Library produced no entries')
    parsed['source'] = parsed_source(self.NAME, base_url, self.source_id)
    return parsed

  def year_urls(self, html, base_url):
    return index_links(html, base_url, self.YEAR_URL_PATTERN)[0]


class UrlFetcherBookerPrize(UrlFetcherBookerPrizeBase):
  SUPPORTS_INCREMENTAL_UPDATE = True
  FIRST_YEAR = 1969
  source_id = 'booker_prize'
  NAME = 'Booker Prize'
  AWARD_NAME = NAME
  CATEGORY = 'Fiction'
  YEAR_URL_PATTERN = r'/the-booker-library/prize-years/(?:19|20)\d{2}$'
  WIKIPEDIA_URL = BOOKER_PRIZE_WIKIPEDIA_URL


class UrlFetcherInternationalBookerPrize(UrlFetcherBookerPrizeBase):
  SUPPORTS_INCREMENTAL_UPDATE = True
  FIRST_YEAR = 2005
  source_id = 'international_booker_prize'
  NAME = 'International Booker Prize'
  AWARD_NAME = NAME
  CATEGORY = 'Translated Fiction'
  YEAR_URL_PATTERN = r'/the-booker-library/prize-years/international/(?:19|20)\d{2}$'
  WIKIPEDIA_URL = INTERNATIONAL_BOOKER_PRIZE_WIKIPEDIA_URL
