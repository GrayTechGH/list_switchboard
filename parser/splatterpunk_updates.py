"""Retain reversible source rows while refreshing intake and Goodreads pages.

Winner history is reusable only during explicit next-calendar-year nomination
intake, with uninterrupted winners through this calendar year and an unchanged
fresh intake revision. Active ballots, rollover and changed intake refetch it.
"""

import datetime
import json

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError,CamoufoxRequiredError
  from calibre_plugins.list_switchboard.parser.incremental import ParsedUnitCache,project_source_rows,restore_source_rows
  from calibre_plugins.list_switchboard.parser.splatterpunk import GOODREADS_URL,OFFICIAL_AWARDS_API_URL,OFFICIAL_PAST_WINNERS_API_URL
except ImportError:
  from errors import ImportCancelledError,CamoufoxRequiredError
  from .incremental import ParsedUnitCache,project_source_rows,restore_source_rows
  from .splatterpunk import GOODREADS_URL,OFFICIAL_AWARDS_API_URL,OFFICIAL_PAST_WINNERS_API_URL


def fetch_splatterpunk(recipe,fetch_url,cached_parsed=None,incremental_update=False,
    before_fetch=None,after_fetch=None,before_parse=None,log=None,progress=None):
  parser=recipe.parser()
  cache=ParsedUnitCache('splatterpunk-next-cycle-winners-v1',json.dumps([
    recipe.source_id,recipe.NAME,recipe.CATEGORY,recipe.CATEGORY_ALIASES,
    recipe.URL,OFFICIAL_AWARDS_API_URL,OFFICIAL_PAST_WINNERS_API_URL,GOODREADS_URL]),cached_parsed,incremental_update)
  notes=[];units={};phase={}
  def previous(key):
    unit=cache.old_units.get(key) or {}
    try:
      return {'entries':restore_source_rows(cache.previous(key),unit.get('metadata') or {}),
        'notes':(unit.get('metadata') or {}).get('notes') or []}
    except (ValueError,TypeError):return {'entries':[],'notes':[]}
  def failed(key,label,error):
    note=f'Splatterpunk {label} failed: {error}'
    notes.append(note)
    if log is not None:log(note)
    return previous(key)
  try:
    current=recipe.fetch_parse_current(parser,fetch_url,before_fetch,after_fetch,before_parse)
    phase=current.pop('current_state');current_complete=True
  except (ImportCancelledError,CamoufoxRequiredError):raise
  except Exception as err:
    current=failed('current','official current nominees',err);current_complete=False
  units['current']=(current,phase.get('revision'),current_complete)

  history=previous('winners');old=cache.old_units.get('winners') or {}
  revision=[phase.get('revision'),phase.get('year')]
  year=datetime.datetime.now().year
  latest=max((int(row['award_year']) for row in history['entries']),default=0)
  complete=False
  if (current_complete and phase.get('intake') is True and phase.get('year')==year+1 and
      latest==year and old.get('complete') is True and old.get('revision')==revision):
    try:parser.validate_official_winner_result(history);complete=True
    except ValueError:pass
  if not complete:
    try:
      history=recipe.fetch_parse_official_winners(parser,fetch_url,before_fetch,after_fetch,before_parse)
      complete=True
    except (ImportCancelledError,CamoufoxRequiredError):raise
    except Exception as err:history=failed('winners','official past winners',err)
  units['winners']=(history,revision,complete)

  try:
    pages=recipe.fetch_parse_goodreads_pages(parser,fetch_url,before_fetch,after_fetch,before_parse,log,progress)
    supplement={'entries':[entry for page in pages for entry in page.get('entries',[])],
      'notes':[note for page in pages for note in page.get('notes',[])]}
    supplement_complete=True
  except (ImportCancelledError,CamoufoxRequiredError):raise
  except Exception as err:
    supplement=failed('goodreads','Goodreads historical supplement',err);supplement_complete=False
  units['goodreads']=(supplement,None,supplement_complete)
  combined=parser.combine_results(recipe.NAME,recipe.URL,current,history,supplement,{'entries':[],'notes':notes})
  for key,(parsed,revision,complete) in units.items():
    projected,metadata=project_source_rows(parsed['entries'],combined['entries'],parser.row_key)
    metadata['notes']=parsed.get('notes',[])
    cache.put(key,projected,revision=revision,complete=complete,metadata=metadata)
  combined['incremental_state']=cache.state(combined['entries'])
  combined['incremental_state']['discovery']={'refresh_units':['current','goodreads']}
  return combined
