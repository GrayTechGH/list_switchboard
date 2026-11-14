"""Per-request browser recovery for Goodreads Choice Awards imports only.

Invariants:
- Validation is page-local; recovery never restarts a multi-page import.
- One failed browser attempt suppresses it for the rest of this operation.
- Legacy retries remain owned by the recipe's existing Goodreads policy.
"""

import time
from urllib.parse import urlparse

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxSkippedError
except ImportError:
  from errors import ImportCancelledError, CamoufoxSkippedError


class GoodreadsChoiceFetchPolicy:

  def __init__(self, fetch_url, legacy_fetch, parser, log=None):
    self.fetch_url = fetch_url
    self.legacy_fetch = legacy_fetch
    self.parser = parser
    self.log = log
    self.owner = getattr(fetch_url, '__self__', None)
    self.browser_disabled = False

  def report(self, message):
    if self.log is not None:
      self.log(message)
    browser_log = getattr(self.owner, 'debug_camoufox', None)
    if browser_log is not None:
      browser_log(message)

  def fetch(self, url):
    host = (urlparse(url).hostname or '').casefold()
    if host != 'goodreads.com' and not host.endswith('.goodreads.com'):
      return self.legacy_fetch(url)
    role = self.parser.fetch_page_role(url)
    if not self.browser_disabled:
      started = time.monotonic()
      self.report(f'Goodreads Choice role={role} transport=Camoufox url={url}')
      try:
        try:
          html = self.fetch_url(url, transport='camoufox', timeout=60)
        except TypeError as err:
          if 'transport' not in str(err) and 'keyword' not in str(err):
            raise
          raise CamoufoxSkippedError('Fetch callback does not support Camoufox.') from err
        self.parser.validate_fetch_payload(html, url)
        self.report(
          f'Goodreads Choice role={role} transport=Camoufox accepted '
          f'seconds={time.monotonic() - started:.1f}')
        return html
      except ImportCancelledError:
        raise
      except Exception as err:
        self.browser_disabled = True
        self.report(
          f'Goodreads Choice role={role} transport=Camoufox '
          f'{"skipped" if isinstance(err, CamoufoxSkippedError) else "failed"} '
          f'seconds={time.monotonic() - started:.1f}: {err}; using legacy for remainder of import')
        reject = getattr(self.owner, 'reject_camoufox_payload', None)
        if reject is not None and not isinstance(err, CamoufoxSkippedError):
          reject(str(err) or err.__class__.__name__)
    started = time.monotonic()
    self.report(f'Goodreads Choice role={role} transport=legacy url={url}')
    try:
      html = self.legacy_fetch(url)
      self.parser.validate_fetch_payload(html, url)
    except ImportCancelledError:
      raise
    except Exception as err:
      self.report(
        f'Goodreads Choice role={role} transport=legacy failed '
        f'seconds={time.monotonic() - started:.1f}: {err}')
      raise
    self.report(
      f'Goodreads Choice role={role} transport=legacy accepted '
      f'seconds={time.monotonic() - started:.1f}')
    return html
