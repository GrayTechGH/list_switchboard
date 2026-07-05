#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_HORROR_DARK_FICTION,
  CATEGORY_NONFICTION,
  UrlFetcherError,
  UrlFetcherGeneric,
)

try:
  from calibre_plugins.list_switchboard.parser.international_horror_guild import (
    OFFICIAL_FINAL_URL, SFADB_URL,
  )
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
except ImportError:
  from parser.international_horror_guild import OFFICIAL_FINAL_URL, SFADB_URL
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner


IHG_CATEGORIES = (CATEGORY_HORROR_DARK_FICTION,)
IHG_NONFICTION_CATEGORIES = (
  CATEGORY_HORROR_DARK_FICTION,
  CATEGORY_NONFICTION,
)


class UrlFetcherInternationalHorrorGuild(UrlFetcherGeneric):

  URL = OFFICIAL_FINAL_URL
  FETCH_URLS = ()
  FILTER_CATEGORIES = IHG_CATEGORIES
  order = 141
  options = {'match_series': False}
  AWARD_NAME = 'International Horror Guild Award'
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.international_horror_guild import (
        InternationalHorrorGuildParser,
      )
    except ImportError:
      from parser.international_horror_guild import InternationalHorrorGuildParser
    return InternationalHorrorGuildParser()

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
        source_choice=source_choice)
    parsed.setdefault('match_series', self.options.get('match_series', True))
    return parsed

  def source_attempts(self):
    parser = self.parser()
    return (
      SourceAttempt(
        'International Horror Guild',
        OFFICIAL_FINAL_URL,
        lambda html, url, fetch_url=None, log=None, progress=None: (
          parser.parse_official(
            html,
            url,
            self.NAME,
            self.CATEGORY,
            self.CATEGORY_ALIASES,
            fetch_url=fetch_url,
            log=log,
            progress=progress)),
        source_rank=0),
      SourceAttempt(
        'SFADB',
        SFADB_URL,
        lambda html, url, fetch_url=None, log=None, progress=None: (
          parser.parse_sfadb(
            html,
            url,
            self.NAME,
            self.CATEGORY,
            self.CATEGORY_ALIASES,
            fetch_url=fetch_url,
            log=log,
            progress=progress)),
        source_rank=1),
    )

  def source_choices(self):
    return SourceFallbackRunner(self.source_attempts()).source_choices()

  def parse(self, html, **_kwargs):
    return self.parser().parse_official(
      html,
      self.URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES)


class UrlFetcherInternationalHorrorGuildNovel(UrlFetcherInternationalHorrorGuild):
  source_id = 'international_horror_guild_novel'
  NAME = 'International Horror Guild - Novel'
  CATEGORY = 'Novel'
  CATEGORY_ALIASES = ('novel',)


class UrlFetcherInternationalHorrorGuildFirstNovel(UrlFetcherInternationalHorrorGuild):
  source_id = 'international_horror_guild_first_novel'
  NAME = 'International Horror Guild - First Novel'
  CATEGORY = 'First Novel'
  CATEGORY_ALIASES = ('first novel',)


class UrlFetcherInternationalHorrorGuildLongFiction(UrlFetcherInternationalHorrorGuild):
  source_id = 'international_horror_guild_long_fiction'
  NAME = 'International Horror Guild - Long Fiction'
  CATEGORY = 'Long Fiction'
  CATEGORY_ALIASES = ('long fiction',)


class UrlFetcherInternationalHorrorGuildMidLengthFiction(UrlFetcherInternationalHorrorGuild):
  source_id = 'international_horror_guild_mid_length_fiction'
  NAME = 'International Horror Guild - Mid-Length Fiction'
  CATEGORY = 'Mid-Length Fiction'
  CATEGORY_ALIASES = ('mid-length fiction', 'mid length fiction')


class UrlFetcherInternationalHorrorGuildCollection(UrlFetcherInternationalHorrorGuild):
  source_id = 'international_horror_guild_collection'
  NAME = 'International Horror Guild - Collection'
  CATEGORY = 'Collection'
  CATEGORY_ALIASES = (
    'collection',
    'collection single author',
    'fiction collection',
  )


class UrlFetcherInternationalHorrorGuildAnthology(UrlFetcherInternationalHorrorGuild):
  source_id = 'international_horror_guild_anthology'
  NAME = 'International Horror Guild - Anthology'
  CATEGORY = 'Anthology'
  CATEGORY_ALIASES = ('anthology',)


class UrlFetcherInternationalHorrorGuildNonfiction(UrlFetcherInternationalHorrorGuild):
  source_id = 'international_horror_guild_nonfiction'
  NAME = 'International Horror Guild - Non-Fiction'
  FILTER_CATEGORIES = IHG_NONFICTION_CATEGORIES
  CATEGORY = 'Non-Fiction'
  CATEGORY_ALIASES = ('non-fiction', 'non fiction', 'nonfiction')


class UrlFetcherInternationalHorrorGuildIllustratedNarrative(UrlFetcherInternationalHorrorGuild):
  source_id = 'international_horror_guild_illustrated_narrative'
  NAME = 'International Horror Guild - Illustrated Narrative'
  CATEGORY = 'Illustrated Narrative'
  CATEGORY_ALIASES = (
    'illustrated narrative',
    'illustrated narrativel',
    'graphic story/illustrated narrative',
    'graphic story illustrated narrative',
  )
