#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_ROMANCE,
  UrlFetcherGeneric,
)


class UrlFetcherRomanticTimesReviewersChoiceRomance(UrlFetcherGeneric):

  source_id = 'romantic_times_reviewers_choice_romance'
  NAME = (
    "Romantic Times Reviewers' Choice Awards - Romance Categories "
    '(discontinued)')
  URL = (
    'https://web.archive.org/cdx?url=www.rtbookreviews.com'
    '/blog/86292/2015-rt-reviewers-choice-award-nominees-mysterysuspensethriller-and-romantic-suspense'
    '&output=json&fl=timestamp,original,statuscode,mimetype,digest'
    '&filter=statuscode:200&collapse=digest&limit=8')
  ARTICLE_URL = (
    'https://web.archive.org/web/*/http://www.rtbookreviews.com/tags/rt-awards')
  order = 250
  options = {'match_series': False}
  FILTER_CATEGORIES = (CATEGORY_ROMANCE, CATEGORY_REGIONAL_NATIONAL_AWARDS)

  @property
  def display_url(self):
    return self.ARTICLE_URL

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.romantic_times_awards import ( # type: ignore
        RomanticTimesReviewersChoiceParser,
      )
    except ImportError:
      from parser.romantic_times_awards import RomanticTimesReviewersChoiceParser
    return RomanticTimesReviewersChoiceParser()

  def parse(self, html, fetch_url=None, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME, fetch_url=fetch_url)
