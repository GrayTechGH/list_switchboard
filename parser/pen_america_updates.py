"""Refresh prize discovery and retain closed parsed annual PEN source units.

Landing winners stay authoritative. A closed post is reusable only under fresh
landing authority for its year, or validated omission from a complete annual
article. Current/winnerless posts and failed units refresh. Reversible parsed
source projections preserve nominee rows through winner promotion and removal.
"""

import datetime
import json
import re
from urllib.parse import urljoin,urlsplit

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError,CamoufoxRequiredError
  from calibre_plugins.list_switchboard.parser.incremental import ParsedUnitCache,project_source_rows,restore_source_rows
  from calibre_plugins.list_switchboard.parser.base import author_list
  from calibre_plugins.list_switchboard.parser.award_base import normalize_heading
  from calibre_plugins.list_switchboard.parser.pen_america_modern import source_soup
except ImportError:
  from errors import ImportCancelledError,CamoufoxRequiredError
  from .incremental import ParsedUnitCache,project_source_rows,restore_source_rows
  from .base import author_list
  from .award_base import normalize_heading
  from .pen_america_modern import source_soup


def is_annual_url(url):
  if not isinstance(url,str):return False
  target=urlsplit(url)
  return bool(target.scheme=='https' and target.netloc.casefold() in ('pen.org','www.pen.org') and
    re.fullmatch(r'/(?:announcing-the-)?(?:19|20)\d{2}-(?:pen-america-)?literary-awards-(?:winners|finalists)/?',target.path,re.I))


def annual_links(html,base_url):
  links=[]
  for node in source_soup(html).find_all('a',href=True):
    target=urlsplit(urljoin(base_url,node['href']))
    if is_annual_url(target.geturl()):
      url=target._replace(query='',fragment='').geturl()
      if url not in links:links.append(url)
  return links


def fetch_pen_america(recipe,fetch_url,cached_parsed=None,incremental_update=False,
    before_fetch=None,after_fetch=None,before_parse=None,progress=None,log=None):
  parser=recipe.parser();config=recipe.config()
  cache=ParsedUnitCache('pen-america-source-posts-v1',json.dumps([
    recipe.source_id,recipe.NAME,recipe.URL,config.award_name,config.category,
    config.heading_aliases,config.split_mode,recipe.ANNUAL_POST_URLS]),cached_parsed,incremental_update)
  notes=[];units={};discovered=[]
  def previous(url):
    old=cache.old_units.get(url) or {};metadata=old.get('metadata') or {}
    try:return restore_source_rows(cache.previous(url),metadata),metadata.get('notes',[])
    except (ValueError,TypeError):return [],[]
  def read(url,kind):
    if before_fetch is not None:before_fetch(url)
    html=fetch_url(url)
    if after_fetch is not None:after_fetch(url,html)
    if before_parse is not None:before_parse(url)
    return html,parser.read_source(html,url,config,kind)
  landing_complete=False
  try:
    landing_html,landing=read(recipe.URL,'landing');landing_complete=landing.get('complete',True)
    discovered=annual_links(landing_html,recipe.URL)
    if not landing_complete:
      old_rows,_old_notes=previous(recipe.URL)
      if old_rows:landing['rows']=old_rows
  except (ImportCancelledError,CamoufoxRequiredError):raise
  except Exception as err:
    if not cache.old_units:raise
    rows,old_notes=previous(recipe.URL)
    landing={'rows':rows,'notes':old_notes,'category_absent':False}
    discovered=cache.old_discovery.get('annual_urls') or []
    if not isinstance(discovered,list):discovered=[]
    notes.append(f'PEN landing page could not be refreshed: {recipe.URL}: {err}; retained cached history.')
  units[recipe.URL]=(landing['rows'],None,landing_complete,landing['notes'],False)
  winners={}
  for row in landing['rows']:
    if row.get('result')=='winner':winners.setdefault(int(row['award_year']),[]).append([row['title'],row['author']])
  latest=max(winners,default=0);calendar=datetime.datetime.now().year
  configured=dict(recipe.ANNUAL_POST_URLS)
  urls=list(dict.fromkeys(list(configured)+discovered))
  # Retained discovery is bookkeeping, not permission to fetch another host.
  urls=[url for url in urls if url in configured or is_annual_url(url)]
  for index,url in enumerate(urls,1):
    kind=configured.get(url,'annual');year=parser.year_from_text(url)
    old=cache.old_units.get(url) or {};metadata=old.get('metadata') or {}
    rows,unit_notes=previous(url);absence=metadata.get('category_absent') is True
    revision=[url,year,winners.get(year,[])]
    reusable=(landing_complete and year and year<min(latest,calendar) and
      (bool(winners.get(year)) or absence) and old.get('complete') is True and old.get('revision')==revision)
    complete=False
    if reusable:
      try:restore_source_rows(cache.previous(url),metadata);complete=True
      except (ValueError,TypeError):pass
    if not complete:
      try:
        _html,parsed=read(url,kind)
        rows,unit_notes,absence=parsed['rows'],parsed['notes'],parsed['category_absent']
        if any(str(row.get('award_year'))!=str(year) for row in rows):
          raise ValueError('PEN annual source returned another award year.')
        complete=(bool(rows) or absence) and parsed.get('complete',True)
        if not complete:
          old_rows,old_notes=previous(url)
          if old_rows:rows,unit_notes=old_rows,old_notes+unit_notes
          unit_notes=unit_notes+[f'PEN annual source did not expose a usable category roster: {url}']
      except (ImportCancelledError,CamoufoxRequiredError):raise
      except Exception as err:
        if not cache.old_units:raise
        rows,unit_notes=previous(url)
        notes.append(f'PEN annual source could not be refreshed: {url}: {err}; retained cached entries.')
    units[url]=(rows,revision,complete,unit_notes,absence)
    if progress is not None:progress(index,len(urls),f'Processed PEN source {index} of {len(urls)}')
  all_rows=[row for rows,_revision,_complete,_notes,_absence in units.values() for row in rows]
  entries=parser.entries_from_rows(parser.dedupe_rows(all_rows),config)
  def identity(row):
    return (str(row['award_year']),normalize_heading(row['category']),normalize_heading(row['title']),
      tuple(normalize_heading(author) for author in author_list(row.get('authors',row.get('author')))))
  for url,(rows,revision,complete,unit_notes,absence) in units.items():
    projected,metadata=project_source_rows(rows,entries,identity)
    metadata.update(notes=unit_notes,category_absent=absence)
    cache.put(url,projected,revision=revision,complete=complete,metadata=metadata)
    notes.extend(unit_notes)
  parsed=parser.parsed_result(recipe.NAME,recipe.URL,entries,notes)
  parsed['incremental_state']=cache.state(entries)
  parsed['incremental_state']['discovery']={'annual_urls':discovered,'refresh_units':[recipe.URL]}
  return parsed
