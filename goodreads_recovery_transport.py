"""Browser-first transport for existing Goodreads matching recovery only.

Maintenance notes:
- HTML stays request-local. Both transports must pass the same structural gate
  before best-effort extraction; a login heading is not series evidence.
- The owner manages nested browser lifetime and import-wide suppression. This
  policy does not crawl, change matching rules, or affect recipe transports.
"""

import json
import time
from urllib.parse import urlparse

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxSkippedError
except ImportError:
  from errors import ImportCancelledError, CamoufoxSkippedError


def is_goodreads_url(url):
  if not isinstance(url, str):
    return False
  try:
    parsed = urlparse(url)
    host = (parsed.hostname or '').casefold()
  except ValueError:
    return False
  return parsed.scheme in ('http', 'https') and (
    host == 'goodreads.com' or host.endswith('.goodreads.com'))


def validate_recovery_payload(html, url):
  """Recognize book data or source rows, allowing valid books with no series."""
  soup = BeautifulSoup(html or '', 'html.parser')
  title = soup.title.get_text(' ', strip=True).casefold() if soup.title else ''
  heading = soup.find('h1')
  heading_text = heading.get_text(' ', strip=True).casefold() if heading else ''
  if any(marker in title or marker in heading_text for marker in (
      'just a moment', 'access denied', 'verify you are human', 'sign in',
      'sign up', 'login', 'page not found', 'robot check', 'security verification',
      'javascript is disabled')):
    raise ValueError('Goodreads recovery returned a login, error, or challenge page')
  if soup.select_one('form[action*="/user/sign_in"], #challenge-running, #cf-challenge-running'):
    raise ValueError('Goodreads recovery returned a login or challenge form')

  script = soup.find('script', id='__NEXT_DATA__')
  book_data = False
  if script is not None:
    try:
      payload = json.loads(script.string or script.get_text() or '')
    except (TypeError, ValueError) as err:
      raise ValueError('Goodreads recovery returned malformed book data') from err

    def has_book(node):
      if isinstance(node, list):
        return any(has_book(child) for child in node)
      if not isinstance(node, dict):
        return False
      if node.get('__typename') == 'Book' and (node.get('title') or node.get('titleComplete')):
        return True
      return any(has_book(child) for child in node.values() if isinstance(child, (dict, list)))

    book_data = has_book(payload)

  primary_title = soup.select_one('.BookPageTitleSection h1, h1#bookTitle')
  primary_author = soup.select_one('.ContributorLinksList a[href*="/author/show/"], a.authorName[href*="/author/show/"]')
  is_book = '/book/show/' in urlparse(url).path
  if is_book and (book_data or (
      primary_title is not None and primary_title.get_text(' ', strip=True)
      and primary_author is not None and primary_author.get_text(' ', strip=True))):
    return
  book_links = soup.select('a[href*="/book/show/"]')
  usable_links = any(link.get_text(' ', strip=True) or link.select_one('img[alt]') for link in book_links)
  if not is_book and heading_text and usable_links:
    return
  raise ValueError('Goodreads recovery returned empty or unrecognizable content')


class GoodreadsRecoveryFetchPolicy:

  def __init__(self, owner, legacy_fetch):
    self.owner = owner
    self.legacy_fetch = legacy_fetch

  def report(self, message):
    self.owner.debug_camoufox(message)

  def fetch(self, url, role):
    if not is_goodreads_url(url):
      raise ValueError('Goodreads recovery requires a Goodreads URL')
    suppressed = getattr(self.owner, '_camoufox_disabled_reason', '')
    transports = ('legacy',) if suppressed else ('Camoufox', 'legacy')
    if suppressed:
      self.report(f'Goodreads recovery role={role} browser suppressed: {suppressed}')
    for transport in transports:
      started = time.monotonic()
      self.report(f'Goodreads recovery role={role} transport={transport} url={url}')
      try:
        if transport == 'Camoufox':
          try:
            html = self.owner.fetch_url(url, transport='camoufox', timeout=60)
          except TypeError as err:
            if 'transport' not in str(err) and 'keyword' not in str(err):
              raise
            raise CamoufoxSkippedError('Fetch callback does not support Camoufox.') from err
        else:
          html = self.legacy_fetch(url)
        validate_recovery_payload(html, url)
        self.report(f'Goodreads recovery role={role} transport={transport} accepted seconds={time.monotonic() - started:.1f}')
        return html
      except ImportCancelledError:
        self.report(f'Goodreads recovery role={role} transport={transport} cancelled')
        raise
      except Exception as err:
        self.report(f'Goodreads recovery role={role} transport={transport} failed seconds={time.monotonic() - started:.1f}: {err}')
        if transport == 'legacy':
          raise
        if isinstance(err, CamoufoxSkippedError):
          self.owner._camoufox_disabled_reason = str(err)
        else:
          self.owner.reject_camoufox_payload(str(err) or err.__class__.__name__)
        self.report(f'Goodreads recovery role={role} using legacy for remainder of import')
