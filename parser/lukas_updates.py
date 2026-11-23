"""Refresh official history and reuse news certified by its fresh year roster.

Only the official source attempt receives this scope. Fallback readers perform
their existing full imports, and missing/incompatible source bookkeeping starts
a new baseline. Projections retain each original outcome before promotion.
"""

import datetime
import json
from urllib.parse import urljoin,urlsplit

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError,CamoufoxRequiredError
  from calibre_plugins.list_switchboard.parser.incremental import ParsedUnitCache,project_source_rows,restore_source_rows
  from calibre_plugins.list_switchboard.parser.base import author_list
  from calibre_plugins.list_switchboard.parser.award_base import normalize_heading
  from calibre_plugins.list_switchboard.parser.lukas_modern import soup_for
except ImportError:
  from errors import ImportCancelledError,CamoufoxRequiredError
  from .incremental import ParsedUnitCache,project_source_rows,restore_source_rows
  from .base import author_list
  from .award_base import normalize_heading
  from .lukas_modern import soup_for


def author_key(value):return tuple(sorted(normalize_heading(a) for a in author_list(value)))


def certified_rows(rows,roster):
  if not rows or not any(r['result']=='winner' and r.get('title') for r in roster):return False
  authors={author_key(row['author']) for row in roster}
  return all(author_key(row['author']) in authors for row in rows)


def fetch_lukas_official(recipe,parser,html,base_url,fetch_url,extra_urls,
    cached_parsed=None,incremental_update=False,progress=None):
  cache=ParsedUnitCache('lukas-archive-certified-news-v1',json.dumps([
    recipe.source_id,base_url,recipe.NAME,recipe.CATEGORY,parser.CATEGORY_ALIASES,
    parser.PEER_PRIZE_ALIASES,extra_urls]),cached_parsed,incremental_update)
  notes=[];units={}
  def previous(url):
    old=cache.old_units.get(url) or {};metadata=old.get('metadata') or {}
    try:return restore_source_rows(cache.previous(url),metadata),metadata.get('notes',[])
    except (ValueError,TypeError):return [],[]
  source=parser.read_official_source(html,base_url,recipe.CATEGORY)
  archive_rows,archive_notes=source['rows'],source['notes']
  archive_complete=source['complete']
  if not archive_complete:
    old_rows,_old_notes=previous(base_url)
    if old_rows:archive_rows=old_rows
  units[base_url]=(archive_rows,None,archive_complete,archive_notes)
  # A maintained manifest preserves earlier coverage; fresh advertised news can
  # add a later cycle without a cached page number or wider search crawl.
  urls=list(extra_urls)
  for link in soup_for(html).find_all('a',href=True):
    target=urlsplit(urljoin(base_url,link['href']))
    if (target.scheme=='https' and target.netloc=='journalism.columbia.edu' and
        target.path.startswith('/news/lukas-') and parser.year_from_text(target.path)):
      url=target._replace(query='',fragment='').geturl()
      if url not in urls:urls.append(url)
  for index,url in enumerate(urls,1):
    year=parser.year_from_text(url)
    revision=[url,(source.get('revisions') or {}).get(str(year))]
    roster=(source.get('rosters') or {}).get(year,[])
    old=cache.old_units.get(url) or {};rows,unit_notes=previous(url);complete=False
    if (archive_complete and year and year<=datetime.datetime.now().year and revision[-1] and
        old.get('complete') is True and old.get('revision')==revision and certified_rows(rows,roster)):
      complete=True
    if not complete and fetch_url is not None:
      try:
        parsed=parser.read_official_source(fetch_url(url),url,recipe.CATEGORY)
        if any(str(row.get('award_year'))!=str(year) for row in parsed['rows']):
          raise ValueError('Official prize news returned another award year.')
        fresh,fresh_notes=parsed['rows'],parsed['notes'];complete=parsed['complete']
        if complete:rows,unit_notes=fresh,fresh_notes
        else:
          if not rows:rows=fresh
          unit_notes=unit_notes+fresh_notes
      except (ImportCancelledError,CamoufoxRequiredError):raise
      except Exception as err:
        if not cache.old_units:raise
        notes.append(f'Official Lukas news could not be refreshed: {url}: {err}; retained cached entries.')
    elif fetch_url is None and not complete:
      continue
    units[url]=(rows,revision,complete,unit_notes)
    if progress is not None:progress(index,len(urls),f'Processed official prize news {index} of {len(urls)}')
  rows=parser.dedupe_rows([row for unit in units.values() for row in unit[0]])
  entries=parser.entries_from_rows(rows)
  def identity(row):
    return (str(row['award_year']),normalize_heading(row['category']),normalize_heading(row['title']),
      author_key(row.get('authors',row.get('author'))))
  for url,(source_rows,revision,complete,unit_notes) in units.items():
    projected,metadata=project_source_rows(source_rows,entries,identity)
    metadata['notes']=unit_notes;cache.put(url,projected,revision=revision,complete=complete,metadata=metadata)
    notes.extend(unit_notes)
  parsed=parser.parsed_result(recipe.NAME,base_url,entries,notes)
  parsed['incremental_state']=cache.state(entries)
  parsed['incremental_state']['discovery']={'refresh_units':[base_url]}
  return parsed
