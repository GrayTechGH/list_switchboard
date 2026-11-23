"""Run read-only browser-backed imports with temporary configuration.

Invoke with the repo venv. The child uses calibre-debug, temporary config and
cache directories, and no Calibre database. --live permits actual requests;
Calibre's shared browser installation is reused and may be updated by Calibre.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types


ROOT = Path(__file__).resolve().parents[1]


def replay_bookclub(payload, recipe):
  """Offline rendered-shape comparison, not a browser-availability test."""
  from markdown import markdown
  parser = recipe.parser()
  source = parser.markdown_from_payload(payload)
  if not source:
    raise ValueError('Replay requires a wiki Markdown/source-view payload.')
  html = ('<html><title>Reddit</title><body><shreddit-app><main>'
    '<div class="md wiki">' + markdown(source) + '</div></main>'
    '<aside><p>Anyone can view, post, and comment to this community</p></aside>'
    '<footer><p>Reddit, Inc. all rights reserved</p></footer></shreddit-app></body></html>')
  expected, actual = recipe.parse(payload), recipe.parse(html)
  differences = []
  for index, (left, right) in enumerate(zip(actual['entries'], expected['entries']), 1):
    if left != right:
      differences.append({'position': index, 'title': right['title'],
        'fields': [key for key in sorted(set(left) | set(right)) if left.get(key) != right.get(key)]})
  print(f'Rendered-shape replay: html={len(actual["entries"])} markdown={len(expected["entries"])} '
    f'different_rows={len(differences)} first_differences={differences[:12]}', flush=True)
  return bool(differences or len(actual['entries']) != len(expected['entries']))


def compare_bookclub(core, prefs, recipe, capture_dir=None):
  """Capture public pages outside runtime caches and compare full entry schemas."""
  from bs4 import BeautifulSoup
  folder = Path(capture_dir) if capture_dir else Path(tempfile.mkdtemp(prefix='list-switchboard-bookclub-capture-'))
  folder.mkdir(parents=True, exist_ok=True)
  print(f'Bookclub diagnostic snapshots: {folder}', flush=True)
  browser = None
  try:
    html = core.fetch_url(recipe.URL, transport='camoufox')
    (folder / 'rendered.html').write_text(html, encoding='utf-8')
    soup = BeautifulSoup(html, 'html.parser')
    heading = soup.find(['h1', 'h2', 'h3'], string=lambda s: s and s.strip() == 'Previous Selections')
    if heading is None:
      heading = next((h for h in soup.find_all(['h1', 'h2', 'h3'])
        if h.get_text(' ', strip=True) == 'Previous Selections'), None)
    ancestors = []
    if heading is not None:
      for node in heading.parents:
        ancestors.append({'tag': node.name, 'id': node.get('id'), 'class': node.get('class'), 'slot': node.get('slot')})
    print(f'Wiki heading ancestors: {ancestors}', flush=True)
    browser = recipe.parse(html)
  except Exception as err:
    from calibre_plugins.list_switchboard.errors import ImportCancelledError
    if isinstance(err, ImportCancelledError):
      raise
    print(f'FAIL browser capture/parse: {err}', flush=True)
  finally:
    core.close_camoufox_transport()
  if browser is not None:
    (folder / 'browser_entries.json').write_text(json.dumps(browser, ensure_ascii=False, indent=2), encoding='utf-8')
  prefs['debug_browser_fallback_level'] = 2
  captured = []

  def record(url, html):
    captured.append(url)
    (folder / f'legacy-{len(captured)}.html').write_text(html, encoding='utf-8')

  core.debug_recipe_fetched = record
  legacy = core.fetch_and_parse_recipe(recipe)
  (folder / 'legacy_entries.json').write_text(json.dumps(legacy, ensure_ascii=False, indent=2), encoding='utf-8')
  if browser is None:
    print(f'Legacy capture: entries={len(legacy["entries"])}; browser comparison unavailable', flush=True)
    return True
  different = []
  for index in range(max(len(browser['entries']), len(legacy['entries']))):
    left = browser['entries'][index] if index < len(browser['entries']) else None
    right = legacy['entries'][index] if index < len(legacy['entries']) else None
    if left != right:
      different.append({'position': index + 1,
        'fields': [key for key in sorted(set(left or {}) | set(right or {}))
          if (left or {}).get(key) != (right or {}).get(key)]})
  print(f'Bookclub comparison: browser={len(browser["entries"])} legacy={len(legacy["entries"])} '
    f'different_rows={len(different)} first_differences={different[:8]} '
    f'legacy_attempts={captured}', flush=True)
  return bool(different)


def check_goodreads_recovery(core, capture_dir=None, source_first=False):
  """Live transport/extraction plus a forced recovery probe in an in-memory DB."""
  from calibre_plugins.list_switchboard.transport.camoufox import browser_operation
  book_url = 'https://www.goodreads.com/book/show/3'
  source_url = 'https://www.goodreads.com/series/45107-the-abbey-girls'
  messages = []
  original = core.debug_camoufox

  def report(message):
    messages.append(message)
    original(message)

  core.debug_camoufox = report
  if capture_dir is not None:
    fetch = core.fetch_url

    def capture(url, **kwargs):
      html = fetch(url, **kwargs)
      capture_dir.mkdir(parents=True, exist_ok=True)
      role = 'book' if '/book/show/' in url else 'source'
      (capture_dir / f'recovery-{role}-{kwargs.get("transport", "legacy")}.html').write_text(html, encoding='utf-8')
      return html

    core.fetch_url = capture
  started = time.monotonic()
  with browser_operation(core):
    # The low-level boundary raises on blocking; an empty best-effort lookup
    # must not disguise failed transport as a passing live check.
    payloads = {}
    failures = []
    urls = (source_url, book_url) if source_first else (book_url, source_url)
    for url in urls:
      try:
        payloads[url] = core.fetch_goodreads_url(url)
      except Exception as err:
        from calibre_plugins.list_switchboard.errors import ImportCancelledError
        if isinstance(err, ImportCancelledError):
          raise
        failures.append(f'{url}: {err}')
    series = core.extract_goodreads_series_names(payloads.get(book_url, ''))
    data = core.extract_goodreads_source_data(payloads.get(source_url, ''))
    print(f'Goodreads recovery evidence: series={series} books={len(data["books"])} failures={failures}', flush=True)
    if not data['books']:
      raise RuntimeError(f'No usable live source evidence: {failures}')
    first = next((book for book in data['books'] if book.get('author')), None)
    if first is None:
      raise RuntimeError('No source book with author evidence')

    class ReadOnlyApi:
      def all_field_for(self, field, ids, default_value=''):
        return {1: first['title'] if field == 'title' else ([first['author']] if field == 'authors' else [])}

    core.db = types.SimpleNamespace(new_api=ReadOnlyApi())
    core.all_book_ids = lambda: [1]
    core.all_local_series_values = lambda ids: {1: []}
    core.saved_unmatched_overrides = lambda list_id: {}
    core.saved_match_overrides = lambda list_id: {}
    core.goodreads_id_for_book = lambda book_id: ''
    # Explicitly force the recovery branch for this diagnostic only; the
    # production local-first matcher and its tight evidence rules are unchanged.
    core.import_list_review_auto_candidates_for_entry = lambda *a, **kw: []
    core.goodreads_series_cache['source:' + source_url] = data
    entry = {'position': '1', 'title': first['title'], 'authors': [first['author']], 'source': {'url': source_url}}
    matched, missing = core.match_imported_entries([entry])
    if matched != {1: '1'} or missing:
      raise RuntimeError(f'In-memory recovery probe failed: matched={matched}, missing={missing}')
    accepted = [line for line in messages if 'Goodreads recovery role=' in line and ' accepted ' in line]
    print(f'PASS Goodreads source recovery: books={len(data["books"])} '
      f'forced_in_memory_match={matched} accepted={accepted} seconds={time.monotonic()-started:.1f}', flush=True)
    if failures or not series:
      raise RuntimeError(f'Book/source checks incomplete: {failures}; series={series}')
    print('PASS Goodreads recovery: both lookup types verified', flush=True)
  if core.goodreads_series_cache or core.camoufox_transport is not None:
    raise RuntimeError('Recovery operation did not release its state')


def observe_goodreads_pages(recipe, results):
  original = recipe.fetch_parse_goodreads_pages
  def observe(*args, **kwargs):
    pages = original(*args, **kwargs)
    results.extend(pages)
    return pages
  recipe.fetch_parse_goodreads_pages = observe
  return recipe


def worker(args):
  sys.path.insert(0, str(ROOT))
  # Load the checkout under its real plugin namespace without installing it.
  package = types.ModuleType('calibre_plugins.list_switchboard')
  package.__path__ = [str(ROOT)]
  sys.modules['calibre_plugins.list_switchboard'] = package
  from qt.core import QApplication
  from calibre.constants import numeric_version, config_dir, cache_dir
  from calibre_plugins.list_switchboard.config import prefs
  from calibre_plugins.list_switchboard.main import ListSwitchboardCore
  from calibre_plugins.list_switchboard.transport import camoufox as camoufox_transport
  from bs4 import BeautifulSoup
  from calibre_plugins.list_switchboard.url_fetcher.strand import UrlFetcherStrandMysteryNovel
  from calibre_plugins.list_switchboard.url_fetcher.davitt import UrlFetcherDavittAdultNovel
  from calibre_plugins.list_switchboard.url_fetcher.macavity import UrlFetcherMacavityMysteryNovel
  from calibre_plugins.list_switchboard.url_fetcher.r_bookclub import UrlFetcherRBookclub
  from calibre_plugins.list_switchboard.url_fetcher.r_fantasy_top_novels_2025 import UrlFetcherRFantasyTopNovels2025
  from calibre_plugins.list_switchboard.url_fetcher.r_fantasy_top_standalone_novels_2024 import UrlFetcherRFantasyTopStandaloneNovels2024
  from calibre_plugins.list_switchboard.url_fetcher.r_fantasy_top_self_published_novels_2024 import UrlFetcherRFantasyTopSelfPublishedNovels2024
  from calibre_plugins.list_switchboard.url_fetcher.dragons_and_jetpacks import UrlFetcherDragonsJetpacks
  from calibre_plugins.list_switchboard.url_fetcher.pulitzer import (
    UrlFetcherPulitzerFiction, UrlFetcherPulitzerGeneralNonfiction)
  from calibre_plugins.list_switchboard.url_fetcher.goodreads_choice_awards import (
    UrlFetcherGoodreadsChoiceAwardsFiction, UrlFetcherGoodreadsChoiceAwardsFantasy)

  from calibre_plugins.list_switchboard.url_fetcher import ladies_of_horror_fiction as lohf
  from calibre_plugins.list_switchboard.url_fetcher import splatterpunk
  from calibre_plugins.list_switchboard.url_fetcher import this_is_horror

  sandbox = Path(args.worker).resolve()
  for path in (config_dir, cache_dir()):
    if not Path(path).resolve().is_relative_to(sandbox):
      raise RuntimeError(f'Calibre configuration escaped smoke sandbox: {path}')
  app = QApplication.instance() or QApplication([])
  prefs['debug_sections'] = {'camoufox': not args.summary_only, 'errors': True}
  prefs['camoufox_first_use_confirmed'] = True
  prefs['debug_librarything_transport'] = args.mode
  prefs['debug_browser_fallback_level'] = args.browser_stage
  prefs['debug_force_fallback_level'] = args.source_level
  detector = camoufox_transport.is_challenge_payload

  def diagnose_payload(html):
    soup = BeautifulSoup(html, 'html.parser')
    title = soup.title.get_text(' ', strip=True) if soup.title else ''
    print(f'Payload structure: title={title!r} tables={len(soup.find_all("table"))} '
      f'work_links={len(soup.select("a[href*=\"/work/\"]"))}', flush=True)
    return detector(html)

  camoufox_transport.is_challenge_payload = diagnose_payload
  if args.compare_bookclub:
    core = ListSwitchboardCore(None, lambda **_kwargs: None)
    core.update_import_progress = lambda *_a, **_kw: app.processEvents()
    return compare_bookclub(core, prefs, UrlFetcherRBookclub(), args.capture_dir)
  if args.cancel:
    from calibre_plugins.list_switchboard.errors import ImportCancelledError
    started = time.monotonic()

    def cancel_in_flight(_message):
      app.processEvents()
      if time.monotonic() - started >= 2:
        raise ImportCancelledError('Isolated cancellation check')

    core = ListSwitchboardCore(None, lambda **_kwargs: None)
    core.update_import_progress = lambda *_a, **_kw: cancel_in_flight('')
    target = {
      'bookclub': UrlFetcherRBookclub.URL,
      'pulitzer': UrlFetcherPulitzerFiction.URL,
      'pulitzer-fiction': UrlFetcherPulitzerFiction.URL,
      'pulitzer-nonfiction': UrlFetcherPulitzerGeneralNonfiction.URL,
      'goodreads': UrlFetcherGoodreadsChoiceAwardsFiction.URL,
      'goodreads-fiction': UrlFetcherGoodreadsChoiceAwardsFiction.URL,
      'goodreads-fantasy': UrlFetcherGoodreadsChoiceAwardsFantasy.URL,
    }.get(args.recipe, UrlFetcherStrandMysteryNovel.URL)
    try:
      if args.recipe == 'goodreads-recovery':
        core.fetch_goodreads_series_names('3')
      elif args.recipe == 'r-fantasy' or args.recipe.startswith('r-fantasy-'):
        core.fetch_and_parse_recipe(UrlFetcherRFantasyTopNovels2025(), {'source_choice': 2})
      elif args.recipe == 'this-is-horror' or args.recipe.startswith('this-is-horror-'):
        from calibre_plugins.list_switchboard.url_fetcher.this_is_horror_transport import ThisIsHorrorFetchPolicy
        recipe = this_is_horror.UrlFetcherThisIsHorrorNovel()
        print('Cancellation target: This Is Horror diagnostic Goodreads requests', flush=True)
        with camoufox_transport.browser_operation(core):
          policy = ThisIsHorrorFetchPolicy(core.fetch_url,
            lambda url: recipe.legacy_fetch_url(core.fetch_url, url), recipe.parser())
          recipe.fetch_parse_goodreads_pages(recipe.parser(), policy.fetch, None, None, None)
      elif args.recipe == 'splatterpunk' or args.recipe.startswith('splatterpunk-'):
        core.fetch_and_parse_recipe(splatterpunk.UrlFetcherSplatterpunkNovel())
      elif args.recipe == 'lohf' or args.recipe.startswith('lohf-'):
        core.fetch_and_parse_recipe(lohf.UrlFetcherLadiesOfHorrorFictionNovel())
      elif args.recipe.startswith('goodreads'):
        recipe = (UrlFetcherGoodreadsChoiceAwardsFantasy() if args.recipe == 'goodreads-fantasy'
          else UrlFetcherGoodreadsChoiceAwardsFiction())
        core.fetch_and_parse_recipe(recipe)
      else:
        core.fetch_url(target, transport='camoufox')
      raise RuntimeError('Cancellation was not observed')
    except ImportCancelledError:
      elapsed = time.monotonic() - started
      if elapsed > 8:
        raise RuntimeError(f'Cancellation took {elapsed:.1f} seconds')
      print(f'PASS cancellation: seconds={elapsed:.1f}', flush=True)
      return 0
    finally:
      core.close_camoufox_transport()
  if args.recipe == 'goodreads-recovery':
    core = ListSwitchboardCore(None, lambda **_kwargs: None)
    core.update_import_progress = lambda *_a, **_kw: app.processEvents()
    try:
      check_goodreads_recovery(core, args.capture_dir, args.recovery_source_first)
      return 0
    except Exception as err:
      print(f'FAIL Goodreads recovery: {err}', flush=True)
      return 1
    finally:
      core.close_camoufox_transport()
  recipes = {
    'strand': (UrlFetcherStrandMysteryNovel, 'automatic'),
    'davitt': (UrlFetcherDavittAdultNovel, 0),
    'macavity': (UrlFetcherMacavityMysteryNovel, 2),
    'bookclub': (UrlFetcherRBookclub, 'automatic'),
    'r-fantasy-novels': (UrlFetcherRFantasyTopNovels2025, 'automatic'),
    'r-fantasy-standalone': (UrlFetcherRFantasyTopStandaloneNovels2024, 'automatic'),
    'r-fantasy-self-published': (UrlFetcherRFantasyTopSelfPublishedNovels2024, 'automatic'),
    'dragons': (UrlFetcherDragonsJetpacks, 'automatic'),
    'pulitzer-fiction': (UrlFetcherPulitzerFiction, 'automatic'),
    'pulitzer-nonfiction': (UrlFetcherPulitzerGeneralNonfiction, 'automatic'),
    'goodreads-fiction': (UrlFetcherGoodreadsChoiceAwardsFiction, 'automatic'),
    'goodreads-fantasy': (UrlFetcherGoodreadsChoiceAwardsFantasy, 'automatic'),
  }
  for suffix, class_suffix in (
      ('novel', 'Novel'), ('novella', 'Novella'), ('collection', 'Collection'),
      ('debut', 'Debut'), ('young-adult', 'YoungAdult'), ('middle-grade', 'MiddleGrade'),
      ('poetry-collection', 'PoetryCollection'), ('graphic-novel', 'GraphicNovel')):
    recipes['lohf-' + suffix] = (getattr(lohf, 'UrlFetcherLadiesOfHorrorFiction' + class_suffix), 'automatic')
  for category in ('Novel', 'Novella', 'Collection', 'Anthology'):
    recipes['splatterpunk-' + category.lower()] = (getattr(splatterpunk, 'UrlFetcherSplatterpunk' + category), 'automatic')
  for suffix, category in (('novel', 'Novel'), ('novella', 'Novella'),
      ('short-story-collection', 'ShortStoryCollection'), ('anthology', 'Anthology')):
    recipes['this-is-horror-' + suffix] = (getattr(this_is_horror, 'UrlFetcherThisIsHorror' + category), 'automatic')
  if args.recipe == 'r-fantasy':
    selected = {key: value for key, value in recipes.items() if key.startswith('r-fantasy-')}
  elif args.recipe == 'this-is-horror':
    selected = {key: value for key, value in recipes.items() if key.startswith('this-is-horror-')}
  elif args.recipe == 'splatterpunk':
    selected = {key: value for key, value in recipes.items() if key.startswith('splatterpunk-')}
  elif args.recipe == 'lohf':
    selected = {key: value for key, value in recipes.items() if key.startswith('lohf-')}
  elif args.recipe == 'pulitzer':
    selected = {key: value for key, value in recipes.items() if key.startswith('pulitzer-')}
  elif args.recipe == 'goodreads':
    selected = {key: value for key, value in recipes.items() if key.startswith('goodreads-')}
  else:
    selected = recipes if args.recipe == 'all' else {args.recipe: recipes[args.recipe]}
  print(f'Isolated Calibre {numeric_version}; browser_stage={camoufox_transport.browser_fallback_level(prefs)} '
    f'source_level={args.source_level}', flush=True)
  failures = 0
  for name, (factory, source_choice) in selected.items():
    if args.source_choice is not None:
      source_choice = args.source_choice if args.source_choice == 'automatic' else int(args.source_choice)
    core = ListSwitchboardCore(None, lambda **_kwargs: None)
    browser_messages = []
    original_browser_log = core.debug_camoufox

    def record_browser_log(message):
      browser_messages.append(message)
      original_browser_log(message)

    core.debug_camoufox = record_browser_log
    core.update_import_progress = lambda *_a, **_kw: app.processEvents()
    captured_pages = []

    def fetched(url, html):
      diagnose_payload(html)
      if args.capture_dir is not None:
        args.capture_dir.mkdir(parents=True, exist_ok=True)
        captured_pages.append(url)
        (args.capture_dir / f'{name}-{len(captured_pages)}.html').write_text(html, encoding='utf-8')

    core.debug_recipe_fetched = fetched
    started = time.monotonic()
    try:
      diagnostic_pages = []
      recipe = factory()
      if name.startswith('this-is-horror-'):
        observe_goodreads_pages(recipe, diagnostic_pages)
      parsed = core.fetch_and_parse_recipe(recipe, {'source_choice': source_choice})
      entries = parsed.get('entries') or []
      if not entries:
        raise RuntimeError('No parsed entries')
      newest = max(((int(e.get('selection_year') or 0), int(e.get('selection_month') or 0))
        for e in entries), default=(0, 0))
      award_years = sorted({int(e['award_year']) for e in entries if e.get('award_year')})
      if name in ('goodreads-fiction', 'goodreads-fantasy') and award_years:
        missing_years = sorted(set(range(award_years[0], award_years[-1] + 1)) - set(award_years))
        if missing_years:
          raise RuntimeError(f'Choice history is incomplete; missing award years {missing_years}')
      winners = [e for e in entries if e.get('result') == 'winner']
      winner_years = {}
      for entry in winners:
        year = str(entry.get('award_year') or '')
        winner_years[year] = winner_years.get(year, 0) + 1
      ties = {year: count for year, count in winner_years.items() if count > 1}
      print(f'PASS {name}: entries={len(entries)} seconds={time.monotonic()-started:.1f} '
        f'newest_selection={newest} source={parsed.get("source")} '
        f'award_years={award_years[:1]}..{award_years[-1:]} year_count={len(award_years)} '
        f'winners={len(winners)} nonwinners={len(entries)-len(winners)} ties={ties} '
        f'notes_count={len(parsed.get("notes") or [])} notes_preview={(parsed.get("notes") or [])[:3]}', flush=True)
      if name.startswith('r-fantasy-'):
        accepted = sum(message == f'{recipe.NAME} transport=Camoufox accepted' for message in browser_messages)
        print(f'r/Fantasy outcomes: accepted_browser_pages={accepted} '
          f'legacy_attempts={sum("transport=legacy url=" in message for message in browser_messages)}', flush=True)
      if name.startswith(('lohf-', 'splatterpunk-', 'this-is-horror-')):
        family = ('This Is Horror' if name.startswith('this-is-horror-') else
          'Splatterpunk' if name.startswith('splatterpunk-') else 'LOHF')
        accepted = [m for m in browser_messages if m.startswith(f'{family} Goodreads role=') and ' accepted ' in m]
        counts = {transport: sum(f'transport={transport} ' in m for m in accepted)
          for transport in ('Camoufox', 'legacy')}
        print(f'{family} outcomes: accepted_pages={counts}', flush=True)
        if family == 'This Is Horror':
          print(f'This Is Horror diagnostic entries: {sum(len(p.get("entries", [])) for p in diagnostic_pages)}', flush=True)
          if any('Goodreads diagnostic supplement failed:' in n for n in parsed.get('notes', [])):
            raise RuntimeError('This Is Horror diagnostic supplement failed; unchanged official entries do not establish success')
        if family == 'Splatterpunk':
          print(f'Splatterpunk source failures: {[n for n in parsed.get("notes", []) if "failed:" in n]}', flush=True)
          if any('Goodreads historical supplement failed:' in n for n in parsed.get('notes', [])):
            raise RuntimeError('Splatterpunk historical supplement was discarded; official-only output is not a successful supplement check')
        if ((args.compare_lohf and family == 'LOHF') or
            (args.compare_splatterpunk and family == 'Splatterpunk') or
            (args.compare_this_is_horror and family == 'This Is Horror')):
          if not counts['Camoufox'] or counts['legacy']:
            raise RuntimeError(f'{family} browser comparison unavailable: browser did not supply every award page')
          core.close_camoufox_transport()
          previous_stage = prefs['debug_browser_fallback_level']
          try:
            prefs['debug_browser_fallback_level'] = 2
            legacy_diagnostic_pages = []
            legacy_recipe = factory()
            if family == 'This Is Horror':
              observe_goodreads_pages(legacy_recipe, legacy_diagnostic_pages)
            legacy = core.fetch_and_parse_recipe(legacy_recipe, {'source_choice': source_choice})
          finally:
            prefs['debug_browser_fallback_level'] = previous_stage
          if family == 'This Is Horror' and diagnostic_pages != legacy_diagnostic_pages:
            raise RuntimeError('This Is Horror diagnostic parsed-page schemas differ')
          if parsed != legacy:
            raise RuntimeError(f'{family} browser/legacy complete schema differs (coverage, credits, results, positions, provenance or notes)')
          print(f'PASS {name} complete browser/legacy schema parity', flush=True)
      if name == 'dragons':
        identities = [e['source']['url'] for e in entries]
        if len(set(identities)) != len(entries):
          raise RuntimeError('Duplicate Dragons & Jetpacks activity IDs')
        accepted = [m for m in browser_messages if m.startswith('Dragons & Jetpacks role=') and ' accepted ' in m]
        counts = {transport: sum(f'transport={transport} ' in m for m in accepted)
          for transport in ('Camoufox', 'legacy')}
        print(f'Dragons outcomes: accepted_pages={counts} unique_group_books={len(set(identities))}', flush=True)
        if args.compare_dragons:
          if not counts['Camoufox'] or counts['legacy']:
            raise RuntimeError('Browser comparison unavailable: browser did not supply every shelf page')
          core.close_camoufox_transport()
          previous_stage = prefs['debug_browser_fallback_level']
          try:
            prefs['debug_browser_fallback_level'] = 2
            legacy = core.fetch_and_parse_recipe(factory(), {'source_choice': source_choice})
          finally:
            prefs['debug_browser_fallback_level'] = previous_stage
          if parsed != legacy:
            raise RuntimeError('Browser/legacy complete schema differs (including coverage or metadata)')
          print('PASS Dragons complete browser/legacy schema parity', flush=True)
      if name.startswith('goodreads-'):
        accepted = [m for m in browser_messages if m.startswith('Goodreads Choice role=') and ' accepted ' in m]
        transport_counts = {transport: sum(f'transport={transport} ' in m for m in accepted)
          for transport in ('Camoufox', 'legacy')}
        print(f'Goodreads outcomes: accepted_pages={transport_counts} '
          f'contributor_pages={sum("role=contributors " in m for m in accepted)} '
          f'enrichment_notes={[n for n in parsed.get("notes", []) if "contributor" in n.lower()]}', flush=True)
      if name.startswith('pulitzer-'):
        print(f'Pulitzer coauthor credits: {[(e.get("award_year"), e["title"], e["authors"]) for e in entries if len(e.get("authors", [])) > 1]}', flush=True)
    except Exception as err:
      failures += 1
      print(f'FAIL {name}: seconds={time.monotonic()-started:.1f} {err}', flush=True)
    finally:
      core.close_camoufox_transport()
  return bool(failures)


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--live', action='store_true')
  parser.add_argument('--mode', choices=('automatic', 'camoufox', 'old'), default='automatic')
  parser.add_argument('--browser-stage', type=int, choices=(0, 1, 2))
  parser.add_argument('--source-level', type=int, default=0)
  parser.add_argument('--source-choice', choices=('automatic', '0', '1', '2'))
  parser.add_argument('--compare-this-is-horror', action='store_true', help='Compare both diagnostic pages and final official results against legacy.')
  parser.add_argument('--compare-splatterpunk', action='store_true', help='Compare complete official-plus-historical results with a separate legacy import.')
  parser.add_argument('--compare-lohf', action='store_true', help='Compare all LOHF result fields against a separate legacy import.')
  parser.add_argument('--compare-dragons', action='store_true', help='Compare complete browser/legacy shelf schemas and unique activity IDs.')
  parser.add_argument('--compare-bookclub', action='store_true', help='Compare rendered and legacy entries; save diagnostic snapshots outside runtime caches.')
  parser.add_argument('--recovery-source-first', action='store_true', help='Probe source recovery before the book lookup to isolate site blocking.')
  parser.add_argument('--summary-only', action='store_true', help='Suppress per-request browser logging while retaining outcome totals.')
  parser.add_argument('--capture-dir', type=Path, help='Opt-in diagnostic HTML directory, outside runtime caches.')
  parser.add_argument('--replay-bookclub', type=Path, help='Offline full-schema HTML/Markdown replay of a captured source-view page; no Calibre or network.')
  parser.add_argument('--recipe', choices=(
    'all', 'strand', 'davitt', 'macavity', 'bookclub',
    'r-fantasy', 'r-fantasy-novels', 'r-fantasy-standalone', 'r-fantasy-self-published',
    'pulitzer', 'pulitzer-fiction', 'pulitzer-nonfiction',
    'goodreads', 'goodreads-fiction', 'goodreads-fantasy', 'goodreads-recovery', 'dragons',
    'lohf', 'lohf-novel', 'lohf-novella', 'lohf-collection', 'lohf-debut',
    'lohf-young-adult', 'lohf-middle-grade', 'lohf-poetry-collection', 'lohf-graphic-novel',
    'splatterpunk', 'splatterpunk-novel', 'splatterpunk-novella', 'splatterpunk-collection', 'splatterpunk-anthology',
    'this-is-horror', 'this-is-horror-novel', 'this-is-horror-novella',
    'this-is-horror-short-story-collection', 'this-is-horror-anthology'), default='all')
  parser.add_argument('--worker', help=argparse.SUPPRESS)
  parser.add_argument('--cancel', action='store_true', help='Cancel a real browser request after two seconds.')
  args = parser.parse_args()
  if args.replay_bookclub is not None:
    sys.path.insert(0, str(ROOT))
    from url_fetcher.r_bookclub import UrlFetcherRBookclub
    return replay_bookclub(args.replay_bookclub.read_text(encoding='utf-8'), UrlFetcherRBookclub())
  if args.worker:
    return worker(args)
  if not args.live:
    parser.error('--live is required to permit browser download and network requests')
  if args.compare_bookclub and args.capture_dir is None:
    # Allocate in the launcher: Calibre redirects tempfile into its own
    # process-lifetime folder, which would discard the diagnostic snapshots.
    capture_root = ROOT / '_dev_tools' / 'Scraps Cache' / 'r_bookclub'
    capture_root.mkdir(parents=True, exist_ok=True)
    args.capture_dir = Path(tempfile.mkdtemp(prefix='capture-', dir=capture_root))
  with tempfile.TemporaryDirectory(prefix='list-switchboard-camoufox-') as folder:
    env = dict(os.environ)
    env['CALIBRE_CONFIG_DIRECTORY'] = str(Path(folder) / 'config')
    env['CALIBRE_CACHE_DIRECTORY'] = str(Path(folder) / 'cache')
    command = [
      'calibre-debug', '-e', str(Path(__file__).resolve()), '--', '--worker', folder,
      '--recipe', args.recipe, '--mode', args.mode,
      '--source-level', str(args.source_level),
    ]
    if args.browser_stage is not None:
      command.extend(('--browser-stage', str(args.browser_stage)))
    if args.source_choice is not None:
      command.extend(('--source-choice', args.source_choice))
    if args.compare_bookclub:
      command.append('--compare-bookclub')
    if args.compare_dragons:
      command.append('--compare-dragons')
    if args.compare_lohf:
      command.append('--compare-lohf')
    if args.compare_splatterpunk:
      command.append('--compare-splatterpunk')
    if args.compare_this_is_horror:
      command.append('--compare-this-is-horror')
    if args.recovery_source_first:
      command.append('--recovery-source-first')
    if args.summary_only:
      command.append('--summary-only')
    if args.capture_dir is not None:
      command.extend(('--capture-dir', str(args.capture_dir.resolve())))
    if args.cancel:
      command.append('--cancel')
    return subprocess.call(command, env=env, cwd=ROOT)


if __name__ == '__main__':
  raise SystemExit(main())
