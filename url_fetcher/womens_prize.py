#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  UrlFetcherError,
  UrlFetcherGeneric,
)

try:
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
except ImportError:
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner


WOMENS_PRIZE_NONFICTION_URL = (
  'https://womensprize.com/prizes/womens-prize-for-non-fiction/'
)
WOMENS_PRIZE_FICTION_URL = (
  'https://womensprize.com/prizes/womens-prize-for-fiction/'
)
WOMENS_PRIZE_NONFICTION_WIKIPEDIA_URL = (
  'https://en.wikipedia.org/wiki/Women%27s_Prize_for_Non-Fiction'
)
WOMENS_PRIZE_FICTION_WIKIPEDIA_URL = (
  'https://en.wikipedia.org/wiki/List_of_Women%27s_Prize_for_Fiction_winners'
)


class UrlFetcherWomensPrize(UrlFetcherGeneric):

  URL = ''
  FETCH_URLS = ()
  order = 178
  options = {'match_series': False}
  AWARD_NAME = ''
  CATEGORY = ''
  PRIZE_ALIASES = ()
  WIKIPEDIA_URL = ''

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.womens_prize import (
        WomensPrizeOfficialParser,
      )
    except ImportError:
      from parser.womens_prize import WomensPrizeOfficialParser
    return WomensPrizeOfficialParser(
      self.AWARD_NAME,
      self.CATEGORY,
      self.PRIZE_ALIASES)

  def create_wikipedia_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.womens_prize import (
        WomensPrizeWikipediaParser,
      )
    except ImportError:
      from parser.womens_prize import WomensPrizeWikipediaParser
    return WomensPrizeWikipediaParser(
      self.AWARD_NAME,
      self.CATEGORY,
      self.PRIZE_ALIASES)

  def source_attempts(self):
    return (
      SourceAttempt(
        'Official Women\'s Prize',
        self.URL,
        lambda html, url, fetch_url=None, **_kwargs: self.parser().parse(
          html,
          url,
          self.NAME,
          self.CATEGORY,
          fetch_url=fetch_url),
        source_rank=0),
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
      force_fallback_level=0, disable_fallbacks=False, source_choice=None):
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
        source_choice=source_choice)
    parsed.setdefault('match_series', self.options.get('match_series', True))
    return parsed

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME, self.CATEGORY)


class UrlFetcherWomensPrizeNonFiction(UrlFetcherWomensPrize):
  source_id = 'womens_prize_nonfiction'
  NAME = 'Women\'s Prize for Non-Fiction'
  URL = WOMENS_PRIZE_NONFICTION_URL
  FETCH_URLS = (WOMENS_PRIZE_NONFICTION_URL,)
  AWARD_NAME = NAME
  CATEGORY = 'Non-Fiction'
  PRIZE_ALIASES = (
    'Women\'s Prize for Non-Fiction',
    'Women\'s Prize for Non Fiction',
  )
  WIKIPEDIA_URL = WOMENS_PRIZE_NONFICTION_WIKIPEDIA_URL
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )


class UrlFetcherWomensPrizeFiction(UrlFetcherWomensPrize):
  source_id = 'womens_prize_fiction'
  NAME = 'Women\'s Prize for Fiction'
  URL = WOMENS_PRIZE_FICTION_URL
  FETCH_URLS = (WOMENS_PRIZE_FICTION_URL,)
  AWARD_NAME = NAME
  CATEGORY = 'Fiction'
  PRIZE_ALIASES = (
    'Women\'s Prize for Fiction',
    'Orange Prize for Fiction',
    'Baileys Women\'s Prize for Fiction',
  )
  WIKIPEDIA_URL = WOMENS_PRIZE_FICTION_WIKIPEDIA_URL
  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
