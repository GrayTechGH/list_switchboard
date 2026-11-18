"""Read bounded WordPress prize histories and annual PEN article sections.

Modern bylines mark the title in emphasis; authors may precede or follow it.
Judges, citations, eligibility, navigation and adjacent awards are not records.
Returning None selects the legacy table/plain-line reader for older fixtures.
"""

import re
from urllib.parse import urljoin,urlsplit

from bs4 import BeautifulSoup,UnicodeDammit

try:
  from calibre_plugins.list_switchboard.parser.award_base import normalize_heading,normalize_line,strip_publication_notes,RESULT_WINNER,RESULT_NOMINEE
except ImportError:
  from .award_base import normalize_heading,normalize_line,strip_publication_notes,RESULT_WINNER,RESULT_NOMINEE


def source_soup(html):
  if isinstance(html,bytes):html=UnicodeDammit(html).unicode_markup or ''
  return BeautifulSoup(html or '','html.parser')


def marked_work(parser,node):
  fragment=source_soup(str(node))
  for label in fragment.find_all(['em','i']):
    if normalize_heading(label.get_text(' ',strip=True)).startswith(('judges','judge','citation','from the judges')):label.decompose()
  for link in fragment.find_all('a'):
    if normalize_heading(link.get_text(' ',strip=True)) in ('bookshop','bookshop org','buy the book'):link.decompose()
  title_node=next((n for n in fragment.find_all(['em','i']) if normalize_line(n.get_text(' ',strip=True))),None)
  if title_node is None:return None
  raw_title=title_node.get_text(' ',strip=True)
  title=parser.clean_title(raw_title)
  if not title:return None
  # PEN's 2026 Open Book row closes emphasis before the final 's' in Times.
  suffix=re.match(r"^([A-Za-z'\u2019]{1,3}),",str(title_node.next_sibling or ''))
  if suffix:title+=suffix.group(1)
  title_node.replace_with('__PEN_TITLE_BOUNDARY__')
  before,after=normalize_line(fragment.get_text(' ',strip=True)).split('__PEN_TITLE_BOUNDARY__',1)
  if suffix:after=re.sub(r'^\s*'+re.escape(suffix.group(1)),'',after,count=1)
  prefix=re.sub(r'^(?:19|20)\d{2}\s*[:\-\u2013,]?\s*','',before.strip())
  prefix=re.sub(r'^(?:winner|finalists?|shortlisted)\s*:\s*','',prefix,flags=re.I).strip(' ,:')
  if not prefix and not (raw_title.rstrip().endswith(',') or re.match(r'^(?:,|by\s)',after.strip(),re.I)):return None
  author=prefix or strip_publication_notes(after).strip(' ,:')
  # Citation paragraphs can emphasize a book without being a byline.
  strongs=[re.sub(r'^(?:19|20)\d{2}\s*[:\-\u2013,]?\s*','',
    normalize_line(n.get_text(' ',strip=True))).strip(' ,:') for n in fragment.find_all(['strong','b'])
    if n.find_parent(['strong','b']) is None]
  if prefix and normalize_heading(parser.clean_author(prefix))!=normalize_heading(' '.join(n for n in strongs if n)):
    return None
  if not author or len(author)>250:return None
  return title,parser.clean_author(author)


def byline_candidate(node):
  text=normalize_line(node.get_text(' ',strip=True))
  marks=[n for n in node.find_all(['em','i']) if normalize_line(n.get_text(' ',strip=True)) and
    not normalize_heading(n.get_text(' ',strip=True)).startswith(('judge','citation','from the judges'))]
  if not marks:return False
  title=marks[0].get_text(' ',strip=True)
  title_first=text.startswith(title) and (title.endswith(',') or text[len(title):].lstrip().startswith(','))
  first=node.find(['strong','b','em','i'])
  return bool(title_first or re.match(r'^(?:(?:19|20)\d{2}|Winner\s*:)',text,re.I) or
    (first is not None and first.name in ('strong','b')) or node.find(['strong','b']))


def marked_works(parser,node):
  fragment=source_soup(str(node));body=fragment.find(node.name)
  if body is None:return [],False
  lines=[];line=fragment.new_tag('p')
  for child in list(body.children):
    if getattr(child,'name',None)=='br':
      lines.append(line);line=fragment.new_tag('p')
    else:line.append(child)
  lines.append(line)
  works=[];incomplete=False
  for item in lines:
    work=marked_work(parser,item)
    if work is not None:works.append(work)
    elif byline_candidate(item):incomplete=True
  return works,incomplete


def read_modern_page(parser,html,url,config,kind):
  soup=source_soup(html)
  heading=soup.select_one('h1.wp-block-post-title')
  if heading is None:return None
  heading_text=normalize_line(heading.get_text(' ',strip=True));key=normalize_heading(heading_text)
  root=soup.select_one('.wp-block-post-content') or soup.find('main')
  if root is None:raise ValueError('PEN article did not expose its content boundary.')
  aliases=tuple(normalize_heading(a) for a in config.heading_aliases)
  year=parser.year_from_text(heading_text) or parser.year_from_text(url)
  expected_year=parser.year_from_text(url)
  if kind!='landing' and expected_year and year!=expected_year:
    raise ValueError('PEN annual article returned another award year.')
  if kind=='landing':
    if not any(alias in key for alias in aliases):raise ValueError('PEN landing page identified another prize.')
  elif (not year or 'pen america' not in key or
      not any(term in key for term in ('literary awards','conferral of annual prizes'))):
    raise ValueError('PEN annual article did not identify its award year and results.')
  annual_result=parser.result_from_heading(heading_text)
  if annual_result is None and 'conferral-of-annual-prizes' in url:annual_result=RESULT_WINNER
  if kind!='landing':
    path=urlsplit(url).path
    if (('finalists' in path and annual_result!=RESULT_NOMINEE) or
        ('winners' in path and annual_result!=RESULT_WINNER)):
      raise ValueError('PEN annual article returned another result stage.')
  rows=[];notes=[];active=False;current_year=None;result=annual_result
  matched=False;award_sections=0;complete=True
  for node in root.find_all(['h1','h2','h3','h4','p','li']):
    if node.find_parent(['nav','footer','header','blockquote']):continue
    text=normalize_line(node.get_text(' ',strip=True));label=normalize_heading(text)
    if node.name in ('h1','h2','h3','h4'):
      if kind=='landing':
        if re.match(r'^(?:19|20)\d{2} winner\b',label):
          active=True;current_year=parser.year_from_text(text);result=RESULT_WINNER
        elif label in ('previous winners','pen beyond margins award winners'):
          active=True;current_year=None;result=RESULT_WINNER
        else:active=False
      elif label.startswith('pen ') or label.startswith('pen/'):
        award_sections+=1;active=any(alias in label for alias in aliases)
        matched=matched or active;result=annual_result
      elif active:
        stage=parser.result_from_heading(text)
        if stage is not None:result=stage
        elif node.name in ('h1','h2','h3'):active=False
      continue
    if not active or result in (None,'longlist'):continue
    if kind=='landing' and not (re.match(r'^(?:19|20)\d{2}\b',text) or re.match(r'^Winner\s*:',text,re.I)):continue
    if parser.is_withdrawn(text):
      notes.append(f'Skipped withdrawn PEN America {year or current_year or "historical"} entry from {url}.')
      continue
    works,incomplete=marked_works(parser,node)
    if incomplete:
      notes.append(f'PEN published byline could not be parsed: {url}: {text}')
      complete=False
    if not works:continue
    row_year=(parser.year_from_text(text[:12]) or current_year) if kind=='landing' else year
    if not row_year:continue
    link=node.find('a',href=True)
    source_url=urljoin(url,link['href']) if link else url
    rows.extend(parser.row(row_year,*work,result,source_url,config) for work in works)
  if kind=='landing' and not rows:raise ValueError('PEN landing page did not expose winner history.')
  if kind!='landing' and award_sections<2:raise ValueError('PEN annual article did not expose bounded award sections.')
  return {'rows':rows,'notes':notes,'year':year,'category_absent':kind!='landing' and not matched,
    'modern':True,'complete':complete}
