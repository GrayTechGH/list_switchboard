"""Regression coverage for deterministic, clean plugin packaging."""

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from _dev_tools.build_plugin import (
  REQUIRED_MEMBERS,
  RUNTIME_ROOT_FILES,
  build_plugin,
  smoke_check_package,
)


class ReleasePackageTests(unittest.TestCase):

  def test_build_contains_only_runtime_assets(self):
    with tempfile.TemporaryDirectory() as folder:
      archive = build_plugin(Path(folder) / 'ListSwitchboard-1.8.0.zip')
      members = set(smoke_check_package(archive))

    self.assertTrue(REQUIRED_MEMBERS <= members)
    self.assertTrue(RUNTIME_ROOT_FILES <= members)
    self.assertIn('transport/__init__.py', members)
    self.assertIn('transport/camoufox.py', members)
    self.assertIn('transport/wayback.py', members)
    self.assertTrue({
      'camoufox_transport.py', 'goodreads.py', 'goodreads_recovery_transport.py',
      'http_policy.py', 'sfadb_transport.py', 'wayback_policy.py',
    }.isdisjoint(members))
    self.assertIn('url_fetcher/goodreads_choice_transport.py', members)
    self.assertIn('url_fetcher/dragons_and_jetpacks_transport.py', members)
    self.assertIn('url_fetcher/ladies_of_horror_fiction_transport.py', members)
    self.assertIn('url_fetcher/splatterpunk_transport.py', members)
    self.assertIn('url_fetcher/this_is_horror_transport.py', members)
    self.assertIn('goodreads/__init__.py', members)
    self.assertIn('goodreads/lookup.py', members)
    self.assertIn('goodreads/recovery_transport.py', members)
    self.assertIn('transport/http.py', members)
    self.assertIn('transport/sfadb.py', members)
    self.assertIn('url_fetcher/isfdb_transport.py', members)
    self.assertIn('url_fetcher/isfdb_originals.py', members)
    self.assertIn('parser/isfdb_title.py', members)
    self.assertIn('url_fetcher/spsfc_transport.py', members)
    self.assertFalse(any('__pycache__' in name or name.endswith('.bak') for name in members))

  def test_package_check_rejects_development_residue(self):
    with tempfile.TemporaryDirectory() as folder:
      archive = Path(folder) / 'invalid.zip'
      with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('__init__.py', '')
        output.writestr('dialogs/import_recipe.py.bak', '')

      with self.assertRaisesRegex(ValueError, 'development residue'):
        smoke_check_package(archive)

  def test_build_is_byte_reproducible(self):
    with tempfile.TemporaryDirectory() as folder:
      first = build_plugin(Path(folder) / 'first.zip')
      second = build_plugin(Path(folder) / 'second.zip')

      self.assertEqual(
        hashlib.sha256(first.read_bytes()).digest(),
        hashlib.sha256(second.read_bytes()).digest())


if __name__ == '__main__':
  unittest.main()
