#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

import re
import json
import datetime
from urllib.parse import urljoin, urlparse

from lxml import html as lxml_html

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherError,
  UrlFetcherGeneric,
  parsed_source,
)

try:
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
  from calibre_plugins.list_switchboard.parser.incremental import ParsedUnitCache,project_source_rows,restore_source_rows
  from calibre_plugins.list_switchboard.errors import ImportCancelledError,CamoufoxRequiredError
except ImportError:
  from parser.generic import position_sort_key
  from parser.incremental import ParsedUnitCache,project_source_rows,restore_source_rows
  from errors import ImportCancelledError,CamoufoxRequiredError


GOVERNOR_GENERAL_ARCHIVE_URL = 'https://ggbooks.ca/past-winners-and-finalists'
GOVERNOR_GENERAL_2025_PRESS_URL = (
  'https://canadacouncil.ca/press/2025/11/2025-ggbooks-winners-revealed'
)
GOVERNOR_GENERAL_2025_WIKIPEDIA_URL = (
  'https://en.wikipedia.org/wiki/2025_Governor_General%27s_Awards'
)
DEFAULT_JSON_URL = (
  'https://ggbooks.ca/Areas/GGBooks/json/ggbooks-data-compressed.json'
)


class UrlFetcherGovernorGeneralAwards(UrlFetcherGeneric):

  URL = GOVERNOR_GENERAL_ARCHIVE_URL
  MAX_RESPONSE_BYTES = 32 * 1024 * 1024
  FETCH_URLS = (GOVERNOR_GENERAL_ARCHIVE_URL,)
  order = 183
  options = {'match_series': False}
  AWARD_NAME = "Governor General's Literary Award"
  CATEGORY = ''
  CATEGORY_KEYS = ()
  LANGUAGE = 'en'
  SUPPLEMENT_YEAR = '2025'
  SUPPLEMENT_ENABLED = True

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.governor_general import (
        GovernorGeneralAwardsParser,
      )
    except ImportError:
      from parser.governor_general import GovernorGeneralAwardsParser
    return GovernorGeneralAwardsParser(
      self.CATEGORY,
      self.CATEGORY_KEYS,
      self.LANGUAGE,
      self.AWARD_NAME)

  def create_supplement_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.governor_general import (
        GovernorGeneralSupplementParser,
      )
    except ImportError:
      from parser.governor_general import GovernorGeneralSupplementParser
    return GovernorGeneralSupplementParser(
      self.CATEGORY,
      self.CATEGORY_KEYS,
      self.LANGUAGE,
      self.AWARD_NAME)

  def source_choices(self):
    return ({'label': 'Automatic', 'value': 'automatic'},)

  def fetch_and_parse(
      self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
      before_fetch=None, after_fetch=None, before_parse=None,
      force_fallback_level=0, disable_fallbacks=False, source_choice=None,
      cached_parsed=None,incremental_update=False):
    if source_choice not in (None, 'automatic'):
      raise UrlFetcherError(
        f'No source fallback attempt exists for selected source {source_choice}.')
    if force_fallback_level:
      raise UrlFetcherError(
        f'No source fallback attempt exists for forced level {force_fallback_level}.')
    cache=ParsedUnitCache('ggbooks-resolved-endpoint-v1',json.dumps([
      self.URL,self.source_id,self.CATEGORY,self.CATEGORY_KEYS,self.LANGUAGE,
      self.SUPPLEMENT_ENABLED,self.SUPPLEMENT_YEAR,GOVERNOR_GENERAL_2025_WIKIPEDIA_URL,
      GOVERNOR_GENERAL_2025_PRESS_URL]),cached_parsed,incremental_update)
    if before_fetch is not None:
      before_fetch(self.URL)
    archive_html = self.fetch_url(fetch_url, self.URL)
    if after_fetch is not None:
      after_fetch(self.URL, archive_html)
    module_url=self.archive_component_url(archive_html,self.URL)
    resolved=cache.old_discovery
    json_url=resolved.get('json_url')
    reuse_endpoint=(resolved.get('contract')==1 and module_url==resolved.get('module_url') and
      bool(re.search(r'/Archives\d{8}\.js$',module_url)) and self.valid_json_url(json_url))
    if not reuse_endpoint:
      json_url = self.json_url_from_archive(archive_html, self.URL, fetch_url)

    def read_json(url):
      if before_fetch is not None:
        before_fetch(url)
      data=self.fetch_url(fetch_url,url)
      if after_fetch is not None:
        after_fetch(url,data)
      if before_parse is not None:
        before_parse(url)
      parsed=self.parser().parse(data,url,self.NAME,self.CATEGORY)
      if not parsed.get('entries'):
        raise ValueError('Official GGBooks JSON had no usable category entries.')
      return parsed

    try:
      parsed=read_json(json_url)
    except (ImportCancelledError,CamoufoxRequiredError):
      raise
    except Exception:
      if not reuse_endpoint:
        raise
      try:
        json_url=self.json_url_from_archive(archive_html,self.URL,fetch_url)
        parsed=read_json(json_url)
      except (ImportCancelledError,CamoufoxRequiredError):
        raise
      except Exception as err:
        if not cache.old_entries:
          raise
        for key in cache.old_units:
          cache.failed(key)
        state=cache.state(cache.old_entries)
        state['discovery']=cache.old_discovery
        return {'name':self.NAME,'source':cached_parsed.get('source') or {},
          'entries':cache.old_entries,'match_series':False,'incremental_state':state,
          'notes':['Official GGBooks JSON refresh failed; retained cached entries: '+str(err)]}
    notes = list(parsed.get('notes', ()))
    supplement=None
    supplement_key='supplement-'+self.SUPPLEMENT_YEAR
    if (
        self.SUPPLEMENT_ENABLED
        and not disable_fallbacks
        and not self.has_year(parsed, self.SUPPLEMENT_YEAR)):
      old=cache.old_units.get(supplement_key) or {}
      if old.get('complete') is True and int(self.SUPPLEMENT_YEAR)<datetime.datetime.now().year:
        try:
          rows=restore_source_rows(cache.previous(supplement_key),old.get('metadata') or {})
          if rows and all(r.get('award_year')==self.SUPPLEMENT_YEAR for r in rows):
            supplement={'entries':rows,'notes':[]}
        except (ValueError,TypeError):
          pass
      if supplement is None:
        supplement = self.fetch_supplement(fetch_url, before_fetch, after_fetch, before_parse)
        if supplement.get('notes'):
          try:
            retained=restore_source_rows(cache.previous(supplement_key),old.get('metadata') or {})
            if retained:
              supplement['entries']=retained
          except (ValueError,TypeError):
            pass
      notes.extend(supplement.get('notes') or [])
      if supplement.get('entries'):
        parsed['entries'] = self.merge_entries(parsed.get('entries', ()), supplement['entries'])
        notes.append(
          'Added %s Governor General supplement entries because official GGBooks JSON lacked %s.'
          % (len(supplement['entries']), self.SUPPLEMENT_YEAR))
    parsed['notes'] = notes
    parsed['source'] = parsed_source(self.NAME, json_url, self.source_id)
    parsed.setdefault('match_series', self.options.get('match_series', True))
    # Every update still downloads the complete current JSON. Annual units
    # describe real parsed entries for recovery; only bootstrap mapping and a
    # complete closed supplement may avoid requests.
    for year in {row['award_year'] for row in parsed['entries']}:
      cache.put('official-'+year,[r for r in parsed['entries'] if r['award_year']==year])
    if supplement is not None:
      rows,metadata=project_source_rows(supplement.get('entries') or [],parsed['entries'],
        lambda r:(r['award_year'],r['title'],tuple(r['authors'])))
      complete=bool(rows) and not supplement.get('notes') and any(r['result']=='winner' for r in rows)
      cache.put(supplement_key,rows,complete=complete,metadata=metadata)
    parsed['incremental_state']=cache.state(parsed['entries'])
    parsed['incremental_state']['discovery']={'module_url':module_url,'json_url':json_url,'contract':1}
    return parsed

  def valid_json_url(self,url):
    if not isinstance(url,str):
      return False
    parsed=urlparse(url)
    return parsed.scheme=='https' and parsed.netloc==urlparse(self.URL).netloc and bool(
      re.fullmatch(r'/Areas/GGBooks/json/[A-Za-z0-9_-]+\.json',parsed.path)) and not parsed.query and not parsed.fragment

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME, self.CATEGORY)

  def json_url_from_archive(self, html, base_url, fetch_url=None):
    module_url = self.archive_component_url(html, base_url)
    if module_url and fetch_url is not None:
      script = self.fetch_url(fetch_url, module_url)
      json_url = self.json_url_from_component(script, module_url)
      if json_url:
        return json_url
    json_url = self.json_url_from_component(html, base_url)
    return json_url or DEFAULT_JSON_URL

  def archive_component_url(self, html, base_url):
    root=lxml_html.fromstring(html or '<html></html>')
    matches=[]
    for value in root.xpath('//*[@data-ux-module]/@data-ux-module|//script[@src]/@src'):
      match=re.search(r'Components/(Archives[0-9A-Za-z_-]*)(?:\.js)?$',value)
      if match:
        matches.append(match.group(1))
    if not matches:
      return ''
    return urljoin(base_url, '/Areas/GGBooks/js/Components/%s.js' % matches[-1])

  def json_url_from_component(self, script, base_url):
    match = re.search(r'\$\.getJSON\(\s*[\'"]([^\'"]+\.json)[\'"]', script or '')
    if match is None:
      return ''
    return urljoin(base_url, match.group(1))

  def fetch_supplement(self, fetch_url, before_fetch, after_fetch, before_parse):
    wikipedia_html = ''
    press_html = ''
    notes=[]
    for url, label in (
        (GOVERNOR_GENERAL_2025_WIKIPEDIA_URL, 'Wikipedia'),
        (GOVERNOR_GENERAL_2025_PRESS_URL, 'Canada Council press release')):
      if before_fetch is not None:
        before_fetch(url)
      try:
        html = self.fetch_url(fetch_url, url)
      except (ImportCancelledError,CamoufoxRequiredError):
        raise
      except Exception as err:
        html = ''
        notes.append('Governor General supplement page failed for %s: %s'%(url,err))
      if after_fetch is not None:
        after_fetch(url, html)
      if label == 'Wikipedia':
        wikipedia_html = html
      else:
        press_html = html
    if before_parse is not None:
      before_parse(GOVERNOR_GENERAL_2025_WIKIPEDIA_URL)
    parsed=self.create_supplement_parser().parse(
      wikipedia_html,
      GOVERNOR_GENERAL_2025_WIKIPEDIA_URL,
      self.NAME,
      self.CATEGORY,
      year=self.SUPPLEMENT_YEAR,
      winner_html=press_html)
    parsed['notes']=list(parsed.get('notes') or [])+notes
    return parsed

  def has_year(self, parsed, year):
    return any(entry.get('award_year') == str(year) for entry in parsed.get('entries', ()))

  def merge_entries(self, official_entries, supplement_entries):
    by_key = {}
    for entry in tuple(official_entries) + tuple(supplement_entries):
      key = (
        entry.get('award_year'),
        entry.get('category', '').casefold(),
        entry.get('title', '').casefold(),
        tuple(str(author or '').casefold() for author in (entry.get('authors') or ())),
      )
      by_key[key] = entry
    return sorted(
      by_key.values(),
      key=lambda item: position_sort_key(item.get('position', '')))


class UrlFetcherGovernorGeneralEnglishFiction(UrlFetcherGovernorGeneralAwards):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'governor_general_literary_award_english_fiction'
  NAME = "Governor General's Literary Award - English Fiction"
  CATEGORY = 'English Fiction'
  CATEGORY_KEYS = ('fiction',)
  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )


class UrlFetcherGovernorGeneralEnglishNonfiction(UrlFetcherGovernorGeneralAwards):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'governor_general_literary_award_english_nonfiction'
  NAME = "Governor General's Literary Award - English Non-fiction"
  CATEGORY = 'English Non-fiction'
  CATEGORY_KEYS = ('nonFiction',)
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )


class UrlFetcherGovernorGeneralEnglishYoungPeoplesText(UrlFetcherGovernorGeneralAwards):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'governor_general_literary_award_english_young_peoples_text'
  NAME = (
    "Governor General's Literary Award - English Young People's Literature - Text"
  )
  CATEGORY = "English Young People's Literature - Text"
  CATEGORY_KEYS = ('youngPeoplesLiteratureText', 'juvenile')
  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )


class UrlFetcherGovernorGeneralEnglishYoungPeoplesIllustratedBooks(
    UrlFetcherGovernorGeneralAwards):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = (
    'governor_general_literary_award_english_young_peoples_illustrated_books'
  )
  NAME = (
    "Governor General's Literary Award - English Young People's Literature - "
    'Illustrated Books'
  )
  CATEGORY = "English Young People's Literature - Illustrated Books"
  CATEGORY_KEYS = ('youngPeoplesLiteratureIllustratedBooks',)
  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )


class UrlFetcherGovernorGeneralFrenchYoungPeoplesText(UrlFetcherGovernorGeneralAwards):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'governor_general_literary_award_french_young_peoples_text'
  NAME = (
    "Governor General's Literary Award - French Young People's Literature - Text"
  )
  CATEGORY = "French Young People's Literature - Text"
  CATEGORY_KEYS = ('youngPeoplesLiteratureText',)
  LANGUAGE = 'fr'
  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )


class UrlFetcherGovernorGeneralFrenchYoungPeoplesIllustratedBooks(
    UrlFetcherGovernorGeneralAwards):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = (
    'governor_general_literary_award_french_young_peoples_illustrated_books'
  )
  NAME = (
    "Governor General's Literary Award - French Young People's Literature - "
    'Illustrated Books'
  )
  CATEGORY = "French Young People's Literature - Illustrated Books"
  CATEGORY_KEYS = ('youngPeoplesLiteratureIllustratedBooks',)
  LANGUAGE = 'fr'
  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
