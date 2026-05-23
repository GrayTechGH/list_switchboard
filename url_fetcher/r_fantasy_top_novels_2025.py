#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .reddit import UrlFetcherReddit


class UrlFetcherRFantasyTopNovels2025(UrlFetcherReddit):

  source_id = 'r_fantasy_top_novels_2025'
  NAME = 'r/Fantasy Top Novels 2025'
  REQUIRES_SERIES_MATCHING = True
  URL = 'https://www.reddit.com/r/Fantasy/comments/1jjif55/rfantasy_top_novels_2025_results/'
  FETCH_URLS = (
    'https://old.reddit.com/r/Fantasy/comments/1jjif55/rfantasy_top_novels_2025_results/',
    URL,
  )
  order = 10
  schemas = (
    {
      'headers': ('Rank', 'Series', 'Votes', 'Author', 'Rank Change'),
      'fields': ('position', 'title', 'votes', 'author', 'rank_change'),
    },
  )
