import json
from pathlib import Path
import unittest

from dcc_catalog import catalog_application_key, catalog_image_is_older, validate_catalog_uniqueness


class CatalogIdentityTests(unittest.TestCase):
    def test_published_catalog_defines_each_application_once(self):
        apps = json.loads((Path(__file__).resolve().parents[1] / 'dcc-catalog.json').read_text(encoding='utf-8'))['apps']
        validate_catalog_uniqueness(apps)
        for name in ('DCC Web', 'DCC Container Updater'):
            self.assertEqual(sum(app['name'] == name for app in apps), 1)

    def test_new_version_is_not_a_new_application_or_category_entry(self):
        one = dict(name='DCC Web', image='ghcr.io/hattimon/dcc-web:0.1.1', category='WWW')
        two = dict(one, image='ghcr.io/hattimon/dcc-web:0.1.3', category='DCC')
        with self.assertRaisesRegex(ValueError, 'Duplicate catalog application'):
            validate_catalog_uniqueness([one, two])
        self.assertEqual(catalog_application_key(one['name'], one['image']),
                         catalog_application_key(two['name'], two['image'], 'dcc-web'))

    def test_version_order_is_numeric_and_ignores_registry_port(self):
        repo = 'registry.example:5000/team/app:'
        self.assertTrue(catalog_image_is_older(repo + '1.9', repo + 'v1.10.0'))
        self.assertFalse(catalog_image_is_older(repo + '1.10.0', repo + '1.9'))
        self.assertFalse(catalog_image_is_older(repo + '1.10', repo + '1.10.0'))
        for tag in ('latest', 'stable', '1.11-rc.1', '1.10@sha256:abc'):
            self.assertFalse(catalog_image_is_older(repo + tag, repo + '1.10.0'))
        self.assertFalse(catalog_image_is_older('other/app:1', repo + '2'))

    def test_explicit_variants_and_unrelated_repositories_are_preserved(self):
        apps = [dict(name='App', image='example/app:1', default_name='app-v1'),
                dict(name='App', image='example/app:2', default_name='app'),
                dict(name='App', image='other/app:1', default_name='app')]
        validate_catalog_uniqueness(apps)


if __name__ == '__main__':
    unittest.main()
