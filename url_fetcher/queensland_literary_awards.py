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


OFFICIAL_URL = 'https://www.slq.qld.gov.au/queensland-literary-awards/past-winners'
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Queensland_Literary_Awards'


class UrlFetcherQueenslandLiteraryAwards(UrlFetcherGeneric):

  URL = OFFICIAL_URL
  WIKIPEDIA_URL = WIKIPEDIA_URL
  FETCH_URLS = ()
  order = 243
  options = {'match_series': False}
  AWARD_NAME = 'Queensland Literary Awards'
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_official_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.queensland_literary_awards import (
        QueenslandLiteraryAwardsOfficialParser,
      )
    except ImportError:
      from parser.queensland_literary_awards import (
        QueenslandLiteraryAwardsOfficialParser,
      )
    return QueenslandLiteraryAwardsOfficialParser(
      self.CATEGORY, self.CATEGORY_ALIASES)

  def create_wikipedia_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.queensland_literary_awards import (
        QueenslandLiteraryAwardsWikipediaParser,
      )
    except ImportError:
      from parser.queensland_literary_awards import (
        QueenslandLiteraryAwardsWikipediaParser,
      )
    return QueenslandLiteraryAwardsWikipediaParser(
      self.CATEGORY, self.CATEGORY_ALIASES)

  def source_attempts(self):
    return (
      SourceAttempt(
        'State Library of Queensland',
        self.URL,
        lambda html, url, **_kwargs: self.create_official_parser().parse(
          html, url, self.NAME),
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

  def parse(self, html, **_kwargs):
    return self.create_official_parser().parse(html, self.URL, self.NAME)


class UrlFetcherQueenslandLiteraryAwardsStateSignificance(
    UrlFetcherQueenslandLiteraryAwards):

  FILTER_CATEGORIES = (CATEGORY_REGIONAL_NATIONAL_AWARDS,)
  source_id = 'queensland_literary_awards_state_significance'
  NAME = 'Queensland Literary Awards - Work of State Significance'
  CATEGORY = 'Work of State Significance'
  CATEGORY_ALIASES = (
    'Queensland Premier\'s Award for a Work of State Significance',
    'Queensland Premier’s Award for a Work of State Significance',
    'Queensland Premier\'s Award for a Work of State Signiﬁcance',
    'Premier\'s Award for a Work of State Significance',
    'Work of State Significance',
  )


class UrlFetcherQueenslandLiteraryAwardsFiction(
    UrlFetcherQueenslandLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'queensland_literary_awards_fiction'
  NAME = 'Queensland Literary Awards - Fiction'
  CATEGORY = 'Fiction'
  CATEGORY_ALIASES = (
    'The University of Queensland Fiction Book Award',
    'University of Queensland Fiction Book Award',
    'Fiction Book Award',
    'Fiction',
  )


class UrlFetcherQueenslandLiteraryAwardsNonfiction(
    UrlFetcherQueenslandLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'queensland_literary_awards_nonfiction'
  NAME = 'Queensland Literary Awards - Non-Fiction'
  CATEGORY = 'Non-Fiction'
  CATEGORY_ALIASES = (
    'The University of Queensland Non-Fiction Book Award',
    'University of Queensland Non-Fiction Book Award',
    'University of Queensland Nonfiction Book Award',
    'Non-Fiction Book Award',
    'Nonfiction Book Award',
    'Non-Fiction',
    'Nonfiction',
  )


class UrlFetcherQueenslandLiteraryAwardsChildrens(
    UrlFetcherQueenslandLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'queensland_literary_awards_childrens'
  NAME = "Queensland Literary Awards - Children's Book"
  CATEGORY = "Children's Book"
  CATEGORY_ALIASES = (
    "Children's Book Award",
    "Griffith University Children's Book Award",
    "Griffith University Children’s Book Award",
    "Children's Book",
  )


class UrlFetcherQueenslandLiteraryAwardsYoungAdult(
    UrlFetcherQueenslandLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'queensland_literary_awards_young_adult'
  NAME = 'Queensland Literary Awards - Young Adult Book'
  CATEGORY = 'Young Adult Book'
  CATEGORY_ALIASES = (
    'Young Adult Book Award',
    'Griffith University Young Adult Book Award',
    'Young Adult Book',
  )


class UrlFetcherQueenslandLiteraryAwardsPeoplesChoice(
    UrlFetcherQueenslandLiteraryAwards):

  FILTER_CATEGORIES = (CATEGORY_REGIONAL_NATIONAL_AWARDS,)
  source_id = 'queensland_literary_awards_peoples_choice'
  NAME = "Queensland Literary Awards - People's Choice"
  CATEGORY = "People's Choice"
  CATEGORY_ALIASES = (
    "People's Choice Queensland Book of the Year Award",
    "People’s Choice Queensland Book of the Year Award",
    "Courier-Mail People's Choice Queensland Book of the Year Award",
    "The Courier-Mail People's Choice Queensland Book of the Year Award",
    "People's Choice",
  )
