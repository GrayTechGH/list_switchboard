#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,
  CATEGORY_NONFICTION,
  UrlFetcherGeneric,
)
try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError


class UrlFetcherLibraryReads(UrlFetcherGeneric):

  source_id = 'library_reads'
  NAME = 'LibraryReads'
  URL = 'https://libraryreads.org/archive'
  order = 48
  SUPPORTS_INCREMENTAL_UPDATE = True
  FILTER_CATEGORIES = (CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,)
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.library_reads import LibraryReadsParser
    except ImportError:
      from parser.library_reads import LibraryReadsParser
    return LibraryReadsParser()

  def parse(self, html, fetch_url=None, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME, fetch_url=fetch_url)

  def fetch_and_parse(self, fetch_url, *args, **kwargs):
    cache = kwargs.get('cached_parsed')
    state = cache.get('incremental_state') if isinstance(cache,dict) else {}
    parser = self.parser()
    try:
      from calibre_plugins.list_switchboard.parser.library_reads import SHEET_CSV_URL
    except ImportError:
      from parser.library_reads import SHEET_CSV_URL
    discovery = state.get('discovery') if isinstance(state,dict) else {}
    discovery = discovery if isinstance(discovery,dict) else {}
    eligible = (not args and kwargs.get('incremental_update') and
      isinstance(state,dict) and state.get('version')==1 and
      state.get('strategy')=='libraryreads-endpoint-v1' and
      state.get('source_key')==[self.URL,parser.DEFAULT_SCOPE] and
      discovery.get('endpoint_verified') is True and discovery.get('endpoint')==SHEET_CSV_URL and
      kwargs.get('source_choice') in (None,'automatic',0,'0') and
      not kwargs.get('force_fallback_level'))
    if eligible:
      try:
        before_fetch,after_fetch,before_parse=(kwargs.get(k) for k in
          ('before_fetch','after_fetch','before_parse'))
        if before_fetch:
          before_fetch(SHEET_CSV_URL)
        payload = self.fetch_url(fetch_url,SHEET_CSV_URL)
        if after_fetch:
          after_fetch(SHEET_CSV_URL,payload)
        if before_parse:
          before_parse(SHEET_CSV_URL)
        if not parser.looks_like_csv(payload):
          raise ValueError('The remembered LibraryReads endpoint no longer returned CSV.')
        parsed = parser.parse(payload,self.URL,self.NAME)
        if not parsed.get('entries'):
          raise ValueError('The remembered LibraryReads endpoint produced no entries.')
        parsed['incremental_update'] = True
        if kwargs.get('progress'):
          kwargs['progress'](1,1,'Refreshed LibraryReads archive data')
        return parsed
      except (ImportCancelledError,CamoufoxRequiredError):
        raise
      except Exception as err:
        if kwargs.get('log'):
          kwargs['log'](f'LibraryReads endpoint rediscovery required: {err}')
    parsed = super().fetch_and_parse(fetch_url,*args,**kwargs)
    if kwargs.get('incremental_update') and isinstance(cache,dict) and cache.get('entries') and not parsed.get('entries'):
      raise ValueError('LibraryReads did not expose usable selections; saved history was not replaced.')
    return parsed


class UrlFetcherLibraryReadsBonusPicks(UrlFetcherLibraryReads):

  source_id = 'library_reads_bonus_picks'
  NAME = 'LibraryReads - Bonus Picks'
  order = 49
  SUPPORTS_INCREMENTAL_UPDATE = True

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.library_reads import (
        LibraryReadsBonusPicksParser,
      )
    except ImportError:
      from parser.library_reads import LibraryReadsBonusPicksParser
    return LibraryReadsBonusPicksParser()


class UrlFetcherLibraryReadsNotableNonfiction(UrlFetcherLibraryReads):

  source_id = 'library_reads_notable_nonfiction'
  NAME = 'LibraryReads - Notable Nonfiction'
  order = 50
  SUPPORTS_INCREMENTAL_UPDATE = True
  FILTER_CATEGORIES = (CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS, CATEGORY_NONFICTION)

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.library_reads import (
        LibraryReadsNotableNonfictionParser,
      )
    except ImportError:
      from parser.library_reads import LibraryReadsNotableNonfictionParser
    return LibraryReadsNotableNonfictionParser()
