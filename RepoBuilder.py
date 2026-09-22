#!/usr/bin/env python3
"""DCC Repo Builder - local editor for dcc-catalog.json.

The tool intentionally edits a local checkout first. GitHub authentication is
handled by the GitHub CLI in the user's browser/session and publishing remains
an explicit user action.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import DockerControlCenter as dcc


DEFAULT_REPO_URL = "https://github.com/hattimon/DCC"


REPO_BUILDER_UI = {
    "EN": {
        "App / Aplikacja": "Application",
        "Store / Sklep": "Store",
        "Advanced": "Advanced",
        "Local folder…": "Local folder…",
        "Open GitHub": "Open GitHub",
        "GitHub login": "GitHub login",
        "Load": "Load",
        "Validate": "Validate",
        "Save local JSON": "Save local JSON",
        "Git status": "Git status",
        "Commit catalog…": "Commit catalog…",
        "Push…": "Push…",
        "New": "New",
        "Duplicate": "Duplicate",
        "Remove": "Remove",
        "Name / Nazwa": "Name",
        "Image": "Image",
        "Container name": "Container name",
        "Category PL": "Category PL",
        "Category EN": "Category EN",
        "Short description PL": "Short description PL",
        "Short description EN": "Short description EN",
        "Container port": "Container port",
        "Host port": "Host port",
        "Extra docker args": "Extra Docker arguments",
        "Command": "Command",
        "Engines (comma)": "Engines (comma separated)",
        "Architectures (comma)": "Architectures (comma separated)",
        "Apply changes to entry": "Apply changes to entry",
        "Store description PL": "Store description PL",
        "Store description EN": "Store description EN",
        "Features PL (one/line)": "Features PL (one per line)",
        "Features EN (one/line)": "Features EN (one per line)",
        "Icon URL / relative path": "Icon URL / relative path",
        "Hero image URL / relative path": "Hero image URL / relative path",
        "Gallery JSON": "Gallery JSON",
        "Choose local hero…": "Choose local hero…",
        "Preview hero": "Preview hero",
        "Source": "Source",
        "Docs": "Documentation",
        "Homepage": "Homepage",
        "Requires (comma)": "Requirements (comma separated)",
        "RAM min MB": "Minimum RAM (MB)",
        "Storage type": "Storage type",
        "Security exposure": "Security exposure",
        "Build context / Git repo": "Build context / Git repository",
        "Build Dockerfile": "Build Dockerfile",
        "Credential patterns JSON": "Credential patterns JSON",
        "Post-install hints PL": "Post-install hints PL",
        "Post-install hints EN": "Post-install hints EN",
        "Provider": "Provider",
        "Model": "Model",
        "OpenAI API key": "OpenAI API key",
        "Ollama URL": "Ollama URL",
        "Guidance": "Guidance",
        "Detect models": "Detect models",
        "Test AI connection": "Test AI connection",
        "Generate PL + EN store content": "Generate PL + EN store content",
        "Generate hero image (OpenAI)": "Generate hero image (OpenAI)",
    },
    "PL": {
        "Repo:": "Repozytorium:",
        "Local:": "Lokalnie:",
        "Catalog:": "Katalog:",
        "App / Aplikacja": "Aplikacja",
        "Store / Sklep": "Sklep",
        "Advanced": "Zaawansowane",
        "Local folder…": "Folder lokalny…",
        "Open GitHub": "Otwórz GitHub",
        "GitHub login": "Logowanie GitHub",
        "Load": "Wczytaj",
        "Validate": "Sprawdź",
        "Save local JSON": "Zapisz lokalny JSON",
        "Git status": "Stan Git",
        "Commit catalog…": "Zapisz commit…",
        "Push…": "Wyślij…",
        "New": "Nowa",
        "Duplicate": "Duplikuj",
        "Remove": "Usuń",
        "Name / Nazwa": "Nazwa",
        "Image": "Obraz",
        "Container name": "Nazwa kontenera",
        "Category PL": "Kategoria PL",
        "Category EN": "Kategoria EN",
        "Short description PL": "Krótki opis PL",
        "Short description EN": "Krótki opis EN",
        "Container port": "Port kontenera",
        "Host port": "Port hosta",
        "Extra docker args": "Dodatkowe parametry Dockera",
        "Command": "Polecenie",
        "Engines (comma)": "Silniki (po przecinku)",
        "Architectures (comma)": "Architektury (po przecinku)",
        "Apply changes to entry": "Zastosuj zmiany we wpisie",
        "Store description PL": "Opis w sklepie PL",
        "Store description EN": "Opis w sklepie EN",
        "Features PL (one/line)": "Funkcje PL (jedna na wiersz)",
        "Features EN (one/line)": "Funkcje EN (jedna na wiersz)",
        "Icon URL / relative path": "URL ikony / ścieżka względna",
        "Hero image URL / relative path": "URL grafiki głównej / ścieżka względna",
        "Gallery JSON": "Galeria JSON",
        "Choose local hero…": "Wybierz grafikę lokalną…",
        "Preview hero": "Podgląd grafiki",
        "Source": "Źródło",
        "Docs": "Dokumentacja",
        "Homepage": "Strona domowa",
        "Requires (comma)": "Wymagania (po przecinku)",
        "RAM min MB": "Minimalna pamięć RAM (MB)",
        "Storage type": "Typ pamięci masowej",
        "Security exposure": "Ekspozycja sieciowa",
        "Build context / Git repo": "Kontekst budowania / repozytorium Git",
        "Build Dockerfile": "Dockerfile budowania",
        "Credential patterns JSON": "Wzorce danych logowania JSON",
        "Post-install hints PL": "Wskazówki po instalacji PL",
        "Post-install hints EN": "Wskazówki po instalacji EN",
        "Provider": "Dostawca",
        "Model": "Model",
        "OpenAI API key": "Klucz API OpenAI",
        "Ollama URL": "Adres Ollama",
        "Guidance": "Wskazówki",
        "Detect models": "Wykryj modele",
        "Test AI connection": "Testuj połączenie AI",
        "Generate PL + EN store content": "Generuj treść sklepu PL + EN",
        "Generate hero image (OpenAI)": "Generuj grafikę główną (OpenAI)",
    },
}

REPO_BUILDER_PLACEHOLDERS = {
    "PL": {
        "GitHub repository URL": "Adres repozytorium GitHub",
        "Local repository checkout": "Lokalna kopia repozytorium",
        "Search applications…": "Szukaj aplikacji…",
        "Session only - never written to catalog": "Tylko ta sesja — klucz nie jest zapisywany w katalogu",
        "Describe the app and what should be emphasized in the DCC store.": "Opisz aplikację i elementy, które mają być wyróżnione w sklepie DCC.",
    }
}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return slug or "app"


def csv_values(value: str) -> List[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def lines(value: str) -> List[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


class RepoBuilderWindow(QMainWindow):
    def __init__(self, language: Optional[str] = None, theme: Optional[str] = None):
        super().__init__()
        app_settings = QSettings(dcc.APP_SETTINGS_ORG, dcc.APP_SETTINGS_NAME)
        self.lang = str(language or app_settings.value("language", "EN") or "EN").upper()
        if self.lang not in REPO_BUILDER_UI:
            self.lang = "EN"
        self.current_theme = str(theme or app_settings.value("theme", "black") or "black").lower()
        if self.current_theme not in {"light", "day", "dark", "black", "night"}:
            self.current_theme = "black"
        self._apply_theme()
        self.setWindowTitle("DCC Repo Builder")
        self.resize(1180, 760)
        self.catalog: Dict[str, Any] = {"apps": []}
        self.catalog_path: Optional[Path] = None
        self.current_index = -1
        self._loading_form = False
        self._build_ui()
        self._load_default_checkout()
        self._apply_language()

    def _apply_theme(self):
        base_theme = "light" if self.current_theme in {"day", "light"} else "dark"
        extra_qss = dcc.gaming_stylesheet(
            self.current_theme,
            0.52,
            False,
            72,
            False,
            "#33f0ff",
        )
        if hasattr(dcc.qdarktheme, "setup_theme"):
            dcc.qdarktheme.setup_theme(base_theme, additional_qss=extra_qss)
        else:
            app = QApplication.instance()
            if app is not None:
                app.setStyleSheet(extra_qss)

    def _apply_language(self):
        translations = REPO_BUILDER_UI[self.lang]
        for label in self.findChildren(QLabel):
            translated = translations.get(label.text())
            if translated is not None:
                label.setText(translated)
        for button in self.findChildren(QPushButton):
            translated = translations.get(button.text())
            if translated is not None:
                button.setText(translated)
        placeholders = REPO_BUILDER_PLACEHOLDERS.get(self.lang, {})
        for field in self.findChildren(QLineEdit):
            translated = placeholders.get(field.placeholderText())
            if translated is not None:
                field.setPlaceholderText(translated)
        for field in self.findChildren(QPlainTextEdit):
            translated = placeholders.get(field.placeholderText())
            if translated is not None:
                field.setPlaceholderText(translated)
        for index in range(self.tabs.count()):
            title = self.tabs.tabText(index)
            self.tabs.setTabText(index, translations.get(title, title))
        apps_count = len(self.catalog.get("apps") or [])
        if self.catalog_path is not None:
            if self.lang == "PL":
                self.status.setText(f"Wczytano {apps_count} aplikacji z {self.catalog_path}")
            else:
                self.status.setText(f"Loaded {apps_count} applications from {self.catalog_path}")
        elif self.lang == "PL":
            self.status.setText("Gotowe. Zmiany pozostają lokalne do czasu jawnego wykonania commit/push.")

    def _build_ui(self):
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        repo_row = QHBoxLayout()
        self.repo_url = QLineEdit(DEFAULT_REPO_URL)
        self.repo_url.setPlaceholderText("GitHub repository URL")
        self.repo_root = QLineEdit(str(Path(__file__).resolve().parent))
        self.repo_root.setPlaceholderText("Local repository checkout")
        self.btn_repo_browse = QPushButton("Local folder…")
        self.btn_repo_open = QPushButton("Open GitHub")
        self.btn_github_login = QPushButton("GitHub login")
        repo_row.addWidget(QLabel("Repo:"))
        repo_row.addWidget(self.repo_url, 2)
        repo_row.addWidget(QLabel("Local:"))
        repo_row.addWidget(self.repo_root, 2)
        repo_row.addWidget(self.btn_repo_browse)
        repo_row.addWidget(self.btn_repo_open)
        repo_row.addWidget(self.btn_github_login)
        layout.addLayout(repo_row)

        file_row = QHBoxLayout()
        self.catalog_file = QLineEdit("dcc-catalog.json")
        self.btn_load = QPushButton("Load")
        self.btn_validate = QPushButton("Validate")
        self.btn_save = QPushButton("Save local JSON")
        self.btn_git_status = QPushButton("Git status")
        self.btn_commit = QPushButton("Commit catalog…")
        self.btn_push = QPushButton("Push…")
        file_row.addWidget(QLabel("Catalog:"))
        file_row.addWidget(self.catalog_file, 1)
        file_row.addWidget(self.btn_load)
        file_row.addWidget(self.btn_validate)
        file_row.addWidget(self.btn_save)
        file_row.addWidget(self.btn_git_status)
        file_row.addWidget(self.btn_commit)
        file_row.addWidget(self.btn_push)
        layout.addLayout(file_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search applications…")
        self.app_list = QListWidget()
        list_buttons = QHBoxLayout()
        self.btn_new = QPushButton("New")
        self.btn_duplicate = QPushButton("Duplicate")
        self.btn_remove = QPushButton("Remove")
        list_buttons.addWidget(self.btn_new)
        list_buttons.addWidget(self.btn_duplicate)
        list_buttons.addWidget(self.btn_remove)
        left_layout.addWidget(self.search)
        left_layout.addWidget(self.app_list, 1)
        left_layout.addLayout(list_buttons)
        splitter.addWidget(left)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_basic_tab(), "App / Aplikacja")
        self.tabs.addTab(self._build_store_tab(), "Store / Sklep")
        self.tabs.addTab(self._build_advanced_tab(), "Advanced")
        self.tabs.addTab(self._build_ai_tab(), "AI")
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

        self.status = QLabel("Ready. Changes stay local until you explicitly commit/push.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.setCentralWidget(root)

        self.btn_repo_browse.clicked.connect(self.choose_repo_root)
        self.btn_repo_open.clicked.connect(lambda: webbrowser.open(self.repo_url.text().strip() or DEFAULT_REPO_URL))
        self.btn_github_login.clicked.connect(self.github_login)
        self.btn_load.clicked.connect(self.load_catalog)
        self.btn_validate.clicked.connect(self.validate_catalog_dialog)
        self.btn_save.clicked.connect(self.save_catalog)
        self.btn_git_status.clicked.connect(self.git_status)
        self.btn_commit.clicked.connect(self.git_commit)
        self.btn_push.clicked.connect(self.git_push)
        self.btn_new.clicked.connect(self.new_app)
        self.btn_duplicate.clicked.connect(self.duplicate_app)
        self.btn_remove.clicked.connect(self.remove_app)
        self.app_list.currentRowChanged.connect(self.load_selected_app)
        self.search.textChanged.connect(self.refresh_app_list)

    def _build_basic_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        self.name = QLineEdit()
        self.image = QLineEdit()
        self.default_name = QLineEdit()
        self.category = QLineEdit()
        self.category_en = QLineEdit()
        self.description = QPlainTextEdit()
        self.description_en = QPlainTextEdit()
        self.description.setMaximumHeight(90)
        self.description_en.setMaximumHeight(90)
        self.container_port = QLineEdit()
        self.host_port = QLineEdit()
        self.extra = QLineEdit()
        self.command = QLineEdit()
        self.engines = QLineEdit("docker")
        self.archs = QLineEdit()
        form.addRow("Name / Nazwa", self.name)
        form.addRow("Image", self.image)
        form.addRow("Container name", self.default_name)
        form.addRow("Category PL", self.category)
        form.addRow("Category EN", self.category_en)
        form.addRow("Short description PL", self.description)
        form.addRow("Short description EN", self.description_en)
        form.addRow("Container port", self.container_port)
        form.addRow("Host port", self.host_port)
        form.addRow("Extra docker args", self.extra)
        form.addRow("Command", self.command)
        form.addRow("Engines (comma)", self.engines)
        form.addRow("Architectures (comma)", self.archs)
        self.btn_apply_form = QPushButton("Apply changes to entry")
        form.addRow(self.btn_apply_form)
        self.btn_apply_form.clicked.connect(self.apply_form_to_entry)
        return tab

    def _build_store_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        self.store_description = QPlainTextEdit()
        self.store_description_en = QPlainTextEdit()
        self.features = QPlainTextEdit()
        self.features_en = QPlainTextEdit()
        self.icon_url = QLineEdit()
        self.hero_image_url = QLineEdit()
        self.gallery_json = QPlainTextEdit()
        self.store_description.setMaximumHeight(110)
        self.store_description_en.setMaximumHeight(110)
        self.features.setMaximumHeight(100)
        self.features_en.setMaximumHeight(100)
        self.gallery_json.setMaximumHeight(120)
        form.addRow("Store description PL", self.store_description)
        form.addRow("Store description EN", self.store_description_en)
        form.addRow("Features PL (one/line)", self.features)
        form.addRow("Features EN (one/line)", self.features_en)
        form.addRow("Icon URL / relative path", self.icon_url)
        form.addRow("Hero image URL / relative path", self.hero_image_url)
        form.addRow("Gallery JSON", self.gallery_json)
        media_row = QHBoxLayout()
        self.btn_choose_hero = QPushButton("Choose local hero…")
        self.btn_preview_hero = QPushButton("Preview hero")
        media_row.addWidget(self.btn_choose_hero)
        media_row.addWidget(self.btn_preview_hero)
        form.addRow(media_row)
        self.btn_choose_hero.clicked.connect(self.choose_local_hero)
        self.btn_preview_hero.clicked.connect(self.preview_hero)
        return tab

    def _build_advanced_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        self.source_url = QLineEdit()
        self.docs_url = QLineEdit()
        self.homepage_url = QLineEdit()
        self.requires = QLineEdit()
        self.ram_min_mb = QLineEdit()
        self.storage_type = QLineEdit()
        self.security_exposure = QLineEdit()
        self.build_context = QLineEdit()
        self.build_dockerfile = QLineEdit()
        self.credential_patterns = QPlainTextEdit()
        self.post_install_hints = QPlainTextEdit()
        self.post_install_hints_en = QPlainTextEdit()
        self.credential_patterns.setMaximumHeight(130)
        self.post_install_hints.setMaximumHeight(90)
        self.post_install_hints_en.setMaximumHeight(90)
        form.addRow("Source", self.source_url)
        form.addRow("Docs", self.docs_url)
        form.addRow("Homepage", self.homepage_url)
        form.addRow("Requires (comma)", self.requires)
        form.addRow("RAM min MB", self.ram_min_mb)
        form.addRow("Storage type", self.storage_type)
        form.addRow("Security exposure", self.security_exposure)
        form.addRow("Build context / Git repo", self.build_context)
        form.addRow("Build Dockerfile", self.build_dockerfile)
        form.addRow("Credential patterns JSON", self.credential_patterns)
        form.addRow("Post-install hints PL", self.post_install_hints)
        form.addRow("Post-install hints EN", self.post_install_hints_en)
        return tab

    def _build_ai_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()
        self.ai_provider = QComboBox()
        self.ai_provider.addItem("OpenAI", "openai")
        self.ai_provider.addItem("Ollama", "ollama")
        self.ai_model = QComboBox()
        self.ai_model.setEditable(True)
        self.ai_model.addItems(dcc.DEFAULT_OPENAI_MODELS)
        self.ai_model.setCurrentText(dcc.DEFAULT_OPENAI_MODELS[0])
        self.ai_key = QLineEdit()
        self.ai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.ai_key.setPlaceholderText("Session only - never written to catalog")
        self.ollama_url = QLineEdit("http://127.0.0.1:11434")
        self.ai_request = QPlainTextEdit()
        self.ai_request.setPlaceholderText("Describe the app and what should be emphasized in the DCC store.")
        self.ai_request.setMaximumHeight(100)
        form.addRow("Provider", self.ai_provider)
        form.addRow("Model", self.ai_model)
        form.addRow("OpenAI API key", self.ai_key)
        form.addRow("Ollama URL", self.ollama_url)
        form.addRow("Guidance", self.ai_request)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        self.btn_ai_detect = QPushButton("Detect models")
        self.btn_ai_test = QPushButton("Test AI connection")
        self.btn_ai_content = QPushButton("Generate PL + EN store content")
        self.btn_ai_image = QPushButton("Generate hero image (OpenAI)")
        buttons.addWidget(self.btn_ai_detect)
        buttons.addWidget(self.btn_ai_test)
        buttons.addWidget(self.btn_ai_content)
        buttons.addWidget(self.btn_ai_image)
        layout.addLayout(buttons)
        self.ai_result = QPlainTextEdit()
        self.ai_result.setReadOnly(True)
        layout.addWidget(self.ai_result, 1)
        self.btn_ai_content.clicked.connect(self.generate_ai_content)
        self.btn_ai_image.clicked.connect(self.generate_ai_image)
        self.btn_ai_detect.clicked.connect(self.detect_ai_models)
        self.btn_ai_test.clicked.connect(self.test_ai_connection)
        self.ai_provider.currentIndexChanged.connect(self.ai_provider_changed)
        return tab

    def _load_default_checkout(self):
        candidate = Path(self.repo_root.text()).expanduser()
        if (candidate / "dcc-catalog.json").is_file():
            self.load_catalog()

    def choose_repo_root(self):
        path = QFileDialog.getExistingDirectory(self, "Choose DCC repository", self.repo_root.text())
        if path:
            self.repo_root.setText(path)
            self.load_catalog()

    def catalog_disk_path(self) -> Path:
        return Path(self.repo_root.text().strip()).expanduser() / self.catalog_file.text().strip()

    def load_catalog(self):
        path = self.catalog_disk_path()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            apps = payload.get("apps") if isinstance(payload, dict) else None
            if not isinstance(apps, list):
                raise ValueError("Catalog must contain an 'apps' array.")
            self.catalog = payload
            self.catalog_path = path
            self.current_index = -1
            self.refresh_app_list()
            self.status.setText(f"Loaded {len(apps)} apps from {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", str(exc))

    def refresh_app_list(self):
        query = self.search.text().strip().casefold() if hasattr(self, "search") else ""
        selected_name = self.name.text().strip() if hasattr(self, "name") else ""
        self.app_list.blockSignals(True)
        self.app_list.clear()
        for index, app in enumerate(self.catalog.get("apps", [])):
            name = str(app.get("name") or "Unnamed")
            haystack = " ".join(
                str(app.get(key) or "") for key in ("name", "image", "category", "category_en", "description", "description_en")
            ).casefold()
            if query and query not in haystack:
                continue
            self.app_list.addItem(name)
            item = self.app_list.item(self.app_list.count() - 1)
            item.setData(Qt.ItemDataRole.UserRole, index)
            if selected_name and name == selected_name:
                self.app_list.setCurrentItem(item)
        self.app_list.blockSignals(False)

    def current_app(self) -> Optional[Dict[str, Any]]:
        if 0 <= self.current_index < len(self.catalog.get("apps", [])):
            return self.catalog["apps"][self.current_index]
        return None

    def load_selected_app(self, row: int):
        item = self.app_list.item(row) if row >= 0 else None
        if item is None:
            return
        index = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(index, int) or not (0 <= index < len(self.catalog.get("apps", []))):
            return
        self.current_index = index
        self.load_app_into_form(self.catalog["apps"][index])

    def _json_text(self, value: Any, default: str = "[]") -> str:
        if value in (None, ""):
            return default
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return default

    def load_app_into_form(self, app: Dict[str, Any]):
        self._loading_form = True
        try:
            fields = {
                self.name: app.get("name", ""),
                self.image: app.get("image", ""),
                self.default_name: app.get("default_name", ""),
                self.category: app.get("category", ""),
                self.category_en: app.get("category_en", ""),
                self.container_port: app.get("container_port", ""),
                self.host_port: app.get("host_port", ""),
                self.extra: app.get("extra", ""),
                self.command: app.get("command", ""),
                self.engines: ", ".join(app.get("engines") or ["docker"]),
                self.archs: ", ".join(app.get("archs") or []),
                self.icon_url: app.get("icon_url", ""),
                self.hero_image_url: app.get("hero_image_url", ""),
                self.source_url: app.get("source_url", ""),
                self.docs_url: app.get("docs_url", ""),
                self.homepage_url: app.get("homepage_url", ""),
                self.requires: ", ".join(app.get("requires") or []),
                self.ram_min_mb: str(app.get("ram_min_mb") or ""),
                self.storage_type: app.get("storage_type", ""),
                self.security_exposure: app.get("security_exposure", ""),
                self.build_context: app.get("build_context", ""),
                self.build_dockerfile: app.get("build_dockerfile", ""),
            }
            for widget, value in fields.items():
                widget.setText(str(value or ""))
            self.description.setPlainText(str(app.get("description") or ""))
            self.description_en.setPlainText(str(app.get("description_en") or ""))
            self.store_description.setPlainText(str(app.get("store_description") or ""))
            self.store_description_en.setPlainText(str(app.get("store_description_en") or ""))
            self.features.setPlainText("\n".join(app.get("features") or []))
            self.features_en.setPlainText("\n".join(app.get("features_en") or []))
            self.gallery_json.setPlainText(self._json_text(app.get("gallery")))
            self.credential_patterns.setPlainText(self._json_text(app.get("credential_patterns")))
            self.post_install_hints.setPlainText("\n".join(app.get("post_install_hints") or []))
            self.post_install_hints_en.setPlainText("\n".join(app.get("post_install_hints_en") or []))
        finally:
            self._loading_form = False

    def _parse_json_list(self, text: str, label: str) -> List[Any]:
        text = str(text or "").strip()
        if not text:
            return []
        value = json.loads(text)
        if not isinstance(value, list):
            raise ValueError(f"{label} must be a JSON list.")
        return value

    def form_payload(self, base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        app = dict(base or {})
        app.update({
            "name": self.name.text().strip(),
            "image": self.image.text().strip(),
            "default_name": self.default_name.text().strip() or slugify(self.name.text()),
            "category": self.category.text().strip(),
            "category_en": self.category_en.text().strip(),
            "description": self.description.toPlainText().strip(),
            "description_en": self.description_en.toPlainText().strip(),
            "container_port": self.container_port.text().strip(),
            "host_port": self.host_port.text().strip(),
            "extra": self.extra.text().strip(),
            "command": self.command.text().strip(),
            "engines": csv_values(self.engines.text()) or ["docker"],
            "archs": csv_values(self.archs.text()) or None,
            "source_url": self.source_url.text().strip(),
            "docs_url": self.docs_url.text().strip(),
            "homepage_url": self.homepage_url.text().strip(),
            "store_description": self.store_description.toPlainText().strip(),
            "store_description_en": self.store_description_en.toPlainText().strip(),
            "features": lines(self.features.toPlainText()),
            "features_en": lines(self.features_en.toPlainText()),
            "icon_url": self.icon_url.text().strip(),
            "hero_image_url": self.hero_image_url.text().strip(),
            "gallery": self._parse_json_list(self.gallery_json.toPlainText(), "Gallery"),
            "credential_patterns": self._parse_json_list(self.credential_patterns.toPlainText(), "Credential patterns"),
            "post_install_hints": lines(self.post_install_hints.toPlainText()),
            "post_install_hints_en": lines(self.post_install_hints_en.toPlainText()),
            "requires": csv_values(self.requires.text()),
            "ram_min_mb": int(self.ram_min_mb.text().strip() or 0),
            "storage_type": self.storage_type.text().strip(),
            "security_exposure": self.security_exposure.text().strip(),
            "build_context": self.build_context.text().strip(),
            "build_dockerfile": self.build_dockerfile.text().strip(),
        })
        return app

    def validate_app(self, app: Dict[str, Any], index: int = -1) -> List[str]:
        errors: List[str] = []
        if not str(app.get("name") or "").strip():
            errors.append("Name is required.")
        if not str(app.get("image") or "").strip():
            errors.append("Image is required.")
        if not str(app.get("category") or "").strip() or not str(app.get("category_en") or "").strip():
            errors.append("Both PL and EN categories are required.")
        if not str(app.get("description") or "").strip() or not str(app.get("description_en") or "").strip():
            errors.append("Both PL and EN short descriptions are required.")
        # Older DCC catalog entries predate the explicit engines field. DCC
        # itself treats those entries as Docker-compatible, so Repo Builder
        # must validate them with the same backwards-compatible default.
        engines = app.get("engines") or ["docker"]
        if not isinstance(engines, list) or not engines:
            errors.append("At least one engine is required.")
        for field in ("source_url", "docs_url", "homepage_url", "icon_url", "hero_image_url", "build_context"):
            value = str(app.get(field) or "").strip()
            if value and (field.endswith("_url") or field == "build_context") and not (re.match(r"^https?://", value, re.I) or "://" not in value):
                errors.append(f"Invalid {field}: {value}")
        for rule in app.get("credential_patterns") or []:
            if not isinstance(rule, dict) or not str(rule.get("regex") or "").strip():
                errors.append("Credential pattern entries require a regex.")
                continue
            try:
                re.compile(str(rule["regex"]), re.I)
            except re.error as exc:
                errors.append(f"Invalid credential regex: {exc}")
        name = str(app.get("name") or "").casefold()
        default_name = str(app.get("default_name") or "").casefold()
        app_engines = {str(value).strip().lower() for value in (app.get("engines") or ["docker"])}
        for other_index, other in enumerate(self.catalog.get("apps", [])):
            if other_index == index:
                continue
            if name and str(other.get("name") or "").casefold() == name:
                other_engines = {str(value).strip().lower() for value in (other.get("engines") or ["docker"])}
                if "disabled" in app_engines or "disabled" in other_engines:
                    continue
                errors.append(f"Duplicate application name: {app.get('name')}")
                break
        for other_index, other in enumerate(self.catalog.get("apps", [])):
            if other_index == index:
                continue
            if default_name and str(other.get("default_name") or "").casefold() == default_name:
                errors.append(f"Duplicate container default_name: {app.get('default_name')}")
                break
        return errors

    def apply_form_to_entry(self):
        try:
            app = self.form_payload(self.current_app())
        except Exception as exc:
            QMessageBox.warning(self, "Invalid form", str(exc))
            return
        errors = self.validate_app(app, self.current_index)
        if errors:
            QMessageBox.warning(self, "Validation", "\n".join(f"• {error}" for error in errors))
            return
        if self.current_index < 0:
            self.catalog.setdefault("apps", []).append(app)
            self.current_index = len(self.catalog["apps"]) - 1
        else:
            self.catalog["apps"][self.current_index] = app
        self.refresh_app_list()
        self.status.setText(f"Updated local entry: {app['name']}. Use Save local JSON to write the file.")

    def new_app(self):
        self.current_index = -1
        self.load_app_into_form({"engines": ["docker"], "gallery": [], "credential_patterns": []})
        self.name.setFocus()

    def duplicate_app(self):
        app = self.current_app()
        if not app:
            return
        copy = json.loads(json.dumps(app, ensure_ascii=False))
        copy["name"] = str(copy.get("name") or "App") + " Copy"
        copy["default_name"] = slugify(str(copy.get("default_name") or copy["name"]) + "-copy")
        self.catalog.setdefault("apps", []).append(copy)
        self.current_index = len(self.catalog["apps"]) - 1
        self.load_app_into_form(copy)
        self.refresh_app_list()

    def remove_app(self):
        app = self.current_app()
        if not app:
            return
        reply = QMessageBox.question(self, "Remove entry", f"Remove '{app.get('name')}' from the local catalog?")
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.catalog["apps"].pop(self.current_index)
        self.current_index = -1
        self.refresh_app_list()
        self.new_app()

    def validate_catalog(self) -> List[str]:
        errors: List[str] = []
        apps = self.catalog.get("apps") or []
        if not isinstance(apps, list):
            return ["Catalog apps must be a list."]
        for index, app in enumerate(apps):
            if not isinstance(app, dict):
                errors.append(f"Entry {index + 1} is not an object.")
                continue
            for error in self.validate_app(app, index):
                errors.append(f"{app.get('name') or '#' + str(index + 1)}: {error}")
        return errors

    def validate_catalog_dialog(self):
        errors = self.validate_catalog()
        if errors:
            QMessageBox.warning(self, "Catalog validation", "\n".join(errors[:40]))
        else:
            QMessageBox.information(self, "Catalog validation", f"OK - {len(self.catalog.get('apps', []))} entries are valid.")

    def save_catalog(self):
        if self.current_app() is not None:
            try:
                candidate = self.form_payload(self.current_app())
                errors = self.validate_app(candidate, self.current_index)
                if not errors:
                    self.catalog["apps"][self.current_index] = candidate
            except Exception:
                pass
        errors = self.validate_catalog()
        if errors:
            QMessageBox.warning(self, "Cannot save", "Fix validation errors first:\n\n" + "\n".join(errors[:30]))
            return
        path = self.catalog_disk_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.catalog_path = path
            self.status.setText(f"Saved locally: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def repo_path(self) -> Path:
        return Path(self.repo_root.text().strip()).expanduser()

    def _run_git(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + list(args),
            cwd=str(self.repo_path()),
            text=True,
            capture_output=True,
            check=check,
        )

    def github_login(self):
        if not shutil.which("gh"):
            QMessageBox.information(
                self,
                "GitHub CLI required",
                "Install GitHub CLI (gh) first. Repo Builder does not store a GitHub token itself.",
            )
            webbrowser.open("https://cli.github.com/")
            return
        try:
            status = subprocess.run(
                ["gh", "auth", "status", "--hostname", "github.com"],
                text=True,
                capture_output=True,
            )
            if status.returncode == 0:
                QMessageBox.information(self, "GitHub", "GitHub CLI is already authenticated.")
                return
            flags = 0
            if os.name == "nt":
                flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            subprocess.Popen(
                ["gh", "auth", "login", "--hostname", "github.com", "--web", "--git-protocol", "https"],
                cwd=str(self.repo_path()),
                creationflags=flags,
            )
            self.status.setText("GitHub login started. Complete browser/device authorization in the opened gh session.")
        except Exception as exc:
            QMessageBox.critical(self, "GitHub login failed", str(exc))

    def git_status(self):
        try:
            result = self._run_git(["status", "--short", "--branch"])
            QMessageBox.information(self, "Git status", result.stdout.strip() or "Working tree clean.")
        except Exception as exc:
            QMessageBox.critical(self, "Git status failed", str(exc))

    def git_commit(self):
        self.save_catalog()
        if not self.catalog_path or not self.catalog_path.exists():
            return
        relative = os.path.relpath(self.catalog_path, self.repo_path())
        message, ok = self._text_prompt("Commit catalog", "Commit message", "Update DCC deployment catalog")
        if not ok or not message.strip():
            return
        reply = QMessageBox.question(
            self,
            "Commit local catalog",
            f"Stage and commit only {relative}?\n\nNo push will be performed.",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._run_git(["add", "--", relative])
            result = self._run_git(["commit", "-m", message.strip()])
            self.status.setText(result.stdout.strip() or "Catalog committed locally.")
        except subprocess.CalledProcessError as exc:
            QMessageBox.critical(self, "Commit failed", (exc.stderr or exc.stdout or str(exc)).strip())

    def git_push(self):
        reply = QMessageBox.question(
            self,
            "Push to GitHub",
            "Push the current branch to its configured upstream now?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            result = self._run_git(["push"])
            self.status.setText((result.stdout or result.stderr).strip() or "Push completed.")
        except subprocess.CalledProcessError as exc:
            QMessageBox.critical(self, "Push failed", (exc.stderr or exc.stdout or str(exc)).strip())

    def _text_prompt(self, title: str, label: str, initial: str = "") -> tuple[str, bool]:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(label))
        edit = QLineEdit(initial)
        layout.addWidget(edit)
        row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        ok_button = QPushButton("OK")
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(ok_button)
        layout.addLayout(row)
        ok_button.clicked.connect(dialog.accept)
        cancel.clicked.connect(dialog.reject)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        return edit.text(), accepted

    def choose_local_hero(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose hero image",
            str(self.repo_path()),
            "Images (*.png *.jpg *.jpeg *.webp)",
        )
        if not path:
            return
        source = Path(path)
        target_dir = self.repo_path() / "catalog-assets" / slugify(self.name.text())
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / ("hero" + source.suffix.lower())
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        self.hero_image_url.setText(target.relative_to(self.repo_path()).as_posix())
        self.preview_hero()

    def preview_hero(self):
        value = self.hero_image_url.text().strip()
        if not value:
            QMessageBox.information(self, "Preview", "No hero image configured.")
            return
        path = self.repo_path() / value
        if not path.is_file():
            QMessageBox.information(self, "Preview", f"Local preview is available for repo-relative images.\n\n{value}")
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            QMessageBox.warning(self, "Preview", "Could not load image.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(self.name.text().strip() or "Preview")
        layout = QVBoxLayout(dialog)
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setPixmap(pixmap.scaled(820, 520, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(label)
        dialog.resize(860, 580)
        dialog.exec()

    def ai_provider_changed(self):
        provider = self.ai_provider.currentData()
        current = self.ai_model.currentText().strip()
        if provider == "ollama":
            if current.startswith("gpt-") or not current:
                self.ai_model.setCurrentText("qwen3:1.7b")
            self.ai_key.setEnabled(False)
            self.ollama_url.setEnabled(True)
            self.btn_ai_image.setEnabled(False)
            self.detect_ai_models(show_dialog=False)
        else:
            if not current.startswith("gpt-"):
                self._set_ai_model_items(dcc.DEFAULT_OPENAI_MODELS, dcc.DEFAULT_OPENAI_MODELS[0])
            self.ai_key.setEnabled(True)
            self.ollama_url.setEnabled(False)
            self.btn_ai_image.setEnabled(True)

    def _set_ai_model_items(self, models: List[str], selected: str = ""):
        values = [str(model).strip() for model in models if str(model).strip()]
        if not values:
            return
        current = selected.strip() or self.ai_model.currentText().strip()
        self.ai_model.blockSignals(True)
        self.ai_model.clear()
        self.ai_model.addItems(values)
        if current in values:
            self.ai_model.setCurrentText(current)
        else:
            self.ai_model.setCurrentText(values[0])
        self.ai_model.blockSignals(False)

    def detect_ai_models(self, _checked: bool = False, show_dialog: bool = True) -> List[str]:
        provider = str(self.ai_provider.currentData() or "openai")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            if provider == "ollama":
                base_url = self.ollama_url.text().strip() or "http://127.0.0.1:11434"
                models = dcc.fetch_ollama_models(base_url)
                selected = self.ai_model.currentText().strip()
                if selected not in models:
                    selected = dcc.select_ollama_fallback_model(models)
                self._set_ai_model_items(models, selected)
                self.status.setText(
                    f"Ollama connected: {len(models)} local model(s). Selected: {self.ai_model.currentText()}."
                )
            else:
                key = self.ai_key.text().strip()
                if not key:
                    raise RuntimeError("Enter an OpenAI API key for this session.")
                models = dcc.fetch_openai_models(key)
                selected = self.ai_model.currentText().strip()
                self._set_ai_model_items(models, selected if selected in models else dcc.DEFAULT_OPENAI_MODELS[0])
                self.status.setText(f"OpenAI connected: {len(models)} model(s) detected.")
            if show_dialog:
                QMessageBox.information(self, "AI models", self.status.text())
            return models
        except Exception as exc:
            message = f"Could not detect {provider} models: {exc}"
            self.status.setText(message)
            if show_dialog:
                QMessageBox.critical(self, "AI connection failed", message)
            return []
        finally:
            QApplication.restoreOverrideCursor()

    def test_ai_connection(self):
        provider = str(self.ai_provider.currentData() or "openai")
        models = self.detect_ai_models(show_dialog=False)
        if not models:
            QMessageBox.critical(self, "AI connection failed", self.status.text())
            return
        QMessageBox.information(
            self,
            "AI connection",
            f"{provider.title()} is reachable.\nDetected models: {len(models)}\nSelected: {self.ai_model.currentText()}",
        )

    def _extract_json_object(self, text: str) -> Dict[str, Any]:
        text = str(text or "").strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S | re.I)
        candidate = fenced.group(1) if fenced else text
        if not candidate.startswith("{"):
            match = re.search(r"\{.*\}", candidate, re.S)
            if match:
                candidate = match.group(0)
        payload = json.loads(candidate)
        if not isinstance(payload, dict):
            raise ValueError("AI result must be a JSON object.")
        return payload

    def generate_ai_content(self):
        name = self.name.text().strip()
        image = self.image.text().strip()
        source = self.source_url.text().strip()
        if not name and not image:
            QMessageBox.warning(self, "AI", "Enter at least the application name or image first.")
            return
        provider = str(self.ai_provider.currentData() or "openai")
        model = self.ai_model.currentText().strip()
        guidance = self.ai_request.toPlainText().strip()
        system_prompt = (
            "You prepare metadata for a self-hosted application store. Return ONLY valid JSON. "
            "Write concise, factual Polish and English copy. Do not invent capabilities. "
            "Return keys: category, category_en, description, description_en, store_description, "
            "store_description_en, features, features_en, post_install_hints, post_install_hints_en. "
            "features and hints must be arrays of strings."
        )
        user_prompt = (
            f"Application: {name}\nImage: {image}\nSource: {source}\n"
            f"Current PL description: {self.description.toPlainText()}\n"
            f"Current EN description: {self.description_en.toPlainText()}\n"
            f"Additional guidance: {guidance or 'none'}"
        )
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            if provider == "openai":
                key = self.ai_key.text().strip()
                if not key:
                    raise RuntimeError("Enter an OpenAI API key for this session.")
                result = dcc.call_openai_model(key, model or dcc.DEFAULT_OPENAI_MODELS[0], system_prompt, user_prompt)
            else:
                base_url = self.ollama_url.text().strip() or "http://127.0.0.1:11434"
                models = dcc.fetch_ollama_models(base_url)
                if model not in models:
                    model = dcc.select_ollama_fallback_model(models)
                    self._set_ai_model_items(models, model)
                    self.status.setText(f"Selected Ollama model was unavailable. Using {model}.")
                result = dcc.call_ollama_model(base_url, model, system_prompt, user_prompt)
            payload = self._extract_json_object(result)
            self.ai_result.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))
            mapping = {
                "category": self.category,
                "category_en": self.category_en,
            }
            for key_name, widget in mapping.items():
                if payload.get(key_name):
                    widget.setText(str(payload[key_name]))
            text_mapping = {
                "description": self.description,
                "description_en": self.description_en,
                "store_description": self.store_description,
                "store_description_en": self.store_description_en,
            }
            for key_name, widget in text_mapping.items():
                if payload.get(key_name):
                    widget.setPlainText(str(payload[key_name]))
            list_mapping = {
                "features": self.features,
                "features_en": self.features_en,
                "post_install_hints": self.post_install_hints,
                "post_install_hints_en": self.post_install_hints_en,
            }
            for key_name, widget in list_mapping.items():
                value = payload.get(key_name)
                if isinstance(value, list):
                    widget.setPlainText("\n".join(str(item) for item in value if str(item).strip()))
            self.tabs.setCurrentIndex(1)
            self.status.setText("AI content generated in the form. Review it before applying/saving.")
        except Exception as exc:
            QMessageBox.critical(self, "AI generation failed", str(exc))
        finally:
            QApplication.restoreOverrideCursor()

    def generate_ai_image(self):
        key = self.ai_key.text().strip()
        if not key:
            QMessageBox.warning(self, "AI image", "Enter an OpenAI API key for this session.")
            return
        name = self.name.text().strip() or "self-hosted application"
        guidance = self.ai_request.toPlainText().strip()
        prompt = (
            f"Create a clean modern application-store hero image for {name}. "
            "Dark technology UI aesthetic, polished 3D/isometric visual language, no fake UI text, "
            "no logos unless clearly implied by the project identity, suitable for a Docker self-hosted app catalog. "
            f"Additional direction: {guidance or 'focus on the application purpose'}"
        )
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            payload = dcc.request_json(
                "https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {key}", "User-Agent": f"DCC-Repo-Builder/{dcc.APP_VERSION}"},
                payload={"model": "gpt-image-2", "prompt": prompt, "size": "1024x1024"},
                timeout=120,
            )
            data = payload.get("data") or []
            if not data or not isinstance(data[0], dict):
                raise RuntimeError("OpenAI returned no image data.")
            encoded = str(data[0].get("b64_json") or "")
            if not encoded:
                image_url = str(data[0].get("url") or "")
                if image_url:
                    self.hero_image_url.setText(image_url)
                    self.status.setText("OpenAI returned a hosted image URL. Review it before saving.")
                    return
                raise RuntimeError("OpenAI response did not contain b64_json or an image URL.")
            target_dir = self.repo_path() / "catalog-assets" / slugify(name)
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / "hero.png"
            target.write_bytes(base64.b64decode(encoded))
            self.hero_image_url.setText(target.relative_to(self.repo_path()).as_posix())
            self.status.setText(f"Generated image saved locally: {target}")
            self.preview_hero()
        except Exception as exc:
            QMessageBox.critical(self, "AI image generation failed", str(exc))
        finally:
            QApplication.restoreOverrideCursor()


def main() -> int:
    self_check = "--self-check" in sys.argv
    if self_check:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(sys.argv)
    app.setApplicationName("DCC Repo Builder")
    if sys.platform.startswith("linux") and hasattr(app, "setDesktopFileName"):
        app.setDesktopFileName("dcc-repo-builder")
    if dcc.ICON_FILE.exists():
        app.setWindowIcon(QIcon(str(dcc.ICON_FILE)))
    window = RepoBuilderWindow()
    if self_check:
        errors = window.validate_catalog()
        checks = {
            "window": window.windowTitle() == "DCC Repo Builder",
            "catalog_loaded": bool(window.catalog.get("apps")),
            "catalog_valid": not errors,
            "store_tab": window.tabs.count() >= 4,
            "repo_controls": bool(window.repo_url.text().strip()) and hasattr(window, "btn_commit") and hasattr(window, "btn_push"),
            "ai_controls": hasattr(window, "ai_provider") and hasattr(window, "btn_ai_detect") and hasattr(window, "btn_ai_test"),
        }
        ok = all(checks.values())
        payload = {
            "ok": ok,
            "apps": len(window.catalog.get("apps") or []),
            "checks": checks,
            "validation_errors": errors[:10],
        }
        try:
            print(json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass
        window.close()
        return 0 if ok else 2
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
