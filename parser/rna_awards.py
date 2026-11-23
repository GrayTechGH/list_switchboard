#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
RNA award parsers for the official winners archive and shortlist news pages.

Maintenance notes:
- The RNA past-winners archive exposes winners for multiple RNA-controlled
  awards. The parser family imports Romantic Novel of the Year/RoNA and Joan
  Hessayon rows through separate recipes.
- Shortlists are not in the archive. They are parsed from official RNA news
  posts discovered through the site's WordPress REST search endpoint.
- Archive offsets carry no completeness count, so every archive page stays
  fresh. A dated shortlist post is reusable only when the fresh archive has
  winners for all its categories. Source projections retain its original
  nominee results through later winner changes.
- Joan Hessayon contender/finalist coverage is official-news dependent and not
  historically complete; individual contender profile posts are intentionally
  excluded in V1.
"""

import json
import re
import datetime
from urllib.parse import urljoin,urlsplit

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,is_author_suffix,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
  from calibre_plugins.list_switchboard.parser.incremental import ParsedUnitCache,project_source_rows,restore_source_rows
  from calibre_plugins.list_switchboard.errors import ImportCancelledError,CamoufoxRequiredError
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,is_author_suffix,
  )
  from .generic import position_sort_key
  from .incremental import ParsedUnitCache,project_source_rows,restore_source_rows
  from errors import ImportCancelledError,CamoufoxRequiredError


RNA_RONA_AWARD_NAME = 'RNA Romantic Novel of the Year Awards'
RNA_JOAN_HESSAYON_AWARD_NAME = 'RNA Joan Hessayon Award for New Writers'
RNA_JOAN_HESSAYON_CATEGORY = 'Joan Hessayon'
RNA_PAST_WINNERS_URL = 'https://romanticnovelistsassociation.org/past-winners'
RNA_REST_ROOT = 'https://romanticnovelistsassociation.org/wp-json/wp/v2'
RNA_SHORTLIST_SEARCH_URLS = (
  RNA_REST_ROOT + '/search?search=shortlist%20romantic%20novel%20awards&per_page=50',
  RNA_REST_ROOT + '/search?search=finalists%20romantic%20novel%20awards&per_page=50',
)
RNA_JOAN_HESSAYON_SEARCH_URLS = (
  RNA_REST_ROOT + '/search?search=Joan%20Hessayon%20finalists&per_page=50',
  RNA_REST_ROOT + '/search?search=Joan%20Hessayon%20contenders&per_page=50',
  RNA_REST_ROOT + '/search?search=Joan%20Hessayon%20shortlist&per_page=50',
  RNA_REST_ROOT + '/search?search=Joan%20Hessayon%20Award&per_page=50',
)

SHORTLIST_RESULT_WORDS = ('shortlist', 'shortlists', 'shortlisted', 'finalist', 'finalists')
RESULT_PRIORITY = {RESULT_WINNER: 0, RESULT_SHORTLISTED: 1}

CATEGORY_CANONICAL = {
  normalize_heading(alias):canonical for alias,canonical in (
    ('Popular Romantic Fiction Novel','Popular Romantic Fiction'),
    ('Popular Fiction Romantic Novel','Popular Romantic Fiction'),
    ('Goldsboro Books Contemporary Romantic Novel','Contemporary Romantic Novel'),
    ('Goldsboro Books Historical Romantic Novel','Historical Romantic Novel'),
    ('Sapere Books Popular Romantic Fiction','Popular Romantic Fiction'),
    ('Sapere Books Popular Fiction','Popular Romantic Fiction'),
    ('Katie Fforde Debut Romantic Novel','Debut Romantic Novel'),
    ('Jackie Collins Award for Romantic Thrillers','Romantic Thriller'),
    ('Jackie Collins Romantic Thriller','Romantic Thriller'),
    ('Christmas/Festive Holiday Romantic Novel','Festive Holiday Romantic Novel'),
    ('Christmas / Festive Holiday Romantic Novel','Festive Holiday Romantic Novel'),
    ('Jane Wenham-Jones Award for Romantic Comedy','Romantic Comedy'),
    ('Romantic Comedy Novel','Romantic Comedy'),
    ('Books and the City Romantic Comedy Novel','Romantic Comedy'),
    ('Libert\u00e0 Books Shorter Romantic Novel','Shorter Romantic Novel'),
    ('Libert\u00e0 Shorter Romantic Novel','Shorter Romantic Novel'),
  )}


class RNARomanticNovelAwardsParser(AwardParserBase):

  AWARD_NAME = RNA_RONA_AWARD_NAME
  MAX_ARCHIVE_PAGES = 30
  MAX_SHORTLIST_POSTS = 30
  SHORTLIST_SEARCH_URLS = RNA_SHORTLIST_SEARCH_URLS
  COMMA_SHORTLIST_ROWS = True

  def parse(
      self, html, base_url=RNA_PAST_WINNERS_URL, name=RNA_RONA_AWARD_NAME,
      fetch_url=None, shortlist_pages=None,cached_parsed=None,incremental_update=False):
    if fetch_url is not None and shortlist_pages is None:
      return self.parse_live_sources(html,base_url,name,fetch_url,cached_parsed,incremental_update)
    notes = []
    rows = []
    rows.extend(self.parse_archive_rows(html, base_url))
    rows.extend(self.fetch_archive_page_rows(html, base_url, fetch_url, notes))
    if shortlist_pages is not None:
      rows.extend(self.parse_shortlist_pages(shortlist_pages))
    elif fetch_url is not None:
      rows.extend(self.fetch_shortlist_rows(fetch_url, notes))
    rows = self.dedupe_rows(rows)
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def parse_live_sources(self,html,base_url,name,fetch_url,cached_parsed,incremental_update):
    cache=ParsedUnitCache('rna-closed-shortlist-posts-v1',json.dumps([
      base_url,name,type(self).__name__,self.SHORTLIST_SEARCH_URLS,self.MAX_ARCHIVE_PAGES,
      self.MAX_SHORTLIST_POSTS]),cached_parsed,incremental_update)
    notes=[]
    archive_rows=list(self.parse_archive_rows(html,base_url))
    pages=self.discover_archive_page_urls(BeautifulSoup(html,'html.parser'),base_url)
    archive_complete=self.is_archive_document(html)
    if not archive_complete:
      notes.append('RNA archive front did not expose recognizable award metadata.')
    for url in pages:
      try:
        page_html=fetch_url(url)
        if not self.is_archive_document(page_html):
          raise ValueError('RNA archive page did not expose recognizable award metadata.')
        page_rows=self.parse_archive_rows(page_html,url)
        for row in page_rows:
          row['_source_order']=1000+len(archive_rows)
          archive_rows.append(row)
      except (ImportCancelledError,CamoufoxRequiredError):
        raise
      except Exception as err:
        archive_complete=False
        notes.append(f'RNA archive page could not be fetched: {url}: {err}')
    if not archive_complete:
      try:
        retained=restore_source_rows(cache.previous('archive'),
          (cache.old_units.get('archive') or {}).get('metadata') or {})
        archive_rows=self.dedupe_rows(archive_rows+retained)
      except (ValueError,TypeError):
        pass
    winners={(r['award_year'],normalize_heading(r['category'])) for r in archive_rows}
    posts={}
    discovery_complete=True
    for search_url in self.SHORTLIST_SEARCH_URLS:
      try:
        data=json.loads(fetch_url(search_url))
        if not isinstance(data,list):
          raise ValueError('RNA search did not return a result list.')
        for item in data:
          if not isinstance(item,dict):
            continue
          title=self.rendered_json_text(item.get('title'))
          if not self.accept_shortlist_search_title(title):
            continue
          url=self.rest_post_url(item)
          if (not url or url in posts or urlsplit(url).scheme!='https' or
              urlsplit(url).netloc!=urlsplit(base_url).netloc):
            continue
          posts[url]=[title,url]
          if len(posts)>self.MAX_SHORTLIST_POSTS:
            posts.pop(url)
            break
      except (ImportCancelledError,CamoufoxRequiredError):
        raise
      except Exception as err:
        discovery_complete=False
        notes.append(f'RNA shortlist search could not be fetched: {err}')
    if not discovery_complete:
      for url,unit in cache.old_units.items():
        if url!='archive' and url not in posts:
          posts[url]=unit.get('revision')
    rows=list(archive_rows)
    units={'archive':(archive_rows,None,archive_complete)}
    shortlist_count=0
    for url,revision in posts.items():
      old=cache.old_units.get(url) or {}
      previous=[]
      try:
        previous=restore_source_rows(cache.previous(url),old.get('metadata') or {})
      except (ValueError,TypeError):
        pass
      years={int(r['award_year']) for r in previous}
      closed=(archive_complete and previous and len(years)==1 and
        max(years)<datetime.datetime.now().year and all(
          (r['award_year'],normalize_heading(r['category'])) in winners for r in previous))
      if old.get('complete') is True and old.get('revision')==revision and closed:
        source_rows,complete=previous,True
      else:
        try:
          source_rows=self.parse_shortlist_pages([(url,fetch_url(url))])
          complete=bool(source_rows) and len({r['award_year'] for r in source_rows})==1
          if not complete:
            notes.append(f'RNA shortlist post had no usable category snapshot: {url}')
            if previous:
              source_rows=previous
        except (ImportCancelledError,CamoufoxRequiredError):
          raise
        except Exception as err:
          source_rows,complete=previous,False
          notes.append(f'RNA shortlist post could not be fetched: {url}: {err}')
      source_rows=[dict(row,_source_order=shortlist_count+i) for i,row in enumerate(source_rows)]
      shortlist_count+=len(source_rows)
      rows.extend(source_rows)
      units[url]=(source_rows,revision,complete and discovery_complete)
    entries=self.entries_from_rows(self.dedupe_rows(rows))
    entries=sorted(entries,key=lambda r:position_sort_key(r.get('position','')))
    for url,(source_rows,revision,complete) in units.items():
      projected,metadata=project_source_rows(source_rows,entries,
        lambda row:(str(row['award_year']),normalize_heading(row['category']),normalize_heading(row['title'])))
      cache.put(url,projected,revision=revision,complete=complete,metadata=metadata)
    result=self.parsed_result(name,base_url,entries,notes=notes)
    result['incremental_state']=cache.state(entries)
    result['incremental_state']['discovery']={'refresh_units':['archive']+[
      url for url,(rs,_revision,_complete) in units.items() if url!='archive' and
      any(int(r['award_year'])>=datetime.datetime.now().year for r in rs)]}
    return result

  def is_archive_document(self,html):
    soup=BeautifulSoup(html or '','html.parser')
    for heading in soup.find_all('h2'):
      if heading.find('a',href=True) is None:
        continue
      author=heading.find_next('h2')
      if author is not None and author.find('a',href=True) is None:
        metadata=self.metadata_after_heading(author)
        if metadata is not None and self.archive_metadata(metadata)[2] is not None:
          return True
    return False

  def parse_archive_rows(self, html, page_url):
    soup = BeautifulSoup(html or '', 'html.parser')
    rows = []
    for heading in soup.find_all('h2'):
      link = heading.find('a', href=True)
      if link is None:
        continue
      title = self.clean_title(link.get_text(' ', strip=True))
      if not title or self.skip_archive_title(title):
        continue
      author_heading = heading.find_next('h2')
      if author_heading is None or author_heading.find('a', href=True) is not None:
        continue
      author = self.clean_author(author_heading.get_text(' ', strip=True))
      metadata = self.metadata_after_heading(author_heading)
      if not author or metadata is None:
        continue
      award_group, category, year = self.archive_metadata(metadata)
      if year is None or not self.is_romantic_novel_award_group(award_group):
        continue
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': RESULT_WINNER,
        'source_url': urljoin(page_url, link['href']),
        'category': self.clean_category(category),
        '_source_order': len(rows),
      })
    return rows

  def fetch_archive_page_rows(self, html, base_url, fetch_url, notes):
    if fetch_url is None:
      return []
    soup = BeautifulSoup(html or '', 'html.parser')
    urls = self.discover_archive_page_urls(soup, base_url)
    rows = []
    for url in urls:
      try:
        page_html = fetch_url(url)
      except (ImportCancelledError,CamoufoxRequiredError):
        raise
      except Exception as err:
        notes.append(f'RNA archive page could not be fetched: {url}: {err}')
        continue
      before_count = len(rows)
      rows.extend(self.parse_archive_rows(page_html, url))
      for index, row in enumerate(rows[before_count:], start=before_count):
        row['_source_order'] = 1000 + index
    return rows

  def discover_archive_page_urls(self, soup, base_url):
    urls = {}
    for link in soup.find_all('a', href=True):
      href = urljoin(base_url, link['href'])
      match = re.search(r'/past-winners/page/(\d+)/?$', href)
      if match is None:
        continue
      page_number = int(match.group(1))
      if page_number <= 1 or page_number > self.MAX_ARCHIVE_PAGES:
        continue
      urls[page_number]=href
    if urls:
      last=max(urls)
      return tuple(urls.get(page,base_url.rstrip('/')+'/page/'+str(page)) for page in range(2,last+1))
    return ()

  def archive_page_sort_key(self, url):
    match = re.search(r'/page/(\d+)/?$', url)
    return int(match.group(1)) if match is not None else 0

  def fetch_shortlist_rows(self, fetch_url, notes):
    pages = []
    seen_post_urls = set()
    for search_url in self.SHORTLIST_SEARCH_URLS:
      try:
        search_html = fetch_url(search_url)
      except (ImportCancelledError,CamoufoxRequiredError):
        raise
      except Exception as err:
        notes.append(f'RNA shortlist search could not be fetched: {err}')
        continue
      for item in self.shortlist_search_items(search_html):
        title = self.rendered_json_text(item.get('title'))
        if not self.accept_shortlist_search_title(title):
          continue
        post_url = self.rest_post_url(item)
        if not post_url or post_url in seen_post_urls:
          continue
        seen_post_urls.add(post_url)
        if len(seen_post_urls) > self.MAX_SHORTLIST_POSTS:
          break
        try:
          pages.append((post_url, fetch_url(post_url)))
        except (ImportCancelledError,CamoufoxRequiredError):
          raise
        except Exception as err:
          notes.append(f'RNA shortlist post could not be fetched: {post_url}: {err}')
    return self.parse_shortlist_pages(pages)

  def shortlist_search_items(self, search_html):
    try:
      data = json.loads(search_html or '[]')
    except Exception:
      return []
    return data if isinstance(data, list) else []

  def accept_shortlist_search_title(self, title):
    heading = normalize_heading(title)
    if 'industry' in heading or 'joan hessayon' in heading:
      return False
    if 'romantic novel awards' not in heading and 'romantic novel of the year awards' not in heading:
      return False
    return any(word in heading for word in SHORTLIST_RESULT_WORDS)

  def rest_post_url(self, item):
    links = item.get('_links') if isinstance(item, dict) else None
    if isinstance(links, dict):
      self_links = links.get('self') or []
      for link in self_links:
        href = link.get('href') if isinstance(link, dict) else ''
        if href:
          return href
    return item.get('url') if isinstance(item, dict) else ''

  def parse_shortlist_pages(self, pages):
    rows = []
    for page_url, page_html in pages:
      title, content_html, source_url = self.shortlist_page_content(page_url, page_html)
      page_year = self.year_from_text(title) or self.year_from_text(content_html)
      if page_year is None:
        continue
      rows.extend(self.parse_shortlist_content(content_html, source_url, page_year, len(rows)))
    return rows

  def shortlist_page_content(self, page_url, page_html):
    try:
      data = json.loads(page_html or '{}')
    except Exception:
      return '', page_html or '', page_url
    if not isinstance(data, dict):
      return '', page_html or '', page_url
    title = self.rendered_json_text(data.get('title'))
    content = ''
    content_data = data.get('content')
    if isinstance(content_data, dict):
      content = content_data.get('rendered') or ''
    source_url = data.get('link') or page_url
    return title, content, source_url

  def rendered_json_text(self, value):
    if isinstance(value, dict):
      value = value.get('rendered') or ''
    return BeautifulSoup(value or '', 'html.parser').get_text(' ', strip=True)

  def parse_shortlist_content(self, content_html, source_url, year, source_order_start=0):
    soup = BeautifulSoup(content_html or '', 'html.parser')
    rows = []
    rows.extend(self.parse_accordion_shortlist_rows(soup, source_url, year, source_order_start))
    rows.extend(self.parse_linear_shortlist_rows(
      soup, source_url, year, source_order_start + len(rows)))
    return self.dedupe_rows(rows)

  def parse_accordion_shortlist_rows(self, soup, source_url, year, source_order_start):
    rows = []
    for accordion in soup.find_all('section', class_=lambda value: value and 'accordion' in value):
      category = None
      for child in accordion.find_all(['h2', 'div'], recursive=False):
        if child.name == 'h2':
          category = self.clean_category(child.get_text(' ', strip=True))
          if self.skip_shortlist_category(category):
            category = None
        elif child.name == 'div' and category:
          for heading in child.find_all('h3'):
            parsed = self.title_author_from_text(heading.get_text(' ', strip=True))
            if parsed is None:
              continue
            title, author = parsed
            rows.append(self.shortlist_row(
              title, author, category, year, source_url, source_order_start + len(rows)))
    return rows

  def parse_linear_shortlist_rows(self, soup, source_url, year, source_order_start):
    rows = []
    category = None
    result = RESULT_SHORTLISTED
    for node in soup.find_all(['h2', 'h3', 'h4', 'p', 'li']):
      text=normalize_line(node.get_text())
      if rows and (re.match(r'^(?:about (?:the )?(?:award sponsors|romantic novelists)|notes to editors|author and cover images|for further information|we would like to give a special thank)',text,re.I) or
          re.search(r'\bwill present the awards\b',text,re.I)):
        break
      if self.is_shortlist_category_node(node):
        category = self.clean_category(text)
        result=RESULT_WINNER if re.search(r'\bwinner of\b',text,re.I) else RESULT_SHORTLISTED
        if self.skip_shortlist_category(category):
          category = None
        continue
      if category is None:
        continue
      parsed = self.title_author_from_node(node)
      if parsed is None:
        continue
      title, author = parsed
      row=self.shortlist_row(title,author,category,year,source_url,source_order_start+len(rows))
      row['result']=result
      rows.append(row)
    return rows

  def is_shortlist_category_node(self, node):
    if node.name not in ('h2','h3','h4','p'):
      return False
    if node.name=='p' and node.find(['strong','b','u']) is None:
      return False
    text=normalize_line(node.get_text())
    if len(text)>160 or ',' in text or re.search(r'\b(?:announced|announces|present|said|judging|judged|sponsors?|enquiries)\b',text,re.I):
      return False
    raw_heading = normalize_heading(text)
    text = self.clean_category(text)
    heading = normalize_heading(text)
    if not re.search(r'\baward\b',raw_heading):
      return False
    if 'award' not in heading:
      heading = raw_heading
    if 'joan hessayon' in heading or 'industry' in heading:
      return True
    return any(word in heading for word in (
      'romantic', 'romance', 'romantasy', 'fantasy', 'saga', 'bestseller',
      'popular'))

  def title_author_from_node(self, node):
    em = node.find(['em','i'])
    if em is not None:
      title = self.clean_title(em.get_text())
      full_text = normalize_line(node.get_text())
      remainder = full_text
      if title and title in remainder:
        remainder = remainder.split(title, 1)[1]
      parsed = self.title_author_from_text(f'{title} {remainder}')
      if parsed is not None:
        return parsed
    else:
      parsed=self.title_author_from_text(node.get_text())
      if parsed is not None:
        return parsed
    if self.COMMA_SHORTLIST_ROWS:
      text=normalize_line(node.get_text())
      marked=normalize_line(em.get_text()) if em is not None else ''
      if marked and not normalize_line(text.split(marked,1)[0]):
        title=self.clean_title(marked)
        remainder=text.split(marked,1)[-1].strip(' ,:')
      elif text.count(',')>=2:
        title,remainder=text.split(',',1)
        title=self.clean_title(title)
        remainder=remainder.strip(' ,:')
      else:
        return None
      pieces=[p.strip() for p in remainder.split(',')]
      author=pieces[0]
      if len(pieces)>1 and is_author_suffix(pieces[1]):
        author+=', '+pieces[1]
      author=self.clean_author(author)
      if title and author and not self.looks_like_non_book_row(title,author):
        return title,author
    return None

  def title_author_from_text(self, value):
    value = normalize_line(value).strip(':')
    value = re.sub(r'^\s*(?:winner|finalist|shortlisted)\s*:?\s*', '', value, flags=re.I)
    match = re.match(r'^(.+)\s+by\s+(.+)$', value, flags=re.I)
    if match is None:
      return None
    title = self.clean_title(match.group(1))
    author = self.clean_author(match.group(2))
    if not title or not author:
      return None
    if self.looks_like_non_book_row(title, author):
      return None
    return title, author

  def shortlist_row(self, title, author, category, year, source_url, source_order):
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': RESULT_SHORTLISTED,
      'source_url': source_url,
      'category': self.clean_category(category),
      '_source_order': source_order,
    }

  def metadata_after_heading(self, heading):
    for sibling in heading.find_next_siblings():
      if getattr(sibling,'name',None)=='h2':
        break
      if getattr(sibling,'name',None)=='ul' and 'tags' in (sibling.get('class') or []):
        return sibling
    next_title = heading.find_next('h2')
    metadata = heading.find_next('ul')
    if metadata is None:
      return None
    if next_title is not None and next_title.find('a', href=True) is not None:
      if metadata.sourceline is not None and next_title.sourceline is not None:
        if metadata.sourceline > next_title.sourceline:
          return None
    return metadata

  def archive_metadata(self, metadata):
    link_texts = [
      normalize_line(link.get_text(' ', strip=True))
      for link in metadata.find_all('a')
      if normalize_line(link.get_text(' ', strip=True))
    ]
    year = None
    year_index = None
    for index, text in enumerate(link_texts):
      year = self.year_from_text(text)
      if year is not None:
        year_index = index
        break
    if year is None:
      year = self.year_from_text(metadata.get_text(' ', strip=True))
      year_index = len(link_texts)
    if year_index is None:
      return '', '', None
    award_group = link_texts[year_index - 2] if year_index >= 2 else ''
    category = link_texts[year_index - 1] if year_index >= 1 else ''
    return award_group, category, year

  def is_romantic_novel_award_group(self, value):
    heading = normalize_heading(value)
    return heading in {
      'romantic novel of the year',
      'the romantic novel of the year awards',
      'romantic novel of the year awards',
    }

  def clean_category(self, value):
    value = normalize_line(value)
    value = re.sub(r'\s+<[^>]+>$', '', value)
    value = value.replace('\xa0', ' ')
    value = re.sub(r'\s+', ' ', value).strip(' "\'\u2018\u2019\u201c\u201d,:')
    value = re.sub(r'^the\s+', '', value, flags=re.I).strip()
    value = re.sub(r'^winner of (?:the )?', '', value, flags=re.I).strip()
    value = re.sub(r'\s+novel\s+award$', ' Novel', value, flags=re.I)
    value = re.sub(r'\s+award$', '', value, flags=re.I).strip()
    value = value.replace('Festive/Holiday', 'Festive Holiday')
    value = value.replace('Romantasy/Romantic Fantasy', 'Romantasy / Romantic Fantasy')
    value=normalize_line(value)
    return CATEGORY_CANONICAL.get(normalize_heading(value),value)

  def clean_title(self, value):
    value = strip_publication_notes(normalize_line(value))
    return value.strip(' "\'\u2018\u2019\u201c\u201d,:')

  def clean_author(self, value):
    value = normalize_line(value)
    value = re.sub(r'\s*:\s*$', '', value)
    value = strip_publication_notes(value)
    value = re.sub(r'\s+(?:Publisher|Agent)\s*:.*$', '', value, flags=re.I)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,:')

  def skip_archive_title(self, title):
    heading = normalize_heading(title)
    return heading in {'image', 'get in touch', 'legal', 'membership'} or heading.startswith('image ')

  def skip_shortlist_category(self, category):
    heading = normalize_heading(category)
    if 'joan hessayon' in heading or 'industry' in heading:
      return True
    if 'award' not in heading and not any(word in heading for word in (
        'romantic', 'romance', 'romantasy', 'fantasy', 'saga', 'bestseller',
        'popular')):
      return True
    return False

  def looks_like_non_book_row(self, title, author):
    title_heading = normalize_heading(title)
    author_heading = normalize_heading(author)
    if not title_heading or not author_heading:
      return True
    if title_heading in {'publisher', 'agent', 'media enquiries'}:
      return True
    if author_heading.startswith('publisher ') or author_heading.startswith('agent '):
      return True
    return False

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def dedupe_rows(self, rows):
    deduped = []
    index_by_key = {}
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['category']),
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      existing_index = index_by_key.get(key)
      if existing_index is None:
        index_by_key[key] = len(deduped)
        deduped.append(row)
        continue
      existing = deduped[existing_index]
      if RESULT_PRIORITY.get(row.get('result'), 99) < RESULT_PRIORITY.get(
          existing.get('result'), 99):
        deduped[existing_index] = row
    return deduped

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      year_rows = sorted(
        by_year[year],
        key=lambda row: (
          RESULT_PRIORITY.get(row.get('result'), 99),
          row.get('_source_order', 0),
          normalize_heading(row.get('category', '')),
        ))
      award_rows = []
      for row in year_rows:
        entry_row = {key: value for key, value in row.items() if not key.startswith('_')}
        award_rows.append(self.build_award_entry(
          entry_row, row['source_url'], year, row['category']))
      entries.extend(assign_positions(award_rows, int(year)))
    return entries


def parse_rna_romantic_novel_awards(
    html, base_url=RNA_PAST_WINNERS_URL, name=RNA_RONA_AWARD_NAME, fetch_url=None,
    shortlist_pages=None):
  return RNARomanticNovelAwardsParser().parse(
    html, base_url, name, fetch_url=fetch_url, shortlist_pages=shortlist_pages)


class RNAJoanHessayonAwardParser(RNARomanticNovelAwardsParser):

  AWARD_NAME = RNA_JOAN_HESSAYON_AWARD_NAME
  SHORTLIST_SEARCH_URLS = RNA_JOAN_HESSAYON_SEARCH_URLS
  COMMA_SHORTLIST_ROWS = False

  def parse(
      self, html, base_url=RNA_PAST_WINNERS_URL,
      name=RNA_JOAN_HESSAYON_AWARD_NAME, fetch_url=None, shortlist_pages=None,
      cached_parsed=None,incremental_update=False):
    parsed = super().parse(
      html,
      base_url,
      name,
      fetch_url=fetch_url,
      shortlist_pages=shortlist_pages,cached_parsed=cached_parsed,incremental_update=incremental_update)
    parsed.setdefault('notes', []).insert(
      0,
      'Joan Hessayon contender/finalist coverage is official-news dependent '
      'and may be incomplete for older years.')
    return parsed

  def is_romantic_novel_award_group(self, value):
    return 'joan hessayon' in normalize_heading(value)

  def accept_shortlist_search_title(self, title):
    heading = normalize_heading(title)
    if 'industry' in heading or 'elizabeth goudge' in heading:
      return False
    if 'joan hessayon' not in heading and ' jha' not in f' {heading}':
      return False
    if any(phrase in heading for phrase in (
        'contenders announced',
        'contenders revealed',
        'finalists',
        'line up',
        'lineup',
        'shortlist',
        'shortlists',
    )):
      return True
    if 'announces' in heading and 'contenders' in heading:
      return True
    if 'winner' in heading:
      return False
    return False

  def parse_shortlist_content(self, content_html, source_url, year, source_order_start=0):
    soup = BeautifulSoup(content_html or '', 'html.parser')
    rows = []
    panels = self.joan_hessayon_panels(soup)
    rows.extend(self.parse_accordion_shortlist_rows(soup, source_url, year, source_order_start))
    if panels:
      for panel in panels:
        rows.extend(self.parse_joan_hessayon_nodes(
          panel,
          source_url,
          year,
          source_order_start + len(rows)))
    else:
      rows.extend(self.parse_joan_hessayon_nodes(
        soup,
        source_url,
        year,
        source_order_start + len(rows)))
    return self.dedupe_rows(rows)

  def joan_hessayon_panels(self, soup):
    panels = []
    for heading in soup.find_all(['h2', 'h3']):
      if self.skip_shortlist_category(heading.get_text(' ', strip=True)):
        continue
      panel = heading.find_next_sibling('div')
      if panel is not None:
        panels.append(panel)
    return panels

  def parse_joan_hessayon_nodes(self, root, source_url, year, source_order_start):
    rows = []
    for node in root.find_all(['h3', 'p', 'li']):
      parsed = self.joan_hessayon_title_author_from_node(node)
      if parsed is None:
        continue
      title, author = parsed
      rows.append(self.shortlist_row(
        title,
        author,
        RNA_JOAN_HESSAYON_CATEGORY,
        year,
        source_url,
        source_order_start + len(rows)))
    return rows

  def joan_hessayon_title_author_from_node(self, node):
    text = normalize_line(node.get_text(' ', strip=True))
    if not text or self.looks_like_joan_hessayon_noise(text):
      return None
    parsed = self.title_author_from_node(node)
    if parsed is not None:
      return parsed
    em = node.find('em')
    if em is not None:
      title = self.clean_title(em.get_text(' ', strip=True))
      before_title = text.split(em.get_text(' ', strip=True), 1)[0]
      author = self.clean_author(before_title.rstrip(' ,:-'))
      if title and author and not self.looks_like_non_book_row(title, author):
        return title, author
    parts = [part.strip() for part in re.split(r'\s*,\s*', text) if part.strip()]
    if len(parts) >= 2:
      author = self.clean_author(parts[0])
      title = self.clean_title(parts[1])
      if title and author and not self.looks_like_non_book_row(title, author):
        return title, author
    return None

  def is_shortlist_category_node(self, node):
    return not self.skip_shortlist_category(node.get_text(' ', strip=True))

  def skip_shortlist_category(self, category):
    return 'joan hessayon' not in normalize_heading(category)

  def clean_category(self, value):
    if 'joan hessayon' in normalize_heading(value):
      return RNA_JOAN_HESSAYON_CATEGORY
    return super().clean_category(value)

  def looks_like_joan_hessayon_noise(self, text):
    heading = normalize_heading(text)
    if heading in {'publisher', 'agent', 'website', 'facebook', 'instagram', 'twitter'}:
      return True
    if heading.startswith(('publisher ', 'agent ', 'website ', 'facebook ', 'instagram ')):
      return True
    if any(phrase in heading for phrase in (
        'media enquiries',
        'the contenders for',
        'the winner of',
        'the award is',
        'the novels are judged',
        'previous winners include',
        'many congratulations',
        'winner will be announced',
        'i am ',
        'i m ',
        'i am absolutely',
        'to be a contender',
    )):
      return True
    return False


def parse_rna_joan_hessayon_award(
    html, base_url=RNA_PAST_WINNERS_URL, name=RNA_JOAN_HESSAYON_AWARD_NAME,
    fetch_url=None, shortlist_pages=None):
  return RNAJoanHessayonAwardParser().parse(
    html, base_url, name, fetch_url=fetch_url, shortlist_pages=shortlist_pages)
