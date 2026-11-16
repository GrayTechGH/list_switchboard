"""Camoufox then legacy for official SPSFC posts; File 770 stays legacy-only.

Validate each configured page before acceptance. A failed browser attempt
suppresses it for the rest of this import, without changing source precedence.
"""

from urllib.parse import urlparse

try:
  from calibre_plugins.list_switchboard.errors import (
    ImportCancelledError, CamoufoxRequiredError, CamoufoxSkippedError,
  )
  from calibre_plugins.list_switchboard.parser.spsfc import SPSFC_SOURCE_PAGES
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError, CamoufoxSkippedError
  from parser.spsfc import SPSFC_SOURCE_PAGES


class SPSFCFetchPolicy:

  def __init__(self, fetch_url, parser, log=None):
    self.fetch_url = fetch_url
    self.parser = parser
    self.log = log
    self.owner = getattr(fetch_url, '__self__', None)
    self.browser_disabled = False
    self.pages = {page['url'].rstrip('/'): page for page in SPSFC_SOURCE_PAGES}

  def report(self, message):
    if self.log is not None:
      self.log(message)
    log = getattr(self.owner, 'debug_camoufox', None)
    if log is not None:
      log(message)

  def fetch(self, url, **options):
    if url.rstrip('/') not in self.pages:
      raise ValueError('SPSFC requested an unconfigured source page.')
    host = (urlparse(url).hostname or '').casefold()
    official = host == 'spsfc.space' or host.endswith('.spsfc.space')
    if official and not self.browser_disabled:
      try:
        self.report(f'SPSFC transport=Camoufox url={url}')
        html = self.fetch_url(url, transport='camoufox', **options)
        self.validate(html, url)
        return html
      except (ImportCancelledError, CamoufoxRequiredError):
        raise
      except Exception as err:
        self.browser_disabled = True
        self.report(f'SPSFC Camoufox unavailable/rejected: {err}; using legacy')
        reject = getattr(self.owner, 'reject_camoufox_payload', None)
        if reject is not None and not isinstance(err, CamoufoxSkippedError):
          reject(str(err) or err.__class__.__name__)
    self.report(f'SPSFC transport=legacy url={url}')
    html = self.fetch_url(url, **options)
    self.validate(html, url)
    return html

  def validate(self, html, url):
    page = self.pages.get(url.rstrip('/'))
    if page is None:
      raise ValueError('SPSFC requested an unconfigured source page.')
    if not self.parser.parse_source_page(html, page):
      raise ValueError(f'SPSFC source did not contain usable award entries: {url}')
