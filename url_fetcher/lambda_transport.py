"""Validate official Lambda documents before browser/same-URL legacy recovery."""

from urllib.parse import urlsplit

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError, CamoufoxSkippedError
  from calibre_plugins.list_switchboard.parser.lambda_updates import directory_source, current_source
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError, CamoufoxSkippedError
  from parser.lambda_updates import directory_source, current_source


class LambdaOfficialFetchPolicy:

  def __init__(self, recipe, callback, log=None):
    self.recipe, self.callback, self.log = recipe, callback, log
    self.browser_disabled = False

  def validate(self, html, url):
    parser = self.recipe.parser()
    if url == self.recipe.URL:
      directory_source(parser, html, url)
    else:
      current_source(parser, html, url, 'winners' if 'winners' in urlsplit(url).path else 'finalists')

  def fetch(self, url):
    if urlsplit(url).hostname not in ('lambdaliterary.org', 'www.lambdaliterary.org'):
      return self.recipe.fetch_url(self.callback, url)
    if not self.browser_disabled:
      try:
        try:
          html = self.callback(url, transport='camoufox', timeout=60)
        except TypeError as err:
          if 'transport' not in str(err) and 'keyword' not in str(err):
            raise
          raise CamoufoxSkippedError('Fetch callback does not support Camoufox.') from err
        self.validate(html, url)
        return html
      except (ImportCancelledError, CamoufoxRequiredError):
        raise
      except Exception as err:
        self.browser_disabled = True
        if self.log:
          self.log(f'Lambda official browser recovery: {err}; using legacy fetching.')
        reject = getattr(getattr(self.callback, '__self__', None), 'reject_camoufox_payload', None)
        if reject and not isinstance(err, CamoufoxSkippedError):
          reject(str(err))
    html = self.recipe.fetch_url(self.callback, url)
    self.validate(html, url)
    return html
