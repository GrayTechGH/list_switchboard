"""Browser-first request policy for SFADB award pages.

Parsers retain source/category interpretation. Transport validation recognizes
award overview/year structure and rejects challenge pages or a stale year.
"""

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.errors import (
    ImportCancelledError, CamoufoxRequiredError, CamoufoxSkippedError,
  )
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError, CamoufoxSkippedError


def is_sfadb_url(url):
  host = (urlparse(url).hostname or '').casefold()
  return host == 'sfadb.com' or host.endswith('.sfadb.com')


def validate_sfadb_page(html, url):
  soup = BeautifulSoup(html, 'html.parser')
  title = soup.title.get_text(' ', strip=True) if soup.title else ''
  if not re.match(r'^sfadb\s*:', title, re.I):
    raise ValueError('SFADB returned an unrecognized page instead of award data.')
  path = urlparse(url).path.rstrip('/')
  # Citation polls are ranked pages, and their titles may omit the poll year.
  if re.fullmatch(r'/Locus_(?:19|20)\d{2}(?:_[A-Za-z0-9]+)?', path):
    if 'locus' in title.casefold() and any(
        item.find('b') is not None and item.find('a', href=True) is not None
        for item in soup.select('ol li')):
      return
    raise ValueError('SFADB did not return a ranked Locus citation page.')
  expected_year = re.search(r'_((?:19|20)\d{2})$', path)
  if expected_year:
    actual_year = re.search(r'\b((?:19|20)\d{2})\b', title)
    if not actual_year or actual_year.group(1) != expected_year.group(1):
      raise ValueError('SFADB returned a page for a different award year.')
  if soup.select_one('div.categoryblock, div.nomineeblock') is not None:
    return
  for link in soup.find_all('a', href=True):
    href = urljoin(url, link['href'])
    if (
        is_sfadb_url(href)
        and re.fullmatch(r'(?:19|20)\d{2}', link.get_text(' ', strip=True))
        and re.search(r'_((?:19|20)\d{2})$', urlparse(href).path.rstrip('/'))):
      return
  raise ValueError('SFADB page did not contain award sections or year links.')


def fetch_sfadb_url(owner, url, user_agent=None, max_bytes=None, timeout=None):
  try:
    html = owner.fetch_camoufox_url(url, max_bytes=max_bytes, timeout=timeout)
    try:
      validate_sfadb_page(html, url)
    except Exception as err:
      owner.reject_camoufox_payload(str(err))
      raise
    return html
  except (ImportCancelledError, CamoufoxRequiredError):
    raise
  except Exception as err:
    owner.debug_camoufox(f'SFADB browser unavailable/rejected; using legacy: {err}')
    if not isinstance(err, CamoufoxSkippedError) and not getattr(owner, '_camoufox_disabled_reason', ''):
      owner.reject_camoufox_payload(str(err) or err.__class__.__name__)
  html = owner.fetch_legacy_url(
    url, user_agent=user_agent, max_bytes=max_bytes, timeout=timeout)
  validate_sfadb_page(html, url)
  return html
