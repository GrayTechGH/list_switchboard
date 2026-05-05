#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .r_fantasy_top_novels_2025 import UrlFetcherRFantasyTopNovels2025
from .r_fantasy_top_self_published_novels_2024 import (
  UrlFetcherRFantasyTopSelfPublishedNovels2024,
)
from .r_fantasy_top_standalone_novels_2024 import (
  UrlFetcherRFantasyTopStandaloneNovels2024,
)
from .sword_and_laser import UrlFetcherSwordAndLaser


URL_FETCHER_CLASSES = (
  UrlFetcherRFantasyTopNovels2025,
  UrlFetcherRFantasyTopStandaloneNovels2024,
  UrlFetcherRFantasyTopSelfPublishedNovels2024,
  UrlFetcherSwordAndLaser,
)


def available_url_fetchers():
  return tuple(fetcher_class() for fetcher_class in URL_FETCHER_CLASSES)
