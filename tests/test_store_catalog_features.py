import math
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFontMetrics
from PyQt6.QtWidgets import QApplication, QListView

import DockerControlCenter as dcc


class _FakeImage:
    def __init__(self, tags=None):
        self.tags = tags or []


class _FakeContainer:
    def __init__(self, name, image):
        self.name = name
        self.attrs = {"Config": {"Image": image}}
        self.image = _FakeImage([image])


class _FakeContainers:
    def __init__(self, containers=None):
        self._containers = list(containers or [])

    def list(self, all=True):
        return list(self._containers)


class _FakeClient:
    def __init__(self, containers=None):
        self.containers = _FakeContainers(containers)


class StoreCatalogFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_extended_store_metadata_is_parsed(self):
        template = dcc.image_template_from_dict(
            {
                "name": "Demo",
                "image": "example/demo:latest",
                "store_description": "Długi opis",
                "store_description_en": "Long description",
                "features": ["A", "B"],
                "features_en": ["One", "Two"],
                "icon_url": "catalog-assets/demo/icon.png",
                "hero_image_url": "catalog-assets/demo/hero.png",
                "gallery": [{"url": "catalog-assets/demo/01.png", "caption": "Widok"}],
                "credential_patterns": [
                    {"label": "Hasło", "label_en": "Password", "regex": "Password: (?P<value>\\S+)"}
                ],
                "post_install_hints": ["Otwórz panel"],
                "post_install_hints_en": ["Open dashboard"],
            },
            dcc.DEFAULT_DEPLOYMENT_REPOSITORY,
        )
        self.assertIsNotNone(template)
        self.assertEqual(template.store_description_for("PL"), "Długi opis")
        self.assertEqual(template.store_description_for("EN"), "Long description")
        self.assertEqual(template.features_for("EN"), ["One", "Two"])
        self.assertEqual(template.gallery[0]["caption"], "Widok")
        self.assertEqual(template.credential_patterns[0]["label_en"], "Password")

    def test_relative_store_media_resolves_to_primary_github_raw(self):
        template = dcc.ImageTemplate("Demo", "example/demo:latest", "Tools", "Demo", "demo")
        resolved = dcc.resolve_catalog_media_source(template, "catalog-assets/demo/hero.png")
        self.assertEqual(
            resolved,
            "https://raw.githubusercontent.com/hattimon/DCC/main/catalog-assets/demo/hero.png",
        )

    def test_pihole_style_password_is_extracted_without_persisting(self):
        template = dcc.ImageTemplate(
            "Pi-hole",
            "pihole/pihole:latest",
            "Network",
            "DNS",
            "pihole",
            credential_patterns=[
                {
                    "label": "Hasło panelu WWW",
                    "label_en": "Web dashboard password",
                    "regex": r"assigning random password:\s*(?P<value>\S+)",
                }
            ],
        )
        found = dcc.parse_credentials_from_logs(
            "startup complete\nAssigning random password: N7x-Example-42\nready",
            template,
            "PL",
        )
        self.assertIn(("Hasło panelu WWW", "N7x-Example-42"), found)

    def test_installed_state_matches_exact_image_or_same_named_repo(self):
        template = dcc.ImageTemplate("Demo", "ghcr.io/acme/demo:2", "Tools", "Demo", "demo")
        self.assertTrue(dcc.template_matches_container(template, _FakeContainer("other", "ghcr.io/acme/demo:2")))
        self.assertTrue(dcc.template_matches_container(template, _FakeContainer("demo", "ghcr.io/acme/demo:1")))
        self.assertFalse(dcc.template_matches_container(template, _FakeContainer("something", "ghcr.io/acme/other:2")))

    def test_balena_virtual_category_and_description_tab_are_available(self):
        with patch.object(dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]), patch.object(
            dcc, "load_cached_deployment_catalog", return_value=[]
        ):
            dialog = dcc.NewContainerDialog(_FakeClient(), dcc.TEXTS["EN"], lang="EN")
            self.assertIs(dialog.editor_tabs.widget(0), dialog.store_tab)
            self.assertFalse(dialog.manual_configuration_mode)
            self.assertGreater(dialog.category_nav.count(), 1)
            self.assertEqual(
                dialog.category_nav.item(0).data(Qt.ItemDataRole.UserRole),
                dcc.TEXTS["EN"]["wizard_all_categories"],
            )
            self.assertEqual(
                dialog.category_nav.item(1).data(Qt.ItemDataRole.UserRole),
                dcc.TEXTS["EN"]["wizard_installed_category"],
            )
            self.assertTrue(dialog.category_combo.isHidden())
            self.assertEqual(dialog.catalog_list.currentRow(), 0)
            self.assertLess(dialog.category_nav.count(), 25)
            self.assertEqual(dialog._catalog_category_group("AI 💬 › UI"), "AI")
            self.assertTrue(all("›" not in dialog.category_nav.item(i).text() for i in range(dialog.category_nav.count())))
            balena_label = dcc.TEXTS["EN"]["wizard_balena_category"]
            self.assertGreaterEqual(dialog.category_combo.findText(balena_label), 0)
            dialog.category_combo.setCurrentText(balena_label)
            dialog.filter_catalog()
            self.assertEqual(
                dialog.category_nav.currentItem().data(Qt.ItemDataRole.UserRole),
                balena_label,
            )
            self.assertGreater(dialog.catalog_list.count(), 0)
            self.assertTrue(all(item.supports_engine("balena") for item in dialog.filtered_catalog))
            dialog.close()

    def test_store_palette_follows_theme_with_neutral_surfaces(self):
        with patch.object(dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]), patch.object(
            dcc, "load_cached_deployment_catalog", return_value=[]
        ):
            dialog = dcc.NewContainerDialog(_FakeClient(), dcc.TEXTS["EN"], lang="EN")
            dialog.catalog_theme = "black"
            dialog.catalog_accent = "#ff4bd8"
            colors = dialog._catalog_visual_colors()
            self.assertEqual(colors["accent"], "#ff4bd8")
            self.assertIn("rgba(14, 15, 17", colors["surface"])
            self.assertIn("rgba(24, 25, 28", colors["card_bg"])
            dialog.close()

    def test_light_store_uses_readable_text_and_accent(self):
        with patch.object(dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]), patch.object(
            dcc, "load_cached_deployment_catalog", return_value=[]
        ):
            dialog = dcc.NewContainerDialog(_FakeClient(), dcc.TEXTS["PL"], lang="PL")
            dialog.catalog_theme = "light"
            dialog.catalog_accent = "#33f0ff"
            colors = dialog._catalog_visual_colors()
            self.assertEqual(colors["accent"], "#33f0ff")
            self.assertNotEqual(colors["accent_text"], colors["accent"])
            self.assertEqual(colors["title"], dcc.palette_for_theme("light")["fg"])
            self.assertEqual(colors["description"], dcc.palette_for_theme("light")["muted"])
            self.assertIn("rgba(248, 248, 249", colors["card_bg"])
            dialog.close()

        qss = dcc.gaming_stylesheet("light", 0.0, False, 100, False, "#33f0ff")
        self.assertIn("rgba(250,252,255,0.88)", qss)
        self.assertIn("rgba(218,231,250,0.92)", qss)

    def test_store_categories_stay_compact_at_desktop_width(self):
        with patch.object(dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]), patch.object(
            dcc, "load_cached_deployment_catalog", return_value=[]
        ):
            dialog = dcc.NewContainerDialog(_FakeClient(), dcc.TEXTS["PL"], lang="PL")
            dialog.show()
            self.assertEqual(dialog.category_nav.viewMode(), QListView.ViewMode.ListMode)
            self.assertEqual(dialog.category_nav.textElideMode(), Qt.TextElideMode.ElideNone)
            previous_frame_height = None
            for width, height in ((820, 700), (1360, 820), (1920, 1080)):
                dialog.resize(width, height)
                self.app.processEvents()
                dialog._update_category_nav_height()
                self.app.processEvents()
                dialog._update_category_nav_height()
                self.app.processEvents()

                viewport = dialog.category_nav.viewport().rect()
                rects = [
                    dialog.category_nav.visualItemRect(dialog.category_nav.item(i))
                    for i in range(dialog.category_nav.count())
                ]
                self.assertTrue(all(rect.isValid() for rect in rects))
                self.assertTrue(all(rect.right() <= viewport.right() + 1 for rect in rects))
                self.assertTrue(all(rect.bottom() <= viewport.bottom() + 1 for rect in rects))
                self.assertTrue(all(not dialog.category_nav.item(i).icon().isNull() for i in range(dialog.category_nav.count())))

                dialog.category_nav.setCurrentRow(dialog.category_nav.count() - 1)
                dialog.category_nav.scrollToItem(dialog.category_nav.item(dialog.category_nav.count() - 1))
                self.app.processEvents()
                first_rect = dialog.category_nav.visualItemRect(dialog.category_nav.item(0))
                self.assertTrue(viewport.contains(first_rect))
                self.assertEqual(dialog.category_nav.verticalScrollBar().value(), 0)
                self.assertEqual(dialog.category_nav.horizontalScrollBar().value(), 0)
                self.assertEqual(dialog.category_nav.verticalScrollBar().maximum(), 0)
                self.assertEqual(dialog.category_nav.horizontalScrollBar().maximum(), 0)

                for i in range(dialog.category_nav.count()):
                    item = dialog.category_nav.item(i)
                    full_text_width = QFontMetrics(item.font()).horizontalAdvance(item.text())
                    self.assertGreaterEqual(item.sizeHint().width(), full_text_width + dialog.category_nav.iconSize().width() + 20)

                actual_bottom = max(rect.bottom() + 1 for rect in rects)
                bottom_gap = dialog.category_nav.height() - actual_bottom
                self.assertGreaterEqual(bottom_gap, 10)
                self.assertLessEqual(bottom_gap, 16)
                if previous_frame_height is not None:
                    self.assertLessEqual(dialog.store_categories_frame.height(), previous_frame_height)
                previous_frame_height = dialog.store_categories_frame.height()

            self.assertTrue(dialog.category_nav.item(0).font().bold())
            self.assertTrue(dialog.category_nav.item(1).font().bold())
            dialog.close()

    def test_installed_category_lists_only_apps_present_on_current_host(self):
        template = dcc.default_image_catalog()[0]
        container = _FakeContainer(template.default_name or template.name, template.image)
        with patch.object(dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]), patch.object(
            dcc, "load_cached_deployment_catalog", return_value=[]
        ):
            dialog = dcc.NewContainerDialog(_FakeClient([container]), dcc.TEXTS["PL"], lang="PL")
            installed_label = dcc.TEXTS["PL"]["wizard_installed_category"]
            self.assertGreaterEqual(dialog.category_combo.findText(installed_label), 0)
            dialog.category_combo.setCurrentText(installed_label)
            self.app.processEvents()
            self.assertGreater(dialog.catalog_list.count(), 0)
            installed_containers = dialog.client.containers.list(all=True)
            self.assertTrue(
                all(
                    any(dcc.template_matches_container(item, current) for current in installed_containers)
                    for item in dialog.filtered_catalog
                )
            )
            dialog.catalog_list.setCurrentRow(0)
            self.app.processEvents()
            self.assertEqual(dialog.btn_store_primary.text(), dcc.TEXTS["PL"]["wizard_store_uninstall"])
            dialog.close()

    def test_store_layout_has_no_horizontal_scroll_at_normal_compact_width(self):
        with patch.object(dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]), patch.object(
            dcc, "load_cached_deployment_catalog", return_value=[]
        ):
            dialog = dcc.NewContainerDialog(_FakeClient(), dcc.TEXTS["PL"], lang="PL")
            dialog.resize(820, 760)
            dialog.show()
            self.app.processEvents()
            dialog._update_store_responsive_layout()
            self.app.processEvents()
            self.assertEqual(dialog.dialog_scroll_area.horizontalScrollBar().maximum(), 0)
            self.assertEqual(dialog.catalog_row.direction(), dcc.QBoxLayout.Direction.TopToBottom)
            dialog.close()

    def test_bundled_icons_are_used_and_missing_media_reserves_no_space(self):
        with patch.object(dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]), patch.object(
            dcc, "load_cached_deployment_catalog", return_value=[]
        ):
            dialog = dcc.NewContainerDialog(_FakeClient(), dcc.TEXTS["EN"], lang="EN")
            dialog.show()
            self.app.processEvents()
            first = dialog.selected_catalog_template()
            self.assertIsNotNone(first)
            self.assertTrue(first.icon_url)
            self.assertTrue(dcc.resolve_catalog_media_source(first, first.icon_url).startswith("file:"))
            self.assertTrue(any(size.width() > 44 for size in dcc.deployment_catalog_icon(first).availableSizes()))
            self.assertFalse(dialog.store_hero_image.isVisible())
            self.assertFalse(dialog.store_gallery_title.isVisible())

            smartwan_row = next(i for i, item in enumerate(dialog.filtered_catalog) if item.name == "SmartWAN Manager")
            dialog.catalog_list.setCurrentRow(smartwan_row)
            self.app.processEvents()
            self.assertTrue(dialog.store_hero_image.isVisible())
            self.assertTrue(dialog.store_gallery_title.isVisible())
            dialog.close()

    def test_two_line_description_uses_three_dots_only_on_overflow(self):
        label = dcc.TwoLineElideLabel()
        label.resize(190, 48)
        label.setText(
            "This is a deliberately long application description that should use the available two rows before it is truncated."
        )
        self.app.processEvents()
        rendered = label.text()
        self.assertIn("\n", rendered)
        self.assertTrue(rendered.endswith("..."))
        self.assertLessEqual(len(rendered.splitlines()), 2)

    def test_animated_neon_preserves_selected_hue(self):
        phase = 0.0
        base = QColor("#ff5f5f")
        hue, saturation, value, _alpha = base.getHsvF()
        pulse = 0.78 + 0.22 * (0.5 + 0.5 * math.sin(phase * math.tau))
        expected = QColor.fromHsvF(hue, max(0.18, saturation), max(0.35, min(1.0, value * pulse))).name()
        qss = dcc.gaming_stylesheet("dark", phase, False, 100, True, "#ff5f5f")
        self.assertIn(expected, qss)
        self.assertNotIn("#33f0ff", qss.lower())

    def test_source_build_metadata_is_parsed(self):
        template = dcc.image_template_from_dict(
            {
                "name": "Demo source build",
                "image": "demo-source:latest",
                "build_context": "https://github.com/example/demo.git#main",
                "build_dockerfile": "Dockerfile.custom",
            },
            dcc.DEFAULT_DEPLOYMENT_REPOSITORY,
        )
        self.assertIsNotNone(template)
        self.assertEqual(template.build_context, "https://github.com/example/demo.git#main")
        self.assertEqual(template.build_dockerfile, "Dockerfile.custom")

    def test_bundled_catalog_contains_smartwan_manager_source_build(self):
        catalog = dcc.load_bundled_deployment_catalog()
        smartwan = next((item for item in catalog if item.name == "SmartWAN Manager"), None)
        self.assertIsNotNone(smartwan)
        self.assertEqual(smartwan.image, "smartwan-manager:latest")
        self.assertEqual(smartwan.container_port, "8080")
        self.assertEqual(smartwan.host_port, "8888")
        self.assertEqual(smartwan.build_context, "https://github.com/hattimon/SmartWAN-Manager.git#main")
        self.assertEqual(smartwan.build_dockerfile, "Dockerfile")
        self.assertEqual(smartwan.icon_url, "catalog/media/icons/smartwan-manager.png")
        self.assertEqual(smartwan.hero_image_url, "catalog/media/heroes/smartwan-manager.png")
        self.assertTrue(smartwan.supports_engine("docker"))
        self.assertTrue(smartwan.supports_arch("aarch64"))
        self.assertTrue(smartwan.supports_arch("armv7l"))
        self.assertTrue(smartwan.supports_arch("armhf"))

        media_values = [smartwan.icon_url, smartwan.hero_image_url]
        media_values.extend(entry.get("url", "") for entry in smartwan.gallery or [])
        self.assertTrue(all(dcc.resolve_catalog_media_source(smartwan, value).startswith("file:///") for value in media_values))

    def test_refresh_merge_keeps_smartwan_on_raspberry_pi_ubuntu(self):
        bundled = dcc.load_bundled_deployment_catalog()
        refreshed_without_smartwan = [item for item in bundled[:8] if item.name != "SmartWAN Manager"]
        merged = dcc.merge_catalog_lists(bundled, refreshed_without_smartwan)
        smartwan = next((item for item in merged if item.name == "SmartWAN Manager"), None)
        self.assertIsNotNone(smartwan)
        self.assertTrue(smartwan.supports_engine("docker"))
        self.assertTrue(smartwan.supports_arch("aarch64"))
        self.assertTrue(smartwan.supports_arch("armv7l"))
        self.assertTrue(smartwan.hero_image_url)
        self.assertEqual(len(smartwan.gallery or []), 2)

        with patch.object(dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]), patch.object(
            dcc, "load_cached_deployment_catalog", return_value=[]
        ):
            dialog = dcc.NewContainerDialog(
                _FakeClient(),
                dcc.TEXTS["PL"],
                lang="PL",
                cli_command="docker",
                cli_choices=["docker"],
                remote_arch="armv7l",
                target_host_label="Raspberry Pi · Ubuntu · armv7l",
            )
            self.assertIn("SmartWAN Manager", [item.name for item in dialog.filtered_catalog])
            dialog.close()

    def test_source_built_catalog_app_never_pulls_registry_image_on_run(self):
        with patch.object(dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]), patch.object(
            dcc, "load_cached_deployment_catalog", return_value=[]
        ):
            dialog = dcc.NewContainerDialog(_FakeClient(), dcc.TEXTS["EN"], lang="EN")
            smartwan_row = next(i for i, item in enumerate(dialog.filtered_catalog) if item.name == "SmartWAN Manager")
            dialog.catalog_list.setCurrentRow(smartwan_row)
            self.app.processEvents()
            args = dialog.build_run_args()
            pull_index = args.index("--pull")
            self.assertEqual(args[pull_index + 1], "never")
            self.assertIn("smartwan-manager:latest", args)

            regular_row = next(i for i, item in enumerate(dialog.filtered_catalog) if not item.build_context)
            dialog.catalog_list.setCurrentRow(regular_row)
            self.app.processEvents()
            regular_args = dialog.build_run_args()
            regular_pull_index = regular_args.index("--pull")
            self.assertEqual(regular_args[regular_pull_index + 1], "always")
            dialog.close()

    def test_store_target_host_is_visually_emphasized(self):
        with patch.object(dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]), patch.object(
            dcc, "load_cached_deployment_catalog", return_value=[]
        ):
            dialog = dcc.NewContainerDialog(
                _FakeClient(),
                dcc.TEXTS["PL"],
                lang="PL",
                target_host_label="LOCAL / Docker Desktop",
            )
            self.assertEqual(dialog.target_host_frame.objectName(), "storeTargetHostFrame")
            self.assertTrue(dialog.target_label.font().bold())
            self.assertIn("LOCAL / Docker Desktop", dialog.target_label.text())
            self.assertFalse(dialog.target_host_icon.pixmap().isNull())
            self.assertIn("border", dialog.target_host_frame.styleSheet())
            dialog.close()


if __name__ == "__main__":
    unittest.main()
