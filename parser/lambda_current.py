"""Read named Elementor category sections with publication-year attribution.

Finalists use marked italic author fields; winners use separate book/author
headings. Their widget wrappers are not siblings of the category heading. The
own article introduction/H1 supplies the ceremony year, not stale SEO metadata
or footer dates. Published years remain one year before that ceremony.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, UnicodeDammit

try:
  from calibre_plugins.list_switchboard.parser.award_base import is_author_suffix, normalize_heading
except ImportError:
  from .award_base import is_author_suffix, normalize_heading


def soup_for(html):
  if isinstance(html, bytes):
    html = UnicodeDammit(html, is_html=True).unicode_markup
  return BeautifulSoup(html or '', 'html.parser')


def modern_page(html):
  return soup_for(html).select_one('div.elementor') is not None


def author_field(parser, node):
  author = parser.clean_author(node.get_text(' ', strip=True))
  final = author.rsplit(' ', 1)[-1]
  if author.endswith('.') and not is_author_suffix(final) and not re.search(r'\b[A-Z]\.$', author):
    author = author[:-1]
  return author


def read_current(parser, html, url, kind):
  soup = soup_for(html)
  headings = [h for h in soup.find_all(['h2', 'h3']) if parser.is_romance_category(h.get_text(' ', strip=True))]
  if not headings:
    raise ValueError('Lambda official page had no romance category headings.')
  root = headings[0].find_parent('div', class_='elementor')
  if root is None:
    raise ValueError('Lambda official article did not expose its Elementor content.')
  cycle_years = set()
  intro = []
  page_heading = soup.find('h1')
  if page_heading:
    found = parser.year_from_text(page_heading.get_text(' ', strip=True))
    if found:
      cycle_years.add(found)
  for node in root.find_all(['h1', 'h2', 'p']):
    text = node.get_text(' ', strip=True)
    if node.name == 'h2' and not re.search(r'\b(?:congratulations|lammy|lambda literary award)', text, re.I):
      break
    intro.append(text)
    for match in re.finditer(r'\b((?:19|20)\d{2})\s+(?:Lammy|Lammys|Lambda Literary Award)', text, re.I):
      cycle_years.add(int(match[1]))
  if len(cycle_years) != 1:
    raise ValueError('Lambda official article had no unambiguous ceremony year.')
  cycle = cycle_years.pop()
  dated = parser.year_from_text(url)
  if dated and dated != cycle:
    raise ValueError('Lambda official article returned another ceremony year.')
  year = cycle - 1
  rows, notes, categories = [], [], []
  for heading in headings:
    if heading.find_parent('div', class_='elementor') is not root:
      continue
    category = parser.clean_category(heading.get_text(' ', strip=True))
    section = heading.find_parent('section')
    if section is None:
      notes.append('Lambda romance heading had no bounded category section.')
      continue
    peers = [h for h in section.find_all(['h2', 'h3']) if parser.is_romance_category(h.get_text(' ', strip=True))]
    if len(peers) != 1:
      notes.append('Lambda category section contained ambiguous peer categories.')
      continue
    categories.append(category)
    if kind == 'finalists':
      items = section.find_all('li')
      if not items:
        notes.append(f'Lambda {category} finalist section had no roster items.')
      for image in section.find_all('img', alt=True):
        declared = re.search(r'\b(five|six|5|6)\b.*\bfinalists\b', image['alt'], re.I)
        if declared:
          count = {'five': 5, 'six': 6, '5': 5, '6': 6}[declared[1].lower()]
          if len(items) != count:
            notes.append(f'Lambda {category} finalist roster did not match its declared count.')
      for item in items:
        title_link = item.find('a', href=True)
        credit = next((tag for tag in item.find_all(['i', 'em']) if tag.find_parent('a') is None), None)
        text = item.get_text(' ', strip=True)
        if credit is None or '//' not in text:
          notes.append(f'Lambda {category} finalist row had incomplete marked title/author metadata.')
          continue
        title = parser.clean_title(title_link.get_text(' ', strip=True) if title_link else text.split('//', 1)[0])
        author = author_field(parser, credit)
        if not title or not author:
          notes.append(f'Lambda {category} finalist row had empty title/author metadata.')
          continue
        rows.append({'award_year': str(year), 'category': category, 'title': title,
          'author': author, 'result': 'shortlisted', 'source_url': urljoin(url, title_link['href']) if title_link else url})
    else:
      book = next((h for h in section.find_all(['h2', 'h3']) if h is not heading), None)
      credit = section.find('h4')
      if book is None or credit is None:
        notes.append(f'Lambda {category} winner section had incomplete title/author headings.')
        continue
      title = parser.clean_title(book.get_text(' ', strip=True))
      author = author_field(parser, credit)
      if not title or not author:
        notes.append(f'Lambda {category} winner section had empty title/author metadata.')
        continue
      link = book.find('a', href=True)
      rows.append({'award_year': str(year), 'category': category, 'title': title,
        'author': author, 'result': 'winner', 'source_url': urljoin(url, link['href']) if link else url})
  required = {'Gay Romance', 'Lesbian Romance'}
  if cycle >= 2025:
    required.add('LGBTQ+ Romance and Erotica')
  if not {normalize_heading(c) for c in required}.issubset({normalize_heading(c) for c in categories}):
    notes.append('Lambda official page did not expose all expected romance categories.')
  return {'rows': rows, 'notes': notes, 'complete': bool(rows) and not notes,
    'publication_year': year, 'ceremony_year': cycle, 'categories': categories,
    'closed': bool(re.search(r'ceremony took place|winners (?:were |are |have been )?announced', ' '.join(intro), re.I))}
