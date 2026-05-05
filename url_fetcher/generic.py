#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai


class UrlFetcherGeneric:

  source_id = ''
  NAME = ''
  URL = ''
  FETCH_URLS = ()
  order = 0
  options = {}
  schemas = ()

  @property
  def name(self):
    return self.NAME

  @property
  def display_url(self):
    return self.URL

  def primary_urls(self):
    return tuple(self.FETCH_URLS or ((self.URL,) if self.URL else ()))

  def fallback_urls(self, _url):
    return ()

  def fetch_urls(self):
    urls = []
    for url in self.primary_urls():
      self.add_unique_url(urls, url)
      for fallback_url in self.fallback_urls(url):
        self.add_unique_url(urls, fallback_url)
    return tuple(urls)

  def add_unique_url(self, urls, url):
    if url and url not in urls:
      urls.append(url)

  def fetch_and_parse(
      self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
      before_fetch=None, after_fetch=None, before_parse=None):
    last_error = None
    errors = []
    for url in self.fetch_urls():
      try:
        if before_fetch is not None:
          before_fetch(url)
        html = fetch_url(url)
        if after_fetch is not None:
          after_fetch(url, html)
        if before_parse is not None:
          before_parse(url)
        parsed = self.parse(
          html,
          fetch_url=fetch_url,
          sleep=sleep,
          fetch_error=fetch_error,
          log=log,
          progress=progress)
        parsed.setdefault('source_url', url)
        parsed.setdefault('match_series', self.options.get('match_series', True))
        return parsed
      except Exception as err:
        last_error = err
        errors.append(f'{url}: {err}')
    if last_error is not None:
      raise UrlFetcherError(
        'Could not fetch or parse the imported list.\n\nTried:\n- ' + '\n- '.join(errors))
    raise UrlFetcherError('The URL fetcher did not define a URL to import.')

  def parse(self, _html, **_kwargs):
    raise NotImplementedError


class UrlFetcherError(Exception):
  pass
