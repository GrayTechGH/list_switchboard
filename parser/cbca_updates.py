"""Refresh CBCA discovery and reuse complete historical parsed source units.

A year owns its shortlist and results together. Fresh archive outcomes have
precedence, while original source projections preserve bylines/results across
later corrections and failed refreshes. Only parsed entries enter the cache.
"""

from copy import deepcopy
from datetime import date
import hashlib
import json
from urllib.parse import urlsplit

from .award_base import normalize_heading
from .cbca_book_of_the_year import AWARDS_URL, PDF_URL, CATEGORY_MIDDLE_READERS, shortlist_url, winners_url
from .cbca_sources import soup_for
from .cbca_2022 import SHORTLIST_URL, shortlist_rows
from .incremental import ParsedUnitCache, project_source_rows, restore_source_rows

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError


ANNUAL_PDFS = {
  2022: ('https://cbca.blob.core.windows.net/documents/BookOfTheYear/2022/2022%20CBCA%20Winners_full.pdf',),
  2023: ('https://cbca.blob.core.windows.net/documents/BookOfTheYear/2023/2023_CBCA_Shortlist_List.pdf',
    'https://cbca.blob.core.windows.net/documents/BookOfTheYear/2023/2023_CBCA-WinnersList.pdf'),
}
HISTORY_START = {'Older Readers': 1946, 'Younger Readers': 1982, 'Early Childhood': 2001,
  'Picture Book': 1955, 'Eve Pownall': 1988, 'New Illustrator': 1988,
  CATEGORY_MIDDLE_READERS: 2027}
NO_WINNER = {'Older Readers': {1947, 1949, 1975},
  'Picture Book': {1952, 1953, 1954, 1955, 1957, 1959, 1960, 1961, 1962, 1963, 1964, 1966, 1967, 1968, 1970, 1972, 1973, 1977, 1981, 1985},
  'Eve Pownall': {1989, 1990, 1991, 1992}, 'New Illustrator': {1999}}


def identity(row):
  return (str(row.get('award_year')), normalize_heading(row.get('category', '')), normalize_heading(row.get('title', '')))


def signature(value):
  return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def history_complete(parser, rows):
  start = HISTORY_START.get(parser.category)
  if not start or not rows:
    return False
  years = [int(r['award_year']) for r in rows]
  winners = {int(r['award_year']) for r in rows if r.get('result') == 'winner'}
  expected = set(range(start, max(years) + 1)) - NO_WINNER.get(parser.category, set())
  return (min(years) == start and max(years) >= 2021 and winners == expected and
    all(r.get('title') and r.get('author') and r.get('category') == parser.category and
      '\ufffd' not in r['title'] + r['author'] for r in rows))


def roster_complete(rows, winners=True):
  return len({identity(r) for r in rows}) == 6 and (not winners or sum(r.get('result') == 'winner' for r in rows) == 1)


def annual_html_rows(parser, source, url, year):
  soup = soup_for(source)
  own = soup.find('main') or soup
  heading = own.find(['h1', 'h2', 'h3'])
  if heading is None or parser.year_from_text(heading.get_text(' ', strip=True)) != year:
    raise ValueError('CBCA annual page has the wrong own award year.')
  rows = parser.html_rows(source, url)
  kind = 'shortlist' if 'shortlist' in urlsplit(url).path else 'winners'
  expected = 6 if kind == 'shortlist' else 1 if parser.category == 'New Illustrator' else 3
  if (len({identity(r) for r in rows}) != expected or any(int(r['award_year']) != year for r in rows) or
      (kind == 'winners' and sum(r['result'] == 'winner' for r in rows) != 1)):
    raise ValueError('Incomplete CBCA annual category roster.')
  return rows


def merge_year(archive_rows, supplemental):
  source_rows = deepcopy(archive_rows + supplemental)
  winners = [r for r in source_rows if r['result'] == 'winner']
  # Only a unique same-creator/main-title pair can correct a subtitle typo.
  # The 2023 official shortlist prints DEEP: Delve; results print DEEP: Dive.
  for row in source_rows:
    if row['result'] == 'winner' or ':' not in row['title']:
      continue
    main = normalize_heading(row['title'].split(':', 1)[0])
    same = [r for r in winners if ':' in r['title'] and
      identity(r)[:2] == identity(row)[:2] and
      normalize_heading(r['title'].split(':', 1)[0]) == main and
      normalize_heading(r['author']) == normalize_heading(row['author'])]
    alternatives = {identity(r) for r in source_rows if ':' in r['title'] and
      identity(r)[:2] == identity(row)[:2] and
      normalize_heading(r['title'].split(':', 1)[0]) == main and
      normalize_heading(r['author']) == normalize_heading(row['author']) and r['result'] != 'winner'}
    if len({identity(r) for r in same}) == 1 and len(alternatives) == 1:
      canonical = same[0]
      if row['title'] != canonical['title']:
        row['source_title'], row['title_source_url'] = row['title'], canonical['source_url']
        row['title'] = canonical['title']
  shortlist_sources = {}
  for row in source_rows:
    if 'shortlist' in urlsplit(row.get('source_url', '')).path.casefold():
      shortlist_sources.setdefault(row['source_url'], set()).add(identity(row))
  rosters = [keys for keys in shortlist_sources.values() if len(keys) == 6]
  roster = rosters[0] if rosters and all(keys == rosters[0] for keys in rosters) else None
  rows = {}
  authority = {identity(r) for r in archive_rows if r['result'] == 'winner'}
  if roster is not None and not authority <= roster:
    raise ValueError('CBCA archive winner is absent from the complete official shortlist.')
  archive_keys = {identity(r) for r in archive_rows}
  for row in source_rows:
    key = identity(row)
    if roster is not None and key not in roster:
      if key in archive_keys and row['result'] != 'winner':
        continue
      raise ValueError('CBCA result work is absent from the complete official shortlist.')
    if key not in rows:
      rows[key] = deepcopy(row)
    elif row['result'] == 'winner' and not authority:
      rows[key]['result'] = 'winner'
  if authority:
    for key, row in rows.items():
      row['result'] = 'winner' if key in authority else 'shortlisted'
  return list(rows.values())


def fetch_cbca(recipe, parser, html, fetch_url, cached=None, incremental=False, current_year=None, progress=None):
  current_year = int(current_year or date.today().year)
  middle_readers = parser.category == CATEGORY_MIDDLE_READERS
  cache = ParsedUnitCache('cbca-middle-readers-from-2027-v1' if middle_readers else 'cbca-official-units-v1', json.dumps([
    recipe.source_id, recipe.URL, parser.category, sorted(parser.category_aliases),
    AWARDS_URL, PDF_URL, ANNUAL_PDFS, SHORTLIST_URL], sort_keys=True), cached, incremental)
  units, notes = {}, []

  def previous(key):
    old = cache.old_units.get(key) or {}
    try:
      return restore_source_rows(cache.previous(key), old.get('metadata') or {})
    except (ValueError, TypeError):
      return []

  archive = parser.html_rows(html, recipe.URL)
  by_year = {}
  for row in archive:
    by_year.setdefault(int(row['award_year']), []).append(row)
  if not by_year:
    if middle_readers and current_year < HISTORY_START[CATEGORY_MIDDLE_READERS]:
      cache.put('archive', [], revision=2027, complete=True,
        metadata={'category_starts': 2027, 'not_applicable_before': 2027})
      parsed = parser.parsed_result(recipe.NAME, recipe.URL, [],
        notes=['CBCA Middle Readers starts with the 2027 Awards; there are no results for earlier award years.'])
      parsed['incremental_state'] = cache.state([])
      return parsed
    raise ValueError('CBCA archive has no available results for this category.')
  for year, rows in by_year.items():
    if middle_readers and year < HISTORY_START[CATEGORY_MIDDLE_READERS]:
      raise ValueError('CBCA Middle Readers cannot have results before its first 2027 award.')
    if not roster_complete(rows, winners=year < current_year):
      raise ValueError('CBCA archive category roster is incomplete.')
  units['archive'] = ([], None, True, {'years': sorted(by_year)})
  latest, earliest = max(by_year), min(by_year)
  advertised = list(parser.annual_links(html, recipe.URL))
  awards_ok = False
  try:
    awards = fetch_url(AWARDS_URL)
    heading = (soup_for(awards).find('main') or soup_for(awards)).find('h1')
    if heading is None or normalize_heading(heading.get_text(' ', strip=True)) != 'book of the year awards':
      raise ValueError('CBCA awards discovery document was incomplete.')
    advertised.extend(parser.annual_links(awards, AWARDS_URL))
    awards_ok = True
  except (ImportCancelledError, CamoufoxRequiredError):
    raise
  except Exception as err:
    notes.append(f'CBCA awards discovery could not be refreshed: {err}; prior source units remain pending.')
    advertised.extend((cache.old_units.get('awards', {}).get('metadata') or {}).get('urls', ()))
  advertised = list(dict.fromkeys(advertised))
  units['awards'] = ([], None, awards_ok, {'urls': advertised})

  discovered_pdf = parser.pdf_url_from_archive(html, recipe.URL)
  pdf_url = discovered_pdf or PDF_URL
  prior = previous('pdf')
  old = cache.old_units.get('pdf') or {}
  pdf_ok = (bool(discovered_pdf) and old.get('complete') is True and old.get('revision') == pdf_url and
    history_complete(parser, prior) and max(int(r['award_year']) for r in prior) < current_year)
  pdf_rows = prior
  if middle_readers:
    # This category starts after the universal historical PDF's coverage. Its
    # history is owned by annual units from 2027, including later archive gaps.
    pdf_rows, pdf_ok = [], True
  elif not pdf_ok:
    try:
      if progress:
        progress(1, 1, 'Fetching CBCA complete historical PDF')
      found = parser.pdf_rows(fetch_url(pdf_url), pdf_url)
      if not history_complete(parser, found):
        raise ValueError('CBCA historical PDF has incomplete year/category coverage.')
      pdf_rows, pdf_ok = found, bool(discovered_pdf)
    except (ImportCancelledError, CamoufoxRequiredError):
      raise
    except Exception as err:
      notes.append(f'CBCA historical PDF could not be refreshed: {err}; retained cached history where available.')
  units['pdf'] = (pdf_rows, pdf_url, pdf_ok,
    {'annual_history_starts': 2027} if middle_readers else {})
  last_pdf = max((int(r['award_year']) for r in pdf_rows), default=2026 if middle_readers else 2021)
  annual_urls = {}
  for url in advertised:
    year = parser.year_from_text(url)
    if year and (not middle_readers or year >= HISTORY_START[CATEGORY_MIDDLE_READERS]):
      annual_urls.setdefault(year, []).append(url)
  for year in range(last_pdf + 1, earliest):
    if year in ANNUAL_PDFS:
      annual_urls[year] = list(ANNUAL_PDFS[year])
      if year == 2022:
        annual_urls[year].insert(0, SHORTLIST_URL)
    elif year not in annual_urls:
      prior_urls = (cache.old_units.get(f'year:{year}', {}).get('metadata') or {}).get('urls')
      annual_urls[year] = prior_urls or [shortlist_url(year), winners_url(year)]
  # Previously discovered years stay addressable if archive paging changes.
  for key, old in cache.old_units.items():
    if key.startswith('year:'):
      year = int(key.split(':')[1])
      if year > last_pdf and year not in by_year and year not in annual_urls:
        annual_urls[year] = list((old.get('metadata') or {}).get('urls') or [shortlist_url(year), winners_url(year)])

  for year in sorted(set(by_year) | set(annual_urls)):
    key = f'year:{year}'
    fresh = by_year.get(year, [])
    urls = list(dict.fromkeys(annual_urls.get(year, ())))
    revision = signature([urls, fresh])
    old = cache.old_units.get(key) or {}
    prior = previous(key)
    can_reuse = (awards_ok and year < current_year and year < latest and old.get('complete') is True and
      old.get('revision') == revision and roster_complete(merge_year(fresh, prior)))
    old_archive_count = (old.get('metadata') or {}).get('archive_count', 0)
    if type(old_archive_count) is not int or not 0 <= old_archive_count <= len(prior):
      can_reuse = False
      old_archive_count = 0
    source_rows, complete = prior[old_archive_count:], can_reuse
    if not can_reuse:
      try:
        found = []
        for url in urls:
          if progress:
            progress(1, 1, f'Fetching {year} CBCA sources')
          payload = fetch_url(url)
          if url == SHORTLIST_URL:
            found.extend(shortlist_rows(parser, payload, fetch_url))
          elif urlsplit(url).path.lower().endswith('.pdf'):
            rows = parser.pdf_rows(payload, url)
            expected = 6 if 'shortlist' in url.lower() else 1 if parser.category == 'New Illustrator' else 3
            if len({identity(r) for r in rows}) != expected or any(int(r['award_year']) != year for r in rows):
              raise ValueError('Incomplete CBCA annual PDF category roster.')
            found.extend(rows)
          else:
            found.extend(annual_html_rows(parser, payload, url, year))
        result_advertised = any('winner' in urlsplit(url).path.casefold() for url in urls)
        if not roster_complete(merge_year(fresh, found), winners=year < current_year or result_advertised):
          raise ValueError('CBCA year does not expose a complete shortlist/result roster.')
        source_rows, complete = found, True
      except (ImportCancelledError, CamoufoxRequiredError):
        raise
      except Exception as err:
        notes.append(f'CBCA {year} could not be refreshed: {err}; retained whole cached year where available.')
        source_rows = prior
        complete = False
    raw = fresh + source_rows
    if not complete:
      raw = list({json.dumps(r, sort_keys=True): r for r in raw}.values())
    units[key] = (raw, revision, complete, {'urls': urls, 'archive_count': len(fresh)})

  all_years = {}
  # History and each year are separate ownership units; no source result leaks
  # from a previous merge back into a reused raw source projection.
  for row in pdf_rows:
    all_years.setdefault(int(row['award_year']), []).append(row)
  for key, (rows, _, _, _) in units.items():
    if key.startswith('year:'):
      year = int(key.split(':')[1])
      all_years.setdefault(year, []).extend(rows)
  merged = [row for year, rows in sorted(all_years.items()) for row in merge_year(by_year.get(year, []), rows)]
  entries = parser.entries_from_rows(parser.dedupe_rows(merged))
  if not entries:
    raise ValueError('No CBCA entries found on official sources.')
  for key, (rows, revision, complete, extra) in units.items():
    projected, metadata = project_source_rows(rows, entries, identity)
    metadata.update(extra)
    cache.put(key, projected, revision=revision, complete=complete, metadata=metadata)
  notes.extend(parser.coverage_notes(entries, current_year))
  parsed = parser.parsed_result(recipe.NAME, recipe.URL, entries, notes=notes)
  parsed['incremental_state'] = cache.state(entries)
  parsed['incremental_state']['discovery'] = {'refresh_units': [f'year:{latest}']}
  return parsed
