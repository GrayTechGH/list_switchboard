#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

import json
import re
import xml.etree.ElementTree as ET
from html import escape, unescape
from urllib.parse import quote


def fandom_api_html(html):
  text = html.lstrip()
  if text.startswith('{'):
    try:
      data = json.loads(html)
    except Exception:
      return html
    parsed = data.get('parse') or {}
    content = parsed.get('text') or ''
    if isinstance(content, dict):
      content = next(iter(content.values()), '')
    return content or html

  if text.startswith('<') and '<text' in html:
    try:
      root = ET.fromstring(html)
      text_el = root.find('.//text')
      if text_el is not None and text_el.text is not None:
        return unescape(text_el.text)
    except ET.ParseError:
      return html
  return html


def looks_like_wikitext(text):
  return '{| class=' in text or '\n|-' in text or '\n!' in text


def fandom_wikitext_table_to_html(text):
  tables = []
  current_table = {'rows': [], 'current': [], 'caption': None}
  for line in text.splitlines():
    line = line.strip()
    if line.startswith('{|'):
      if current_table['current']:
        current_table['rows'].append(current_table['current'])
      if current_table['rows']:
        tables.append(current_table)
      current_table = {'rows': [], 'current': [], 'caption': None}
    elif line.startswith('|+'):
      current_table['caption'] = clean_wikitext_cell(line[2:].strip())
    elif line.startswith('|-'):
      if current_table['current']:
        current_table['rows'].append(current_table['current'])
        current_table['current'] = []
    elif line.startswith('|}') or line == '':
      if current_table['current']:
        current_table['rows'].append(current_table['current'])
      if current_table['rows']:
        tables.append(current_table)
      current_table = {'rows': [], 'current': [], 'caption': None}
    elif line.startswith('!') or line.startswith('|'):
      cells = [cell.strip() for cell in line[1:].split('!!' if line.startswith('!') else '||')]
      if len(cells) == 1 and not line.startswith('!'):
        cells = [cell.strip() for cell in line[1:].split('|')]
      current_table['current'].extend(clean_wikitext_cell(cell) for cell in cells if cell.strip())
  if current_table['current']:
    current_table['rows'].append(current_table['current'])
  if current_table['rows']:
    tables.append(current_table)

  html_parts = []
  for table in tables:
    parts = ['<table>']
    if table['caption']:
      parts.append(f'<caption>{table["caption"]}</caption>')
    for row_index, row in enumerate(table['rows']):
      tag = 'th' if row_index == 0 else 'td'
      parts.append('<tr>' + ''.join(f'<{tag}>{cell}</{tag}>' for cell in row) + '</tr>')
    parts.append('</table>')
    html_parts.append(''.join(parts))
  return ''.join(html_parts)


def clean_wikitext_cell(value):
  value = re.sub(r'<[^>]+>', '', value)
  value = re.sub(r'\[\[([^|\]#]+)(?:#[^|\]]*)?\|([^\]]+)\]\]', wikitext_link_to_html, value)
  value = re.sub(r'\[\[([^|\]#]+)(?:#[^\]]*)?\]\]', wikitext_link_to_html, value)
  value = re.sub(r'\[https?://[^\s\]]+\s+([^\]]+)\]', r'\1', value)
  value = value.replace("'''", '').replace("''", '')
  return value.strip()


def wikitext_link_to_html(match):
  page = match.group(1).strip()
  label = match.group(2).strip() if len(match.groups()) > 1 and match.group(2) else page
  href = '/wiki/' + quote(page.replace(' ', '_'), safe='')
  return f'<a href="{href}">{escape(label)}</a>'
