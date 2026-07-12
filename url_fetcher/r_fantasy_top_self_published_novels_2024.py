#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .reddit import UrlFetcherReddit


class UrlFetcherRFantasyTopSelfPublishedNovels2024(UrlFetcherReddit):

  source_id = 'r_fantasy_top_self_published_novels_2024'
  NAME = 'r/Fantasy Top Self-Published Novels 2024'
  URL = 'https://www.reddit.com/r/Fantasy/comments/1g3lo7l/big_list_rfantasys_top_selfpublished_novels_2024/'
  WAYBACK_URL = (
    'https://web.archive.org/web/20250327171534id_/'
    'https://www.reddit.com/r/Fantasy/comments/1g3lo7l/'
    'big_list_rfantasys_top_selfpublished_novels_2024/'
  )
  WAYBACK_CAPTURE_DATE = '2025-03-27'
  FETCH_URLS = (
    'https://old.reddit.com/r/Fantasy/comments/1g3lo7l/big_list_rfantasys_top_selfpublished_novels_2024/',
    WAYBACK_URL,
    URL,
  )
  order = 30
  schemas = (
    {
      'headers': (
        'Rank / Change',
        'Book/series',
        'Author',
        'Number of Votes',
        'GR ratings (the first book in the series)',
      ),
      'fields': ('position', 'title', 'author', 'votes', 'ratings'),
    },
  )
