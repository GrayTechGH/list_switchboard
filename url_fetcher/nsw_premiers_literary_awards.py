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


OFFICIAL_ROOT_URL = 'https://www.sl.nsw.gov.au/awards/nsw-literary-awards'
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/New_South_Wales_Premier%27s_Literary_Awards'


class UrlFetcherNSWPremiersLiteraryAwards(UrlFetcherGeneric):

  URL = OFFICIAL_ROOT_URL
  WIKIPEDIA_URL = WIKIPEDIA_URL
  FETCH_URLS = ()
  order = 242
  options = {'match_series': False}
  AWARD_NAME = "NSW Premier's Literary Awards"
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  USE_WIKIPEDIA_FALLBACK = False

  def create_official_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.nsw_premiers_literary_awards import (
        NSWPremiersLiteraryAwardsOfficialParser,
      )
    except ImportError:
      from parser.nsw_premiers_literary_awards import (
        NSWPremiersLiteraryAwardsOfficialParser,
      )
    return NSWPremiersLiteraryAwardsOfficialParser(
      self.CATEGORY, self.CATEGORY_ALIASES)

  def create_wikipedia_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.nsw_premiers_literary_awards import (
        NSWPremiersLiteraryAwardsWikipediaParser,
      )
    except ImportError:
      from parser.nsw_premiers_literary_awards import (
        NSWPremiersLiteraryAwardsWikipediaParser,
      )
    return NSWPremiersLiteraryAwardsWikipediaParser(
      self.CATEGORY, self.CATEGORY_ALIASES)

  def source_attempts(self):
    attempts = [
      SourceAttempt(
        'State Library NSW',
        self.URL,
        lambda html, url, **_kwargs: self.create_official_parser().parse(
          html, url, self.NAME),
        source_rank=0),
    ]
    if self.USE_WIKIPEDIA_FALLBACK:
      attempts.append(SourceAttempt(
        'Wikipedia',
        self.WIKIPEDIA_URL,
        lambda html, url, **_kwargs: self.create_wikipedia_parser().parse(
          html, url, self.NAME),
        source_rank=1))
    return tuple(attempts)

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
    return self.create_official_parser().parse(html, self.URL, self.NAME)


class UrlFetcherNSWPremiersLiteraryAwardsChristinaSteadFiction(
    UrlFetcherNSWPremiersLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'nsw_premiers_literary_awards_christina_stead_fiction'
  NAME = "NSW Premier's Literary Awards - Christina Stead Prize for Fiction"
  URL = f'{OFFICIAL_ROOT_URL}/christina-stead-prize-fiction'
  CATEGORY = 'Christina Stead Prize for Fiction'
  CATEGORY_ALIASES = ('Christina Stead Prize for Fiction', 'Fiction')


class UrlFetcherNSWPremiersLiteraryAwardsDouglasStewartNonfiction(
    UrlFetcherNSWPremiersLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'nsw_premiers_literary_awards_douglas_stewart_nonfiction'
  NAME = "NSW Premier's Literary Awards - Douglas Stewart Prize for Non-Fiction"
  URL = f'{OFFICIAL_ROOT_URL}/douglas-stewart-prize-non-fiction'
  CATEGORY = 'Douglas Stewart Prize for Non-Fiction'
  CATEGORY_ALIASES = (
    'Douglas Stewart Prize for Non-Fiction',
    'Douglas Stewart Prize for Nonfiction',
    'Non-Fiction',
    'Nonfiction',
  )


class UrlFetcherNSWPremiersLiteraryAwardsPatriciaWrightsonChildrens(
    UrlFetcherNSWPremiersLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'nsw_premiers_literary_awards_patricia_wrightson_childrens'
  NAME = "NSW Premier's Literary Awards - Patricia Wrightson Prize for Children's Literature"
  URL = f'{OFFICIAL_ROOT_URL}/patricia-wrightson-prize-childrens-literature'
  CATEGORY = "Patricia Wrightson Prize for Children's Literature"
  CATEGORY_ALIASES = (
    "Patricia Wrightson Prize for Children's Literature",
    "Children's Literature",
  )


class UrlFetcherNSWPremiersLiteraryAwardsEthelTurnerYoungPeople(
    UrlFetcherNSWPremiersLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'nsw_premiers_literary_awards_ethel_turner_young_people'
  NAME = "NSW Premier's Literary Awards - Ethel Turner Prize for Young People's Literature"
  URL = f'{OFFICIAL_ROOT_URL}/ethel-turner-prize-young-peoples-literature'
  CATEGORY = "Ethel Turner Prize for Young People's Literature"
  CATEGORY_ALIASES = (
    "Ethel Turner Prize for Young People's Literature",
    "Young People's Literature",
    'Young Adult Literature',
  )


class UrlFetcherNSWPremiersLiteraryAwardsIndigenousWriters(
    UrlFetcherNSWPremiersLiteraryAwards):

  FILTER_CATEGORIES = (CATEGORY_REGIONAL_NATIONAL_AWARDS,)
  source_id = 'nsw_premiers_literary_awards_indigenous_writers'
  NAME = "NSW Premier's Literary Awards - Indigenous Writers' Prize"
  URL = f'{OFFICIAL_ROOT_URL}/indigenous-writers-prize'
  CATEGORY = "Indigenous Writers' Prize"
  CATEGORY_ALIASES = ("Indigenous Writers' Prize", 'Indigenous Writing')


class UrlFetcherNSWPremiersLiteraryAwardsGlendaAdamsNewWriting(
    UrlFetcherNSWPremiersLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'nsw_premiers_literary_awards_glenda_adams_new_writing'
  NAME = "NSW Premier's Literary Awards - UTS Glenda Adams Award for New Writing"
  URL = f'{OFFICIAL_ROOT_URL}/uts-glenda-adams-award-new-writing'
  CATEGORY = 'UTS Glenda Adams Award for New Writing'
  CATEGORY_ALIASES = (
    'UTS Glenda Adams Award for New Writing',
    'Glenda Adams Award for New Writing',
    'New Writing',
  )


class UrlFetcherNSWPremiersLiteraryAwardsMulticulturalNSW(
    UrlFetcherNSWPremiersLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'nsw_premiers_literary_awards_multicultural_nsw'
  NAME = "NSW Premier's Literary Awards - Multicultural NSW Award"
  URL = f'{OFFICIAL_ROOT_URL}/multicultural-nsw-award'
  CATEGORY = 'Multicultural NSW Award'
  CATEGORY_ALIASES = ('Multicultural NSW Award', 'Multicultural Award')


class UrlFetcherNSWPremiersLiteraryAwardsBookOfTheYear(
    UrlFetcherNSWPremiersLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'nsw_premiers_literary_awards_book_of_the_year'
  NAME = "NSW Premier's Literary Awards - Book of the Year"
  URL = f'{OFFICIAL_ROOT_URL}/book-year'
  CATEGORY = 'Book of the Year'
  CATEGORY_ALIASES = ('Book of the Year',)
  USE_WIKIPEDIA_FALLBACK = True


class UrlFetcherNSWPremiersLiteraryAwardsPeoplesChoice(
    UrlFetcherNSWPremiersLiteraryAwards):

  FILTER_CATEGORIES = (CATEGORY_REGIONAL_NATIONAL_AWARDS,)
  source_id = 'nsw_premiers_literary_awards_peoples_choice'
  NAME = "NSW Premier's Literary Awards - People's Choice Award"
  URL = f'{OFFICIAL_ROOT_URL}/university-sydney-peoples-choice-award'
  CATEGORY = "People's Choice Award"
  CATEGORY_ALIASES = (
    "People's Choice Award",
    "The University of Sydney People's Choice Award",
    "The University of Sydney People’s Choice Award",
    'University of Sydney Peoples Choice Award',
  )
  USE_WIKIPEDIA_FALLBACK = True
