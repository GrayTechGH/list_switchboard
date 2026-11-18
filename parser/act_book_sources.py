"""Read Libraries ACT's labelled archive and bounded result tables.

Archive year labels and annual headings establish the award year. Migrated URL
digits and recycled table IDs do not. Catalogue-linked and unlinked italic
titles share author / title / publisher cells, outside judge/synopsis prose.
"""

import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, NavigableString, UnicodeDammit


ARCHIVE_PATH = '/find/history/frequentlyaskedquestions/Events/literaryawards/book_of_the_year'


def soup_for(html):
  if isinstance(html, bytes):
    html = UnicodeDammit(html, is_html=True).unicode_markup
  return BeautifulSoup(html or '', 'html.parser')


def official_url(href, base_url):
  target = urlsplit(urljoin(base_url, href))
  if target.scheme not in ('http', 'https') or target.netloc not in ('www.library.act.gov.au', 'library.act.gov.au'):
    return None
  if not (target.path.startswith(ARCHIVE_PATH + '/') or re.fullmatch(ARCHIVE_PATH + r'_(?:19|20)\d{2}', target.path)):
    return None
  return target._replace(scheme='https', netloc='www.library.act.gov.au', fragment='', query='').geturl().rstrip('/')


def content_root(soup):
  return soup.find(id='main') or soup.find('main') or soup.find('article')


def validate_source(html, url):
  soup = soup_for(html)
  root = content_root(soup)
  if root is None:
    raise ValueError('Libraries ACT source had no main award content.')
  headings = soup.find_all(['h1', 'h2'])
  if not any('act book of the year' in h.get_text(' ', strip=True).casefold() for h in headings):
    publisher = soup.find('meta', attrs={'name': 'dcterms.publisher'})
    # The 2010 page has only numeric headings, but retains the official
    # publisher metadata, annual path and structured result tables.
    if (official_url(url, url) and publisher and
        publisher.get('content', '').casefold() == 'libraries act' and
        any(re.fullmatch(r'(?:19|20)\d{2}', h.get_text(' ', strip=True)) for h in soup.find_all('h1')) and
        root.find('table')):
      return root
    # Legacy overview callers supply a bare list of labelled annual links.
    if url.rstrip('/').endswith(ARCHIVE_PATH) and discover_archive(html, url, validate=False)['years']:
      return root
    raise ValueError('Libraries ACT response was not an award page.')
  return root


def discover_archive(html, base_url, validate=True):
  soup = soup_for(html)
  root = validate_source(html, base_url) if validate else content_root(soup)
  if root is None:
    raise ValueError('Libraries ACT archive had no main content.')
  years, covers = {}, {}
  for link in root.find_all('a', href=True):
    if link.find_parent(['nav', 'footer']):
      continue
    label = link.get_text(' ', strip=True)
    if not label and 'shortlist' in link.get('title', '').casefold():
      label = link['title']
    match = re.search(r'\b(?:19|20)\d{2}\b', label)
    url = official_url(link['href'], base_url)
    if match is None or url is None:
      continue
    year = int(match[0])
    if url not in years.setdefault(year, []):
      years[year].append(url)
    cell = link.find_parent('td')
    if cell:
      for image in cell.find_all('img'):
        cover = [image.get('alt', ''), image.get('title', ''), image.get('src', '')]
        if cover not in covers.setdefault(year, []):
          covers[year].append(cover)
  return {'years': years, 'covers': covers, 'modern': soup.find(id='main') is not None}


def stage(parser, text):
  # Only the visible label supplies a stage/year; table IDs are often stale.
  text = re.sub(r'\b(?:19|20)\d{2}\b', '', text).strip()
  label = text.casefold().replace('\u2019', "'")
  if label == "judges' choice":
    return 'winner'
  if label in ("people's choice", "highly commended and people's choice"):
    return 'shortlisted'
  return parser.result_from_heading(text)


def read_year(parser, html, url, expected_year):
  soup = soup_for(html)
  root = validate_source(html, url)
  declared = []
  for heading in soup.find_all('h1'):
    found = parser.year_from_text(heading.get_text(' ', strip=True))
    if found is not None:
      declared.append(found)
  for heading in root.find_all('h2'):
    text = heading.get_text(' ', strip=True)
    if re.fullmatch(r'(?:19|20)\d{2}', text):
      declared.append(int(text))
  if not declared or any(year != expected_year for year in declared):
    raise ValueError('Libraries ACT annual page returned another or missing award year.')
  rows, notes = [], []
  current = None
  tables = root.find_all('table')
  if not tables:
    rows = parser.parse_year_page(html, url, default_year=expected_year)
    return {'rows': rows, 'notes': [] if rows else ['Libraries ACT annual page had no result roster.'], 'complete': bool(rows)}
  for node in root.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'table']):
    if node.find_parent('table'):
      continue
    if node.name != 'table':
      text = node.get_text(' ', strip=True)
      found = stage(parser, text)
      if found:
        current = found
      elif node.name in ('h2', 'h3') and not re.fullmatch(r'(?:19|20)\d{2}', text):
        current = None
      # H4 synopsis/citation headings separate books inside one result section.
      # Only the book tables are read, so those headings must not end the stage.
      continue
    labels = [stage(parser, h.get_text(' ', strip=True)) for h in node.find_all('th')]
    result = next((label for label in labels if label), current)
    if result is None:
      if node.find(['em', 'i']) is not None:
        notes.append('Libraries ACT book table had no visible result section.')
      continue
    for cell in node.find_all('td'):
      if cell.find_parent('table') is not node:
        continue
      marker = cell.find(['em', 'i'])
      if marker is None:
        marker = next((a for a in cell.find_all('a', href=True) if
          (('spydus' in (urlsplit(urljoin(url, a['href'])).hostname or '')) or
           urlsplit(urljoin(url, a['href'])).hostname in ('librarycatalogue.act.gov.au', 'www.librarycatalogue.act.gov.au')) and
          a.get_text(' ', strip=True)), None)
      if marker is None:
        # Image-only and empty layout cells are not missing book records.
        if cell.get_text(' ', strip=True) and cell.find('br'):
          notes.append('Libraries ACT result cell had no marked book title.')
        continue
      block = cell
      before = []
      for item in block.descendants:
        if item is marker:
          break
        if isinstance(item, NavigableString):
          if item.parent.name == 'p' and stage(parser, item.parent.get_text(' ', strip=True)):
            continue
          before.append(str(item))
      title = parser.clean_title(marker.get_text(' ', strip=True))
      author = parser.clean_author(' '.join(before))
      if not title or not author:
        notes.append('Libraries ACT result cell had incomplete title/author metadata.')
        continue
      link = marker if marker.name == 'a' else marker.find('a', href=True)
      source = urljoin(url, link['href']) if link else url
      row = parser.row(expected_year, title, author, result, source)
      authors = [part.strip() for part in re.split(r'\s+(?:and|&)\s+', author) if part.strip()]
      if len(authors) > 1:
        row['authors'] = authors
      rows.append(row)
  if not rows:
    notes.append('Libraries ACT annual page had no usable result tables.')
  return {'rows': parser.dedupe_rows(rows), 'notes': notes, 'complete': bool(rows) and not notes}
