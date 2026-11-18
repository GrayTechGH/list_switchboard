"""Refresh rolling sources; reuse complete closed dated winner supplements.

The original directory reader accepts HTML/JSON exports and explicitly reports
unavailable embedded Airtable history. That coverage note remains visible; a
successful directory-document unit never claims to contain the virtual grid.
"""

import datetime
import hashlib
import json
import re
from copy import deepcopy
from urllib.parse import urljoin, urlsplit

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError
  from calibre_plugins.list_switchboard.parser.base import author_list
  from calibre_plugins.list_switchboard.parser.award_base import normalize_heading
  from calibre_plugins.list_switchboard.parser.incremental import ParsedUnitCache, project_source_rows, restore_source_rows
  from calibre_plugins.list_switchboard.parser.lambda_current import modern_page, read_current, soup_for
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError
  from .base import author_list
  from .award_base import normalize_heading
  from .incremental import ParsedUnitCache, project_source_rows, restore_source_rows
  from .lambda_current import modern_page, read_current, soup_for


DIRECTORY_NOTE = ('Lambda Lammys Directory embeds Airtable data; no parseable '
  'server-rendered directory rows were available from the fetched page.')


def identity(row):
  return (str(row.get('award_year')), normalize_heading(row.get('category', '')),
    normalize_heading(row.get('title', '')),
    tuple(sorted(normalize_heading(a) for a in author_list(row.get('authors', row.get('author', ''))))))


def directory_source(parser, html, url):
  rows = parser.parse_directory_rows(html, url)
  embedded = not rows and parser.has_airtable_embed(html)
  if not rows and not embedded:
    raise ValueError('Lambda directory exposed neither supported rows nor its known Airtable embed.')
  return {'rows': rows, 'notes': [DIRECTORY_NOTE] if embedded else [], 'complete': True,
    'coverage': 'embedded-history-unavailable' if embedded else 'parsed-directory-rows'}


def current_source(parser, html, url, kind):
  if modern_page(html):
    result = read_current(parser, html, url, kind)
  else:
    rows = (parser.parse_current_finalists_page(html, url) if kind == 'finalists' else parser.parse_current_winners_page(html, url))
    years = {int(row['award_year']) for row in rows}
    result = {'rows': rows, 'notes': [], 'complete': bool(rows),
      'publication_year': next(iter(years)) if len(years) == 1 else None}
    intro = []
    for node in soup_for(html).find_all(['h1', 'h2', 'p']):
      text = node.get_text(' ', strip=True)
      if node.name == 'h2' and parser.is_romance_category(text):
        break
      intro.append(text)
    result['closed'] = bool(re.search(r'ceremony took place|winners (?:were |are |have been )?announced', ' '.join(intro), re.I))
  if not result['complete']:
    raise ValueError('Lambda award article was incomplete: ' + '; '.join(result['notes']))
  return result


def winner_urls(html, base_url, configured):
  urls = list(configured)
  for link in soup_for(html).find_all('a', href=True):
    target = urlsplit(urljoin(base_url, link['href']))
    if (target.scheme in ('http', 'https') and target.netloc in ('lambdaliterary.org', 'www.lambdaliterary.org') and
        re.fullmatch(r'/awards/(?:19|20)\d{2}-winners/?', target.path)):
      url = target._replace(scheme='https', netloc='lambdaliterary.org', query='', fragment='').geturl().rstrip('/') + '/'
      if url not in urls:
        urls.append(url)
  return urls


def merge_rows(parser, directory_rows, other_rows):
  authority = {}
  for row in directory_rows:
    if row.get('result') == 'winner':
      authority.setdefault(identity(row)[:2], set()).add(identity(row))
  rows = deepcopy(directory_rows + other_rows)
  for row in rows:
    winners = authority.get(identity(row)[:2])
    if winners and row.get('result') == 'winner' and identity(row) not in winners:
      row['result'] = 'shortlisted'
  return parser.dedupe_rows(rows)


def fetch_lambda(recipe, parser, html, base_url, fetch_url, cached=None, incremental=False):
  cache = ParsedUnitCache('lambda-rolling-dated-v1', json.dumps([
    recipe.source_id, base_url, recipe.FINALISTS_URL, recipe.WINNER_URLS,
    sorted(recipe.ROMANCE_CATEGORIES)]), cached, incremental)
  units, notes = {}, []

  def previous(url):
    metadata = (cache.old_units.get(url) or {}).get('metadata') or {}
    try:
      return restore_source_rows(cache.previous(url), metadata), metadata
    except (TypeError, ValueError):
      return [], {}

  directory = directory_source(parser, html, base_url)
  units[base_url] = (directory['rows'], None, True, directory['notes'], {'coverage': directory['coverage']})
  finalist_rows, finalist_metadata = previous(recipe.FINALISTS_URL)
  finalists, finalists_complete = {}, False
  finalist_html = ''
  try:
    finalist_html = fetch_url(recipe.FINALISTS_URL)
    finalists = current_source(parser, finalist_html, recipe.FINALISTS_URL, 'finalists')
    finalist_rows = finalists['rows']; finalists_complete = True
  except (ImportCancelledError, CamoufoxRequiredError):
    raise
  except Exception as err:
    notes.append(f'Lambda current finalists could not be refreshed: {err}; retained cached rows where available.')
  current_year = finalists.get('publication_year')
  units[recipe.FINALISTS_URL] = (finalist_rows, None, finalists_complete, [],
    {'publication_year': current_year or finalist_metadata.get('publication_year')})
  if directory['coverage'] == 'embedded-history-unavailable':
    # The rolling page can advance before its older finalists become readable
    # in the embedded history. Keep previously parsed years, not raw documents.
    # A supported fresh directory export replaces these retained snapshots.
    for key, old in cache.old_units.items():
      if key != recipe.FINALISTS_URL and not key.startswith('retained-finalists-'):
        continue
      retained, _metadata = previous(key)
      by_year = {}
      for row in retained:
        year = int(row['award_year'])
        if (key.startswith('retained-finalists-') and current_year is None) or (current_year and year < current_year):
          by_year.setdefault(year, []).append(row)
      for year, rows in by_year.items():
        units[f'retained-finalists-{year}'] = (rows, None, old.get('complete') is True, [],
          {'retained_publication_year': year})
  discovered = winner_urls(html, base_url, recipe.WINNER_URLS)
  if finalists_complete:
    discovered = winner_urls(finalist_html, recipe.FINALISTS_URL, discovered)
  for url in discovered:
    year = parser.year_from_text(url) - 1
    rows, metadata = previous(url)
    old = cache.old_units.get(url) or {}
    same_cycle = current_year == year
    roster = sorted(identity(row) for row in finalist_rows if str(row['award_year']) == str(year))
    directory_winners = sorted(identity(row) for row in directory['rows']
      if str(row['award_year']) == str(year) and row.get('result') == 'winner')
    revision = [url, hashlib.sha256(json.dumps([roster if same_cycle else [], directory_winners]).encode()).hexdigest()]
    closed = bool(finalists_complete and current_year is not None and
      (year < current_year or (same_cycle and finalists.get('closed'))))
    eligible = (closed and year < datetime.datetime.now().year and rows and
      all(row.get('result') == 'winner' and str(row.get('award_year')) == str(year) for row in rows))
    complete = bool(eligible and metadata.get('closed_certified') is True and
      old.get('complete') is True and old.get('revision') == revision)
    if not complete:
      try:
        source = current_source(parser, fetch_url(url), url, 'winners')
        if any(str(row.get('award_year')) != str(year) for row in source['rows']):
          raise ValueError('Lambda dated winner source returned another publication year.')
        rows, complete = source['rows'], source['complete']
      except (ImportCancelledError, CamoufoxRequiredError):
        raise
      except Exception as err:
        notes.append(f'Lambda dated winners could not be refreshed: {url}: {err}; retained cached rows where available.')
        complete = False
    if same_cycle:
      closed = closed and bool(rows) and all(identity(row) in roster for row in rows)
    units[url] = (rows, revision, complete, [], {'closed_certified': bool(closed and complete)})
  other_rows = [row for url, unit in units.items() if url != base_url for row in unit[0]]
  merged = merge_rows(parser, directory['rows'], other_rows)
  entries = parser.entries_from_rows(merged)
  if not entries:
    raise ValueError('Could not parse Lambda Literary Awards romance rows from source.')
  for url, (rows, revision, complete, unit_notes, extra) in units.items():
    projected, metadata = project_source_rows(rows, entries, identity)
    metadata.update(extra); metadata['notes'] = unit_notes
    cache.put(url, projected, revision=revision, complete=complete, metadata=metadata)
    notes.extend(unit_notes)
  parsed = parser.parsed_result(recipe.NAME, base_url, entries, notes)
  parsed['incremental_state'] = cache.state(entries)
  parsed['incremental_state']['discovery'] = {'refresh_units': [recipe.FINALISTS_URL]}
  return parsed
