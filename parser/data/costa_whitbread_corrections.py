#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Versioned coverage and verified corrections for Costa/Whitbread imports."""


SCHEMA_VERSION = 1

OFFICIAL_WINNERS_URL = 'https://www.costa.co.uk/docs/cba-past-winners.pdf'
OFFICIAL_SHORTLISTS_URL = (
  'https://assets.ctfassets.net/royi30b2qd26/0fYMQAdicaCewJmOhXoSz/'
  'c9f89bfb3c9797f21d5eaaa438a96efa/past-shortlists-2019-end.pdf')
BOOKSELLERS_2020_URL = (
  'https://www.booksellers.org.uk/industryinfo/industryinfo/latestnews/'
  'Costa-Book-Awards-2020-shortlists-announced')


def _year_counts(start, end, rows=1, winners=1):
  return {
    str(year): {'rows': rows, 'winners': winners}
    for year in range(start, end + 1)
  }


def _coverage(*parts):
  result = {}
  for part in parts:
    result.update(part)
  return result


# These expand to an exact per-recipe, per-year map at import time. Gaps are
# deliberate and therefore absent rather than represented by zero-row years.
COVERAGE = {
  'novel': _coverage(
    _year_counts(1971, 1994),
    {
      '1995': {'rows': 5, 'winners': 1},
      '1996': {'rows': 6, 'winners': 1},
      '1997': {'rows': 5, 'winners': 1},
      '1998': {'rows': 3, 'winners': 1},
      '1999': {'rows': 4, 'winners': 1},
      '2000': {'rows': 5, 'winners': 1},
    },
    _year_counts(2001, 2021, rows=4),
  ),
  'first_novel': _coverage(
    _year_counts(1974, 1975),
    _year_counts(1981, 1994),
    {
      '1995': {'rows': 3, 'winners': 1},
      '1996': {'rows': 4, 'winners': 1},
      '1997': {'rows': 5, 'winners': 1},
    },
    _year_counts(1998, 2021, rows=4),
  ),
  'biography': _coverage(
    _year_counts(1971, 1982),
    {'1983': {'rows': 2, 'winners': 2}},
    _year_counts(1984, 1994),
    {
      '1995': {'rows': 4, 'winners': 1},
      '1996': {'rows': 4, 'winners': 1},
      '1997': {'rows': 5, 'winners': 1},
      '1998': {'rows': 3, 'winners': 1},
      '1999': {'rows': 3, 'winners': 1},
    },
    _year_counts(2000, 2009, rows=4),
    {'2010': {'rows': 3, 'winners': 1}},
    _year_counts(2011, 2021, rows=4),
  ),
  'childrens_book': _coverage(
    _year_counts(1972, 1973),
    {'1974': {'rows': 2, 'winners': 2}},
    _year_counts(1976, 1994),
    {'1995': {'rows': 3, 'winners': 1}},
    _year_counts(1996, 2021, rows=4),
  ),
  'book_of_the_year': _coverage(
    _year_counts(1980, 1980),
    _year_counts(1985, 2021),
  ),
}

EXPECTED_TOTALS = {
  'novel': 136,
  'first_novel': 124,
  'biography': 131,
  'childrens_book': 130,
  'book_of_the_year': 38,
}

REPLACEMENT_YEARS = {
  'childrens_book': {
    '2016': [
      {
        'title': 'The Bombs That Brought Us Together',
        'authors': ['Brian Conaghan'],
        'result': 'winner',
        'source_url': OFFICIAL_WINNERS_URL,
      },
      {
        'title': 'Orangeboy',
        'authors': ['Patrice Lawrence'],
        'result': 'shortlisted',
        'source_url': OFFICIAL_SHORTLISTS_URL,
      },
      {
        'title': 'The Monstrous Child',
        'authors': ['Francesca Simon'],
        'result': 'shortlisted',
        'source_url': OFFICIAL_SHORTLISTS_URL,
      },
      {
        'title': 'Time Travelling with a Hamster',
        'authors': ['Ross Welford'],
        'result': 'shortlisted',
        'source_url': OFFICIAL_SHORTLISTS_URL,
      },
    ],
    '2017': [
      {
        'title': 'The Explorer',
        'authors': ['Katherine Rundell'],
        'result': 'winner',
        'source_url': OFFICIAL_WINNERS_URL,
      },
      {
        'title': 'Moonrise',
        'authors': ['Sarah Crossan'],
        'result': 'shortlisted',
        'source_url': OFFICIAL_SHORTLISTS_URL,
      },
      {
        'title': 'Wed Wabbit',
        'authors': ['Lissa Evans'],
        'result': 'shortlisted',
        'source_url': OFFICIAL_SHORTLISTS_URL,
      },
      {
        'title': 'The Island at the End of Everything',
        'authors': ['Kiran Millwood Hargrave'],
        'result': 'shortlisted',
        'source_url': OFFICIAL_SHORTLISTS_URL,
      },
    ],
  },
  'biography': {
    '2018': [
      {
        'title': 'The Cut Out Girl: A Story of War and Family, Lost and Found',
        'authors': ['Bart van Es'],
        'result': 'winner',
        'source_url': OFFICIAL_WINNERS_URL,
      },
      {
        'title': 'To Throw Away Unopened',
        'authors': ['Viv Albertine'],
        'result': 'shortlisted',
        'source_url': OFFICIAL_SHORTLISTS_URL,
      },
      {
        'title': 'The Salt Path',
        'authors': ['Raynor Winn'],
        'result': 'shortlisted',
        'source_url': OFFICIAL_SHORTLISTS_URL,
      },
      {
        'title': 'The Life and Rhymes of Benjamin Zephaniah: The Autobiography',
        'authors': ['Benjamin Zephaniah'],
        'result': 'shortlisted',
        'source_url': OFFICIAL_SHORTLISTS_URL,
      },
    ],
    '2020': [
      {
        'title': 'The Louder I Will Sing',
        'authors': ['Lee Lawrence'],
        'result': 'winner',
        'source_url': OFFICIAL_WINNERS_URL,
      },
      {
        'title': 'The Man in the Red Coat',
        'authors': ['Julian Barnes'],
        'result': 'shortlisted',
        'source_url': BOOKSELLERS_2020_URL,
      },
      {
        'title': 'Dear Life',
        'authors': ['Rachel Clarke'],
        'result': 'shortlisted',
        'source_url': BOOKSELLERS_2020_URL,
      },
      {
        'title': 'Ghost Town: A Liverpool Shadow Play',
        'authors': ['Jeff Young'],
        'result': 'shortlisted',
        'source_url': BOOKSELLERS_2020_URL,
      },
    ],
  },
}

TITLE_CORRECTIONS = (
  {
    'recipe': 'biography',
    'year': '1990',
    'source_title': 'AA Milne–His Life',
    'title': 'A. A. Milne: His Life',
  },
  {
    'recipe': 'biography',
    'year': '1998',
    'source_title': 'Hitler, Volume One Hubris 1889–1936',
    'title': 'Hitler, Volume One: Hubris 1889–1936',
  },
  {
    'recipe': 'biography',
    'year': '2005',
    'source_title': 'Matisse the Master',
    'title': 'Matisse: The Master',
  },
  {
    'recipe': 'book_of_the_year',
    'year': '2005',
    'source_title': 'Matisse the Master',
    'title': 'Matisse: The Master',
  },
  {
    'recipe': 'biography',
    'year': '2006',
    'source_title': "Nabeel's Song : A Family Story of Survival in Iraq",
    'title': "Nabeel's Song: A Family Story of Survival in Iraq",
  },
  {
    'recipe': 'biography',
    'year': '2015',
    'source_title': 'The Invention of Nature',
    'title': (
      'The Invention of Nature: The Adventures of Alexander von Humboldt, '
      'the Lost Hero of Science'),
  },
  {
    'recipe': 'book_of_the_year',
    'year': '1980',
    'source_title': 'How Far Can You Go',
    'title': 'How Far Can You Go?',
  },
  {
    'recipe': 'book_of_the_year',
    'year': '2012',
    'source_title': 'Bring up the Bodies',
    'title': 'Bring Up the Bodies',
  },
  {
    'recipe': 'book_of_the_year',
    'year': '2019',
    'source_title': 'The Volunteer',
    'title': (
      'The Volunteer: The True Story of the Resistance Hero who Infiltrated '
      'Auschwitz'),
  },
)

AUTHOR_OVERRIDES = (
  {
    'recipe': 'childrens_book',
    'year': '1973',
    'title': "The Butterfly Ball and the Grasshopper's Feast",
    'authors': ['William Plomer'],
  },
  {
    'recipe': 'childrens_book',
    'year': '1974',
    'title': 'How Tom Beat Captain Najork and His Hired Sportsmen',
    'authors': ['Russell Hoban'],
  },
)


CORRECTIONS = {
  'schema_version': SCHEMA_VERSION,
  'coverage': COVERAGE,
  'expected_totals': EXPECTED_TOTALS,
  'replacement_years': REPLACEMENT_YEARS,
  'title_corrections': TITLE_CORRECTIONS,
  'author_overrides': AUTHOR_OVERRIDES,
}
