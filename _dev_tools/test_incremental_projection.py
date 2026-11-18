import json
import unittest

from parser.incremental import (
  ParsedUnitCache, project_source_rows, restore_source_rows,
  project_parsed_units, restore_parsed_units,
)


class ParsedSourceProjectionTests(unittest.TestCase):

  def identity(self, entry):
    return entry['title']

  def test_roundtrip_preserves_raw_source_position_result_and_provenance(self):
    source = [{'title': 'Book', 'position': '2024.01', 'result': 'nominee',
      'source': {'url': 'annual-post'}, 'authors': ['Writer']}]
    final = [dict(source[0], position='2024', result='winner',
      source={'url': 'history'}, extra='merged-only')]
    projected, metadata = project_source_rows(source, final, self.identity)
    metadata = json.loads(json.dumps(metadata))
    self.assertEqual(source, restore_source_rows(projected, metadata))
    self.assertNotIn('authors', metadata['rows'][0]['overrides'])
    self.assertEqual(final, projected)

  def test_omitted_or_ambiguous_source_rows_are_retained_without_guessing(self):
    source = [{'title': 'Omitted', 'authors': ['One']}, {'title': 'Ambiguous', 'authors': ['Two']}]
    final = [{'title': 'Ambiguous', 'authors': ['Two']}, {'title': 'Ambiguous', 'authors': ['Three']}]
    projected, metadata = project_source_rows(source, final, self.identity)
    self.assertEqual([], projected)
    self.assertEqual(source, restore_source_rows(projected, metadata))

  def test_references_are_local_and_do_not_follow_other_unit_indexes(self):
    source = [{'title': 'Second', 'position': '2'}]
    final = [{'title': 'First'}, {'title': 'Second', 'position': '99'}]
    projected, metadata = project_source_rows(source, final, self.identity)
    self.assertEqual(0, metadata['rows'][0]['reference'])
    self.assertEqual(source, restore_source_rows(projected, metadata))
    self.assertEqual([], restore_source_rows([], {'projection_version': 1, 'rows': []}))

  def test_bad_projection_requires_refetch(self):
    invalid = ({}, {'projection_version': 1, 'rows': [None]},
      {'projection_version': 1, 'rows': [{'reference': 7, 'overrides': {}, 'removed': []}]})
    for metadata in invalid:
      with self.subTest(metadata=metadata), self.assertRaises(ValueError):
        restore_source_rows([], metadata)

  def projected_year_cache(self):
    raw = [
      {'title': 'Repeated', 'position': '2020.01', 'award_year': '2020', 'result': 'nominee'},
      {'title': 'Unique', 'position': '2020', 'award_year': '2020', 'result': 'winner'},
      {'title': 'Repeated', 'position': '2021', 'award_year': '2021', 'result': 'winner'},
    ]
    source = ParsedUnitCache('raw-years', 'source')
    source.put('2020', raw[:2], 2020, metadata={'settled': True})
    source.put('2021', raw[2:], 2021, metadata={'settled': True})
    parsed = {'entries': raw, 'incremental_state': source.state(raw)}
    final = [raw[1], raw[2]]
    state = project_parsed_units(parsed, final, 'collapsed', 'scope', self.identity)
    return parsed, json.loads(json.dumps({'entries': final, 'incremental_state': state}))

  def test_collapsed_year_projection_retains_original_nomination_and_winner_units(self):
    original, saved = self.projected_year_cache()
    restored = restore_parsed_units(ParsedUnitCache('collapsed', 'scope', saved, True))
    for key, unit in original['incremental_state']['units'].items():
      raw = [original['entries'][i] for i in unit['entry_indexes']]
      current = restored['incremental_state']['units'][key]
      self.assertEqual(raw, [restored['entries'][i] for i in current['entry_indexes']])
      self.assertEqual(unit['metadata'], current['metadata'])

  def test_bad_year_projection_is_missing_for_refetch_without_losing_other_units(self):
    _original, saved = self.projected_year_cache()
    saved['incremental_state']['units']['2020']['metadata']['rows'] = [None]
    restored = restore_parsed_units(ParsedUnitCache('collapsed', 'scope', saved, True))
    self.assertNotIn('2020', restored['incremental_state']['units'])
    self.assertIn('2021', restored['incremental_state']['units'])

  def test_failed_year_stays_pending_and_different_scope_cannot_restore_it(self):
    _original, saved = self.projected_year_cache()
    saved['incremental_state']['units']['2020']['complete'] = False
    restored = restore_parsed_units(ParsedUnitCache('collapsed', 'scope', saved, True))
    self.assertFalse(restored['incremental_state']['units']['2020']['complete'])
    self.assertIsNone(restore_parsed_units(ParsedUnitCache('collapsed', 'other', saved, True)))


if __name__ == '__main__':
  unittest.main()
