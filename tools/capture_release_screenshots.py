import os
import sys
import tempfile
from pathlib import Path


def configure_qt_platform():
    """Use the native desktop backend when one is available.

    Qt's offscreen backend is useful for headless Linux jobs, but on Windows it
    can render application fonts as missing-glyph squares.  Leave normal
    desktop sessions on their native platform and only fall back to offscreen
    when Linux has no display server.
    """
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
from PyQt6.QtWidgets import QApplication, QWidget

import DockerControlCenter as dcc


OUT = ROOT / "images" / "release-1.3.5"


class EmptyContainers:
    def list(self, all=True):
        return []


class FakeClient:
    def __init__(self):
        self.containers = EmptyContainers()


class DependencyStub(QWidget):
    def __init__(self, texts):
        super().__init__()
        self.texts = texts

    def is_local_docker_available(self):
        return True

    def windows_docker_desktop_installed(self):
        return True

    def is_ssh_client_available(self):
        return True

    def is_ssh_agent_available(self):
        return True

    def ssh_tools_auto_install_supported(self):
        return True

    def linux_docker_auto_install_supported(self):
        return True

    def install_windows_docker_desktop_with_progress(self):
        return False

    def try_start_docker_desktop(self):
        return False

    def install_linux_docker_with_progress(self):
        return False

    def install_ssh_tools_with_progress(self):
        return False


def save_widget(app, widget, filename, size=None):
    if size:
        widget.resize(*size)
    widget.show()
    app.processEvents()
    image = widget.grab()
    target = OUT / filename
    image.save(str(target), "PNG")
    widget.hide()
    app.processEvents()
    return target


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    if hasattr(dcc.qdarktheme, "setup_theme"):
        dcc.qdarktheme.setup_theme(
            "dark",
            additional_qss=dcc.gaming_stylesheet("black", 0.52, False, 72, True, "#33f0ff"),
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dcc.PROFILE_FILE = root / "profiles.json"
        dcc.SECRET_FILE = root / "secrets.json"
        dcc.DEPLOYMENT_REPOSITORIES_FILE = root / "repositories.json"
        dcc.DEPLOYMENT_CATALOG_CACHE_FILE = root / "catalog_cache.json"
        dcc.load_cached_deployment_catalog = lambda: []
        dcc.load_deployment_repository_sources = lambda: [dcc.DEFAULT_DEPLOYMENT_REPOSITORY]
        dcc.save_cached_deployment_catalog = lambda items: None

        settings = QSettings(str(root / "ui.ini"), QSettings.Format.IniFormat)
        settings.setValue("language", "EN")
        settings.setValue("theme", "black")
        settings.setValue("music_enabled", "false")
        settings.setValue("updates/auto_check", "false")
        settings.setValue("auto_start_docker_desktop", "false")
        settings.sync()

        original_single_shot = dcc.QTimer.singleShot
        original_media_player = dcc.QMediaPlayer
        original_audio_output = dcc.QAudioOutput
        dcc.QTimer.singleShot = staticmethod(lambda *args, **kwargs: None)
        # Release screenshots never need audio.  Avoid creating Qt Multimedia
        # objects here because their Windows teardown can abort an otherwise
        # successful screenshot run after all PNG files have been written.
        dcc.QMediaPlayer = None
        dcc.QAudioOutput = None
        try:
            main_window = dcc.MainWindow(settings)
            main_window.statusBar().showMessage("Ready · Docker Control Center v1.3.5")
            save_widget(app, main_window, "01-main-window.png", (1360, 760))
            main_window.close()
            main_window.deleteLater()
            app.processEvents()
        finally:
            dcc.QTimer.singleShot = original_single_shot
            dcc.QMediaPlayer = original_media_player
            dcc.QAudioOutput = original_audio_output

        manual = dcc.NewContainerDialog(
            FakeClient(), dcc.TEXTS["EN"], lang="EN", target_host_label="LOCAL · Windows 11 / Docker Desktop"
        )
        manual.name_edit.setText("my-service")
        manual.image_edit.setText("ghcr.io/example/my-service:latest")
        manual.cport_edit.setText("8080")
        manual.hport_edit.setText("18080")
        manual.extra_edit.setText("--restart unless-stopped -v service-data:/data")
        manual.update_summary()
        save_widget(app, manual, "02-manual-container-configuration.png", (980, 760))
        manual.close()

        edit = dcc.NewContainerDialog(
            FakeClient(),
            dcc.TEXTS["EN"],
            initial_args=[
                "run", "-d", "--name", "hqtrader-api", "--restart", "unless-stopped",
                "-p", "8000:8000", "-e", "APP_ENV=production", "hqtrader-api:local",
            ],
            edit_mode=True,
            existing_name="hqtrader-api",
            lang="EN",
            target_host_label="Remote Docker · Ubuntu x86_64",
        )
        save_widget(app, edit, "03-edit-existing-container.png", (980, 760))
        edit.close()

        repos = dcc.CatalogRepositoryDialog([dcc.DEFAULT_DEPLOYMENT_REPOSITORY], dcc.TEXTS["EN"])
        repos.source_edit.setText("https://github.com/example/community-dcc-catalog")
        save_widget(app, repos, "04-catalog-repositories.png", (900, 520))
        repos.close()

        profiles = [
            dcc.RemoteProfile(
                name="Raspberry Pi / Balena",
                mode="ssh",
                ssh_target="admin@192.168.1.42",
                ssh_port=22,
                ssh_auth_mode="agent",
                wait_seconds=3,
            ),
            dcc.RemoteProfile(
                name="Ubuntu Docker Server",
                mode="ssh",
                ssh_target="docker@10.0.0.25",
                ssh_port=22,
                ssh_auth_mode="key",
                ssh_key_path="C:/Users/User/.ssh/id_ed25519",
                wait_seconds=2,
            ),
        ]
        profile_dialog = dcc.ProfileManagerDialog(profiles, dcc.TEXTS["EN"])
        profile_dialog.list_widget.setCurrentRow(0)
        save_widget(app, profile_dialog, "05-connection-profiles.png", (1100, 660))
        profile_dialog.close()

        dep_stub = DependencyStub(dcc.TEXTS["EN"])
        deps = dcc.DependencyManagerDialog(dep_stub, dep_stub)
        save_widget(app, deps, "06-dependencies.png", (820, 500))
        deps.close()
        dep_stub.close()

        secret_store = dcc.SecretStore(root / "llm-secrets.json")
        llm_settings = QSettings(str(root / "llm.ini"), QSettings.Format.IniFormat)
        llm_settings.setValue("llm/provider", "anthropic")
        llm_settings.setValue("llm/model/anthropic", "claude-sonnet-4-5")
        llm_dialog = dcc.LlmSettingsDialog(llm_settings, secret_store, dcc.TEXTS["EN"])
        llm_dialog.provider_combo.setCurrentIndex(llm_dialog.provider_combo.findData("anthropic"))
        save_widget(app, llm_dialog, "07-llm-providers.png", (820, 430))
        if sys.platform.startswith("win"):
            # All release images are complete at this point.  Some Windows
            # PyQt6 builds abort while destroying the remaining Qt objects,
            # even though generation succeeded.  Exit before that native
            # teardown; failures raised before this point still fail normally.
            print("\n".join(str(path) for path in sorted(OUT.glob("*.png"))))
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)
        llm_dialog.close()

    print("\n".join(str(path) for path in sorted(OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
