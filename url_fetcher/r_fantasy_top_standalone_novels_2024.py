#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .reddit import UrlFetcherReddit


class UrlFetcherRFantasyTopStandaloneNovels2024(UrlFetcherReddit):

  source_id = 'r_fantasy_top_standalone_novels_2024'
  NAME = 'r/Fantasy Top Standalone Novels 2024'
  URL = 'https://www.reddit.com/r/Fantasy/comments/1agicpw/rfantasys_2024_top_standalone_novel_poll_results/'
  FETCH_URLS = (
    'https://old.reddit.com/r/Fantasy/comments/1agicpw/rfantasys_2024_top_standalone_novel_poll_results/',
    URL,
  )
  order = 20
  schemas = (
    {
      'headers': ('Rank', 'Title', 'Author', 'Votes', 'Rank change'),
      'fields': ('position', 'title', 'author', 'votes', 'rank_change'),
    },
  )
