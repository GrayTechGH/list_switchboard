"""Validate official PEN article identity before accepting either transport."""

from urllib.parse import urlsplit

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError,CamoufoxRequiredError,CamoufoxSkippedError
except ImportError:
  from errors import ImportCancelledError,CamoufoxRequiredError,CamoufoxSkippedError


class PENAmericaFetchPolicy:

  def __init__(self,fetch_url,legacy_fetch,validate,log=None):
    self.fetch_url,self.legacy_fetch,self.validate,self.log=fetch_url,legacy_fetch,validate,log
    self.owner=getattr(fetch_url,'__self__',None);self.browser_disabled=False

  def fetch(self,url):
    if urlsplit(url).hostname not in ('pen.org','www.pen.org'):return self.legacy_fetch(url)
    if not self.browser_disabled:
      try:
        try:html=self.fetch_url(url,transport='camoufox',timeout=60)
        except TypeError as err:
          if 'transport' not in str(err) and 'keyword' not in str(err):raise
          raise CamoufoxSkippedError('Fetch callback does not support Camoufox.') from err
        self.validate(html,url)
        return html
      except (ImportCancelledError,CamoufoxRequiredError):raise
      except Exception as err:
        self.browser_disabled=True
        if self.log is not None:self.log(f'PEN America browser recovery: {err}; using legacy fetching.')
        reject=getattr(self.owner,'reject_camoufox_payload',None)
        if reject is not None and not isinstance(err,CamoufoxSkippedError):reject(str(err))
    html=self.legacy_fetch(url);self.validate(html,url)
    return html
