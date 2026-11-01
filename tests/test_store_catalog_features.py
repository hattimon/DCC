import json
import math
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, QEvent, Qt
from PyQt6.QtGui import QColor, QFontMetrics
from PyQt6.QtWidgets import QApplication, QListView

import DockerControlCenter as dcc


def _dispose_widget(widget):
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()


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
        # UI tests must not start the delayed network refresh thread.
        # It can still run when the test QApplication is destroyed.
        refresh_patch = patch.object(dcc.NewContainerDialog, "refresh_external_catalogs")
        refresh_patch.start()
        cls.addClassCleanup(refresh_patch.stop)

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
            labels = [dialog.category_nav.item(i).text() for i in range(dialog.category_nav.count())]
            self.assertEqual(len(labels), len(set(labels)))
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
            _dispose_widget(dialog)

    def test_dcc_category_is_between_installed_and_ai_in_both_languages(self):
        for lang in ("PL", "EN"):
            with self.subTest(lang=lang), patch.object(
                dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]
            ), patch.object(dcc, "load_cached_deployment_catalog", return_value=[]):
                dialog = dcc.NewContainerDialog(_FakeClient(), dcc.TEXTS[lang], lang=lang)
                expected = [
                    dcc.TEXTS[lang]["wizard_all_categories"],
                    dcc.TEXTS[lang]["wizard_installed_category"],
                    "DCC",
                    "AI",
                ]
                actual = [dialog.category_combo.itemText(i) for i in range(4)]
                self.assertEqual(actual, expected)
                self.assertEqual(
                    [dialog.category_nav.item(i).text() for i in range(4)], expected
                )
                self.assertEqual(dialog.category_combo.findText("DCC"), 2)
                self.assertTrue(dialog.category_nav.item(2).font().bold())
                self.assertFalse(dialog.category_nav.item(2).icon().isNull())
                dialog.rebuild_catalog_categories()
                self.assertEqual(
                    sum(dialog.category_combo.itemText(i) == "DCC" for i in range(dialog.category_combo.count())),
                    1,
                )
                _dispose_widget(dialog)

    def test_bundled_dcc_updater_keeps_updates_and_adds_dcc(self):
        payload = json.loads(dcc.BUNDLED_DEPLOYMENT_CATALOG_FILE.read_text(encoding="utf-8"))
        entries = [item for item in payload["apps"] if item["name"] == "DCC Container Updater"]
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry["category"], "Aktualizacje 🔄")
        self.assertEqual(entry["category_en"], "Updates 🔄")
        self.assertEqual(entry["image"], "ghcr.io/hattimon/dcc-container-updater:latest")
        self.assertEqual(entry["categories"], ["DCC"])
        self.assertEqual(entry["categories_en"], ["DCC"])
        updater = next(item for item in dcc.load_bundled_deployment_catalog() if item.name == entry["name"])
        self.assertEqual(updater.categories_for("PL"), ["Aktualizacje 🔄", "DCC"])
        self.assertEqual(updater.categories_for("EN"), ["Updates 🔄", "DCC"])

    def test_bundled_dcc_web_has_store_page_and_functional_categories(self):
        payload = json.loads(dcc.BUNDLED_DEPLOYMENT_CATALOG_FILE.read_text(encoding="utf-8"))
        entries = [item for item in payload["apps"] if item["name"] == "DCC Web"]
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry["image"], "ghcr.io/hattimon/dcc-web:0.1.1")
        self.assertEqual(entry["category"], "DCC")
        self.assertEqual(entry["categories"], ["DCC", "Administracja 🛠", "WWW 🌐"])
        self.assertEqual(entry["categories_en"], ["DCC", "Administration 🛠", "WWW 🌐"])
        self.assertIn("/apps/dcc-web", entry["homepage_url"])
        self.assertIn("/apps/dcc-web/docs", entry["docs_url"])
        self.assertEqual(entry["container_port"], "8789")
        self.assertIn("dcc_web_data:/data", entry["extra"])
        self.assertIn("/var/run/docker.sock:/var/run/docker.sock", entry["extra"])
        self.assertIn("--cap-drop=ALL", entry["extra"])
        self.assertIn("--cap-add=SETUID", entry["extra"])
        self.assertIn("losowe hasło administratora", entry["notes"])
        self.assertIn("random administrator password", entry["notes_en"])
        app = dcc.image_template_from_dict(entry, dcc.DEFAULT_DEPLOYMENT_REPOSITORY)
        self.assertEqual(app.categories_for("PL"), ["DCC", "Administracja 🛠", "WWW 🌐"])
        self.assertEqual(app.categories_for("EN"), ["DCC", "Administration 🛠", "WWW 🌐"])

    def test_dcc_updater_is_filterable_in_both_categories_without_duplicates(self):
        for lang, updates in (("PL", "Aktualizacje"), ("EN", "Updates")):
            with self.subTest(lang=lang), patch.object(
                dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]
            ), patch.object(dcc, "load_cached_deployment_catalog", return_value=[]):
                dialog = dcc.NewContainerDialog(_FakeClient(), dcc.TEXTS[lang], lang=lang)
                updater_name = "DCC Container Updater"
                for category in ("DCC", updates, dcc.TEXTS[lang]["wizard_all_categories"]):
                    dialog.category_combo.setCurrentText(category)
                    dialog.filter_catalog()
                    matches = [item for item in dialog.filtered_catalog if item.name == updater_name]
                    self.assertEqual(len(matches), 1, category)
                    keys = [(item.name.lower(), item.image.lower()) for item in dialog.filtered_catalog]
                    self.assertEqual(len(keys), len(set(keys)))

                dialog.category_combo.setCurrentText("DCC")
                description_query = "optional Safe Compose Manager" if lang == "EN" else "opcjonalnym Safe Compose Manager"
                for query in ("cOnTaInEr UpDaTeR", "dcc-container-updater:latest", description_query, "Swarm"):
                    dialog.search_edit.setText(query)
                    dialog.filter_catalog()
                    self.assertEqual([item.name for item in dialog.filtered_catalog], [updater_name], query)
                dialog.search_edit.setText("something-that-cannot-match")
                dialog.filter_catalog()
                self.assertEqual(dialog.catalog_list.count(), 0)
                _dispose_widget(dialog)

    def test_multiple_categories_legacy_catalogs_and_repository_merge(self):
        legacy = dcc.image_template_from_dict(
            {"name": "Legacy", "image": "example/legacy:latest", "category": "AI / UI", "category_en": "AI / UI"}
        )
        self.assertEqual(legacy.categories_for("PL"), ["AI / UI"])
        self.assertEqual(legacy.categories_for("EN"), ["AI / UI"])

        multi = dcc.image_template_from_dict(
            {
                "name": "Demo extension",
                "image": "example/dcc-demo:latest",
                "category": "Aktualizacje 🔄",
                "category_en": "Updates 🔄",
                "categories": ["DCC", "AI / UI", "DCC"],
                "categories_en": ["DCC", "AI / UI", "DCC"],
            },
            "https://example.org/one.json",
        )
        self.assertEqual(multi.categories_for("PL"), ["Aktualizacje 🔄", "DCC", "AI / UI"])
        self.assertEqual(multi.categories_for("EN"), ["Updates 🔄", "DCC", "AI / UI"])
        override = dcc.image_template_from_dict(
            {
                "name": multi.name,
                "image": multi.image,
                "category": "Aktualizacje 🔄",
                "category_en": "Updates 🔄",
            },
            "https://example.org/two.json",
        )
        merged = dcc.merge_catalog_lists([legacy, multi], [override])
        self.assertEqual(len(merged), 2)
        demo = next(item for item in merged if item.name == "Demo extension")
        self.assertIn("DCC", demo.categories_for("PL"))
        self.assertIn("AI / UI", demo.categories_for("PL"))

        for lang in ("PL", "EN"):
            with self.subTest(lang=lang), patch.object(
                dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]
            ), patch.object(dcc, "load_cached_deployment_catalog", return_value=[]):
                dialog = dcc.NewContainerDialog(_FakeClient(), dcc.TEXTS[lang], lang=lang)
                original_groups = {
                    dialog._catalog_category_group(item.category_for(lang))
                    for item in dialog.catalog
                }
                dialog.catalog = dcc.merge_catalog_lists(dialog.catalog, merged)
                dialog.rebuild_catalog_categories()
                current_groups = set(dialog.catalog_category_names()) | {"DCC"}
                self.assertTrue(original_groups <= current_groups)
                for category in ("DCC", "AI", "Updates" if lang == "EN" else "Aktualizacje"):
                    dialog.category_combo.setCurrentText(category)
                    dialog.filter_catalog()
                    demo_rows = [item for item in dialog.filtered_catalog if item.name == "Demo extension"]
                    self.assertEqual(len(demo_rows), 1, category)
                _dispose_widget(dialog)

    def test_updates_category_keeps_existing_bold_style(self):
        updater = next(item for item in dcc.load_bundled_deployment_catalog() if item.name == "DCC Container Updater")
        for lang in ("PL", "EN"):
            with self.subTest(lang=lang), patch.object(
                dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]
            ), patch.object(dcc, "load_cached_deployment_catalog", return_value=[]):
                dialog = dcc.NewContainerDialog(_FakeClient(), dcc.TEXTS[lang], lang=lang)
                dialog.catalog = [updater]
                dialog.rebuild_catalog_categories()
                updates = dcc.TEXTS[lang]["wizard_updates_category"]
                index = dialog.category_combo.findText(updates)
                self.assertGreater(index, dialog.category_combo.findText("DCC"))
                self.assertEqual(
                    sum(dialog.category_combo.itemText(i) == updates for i in range(dialog.category_combo.count())),
                    1,
                )
                all_item = dialog.category_nav.item(0)
                updates_item = dialog.category_nav.item(index)
                self.assertTrue(updates_item.font().bold())
                self.assertEqual(updates_item.foreground().color(), all_item.foreground().color())
                self.assertEqual(updates_item.background().color(), all_item.background().color())
                _dispose_widget(dialog)

    def test_legacy_catalog_cache_and_refresh_keep_dcc_updater_membership(self):
        updater = next(item for item in dcc.load_bundled_deployment_catalog() if item.name == "DCC Container Updater")
        legacy_data = dcc.asdict(updater)
        legacy_data.pop("categories")
        legacy_data.pop("categories_en")
        legacy_updater = dcc.image_template_from_dict(legacy_data, dcc.DEFAULT_DEPLOYMENT_REPOSITORY)
        for lang in ("PL", "EN"):
            with self.subTest(lang=lang), patch.object(
                dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]
            ), patch.object(dcc, "load_cached_deployment_catalog", return_value=[legacy_updater]), patch.object(
                dcc, "save_cached_deployment_catalog"
            ) as save_cache:
                container = _FakeContainer(updater.default_name, updater.image)
                dialog = dcc.NewContainerDialog(_FakeClient([container]), dcc.TEXTS[lang], lang=lang)
                dialog.category_combo.setCurrentText("DCC")
                filtered_names = [item.name for item in dialog.filtered_catalog]
                self.assertEqual(filtered_names.count(updater.name), 1)
                self.assertEqual(filtered_names.count("DCC Web"), 1)
                dialog.catalog_list.setCurrentRow(0)
                dialog.on_external_catalog_refresh_finished([legacy_updater], [])
                save_cache.assert_called_once_with([legacy_updater])
                self.assertEqual(dialog.category_combo.currentText(), "DCC")
                filtered_names = [item.name for item in dialog.filtered_catalog]
                self.assertEqual(filtered_names.count(updater.name), 1)
                self.assertEqual(filtered_names.count("DCC Web"), 1)
                for label in (dialog.app_category_label, dialog.store_category_label):
                    self.assertIn("DCC", label.text())
                    self.assertIn(dcc.TEXTS[lang]["wizard_updates_category"], label.text())
                for category in (
                    dcc.TEXTS[lang]["wizard_updates_category"],
                    dcc.TEXTS[lang]["wizard_installed_category"],
                ):
                    dialog.category_combo.setCurrentText(category)
                    self.assertEqual([item.name for item in dialog.filtered_catalog], [updater.name])
                _dispose_widget(dialog)

    def test_existing_category_memberships_are_preserved(self):
        for lang in ("PL", "EN"):
            with self.subTest(lang=lang), patch.object(
                dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]
            ), patch.object(dcc, "load_cached_deployment_catalog", return_value=[]):
                dialog = dcc.NewContainerDialog(_FakeClient(), dcc.TEXTS[lang], lang=lang)
                legacy_memberships = {}
                all_keys = set()
                for item in dialog.catalog:
                    if not item.supports_engine("docker"):
                        continue
                    key = (item.name, item.image)
                    group = dialog._catalog_category_group(item.category_for(lang))
                    legacy_memberships.setdefault(group, set()).add(key)
                    all_keys.add(key)
                self.assertEqual({(item.name, item.image) for item in dialog.filtered_catalog}, all_keys)
                for category, expected in legacy_memberships.items():
                    self.assertGreaterEqual(dialog.category_combo.findText(category), 0, category)
                    dialog.category_combo.setCurrentText(category)
                    actual = {(item.name, item.image) for item in dialog.filtered_catalog}
                    self.assertTrue(expected <= actual, category)
                    self.assertEqual(len(actual), dialog.catalog_list.count(), category)
                _dispose_widget(dialog)

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
            _dispose_widget(dialog)

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
            _dispose_widget(dialog)

        qss = dcc.gaming_stylesheet("light", 0.0, False, 100, False, "#33f0ff")
        self.assertIn("rgba(250,252,255,0.88)", qss)
        self.assertIn("rgba(218,231,250,0.92)", qss)

    def test_store_light_and_day_categories_use_readable_theme_surfaces(self):
        class Harness:
            catalog_accent = "#33f0ff"

        for theme, lang in (("light", "PL"), ("day", "EN")):
            harness = Harness()
            harness.catalog_theme = theme
            palette = dcc.palette_for_theme(theme)
            colors = dcc.NewContainerDialog._catalog_visual_colors(harness)
            combined = "\n".join(dcc.NewContainerDialog._catalog_category_styles(colors)).lower()
            self.assertIn(palette["fg"].lower(), combined)
            self.assertIn(colors["surface"].lower(), combined)
            self.assertIn(colors["card_bg"].lower(), combined)
            self.assertIn(dcc.TEXTS[lang]["wizard_store_categories"], {"Kategorie", "Categories"})
            self.assertNotIn("background: #0e0f11", combined)
            self.assertNotIn("background: #18191c", combined)

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
            _dispose_widget(dialog)

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
            _dispose_widget(dialog)

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
            _dispose_widget(dialog)

    def test_updater_summary_stays_compact_with_long_details(self):
        for lang in ("PL", "EN"):
            for installed in (False, True):
                with self.subTest(lang=lang, installed=installed), patch.object(
                    dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]
                ), patch.object(dcc, "load_cached_deployment_catalog", return_value=[]):
                    containers = [_FakeContainer("dcc-container-updater", "ghcr.io/hattimon/dcc-container-updater:latest")] if installed else []
                    dialog = dcc.NewContainerDialog(_FakeClient(containers), dcc.TEXTS[lang], lang=lang)
                    dialog.resize(1145, 914)
                    dialog.show()
                    heights = {}
                    for name in ("Home Assistant", "DCC Container Updater"):
                        row = next(i for i, item in enumerate(dialog.filtered_catalog) if item.name == name)
                        dialog.catalog_list.setCurrentRow(row)
                        self.app.processEvents()
                        dialog._fit_editor_tabs_height()
                        self.app.processEvents()
                        header = dialog.store_hero_card
                        content_bottom = max(
                            widget.geometry().bottom()
                            for widget in (dialog.store_icon_label, dialog.store_install_state_label, dialog.btn_store_primary)
                        )
                        bottom_gap = header.height() - content_bottom - 1
                        self.assertLessEqual(bottom_gap, header.layout().contentsMargins().bottom() + 2)
                        self.assertTrue(header.rect().contains(dialog.btn_store_primary.geometry()))
                        self.assertGreater(dialog.store_description_label.y(), header.geometry().bottom())
                        heights[name] = header.height()
                    self.assertEqual(heights["DCC Container Updater"], heights["Home Assistant"])
                    _dispose_widget(dialog)

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
            _dispose_widget(dialog)

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
            _dispose_widget(dialog)

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
            _dispose_widget(dialog)

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
            _dispose_widget(dialog)


if __name__ == "__main__":
    unittest.main()
