"""Validated browser recovery for official CBCA HTML; PDF bytes stay legacy."""

from urllib.parse import urlsplit

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError, CamoufoxSkippedError
  from calibre_plugins.list_switchboard.parser.cbca_sources import soup_for
  from calibre_plugins.list_switchboard.parser.cbca_updates import annual_html_rows
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError, CamoufoxSkippedError
  from parser.cbca_sources import soup_for
  from parser.cbca_updates import annual_html_rows


class CBCAOfficialFetchPolicy:

  def __init__(self, recipe, callback, log=None):
    self.recipe, self.callback, self.log = recipe, callback, log
    self.browser_disabled = False

  def validate(self, source, url):
    soup = soup_for(source)
    if urlsplit(url).hostname == 'readingtime.cbca.org.au':
      if not any(h.find_parent('article') for h in soup.find_all('h1')):
        raise ValueError('CBCA Reading Time article was not readable.')
    elif url == self.recipe.URL:
      if not self.recipe.parser().pdf_url_from_archive(source, url):
        raise ValueError('CBCA archive did not expose its official history document.')
    elif urlsplit(url).path == '/awards/':
      if not soup.find('h1'):
        raise ValueError('CBCA awards discovery was not readable.')
    else:
      parser = self.recipe.parser()
      annual_html_rows(parser, source, url, parser.year_from_text(url))

  def fetch(self, url, **_kwargs):
    if urlsplit(url).hostname not in ('cbca.org.au', 'www.cbca.org.au', 'readingtime.cbca.org.au') or urlsplit(url).path.lower().endswith('.pdf'):
      return self.recipe.fetch_url(self.callback, url)
    if not self.browser_disabled:
      try:
        try:
          source = self.callback(url, transport='camoufox', timeout=60)
        except TypeError as err:
          if 'transport' not in str(err) and 'keyword' not in str(err):
            raise
          raise CamoufoxSkippedError('Fetch callback does not support Camoufox.') from err
        self.validate(source, url)
        return source
      except (ImportCancelledError, CamoufoxRequiredError):
        raise
      except Exception as err:
        self.browser_disabled = True
        if self.log:
          self.log(f'CBCA official browser recovery: {err}; using legacy fetching.')
        reject = getattr(getattr(self.callback, '__self__', None), 'reject_camoufox_payload', None)
        if reject and not isinstance(err, CamoufoxSkippedError):
          reject(str(err))
    source = self.recipe.fetch_url(self.callback, url)
    self.validate(source, url)
    return source
