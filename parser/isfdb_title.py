"""Read explicit ISFDB translation links and bounded title-record metadata.

Title records have a ContentBox containing labelled fields, separate from
publication lists, notes, and other title/author links elsewhere on the page.
"""

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag


def title_id(url):
  parsed = urlparse(url or '')
  if not (parsed.scheme in ('http', 'https')
      and (parsed.hostname or '').casefold() in ('www.isfdb.org', 'isfdb.org')
      and parsed.path == '/cgi-bin/title.cgi' and re.fullmatch(r'\d+', parsed.query)):
    return ''
  return parsed.query


def original_link(html, base_url):
  soup = BeautifulSoup(html, 'html.parser')
  for tooltip in soup.select('.tooltiptext, .mouseover'):
    tooltip.decompose()
  for link in soup.find_all('a', href=True):
    previous = link.find_previous(string=True)
    if isinstance(previous, NavigableString) and re.search(
        r'\btranslation of\s*$', str(previous), re.I):
      url = urljoin(base_url, link['href'])
      if title_id(url):
        prefix = []
        for text in soup.descendants:
          if text is previous:
            prefix.append(re.sub(r'\(?\s*translation of\s*$', '', str(text), flags=re.I))
            break
          if isinstance(text, NavigableString):
            prefix.append(str(text))
        return {'id': title_id(url), 'url': url, 'title': link.get_text(' ', strip=True),
          'edition_title': ' '.join(' '.join(prefix).split())}
  return None


def parse_title_record(html, url, require_complete=True):
  expected = title_id(url)
  if not expected:
    raise ValueError('Not an ISFDB title-record URL.')
  soup = BeautifulSoup(html, 'html.parser')
  for tooltip in soup.select('.tooltiptext, .mouseover'):
    tooltip.decompose()
  box = next((node for node in soup.select('div.ContentBox')
    if any(label.get_text(' ', strip=True) == 'Title:'
      for label in node.find_all(['b', 'strong'], recursive=False))), None)
  if box is None:
    raise ValueError('ISFDB did not return title metadata.')
  record = box.select_one('span.recordID')
  record_id = re.search(r'\bTitle Record\s*#\s*(\d+)\b', record.get_text(' ', strip=True)) if record else None
  if record_id is None or record_id.group(1) != expected:
    raise ValueError('ISFDB returned a different title record.')
  fields = {}
  for label in box.find_all(['b', 'strong'], recursive=False):
    key = label.get_text(' ', strip=True).rstrip(':')
    fragments = []
    for sibling in label.next_siblings:
      if isinstance(sibling, Tag) and (sibling.name in ('br', 'b', 'strong')
          or (sibling.name == 'div' and 'tooltip' not in sibling.get('class', ()))):
        break
      if isinstance(sibling, Tag) and 'recordID' in sibling.get('class', ()):
        continue
      fragments.append(str(sibling))
    fields[key] = BeautifulSoup(''.join(fragments), 'html.parser')
  title = fields.get('Title')
  authors = fields.get('Author', fields.get('Authors'))
  language = fields.get('Language')
  names = []
  if authors:
    for link in authors.find_all('a', href=True):
      target = urlparse(urljoin(url, link['href']))
      if (target.hostname or '').casefold() in ('www.isfdb.org', 'isfdb.org') and target.path == '/cgi-bin/ea.cgi':
        name = link.get_text(' ', strip=True)
        if name and name not in names:
          names.append(name)
  if require_complete and (title is None or not title.get_text(' ', strip=True)
      or not names or language is None):
    raise ValueError('ISFDB title metadata is missing title, authors or language.')
  english_variants = []
  for table in soup.select('table.variantscolumn'):
    headers = [cell.get_text(' ', strip=True) for cell in table.find_all('th')]
    if 'Language' not in headers or 'Title' not in headers:
      continue
    language_index, title_index = headers.index('Language'), headers.index('Title')
    for row in table.find_all('tr'):
      cells = row.find_all('td', recursive=False)
      if len(cells) <= max(language_index, title_index):
        continue
      if cells[language_index].get_text(' ', strip=True).casefold() != 'english':
        continue
      for link in cells[title_index].find_all('a', href=True):
        target = urljoin(url, link['href'])
        if title_id(target) and not any(v['url'] == target for v in english_variants):
          english_variants.append({'url': target, 'title': link.get_text(' ', strip=True)})
  return {'id': expected, 'url': url, 'title': title.get_text(' ', strip=True) if title else '',
    'authors': names, 'language': language.get_text(' ', strip=True) if language else '',
    'english_variants': english_variants}
