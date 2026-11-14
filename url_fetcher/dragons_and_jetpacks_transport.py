"""Per-request browser recovery for Dragons & Jetpacks shelf pages only.

Invariants:
- Structural/identity checks are page-local; accepted record sets detect stale
  pagination across requests without rejecting ordinary boundary overlap.
- One failed browser attempt suppresses it for the rest of this operation.
- Legacy retries remain owned by the recipe's existing Goodreads policy.
"""

import time

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxSkippedError
except ImportError:
  from errors import ImportCancelledError, CamoufoxSkippedError


class DragonsJetpacksFetchPolicy:

  def __init__(self, fetch_url, legacy_fetch, parser, log=None):
    self.fetch_url = fetch_url
    self.legacy_fetch = legacy_fetch
    self.parser = parser
    self.log = log
    self.owner = getattr(fetch_url, '__self__', None)
    self.browser_disabled = False
    self.page_records = {}

  def report(self, message):
    if self.log is not None:
      self.log(message)
    browser_log = getattr(self.owner, 'debug_camoufox', None)
    if browser_log is not None:
      browser_log(message)

  def fetch(self, url):
    self.parser.validated_page_url(url)
    role = 'shelf'
    if not self.browser_disabled:
      started = time.monotonic()
      self.report(f'Dragons & Jetpacks role={role} transport=Camoufox url={url}')
      try:
        try:
          html = self.fetch_url(url, transport='camoufox', timeout=60)
        except TypeError as err:
          if 'transport' not in str(err) and 'keyword' not in str(err):
            raise
          raise CamoufoxSkippedError('Fetch callback does not support Camoufox.') from err
        self.validate(html, url)
        self.report(
          f'Dragons & Jetpacks role={role} transport=Camoufox accepted '
          f'seconds={time.monotonic() - started:.1f}')
        return html
      except ImportCancelledError:
        raise
      except Exception as err:
        self.browser_disabled = True
        self.report(
          f'Dragons & Jetpacks role={role} transport=Camoufox '
          f'{"skipped" if isinstance(err, CamoufoxSkippedError) else "failed"} '
          f'seconds={time.monotonic() - started:.1f}: {err}; using legacy for remainder of import')
        reject = getattr(self.owner, 'reject_camoufox_payload', None)
        if reject is not None and not isinstance(err, CamoufoxSkippedError):
          reject(str(err) or err.__class__.__name__)
    started = time.monotonic()
    self.report(f'Dragons & Jetpacks role={role} transport=legacy url={url}')
    try:
      html = self.legacy_fetch(url)
      self.validate(html, url)
    except ImportCancelledError:
      raise
    except Exception as err:
      self.report(
        f'Dragons & Jetpacks role={role} transport=legacy failed '
        f'seconds={time.monotonic() - started:.1f}: {err}')
      raise
    self.report(
      f'Dragons & Jetpacks role={role} transport=legacy accepted '
      f'seconds={time.monotonic() - started:.1f}')
    return html

  def validate(self, html, url):
    _, table, _ = self.parser.require_real_shelf_page(html, url)
    records = frozenset(row['id'] for row in table.select('tr[id^="groupBook"]'))
    page = self.parser.page_key(url)
    if any(key != page and value == records for key, value in self.page_records.items()):
      raise ValueError('Dragons & Jetpacks returned repeated shelf contents for another page.')
    self.page_records[page] = records
