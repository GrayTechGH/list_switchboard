#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_FANTASY,
  CATEGORY_HORROR_DARK_FICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_SCIENCE_FICTION,
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

try:
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from parser.generic import position_sort_key


AUREALIS_AWARDS_URL = 'https://www.sfadb.com/Aurealis_Awards'
ISFDB_AUREALIS_CATEGORY_URL = 'https://www.isfdb.org/cgi-bin/award_category.cgi?{}+1'
LIBRARYTHING_AUREALIS_URL = 'https://www.librarything.com/award/1348/Aurealis-Award'
SPECULATIVE_REGIONAL_CATEGORIES = (
  CATEGORY_SCIENCE_FICTION,
  CATEGORY_FANTASY,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
)
YOUNG_READER_SPECULATIVE_REGIONAL_CATEGORIES = (
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
) + SPECULATIVE_REGIONAL_CATEGORIES


class UrlFetcherAurealis(LibraryThingAwardFallbackMixin, UrlFetcherGeneric):

  URL = AUREALIS_AWARDS_URL
  FETCH_URLS = ()
  order = 190
  options = {
    'match_series': False,
  }
  AWARD_NAME = 'Aurealis Award'
  LIBRARYTHING_AWARD_NAME = AWARD_NAME
  LIBRARYTHING_URL = LIBRARYTHING_AUREALIS_URL
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  SKIP_QUOTED = False
  ISFDB_CATEGORY_IDS = ()
  LIBRARYTHING_CATEGORY_ALIASES = ()
  USE_LIBRARYTHING_FALLBACK = True

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.aurealis import AurealisParser
    except ImportError:
      from parser.aurealis import AurealisParser

    return AurealisParser(skip_quoted=self.SKIP_QUOTED)

  def create_isfdb_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.isfdb_base import (
        ISFDBAwardParserBase,
      )
    except ImportError:
      from parser.isfdb_base import ISFDBAwardParserBase

    parser = ISFDBAwardParserBase()
    parser.AWARD_NAME = self.AWARD_NAME
    return parser

  def isfdb_urls(self):
    return tuple(
      ISFDB_AUREALIS_CATEGORY_URL.format(category_id)
      for category_id in self.ISFDB_CATEGORY_IDS)

  def librarything_aliases(self):
    return self.CATEGORY_ALIASES + self.LIBRARYTHING_CATEGORY_ALIASES

  def librarything_attempt(self, source_rank=2):
    parser = self.create_librarything_parser()
    return SourceAttempt(
      'LibraryThing',
      self.LIBRARYTHING_URL,
      lambda html, url, **_kwargs: parser.parse(
        html, url, self.NAME, self.CATEGORY, self.librarything_aliases()),
      source_rank=source_rank)

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
    parsed['match_series'] = self.options.get('match_series', True)
    return parsed

  def source_attempts(self):
    attempts = [
      SourceAttempt(
        'SFADB',
        self.URL,
        lambda html, _url, **kwargs: self.parse(html, **kwargs),
        source_rank=0),
    ]
    isfdb_urls = self.isfdb_urls()
    if isfdb_urls:
      attempts.append(SourceAttempt(
        'ISFDB',
        isfdb_urls[0],
        lambda html, url, **kwargs: self.parse_isfdb_pages(
          html, url, isfdb_urls, **kwargs),
        source_rank=1))
    if self.USE_LIBRARYTHING_FALLBACK:
      attempts.append(self.librarything_attempt(source_rank=2))
    return tuple(attempts)

  def source_choices(self):
    return SourceFallbackRunner(self.source_attempts()).source_choices()

  def parse_isfdb_pages(
      self, html, base_url, urls, fetch_url=None, log=None, progress=None):
    parser = self.create_isfdb_parser()
    parsed = parser.parse(
      html,
      base_url,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES)
    entries = list(parsed.get('entries', ()))
    notes = list(parsed.get('notes', ()))
    for url in urls[1:]:
      try:
        extra_html = fetch_url(url) if fetch_url is not None else ''
        extra = parser.parse(
          extra_html,
          url,
          self.NAME,
          self.CATEGORY,
          self.CATEGORY_ALIASES)
        entries.extend(extra.get('entries', ()))
        notes.extend(extra.get('notes', ()))
      except Exception as err:
        notes.append(f'{self.AWARD_NAME} ISFDB category {url} could not be fetched: {err}')
        if log is not None:
          log(f'{self.AWARD_NAME} ISFDB category failed: {url}: {err}')
    parsed['entries'] = sorted(
      entries,
      key=lambda entry: position_sort_key(entry.get('position', '')))
    parsed['notes'] = notes
    return parsed

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES,
      fetch_url=fetch_url,
      log=log,
      progress=progress)


class UrlFetcherAurealisSFNovel(UrlFetcherAurealis):
  source_id = 'aurealis_sf_novel'
  NAME = 'Aurealis - SF Novel'
  FILTER_CATEGORIES = (CATEGORY_SCIENCE_FICTION, CATEGORY_REGIONAL_NATIONAL_AWARDS)
  CATEGORY = 'SF Novel'
  CATEGORY_ALIASES = ('sf novel', 'science fiction novel')
  ISFDB_CATEGORY_IDS = (50,)


class UrlFetcherAurealisGoldenAurealisNovel(UrlFetcherAurealis):
  source_id = 'aurealis_golden_aurealis_novel'
  NAME = 'Aurealis - Golden Aurealis Novel (discontinued)'
  FILTER_CATEGORIES = YOUNG_READER_SPECULATIVE_REGIONAL_CATEGORIES
  CATEGORY = 'Golden Aurealis - Novel'
  CATEGORY_ALIASES = ('golden aurealis novel',)
  ISFDB_CATEGORY_IDS = (42,)
  LIBRARYTHING_CATEGORY_ALIASES = ('golden aurealis award best novel',)


class UrlFetcherAurealisFantasyNovel(UrlFetcherAurealis):
  source_id = 'aurealis_fantasy_novel'
  NAME = 'Aurealis - Fantasy Novel'
  FILTER_CATEGORIES = (CATEGORY_FANTASY, CATEGORY_REGIONAL_NATIONAL_AWARDS)
  CATEGORY = 'Fantasy Novel'
  CATEGORY_ALIASES = ('fantasy novel',)
  ISFDB_CATEGORY_IDS = (39,)


class UrlFetcherAurealisHorrorNovel(UrlFetcherAurealis):
  source_id = 'aurealis_horror_novel'
  NAME = 'Aurealis - Horror Novel'
  FILTER_CATEGORIES = (CATEGORY_HORROR_DARK_FICTION, CATEGORY_REGIONAL_NATIONAL_AWARDS)
  CATEGORY = 'Horror Novel'
  CATEGORY_ALIASES = ('horror novel',)
  ISFDB_CATEGORY_IDS = (44,)


class UrlFetcherAurealisSFNovella(UrlFetcherAurealis):
  source_id = 'aurealis_sf_novella'
  NAME = 'Aurealis - SF Novella'
  FILTER_CATEGORIES = (CATEGORY_SCIENCE_FICTION, CATEGORY_REGIONAL_NATIONAL_AWARDS)
  CATEGORY = 'SF Novella'
  CATEGORY_ALIASES = ('sf novella', 'science fiction novella')
  ISFDB_CATEGORY_IDS = (640,)
  SKIP_QUOTED = True


class UrlFetcherAurealisFantasyNovella(UrlFetcherAurealis):
  source_id = 'aurealis_fantasy_novella'
  NAME = 'Aurealis - Fantasy Novella'
  FILTER_CATEGORIES = (CATEGORY_FANTASY, CATEGORY_REGIONAL_NATIONAL_AWARDS)
  CATEGORY = 'Fantasy Novella'
  CATEGORY_ALIASES = ('fantasy novella',)
  ISFDB_CATEGORY_IDS = (641,)
  SKIP_QUOTED = True


class UrlFetcherAurealisHorrorNovella(UrlFetcherAurealis):
  source_id = 'aurealis_horror_novella'
  NAME = 'Aurealis - Horror Novella'
  FILTER_CATEGORIES = (CATEGORY_HORROR_DARK_FICTION, CATEGORY_REGIONAL_NATIONAL_AWARDS)
  CATEGORY = 'Horror Novella'
  CATEGORY_ALIASES = ('horror novella',)
  ISFDB_CATEGORY_IDS = (642,)
  SKIP_QUOTED = True


class UrlFetcherAurealisAnthology(UrlFetcherAurealis):
  source_id = 'aurealis_anthology'
  NAME = 'Aurealis - Anthology'
  FILTER_CATEGORIES = SPECULATIVE_REGIONAL_CATEGORIES
  CATEGORY = 'Anthology'
  CATEGORY_ALIASES = ('anthology',)
  ISFDB_CATEGORY_IDS = (30,)


class UrlFetcherAurealisCollection(UrlFetcherAurealis):
  source_id = 'aurealis_collection'
  NAME = 'Aurealis - Collection'
  FILTER_CATEGORIES = SPECULATIVE_REGIONAL_CATEGORIES
  CATEGORY = 'Collection'
  CATEGORY_ALIASES = ('collection',)
  ISFDB_CATEGORY_IDS = (37,)


class UrlFetcherAurealisGraphicNovelIllustratedWork(UrlFetcherAurealis):
  source_id = 'aurealis_graphic_novel_illustrated_work'
  NAME = 'Aurealis - Graphic Novel/Illustrated Work'
  FILTER_CATEGORIES = SPECULATIVE_REGIONAL_CATEGORIES
  CATEGORY = 'Graphic Novel/Illustrated Work'
  CATEGORY_ALIASES = (
    'graphic novel/illustrated work',
    'illustrated book/graphic novel',
    'illustrated book / graphic novel',
    'graphic novel',
  )
  ISFDB_CATEGORY_IDS = (621, 47)


class UrlFetcherAurealisYoungAdultNovel(UrlFetcherAurealis):
  source_id = 'aurealis_young_adult_novel'
  NAME = 'Aurealis - Young Adult Novel'
  FILTER_CATEGORIES = YOUNG_READER_SPECULATIVE_REGIONAL_CATEGORIES
  CATEGORY = 'Young Adult Novel'
  CATEGORY_ALIASES = ('young adult novel', 'ya novel')
  ISFDB_CATEGORY_IDS = (53,)


class UrlFetcherAurealisChildrensFiction(UrlFetcherAurealis):
  source_id = 'aurealis_childrens_fiction'
  NAME = "Aurealis - Children's Fiction"
  FILTER_CATEGORIES = YOUNG_READER_SPECULATIVE_REGIONAL_CATEGORIES
  CATEGORY = "Children's Fiction"
  CATEGORY_ALIASES = ("children's fiction", 'childrens fiction', 'children fiction')
  ISFDB_CATEGORY_IDS = (620,)


class UrlFetcherAurealisChildrensBook(UrlFetcherAurealis):
  source_id = 'aurealis_childrens_book'
  NAME = "Aurealis - Children's Book (discontinued)"
  FILTER_CATEGORIES = YOUNG_READER_SPECULATIVE_REGIONAL_CATEGORIES
  CATEGORY = "Children's Book"
  CATEGORY_ALIASES = ("children's book", 'childrens book')
  ISFDB_CATEGORY_IDS = (34,)


class UrlFetcherAurealisChildrensFictionWords(UrlFetcherAurealis):
  source_id = 'aurealis_childrens_fiction_words'
  NAME = "Aurealis - Children's Fiction (Words) (discontinued)"
  FILTER_CATEGORIES = YOUNG_READER_SPECULATIVE_REGIONAL_CATEGORIES
  CATEGORY = "Children's Fiction (told primarily through words)"
  CATEGORY_ALIASES = (
    "children's fiction told primarily through words",
    'childrens fiction told primarily through words',
    "children's fiction words",
    "children's fiction (words)",
  )
  ISFDB_CATEGORY_IDS = (36,)


class UrlFetcherAurealisChildrensFictionPictures(UrlFetcherAurealis):
  source_id = 'aurealis_childrens_fiction_pictures'
  NAME = "Aurealis - Children's Fiction (Pictures) (discontinued)"
  FILTER_CATEGORIES = YOUNG_READER_SPECULATIVE_REGIONAL_CATEGORIES
  CATEGORY = "Children's Fiction (told primarily through pictures)"
  CATEGORY_ALIASES = (
    "children's fiction told primarily through pictures",
    'childrens fiction told primarily through pictures',
    "children's fiction pictures",
    "children's fiction (pictures)",
  )
  ISFDB_CATEGORY_IDS = (35,)


class UrlFetcherAurealisChildrens812LongFiction(UrlFetcherAurealis):
  source_id = 'aurealis_childrens_8_12_long_fiction'
  NAME = "Aurealis - Children's 8-12 Long Fiction (discontinued)"
  FILTER_CATEGORIES = YOUNG_READER_SPECULATIVE_REGIONAL_CATEGORIES
  CATEGORY = "Children's (8-12 years) Long Fiction"
  CATEGORY_ALIASES = (
    "children's 8 12 years long fiction",
    'childrens 8 12 years long fiction',
    "children's long fiction",
  )
  ISFDB_CATEGORY_IDS = (32,)


class UrlFetcherAurealisChildrens812IllustratedWorkPictureBook(UrlFetcherAurealis):
  source_id = 'aurealis_childrens_8_12_illustrated_work_picture_book'
  NAME = (
    "Aurealis - Children's 8-12 Illustrated Work/Picture Book "
    '(discontinued)')
  FILTER_CATEGORIES = YOUNG_READER_SPECULATIVE_REGIONAL_CATEGORIES
  CATEGORY = "Children's (8-12 years) Illustrated Work/Picture Book"
  CATEGORY_ALIASES = (
    "children's 8 12 years illustrated work/picture book",
    'childrens 8 12 years illustrated work/picture book',
    "children's illustrated work/picture book",
  )
  ISFDB_CATEGORY_IDS = (31,)


class UrlFetcherAurealisSaraDouglassBookSeries(UrlFetcherAurealis):
  source_id = 'aurealis_sara_douglass_book_series_award'
  NAME = 'Aurealis - Sara Douglass Book Series Award'
  REQUIRES_SERIES_MATCHING = True
  FILTER_CATEGORIES = SPECULATIVE_REGIONAL_CATEGORIES
  CATEGORY = 'Sara Douglass Book Series Award'
  CATEGORY_ALIASES = ('sara douglass book series award', 'sara douglass book series')
  ISFDB_CATEGORY_IDS = (643,)
  USE_LIBRARYTHING_FALLBACK = False
  options = {
    'match_series': True,
  }

  def parse(self, *args, **kwargs):
    parsed = super().parse(*args, **kwargs)
    parsed['match_series'] = True
    return parsed
