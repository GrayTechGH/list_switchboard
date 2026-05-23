#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_FANTASY,
  CATEGORY_SCIENCE_FICTION,
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


class UrlFetcherNebulaAwardsNovel(UrlFetcherGeneric):

  source_id = 'nebula_awards_novel'
  NAME = 'Nebula Awards - Novel'
  FILTER_CATEGORIES = (
    CATEGORY_SCIENCE_FICTION,
    CATEGORY_FANTASY,
  )
  URL = 'https://nebulas.sfwa.org/award/best-novel/'
  FETCH_URLS = (
    'https://nebulas.sfwa.org/award/best-novel/',
  )
  SFADB_URL = 'https://www.sfadb.com/Nebula_Awards'
  order = 60
  options = {
    'match_series': False,
  }

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.nebula import NebulaAwardsNovelParser
    except ImportError:
      from parser.nebula import NebulaAwardsNovelParser

    return NebulaAwardsNovelParser()

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

  def source_attempts(self):
    parser = self.parser()
    return (
      SourceAttempt(
        'Official SFWA',
        self.URL,
        parser.parse_official,
        source_rank=0),
      SourceAttempt(
        'SFADB',
        self.SFADB_URL,
        parser.parse_sfadb,
        source_rank=1),
    )

  def source_choices(self):
    return SourceFallbackRunner(self.source_attempts()).source_choices()

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    base_url = getattr(self, '_last_fetch_url', None) or self.URL
    return self.parser().parse(
      html,
      base_url,
      fetch_url=fetch_url,
      log=log,
      progress=progress)


class UrlFetcherNebulaSFADBCategory(UrlFetcherGeneric):

  URL = 'https://www.sfadb.com/Nebula_Awards'
  FETCH_URLS = (URL,)
  FILTER_CATEGORIES = (
    CATEGORY_SCIENCE_FICTION,
    CATEGORY_FANTASY,
  )
  order = 61
  options = {
    'match_series': False,
  }
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.nebula import NebulaSFADBCategoryParser
    except ImportError:
      from parser.nebula import NebulaSFADBCategoryParser

    return NebulaSFADBCategoryParser()

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES,
      fetch_url=fetch_url,
      log=log,
      progress=progress)


class UrlFetcherNebulaAwardsNovella(UrlFetcherNebulaSFADBCategory):
  source_id = 'nebula_awards_novella'
  NAME = 'Nebula Awards - Novella'
  CATEGORY = 'Best Novella'
  CATEGORY_ALIASES = ('best novella', 'novella')


class UrlFetcherNebulaAndreNorton(UrlFetcherNebulaSFADBCategory):
  source_id = 'nebula_andre_norton_middle_grade_young_adult'
  NAME = 'Nebula Awards - Andre Norton Middle Grade/YA'
  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_SCIENCE_FICTION,
    CATEGORY_FANTASY,
  )
  CATEGORY = 'Andre Norton Middle Grade and Young Adult Fiction'
  CATEGORY_ALIASES = (
    'andre norton award',
    'andre norton',
    'middle grade and young adult fiction',
    'best middle grade and young adult fiction',
  )


class UrlFetcherNebulaAwardsComics(UrlFetcherNebulaSFADBCategory):
  source_id = 'nebula_awards_comics'
  NAME = 'Nebula Awards - Comics'
  CATEGORY = 'Best Comics'
  CATEGORY_ALIASES = ('best comics', 'comics')
