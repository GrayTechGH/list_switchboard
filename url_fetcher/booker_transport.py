"""Optional browser/validated legacy recovery limited to official Booker pages."""

from urllib.parse import urlsplit

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError, CamoufoxSkippedError
  from calibre_plugins.list_switchboard.parser.source_fallback import SourceAttempt
  from calibre_plugins.list_switchboard.parser.booker_modern import INDEX_PATH, index_links, page_identity
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError, CamoufoxSkippedError
  from parser.source_fallback import SourceAttempt
  from parser.booker_modern import INDEX_PATH, index_links, page_identity


class BookerOfficialSourceAttempt(SourceAttempt):

  def __init__(self, recipe, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.recipe = recipe
    self._browser_disabled = False
    self._operation_log = None

  def execute(self, fetch_url, **kwargs):
    self._operation_log = kwargs.get('log')
    self._browser_disabled = False
    try:
      return super().execute(fetch_url, **kwargs)
    finally:
      self._operation_log = None
      self._browser_disabled = False

  def validate(self, html, url):
    path = urlsplit(url).path.rstrip('/')
    if path == INDEX_PATH:
      index_links(html, url, self.recipe.YEAR_URL_PATTERN)
    elif path.startswith(INDEX_PATH + '/'):
      page_identity(html, url)
    else:
      title, author = self.recipe.parser().title_author_from_detail(html)
      if not title or not author:
        raise ValueError('Official Booker book detail had no title/author metadata.')

  def fetch_url(self, fetch_url):
    if fetch_url is None:
      return None

    def fetch(url):
      if urlsplit(url).hostname != 'thebookerprizes.com':
        return self.recipe.fetch_url(fetch_url, url)
      if not self._browser_disabled:
        try:
          try:
            html = fetch_url(url, transport='camoufox', timeout=60)
          except TypeError as err:
            if 'transport' not in str(err) and 'keyword' not in str(err):
              raise
            raise CamoufoxSkippedError('Fetch callback does not support Camoufox.') from err
          self.validate(html, url)
          return html
        except (ImportCancelledError, CamoufoxRequiredError):
          raise
        except Exception as err:
          self._browser_disabled = True
          if self._operation_log:
            self._operation_log(f'Booker official browser recovery: {err}; using legacy fetching.')
          owner = getattr(fetch_url, '__self__', None)
          reject = getattr(owner, 'reject_camoufox_payload', None)
          if reject and not isinstance(err, CamoufoxSkippedError):
            reject(str(err))
      html = self.recipe.fetch_url(fetch_url, url)
      self.validate(html, url)
      return html

    return fetch
