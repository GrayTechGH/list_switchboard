#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_CRIME_MYSTERY_THRILLER,
  CATEGORY_NONFICTION,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherError,
  UrlFetcherGeneric,
)

try:
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
  from calibre_plugins.list_switchboard.url_fetcher.librarything_fallback import (
    LibraryThingAwardFallbackMixin,
  )
except ImportError:
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner
  from url_fetcher.librarything_fallback import LibraryThingAwardFallbackMixin


LIBRARYTHING_EDGAR_URL = 'https://www.librarything.com/award/490/Edgar-Award'
EDGAR_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER,)
EDGAR_YA_CATEGORIES = (
  CATEGORY_CRIME_MYSTERY_THRILLER,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
)
EDGAR_NONFICTION_CATEGORIES = (
  CATEGORY_CRIME_MYSTERY_THRILLER,
  CATEGORY_NONFICTION,
)


class UrlFetcherEdgar(LibraryThingAwardFallbackMixin, UrlFetcherGeneric):

  FILTER_CATEGORIES = EDGAR_CATEGORIES
  FETCH_URLS = ()
  order = 220
  options = {
    'match_series': False,
  }
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  LIBRARYTHING_URL = LIBRARYTHING_EDGAR_URL
  LIBRARYTHING_AWARD_NAME = 'Edgar Award'
  AWARD_NAME = 'Edgar Award'

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.edgar import EdgarAwardsParser
    except ImportError:
      from parser.edgar import EdgarAwardsParser

    return EdgarAwardsParser()

  def fetch_and_parse(
      self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
      before_fetch=None, after_fetch=None, before_parse=None,
      force_fallback_level=0, disable_fallbacks=False, source_choice=None):
    parsed = SourceFallbackRunner(
      self.source_attempts(),
      error_class=UrlFetcherError).run(
        fetch_url,
        log=log,
        progress=progress,
        before_fetch=before_fetch,
        after_fetch=after_fetch,
        before_parse=before_parse,
        force_fallback_level=force_fallback_level,
        disable_fallbacks=disable_fallbacks,
        source_choice=source_choice)
    parsed.setdefault('match_series', self.options.get('match_series', True))
    return parsed

  def source_attempts(self):
    official_parser = self.parser()
    return (
      SourceAttempt(
        'Official Edgar',
        self.URL,
        lambda html, url, **kwargs: official_parser.parse(
          html, url, self.NAME, self.CATEGORY, **kwargs),
        source_rank=0),
      self.librarything_attempt(source_rank=1),
    )

  def source_choices(self):
    return SourceFallbackRunner(self.source_attempts()).source_choices()

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      self.CATEGORY,
      fetch_url=fetch_url,
      log=log,
      progress=progress)


class UrlFetcherEdgarNovel(UrlFetcherEdgar):
  source_id = 'edgar_award_novel'
  NAME = 'Edgar Award - Novel'
  URL = 'https://edgarawards.com/category-list-best-novel/'
  CATEGORY = 'Best Novel'
  CATEGORY_ALIASES = ('novel', 'best novel')


class UrlFetcherEdgarFirstNovel(UrlFetcherEdgar):
  source_id = 'edgar_award_first_novel'
  NAME = 'Edgar Award - First Novel'
  URL = 'https://edgarawards.com/category-list-best-first-novel/'
  CATEGORY = 'Best First Novel'
  CATEGORY_ALIASES = ('first novel', 'best first novel')


class UrlFetcherEdgarPaperbackOriginal(UrlFetcherEdgar):
  source_id = 'edgar_award_paperback_original'
  NAME = 'Edgar Award - Paperback Original'
  URL = 'https://edgarawards.com/category-list-best-paperback-original/'
  CATEGORY = 'Best Paperback Original'
  CATEGORY_ALIASES = (
    'paperback original',
    'paperback or ebook original',
    'best paperback original',
  )


class UrlFetcherEdgarFactCrime(UrlFetcherEdgar):
  source_id = 'edgar_award_fact_crime'
  NAME = 'Edgar Award - Fact Crime'
  FILTER_CATEGORIES = EDGAR_NONFICTION_CATEGORIES
  URL = 'https://edgarawards.com/category-list-best-fact-crime/'
  CATEGORY = 'Best Fact Crime'
  CATEGORY_ALIASES = ('fact crime', 'best fact crime')


class UrlFetcherEdgarCriticalBiographicalWork(UrlFetcherEdgar):
  source_id = 'edgar_award_critical_biographical_work'
  NAME = 'Edgar Award - Critical/Biographical Work'
  FILTER_CATEGORIES = EDGAR_NONFICTION_CATEGORIES
  URL = 'https://edgarawards.com/category-list-best-critical-biographical-work/'
  CATEGORY = 'Best Critical/Biographical Work'
  CATEGORY_ALIASES = (
    'critical/biographical work',
    'critical / biographical work',
    'critical/biography',
    'best critical/biographical work',
  )


class UrlFetcherEdgarJuvenile(UrlFetcherEdgar):
  source_id = 'edgar_award_juvenile'
  NAME = 'Edgar Award - Juvenile'
  FILTER_CATEGORIES = EDGAR_YA_CATEGORIES
  URL = 'https://edgarawards.com/category-list-best-juvenile/'
  CATEGORY = 'Best Juvenile'
  CATEGORY_ALIASES = ('juvenile', 'best juvenile')


class UrlFetcherEdgarYoungAdult(UrlFetcherEdgar):
  source_id = 'edgar_award_young_adult'
  NAME = 'Edgar Award - Young Adult'
  FILTER_CATEGORIES = EDGAR_YA_CATEGORIES
  URL = 'https://edgarawards.com/category-list-best-young-adult/'
  CATEGORY = 'Best Young Adult'
  CATEGORY_ALIASES = (
    'young adult',
    'young adult novel',
    'best young adult',
  )


class UrlFetcherEdgarMaryHigginsClarkAward(UrlFetcherEdgar):
  source_id = 'edgar_award_mary_higgins_clark_award'
  NAME = 'Edgar Award - Mary Higgins Clark Award'
  URL = 'https://edgarawards.com/category-list-mary-higgins-clark-award/'
  CATEGORY = 'Mary Higgins Clark Award'
  CATEGORY_ALIASES = (
    'mary higgins clark award',
    'simon and schuster mary higgins clark award',
    'simon & schuster mary higgins clark award',
  )


class UrlFetcherEdgarLilianJacksonBraunAward(UrlFetcherEdgar):
  source_id = 'edgar_award_lilian_jackson_braun_award'
  NAME = 'Edgar Award - Lilian Jackson Braun Award'
  URL = 'https://edgarawards.com/category-list-lilian-jackson-braun/'
  CATEGORY = 'Lilian Jackson Braun Award'
  CATEGORY_ALIASES = (
    'lilian jackson braun award',
    'lilian jackson braun memorial award',
    'the lilian jackson braun memorial award',
  )
