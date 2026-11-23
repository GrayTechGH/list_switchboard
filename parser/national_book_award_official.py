"""Read advertised Foundation category routes within one award year.

Historical tabs use different slugs, and subcategories can sit below an
unrelated default parent. Only advertised, same-year Foundation routes enter
the configured family. One annual cache unit owns the complete routed year.
"""

import re
from urllib.parse import parse_qs, urljoin, urlsplit

from .award_base import normalize_heading, normalize_line
from .generic import position_sort_key
from .incremental import ParsedUnitCache

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError


NONFICTION_CATEGORIES = {
  normalize_heading(label): label for label in (
    'Nonfiction', 'Arts and Letters', 'History and Biography', 'History',
    'Biography', 'Autobiography', 'General Nonfiction', 'Current Interest',
    'General Reference', 'Science', 'The Sciences', 'Contemporary Affairs',
    'Philosophy and Religion', 'Science, Philosophy and Religion',
    'Religion/Inspiration', 'Autobiography/Biography',
  )
}
NONFICTION_CATEGORIES['general reference books'] = 'General Reference'


def category_label(label, family):
  text = normalize_heading(label)
  text = re.sub(r'\b(?:hardcover|paperback|paper|hc|pb)\b', '', text)
  text = normalize_line(text).replace('non fiction', 'nonfiction')
  family = normalize_heading(family)
  if family == 'fiction':
    return 'Fiction' if text == 'fiction' else None
  if family == 'nonfiction':
    return NONFICTION_CATEGORIES.get(text)
  if family == normalize_heading("Young People's Literature"):
    if text == family:
      return "Young People's Literature"
    for prefix in ("children s books", "children s literature"):
      if text == prefix:
        return "Children's Books" if prefix.endswith('books') else "Children's Literature"
      if text.startswith(prefix + ' '):
        return {'fiction': 'Fiction', 'nonfiction': 'Nonfiction',
          'picture books': 'Picture Books'}.get(text[len(prefix):].strip())
  return None


def category_routes(parser, root, base_url, family):
  nodes = root.xpath(
    '//a[contains(concat(" ", normalize-space(@class), " "), " category-winner ")'
    ' or contains(concat(" ", normalize-space(@class), " "), " sub-category-winners ")]')
  if not nodes:
    return None
  routes = {}
  for node in nodes:
    label = parser.node_text(node)
    category = category_label(label, family)
    if category is None:
      continue
    url = urljoin(base_url, node.get('href') or '')
    target = urlsplit(url)
    if (target.scheme != 'https' or target.hostname not in ('nationalbook.org', 'www.nationalbook.org')
        or target.username or target.password or target.path != urlsplit(base_url).path):
      raise ValueError('Foundation category link left the configured award year.')
    query = parse_qs(target.query)
    if (set(query) - {'cat', 'sub-cat'} or len(query.get('cat', [])) != 1
        or len(query.get('sub-cat', [])) > 1):
      raise ValueError('Foundation category link has an unsupported query.')
    key = (query.get('sub-cat') or query['cat'])[0]
    routes.setdefault(key, {'url': url, 'label': label, 'category': category,
      'parent': query['cat'][0], 'child': 'sub-cat' in query})
  return list(routes.values())


def read_year(parser, html, base_url, name, family, fetch_url):
  root = parser.html_root(html)
  routes = category_routes(parser, root, base_url, family)
  if routes is None:
    return parser.parse(html, base_url, name, family, fetch_url=fetch_url)
  if not routes:
    year = parser.year_from_url(base_url)
    titles = root.xpath('//title')
    branded = titles and f'National Book Awards {year}' in parser.node_text(titles[0])
    roster = root.xpath('//div[contains(concat(" ", normalize-space(@class), " "), " finalists-wrapper ")]')
    if not branded or not roster:
      parser.validate_category(root, family, base_url)
      raise ValueError('Foundation page did not establish category absence for this award year.')
    return parser.parsed_result(name, base_url, [])
  rows = []
  for route in routes:
    page = html if route['url'] == base_url else fetch_url(route['url'])
    current = parser.parse_rows(page, route['url'], route['label'], fetch_url=fetch_url)
    if not current:
      raise ValueError(f'Official Foundation category {route["label"]} had no usable roster.')
    if (family == 'Fiction' and parser.year_from_url(base_url) in (1980, 1981, 1982, 1983)
        and re.search(r'\b(?:hardcover|paperback)\b', route['label'], re.I)
        and sum(row['result'] == 'winner' for row in current) != 1):
      # These split-format awards have one winner per format. The 1982
      # hardcover filter also returns a children's winner and its nominees.
      raise ValueError('Foundation split-format Fiction roster mixes award categories.')
    for row in current:
      row['category'] = route['category']
    rows.extend(current)
  # Generic Nonfiction pages also carry nominees from narrower branches.
  # Prefer the source's specific category when the same work appears in both.
  if family == 'Nonfiction':
    specific = {(row['award_year'], normalize_heading(row['title']),
      normalize_heading(row['author']), row['result']) for row in rows
      if row['category'] != 'Nonfiction'}
    rows = [row for row in rows if row['category'] != 'Nonfiction' or (
      row['award_year'], normalize_heading(row['title']), normalize_heading(row['author']),
      row['result']) not in specific]
  entries = parser.entries_from_rows(parser.dedupe_rows(rows))
  return parser.parsed_result(name, base_url, entries)


def supplement_failed_years(parsed, fetch_url, wikipedia_url, name, family, log=None):
  """Wikipedia fills failed annual units; its failure cannot discard Foundation.

  Complete Foundation years keep authority. Supplemented units remain incomplete
  so a later update retries the official source, with per-entry provenance intact.
  """
  state = parsed.get('incremental_state') or {}
  units = state.get('units') or {}
  failed = {key: str(unit['revision']) for key, unit in units.items()
    if unit.get('complete') is not True}
  if not failed or not parsed.get('entries'):
    return parsed
  try:
    from .national_book_award import NationalBookAwardWikipediaParser
    supplement = NationalBookAwardWikipediaParser().parse(
      fetch_url(wikipedia_url), wikipedia_url, name, family)
    if not supplement['entries']:
      raise ValueError('Wikipedia did not expose usable award entries.')
  except (ImportCancelledError, CamoufoxRequiredError):
    raise
  except Exception as err:
    note = f'Wikipedia supplement unavailable; Foundation results retained: {err}'
    parsed['notes'].append(note)
    if log is not None:
      log(note)
    return parsed

  by_year = {}
  for entry in supplement['entries']:
    by_year.setdefault(str(entry['award_year']), []).append(entry)
  cache = ParsedUnitCache(state['strategy'], state['source_key'])
  original = parsed['entries']
  entries, filled, missing = [], set(), set()
  for key, unit in units.items():
    rows = [original[index] for index in unit['entry_indexes']]
    metadata = dict(unit.get('metadata') or {})
    if key in failed:
      year = failed[key]
      if by_year.get(year):
        rows = by_year[year]
        metadata['supplement_source'] = wikipedia_url
        filled.add(year)
      else:
        missing.add(year)
    cache.put(key, rows, revision=unit['revision'], complete=unit['complete'], metadata=metadata)
    entries.extend(rows)
  parsed['entries'] = sorted(entries, key=lambda entry: position_sort_key(entry['position']))
  parsed['incremental_state'] = cache.state(parsed['entries'])
  if filled:
    parsed['notes'].append('Wikipedia supplied unavailable Foundation award years: ' + ', '.join(sorted(filled)) + '.')
  if missing:
    parsed['notes'].append('Wikipedia had no supplement for Foundation award years: ' + ', '.join(sorted(missing)) + '.')
  return parsed
