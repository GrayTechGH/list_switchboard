#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""URL fetcher for the BookBrowse Online Book Club."""

from urllib.parse import urlparse
try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError

try:
  from calibre_plugins.list_switchboard.transport.http import random_user_agent
except ImportError:
  from transport.http import random_user_agent


try:
  from calibre.utils.https import get_https_resource_securely as calibre_https_fetch
except ImportError:
  calibre_https_fetch = None

from .generic import (
  CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,
  CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
  UrlFetcherGeneric,
)


class UrlFetcherBookBrowseOnlineBookClub(UrlFetcherGeneric):

  source_id = 'bookbrowse_online_book_club'
  NAME = 'BookBrowse Online Book Club'
  URL = 'https://www.bookbrowse.com/onlinebookclub/'
  order = 57
  SUPPORTS_INCREMENTAL_UPDATE = True
  FILTER_CATEGORIES = (
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,
  )
  options = {'match_series': False}
  RESPONSE_MAX_BYTES = 10 * 1024 * 1024

  def source_choices(self):
    return ({'label': 'Automatic', 'value': 'automatic'},)

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.bookbrowse import (
        BookBrowseOnlineBookClubParser,
      )
    except ImportError:
      from parser.bookbrowse import BookBrowseOnlineBookClubParser
    return BookBrowseOnlineBookClubParser()

  def fetch_url(self, fetch_url, url):
    try:
      return super().fetch_url(fetch_url, url)
    except (ImportCancelledError,CamoufoxRequiredError):
      raise
    except Exception:
      host = (urlparse(url).hostname or '').casefold()
      if calibre_https_fetch is None or not (
          host == 'bookbrowse.com' or host.endswith('.bookbrowse.com')):
        raise
      # BookBrowse rejects Calibre's mechanize TLS/HTTP fingerprint even with
      # a current browser identity. Calibre's secure HTTPS helper uses a
      # different native transport and succeeds anonymously on the same URLs.
      headers = {
        'User-Agent': random_user_agent(),
        'Accept': 'text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
      }
      try:
        payload = calibre_https_fetch(
          url, cacerts=None, timeout=30, headers=headers)
      except Exception as err:
        redirect_url = getattr(err, 'url', '')
        redirect_host = (urlparse(redirect_url).hostname or '').casefold()
        if not (
            getattr(err, 'code', None) == 403
            and redirect_url and redirect_url != url
            and (redirect_host == 'bookbrowse.com' or redirect_host.endswith('.bookbrowse.com'))):
          raise
        # A migrated brief can redirect to an official /reviews/ URL whose
        # redirect request is rejected while the same final URL succeeds as a
        # fresh Calibre HTTPS request.
        headers['User-Agent'] = random_user_agent()
        payload = calibre_https_fetch(
          redirect_url, cacerts=None, timeout=30, headers=headers)
      if len(payload) > self.RESPONSE_MAX_BYTES:
        raise ValueError('BookBrowse response exceeded the 10 MiB limit.')
      if isinstance(payload, bytes):
        return payload.decode('utf-8', 'replace')
      return str(payload or '')

  def parse(self, html, fetch_url=None, progress=None, cached_parsed=None,
            incremental_update=False, **_kwargs):
    return self.parser().parse(
      html, self.URL, self.NAME, fetch_url=fetch_url, progress=progress,
      cached_parsed=cached_parsed,incremental_update=incremental_update)
