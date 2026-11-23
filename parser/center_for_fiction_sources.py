"""Bounded official award cards and older inline Winner/Shortlist rosters.

The editorial article contains book cards followed by people biographies.
Recommendations elsewhere in main are not award rows. A URL named long-list
may now contain a settled annual ballot: rendered result labels own the stage.
"""

import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, UnicodeDammit


WINNERS_URL = 'https://centerforfiction.org/book-recs/first-novel-prize-winners/'
ANNUAL_PATH = re.compile(r'^/book-recs/((?:19|20)\d{2})-first-novel-prize(?:-[a-z0-9]+)*/?$')


def soup_for(html):
  if isinstance(html, bytes):
    html = UnicodeDammit(html, is_html=True).unicode_markup
  return BeautifulSoup(html or '', 'html.parser')


def annual_url(value, base_url):
  target = urlsplit(urljoin(base_url, value))
  match = ANNUAL_PATH.fullmatch(target.path)
  if target.scheme not in ('http', 'https') or target.netloc not in ('centerforfiction.org', 'www.centerforfiction.org') or not match:
    return None
  return int(match[1]), target._replace(scheme='https', netloc='centerforfiction.org', query='', fragment='').geturl().rstrip('/') + '/'


def source_root(html, url):
  soup = soup_for(html)
  main = soup.find('main')
  if main is None:
    raise ValueError('Official Center for Fiction source has no main content.')
  root = main.select_one('article.editorial') or main
  heading = root.find('h1')
  title = heading.get_text(' ', strip=True) if heading else ''
  if not re.search(r'\bfirst novel prize\b', title, re.I):
    raise ValueError('Official Center for Fiction source returned another article.')
  annual = annual_url(url, url)
  heading_year = re.search(r'\b(?:19|20)\d{2}\b', title)
  if annual and (not heading_year or int(heading_year[0]) != annual[0]):
    raise ValueError('Official Center for Fiction annual source returned another award year.')
  if url.rstrip('/') == WINNERS_URL.rstrip('/') and not re.search(r'\bwinners\b', title, re.I):
    raise ValueError('Official Center for Fiction winner history was not returned.')
  return root, title, annual[0] if annual else None


def discover_links(html, url, validate=True):
  if validate:
    root, _title, _year = source_root(html, url)
  else:
    soup = soup_for(html)
    root = soup.find('main') or soup
  links = []
  for link in root.find_all('a', href=True):
    if link.find_parent(['nav', 'footer']):
      continue
    item = annual_url(link['href'], url)
    if item and item not in links:
      links.append(item)
  return links


def stage_text(parser, text):
  text = re.sub(r'^\s*(?:19|20)\d{2}\s+', '', text)
  # The official 2021 Brood card spells its standalone status Shorlisted.
  if text.strip().casefold() == 'shorlisted':
    return 'shortlisted'
  return parser.result_from_text(text)


def read_source(parser, html, url):
  root, title, year = source_root(html, url)
  history = url.rstrip('/') == WINNERS_URL.rstrip('/')
  rows, notes = [], []
  default_stage = ''
  if year:
    if re.search(r'\bshort\s*list\b', title, re.I):
      default_stage = 'shortlisted'
    elif re.search(r'\blong\s*list\b', title, re.I):
      default_stage = 'longlisted'

  # Inline historic rosters and modern announcement bullet lists live in text
  # components, not in book synopses or people biographies.
  for content in root.select('.editorial-content-text'):
    stage = default_stage
    for node in content.find_all(['p', 'h2', 'h3', 'ul', 'ol']):
      if node.find_parent(['li', 'ul', 'ol']):
        continue
      if node.name not in ('ul', 'ol'):
        explicit = stage_text(parser, node.get_text(' ', strip=True))
        if explicit:
          stage = explicit
        continue
      if stage not in ('winner', 'shortlisted') or not year:
        continue
      for item in node.find_all('li', recursive=False):
        book, author = parser.parse_text_entry(item.get_text(' ', strip=True))
        if not book or not author:
          notes.append('Official First Novel Prize inline roster had an incomplete title/author row.')
          continue
        rows.append(parser.row(year, book, author, stage, parser.first_link_url(item, url) or url))

  cards = root.select('.featured-books li.featured-books-item')
  for card in cards:
    book_heading = card.find(['h2', 'h3'])
    author_node = next((p for p in card.find_all('p', class_='detail')
      if re.match(r'^By(?:\s|:)', p.get_text(' ', strip=True), re.I)), None)
    container = card.find_parent(class_='featured-books')
    section_heading = next((h for h in container.find_all('h2') if not h.find_parent('li')), None)
    result = stage_text(parser, section_heading.get_text(' ', strip=True)) if section_heading else default_stage
    result_year = year
    for node in card.select('.rich-text > p')[:1]:
      text = node.get_text(' ', strip=True)
      if history:
        label = node.find('strong', recursive=False)
        if label:
          text = label.get_text(' ', strip=True)
      explicit = stage_text(parser, text)
      if explicit:
        result = explicit
        if history:
          result_year = parser.year_from_text(text)
        break
    if result == 'longlisted':
      continue
    if not result:
      notes.append('Official First Novel Prize book card had no result stage.')
      continue
    if not result_year or not book_heading or not author_node:
      notes.append('Official First Novel Prize book card had incomplete year/title/author metadata.')
      continue
    if section_heading and not history:
      declared = parser.year_from_text(section_heading.get_text(' ', strip=True))
      if declared and declared != year:
        notes.append('Official First Novel Prize book section declared another award year.')
        continue
    book = parser.clean_title(book_heading.get_text(' ', strip=True))
    author = parser.clean_author(author_node.get_text(' ', strip=True))
    if not book or not author:
      notes.append('Official First Novel Prize book card had empty title/author metadata.')
      continue
    rows.append(parser.row(result_year, book, author, result, parser.first_link_url(book_heading, url) or url))
  if history and any(row['result'] != 'winner' for row in rows):
    notes.append('Official First Novel Prize winner history contained an unexpected result stage.')
  empty_longlist = not rows and bool(cards) and default_stage == 'longlisted'
  if not rows and not empty_longlist:
    notes.append('Official First Novel Prize source had no usable winner/shortlist roster.')
  return {'rows': parser.dedupe_rows(rows), 'notes': notes,
    'complete': not notes and (bool(rows) or empty_longlist)}
