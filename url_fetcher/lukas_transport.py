"""An official-attempt-local policy leaves LibraryThing/Wikipedia unchanged."""

from urllib.parse import urlsplit

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError,CamoufoxRequiredError,CamoufoxSkippedError
  from calibre_plugins.list_switchboard.parser.source_fallback import SourceAttempt
except ImportError:
  from errors import ImportCancelledError,CamoufoxRequiredError,CamoufoxSkippedError
  from parser.source_fallback import SourceAttempt


class LukasOfficialFetchPolicy:

  def __init__(self,fetch_url,legacy_fetch,validate,log=None):
    self.fetch_url,self.legacy_fetch,self.validate,self.log=fetch_url,legacy_fetch,validate,log
    self.owner=getattr(fetch_url,'__self__',None);self.browser_disabled=False

  def fetch(self,url):
    if urlsplit(url).hostname not in ('journalism.columbia.edu','nieman.harvard.edu'):
      return self.legacy_fetch(url)
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
        if self.log is not None:self.log(f'Lukas official browser recovery: {err}; using legacy fetching.')
        reject=getattr(self.owner,'reject_camoufox_payload',None)
        if reject is not None and not isinstance(err,CamoufoxSkippedError):reject(str(err))
    html=self.legacy_fetch(url);self.validate(html,url)
    return html


class LukasOfficialSourceAttempt(SourceAttempt):

  def __init__(self,recipe,*args,**kwargs):
    super().__init__(*args,**kwargs)
    self.recipe=recipe;self._policy=None;self._operation_log=None

  def execute(self,fetch_url,**kwargs):
    self._operation_log=kwargs.get('log')
    try:return super().execute(fetch_url,**kwargs)
    finally:self._policy=None;self._operation_log=None

  def fetch_url(self,fetch_url):
    if fetch_url is None:return None
    if self._policy is None:
      self._policy=LukasOfficialFetchPolicy(fetch_url,
        lambda url:self.recipe.fetch_url(fetch_url,url),
        lambda html,url:self.recipe.parser().read_official_source(html,url,self.recipe.CATEGORY),self._operation_log)
    return self._policy.fetch
