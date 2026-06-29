#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherError,
  UrlFetcherGeneric,
)

try:
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
except ImportError:
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner


OFFICIAL_URL = 'https://nerobookawards.com/key-dates/'
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Nero_Book_Awards'


class UrlFetcherNeroBookAwards(UrlFetcherGeneric):

  URL = OFFICIAL_URL
  WIKIPEDIA_URL = WIKIPEDIA_URL
  order = 242
  options = {'match_series': False}
  AWARD_NAME = 'Nero Book Awards'
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_official_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.nero_book_awards import (
        NeroBookAwardsOfficialParser,
      )
    except ImportError:
      from parser.nero_book_awards import NeroBookAwardsOfficialParser
    return NeroBookAwardsOfficialParser(self.CATEGORY, self.CATEGORY_ALIASES)

  def create_wikipedia_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.nero_book_awards import (
        NeroBookAwardsWikipediaParser,
      )
    except ImportError:
      from parser.nero_book_awards import NeroBookAwardsWikipediaParser
    return NeroBookAwardsWikipediaParser(self.CATEGORY, self.CATEGORY_ALIASES)

  def source_attempts(self):
    return (
      SourceAttempt(
        'Nero Book Awards',
        self.URL,
        lambda html, url, fetch_url=None, log=None, progress=None: (
          self.create_official_parser().parse(
            html, url, self.NAME, fetch_url=fetch_url, log=log, progress=progress)),
        source_rank=0),
      SourceAttempt(
        'Wikipedia',
        self.WIKIPEDIA_URL,
        lambda html, url, **_kwargs: self.create_wikipedia_parser().parse(
          html, url, self.NAME),
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

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.create_official_parser().parse(
      html, self.URL, self.NAME, fetch_url=fetch_url, log=log, progress=progress)


class UrlFetcherNeroBookAwardsFiction(UrlFetcherNeroBookAwards):

  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'nero_book_awards_fiction'
  NAME = 'Nero Book Awards - Fiction'
  CATEGORY = 'Fiction'
  CATEGORY_ALIASES = ('Fiction',)


class UrlFetcherNeroBookAwardsDebutFiction(UrlFetcherNeroBookAwards):

  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'nero_book_awards_debut_fiction'
  NAME = 'Nero Book Awards - Debut Fiction'
  CATEGORY = 'Debut Fiction'
  CATEGORY_ALIASES = ('Debut Fiction', 'Debut')


class UrlFetcherNeroBookAwardsNonfiction(UrlFetcherNeroBookAwards):

  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'nero_book_awards_nonfiction'
  NAME = 'Nero Book Awards - Non-Fiction'
  CATEGORY = 'Non-Fiction'
  CATEGORY_ALIASES = ('Non-Fiction', 'Nonfiction', 'Non Fiction')


class UrlFetcherNeroBookAwardsChildrensFiction(UrlFetcherNeroBookAwards):

  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'nero_book_awards_childrens_fiction'
  NAME = "Nero Book Awards - Children's Fiction"
  CATEGORY = "Children's Fiction"
  CATEGORY_ALIASES = (
    "Children's Fiction",
    'Children’s Fiction',
    'Childrens Fiction',
  )


class UrlFetcherNeroBookAwardsGoldPrize(UrlFetcherNeroBookAwards):

  FILTER_CATEGORIES = (CATEGORY_REGIONAL_NATIONAL_AWARDS,)
  source_id = 'nero_book_awards_gold_prize'
  NAME = 'Nero Gold Prize / Book of the Year'
  CATEGORY = 'Nero Gold Prize'
  CATEGORY_ALIASES = (
    'Nero Gold Prize',
    'Overall winner',
    'Book of the Year',
  )
