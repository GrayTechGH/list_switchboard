#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

try:
  from calibre_plugins.list_switchboard.parser.ladies_of_horror_fiction import (
    FILE770_2021_WINNERS_URL,
    GOODREADS_URL,
  )
except ImportError:
  from parser.ladies_of_horror_fiction import (
    FILE770_2021_WINNERS_URL,
    GOODREADS_URL,
  )

from .generic import (
  CATEGORY_HORROR_DARK_FICTION,
  UrlFetcherError,
  UrlFetcherGeneric,
)


class UrlFetcherLadiesOfHorrorFiction(UrlFetcherGeneric):

  URL = GOODREADS_URL
  FETCH_URLS = ()
  FILTER_CATEGORIES = (CATEGORY_HORROR_DARK_FICTION,)
  order = 94
  options = {'match_series': False}
  AWARD_NAME = 'Ladies of Horror Fiction Award'
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.ladies_of_horror_fiction import (
        LadiesOfHorrorFictionParser,
      )
    except ImportError:
      from parser.ladies_of_horror_fiction import LadiesOfHorrorFictionParser
    return LadiesOfHorrorFictionParser()

  def source_choices(self):
    return ({'label': 'Automatic', 'value': 'automatic'},)

  def fetch_and_parse(
      self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
      before_fetch=None, after_fetch=None, before_parse=None,
      force_fallback_level=0, disable_fallbacks=False, source_choice=None,
      cached_parsed=None, incremental_update=False):
    if source_choice not in (None, 'automatic'):
      raise UrlFetcherError(
        f'No source fallback attempt exists for selected source {source_choice}.')

    fetcher_fetch_url = lambda target_url: self.fetch_url(fetch_url, target_url)
    parser = self.parser()
    parsed_results = []
    notes = []

    try:
      parsed_results.extend(self.fetch_parse_goodreads_pages(
        parser, fetcher_fetch_url, before_fetch, after_fetch, before_parse, log))
    except Exception as err:
      note = f'Ladies of Horror Fiction Goodreads primary source failed: {err}'
      notes.append(note)
      if log is not None:
        log(note)

    try:
      parsed_results.append(self.fetch_parse_file770_winners(
        parser, fetcher_fetch_url, before_fetch, after_fetch, before_parse))
    except Exception as err:
      note = f'Ladies of Horror Fiction File 770 winner supplement failed: {err}'
      notes.append(note)
      if log is not None:
        log(note)

    combined = parser.combine_results(
      self.NAME,
      self.URL,
      *parsed_results,
      {'entries': (), 'notes': notes})
    if not combined.get('entries'):
      raise UrlFetcherError('Could not fetch or parse the imported list.')
    combined['match_series'] = self.options.get('match_series', True)
    combined.setdefault('source_url', self.URL)
    return combined

  def fetch_parse_goodreads_pages(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse, log):
    first_page = self.fetch_page(fetch_url, GOODREADS_URL, before_fetch, after_fetch)
    self.before_parse(before_parse, GOODREADS_URL)
    urls = list(parser.discover_goodreads_page_urls(first_page, GOODREADS_URL))
    parsed_results = [
      parser.parse_goodreads(
        first_page,
        GOODREADS_URL,
        self.NAME,
        self.CATEGORY,
        self.CATEGORY_ALIASES)
    ]
    for url in urls[1:8]:
      try:
        html = self.fetch_page(fetch_url, url, before_fetch, after_fetch)
        self.before_parse(before_parse, url)
        parsed_results.append(parser.parse_goodreads(
          html,
          url,
          self.NAME,
          self.CATEGORY,
          self.CATEGORY_ALIASES))
      except Exception as err:
        note = f'Ladies of Horror Fiction Goodreads page failed: {url}: {err}'
        parsed_results.append({'entries': (), 'notes': [note]})
        if log is not None:
          log(note)
    return parsed_results

  def fetch_parse_file770_winners(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse):
    html = self.fetch_page(
      fetch_url, FILE770_2021_WINNERS_URL, before_fetch, after_fetch)
    self.before_parse(before_parse, FILE770_2021_WINNERS_URL)
    return parser.parse_file770_winners(
      html,
      FILE770_2021_WINNERS_URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES)

  def fetch_page(self, fetch_url, url, before_fetch, after_fetch):
    if before_fetch is not None:
      before_fetch(url)
    html = fetch_url(url)
    if after_fetch is not None:
      after_fetch(url, html)
    return html

  def before_parse(self, before_parse, url):
    if before_parse is not None:
      before_parse(url)

  def parse(self, html, **_kwargs):
    return self.parser().parse_goodreads(
      html,
      GOODREADS_URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES)


class UrlFetcherLadiesOfHorrorFictionNovel(UrlFetcherLadiesOfHorrorFiction):
  source_id = 'ladies_of_horror_fiction_novel'
  NAME = 'Ladies of Horror Fiction - Novel'
  CATEGORY = 'Novel'
  CATEGORY_ALIASES = ('novel', 'best novel')


class UrlFetcherLadiesOfHorrorFictionNovella(UrlFetcherLadiesOfHorrorFiction):
  source_id = 'ladies_of_horror_fiction_novella'
  NAME = 'Ladies of Horror Fiction - Novella'
  CATEGORY = 'Novella'
  CATEGORY_ALIASES = ('novella', 'best novella')


class UrlFetcherLadiesOfHorrorFictionCollection(UrlFetcherLadiesOfHorrorFiction):
  source_id = 'ladies_of_horror_fiction_collection'
  NAME = 'Ladies of Horror Fiction - Collection'
  CATEGORY = 'Collection'
  CATEGORY_ALIASES = ('collection', 'best collection')


class UrlFetcherLadiesOfHorrorFictionDebut(UrlFetcherLadiesOfHorrorFiction):
  source_id = 'ladies_of_horror_fiction_debut'
  NAME = 'Ladies of Horror Fiction - Debut'
  CATEGORY = 'Debut'
  CATEGORY_ALIASES = ('debut', 'best debut')


class UrlFetcherLadiesOfHorrorFictionYoungAdult(UrlFetcherLadiesOfHorrorFiction):
  source_id = 'ladies_of_horror_fiction_young_adult'
  NAME = 'Ladies of Horror Fiction - Young Adult'
  CATEGORY = 'Young Adult'
  CATEGORY_ALIASES = ('young adult', 'best young adult')


class UrlFetcherLadiesOfHorrorFictionMiddleGrade(UrlFetcherLadiesOfHorrorFiction):
  source_id = 'ladies_of_horror_fiction_middle_grade'
  NAME = 'Ladies of Horror Fiction - Middle Grade'
  CATEGORY = 'Middle Grade'
  CATEGORY_ALIASES = ('middle grade', 'best middle grade')


class UrlFetcherLadiesOfHorrorFictionPoetryCollection(
    UrlFetcherLadiesOfHorrorFiction):
  source_id = 'ladies_of_horror_fiction_poetry_collection'
  NAME = 'Ladies of Horror Fiction - Poetry Collection'
  CATEGORY = 'Poetry Collection'
  CATEGORY_ALIASES = (
    'poetry',
    'best poetry',
    'poetry collection',
    'best poetry collection',
  )


class UrlFetcherLadiesOfHorrorFictionGraphicNovel(UrlFetcherLadiesOfHorrorFiction):
  source_id = 'ladies_of_horror_fiction_graphic_novel'
  NAME = 'Ladies of Horror Fiction - Graphic Novel'
  CATEGORY = 'Graphic Novel'
  CATEGORY_ALIASES = ('graphic novel', 'best graphic novel')
