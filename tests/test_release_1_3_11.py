import json
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import DockerControlCenter as dcc
from dcc_catalog import category_group,localized_categories

ROOT=Path(__file__).resolve().parents[1]


class Release1311Tests(unittest.TestCase):
    def test_version_and_bom_installer_sources_match(self):
        self.assertEqual(dcc.APP_VERSION,'1.3.11')
        for language in ('PL','EN'):
            self.assertIn(dcc.APP_VERSION,dcc.TEXTS[language]['info_app_changelog_title'])
        first=(ROOT/'DockerControlCenter.nsi').read_bytes()
        self.assertTrue(first.startswith(b'\xef\xbb\xbf'))
        self.assertEqual(first,(ROOT/'upstream_assets/DockerControlCenter.nsi').read_bytes())

    def test_upgrade_1310_to_1311_is_detected(self):
        harness=SimpleNamespace(_parse_version_value=dcc.MainWindow._parse_version_value)
        # The parser is an instance method; bind it exactly as the running application does.
        harness._parse_version_value=lambda value:dcc.MainWindow._parse_version_value(harness,value)
        with patch.object(dcc,'APP_VERSION','1.3.10'):
            self.assertTrue(dcc.MainWindow._is_newer_version(harness,'v1.3.11'))
            self.assertFalse(dcc.MainWindow._is_newer_version(harness,'v1.3.10'))

    def test_release_assets_are_selected_for_the_correct_platform(self):
        assets={'tag_name':'v1.3.11','assets':[
            {'name':'DockerControlCenter-Setup-1.3.11.exe'},
            {'name':'DockerControlCenter_1.3.11_amd64.deb'},
        ]}
        with patch.object(dcc.sys,'platform','win32'):
            self.assertEqual(dcc.MainWindow.select_update_installer_asset(None,assets)['name'],'DockerControlCenter-Setup-1.3.11.exe')
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
        notes=(ROOT/'release/RELEASE_NOTES_1.3.11.md').read_text(encoding='utf-8')
        for name in ('DockerControlCenter-Setup-1.3.11.exe','DockerControlCenter_1.3.11_amd64.deb','SHA256SUMS-1.3.11.txt'):
            self.assertIn(name,notes)
        self.assertIn('/v1.3.11/',(ROOT/'README.md').read_text(encoding='utf-8'))

    def test_linux_deb_declares_audio_runtime_and_desktop_launch_is_smoke_tested(self):
        builder=(ROOT/'packaging/linux/build_deb.sh').read_text(encoding='utf-8')
        smoke=(ROOT/'tests/linux_deb_upgrade_smoke.sh').read_text(encoding='utf-8')
        self.assertRegex(builder,r'(?m)^Depends:.*\blibpulse0\b')
        self.assertIn('desktop-file-validate "$desktop_file"',smoke)
        self.assertIn('xvfb-run -a env',smoke)
        self.assertIn('"$desktop_exec"',smoke)


if __name__=='__main__':unittest.main()
