"""Reuse official history only within a freshly verified current award cycle.

Current pages always refresh. Changed rosters, guidelines, rollover and failed
discovery refresh history; source projections preserve original credits and
outcomes through the existing history/current precedence rules.
"""

import datetime
import hashlib
import json

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError,CamoufoxRequiredError
  from calibre_plugins.list_switchboard.parser.award_base import normalize_heading,normalize_line
  from calibre_plugins.list_switchboard.parser.incremental import ParsedUnitCache,project_source_rows,restore_source_rows
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
  from calibre_plugins.list_switchboard.parser.base import author_list
except ImportError:
  from errors import ImportCancelledError,CamoufoxRequiredError
  from .award_base import normalize_heading,normalize_line
  from .incremental import ParsedUnitCache,project_source_rows,restore_source_rows
  from .generic import position_sort_key
  from .base import author_list


def current_revision(html):
  soup=BeautifulSoup(html or '','html.parser');body=soup.find('main') or soup
  for node in body.find_all(['script','style','nav','header','footer','svg']):node.decompose()
  return hashlib.sha256(normalize_line(body.get_text(' ',strip=True)).encode('utf-8')).hexdigest()


def fetch_writers_trust(recipe,fetch_url,cached_parsed=None,incremental_update=False,
    before_fetch=None,after_fetch=None,before_parse=None,progress=None):
  parser=recipe.parser()
  cache=ParsedUnitCache('writers-trust-current-cycle-v1',json.dumps([
    recipe.URL,recipe.CURRENT_URL,recipe.NAME,parser.award_name,parser.category,
    parser.category_aliases,parser.current_page_enabled]),cached_parsed,incremental_update)
  notes=[]
  def previous(key):
    try:return restore_source_rows(cache.previous(key),(cache.old_units.get(key) or {}).get('metadata') or {})
    except (ValueError,TypeError):return []
  def read(url):
    if before_fetch is not None:before_fetch(url)
    if progress is not None:progress(0,1,f'Fetching {recipe.NAME}: {url}')
    html=recipe.fetch_url(fetch_url,url)
    if after_fetch is not None:after_fetch(url,html)
    return html
  current,revision,current_complete=previous('current'),None,False
  if parser.current_page_enabled:
    try:
      html=read(recipe.CURRENT_URL)
      current=parser.validate_fetch_payload(html,recipe.CURRENT_URL)
      revision=current_revision(html);current_complete=True
    except (ImportCancelledError,CamoufoxRequiredError):raise
    except Exception as err:notes.append(f'{recipe.NAME} current award page could not be fetched: {recipe.CURRENT_URL}: {err}')
  else:current,revision,current_complete=[],'disabled',True
  history=previous('history');old=cache.old_units.get('history') or {}
  cycle=max((int(r['award_year']) for r in current),default=0)
  last=max((int(r['award_year']) for r in history),default=0)
  identity=[recipe.URL,revision]
  if (current_complete and old.get('complete') is True and old.get('revision')==identity and
      history and cycle==last and cycle>=datetime.datetime.now().year):
    history_complete=True
  else:
    history_complete=False
    try:
      fresh=parser.validate_fetch_payload(read(recipe.URL),recipe.URL)
      history,history_complete=fresh,True
    except (ImportCancelledError,CamoufoxRequiredError):raise
    except Exception as err:notes.append(f'{recipe.NAME} history page could not be fetched: {recipe.URL}: {err}')
  if before_parse is not None:before_parse(recipe.URL)
  entries=sorted(parser.entries_from_rows(parser.dedupe_rows(history+current)),key=lambda item:position_sort_key(item.get('position','')))
  if not entries:raise ValueError(f'No {recipe.NAME} entries found on the official Writers Trust pages.')
  for key,source_rows,rev,complete in (('history',history,identity,history_complete),('current',current,revision,current_complete)):
    projected,metadata=project_source_rows(source_rows,entries,lambda row:(str(row['award_year']),normalize_heading(row['category']),
      normalize_heading(row['title']),tuple(normalize_heading(a) for a in author_list(row.get('authors',row.get('author'))))))
    cache.put(key,projected,revision=rev,complete=complete,metadata=metadata)
  result=parser.parsed_result(recipe.NAME,recipe.URL,entries,notes=notes)
  result['incremental_state']=cache.state(entries)
  result['incremental_state']['discovery']={'refresh_units':['current']}
  return result
