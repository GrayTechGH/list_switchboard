#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Small PDF text extraction helper for official award-list PDFs.

Maintenance notes:
- This intentionally stays tiny and dependency-free for source PDFs whose text
  streams are already enough for regression-tested award parsing.
- It is not a general-purpose PDF layout engine. Source parsers still own line
  reconstruction and page-artifact cleanup.
"""

import re
import zlib


def extract_pdf_text(value):
  if isinstance(value, bytes):
    data = value
    source_text = value.decode('latin-1', 'ignore')
  else:
    source_text = str(value or '')
    data = source_text.encode('latin-1', 'ignore')
  if '%PDF' not in source_text[:1024]:
    return source_text

  fragments = []
  for match in re.finditer(rb'stream\r?\n(.*?)\r?\nendstream', data, re.S):
    stream = match.group(1).strip(b'\r\n')
    try:
      stream = zlib.decompress(stream)
    except Exception:
      pass
    fragments.extend(pdf_text_fragments(stream))
  return '\n'.join(fragments)


def pdf_text_fragments(stream):
  text = stream.decode('latin-1', 'ignore')
  fragments = []
  for array in re.finditer(r'\[(.*?)\]\s*TJ', text, re.S):
    fragments.append(''.join(pdf_literal_strings(array.group(1))))
  for item in re.finditer(r'(\((?:\\.|[^\\()])*\)|<[\da-fA-F\s]+>)\s*(?:Tj|\'|")', text, re.S):
    fragments.append(decode_pdf_string(item.group(1)))
  return [normalize_line(item) for item in fragments if normalize_line(item)]


def pdf_literal_strings(value):
  return [
    decode_pdf_string(item.group(0))
    for item in re.finditer(r'\((?:\\.|[^\\()])*\)|<[\da-fA-F\s]+>', value, re.S)
  ]


def decode_pdf_string(token):
  if token.startswith('<'):
    compact = re.sub(r'\s+', '', token.strip('<>'))
    try:
      return bytes.fromhex(compact).decode('utf-16-be', 'ignore')
    except Exception:
      try:
        return bytes.fromhex(compact).decode('latin-1', 'ignore')
      except Exception:
        return ''
  value = token[1:-1]
  value = re.sub(r'\\\r?\n', '', value)
  replacements = {
    r'\(': '(',
    r'\)': ')',
    r'\\': '\\',
    r'\n': '\n',
    r'\r': '\n',
    r'\t': ' ',
  }
  for source, target in replacements.items():
    value = value.replace(source, target)
  return value


def normalize_line(value):
  return re.sub(r'\s+', ' ', value or '').strip()
