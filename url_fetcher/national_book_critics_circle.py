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


OFFICIAL_URL = 'https://www.bookcritics.org/past-awards/'

WIKIPEDIA_URLS = {
  'fiction': 'https://en.wikipedia.org/wiki/National_Book_Critics_Circle_Award_for_Fiction',
  'nonfiction': 'https://en.wikipedia.org/wiki/National_Book_Critics_Circle_Award_for_Nonfiction',
  'biography': 'https://en.wikipedia.org/wiki/National_Book_Critics_Circle_Award_for_Biography',
  'memoir_autobiography': 'https://en.wikipedia.org/wiki/National_Book_Critics_Circle_Award_for_Memoir_and_Autobiography',
  'poetry': 'https://en.wikipedia.org/wiki/National_Book_Critics_Circle_Award_for_Poetry',
  'criticism': 'https://en.wikipedia.org/wiki/National_Book_Critics_Circle_Award_for_Criticism',
  'john_leonard': 'https://en.wikipedia.org/wiki/John_Leonard_Prize',
  'gregg_barrios_translation': 'https://en.wikipedia.org/wiki/Gregg_Barrios_Book_in_Translation_Prize',
}


class UrlFetcherNationalBookCriticsCircleAward(UrlFetcherGeneric):

  URL = OFFICIAL_URL
  FETCH_URLS = ()
  order = 242
  options = {'match_series': False}
  AWARD_NAME = 'National Book Critics Circle Award'
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  WIKIPEDIA_KEY = ''

  @property
  def WIKIPEDIA_URL(self):
    return WIKIPEDIA_URLS[self.WIKIPEDIA_KEY]

  def create_official_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.national_book_critics_circle import (
        NationalBookCriticsCircleOfficialParser,
      )
    except ImportError:
      from parser.national_book_critics_circle import (
        NationalBookCriticsCircleOfficialParser,
      )
    return NationalBookCriticsCircleOfficialParser(
      self.CATEGORY, self.CATEGORY_ALIASES)

  def create_wikipedia_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.national_book_critics_circle import (
        NationalBookCriticsCircleWikipediaParser,
      )
    except ImportError:
      from parser.national_book_critics_circle import (
        NationalBookCriticsCircleWikipediaParser,
      )
    return NationalBookCriticsCircleWikipediaParser(
      self.CATEGORY, self.CATEGORY_ALIASES)

  def source_attempts(self):
    return (
      SourceAttempt(
        'NBCC',
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


class UrlFetcherNationalBookCriticsCircleFiction(
    UrlFetcherNationalBookCriticsCircleAward):

  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'national_book_critics_circle_fiction'
  NAME = 'National Book Critics Circle Award - Fiction'
  CATEGORY = 'Fiction'
  CATEGORY_ALIASES = ('Fiction',)
  WIKIPEDIA_KEY = 'fiction'


class UrlFetcherNationalBookCriticsCircleNonfiction(
    UrlFetcherNationalBookCriticsCircleAward):

  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'national_book_critics_circle_nonfiction'
  NAME = 'National Book Critics Circle Award - Nonfiction'
  CATEGORY = 'Nonfiction'
  CATEGORY_ALIASES = ('Nonfiction', 'Non-fiction')
  WIKIPEDIA_KEY = 'nonfiction'


class UrlFetcherNationalBookCriticsCircleBiography(
    UrlFetcherNationalBookCriticsCircleAward):

  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'national_book_critics_circle_biography'
  NAME = 'National Book Critics Circle Award - Biography'
  CATEGORY = 'Biography'
  CATEGORY_ALIASES = ('Biography',)
  WIKIPEDIA_KEY = 'biography'


class UrlFetcherNationalBookCriticsCircleMemoirAutobiography(
    UrlFetcherNationalBookCriticsCircleAward):

  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'national_book_critics_circle_memoir_autobiography'
  NAME = 'National Book Critics Circle Award - Memoir/Autobiography'
  CATEGORY = 'Memoir/Autobiography'
  CATEGORY_ALIASES = (
    'Memoir/Autobiography',
    'Memoir and Autobiography',
    'Memoir & Autobiography',
    'Autobiography',
    'Memoir',
  )
  WIKIPEDIA_KEY = 'memoir_autobiography'


class UrlFetcherNationalBookCriticsCirclePoetry(
    UrlFetcherNationalBookCriticsCircleAward):

  FILTER_CATEGORIES = (CATEGORY_REGIONAL_NATIONAL_AWARDS,)
  source_id = 'national_book_critics_circle_poetry'
  NAME = 'National Book Critics Circle Award - Poetry'
  CATEGORY = 'Poetry'
  CATEGORY_ALIASES = ('Poetry',)
  WIKIPEDIA_KEY = 'poetry'


class UrlFetcherNationalBookCriticsCircleCriticism(
    UrlFetcherNationalBookCriticsCircleAward):

  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'national_book_critics_circle_criticism'
  NAME = 'National Book Critics Circle Award - Criticism'
  CATEGORY = 'Criticism'
  CATEGORY_ALIASES = ('Criticism',)
  WIKIPEDIA_KEY = 'criticism'


class UrlFetcherNationalBookCriticsCircleJohnLeonard(
    UrlFetcherNationalBookCriticsCircleAward):

  FILTER_CATEGORIES = (CATEGORY_REGIONAL_NATIONAL_AWARDS,)
  source_id = 'national_book_critics_circle_john_leonard'
  NAME = 'National Book Critics Circle Award - John Leonard Prize'
  CATEGORY = 'John Leonard Prize'
  CATEGORY_ALIASES = (
    'John Leonard Prize',
    'John Leonard Award',
    'John Leonard Prize for Best First Book',
    'Best First Book',
  )
  WIKIPEDIA_KEY = 'john_leonard'


class UrlFetcherNationalBookCriticsCircleGreggBarriosTranslation(
    UrlFetcherNationalBookCriticsCircleAward):

  FILTER_CATEGORIES = (CATEGORY_REGIONAL_NATIONAL_AWARDS,)
  source_id = 'national_book_critics_circle_gregg_barrios_translation'
  NAME = 'National Book Critics Circle Award - Gregg Barrios Book in Translation Prize'
  CATEGORY = 'Gregg Barrios Book in Translation Prize'
  CATEGORY_ALIASES = (
    'Gregg Barrios Book in Translation Prize',
    'Gregg Barrios Book in Translation',
    'Book in Translation',
    'Gregg Barrios',
  )
  WIKIPEDIA_KEY = 'gregg_barrios_translation'
