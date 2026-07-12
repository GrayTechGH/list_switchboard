#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

import re
from urllib.parse import urljoin

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
except ImportError:
  from parser.generic import position_sort_key


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
      force_fallback_level=0, disable_fallbacks=False, source_choice=None):
    if source_choice not in (None, 'automatic'):
      raise UrlFetcherError(
        f'No source fallback attempt exists for selected source {source_choice}.')
    if force_fallback_level:
      raise UrlFetcherError(
        f'No source fallback attempt exists for forced level {force_fallback_level}.')
    if before_fetch is not None:
      before_fetch(self.URL)
    archive_html = self.fetch_url(fetch_url, self.URL)
    if after_fetch is not None:
      after_fetch(self.URL, archive_html)
    json_url = self.json_url_from_archive(archive_html, self.URL, fetch_url)
    if before_fetch is not None:
      before_fetch(json_url)
    json_data = self.fetch_url(fetch_url, json_url)
    if after_fetch is not None:
      after_fetch(json_url, json_data)
    if before_parse is not None:
      before_parse(json_url)
    parsed = self.parser().parse(json_data, json_url, self.NAME, self.CATEGORY)
    notes = list(parsed.get('notes', ()))
    if (
        self.SUPPLEMENT_ENABLED
        and not disable_fallbacks
        and not self.has_year(parsed, self.SUPPLEMENT_YEAR)):
      supplement = self.fetch_supplement(fetch_url, before_fetch, after_fetch, before_parse)
      if supplement.get('entries'):
        parsed['entries'] = self.merge_entries(parsed.get('entries', ()), supplement['entries'])
        notes.append(
          'Added %s Governor General supplement entries because official GGBooks JSON lacked %s.'
          % (len(supplement['entries']), self.SUPPLEMENT_YEAR))
    parsed['notes'] = notes
    parsed['source'] = parsed_source(self.NAME, json_url, self.source_id)
    parsed.setdefault('match_series', self.options.get('match_series', True))
    return parsed

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
    matches = re.findall(r'Components/(Archives[0-9A-Za-z_-]*)', html or '')
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
    for url, label in (
        (GOVERNOR_GENERAL_2025_WIKIPEDIA_URL, 'Wikipedia'),
        (GOVERNOR_GENERAL_2025_PRESS_URL, 'Canada Council press release')):
      if before_fetch is not None:
        before_fetch(url)
      try:
        html = self.fetch_url(fetch_url, url)
      except Exception:
        html = ''
      if after_fetch is not None:
        after_fetch(url, html)
      if label == 'Wikipedia':
        wikipedia_html = html
      else:
        press_html = html
    if before_parse is not None:
      before_parse(GOVERNOR_GENERAL_2025_WIKIPEDIA_URL)
    return self.create_supplement_parser().parse(
      wikipedia_html,
      GOVERNOR_GENERAL_2025_WIKIPEDIA_URL,
      self.NAME,
      self.CATEGORY,
      year=self.SUPPLEMENT_YEAR,
      winner_html=press_html)

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
  source_id = 'governor_general_literary_award_english_fiction'
  NAME = "Governor General's Literary Award - English Fiction"
  CATEGORY = 'English Fiction'
  CATEGORY_KEYS = ('fiction',)
  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )


class UrlFetcherGovernorGeneralEnglishNonfiction(UrlFetcherGovernorGeneralAwards):
  source_id = 'governor_general_literary_award_english_nonfiction'
  NAME = "Governor General's Literary Award - English Non-fiction"
  CATEGORY = 'English Non-fiction'
  CATEGORY_KEYS = ('nonFiction',)
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )


class UrlFetcherGovernorGeneralEnglishYoungPeoplesText(UrlFetcherGovernorGeneralAwards):
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
