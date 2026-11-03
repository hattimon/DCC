import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from zipfile import ZipFile

import DockerControlCenter as dcc
from dcc_catalog import category_group,localized_categories

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'packaging'/'web'))
from build_source_archive import build_archive, VERSION as WEB_VERSION


class Release1312Tests(unittest.TestCase):
    def test_version_and_bom_installer_sources_match(self):
        self.assertEqual(dcc.APP_VERSION,'1.3.12')
        for language in ('PL','EN'):
            self.assertIn(dcc.APP_VERSION,dcc.TEXTS[language]['info_app_changelog_title'])
        first=(ROOT/'DockerControlCenter.nsi').read_bytes()
        self.assertTrue(first.startswith(b'\xef\xbb\xbf'))
        self.assertEqual(first,(ROOT/'upstream_assets/DockerControlCenter.nsi').read_bytes())

    def test_upgrade_1311_to_1312_is_detected(self):
        harness=SimpleNamespace(_parse_version_value=dcc.MainWindow._parse_version_value)
        # The parser is an instance method; bind it exactly as the running application does.
        harness._parse_version_value=lambda value:dcc.MainWindow._parse_version_value(harness,value)
        with patch.object(dcc,'APP_VERSION','1.3.11'):
            self.assertTrue(dcc.MainWindow._is_newer_version(harness,'v1.3.12'))
            self.assertFalse(dcc.MainWindow._is_newer_version(harness,'v1.3.11'))

    def test_release_assets_are_selected_for_the_correct_platform(self):
        assets={'tag_name':'v1.3.12','assets':[
            {'name':'DockerControlCenter-Setup-1.3.12.exe'},
            {'name':'DockerControlCenter_1.3.12_amd64.deb'},
        ]}
        with patch.object(dcc.sys,'platform','win32'):
            self.assertEqual(dcc.MainWindow.select_update_installer_asset(None,assets)['name'],'DockerControlCenter-Setup-1.3.12.exe')
        with patch.object(dcc.sys,'platform','linux'),patch.object(dcc.platform,'machine',return_value='x86_64'):
            self.assertTrue(dcc.MainWindow.select_update_installer_asset(None,assets)['name'].endswith('_amd64.deb'))
        with patch.object(dcc.sys,'platform','linux'),patch.object(dcc.platform,'machine',return_value='aarch64'):
            self.assertIsNone(dcc.MainWindow.select_update_installer_asset(None,assets))

    def test_canonical_catalog_keeps_all_68_entries_and_updater_configuration(self):
        entries=json.loads((ROOT/'dcc-catalog.json').read_text(encoding='utf-8'))['apps']
        self.assertEqual(len(entries),68)
        updater=next(app for app in entries if app['name']=='DCC Container Updater')
        self.assertEqual(updater['image'],'ghcr.io/hattimon/dcc-container-updater:latest')
        self.assertEqual(updater['default_name'],'dcc-container-updater')
        self.assertEqual(updater['category'],'Aktualizacje 🔄')
        self.assertIn('DCC',updater['categories'])

    def test_web_and_desktop_use_the_same_qt_free_categories(self):
        value=dcc.image_template_from_dict({'name':'Example','image':'example:1','category':'Aktualizacje 🔄','category_en':'Updates 🔄','categories':['DCC']})
        self.assertEqual(value.categories_for('EN'),localized_categories('Aktualizacje 🔄','Updates 🔄',['DCC'],None,'EN'))
        self.assertEqual(category_group('AI 🤖 › Agenci'),'AI')
        self.assertNotIn('PyQt',(ROOT/'dcc_catalog.py').read_text(encoding='utf-8'))

    def test_release_notes_and_readme_reference_new_assets(self):
        notes=(ROOT/'release/RELEASE_NOTES_1.3.12.md').read_text(encoding='utf-8')
        for name in ('DockerControlCenter-Setup-1.3.12.exe','DockerControlCenter_1.3.12_amd64.deb','SHA256SUMS-1.3.12.txt'):
            self.assertIn(name,notes)
        readme=(ROOT/'README.md').read_text(encoding='utf-8')
        self.assertIn('### Download Latest Version',readme)
        for image in ('images/release-1.3.5/09-v1.3.5-overview-en.png','images/release-1.3.5/08-v1.3.5-overview-pl.png'):
            self.assertIn(image,readme)
        self.assertIn('/v1.3.12/',readme)
        self.assertIn(f'DCC%20Web-v{WEB_VERSION}',readme)
        self.assertIn('apps/dcc-web/docs/installation.md',readme)

    def test_dcc_web_source_archive_contains_cross_platform_port_installer(self):
        self.assertRegex(WEB_VERSION,r'^\d+\.\d+\.\d+$')
        self.assertEqual(json.loads((ROOT/'apps'/'dcc-web'/'package.json').read_text(encoding='utf-8'))['version'], WEB_VERSION)
        with tempfile.TemporaryDirectory() as directory:
            archive_path=build_archive(Path(directory)/f'DCC-Web-{WEB_VERSION}-source.zip')
            with ZipFile(archive_path) as archive:
                names=set(archive.namelist())
                self.assertIn(f'DCC-Web-{WEB_VERSION}/apps/dcc-web/install.py',names)
                self.assertIn(f'DCC-Web-{WEB_VERSION}/apps/dcc-web/docs/installation.md',names)
                self.assertIn(f'DCC-Web-{WEB_VERSION}/dcc-catalog.json',names)
                self.assertNotIn(f'DCC-Web-{WEB_VERSION}/apps/dcc-web/tests/test_install.py',names)

    def test_linux_deb_declares_audio_runtime_and_desktop_launch_is_smoke_tested(self):
        builder=(ROOT/'packaging/linux/build_deb.sh').read_text(encoding='utf-8')
        smoke=(ROOT/'tests/linux_deb_upgrade_smoke.sh').read_text(encoding='utf-8')
        self.assertRegex(builder,r'(?m)^Depends:.*\blibpulse0\b')
        self.assertRegex(builder,r'(?m)^Depends:.*\bpkexec\b')
        self.assertNotRegex(builder,r'(?m)^Depends:.*\bpolicykit-1\b')
        self.assertIn('desktop-file-validate "$desktop_file"',smoke)
        self.assertIn('xvfb-run -a env',smoke)
        self.assertIn('"$desktop_exec"',smoke)

    def test_debian_build_and_stable_compatibility_jobs_cover_ubuntu_and_debian(self):
        workflow=(ROOT/'.github/workflows/release-candidate-checks.yml').read_text(encoding='utf-8')
        release_workflow=(ROOT/'.github/workflows/release.yml').read_text(encoding='utf-8')
        self.assertIn('runs-on: ubuntu-22.04',workflow)
        self.assertIn('container: debian:trixie-slim',workflow)
        self.assertIn('tests/linux_deb_compat_smoke.sh',workflow)
        self.assertIn('debian-bookworm-upgrade-compatibility:',workflow)
        self.assertIn('container: debian:bookworm-slim',workflow)
        self.assertIn('Upgrade smoke test must start without docker-control-center already installed.',(ROOT/'tests/linux_deb_upgrade_smoke.sh').read_text(encoding='utf-8'))
        self.assertIn('Verify App Store first-start credentials and restart behavior',workflow)
        self.assertIn('runs-on: ubuntu-22.04',release_workflow)
        self.assertIn('libpulse0 pkexec openssh-client',release_workflow)
        self.assertNotIn('policykit-1',release_workflow)


if __name__=='__main__':unittest.main()
