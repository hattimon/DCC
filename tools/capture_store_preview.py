import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QWidget

import DockerControlCenter as dcc


class EmptyContainers:
    def list(self, all=True):
        return []


class FakeClient:
    def __init__(self):
        self.containers = EmptyContainers()


class ThemeHost(QWidget):
    def __init__(self, theme: str, accent: str):
        super().__init__()
        self.current_theme = theme
        self.accent_color = accent


def main():
    width = int(sys.argv[1]) if len(sys.argv) > 1 else 1360
    height = int(sys.argv[2]) if len(sys.argv) > 2 else 820
    filename = sys.argv[3] if len(sys.argv) > 3 else "DCC-Store-Preview-v3.png"
    theme = sys.argv[4] if len(sys.argv) > 4 else "black"
    accent = sys.argv[5] if len(sys.argv) > 5 else "#ff4bd8"
    app = QApplication.instance() or QApplication([])
    stylesheet = dcc.gaming_stylesheet(theme, 0.52, False, 72, False, accent)
    if hasattr(dcc.qdarktheme, "setup_theme"):
        dcc.qdarktheme.setup_theme("dark", additional_qss=stylesheet)
    else:
        app.setStyleSheet(stylesheet)
    parent = ThemeHost(theme, accent)
    original_single_shot = QTimer.singleShot
    QTimer.singleShot = staticmethod(lambda *args, **kwargs: None)
    try:
        dialog = dcc.NewContainerDialog(
            FakeClient(),
            dcc.TEXTS["PL"],
            lang="PL",
            target_host_label="LOCAL - Windows 11 / Docker Desktop",
            parent=parent,
        )
        dialog.resize(width, height)
        dialog.show()
        app.processEvents()
        dialog._update_category_nav_height()
        app.processEvents()
        target = ROOT / "release" / filename
        dialog.grab().save(str(target), "PNG")
        print(target)
        dialog.close()
        app.processEvents()
    finally:
        QTimer.singleShot = original_single_shot


if __name__ == "__main__":
    main()
