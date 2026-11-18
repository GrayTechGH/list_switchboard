"""Read bounded Booker year cards, excluding navigation, news and translators.

Modern year pages repeat their books in hero navigation, winner features,
shortlists and longlists. Only the labelled shortlist and an explicit winner
feature for this year establish results. Author and translator credits share
the same URL shape, so their By/Translated by roles must remain distinct.
"""

import re
import datetime
from urllib.parse import urljoin, urlsplit, parse_qs

from bs4 import BeautifulSoup, UnicodeDammit

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError


HOST = 'thebookerprizes.com'
INDEX_PATH = '/the-booker-library/prize-years'


def soup_for(html):
  if isinstance(html, bytes):
    html = UnicodeDammit(html, is_html=True).unicode_markup
  return BeautifulSoup(html or '', 'html.parser')


def official_url(value, base_url):
  url = urlsplit(urljoin(base_url, value))
  if url.scheme not in ('http', 'https') or url.hostname != HOST or url.port:
    return None
  return url._replace(scheme='https', query='', fragment='').geturl().rstrip('/')


def index_links(html, base_url, year_pattern):
  soup = soup_for(html)
  main = soup.find('main')
  if main is None or not any(h.get_text(' ', strip=True).lower() == 'prize years'
                             for h in main.find_all('h1')):
    raise ValueError('Official Booker overview did not expose its prize-year listing.')
  years, pages = [], []
  listing_present = False
  # Each listing card is a year; site-wide navigation and filter options are not.
  for article in main.find_all('article'):
    for link in article.find_all('a', href=True):
      url = official_url(link['href'], base_url)
      if url and re.fullmatch(INDEX_PATH + r'/(?:international/)?(?:19|20)\d{2}', urlsplit(url).path):
        listing_present = True
      if url and re.search(year_pattern, urlsplit(url).path) and url not in years:
        years.append(url)
  if not listing_present:
    raise ValueError('Official Booker overview had no rendered prize-year cards.')
  for nav in main.find_all('nav'):
    if 'pager' not in nav.get('class', []) and 'pagination' not in str(nav.get('aria-labelledby', '')).lower():
      continue
    for link in nav.find_all('a', href=True):
      target = urlsplit(urljoin(base_url, link['href']))
      query = parse_qs(target.query)
      if (target.scheme in ('http', 'https') and target.hostname == HOST and
          not target.port and target.path.rstrip('/') == INDEX_PATH and
          set(query) == {'page'} and len(query['page']) == 1 and
          re.fullmatch(r'\d+', query['page'][0])):
        number = int(query['page'][0])
        # Page zero is already the root request. Discover all other real pages
        # afresh; a cached offset is never evidence that older years are covered.
        if number and number not in pages:
          pages.append(number)
  return years, pages


def page_identity(html, url):
  soup = soup_for(html)
  main = soup.find('main')
  year_match = re.fullmatch(INDEX_PATH + r'/(international/)?((?:19|20)\d{2})', urlsplit(url).path.rstrip('/'))
  if main is None or year_match is None:
    raise ValueError('Official Booker response was not a prize-year page.')
  international, year = bool(year_match[1]), int(year_match[2])
  headings = [h.get_text(' ', strip=True) for h in main.find_all('h1')]
  expected = re.compile(r'^(?:The )?(?:Man Booker International|(?:Bukhman )?International Booker|(?:Man )?Booker) Prize ' + str(year) + r'$', re.I)
  if not headings or any(not expected.fullmatch(h) or ('international' in h.lower()) != international for h in headings):
    raise ValueError('Official Booker page returned another award or year.')
  return main, year, international


def author_credit(node):
  for label in node.find_all('dt'):
    if label.get_text(' ', strip=True).lower() == 'by':
      credit = label.find_next_sibling('dd')
      if credit:
        return credit.get_text(' ', strip=True)
  for paragraph in node.find_all('p'):
    text = paragraph.get_text(' ', strip=True)
    if re.match(r'^By\s+', text, re.I):
      return re.sub(r'^By\s+', '', text, flags=re.I)
  return ''


def modern_rows(parser, html, url, category, fetch_url, notes):
  main, year, international = page_identity(html, url)
  if international and year < 2016:
    if not empty_year(main, year, international):
      notes.append(f'Official International Booker {year} page had no author-prize winner section.')
    return []
  shortlist = main.find('section', attrs={'aria-labelledby': 'section-section-shortlisted-books-title'})
  # Old plain-heading fixtures and pages keep their existing reader. Rendered
  # modern pages must not fall through to its page-wide first-link deduplication.
  modern = shortlist is not None or main.find(class_='c-booker-grid') is not None
  if not modern:
    return None
  rows = []

  def add(node, result):
    links = [link for link in node.find_all('a', href=True)
      if (official_url(link['href'], url) or '').startswith('https://' + HOST + '/the-booker-library/books/')]
    link = next((link for link in links if link.find(['h2', 'h3', 'h4'])), None)
    if link is None:
      notes.append(f'Official Booker {year} result card had no titled book link.')
      return
    source_url = official_url(link['href'], url)
    title = parser.clean_title(link.get_text(' ', strip=True))
    author = parser.clean_author(author_credit(node))
    if not author and fetch_url is not None:
      try:
        detail_title, detail_author = parser.title_author_from_detail(fetch_url(source_url))
        title, author = detail_title or title, detail_author
      except (ImportCancelledError, CamoufoxRequiredError):
        raise
      except Exception as err:
        notes.append(f'Official Booker detail page failed for {source_url}: {err}')
    if not title or not author:
      notes.append(f'Official Booker {year} result card had incomplete title/author metadata: {source_url}')
      return
    rows.append({'award_year': str(year), 'title': title, 'author': author,
      'result': result, 'source_url': source_url, 'category': category})

  if shortlist is not None:
    cards = shortlist.find_all('article')
    if not cards:
      notes.append(f'Official Booker {year} shortlist had no book cards.')
    for card in cards:
      winner = any(n.get_text(' ', strip=True).lower() == 'prize winner' for n in card.find_all('span'))
      add(card, 'winner' if winner else 'shortlisted')
  # Winner features are outside section tags and can precede the shortlist.
  # Their explicit Winner of link must identify this exact award-year URL.
  for grid in main.select('div.group.c-booker-grid'):
    if grid.find_parent('section') is shortlist and shortlist is not None:
      continue
    if any((official_url(link['href'], url) == official_url(url, url)) and
           link.parent.get_text(' ', strip=True).lower().startswith('winner of ')
           for link in grid.find_all('a', href=True)):
      add(grid, 'winner')
  if not rows and not empty_year(main, year, international):
    notes.append(f'Official Booker {year} page had no usable winner/shortlist books.')
  return rows


def empty_year(main, year, international):
  if international and year < 2016:
    # The earlier award honours a writer's body of work, not a specific book.
    winner = next((h for h in main.find_all('h2') if h.get_text(' ', strip=True).lower() == 'winner'), None)
    if winner:
      section = winner.find_parent('section')
      return bool(section and section.find('a', href=re.compile(r'^/the-booker-library/authors/')) and
                  not section.find('a', href=re.compile(r'^/the-booker-library/books/')))
  if year >= datetime.datetime.now().year:
    text = main.get_text(' ', strip=True)
    return bool(re.search(r'entries (?:are |now )?open|submissions (?:are |now )?open|judges|judging panel', text, re.I) and
                main.find('section', attrs={'aria-labelledby': 'section-section-shortlisted-books-title'}) is None and
                not main.select('div.group.c-booker-grid a[href*="/the-booker-library/books/"]'))
  return False


def valid_empty_year(html, url, year):
  main, actual, international = page_identity(html, url)
  return actual == year and empty_year(main, year, international)
