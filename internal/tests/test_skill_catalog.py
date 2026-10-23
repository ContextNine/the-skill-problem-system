from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[2]
SRC = PACKAGE / 'internal/src'
sys.path.insert(0, str(SRC))

import package_export
from package_installer import WORKSPACE_SYNC_HELPERS, install
import skill_catalog
import skill_snapshots
import sync_skills
import working_repo_skills


class SkillCatalogIntegrationTests(unittest.TestCase):
    def skill(self, source: Path, group: str, name: str) -> Path:
        path = source / 'edit/skills' / group / name
        (path / 'agents').mkdir(parents=True)
        (path / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: Example.\n---\n# Example\n')
        (path / 'agents/openai.yaml').write_text('policy:\n  allow_implicit_invocation: false\n')
        return path

    def fixture(self, root: Path) -> tuple[Path, Path]:
        source, home = root / 'source', root / 'home'
        home.mkdir()
        for name in ('src', 'schemas', 'defaults'):
            shutil.copytree(PACKAGE / 'internal' / name, source / 'internal' / name,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for name in WORKSPACE_SYNC_HELPERS:
            target = source / 'internal/src' / name
            if not target.exists():
                shutil.copy2(PACKAGE / 'edit/skills/areas/fleet/fleet-i-sync-code-workspaces/scripts' / name, target)
        shutil.copytree(source / 'internal/defaults/settings', source / 'edit/settings')
        for name in ('alpha', 'beta', 'zero', 'unrated'):
            self.skill(source, 'areas/uiux', name)
        self.skill(source, 'areas/creative', 'other')
        self.skill(source, 'collections/local-pack/nested', 'pack-skill')
        upstream = self.skill(source, 'github/example/skills', 'imported')
        doc = upstream / 'SKILL.md'
        doc.write_text(doc.read_text().replace('description: Example.',
            'description: Example.\nmetadata:\n  github-repo: https://github.com/example/skills\n'
            '  github-path: skills/imported\n  github-ref: refs/heads/main\n'
            '  github-tree-sha: ' + 'a' * 40))
        repo = home / 'Code/app'
        (repo / '.agents/skills/app-skill').mkdir(parents=True)
        (repo / '.agents/skills/app-skill/SKILL.md').write_text('---\nname: app-skill\ndescription: Example.\n---\n# App\n')
        (source / 'edit/settings/skills/skill-sources.json').write_text(json.dumps({
            'schema_version': 4, 'gh_skills': {},
            'repos': [{'path': '~/Code/app', 'github': 'https://github.com/example/app', 'all_skills': True}]}))
        install(source, home, apply=True, global_instructions=False, claude_alias=False,
                discovery_aliases=True, machine_id='primary', initialize_source=True)
        return source, home

    def cli(self, home: Path, *args: str, success: bool = True, json_output: bool = True):
        result = subprocess.run(
            [sys.executable, str(home / '.agents/internal/src/fleet.py'), 'skills', *args],
            env={**os.environ, 'HOME': str(home)}, capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stderr)
        return json.loads(result.stdout) if success and json_output else result

    def test_folder_discovery_ratings_cli_and_offline_worker(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, home = self.fixture(Path(temporary))
            self.cli(home, 'rate', 'alpha', '5')
            self.cli(home, 'rate', 'beta', '5')
            self.cli(home, 'rate', 'zero', '0')
            self.cli(home, 'rate', 'other', '4')
            self.cli(home, 'rate', 'imported', '5')
            rows = self.cli(home, 'list', '--json')['skills']
            self.assertTrue(all(r['area'] is not None or r['collection'] is not None for r in rows))
            self.assertEqual([r['name'] for r in rows],
                ['other', 'alpha', 'beta', 'zero', 'unrated', 'app-skill', 'imported', 'pack-skill'])
            self.assertEqual([r['name'] for r in self.cli(home, 'list', '--area', 'uiux', '--min-rating', '4', '--json')['skills']], ['alpha', 'beta'])
            union = self.cli(home, 'list', '--area', 'uiux', '--collection', 'example', '--json')['skills']
            self.assertEqual({r['name'] for r in union}, {'alpha', 'beta', 'zero', 'unrated', 'imported'})
            flat = self.cli(home, 'list', '--group-by', 'none', '--sort', 'rating', '--descending', '--json')['skills']
            self.assertEqual([r['name'] for r in flat][:5], ['alpha', 'beta', 'imported', 'other', 'zero'])
            preferred = self.cli(home, 'list', '--group-by', 'none', '--json')['skills']
            self.assertLess([r['name'] for r in preferred].index('pack-skill'), [r['name'] for r in preferred].index('imported'))
            text = self.cli(home, 'list', '--area', 'uiux', '--sort', 'name', json_output=False).stdout
            self.assertIn('alpha', text)
            self.cli(home, 'list', '--unrated', '--rating', '0', success=False)
            self.cli(home, 'list', '--descending', success=False)
            metadata = source / skill_catalog.METADATA_RELATIVE
            before = skill_catalog.read_metadata(metadata)
            moved = source / 'edit/skills/areas/creative/alpha'
            (source / 'edit/skills/areas/uiux/alpha').rename(moved)
            self.skill(source, 'areas/new-area', 'added')
            self.skill(source, 'collections/new-pack', 'added-pack')
            self.assertEqual(self.cli(home, 'list', '--area', 'creative', '--rating', '5', '--json')['skills'][0]['name'], 'alpha')
            self.assertEqual(self.cli(home, 'list', '--collection', 'new-pack', '--json')['skills'][0]['name'], 'added-pack')
            self.assertEqual(skill_catalog.read_metadata(metadata), before)
            self.cli(home, 'rate', 'beta', '--clear')
            self.assertIsNone(next(r for r in self.cli(home, 'list', '--area', 'uiux', '--json')['skills'] if r['name'] == 'beta')['rating'])

            # Distribute the same grouping and ratings to a worker, then browse offline.
            worker = Path(temporary) / 'worker'
            install(source, worker, apply=True, global_instructions=False, claude_alias=False,
                    discovery_aliases=True, machine_id='primary')
            # A worker uses its installed catalog even when an older checkout exists.
            registry_path = worker / '.agents/settings/fleet/machines.json'
            registry = json.loads(registry_path.read_text())
            registry['machines'][0]['role'] = 'worker'
            primary = dict(registry['machines'][0], id='source-owner', role='primary')
            registry['machines'].append(primary)
            registry['primary_machine_id'] = 'source-owner'
            registry_path.write_text(json.dumps(registry))
            install(source, worker, apply=True, global_instructions=False, claude_alias=False,
                    discovery_aliases=True, runtime_upgrade=True)
            self.assertEqual((worker / '.agents/state/machine-id').read_text().strip(), 'primary')
            changed_source = skill_catalog.read_metadata(metadata)
            changed_source['alpha']['rating'] = 0
            metadata.write_text(json.dumps({'schema_version': 1, 'skills': changed_source}))
            self.assertEqual(self.cli(worker, 'list', '--area', 'creative', '--rating', '5', '--json')['skills'][0]['name'], 'alpha')
            worker_rows = self.cli(worker, 'list', '--collection', 'local-pack', '--json')['skills']
            self.assertEqual(worker_rows[0]['collection'], 'local-pack')
            source.rename(Path(temporary) / 'offline-source')
            self.assertEqual(self.cli(worker, 'list', '--area', 'creative', '--rating', '5', '--json')['skills'][0]['name'], 'alpha')
            self.assertIn('source owner', self.cli(worker, 'rate', 'alpha', '4', success=False).stderr)

    def test_imported_pack_area_filters_and_offline_distribution(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, home = self.fixture(Path(temporary))
            policy_path = source / working_repo_skills.SELECTION
            policy = json.loads(policy_path.read_text())
            original = (source / 'edit/skills/github/example/skills/imported/SKILL.md').read_bytes()
            policy['gh_skills']['example'] = {'area': 'creative'}
            policy_path.write_text(json.dumps(policy))
            self.cli(home, 'rate', 'imported', '4')
            creative = self.cli(home, 'list', '--area', 'creative', '--json')['skills']
            imported = next(row for row in creative if row['name'] == 'imported')
            self.assertEqual(imported, {
                'name': 'imported', 'area': 'creative', 'collection': 'example',
                'rating': 4, 'source': 'gh', 'mode': 'manual',
            })
            self.assertEqual(self.cli(home, 'list', '--collection', 'example', '--json')['skills'], [imported])
            _, skills = sync_skills.discover_skills(source, home=home)
            projected = next(skill for skill in skills if skill.name == 'imported')
            working_repo_skills.apply(working_repo_skills.plan(source, home=home), source)
            bundle = skill_snapshots.build_bundle({'imported': projected.path}, catalog={'imported': imported})
            worker = Path(temporary) / 'worker'
            worker.mkdir()
            payload = skill_snapshots.payload_for(worker, bundle, apply=True, verify=False,
                                                  backup_suffix='test', legacy_catalog=None)
            with patch.object(Path, 'home', return_value=worker):
                self.assertTrue(skill_snapshots.reconcile_payload(payload)['ready'])
            with patch.object(skill_catalog, 'source_root', return_value=None):
                self.assertEqual(skill_catalog.catalog(worker), {'imported': imported})
            self.assertEqual((source / 'edit/skills/github/example/skills/imported/SKILL.md').read_bytes(), original)
            for invalid_area in ('../creative', '', 'Creative', None):
                policy['gh_skills']['example']['area'] = invalid_area
                policy_path.write_text(json.dumps(policy))
                self.cli(home, 'list', '--json', success=False)

    def test_public_export_install_groups_and_filtered_ratings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source, home = self.fixture(root)
            policy_path = source / working_repo_skills.SELECTION
            policy = json.loads(policy_path.read_text())
            policy['gh_skills']['example'] = {'area': 'creative'}
            policy_path.write_text(json.dumps(policy))
            self.cli(home, 'rate', 'alpha', '4')
            self.cli(home, 'rate', 'imported', '5')
            self.cli(home, 'rate', 'pack-skill', '2')
            working_repo_skills.apply(working_repo_skills.plan(source, home=home), source)
            privacy = root / 'privacy.json'
            privacy.write_text(json.dumps({'schema_version': 2,
                'exclude': ['skills/collections/local-pack/**'], 'partial_hiding': []}))
            (source / 'AGENTS.md').write_text('# Public instructions\n')
            manifest = source / 'export.json'
            manifest.write_text(json.dumps({'schema_version': 2,
                'default_export_root': str(root / 'unused'),
                'trees': [{'source': f'internal/{name}', 'target': f'internal/{name}'}
                          for name in ('src', 'schemas', 'defaults')]
                          + [{'source': 'internal/defaults/settings', 'target': 'edit/settings'}],
                'files': [{'source': 'AGENTS.md', 'target': 'AGENTS.md'}],
                'third_party_licenses': {'https://github.com/example/skills': {
                    'spdx': 'MIT', 'license_url': 'https://github.com/example/skills/blob/main/LICENSE'}}}))
            destination = root / 'public'
            with patch.object(package_export, 'AGENTS_ROOT', source), patch.object(package_export, 'VAULT_ROOT', source), patch.object(Path, 'home', return_value=home):
                report = package_export.export(destination, apply=True, manifest_path=manifest, privacy_path=privacy)
            included = {r['name'] for r in report['skill_inventory'] if r['status'] == 'included'}
            exported = skill_catalog.read_metadata(destination / skill_catalog.METADATA_RELATIVE)
            self.assertEqual(set(exported), {'alpha', 'imported'} & included)
            public_home = root / 'public-home'
            install(destination, public_home, apply=True, global_instructions=False, claude_alias=False,
                    discovery_aliases=True, machine_id='primary', initialize_source=True)
            self.assertEqual(self.cli(public_home, 'list', '--area', 'uiux', '--rating', '4', '--json')['skills'][0]['name'], 'alpha')
            self.assertEqual(self.cli(public_home, 'list', '--collection', 'example', '--json')['skills'][0]['name'], 'imported')
            self.assertEqual(self.cli(public_home, 'list', '--area', 'creative', '--rating', '5', '--json')['skills'][0]['name'], 'imported')
            self.assertTrue(all((public_home / '.agents/internal/src' / name).is_file() for name in WORKSPACE_SYNC_HELPERS))


if __name__ == '__main__':
    unittest.main()
