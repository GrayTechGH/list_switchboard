#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_CRIME_MYSTERY_THRILLER,
  CATEGORY_NONFICTION,
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


DAVITT_URL = 'https://www.librarything.com/award/2525/Davitt-Award'
DAVITT_WIKI_URL = 'https://en.wikipedia.org/wiki/Davitt_Award'
DAVITT_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER,)
DAVITT_NONFICTION_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER, CATEGORY_NONFICTION)
DAVITT_YA_CATEGORIES = (
  CATEGORY_CRIME_MYSTERY_THRILLER,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
)


class UrlFetcherDavittAward(UrlFetcherGeneric):

  FILTER_CATEGORIES = DAVITT_CATEGORIES
  FETCH_URLS = ()
  order = 232
  options = {'match_series': False}
  URL = DAVITT_URL
  WIKIPEDIA_URL = DAVITT_WIKI_URL
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def source_attempts(self):
    try:
      from calibre_plugins.list_switchboard.parser.davitt import (
        DavittLibraryThingParser,
        DavittWikipediaParser,
      )
    except ImportError:
      from parser.davitt import DavittLibraryThingParser, DavittWikipediaParser
    return (
      SourceAttempt(
        'LibraryThing',
        self.URL,
        lambda html, url, **_kwargs: DavittLibraryThingParser().parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES),
        source_rank=0),
      SourceAttempt(
        'Wikipedia',
        self.WIKIPEDIA_URL,
        lambda html, url, **_kwargs: DavittWikipediaParser().parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES, allowed_results=('winner',)),
        source_rank=1),
    )

  def source_choices(self):
    return SourceFallbackRunner(self.source_attempts()).source_choices()

  def fetch_and_parse(self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
                      before_fetch=None, after_fetch=None, before_parse=None,
                      force_fallback_level=0, disable_fallbacks=False, source_choice=None):
    parsed = SourceFallbackRunner(self.source_attempts(), error_class=UrlFetcherError).run(
      fetch_url,
      log=log,
      progress=progress,
      before_fetch=before_fetch,
      after_fetch=after_fetch,
      before_parse=before_parse,
      force_fallback_level=force_fallback_level,
      disable_fallbacks=disable_fallbacks,
      source_choice=source_choice)
    parsed.setdefault('match_series', False)
    return parsed


class UrlFetcherDavittAdultNovel(UrlFetcherDavittAward):
  source_id = 'davitt_award_adult_novel'
  NAME = 'Davitt Award - Adult Novel'
  CATEGORY = 'Adult Fiction'
  CATEGORY_ALIASES = ('Adult Novel',)


class UrlFetcherDavittDebutNovel(UrlFetcherDavittAward):
  source_id = 'davitt_award_debut_novel'
  NAME = 'Davitt Award - Debut Novel'
  CATEGORY = 'Debut Fiction'
  CATEGORY_ALIASES = ('Debut Crime', 'Debut Novel')


class UrlFetcherDavittNonFiction(UrlFetcherDavittAward):
  source_id = 'davitt_award_non_fiction'
  NAME = 'Davitt Award - Non-Fiction'
  FILTER_CATEGORIES = DAVITT_NONFICTION_CATEGORIES
  CATEGORY = 'Non-Fiction'
  CATEGORY_ALIASES = ('True Crime', 'Nonfiction')


class UrlFetcherDavittYoungAdultNovel(UrlFetcherDavittAward):
  source_id = 'davitt_award_young_adult_novel'
  NAME = 'Davitt Award - Young Adult Novel'
  FILTER_CATEGORIES = DAVITT_YA_CATEGORIES
  CATEGORY = 'Young Adult Novel'
  CATEGORY_ALIASES = ('Children’s/YA', 'Children\'s/YA')


class UrlFetcherDavittChildrensNovel(UrlFetcherDavittAward):
  source_id = 'davitt_award_childrens_novel'
  NAME = "Davitt Award - Children's Novel"
  FILTER_CATEGORIES = DAVITT_YA_CATEGORIES
  CATEGORY = "Children's Novel"
  CATEGORY_ALIASES = ('Children’s Novel', 'Children’s/YA', 'Children\'s/YA')
