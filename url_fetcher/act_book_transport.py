"""Optional validated browser recovery for Libraries ACT source pages only."""

from urllib.parse import urlsplit

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError, CamoufoxSkippedError
  from calibre_plugins.list_switchboard.parser.act_book_sources import validate_source
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError, CamoufoxSkippedError
  from parser.act_book_sources import validate_source


class ACTOfficialFetchPolicy:

  def __init__(self, callback, legacy, log=None):
    self.callback, self.legacy, self.log = callback, legacy, log
    self.browser_disabled = False

  def fetch(self, url):
    if urlsplit(url).hostname not in ('www.library.act.gov.au', 'library.act.gov.au'):
      return self.legacy(url)
    if not self.browser_disabled:
      try:
        try:
          html = self.callback(url, transport='camoufox', timeout=60)
        except TypeError as err:
          if 'transport' not in str(err) and 'keyword' not in str(err):
            raise
          raise CamoufoxSkippedError('Fetch callback does not support Camoufox.') from err
        validate_source(html, url)
        return html
      except (ImportCancelledError, CamoufoxRequiredError):
        raise
      except Exception as err:
        self.browser_disabled = True
        if self.log:
          self.log(f'Libraries ACT browser recovery: {err}; using legacy fetching.')
        reject = getattr(getattr(self.callback, '__self__', None), 'reject_camoufox_payload', None)
        if reject and not isinstance(err, CamoufoxSkippedError):
          reject(str(err))
    html = self.legacy(url)
    validate_source(html, url)
    return html
