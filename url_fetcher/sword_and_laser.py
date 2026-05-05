#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from urllib.parse import parse_qs, quote, unquote, urlparse

from .generic import UrlFetcherGeneric


class UrlFetcherSwordAndLaser(UrlFetcherGeneric):

  source_id = 'sword_and_laser_book_list'
  NAME = 'Sword and Laser'
  URL = 'https://swordandlaser.fandom.com/wiki/Book_List'
  FETCH_URLS = (
    'https://swordandlaser.fandom.com/api.php?action=parse&page=Book_List&prop=text&format=json',
  )
  order = 40
  options = {
    'include_march_madness': True,
    'fetch_delay_seconds': 1.5,
    'match_series': False,
  }
  schemas = (
    {
      'headers': ('Title', 'Author(s)', 'Publisher', 'Month Read', 'Seq'),
      'fields': ('title', 'author', 'publisher', 'month_read', 'position'),
    },
  )

  def fallback_urls(self, url):
    if 'swordandlaser.fandom.com' not in url:
      return ()
    parsed = urlparse(url)
    title = ''
    if parsed.path.endswith('/api.php'):
      title = parse_qs(parsed.query).get('page', [''])[0]
    elif '/wiki/' in parsed.path:
      title = parsed.path.rsplit('/wiki/', 1)[-1]
    if not title:
      return ()
    title = quote(unquote(title).replace(' ', '_'), safe='')
    api_url = f'https://swordandlaser.fandom.com/api.php?action=parse&page={title}&prop=text&format=json'
    urls = (
      f'https://swordandlaser.fandom.com/wiki/{title}',
      f'https://swordandlaser.fandom.com/wiki/{title}?action=raw',
      f'https://swordandlaser.fandom.com/wiki/Special:Export/{title}',
    )
    if url != api_url:
      urls = (api_url,) + urls
    return urls

  def parse(self, html, fetch_url=None, sleep=None, fetch_error=None, log=None, progress=None):
    try:
      from calibre_plugins.list_switchboard.parser.sword_and_laser import parse_sword_and_laser_book_list
    except ImportError:
      from parser.sword_and_laser import parse_sword_and_laser_book_list

    return parse_sword_and_laser_book_list(
      self,
      html,
      fetch_url=fetch_url,
      sleep=sleep,
      fetch_error=fetch_error,
      log=log,
      progress=progress)
