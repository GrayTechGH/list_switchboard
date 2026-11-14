#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Fetchers for Big Library Read and the successor Libby Reads Global."""

from urllib.parse import urlparse

try:
  from calibre.utils.https import get_https_resource_securely as calibre_https_fetch
except ImportError:
  calibre_https_fetch = None

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
  USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/150.0.0.0 Safari/537.36'
  )
  RESPONSE_MAX_BYTES = 10 * 1024 * 1024
  order = 56
  FILTER_CATEGORIES = (CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,)
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.big_library_read import LibbyReadsGlobalParser
    except ImportError:
      from parser.big_library_read import LibbyReadsGlobalParser
    return LibbyReadsGlobalParser()

  def fetch_url(self, fetch_url, url):
    try:
      return super().fetch_url(fetch_url, url)
    except Exception:
      host = (urlparse(url).hostname or '').casefold()
      if calibre_https_fetch is None or not (
          host == 'libbylife.com' or host.endswith('.libbylife.com')):
        raise
      # Libby Life returns HTTP 403 to Calibre's mechanize transport even with
      # a current browser identity. Calibre's native secure HTTPS helper uses a
      # different TLS/HTTP fingerprint and succeeds anonymously.
      headers = {
        'User-Agent': self.USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
      }
      payload = calibre_https_fetch(
        url, cacerts=None, timeout=30, headers=headers)
      if len(payload) > self.RESPONSE_MAX_BYTES:
        raise ValueError('Libby Reads response exceeded the 10 MiB limit.')
      if isinstance(payload, bytes):
        return payload.decode('utf-8', 'replace')
      return str(payload or '')

  def parse(self, html, fetch_url=None, **_kwargs):
    return self.parser().parse(
      html, self.URL, self.NAME, fetch_url=fetch_url)
