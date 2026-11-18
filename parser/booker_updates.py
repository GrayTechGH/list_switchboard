"""Fresh full pagination discovers annual units; only settled history is reused."""

import json
import datetime

try:
  from calibre_plugins.list_switchboard.parser.booker_modern import index_links, valid_empty_year
  from calibre_plugins.list_switchboard.parser.annual_updates import read_annual_pages
except ImportError:
  from .booker_modern import index_links, valid_empty_year
  from .annual_updates import read_annual_pages


def discover_years(recipe, html, base_url, fetch_url):
  years, pending = index_links(html, base_url, recipe.YEAR_URL_PATTERN)
  seen = {0}
  while pending:
    number = pending.pop(0)
    if number in seen:
      continue
    if number > 100:
      raise ValueError('Official Booker pagination exceeded its bounded archive.')
    seen.add(number)
    if fetch_url is None:
      raise ValueError('Official Booker archive requires linked pagination.')
    page_url = base_url + '?page=' + str(number)
    discovered, links = index_links(fetch_url(page_url), page_url, recipe.YEAR_URL_PATTERN)
    years.extend(url for url in discovered if url not in years)
    pending.extend(page for page in links if page not in seen and page not in pending)
  if not years:
    raise ValueError('Official Booker Library had no prize-year URLs.')
  discovered = [(url, recipe.parser().year_from_url(url)) for url in years]
  actual = {year for url, year in discovered}
  latest = max(actual)
  if latest < datetime.datetime.now().year - 1:
    raise ValueError('Official Booker archive is missing its recent award years.')
  expected = set(range(recipe.FIRST_YEAR, latest + 1))
  if recipe.source_id == 'international_booker_prize':
    expected = {year for year in expected if year >= 2016 or year % 2 == 1}
  if actual != expected:
    raise ValueError('Official Booker archive has incomplete or unexpected year coverage: ' +
      json.dumps({'missing': sorted(expected - actual), 'unexpected': sorted(actual - expected)}))
  return sorted(discovered, key=lambda item: item[1], reverse=True)


def fetch_booker_years(recipe, parser, html, base_url, fetch_url,
    cached_parsed=None, incremental_update=False, progress=None):
  discovered = discover_years(recipe, html, base_url, fetch_url)
  key = json.dumps([recipe.source_id, base_url, recipe.NAME, recipe.CATEGORY,
    recipe.YEAR_URL_PATTERN, recipe.FIRST_YEAR, parser.url_marker, 'bounded-booker-cards-v1'])
  parsed = read_annual_pages(key, discovered, fetch_url,
    lambda page, url: parser.parse(page, url, recipe.NAME, recipe.CATEGORY, fetch_url=fetch_url),
    cached_parsed=cached_parsed, incremental_update=incremental_update,
    validate_empty=valid_empty_year, progress=progress)
  for url, year in discovered:
    unit = parsed['incremental_state']['units'][url]
    if year >= 2016 and not unit['entry_indexes']:
      # A valid forthcoming intake is not a settled empty award. It must still
      # refresh after calendar rollover until real results become available.
      unit['metadata']['settled'] = False
  if recipe.source_id == 'international_booker_prize' and any(year < 2016 for url, year in discovered):
    parsed['notes'].append('International Booker years before 2016 honour an author’s body of work; no individual book titles are inferred.')
  parsed.update(name=recipe.NAME, match_series=False)
  return parsed
