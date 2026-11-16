"""Camoufox then random-agent legacy fetching inside the ISFDB source rank.

The wrapper covers root and linked category/year pages. Rendered pages must
pass the source validator before acceptance; cancellation never retries.
"""

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError
  from calibre_plugins.list_switchboard.parser.source_fallback import SourceAttempt
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError
  from parser.source_fallback import SourceAttempt


class ISFDBSourceAttempt(SourceAttempt):

  def __init__(self, *args, page_validator=None, **kwargs):
    super().__init__(*args, **kwargs)
    self.page_validator = page_validator

  def fetch_url(self, fetch_url):
    fetch = super().fetch_url(fetch_url)
    if fetch is None:
      return None
    owner = getattr(fetch_url, '__self__', None)

    def wrapped(url):
      try:
        payload = fetch_url(url, transport='camoufox')
        try:
          if self.page_validator is not None and not self.page_validator(payload, url):
            raise ValueError('ISFDB browser page did not contain usable award records.')
        except (ImportCancelledError, CamoufoxRequiredError):
          raise
        except Exception as err:
          reject = getattr(owner, 'reject_camoufox_payload', None)
          if reject is not None:
            reject(str(err) or err.__class__.__name__)
          raise
        return payload
      except (ImportCancelledError, CamoufoxRequiredError):
        raise
      except Exception as err:
        log = getattr(owner, 'debug_camoufox', None)
        if log is not None:
          log(f'ISFDB Camoufox failed; using legacy transport: {err}')
      return fetch(url)

    return wrapped
