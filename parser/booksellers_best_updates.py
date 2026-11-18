"""Reuse parsed GDRW captures only after refreshing all three archive indexes.

Capture identity includes its timestamp, original URL and CDX digest. Original
source rows remain reversible after winner promotion and cross-capture dedupe.
An unavailable index retains its own former discoveries pending retry; a healthy
index can remove captures. Empty branded rules/navigation captures are valid,
but a result page whose roster no longer parses must remain pending.
"""

import json
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError,CamoufoxRequiredError
  from calibre_plugins.list_switchboard.parser.base import author_list
  from calibre_plugins.list_switchboard.parser.award_base import normalize_heading
  from calibre_plugins.list_switchboard.parser.booksellers_best import BOOKSELLERS_BEST_CDX_URLS
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
  from calibre_plugins.list_switchboard.parser.incremental import ParsedUnitCache,project_source_rows,restore_source_rows
except ImportError:
  from errors import ImportCancelledError,CamoufoxRequiredError
  from .base import author_list
  from .award_base import normalize_heading
  from .booksellers_best import BOOKSELLERS_BEST_CDX_URLS
  from .generic import position_sort_key
  from .incremental import ParsedUnitCache,project_source_rows,restore_source_rows


def capture_index(parser,source):
  data=json.loads(parser.source_text(source))
  columns=['timestamp','original','statuscode','mimetype','digest']
  if not isinstance(data,list) or not data or data[0]!=columns:
    raise ValueError('GDRW archive index has an incompatible CDX schema.')
  captures={}
  for row in data[1:]:
    if not isinstance(row,list) or len(row)!=len(columns):
      raise ValueError('GDRW archive index contains a malformed capture.')
    stamp,original,status,mime,digest=row
    if not all(isinstance(value,str) for value in row):
      raise ValueError('GDRW archive index contains invalid capture fields.')
    target=urlsplit(original)
    if (not re.fullmatch(r'\d{14}',stamp) or target.scheme not in ('http','https') or
        target.hostname not in ('gdrwa.org','www.gdrwa.org') or target.username or target.password or
        status!='200'):
      raise ValueError('GDRW archive index contains an unrelated or unsuccessful capture.')
    if not (target.path.casefold()=='/contests.html' or target.path.casefold().startswith(('/bba','/winners'))):
      raise ValueError('GDRW archive index left the configured award paths.')
    if parser.skip_source_url(original):continue
    # Wildcard CDX responses also contain PDF/Word entry and judging forms.
    # Exclude recognized administrative URLs before requiring a roster's HTML.
    if mime not in ('text/html','application/xhtml+xml'):
      raise ValueError('GDRW result capture is not an HTML page.')
    url=f'https://web.archive.org/web/{stamp}id_/{original}'
    revision=[stamp,original,digest]
    if url in captures and captures[url]!=revision:
      raise ValueError('GDRW archive index gives conflicting capture digests.')
    captures[url]=revision
  return captures


def validated_rows(parser,source,url,notes):
  soup=BeautifulSoup(parser.source_text(source),'html.parser')
  text=normalize_heading(soup.get_text(' ',strip=True))
  if (not soup.find(['html','body']) or not soup.find(['p','h1','h2','h3','h4','table']) or
      any(term in text for term in ('verify you are human','access denied','just a moment','rate limit exceeded')) or
      not any(term in text for term in ('gdrwa','greater detroit romance','booksellers best','bookseller s best','bba'))):
    raise ValueError('GDRW capture did not expose a branded official page.')
  rows=parser.parse_page_rows(source,url,notes)
  for section in parser.award_sections(soup):
    section_text=normalize_heading(section.get_text(' ',strip=True))
    section_rows=parser.parse_section_rows(section,url,[])
    roster_heading=any(re.search(r'\b(?:finalists?|winners?)\b',normalize_heading(node.get_text(' ',strip=True)))
      and len(node.get_text(' ',strip=True))<150 for node in section.find_all(['h1','h2','h3','h4','h5']))
    if (parser.result_for_page(section,url) is not None and not section_rows
        and not parser.known_image_roster(section)) and (
        roster_heading or not parser.is_entry_or_rules_page(section_text)):
      raise ValueError('GDRW result capture did not expose a usable roster.')
  return rows


def fetch_booksellers_best(parser,fetch_url,base_url,name,cached_parsed=None,
    incremental_update=False,initial_source=None,progress=None):
  indexes=tuple(dict.fromkeys((base_url,)+BOOKSELLERS_BEST_CDX_URLS))
  cache=ParsedUnitCache('gdrw-immutable-captures-v4',json.dumps([
    base_url,name,type(parser).__name__,indexes]),cached_parsed,incremental_update)
  notes=[];discoveries={};pending=[];captures={};failed_urls=set()
  old_discoveries=cache.old_discovery.get('indexes',{})
  if not isinstance(old_discoveries,dict):old_discoveries={}
  for index_url in indexes:
    try:
      source=initial_source if index_url==base_url and initial_source is not None else fetch_url(index_url)
      found=capture_index(parser,source)
      discoveries[index_url]=list(found)
    except (ImportCancelledError,CamoufoxRequiredError):raise
    except Exception as err:
      notes.append(f'Official GDRW Wayback CDX page could not be fetched: {index_url}: {err}')
      pending.append(index_url);found={}
      for url in old_discoveries.get(index_url,[]):
        old=cache.old_units.get(url)
        if old:found[url]=old.get('revision')
      discoveries[index_url]=list(found);failed_urls.update(found)
    for url,revision in found.items():
      if url not in captures:captures[url]=revision
      elif captures[url]!=revision:failed_urls.add(url)
  units={};all_rows=[]
  for index,(url,revision) in enumerate(captures.items()):
    old=cache.old_units.get(url) or {};metadata=old.get('metadata') or {}
    try:previous=restore_source_rows(cache.previous(url),metadata)
    except (ValueError,TypeError):previous=[];old={}
    complete=False;rows=previous;page_notes=[]
    if url in failed_urls:
      page_notes=list(metadata.get('notes',[]))
    elif old.get('complete') is True and old.get('revision')==revision and revision[-1] not in ('','-'):
      rows=previous;page_notes=list(metadata.get('notes',[]));complete=True
    else:
      try:
        if progress is not None:progress(index,len(captures),f'Fetching archived GDRW page {index+1} of {len(captures)}')
        rows=validated_rows(parser,fetch_url(url),url,page_notes);complete=True
      except (ImportCancelledError,CamoufoxRequiredError):raise
      except Exception as err:
        notes.append(f'Official GDRW archived page could not be fetched: {url}: {err}')
        page_notes=list(metadata.get('notes',[]))
    notes.extend(page_notes);all_rows.extend(rows)
    units[url]=(rows,revision,complete,page_notes)
  rows=parser.dedupe_rows(parser.with_source_order(all_rows))
  entries=sorted(parser.entries_from_rows(rows),key=lambda item:position_sort_key(item.get('position','')))
  def identity(row):
    return (str(row['award_year']),normalize_heading(row['category']),normalize_heading(row['title']),
      tuple(normalize_heading(a) for a in author_list(row.get('authors',row.get('author')))))
  for url,(source_rows,revision,complete,page_notes) in units.items():
    projected,metadata=project_source_rows(source_rows,entries,identity)
    metadata['notes']=page_notes
    cache.put(url,projected,revision=revision,complete=complete,metadata=metadata)
  for index_url in indexes:
    cache.put(index_url,[],revision=index_url,complete=index_url not in pending,
      metadata={'kind':'cdx-discovery'})
  result=parser.result_from_rows(rows,base_url,name,notes)
  result['incremental_state']=cache.state(result['entries'])
  result['incremental_state']['discovery']={'indexes':discoveries,'pending_indexes':pending}
  return result
