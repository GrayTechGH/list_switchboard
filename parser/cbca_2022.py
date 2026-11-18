"""Recover the image-only 2022 shortlist from CBCA's own Reading Time.

Only the category's explicit shortlist review links select works. The Notable
tables and bounded review headers supply creator metadata, never award status.
New Illustrator has no Notable table; its known finalists may use metadata
from other categories or their linked review headers.
"""

from urllib.parse import urljoin, urlsplit
import re

from bs4 import NavigableString

from .award_base import normalize_heading, normalize_line
from .cbca_sources import soup_for


SHORTLIST_URL = 'https://readingtime.cbca.org.au/announcing-the-2022-book-of-the-year-awards-shortlist/'
NOTABLES_URL = 'https://readingtime.cbca.org.au/announcing-the-2021-cbca-notable-books/'


def article(source, expected):
  soup = soup_for(source)
  for heading in soup.find_all('h1'):
    own = heading.find_parent('article')
    if own is not None and normalize_heading(heading.get_text(' ', strip=True)) == normalize_heading(expected):
      return own
  raise ValueError('CBCA Reading Time did not expose the expected own article heading.')


def category_for(parser, text):
  key = normalize_heading(text)
  if key == 'cbca new illustrator s award':
    return 'New Illustrator'
  if key == 'the eve pownall information book of the year':
    return 'Eve Pownall'
  return parser.category_from_text(text)


def shortlist_links(parser, source):
  own = article(source, 'Announcing the 2022 Book of the Year Awards Shortlist')
  category, reviews, selected = None, False, {}
  for node in own.find_all(['h2', 'p']):
    text = node.get_text(' ', strip=True)
    if node.name == 'h2':
      found = category_for(parser, text)
      if found:
        category, reviews = found, False
      elif normalize_heading(text) == 'reviews':
        reviews = True
      elif text:
        reviews = False
      continue
    if not reviews or category != parser.category:
      continue
    for link in node.find_all('a', href=True):
      title = normalize_line(re.sub(r'\s+review by\b.*$', '', link.get_text(' ', strip=True), flags=re.I))
      url = urljoin(SHORTLIST_URL, link['href'])
      if urlsplit(url).hostname not in ('readingtime.cbca.org.au', 'cbca.org.au', 'www.cbca.org.au'):
        raise ValueError('Unexpected host in CBCA shortlist review links.')
      if title:
        selected.setdefault(normalize_heading(title), (title, url))
  if len(selected) != 6:
    raise ValueError(f'CBCA 2022 {parser.category} did not expose six distinct shortlist works.')
  return selected


def notable_metadata(parser, source):
  own = article(source, 'Announcing the 2022 CBCA Notable Books')
  metadata = {}
  for table in own.find_all('table'):
    category = None
    for prior in table.find_all_previous(['h2', 'h3', 'h4', 'h5', 'p']):
      if prior.find_parent('article') is not own:
        break
      text = prior.get_text(' ', strip=True)
      if len(text) < 150 and (prior.name.startswith('h') or prior.find(['b', 'strong'])):
        category = category_for(parser, text)
        if category:
          break
    if category is None or (parser.category != 'New Illustrator' and category != parser.category):
      continue
    trs = table.find_all('tr')
    if not trs:
      continue
    headers = [normalize_heading(n.get_text(' ', strip=True)) for n in trs[0].find_all(['th', 'td'])]
    if not {'author', 'illustrator', 'title', 'isbn', 'publisher'} <= set(headers):
      raise ValueError('Unexpected CBCA Notable metadata table columns.')
    for tr in trs[1:]:
      cells = tr.find_all(['th', 'td'], recursive=False)
      if len(cells) != len(headers):
        raise ValueError('Incomplete CBCA Notable metadata table row.')
      row = dict(zip(headers, (normalize_line(n.get_text(' ', strip=True)) for n in cells)))
      title_cell = cells[headers.index('title')]
      title_link = title_cell.find('a', href=True)
      marked_title = title_link or title_cell.find(['i', 'em'])
      if marked_title is not None:
        row['title'] = normalize_line(marked_title.get_text(' ', strip=True))
      if not row['title']:
        continue
      if parser.category == 'New Illustrator':
        creator = row['illustrator'] or row['author']
        if row['illustrator'] and row['author']:
          creator += ', text by ' + row['author']
      elif headers[0] == 'illustrator':
        creator = row['illustrator']
        if row['author']:
          creator += ', text by ' + row['author']
      else:
        creator = row['author']
        if row['illustrator']:
          creator += ', illustrated by ' + row['illustrator']
      key = normalize_heading(row['title'])
      if creator and re.fullmatch(r'97[89]\d{10}', row['isbn']) and row['publisher']:
        value = (row['title'], creator)
        metadata.setdefault('title:' + key, set()).add(value)
        if title_link:
          metadata.setdefault('url:' + urljoin(NOTABLES_URL, title_link['href']).rstrip('/'), set()).add(value)
  return metadata


def review_creator(source, expected_title):
  own = article(source, expected_title)
  for heading in own.find_all(['h2', 'h3']):
    if not re.search(r'\bISBN\s*97[89]\d{10}', heading.get_text(' ', strip=True)):
      continue
    title = next((n for n in heading.find_all(['i', 'em'])
      if normalize_heading(n.get_text(' ', strip=True)) == normalize_heading(expected_title)), None)
    if title is None:
      continue
    prefix = []
    for child in heading.descendants:
      if child is title:
        break
      if isinstance(child, NavigableString):
        prefix.append(str(child))
    creator = normalize_line(''.join(prefix)).strip(' ,')
    creator = re.sub(r'\s*\((?:text|illustrator)\)', '', creator, flags=re.I)
    if creator:
      return creator
  raise ValueError('CBCA review has no complete bounded title/creator/ISBN header.')


def shortlist_rows(parser, source, fetch_url):
  selected = shortlist_links(parser, source)
  metadata = notable_metadata(parser, fetch_url(NOTABLES_URL))
  rows = []
  for key, (title, review_url) in selected.items():
    creators = metadata.get('url:' + review_url.rstrip('/')) or metadata.get('title:' + key, set())
    if len(creators) > 1:
      raise ValueError('Ambiguous creator metadata for a CBCA 2022 finalist.')
    if creators:
      canonical_title, creator = next(iter(creators))
      creator_url = NOTABLES_URL
    else:
      creator, creator_url = review_creator(fetch_url(review_url), title), review_url
      canonical_title = title
    row = parser.build_row(2022, parser.category, canonical_title, creator, 'shortlisted', SHORTLIST_URL)
    if row is None:
      raise ValueError('Incomplete CBCA 2022 finalist metadata.')
    row['author_source_url'] = creator_url
    if normalize_heading(canonical_title) != key:
      row['source_title'] = title
      row['title_source_url'] = creator_url
    rows.append(row)
  return rows
