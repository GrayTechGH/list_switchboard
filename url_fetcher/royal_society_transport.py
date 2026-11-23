"""Optional validated browser recovery for adult Science Book Prize pages."""

from urllib.parse import urlsplit

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError,CamoufoxRequiredError,CamoufoxSkippedError
except ImportError:
  from errors import ImportCancelledError,CamoufoxRequiredError,CamoufoxSkippedError


class RoyalSocietyFetchPolicy:

  def __init__(self,fetch_url,legacy_fetch,parser,log=None):
    self.fetch_url,self.legacy_fetch,self.parser,self.log=fetch_url,legacy_fetch,parser,log
    self.owner=getattr(fetch_url,'__self__',None)
    self.browser_disabled=False

  def fetch(self,url):
    target=urlsplit(url)
    if (target.hostname not in ('royalsociety.org','www.royalsociety.org') or
        not target.path.startswith('/medals-and-prizes/science-book-prize/')):
      return self.legacy_fetch(url)
    if not self.browser_disabled:
      try:
        try:html=self.fetch_url(url,transport='camoufox',timeout=60)
        except TypeError as err:
          if 'transport' not in str(err) and 'keyword' not in str(err):raise
          raise CamoufoxSkippedError('Fetch callback does not support Camoufox.') from err
        self.parser.validate_fetch_payload(html,url)
        return html
      except (ImportCancelledError,CamoufoxRequiredError):raise
      except Exception as err:
        self.browser_disabled=True
        if self.log is not None:self.log(f'Royal Society browser recovery: {err}; using legacy fetching.')
        reject=getattr(self.owner,'reject_camoufox_payload',None)
        if reject is not None and not isinstance(err,CamoufoxSkippedError):reject(str(err))
    html=self.legacy_fetch(url)
    self.parser.validate_fetch_payload(html,url)
    return html
