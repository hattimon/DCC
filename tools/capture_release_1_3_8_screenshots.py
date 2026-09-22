import os
import sys
import tempfile
from pathlib import Path


def configure_qt_platform():
    if os.environ.get("QT_QPA_PLATFORM"):
        return
    if sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"


configure_qt_platform()

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QTabWidget

import DockerControlCenter as dcc
from RepoBuilder import RepoBuilderWindow


OUT = ROOT / "images" / "release-1.3.8"


class EmptyContainers:
    def list(self, all=True):
        return []


class FakeClient:
    def __init__(self):
        self.containers = EmptyContainers()


def process_events(app: QApplication, rounds: int = 4):
    for _ in range(rounds):
        app.processEvents()


def save_widget(app: QApplication, widget, filename: str, size):
    widget.resize(*size)
    widget.show()
    process_events(app, 8)
    target = OUT / filename
    image = widget.grab()
    if not image.save(str(target), "PNG"):
        raise RuntimeError(f"Could not save screenshot: {target}")
    widget.hide()
    process_events(app, 3)
    return target


def select_smartwan(dialog: dcc.NewContainerDialog, app: QApplication):
    dialog.manual_configuration_mode = False
    dialog.search_edit.setText("SmartWAN")
    dialog.filter_catalog()
    process_events(app, 4)
    row = next(
        (index for index, item in enumerate(dialog.filtered_catalog) if "smartwan" in item.name.lower()),
        -1,
    )
    if row < 0:
        raise RuntimeError("SmartWAN Manager was not found in the bundled DCC catalog")
    dialog.catalog_list.setCurrentRow(row)
    dialog.apply_selected_template(row)
    dialog.editor_tabs.setCurrentIndex(0)
    process_events(app, 8)


def select_repo_builder_smartwan(window: RepoBuilderWindow, app: QApplication):
    window.search.setText("SmartWAN")
    process_events(app, 3)
    if window.app_list.count() < 1:
        raise RuntimeError("SmartWAN Manager was not found in Repo Builder")
    window.app_list.setCurrentRow(0)
    window.tabs.setCurrentIndex(1)
    process_events(app, 5)


def create_main_window(app: QApplication, root: Path, lang: str, theme: str):
    settings = QSettings(str(root / f"main-{lang}-{theme}.ini"), QSettings.Format.IniFormat)
    settings.setValue("language", lang)
    settings.setValue("theme", theme)
    settings.setValue("music_enabled", "false")
    settings.setValue("updates/auto_check", "false")
    settings.setValue("auto_start_docker_desktop", "false")
    settings.setValue("transparent_mode", "false")
    settings.sync()
    window = dcc.MainWindow(settings)
    ready = "Gotowe" if lang == "PL" else "Ready"
    window.statusBar().showMessage(f"{ready} · Docker Control Center v{dcc.APP_VERSION}")
    process_events(app, 5)
    return window


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName(dcc.APP_SETTINGS_ORG)
    app.setApplicationName(dcc.APP_SETTINGS_NAME)

    generated = []
    with tempfile.TemporaryDirectory() as tmp:
        temp_root = Path(tmp)
        dcc.PROFILE_FILE = temp_root / "profiles.json"
        dcc.SECRET_FILE = temp_root / "secrets.json"
        dcc.DEPLOYMENT_REPOSITORIES_FILE = temp_root / "repositories.json"
        dcc.DEPLOYMENT_CATALOG_CACHE_FILE = temp_root / "catalog-cache.json"
        dcc.STORE_MEDIA_CACHE_DIR = temp_root / "store-media"
        dcc.STORE_MEDIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        dcc.load_cached_deployment_catalog = lambda: []
        dcc.load_deployment_repository_sources = lambda: [dcc.DEFAULT_DEPLOYMENT_REPOSITORY]
        dcc.save_cached_deployment_catalog = lambda items: None

        original_single_shot = dcc.QTimer.singleShot
        original_media_player = dcc.QMediaPlayer
        original_audio_output = dcc.QAudioOutput
        dcc.QTimer.singleShot = staticmethod(lambda *args, **kwargs: None)
        dcc.QMediaPlayer = None
        dcc.QAudioOutput = None
        try:
            for lang in ("PL", "EN"):
                lang_slug = lang.lower()
                for theme in ("day", "night"):
                    main_window = create_main_window(app, temp_root, lang, theme)
                    generated.append(
                        save_widget(
                            app,
                            main_window,
                            f"main-{theme}-{lang_slug}.png",
                            (1440, 860),
                        )
                    )
                    main_window.close()
                    main_window.deleteLater()
                    process_events(app, 4)

                    if hasattr(dcc.qdarktheme, "setup_theme"):
                        base_theme = "light" if theme == "day" else "dark"
                        dcc.qdarktheme.setup_theme(
                            base_theme,
                            additional_qss=dcc.gaming_stylesheet(
                                theme, 0.52, False, 72, False, "#33f0ff"
                            ),
                        )
                    store = dcc.NewContainerDialog(
                        FakeClient(),
                        dcc.TEXTS[lang],
                        lang=lang,
                        target_host_label="LOCAL · Windows / Docker Desktop",
                    )
                    store.catalog_theme = theme
                    store.catalog_accent = dcc.effective_accent_color(theme, "#33f0ff")
                    store._apply_catalog_card_style()
                    select_smartwan(store, app)
                    generated.append(
                        save_widget(
                            app,
                            store,
                            f"store-smartwan-{theme}-{lang_slug}.png",
                            (1600, 900),
                        )
                    )
                    store.close()
                    store.deleteLater()
                    process_events(app, 4)

                    repo_builder = RepoBuilderWindow(language=lang, theme=theme)
                    select_repo_builder_smartwan(repo_builder, app)
                    generated.append(
                        save_widget(
                            app,
                            repo_builder,
                            f"repo-builder-{theme}-{lang_slug}.png",
                            (1440, 860),
                        )
                    )
                    repo_builder.close()
                    repo_builder.deleteLater()
                    process_events(app, 4)
        finally:
            dcc.QTimer.singleShot = original_single_shot
            dcc.QMediaPlayer = original_media_player
            dcc.QAudioOutput = original_audio_output

    print("\n".join(str(path) for path in generated))
    if sys.platform.startswith("win"):
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)


if __name__ == "__main__":
    main()
