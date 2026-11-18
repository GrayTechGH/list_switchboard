"""Reuse parsed source units while keeping the flat schema-2 entry cache.

Units reference entry indexes, never raw responses. Callers own discovery,
unit revisions/completeness and source-specific merge/position rules. A cache
from another source/configuration or without a complete index is not reusable.

Maintenance notes:
- Current users: Oprah, Reese monthly/YA, Jenna Jr., LibraryReads, Service95,
  Libby Global, BookBrowse, Dragons & Jetpacks, official Hugo/Lodestar years
  opted-in SFADB award categories, British Fantasy and Australasian Shadows.
- Unit indexes must be rebuilt after final sorting/positioning. Callers that
  renumber rows use a position-independent identity; ambiguous rows invalidate
  reuse rather than silently assigning one cached row to multiple positions.
"""

from copy import deepcopy
import json


def entry_fingerprint(entry):
  return json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def position_independent_fingerprint(entry):
  return entry_fingerprint({key:value for key,value in entry.items() if key!='position'})


def project_source_rows(source_rows, final_rows, identity):
  """Represent a parsed source against merged rows without losing provenance.

  References are local to the unit, so removing another unit and remapping flat
  indexes cannot corrupt them. Store only changed fields; rows omitted by the
  merge remain parsed entries in the small source-specific projection.
  """
  candidates = {}
  for index, entry in enumerate(final_rows):
    key = identity(entry)
    candidates[key] = index if key not in candidates else None
  projected, references, rows = [], {}, []
  for entry in source_rows:
    index = candidates.get(identity(entry))
    if index is None:
      rows.append({'entry': deepcopy(entry)})
      continue
    if index not in references:
      references[index] = len(projected)
      projected.append(deepcopy(final_rows[index]))
    base = final_rows[index]
    rows.append({'reference': references[index],
      'overrides': {key: deepcopy(value) for key, value in entry.items()
        if key not in base or base[key] != value},
      'removed': [key for key in base if key not in entry]})
  return projected, {'projection_version': 1, 'rows': rows}


def restore_source_rows(projected_rows, metadata):
  if metadata.get('projection_version') != 1 or not isinstance(metadata.get('rows'), list):
    raise ValueError('Missing parsed source projection.')
  entries = []
  for row in metadata['rows']:
    if not isinstance(row, dict):
      raise ValueError('Invalid parsed source projection row.')
    if set(row) == {'entry'} and isinstance(row['entry'], dict):
      entries.append(deepcopy(row['entry']))
      continue
    reference, overrides, removed = row.get('reference'), row.get('overrides'), row.get('removed')
    if (set(row) != {'reference', 'overrides', 'removed'} or type(reference) is not int or
        not 0 <= reference < len(projected_rows) or not isinstance(overrides, dict) or
        any(not isinstance(key, str) for key in overrides) or not isinstance(removed, list) or
        any(not isinstance(key, str) for key in removed)):
      raise ValueError('Invalid parsed source projection reference.')
    entry = deepcopy(projected_rows[reference])
    for key in removed:
      entry.pop(key, None)
    entry.update(deepcopy(overrides))
    entries.append(entry)
  return entries


def project_parsed_units(parsed, final_rows, strategy, source_key, identity):
  """Keep original source-year units reversible after cross-year collapsing."""
  source_state = parsed['incremental_state']
  cache = ParsedUnitCache(strategy, source_key)
  for key, unit in source_state['units'].items():
    rows = [parsed['entries'][index] for index in unit['entry_indexes']]
    projected, metadata = project_source_rows(rows, final_rows, identity)
    metadata['source_unit'] = {name: deepcopy(value) for name, value in unit.items()
      if name != 'entry_indexes'}
    cache.put(key, projected, revision=unit.get('revision'),
      complete=unit.get('complete') is True, metadata=metadata)
  state = cache.state(final_rows)
  state['discovery'] = {'original_state': {key: deepcopy(value)
    for key, value in source_state.items() if key != 'units'}}
  return state


def restore_parsed_units(cache):
  header = cache.old_discovery.get('original_state')
  if (not isinstance(header, dict) or header.get('version') != 1 or
      not isinstance(header.get('strategy'), str) or 'source_key' not in header):
    return None
  entries, units = [], {}
  for key, unit in cache.old_units.items():
    metadata = unit.get('metadata', {})
    source_unit = metadata.get('source_unit')
    if not isinstance(source_unit, dict) or not isinstance(source_unit.get('metadata', {}), dict):
      continue
    try:
      rows = restore_source_rows(cache.previous(key), metadata)
    except ValueError:
      continue
    start = len(entries)
    entries.extend(rows)
    units[key] = dict(deepcopy(source_unit), entry_indexes=list(range(start, len(entries))),
      complete=unit.get('complete') is True and source_unit.get('complete') is True)
  return {'entries': entries, 'incremental_state': dict(deepcopy(header), units=units)}


class ParsedUnitCache:

  def __init__(self, strategy, source_key, cached_parsed=None, incremental_update=False):
    self.strategy, self.source_key = strategy, source_key
    self.old_units, self.old_entries, self.units = {}, [], {}
    self.old_discovery = {}
    cache = cached_parsed if incremental_update and isinstance(cached_parsed, dict) else {}
    state = cache.get('incremental_state') or {}
    entries = cache.get('entries')
    if (not isinstance(state, dict) or state.get('version') != 1 or
        state.get('strategy') != strategy or state.get('source_key') != source_key or
        not isinstance(state.get('units'), dict) or not isinstance(entries, list) or
        any(not isinstance(entry, dict) for entry in entries)):
      return
    indexes = set()
    for key, unit in state['units'].items():
      if (not isinstance(key, str) or not isinstance(unit, dict) or
          not isinstance(unit.get('metadata', {}), dict) or
          not isinstance(unit.get('entry_indexes'), list) or
          any(type(i) is not int or not 0 <= i < len(entries) for i in unit['entry_indexes'])):
        return
      indexes.update(unit['entry_indexes'])
    if indexes != set(range(len(entries))):
      return
    self.old_units, self.old_entries = deepcopy(state['units']), deepcopy(entries)
    if isinstance(state.get('discovery'),dict):
      self.old_discovery = deepcopy(state['discovery'])

  def previous(self, key):
    unit = self.old_units.get(key)
    return [deepcopy(self.old_entries[i]) for i in unit['entry_indexes']] if unit else []

  def reuse(self, key, revision=None):
    unit = self.old_units.get(key)
    if not unit or unit.get('complete') is not True or unit.get('revision') != revision:
      return None
    entries = self.previous(key)
    self.put(key, entries, revision, metadata=unit.get('metadata'))
    return entries

  def put(self, key, entries, revision=None, complete=True, metadata=None):
    self.units[key] = {'entries': deepcopy(entries), 'revision': revision,
      'complete': bool(complete), 'metadata': deepcopy(metadata or {})}

  def failed(self, key, revision=None):
    entries = self.previous(key)
    self.put(key, entries, revision, complete=False,
      metadata=(self.old_units.get(key) or {}).get('metadata'))
    return entries

  def state(self, entries, identity=entry_fingerprint):
    indexes = {}
    for i, entry in enumerate(entries):
      key = identity(entry)
      indexes[key] = i if key not in indexes else None
    units = {}
    for key, unit in self.units.items():
      fingerprints = [identity(e) for e in unit['entries']]
      # A caller may deliberately drop a duplicate or obsolete row. Incomplete
      # mapping must force rediscovery rather than certifying partial history.
      complete = unit['complete'] and all(indexes.get(f) is not None for f in fingerprints)
      units[key] = {'revision': unit['revision'], 'complete': complete,
        'entry_indexes': [indexes[f] for f in fingerprints if indexes.get(f) is not None]}
      if unit['metadata']:
        units[key]['metadata'] = unit['metadata']
    return {'version': 1, 'strategy': self.strategy, 'source_key': self.source_key,
      'units': units}
