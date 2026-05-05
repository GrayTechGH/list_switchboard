#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

try:
  from calibre_plugins.list_switchboard.parser.reddit import parse_reddit_results
except ImportError:
  from parser.reddit import parse_reddit_results

from .generic import UrlFetcherGeneric


class UrlFetcherReddit(UrlFetcherGeneric):

  parser = 'reddit_results'

  def parse(self, html, **_kwargs):
    return parse_reddit_results(html, self.NAME, self.URL, self.schemas)
