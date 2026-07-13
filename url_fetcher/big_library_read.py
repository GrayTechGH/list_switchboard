#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Fetchers for Big Library Read and the successor Libby Reads Global."""

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError
except ImportError:
  from errors import ImportCancelledError

from .generic import CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS, UrlFetcherGeneric


class PackagedHistoryFallbackMixin:
  """Use one complete packaged result after any remote-source failure."""

  def source_choices(self):
    return ({'label': 'Automatic', 'value': 'automatic'},)

  def fetch_and_parse(self, *args, **kwargs):
    try:
      return super().fetch_and_parse(*args, **kwargs)
    except ImportCancelledError:
      raise
    except Exception as err:
      recover_remote = getattr(self, 'recover_remote', None)
      if callable(recover_remote):
        try:
          return recover_remote(args, kwargs, err)
        except ImportCancelledError:
          raise
        except Exception as recovery_err:
          err = recovery_err
      return self.parser().parse_ledger(str(err))


class UrlFetcherBigLibraryRead(PackagedHistoryFallbackMixin, UrlFetcherGeneric):

  source_id = 'big_library_read'
  NAME = 'Big Library Read (discontinued)'
  URL = 'https://www.biglibraryread.com/past-titles/'
  order = 55
  FILTER_CATEGORIES = (CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,)
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.big_library_read import BigLibraryReadParser
    except ImportError:
      from parser.big_library_read import BigLibraryReadParser
    return BigLibraryReadParser()

  def parse(self, html, fetch_url=None, **_kwargs):
    return self.parser().parse(
      html, self.URL, self.NAME, fetch_url=fetch_url)

  def recover_remote(self, args, kwargs, initial_error):
    if 'Internet Archive union failed' in str(initial_error):
      raise initial_error
    fetch_url = args[0] if args else kwargs.get('fetch_url')
    if fetch_url is None:
      raise initial_error
    fetcher_fetch_url = lambda target_url: self.fetch_url(fetch_url, target_url)
    unavailable_html = '<html><h1>Live archive request unavailable</h1></html>'
    return self.parser().parse(
      unavailable_html, self.URL, self.NAME, fetch_url=fetcher_fetch_url)


class UrlFetcherLibbyReadsGlobal(PackagedHistoryFallbackMixin, UrlFetcherGeneric):

  source_id = 'libby_reads_global'
  NAME = 'Libby Reads Global'
  URL = 'https://www.libbylife.com/libby-reads'
  order = 56
  FILTER_CATEGORIES = (CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,)
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.big_library_read import LibbyReadsGlobalParser
    except ImportError:
      from parser.big_library_read import LibbyReadsGlobalParser
    return LibbyReadsGlobalParser()

  def parse(self, html, fetch_url=None, **_kwargs):
    return self.parser().parse(
      html, self.URL, self.NAME, fetch_url=fetch_url)
