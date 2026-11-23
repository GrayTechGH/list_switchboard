"""Opt-in ISFDB award-year reuse; category pages remain complete refreshes.

Maintenance notes:
- Reuse only settled historical category ballots after fresh overview discovery.
  Empty categories require a recognizable year page; failed/malformed snapshots
  retain old rows pending. Parsed rows and notes are the only cached source data.
"""

import datetime
import json
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError
  from calibre_plugins.list_switchboard.parser.incremental import ParsedUnitCache
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError
  from .incremental import ParsedUnitCache
  from .generic import position_sort_key


def parse_year_pages(parser, html, base_url, name, category, aliases,
    fetch_url=None, log=None, progress=None, cached_parsed=None, incremental_update=False):
  soup = BeautifulSoup(html, 'html.parser')
  links = []
  for node in soup.find_all('a', href=True):
    url = urljoin(base_url, node['href'])
    target = urlsplit(url)
    match = re.fullmatch(r'(\d+)\+((?:19|20)\d{2})', target.query)
    if (target.netloc != urlsplit(base_url).netloc or
        target.path != '/cgi-bin/ay.cgi' or match is None):
      continue
    if url not in links:
      links.append(url)
  if not links:
    raise ValueError('ISFDB overview did not expose award year links.')
  cache = ParsedUnitCache('isfdb-award-years-v1', json.dumps([
    base_url, name, category, aliases, type(parser).__name__, parser.AWARD_NAME,
    parser.CAPTURE_ORIGINAL_WORK], sort_keys=True), cached_parsed, incremental_update)
  latest = max(int(url.rsplit('+', 1)[-1]) for url in links)
  entries, notes = [], []
  for index, url in enumerate(links, 1):
    year = int(url.rsplit('+', 1)[-1])
    old = cache.old_units.get(url) or {}
    if progress is not None:
      progress(index - 1, len(links), f'Fetching ISFDB {category}: {year} ({index} of {len(links)} years)...')
    reused = None
    if (year < min(latest, datetime.datetime.now().year) and
        (old.get('metadata') or {}).get('settled') is True):
      reused = cache.reuse(url, revision=year)
    if reused is not None:
      entries.extend(reused)
      notes.extend((old.get('metadata') or {}).get('notes') or [])
    else:
      try:
        page = fetch_url(url)
        parsed = parser.parse(page, url, name, category, aliases)
        rows = parsed.get('entries') or []
        page_soup = BeautifulSoup(page, 'html.parser')
        title = page_soup.title.get_text(' ', strip=True) if page_soup.title else ''
        titled_year = re.search(r'\b((?:19|20)\d{2})\b', title)
        recognized_empty = bool(titled_year and int(titled_year.group(1)) == year and
          page_soup.find('table') and page_soup.find('a', href=re.compile(r'award_category\.cgi\?\d+')))
        if ((titled_year and int(titled_year.group(1)) != year) or
            any(str(row.get('award_year')) != str(year) for row in rows) or
            (not rows and not recognized_empty)):
          raise ValueError('ISFDB page did not expose a recognizable matching award year.')
        unit_notes = parsed.get('notes') or []
        cache.put(url, rows, revision=year, metadata={
          'settled': not rows or any(row.get('result') == 'winner' for row in rows),
          'notes': unit_notes})
        entries.extend(rows)
        notes.extend(unit_notes)
      except (ImportCancelledError, CamoufoxRequiredError):
        raise
      except Exception as err:
        entries.extend(cache.failed(url, revision=year))
        notes.extend((old.get('metadata') or {}).get('notes') or [])
        notes.append(f'{parser.AWARD_NAME} ISFDB year {url} could not be fetched or parsed: {err}')
        if log is not None:
          log(notes[-1])
    if progress is not None:
      progress(index, len(links), f'Processed ISFDB year {year} ({index} of {len(links)}).')
  entries.sort(key=lambda entry: position_sort_key(entry.get('position', '')))
  return {'name': name, 'entries': entries, 'notes': notes,
    'incremental_state': cache.state(entries)}
