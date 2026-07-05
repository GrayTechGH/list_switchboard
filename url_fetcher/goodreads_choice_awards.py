#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_CRIME_MYSTERY_THRILLER,
  CATEGORY_FANTASY,
  CATEGORY_HORROR_DARK_FICTION,
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_NONFICTION,
  CATEGORY_ROMANCE,
  CATEGORY_SCIENCE_FICTION,
  CATEGORY_UNKNOWN,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherGeneric,
)

try:
  from calibre_plugins.list_switchboard.parser.goodreads_choice_awards import ( # type: ignore
    CHOICE_AWARDS_URL,
  )
except ImportError:
  from parser.goodreads_choice_awards import CHOICE_AWARDS_URL


class UrlFetcherGoodreadsChoiceAwards(UrlFetcherGeneric):

  URL = CHOICE_AWARDS_URL
  order = 260
  options = {'match_series': False}
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  FILTER_CATEGORIES = (CATEGORY_UNKNOWN,)

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.goodreads_choice_awards import ( # type: ignore
        GoodreadsChoiceAwardsParser,
      )
    except ImportError:
      from parser.goodreads_choice_awards import GoodreadsChoiceAwardsParser
    return GoodreadsChoiceAwardsParser(self.CATEGORY, self.CATEGORY_ALIASES)

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      fetch_url=fetch_url,
      log=log,
      progress=progress)


class UrlFetcherGoodreadsChoiceAwardsFiction(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_fiction'
  NAME = 'Goodreads Choice Awards - Fiction'
  CATEGORY = 'Fiction'
  CATEGORY_ALIASES = ('Fiction',)
  FILTER_CATEGORIES = (CATEGORY_LITERARY_GENERAL_FICTION,)


class UrlFetcherGoodreadsChoiceAwardsHistoricalFiction(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_historical_fiction'
  NAME = 'Goodreads Choice Awards - Historical Fiction'
  CATEGORY = 'Historical Fiction'
  CATEGORY_ALIASES = ('Historical Fiction',)
  FILTER_CATEGORIES = (CATEGORY_LITERARY_GENERAL_FICTION,)


class UrlFetcherGoodreadsChoiceAwardsMysteryThriller(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_mystery_thriller'
  NAME = 'Goodreads Choice Awards - Mystery & Thriller'
  CATEGORY = 'Mystery & Thriller'
  CATEGORY_ALIASES = ('Mystery & Thriller', 'Mystery and Thriller')
  FILTER_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER,)


class UrlFetcherGoodreadsChoiceAwardsRomance(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_romance'
  NAME = 'Goodreads Choice Awards - Romance'
  CATEGORY = 'Romance'
  CATEGORY_ALIASES = ('Romance',)
  FILTER_CATEGORIES = (CATEGORY_ROMANCE,)


class UrlFetcherGoodreadsChoiceAwardsRomantasy(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_romantasy'
  NAME = 'Goodreads Choice Awards - Romantasy'
  CATEGORY = 'Romantasy'
  CATEGORY_ALIASES = ('Romantasy',)
  FILTER_CATEGORIES = (CATEGORY_ROMANCE, CATEGORY_FANTASY)


class UrlFetcherGoodreadsChoiceAwardsFantasy(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_fantasy'
  NAME = 'Goodreads Choice Awards - Fantasy'
  CATEGORY = 'Fantasy'
  CATEGORY_ALIASES = ('Fantasy',)
  FILTER_CATEGORIES = (CATEGORY_FANTASY,)


class UrlFetcherGoodreadsChoiceAwardsScienceFiction(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_science_fiction'
  NAME = 'Goodreads Choice Awards - Science Fiction'
  CATEGORY = 'Science Fiction'
  CATEGORY_ALIASES = ('Science Fiction', 'Sci-Fi', 'Sci Fi')
  FILTER_CATEGORIES = (CATEGORY_SCIENCE_FICTION,)


class UrlFetcherGoodreadsChoiceAwardsHorror(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_horror'
  NAME = 'Goodreads Choice Awards - Horror'
  CATEGORY = 'Horror'
  CATEGORY_ALIASES = ('Horror',)
  FILTER_CATEGORIES = (CATEGORY_HORROR_DARK_FICTION,)


class UrlFetcherGoodreadsChoiceAwardsDebutNovel(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_debut_novel'
  NAME = 'Goodreads Choice Awards - Debut Novel'
  CATEGORY = 'Debut Novel'
  CATEGORY_ALIASES = ('Debut Novel',)
  FILTER_CATEGORIES = (CATEGORY_LITERARY_GENERAL_FICTION,)


class UrlFetcherGoodreadsChoiceAwardsAudiobook(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_audiobook'
  NAME = 'Goodreads Choice Awards - Audiobook'
  CATEGORY = 'Audiobook'
  CATEGORY_ALIASES = ('Audiobook',)
  FILTER_CATEGORIES = (CATEGORY_LITERARY_GENERAL_FICTION,)


class UrlFetcherGoodreadsChoiceAwardsYoungAdultFiction(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_young_adult_fiction'
  NAME = 'Goodreads Choice Awards - Young Adult Fiction'
  CATEGORY = 'Young Adult Fiction'
  CATEGORY_ALIASES = ('Young Adult Fiction',)
  FILTER_CATEGORIES = (CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,)


class UrlFetcherGoodreadsChoiceAwardsYoungAdultFantasyScienceFiction(
    UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_young_adult_fantasy_science_fiction'
  NAME = 'Goodreads Choice Awards - Young Adult Fantasy & Science Fiction'
  CATEGORY = 'Young Adult Fantasy & Science Fiction'
  CATEGORY_ALIASES = (
    'Young Adult Fantasy & Science Fiction',
    'Young Adult Fantasy & Sci-Fi',
    'Young Adult Fantasy and Science Fiction',
    'Young Adult Fantasy and Sci Fi',
    'Young Adult Fantasy',
  )
  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_FANTASY,
    CATEGORY_SCIENCE_FICTION,
  )


class UrlFetcherGoodreadsChoiceAwardsNonfiction(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_nonfiction'
  NAME = 'Goodreads Choice Awards - Nonfiction'
  CATEGORY = 'Nonfiction'
  CATEGORY_ALIASES = ('Nonfiction', 'Non-fiction')
  FILTER_CATEGORIES = (CATEGORY_NONFICTION,)


class UrlFetcherGoodreadsChoiceAwardsMemoir(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_memoir'
  NAME = 'Goodreads Choice Awards - Memoir'
  CATEGORY = 'Memoir'
  CATEGORY_ALIASES = ('Memoir', 'Memoir & Autobiography', 'Memoir and Autobiography')
  FILTER_CATEGORIES = (CATEGORY_NONFICTION,)


class UrlFetcherGoodreadsChoiceAwardsHistoryBiography(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_history_biography'
  NAME = 'Goodreads Choice Awards - History & Biography'
  CATEGORY = 'History & Biography'
  CATEGORY_ALIASES = ('History & Biography', 'History and Biography')
  FILTER_CATEGORIES = (CATEGORY_NONFICTION,)


class UrlFetcherGoodreadsChoiceAwardsYoungAdultSeries(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_young_adult_series'
  NAME = 'Goodreads Choice Awards - Young Adult Series (discontinued)'
  CATEGORY = 'Young Adult Series'
  CATEGORY_ALIASES = ('Young Adult Series',)
  FILTER_CATEGORIES = (CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,)


class UrlFetcherGoodreadsChoiceAwardsChildrensMiddleGrade(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_childrens_middle_grade'
  NAME = "Goodreads Choice Awards - Children's & Middle Grade (discontinued)"
  CATEGORY = "Children's & Middle Grade"
  CATEGORY_ALIASES = (
    "Children's & Middle Grade",
    "Children's and Middle Grade",
    "Children's",
    'Childrens & Middle Grade',
    'Childrens and Middle Grade',
    'Children',
  )
  FILTER_CATEGORIES = (CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,)


class UrlFetcherGoodreadsChoiceAwardsPictureBook(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_picture_book'
  NAME = 'Goodreads Choice Awards - Picture Book (discontinued)'
  CATEGORY = 'Picture Book'
  CATEGORY_ALIASES = ('Picture Book',)
  FILTER_CATEGORIES = (CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,)


class UrlFetcherGoodreadsChoiceAwardsScienceTechnology(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_science_technology'
  NAME = 'Goodreads Choice Awards - Science & Technology (discontinued)'
  CATEGORY = 'Science & Technology'
  CATEGORY_ALIASES = ('Science & Technology', 'Science and Technology')
  FILTER_CATEGORIES = (CATEGORY_NONFICTION,)


class UrlFetcherGoodreadsChoiceAwardsBusiness(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_business'
  NAME = 'Goodreads Choice Awards - Business (discontinued)'
  CATEGORY = 'Business'
  CATEGORY_ALIASES = ('Business',)
  FILTER_CATEGORIES = (CATEGORY_NONFICTION,)


class UrlFetcherGoodreadsChoiceAwardsFoodCooking(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_food_cooking'
  NAME = 'Goodreads Choice Awards - Food & Cooking (discontinued)'
  CATEGORY = 'Food & Cooking'
  CATEGORY_ALIASES = ('Food & Cooking', 'Food and Cooking')
  FILTER_CATEGORIES = (CATEGORY_NONFICTION,)


class UrlFetcherGoodreadsChoiceAwardsTravelOutdoors(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_travel_outdoors'
  NAME = 'Goodreads Choice Awards - Travel & Outdoors (discontinued)'
  CATEGORY = 'Travel & Outdoors'
  CATEGORY_ALIASES = ('Travel & Outdoors', 'Travel and Outdoors')
  FILTER_CATEGORIES = (CATEGORY_NONFICTION,)


class UrlFetcherGoodreadsChoiceAwardsGraphicNovelsComics(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_graphic_novels_comics'
  NAME = 'Goodreads Choice Awards - Graphic Novels & Comics (discontinued)'
  CATEGORY = 'Graphic Novels & Comics'
  CATEGORY_ALIASES = (
    'Graphic Novels & Comics',
    'Graphic Novel & Comics',
    'Graphic Novel',
    'Graphic Novels and Comics',
  )
  FILTER_CATEGORIES = (CATEGORY_LITERARY_GENERAL_FICTION,)


class UrlFetcherGoodreadsChoiceAwardsPoetry(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_poetry'
  NAME = 'Goodreads Choice Awards - Poetry (discontinued)'
  CATEGORY = 'Poetry'
  CATEGORY_ALIASES = ('Poetry',)
  FILTER_CATEGORIES = (CATEGORY_LITERARY_GENERAL_FICTION,)


class UrlFetcherGoodreadsChoiceAwardsHumor(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_humor'
  NAME = 'Goodreads Choice Awards - Humor (discontinued)'
  CATEGORY = 'Humor'
  CATEGORY_ALIASES = ('Humor', 'Humour')
  FILTER_CATEGORIES = (CATEGORY_LITERARY_GENERAL_FICTION, CATEGORY_NONFICTION)


class UrlFetcherGoodreadsChoiceAwardsParanormalFantasy(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_paranormal_fantasy'
  NAME = 'Goodreads Choice Awards - Paranormal Fantasy (discontinued)'
  CATEGORY = 'Paranormal Fantasy'
  CATEGORY_ALIASES = ('Paranormal Fantasy',)
  FILTER_CATEGORIES = (CATEGORY_FANTASY,)


class UrlFetcherGoodreadsChoiceAwardsChickLit(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_chick_lit'
  NAME = 'Goodreads Choice Awards - Chick Lit (discontinued)'
  CATEGORY = 'Chick Lit'
  CATEGORY_ALIASES = ('Chick Lit',)
  FILTER_CATEGORIES = (CATEGORY_LITERARY_GENERAL_FICTION, CATEGORY_ROMANCE)


class UrlFetcherGoodreadsChoiceAwardsBestBook(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_best_book'
  NAME = 'Goodreads Choice Awards - Best Book (discontinued)'
  CATEGORY = 'Best Book'
  CATEGORY_ALIASES = ('Best Book',)
  FILTER_CATEGORIES = (CATEGORY_LITERARY_GENERAL_FICTION,)


class UrlFetcherGoodreadsChoiceAwardsBestOfTheBest(UrlFetcherGoodreadsChoiceAwards):

  source_id = 'goodreads_choice_awards_best_of_the_best'
  NAME = 'Goodreads Choice Awards - Best of the Best (discontinued)'
  CATEGORY = 'Best of the Best'
  CATEGORY_ALIASES = ('Best of the Best',)
  FILTER_CATEGORIES = (CATEGORY_LITERARY_GENERAL_FICTION,)
