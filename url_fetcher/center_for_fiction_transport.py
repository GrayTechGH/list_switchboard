"""Keep official browser recovery inside the Center for Fiction attempt."""

from urllib.parse import urlsplit

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError, CamoufoxSkippedError
  from calibre_plugins.list_switchboard.parser.source_fallback import SourceAttempt
  from calibre_plugins.list_switchboard.parser.center_for_fiction_sources import source_root
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError, CamoufoxSkippedError
  from parser.source_fallback import SourceAttempt
  from parser.center_for_fiction_sources import source_root


class CenterForFictionOfficialAttempt(SourceAttempt):

  def __init__(self, recipe, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.recipe, self._browser_disabled, self._log = recipe, False, None

  def execute(self, fetch_url, **kwargs):
    self._browser_disabled, self._log = False, kwargs.get('log')
    try:
      return super().execute(fetch_url, **kwargs)
    finally:
      self._browser_disabled, self._log = False, None

  def fetch_url(self, callback):
    if callback is None:
      return None

    def fetch(url):
      if urlsplit(url).hostname not in ('centerforfiction.org', 'www.centerforfiction.org'):
        return self.recipe.fetch_url(callback, url)
      if not self._browser_disabled:
        try:
          try:
            html = callback(url, transport='camoufox', timeout=60)
          except TypeError as err:
            if 'transport' not in str(err) and 'keyword' not in str(err):
              raise
            raise CamoufoxSkippedError('Fetch callback does not support Camoufox.') from err
          source_root(html, url)
          return html
        except (ImportCancelledError, CamoufoxRequiredError):
          raise
        except Exception as err:
          self._browser_disabled = True
          if self._log:
            self._log(f'Center for Fiction browser recovery: {err}; using legacy fetching.')
          reject = getattr(getattr(callback, '__self__', None), 'reject_camoufox_payload', None)
          if reject and not isinstance(err, CamoufoxSkippedError):
            reject(str(err))
      html = self.recipe.fetch_url(callback, url)
      source_root(html, url)
      return html

    return fetch
