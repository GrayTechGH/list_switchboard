#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

try:
  from calibre_plugins.list_switchboard.parser.ladies_of_horror_fiction import (
    FILE770_2021_WINNERS_URL,
    LOHFPaginationError,
    GOODREADS_URL,
  )
except ImportError:
  from parser.ladies_of_horror_fiction import (
    FILE770_2021_WINNERS_URL,
    LOHFPaginationError,
    GOODREADS_URL,
  )

from .ladies_of_horror_fiction_transport import LadiesOfHorrorFictionFetchPolicy

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError
except ImportError:
  from errors import ImportCancelledError

from .generic import (
  CATEGORY_HORROR_DARK_FICTION,
  GoodreadsFetchPolicyMixin,
  UrlFetcherError,
  UrlFetcherGeneric,
  parsed_source,
)


class UrlFetcherLadiesOfHorrorFiction(
    GoodreadsFetchPolicyMixin, UrlFetcherGeneric):
  """Own per-import Goodreads recovery and the separate File 770 supplement.

  Invariants:
  - The operation policy and progress callback are cleared on every exit.
  - Transport recovery cannot replace the final category/year coverage gate.
  - Cancellation bypasses source/page warning handlers, including File 770.
  """

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
    self._lohf_progress = progress
    self._lohf_fetch_policy = LadiesOfHorrorFictionFetchPolicy(
      fetch_url, lambda url: self.legacy_fetch_url(fetch_url, url), self.parser(),
      log=log, progress=progress)
    try:
      return self._fetch_and_parse(
        fetch_url, sleep, fetch_error, log, progress, before_fetch, after_fetch,
        before_parse, force_fallback_level, disable_fallbacks, source_choice,
        cached_parsed, incremental_update)
    finally:
      self._lohf_fetch_policy = None
      self._lohf_progress = None

  def fetch_url(self, fetch_url, url):
    policy = getattr(self, '_lohf_fetch_policy', None)
    if policy is not None and url.startswith(GOODREADS_URL):
      return policy.fetch(url)
    return self.legacy_fetch_url(fetch_url, url)

  def legacy_fetch_url(self, fetch_url, url):
    retries = self.timeout_retries(url)
    for retry in range(retries + 1):
      try:
        return self.fetch_url_once(fetch_url, url)
      except (ImportCancelledError, LOHFPaginationError):
        raise
      except Exception as err:
        if retry >= retries or not self.is_timeout_error(err):
          raise
        progress = getattr(self, '_lohf_progress', None)
        if progress is not None:
          progress(0, 1, f'LOHF Goodreads timed out; retry {retry + 1} of {retries}: {url}')

  def _fetch_and_parse(
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
        parser, fetcher_fetch_url, before_fetch, after_fetch, before_parse, log, progress))
    except (ImportCancelledError, LOHFPaginationError):
      raise
    except Exception as err:
      note = f'Ladies of Horror Fiction Goodreads primary source failed: {err}'
      notes.append(note)
      if log is not None:
        log(note)

    try:
      parsed_results.append(self.fetch_parse_file770_winners(
        parser, fetcher_fetch_url, before_fetch, after_fetch, before_parse))
    except (ImportCancelledError, LOHFPaginationError):
      raise
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
    try:
      try:
        from calibre_plugins.list_switchboard.parser.ladies_of_horror_fiction import (
          require_complete_lohf_result,
        )
      except ImportError:
        from parser.ladies_of_horror_fiction import require_complete_lohf_result
      combined = require_complete_lohf_result(
        combined, self.CATEGORY, 'Ladies of Horror Fiction sources')
    except ValueError as err:
      raise UrlFetcherError(str(err)) from err
    combined['match_series'] = self.options.get('match_series', True)
    combined.setdefault('source', parsed_source(self.NAME, self.URL, self.source_id))
    return combined

  def fetch_parse_goodreads_pages(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse, log,
      progress=None):
    urls = [GOODREADS_URL]
    parsed_results = []
    index = 0
    while index < len(urls):
      url = urls[index]
      try:
        if progress is not None:
          progress(index, len(urls), f'Fetching LOHF Goodreads page {index + 1} of {len(urls)}')
        html = self.fetch_page(fetch_url, url, before_fetch, after_fetch)
        # Discover from every page; the first page need not expose every link.
        for target in parser.discover_goodreads_page_urls(html, url):
          if target not in urls:
            urls.append(target)
        self.before_parse(before_parse, url)
        if progress is not None:
          progress(index, len(urls), f'Parsing LOHF Goodreads page {index + 1} of {len(urls)}')
        parsed_results.append(parser.parse_goodreads(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES))
      except (ImportCancelledError, LOHFPaginationError):
        raise
      except Exception as err:
        if index == 0:
          raise
        note = f'Ladies of Horror Fiction Goodreads page failed: {url}: {err}'
        parsed_results.append({'entries': (), 'notes': [note]})
        if log is not None:
          log(note)
      index += 1
      if progress is not None:
        progress(index, len(urls), f'Parsed LOHF Goodreads page {index} of {len(urls)}')
    return parsed_results

  def fetch_parse_file770_winners(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse):
    progress = getattr(self, '_lohf_progress', None)
    if progress is not None:
      progress(0, 1, 'Fetching LOHF File 770 winner supplement')
    html = self.fetch_page(
      fetch_url, FILE770_2021_WINNERS_URL, before_fetch, after_fetch)
    self.before_parse(before_parse, FILE770_2021_WINNERS_URL)
    if progress is not None:
      progress(0, 1, 'Parsing LOHF File 770 winner supplement')
    parsed = parser.parse_file770_winners(
      html,
      FILE770_2021_WINNERS_URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES)
    if progress is not None:
      progress(1, 1, 'Parsed LOHF File 770 winner supplement')
    return parsed

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
  NAME = 'Ladies of Horror Fiction - Novel (discontinued)'
  CATEGORY = 'Novel'
  CATEGORY_ALIASES = ('novel', 'best novel')


class UrlFetcherLadiesOfHorrorFictionNovella(UrlFetcherLadiesOfHorrorFiction):
  source_id = 'ladies_of_horror_fiction_novella'
  NAME = 'Ladies of Horror Fiction - Novella (discontinued)'
  CATEGORY = 'Novella'
  CATEGORY_ALIASES = ('novella', 'best novella')


class UrlFetcherLadiesOfHorrorFictionCollection(UrlFetcherLadiesOfHorrorFiction):
  source_id = 'ladies_of_horror_fiction_collection'
  NAME = 'Ladies of Horror Fiction - Collection (discontinued)'
  CATEGORY = 'Collection'
  CATEGORY_ALIASES = ('collection', 'best collection')


class UrlFetcherLadiesOfHorrorFictionDebut(UrlFetcherLadiesOfHorrorFiction):
  source_id = 'ladies_of_horror_fiction_debut'
  NAME = 'Ladies of Horror Fiction - Debut (discontinued)'
  CATEGORY = 'Debut'
  CATEGORY_ALIASES = ('debut', 'best debut')


class UrlFetcherLadiesOfHorrorFictionYoungAdult(UrlFetcherLadiesOfHorrorFiction):
  source_id = 'ladies_of_horror_fiction_young_adult'
  NAME = 'Ladies of Horror Fiction - Young Adult (discontinued)'
  CATEGORY = 'Young Adult'
  CATEGORY_ALIASES = ('young adult', 'best young adult')


class UrlFetcherLadiesOfHorrorFictionMiddleGrade(UrlFetcherLadiesOfHorrorFiction):
  source_id = 'ladies_of_horror_fiction_middle_grade'
  NAME = 'Ladies of Horror Fiction - Middle Grade (discontinued)'
  CATEGORY = 'Middle Grade'
  CATEGORY_ALIASES = ('middle grade', 'best middle grade')


class UrlFetcherLadiesOfHorrorFictionPoetryCollection(
    UrlFetcherLadiesOfHorrorFiction):
  source_id = 'ladies_of_horror_fiction_poetry_collection'
  NAME = 'Ladies of Horror Fiction - Poetry Collection (discontinued)'
  CATEGORY = 'Poetry Collection'
  CATEGORY_ALIASES = (
    'poetry',
    'best poetry',
    'poetry collection',
    'best poetry collection',
  )


class UrlFetcherLadiesOfHorrorFictionGraphicNovel(UrlFetcherLadiesOfHorrorFiction):
  source_id = 'ladies_of_horror_fiction_graphic_novel'
  NAME = 'Ladies of Horror Fiction - Graphic Novel (discontinued)'
  CATEGORY = 'Graphic Novel'
  CATEGORY_ALIASES = ('graphic novel', 'best graphic novel')
