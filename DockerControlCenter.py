
import base64
import ctypes
import getpass
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import shlex
import sys
import tempfile
import time
import uuid
import webbrowser
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

if os.name == 'nt':
    from ctypes import wintypes

import docker
import qdarktheme
from PyQt6.QtCore import QEvent, QObject, QProcess, QPropertyAnimation, QRectF, QSettings, QSize, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
try:
    import paramiko
except Exception:
    paramiko = None
from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetrics, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QTextCursor
try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
except Exception:
    QAudioOutput = None
    QMediaPlayer = None
from PyQt6.QtWidgets import (
    QFileDialog,
    QApplication,
    QAbstractItemView,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class CategoryTileDelegate(QStyledItemDelegate):
    """Render category tiles as compact icon-left / text-right buttons."""

    def initStyleOption(self, option: QStyleOptionViewItem, index):
        super().initStyleOption(option, index)
        option.decorationPosition = QStyleOptionViewItem.Position.Left
        option.decorationAlignment = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        option.displayAlignment = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft


class StaticCategoryListWidget(QListWidget):
    """Wrapping category buttons that never behave like a scrollable list."""

    def wheelEvent(self, event):
        # Consume mouse-wheel and touchpad-wheel input instead of passing it to
        # QListView or the outer dialog scroll area.
        event.accept()

    def scrollTo(self, index, hint=QAbstractItemView.ScrollHint.EnsureVisible):  # type: ignore[override]
        # Selecting a chip in the last row must not make QListView move the
        # first rows outside its viewport.
        return

    def lock_scroll_position(self) -> None:
        for scrollbar in (self.verticalScrollBar(), self.horizontalScrollBar()):
            scrollbar.setValue(0)
            scrollbar.setRange(0, 0)

DOCKER_HTTP_TIMEOUT = 30
APP_SETTINGS_ORG = "DockerControlCenter"
APP_SETTINGS_NAME = "DockerControlCenter"
APP_DATA_DIR_NAME = "DockerControlCenter"
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
if os.name == "nt":
    USER_DATA_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / APP_DATA_DIR_NAME
else:
    USER_DATA_DIR = Path.home() / ".docker-control-center"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
PROFILE_FILE = USER_DATA_DIR / "docker_connection_profiles.json"
DEPLOYMENT_REPOSITORIES_FILE = USER_DATA_DIR / "deployment_repositories.json"
DEPLOYMENT_CATALOG_CACHE_FILE = USER_DATA_DIR / "deployment_catalog_cache.json"
BUNDLED_DEPLOYMENT_CATALOG_FILE = RESOURCE_DIR / "dcc-catalog.json"
STORE_MEDIA_CACHE_DIR = USER_DATA_DIR / "store-media-cache"
STORE_MEDIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
MUSIC_FILE = RESOURCE_DIR / "bg.mp3"
SECRET_FILE = USER_DATA_DIR / "docker_control_center_secrets.json"
BACKGROUND_DIR = RESOURCE_DIR / "backgrounds"
ICON_FILE = RESOURCE_DIR / "icon.png"
BACKGROUND_NAMES = {
    "light": ("theme_light", "light"),
    "day": ("theme_day", "day"),
    "dark": ("theme_dark", "dark"),
    "black": ("theme_black", "black"),
    "night": ("theme_night", "night"),
}
BACKGROUND_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
NEON_PALETTE = [
    ("Cyan", "#33f0ff"),
    ("Blue", "#4b7bff"),
    ("Mint", "#4bffad"),
    ("Purple", "#b26bff"),
    ("Pink", "#ff4bd8"),
    ("Orange", "#ff9955"),
    ("Gold", "#ffd166"),
    ("Red", "#ff5f5f"),
]
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
DEFAULT_OPENAI_MODELS = [
    "gpt-4.1-mini",
    "gpt-4.1",
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-3.5-turbo-0125",
]
DEFAULT_OLLAMA_MODELS = [
    "qwen3:4b-instruct",
    "qwen3:1.7b",
    "qwen2.5-coder:7b",
    "llama3.2",
]

LLM_PROVIDER_ORDER = [
    "ollama",
    "openai",
    "anthropic",
    "gemini",
    "groq",
    "mistral",
    "openrouter",
    "deepseek",
    "xai",
]
LLM_PROVIDER_LABEL_KEYS = {
    "ollama": "llm_provider_ollama",
    "openai": "llm_provider_openai",
    "anthropic": "llm_provider_anthropic",
    "gemini": "llm_provider_gemini",
    "groq": "llm_provider_groq",
    "mistral": "llm_provider_mistral",
    "openrouter": "llm_provider_openrouter",
    "deepseek": "llm_provider_deepseek",
    "xai": "llm_provider_xai",
}
LLM_DEFAULT_MODELS = {
    "ollama": list(DEFAULT_OLLAMA_MODELS),
    "openai": list(DEFAULT_OPENAI_MODELS),
    "anthropic": ["claude-opus-5", "claude-sonnet-4-5", "claude-haiku-4-5"],
    "gemini": ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-2.5-pro"],
    "groq": ["openai/gpt-oss-20b", "llama-3.3-70b-versatile", "qwen/qwen3.6-27b"],
    "mistral": ["mistral-medium-latest", "mistral-small-latest", "codestral-latest"],
    "openrouter": ["~openai/gpt-latest", "~anthropic/claude-sonnet-latest"],
    "deepseek": ["deepseek-flash", "deepseek-v4-pro"],
    "xai": ["grok-4.6", "grok-4", "grok-3"],
}
LLM_OPENAI_COMPATIBLE_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "deepseek": "https://api.deepseek.com",
    "xai": "https://api.x.ai/v1",
}

APP_VERSION = "1.3.8"
APP_VERSION_TAG = f"v{APP_VERSION}"
GITHUB_REPO = "hattimon/DCC"
GITHUB_REPO_URL = f"https://github.com/{GITHUB_REPO}"
DEFAULT_DEPLOYMENT_REPOSITORY = GITHUB_REPO_URL
GITHUB_RELEASES_URL = f"{GITHUB_REPO_URL}/releases"
GITHUB_LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
UPDATE_CHECK_INTERVAL_MS = 15 * 60 * 1000

TEXTS = {
    "EN": {
        "app_title": "Docker Control Center",
        "menu_file": "File",
        "menu_store": "Application Store / SHOP",
        "menu_profiles_import": "Import connection profiles...",
        "menu_profiles_export": "Export connection profiles...",
        "profiles_import_title": "Import connection profiles",
        "profiles_export_title": "Export connection profiles",
        "profiles_import_done": "Imported {count} connection profile(s). Passwords and key passphrases are not imported from portable profile files.",
        "profiles_export_done": "Exported {count} connection profile(s). Passwords and key passphrases were intentionally omitted from the portable file.",
        "profiles_import_invalid": "The selected file is not a valid Docker Control Center connection-profile export.",
        "profiles_portable_filter": "DCC connection profiles (*.json);;JSON files (*.json);;All files (*.*)",
        "menu_quit": "Exit",
        "menu_view": "View",
        "menu_fullscreen": "Full screen / restore window",
        "menu_theme": "Theme",
        "menu_lang": "Language",
        "lang_en": "English",
        "lang_pl": "Polish",
        "theme_light": "Light",
        "theme_day": "Day",
        "theme_dark": "Dark",
        "theme_black": "Black",
        "theme_night": "Night",
        "menu_info": "Info",
        "info_app": "Application info",
        "info_check_updates": "Check updates",
        "info_app_title": "Docker Control Center",
        "info_app_version": "Version: {version}",
        "info_app_repo": "Repository: {repo}",
        "info_app_latest": "Latest release: {release}",
        "info_app_latest_unknown_value": "unknown",
        "info_app_open_repo": "Open repository",
        "info_app_open_release": "Open latest release",
        "info_app_check_updates": "Check updates",
        "info_app_changelog_title": "Changelog (v1.3.8)",
        "info_app_changelog": "- Added Day and Night themes and improved GUI menu readability.\n- Kept category buttons fixed in place, moved the heading above their frame and added bottom spacing.\n- Fixed SmartWAN artwork and description overlap in the application catalog.\n- Increased application and configuration rows so their text is fully visible.\n- Expanded the application store and Repo Builder workflow.",
        "info_update_available_title": "Update available",
        "info_update_available_body": "A newer release is available: {release}.",
        "info_update_question": "Update to {release} is available. Install it now?",
        "info_update_now": "Update now",
        "info_update_later": "Remind me later",
        "info_update_cancel": "Cancel",
        "info_update_downloading": "Downloading update {release}...",
        "info_update_download_failed": "Could not download or start the update.",
        "info_update_linux_auth_title": "Linux update - password required",
        "info_update_linux_auth": "The update package has been downloaded. Linux will now open a system authorization window. Enter your user/administrator password there to allow the package installation. Docker Control Center will remain open until the installation finishes.",
        "info_update_linux_installing": "Installing the Linux update... Complete the system password prompt if it is still visible.",
        "info_update_linux_installed": "The update was installed successfully. Docker Control Center will now close. Start it again to use the new version.",
        "info_update_linux_install_failed": "The Linux update was not installed. The password prompt may have been cancelled or the package manager returned an error.",
        "info_update_no_installer": "This release does not contain an installer compatible with this operating system and architecture.",
        "info_update_none_title": "No updates",
        "info_update_none": "You are already on the latest version.",
        "info_update_check_failed": "Could not check for updates right now.",
        "menu_config": "Configure",
        "menu_llm": "LLM",
        "menu_app": "Application",
        "menu_repo_builder": "Repo Builder",
        "repo_builder_missing": "Repo Builder is not installed in this build.",
        "repo_builder_start_failed": "Could not start Repo Builder: {error}",
        "menu_reset_settings": "Reset settings to defaults...",
        "menu_factory_reset": "Factory reset...",
        "reset_settings_title": "Reset settings to defaults?",
        "reset_settings_body": "DCC application settings will return to their defaults.\n\nConnection profiles and their saved SSH passwords/passphrases will be preserved. Custom deployment repositories and cached catalog data will also remain.\n\nDCC will restart after the reset.",
        "reset_settings_done": "Settings were reset to defaults. DCC will now restart.",
        "reset_settings_action": "Reset settings",
        "factory_reset_title": "Factory reset DCC?",
        "factory_reset_body": "This will remove all local Docker Control Center data:\n\n• connection profiles and saved SSH passwords/passphrases\n• saved LLM/API credentials\n• custom deployment repositories and catalog cache\n• all application, appearance, update and LLM settings\n\nDocker containers, images, networks, volumes and data stored on Docker hosts will NOT be deleted.\n\nThis action cannot be undone. DCC will restart with factory defaults.",
        "factory_reset_done": "Factory reset completed. DCC will now restart.",
        "factory_reset_action": "Factory reset",
        "reset_cancel": "Cancel",
        "reset_failed": "The reset could not be completed: {error}",
        "reset_restart_failed": "The reset completed, but DCC could not restart automatically. Please start the application again manually.",
        "app_settings_title": "Application settings",
        "app_settings_intro": "Startup and appearance settings for local Docker integration.",
        "app_settings_autostart_dd": "Start Docker Desktop in background when DCC starts (local mode)",
        "app_settings_note": "When enabled, DCC checks local Docker at startup and launches Docker Desktop automatically if needed.",
        "app_settings_theme": "Theme",
        "app_settings_neon_animate": "Animate neon glow",
        "app_settings_neon_color": "Neon color (static)",
        "app_settings_updates_title": "Updates",
        "app_settings_auto_updates": "Automatic updates: check at startup and ask before installing",
        "app_settings_update_notifications": "Show notifications when a new version is available",
        "app_settings_check_updates": "Check for updates now",
        "info_safe_danger": "Safe vs dangerous commands",
        "menu_first_run_wizard": "First-run setup wizard",
        "menu_dependencies": "Dependencies",
        "dependencies_title": "Dependencies",
        "dependencies_intro": "Install or repair optional system components used by Docker Control Center. Status is checked on this computer each time this window is opened or refreshed.",
        "dependencies_docker_windows": "Docker Desktop",
        "dependencies_docker_linux": "Docker Engine",
        "dependencies_docker_linux_desktop": "Docker Desktop (Linux)",
        "dependencies_ssh": "OpenSSH client / SSH Agent",
        "dependencies_ready": "✓ Installed and available",
        "dependencies_installed_not_running": "Installed, but the local Docker engine is not running or is not reachable.",
        "dependencies_missing": "Not installed or not detected.",
        "dependencies_install": "Install",
        "dependencies_start": "Start",
        "dependencies_recheck": "Check again",
        "dependencies_close": "Close",
        "dependencies_auto_unavailable": "Automatic installation is unavailable on this system.",
        "dependencies_install_docker_desktop": "Install Docker Desktop",
        "dependencies_install_docker": "Install Docker",
        "dependencies_install_docker_engine": "Install Docker Engine",
        "dependencies_add_docker_group": "Add user to Docker group",
        "dependencies_docker_group_added": "\u2713 Added to Docker group",
        "dependencies_docker_group_member": "User is already assigned to the docker group.",
        "dependencies_docker_group_missing": "Docker is installed, but this user is not assigned to the docker group yet.",
        "dependencies_docker_group_session": "? Docker group is configured. This running DCC process has not inherited the permission yet. Click Connect local and choose Restart DCC with Docker access, or sign out and back in once.",
        "docker_group_relaunch_title": "Docker permission needs activation",
        "docker_group_relaunch_hint": "Your account is already in the docker group, but this running DCC process was started before that permission became active. DCC can restart itself inside the docker group now. If that does not work in this desktop session, sign out and back in once.",
        "docker_group_restart_app": "Restart DCC with Docker access",
        "docker_group_restart_failed": "DCC could not restart itself inside the docker group. Sign out and back in once, then start DCC again.",
        "dependencies_docker_group_active_no_daemon": "\u2713 Docker group permission is active, but the Docker daemon is not reachable. Check that the Docker service is running.",
        "dependencies_install_ssh": "Install SSH tools",
        "dependencies_open": "Dependencies...",
        "dependencies_install_success": "Installation completed. Dependency status will be checked again.",
        "dependencies_docker_desktop_winget_missing": "Windows Package Manager (winget) is unavailable. The official Docker Desktop download page will be opened instead.",
        "dependencies_ssh_install_title": "Installing SSH tools",
        "dependencies_ssh_install_status": "Installing OpenSSH Client and SSH Agent components...",
        "dependencies_docker_desktop_install_title": "Installing Docker Desktop",
        "dependencies_docker_desktop_install_status": "Installing Docker Desktop with Windows Package Manager...",
        "docker_desktop_linux_stopped": "Docker Desktop is installed, but it is currently stopped. Start it to manage local containers.",
        "docker_desktop_linux_missing": "Docker Desktop is not installed. You can open the official Docker Desktop for Linux installation page.",
        "docker_desktop_linux_install_opened": "The official Docker Desktop for Linux installation page was opened in your browser.",
        "docker_desktop_linux_install_failed": "Could not open the Docker Desktop for Linux installation page automatically.",
        "docker_desktop_starting": "Starting Docker Desktop and waiting for the local Docker engine...",
        "first_run_title": "Docker Control Center setup",
        "first_run_intro": "First-run setup checks this computer, Docker and portable SSH profiles.",
        "first_run_system_tab": "1. System",
        "first_run_docker_tab": "2. Docker",
        "first_run_profiles_tab": "3. SSH profiles",
        "first_run_system_detected": "Detected system: {system}",
        "first_run_docker_ready": "✓ Docker is installed and the daemon is available.",
        "first_run_docker_installed_no_access": "Docker is installed, but this user cannot access the daemon yet. Log out and back in after being added to the docker group.",
        "first_run_docker_missing": "Docker is not available on this Linux system. DCC can install the distribution package and start the service.",
        "first_run_docker_unsupported": "Automatic Docker installation is available on Debian/Ubuntu/MX and other apt-based systems. Install Docker manually on this system.",
        "first_run_install_docker": "Install Docker",
        "first_run_add_docker_group": "Add me to the Docker group",
        "first_run_docker_group_added": "\u2713 Added to Docker group",
        "first_run_recheck_docker": "Check again",
        "first_run_install_title": "Installing Docker",
        "first_run_install_status": "Installing Docker and configuring the local service...",
        "first_run_install_success": "Docker installation completed. If DCC still has no access, log out and back in once so the new docker-group membership becomes active.",
        "docker_group_auth_title": "Docker user permissions",
        "docker_group_auth_info": "The system authorization window will open. Enter your Linux account/administrator password there. DCC does not see or store this password.\n\nAfter the change completes, sign out and back in once so the new docker-group membership becomes active.",
        "docker_group_install_title": "Configuring Docker permissions",
        "docker_group_install_status": "Adding the current user to the docker group...",
        "docker_group_install_success": "The user was added to the docker group successfully. Sign out and back in once, then reopen DCC to activate Docker access.",
        "docker_group_already_member": "This user already belongs to the docker group. If Docker is still unavailable, sign out and back in once or check whether the Docker service is running.",
        "docker_group_unsupported": "Automatic docker-group configuration requires Linux with PolicyKit (pkexec).",
        "first_run_profiles_intro": "You can import connection profiles now. Passwords and key passphrases are intentionally not transferred. Key paths from another computer are cleared when they do not exist here.",
        "first_run_import_profiles": "Import profiles",
        "first_run_edit_profiles": "Edit profiles / key paths",
        "first_run_profiles_count": "Connection profiles: {count}",
        "first_run_key_paths_missing": "Profiles requiring a new SSH key path: {count}",
        "first_run_finish": "Finish setup",
        "first_run_later": "Later",
        "info_shortcuts": "Keyboard shortcuts",
        "info_shortcuts_title": "Keyboard shortcuts",
        "info_shortcuts_body": (
            "Ctrl + mouse wheel over containers  -  zoom container list\n"
            "Ctrl + 0  -  reset container list zoom to 100%\n"
            "Ctrl + F  -  focus container search\n"
            "F5  -  refresh containers\n"
            "F11  -  full screen / restore last normal window size\n"
            "Esc  -  leave full screen"
        ),
        "container_zoom_status": "Container view zoom: {percent}%",
        "info_title": "Docker Control Center",
        "btn_refresh": "Refresh",
        "btn_start": "Start",
        "btn_stop": "Stop",
        "btn_restart": "Restart",
        "btn_autostart_on": "Autostart ON",
        "btn_autostart_off": "Autostart OFF",
        "autostart_status_on": "Yes ({policy})",
        "autostart_status_off": "No",
        "autostart_status_managed": "Auto (managed)",
        "autostart_status_unknown": "N/A",
        "btn_remove": "Remove",
        "btn_logs": "Logs",
        "btn_new": "New container",
        "btn_shop_short": "+ SHOP",
        "btn_edit_start": "Edit start",
        "btn_pause": "Pause",
        "btn_unpause": "Unpause",
        "btn_start_profile": "Start profile",
        "btn_profiles": "Connection profiles",
        "btn_ssh_terminal": "SSH terminal",
        "btn_local_info": "Local INFO",
        "infra_unknown": "Infrastructure: unknown",
        "infra_local_label": "Infrastructure: Local host ({os} | {arch})",
        "infra_local_fallback": "Infrastructure: Docker Desktop",
        "infra_local_wsl": "Infrastructure: WSL ({distro})",
        "infra_remote_label": "Infrastructure: Remote host ({os} | {arch})",
        "infra_remote_tunnel": "Infrastructure: Remote tunnel",
        "infra_terminal_tooltip": "Click to open the host terminal",
        "btn_host_restart": "Restart host",
        "host_status_running": "Host is reachable",
        "host_status_off": "Host is offline",
        "host_restart_title": "Restart host?",
        "host_restart_body": "This will restart the current host. Continue?",
        "host_restart_sent": "Restart command sent to the host.",
        "host_restart_probable": "SSH connection dropped after the restart command. The host is probably restarting.",
        "host_restart_in_progress": "Restart requested. Waiting for the host to come back online...",
        "host_restart_checking": "Checking connection to {name}... attempt {attempt}",
        "host_restart_waiting_retry": "Host is still restarting. Next connection check will run automatically.",
        "host_restart_engine_ready": "Host is reachable again. Refreshing the container list...",
        "host_restart_recovered": "Connection restored. The container list has been refreshed.",
        "host_restart_timeout": "The host did not come back online within 5 minutes. Automatic checks were stopped.",
        "host_restart_cancel_checks": "Cancel checks",
        "host_restart_cancelled": "Automatic connection checks cancelled.",
        "host_restart_notice_title": "Host restart",
        "host_restart_failed": "Could not restart the host with the available commands.",
        "host_metrics_unknown": "Host/containers load: unavailable",
        "host_metrics_format": "Host CPU {host_cpu:.1f}% | RAM {host_mem} / {host_total} ({host_mem_pct:.1f}%) | Containers CPU {container_cpu:.1f}% | RAM {container_mem}",
        "container_metrics_format": "Containers CPU {container_cpu:.1f}% | RAM {container_mem}",
        "local_profiles_wsl_command": "WSL quick test (selected distro): wsl -d {distro} sh -lc \"docker ps\"",        "btn_transparency_on": "Transparency: ON",
        "btn_transparency_off": "Transparency: OFF",
        "transparency_level": "Glass level",
        "btn_music_on": "Music: ON",
        "btn_music_off": "Music: OFF",
        "music_missing": "bg.mp3 was not found next to the application.",
        "music_unavailable": "PyQt6 audio module is not available. Install PyQt6 multimedia support.",
        "hero_title": "DCC | DOCKER CONTROL CENTER",
        "hero_subtitle": "Professional control center for local Docker, WSL and remote SSH hosts with ready deployment presets.",
        "hero_subtitle_linux": "Professional control center for the local Docker Engine and remote SSH / Balena hosts with ready deployment presets.",
        "profile_label": "Remote profile",
        "profile_name": "Profile name",
        "profile_mode": "Connection mode",
        "profile_ssh_target": "SSH target (user@host)",
        "profile_ssh_port": "SSH port",
        "profile_auth_mode": "SSH authentication",
        "profile_auth_key": "SSH key",
        "profile_auth_both": "SSH key + passphrase",
        "profile_auth_agent": "SSH Agent",
        "profile_auth_password": "Login and password",
        "profile_key_path": "SSH key file (optional)",
        "profile_key_browse": "Change key path",
        "profile_key_path_ok": "SSH key file is available on this computer.",
        "profile_key_path_missing": "This profile needs an SSH key path valid on this computer. Copy the key here, then choose it with 'Change key path'.",
        "profiles_import_key_paths": "{count} imported profile(s) require selecting a new SSH key path on this computer.",
        "profile_passphrase": "Key passphrase",
        "profile_passphrase_note": "Use this when your SSH key is protected with a passphrase (SenseCap M1).",
        "profile_key_path_required_passphrase": "Select an SSH key file for key passphrase mode.",
        "profile_password": "SSH password",
        "profile_password_note": "The password is stored in the local secret store for your user account. Use it only on a trusted computer.",
        "profile_base_url": "Docker URL",
        "profile_tunnel_command": "Tunnel command",
        "profile_wait": "Wait after start (s)",
        "profile_add": "Add",
        "profile_copy": "Copy",
        "profile_copy_suffix": "copy",
        "profile_save": "Save",
        "profile_delete": "Delete",
        "profile_tutorial": "Host setup guide",
        "profile_dialog_title": "Remote connection profiles",
        "profile_saved": "Profile saved.",
        "profile_deleted": "Profile deleted.",
        "profile_missing_name": "Profile name is required.",
        "profile_missing_target": "For SSH mode, enter user@host or provide a valid Docker URL.",
        "profile_mode_ssh": "Direct SSH",
        "profile_mode_tunnel": "TCP tunnel",
        "profile_starting": "Starting connection for profile: {name}",
        "profile_connecting": "Connecting to profile: {name}",
        "profile_connected": "Connected to profile: {name}",
        "profile_no_profiles": "No remote profiles available. Add a connection profile.",
        "profile_file_error": "Could not save the profiles file.",
        "profile_started": "Connection started. Connecting in a moment...",
        "profile_tutorial_title": "Remote Docker host guide",
        "profile_tutorial_intro": "Steps for a new Docker device:",
        "profile_tutorial_hint": "You can use an SSH key or login and password. Keep tunnel mode as a fallback. If the host runs Balena OS, use balena ps / balena run - DCC will auto-detect.",
        "profile_tutorial_agent_windows": "SSH key in Windows (optional, run PowerShell as Administrator):\n1) Get-Service ssh-agent | Set-Service -StartupType Automatic  - set ssh-agent to start automatically\n2) Start-Service ssh-agent  - start the agent now\n3) ssh-add C:\\Users\\Kosmo\\.ssh\\your_key_name  - add your private key to the agent",
        "profile_tutorial_agent_linux": "SSH key in Linux (optional):\n1) eval \"$(ssh-agent -s)\"  - start ssh-agent for the session\n2) ssh-add ~/.ssh/your_key_name  - add your private key\n3) ssh-add -l  - list loaded keys",
        "profile_tutorial_test": "Test (Docker): ssh -p {port} {target} docker ps\nTest (Balena OS): ssh -p {port} {target} balena ps",
        "profile_tutorial_steps": (
            "1. Install Docker on the remote device.\n"
            "2. Add the user to the docker group: sudo usermod -aG docker {user}\n"
            "3. Log in again on the host.\n"
            "4. Verify locally on the host: docker ps\n"
            "5. Configure an SSH key or prepare login and password for the GUI.\n"
            "6. In the GUI choose Direct SSH mode and enter {target} and port {port}."
        ),
        "col_select": "",
        "col_status_icon": "",
        "col_name": "Name",
        "col_image": "Image",
        "col_status": "Status",
        "col_ports": "Ports",
        "col_cpu": "CPU",
        "col_memory": "RAM",
        "col_links": "Web / Links",
        "col_project": "Project",
        "col_networks": "Networks",
        "col_autostart": "Autostart",
        "select_all": "Select all",
        "column_magnet": "Magnet",
        "column_magnet_tooltip": "Keep the manually set column proportions and fit them to the table width when the window is resized.",
        "container_search_placeholder": "Search containers by name...",
        "group_by_label": "Group",
        "group_by_project": "Projects",
        "group_by_network": "Networks",
        "group_by_none": "Flat list",
        "group_project_prefix": "Project",
        "group_network_prefix": "Network",
        "group_standalone": "Standalone containers",
        "group_no_network": "No network",
        "group_summary": "{count} containers · {running} running · networks: {networks}",
        "group_display_expand": "Expand group",
        "group_display_collapse": "Collapse group",
        "group_select_all": "Select all containers in this group",
        "controls_connection": "CONNECTIONS",
        "controls_containers": "CONTAINERS",
        "controls_view": "VIEW & HOST",
        "btn_more_actions": "More actions ▾",
        "status_ready": "Ready",
        "status_loading": "Loading containers...",
        "status_local_connected": "Connected to local Docker",
        "engine_docker": "Detected engine: Docker",
        "engine_balena": "Detected engine: Balena OS",
        "engine_unknown": "Detected engine: Unknown",
        "status_wsl_connected": "Connected to Docker in WSL: {distro}",
        "msg_no_selection": "No containers selected.",
        "msg_confirm_remove": "Remove selected containers? This will delete their data.",
        "msg_error": "Error",
        "msg_info": "Information",
        "msg_action_blocked": "Action blocked",
        "autostart_enable_title": "Enable autostart?",
        "autostart_disable_title": "Disable autostart?",
        "autostart_enable_confirm": "This will set the Docker restart policy to unless-stopped. The container will keep its data and settings, but after a system or Docker restart it will start automatically unless it was explicitly stopped. Continue?",
        "autostart_disable_confirm": "This will set the Docker restart policy to no. The container will keep its data and settings, but after a system or Docker restart it will not start automatically. Continue?",
        "logs_title": "Logs: {name}",
        "logs_loading": "Loading logs...",
        "wizard_title": "Docker deployment catalog",
        "wizard_store_subtitle": "Application store for the currently selected Docker host",
        "wizard_target_host": "Target host: {host}",
        "wizard_repositories": "Repositories",
        "wizard_repo_title": "Deployment catalog repositories",
        "wizard_repo_intro": "Add a JSON catalog URL or a GitHub repository containing dcc-catalog.json / catalog.json.",
        "wizard_repo_primary": "Main DCC catalog · automatic",
        "wizard_repo_primary_hint": "The main DCC catalog is built into the application and cannot be removed. Add optional repositories below it.",
        "wizard_repo_url": "Repository or catalog URL",
        "wizard_repo_add": "Add",
        "wizard_repo_remove": "Remove",
        "wizard_repo_open": "Open",
        "wizard_repo_refresh": "Refresh catalogs",
        "wizard_repo_syncing": "Updating application catalogs...",
        "wizard_repo_status_cached": "Catalog cache ready",
        "wizard_repo_status_updated": "Catalog updated · {count} apps from repositories",
        "wizard_repo_status_partial": "Catalog updated from cache · {count} apps · some repositories unavailable",
        "wizard_repo_invalid": "Could not load this deployment repository.",
        "wizard_repo_loaded": "Loaded {count} application(s) from external repositories.",
        "wizard_repo_errors": "Some repositories could not be loaded:\n{errors}",
        "wizard_source": "Source",
        "wizard_docs": "Documentation",
        "wizard_homepage": "Website",
        "wizard_quick_deploy": "Deploy selected app",
        "wizard_store_tab": "Description",
        "wizard_store_install": "Install",
        "wizard_store_uninstall": "Uninstall",
        "wizard_store_installed": "Installed on this host",
        "wizard_store_not_installed": "Not installed on this host",
        "wizard_store_features": "Highlights",
        "wizard_store_gallery": "Gallery",
        "wizard_store_requirements": "Requirements",
        "wizard_store_categories": "Categories",
        "wizard_store_apps": "Applications",
        "wizard_store_no_media": "No preview image supplied by the catalog.",
        "wizard_store_uninstall_title": "Uninstall application?",
        "wizard_store_uninstall_confirm": "DCC found {count} matching container(s):\n\n{names}\n\nThe containers will be removed. Named volumes and bind-mounted data are not deleted automatically, but data stored only in the writable container layer can be lost. Continue?",
        "wizard_store_uninstall_done": "Application container(s) removed.",
        "wizard_balena_category": "Balena OS",
        "wizard_installed_category": "Installed",
        "wizard_credentials_title": "Access details detected",
        "wizard_credentials_intro": "DCC found the following access details in the container startup logs. They are shown here only and are not saved by DCC:",
        "wizard_credentials_none": "Deployment completed. No login credentials were detected in the startup logs.",
        "wizard_auto_fix": "Automatically resolve safe name and host-port conflicts",
        "wizard_ai_fallback": "Use AI only if deterministic repair cannot solve the failure",
        "wizard_safe_changes_title": "Safe deployment adjustments",
        "wizard_safe_changes_body": "DCC found conflicts and can apply these safe changes:\n\n{changes}\n\nApply them and continue?",
        "wizard_safe_name_change": "Container name: {old} -> {new}",
        "wizard_safe_port_change": "Host port: {old} -> {new}",
        "wizard_model_fallback": "Configured model '{old}' is not installed. Using '{new}'.",
        "wizard_arch_unsupported": "This application does not declare support for host architecture: {arch}.",
        "wizard_risky_title": "Review elevated container access",
        "wizard_risky_body": "This deployment requests elevated host access:\n\n{risks}\n\nReview the project source/documentation before continuing. Deploy anyway?",
        "wizard_edit_title": "Edit container start",
        "wizard_catalog": "Image catalog",
        "wizard_search": "Search image or description",
        "wizard_category": "Category",
        "wizard_catalog_count": "{count} apps",
        "wizard_pick_image": "Choose a preset image",
        "wizard_manual": "Manual configuration",
        "wizard_manual_title": "Custom container configuration",
        "wizard_manual_description": "Enter the image, ports, parameters and command manually, or paste a docker run command below.",
        "wizard_current_container_title": "Container: {name}",
        "wizard_current_container_description": "Current image: {image}",
        "wizard_latest_release": "Latest upstream release: {version}",
        "wizard_all_categories": "All",
        "wizard_name": "Container name (e.g. my-app)",
        "wizard_image": "Image (e.g. ghcr.io/open-webui/open-webui:main)",
        "wizard_cport": "Container port (e.g. 8080)",
        "wizard_hport": "Host port (blank = same as container)",
        "wizard_extra": "Extra parameters (e.g. -e KEY=VAL -v host:cont)",
        "wizard_command_only": "Container start command (optional)",
        "wizard_cli": "Command engine",
        "wizard_command_input": "Paste docker run (single line or multiline; it will be normalized)",
        "wizard_parse": "Fill from command",
        "wizard_normalize": "Normalize command",
        "wizard_ai_button": "Configure with AI",
        "wizard_setup_tab": "Container setup",
        "wizard_ai_tab": "AI assistant",
        "llm_title": "LLM configuration",
        "llm_provider": "Provider",
        "llm_provider_ollama": "Local Ollama",
        "llm_provider_openai": "OpenAI",
        "llm_provider_anthropic": "Anthropic Claude",
        "llm_provider_gemini": "Google Gemini",
        "llm_provider_groq": "Groq",
        "llm_provider_mistral": "Mistral AI",
        "llm_provider_openrouter": "OpenRouter",
        "llm_provider_deepseek": "DeepSeek",
        "llm_provider_xai": "xAI Grok",
        "llm_ollama_url": "Ollama URL",
        "llm_model": "Model",
        "llm_openai_key": "OpenAI API key",
        "llm_api_key": "API key",
        "llm_detect": "Detect models",
        "llm_save": "Save",
        "llm_close": "Close",
        "llm_models_ready": "Models loaded.",
        "llm_models_failed": "Could not load models.",
        "llm_api_key_missing": "Enter the {provider} API key in Configure -> LLM.",
        "llm_prompt_placeholder": "Describe how the docker run command should be modified. Example: Mount D:/Music from Windows 11 to /data/music in Jellyfin as read-only and keep everything in one line.",
        "llm_generate": "Generate command",
        "llm_apply": "Apply this command",
        "llm_status_idle": "Ready for AI suggestions.",
        "llm_status_working": "Generating a docker run command with AI...",
        "llm_status_done": "AI proposed a new docker run command.",
        "llm_status_error": "AI request failed.",
        "llm_result": "AI result command",
        "llm_request": "What do you want to change?",
        "llm_context": "Current docker run context",
        "llm_use_saved": "Provider settings are taken from Configure -> LLM.",
        "llm_refresh_models": "Refresh models",
        "llm_response_invalid": "The model did not return a valid docker run command.",
        "llm_apply_done": "The AI command was applied to the form.",
        "llm_prompt_required": "Describe what you want to change in the docker run command.",
        "wizard_notes": "Description and hints",
        "wizard_online_refresh": "Refresh online descriptions",
        "wizard_catalog_loading": "Fetching image details...",
        "wizard_catalog_loaded": "Image description updated from Docker Hub.",
        "wizard_command_invalid": "Could not parse the docker run command.",
        "wizard_balena_notice": "Balena OS detected. This docker run will be executed as 'balena run'.",
        "wizard_balena_only": "Balena OS detected. DCC will use balena run/balena ps. Use Balena-compatible images only.",
        "wizard_port_in_use": "Port {port} is already used by: {users}. Choose another port.",
        "wizard_summary": "Command to run:",
        "wizard_run": "Run container",
        "wizard_apply": "Apply start",
        "wizard_cancel": "Cancel",
        "wizard_done": "Deployment completed and the container was verified.",
        "wizard_recreate_title": "Recreate container?",
        "wizard_recreate_confirm": "The container will be stopped, removed and created again with the new docker run parameters.\n\nData in bind mounts and named volumes will stay intact if you keep the same mount paths. Data stored only inside the container filesystem may be lost.\n\nContinue?",
        "wizard_recreate_done": "Container was recreated with the new start parameters.",
        "wizard_select_one_edit": "Select one container to edit its start configuration.",
        "progress_title_create": "Container deployment",
        "progress_title_recreate": "Container recreation",
        "progress_status_create": "Container deployment in progress...",
        "progress_status_build_source": "{name}: step 1/2 - building a local Docker image from the source repository...",
        "progress_status_recreate": "Recreating container with new start parameters...",
        "progress_status_done": "SUCCESS — deployment completed.",
        "progress_status_failed": "FAILED — deployment did not complete.",
        "progress_elapsed": "Elapsed: {seconds}s",
        "progress_copy_log": "Copy log",
        "progress_log_copied": "Log copied.",
        "progress_verify_start": "Verifying the deployed container...",
        "progress_verify_found": "Verification OK: {name} exists (status: {status}).",
        "progress_verify_missing": "Verification failed: container {name} was not found after deployment.",
        "progress_ssh_verified": "Detached container {id} was created and verified on the remote host.",
        "progress_close": "Close",
        "command_copy": "Copy command",
        "command_run": "Run command",
        "exec_shell_title": "Exec shell",
        "exec_shell_intro_local": "This command opens an interactive shell inside the selected container on the local Docker engine.",
        "exec_shell_intro_wsl": "This command opens an interactive shell inside the selected container through WSL distribution: {target}.",
        "exec_shell_intro_remote_ssh": "This command opens an interactive shell inside the selected container on remote host: {target}.",
        "exec_shell_intro_remote_tunnel": "This command opens an interactive shell inside the selected container through the configured Docker tunnel.",
        "docker_not_available": "Docker connection unavailable. Is Docker Desktop or the remote host running?",
        "docker_local_unavailable_title": "Local Docker is unavailable",
        "docker_local_unavailable_hint": "No local Docker engine is reachable. You can install or start the required Docker runtime here, then retry the local connection.",
        "docker_local_unavailable_hint_linux": "The local Docker Engine is not reachable from DCC. DCC follows DOCKER_HOST and the active Docker CLI context (including Docker Desktop/rootless sockets), then falls back to the system Docker socket.",
        "docker_local_endpoint_detected": "Detected Docker endpoint: {context} -> {endpoint}",
        "docker_local_open_desktop": "Start Docker Desktop",
        "docker_local_install_desktop": "Install Docker Desktop",
        "docker_local_install_docker": "Install Docker",
        "docker_local_open_failed": "Could not start Docker Desktop automatically. Start it manually and try again.",
        "local_client": "Connect local",
        "btn_local_profiles": "Local INFO",
        "btn_wsl_profile": "Local WSL",
        "btn_wsl_refresh": "Detect WSL",
        "wsl_label": "WSL",
        "wsl_none": "No WSL distributions",
        "wsl_detect_error": "Could not retrieve the WSL distribution list. Run the application with WSL access or verify that the WSL service is working.",
        "wsl_connect_error": "Could not connect to Docker in WSL. Make sure Docker is running in the selected distribution.",
        "wsl_help_title": "WSL / WSL2 Docker",
        "wsl_help_text": "Detected distribution: {distro}\n\nGUI connection options:\n1. Easiest: Docker Desktop with WSL integration and the Connect local button.\n2. Click Local WSL to manage Docker running directly in this distribution.\n3. SSH profile: run OpenSSH in WSL and connect using an SSH profile.\n4. Tunnel profile: expose the Docker socket from WSL over TCP and connect using a tunnel profile.\n\nQuick terminal test:\nwsl -d {distro} sh -lc \"docker ps\"",
        "local_profiles_text": "Local profiles for beginners:\n\n1. Local containers\nUse this when Docker Desktop or a local daemon is running on Windows.\nCheck: PowerShell -> docker ps\n\n2. Local WSL\nUse this when Docker runs directly in Ubuntu, Debian, Kali or another WSL2 distribution.\nCheck: PowerShell -> wsl -d Ubuntu sh -lc \"docker ps\"\n\nHow to add a container:\n- click New container\n- choose a preset image or paste a docker run command\n- review the summary and run it\n\nWhich mode to use:\n- Windows / Docker Desktop: Connect local\n- WSL2 with its own dockerd: Local WSL\n- Raspberry Pi / server / NAS: Start profile through SSH or tunnel",
        "local_profiles_text_linux": "Linux connection modes for beginners:\n\n1. Local Docker Engine\nUse Connect local to manage Docker running directly on this Linux computer.\nCheck in a terminal: docker ps\n\nIf DCC has just added your account to the docker group, use the offered DCC restart with Docker access or sign out and back in once.\n\n2. Remote Linux / Balena / Raspberry Pi / server / NAS\nCreate an SSH profile and start that profile to manage Docker remotely.\n\nHow to add a container:\n- click New container\n- choose a preset image or paste a docker run command\n- review the summary and run it",
        "remote_hint": "Local, WSL and remote Docker engines in one operator panel.",
        "remote_hint_linux": "Local Linux Docker Engine and remote SSH / Balena Docker hosts in one operator panel.",
        "remote_sysinfo_label": "Remote host: {os} | {arch}",
        "remote_sysinfo_unknown": "Remote host: unknown",
        "remote_sysinfo_fetch_failed": "Remote host: unavailable",
        "ssh_terminal_unavailable": "SSH terminal is available only for Direct SSH profiles.",
        "ssh_terminal_tunnel": "SSH terminal is not available for tunnel profiles.",
        "ctx_start": "Start",
        "ctx_stop": "Stop",
        "ctx_restart": "Restart",
        "ctx_autostart_on": "Autostart ON",
        "ctx_autostart_off": "Autostart OFF",
        "ctx_pause": "Pause",
        "ctx_unpause": "Unpause",
        "ctx_logs": "Logs",
        "ctx_inspect": "Inspect",
        "ctx_exec": "Exec shell",
        "ctx_edit_start": "Edit start",
        "ctx_open_link": "Open link",
        "ctx_copy_link": "Copy link",
        "link_local": "Local",
        "link_device": "Device",
        "link_lan": "LAN",
        "ctx_remove": "Remove"
        ,"ctx_lifecycle": "Lifecycle"
        ,"ctx_configuration": "Configuration"
        ,"ctx_diagnostics": "Diagnostics"
        ,"ctx_links": "Web links"
        ,"ctx_actual_data": "Actual container data"
        ,"ctx_copy_details": "Copy technical details"
        ,"ctx_copy_ports": "Copy published ports"
        ,"ctx_copy_networks": "Copy networks"
        ,"ctx_project": "Project: {project}"
        ,"ctx_networks": "Networks: {networks}"
        ,"ctx_ports": "Published ports: {ports}"
        ,"ctx_mounts": "Mounts: {count}"
        ,"ctx_cached_data_missing": "Container data is no longer available. Refresh the list."
    },
    "PL": {
        "app_title": "Docker Control Center",
        "menu_file": "Plik",
        "menu_store": "Sklep aplikacji / SKLEP",
        "menu_profiles_import": "Importuj profile połączeń...",
        "menu_profiles_export": "Eksportuj profile połączeń...",
        "profiles_import_title": "Import profili połączeń",
        "profiles_export_title": "Eksport profili połączeń",
        "profiles_import_done": "Zaimportowano profile połączeń: {count}. Hasła i hasła do kluczy nie są importowane z przenośnych plików profili.",
        "profiles_export_done": "Wyeksportowano profile połączeń: {count}. Hasła i hasła do kluczy zostały celowo pominięte w przenośnym pliku.",
        "profiles_import_invalid": "Wybrany plik nie jest prawidłowym eksportem profili połączeń Docker Control Center.",
        "profiles_portable_filter": "Profile połączeń DCC (*.json);;Pliki JSON (*.json);;Wszystkie pliki (*.*)",
        "menu_quit": "Wyjście",
        "menu_view": "Widok",
        "menu_fullscreen": "Pełny ekran / przywróć okno",
        "menu_theme": "Motyw",
        "menu_lang": "Język",
        "lang_en": "Angielski",
        "lang_pl": "Polski",
        "theme_light": "Jasny",
        "theme_day": "Day",
        "theme_dark": "Ciemny",
        "theme_black": "Czarny",
        "theme_night": "Noc",
        "menu_info": "Informacje",
        "info_app": "Informacje o aplikacji",
        "info_check_updates": "Sprawdź aktualizacje",
        "info_app_title": "Docker Control Center",
        "info_app_version": "Wersja: {version}",
        "info_app_repo": "Repozytorium: {repo}",
        "info_app_latest": "Najnowsze wydanie: {release}",
        "info_app_latest_unknown_value": "nieznany",
        "info_app_open_repo": "Otwórz repozytorium",
        "info_app_open_release": "Otwórz najnowsze wydanie",
        "info_app_check_updates": "Sprawdź aktualizacje",
        "info_app_changelog_title": "Changelog (v1.3.8)",
        "info_app_changelog": "- Dodano motywy Day i Noc oraz poprawiono czytelność menu GUI.\n- Przyciski kategorii są nieruchome, nagłówek przeniesiono nad ramkę i dodano dolny odstęp.\n- Poprawiono nakładanie grafiki SmartWAN i opisu w katalogu aplikacji.\n- Zwiększono wysokość kart aplikacji i pól konfiguracji, aby tekst nie był ucinany.\n- Rozbudowano sklep aplikacji i Repo Builder.",
        "info_update_available_title": "Dostępna aktualizacja",
        "info_update_available_body": "Dostępna jest nowsza wersja: {release}.",
        "info_update_question": "Dostępna jest aktualizacja do wersji {release}. Czy wykonać ja teraz?",
        "info_update_now": "Aktualizuj teraz",
        "info_update_later": "Przypomnij później",
        "info_update_cancel": "Anuluj",
        "info_update_downloading": "Pobieranie aktualizacji {release}...",
        "info_update_download_failed": "Nie udało się pobrać lub uruchomić aktualizacji.",
        "info_update_linux_auth_title": "Aktualizacja Linux - wymagane hasło",
        "info_update_linux_auth": "Pakiet aktualizacji został pobrany. Linux otworzy teraz systemowe okno uwierzytelnienia. Wpisz w nim hasło swojego konta/użytkownika administratora, aby zezwolić na instalację pakietu. Docker Control Center pozostanie uruchomiony aż do zakończenia instalacji.",
        "info_update_linux_installing": "Instalowanie aktualizacji Linux... Jeśli okno hasła jest nadal widoczne, wpisz hasło i zatwierdź.",
        "info_update_linux_installed": "Aktualizacja została zainstalowana poprawnie. Docker Control Center zostanie teraz zamknięty. Uruchom aplikację ponownie, aby korzystać z nowej wersji.",
        "info_update_linux_install_failed": "Aktualizacja Linux nie została zainstalowana. Okno hasła mogło zostać anulowane albo menedżer pakietów zwrócił błąd.",
        "info_update_no_installer": "Ta wersja nie zawiera instalatora zgodnego z tym systemem operacyjnym i architekturą.",
        "info_update_none_title": "Brak aktualizacji",
        "info_update_none": "Masz najnowszą wersję.",
        "info_update_check_failed": "Nie udało się sprawdzic aktualizacji.",
        "menu_config": "Konfiguruj",
        "menu_llm": "LLM",
        "menu_app": "Aplikacja",
        "menu_repo_builder": "Repo Builder",
        "repo_builder_missing": "Repo Builder nie jest zainstalowany w tej kompilacji.",
        "repo_builder_start_failed": "Nie udało się uruchomić Repo Buildera: {error}",
        "menu_reset_settings": "Resetuj ustawienia do domyślnych...",
        "menu_factory_reset": "Reset do ustawień fabrycznych...",
        "reset_settings_title": "Zresetować ustawienia do domyślnych?",
        "reset_settings_body": "Ustawienia aplikacji DCC wrócą do wartości domyślnych.\n\nProfile połączeń oraz zapisane hasła SSH i hasła do kluczy zostaną zachowane. Własne repozytoria wdrożeń i pamięć podręczna katalogu również pozostaną.\n\nPo resecie DCC uruchomi się ponownie.",
        "reset_settings_done": "Ustawienia zostały przywrócone do domyślnych. DCC uruchomi się ponownie.",
        "reset_settings_action": "Resetuj ustawienia",
        "factory_reset_title": "Przywrócić ustawienia fabryczne DCC?",
        "factory_reset_body": "To usunie wszystkie lokalne dane Docker Control Center:\n\n• profile połączeń i zapisane hasła SSH / hasła do kluczy\n• zapisane dane LLM i klucze API\n• własne repozytoria wdrożeń i pamięć podręczną katalogu\n• wszystkie ustawienia aplikacji, wyglądu, aktualizacji i LLM\n\nKontenery, obrazy, sieci, wolumeny ani dane znajdujące się na hostach Docker NIE zostaną usunięte.\n\nTej operacji nie można cofnąć. DCC uruchomi się ponownie z ustawieniami fabrycznymi.",
        "factory_reset_done": "Reset fabryczny zakończony. DCC uruchomi się ponownie.",
        "factory_reset_action": "Reset fabryczny",
        "reset_cancel": "Anuluj",
        "reset_failed": "Nie udało się wykonać resetu: {error}",
        "reset_restart_failed": "Reset został wykonany, ale DCC nie udało się uruchomić automatycznie ponownie. Uruchom aplikację ręcznie.",
        "app_settings_title": "Ustawienia aplikacji",
        "app_settings_intro": "Ustawienia startowe i wyglądu dla lokalnej integracji z Docker.",
        "app_settings_autostart_dd": "Uruchamiaj Docker Desktop w tle przy starcie DCC (tryb lokalny)",
        "app_settings_note": "Po włączeniu DCC sprawdza lokalny Docker przy starcie i automatycznie uruchamia Docker Desktop, jeśli potrzeba.",
        "app_settings_theme": "Motyw",
        "app_settings_neon_animate": "Animuj neon",
        "app_settings_neon_color": "Kolor neonu (stały)",
        "app_settings_updates_title": "Aktualizacje",
        "app_settings_auto_updates": "Automatyczne aktualizacje: sprawdzaj przy starcie i pytaj przed instalacją",
        "app_settings_update_notifications": "Pokazuj powiadomienia o dostępnej nowej wersji",
        "app_settings_check_updates": "Sprawdź aktualizacje teraz",
        "info_safe_danger": "Bezpieczne vs niebezpieczne komendy",
        "menu_first_run_wizard": "Kreator pierwszego uruchomienia",
        "menu_dependencies": "Zależności",
        "dependencies_title": "Zależności",
        "dependencies_intro": "Zainstaluj lub napraw opcjonalne składniki systemowe używane przez Docker Control Center. Stan jest sprawdzany na tym komputerze przy każdym otwarciu lub odświeżeniu okna.",
        "dependencies_docker_windows": "Docker Desktop",
        "dependencies_docker_linux": "Docker Engine",
        "dependencies_docker_linux_desktop": "Docker Desktop (Linux)",
        "dependencies_ssh": "Klient OpenSSH / Agent SSH",
        "dependencies_ready": "✓ Zainstalowane i dostępne",
        "dependencies_installed_not_running": "Zainstalowane, ale lokalny silnik Docker nie działa lub jest niedostępny.",
        "dependencies_missing": "Nie zainstalowano lub nie wykryto.",
        "dependencies_install": "Zainstaluj",
        "dependencies_start": "Uruchom",
        "dependencies_recheck": "Sprawdź ponownie",
        "dependencies_close": "Zamknij",
        "dependencies_auto_unavailable": "Automatyczna instalacja nie jest dostępna w tym systemie.",
        "dependencies_install_docker_desktop": "Zainstaluj Docker Desktop",
        "dependencies_install_docker": "Zainstaluj Docker",
        "dependencies_install_docker_engine": "Zainstaluj Docker Engine",
        "dependencies_add_docker_group": "Dodaj użytkownika do grupy Docker",
        "dependencies_docker_group_added": "\u2713 Dodano do grupy Docker",
        "dependencies_docker_group_member": "Użytkownik jest już przypisany do grupy docker.",
        "dependencies_docker_group_missing": "Docker jest zainstalowany, ale ten użytkownik nie jest jeszcze przypisany do grupy docker.",
        "dependencies_docker_group_session": "\u2713 Grupa docker jest skonfigurowana. Uruchomiony proces DCC nie odziedziczy\u0142 jeszcze tego uprawnienia. Kliknij Po\u0142\u0105cz lokalnie i wybierz Uruchom DCC ponownie z dost\u0119pem do Docker albo wyloguj si\u0119 i zaloguj ponownie jeden raz.",
        "docker_group_relaunch_title": "Trzeba aktywowa\u0107 uprawnienie Docker",
        "docker_group_relaunch_hint": "Twoje konto jest ju\u017c w grupie docker, ale uruchomiony proces DCC wystartowa\u0142 zanim to uprawnienie sta\u0142o si\u0119 aktywne. DCC mo\u017ce teraz uruchomi\u0107 si\u0119 ponownie wewn\u0105trz grupy docker. Je\u017celi ta metoda nie zadzia\u0142a w tej sesji pulpitu, wyloguj si\u0119 i zaloguj ponownie jeden raz.",
        "docker_group_restart_app": "Uruchom DCC ponownie z dost\u0119pem do Docker",
        "docker_group_restart_failed": "Nie uda\u0142o si\u0119 uruchomi\u0107 DCC ponownie wewn\u0105trz grupy docker. Wyloguj si\u0119 i zaloguj ponownie jeden raz, a nast\u0119pnie uruchom DCC.",
        "dependencies_docker_group_active_no_daemon": "\u2713 Uprawnienie grupy docker jest aktywne, ale demon Docker jest niedost\u0119pny. Sprawd\u017a, czy us\u0142uga Docker jest uruchomiona.",
        "dependencies_install_ssh": "Zainstaluj narzędzia SSH",
        "dependencies_open": "Zależności...",
        "dependencies_install_success": "Instalacja zakończona. Stan zależności zostanie sprawdzony ponownie.",
        "dependencies_docker_desktop_winget_missing": "Menedżer pakietów Windows (winget) jest niedostępny. Zamiast tego zostanie otwarta oficjalna strona pobierania Docker Desktop.",
        "dependencies_ssh_install_title": "Instalacja narzędzi SSH",
        "dependencies_ssh_install_status": "Instalowanie składników OpenSSH Client i Agenta SSH...",
        "dependencies_docker_desktop_install_title": "Instalacja Docker Desktop",
        "dependencies_docker_desktop_install_status": "Instalowanie Docker Desktop przez Menedżer pakietów Windows...",
        "docker_desktop_linux_stopped": "Docker Desktop jest zainstalowany, ale obecnie jest wyłączony. Uruchom go, aby zarządzać lokalnymi kontenerami.",
        "docker_desktop_linux_missing": "Docker Desktop nie jest zainstalowany. Możesz otworzyć oficjalną stronę instalacji Docker Desktop dla Linux.",
        "docker_desktop_linux_install_opened": "Otworzono w przeglądarce oficjalną stronę instalacji Docker Desktop dla Linux.",
        "docker_desktop_linux_install_failed": "Nie udało się automatycznie otworzyć strony instalacji Docker Desktop dla Linux.",
        "docker_desktop_starting": "Uruchamianie Docker Desktop i oczekiwanie na lokalny silnik Docker...",
        "first_run_title": "Konfiguracja Docker Control Center",
        "first_run_intro": "Kreator pierwszego uruchomienia sprawdza ten komputer, Docker oraz przenośne profile SSH.",
        "first_run_system_tab": "1. System",
        "first_run_docker_tab": "2. Docker",
        "first_run_profiles_tab": "3. Profile SSH",
        "first_run_system_detected": "Wykryty system: {system}",
        "first_run_docker_ready": "✓ Docker jest zainstalowany i demon jest dostępny.",
        "first_run_docker_installed_no_access": "Docker jest zainstalowany, ale ten użytkownik nie ma jeszcze dostępu do demona. Po dodaniu do grupy docker wyloguj się i zaloguj ponownie do sesji.",
        "first_run_docker_missing": "Docker nie jest dostępny w tym systemie Linux. DCC może zainstalować pakiet dystrybucji i uruchomić usługę.",
        "first_run_docker_unsupported": "Automatyczna instalacja Dockera jest dostępna dla Debian/Ubuntu/MX i innych systemów opartych na apt. W tym systemie zainstaluj Docker ręcznie.",
        "first_run_install_docker": "Zainstaluj Docker",
        "first_run_add_docker_group": "Dodaj mnie do grupy Docker",
        "first_run_docker_group_added": "\u2713 Dodano do grupy Docker",
        "first_run_recheck_docker": "Sprawdź ponownie",
        "first_run_install_title": "Instalacja Dockera",
        "first_run_install_status": "Instalowanie Dockera i konfigurowanie lokalnej usługi...",
        "first_run_install_success": "Instalacja Dockera zakończona. Jeżeli DCC nadal nie ma dostępu, wyloguj się i zaloguj ponownie jeden raz, aby aktywować członkostwo w grupie docker.",
        "docker_group_auth_title": "Uprawnienia użytkownika Docker",
        "docker_group_auth_info": "Za chwilę otworzy się systemowe okno autoryzacji. Wpisz w nim hasło swojego konta Linux / administratora. DCC nie widzi ani nie zapisuje tego hasła.\n\nPo zakończeniu wyloguj się i zaloguj ponownie jeden raz, aby aktywować członkostwo w grupie docker.",
        "docker_group_install_title": "Konfiguracja uprawnień Docker",
        "docker_group_install_status": "Dodawanie bieżącego użytkownika do grupy docker...",
        "docker_group_install_success": "Użytkownik został poprawnie dodany do grupy docker. Wyloguj się i zaloguj ponownie, a następnie uruchom ponownie DCC, aby aktywować dostęp do Dockera.",
        "docker_group_already_member": "Ten użytkownik już należy do grupy docker. Jeżeli Docker nadal jest niedostępny, wyloguj się i zaloguj ponownie albo sprawdź, czy usługa Docker działa.",
        "docker_group_unsupported": "Automatyczna konfiguracja grupy docker wymaga Linuxa z PolicyKit (pkexec).",
        "first_run_profiles_intro": "Możesz teraz zaimportować profile połączeń. Hasła i hasła do kluczy celowo nie są przenoszone. Ścieżki kluczy z innego komputera są czyszczone, jeżeli tutaj nie istnieją.",
        "first_run_import_profiles": "Importuj profile",
        "first_run_edit_profiles": "Edytuj profile / ścieżki kluczy",
        "first_run_profiles_count": "Profile połączeń: {count}",
        "first_run_key_paths_missing": "Profile wymagające nowej ścieżki klucza SSH: {count}",
        "first_run_finish": "Zakończ konfigurację",
        "first_run_later": "Później",
        "info_shortcuts": "Skróty klawiszowe",
        "info_shortcuts_title": "Skróty klawiszowe",
        "info_shortcuts_body": (
            "Ctrl + kółko myszy nad kontenerami  -  powiększanie / zmniejszanie listy\n"
            "Ctrl + 0  -  przywróć skalę listy do 100%\n"
            "Ctrl + F  -  przejdź do wyszukiwarki kontenerów\n"
            "F5  -  odśwież kontenery\n"
            "F11  -  pełny ekran / przywróć ostatni normalny rozmiar\n"
            "Esc  -  wyjdź z pełnego ekranu"
        ),
        "container_zoom_status": "Skala widoku kontenerów: {percent}%",
        "info_title": "Docker Control Center",
        "btn_refresh": "Odśwież",
        "btn_start": "Start",
        "btn_stop": "Stop",
        "btn_restart": "Restart",
        "btn_autostart_on": "Autostart ON",
        "btn_autostart_off": "Autostart OFF",
        "autostart_status_on": "Tak ({policy})",
        "autostart_status_off": "Nie",
        "autostart_status_managed": "Auto (zarządzane)",
        "autostart_status_unknown": "N/D",

        "btn_remove": "Usuń",
        "btn_logs": "Logi",
        "btn_new": "Nowy kontener",
        "btn_shop_short": "+ SKLEP",
        "btn_edit_start": "Edytuj start",
        "btn_pause": "Pauza",
        "btn_unpause": "Wznów",
        "btn_start_profile": "Start profilu",
        "btn_profiles": "Profile połączeń",
        "btn_ssh_terminal": "Terminal SSH",
        "btn_local_info": "INFO lokalne",
        "infra_unknown": "Infrastruktura: nieznana",
        "infra_local_label": "Infrastruktura: Lokalny host ({os} | {arch})",
        "infra_local_fallback": "Infrastruktura: Docker Desktop",
        "infra_local_wsl": "Infrastruktura: WSL ({distro})",
        "infra_remote_label": "Infrastruktura: Host zdalny ({os} | {arch})",
        "infra_remote_tunnel": "Infrastruktura: Tunel zdalny",
        "infra_terminal_tooltip": "Kliknij, aby otworzyć terminal hosta",
        "btn_host_restart": "Uruchom ponownie komputer",
        "host_status_running": "Host jest dostępny",
        "host_status_off": "Host jest wyłączony",
        "host_restart_title": "Uruchomić ponownie hosta?",
        "host_restart_body": "To spowoduje restart bieżącego hosta. Kontynuować?",
        "host_restart_sent": "Polecenie restartu zostało wysłane.",
        "host_restart_probable": "Połączenie SSH zostało zerwane po wysłaniu restartu. Host prawdopodobnie uruchamia się ponownie.",
        "host_restart_in_progress": "Restart zlecony. Oczekiwanie na ponowną dostępność hosta...",
        "host_restart_checking": "Sprawdzanie połączenia z {name}... próba {attempt}",
        "host_restart_waiting_retry": "Host nadal się uruchamia. Kolejna próba połączenia zostanie wykonana automatycznie.",
        "host_restart_engine_ready": "Host znów odpowiada. Odświeżanie listy kontenerów...",
        "host_restart_recovered": "Połączenie odzyskane. Lista kontenerów została odświeżona.",
        "host_restart_timeout": "Host nie odzyskał połączenia w ciągu 5 minut. Automatyczne sprawdzanie zostało zatrzymane.",
        "host_restart_cancel_checks": "Anuluj sprawdzanie",
        "host_restart_cancelled": "Automatyczne sprawdzanie połączenia anulowane.",
        "host_restart_notice_title": "Restart hosta",
        "host_restart_failed": "Nie udało się zrestartować hosta dostępnymi komendami.",
        "host_metrics_unknown": "Obciążenie hosta/kontenerów: niedostępne",
        "host_metrics_format": "Host CPU {host_cpu:.1f}% | RAM {host_mem} / {host_total} ({host_mem_pct:.1f}%) | Kontenery CPU {container_cpu:.1f}% | RAM {container_mem}",
        "container_metrics_format": "Kontenery CPU {container_cpu:.1f}% | RAM {container_mem}",
        "local_profiles_wsl_command": "Szybki test WSL (wybrana dystrybucja): wsl -d {distro} sh -lc \"docker ps\"",        "btn_transparency_on": "Przezroczystość: ON",
        "btn_transparency_off": "Przezroczystość: OFF",
        "transparency_level": "Poziom szkła",
        "btn_music_on": "Muzyka: ON",
        "btn_music_off": "Muzyka: OFF",
        "music_missing": "Nie znaleziono pliku bg.mp3 obok aplikacji.",
        "music_unavailable": "Moduł audio PyQt6 nie jest dostępny. Doinstaluj PyQt6-Qt6 / multimedia.",
        "hero_title": "DCC | DOCKER CONTROL CENTER",
        "hero_subtitle": "Profesjonalny panel do zarządzania Dockerem lokalnym, WSL i zdalnymi hostami SSH z gotowymi presetami wdrożeń.",
        "hero_subtitle_linux": "Profesjonalny panel do lokalnego Docker Engine oraz zdalnych host\u00f3w SSH / Balena z gotowymi presetami wdro\u017ce\u0144.",
        "profile_label": "Profil zdalny",
        "profile_name": "Nazwa profilu",
        "profile_mode": "Tryb połączenia",
        "profile_ssh_target": "Cel SSH (user@host)",
        "profile_ssh_port": "Port SSH",
        "profile_auth_mode": "Autoryzacja SSH",
        "profile_auth_key": "Klucz SSH",
        "profile_auth_both": "Klucz + hasło do klucza",
        "profile_auth_agent": "Agent SSH",
        "profile_auth_password": "Login i hasło",
        "profile_key_path": "Plik klucza SSH (opcjonalnie)",
        "profile_key_browse": "Zmień ścieżkę klucza",
        "profile_key_path_ok": "Plik klucza SSH jest dostępny na tym komputerze.",
        "profile_key_path_missing": "Ten profil wymaga ścieżki klucza SSH poprawnej na tym komputerze. Skopiuj tutaj klucz, a potem wskaż go przez „Zmień ścieżkę klucza”.",
        "profiles_import_key_paths": "Zaimportowane profile wymagające wskazania nowej ścieżki klucza SSH na tym komputerze: {count}.",
        "profile_passphrase": "Hasło do klucza",
        "profile_passphrase_note": "Użyj tego pola, gdy klucz SSH ma hasło (SenseCap M1).",
        "profile_key_path_required_passphrase": "Wybierz plik klucza SSH dla trybu z haslem do klucza.",
        "profile_password": "Hasło SSH",
        "profile_password_note": "Hasło jest zapisywane w lokalnym magazynie sekretów Twojego konta użytkownika. Używaj tylko na zaufanym komputerze.",
        "profile_base_url": "Docker URL",
        "profile_tunnel_command": "Komenda tunelu",
        "profile_wait": "Czekaj po starcie (s)",
        "profile_add": "Dodaj",
        "profile_copy": "Kopiuj",
        "profile_copy_suffix": "kopia",
        "profile_save": "Zapisz",
        "profile_delete": "Usuń",
        "profile_tutorial": "Konfigurator hosta",
        "profile_dialog_title": "Profile połączeń zdalnych",
        "profile_saved": "Profil zapisany.",
        "profile_deleted": "Profil usunięty.",
        "profile_missing_name": "Nazwa profilu jest wymagana.",
        "profile_missing_target": "Dla trybu SSH wpisz user@host albo popraw Docker URL.",
        "profile_mode_ssh": "SSH bezpośrednio",
        "profile_mode_tunnel": "Tunel TCP",
        "profile_starting": "Startuje połączenie dla profilu: {name}",
        "profile_connecting": "Łączenie z profilem: {name}",
        "profile_connected": "Połączono z profilem: {name}",
        "profile_no_profiles": "Brak profili zdalnych. Dodaj profil połączenia.",
        "profile_file_error": "Nie udało się zapisac pliku profili.",
        "profile_started": "Połączenie uruchomione. Próba łączenia za chwile...",
        "profile_tutorial_title": "Konfigurator zdalnego hosta Docker",
        "profile_tutorial_intro": "Kroki dla nowego urządzenia z Dockerem:",
        "profile_tutorial_hint": "Możesz użyć klucza SSH albo loginu z hasłem. Tunel zostaw jako tryb awaryjny. Jeśli host ma Balena OS, użyj balena ps / balena run - DCC wykryje to automatycznie.",
        "profile_tutorial_agent_windows": "Klucz SSH w Windows (opcjonalnie, uruchom PowerShell jako administrator):\n1) Get-Service ssh-agent | Set-Service -StartupType Automatic  - ustawia ssh-agent na start automatyczny\n2) Start-Service ssh-agent  - uruchamia agent teraz\n3) ssh-add C:\\Users\\Kosmo\\.ssh\\your_key_name  - dodaje klucz prywatny do agenta",
        "profile_tutorial_agent_linux": "Klucz SSH w Linux (opcjonalnie):\n1) eval \"$(ssh-agent -s)\"  - uruchamia ssh-agent dla sesji\n2) ssh-add ~/.ssh/twoj_klucz  - dodaje klucz prywatny\n3) ssh-add -l  - pokazuje załadowane klucze",
        "profile_tutorial_test": "Test (Docker): ssh -p {port} {target} docker ps\nTest (Balena OS): ssh -p {port} {target} balena ps",
        "profile_tutorial_steps": (
            "1. Zainstaluj Docker na zdalnym urządzeniu.\n"
            "2. Dodaj użytkownika do grupy docker: sudo usermod -aG docker {user}\n"
            "3. Zaloguj się ponownie na hosta.\n"
            "4. Sprawdź lokalnie na hoście: docker ps\n"
            "5. Skonfiguruj klucz SSH albo przygotuj login i hasło do GUI.\n"
            "6. W GUI wybierz tryb SSH bezpośrednio i wpisz {target} i port {port}."
        ),
        "col_select": "",
        "col_status_icon": "",
        "col_name": "Nazwa",
        "col_image": "Obraz",
        "col_status": "Status",
        "col_ports": "Porty",
        "col_cpu": "CPU",
        "col_memory": "RAM",
        "col_links": "WWW / Linki",
        "col_project": "Projekt",
        "col_networks": "Sieci",
        "col_autostart": "Autostart",
        "select_all": "Zaznacz wszystkie",
        "column_magnet": "Magnes",
        "column_magnet_tooltip": "Zachowuj ręcznie ustawione proporcje kolumn i dopasowuj je do szerokości tabeli przy zmianie rozmiaru okna.",
        "container_search_placeholder": "Szukaj kontenera po nazwie...",
        "group_by_label": "Grupuj",
        "group_by_project": "Projekty",
        "group_by_network": "Sieci",
        "group_by_none": "Lista płaska",
        "group_project_prefix": "Projekt",
        "group_network_prefix": "Sieć",
        "group_standalone": "Kontenery samodzielne",
        "group_no_network": "Bez sieci",
        "group_summary": "{count} kontenerów · {running} uruchomionych · sieci: {networks}",
        "group_display_expand": "Rozwiń grupę",
        "group_display_collapse": "Zwiń grupę",
        "group_select_all": "Zaznacz wszystkie kontenery w tej grupie",
        "controls_connection": "POŁĄCZENIA",
        "controls_containers": "KONTENERY",
        "controls_view": "WIDOK I HOST",
        "btn_more_actions": "Więcej akcji ▾",
        "status_ready": "Gotowe",
        "status_loading": "Wczytywanie kontenerów...",
        "status_local_connected": "Połączono z lokalnym Docker",
        "engine_docker": "Wykryto silnik: Docker",
        "engine_balena": "Wykryto silnik: Balena OS",
        "engine_unknown": "Wykryto silnik: Nieznany",
        "status_wsl_connected": "Połączono z Docker w WSL: {distro}",
        "msg_no_selection": "Brak zaznaczonych kontenerów.",
        "msg_confirm_remove": "Na pewno usunąć zaznaczone kontenery? To skasuje ich dane.",
        "msg_error": "Błąd",
        "msg_info": "Informacja",
        "msg_action_blocked": "Akcja wstrzymana",
        "autostart_enable_title": "Włączyć autostart?",
        "autostart_disable_title": "Wyłączyć autostart?",
        "autostart_enable_confirm": "Zmiana ustawi politykę restartu Docker na unless-stopped. Kontener nie straci danych ani ustawień, ale po restarcie systemu lub demona Docker będzie próbował uruchomić się automatycznie. Kontynuować?",
        "autostart_disable_confirm": "Zmiana ustawi politykę restartu Docker na no. Kontener nie straci danych ani ustawień, ale po restarcie systemu lub demona Docker nie będzie uruchamiany automatycznie. Kontynuować?",
        "logs_title": "Logi: {name}",
        "logs_loading": "Wczytywanie logow...",
        "wizard_title": "Katalog wdrożeń Docker",
        "wizard_store_subtitle": "Sklep aplikacji dla aktualnie wybranego hosta Docker",
        "wizard_target_host": "Host docelowy: {host}",
        "wizard_repositories": "Repozytoria",
        "wizard_repo_title": "Repozytoria katalogu wdrożeń",
        "wizard_repo_intro": "Dodaj URL katalogu JSON lub repozytorium GitHub zawierające dcc-catalog.json / catalog.json.",
        "wizard_repo_primary": "Główny katalog DCC · automatyczny",
        "wizard_repo_primary_hint": "Główny katalog DCC jest wbudowany w aplikację i nie można go usunąć. Poniżej możesz dodać opcjonalne repozytoria.",
        "wizard_repo_url": "URL repozytorium lub katalogu",
        "wizard_repo_add": "Dodaj",
        "wizard_repo_remove": "Usuń",
        "wizard_repo_open": "Otwórz",
        "wizard_repo_refresh": "Odśwież katalogi",
        "wizard_repo_syncing": "Aktualizowanie katalogów aplikacji...",
        "wizard_repo_status_cached": "Pamięć katalogu gotowa",
        "wizard_repo_status_updated": "Katalog zaktualizowany · aplikacje z repozytoriów: {count}",
        "wizard_repo_status_partial": "Katalog zaktualizowany z pamięci · aplikacje: {count} · część repozytoriów niedostępna",
        "wizard_repo_invalid": "Nie udało się wczytać tego repozytorium wdrożeń.",
        "wizard_repo_loaded": "Wczytano aplikacje z zewnętrznych repozytoriów: {count}.",
        "wizard_repo_errors": "Niektórych repozytoriów nie udało się wczytać:\n{errors}",
        "wizard_source": "Źródło",
        "wizard_docs": "Dokumentacja",
        "wizard_homepage": "Strona",
        "wizard_quick_deploy": "Wdróż wybraną aplikację",
        "wizard_store_tab": "Opis",
        "wizard_store_install": "Instaluj",
        "wizard_store_uninstall": "Odinstaluj",
        "wizard_store_installed": "Zainstalowana na tym hoście",
        "wizard_store_not_installed": "Niezainstalowana na tym hoście",
        "wizard_store_features": "Najważniejsze funkcje",
        "wizard_store_gallery": "Galeria",
        "wizard_store_requirements": "Wymagania",
        "wizard_store_categories": "Kategorie",
        "wizard_store_apps": "Aplikacje",
        "wizard_store_no_media": "Katalog nie zawiera grafiki podglądowej.",
        "wizard_store_uninstall_title": "Odinstalować aplikację?",
        "wizard_store_uninstall_confirm": "DCC znalazło pasujące kontenery ({count}):\n\n{names}\n\nKontenery zostaną usunięte. Nazwane wolumeny i dane bind-mounted nie są kasowane automatycznie, ale dane zapisane wyłącznie w zapisywalnej warstwie kontenera mogą zostać utracone. Kontynuować?",
        "wizard_store_uninstall_done": "Kontenery aplikacji zostały usunięte.",
        "wizard_balena_category": "Balena OS",
        "wizard_installed_category": "Zainstalowane",
        "wizard_credentials_title": "Wykryto dane dostępu",
        "wizard_credentials_intro": "DCC znalazło poniższe dane dostępu w logach startowych kontenera. Są wyświetlane tylko tutaj i DCC ich nie zapisuje:",
        "wizard_credentials_none": "Wdrożenie zakończone. W logach startowych nie wykryto danych logowania.",
        "wizard_auto_fix": "Automatycznie rozwiązuj bezpieczne konflikty nazw i portów hosta",
        "wizard_ai_fallback": "Użyj AI tylko, gdy reguły lokalne nie potrafią naprawić błędu",
        "wizard_safe_changes_title": "Bezpieczne poprawki wdrożenia",
        "wizard_safe_changes_body": "DCC wykrył konflikty i może zastosować bezpieczne zmiany:\n\n{changes}\n\nZastosować je i kontynuować?",
        "wizard_safe_name_change": "Nazwa kontenera: {old} -> {new}",
        "wizard_safe_port_change": "Port hosta: {old} -> {new}",
        "wizard_model_fallback": "Model '{old}' nie jest zainstalowany. Używam '{new}'.",
        "wizard_arch_unsupported": "Ta aplikacja nie deklaruje obsługi architektury hosta: {arch}.",
        "wizard_risky_title": "Sprawdź podwyższone uprawnienia kontenera",
        "wizard_risky_body": "To wdrożenie prosi o podwyższony dostęp do hosta:\n\n{risks}\n\nPrzed kontynuacją sprawdź źródło i dokumentację projektu. Mimo to wdrożyć?",
        "wizard_edit_title": "Edycja startu kontenera",
        "wizard_catalog": "Katalog obrazów",
        "wizard_search": "Szukaj obrazu lub opisu",
        "wizard_category": "Kategoria",
        "wizard_catalog_count": "Aplikacje: {count}",
        "wizard_pick_image": "Wybierz gotowy obraz",
        "wizard_manual": "Konfiguracja ręczna",
        "wizard_manual_title": "Własna konfiguracja kontenera",
        "wizard_manual_description": "Wpisz ręcznie obraz, porty, parametry i komendę albo wklej niżej polecenie docker run.",
        "wizard_current_container_title": "Kontener: {name}",
        "wizard_current_container_description": "Aktualny obraz: {image}",
        "wizard_latest_release": "Najnowsza wersja upstream: {version}",
        "wizard_all_categories": "Wszystkie",
        "wizard_name": "Nazwa kontenera (np. my-app)",
        "wizard_image": "Obraz (np. ghcr.io/open-webui/open-webui:main)",
        "wizard_cport": "Port w kontenerze (np. 8080)",
        "wizard_hport": "Port hosta (puste = taki sam jak w kontenerze)",
        "wizard_extra": "Dodatkowe parametry (np. -e KEY=VAL -v host:cont)",
        "wizard_command_only": "Polecenie startowe w kontenerze (opcjonalne)",
        "wizard_cli": "Silnik poleceń",
        "wizard_command_input": "Wklej docker run (jedna linia lub wiele linii; zostanie wyrównane)",
        "wizard_parse": "Uzupełnij z komendy",
        "wizard_normalize": "Wyrównaj komendę",
        "wizard_ai_button": "Konfiguruj z AI",
        "wizard_setup_tab": "Konfiguracja kontenera",
        "wizard_ai_tab": "Asystent AI",
        "llm_title": "Konfiguracja LLM",
        "llm_provider": "Dostawca",
        "llm_provider_ollama": "Lokalna Ollama",
        "llm_provider_openai": "OpenAI",
        "llm_provider_anthropic": "Anthropic Claude",
        "llm_provider_gemini": "Google Gemini",
        "llm_provider_groq": "Groq",
        "llm_provider_mistral": "Mistral AI",
        "llm_provider_openrouter": "OpenRouter",
        "llm_provider_deepseek": "DeepSeek",
        "llm_provider_xai": "xAI Grok",
        "llm_ollama_url": "URL Ollama",
        "llm_model": "Model",
        "llm_openai_key": "Klucz API OpenAI",
        "llm_api_key": "Klucz API",
        "llm_detect": "Wykryj modele",
        "llm_save": "Zapisz",
        "llm_close": "Zamknij",
        "llm_models_ready": "Załadowano modele.",
        "llm_models_failed": "Nie udało się pobrać modeli.",
        "llm_api_key_missing": "Wpisz klucz API {provider} w Konfiguruj -> LLM.",
        "llm_prompt_placeholder": "Opisz, jak zmienić komendę docker run. Przykład: Zamontuj D:/Muzyka z Windows 11 do /data/music w Jellyfin jako read-only i zachowaj jedną linię.",
        "llm_generate": "Generuj komendę",
        "llm_apply": "Zastosuj te komendę",
        "llm_status_idle": "AI jest gotowe do podpowiedzi.",
        "llm_status_working": "Trwa generowanie komendy docker run przez AI...",
        "llm_status_done": "AI przygotowało nową komendę docker run.",
        "llm_status_error": "Zapytanie do AI nie powiodło się.",
        "llm_result": "Komenda wynikowa AI",
        "llm_request": "Co chcesz zmienić?",
        "llm_context": "Aktualny kontekst docker run",
        "llm_use_saved": "Ustawienia dostawcy są pobierane z Konfiguruj -> LLM.",
        "llm_refresh_models": "Odśwież modele",
        "llm_response_invalid": "Model nie zwrócił poprawnej komendy docker run.",
        "llm_apply_done": "Komenda z AI zostala wpisana do formularza.",
        "llm_prompt_required": "Opisz, co chcesz zmienić w komendzie docker run.",
        "wizard_notes": "Opis i podpowiedzi",
        "wizard_online_refresh": "Odśwież opisy online",
        "wizard_catalog_loading": "Pobieranie danych o obrazie...",
        "wizard_catalog_loaded": "Zaktualizowano opis obrazu z Docker Hub.",
        "wizard_command_invalid": "Nie udało się sparsować komendy docker run.",
        "wizard_balena_notice": "Wykryto Balena OS. Ta komenda docker run zostanie uruchomiona jako 'balena run'.",
        "wizard_balena_only": "Wykryto Balena OS. DCC używa balena run/balena ps. Używaj tylko obrazów kompatybilnych z Balena.",
        "wizard_port_in_use": "Port {port} jest już używany przez: {users}. Wybierz inny port.",
        "wizard_summary": "Komenda do uruchomienia:",
        "wizard_run": "Uruchom kontener",
        "wizard_apply": "Zastosuj start",
        "wizard_cancel": "Anuluj",
        "wizard_done": "Wdrożenie zakończone, a kontener został zweryfikowany.",
        "wizard_recreate_title": "Odtworzyć kontener?",
        "wizard_recreate_confirm": "Kontener zostanie zatrzymany, usunięty i utworzony ponownie z nowymi parametrami docker run.\n\nDane w bind mountach i nazwanych volume pozostaną zachowane, jeśli zostawisz te same ścieżki montowania. Dane zapisane tylko wewnątrz filesystemu kontenera mogą zostac utracone.\n\nKontynuowac?",
        "wizard_recreate_done": "Kontener został odtworzony z nowymi parametrami startu.",
        "wizard_select_one_edit": "Zaznacz jeden kontener, aby edytować jego konfigurację startu.",
        "progress_title_create": "Wdrażanie kontenera",
        "progress_title_recreate": "Odtwarzanie kontenera",
        "progress_status_create": "Trwa instalacja / wdrażanie kontenera...",
        "progress_status_build_source": "{name}: etap 1/2 - budowanie lokalnego obrazu Docker ze źródeł...",
        "progress_status_recreate": "Trwa odtwarzanie kontenera z nowymi parametrami startu...",
        "progress_status_done": "SUKCES — wdrożenie zakończone.",
        "progress_status_failed": "BŁĄD — wdrożenie nie zostało zakończone.",
        "progress_elapsed": "Czas: {seconds}s",
        "progress_copy_log": "Kopiuj log",
        "progress_log_copied": "Log skopiowany.",
        "progress_verify_start": "Sprawdzanie wdrożonego kontenera...",
        "progress_verify_found": "Weryfikacja OK: {name} istnieje (stan: {status}).",
        "progress_verify_missing": "Weryfikacja nie powiodła się: po wdrożeniu nie znaleziono kontenera {name}.",
        "progress_ssh_verified": "Odłączony kontener {id} został utworzony i potwierdzony na zdalnym hoście.",
        "progress_close": "Zamknij",
        "command_copy": "Kopiuj polecenie",
        "command_run": "Uruchom polecenie",
        "exec_shell_title": "Powłoka kontenera",
        "exec_shell_intro_local": "To polecenie otwiera interaktywną powłokę wewnątrz wybranego kontenera na lokalnym silniku Docker.",
        "exec_shell_intro_wsl": "To polecenie otwiera interaktywną powłokę wewnątrz wybranego kontenera przez dystrybucję WSL: {target}.",
        "exec_shell_intro_remote_ssh": "To polecenie otwiera interaktywną powłokę wewnątrz wybranego kontenera na zdalnym hoście: {target}.",
        "exec_shell_intro_remote_tunnel": "To polecenie otwiera interaktywną powłokę wewnątrz wybranego kontenera przez skonfigurowany tunel Docker.",
        "docker_not_available": "Brak połączenia z Docker. Czy Docker Desktop lub host zdalny działa?",
        "docker_local_unavailable_title": "Lokalny Docker jest niedostępny",
        "docker_local_unavailable_hint": "Lokalny silnik Docker jest niedostępny. Możesz tutaj zainstalować lub uruchomić wymagany Docker, a następnie ponowić połączenie lokalne.",
        "docker_local_unavailable_hint_linux": "Lokalny Docker Engine jest niedost\u0119pny z poziomu DCC. DCC korzysta z DOCKER_HOST i aktywnego kontekstu Docker CLI (w tym socketu Docker Desktop/rootless), a dopiero potem z systemowego socketu Dockera.",
        "docker_local_endpoint_detected": "Wykryty endpoint Dockera: {context} -> {endpoint}",
        "docker_local_open_desktop": "Uruchom Docker Desktop",
        "docker_local_install_desktop": "Zainstaluj Docker Desktop",
        "docker_local_install_docker": "Zainstaluj Docker",
        "docker_local_open_failed": "Nie udało się uruchomić Docker Desktop automatycznie. Uruchom go ręcznie i spróbuj ponownie.",
        "local_client": "Połącz lokalnie",
        "btn_local_profiles": "INFO lokalne",
        "btn_wsl_profile": "WSL lokalne",
        "btn_wsl_refresh": "WSL wykryj",
        "wsl_label": "WSL",
        "wsl_none": "Brak dystrybucji WSL",
        "wsl_detect_error": "Nie udało się pobrać listy dystrybucji WSL. Uruchom aplikację z uprawnieniami do WSL albo sprawdź, czy usługa WSL działa.",
        "wsl_connect_error": "Nie udało się połączyć z Dockerem w WSL. Upewnij się, że Docker działa w wybranej dystrybucji.",
        "wsl_help_title": "WSL / WSL2 Docker",
        "wsl_help_text": "Wykryta dystrybucja: {distro}\n\nOpcje połączenia z GUI:\n1. Najłatwiej: Docker Desktop z integracją WSL i przycisk Połącz lokalnie.\n2. Kliknij WSL lokalne, aby zarządzać Dockerem uruchomionym bezpośrednio w tej dystrybucji.\n3. Profil SSH: uruchom OpenSSH w WSL i połącz profilem SSH.\n4. Profil tunelowy: wystaw socket Dockera z WSL do TCP i połącz profilem tunelowym.\n\nSzybki test w terminalu:\nwsl -d {distro} sh -lc \"docker ps\"",
        "local_profiles_text": "Profile lokalne dla początkujących:\n\n1. Kontenery lokalne\nUżywaj, gdy Docker Desktop albo lokalny daemon jest uruchomiony w Windows.\nSprawdź: PowerShell -> docker ps\n\n2. WSL lokalne\nUżywaj, gdy Docker działa bezpośrednio w Ubuntu, Debianie, Kali albo innej dystrybucji WSL2.\nSprawdź: PowerShell -> wsl -d Ubuntu sh -lc \"docker ps\"\n\nJak dodać kontener:\n- kliknij Nowy kontener\n- wybierz gotowy obraz albo wklej komendę docker run\n- sprawdź podsumowanie i uruchom\n\nKiedy który tryb:\n- Windows / Docker Desktop: Połącz lokalnie\n- WSL2 z własnym dockerd: WSL lokalne\n- Raspberry Pi / serwer / NAS: Start profilu przez SSH lub tunel",
        "local_profiles_text_linux": "Tryby po\u0142\u0105czenia na Linux dla pocz\u0105tkuj\u0105cych:\n\n1. Lokalny Docker Engine\nU\u017cyj Po\u0142\u0105cz lokalnie, aby zarz\u0105dza\u0107 Dockerem uruchomionym bezpo\u015brednio na tym komputerze Linux.\nSprawdzenie w terminalu: docker ps\n\nJe\u017celi DCC dopiero doda\u0142o Twoje konto do grupy docker, skorzystaj z proponowanego ponownego uruchomienia DCC z dost\u0119pem do Docker albo wyloguj si\u0119 i zaloguj ponownie jeden raz.\n\n2. Zdalny Linux / Balena / Raspberry Pi / serwer / NAS\nUtw\u00f3rz profil SSH i uruchom ten profil, aby zarz\u0105dza\u0107 Dockerem zdalnie.\n\nJak doda\u0107 kontener:\n- kliknij Nowy kontener\n- wybierz gotowy obraz albo wklej komend\u0119 docker run\n- sprawd\u017a podsumowanie i uruchom",
        "remote_hint": "Lokalne, WSL i zdalne silniki Dockera w jednym panelu operatorskim.",
        "remote_hint_linux": "Lokalny Docker Engine na Linux oraz zdalne hosty Docker przez SSH / Balena w jednym panelu operatorskim.",
        "remote_sysinfo_label": "Host zdalny: {os} | {arch}",
        "remote_sysinfo_unknown": "Host zdalny: nieznany",
        "remote_sysinfo_fetch_failed": "Host zdalny: brak danych",
        "ssh_terminal_unavailable": "Terminal SSH jest dostępny tylko dla profili SSH bezpośrednio.",
        "ssh_terminal_tunnel": "Terminal SSH nie jest dostępny w trybie tunelu.",
        "ctx_start": "Start",
        "ctx_stop": "Stop",
        "ctx_restart": "Restart",
        "ctx_autostart_on": "Autostart ON",
        "ctx_autostart_off": "Autostart OFF",
        "ctx_pause": "Pauza",
        "ctx_unpause": "Wznów",
        "ctx_logs": "Logi",
        "ctx_inspect": "Inspekcja",
        "ctx_exec": "Powłoka kontenera",
        "ctx_edit_start": "Edytuj start",
        "ctx_open_link": "Otwórz link",
        "ctx_copy_link": "Kopiuj link",
        "link_local": "Lokalnie",
        "link_device": "Na urządzeniu",
        "link_lan": "LAN",
        "ctx_remove": "Usuń",
        "ctx_lifecycle": "Cykl życia",
        "ctx_configuration": "Konfiguracja",
        "ctx_diagnostics": "Diagnostyka",
        "ctx_links": "Linki WWW",
        "ctx_actual_data": "Rzeczywiste dane kontenera",
        "ctx_copy_details": "Kopiuj dane techniczne",
        "ctx_copy_ports": "Kopiuj wystawione porty",
        "ctx_copy_networks": "Kopiuj sieci",
        "ctx_project": "Projekt: {project}",
        "ctx_networks": "Sieci: {networks}",
        "ctx_ports": "Wystawione porty: {ports}",
        "ctx_mounts": "Montowania: {count}",
        "ctx_cached_data_missing": "Dane kontenera nie są już dostępne. Odśwież listę."
    }
}
@dataclass
class RemoteProfile:
    name: str
    mode: str = "ssh"
    ssh_target: str = "user@192.168.0.200"
    ssh_port: int = 0
    ssh_auth_mode: str = "key"
    ssh_username: str = ""
    ssh_password: str = ""
    ssh_passphrase: str = ""
    ssh_key_path: str = ""
    secret_id: str = ""
    base_url: str = ""
    tunnel_command: str = "ssh -N -L 23750:127.0.0.1:2375 user@192.168.0.200"
    wait_seconds: int = 2

    @classmethod
    def default(cls) -> "RemoteProfile":
        return cls(name="Raspberry Pi SSH")

    def resolved_base_url(self) -> str:
        if self.mode == "ssh":
            port = self.resolved_ssh_port()
            user = self.resolved_ssh_user()
            host = self.resolved_ssh_host()
            return f"ssh://{user}@{host}:{port}"
        if self.base_url:
            return self.base_url
        return "tcp://127.0.0.1:23750"

    def resolved_ssh_host(self) -> str:
        target = self.ssh_target
        if "@" in target:
            target = target.split("@", 1)[1]
        if ":" in target:
            host, tail = target.rsplit(":", 1)
            if tail.isdigit():
                return host
        return target

    def resolved_ssh_user(self) -> str:
        if self.ssh_username:
            return self.ssh_username
        if "@" in self.ssh_target:
            return self.ssh_target.split("@", 1)[0]
        return "root"

    def resolved_ssh_port(self) -> int:
        target = self.ssh_target
        if "@" in target:
            target = target.split("@", 1)[1]
        if ":" in target:
            _host, tail = target.rsplit(":", 1)
            if tail.isdigit():
                return int(tail)
        if self.ssh_port:
            try:
                return int(self.ssh_port)
            except Exception:
                pass
        return 22
class SecretStore:
    def __init__(self, path: Path):
        self.path = path
        self._data = self._load()

    def _load(self) -> Dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return dict(payload.get("secrets", {}) or {})
        except Exception:
            return {}

    def _save(self):
        self.path.write_text(json.dumps({"secrets": self._data}, indent=2, ensure_ascii=True), encoding="utf-8")

    def _protect(self, value: str) -> str:
        raw = value.encode("utf-8")
        if os.name != "nt":
            return base64.b64encode(raw).decode("ascii")

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        buffer = ctypes.create_string_buffer(raw, len(raw))
        in_blob = DATA_BLOB(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
        out_blob = DATA_BLOB()
        if not crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
            raise ctypes.WinError()
        try:
            protected = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            return base64.b64encode(protected).decode("ascii")
        finally:
            kernel32.LocalFree(out_blob.pbData)

    def _unprotect(self, value: str) -> str:
        raw = base64.b64decode(value.encode("ascii"))
        if os.name != "nt":
            return raw.decode("utf-8", errors="ignore")

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        buffer = ctypes.create_string_buffer(raw, len(raw))
        in_blob = DATA_BLOB(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
        out_blob = DATA_BLOB()
        if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
            raise ctypes.WinError()
        try:
            plain = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            return plain.decode("utf-8", errors="ignore")
        finally:
            kernel32.LocalFree(out_blob.pbData)

    def get_secret(self, key: str, default: str = "") -> str:
        value = self._data.get(key)
        if not value:
            return default
        try:
            return self._unprotect(value)
        except Exception:
            return default

    def set_secret(self, key: str, value: str):
        if value:
            self._data[key] = self._protect(value)
        else:
            self._data.pop(key, None)
        self._save()

    def delete_secret(self, key: str):
        if key in self._data:
            self._data.pop(key, None)
            self._save()
@dataclass
class ImageTemplate:
    name: str
    image: str
    category: str
    description: str
    default_name: str
    container_port: str = ""
    host_port: str = ""
    extra: str = ""
    command: str = ""
    notes: str = ""
    lightweight: bool = False
    category_en: str = ""
    description_en: str = ""
    notes_en: str = ""
    engines: Optional[List[str]] = None
    archs: Optional[List[str]] = None
    source_url: str = ""
    docs_url: str = ""
    homepage_url: str = ""
    icon_text: str = ""
    repository_source: str = ""
    upstream_repo: str = ""
    latest_release: str = ""
    latest_release_url: str = ""
    last_checked: str = ""
    verified: bool = False
    requires: Optional[List[str]] = None
    gpu: bool = False
    ram_min_mb: int = 0
    storage_type: str = ""
    backup_priority: str = ""
    security_exposure: str = ""
    compose_required: bool = False
    build_context: str = ""
    build_dockerfile: str = ""
    balena_verified: bool = False
    store_description: str = ""
    store_description_en: str = ""
    features: Optional[List[str]] = None
    features_en: Optional[List[str]] = None
    icon_url: str = ""
    hero_image_url: str = ""
    gallery: Optional[List[Dict[str, str]]] = None
    credential_patterns: Optional[List[Dict[str, str]]] = None
    post_install_hints: Optional[List[str]] = None
    post_install_hints_en: Optional[List[str]] = None

    def supports_engine(self, engine: str) -> bool:
        engine = str(engine or "").lower().strip()
        if not engine:
            return True
        engines = [str(item).lower() for item in (self.engines or ["docker"]) if str(item).strip()]
        return engine in engines or "any" in engines

    def supports_arch(self, arch: str) -> bool:
        arch = str(arch or "").lower().strip()
        if not arch:
            return True
        archs = [str(item).lower() for item in (self.archs or []) if str(item).strip()]
        if not archs:
            return True
        return arch in archs

    def category_for(self, lang: str) -> str:
        return self.category_en if lang == "EN" and self.category_en else self.category

    def description_for(self, lang: str) -> str:
        return self.description_en if lang == "EN" and self.description_en else self.description

    def notes_for(self, lang: str) -> str:
        return self.notes_en if lang == "EN" and self.notes_en else self.notes

    def store_description_for(self, lang: str) -> str:
        if lang == "EN" and self.store_description_en:
            return self.store_description_en
        return self.store_description or self.description_for(lang)

    def features_for(self, lang: str) -> List[str]:
        values = self.features_en if lang == "EN" and self.features_en else self.features
        return [str(item).strip() for item in (values or []) if str(item).strip()]

    def post_install_hints_for(self, lang: str) -> List[str]:
        values = self.post_install_hints_en if lang == "EN" and self.post_install_hints_en else self.post_install_hints
        return [str(item).strip() for item in (values or []) if str(item).strip()]


def image_template_from_dict(raw: Dict, repository_source: str = "") -> Optional[ImageTemplate]:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or raw.get("title") or "").strip()
    image = str(raw.get("image") or raw.get("docker_image") or "").strip()
    if not name or not image:
        return None
    raw_gallery = raw.get("gallery") or raw.get("screenshots") or []
    gallery: List[Dict[str, str]] = []
    if isinstance(raw_gallery, list):
        for entry in raw_gallery:
            if isinstance(entry, str) and entry.strip():
                gallery.append({"url": entry.strip()})
            elif isinstance(entry, dict):
                url = str(entry.get("url") or entry.get("image") or "").strip()
                if url:
                    gallery.append({
                        "url": url,
                        "caption": str(entry.get("caption") or "").strip(),
                        "caption_en": str(entry.get("caption_en") or "").strip(),
                    })
    credential_patterns: List[Dict[str, str]] = []
    raw_patterns = raw.get("credential_patterns") or []
    if isinstance(raw_patterns, list):
        for entry in raw_patterns:
            if not isinstance(entry, dict):
                continue
            regex = str(entry.get("regex") or entry.get("pattern") or "").strip()
            if regex:
                credential_patterns.append({
                    "label": str(entry.get("label") or entry.get("name") or "Credential").strip(),
                    "label_en": str(entry.get("label_en") or "").strip(),
                    "regex": regex,
                })
    return ImageTemplate(
        name=name,
        image=image,
        category=str(raw.get("category") or "Inne").strip() or "Inne",
        description=str(raw.get("description") or "").strip(),
        default_name=str(raw.get("default_name") or raw.get("container_name") or re.sub(r"[^a-z0-9_.-]+", "-", name.lower()).strip("-") or "app"),
        container_port=str(raw.get("container_port") or "").strip(),
        host_port=str(raw.get("host_port") or "").strip(),
        extra=str(raw.get("extra") or raw.get("extra_args") or "").strip(),
        command=str(raw.get("command") or "").strip(),
        notes=str(raw.get("notes") or "").strip(),
        lightweight=bool(raw.get("lightweight", False)),
        category_en=str(raw.get("category_en") or "").strip(),
        description_en=str(raw.get("description_en") or "").strip(),
        notes_en=str(raw.get("notes_en") or "").strip(),
        engines=[str(item) for item in (raw.get("engines") or ["docker"]) if str(item).strip()],
        archs=[str(item) for item in (raw.get("archs") or raw.get("architectures") or []) if str(item).strip()],
        source_url=str(raw.get("source_url") or raw.get("source") or raw.get("github") or "").strip(),
        docs_url=str(raw.get("docs_url") or raw.get("docs") or raw.get("documentation") or "").strip(),
        homepage_url=str(raw.get("homepage_url") or raw.get("homepage") or raw.get("website") or "").strip(),
        icon_text=str(raw.get("icon_text") or raw.get("icon") or "").strip(),
        repository_source=repository_source,
        upstream_repo=str(raw.get("upstream_repo") or "").strip(),
        latest_release=str(raw.get("latest_release") or raw.get("current_version") or "").strip(),
        latest_release_url=str(raw.get("latest_release_url") or raw.get("release_url") or "").strip(),
        last_checked=str(raw.get("last_checked") or "").strip(),
        verified=bool(raw.get("verified", False)),
        requires=[str(item).strip() for item in (raw.get("requires") or []) if str(item).strip()],
        gpu=bool(raw.get("gpu", False)),
        ram_min_mb=max(0, int(raw.get("ram_min_mb") or 0)),
        storage_type=str(raw.get("storage_type") or "").strip(),
        backup_priority=str(raw.get("backup_priority") or "").strip(),
        security_exposure=str(raw.get("security_exposure") or "").strip(),
        compose_required=bool(raw.get("compose_required", False)),
        build_context=str(raw.get("build_context") or raw.get("build_source") or "").strip(),
        build_dockerfile=str(raw.get("build_dockerfile") or raw.get("dockerfile") or "").strip(),
        balena_verified=bool(raw.get("balena_verified", False)),
        store_description=str(raw.get("store_description") or "").strip(),
        store_description_en=str(raw.get("store_description_en") or "").strip(),
        features=[str(item).strip() for item in (raw.get("features") or []) if str(item).strip()],
        features_en=[str(item).strip() for item in (raw.get("features_en") or []) if str(item).strip()],
        icon_url=str(raw.get("icon_url") or "").strip(),
        hero_image_url=str(raw.get("hero_image_url") or raw.get("hero_url") or "").strip(),
        gallery=gallery,
        credential_patterns=credential_patterns,
        post_install_hints=[str(item).strip() for item in (raw.get("post_install_hints") or []) if str(item).strip()],
        post_install_hints_en=[str(item).strip() for item in (raw.get("post_install_hints_en") or []) if str(item).strip()],
    )


def normalize_container_image(value: str) -> str:
    value = str(value or "").strip().lower()
    if value.startswith("docker.io/"):
        value = value[len("docker.io/"):]
    if "@sha256:" in value:
        value = value.split("@sha256:", 1)[0]
    if value and ":" not in value.rsplit("/", 1)[-1]:
        value += ":latest"
    return value


def container_image_name(container) -> str:
    attrs = getattr(container, "attrs", {}) or {}
    config = attrs.get("Config", {}) or {}
    value = str(config.get("Image") or "").strip()
    if value:
        return value
    image = getattr(container, "image", None)
    tags = getattr(image, "tags", []) if image is not None else []
    return str(tags[0]) if tags else ""


def template_matches_container(template: ImageTemplate, container) -> bool:
    target = normalize_container_image(template.image)
    current = normalize_container_image(container_image_name(container))
    if target and current and target == current:
        return True
    target_repo = target.rsplit(":", 1)[0] if target else ""
    current_repo = current.rsplit(":", 1)[0] if current else ""
    name = str(getattr(container, "name", "") or "").lstrip("/").casefold()
    return bool(
        template.default_name
        and name == template.default_name.casefold()
        and target_repo
        and current_repo
        and target_repo == current_repo
    )


def container_name_from_run_args(args: List[str]) -> str:
    for index, token in enumerate(args):
        token = str(token)
        if token == "--name" and index + 1 < len(args):
            return str(args[index + 1]).strip()
        if token.startswith("--name="):
            return token.split("=", 1)[1].strip()
    return ""


def parse_credentials_from_logs(log_text: str, template: Optional[ImageTemplate] = None, lang: str = "EN") -> List[tuple[str, str]]:
    text = str(log_text or "")
    if not text.strip():
        return []
    found: List[tuple[str, str]] = []
    seen = set()

    def add(label: str, value: str):
        clean_value = str(value or "").strip().strip("'\"`.,;[]()")
        clean_label = str(label or "Credential").strip()
        if not clean_value or len(clean_value) > 256:
            return
        key = (clean_label.casefold(), clean_value)
        if key not in seen:
            seen.add(key)
            found.append((clean_label, clean_value))

    for rule in (template.credential_patterns if template else []) or []:
        try:
            pattern = str(rule.get("regex") or "")
            label = str(rule.get("label_en") if lang == "EN" and rule.get("label_en") else rule.get("label") or "Credential")
            for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
                value = match.groupdict().get("value") if match.groupdict() else None
                if value is None and match.lastindex:
                    value = match.group(1)
                if value:
                    add(label, value)
        except re.error:
            continue

    generic_patterns = [
        ("Password" if lang == "EN" else "Hasło", r"(?:web\s+)?(?:admin\s+)?password\s*(?:is|:|=|->)\s*(?P<value>[^\s]+)"),
        ("Username" if lang == "EN" else "Login", r"(?:user(?:name)?|login)\s*(?:is|:|=|->)\s*(?P<value>[^\s]+)"),
        ("Token", r"(?:access\s+)?token\s*(?:is|:|=|->)\s*(?P<value>[A-Za-z0-9._~+/-]{8,})"),
    ]
    for label, pattern in generic_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
            add(label, match.group("value"))
    return found[:8]


def normalize_deployment_repository_source(source: str) -> str:
    normalized = str(source or "").strip().rstrip("/")
    if normalized.lower().endswith(".git"):
        normalized = normalized[:-4]
    return normalized.casefold()


def is_primary_deployment_repository(source: str) -> bool:
    return normalize_deployment_repository_source(source) == normalize_deployment_repository_source(DEFAULT_DEPLOYMENT_REPOSITORY)


def load_deployment_repository_sources() -> List[str]:
    result = [DEFAULT_DEPLOYMENT_REPOSITORY]
    if not DEPLOYMENT_REPOSITORIES_FILE.exists():
        return result
    try:
        payload = json.loads(DEPLOYMENT_REPOSITORIES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return result
    raw_sources = payload.get("repositories", []) if isinstance(payload, dict) else []
    seen = {normalize_deployment_repository_source(DEFAULT_DEPLOYMENT_REPOSITORY)}
    for value in raw_sources:
        source = str(value or "").strip()
        normalized = normalize_deployment_repository_source(source)
        if source and normalized and normalized not in seen:
            result.append(source)
            seen.add(normalized)
    return result


def save_deployment_repository_sources(sources: List[str]) -> None:
    custom_sources = []
    seen = set()
    for value in sources:
        source = str(value or "").strip()
        normalized = normalize_deployment_repository_source(source)
        if not source or not normalized or is_primary_deployment_repository(source) or normalized in seen:
            continue
        custom_sources.append(source)
        seen.add(normalized)
    DEPLOYMENT_REPOSITORIES_FILE.write_text(
        json.dumps({"repositories": custom_sources}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_cached_deployment_catalog() -> List[ImageTemplate]:
    if not DEPLOYMENT_CATALOG_CACHE_FILE.exists():
        return []
    try:
        payload = json.loads(DEPLOYMENT_CATALOG_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    apps = payload.get("apps", []) if isinstance(payload, dict) else []
    parsed = [image_template_from_dict(item, str(item.get("repository_source") or "")) for item in apps if isinstance(item, dict)]
    return [item for item in parsed if item is not None]


def load_bundled_deployment_catalog() -> List[ImageTemplate]:
    if not BUNDLED_DEPLOYMENT_CATALOG_FILE.is_file():
        return []
    try:
        payload = json.loads(BUNDLED_DEPLOYMENT_CATALOG_FILE.read_text(encoding="utf-8"))
        apps = payload.get("apps", []) if isinstance(payload, dict) else []
        parsed = [image_template_from_dict(item, DEFAULT_DEPLOYMENT_REPOSITORY) for item in apps if isinstance(item, dict)]
        return [item for item in parsed if item is not None]
    except Exception:
        return []


STORE_METADATA_FIELDS = (
    "store_description",
    "store_description_en",
    "features",
    "features_en",
    "icon_url",
    "hero_image_url",
    "gallery",
    "credential_patterns",
    "post_install_hints",
    "post_install_hints_en",
    "build_context",
    "build_dockerfile",
)


def merge_catalog_template(base: ImageTemplate, override: ImageTemplate) -> ImageTemplate:
    data = asdict(override)
    for field_name in STORE_METADATA_FIELDS:
        value = data.get(field_name)
        if value in (None, "", []):
            data[field_name] = getattr(base, field_name, value)
    return ImageTemplate(**data)


def merge_catalog_lists(*catalogs: List[ImageTemplate]) -> List[ImageTemplate]:
    merged: Dict[tuple[str, str], ImageTemplate] = {}
    for catalog in catalogs:
        for item in catalog:
            key = (item.name.lower(), item.image.lower())
            if key in merged:
                merged[key] = merge_catalog_template(merged[key], item)
            else:
                merged[key] = item
    return list(merged.values())


def save_cached_deployment_catalog(items: List[ImageTemplate]) -> None:
    DEPLOYMENT_CATALOG_CACHE_FILE.write_text(
        json.dumps({"apps": [asdict(item) for item in items]}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _catalog_source_candidates(source: str) -> List[str]:
    source = str(source or "").strip()
    if not source:
        return []
    match = re.match(r"^https?://github\.com/([^/]+)/([^/#?]+?)(?:\.git)?/?(?:[?#].*)?$", source, re.IGNORECASE)
    if not match:
        return [source]
    owner, repo = match.group(1), match.group(2)
    return [
        f"https://raw.githubusercontent.com/{owner}/{repo}/main/dcc-catalog.json",
        f"https://raw.githubusercontent.com/{owner}/{repo}/main/catalog.json",
        f"https://raw.githubusercontent.com/{owner}/{repo}/master/dcc-catalog.json",
        f"https://raw.githubusercontent.com/{owner}/{repo}/master/catalog.json",
    ]


def resolve_catalog_media_source(template: Optional[ImageTemplate], value: str) -> str:
    value = str(value or "").strip().replace("\\", "/")
    if not value:
        return ""
    if re.match(r"^https?://", value, re.IGNORECASE):
        return value
    # Prefer bundled/local store assets before falling back to repository raw
    # URLs.  This keeps official app icons available in packaged builds even
    # before catalog media is published remotely.
    for root in (RESOURCE_DIR, Path(__file__).resolve().parent):
        try:
            local_candidate = (root / value).resolve()
            if local_candidate.is_file():
                return local_candidate.as_uri()
        except Exception:
            pass
    source = str(getattr(template, "repository_source", "") or DEFAULT_DEPLOYMENT_REPOSITORY).strip()
    github = re.match(r"^https?://github\.com/([^/]+)/([^/#?]+?)(?:\.git)?/?(?:[?#].*)?$", source, re.IGNORECASE)
    if github:
        owner, repo = github.group(1), github.group(2)
        return f"https://raw.githubusercontent.com/{owner}/{repo}/main/{value.lstrip('/')}"
    try:
        source_path = Path(source).expanduser()
        if source_path.is_file():
            source_path = source_path.parent
        candidate = (source_path / value).resolve()
        if candidate.is_file():
            return candidate.as_uri()
    except Exception:
        pass
    return value


def fetch_deployment_repository(source: str, timeout: int = 10) -> List[ImageTemplate]:
    last_error = ""
    for candidate in _catalog_source_candidates(source):
        try:
            if re.match(r"^https?://", candidate, re.IGNORECASE):
                request = Request(candidate, headers={"User-Agent": f"DCC/{APP_VERSION}"})
                with urlopen(request, timeout=timeout) as response:
                    payload = json.loads(response.read().decode("utf-8", errors="ignore"))
            else:
                path = Path(candidate).expanduser()
                payload = json.loads(path.read_text(encoding="utf-8"))
            apps = payload.get("apps", payload.get("applications", [])) if isinstance(payload, dict) else payload
            if not isinstance(apps, list):
                raise RuntimeError("catalog must contain an apps array")
            parsed = [image_template_from_dict(item, source) for item in apps]
            parsed = [item for item in parsed if item is not None]
            if not parsed:
                raise RuntimeError("catalog contains no valid applications")
            return parsed
        except Exception as exc:
            last_error = str(exc)
    raise RuntimeError(last_error or "deployment catalog could not be loaded")


class CatalogRefreshWorker(QObject):
    finished = pyqtSignal(list, list)

    def __init__(self, sources: List[str], previous_by_source: Dict[str, List[ImageTemplate]]):
        super().__init__()
        self.sources = list(sources)
        self.previous_by_source = {key: list(value) for key, value in previous_by_source.items()}

    def run(self):
        refreshed: List[ImageTemplate] = []
        errors = []
        for source in self.sources:
            try:
                refreshed.extend(fetch_deployment_repository(source))
            except Exception as exc:
                errors.append(f"{source}: {exc}")
                refreshed.extend(self.previous_by_source.get(source, []))
        self.finished.emit(refreshed, errors)


def deployment_catalog_icon(template: ImageTemplate) -> QIcon:
    if template.icon_url:
        source = resolve_catalog_media_source(template, template.icon_url)
        try:
            qurl = QUrl(source)
            if qurl.isLocalFile():
                pixmap = QPixmap(qurl.toLocalFile())
                if not pixmap.isNull():
                    return QIcon(pixmap)
            elif source and not re.match(r"^https?://", source, re.IGNORECASE):
                pixmap = QPixmap(source)
                if not pixmap.isNull():
                    return QIcon(pixmap)
        except Exception:
            pass
    pixmap = QPixmap(44, 44)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    palette = ["#29434e", "#34495e", "#3b4d61", "#40566b", "#354f52", "#4a4458"]
    color = QColor(palette[sum(ord(ch) for ch in template.name) % len(palette)])
    painter.setBrush(QBrush(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, 40, 40, 9, 9)
    painter.setPen(QPen(QColor("#e7f7ff")))
    font = QFont()
    font.setBold(True)
    font.setPointSize(13)
    painter.setFont(font)
    text = (template.icon_text or template.name[:1] or "D").strip()[:2].upper()
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return QIcon(pixmap)


def catalog_category_sort_key(category: str) -> tuple[int, str]:
    text = str(category or "").strip()
    normalized = text.casefold()
    priorities = [
        ("ai", 0),
        ("autom", 1),
        ("low-code", 2),
        ("administr", 3),
        ("monitor", 4),
        ("narz", 5),
        ("tools", 5),
        ("aplikacje www", 6),
        ("web apps", 6),
        ("www", 7),
        ("web /", 7),
        ("devops", 8),
        ("smart home", 9),
        ("media", 10),
        ("network", 11),
        ("sie", 11),
        ("bazy", 12),
        ("databases", 12),
        ("messaging", 13),
        ("cache", 14),
        ("runtime", 15),
        ("baza /", 16),
        ("base /", 16),
        ("balena", 17),
    ]
    for prefix, priority in priorities:
        if normalized.startswith(prefix):
            return priority, normalized
    return 50, normalized


def default_image_catalog() -> List[ImageTemplate]:
    return [
        ImageTemplate(
            "Agent Zero",
            "agent0ai/agent-zero:latest",
            "AI / Agenci",
            "Samodzielny framework agenta AI z webowym interfejsem, narzędziami i trwałą przestrzenią użytkownika.",
            "agent-zero",
            "80",
            "5080",
            extra="-v a0_usr:/a0/usr --restart unless-stopped",
            notes="Po wdrożeniu otwórz panel i skonfiguruj dostawcę/model LLM. Dane użytkownika są przechowywane w volume a0_usr.",
            category_en="AI / Agents",
            description_en="Autonomous AI agent framework with a web UI, tools and persistent user workspace.",
            notes_en="Open the UI after deployment and configure an LLM provider/model. User data is persisted in the a0_usr volume.",
            source_url="https://github.com/agent0ai/agent-zero",
            docs_url="https://github.com/agent0ai/agent-zero/blob/main/docs/setup/installation.md",
            homepage_url="https://www.agent-zero.ai/",
            icon_text="A0",
            engines=["docker"],
        ),
        ImageTemplate(
            "Ollama",
            "ollama/ollama:latest",
            "AI / Runtime",
            "Lokalny serwer modeli LLM z API, dobry jako backend dla Open WebUI i innych aplikacji AI.",
            "ollama",
            "11434",
            "11434",
            extra="-v ollama:/root/.ollama --restart unless-stopped",
            notes="Preset CPU. Akcelerację NVIDIA/AMD możesz później dodać w parametrach uruchomienia zgodnie z dokumentacją Ollama.",
            category_en="AI / Runtime",
            description_en="Local LLM model server with an API, useful as a backend for Open WebUI and other AI applications.",
            notes_en="CPU preset. NVIDIA/AMD acceleration can be added later in the run parameters according to Ollama documentation.",
            source_url="https://github.com/ollama/ollama",
            docs_url="https://github.com/ollama/ollama/blob/main/docs/docker.mdx",
            homepage_url="https://ollama.com/",
            icon_text="OL",
            engines=["docker"],
        ),
        ImageTemplate(
            "NocoDB",
            "nocodb/nocodb:latest",
            "Automatyzacja / Low-code",
            "Self-hosted alternatywa dla Airtable do budowy baz, widoków i prostych workflow bez kodowania.",
            "nocodb",
            "8080",
            "8084",
            extra="-v nocodb_data:/usr/app/data --restart unless-stopped",
            notes="Preset używa lokalnej bazy SQLite i trwałego volume. DCC automatycznie zmieni port hosta, jeśli 8084 jest zajęty.",
            category_en="Automation / Low-code",
            description_en="Self-hosted Airtable alternative for databases, views and lightweight no-code workflows.",
            notes_en="This preset uses local SQLite with a persistent volume. DCC will automatically change host port 8084 if it is occupied.",
            source_url="https://github.com/nocodb/nocodb",
            docs_url="https://docs.nocodb.com/",
            homepage_url="https://nocodb.com/",
            icon_text="NC",
            engines=["docker"],
        ),
        ImageTemplate(
            "Stirling PDF",
            "docker.stirlingpdf.com/stirlingtools/stirling-pdf",
            "Narzędzia / Dokumenty",
            "Rozbudowany, lokalny zestaw narzędzi PDF: edycja, łączenie, OCR, konwersja, podpisywanie i automatyzacje.",
            "stirling-pdf",
            "8080",
            "8091",
            extra="--restart unless-stopped",
            notes="Szybki preset zgodny z oficjalnym Quick Start. Zaawansowaną konfigurację i dodatkowe volume możesz dodać później.",
            category_en="Tools / Documents",
            description_en="Self-hosted PDF toolkit for editing, merging, OCR, conversion, signing and automation.",
            notes_en="Quick preset matching the official Quick Start. Add advanced configuration and extra volumes later if needed.",
            source_url="https://github.com/Stirling-Tools/Stirling-PDF",
            docs_url="https://docs.stirlingpdf.com/",
            homepage_url="https://www.stirlingpdf.com/",
            icon_text="SP",
            engines=["docker"],
        ),
        ImageTemplate(
            "IT-Tools",
            "ghcr.io/corentinth/it-tools:latest",
            "Narzędzia / Developer",
            "Lekki portal z dziesiątkami narzędzi dla programistów i administratorów, działający lokalnie w przeglądarce.",
            "it-tools",
            "80",
            "8092",
            extra="--restart unless-stopped",
            notes="Obraz GHCR obsługuje amd64 i arm64; nadaje się także do kompatybilnych hostów Balena OS.",
            lightweight=True,
            category_en="Tools / Developer",
            description_en="Lightweight portal with dozens of developer and administrator utilities running locally in the browser.",
            notes_en="The GHCR image supports amd64 and arm64 and is also suitable for compatible Balena OS hosts.",
            source_url="https://github.com/CorentinTh/it-tools",
            docs_url="https://github.com/CorentinTh/it-tools#self-host",
            homepage_url="https://it-tools.tech/",
            icon_text="IT",
            engines=["docker", "balena"],
            archs=["x86_64", "amd64", "aarch64", "arm64"],
        ),
        ImageTemplate(
            "Dozzle",
            "amir20/dozzle:latest",
            "Administracja / Logi",
            "Lekki panel do podglądu logów kontenerów w czasie rzeczywistym z informacjami o zasobach.",
            "dozzle",
            "8080",
            "8093",
            extra="-v /var/run/docker.sock:/var/run/docker.sock -v dozzle_data:/data --restart unless-stopped",
            notes="Wymaga dostępu do socketu Docker. Nie wystawiaj panelu publicznie bez skonfigurowania uwierzytelniania.",
            lightweight=True,
            category_en="Administration / Logs",
            description_en="Lightweight real-time container log viewer with resource information.",
            notes_en="Requires access to the Docker socket. Do not expose the UI publicly without configuring authentication.",
            source_url="https://github.com/amir20/dozzle",
            docs_url="https://dozzle.dev/guide/getting-started",
            homepage_url="https://dozzle.dev/",
            icon_text="DZ",
            engines=["docker"],
        ),
        ImageTemplate(
            'SFTPGo Community',
            'ghcr.io/drakkan/sftpgo:2.7.x',
            'Narzędzia / Pliki',
            'Nowoczesny webowy menedżer i bezpieczny serwer transferu plików z obsługą SFTP, HTTP/S, FTP/S i WebDAV.',
            'sftpgo',
            '8080',
            '8094',
            extra='-p 2022:2022 -v sftpgo_data:/srv/sftpgo/data -v sftpgo_home:/var/lib/sftpgo --restart unless-stopped',
            notes='Zastępuje porzucony File Browser jako aktywnie rozwijana opcja do zarządzania i udostępniania plików. Po starcie utwórz administratora w Web Admin; SFTP działa na porcie hosta 2022.',
            lightweight=False,
            category_en='Tools / Files',
            description_en='Modern web file manager and secure file transfer server supporting SFTP, HTTP/S, FTP/S and WebDAV.',
            notes_en='Replaces the abandoned File Browser entry with an actively maintained file-management and transfer option. Create the first administrator in Web Admin; SFTP is exposed on host port 2022.',
            source_url='https://github.com/drakkan/sftpgo',
            docs_url='https://docs.sftpgo.com/latest/',
            homepage_url='https://sftpgo.com/',
            icon_text='SF',
            engines=['docker', 'balena'],
            archs=['x86_64', 'amd64', 'aarch64', 'arm64', 'armv7l', 'armv7', 'armhf', 'arm'],
        ),
        ImageTemplate(
            "Beszel Hub",
            "henrygd/beszel:latest",
            "Monitoring",
            "Lekki hub monitoringu serwerów i kontenerów z nowoczesnym panelem WWW.",
            "beszel",
            "8090",
            "8095",
            extra="-v beszel_data:/beszel_data --restart unless-stopped",
            notes="To jest hub Beszel. Kolejne hosty dodasz z panelu Beszel za pomocą jego agenta.",
            lightweight=True,
            category_en="Monitoring",
            description_en="Lightweight server and container monitoring hub with a modern web dashboard.",
            notes_en="This installs the Beszel hub. Add additional hosts from the Beszel UI using its agent.",
            source_url="https://github.com/henrygd/beszel",
            docs_url="https://beszel.dev/guide/getting-started",
            homepage_url="https://beszel.dev/",
            icon_text="BZ",
            engines=["docker"],
        ),
        ImageTemplate(
            "ChangeDetection.io",
            "dgtlmoon/changedetection.io:latest",
            "Monitoring",
            "Monitor zmian stron WWW, cen, dostępności produktów i treści z historią oraz alertami.",
            "changedetection",
            "5000",
            "5000",
            extra="-v changedetection_data:/datastore --restart unless-stopped",
            notes="Podstawowy tryb HTTP działa w jednym kontenerze. Pełne renderowanie JavaScript może wymagać dodatkowej usługi przeglądarki.",
            category_en="Monitoring",
            description_en="Monitor website changes, prices, restocks and content with history and alerts.",
            notes_en="The basic HTTP mode runs in one container. Full JavaScript rendering can require an additional browser service.",
            source_url="https://github.com/dgtlmoon/changedetection.io",
            docs_url="https://github.com/dgtlmoon/changedetection.io/wiki",
            homepage_url="https://changedetection.io/",
            icon_text="CD",
            engines=["docker"],
        ),
        ImageTemplate(
            'ntfy',
            'binwiederhier/ntfy:latest',
            'Powiadomienia / Push',
            'Lekki self-hosted serwer powiadomień push z prostym API HTTP, Web UI i klientami mobilnymi.',
            'ntfy',
            '80',
            '8100',
            extra='-v ntfy_cache:/var/cache/ntfy --restart unless-stopped',
            command='serve --cache-file /var/cache/ntfy/cache.db',
            notes='Preset zapisuje cache wiadomości w trwałym volume. Dodatkową konfigurację możesz później podłączyć do /etc/ntfy.',
            lightweight=True,
            category_en='Notifications / Push',
            description_en='Lightweight self-hosted push notification server with a simple HTTP API, web UI and mobile clients.',
            notes_en='This preset persists the message cache in a volume. Additional configuration can later be mounted at /etc/ntfy.',
            source_url='https://github.com/binwiederhier/ntfy',
            docs_url='https://docs.ntfy.sh/install/',
            homepage_url='https://ntfy.sh/',
            icon_text='NT',
            engines=['docker', 'balena'],
            archs=['x86_64', 'amd64', 'aarch64', 'arm64', 'armv7l', 'armv7', 'armhf', 'arm', 'armv6'],
        ),
        ImageTemplate(
            'Gotify',
            'gotify/server:latest',
            'Powiadomienia / Push',
            'Serwer powiadomień czasu rzeczywistego z Web UI, REST API i klientami mobilnymi.',
            'gotify',
            '80',
            '8101',
            extra='-v gotify_data:/app/data --restart unless-stopped',
            notes='Dane SQLite, obrazy aplikacji i certyfikaty są przechowywane w trwałym volume /app/data.',
            lightweight=True,
            category_en='Notifications / Push',
            description_en='Real-time notification server with a web UI, REST API and mobile clients.',
            notes_en='SQLite data, application images and certificates are persisted in the /app/data volume.',
            source_url='https://github.com/gotify/server',
            docs_url='https://gotify.net/docs/install',
            homepage_url='https://gotify.net/',
            icon_text='GF',
            engines=['docker', 'balena'],
            archs=['x86_64', 'amd64', 'aarch64', 'arm64', 'armv7l', 'armv7', 'armhf', 'arm'],
        ),
        ImageTemplate(
            'Vaultwarden',
            'vaultwarden/server:latest',
            'Bezpieczeństwo / Hasła',
            'Lekki self-hosted serwer menedżera haseł kompatybilny z klientami Bitwarden.',
            'vaultwarden',
            '80',
            '8102',
            extra='-v vaultwarden_data:/data --restart unless-stopped',
            notes='Dane są przechowywane w /data. Przy dostępie spoza zaufanej sieci wystawiaj usługę przez HTTPS/reverse proxy i regularnie twórz kopie volume.',
            lightweight=True,
            category_en='Security / Passwords',
            description_en='Lightweight self-hosted password manager server compatible with Bitwarden clients.',
            notes_en='Data is persisted in /data. For access outside a trusted network, publish it through HTTPS/reverse proxy and back up the volume regularly.',
            source_url='https://github.com/dani-garcia/vaultwarden',
            docs_url='https://github.com/dani-garcia/vaultwarden/wiki',
            homepage_url='https://github.com/dani-garcia/vaultwarden',
            icon_text='VW',
            engines=['docker', 'balena'],
            archs=['x86_64', 'amd64', 'aarch64', 'arm64', 'armv7l', 'armv7', 'armhf', 'arm', 'armv6'],
        ),
        ImageTemplate(
            'Memos',
            'neosmemo/memos:stable',
            'Produktywność / Notatki',
            'Lekka, prywatna aplikacja do notatek i mikro-dziennika z lokalną bazą SQLite.',
            'memos',
            '5230',
            '5230',
            extra='-v memos_data:/var/opt/memos --restart unless-stopped',
            notes='Używa rekomendowanego tagu stable i trwałego volume. Dobry wybór także dla małych serwerów ARM64.',
            lightweight=True,
            category_en='Productivity / Notes',
            description_en='Lightweight private notes and micro-journal application with a local SQLite database.',
            notes_en='Uses the recommended stable tag and a persistent volume. Also a good fit for small ARM64 servers.',
            source_url='https://github.com/usememos/memos',
            docs_url='https://usememos.com/docs/deploy/docker',
            homepage_url='https://usememos.com/',
            icon_text='MM',
            engines=['docker', 'balena'],
            archs=['x86_64', 'amd64', 'aarch64', 'arm64'],
        ),
        ImageTemplate(
            'Vikunja',
            'vikunja/vikunja:latest',
            'Produktywność / Zadania',
            'Self-hosted menedżer zadań i projektów z listami, Kanbanem, kalendarzem i API.',
            'vikunja',
            '3456',
            '3456',
            extra='-e VIKUNJA_CORS_ENABLE=false -v vikunja_files:/app/vikunja/files -v vikunja_db:/db --restart unless-stopped',
            notes='Preset startuje od razu na SQLite i wyłącza CORS dla prostego użycia lokalnego/LAN. Przy publikacji ustaw VIKUNJA_SERVICE_PUBLICURL i skonfiguruj reverse proxy.',
            lightweight=False,
            category_en='Productivity / Tasks',
            description_en='Self-hosted task and project manager with lists, Kanban, calendar and an API.',
            notes_en='This preset starts immediately with SQLite and disables CORS for simple local/LAN use. For public access set VIKUNJA_SERVICE_PUBLICURL and configure a reverse proxy.',
            source_url='https://github.com/go-vikunja/vikunja',
            docs_url='https://vikunja.io/docs/installing/',
            homepage_url='https://vikunja.io/',
            icon_text='VK',
            engines=['docker'],
        ),
        ImageTemplate(
            'Linkding',
            'sissbruecker/linkding:latest',
            'Produktywność / Zakładki',
            'Minimalistyczny, szybki self-hosted menedżer zakładek z tagami, wyszukiwaniem i API.',
            'linkding',
            '9090',
            '9091',
            extra='-v linkding_data:/etc/linkding/data --restart unless-stopped',
            notes='Baza i konfiguracja są przechowywane w trwałym volume /etc/linkding/data.',
            lightweight=True,
            category_en='Productivity / Bookmarks',
            description_en='Minimal, fast self-hosted bookmark manager with tags, search and an API.',
            notes_en='Database and configuration are persisted in the /etc/linkding/data volume.',
            source_url='https://github.com/sissbruecker/linkding',
            docs_url='https://linkding.link/installation/',
            homepage_url='https://linkding.link/',
            icon_text='LD',
            engines=['docker'],
        ),
        ImageTemplate(
            'Actual Budget',
            'actualbudget/actual-server:latest',
            'Finanse / Budżet',
            'Local-first, darmowa i open-source aplikacja do budżetu osobistego z synchronizacją między urządzeniami.',
            'actual-budget',
            '5006',
            '5006',
            extra='-v actual_data:/data --restart unless-stopped',
            notes='Używa oficjalnego obrazu latest i zapisuje dane w /data. Dla dostępu zdalnego skonfiguruj HTTPS/reverse proxy.',
            lightweight=True,
            category_en='Finance / Budgeting',
            description_en='Local-first, free and open-source personal budgeting application with cross-device sync.',
            notes_en='Uses the official latest image and persists data in /data. Configure HTTPS/reverse proxy for remote access.',
            source_url='https://github.com/actualbudget/actual',
            docs_url='https://actualbudget.org/docs/install/docker/',
            homepage_url='https://actualbudget.org/',
            icon_text='AB',
            engines=['docker'],
        ),
        ImageTemplate(
            'CyberChef',
            'ghcr.io/gchq/cyberchef:latest',
            'Bezpieczeństwo / Narzędzia',
            'Przeglądarkowy zestaw operacji do kodowania, dekodowania, szyfrowania, kompresji i analizy danych.',
            'cyberchef',
            '8080',
            '8103',
            extra='--restart unless-stopped',
            notes='Gotowy oficjalny obraz GHCR; działa lokalnie bez potrzeby instalowania toolchainu Node.js.',
            lightweight=False,
            category_en='Security / Tools',
            description_en='Browser-based toolkit for encoding, decoding, encryption, compression and data analysis.',
            notes_en='Official pre-built GHCR image; runs locally without installing the Node.js toolchain.',
            source_url='https://github.com/gchq/CyberChef',
            docs_url='https://github.com/gchq/CyberChef',
            homepage_url='https://gchq.github.io/CyberChef/',
            icon_text='CC',
            engines=['docker'],
        ),
        ImageTemplate(
            'OpenSpeedTest',
            'openspeedtest/latest',
            'Sieć / Diagnostyka',
            'Self-hosted test prędkości sieci działający w przeglądarce, przydatny do LAN, VPN, Wi-Fi i zdalnych serwerów.',
            'openspeedtest',
            '3000',
            '3004',
            extra='-p 3005:3001 --restart unless-stopped',
            notes='HTTP jest dostępne na porcie hosta 3004, a drugi port kontenera 3001 jest mapowany na 3005.',
            lightweight=True,
            category_en='Network / Diagnostics',
            description_en='Self-hosted browser-based network speed test useful for LAN, VPN, Wi-Fi and remote servers.',
            notes_en="HTTP is available on host port 3004, while the container's second port 3001 is mapped to host port 3005.",
            source_url='https://github.com/openspeedtest/Speed-Test',
            docs_url='https://github.com/openspeedtest/Speed-Test',
            homepage_url='https://openspeedtest.com/',
            icon_text='OS',
            engines=['docker'],
        ),
        ImageTemplate(
            'AdGuard Home',
            'adguard/adguardhome:latest',
            'Sieć / DNS',
            'Self-hosted serwer DNS do blokowania reklam i trackerów w całej sieci z nowoczesnym panelem WWW.',
            'adguard-home',
            '3000',
            '3006',
            extra='-p 53:53/tcp -p 53:53/udp -p 8104:80/tcp -v adguard_work:/opt/adguardhome/work -v adguard_conf:/opt/adguardhome/conf --restart unless-stopped',
            notes='Pierwsza konfiguracja jest na porcie 3006. Port DNS 53 musi być wolny; po konfiguracji panel HTTP może być dostępny także na porcie hosta 8104.',
            lightweight=True,
            category_en='Network / DNS',
            description_en='Self-hosted DNS server for network-wide ad and tracker blocking with a modern web dashboard.',
            notes_en='Initial setup is on host port 3006. DNS port 53 must be free; after setup the HTTP admin UI can also be available on host port 8104.',
            source_url='https://github.com/AdguardTeam/AdGuardHome',
            docs_url='https://github.com/AdguardTeam/AdGuardHome/wiki/Docker',
            homepage_url='https://adguard.com/adguard-home/overview.html',
            icon_text='AG',
            engines=['docker', 'balena'],
            archs=['x86_64', 'amd64', 'x86', 'i386', 'aarch64', 'arm64', 'armv7l', 'armv7', 'armhf', 'arm', 'armv6'],
        ),
        ImageTemplate("Alpine Linux", "alpine:latest", "Baza / System", "Minimalny obraz systemowy (Alpine Linux).", "alpine", "", "", notes="Bardzo lekki, dobry na Raspberry Pi.", lightweight=True, category_en="Base / System", description_en="Minimal base image (Alpine Linux).", notes_en="Very lightweight, great for low-end devices."),
        ImageTemplate("Debian", "debian:bookworm", "Baza / System", "Stabilny system bazowy (Debian Bookworm).", "debian", "", "", notes="Dobry kompromis miedzy rozmiarem a kompatybilnoscia.", category_en="Base / System", description_en="Stable base system (Debian Bookworm).", notes_en="Good balance of size and compatibility."),
        ImageTemplate("Ubuntu", "ubuntu:24.04", "Baza / System", "Popularny system bazowy (Ubuntu 24.04).", "ubuntu", "", "", notes="Latwy start do aplikacji Linux.", category_en="Base / System", description_en="Popular base system (Ubuntu 24.04).", notes_en="Easy starting point for Linux apps."),
        ImageTemplate("BusyBox", "busybox:latest", "Baza / System", "Najmniejszy obraz narzedziowy.", "busybox", "", "", notes="Idealny do testow i narzedzi.", lightweight=True, category_en="Base / System", description_en="Tiny utility image.", notes_en="Great for tests and tooling."),
        ImageTemplate("Node.js", "node:24-alpine", "Runtime / Dev", "Runtime Node.js dla aplikacji JS.", "node-app", "", "", notes="Wersja alpine jest lekka.", lightweight=True, category_en="Runtime / Dev", description_en="Node.js runtime for JavaScript apps.", notes_en="Alpine variant is lightweight."),
        ImageTemplate("Python", "python:3.12-slim", "Runtime / Dev", "Runtime Python do aplikacji i skryptow.", "python-app", "", "", notes="Slim to mniejszy obraz.", category_en="Runtime / Dev", description_en="Python runtime for apps and scripts.", notes_en="Slim variant is smaller."),
        ImageTemplate("Golang", "golang:1.27-alpine", "Runtime / Dev", "Golang toolchain do budowy i uruchamiania aplikacji.", "go-app", "", "", notes="Lekki obraz do projektow Go.", lightweight=True, category_en="Runtime / Dev", description_en="Golang toolchain for building and running apps.", notes_en="Lightweight image for Go projects."),
        ImageTemplate("Apache HTTPD", "httpd:2.4", "WWW / Proxy", "Serwer HTTP Apache.", "apache", "80", "8083", category_en="Web / Proxy", description_en="Apache HTTP server."),
        ImageTemplate("PostgreSQL", "postgres:16", "Bazy danych", "Popularna relacyjna baza danych.", "postgres", "5432", "5432", extra="-e POSTGRES_PASSWORD=changeme -v postgres_data:/var/lib/postgresql/data", notes="Ustaw haslo i dane dostepu.", category_en="Databases", description_en="Popular relational database.", notes_en="Set password and access details."),
        ImageTemplate("MySQL", "mysql:8.0", "Bazy danych", "Relacyjna baza danych MySQL.", "mysql", "3306", "3307", extra="-e MYSQL_ROOT_PASSWORD=changeme -v mysql_data:/var/lib/mysql", notes="Zmien domyslne haslo.", category_en="Databases", description_en="MySQL relational database.", notes_en="Change the default password."),
        ImageTemplate("MongoDB", "mongo:7", "Bazy danych", "Baza danych dokumentowa MongoDB.", "mongo", "27017", "27017", extra="-v mongo_data:/data/db", category_en="Databases", description_en="MongoDB document database."),
        ImageTemplate("RabbitMQ", "rabbitmq:3-management", "Messaging", "Broker kolejek z panelem WWW.", "rabbitmq", "5672", "5672", extra="-p 15672:15672", notes="Panel WWW na porcie 15672.", category_en="Messaging", description_en="Message broker with web UI.", notes_en="Web UI on port 15672."),
        ImageTemplate("NATS", "nats:latest", "Messaging", "Lekki broker wiadomosci.", "nats", "4222", "4222", extra="-p 8222:8222", notes="Monitoring na porcie 8222.", category_en="Messaging", description_en="Lightweight messaging broker.", notes_en="Monitoring on port 8222."),
        ImageTemplate("Memcached", "memcached:latest", "Cache", "Lekki cache w pamieci.", "memcached", "11211", "11211", lightweight=True, category_en="Cache", description_en="Lightweight in-memory cache."),
        ImageTemplate("WordPress", "wordpress:latest", "Aplikacje WWW", "Popularny CMS do stron i blogow.", "wordpress", "80", "8086", notes="Wymaga bazy MySQL/MariaDB.", category_en="Web Apps", description_en="Popular CMS for websites and blogs.", notes_en="Requires MySQL/MariaDB."),
        ImageTemplate("Nextcloud", "nextcloud:latest", "Aplikacje WWW", "Self-hosted chmura plikow.", "nextcloud", "80", "8087", extra="-v nextcloud_data:/var/www/html", notes="Wymaga bazy danych.", category_en="Web Apps", description_en="Self-hosted file cloud.", notes_en="Requires a database."),
        ImageTemplate("Open WebUI", "ghcr.io/open-webui/open-webui:main", "AI / UI", "Interfejs webowy do modeli i lokalnych pipeline'ow AI.", "open-webui", "8080", "3000", notes="Dobra para z Ollama albo OpenAI API.", category_en="AI / UI", description_en="Web interface for AI models and local AI pipelines.", notes_en="Great pair with Ollama or OpenAI API.", source_url="https://github.com/open-webui/open-webui", docs_url="https://docs.openwebui.com/", homepage_url="https://openwebui.com/", icon_text="OW"),
        ImageTemplate("Vane (dawniej Perplexica)", "itzcrazykns1337/vane:latest", "AI / Search", "Prywatna wyszukiwarka i silnik odpowiedzi AI, projekt znany wcześniej jako Perplexica.", "vane", "3000", "3100", extra="-v vane-data:/home/vane/data --restart unless-stopped", notes="Aktualny oficjalny sposób instalacji używa obrazu itzcrazykns1337/vane:latest z trwałym volume vane-data. Obraz zawiera wbudowany SearXNG; modele i klucze konfigurujesz po uruchomieniu.", category_en="AI / Search", description_en="Privacy-focused AI answering engine formerly known as Perplexica.", notes_en="The current official Docker install uses itzcrazykns1337/vane:latest with persistent vane-data. The image bundles SearXNG; configure models and API keys after deployment.", source_url="https://github.com/ItzCrazyKns/Vane", docs_url="https://github.com/ItzCrazyKns/Vane/tree/master/docs/installation", homepage_url="https://github.com/ItzCrazyKns/Vane", icon_text="VA"),
        ImageTemplate("SearXNG", "searxng/searxng:latest", "AI / Search", "Meta-wyszukiwarka prywatnosciowa dla self-hostingu.", "searxng", "8080", "8888", notes="Przydatna jako backend wyszukiwania dla narzedzi AI.", category_en="AI / Search", description_en="Privacy-focused metasearch engine for self-hosting.", notes_en="Useful as a search backend for AI tools.", source_url="https://github.com/searxng/searxng", docs_url="https://docs.searxng.org/", homepage_url="https://searxng.org/", icon_text="SX"),
        ImageTemplate("Portainer CE", "portainer/portainer-ce:latest", "Administracja", "Panel administracyjny do Docker i kontenerow.", "portainer", "9000", "9000", extra="-p 9443:9443 -v portainer_data:/data -v /var/run/docker.sock:/var/run/docker.sock", notes="Dziala na x86 i ARM, dobre rowniez na Raspberry Pi.", category_en="Administration", description_en="Administration panel for Docker and containers.", notes_en="Runs on x86 and ARM, including Raspberry Pi.", source_url="https://github.com/portainer/portainer", docs_url="https://docs.portainer.io/", homepage_url="https://www.portainer.io/", icon_text="PT"),
        ImageTemplate("Nginx", "nginx:alpine", "WWW / Proxy", "Lekki serwer WWW i reverse proxy.", "nginx", "80", "8080", lightweight=True, notes="Wersja alpine jest lekka i dobra na slabsze maszyny.", category_en="Web / Proxy", description_en="Lightweight web server and reverse proxy.", notes_en="Alpine image is lightweight and great for low-end hardware."),
        ImageTemplate("Caddy", "caddy:alpine", "WWW / Proxy", "Nowoczesny reverse proxy z prostym HTTPS.", "caddy", "80", "8081", lightweight=True, notes="Bardzo wygodny do szybkich wdrozen stron i API.", category_en="Web / Proxy", description_en="Modern reverse proxy with simple HTTPS setup.", notes_en="Very convenient for quick website and API deployments."),
        ImageTemplate("Redis", "redis:7-alpine", "Bazy danych", "Lekka baza key-value i cache.", "redis", "6379", "6379", lightweight=True, category_en="Databases", description_en="Lightweight key-value database and cache."),
        ImageTemplate("MariaDB", "mariadb:11", "Bazy danych", "MySQL-compatible baza danych dla aplikacji self-hosted.", "mariadb", "3306", "3306", extra="-e MARIADB_ROOT_PASSWORD=changeme -v mariadb_data:/var/lib/mysql", category_en="Databases", description_en="MySQL-compatible database for self-hosted applications."),
        ImageTemplate("Adminer", "adminer:latest", "Bazy danych", "Lekki panel WWW do baz danych.", "adminer", "8080", "8082", lightweight=True, category_en="Databases", description_en="Lightweight web panel for database management."),
        ImageTemplate("Eclipse Mosquitto", "eclipse-mosquitto:2", "Smart Home / IoT", "Broker MQTT dla IoT i Home Assistant.", "mosquitto", "1883", "1883", lightweight=True, notes="Dobry wybor dla slabszych maszyn i Raspberry Pi 3; dostepny rowniez w katalogu hostow Balena.", category_en="Smart Home / IoT", description_en="MQTT broker for IoT and Home Assistant.", notes_en="Good choice for low-end devices and Raspberry Pi 3; also available for Balena hosts.", engines=["docker", "balena"], archs=["x86_64", "amd64", "aarch64", "arm64", "armv7l", "armv7", "armhf", "arm"]),
        ImageTemplate("Node-RED", "nodered/node-red:latest", "Smart Home / IoT", "Wizualna automatyzacja workflow i integracji.", "node-red", "1880", "1880", extra="-v node_red_data:/data --restart unless-stopped", notes="Oficjalny obraz jest wieloarchitekturowy i nadaje sie do Raspberry Pi; dostepny rowniez dla hostow Balena.", category_en="Smart Home / IoT", description_en="Visual workflow automation and integrations.", notes_en="The official image is multi-architecture and Raspberry Pi friendly; also available for Balena hosts.", engines=["docker", "balena"], archs=["x86_64", "amd64", "aarch64", "arm64", "armv7l", "armv7", "armhf", "arm"]),
        ImageTemplate("Gitea", "gitea/gitea:latest", "DevOps", "Lekki self-hosted Git server.", "gitea", "3000", "3001", extra="-p 2222:22 -v gitea:/data", notes="Przyjazny dla Raspberry Pi i slabego sprzetu.", category_en="DevOps", description_en="Lightweight self-hosted Git server.", notes_en="Friendly for Raspberry Pi and low-end hardware.", source_url="https://github.com/go-gitea/gitea", docs_url="https://docs.gitea.com/", homepage_url="https://about.gitea.com/", icon_text="GT"),
        ImageTemplate("Jellyfin", "linuxserver/jellyfin:latest", "Media", "Self-hosted media server z obsluga ARM i x86.", "jellyfin", "8096", "8096", extra="-v jellyfin_config:/config -v jellyfin_cache:/cache", notes="Aby dodac muzyke z Windows, dopisz w Dodatkowe parametry mount typu -v C:/TwojaMuzyka:/data/music:ro i potem w Jellyfin wskaz folder /data/music. Na slabszych maszynach ogranicz transkodowanie.", category_en="Media", description_en="Self-hosted media server with ARM and x86 support.", notes_en="To expose Windows music, add -v C:/YourMusic:/data/music:ro in Extra parameters and then add /data/music in Jellyfin. On low-end hardware, limit transcoding.", source_url="https://github.com/jellyfin/jellyfin", docs_url="https://jellyfin.org/docs/", homepage_url="https://jellyfin.org/", icon_text="JF"),
        ImageTemplate("Uptime Kuma", "louislam/uptime-kuma:2", "Monitoring", "Monitoring stron i uslug z prostym dashboardem.", "uptime-kuma", "3001", "3002", extra="-v uptime_kuma:/app/data", notes="Bardzo lekki do domowego monitoringu.", category_en="Monitoring", description_en="Website and service monitoring with a simple dashboard.", notes_en="Very lightweight for home monitoring.", source_url="https://github.com/louislam/uptime-kuma", homepage_url="https://uptime.kuma.pet/", icon_text="UK"),
        ImageTemplate("Pi-hole", "pihole/pihole:latest", "Network / DNS", "Blokowanie reklam i DNS sinkhole.", "pihole", "80", "8088", extra="-e TZ=Europe/Warsaw -p 53:53/tcp -p 53:53/udp -p 67:67/udp -v pihole_data:/etc/pihole -v pihole_dnsmasq:/etc/dnsmasq.d", notes="Lekki i bardzo popularny. Idealny na Raspberry Pi.", lightweight=True, category_en="Network / DNS", description_en="Ad blocking DNS sinkhole and web UI.", notes_en="Lightweight and very popular. Great for Raspberry Pi."),
        ImageTemplate("Home Assistant", "homeassistant/home-assistant:stable", "Smart Home / IoT", "Centrum automatyzacji smart home.", "home-assistant", "8123", "8123", extra="--network=host", notes="Wymaga trybu host. Zalecany mocniejszy sprzet lub Raspberry Pi 4+.", category_en="Smart Home / IoT", description_en="Smart home automation hub.", notes_en="Requires host network mode. Recommended on stronger hardware or Raspberry Pi 4+."),
        ImageTemplate("Grafana", "grafana/grafana:latest", "Monitoring", "Dashboardy i wizualizacja metryk.", "grafana", "3000", "3003", extra="-v grafana_data:/var/lib/grafana", notes="Dobre do monitoringu na NAS/serwerze. Wymaga wiecej RAM.", category_en="Monitoring", description_en="Metrics dashboards and visualization.", notes_en="Great for NAS/server monitoring. Needs more RAM."),
        ImageTemplate("Prometheus", "prom/prometheus:latest", "Monitoring", "Zbieranie metryk i alerty.", "prometheus", "9090", "9090", extra="-v prometheus_data:/prometheus", notes="Popularny backend metryk. Na slabszym sprzecie ogranicz retention.", category_en="Monitoring", description_en="Metrics collection and alerting.", notes_en="Popular metrics backend. On low-end hardware, reduce retention."),
        ImageTemplate("InfluxDB", "influxdb:2", "Bazy danych", "Baza danych time-series dla IoT i monitoringu.", "influxdb", "8086", "8086", extra="-v influxdb_data:/var/lib/influxdb2", notes="Wersja 2.x jest ciezsza - lepiej na mocniejszy sprzet.", category_en="Databases", description_en="Time-series database for IoT and monitoring.", notes_en="2.x is heavier - best on stronger hardware."),
        ImageTemplate("Plex Media Server", "plexinc/pms-docker:latest", "Media", "Serwer multimedialny Plex (x86_64).", "plex", "32400", "32400", extra="-v plex_config:/config -v plex_transcode:/transcode", notes="Wymaga mocniejszego CPU, szczegolnie przy transkodowaniu. Dobre na Windows/x86_64.", category_en="Media", description_en="Plex media server (x86_64).", notes_en="Needs stronger CPU, especially for transcoding. Good on Windows/x86_64."),
    ]

def fetch_docker_hub_description(image: str) -> Optional[str]:
    repo = image.split(":", 1)[0].strip()
    if not repo:
        return None
    namespace, name = ("library", repo) if "/" not in repo else repo.split("/", 1)
    url = f"https://hub.docker.com/v2/repositories/{quote(namespace)}/{quote(name)}/"
    request = Request(url, headers={"User-Agent": "Docker-Control-Center/1.0"})
    with urlopen(request, timeout=6) as response:
        payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    description = payload.get("description") or payload.get("full_description") or ""
    return description.strip() or None



def normalize_docker_command_text(raw: str) -> str:
    raw = str(raw or "").strip()
    raw = re.sub(r"\\s*\\^\\s*\\r?\\n+\\s*", " ", raw)
    raw = re.sub(r"\\\\\\s*\\r?\\n+\\s*", " ", raw)
    raw = re.sub(r"\\r?\\n+", " ", raw)
    raw = re.sub(r"\\s{2,}", " ", raw)
    return raw.strip()


    return raw.strip()


def request_json(url: str, headers: Optional[Dict[str, str]] = None, payload: Optional[Dict] = None, timeout: int = 20) -> Dict:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, method="POST" if data is not None else "GET")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="ignore") or "{}")


def fetch_ollama_models(base_url: str) -> List[str]:
    payload = request_json(
        f"{base_url.rstrip('/')}/api/tags",
        headers={"User-Agent": "Docker-Control-Center/1.0"},
        timeout=8,
    )
    models = []
    for item in payload.get("models", []) or []:
        name = str(item.get("name") or "").strip()
        if name and name not in models:
            models.append(name)
    if not models:
        raise RuntimeError("Ollama is reachable, but no local models are installed.")
    return models


def select_ollama_fallback_model(models: List[str]) -> str:
    cleaned = [str(model).strip() for model in models if str(model).strip()]
    if not cleaned:
        raise RuntimeError("No local Ollama model is available.")
    preferred = [
        "qwen3:4b-instruct",
        "qwen2.5-coder:7b",
        "qwen3:1.7b",
        "llama3.2",
    ]
    by_lower = {model.lower(): model for model in cleaned}
    for wanted in preferred:
        if wanted.lower() in by_lower:
            return by_lower[wanted.lower()]
    for model in cleaned:
        lower = model.lower()
        if "coder" in lower or "instruct" in lower:
            return model
    return cleaned[0]


def fetch_openai_models(api_key: str) -> List[str]:
    if not api_key.strip():
        raise RuntimeError("OpenAI API key is missing")
    return fetch_openai_compatible_models("openai", "https://api.openai.com/v1", api_key)


def llm_default_models(provider: str) -> List[str]:
    provider = str(provider or "ollama").strip().lower()
    return list(LLM_DEFAULT_MODELS.get(provider) or DEFAULT_OLLAMA_MODELS)


def llm_model_setting_key(provider: str) -> str:
    return f"llm/{str(provider or 'ollama').strip().lower()}_model"


def llm_secret_key(provider: str) -> str:
    return f"llm/{str(provider or '').strip().lower()}_api_key"


def _model_is_text_generation_candidate(provider: str, model_id: str) -> bool:
    provider = str(provider or "").lower()
    model_id = str(model_id or "").strip()
    lower = model_id.lower()
    if not model_id:
        return False
    if provider == "openai":
        if not re.match(r"^(gpt-|chatgpt-|o\d)", lower):
            return False
        return not any(token in lower for token in ("embedding", "moderation", "transcribe", "tts", "realtime", "image"))
    if provider == "xai":
        return lower.startswith("grok")
    if provider == "deepseek":
        return lower.startswith("deepseek")
    if provider == "groq":
        return not any(token in lower for token in ("whisper", "tts"))
    if provider == "mistral":
        return not any(token in lower for token in ("embed", "ocr", "transcribe", "tts"))
    return True


def fetch_openai_compatible_models(provider: str, base_url: str, api_key: str) -> List[str]:
    if not api_key.strip():
        raise RuntimeError(f"{provider} API key is missing")
    payload = request_json(
        f"{base_url.rstrip('/')}/models",
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "User-Agent": f"Docker-Control-Center/{APP_VERSION}",
        },
        timeout=15,
    )
    models: List[str] = []
    for item in payload.get("data", []) or []:
        model_id = str((item or {}).get("id") or "").strip()
        if _model_is_text_generation_candidate(provider, model_id) and model_id not in models:
            models.append(model_id)
    if not models:
        raise RuntimeError("The provider returned no text-generation models.")
    return models


def fetch_anthropic_models(api_key: str) -> List[str]:
    if not api_key.strip():
        raise RuntimeError("Anthropic API key is missing")
    payload = request_json(
        "https://api.anthropic.com/v1/models?limit=1000",
        headers={
            "x-api-key": api_key.strip(),
            "anthropic-version": "2023-06-01",
            "User-Agent": f"Docker-Control-Center/{APP_VERSION}",
        },
        timeout=15,
    )
    models = []
    for item in payload.get("data", []) or []:
        model_id = str((item or {}).get("id") or "").strip()
        if model_id.startswith("claude-") and model_id not in models:
            models.append(model_id)
    if not models:
        raise RuntimeError("Anthropic returned no Claude models.")
    return models


def fetch_gemini_models(api_key: str) -> List[str]:
    if not api_key.strip():
        raise RuntimeError("Gemini API key is missing")
    payload = request_json(
        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
        headers={
            "x-goog-api-key": api_key.strip(),
            "User-Agent": f"Docker-Control-Center/{APP_VERSION}",
        },
        timeout=15,
    )
    models = []
    excluded = ("embedding", "image", "live", "tts", "transcribe", "robotics", "lyria", "veo", "imagen", "deep-research", "antigravity")
    for item in payload.get("models", []) or []:
        methods = [str(value) for value in ((item or {}).get("supportedGenerationMethods") or [])]
        if "generateContent" not in methods:
            continue
        model_id = str((item or {}).get("name") or "").strip()
        if model_id.startswith("models/"):
            model_id = model_id[len("models/"):]
        lower = model_id.lower()
        if model_id and not any(token in lower for token in excluded) and model_id not in models:
            models.append(model_id)
    if not models:
        raise RuntimeError("Gemini returned no models that support generateContent.")
    return models


def fetch_provider_models(provider: str, api_key: str = "", ollama_url: str = "") -> List[str]:
    provider = str(provider or "ollama").strip().lower()
    if provider == "ollama":
        return fetch_ollama_models(ollama_url or "http://127.0.0.1:11434")
    if provider == "openai":
        return fetch_openai_models(api_key)
    if provider == "anthropic":
        return fetch_anthropic_models(api_key)
    if provider == "gemini":
        return fetch_gemini_models(api_key)
    base_url = LLM_OPENAI_COMPATIBLE_BASE_URLS.get(provider)
    if not base_url:
        raise RuntimeError(f"Unsupported LLM provider: {provider}")
    return fetch_openai_compatible_models(provider, base_url, api_key)


def extract_docker_run_command(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = cleaned.replace("```bash", "```").replace("```sh", "```").replace("```powershell", "```")
    if "```" in cleaned:
        for part in [chunk.strip() for chunk in cleaned.split("```") if chunk.strip()]:
            if "docker run" in part.lower() or "balena run" in part.lower():
                cleaned = part
                break
    cleaned = normalize_docker_command_text(cleaned)
    match = re.search(r"(docker|balena)\s+run\b.*", cleaned, re.IGNORECASE)
    if match:
        return normalize_docker_command_text(match.group(0))
    return cleaned


def parse_run_command_text(command: str) -> tuple[str, List[str]]:
    cleaned = normalize_docker_command_text(extract_docker_run_command(command))
    tokens = shlex.split(cleaned)
    if len(tokens) >= 2 and tokens[0].lower() in {"docker", "balena"} and tokens[1].lower() == "run":
        return tokens[0].lower(), tokens[2:]
    if tokens and tokens[0].lower() == "run":
        return "docker", tokens[1:]
    raise RuntimeError("Expected a docker run or balena run command.")


def published_host_ports(args: List[str]) -> List[str]:
    ports: List[str] = []
    i = 0
    while i < len(args):
        token = str(args[i])
        value = ""
        if token in {"-p", "--publish"} and i + 1 < len(args):
            value = str(args[i + 1])
            i += 2
        elif token.startswith("--publish="):
            value = token.split("=", 1)[1]
            i += 1
        elif token.startswith("-p") and token != "-p":
            value = token[2:]
            i += 1
        else:
            i += 1
        if not value:
            continue
        parts = value.rsplit(":", 2)
        host_port = parts[-2] if len(parts) >= 2 else ""
        host_port = host_port.split("-")[0].strip()
        if host_port.isdigit() and host_port not in ports:
            ports.append(host_port)
    return ports


def _publish_parts(value: str) -> Optional[tuple[str, str, str]]:
    raw = str(value or "").strip()
    parts = raw.rsplit(":", 2)
    if len(parts) == 2:
        host_ip, host_port, container_part = "", parts[0], parts[1]
    elif len(parts) == 3:
        host_ip, host_port, container_part = parts[0], parts[1], parts[2]
    else:
        return None
    if not host_port.isdigit() or "-" in host_port:
        return None
    return host_ip, host_port, container_part


def _replace_publish_host_port(value: str, new_port: str) -> str:
    parsed = _publish_parts(value)
    if not parsed:
        return value
    host_ip, _old_port, container_part = parsed
    if host_ip:
        return f"{host_ip}:{new_port}:{container_part}"
    return f"{new_port}:{container_part}"


def _next_free_host_port(preferred: int, reserved: set[str]) -> str:
    start = max(1024, min(65535, int(preferred) + 1))
    for candidate in range(start, 65536):
        if str(candidate) not in reserved:
            return str(candidate)
    for candidate in range(1024, start):
        if str(candidate) not in reserved:
            return str(candidate)
    raise RuntimeError("No free host port is available.")


def safe_repair_run_args(args: List[str], port_usage: Dict[str, List[str]], container_names: List[str], ignore_name: str = "") -> tuple[List[str], List[tuple[str, str, str]]]:
    """Resolve only deterministic conflicts. Never changes images, mounts, env vars or volumes."""
    repaired = list(args)
    changes: List[tuple[str, str, str]] = []
    names = {str(name).lstrip("/") for name in container_names if str(name).strip()}
    if ignore_name:
        names.discard(ignore_name.lstrip("/"))

    index = 0
    while index < len(repaired):
        token = str(repaired[index])
        current_name = ""
        if token == "--name" and index + 1 < len(repaired):
            current_name = str(repaired[index + 1]).strip()
            if current_name and current_name in names:
                suffix = 2
                candidate = f"{current_name}-{suffix}"
                while candidate in names:
                    suffix += 1
                    candidate = f"{current_name}-{suffix}"
                repaired[index + 1] = candidate
                names.add(candidate)
                changes.append(("name", current_name, candidate))
            index += 2
            continue
        if token.startswith("--name="):
            current_name = token.split("=", 1)[1].strip()
            if current_name and current_name in names:
                suffix = 2
                candidate = f"{current_name}-{suffix}"
                while candidate in names:
                    suffix += 1
                    candidate = f"{current_name}-{suffix}"
                repaired[index] = f"--name={candidate}"
                names.add(candidate)
                changes.append(("name", current_name, candidate))
        index += 1

    reserved = {str(port) for port in port_usage.keys()}
    index = 0
    while index < len(repaired):
        token = str(repaired[index])
        value_index = -1
        inline_prefix = ""
        value = ""
        if token in {"-p", "--publish"} and index + 1 < len(repaired):
            value_index = index + 1
            value = str(repaired[value_index])
            index += 2
        elif token.startswith("--publish="):
            inline_prefix = "--publish="
            value = token.split("=", 1)[1]
            value_index = index
            index += 1
        elif token.startswith("-p") and token != "-p":
            inline_prefix = "-p"
            value = token[2:]
            value_index = index
            index += 1
        else:
            index += 1
            continue
        parsed = _publish_parts(value)
        if not parsed:
            continue
        _host_ip, host_port, _container_part = parsed
        if host_port == "0":
            continue
        new_value = value
        if host_port in reserved:
            new_port = _next_free_host_port(int(host_port), reserved)
            new_value = _replace_publish_host_port(value, new_port)
            changes.append(("port", host_port, new_port))
            host_port = new_port
        reserved.add(host_port)
        if value_index >= 0 and new_value != value:
            repaired[value_index] = f"{inline_prefix}{new_value}" if inline_prefix else new_value
    return repaired, changes


def risky_run_options(args: List[str]) -> List[str]:
    """Return human-readable reasons for options that grant broad host access."""
    text = " ".join(str(part) for part in args)
    lower = text.lower()
    risks = []
    checks = [
        ("--privileged", "--privileged"),
        ("--pid=host", "host PID namespace"),
        ("--network=host", "host network"),
        ("--ipc=host", "host IPC namespace"),
        ("--cap-add=sys_admin", "SYS_ADMIN capability"),
        ("--cap-add sys_admin", "SYS_ADMIN capability"),
        ("/var/run/docker.sock", "Docker socket mount"),
    ]
    for needle, label in checks:
        if needle in lower and label not in risks:
            risks.append(label)
    for index, token in enumerate(args):
        token = str(token)
        value = ""
        if token in {"--device", "-v", "--volume", "--mount"} and index + 1 < len(args):
            value = str(args[index + 1])
        elif token.startswith("--device=") or token.startswith("--volume=") or token.startswith("--mount="):
            value = token.split("=", 1)[1]
        if token == "--device" or token.startswith("--device="):
            label = f"host device: {value or token}"
            if label not in risks:
                risks.append(label)
        if value and token in {"-v", "--volume"}:
            host_path = value.split(":", 1)[0].strip()
            if host_path in {"/", "C:/", "C:\\"}:
                label = f"host root mount: {host_path}"
                if label not in risks:
                    risks.append(label)
    return risks


def parse_os_release(text: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip().upper()] = value.replace(r"\n", " ").strip()
    return values


def clean_system_name(value: str) -> str:
    text = str(value or "").replace("\\l", "").replace("\\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \\t\\r\\n\\\"")


def ssh_optional(client, command: str) -> str:
    try:
        return str(client.run_ssh(command) or "").strip()
    except Exception:
        return ""


def detect_remote_system_info(client) -> tuple[str, str]:
    """Best-effort host OS/architecture detection for Docker API and SSH backends."""
    os_name = ""
    arch = ""

    try:
        info = client.info()
        os_name = clean_system_name(info.get("OperatingSystem") or info.get("OSType") or "")
        arch = clean_system_name(info.get("Architecture") or "").lower()
    except Exception:
        pass

    if not hasattr(client, "run_ssh"):
        return os_name, arch

    release_text = ssh_optional(
        client,
        "cat /etc/os-release 2>/dev/null || cat /usr/lib/os-release 2>/dev/null || true",
    )
    release = parse_os_release(release_text)
    pretty_name = clean_system_name(release.get("PRETTY_NAME", ""))
    distro_name = clean_system_name(release.get("NAME", ""))
    version = clean_system_name(release.get("VERSION_ID", "") or release.get("VERSION", ""))
    distro_id = clean_system_name(release.get("ID", "")).lower()
    distro_like = clean_system_name(release.get("ID_LIKE", "")).lower()
    release_markers = " ".join([pretty_name, distro_name, distro_id, distro_like]).lower()

    if pretty_name:
        os_name = pretty_name
    elif distro_name:
        os_name = f"{distro_name} {version}".strip()

    if not os_name:
        fallbacks = [
            ("lsb_release -ds 2>/dev/null || true", ""),
            ("cat /etc/balena-release 2>/dev/null || cat /etc/resin-release 2>/dev/null || true", "balenaOS "),
            ("cat /etc/debian_version 2>/dev/null || true", "Debian "),
            ("cat /etc/alpine-release 2>/dev/null || true", "Alpine Linux "),
            (". /etc/openwrt_release 2>/dev/null; printf '%s' \"${DISTRIB_DESCRIPTION:-}\"", ""),
            ("cat /etc/redhat-release 2>/dev/null || true", ""),
            ("head -n 1 /etc/issue 2>/dev/null || true", ""),
        ]
        for command, prefix in fallbacks:
            value = clean_system_name(ssh_optional(client, command))
            if value:
                os_name = f"{prefix}{value}".strip()
                break

    if not arch:
        arch = clean_system_name(ssh_optional(client, "uname -m 2>/dev/null || true")).lower()

    kernel_release = clean_system_name(ssh_optional(client, "uname -r 2>/dev/null || true"))
    proc_version = clean_system_name(ssh_optional(client, "cat /proc/version 2>/dev/null || true"))
    wsl_distro = clean_system_name(
        ssh_optional(client, "printf '%s' \"${WSL_DISTRO_NAME:-}\"")
    )
    is_wsl = bool(wsl_distro) or "microsoft" in kernel_release.lower() or "microsoft" in proc_version.lower()
    if is_wsl:
        if not os_name and wsl_distro:
            os_name = wsl_distro
        wsl_label = "WSL2" if "wsl2" in kernel_release.lower() or "microsoft-standard" in kernel_release.lower() else "WSL"
        if wsl_label.lower() not in os_name.lower():
            os_name = f"{os_name or 'Linux'} ({wsl_label})"

    cli_name = str(getattr(client, "detected_cli", "") or "").lower()
    balena_release = clean_system_name(
        ssh_optional(client, "cat /etc/balena-release 2>/dev/null || cat /etc/resin-release 2>/dev/null || true")
    )
    is_balena = "balena" in release_markers or "resin" in release_markers or bool(balena_release) or cli_name == "balena"
    if is_balena and "balena" not in os_name.lower():
        os_name = f"balenaOS {balena_release}".strip()

    if not os_name:
        os_name = clean_system_name(ssh_optional(client, "uname -s 2>/dev/null || true"))
    return os_name, arch


def detect_local_os_name() -> str:
    if os.name == "nt":
        return "Windows"
    release_path = Path("/etc/os-release")
    try:
        release = parse_os_release(release_path.read_text(encoding="utf-8", errors="ignore"))
        name = clean_system_name(release.get("PRETTY_NAME", ""))
        if not name:
            base = clean_system_name(release.get("NAME", ""))
            version = clean_system_name(release.get("VERSION_ID", "") or release.get("VERSION", ""))
            name = f"{base} {version}".strip()
    except Exception:
        name = ""
    if not name:
        name = platform.system() or "Linux"
    kernel = platform.release().lower()
    if "microsoft" in kernel and "wsl" not in name.lower():
        label = "WSL2" if "wsl2" in kernel or "microsoft-standard" in kernel else "WSL"
        name = f"{name} ({label})"
    return name


def launch_interactive_terminal(command: Optional[List[str]] = None, shell_command: str = ""):
    if os.name == "nt":
        argv = list(command or [])
        subprocess.Popen(["cmd.exe", "/k"] + argv)
        return

    text = shell_command.strip()
    if not text and command:
        text = shlex.join([str(part) for part in command])
    if not text:
        text = "exec \"${SHELL:-/bin/sh}\""
    else:
        text = f"{text}; exec \"${{SHELL:-/bin/sh}}\""

    terminal_candidates = [
        ("x-terminal-emulator", ["-e", "sh", "-lc", text]),
        ("gnome-terminal", ["--", "sh", "-lc", text]),
        ("konsole", ["-e", "sh", "-lc", text]),
        ("xfce4-terminal", ["--command", f"sh -lc {shlex.quote(text)}"]),
        ("xterm", ["-e", "sh", "-lc", text]),
    ]
    for binary, args in terminal_candidates:
        executable = shutil.which(binary)
        if executable:
            subprocess.Popen([executable] + args)
            return
    raise RuntimeError("No supported terminal emulator found (x-terminal-emulator, gnome-terminal, konsole, xfce4-terminal or xterm).")


def parse_size_bytes(value: str) -> int:
    text = str(value or "").strip().replace("iB", "B")
    match = re.match(r"^([0-9.]+)\s*([KMGT]?B)$", text, re.IGNORECASE)
    if not match:
        return 0
    amount = float(match.group(1))
    unit = match.group(2).upper()
    scale = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}.get(unit, 1)
    return int(amount * scale)


def format_bytes(value: int) -> str:
    amount = float(max(0, int(value or 0)))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024.0 or unit == "TB":
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024.0
    return f"{amount:.1f} TB"


def docker_stats_metrics(stats: Dict) -> Dict[str, object]:
    cpu_stats = stats.get("cpu_stats", {}) or {}
    precpu_stats = stats.get("precpu_stats", {}) or {}
    cpu_usage = cpu_stats.get("cpu_usage", {}) or {}
    precpu_usage = precpu_stats.get("cpu_usage", {}) or {}
    cpu_delta = float(cpu_usage.get("total_usage", 0) or 0) - float(precpu_usage.get("total_usage", 0) or 0)
    system_delta = float(cpu_stats.get("system_cpu_usage", 0) or 0) - float(precpu_stats.get("system_cpu_usage", 0) or 0)
    online_cpus = int(cpu_stats.get("online_cpus", 0) or len(cpu_usage.get("percpu_usage", []) or []) or 1)
    cpu_percent = (cpu_delta / system_delta) * online_cpus * 100.0 if cpu_delta > 0 and system_delta > 0 else 0.0
    memory_stats = stats.get("memory_stats", {}) or {}
    memory_usage = int(memory_stats.get("usage", 0) or 0)
    cache = int((memory_stats.get("stats", {}) or {}).get("inactive_file", 0) or 0)
    if cache and memory_usage > cache:
        memory_usage -= cache
    memory_limit = int(memory_stats.get("limit", 0) or 0)
    memory_percent = (memory_usage / memory_limit * 100.0) if memory_limit > 0 else 0.0
    return {
        "cpu_percent": cpu_percent,
        "memory_usage": memory_usage,
        "memory_limit": memory_limit,
        "memory_percent": memory_percent,
    }


def call_ollama_model(base_url: str, model: str, system_prompt: str, user_prompt: str) -> str:
    payload = request_json(
        f"{base_url.rstrip('/')}/api/generate",
        headers={"User-Agent": "Docker-Control-Center/1.0"},
        payload={
            "model": model,
            "prompt": f"{system_prompt}\n\n{user_prompt}",
            "stream": False,
        },
        timeout=120,
    )
    return str(payload.get("response") or "").strip()



def sanitize_openai_model_name(model: str) -> str:
    model = str(model or "").strip()
    if not model or "codex" in model.lower():
        return DEFAULT_OPENAI_MODELS[0]
    return model


def scroll_text_edit_to_bottom(widget: QTextEdit):
    def apply_bottom_scroll():
        vbar = widget.verticalScrollBar()
        vbar.setValue(vbar.maximum())
        cursor = widget.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        widget.setTextCursor(cursor)

    QTimer.singleShot(0, apply_bottom_scroll)
    QTimer.singleShot(25, apply_bottom_scroll)
def call_openai_model(api_key: str, model: str, system_prompt: str, user_prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "User-Agent": "Docker-Control-Center/1.0",
    }
    try:
        payload = request_json(
            "https://api.openai.com/v1/responses",
            headers=headers,
            payload={
                "model": model,
                "input": [
                    {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                    {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
                ],
            },
            timeout=45,
        )
        if payload.get("output_text"):
            return str(payload.get("output_text")).strip()
        collected = []
        for item in payload.get("output", []) or []:
            for content in item.get("content", []) or []:
                text_value = content.get("text") or content.get("output_text")
                if text_value:
                    collected.append(str(text_value))
        if collected:
            return "\n".join(collected).strip()
    except HTTPError:
        pass
    payload = request_json(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        payload={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=45,
    )
    choices = payload.get("choices", []) or []
    if not choices:
        return ""
    return str((choices[0].get("message", {}) or {}).get("content") or "").strip()


def call_openai_compatible_model(base_url: str, api_key: str, model: str, system_prompt: str, user_prompt: str) -> str:
    payload = request_json(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key.strip()}", "User-Agent": f"Docker-Control-Center/{APP_VERSION}"},
        payload={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=45,
    )
    choices = payload.get("choices", []) or []
    if not choices:
        return ""
    content = (choices[0].get("message", {}) or {}).get("content")
    if isinstance(content, list):
        values = []
        for item in content:
            if isinstance(item, dict) and (item.get("text") or item.get("content")):
                values.append(str(item.get("text") or item.get("content")))
        return "\n".join(values).strip()
    return str(content or "").strip()


def call_anthropic_model(api_key: str, model: str, system_prompt: str, user_prompt: str) -> str:
    payload = request_json(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key.strip(),
            "anthropic-version": "2023-06-01",
            "User-Agent": f"Docker-Control-Center/{APP_VERSION}",
        },
        payload={
            "model": model,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        },
        timeout=45,
    )
    return "\n".join(
        str(item.get("text"))
        for item in (payload.get("content", []) or [])
        if isinstance(item, dict) and item.get("type") == "text" and item.get("text")
    ).strip()


def call_gemini_model(api_key: str, model: str, system_prompt: str, user_prompt: str) -> str:
    model_id = str(model or "").strip()
    if model_id.startswith("models/"):
        model_id = model_id[len("models/"):]
    payload = request_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model_id, safe='')}:generateContent",
        headers={"x-goog-api-key": api_key.strip(), "User-Agent": f"Docker-Control-Center/{APP_VERSION}"},
        payload={
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        },
        timeout=45,
    )
    candidates = payload.get("candidates", []) or []
    if not candidates:
        return ""
    parts = (((candidates[0] or {}).get("content") or {}).get("parts") or [])
    return "\n".join(str(item.get("text")) for item in parts if isinstance(item, dict) and item.get("text")).strip()


def llm_selected_model(settings: Dict[str, str], provider: str, requested: str = "") -> str:
    provider = str(provider or "ollama").strip().lower()
    defaults = llm_default_models(provider)
    fallback = defaults[0] if defaults else ""
    selected = str(requested or settings.get(f"{provider}_model") or fallback).strip()
    return sanitize_openai_model_name(selected) if provider == "openai" else selected


def call_provider_model(settings: Dict[str, str], provider: str, model: str, system_prompt: str, user_prompt: str) -> str:
    provider = str(provider or "ollama").strip().lower()
    selected_model = llm_selected_model(settings, provider, model)
    if provider == "ollama":
        return call_ollama_model(str(settings.get("ollama_url") or "http://127.0.0.1:11434").strip(), selected_model, system_prompt, user_prompt)
    api_key = str(settings.get(f"{provider}_api_key") or "").strip()
    if not api_key:
        raise RuntimeError(f"{provider} API key is missing")
    if provider == "openai":
        return call_openai_model(api_key, selected_model, system_prompt, user_prompt)
    if provider == "anthropic":
        return call_anthropic_model(api_key, selected_model, system_prompt, user_prompt)
    if provider == "gemini":
        return call_gemini_model(api_key, selected_model, system_prompt, user_prompt)
    base_url = LLM_OPENAI_COMPATIBLE_BASE_URLS.get(provider)
    if not base_url:
        raise RuntimeError(f"Unsupported LLM provider: {provider}")
    return call_openai_compatible_model(base_url, api_key, selected_model, system_prompt, user_prompt)

class ProfileStore:
    def __init__(self, path: Path, secret_store: SecretStore):
        self.path = path
        self.secret_store = secret_store

    def _ensure_secret_id(self, profile: RemoteProfile) -> str:
        if not profile.secret_id:
            profile.secret_id = uuid.uuid4().hex
        return profile.secret_id

    def secret_key_for_password(self, profile: RemoteProfile) -> str:
        secret_id = self._ensure_secret_id(profile)
        return f"profiles/{secret_id}/ssh_password"

    def secret_key_for_passphrase(self, profile: RemoteProfile) -> str:
        secret_id = self._ensure_secret_id(profile)
        return f"profiles/{secret_id}/ssh_passphrase"

    def load(self) -> List[RemoteProfile]:
        if not self.path.exists():
            profiles = [RemoteProfile.default()]
            self.save(profiles)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            profiles = []
            dirty = False
            for item in data.get("profiles", []):
                secret_id = str(item.get("secret_id") or "").strip()
                if not secret_id:
                    secret_id = uuid.uuid4().hex
                    item["secret_id"] = secret_id
                    dirty = True
                password_key = f"profiles/{secret_id}/ssh_password"
                passphrase_key = f"profiles/{secret_id}/ssh_passphrase"
                plain_password = str(item.get("ssh_password") or "")
                plain_passphrase = str(item.get("ssh_passphrase") or "")
                if plain_password:
                    self.secret_store.set_secret(password_key, plain_password)
                    item["ssh_password"] = ""
                    dirty = True
                if plain_passphrase:
                    self.secret_store.set_secret(passphrase_key, plain_passphrase)
                    item["ssh_passphrase"] = ""
                    dirty = True
                profile = RemoteProfile(**item)
                profile.ssh_password = self.secret_store.get_secret(password_key)
                profile.ssh_passphrase = self.secret_store.get_secret(passphrase_key)
                if profile.ssh_auth_mode == "key_password" and not profile.ssh_passphrase and profile.ssh_password:
                    profile.ssh_passphrase = profile.ssh_password
                    profile.ssh_password = ""
                    dirty = True
                profiles.append(profile)
            if dirty:
                self.save(profiles)
        except Exception:
            profiles = []
        if not profiles:
            profiles = [RemoteProfile.default()]
            self.save(profiles)
        return profiles

    def save(self, profiles: List[RemoteProfile]) -> None:
        serialized = []
        for profile in profiles:
            password_key = self.secret_key_for_password(profile)
            passphrase_key = self.secret_key_for_passphrase(profile)
            if profile.ssh_auth_mode == "password" and profile.ssh_password:
                self.secret_store.set_secret(password_key, profile.ssh_password)
            else:
                self.secret_store.delete_secret(password_key)
            if profile.ssh_auth_mode == "key_password" and profile.ssh_passphrase:
                self.secret_store.set_secret(passphrase_key, profile.ssh_passphrase)
            else:
                self.secret_store.delete_secret(passphrase_key)
            item = asdict(profile)
            item["ssh_password"] = ""
            item["ssh_passphrase"] = ""
            serialized.append(item)
        self.path.write_text(json.dumps({"profiles": serialized}, indent=2, ensure_ascii=True), encoding="utf-8")


def export_connection_profiles(path: Path, profiles: List[RemoteProfile]) -> int:
    portable = []
    for profile in profiles:
        item = asdict(profile)
        item["ssh_password"] = ""
        item["ssh_passphrase"] = ""
        item["secret_id"] = ""
        portable.append(item)
    payload = {
        "format": "docker-control-center-profiles",
        "format_version": 1,
        "application_version": APP_VERSION,
        "profiles": portable,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(portable)


def import_connection_profiles(path: Path) -> List[RemoteProfile]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("format") != "docker-control-center-profiles":
        raise ValueError("invalid profile export format")
    raw_profiles = payload.get("profiles")
    if not isinstance(raw_profiles, list):
        raise ValueError("invalid profile list")
    allowed = set(RemoteProfile.__dataclass_fields__.keys())
    imported: List[RemoteProfile] = []
    for raw in raw_profiles:
        if not isinstance(raw, dict):
            continue
        item = {key: raw.get(key) for key in allowed if key in raw}
        item["ssh_password"] = ""
        item["ssh_passphrase"] = ""
        item["secret_id"] = uuid.uuid4().hex
        key_path = str(item.get("ssh_key_path") or "").strip()
        if key_path:
            try:
                key_file = Path(key_path).expanduser()
                if not key_file.is_file():
                    item["ssh_key_path"] = ""
            except Exception:
                item["ssh_key_path"] = ""
        if "name" not in item or not str(item.get("name") or "").strip():
            continue
        imported.append(RemoteProfile(**item))
    if not imported:
        raise ValueError("no profiles")
    return imported


def profile_needs_ssh_key_path(profile: RemoteProfile) -> bool:
    if str(profile.mode or "ssh") != "ssh":
        return False
    if str(profile.ssh_auth_mode or "key") not in {"key", "key_password"}:
        return False
    key_path = str(profile.ssh_key_path or "").strip()
    if not key_path:
        return True
    try:
        return not Path(key_path).expanduser().is_file()
    except Exception:
        return True


def merge_imported_profiles(existing: List[RemoteProfile], imported: List[RemoteProfile]) -> List[RemoteProfile]:
    result = [RemoteProfile(**asdict(profile)) for profile in existing]
    names = {str(profile.name or "").casefold() for profile in result}
    for profile in imported:
        base = str(profile.name or "Profile").strip() or "Profile"
        candidate = base
        index = 2
        while candidate.casefold() in names:
            candidate = f"{base} ({index})"
            index += 1
        profile.name = candidate
        names.add(candidate.casefold())
        result.append(profile)
    return result
def palette_for_theme(theme: str) -> Dict[str, str]:
    palettes = {
        "day": {
            "bg0": "rgba(248,248,245,0.82)",
            "bg1": "rgba(232,236,232,0.74)",
            "bg2": "rgba(255,255,252,0.88)",
            "solid0": "#f5f5ef",
            "solid1": "#e2e5dc",
            "solid2": "#fbfbf7",
            "fg": "#101820",
            "muted": "#45505a",
            "border": "#9aa6a0",
            "glow_text": "#202020",
        },
        "light": {
            "bg0": "rgba(242,247,255,0.78)",
            "bg1": "rgba(223,235,255,0.72)",
            "bg2": "rgba(249,252,255,0.82)",
            "solid0": "#eef5ff",
            "solid1": "#d6e7ff",
            "solid2": "#f9fbff",
            "fg": "#10233f",
            "muted": "#40618e",
            "border": "#8cabde",
            "glow_text": "#2a71ff",
        },
        "dark": {
            "bg0": "rgba(16,24,38,0.74)",
            "bg1": "rgba(28,40,62,0.68)",
            "bg2": "rgba(18,20,34,0.82)",
            "solid0": "#141f31",
            "solid1": "#1d2a43",
            "solid2": "#111521",
            "fg": "#edf4ff",
            "muted": "#abc4ea",
            "border": "#546a92",
            "glow_text": "#76b1ff",
        },
        "black": {
            "bg0": "rgba(10,10,12,0.76)",
            "bg1": "rgba(18,20,24,0.70)",
            "bg2": "rgba(24,18,18,0.82)",
            "solid0": "#0a0b0d",
            "solid1": "#181d24",
            "solid2": "#161111",
            "fg": "#f5f8ff",
            "muted": "#c7d3e7",
            "border": "#676f7d",
            "glow_text": "#ffc4c4",
        },
        "night": {
            "bg0": "rgba(8,10,14,0.80)",
            "bg1": "rgba(18,15,19,0.74)",
            "bg2": "rgba(14,9,12,0.86)",
            "solid0": "#090b0f",
            "solid1": "#171216",
            "solid2": "#100b0e",
            "fg": "#fff3f4",
            "muted": "#d9b8bd",
            "border": "#6f3038",
            "glow_text": "#ff7a84",
        },
    }
    return palettes.get(theme, palettes["black"])


def normalize_accent_color(value: str, fallback: str = "#33f0ff") -> str:
    try:
        color = QColor(value)
        if color.isValid():
            return color.name()
    except Exception:
        pass
    return QColor(fallback).name()


DEFAULT_ACCENT_COLOR = "#33f0ff"
NIGHT_ACCENT_COLOR = "#ff4a55"


def effective_accent_color(theme: str, accent_color: str) -> str:
    """Use a red Night default without overwriting a user's explicit accent choice."""
    normalized = normalize_accent_color(accent_color, DEFAULT_ACCENT_COLOR)
    if str(theme or "").lower() == "night" and normalized == normalize_accent_color(DEFAULT_ACCENT_COLOR):
        return normalize_accent_color(NIGHT_ACCENT_COLOR)
    return normalized


def gaming_stylesheet(theme: str, glow_phase: float, transparent: bool, transparency_level: int, neon_animate: bool = True, accent_color: str = "#33f0ff") -> str:
    palette = palette_for_theme(theme)
    is_day = theme == "day"
    is_light_theme = theme in {"day", "light"}
    base = QColor(effective_accent_color(theme, accent_color))
    if neon_animate:
        hue, saturation, value, _alpha = base.getHsvF()
        pulse = 0.78 + 0.22 * (0.5 + 0.5 * math.sin(float(glow_phase) * math.tau))
        animated = QColor.fromHsvF(hue if hue >= 0 else 0.0, max(0.18, saturation), max(0.35, min(1.0, value * pulse)))
        accent = animated.name()
        soft = QColor(animated)
        soft.setAlpha(150)
        accent_soft = soft.name(QColor.NameFormat.HexArgb)
    else:
        accent = base.name()
        soft = QColor(base)
        soft.setAlpha(160)
        accent_soft = soft.name(QColor.NameFormat.HexArgb)
    accent_text = accent
    if is_light_theme:
        readable_accent = QColor(accent)
        hue, saturation, value, alpha = readable_accent.getHsvF()
        if hue >= 0 and value > 0.58:
            readable_accent = QColor.fromHsvF(hue, max(0.60, saturation), 0.50, alpha)
        accent_text = readable_accent.name()
    if is_day:
        input_bg = "rgba(255,255,255,0.56)"
        combo_bg = "rgba(251,251,247,0.94)"
        table_bg = "rgba(255,255,255,0.24)"
        table_alt_bg = "rgba(230,239,244,0.18)"
        status_bg = "rgba(255,255,255,0.54)"
        menu_bg = palette["solid2"]
        popup_bg = "rgba(251,251,247,0.96)"
        panel_bg = "rgba(255,255,255,0.46)"
        control_bg = "rgba(255,255,255,0.34)"
        button_bg = "rgba(255,255,255,0.54)"
        button_hover_bg = "rgba(255,255,255,0.82)"
        link_bg = "rgba(255,255,255,0.44)"
        header_bg = "rgba(241,247,250,0.58)"
    elif theme == "light":
        input_bg = "rgba(255,255,255,0.92)"
        combo_bg = "rgba(249,251,255,0.94)"
        table_bg = input_bg
        table_alt_bg = "rgba(232,241,255,0.86)"
        status_bg = "rgba(255,255,255,0.72)" if transparent else palette["solid1"]
        menu_bg = palette["solid2"]
        popup_bg = "rgba(249,251,255,0.96)"
        panel_bg = "rgba(250,252,255,0.88)"
        control_bg = "rgba(244,248,255,0.86)"
        button_bg = "rgba(255,255,255,0.82)"
        button_hover_bg = "rgba(224,236,255,0.96)"
        link_bg = "rgba(248,251,255,0.90)"
        header_bg = "rgba(218,231,250,0.92)"
    else:
        input_bg = "rgba(255,255,255,0.06)"
        combo_bg = {
            "dark": "rgba(29,42,67,0.94)",
            "black": "rgba(24,29,36,0.94)",
            "night": "rgba(23,18,22,0.94)",
        }.get(theme, "rgba(24,29,36,0.94)")
        table_bg = input_bg
        table_alt_bg = "rgba(255,255,255,0.035)"
        status_bg = "rgba(5,12,20,0.72)" if transparent else palette["solid1"]
        menu_bg = palette["solid1"]
        popup_bg = {
            "dark": "rgba(29,42,67,0.96)",
            "black": "rgba(24,29,36,0.96)",
            "night": "rgba(23,18,22,0.96)",
        }.get(theme, "rgba(24,29,36,0.96)")
        panel_bg = "rgba(255,255,255,0.06)"
        control_bg = "rgba(255,255,255,0.035)"
        button_bg = "rgba(255,255,255,0.05)"
        button_hover_bg = "rgba(255,255,255,0.10)"
        link_bg = "rgba(255,255,255,0.05)"
        header_bg = "rgba(255,255,255,0.04)"
    surface = palette["bg0"] if transparent else palette["solid0"]
    return f"""
    QWidget {{
        color: {palette['fg']};
        font-family: 'Segoe UI';
        font-size: 10.5pt;
        selection-background-color: {accent_soft};
        selection-color: #08172c;
    }}
    QMainWindow {{
        background: transparent;
    }}
    QMenuBar {{
        background: {menu_bg};
        color: {palette['fg']};
        border-bottom: 1px solid {palette['border']};
    }}
    QMenuBar::item {{
        background: transparent;
        color: {palette['fg']};
        padding: 6px 11px;
        margin: 2px 1px;
    }}
    QMenuBar::item:selected {{
        background: {accent_soft};
        color: {palette['fg']};
    }}
    QMenu {{
        background: {menu_bg};
        color: {palette['fg']};
        border: 1px solid {palette['border']};
        padding: 5px;
    }}
    QMenu::item {{
        background: transparent;
        color: {palette['fg']};
        /* Keep a dedicated right gutter for the native submenu arrow. */
        padding: 7px 34px 7px 12px;
        margin: 2px 3px;
        border-radius: 7px;
    }}
    QMenu::item:selected {{
        background: {accent_soft};
        color: {palette['fg']};
    }}
    QMenu::separator {{
        height: 1px;
        background: {palette['border']};
        margin: 5px 9px;
    }}
    QMenu::right-arrow {{
        margin-right: 9px;
    }}
    QScrollArea#mainScrollArea {{
        background: transparent;
        border: 0px;
    }}
    QScrollArea#mainScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QWidget#rootSurface {{
        background: transparent;
        border-radius: 24px;
        border: 1px solid {palette['border']};
    }}
    QFrame#heroPanel {{
        background: {panel_bg};
        border: 1px solid {accent};
        border-radius: 22px;
    }}
    QFrame#controlPanel {{
        background: {control_bg};
        border: 1px solid {palette['border']};
        border-radius: 16px;
    }}
    QLabel#sectionTitle {{
        color: {accent_text};
        font-size: 8.5pt;
        font-weight: 800;
        letter-spacing: 1px;
        padding: 0px 3px;
    }}
    QLabel#heroTitle {{ font-size: 18pt; font-weight: 700; color: {accent_text}; }}
    QLabel#heroSubtitle {{ color: {palette['muted']}; }}
    QPushButton {{
        background: {button_bg};
        color: {palette['fg']};
        border: 1px solid {palette['border']};
        border-radius: 14px;
        padding: 6px 10px;
    }}
    QPushButton:hover {{ border: 1px solid {accent}; background: {button_hover_bg}; }}
    QPushButton#primaryAction {{
        border: 1px solid {accent};
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {accent_soft}, stop:1 {accent});
        color: #08172c;
        font-weight: 700;
    }}
    QPushButton#profileAction {{ font-weight: 600; }}
    QPushButton#infoAction {{
        border: 1px solid {accent};
        background: rgba(255,210,100,0.14);
        font-weight: 700;
    }}
    QPushButton#containerAction {{
        border: 1px solid {accent_soft};
        background: rgba(40,120,180,0.16);
        font-weight: 700;
        padding: 5px 9px;
        border-radius: 10px;
        min-height: 20px;
    }}
    QPushButton#shopButton {{
        border: 1px solid {accent};
        background: {accent_soft};
        color: {palette['fg']};
        font-weight: 800;
        padding: 5px 11px;
        border-radius: 10px;
        min-height: 20px;
    }}
    QPushButton#shopButton:hover {{
        border: 1px solid {accent};
        background: {accent};
        color: #08172c;
    }}
    QPushButton#containerGroupButton {{
        border: 0;
        background: transparent;
        text-align: left;
        font-weight: 600;
        color: {accent_text};
        padding: 0;
    }}
    QPushButton#containerGroupButton:hover {{
        border: 0;
        background: transparent;
        color: {accent_text};
    }}
    QWidget#linkPanel {{
        background: transparent;
    }}
    QFrame#linkRow {{
        background: {link_bg};
        border: 1px solid {palette['border']};
        border-radius: 8px;
    }}
    QFrame#linkRow[selected="true"] {{
        background: {accent};
        border: 1px solid {accent};
    }}
    QLabel#linkText {{
        color: {palette['fg']};
        padding: 0px 2px;
        font-size: 9.5pt;
    }}
    QLabel#linkText[selected="true"] {{
        color: #08172c;
        font-weight: 700;
    }}
    QPushButton#linkAction {{
        min-width: 20px;
        max-width: 20px;
        min-height: 20px;
        max-height: 20px;
        padding: 0px;
        border-radius: 6px;
        font-weight: 700;
    }}
    QPushButton#linkAction[selected="true"] {{
        color: #08172c;
        border: 1px solid rgba(8,23,44,0.22);
        background: rgba(8,23,44,0.12);
    }}
    QPushButton#linkAction[selected="true"]:hover {{
        background: rgba(8,23,44,0.18);
    }}
    QComboBox, QLineEdit, QTextEdit, QPlainTextEdit, QListWidget, QSpinBox, QTableWidget {{
        background: {input_bg};
        color: {palette['fg']};
        border: 1px solid {palette['border']};
        border-radius: 14px;
        padding: 5px;
    }}
    QComboBox {{
        background: {combo_bg};
    }}
    QTableWidget {{
        background: {table_bg};
        alternate-background-color: {table_alt_bg};
        color: {palette['fg']};
    }}
    QTableWidget::item {{
        color: {palette['fg']};
        background: transparent;
    }}
    QComboBox QAbstractItemView {{
        background: {popup_bg};
        color: {palette['fg']};
        border: 1px solid {palette['border']};
        selection-background-color: {accent_soft};
        selection-color: #08172c;
    }}
    QHeaderView::section {{
        background: {header_bg};
        border: 0;
        border-bottom: 1px solid {palette['border']};
        padding: 5px 10px 5px 6px;
        color: {palette['glow_text']};
        font-weight: 700;
    }}
    QTableWidget::item:selected {{ background: {accent}; color: #08172c; }}
    QStatusBar {{ background: {status_bg}; color: {palette['fg']}; border-top: 1px solid {accent}; font-weight: 600; }}
    QMessageBox QLabel {{ color: {palette['fg']}; }}
    """


def make_colored_icon(color: QColor, size: int = 14) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(color)
    painter.setPen(Qt.GlobalColor.black)
    radius = size // 2 - 1
    painter.drawEllipse(1, 1, radius * 2, radius * 2)
    painter.end()
    return QIcon(pix)


def make_terminal_icon(color: QColor, size: int = 16) -> QIcon:
    """Draw a small terminal glyph without relying on font/emoji support."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(color)
    pen.setWidthF(max(1.2, size / 10.0))
    painter.setPen(pen)
    inset = max(1.5, size * 0.12)
    painter.drawRoundedRect(
        QRectF(inset, inset, size - (inset * 2), size - (inset * 2)),
        size * 0.14,
        size * 0.14,
    )
    painter.drawLine(
        int(size * 0.28),
        int(size * 0.38),
        int(size * 0.43),
        int(size * 0.50),
    )
    painter.drawLine(
        int(size * 0.43),
        int(size * 0.50),
        int(size * 0.28),
        int(size * 0.62),
    )
    painter.drawLine(
        int(size * 0.52),
        int(size * 0.64),
        int(size * 0.72),
        int(size * 0.64),
    )
    painter.end()
    return QIcon(pix)


def make_category_icon(kind: str, color: QColor, size: int = 18) -> QIcon:
    """Draw small category glyphs without relying on emoji/font support."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(color)
    pen.setWidthF(max(1.2, size / 11.0))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    k = (kind or "generic").lower()
    s = float(size)
    if k == "all":
        box = s * 0.26
        gap = s * 0.12
        start = s * 0.17
        for row in range(2):
            for col in range(2):
                x = start + col * (box + gap)
                y = start + row * (box + gap)
                painter.drawRoundedRect(QRectF(x, y, box, box), s * 0.05, s * 0.05)
    elif k == "installed":
        painter.drawRoundedRect(QRectF(s * 0.16, s * 0.16, s * 0.68, s * 0.68), s * 0.10, s * 0.10)
        painter.drawLine(int(s * 0.30), int(s * 0.50), int(s * 0.43), int(s * 0.63))
        painter.drawLine(int(s * 0.43), int(s * 0.63), int(s * 0.70), int(s * 0.34))
    elif k in {"ai", "automation"}:
        painter.drawEllipse(QRectF(s * 0.34, s * 0.34, s * 0.32, s * 0.32))
        for x1, y1, x2, y2 in (
            (0.50, 0.10, 0.50, 0.26), (0.50, 0.74, 0.50, 0.90),
            (0.10, 0.50, 0.26, 0.50), (0.74, 0.50, 0.90, 0.50),
            (0.22, 0.22, 0.33, 0.33), (0.67, 0.67, 0.78, 0.78),
        ):
            painter.drawLine(int(s * x1), int(s * y1), int(s * x2), int(s * y2))
    elif k in {"monitor", "analytics", "finance"}:
        painter.drawRoundedRect(QRectF(s * 0.12, s * 0.18, s * 0.76, s * 0.62), s * 0.08, s * 0.08)
        painter.drawLine(int(s * 0.24), int(s * 0.64), int(s * 0.40), int(s * 0.48))
        painter.drawLine(int(s * 0.40), int(s * 0.48), int(s * 0.56), int(s * 0.58))
        painter.drawLine(int(s * 0.56), int(s * 0.58), int(s * 0.76), int(s * 0.34))
    elif k == "network":
        nodes = [(0.22, 0.28), (0.76, 0.24), (0.50, 0.74)]
        painter.drawLine(int(s * 0.26), int(s * 0.31), int(s * 0.70), int(s * 0.27))
        painter.drawLine(int(s * 0.27), int(s * 0.34), int(s * 0.47), int(s * 0.68))
        painter.drawLine(int(s * 0.72), int(s * 0.31), int(s * 0.54), int(s * 0.68))
        for x, y in nodes:
            painter.drawEllipse(QRectF(s * (x - 0.09), s * (y - 0.09), s * 0.18, s * 0.18))
    elif k in {"security", "backup"}:
        path = QPainterPath()
        path.moveTo(s * 0.50, s * 0.10)
        path.lineTo(s * 0.80, s * 0.22)
        path.lineTo(s * 0.73, s * 0.65)
        path.quadTo(s * 0.50, s * 0.88, s * 0.27, s * 0.65)
        path.lineTo(s * 0.20, s * 0.22)
        path.closeSubpath()
        painter.drawPath(path)
    elif k in {"database", "cache"}:
        painter.drawEllipse(QRectF(s * 0.18, s * 0.14, s * 0.64, s * 0.24))
        painter.drawLine(int(s * 0.18), int(s * 0.26), int(s * 0.18), int(s * 0.70))
        painter.drawLine(int(s * 0.82), int(s * 0.26), int(s * 0.82), int(s * 0.70))
        painter.drawArc(QRectF(s * 0.18, s * 0.58, s * 0.64, s * 0.24), 180 * 16, 180 * 16)
        painter.drawArc(QRectF(s * 0.18, s * 0.36, s * 0.64, s * 0.24), 180 * 16, 180 * 16)
    elif k in {"web", "system", "container"}:
        painter.drawRoundedRect(QRectF(s * 0.12, s * 0.16, s * 0.76, s * 0.68), s * 0.08, s * 0.08)
        painter.drawLine(int(s * 0.12), int(s * 0.34), int(s * 0.88), int(s * 0.34))
        painter.drawEllipse(QRectF(s * 0.20, s * 0.22, s * 0.06, s * 0.06))
        painter.drawEllipse(QRectF(s * 0.31, s * 0.22, s * 0.06, s * 0.06))
    elif k == "home":
        path = QPainterPath()
        path.moveTo(s * 0.16, s * 0.46)
        path.lineTo(s * 0.50, s * 0.16)
        path.lineTo(s * 0.84, s * 0.46)
        path.moveTo(s * 0.24, s * 0.40)
        path.lineTo(s * 0.24, s * 0.82)
        path.lineTo(s * 0.76, s * 0.82)
        path.lineTo(s * 0.76, s * 0.40)
        painter.drawPath(path)
    elif k == "media":
        painter.drawRoundedRect(QRectF(s * 0.14, s * 0.18, s * 0.72, s * 0.64), s * 0.08, s * 0.08)
        path = QPainterPath()
        path.moveTo(s * 0.42, s * 0.35)
        path.lineTo(s * 0.68, s * 0.50)
        path.lineTo(s * 0.42, s * 0.65)
        path.closeSubpath()
        painter.drawPath(path)
    elif k in {"devops", "tools", "productivity", "messaging"}:
        painter.drawRoundedRect(QRectF(s * 0.16, s * 0.22, s * 0.68, s * 0.56), s * 0.10, s * 0.10)
        painter.drawLine(int(s * 0.28), int(s * 0.39), int(s * 0.72), int(s * 0.39))
        painter.drawLine(int(s * 0.28), int(s * 0.54), int(s * 0.64), int(s * 0.54))
    else:
        painter.drawRoundedRect(QRectF(s * 0.16, s * 0.20, s * 0.68, s * 0.60), s * 0.10, s * 0.10)
        painter.drawLine(int(s * 0.28), int(s * 0.38), int(s * 0.72), int(s * 0.38))
        painter.drawLine(int(s * 0.28), int(s * 0.55), int(s * 0.60), int(s * 0.55))
    painter.end()
    return QIcon(pix)


class ResizeGripHeader(QHeaderView):
    """Interactive table header with a visible resize grip at each divider."""

    def paintSection(self, painter: QPainter, rect, logical_index: int):
        super().paintSection(painter, rect, logical_index)
        if (
            not rect.isValid()
            or logical_index < 0
            or self.visualIndex(logical_index) >= self.count() - 1
        ):
            return
        painter.save()
        grip_color = self.palette().color(self.foregroundRole())
        grip_color.setAlpha(150)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grip_color)
        x = rect.right() - 3.0
        center_y = rect.center().y()
        for offset in (-4.0, 0.0, 4.0):
            painter.drawEllipse(QRectF(x - 1.15, center_y + offset - 1.15, 2.3, 2.3))
        painter.restore()


def resolve_background_path(theme: str) -> Path:
    stems = BACKGROUND_NAMES.get(theme, BACKGROUND_NAMES["black"])
    for stem in stems:
        for extension in BACKGROUND_EXTENSIONS:
            candidate = BACKGROUND_DIR / f"{stem}{extension}"
            if candidate.exists():
                return candidate
    return BACKGROUND_DIR / f"{stems[0]}.jpg"


class BackgroundSurface(QWidget):
    def __init__(self, theme: str, transparent: bool, transparency_level: int, parent=None):
        super().__init__(parent)
        self.setObjectName("rootSurface")
        self._theme = theme
        self._transparent = transparent
        self._transparency_level = transparency_level
        self._pixmap = QPixmap()
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.reload_background()

    def set_visual_state(self, theme: str, transparent: bool, transparency_level: int):
        changed_theme = theme != self._theme
        if changed_theme:
            self._theme = theme
            self.reload_background()
        self._transparent = transparent
        self._transparency_level = transparency_level
        self.update()

    def reload_background(self):
        background_path = resolve_background_path(self._theme)
        self._pixmap = QPixmap(str(background_path)) if background_path.exists() else QPixmap()
        self.update()

    def _overlay_color(self) -> QColor:
        palette = palette_for_theme(self._theme)
        overlay = QColor(palette["solid0"])
        if self._theme == "day":
            alpha = max(24, 78 - int(self._transparency_level * 0.42)) if self._transparent else 72
        elif self._transparent:
            if self._theme == "light":
                alpha = max(92, 172 - int(self._transparency_level * 0.55))
            else:
                alpha = max(42, 120 - int(self._transparency_level * 0.7))
        else:
            alpha = 182 if self._theme == "light" else max(122, 210 - self._transparency_level)
        overlay.setAlpha(alpha)
        return overlay

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(0, 0, -1, -1)
        rectf = QRectF(rect)
        if rectf.width() <= 1 or rectf.height() <= 1:
            return
        clip_path = QPainterPath()
        clip_path.addRoundedRect(rectf, 24, 24)
        painter.setClipPath(clip_path)

        palette = palette_for_theme(self._theme)
        fallback = QLinearGradient(rectf.left(), rectf.top(), rectf.right(), rectf.bottom())
        fallback.setColorAt(0.0, QColor(palette["solid1"]))
        fallback.setColorAt(0.55, QColor(palette["solid0"]))
        fallback.setColorAt(1.0, QColor(palette["solid2"]))
        painter.fillRect(rectf, fallback)

        if not self._pixmap.isNull():
            source_width = self._pixmap.width()
            source_height = self._pixmap.height()
            scale = max(rectf.width() / max(1, source_width), rectf.height() / max(1, source_height))
            target_width = source_width * scale
            target_height = source_height * scale
            target_rect = QRectF(
                rectf.x() + (rectf.width() - target_width) / 2,
                rectf.y() + (rectf.height() - target_height) / 2,
                target_width,
                target_height,
            )
            painter.drawPixmap(target_rect, self._pixmap, QRectF(self._pixmap.rect()))

        painter.fillRect(rectf, self._overlay_color())

        glow = QLinearGradient(rectf.left(), rectf.top(), rectf.right(), rectf.bottom())
        if self._theme == "day":
            glow.setColorAt(0.0, QColor(255, 255, 255, 42))
            glow.setColorAt(0.42, QColor(205, 228, 241, 18))
            glow.setColorAt(1.0, QColor(255, 255, 255, 0))
        elif self._theme == "light":
            glow.setColorAt(0.0, QColor(255, 255, 255, 86))
            glow.setColorAt(0.35, QColor(210, 234, 255, 28))
            glow.setColorAt(1.0, QColor(255, 255, 255, 0))
        elif self._theme == "black":
            glow.setColorAt(0.0, QColor(255, 120, 120, 28))
            glow.setColorAt(0.48, QColor(90, 150, 255, 22))
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        elif self._theme == "night":
            glow.setColorAt(0.0, QColor(255, 52, 66, 54))
            glow.setColorAt(0.42, QColor(128, 20, 34, 24))
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        else:
            glow.setColorAt(0.0, QColor(120, 190, 255, 36))
            glow.setColorAt(0.45, QColor(255, 255, 255, 18))
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(rectf, glow)

        painter.setClipping(False)
        border_pen = QPen(QColor(palette["border"]))
        border_pen.setWidth(1)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rectf, 24, 24)


class LogsDialog(QDialog):
    def __init__(self, client: docker.DockerClient, name: str, texts: Dict[str, str], parent=None):
        super().__init__(parent)
        self.client = client
        self.name = name
        self.texts = texts
        self.setWindowTitle(self.texts["logs_title"].format(name=name))
        self.resize(800, 500)
        layout = QVBoxLayout(self)
        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text_edit.setCenterOnScroll(False)
        layout.addWidget(self.text_edit)
        btn_refresh = QPushButton(self.texts["btn_refresh"])
        btn_refresh.clicked.connect(self.load_logs)
        layout.addWidget(btn_refresh)
        self.load_logs()

    def load_logs(self):
        vbar = self.text_edit.verticalScrollBar()
        hbar = self.text_edit.horizontalScrollBar()
        previous_v = vbar.value()
        previous_h = hbar.value()
        self.text_edit.setPlainText(self.texts["logs_loading"])
        try:
            logs = self.client.containers.get(self.name).logs(tail=200).decode("utf-8", errors="ignore")
            self.text_edit.setPlainText(logs)

            def restore_scroll():
                vbar.setValue(min(previous_v, vbar.maximum()))
                hbar.setValue(min(previous_h, hbar.maximum()))

            QTimer.singleShot(0, restore_scroll)
            QTimer.singleShot(25, restore_scroll)
        except Exception as exc:
            self.text_edit.setPlainText(f"{self.texts['msg_error']}: {exc}")


class TutorialDialog(QDialog):
    def __init__(self, profile: RemoteProfile, texts: Dict[str, str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(texts["profile_tutorial_title"])
        self.resize(760, 480)
        layout = QVBoxLayout(self)
        target = profile.ssh_target or "user@192.168.0.200"
        user = target.split("@")[0] if "@" in target else "user"
        port = profile.resolved_ssh_port() or 22
        body = QTextEdit()
        body.setReadOnly(True)
        agent_help_key = "profile_tutorial_agent_windows" if os.name == "nt" else "profile_tutorial_agent_linux"
        body.setPlainText(
            texts["profile_tutorial_intro"] + "\n\n" +
            texts["profile_tutorial_steps"].format(user=user, target=target, port=port) +
            "\n\n" + texts["profile_tutorial_hint"] +
            "\n\n" + texts[agent_help_key] +
            "\n\n" + texts["profile_tutorial_test"].format(target=target, port=port)
        )
        layout.addWidget(body)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        layout.addWidget(buttons)

class LlmSettingsDialog(QDialog):
    def __init__(self, settings: QSettings, secret_store: SecretStore, texts: Dict[str, str], parent=None):
        super().__init__(parent)
        self.settings = settings
        self.secret_store = secret_store
        self.texts = texts
        self._draft_models: Dict[str, str] = {}
        self._draft_keys: Dict[str, str] = {}
        self._draft_ollama_url = "http://127.0.0.1:11434"
        self._current_provider = ""
        self.setWindowTitle(self.texts["llm_title"])
        self.resize(720, 330)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.provider_combo = QComboBox()
        for provider in LLM_PROVIDER_ORDER:
            self.provider_combo.addItem(self.texts[LLM_PROVIDER_LABEL_KEYS[provider]], provider)

        self.ollama_url_edit = QLineEdit()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.btn_detect_models = QPushButton(self.texts["llm_refresh_models"])
        model_row = QHBoxLayout()
        model_row.addWidget(self.model_combo, 1)
        model_row.addWidget(self.btn_detect_models)

        self.ollama_url_label = QLabel(self.texts["llm_ollama_url"])
        self.api_key_label = QLabel(self.texts["llm_api_key"])
        self.model_label = QLabel(self.texts["llm_model"])

        form.addRow(self.texts["llm_provider"], self.provider_combo)
        form.addRow(self.ollama_url_label, self.ollama_url_edit)
        form.addRow(self.api_key_label, self.api_key_edit)
        form.addRow(self.model_label, model_row)
        layout.addLayout(form)

        self.status_label = QLabel(self.texts["llm_status_idle"])
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.btn_save = QPushButton(self.texts["llm_save"])
        self.btn_close = QPushButton(self.texts["llm_close"])
        buttons.addWidget(self.btn_save)
        buttons.addWidget(self.btn_close)
        layout.addLayout(buttons)

        self.provider_combo.currentIndexChanged.connect(self.on_provider_changed)
        self.btn_detect_models.clicked.connect(self.detect_models)
        self.btn_save.clicked.connect(self.save_and_close)
        self.btn_close.clicked.connect(self.reject)

        self.load_settings()

    def set_status(self, text: str):
        self.status_label.setText(text)

    def populate_combo(self, combo: QComboBox, values: List[str], selected: str = ""):
        combo.blockSignals(True)
        combo.clear()
        seen = set()
        for value in values:
            value = str(value).strip()
            if value and value not in seen:
                combo.addItem(value)
                seen.add(value)
        if selected and selected not in seen:
            combo.addItem(selected)
        if selected:
            combo.setCurrentText(selected)
        combo.blockSignals(False)

    def load_settings(self):
        provider = str(self.settings.value("llm/provider", "ollama")).strip().lower()
        if provider not in LLM_PROVIDER_ORDER:
            provider = "ollama"
        self._draft_ollama_url = str(self.settings.value("llm/ollama_url", "http://127.0.0.1:11434"))
        for item in LLM_PROVIDER_ORDER:
            defaults = llm_default_models(item)
            saved = str(self.settings.value(llm_model_setting_key(item), defaults[0] if defaults else "")).strip()
            self._draft_models[item] = sanitize_openai_model_name(saved) if item == "openai" else saved
            if item != "ollama":
                self._draft_keys[item] = self.secret_store.get_secret(llm_secret_key(item))
        self.provider_combo.blockSignals(True)
        self.provider_combo.setCurrentIndex(max(0, self.provider_combo.findData(provider)))
        self.provider_combo.blockSignals(False)
        self._current_provider = ""
        self._render_provider(provider)

    def provider_name(self, provider: str) -> str:
        return self.texts.get(LLM_PROVIDER_LABEL_KEYS.get(provider, ""), provider)

    def _capture_current(self):
        provider = self._current_provider
        if not provider:
            return
        self._draft_models[provider] = self.model_combo.currentText().strip()
        if provider == "ollama":
            self._draft_ollama_url = self.ollama_url_edit.text().strip() or "http://127.0.0.1:11434"
        else:
            self._draft_keys[provider] = self.api_key_edit.text().strip()

    def _render_provider(self, provider: str):
        provider = provider if provider in LLM_PROVIDER_ORDER else "ollama"
        self._current_provider = provider
        is_ollama = provider == "ollama"
        self.ollama_url_label.setVisible(is_ollama)
        self.ollama_url_edit.setVisible(is_ollama)
        self.api_key_label.setVisible(not is_ollama)
        self.api_key_edit.setVisible(not is_ollama)
        self.ollama_url_edit.setText(self._draft_ollama_url)
        self.api_key_label.setText(f'{self.provider_name(provider)} · {self.texts["llm_api_key"]}')
        self.api_key_edit.setText(self._draft_keys.get(provider, ""))
        defaults = llm_default_models(provider)
        selected = self._draft_models.get(provider) or (defaults[0] if defaults else "")
        self.populate_combo(self.model_combo, defaults, selected)
        self.set_status(self.texts["llm_status_idle"])

    def on_provider_changed(self):
        self._capture_current()
        self._render_provider(str(self.provider_combo.currentData() or "ollama"))

    def detect_models(self):
        self._capture_current()
        provider = str(self.provider_combo.currentData() or "ollama")
        api_key = self._draft_keys.get(provider, "") if provider != "ollama" else ""
        if provider != "ollama" and not api_key:
            QMessageBox.warning(
                self,
                self.texts["msg_error"],
                self.texts["llm_api_key_missing"].format(provider=self.provider_name(provider)),
            )
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            models = fetch_provider_models(provider, api_key=api_key, ollama_url=self._draft_ollama_url)
            current = self.model_combo.currentText().strip()
            selected = current if current in models else (select_ollama_fallback_model(models) if provider == "ollama" else models[0])
            self._draft_models[provider] = selected
            self.populate_combo(self.model_combo, models, selected)
            status = self.texts["llm_models_ready"]
            if current and current != selected:
                status += " " + self.texts["wizard_model_fallback"].format(old=current, new=selected)
            self.set_status(status)
        except Exception as exc:
            self.set_status(f'{self.texts["llm_models_failed"]} {exc}')
        finally:
            QApplication.restoreOverrideCursor()

    def save_and_close(self):
        self._capture_current()
        self.settings.setValue("llm/provider", self.provider_combo.currentData() or "ollama")
        self.settings.setValue("llm/ollama_url", self._draft_ollama_url)
        for provider in LLM_PROVIDER_ORDER:
            defaults = llm_default_models(provider)
            model = self._draft_models.get(provider) or (defaults[0] if defaults else "")
            if provider == "openai":
                model = sanitize_openai_model_name(model)
            self.settings.setValue(llm_model_setting_key(provider), model)
            if provider != "ollama":
                self.secret_store.set_secret(llm_secret_key(provider), self._draft_keys.get(provider, ""))
        self.settings.remove("llm/openai_api_key")
        self.accept()

class AppSettingsDialog(QDialog):
    def __init__(self, settings: QSettings, texts: Dict[str, str], parent=None, update_check_callback=None):
        super().__init__(parent)
        self.settings = settings
        self.texts = texts
        self.update_check_callback = update_check_callback
        self.setWindowTitle(self.texts["app_settings_title"])
        self.resize(680, 360)

        layout = QVBoxLayout(self)
        intro = QLabel(self.texts["app_settings_intro"])
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.auto_start_checkbox = QCheckBox(self.texts["app_settings_autostart_dd"])
        enabled = str(self.settings.value("auto_start_docker_desktop", "false")).lower() in {"1", "true", "yes"}
        self.auto_start_checkbox.setChecked(enabled)
        layout.addWidget(self.auto_start_checkbox)

        note = QLabel(self.texts["app_settings_note"])
        note.setWordWrap(True)
        layout.addWidget(note)

        updates_label = QLabel(f"<b>{self.texts['app_settings_updates_title']}</b>")
        layout.addWidget(updates_label)
        self.auto_updates_checkbox = QCheckBox(self.texts["app_settings_auto_updates"])
        auto_updates = str(self.settings.value("updates/auto_check", "true")).lower() in {"1", "true", "yes"}
        self.auto_updates_checkbox.setChecked(auto_updates)
        layout.addWidget(self.auto_updates_checkbox)
        self.update_notifications_checkbox = QCheckBox(self.texts["app_settings_update_notifications"])
        notifications = str(self.settings.value("updates/notifications", "true")).lower() in {"1", "true", "yes"}
        self.update_notifications_checkbox.setChecked(notifications)
        layout.addWidget(self.update_notifications_checkbox)
        self.check_updates_button = QPushButton(self.texts["app_settings_check_updates"])
        self.check_updates_button.setEnabled(self.update_check_callback is not None)
        if self.update_check_callback is not None:
            self.check_updates_button.clicked.connect(self.update_check_callback)
        layout.addWidget(self.check_updates_button)

        form = QFormLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItem(self.texts["theme_day"], "day")
        self.theme_combo.addItem(self.texts["theme_light"], "light")
        self.theme_combo.addItem(self.texts["theme_dark"], "dark")
        self.theme_combo.addItem(self.texts["theme_black"], "black")
        self.theme_combo.addItem(self.texts["theme_night"], "night")
        current_theme = str(self.settings.value("theme", "black"))
        theme_index = self.theme_combo.findData(current_theme)
        if theme_index >= 0:
            self.theme_combo.setCurrentIndex(theme_index)

        self.neon_checkbox = QCheckBox(self.texts["app_settings_neon_animate"])
        neon_enabled = str(self.settings.value("neon_animate", "true")).lower() in {"1", "true", "yes"}
        self.neon_checkbox.setChecked(neon_enabled)

        self.neon_color_combo = QComboBox()
        for label, value in NEON_PALETTE:
            self.neon_color_combo.addItem(label, value)
            index = self.neon_color_combo.count() - 1
            self.neon_color_combo.setItemData(index, QColor(value), Qt.ItemDataRole.DecorationRole)
        saved_color = normalize_accent_color(str(self.settings.value("accent_color", "#33f0ff")))
        color_index = self.neon_color_combo.findData(saved_color)
        if color_index < 0:
            self.neon_color_combo.addItem(saved_color, saved_color)
            self.neon_color_combo.setItemData(self.neon_color_combo.count() - 1, QColor(saved_color), Qt.ItemDataRole.DecorationRole)
            color_index = self.neon_color_combo.count() - 1
        self.neon_color_combo.setCurrentIndex(color_index)
        self.neon_color_combo.setEnabled(True)

        form.addRow(self.texts["app_settings_theme"], self.theme_combo)
        form.addRow(self.neon_checkbox)
        form.addRow(self.texts["app_settings_neon_color"], self.neon_color_combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
class CatalogRepositoryDialog(QDialog):
    def __init__(self, sources: List[str], texts: Dict[str, str], parent=None):
        super().__init__(parent)
        self.texts = texts
        self.sources = load_deployment_repository_sources()
        for source in sources:
            normalized = normalize_deployment_repository_source(source)
            if normalized and all(normalize_deployment_repository_source(existing) != normalized for existing in self.sources):
                self.sources.append(str(source).strip())
        self.setWindowTitle(self.texts["wizard_repo_title"])
        self.resize(760, 420)
        layout = QVBoxLayout(self)
        intro = QLabel(self.texts["wizard_repo_intro"] + "\n" + self.texts["wizard_repo_primary_hint"])
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.list_widget = QListWidget()
        for source in self.sources:
            self.add_source_item(source)
        layout.addWidget(self.list_widget, 1)
        row = QHBoxLayout()
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText(self.texts["wizard_repo_url"])
        self.btn_add = QPushButton(self.texts["wizard_repo_add"])
        self.btn_remove = QPushButton(self.texts["wizard_repo_remove"])
        self.btn_open = QPushButton(self.texts["wizard_repo_open"])
        row.addWidget(self.source_edit, 1)
        row.addWidget(self.btn_add)
        row.addWidget(self.btn_remove)
        row.addWidget(self.btn_open)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.btn_add.clicked.connect(self.add_source)
        self.btn_remove.clicked.connect(self.remove_source)
        self.btn_open.clicked.connect(self.open_source)
        self.source_edit.returnPressed.connect(self.add_source)
        self.list_widget.currentRowChanged.connect(self.update_remove_button)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        self.update_remove_button()

    def add_source_item(self, source: str):
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, source)
        if is_primary_deployment_repository(source):
            item.setText(f"{source}   [{self.texts['wizard_repo_primary']}]")
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            item.setToolTip(self.texts["wizard_repo_primary_hint"])
        else:
            item.setText(source)
        self.list_widget.addItem(item)

    def item_source(self, item: Optional[QListWidgetItem]) -> str:
        if item is None:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or item.text() or "").strip()

    def update_remove_button(self):
        source = self.item_source(self.list_widget.currentItem())
        self.btn_remove.setEnabled(bool(source) and not is_primary_deployment_repository(source))

    def add_source(self):
        source = self.source_edit.text().strip()
        if not source:
            return
        normalized = normalize_deployment_repository_source(source)
        existing = [normalize_deployment_repository_source(self.item_source(self.list_widget.item(i))) for i in range(self.list_widget.count())]
        if normalized and normalized not in existing:
            self.add_source_item(source)
        self.source_edit.clear()

    def remove_source(self):
        row = self.list_widget.currentRow()
        source = self.item_source(self.list_widget.currentItem())
        if row >= 0 and source and not is_primary_deployment_repository(source):
            self.list_widget.takeItem(row)
        self.update_remove_button()

    def open_source(self):
        item = self.list_widget.currentItem()
        source = self.item_source(item)
        if source and re.match(r"^https?://", source, re.IGNORECASE):
            webbrowser.open(source)

    def accept(self):
        self.sources = [self.item_source(self.list_widget.item(i)) for i in range(self.list_widget.count()) if self.item_source(self.list_widget.item(i))]
        super().accept()


class TwoLineElideLabel(QLabel):
    """A wrapping label that shows at most two lines and adds an ellipsis on overflow."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = ""
        self.setWordWrap(False)
        self.setText(text)

    def setText(self, text: str) -> None:  # type: ignore[override]
        self._full_text = str(text or "")
        self._refresh_elided_text()

    def fullText(self) -> str:
        return self._full_text

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_elided_text()

    def _refresh_elided_text(self) -> None:
        text = re.sub(r"\s+", " ", self._full_text).strip()
        if not text:
            super().setText("")
            return
        width = max(40, self.contentsRect().width())
        metrics = QFontMetrics(self.font())
        words = text.split(" ")
        lines: List[str] = []
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if metrics.horizontalAdvance(candidate) <= width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = word
            else:
                lines.append(self._elide_with_dots(word, metrics, width))
                current = ""
        if current:
            lines.append(current)
        if len(lines) <= 2:
            super().setText("\n".join(lines))
            return
        second_line = self._elide_with_dots(" ".join(lines[1:]), metrics, width)
        super().setText(f"{lines[0]}\n{second_line}")

    @staticmethod
    def _elide_with_dots(text: str, metrics: QFontMetrics, width: int) -> str:
        value = str(text or "")
        if metrics.horizontalAdvance(value) <= width:
            return value
        suffix = "..."
        if metrics.horizontalAdvance(suffix) >= width:
            return suffix
        while value and metrics.horizontalAdvance(value.rstrip() + suffix) > width:
            value = value[:-1]
        return value.rstrip() + suffix


class AspectRatioPixmapLabel(QLabel):
    """Keep a source pixmap fully visible and fit the label height to it."""

    def __init__(self, text: str = "", parent=None, max_content_height: int = 210):
        super().__init__(text, parent)
        self._source_pixmap = QPixmap()
        self._max_content_height = max(1, int(max_content_height))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def setSourcePixmap(self, pixmap: QPixmap) -> None:
        self._source_pixmap = QPixmap(pixmap)
        self._refresh_scaled_pixmap()

    def clear(self) -> None:  # type: ignore[override]
        self._source_pixmap = QPixmap()
        super().clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_scaled_pixmap()

    def _refresh_scaled_pixmap(self) -> None:
        if self._source_pixmap.isNull():
            return
        margins = self.contentsMargins()
        available_width = max(1, self.width() - margins.left() - margins.right())
        scaled = self._source_pixmap.scaled(
            QSize(available_width, self._max_content_height),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        super().setPixmap(scaled)
        desired_height = scaled.height() + margins.top() + margins.bottom()
        if self.height() != desired_height:
            self.setFixedHeight(desired_height)


class ContentFittingTabWidget(QTabWidget):
    """Keep store tabs responsive instead of inheriting the widest page minimum."""

    def minimumSizeHint(self) -> QSize:  # type: ignore[override]
        hint = super().minimumSizeHint()
        return QSize(min(hint.width(), max(360, self.minimumWidth())), min(hint.height(), 220))

    def sizeHint(self) -> QSize:  # type: ignore[override]
        hint = super().sizeHint()
        current = self.currentWidget()
        if current is not None:
            current_hint = current.sizeHint()
            tab_height = self.tabBar().sizeHint().height()
            hint.setHeight(max(260, current_hint.height() + tab_height + 16))
        return hint


class NewContainerDialog(QDialog):
    def __init__(self, client, texts: Dict[str, str], run_command_callback=None, parent=None, initial_args: Optional[List[str]] = None, edit_mode: bool = False, existing_name: str = "", llm_settings_getter=None, ai_command_callback=None, build_image_callback=None, lang: str = "EN", cli_command: str = "docker", cli_choices: Optional[List[str]] = None, remote_arch: str = "", target_host_label: str = ""):
        super().__init__(parent)
        self.client = client
        self.texts = texts
        self.run_command_callback = run_command_callback
        self.base_catalog = merge_catalog_lists(default_image_catalog(), load_bundled_deployment_catalog())
        self.repository_sources = load_deployment_repository_sources()
        self.external_catalog = load_cached_deployment_catalog()
        self.catalog = merge_catalog_lists(self.base_catalog, self.external_catalog)
        self.filtered_catalog = list(self.catalog)
        self._syncing = False
        self.manual_configuration_mode = True
        self.catalog_refresh_thread: Optional[QThread] = None
        self.catalog_refresh_worker: Optional[CatalogRefreshWorker] = None
        self._catalog_refresh_notify_on_finish = False
        self.initial_args = list(initial_args or [])
        self.edit_mode = edit_mode
        self.existing_name = existing_name.strip()
        self.llm_settings_getter = llm_settings_getter or (lambda: {})
        self.ai_command_callback = ai_command_callback
        self.build_image_callback = build_image_callback
        self.lang = (lang or "EN").upper()
        self.cli_command = (cli_command or "docker").lower()
        self.cli_choices = [str(item).lower() for item in (cli_choices or [self.cli_command]) if str(item).strip()]
        self.remote_arch = str(remote_arch or "").strip().lower()
        self.target_host_label = target_host_label.strip() or "Docker"
        self.catalog_theme = str(getattr(parent, "current_theme", "dark") or "dark").lower()
        if self.catalog_theme not in {"light", "day", "dark", "black", "night"}:
            self.catalog_theme = "dark"
        self.catalog_accent = effective_accent_color(
            self.catalog_theme,
            str(getattr(parent, "accent_color", DEFAULT_ACCENT_COLOR)),
        )
        self.store_network = QNetworkAccessManager(self)
        self._store_media_generation = 0

        self.setWindowTitle(self.texts["wizard_edit_title"] if self.edit_mode else self.texts["wizard_title"])
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        # Keep the deployment wizard usable on smaller/high-DPI displays.  The
        # old fixed 980x760 start size could extend below the available desktop
        # area once Windows display scaling was applied.
        screen = parent.screen() if parent is not None and parent.screen() is not None else QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        default_width = 1160
        default_height = 720
        if available is not None and available.isValid():
            default_width = min(default_width, max(520, int(available.width() * 0.92)))
            default_height = min(default_height, max(400, int(available.height() * 0.86)))
        self.setMinimumSize(480, 360)
        self.resize(default_width, default_height)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(6, 6, 6, 6)

        self.dialog_scroll_area = QScrollArea(self)
        self.dialog_scroll_area.setObjectName("newContainerScrollArea")
        self.dialog_scroll_area.setWidgetResizable(True)
        self.dialog_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.dialog_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.dialog_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.dialog_scroll_content = QWidget()
        self.dialog_scroll_content.setMinimumHeight(700)
        layout = QVBoxLayout(self.dialog_scroll_content)
        layout.setContentsMargins(4, 4, 4, 4)
        self.dialog_scroll_area.setWidget(self.dialog_scroll_content)
        outer_layout.addWidget(self.dialog_scroll_area, 1)

        store_header = QVBoxLayout()
        store_header.setSpacing(6)
        store_text = QVBoxLayout()
        subtitle = QLabel(self.texts["wizard_store_subtitle"])
        subtitle_font = subtitle.font()
        subtitle_font.setBold(True)
        subtitle.setFont(subtitle_font)
        subtitle.setWordWrap(True)
        subtitle.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)
        self.target_label = QLabel(self.texts["wizard_target_host"].format(host=self.target_host_label))
        target_font = self.target_label.font()
        target_font.setBold(True)
        target_font.setPointSize(max(10, target_font.pointSize() + 1))
        self.target_label.setFont(target_font)
        self.target_label.setWordWrap(True)
        self.target_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)
        store_text.addWidget(subtitle)
        self.target_host_frame = QFrame()
        self.target_host_frame.setObjectName("storeTargetHostFrame")
        target_host_layout = QHBoxLayout(self.target_host_frame)
        target_host_layout.setContentsMargins(10, 7, 10, 7)
        target_host_layout.setSpacing(8)
        self.target_host_icon = QLabel()
        self.target_host_icon.setFixedSize(24, 24)
        self.target_host_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        target_host_layout.addWidget(self.target_host_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        target_host_layout.addWidget(self.target_label, 1)
        store_text.addWidget(self.target_host_frame)
        store_header.addLayout(store_text)
        store_header_actions = QHBoxLayout()
        store_header_actions.setSpacing(8)
        self.store_header_actions = store_header_actions
        self.btn_repositories = QPushButton(self.texts["wizard_repositories"])
        self.btn_repo_refresh = QPushButton(self.texts["wizard_repo_refresh"])
        self.repo_status_label = QLabel(self.texts["wizard_repo_status_cached"])
        self.repo_status_label.setWordWrap(True)
        self.repo_status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)
        store_header_actions.addWidget(self.btn_repositories)
        store_header_actions.addWidget(self.btn_repo_refresh)
        store_header_actions.addWidget(self.repo_status_label, 1)
        store_header.addLayout(store_header_actions)
        layout.addLayout(store_header)

        self.store_toolbar_frame = QFrame()
        self.store_toolbar_frame.setObjectName("storeToolbarFrame")
        toolbar = QHBoxLayout(self.store_toolbar_frame)
        toolbar.setContentsMargins(12, 9, 12, 9)
        toolbar.setSpacing(6)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.texts["wizard_search"])
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumHeight(32)
        self.search_edit.setMinimumWidth(180)
        self.search_edit.setMaximumWidth(320)
        self.search_edit.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.category_combo = QComboBox()
        self.category_combo.addItem(self.texts["wizard_all_categories"])
        self.category_combo.addItem(self.texts["wizard_installed_category"])
        for category in self.catalog_category_names():
            self.category_combo.addItem(category)
        self.category_combo.setVisible(False)
        self.catalog_count_label = QLabel()
        self.catalog_count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.catalog_count_label.setMinimumWidth(90)
        self.catalog_count_label.setMaximumWidth(110)
        self.btn_manual_config = QPushButton(self.texts["wizard_manual"])
        self.btn_manual_config.setMinimumWidth(145)
        self.btn_manual_config.setMaximumWidth(170)
        self.btn_online_refresh = QPushButton(self.texts["wizard_online_refresh"])
        self.btn_online_refresh.setMinimumWidth(160)
        self.btn_online_refresh.setMaximumWidth(190)
        toolbar.addWidget(self.search_edit, 0)
        toolbar.addWidget(self.catalog_count_label, 0)
        toolbar.addStretch(1)
        toolbar.addWidget(self.btn_manual_config, 0)
        toolbar.addWidget(self.btn_online_refresh, 0)
        layout.addWidget(self.store_toolbar_frame)

        # Categories are a full-width, wrapping chip bar.  Keeping them above
        # the app list gives long translated names enough room and avoids the
        # cramped single-column sidebar on smaller displays.
        self.store_categories_title = QLabel(self.texts["wizard_store_categories"])
        self.store_categories_title.setObjectName("storeColumnTitle")
        layout.addWidget(self.store_categories_title)
        self.store_categories_frame = QFrame()
        self.store_categories_frame.setObjectName("storeCategoriesFrame")
        categories_layout = QVBoxLayout(self.store_categories_frame)
        categories_layout.setContentsMargins(8, 6, 8, 10)
        categories_layout.setSpacing(0)
        self.category_nav = StaticCategoryListWidget()
        self.category_nav.setObjectName("storeCategoryNav")
        # ListMode keeps the icon on the left and the full category label on
        # the right.  Combined with LeftToRight + wrapping this behaves like a
        # real responsive chip/flow layout instead of IconMode's fixed cells.
        self.category_nav.setViewMode(QListView.ViewMode.ListMode)
        self.category_nav.setFlow(QListView.Flow.LeftToRight)
        self.category_nav.setResizeMode(QListView.ResizeMode.Adjust)
        self.category_nav.setMovement(QListView.Movement.Static)
        self.category_nav.setWrapping(True)
        self.category_nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.category_nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.category_nav.setSpacing(4)
        self.category_nav.setWordWrap(False)
        self.category_nav.setUniformItemSizes(False)
        self.category_nav.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.category_nav.setIconSize(QSize(16, 16))
        self.category_nav.setItemDelegate(CategoryTileDelegate(self.category_nav))
        self.category_nav.setFixedHeight(120)
        categories_layout.addWidget(self.category_nav)
        layout.addWidget(self.store_categories_frame)

        self.catalog_row = QHBoxLayout()
        self.catalog_row.setSpacing(10)
        self.store_browser_frame = QFrame()
        self.store_browser_frame.setObjectName("storeBrowserFrame")
        browser_layout = QVBoxLayout(self.store_browser_frame)
        browser_layout.setContentsMargins(10, 10, 10, 10)
        browser_layout.setSpacing(6)

        apps_column = QVBoxLayout()
        apps_column.setSpacing(6)
        self.store_apps_title = QLabel(self.texts["wizard_store_apps"])
        self.store_apps_title.setObjectName("storeColumnTitle")
        apps_column.addWidget(self.store_apps_title)
        self.catalog_list = QListWidget()
        self.catalog_list.setObjectName("storeCatalogList")
        self.catalog_list.setMinimumWidth(270)
        self.catalog_list.setIconSize(QSize(44, 44))
        self.catalog_list.setSpacing(1)
        self.catalog_list.setWordWrap(False)
        self.catalog_list.setUniformItemSizes(False)
        apps_column.addWidget(self.catalog_list, 1)
        browser_layout.addLayout(apps_column, 1)
        self.catalog_row.addWidget(self.store_browser_frame, 2)

        self.editor_tabs = ContentFittingTabWidget()
        self.editor_tabs.setObjectName("storeEditorTabs")
        self.editor_tabs.setMinimumWidth(360)
        self.editor_tabs.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)

        self.store_tab = QWidget()
        self.store_tab.setObjectName("storeDescriptionPage")
        store_page_layout = QVBoxLayout(self.store_tab)
        store_page_layout.setContentsMargins(10, 9, 10, 9)
        store_page_layout.setSpacing(8)
        store_page_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.store_hero_card = QFrame()
        self.store_hero_card.setObjectName("storeHeroCard")
        hero_layout = QHBoxLayout(self.store_hero_card)
        hero_layout.setContentsMargins(12, 10, 12, 10)
        hero_layout.setSpacing(11)
        self.store_icon_label = QLabel()
        self.store_icon_label.setFixedSize(72, 72)
        self.store_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(self.store_icon_label, 0, Qt.AlignmentFlag.AlignTop)
        hero_text = QVBoxLayout()
        hero_text.setSpacing(4)
        self.store_title_label = QLabel()
        self.store_title_label.setObjectName("storeTitle")
        store_title_font = self.store_title_label.font()
        store_title_font.setBold(True)
        store_title_font.setPointSize(max(14, store_title_font.pointSize() + 5))
        self.store_title_label.setFont(store_title_font)
        self.store_category_label = QLabel()
        self.store_category_label.setObjectName("storeCategory")
        self.store_install_state_label = QLabel()
        self.store_install_state_label.setObjectName("storeInstallState")
        hero_text.addWidget(self.store_title_label)
        hero_text.addWidget(self.store_category_label)
        hero_text.addWidget(self.store_install_state_label)
        hero_text.addStretch()
        hero_layout.addLayout(hero_text, 1)
        self.btn_store_primary = QPushButton(self.texts["wizard_store_install"])
        self.btn_store_primary.setObjectName("primaryAction")
        self.btn_store_primary.setMinimumWidth(130)
        hero_layout.addWidget(self.btn_store_primary, 0, Qt.AlignmentFlag.AlignTop)
        store_page_layout.addWidget(self.store_hero_card)

        self.store_hero_image = AspectRatioPixmapLabel(
            self.texts["wizard_store_no_media"],
            max_content_height=210,
        )
        self.store_hero_image.setObjectName("storeHeroImage")
        self.store_hero_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.store_hero_image.setContentsMargins(8, 8, 8, 8)
        self.store_hero_image.setMinimumHeight(160)
        self.store_hero_image.setWordWrap(True)
        self.store_hero_image.setVisible(False)
        store_page_layout.addWidget(self.store_hero_image)

        self.store_description_label = QLabel()
        self.store_description_label.setObjectName("storeDescription")
        self.store_description_label.setWordWrap(True)
        self.store_description_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.store_description_label.setMinimumHeight(56)
        self.store_description_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        store_page_layout.addWidget(self.store_description_label)

        self.store_features_title = QLabel(self.texts["wizard_store_features"])
        self.store_features_title.setObjectName("storeSectionTitle")
        store_page_layout.addWidget(self.store_features_title)
        self.store_features_label = QLabel()
        self.store_features_label.setWordWrap(True)
        self.store_features_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.store_features_label.setMinimumHeight(80)
        self.store_features_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        store_page_layout.addWidget(self.store_features_label)

        self.store_metadata_label = QLabel()
        self.store_metadata_label.setObjectName("storeMetadata")
        self.store_metadata_label.setWordWrap(True)
        self.store_metadata_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.store_metadata_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        store_page_layout.addWidget(self.store_metadata_label)

        store_links = QHBoxLayout()
        self.btn_store_source = QPushButton(self.texts["wizard_source"])
        self.btn_store_docs = QPushButton(self.texts["wizard_docs"])
        self.btn_store_homepage = QPushButton(self.texts["wizard_homepage"])
        store_links.addWidget(self.btn_store_source)
        store_links.addWidget(self.btn_store_docs)
        store_links.addWidget(self.btn_store_homepage)
        store_links.addStretch()
        store_page_layout.addLayout(store_links)

        self.store_gallery_title = QLabel(self.texts["wizard_store_gallery"])
        self.store_gallery_title.setObjectName("storeSectionTitle")
        self.store_gallery_title.setVisible(False)
        store_page_layout.addWidget(self.store_gallery_title)
        gallery_layout = QHBoxLayout()
        gallery_layout.setSpacing(8)
        self.store_gallery_labels = []
        for _index in range(3):
            label = QLabel()
            label.setObjectName("storeGalleryImage")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumSize(110, 74)
            label.setMaximumHeight(112)
            label.setVisible(False)
            gallery_layout.addWidget(label, 1)
            self.store_gallery_labels.append(label)
        store_page_layout.addLayout(gallery_layout)
        self.editor_tabs.addTab(self.store_tab, self.texts["wizard_store_tab"])

        self.setup_tab = QWidget()
        self.setup_tab.setObjectName("storeSetupPage")
        setup_layout = QVBoxLayout(self.setup_tab)
        self.app_card = QFrame()
        self.app_card.setObjectName("catalogAppCard")
        app_card_layout = QVBoxLayout(self.app_card)
        app_card_layout.setContentsMargins(14, 12, 14, 12)
        app_card_layout.setSpacing(7)
        self.app_title_label = QLabel()
        self.app_title_label.setObjectName("catalogAppTitle")
        app_title_font = self.app_title_label.font()
        app_title_font.setPointSize(max(11, app_title_font.pointSize() + 2))
        app_title_font.setBold(True)
        self.app_title_label.setFont(app_title_font)
        self.app_category_label = QLabel()
        self.app_category_label.setObjectName("catalogAppCategory")
        self.app_description_label = QLabel()
        self.app_description_label.setObjectName("catalogAppDescription")
        self.app_description_label.setWordWrap(True)
        app_links = QHBoxLayout()
        self.btn_app_source = QPushButton(self.texts["wizard_source"])
        self.btn_app_docs = QPushButton(self.texts["wizard_docs"])
        self.btn_app_homepage = QPushButton(self.texts["wizard_homepage"])
        self.btn_quick_deploy = QPushButton(self.texts["wizard_quick_deploy"])
        app_links.addWidget(self.btn_app_source)
        app_links.addWidget(self.btn_app_docs)
        app_links.addWidget(self.btn_app_homepage)
        app_links.addStretch()
        app_links.addWidget(self.btn_quick_deploy)
        app_card_layout.addWidget(self.app_title_label)
        app_card_layout.addWidget(self.app_category_label)
        app_card_layout.addWidget(self.app_description_label)
        app_card_layout.addLayout(app_links)
        self._apply_catalog_card_style()
        setup_layout.addWidget(self.app_card)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.image_edit = QLineEdit()
        self.cport_edit = QLineEdit()
        self.hport_edit = QLineEdit()
        self.extra_edit = QLineEdit()
        self.command_edit = QLineEdit()
        self.cli_combo = QComboBox()
        configuration_field_height = max(30, self.fontMetrics().lineSpacing() + 12)
        for configuration_field in (
            self.name_edit,
            self.image_edit,
            self.cport_edit,
            self.hport_edit,
            self.extra_edit,
            self.command_edit,
            self.cli_combo,
        ):
            configuration_field.setMinimumHeight(configuration_field_height)
        for cli in self.cli_choices:
            self.cli_combo.addItem(cli, cli)
        if self.cli_command in self.cli_choices:
            self.cli_combo.setCurrentText(self.cli_command)
        self.cli_combo.setEnabled(len(self.cli_choices) > 1)
        form.addRow(self.texts["wizard_name"], self.name_edit)
        form.addRow(self.texts["wizard_image"], self.image_edit)
        form.addRow(self.texts["wizard_cport"], self.cport_edit)
        form.addRow(self.texts["wizard_hport"], self.hport_edit)
        form.addRow(self.texts["wizard_extra"], self.extra_edit)
        form.addRow(self.texts["wizard_cli"], self.cli_combo)
        form.addRow(self.texts["wizard_command_only"], self.command_edit)
        setup_layout.addLayout(form)
        self.engine_notice = QLabel(self.texts["wizard_balena_only"])
        self.engine_notice.setWordWrap(True)
        setup_layout.addWidget(self.engine_notice)

        self.command_input_label = QLabel(self.texts["wizard_command_input"])
        setup_layout.addWidget(self.command_input_label)
        command_row = QHBoxLayout()
        self.command_input = QPlainTextEdit()
        self.command_input.setPlaceholderText(f"{self.cli_command} run -d --name my-app -p 8080:80 nginx:alpine")
        self.command_input.setMaximumHeight(100)
        self.btn_parse_command = QPushButton(self.texts["wizard_parse"])
        self.btn_normalize_command = QPushButton(self.texts["wizard_normalize"])
        self.btn_ai_assistant = QPushButton(self.texts["wizard_ai_button"])
        command_buttons = QVBoxLayout()
        command_buttons.addWidget(self.btn_parse_command)
        command_buttons.addWidget(self.btn_normalize_command)
        command_buttons.addWidget(self.btn_ai_assistant)
        command_buttons.addStretch()
        command_row.addWidget(self.command_input, 1)
        command_row.addLayout(command_buttons)
        setup_layout.addLayout(command_row)

        setup_layout.addWidget(QLabel(self.texts["wizard_notes"]))
        self.notes_text = QPlainTextEdit()
        self.notes_text.setReadOnly(True)
        self.notes_text.setMaximumHeight(140)
        setup_layout.addWidget(self.notes_text)

        self.auto_fix_checkbox = QCheckBox(self.texts["wizard_auto_fix"])
        self.auto_fix_checkbox.setChecked(True)
        self.ai_repair_checkbox = QCheckBox(self.texts["wizard_ai_fallback"])
        self.ai_repair_checkbox.setChecked(False)
        setup_layout.addWidget(self.auto_fix_checkbox)
        setup_layout.addWidget(self.ai_repair_checkbox)

        setup_layout.addWidget(QLabel(self.texts["wizard_summary"]))
        self.summary_text = QPlainTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setMaximumHeight(110)
        setup_layout.addWidget(self.summary_text)
        self.editor_tabs.addTab(self.setup_tab, self.texts["wizard_setup_tab"])

        self.ai_tab = QWidget()
        self.ai_tab.setObjectName("storeAiPage")
        ai_layout = QVBoxLayout(self.ai_tab)
        self.ai_hint_label = QLabel(self.texts["llm_use_saved"])
        self.ai_hint_label.setWordWrap(True)
        ai_layout.addWidget(self.ai_hint_label)

        ai_form = QFormLayout()
        self.ai_provider_combo = QComboBox()
        for provider in LLM_PROVIDER_ORDER:
            self.ai_provider_combo.addItem(self.texts[LLM_PROVIDER_LABEL_KEYS[provider]], provider)
        self.ai_model_combo = QComboBox()
        self.ai_model_combo.setEditable(True)
        self.btn_ai_refresh_models = QPushButton(self.texts["llm_refresh_models"])
        ai_model_row = QHBoxLayout()
        ai_model_row.addWidget(self.ai_model_combo, 1)
        ai_model_row.addWidget(self.btn_ai_refresh_models)
        ai_form.addRow(self.texts["llm_provider"], self.ai_provider_combo)
        ai_form.addRow(self.texts["llm_model"], ai_model_row)
        ai_layout.addLayout(ai_form)

        ai_layout.addWidget(QLabel(self.texts["llm_request"]))
        self.ai_prompt_edit = QPlainTextEdit()
        self.ai_prompt_edit.setPlaceholderText(self.texts["llm_prompt_placeholder"])
        self.ai_prompt_edit.setMaximumHeight(120)
        ai_layout.addWidget(self.ai_prompt_edit)

        ai_layout.addWidget(QLabel(self.texts["llm_context"]))
        self.ai_context_text = QPlainTextEdit()
        self.ai_context_text.setReadOnly(True)
        self.ai_context_text.setMaximumHeight(110)
        ai_layout.addWidget(self.ai_context_text)

        ai_layout.addWidget(QLabel(self.texts["llm_result"]))
        self.ai_result_text = QPlainTextEdit()
        self.ai_result_text.setMaximumHeight(120)
        ai_layout.addWidget(self.ai_result_text)

        for text_box in [self.command_input, self.notes_text, self.summary_text, self.ai_context_text, self.ai_result_text, self.ai_prompt_edit]:
            text_box.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
            text_box.setCenterOnScroll(False)
            text_box.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.ai_status_label = QLabel(self.texts["llm_status_idle"])
        self.ai_status_label.setWordWrap(True)
        ai_layout.addWidget(self.ai_status_label)

        ai_buttons = QHBoxLayout()
        ai_buttons.addStretch()
        self.btn_ai_generate = QPushButton(self.texts["llm_generate"])
        self.btn_ai_apply = QPushButton(self.texts["llm_apply"])
        ai_buttons.addWidget(self.btn_ai_generate)
        ai_buttons.addWidget(self.btn_ai_apply)
        ai_layout.addLayout(ai_buttons)
        self.editor_tabs.addTab(self.ai_tab, self.texts["wizard_ai_tab"])

        self.catalog_row.addWidget(self.editor_tabs, 3, Qt.AlignmentFlag.AlignTop)
        self.editor_tabs.currentChanged.connect(lambda _index: self._fit_editor_tabs_height())
        layout.addLayout(self.catalog_row)

        self.search_edit.textChanged.connect(self.filter_catalog)
        self.category_combo.currentIndexChanged.connect(self.filter_catalog)
        self.category_combo.currentIndexChanged.connect(self._sync_category_sidebar_from_combo)
        self.category_nav.currentRowChanged.connect(self._on_category_sidebar_changed)
        self.catalog_list.currentRowChanged.connect(self.apply_selected_template)
        self.cli_combo.currentIndexChanged.connect(self.on_cli_changed)
        for widget in [self.name_edit, self.image_edit, self.cport_edit, self.hport_edit, self.extra_edit, self.command_edit]:
            widget.textChanged.connect(self.update_summary)
        self.btn_parse_command.clicked.connect(self.parse_command_input)
        self.btn_normalize_command.clicked.connect(self.normalize_command_input)
        self.btn_ai_assistant.clicked.connect(self.open_ai_assistant_tab)
        self.btn_ai_refresh_models.clicked.connect(lambda: self.load_ai_models(fetch=True))
        self.ai_provider_combo.currentIndexChanged.connect(lambda: self.load_ai_models(fetch=False))
        self.btn_ai_generate.clicked.connect(self.generate_ai_command)
        self.btn_ai_apply.clicked.connect(self.apply_ai_command)
        self.btn_online_refresh.clicked.connect(self.refresh_selected_description_online)
        self.btn_manual_config.clicked.connect(self.select_manual_configuration)
        self.btn_repositories.clicked.connect(self.manage_catalog_repositories)
        self.btn_repo_refresh.clicked.connect(self.refresh_external_catalogs)
        self.btn_app_source.clicked.connect(lambda: self.open_selected_app_url("source"))
        self.btn_app_docs.clicked.connect(lambda: self.open_selected_app_url("docs"))
        self.btn_app_homepage.clicked.connect(lambda: self.open_selected_app_url("homepage"))
        self.btn_quick_deploy.clicked.connect(self.on_run_clicked)
        self.btn_store_source.clicked.connect(lambda: self.open_selected_app_url("source"))
        self.btn_store_docs.clicked.connect(lambda: self.open_selected_app_url("docs"))
        self.btn_store_homepage.clicked.connect(lambda: self.open_selected_app_url("homepage"))
        self.btn_store_primary.clicked.connect(self.on_store_primary_action)

        self._populate_category_sidebar()
        self.filter_catalog()
        self.update_cli_labels()
        if self.initial_args:
            self.load_run_args(self.initial_args)
            self.select_manual_configuration()
        elif self.edit_mode:
            self.select_manual_configuration()
        elif self.catalog_list.count() > 0:
            # Normal deployment opens as an application store.  Manual mode is
            # still one click away and edit mode keeps the current container
            # parameters visible instead of silently replacing them.
            self.manual_configuration_mode = False
            self.catalog_list.setCurrentRow(0)
        else:
            self.select_manual_configuration()
        self.load_ai_models(fetch=False)
        self.update_summary()
        QTimer.singleShot(250, lambda: self.refresh_external_catalogs(silent=True))

    def _catalog_visual_colors(self) -> Dict[str, str]:
        palette = palette_for_theme(self.catalog_theme)
        if self.catalog_theme in {"day", "light"}:
            accent = QColor(self.catalog_accent)
            hue, saturation, value, alpha = accent.getHsvF()
            if hue >= 0 and value > 0.58:
                accent = QColor.fromHsvF(hue, max(0.60, saturation), 0.50, alpha)
            if self.catalog_theme == "day":
                return {
                    "accent": self.catalog_accent,
                    "accent_text": accent.name(),
                    "title": palette["fg"],
                    "description": palette["muted"],
                    "card_bg": "rgba(255, 255, 255, 142)",
                    "surface": "rgba(255, 255, 255, 112)",
                    "surface_alt": "rgba(235, 244, 248, 158)",
                    "border": "rgba(74, 96, 108, 118)",
                }
            return {
                "accent": self.catalog_accent,
                "accent_text": accent.name(),
                "title": palette["fg"],
                "description": palette["muted"],
                "card_bg": "rgba(248, 248, 249, 246)",
                "surface": "rgba(232, 233, 236, 246)",
                "surface_alt": "rgba(218, 220, 224, 242)",
                "border": "rgba(110, 114, 122, 110)",
            }
        if self.catalog_theme == "dark":
            return {
                "accent": self.catalog_accent,
                "accent_text": self.catalog_accent,
                "title": palette["fg"],
                "description": palette["muted"],
                "card_bg": "rgba(39, 41, 46, 238)",
                "surface": "rgba(29, 31, 35, 244)",
                "surface_alt": "rgba(52, 54, 60, 238)",
                "border": "rgba(118, 122, 132, 92)",
            }
        if self.catalog_theme == "night":
            return {
                "accent": self.catalog_accent,
                "accent_text": self.catalog_accent,
                "title": palette["fg"],
                "description": palette["muted"],
                "card_bg": "rgba(24, 18, 21, 244)",
                "surface": "rgba(13, 10, 13, 248)",
                "surface_alt": "rgba(38, 22, 27, 242)",
                "border": "rgba(136, 55, 66, 120)",
            }
        return {
            "accent": self.catalog_accent,
            "accent_text": self.catalog_accent,
            "title": palette["fg"],
            "description": palette["muted"],
            "card_bg": "rgba(24, 25, 28, 242)",
            "surface": "rgba(14, 15, 17, 246)",
            "surface_alt": "rgba(35, 37, 41, 240)",
            "border": "rgba(112, 116, 124, 88)",
        }

    def _apply_catalog_card_style(self):
        colors = self._catalog_visual_colors()
        if hasattr(self, "target_host_icon"):
            self.target_host_icon.setPixmap(
                make_category_icon("container", QColor(colors["accent"]), 18).pixmap(18, 18)
            )
        if hasattr(self, "target_host_frame"):
            self.target_host_frame.setStyleSheet(
                f"""
                QFrame#storeTargetHostFrame {{
                    border: 1px solid {colors['accent']};
                    border-radius: 10px;
                    background: {colors['surface_alt']};
                }}
                QLabel {{
                    color: {colors['title']};
                    background: transparent;
                }}
                """
            )
        self.store_toolbar_frame.setStyleSheet(
            f"""
            QFrame#storeToolbarFrame {{
                border: 1px solid {colors['border']};
                border-radius: 14px;
                background: {colors['surface']};
            }}
            QLineEdit {{
                border: 1px solid {colors['border']};
                border-radius: 10px;
                padding: 7px 11px;
                background: {colors['card_bg']};
                color: {colors['title']};
            }}
            QLabel {{ color: {colors['description']}; background: transparent; }}
            """
        )
        self.store_browser_frame.setStyleSheet(
            f"""
            QFrame#storeBrowserFrame {{
                border: 1px solid {colors['border']};
                border-radius: 16px;
                background: {colors['surface']};
            }}
            QLabel#storeColumnTitle {{
                color: {colors['title']};
                background: transparent;
                font-weight: 800;
                font-size: 12pt;
                padding: 3px 4px 7px 4px;
            }}
            """
        )
        self.store_categories_frame.setStyleSheet(
            f"""
            QFrame#storeCategoriesFrame {{
                border: 1px solid {colors['border']};
                border-radius: 14px;
                background: {colors['surface']};
            }}
            """
        )
        self.store_categories_title.setStyleSheet(
            f"""
            QLabel#storeColumnTitle {{
                color: {colors['title']};
                background: transparent;
                font-weight: 800;
                font-size: 10pt;
                padding: 2px 10px 0px 10px;
            }}
            """
        )
        self.category_nav.setStyleSheet(
            f"""
            QListWidget#storeCategoryNav {{
                border: none;
                background: transparent;
                outline: 0;
            }}
            QListWidget#storeCategoryNav::item {{
                color: {colors['description']};
                border: 1px solid {colors['border']};
                border-radius: 9px;
                background: {colors['card_bg']};
                padding: 3px 8px;
                margin: 1px;
            }}
            QListWidget#storeCategoryNav::item:hover {{
                color: {colors['title']};
                background: {colors['surface_alt']};
            }}
            QListWidget#storeCategoryNav::item:selected {{
                color: {colors['title']};
                border: 1px solid {colors['accent']};
                background: {colors['surface_alt']};
                font-weight: 700;
            }}
            """
        )
        self.editor_tabs.setStyleSheet(
            f"""
            QTabWidget#storeEditorTabs::pane {{
                border: 1px solid {colors['border']};
                border-radius: 12px;
                background: {colors['surface']};
                top: -1px;
            }}
            QTabWidget#storeEditorTabs QTabBar::tab {{
                color: {colors['description']};
                background: {colors['card_bg']};
                border: 1px solid {colors['border']};
                border-bottom: none;
                padding: 6px 12px;
                margin-right: 2px;
            }}
            QTabWidget#storeEditorTabs QTabBar::tab:selected {{
                color: {colors['title']};
                background: {colors['surface_alt']};
                border-color: {colors['accent']};
                font-weight: 700;
            }}
            QWidget#storeDescriptionPage,
            QWidget#storeSetupPage,
            QWidget#storeAiPage {{
                background: {colors['surface']};
            }}
            """
        )
        self.catalog_list.setStyleSheet(
            f"""
            QListWidget#storeCatalogList {{
                border: none;
                background: transparent;
                outline: 0;
            }}
            QListWidget#storeCatalogList::item {{
                border: 1px solid {colors['border']};
                border-radius: 12px;
                background: {colors['card_bg']};
                margin: 2px 1px;
                padding: 2px;
            }}
            QListWidget#storeCatalogList::item:hover {{
                border: 1px solid {colors['accent']};
                background: {colors['surface_alt']};
            }}
            QListWidget#storeCatalogList::item:selected {{
                border: 2px solid {colors['accent']};
                background: {colors['surface_alt']};
            }}
            """
        )
        self.app_card.setStyleSheet(
            f"""
            QFrame#catalogAppCard {{
                border: 1px solid {colors['accent']};
                border-radius: 12px;
                background: {colors['card_bg']};
            }}
            QLabel#catalogAppTitle {{
                color: {colors['title']};
                border: none;
                background: transparent;
                font-weight: 700;
            }}
            QLabel#catalogAppCategory {{
                color: {colors['accent_text']};
                border: none;
                background: transparent;
                font-weight: 600;
            }}
            QLabel#catalogAppDescription {{
                color: {colors['description']};
                border: none;
                background: transparent;
            }}
            """
        )
        self.store_hero_card.setStyleSheet(
            f"""
            QFrame#storeHeroCard {{
                border: 1px solid {colors['accent']};
                border-radius: 14px;
                background: {colors['card_bg']};
            }}
            QLabel#storeTitle {{ color: {colors['title']}; background: transparent; }}
            QLabel#storeCategory {{ color: {colors['accent_text']}; background: transparent; font-weight: 700; }}
            QLabel#storeInstallState {{ color: {colors['description']}; background: transparent; }}
            """
        )
        self.store_hero_image.setStyleSheet(
            f"border: 1px solid {colors['accent']}; border-radius: 12px; "
            f"background: {colors['card_bg']}; color: {colors['description']};"
        )
        for label in self.store_gallery_labels:
            label.setStyleSheet(
                f"border: 1px solid {colors['accent']}; border-radius: 10px; "
                f"background: {colors['card_bg']}; color: {colors['description']}; padding: 4px;"
            )
        self.store_description_label.setStyleSheet(f"color: {colors['title']}; background: transparent;")
        self.store_features_title.setStyleSheet(f"color: {colors['accent']}; background: transparent; font-weight: 700;")
        self.store_gallery_title.setStyleSheet(f"color: {colors['accent']}; background: transparent; font-weight: 700;")
        self.store_features_label.setStyleSheet(f"color: {colors['description']}; background: transparent;")
        self.store_metadata_label.setStyleSheet(f"color: {colors['description']}; background: transparent;")

    def _catalog_category_group(self, category: str) -> str:
        raw = str(category or "")
        if raw == self.texts["wizard_all_categories"]:
            return raw
        if raw == self.texts["wizard_installed_category"]:
            return raw
        if raw == self.texts["wizard_balena_category"]:
            return raw
        head = re.split(r"\s*[›/]\s*", raw, maxsplit=1)[0].strip()
        # Repository categories may contain emoji.  Keep them in catalog data,
        # but do not render them in the navigation because some Qt/font stacks
        # display them as tofu squares instead of glyphs.
        while head and not head[-1].isalnum():
            head = head[:-1].rstrip()
        return head or raw

    def _category_icon_kind(self, category: str) -> str:
        value = str(category or "").casefold()
        if category == self.texts["wizard_all_categories"]:
            return "all"
        if category == self.texts["wizard_installed_category"]:
            return "installed"
        if category == self.texts["wizard_balena_category"]:
            return "container"
        if value.startswith("ai"):
            return "ai"
        if "automat" in value:
            return "automation"
        if "monitor" in value:
            return "monitor"
        if "anality" in value or "analytics" in value or "finan" in value:
            return "analytics"
        if "sie" in value or "network" in value:
            return "network"
        if "bezpie" in value or "security" in value:
            return "security"
        if "backup" in value or "kopi" in value:
            return "backup"
        if "bazy" in value or "database" in value or "cache" in value:
            return "database"
        if "www" in value or "web" in value:
            return "web"
        if "smart home" in value or "iot" in value:
            return "home"
        if "media" in value:
            return "media"
        if "devops" in value:
            return "devops"
        if "runtime" in value or "system" in value or "baza" in value:
            return "system"
        if "powiad" in value or "messag" in value:
            return "messaging"
        if "produkt" in value:
            return "productivity"
        if "narz" in value or "tools" in value or "admin" in value:
            return "tools"
        return "generic"

    def _populate_category_sidebar(self):
        if not hasattr(self, "category_nav"):
            return
        current = self.category_combo.currentText()
        previous_block = self.category_nav.blockSignals(True)
        self.category_nav.clear()
        colors = self._catalog_visual_colors()
        accent = QColor(colors["accent"])
        accent_text = QColor(colors["accent_text"])
        special_bg = QColor(accent)
        special_bg.setAlpha(34)
        for index in range(self.category_combo.count()):
            category = self.category_combo.itemText(index)
            item = QListWidgetItem(category)
            item.setData(Qt.ItemDataRole.UserRole, category)
            item.setToolTip(category)
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            item.setIcon(make_category_icon(self._category_icon_kind(category), accent, 16))
            if category in {self.texts["wizard_all_categories"], self.texts["wizard_installed_category"]}:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setForeground(QBrush(accent_text))
                item.setBackground(QBrush(special_bg))
            self.category_nav.addItem(item)
        self.category_nav.blockSignals(previous_block)
        row = self.category_combo.findText(current)
        self.category_nav.setCurrentRow(max(0, row))
        QTimer.singleShot(0, self._update_category_nav_height)

    def _update_category_nav_height(self):
        if not hasattr(self, "category_nav") or self.category_nav.count() <= 0:
            return
        viewport_width = self.category_nav.viewport().width()
        available = max(260, viewport_width if viewport_width > 80 else self.width() - 40)
        count = self.category_nav.count()
        spacing = self.category_nav.spacing()
        tile_height = 34
        icon_and_gap = self.category_nav.iconSize().width() + 6
        # Account for the stylesheet's padding, border and item margins in
        # addition to the icon/text gap.  The former 20 px allowance was too
        # small for longer translated labels and clipped their final letters.
        horizontal_chrome = 40

        # Every chip follows the full label width with breathing room around
        # it.  Only a label wider than the whole viewport is constrained.
        self.category_nav.setGridSize(QSize())
        tile_widths: List[int] = []
        for index in range(count):
            item = self.category_nav.item(index)
            metrics = QFontMetrics(item.font())
            text_width = metrics.horizontalAdvance(item.text())
            tile_height = max(tile_height, metrics.lineSpacing() + 14)
            tile_width = max(88, text_width + icon_and_gap + horizontal_chrome)
            tile_width = max(88, min(tile_width, max(88, available - spacing * 2)))
            tile_widths.append(tile_width)
            item.setSizeHint(QSize(tile_width, tile_height))

        # Calculate the wrapped rows ourselves so the viewport is already tall
        # enough before Qt lays out the items.  This prevents an invisible
        # scroll range and guarantees that every category remains on screen.
        rows = 1
        used_width = 0
        row_limit = max(88, available - spacing)
        for tile_width in tile_widths:
            needed = tile_width if used_width == 0 else spacing + tile_width
            if used_width and used_width + needed > row_limit:
                rows += 1
                used_width = tile_width
            else:
                used_width += needed
        bottom_breathing_room = 12
        nav_height = rows * tile_height + (rows + 1) * spacing + bottom_breathing_room
        self.category_nav.setFixedHeight(nav_height)
        self.category_nav.doItemsLayout()

        # Keep a final safety margin when the platform style adds extra pixels.
        bottom = 0
        for index in range(count):
            rect = self.category_nav.visualItemRect(self.category_nav.item(index))
            if rect.isValid():
                bottom = max(bottom, rect.bottom() + 1)
        nav_height = max(nav_height, bottom + bottom_breathing_room)
        if self.category_nav.height() != nav_height:
            self.category_nav.setFixedHeight(nav_height)
        self.category_nav.lock_scroll_position()

        if hasattr(self, "store_categories_frame") and hasattr(self, "store_categories_title"):
            frame_layout = self.store_categories_frame.layout()
            margins = frame_layout.contentsMargins()
            frame_height = (
                margins.top()
                + nav_height
                + margins.bottom()
            )
            if self.store_categories_frame.height() != frame_height:
                self.store_categories_frame.setFixedHeight(frame_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "category_nav"):
            QTimer.singleShot(0, self._update_category_nav_height)
        if hasattr(self, "catalog_row"):
            QTimer.singleShot(0, self._update_store_responsive_layout)

    def _update_store_responsive_layout(self):
        if not hasattr(self, "catalog_row"):
            return
        viewport_width = self.dialog_scroll_area.viewport().width() if hasattr(self, "dialog_scroll_area") else self.width()
        compact = viewport_width < 1020
        direction = QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
        if self.catalog_row.direction() != direction:
            self.catalog_row.setDirection(direction)
        narrow_direction = QBoxLayout.Direction.TopToBottom if viewport_width < 650 else QBoxLayout.Direction.LeftToRight
        if hasattr(self, "store_header_actions") and self.store_header_actions.direction() != narrow_direction:
            self.store_header_actions.setDirection(narrow_direction)
        if compact:
            self.store_browser_frame.setMinimumHeight(300)
            self.store_browser_frame.setMaximumHeight(360)
        else:
            self.store_browser_frame.setMinimumHeight(0)
            self.store_browser_frame.setMaximumHeight(16777215)
        self._fit_editor_tabs_height()

    def _fit_editor_tabs_height(self):
        if not hasattr(self, "editor_tabs"):
            return
        current = self.editor_tabs.currentWidget()
        if current is None:
            return
        current_layout = current.layout()
        if current_layout is not None:
            current_layout.activate()
        desired = current.sizeHint().height() + self.editor_tabs.tabBar().sizeHint().height() + 12
        if current is self.store_tab:
            # The outer dialog already scrolls.  Let the description page use
            # its full natural height so hero media, description and feature
            # text cannot be compressed into overlapping rectangles.
            desired = max(230, desired)
        else:
            desired = max(360, min(desired, 760))
        self.editor_tabs.setMaximumHeight(desired)
        self.editor_tabs.updateGeometry()

    def _on_category_sidebar_changed(self, row: int):
        if row < 0 or row >= self.category_nav.count():
            return
        category = str(self.category_nav.item(row).data(Qt.ItemDataRole.UserRole) or "")
        index = self.category_combo.findText(category)
        if index >= 0 and index != self.category_combo.currentIndex():
            self.category_combo.setCurrentIndex(index)

    def _sync_category_sidebar_from_combo(self):
        if not hasattr(self, "category_nav"):
            return
        category = self.category_combo.currentText()
        for row in range(self.category_nav.count()):
            if self.category_nav.item(row).data(Qt.ItemDataRole.UserRole) == category:
                if self.category_nav.currentRow() != row:
                    previous_block = self.category_nav.blockSignals(True)
                    self.category_nav.setCurrentRow(row)
                    self.category_nav.blockSignals(previous_block)
                break

    def _catalog_list_item_widget(self, template: ImageTemplate, badges: str, description: str) -> QWidget:
        colors = self._catalog_visual_colors()
        card = QWidget()
        card.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        row = QHBoxLayout(card)
        row.setContentsMargins(5, 6, 8, 6)
        row.setSpacing(10)

        icon_label = QLabel()
        icon_label.setFixedSize(48, 48)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setPixmap(deployment_catalog_icon(template).pixmap(44, 44))
        icon_label.setStyleSheet("background: transparent;")
        row.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(1)

        name_label = QLabel(template.name)
        name_font = name_label.font()
        name_font.setBold(True)
        name_font.setPointSize(max(10, name_font.pointSize()))
        name_label.setFont(name_font)
        name_label.setStyleSheet(f"color: {colors['title']}; background: transparent;")

        badges_label = QLabel(badges)
        badges_label.setStyleSheet(
            f"color: {colors['accent']}; background: transparent; font-weight: 600;"
        )

        description_label = TwoLineElideLabel(description)
        description_height = QFontMetrics(description_label.font()).lineSpacing() * 2 + 6
        description_label.setMinimumHeight(description_height)
        description_label.setMaximumHeight(description_height)
        description_label.setStyleSheet(
            f"color: {colors['description']}; background: transparent;"
        )

        text_column.addWidget(name_label)
        text_column.addWidget(badges_label)
        if description:
            text_column.addWidget(description_label)
        row.addLayout(text_column, 1)
        return card

    def catalog_category_names(self) -> List[str]:
        categories = {
            self._catalog_category_group(item.category_for(self.lang))
            for item in self.catalog
            if item.category_for(self.lang)
        }
        if any(item.supports_engine("balena") for item in self.catalog):
            categories.add(self.texts["wizard_balena_category"])
        return sorted(categories, key=catalog_category_sort_key)

    def filter_catalog(self):
        selected = self.selected_catalog_template()
        selected_key = (selected.name.lower(), selected.image.lower()) if selected else None
        query = self.search_edit.text().strip().lower()
        category = self.category_combo.currentText().strip()
        self.filtered_catalog = []
        engine = self.current_cli()
        balena_view = category == self.texts["wizard_balena_category"]
        installed_view = category == self.texts["wizard_installed_category"]
        installed_containers = []
        if installed_view:
            try:
                installed_containers = list(self.client.containers.list(all=True))
            except Exception:
                installed_containers = []
        previous_block = self.catalog_list.blockSignals(True)
        self.catalog_list.clear()
        for item in self.catalog:
            if balena_view:
                if not item.supports_engine("balena"):
                    continue
            elif not item.supports_engine(engine):
                continue
            if self.remote_arch and not item.supports_arch(self.remote_arch):
                continue
            if installed_view and not any(template_matches_container(item, container) for container in installed_containers):
                continue
            if (
                not balena_view
                and not installed_view
                and category
                and category != self.texts["wizard_all_categories"]
                and self._catalog_category_group(item.category_for(self.lang)) != category
            ):
                continue
            haystack = f"{item.name} {item.image} {item.description_for(self.lang)} {item.notes_for(self.lang)}"
            if query and query not in haystack.lower():
                continue
            self.filtered_catalog.append(item)
            description = re.sub(r"\s+", " ", item.description_for(self.lang)).strip()
            badges = self._catalog_category_group(item.category_for(self.lang))
            if item.lightweight:
                badges += " \u00b7 light"
            if "balena" in [str(engine).lower() for engine in (item.engines or [])]:
                badges += " \u00b7 Balena"
            if item.repository_source:
                badges += " \u00b7 repo"
            label = f"{item.name}\n{badges}"
            if description:
                label += f"\n{description}"
            list_item = QListWidgetItem()
            list_item.setData(Qt.ItemDataRole.AccessibleTextRole, label)
            # Roughly 10% more height than the old 86/64 px rows.  This also
            # leaves enough room for descenders on the second description line.
            list_item.setSizeHint(QSize(320, 95 if description else 70))
            tooltip = f"{item.name}\n{item.image}"
            if item.source_url:
                tooltip += f"\n{item.source_url}"
            list_item.setToolTip(tooltip)
            self.catalog_list.addItem(list_item)
            self.catalog_list.setItemWidget(
                list_item,
                self._catalog_list_item_widget(item, badges, description),
            )
        self.catalog_list.blockSignals(previous_block)
        self.catalog_count_label.setText(self.texts["wizard_catalog_count"].format(count=self.catalog_list.count()))
        if self.manual_configuration_mode:
            self.catalog_list.setCurrentRow(-1)
            self.update_manual_store_card()
        elif selected_key:
            restored_row = next(
                (
                    index
                    for index, item in enumerate(self.filtered_catalog)
                    if (item.name.lower(), item.image.lower()) == selected_key
                ),
                -1,
            )
            self.catalog_list.setCurrentRow(restored_row)
            if restored_row < 0:
                self.select_manual_configuration()
        else:
            self.update_store_card(None)

    def selected_catalog_template(self) -> Optional[ImageTemplate]:
        if self.manual_configuration_mode:
            return None
        row = self.catalog_list.currentRow()
        if 0 <= row < len(self.filtered_catalog):
            return self.filtered_catalog[row]
        return None

    def update_store_card(self, template: Optional[ImageTemplate]):
        if template is None:
            self.app_title_label.setText("")
            self.app_category_label.setText("")
            self.app_category_label.setVisible(False)
            self.app_description_label.setText("")
            for button in (self.btn_app_source, self.btn_app_docs, self.btn_app_homepage, self.btn_quick_deploy):
                button.setEnabled(False)
            self.btn_quick_deploy.setText(
                self.texts["wizard_apply"] if self.edit_mode else self.texts["wizard_quick_deploy"]
            )
            self.update_store_description(None)
            return
        self.app_title_label.setText(template.name)
        self.app_category_label.setText(self._catalog_category_group(template.category_for(self.lang)))
        self.app_category_label.setVisible(True)
        description = template.description_for(self.lang) or template.image
        if template.latest_release:
            description += "\n" + self.texts["wizard_latest_release"].format(version=template.latest_release)
        self.app_description_label.setText(description)
        self.btn_app_source.setEnabled(bool(template.source_url))
        self.btn_app_docs.setEnabled(bool(template.docs_url))
        self.btn_app_homepage.setEnabled(bool(template.homepage_url))
        self.btn_quick_deploy.setText(
            self.texts["wizard_apply"] if self.edit_mode else self.texts["wizard_quick_deploy"]
        )
        self.btn_quick_deploy.setEnabled(True)
        self.update_store_description(template)

    def update_manual_store_card(self):
        image = self.image_edit.text().strip()
        if self.edit_mode and self.existing_name:
            self.app_title_label.setText(self.texts["wizard_current_container_title"].format(name=self.existing_name))
            self.app_category_label.setText("")
            self.app_category_label.setVisible(False)
            self.app_description_label.setText(
                self.texts["wizard_current_container_description"].format(image=image or "-")
            )
        else:
            self.app_title_label.setText(self.texts["wizard_manual_title"])
            self.app_category_label.setText("")
            self.app_category_label.setVisible(False)
            self.app_description_label.setText(self.texts["wizard_manual_description"])
        for button in (self.btn_app_source, self.btn_app_docs, self.btn_app_homepage):
            button.setEnabled(False)
        self.btn_quick_deploy.setText(
            self.texts["wizard_apply"] if self.edit_mode else self.texts["wizard_run"]
        )
        self.btn_quick_deploy.setEnabled(True)
        self.update_store_description(None)

    def matching_installed_containers(self, template: Optional[ImageTemplate]) -> List[object]:
        if template is None:
            return []
        try:
            containers = self.client.containers.list(all=True)
        except Exception:
            return []
        return [container for container in containers if template_matches_container(template, container)]

    def _store_media_cache_path(self, url: str) -> Path:
        suffix = Path(QUrl(url).path()).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            suffix = ".img"
        return STORE_MEDIA_CACHE_DIR / (hashlib.sha256(url.encode("utf-8")).hexdigest() + suffix)

    def _set_store_pixmap(self, label: QLabel, data: bytes, hero: bool = False) -> bool:
        pixmap = QPixmap()
        if not data or not pixmap.loadFromData(data):
            return False
        label.setText("")
        if isinstance(label, AspectRatioPixmapLabel):
            label.setSourcePixmap(pixmap)
        else:
            target = QSize(230, 125)
            scaled = pixmap.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            label.setPixmap(scaled)
        label.setVisible(True)
        if hasattr(self, "store_gallery_labels") and label in self.store_gallery_labels:
            self.store_gallery_title.setVisible(True)
        if hasattr(self, "editor_tabs"):
            QTimer.singleShot(0, self._fit_editor_tabs_height)
        return True

    def load_store_image(self, url: str, label: QLabel, hero: bool = False, generation: Optional[int] = None):
        url = str(url or "").strip()
        if not url:
            return
        qurl = QUrl(url)
        if qurl.isLocalFile():
            try:
                self._set_store_pixmap(label, Path(qurl.toLocalFile()).read_bytes(), hero=hero)
            except Exception:
                pass
            return
        if not re.match(r"^https?://", url, re.IGNORECASE):
            return
        cache_path = self._store_media_cache_path(url)
        try:
            if cache_path.exists() and cache_path.stat().st_size > 0:
                self._set_store_pixmap(label, cache_path.read_bytes(), hero=hero)
                return
        except Exception:
            pass
        request = QNetworkRequest(qurl)
        request.setRawHeader(b"User-Agent", f"DCC/{APP_VERSION}".encode("ascii", errors="ignore"))
        reply = self.store_network.get(request)
        expected_generation = self._store_media_generation if generation is None else generation

        def finished():
            try:
                if expected_generation != self._store_media_generation:
                    return
                data = bytes(reply.readAll())
                if data:
                    try:
                        cache_path.write_bytes(data)
                    except Exception:
                        pass
                    self._set_store_pixmap(label, data, hero=hero)
            finally:
                reply.deleteLater()

        reply.finished.connect(finished)

    def update_store_description(self, template: Optional[ImageTemplate]):
        self._store_media_generation += 1
        generation = self._store_media_generation
        self.store_hero_image.clear()
        self.store_hero_image.setVisible(False)
        self.store_gallery_title.setVisible(False)
        for label in self.store_gallery_labels:
            label.clear()
            label.setVisible(False)
        if template is None:
            title = self.texts["wizard_current_container_title"].format(name=self.existing_name) if self.edit_mode and self.existing_name else self.texts["wizard_manual_title"]
            self.store_title_label.setText(title)
            self.store_category_label.setText("")
            self.store_description_label.setText(self.texts["wizard_manual_description"])
            self.store_features_label.setText("")
            self.store_features_title.setVisible(False)
            self.store_features_label.setVisible(False)
            self.store_metadata_label.setText("")
            self.store_install_state_label.setText("")
            self.store_icon_label.clear()
            self.btn_store_primary.setEnabled(False)
            for button in (self.btn_store_source, self.btn_store_docs, self.btn_store_homepage):
                button.setEnabled(False)
            return

        self.store_title_label.setText(template.name)
        self.store_category_label.setText(self._catalog_category_group(template.category_for(self.lang)))
        self.store_description_label.setText(template.store_description_for(self.lang) or template.description_for(self.lang) or template.image)
        features = template.features_for(self.lang)
        features_text = "\n".join(f"- {item}" for item in features) if features else (template.notes_for(self.lang) or "")
        self.store_features_label.setText(features_text)
        self.store_features_title.setVisible(bool(features_text))
        self.store_features_label.setVisible(bool(features_text))
        requirements = []
        if template.latest_release:
            requirements.append(self.texts["wizard_latest_release"].format(version=template.latest_release))
        if template.ram_min_mb:
            requirements.append(f"RAM ≥ {template.ram_min_mb} MB")
        if template.gpu:
            requirements.append("GPU")
        if template.compose_required:
            requirements.append("Docker Compose")
        if template.archs:
            requirements.append("Arch: " + ", ".join(template.archs))
        if template.requires:
            requirements.append("Requires: " + ", ".join(template.requires))
        engines = ", ".join(template.engines or ["docker"])
        requirements.append("Engine: " + engines)
        self.store_metadata_label.setText("  ·  ".join(requirements))

        self.store_icon_label.setPixmap(deployment_catalog_icon(template).pixmap(78, 78))
        if template.icon_url:
            self.load_store_image(resolve_catalog_media_source(template, template.icon_url), self.store_icon_label, hero=False, generation=generation)
        gallery = list(template.gallery or [])
        hero_url = template.hero_image_url or (gallery[0].get("url", "") if gallery else "")
        if hero_url:
            self.load_store_image(resolve_catalog_media_source(template, hero_url), self.store_hero_image, hero=True, generation=generation)
        for label, entry in zip(self.store_gallery_labels, gallery[:3]):
            url = str(entry.get("url") or "")
            if url:
                caption = str(entry.get("caption_en") if self.lang == "EN" and entry.get("caption_en") else entry.get("caption") or "")
                label.setToolTip(caption)
                self.load_store_image(resolve_catalog_media_source(template, url), label, hero=False, generation=generation)

        self.btn_store_source.setEnabled(bool(template.source_url))
        self.btn_store_docs.setEnabled(bool(template.docs_url))
        self.btn_store_homepage.setEnabled(bool(template.homepage_url))
        installed = self.matching_installed_containers(template)
        if installed:
            self.store_install_state_label.setText(self.texts["wizard_store_installed"] + f" · {len(installed)}")
            self.btn_store_primary.setText(self.texts["wizard_store_uninstall"])
        else:
            self.store_install_state_label.setText(self.texts["wizard_store_not_installed"])
            self.btn_store_primary.setText(self.texts["wizard_store_install"])
        self.btn_store_primary.setEnabled(not self.edit_mode)
        self._fit_editor_tabs_height()

    def on_store_primary_action(self):
        template = self.selected_catalog_template()
        if template is None:
            return
        installed = self.matching_installed_containers(template)
        if not installed:
            self.on_run_clicked()
            return
        names = [str(getattr(container, "name", "") or "?") for container in installed]
        reply = QMessageBox.question(
            self,
            self.texts["wizard_store_uninstall_title"],
            self.texts["wizard_store_uninstall_confirm"].format(count=len(installed), names="\n".join(names)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            for container in installed:
                container.remove(force=True)
        except Exception as exc:
            QMessageBox.critical(self, self.texts["msg_error"], str(exc))
            return
        QMessageBox.information(self, self.texts["msg_info"], self.texts["wizard_store_uninstall_done"])
        if self.category_combo.currentText().strip() == self.texts["wizard_installed_category"]:
            self.filter_catalog()
        else:
            self.update_store_description(template)

    def select_manual_configuration(self):
        self.manual_configuration_mode = True
        previous_block = self.catalog_list.blockSignals(True)
        self.catalog_list.clearSelection()
        self.catalog_list.setCurrentRow(-1)
        self.catalog_list.blockSignals(previous_block)
        self.update_manual_store_card()
        self.update_summary()

    def open_selected_app_url(self, kind: str):
        template = self.selected_catalog_template()
        if not template:
            return
        url = {
            "source": template.source_url,
            "docs": template.docs_url,
            "homepage": template.homepage_url,
        }.get(kind, "")
        if url and re.match(r"^https?://", url, re.IGNORECASE):
            webbrowser.open(url)

    def rebuild_catalog_categories(self):
        current = self.category_combo.currentText().strip()
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem(self.texts["wizard_all_categories"])
        self.category_combo.addItem(self.texts["wizard_installed_category"])
        for category in self.catalog_category_names():
            self.category_combo.addItem(category)
        if current:
            index = self.category_combo.findText(current)
            if index >= 0:
                self.category_combo.setCurrentIndex(index)
        self.category_combo.blockSignals(False)
        self._populate_category_sidebar()

    def manage_catalog_repositories(self):
        dialog = CatalogRepositoryDialog(self.repository_sources, self.texts, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.repository_sources = dialog.sources
        save_deployment_repository_sources(self.repository_sources)
        self.refresh_external_catalogs()

    def refresh_external_catalogs(self, silent: bool = False):
        if self.catalog_refresh_thread is not None and self.catalog_refresh_thread.isRunning():
            if not silent:
                self._catalog_refresh_notify_on_finish = True
            return

        previous_by_source: Dict[str, List[ImageTemplate]] = {}
        for item in self.external_catalog:
            previous_by_source.setdefault(item.repository_source, []).append(item)

        self._catalog_refresh_notify_on_finish = not silent
        self.btn_repo_refresh.setEnabled(False)
        self.repo_status_label.setText(self.texts["wizard_repo_syncing"])
        thread_parent = self.parent() if isinstance(self.parent(), QObject) else QApplication.instance()
        self.catalog_refresh_thread = QThread(thread_parent)
        self.catalog_refresh_worker = CatalogRefreshWorker(self.repository_sources, previous_by_source)
        self.catalog_refresh_worker.moveToThread(self.catalog_refresh_thread)
        self.catalog_refresh_thread.started.connect(self.catalog_refresh_worker.run)
        self.catalog_refresh_worker.finished.connect(self.on_external_catalog_refresh_finished)
        self.catalog_refresh_worker.finished.connect(self.catalog_refresh_thread.quit)
        self.catalog_refresh_worker.finished.connect(self.catalog_refresh_worker.deleteLater)
        self.catalog_refresh_thread.finished.connect(self.on_catalog_refresh_thread_finished)
        self.catalog_refresh_thread.finished.connect(self.catalog_refresh_thread.deleteLater)
        self.catalog_refresh_thread.start()

    def on_external_catalog_refresh_finished(self, refreshed: List[ImageTemplate], errors: List[str]):
        self.external_catalog = list(refreshed)
        save_cached_deployment_catalog(self.external_catalog)
        self.catalog = merge_catalog_lists(self.base_catalog, self.external_catalog)
        self.rebuild_catalog_categories()
        self.filter_catalog()

        if errors:
            self.repo_status_label.setText(self.texts["wizard_repo_status_partial"].format(count=len(self.external_catalog)))
            if self._catalog_refresh_notify_on_finish:
                QMessageBox.warning(self, self.texts["msg_error"], self.texts["wizard_repo_errors"].format(errors="\n".join(errors)))
        else:
            self.repo_status_label.setText(self.texts["wizard_repo_status_updated"].format(count=len(self.external_catalog)))
            if self._catalog_refresh_notify_on_finish:
                QMessageBox.information(self, self.texts["msg_info"], self.texts["wizard_repo_loaded"].format(count=len(self.external_catalog)))

    def on_catalog_refresh_thread_finished(self):
        self.btn_repo_refresh.setEnabled(True)
        self.catalog_refresh_worker = None
        self.catalog_refresh_thread = None
        self._catalog_refresh_notify_on_finish = False

    def set_text_preserving_view(self, widget, text: str, block_signals: bool = False):
        if widget.toPlainText() == text:
            return
        vbar = widget.verticalScrollBar()
        previous_v = vbar.value()
        was_at_bottom = previous_v >= max(0, vbar.maximum() - 2)
        previous_block = widget.blockSignals(block_signals)
        widget.setPlainText(text)
        if block_signals:
            widget.blockSignals(previous_block)

        def restore_scroll():
            if was_at_bottom:
                vbar.setValue(vbar.maximum())
            else:
                vbar.setValue(min(previous_v, vbar.maximum()))
            widget.horizontalScrollBar().setValue(0)

        QTimer.singleShot(0, restore_scroll)
        QTimer.singleShot(25, restore_scroll)
        QTimer.singleShot(60, restore_scroll)

    def apply_selected_template(self, row: int):
        if row < 0 or row >= len(self.filtered_catalog) or self._syncing:
            if self.manual_configuration_mode:
                self.update_manual_store_card()
            else:
                self.update_store_card(None)
            return
        self.manual_configuration_mode = False
        template = self.filtered_catalog[row]
        self.update_store_card(template)
        self._syncing = True
        self.name_edit.setText(template.default_name)
        self.image_edit.setText(template.image)
        self.cport_edit.setText(template.container_port)
        self.hport_edit.setText(template.host_port)
        self.extra_edit.setText(template.extra)
        self.command_edit.setText(template.command)
        notes = template.description_for(self.lang)
        notes_extra = template.notes_for(self.lang)
        if notes_extra:
            notes += f"\n\n{notes_extra}"
        self.set_text_preserving_view(self.notes_text, notes)
        self._syncing = False
        self.load_ai_models(fetch=False)
        self.update_summary()

    def build_run_args(self) -> List[str]:
        name = self.name_edit.text().strip()
        image = self.image_edit.text().strip()
        cport = self.cport_edit.text().strip()
        hport = self.hport_edit.text().strip() or cport
        extra = self.extra_edit.text().strip()
        command = self.command_edit.text().strip()
        args = ["run", "-d"]
        selected_template = self.selected_catalog_template()
        if selected_template is not None and self.current_cli() == "docker":
            # Catalog images normally refresh before deployment. Source-built
            # applications are different: the image was just built locally on
            # the selected host and may not exist in any registry at all.
            # Explicitly prevent Docker from trying Docker Hub after a
            # successful source build (e.g. SmartWAN Manager).
            if selected_template.build_context:
                args.extend(["--pull", "never"])
            else:
                args.extend(["--pull", "always"])
        if name:
            args.extend(["--name", name])
        if cport:
            args.extend(["-p", f"{hport}:{cport}"])
        if extra:
            args.extend(shlex.split(extra))
        if image:
            args.append(image)
        if command:
            args.extend(shlex.split(command))
        return args

    def load_run_args(self, args: List[str]):
        prefix = self.current_cli()
        rendered = prefix + " " + " ".join(shlex.quote(str(part)) for part in args)
        self.set_text_preserving_view(self.command_input, rendered, block_signals=True)
        self.parse_command_input()

    def current_cli(self) -> str:
        return (self.cli_combo.currentData() or self.cli_command or "docker").lower()

    def set_cli_command(self, cli: str):
        cli = str(cli or "").lower()
        index = self.cli_combo.findData(cli)
        if index >= 0:
            self.cli_combo.blockSignals(True)
            self.cli_combo.setCurrentIndex(index)
            self.cli_combo.blockSignals(False)
        self.update_cli_labels()
        self.filter_catalog()

    def update_cli_labels(self):
        prefix = self.current_cli()
        self.command_input_label.setText(self.texts["wizard_command_input"].replace("docker", prefix))
        self.command_input.setPlaceholderText(f"{prefix} run -d --name my-app -p 8080:80 nginx:alpine")
        self.ai_prompt_edit.setPlaceholderText(self.texts["llm_prompt_placeholder"].replace("docker", prefix))
        self.engine_notice.setVisible(prefix == "balena")

    def on_cli_changed(self):
        self.update_cli_labels()
        self.filter_catalog()
        self.update_summary()

    def update_summary(self):
        if self._syncing:
            return
        if self.manual_configuration_mode:
            self.update_manual_store_card()
        args = self.build_run_args()
        if len(args) <= 2:
            self.set_text_preserving_view(self.summary_text, "")
            self.refresh_ai_context()
            return
        prefix = self.current_cli()
        summary = prefix + " " + " ".join(shlex.quote(part) for part in args)
        self.set_text_preserving_view(self.summary_text, summary)
        self.set_text_preserving_view(self.command_input, summary, block_signals=True)
        self.refresh_ai_context()

    def populate_combo_values(self, combo: QComboBox, values: List[str], selected: str = ""):
        combo.blockSignals(True)
        combo.clear()
        seen = set()
        for value in values:
            value = str(value).strip()
            if value and value not in seen:
                combo.addItem(value)
                seen.add(value)
        if selected and selected not in seen:
            combo.addItem(selected)
        if selected:
            combo.setCurrentText(selected)
        combo.blockSignals(False)

    def current_ai_context(self) -> str:
        current = self.summary_text.toPlainText().strip() or self.command_input.toPlainText().strip()
        if current:
            return current
        image = self.image_edit.text().strip() or "<image>"
        return f"{self.current_cli()} run -d {image}"

    def refresh_ai_context(self):
        self.set_text_preserving_view(self.ai_context_text, self.current_ai_context())

    def open_ai_assistant_tab(self):
        self.refresh_ai_context()
        self.load_ai_models(fetch=False)
        self.editor_tabs.setCurrentWidget(self.ai_tab)

    def normalize_command_input(self):
        raw = normalize_docker_command_text(self.command_input.toPlainText())
        self.set_text_preserving_view(self.command_input, raw, block_signals=True)

    def load_ai_models(self, fetch: bool = False):
        llm_settings = dict(self.llm_settings_getter() or {})
        saved_provider = str(llm_settings.get("provider", "ollama")).strip().lower()
        if saved_provider not in LLM_PROVIDER_ORDER:
            saved_provider = "ollama"
        if self.ai_model_combo.count() == 0:
            index = self.ai_provider_combo.findData(saved_provider)
            if index >= 0:
                self.ai_provider_combo.setCurrentIndex(index)
        provider = str(self.ai_provider_combo.currentData() or saved_provider or "ollama").strip().lower()
        models = llm_default_models(provider)
        selected = llm_selected_model(llm_settings, provider)
        if fetch:
            api_key = str(llm_settings.get(f"{provider}_api_key", "")).strip() if provider != "ollama" else ""
            if provider != "ollama" and not api_key:
                provider_name = self.texts.get(LLM_PROVIDER_LABEL_KEYS.get(provider, ""), provider)
                QMessageBox.warning(
                    self,
                    self.texts["msg_error"],
                    self.texts["llm_api_key_missing"].format(provider=provider_name),
                )
                return
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                models = fetch_provider_models(
                    provider,
                    api_key=api_key,
                    ollama_url=str(llm_settings.get("ollama_url", "http://127.0.0.1:11434")),
                )
                if selected not in models:
                    selected = select_ollama_fallback_model(models) if provider == "ollama" else models[0]
                self.ai_status_label.setText(self.texts["llm_models_ready"])
            except Exception as exc:
                self.ai_status_label.setText(f'{self.texts["llm_models_failed"]} {exc}')
            finally:
                QApplication.restoreOverrideCursor()
        self.populate_combo_values(self.ai_model_combo, models, selected)
        self.refresh_ai_context()

    def generate_ai_command(self):
        prompt = self.ai_prompt_edit.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, self.texts["msg_error"], self.texts["llm_prompt_required"])
            return
        if self.ai_command_callback is None:
            QMessageBox.warning(self, self.texts["msg_error"], self.texts["llm_status_error"])
            return
        self.refresh_ai_context()
        self.ai_status_label.setText(self.texts["llm_status_working"])
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            provider = str(self.ai_provider_combo.currentData() or "ollama")
            selected_model = self.ai_model_combo.currentText().strip()
            fallback_message = ""
            if provider == "ollama":
                llm_settings = dict(self.llm_settings_getter() or {})
                base_url = str(llm_settings.get("ollama_url", "http://127.0.0.1:11434")).strip()
                available_models = fetch_ollama_models(base_url)
                if available_models and selected_model not in available_models:
                    fallback_model = select_ollama_fallback_model(available_models)
                    fallback_message = self.texts["wizard_model_fallback"].format(old=selected_model or "?", new=fallback_model)
                    selected_model = fallback_model
                    self.populate_combo_values(self.ai_model_combo, available_models, selected_model)
            command = self.ai_command_callback(
                provider=provider,
                model=selected_model,
                prompt=prompt,
                current_command=self.current_ai_context(),
                image=self.image_edit.text().strip(),
                edit_mode=self.edit_mode,
                runtime_context=self.build_ai_runtime_context(),
            )
            command = normalize_docker_command_text(extract_docker_run_command(command))
            desired = self.current_cli()
            if desired == "balena":
                if command.lower().startswith("docker run"):
                    command = "balena run" + command[len("docker run"):]
                if not command.lower().startswith("balena run"):
                    raise RuntimeError(self.texts["llm_response_invalid"])
            else:
                if command.lower().startswith("balena run"):
                    command = "docker run" + command[len("balena run"):]
                if not command.lower().startswith("docker run"):
                    raise RuntimeError(self.texts["llm_response_invalid"])
            self.set_text_preserving_view(self.ai_result_text, command)
            status = self.texts["llm_status_done"]
            if fallback_message:
                status += f" {fallback_message}"
            self.ai_status_label.setText(status)
        except Exception as exc:
            self.ai_status_label.setText(f'{self.texts["llm_status_error"]} {exc}')
        finally:
            QApplication.restoreOverrideCursor()

    def apply_ai_command(self):
        command = normalize_docker_command_text(self.ai_result_text.toPlainText())
        if not command:
            return
        self.set_text_preserving_view(self.command_input, command, block_signals=True)
        self.parse_command_input()
        self.ai_status_label.setText(self.texts["llm_apply_done"])
        self.editor_tabs.setCurrentWidget(self.setup_tab)

    def _parse_port_mapping(self, port_map: str) -> Optional[tuple[str, str]]:
        raw = str(port_map).strip()
        if not raw:
            return None
        parts = raw.split(":")
        if len(parts) < 2:
            return None
        host_port = parts[-2]
        container_part = parts[-1]
        return host_port, container_part.split("/")[0]

    def parse_command_input(self):
        raw = normalize_docker_command_text(self.command_input.toPlainText())
        if not raw:
            return
        self.set_text_preserving_view(self.command_input, raw, block_signals=True)
        try:
            tokens = shlex.split(raw)
        except Exception:
            QMessageBox.warning(self, self.texts["msg_error"], self.texts["wizard_command_invalid"])
            return
        if len(tokens) >= 2 and tokens[0] in {"docker", "balena"} and tokens[1] == "run":
            if self.current_cli() == "balena" and tokens[0] == "docker":
                QMessageBox.information(self, self.texts["msg_info"], self.texts["wizard_balena_notice"])
                self.set_cli_command("balena")
            else:
                self.set_cli_command(tokens[0])
            tokens = tokens[2:]
        elif tokens and tokens[0] == "run":
            tokens = tokens[1:]
        extras = []
        name = ""
        cport = ""
        hport = ""
        image = ""
        command = []
        i = 0
        no_value_flags = {
            "--rm", "--privileged", "--init", "--read-only", "--tty", "--interactive",
            "--sig-proxy", "--oom-kill-disable", "--publish-all",
            "-i", "-t", "-it", "-ti", "-P",
        }
        while i < len(tokens):
            token = tokens[i]
            if token == "-d":
                i += 1
                continue
            if token == "--name" and i + 1 < len(tokens):
                name = tokens[i + 1]
                i += 2
                continue
            if token.startswith("--name="):
                name = token.split("=", 1)[1]
                i += 1
                continue
            if token in {"-p", "--publish"} and i + 1 < len(tokens):
                port_map = tokens[i + 1]
                parsed = self._parse_port_mapping(port_map)
                if parsed and not cport and not hport:
                    hport, cport = parsed
                else:
                    extras.extend([token, port_map])
                i += 2
                continue
            if token.startswith("--publish="):
                port_map = token.split("=", 1)[1]
                parsed = self._parse_port_mapping(port_map)
                if parsed and not cport and not hport:
                    hport, cport = parsed
                else:
                    extras.append(token)
                i += 1
                continue
            if token.startswith("-p") and token != "-p":
                port_map = token[2:]
                parsed = self._parse_port_mapping(port_map)
                if parsed and not cport and not hport:
                    hport, cport = parsed
                else:
                    extras.extend(["-p", port_map])
                i += 1
                continue
            if token.startswith("-"):
                extras.append(token)
                expects_value = token not in no_value_flags and not (token.startswith("--") and "=" in token)
                if expects_value and i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                    extras.append(tokens[i + 1])
                    i += 2
                else:
                    i += 1
                continue
            image = token
            command = tokens[i + 1:]
            break
        self._syncing = True
        self.name_edit.setText(name)
        self.image_edit.setText(image)
        self.cport_edit.setText(cport)
        self.hport_edit.setText(hport)
        self.extra_edit.setText(" ".join(shlex.quote(part) for part in extras))
        self.command_edit.setText(" ".join(shlex.quote(part) for part in command))
        self._syncing = False
        self.update_notes_from_image(image)
        self.load_ai_models(fetch=False)
        self.update_summary()

    def update_notes_from_image(self, image: str):
        match = next((item for item in self.catalog if item.image == image), None)
        if match:
            notes = match.description_for(self.lang)
            notes_extra = match.notes_for(self.lang)
            if notes_extra:
                notes += f"\n\n{notes_extra}"
            self.set_text_preserving_view(self.notes_text, notes)
        elif image:
            self.set_text_preserving_view(self.notes_text, image)

    def refresh_selected_description_online(self):
        image = self.image_edit.text().strip()
        if not image:
            return
        self.set_text_preserving_view(self.notes_text, self.texts["wizard_catalog_loading"])
        try:
            description = fetch_docker_hub_description(image)
            if description:
                self.set_text_preserving_view(self.notes_text, description)
            else:
                self.update_notes_from_image(image)
        except Exception:
            self.update_notes_from_image(image)

    def get_port_usage(self, ignore_name: str = "") -> Dict[str, List[str]]:
        usage: Dict[str, List[str]] = {}
        for container in self.client.containers.list(all=True):
            if ignore_name and getattr(container, "name", "") == ignore_name:
                continue
            ports = container.attrs.get("NetworkSettings", {}).get("Ports", {}) or {}
            for cont_port, mappings in ports.items():
                for mapping in mappings or []:
                    host_port = mapping.get("HostPort")
                    if host_port:
                        usage.setdefault(host_port, []).append(f"{container.name}({cont_port})")
        return usage

    def build_ai_runtime_context(self) -> str:
        lines = []
        try:
            containers = self.client.containers.list(all=True)
        except Exception as exc:
            return f"Could not inspect current containers: {exc}"
        for container in containers:
            if self.existing_name and getattr(container, "name", "") == self.existing_name:
                marker = " [currently edited]"
            else:
                marker = ""
            attrs = getattr(container, "attrs", {}) or {}
            config = attrs.get("Config", {}) or {}
            image_name = str(config.get("Image") or attrs.get("Image") or "?")
            mappings = []
            for cont_port, entries in ((attrs.get("NetworkSettings", {}) or {}).get("Ports", {}) or {}).items():
                for entry in entries or []:
                    host_port = str(entry.get("HostPort") or "").strip()
                    host_ip = str(entry.get("HostIp") or "").strip()
                    if host_port:
                        mappings.append(f"{host_ip or '0.0.0.0'}:{host_port}->{cont_port}")
            lines.append(
                f"- {getattr(container, 'name', '?')}{marker}: image={image_name}, "
                f"status={getattr(container, 'status', '?')}, ports={', '.join(mappings) or 'none'}"
            )
        usage = self.get_port_usage(self.existing_name if self.edit_mode else "")
        used = ", ".join(f"{port} ({'/'.join(users)})" for port, users in sorted(usage.items(), key=lambda item: int(item[0]) if item[0].isdigit() else 999999))
        return (
            f"Target engine: {self.current_cli()}\n"
            f"Target architecture: {self.remote_arch or 'unknown/local'}\n"
            f"Published host ports already in use: {used or 'none'}\n"
            "Current containers:\n" + ("\n".join(lines) if lines else "- none")
        )

    def collect_post_install_access_details(self, args: List[str], template: Optional[ImageTemplate]) -> List[tuple[str, str]]:
        name = container_name_from_run_args(args)
        if not name:
            return []
        for attempt in range(8):
            try:
                container = self.client.containers.get(name)
                raw = container.logs(tail=300)
                if isinstance(raw, bytes):
                    log_text = raw.decode("utf-8", errors="ignore")
                else:
                    log_text = str(raw or "")
                detected = parse_credentials_from_logs(log_text, template, self.lang)
                if detected:
                    return detected
            except Exception:
                pass
            if attempt < 7:
                QApplication.processEvents()
                time.sleep(0.25)
        return []

    def on_run_clicked(self):
        selected_template = self.selected_catalog_template()
        image = self.image_edit.text().strip()
        if not image:
            QMessageBox.warning(self, self.texts["msg_error"], self.texts["wizard_image"])
            return
        if (
            selected_template is not None
            and selected_template.build_context
            and not self.edit_mode
            and self.build_image_callback is not None
        ):
            try:
                if self.build_image_callback(selected_template) is False:
                    return
            except Exception as exc:
                QMessageBox.critical(self, self.texts["msg_error"], str(exc))
                return
        args = self.build_run_args()
        usage = self.get_port_usage(self.existing_name if self.edit_mode else "")
        try:
            existing_names = [getattr(container, "name", "") for container in self.client.containers.list(all=True)]
        except Exception:
            existing_names = []
        if self.auto_fix_checkbox.isChecked():
            repaired_args, changes = safe_repair_run_args(args, usage, existing_names, self.existing_name if self.edit_mode else "")
            if changes:
                change_lines = []
                for kind, old, new in changes:
                    key = "wizard_safe_name_change" if kind == "name" else "wizard_safe_port_change"
                    change_lines.append(self.texts[key].format(old=old, new=new))
                reply = QMessageBox.question(
                    self,
                    self.texts["wizard_safe_changes_title"],
                    self.texts["wizard_safe_changes_body"].format(changes="\n".join(change_lines)),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
                args = repaired_args
                self.load_run_args(args)
        else:
            conflicts = []
            for hport in published_host_ports(args):
                if hport in usage:
                    conflicts.append((hport, ", ".join(usage[hport])))
            if conflicts:
                port, users = conflicts[0]
                msg = self.texts["wizard_port_in_use"].format(port=port, users=users)
                QMessageBox.warning(self, self.texts["msg_error"], msg)
                return
        risks = risky_run_options(args)
        if risks:
            reply = QMessageBox.question(
                self,
                self.texts["wizard_risky_title"],
                self.texts["wizard_risky_body"].format(risks="\n".join(f"• {risk}" for risk in risks)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        try:
            if self.run_command_callback:
                result = self.run_command_callback(args, self.auto_fix_checkbox.isChecked(), self.ai_repair_checkbox.isChecked())
                if result is False:
                    return
            else:
                self.client.containers.run(image, detach=True)
        except Exception as exc:
            QMessageBox.critical(self, self.texts["msg_error"], str(exc))
            return
        done_text = self.texts["wizard_recreate_done"] if self.edit_mode else self.texts["wizard_done"]
        access_details_shown = False
        if not self.edit_mode:
            credentials = self.collect_post_install_access_details(args, selected_template)
            hints = selected_template.post_install_hints_for(self.lang) if selected_template else []
            if credentials or hints:
                access_details_shown = True
                details = [done_text, "", self.texts["wizard_credentials_intro"]]
                details.extend(f"{label}: {value}" for label, value in credentials)
                if hints:
                    details.append("")
                    details.extend(f"• {hint}" for hint in hints)
                done_text = "\n".join(details)
        QMessageBox.information(
            self,
            self.texts["wizard_credentials_title"] if access_details_shown else self.texts["msg_info"],
            done_text,
        )
        self.accept()

class SimpleImageRef:
    def __init__(self, tag: str = ""):
        self.tags = [tag] if tag else []
        self.short_id = tag or "<none>"


class WslContainerProxy:
    def __init__(self, client, attrs: Dict):
        self.client = client
        self.attrs = attrs
        self._sync_from_attrs()

    def _sync_from_attrs(self):
        config = self.attrs.get("Config", {}) or {}
        image_name = config.get("Image") or self.attrs.get("Image") or "<unknown>"
        self.name = (self.attrs.get("Name") or "").lstrip("/")
        state = self.attrs.get("State", {}) or {}
        if state.get("Paused"):
            self.status = "paused"
        elif state.get("Running"):
            self.status = "running"
        else:
            self.status = (state.get("Status") or "exited").lower()
        self.image = SimpleImageRef(image_name)

    def reload(self):
        self.attrs = self.client.inspect_container(self.name)
        self._sync_from_attrs()

    def logs(self, tail=200):
        result = self.client.run_docker(["logs", f"--tail={tail}", self.name], capture_output=True)
        return result.stdout.encode("utf-8", errors="ignore")

    def start(self):
        self.client.run_docker(["start", self.name])
        self.reload()

    def stop(self):
        self.client.run_docker(["stop", self.name])
        self.reload()

    def restart(self):
        self.client.run_docker(["restart", self.name])
        self.reload()

    def pause(self):
        self.client.run_docker(["pause", self.name])
        self.reload()

    def unpause(self):
        self.client.run_docker(["unpause", self.name])
        self.reload()

    def remove(self, force=False):
        command = ["rm"]
        if force:
            command.append("-f")
        command.append(self.name)
        self.client.run_docker(command)

    def update(self, restart_policy=None):
        if restart_policy:
            name = restart_policy.get("Name", "no")
            self.client.run_docker(["update", "--restart", name, self.name])
            self.reload()


class WslContainerCollection:
    def __init__(self, client):
        self.client = client

    def list(self, all=True):
        names_result = self.client.run_docker(["ps", "-aq"] if all else ["ps", "-q"], capture_output=True)
        names = [line.strip() for line in names_result.stdout.splitlines() if line.strip()]
        containers = []
        for identifier in names:
            try:
                inspect = self.client.inspect_container(identifier)
                containers.append(WslContainerProxy(self.client, inspect))
            except Exception:
                continue
        return containers

    def get(self, name: str):
        return WslContainerProxy(self.client, self.client.inspect_container(name))

    def run(self, image, name=None, ports=None, detach=True, command=None, **kwargs):
        args = ["run"]
        if detach:
            args.append("-d")
        if name:
            args.extend(["--name", name])
        for container_port, host_port in (ports or {}).items():
            port_value = str(container_port).split("/")[0]
            args.extend(["-p", f"{host_port}:{port_value}"])
        extra_args = kwargs.pop("extra_args", []) or []
        args.extend(extra_args)
        args.append(image)
        if command:
            args.extend(shlex.split(command))
        self.client.run_docker(args)


class WslDockerClient:
    def __init__(self, distro: str, timeout: int = DOCKER_HTTP_TIMEOUT):
        self.distro = distro
        self.timeout = timeout
        self.containers = WslContainerCollection(self)
        self.detected_cli = ""

    def _wsl_command(self, args: List[str]) -> List[str]:
        docker_args = " ".join(shlex.quote(str(arg)) for arg in args)
        return ["wsl.exe", "-d", self.distro, "sh", "-lc", f"docker {docker_args}"]

    def run_docker(self, args: List[str], capture_output: bool = False):
        docker_args = " ".join(shlex.quote(str(arg)) for arg in args)
        preferred = getattr(self, "detected_cli", "") or ""
        cli_order = []
        if preferred:
            cli_order.append(preferred)
        for name in ["docker", "balena"]:
            if name not in cli_order:
                cli_order.append(name)
        last_error = ""
        for cli_name in cli_order:
            base = f"{cli_name} {docker_args}"
            command = ["wsl.exe", "-d", self.distro, "sh", "-lc", base]
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    creationflags=CREATE_NO_WINDOW,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f"WSL command timed out after {self.timeout}s: {base}") from exc
            if result.returncode == 0:
                self.detected_cli = cli_name
                return result
            combined = (result.stderr or result.stdout or "").strip()
            last_error = combined or "Docker command failed in WSL"
            lowered = combined.lower()
            if "command not found" in lowered or "not found" in lowered or "no such file" in lowered:
                continue
            if "illegal option" in lowered or "unknown option" in lowered:
                continue
            break
        raise RuntimeError(last_error)

    def ping(self):
        self.run_docker(["version"], capture_output=True)

    def inspect_container(self, name: str) -> Dict:
        result = self.run_docker(["inspect", name], capture_output=True)
        data = json.loads(result.stdout)
        if not data:
            raise RuntimeError(f"Container not found: {name}")
        return data[0]




class SshDockerClient:
    def __init__(self, profile: RemoteProfile, timeout: int = DOCKER_HTTP_TIMEOUT):
        if paramiko is None:
            raise RuntimeError("Brakuje pakietu paramiko do polaczen SSH. Zainstaluj: pip install paramiko")
        self.profile = profile
        self.timeout = timeout
        self.containers = SshContainerCollection(self)
        self._client = None
        self.detected_cli = ""
        self.use_sudo = False

    def close(self):
        client = self._client
        self._client = None
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        auth_mode = (self.profile.ssh_auth_mode or "key").strip()
        use_key = auth_mode in {"key", "key_password"}
        use_password = auth_mode == "password"
        use_agent = auth_mode == "agent"
        key_path = (self.profile.ssh_key_path or "").strip()
        passphrase = self.profile.ssh_passphrase if auth_mode == "key_password" else ""
        kwargs = {
            "hostname": self.profile.resolved_ssh_host(),
            "username": self.profile.resolved_ssh_user(),
            "port": self.profile.resolved_ssh_port(),
            "timeout": self.timeout,
            "banner_timeout": self.timeout,
            "look_for_keys": use_key,
            "allow_agent": use_key or use_agent,
        }
        if use_agent:
            kwargs["look_for_keys"] = False
        if use_password:
            kwargs["password"] = self.profile.ssh_password
            kwargs["look_for_keys"] = False
            kwargs["allow_agent"] = False
        if use_agent:
            try:
                if not paramiko.Agent().get_keys():
                    raise RuntimeError("SSH Agent is enabled for this profile, but no keys are loaded in the agent.")
            except RuntimeError:
                raise
            except Exception as exc:
                raise RuntimeError(f"SSH Agent is not available: {exc}") from exc
        if key_path and use_key:
            key_file = Path(key_path)
            if not key_file.exists():
                raise RuntimeError(f"SSH key file not found: {key_path}")
            kwargs["key_filename"] = str(key_file)
            if passphrase:
                kwargs["password"] = passphrase
        try:
            client.connect(**kwargs)
        except paramiko.ssh_exception.PasswordRequiredException:
            raise RuntimeError("SSH key requires a passphrase. Provide it in the profile.")
        except paramiko.ssh_exception.AuthenticationException:
            if use_key:
                kwargs["disabled_algorithms"] = {"pubkeys": ["rsa-sha2-256", "rsa-sha2-512"]}
                client.connect(**kwargs)
            else:
                raise
        self._client = client
        return self._client

    def run_ssh(self, command: str) -> str:
        ssh = self._ensure_client()
        stdin, stdout, stderr = ssh.exec_command(command, timeout=self.timeout)
        out = stdout.read().decode("utf-8", errors="ignore")
        err = stderr.read().decode("utf-8", errors="ignore")
        code = stdout.channel.recv_exit_status()
        if code != 0:
            raise RuntimeError((err or out or "SSH command failed").strip())
        return out.strip()

    def dispatch_reboot(self, commands: List[str]) -> tuple[bool, bool, str]:
        last_error = ""
        for command in commands:
            dispatched = False
            try:
                ssh = self._ensure_client()
                stdin, stdout, stderr = ssh.exec_command(command, timeout=min(self.timeout, 6))
                dispatched = True
                channel = stdout.channel
                deadline = time.time() + 2.5
                while time.time() < deadline:
                    if channel.exit_status_ready():
                        code = channel.recv_exit_status()
                        if code == 0:
                            try:
                                ssh.close()
                            except Exception:
                                pass
                            self._client = None
                            return True, False, command
                        err = stderr.read().decode("utf-8", errors="ignore").strip()
                        out = stdout.read().decode("utf-8", errors="ignore").strip()
                        last_error = err or out or f"{command}: exit code {code}"
                        break
                    transport = ssh.get_transport()
                    if transport is None or not transport.is_active():
                        self._client = None
                        return True, True, command
                    time.sleep(0.1)
                else:
                    try:
                        ssh.close()
                    except Exception:
                        pass
                    self._client = None
                    return True, True, command
            except Exception as exc:
                if dispatched:
                    try:
                        if self._client is not None:
                            self._client.close()
                    except Exception:
                        pass
                    self._client = None
                    return True, True, command
                last_error = str(exc)
                self._client = None
                continue
        return False, False, last_error

    def run_docker(self, args: List[str], capture_output: bool = False):
        docker_args = " ".join(shlex.quote(str(arg)) for arg in args)
        preferred = getattr(self, "detected_cli", "") or ""
        cli_order = []
        if preferred:
            cli_order.append(preferred)
        for name in ["docker", "balena"]:
            if name not in cli_order:
                cli_order.append(name)
        last_error = ""
        fatal_error = False
        for cli_name in cli_order:
            cli_prefix = f"sudo -n {cli_name}" if self.use_sudo else cli_name
            base = f"{cli_prefix} {docker_args}"
            candidates = [base, f"sh -lc {shlex.quote(base)}", f"sh -c {shlex.quote(base)}"]
            for command in candidates:
                ssh = self._ensure_client()
                stdin, stdout, stderr = ssh.exec_command(command, timeout=self.timeout)
                out = stdout.read().decode("utf-8", errors="ignore")
                err = stderr.read().decode("utf-8", errors="ignore")
                code = stdout.channel.recv_exit_status()
                if code == 0:
                    self.detected_cli = cli_name
                    return subprocess.CompletedProcess(command, code, out, err)
                combined = (err or out or "").strip()
                last_error = combined or "Docker command failed over SSH"
                lowered = combined.lower()
                if (
                    not self.use_sudo
                    and cli_name == "docker"
                    and "permission denied" in lowered
                    and ("docker.sock" in lowered or "docker daemon" in lowered)
                ):
                    sudo_command = f"sudo -n {cli_name} {docker_args}"
                    sudo_stdin, sudo_stdout, sudo_stderr = ssh.exec_command(sudo_command, timeout=self.timeout)
                    sudo_out = sudo_stdout.read().decode("utf-8", errors="ignore")
                    sudo_err = sudo_stderr.read().decode("utf-8", errors="ignore")
                    sudo_code = sudo_stdout.channel.recv_exit_status()
                    if sudo_code == 0:
                        self.use_sudo = True
                        self.detected_cli = cli_name
                        return subprocess.CompletedProcess(sudo_command, sudo_code, sudo_out, sudo_err)
                    last_error = (sudo_err or sudo_out or combined or "Docker command failed over SSH").strip()
                    fatal_error = True
                    break
                if "command not found" in lowered or "not found" in lowered or "no such file" in lowered:
                    continue
                if "illegal option" in lowered or "unknown option" in lowered:
                    continue
                fatal_error = True
                break
            if fatal_error:
                break
        raise RuntimeError(last_error)

    def ping(self):
        self.run_docker(["version"], capture_output=True)

    def inspect_container(self, name: str) -> Dict:
        result = self.run_docker(["inspect", name], capture_output=True)
        data = json.loads(result.stdout)
        if not data:
            raise RuntimeError(f"Container not found: {name}")
        return data[0]

class SshContainerCollection:
    def __init__(self, client):
        self.client = client

    def list(self, all=True):
        names_result = self.client.run_docker(["ps", "-aq"] if all else ["ps", "-q"], capture_output=True)
        names = [line.strip() for line in names_result.stdout.splitlines() if line.strip()]
        containers = []
        for identifier in names:
            try:
                inspect = self.client.inspect_container(identifier)
                containers.append(WslContainerProxy(self.client, inspect))
            except Exception:
                continue
        return containers

    def get(self, name: str):
        return WslContainerProxy(self.client, self.client.inspect_container(name))

    def run(self, image, name=None, ports=None, detach=True, command=None, **kwargs):
        args = ["run"]
        if detach:
            args.append("-d")
        if name:
            args.extend(["--name", name])
        for container_port, host_port in (ports or {}).items():
            port_value = str(container_port).split("/")[0]
            args.extend(["-p", f"{host_port}:{port_value}"])
        extra_args = kwargs.pop("extra_args", []) or []
        args.extend(extra_args)
        args.append(image)
        if command:
            args.extend(shlex.split(command))
        self.client.run_docker(args)


class RefreshWorker(QObject):
    finished = pyqtSignal(list, str)

    def __init__(self, client: docker.DockerClient):
        super().__init__()
        self.client = client
        self.metrics_summary = {"cpu_percent": 0.0, "memory_usage": 0}
        self.host_metrics: Dict[str, object] = {}

    def collect_container_metrics(self, containers):
        metrics_by_name: Dict[str, Dict[str, object]] = {}
        if hasattr(self.client, "run_docker"):
            try:
                result = self.client.run_docker(
                    ["stats", "--no-stream", "--format", "{{json .}}"],
                    capture_output=True,
                )
                for line in str(getattr(result, "stdout", "") or "").splitlines():
                    try:
                        item = json.loads(line.strip())
                    except Exception:
                        continue
                    name = str(item.get("Name") or item.get("Container") or "").strip()
                    cpu_text = str(item.get("CPUPerc") or "0").strip().rstrip("%")
                    mem_text = str(item.get("MemUsage") or "").strip()
                    usage_text, _, limit_text = mem_text.partition("/")
                    memory_usage = parse_size_bytes(usage_text.strip())
                    memory_limit = parse_size_bytes(limit_text.strip())
                    try:
                        cpu_percent = float(cpu_text or 0)
                    except Exception:
                        cpu_percent = 0.0
                    metrics_by_name[name] = {
                        "cpu_percent": cpu_percent,
                        "memory_usage": memory_usage,
                        "memory_limit": memory_limit,
                        "memory_percent": (memory_usage / memory_limit * 100.0) if memory_limit else 0.0,
                    }
            except Exception:
                pass
        else:
            for container in containers:
                try:
                    metrics_by_name[container.name] = docker_stats_metrics(container.stats(stream=False, one_shot=True))
                except Exception:
                    metrics_by_name[container.name] = {}

        total_cpu = 0.0
        total_memory = 0
        for container in containers:
            metrics = metrics_by_name.get(getattr(container, "name", ""), {}) or {}
            setattr(container, "_dcc_metrics", metrics)
            total_cpu += float(metrics.get("cpu_percent", 0.0) or 0.0)
            total_memory += int(metrics.get("memory_usage", 0) or 0)
        self.metrics_summary = {"cpu_percent": total_cpu, "memory_usage": total_memory}

    def collect_remote_host_metrics(self):
        if not hasattr(self.client, "run_ssh"):
            return
        command = (
            "cat /proc/stat | head -n 1; "
            "sleep 0.2; "
            "cat /proc/stat | head -n 1; "
            "grep -E '^(MemTotal|MemAvailable):' /proc/meminfo"
        )
        try:
            output = self.client.run_ssh(command)
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            cpu_lines = [line for line in lines if line.startswith("cpu ")]
            memory = {}
            for line in lines:
                if ":" in line and line.split(":", 1)[0] in {"MemTotal", "MemAvailable"}:
                    key, value = line.split(":", 1)
                    amount = re.search(r"([0-9]+)", value)
                    if amount:
                        memory[key] = int(amount.group(1)) * 1024
            cpu_percent = 0.0
            if len(cpu_lines) >= 2:
                def cpu_values(line):
                    values = [int(value) for value in line.split()[1:] if value.isdigit()]
                    idle = sum(values[3:5]) if len(values) >= 5 else (values[3] if len(values) >= 4 else 0)
                    return sum(values), idle
                total1, idle1 = cpu_values(cpu_lines[0])
                total2, idle2 = cpu_values(cpu_lines[1])
                delta_total = total2 - total1
                delta_idle = idle2 - idle1
                if delta_total > 0:
                    cpu_percent = max(0.0, min(100.0, (delta_total - delta_idle) / delta_total * 100.0))
            total_mem = int(memory.get("MemTotal", 0) or 0)
            available_mem = int(memory.get("MemAvailable", 0) or 0)
            used_mem = max(0, total_mem - available_mem) if total_mem else 0
            self.host_metrics = {
                "cpu_percent": cpu_percent,
                "memory_usage": used_mem,
                "memory_total": total_mem,
                "memory_percent": (used_mem / total_mem * 100.0) if total_mem else 0.0,
            }
        except Exception:
            self.host_metrics = {}

    def run(self):
        try:
            containers = self.client.containers.list(all=True)
            self.collect_container_metrics(containers)
            self.collect_remote_host_metrics()
            self.finished.emit(containers, "")
        except Exception as exc:
            self.finished.emit([], f"{type(exc).__name__}: {exc}")


class RemoteConnectWorker(QObject):
    finished = pyqtSignal(object, str, str, str)

    def __init__(self, profile: RemoteProfile, timeout: int = 12):
        super().__init__()
        self.profile = profile
        self.timeout = max(3, int(timeout))

    def run(self):
        client = None
        try:
            if self.profile.mode == "ssh":
                client = SshDockerClient(self.profile, timeout=self.timeout)
            else:
                client = docker.DockerClient(base_url=self.profile.resolved_base_url(), timeout=self.timeout)
            client.ping()

            os_name, arch = detect_remote_system_info(client)
            self.finished.emit(client, "", os_name.strip(), arch.strip().lower())
        except Exception as exc:
            try:
                if client is not None and hasattr(client, "close"):
                    client.close()
                elif isinstance(client, SshDockerClient) and getattr(client, "_client", None) is not None:
                    client._client.close()
            except Exception:
                pass
            self.finished.emit(None, f"{type(exc).__name__}: {exc}", "", "")


class UpdateDownloadWorker(QObject):
    finished = pyqtSignal(bool, str, str)

    def __init__(self, url: str, target_path: str):
        super().__init__()
        self.url = url
        self.target_path = target_path

    def run(self):
        target = Path(self.target_path)
        part = target.with_suffix(target.suffix + ".part")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            request = Request(self.url, headers={"User-Agent": f"DCC/{APP_VERSION}"})
            with urlopen(request, timeout=60) as response, part.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
            os.replace(part, target)
            self.finished.emit(True, str(target), "")
        except Exception as exc:
            try:
                if part.exists():
                    part.unlink()
            except Exception:
                pass
            self.finished.emit(False, "", str(exc))


class CommandInfoDialog(QDialog):
    def __init__(self, title: str, intro: str, command: str, texts: Dict[str, str], parent=None, action_text: str = "", action_callback=None):
        super().__init__(parent)
        self.texts = texts
        self.action_callback = action_callback
        self.setWindowTitle(title)
        self.resize(720, 320)

        layout = QVBoxLayout(self)
        intro_label = QLabel(intro)
        intro_label.setWordWrap(True)
        layout.addWidget(intro_label)

        self.command_edit = QTextEdit()
        self.command_edit.setReadOnly(True)
        self.command_edit.setPlainText(command)
        layout.addWidget(self.command_edit)

        buttons_layout = QHBoxLayout()
        self.copy_button = QPushButton(self.texts["command_copy"])
        buttons_layout.addWidget(self.copy_button)
        if action_text:
            self.run_button = QPushButton(action_text)
            self.run_button.clicked.connect(self.run_action)
            buttons_layout.addWidget(self.run_button)
        else:
            self.run_button = None
        buttons_layout.addStretch()
        self.close_button = QPushButton(self.texts["progress_close"])
        buttons_layout.addWidget(self.close_button)
        layout.addLayout(buttons_layout)

        self.copy_button.clicked.connect(self.copy_command)
        self.close_button.clicked.connect(self.accept)

    def copy_command(self):
        QApplication.clipboard().setText(self.command_edit.toPlainText())

    def run_action(self):
        if self.action_callback is not None:
            self.action_callback()
        self.accept()
class CommandProgressWorker(QObject):
    output_received = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, runner, args: List[str], status_text: str):
        super().__init__()
        self.runner = runner
        self.args = list(args)
        self.status_text = status_text

    def run(self):
        self.output_received.emit(self.status_text)
        try:
            result = self.runner(self.args, self.output_received.emit)
            summary_parts = []
            if isinstance(result, subprocess.CompletedProcess):
                if getattr(result, "stdout", ""):
                    summary_parts.append(str(result.stdout).strip())
                if getattr(result, "stderr", ""):
                    summary_parts.append(str(result.stderr).strip())
            elif isinstance(result, str) and result.strip():
                summary_parts.append(result.strip())
            self.finished.emit(True, "\n".join(part for part in summary_parts if part))
        except Exception as exc:
            self.finished.emit(False, str(exc))


class CommandProgressDialog(QDialog):
    def __init__(self, title: str, status_text: str, runner, args: List[str], texts: Dict[str, str], parent=None):
        super().__init__(parent)
        self.texts = texts
        self.success: Optional[bool] = None
        self.started_at = time.monotonic()
        self.spinner_frames = ["◐", "◓", "◑", "◒"]
        self.spinner_index = 0
        self.setWindowTitle(title)
        self.resize(780, 460)

        layout = QVBoxLayout(self)
        status_panel = QFrame()
        status_panel.setObjectName("deploymentStatusPanel")
        status_layout = QHBoxLayout(status_panel)
        status_layout.setContentsMargins(14, 10, 14, 10)
        status_layout.setSpacing(12)
        self.status_icon = QLabel(self.spinner_frames[0])
        self.status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_icon.setFixedSize(42, 42)
        icon_font = self.status_icon.font()
        icon_font.setPointSize(22)
        icon_font.setBold(True)
        self.status_icon.setFont(icon_font)
        status_text_layout = QVBoxLayout()
        self.status_label = QLabel(status_text)
        self.status_label.setWordWrap(True)
        status_font = self.status_label.font()
        status_font.setBold(True)
        status_font.setPointSize(max(10, status_font.pointSize() + 1))
        self.status_label.setFont(status_font)
        self.elapsed_label = QLabel(self.texts["progress_elapsed"].format(seconds=0))
        status_text_layout.addWidget(self.status_label)
        status_text_layout.addWidget(self.elapsed_label)
        status_layout.addWidget(self.status_icon)
        status_layout.addLayout(status_text_layout, 1)
        layout.addWidget(status_panel)
        self.status_panel = status_panel
        self._apply_status_visual("working")

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log_edit.setCenterOnScroll(False)
        layout.addWidget(self.log_edit)

        buttons = QHBoxLayout()
        self.copy_log_button = QPushButton(self.texts["progress_copy_log"])
        self.copy_log_button.clicked.connect(self.copy_log)
        buttons.addWidget(self.copy_log_button)
        buttons.addStretch()
        self.close_button = QPushButton(self.texts["progress_close"])
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self.thread = QThread(self)
        self.worker = CommandProgressWorker(runner, args, status_text)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.output_received.connect(self.append_output)
        self.worker.finished.connect(self.on_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.activity_timer = QTimer(self)
        self.activity_timer.setInterval(180)
        self.activity_timer.timeout.connect(self.advance_activity)
        self.activity_timer.start()
        self.thread.start()

    def _apply_status_visual(self, state: str):
        if state == "success":
            self.status_icon.setText("✓")
            self.status_icon.setStyleSheet("color: #58d68d;")
            self.status_label.setStyleSheet("color: #58d68d;")
            self.status_panel.setStyleSheet("QFrame#deploymentStatusPanel { border: 1px solid rgba(88, 214, 141, 120); border-radius: 8px; }")
        elif state == "failed":
            self.status_icon.setText("✕")
            self.status_icon.setStyleSheet("color: #ff6b6b;")
            self.status_label.setStyleSheet("color: #ff6b6b;")
            self.status_panel.setStyleSheet("QFrame#deploymentStatusPanel { border: 1px solid rgba(255, 107, 107, 140); border-radius: 8px; }")
        else:
            self.status_icon.setStyleSheet("color: #67d9ff;")
            self.status_label.setStyleSheet("color: #67d9ff;")
            self.status_panel.setStyleSheet("QFrame#deploymentStatusPanel { border: 1px solid rgba(103, 217, 255, 100); border-radius: 8px; }")

    def advance_activity(self):
        if self.success is not None:
            return
        self.spinner_index = (self.spinner_index + 1) % len(self.spinner_frames)
        self.status_icon.setText(self.spinner_frames[self.spinner_index])
        seconds = max(0, int(time.monotonic() - self.started_at))
        self.elapsed_label.setText(self.texts["progress_elapsed"].format(seconds=seconds))

    def copy_log(self):
        QApplication.clipboard().setText(self.log_edit.toPlainText())
        self.copy_log_button.setToolTip(self.texts["progress_log_copied"])

    def append_output(self, text: str):
        if not text:
            return
        vbar = self.log_edit.verticalScrollBar()
        hbar = self.log_edit.horizontalScrollBar()
        previous_v = vbar.value()
        previous_h = hbar.value()
        was_at_bottom = previous_v >= max(0, vbar.maximum() - 4)
        self.log_edit.appendPlainText(text.rstrip())

        def restore_scroll():
            if was_at_bottom:
                vbar.setValue(vbar.maximum())
            else:
                vbar.setValue(min(previous_v, vbar.maximum()))
            hbar.setValue(min(previous_h, hbar.maximum()))

        QTimer.singleShot(0, restore_scroll)
        QTimer.singleShot(25, restore_scroll)

    def on_finished(self, success: bool, summary: str):
        if summary:
            self.append_output(summary)
        self.success = bool(success)
        self.activity_timer.stop()
        seconds = max(0, int(time.monotonic() - self.started_at))
        self.elapsed_label.setText(self.texts["progress_elapsed"].format(seconds=seconds))
        self.status_label.setText(self.texts["progress_status_done"] if success else self.texts["progress_status_failed"])
        self._apply_status_visual("success" if success else "failed")
        self.close_button.setText(("✓ " if success else "✕ ") + self.texts["progress_close"])
        self.close_button.setEnabled(True)
        self.close_button.setDefault(True)
class ProfileManagerDialog(QDialog):
    def __init__(self, profiles: List[RemoteProfile], texts: Dict[str, str], parent=None):
        super().__init__(parent)
        self.texts = texts
        self.profiles = [RemoteProfile(**asdict(profile)) for profile in profiles]
        self.setWindowTitle(self.texts["profile_dialog_title"])
        self.resize(900, 560)
        layout = QHBoxLayout(self)

        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self.load_selected_profile)
        layout.addWidget(self.list_widget, 1)

        right = QVBoxLayout()
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(self.texts["profile_mode_ssh"], "ssh")
        self.mode_combo.addItem(self.texts["profile_mode_tunnel"], "tunnel")
        self.ssh_target_edit = QLineEdit()
        self.ssh_port_spin = QSpinBox()
        self.ssh_port_spin.setRange(1, 65535)
        self.ssh_port_spin.setValue(22)
        self.auth_mode_combo = QComboBox()
        self.auth_mode_combo.addItem(self.texts["profile_auth_key"], "key")
        self.auth_mode_combo.addItem(self.texts["profile_auth_both"], "key_password")
        self.auth_mode_combo.addItem(self.texts["profile_auth_agent"], "agent")
        self.auth_mode_combo.addItem(self.texts["profile_auth_password"], "password")
        self.key_path_edit = QLineEdit()
        self.key_browse_btn = QPushButton(self.texts["profile_key_browse"])
        key_row = QHBoxLayout()
        key_row.addWidget(self.key_path_edit, 1)
        key_row.addWidget(self.key_browse_btn)
        self.key_path_status = QLabel("")
        self.key_path_status.setWordWrap(True)
        self.passphrase_edit = QLineEdit()
        self.passphrase_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.base_url_edit = QLineEdit()
        self.tunnel_command_edit = QTextEdit()
        self.wait_spin = QSpinBox()
        self.wait_spin.setRange(0, 60)

        form.addRow(self.texts["profile_name"], self.name_edit)
        form.addRow(self.texts["profile_mode"], self.mode_combo)
        form.addRow(self.texts["profile_ssh_target"], self.ssh_target_edit)
        form.addRow(self.texts["profile_ssh_port"], self.ssh_port_spin)
        form.addRow(self.texts["profile_auth_mode"], self.auth_mode_combo)
        form.addRow(self.texts["profile_key_path"], key_row)
        form.addRow("", self.key_path_status)
        form.addRow(self.texts["profile_passphrase"], self.passphrase_edit)
        form.addRow(self.texts["profile_password"], self.password_edit)
        form.addRow(self.texts["profile_base_url"], self.base_url_edit)
        form.addRow(self.texts["profile_tunnel_command"], self.tunnel_command_edit)
        form.addRow(self.texts["profile_wait"], self.wait_spin)
        right.addLayout(form)

        self.passphrase_note = QLabel(self.texts["profile_passphrase_note"])
        self.password_note = QLabel(self.texts["profile_password_note"])
        self.passphrase_note.setWordWrap(True)
        self.password_note.setWordWrap(True)
        right.addWidget(self.passphrase_note)
        right.addWidget(self.password_note)

        actions = QHBoxLayout()
        self.btn_add = QPushButton(self.texts["profile_add"])
        self.btn_copy = QPushButton(self.texts["profile_copy"])
        self.btn_save = QPushButton(self.texts["profile_save"])
        self.btn_delete = QPushButton(self.texts["profile_delete"])
        self.btn_tutorial = QPushButton(self.texts["profile_tutorial"])
        self.btn_import = QPushButton(self.texts["menu_profiles_import"])
        self.btn_export = QPushButton(self.texts["menu_profiles_export"])
        actions.addWidget(self.btn_add)
        actions.addWidget(self.btn_copy)
        actions.addWidget(self.btn_save)
        actions.addWidget(self.btn_delete)
        actions.addWidget(self.btn_tutorial)
        right.addLayout(actions)

        transfer_actions = QHBoxLayout()
        transfer_actions.addWidget(self.btn_import)
        transfer_actions.addWidget(self.btn_export)
        transfer_actions.addStretch()
        right.addLayout(transfer_actions)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        right.addWidget(buttons)
        layout.addLayout(right, 2)

        self.btn_add.clicked.connect(self.add_profile)
        self.btn_copy.clicked.connect(self.copy_current_profile)
        self.btn_save.clicked.connect(self.save_current_profile)
        self.btn_delete.clicked.connect(self.delete_current_profile)
        self.btn_tutorial.clicked.connect(self.show_tutorial)
        self.btn_import.clicked.connect(self.import_profiles)
        self.btn_export.clicked.connect(self.export_profiles)
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        self.auth_mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        self.key_browse_btn.clicked.connect(self.choose_key_path)
        self.key_path_edit.textChanged.connect(self.update_key_path_status)
        self.refresh_list()
        if self.profiles:
            self.list_widget.setCurrentRow(0)

    def refresh_list(self):
        self.list_widget.clear()
        for profile in self.profiles:
            self.list_widget.addItem(QListWidgetItem(profile.name))

    def current_mode(self) -> str:
        return self.mode_combo.currentData() or "ssh"

    def current_auth_mode(self) -> str:
        return self.auth_mode_combo.currentData() or "key"

    def choose_key_path(self):
        current = self.key_path_edit.text().strip()
        start_dir = Path.home() / ".ssh"
        if current:
            try:
                current_path = Path(current).expanduser()
                start_dir = current_path.parent if current_path.parent.exists() else start_dir
            except Exception:
                pass
        if not start_dir.exists():
            start_dir = Path.home()
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.texts["profile_key_path"],
            str(start_dir),
            "SSH Keys (id_* *.pem *.key *.ppk);;All files (*.*)",
        )
        if path:
            self.key_path_edit.setText(path)

    def update_key_path_status(self):
        key_mode = self.current_auth_mode() in {"key", "key_password"}
        path = self.key_path_edit.text().strip()
        available = False
        if key_mode and path:
            try:
                available = Path(path).expanduser().is_file()
            except Exception:
                available = False
        if not key_mode:
            self.key_path_status.clear()
            self.key_path_status.setVisible(False)
            return
        self.key_path_status.setVisible(True)
        if available:
            self.key_path_status.setText("✓ " + self.texts["profile_key_path_ok"])
            self.key_path_status.setStyleSheet("color: #58d68d;")
        else:
            self.key_path_status.setText("⚠ " + self.texts["profile_key_path_missing"])
            self.key_path_status.setStyleSheet("color: #ffcc66;")


    def on_mode_changed(self):
        tunnel_mode = self.current_mode() == "tunnel"
        ssh_mode = self.current_mode() == "ssh"
        password_mode = self.current_auth_mode() == "password"
        passphrase_mode = self.current_auth_mode() == "key_password"
        key_mode = self.current_auth_mode() in {"key", "key_password"}
        self.auth_mode_combo.setEnabled(ssh_mode)
        self.ssh_port_spin.setEnabled(ssh_mode or tunnel_mode)
        self.key_path_edit.setEnabled(ssh_mode and key_mode)
        self.key_browse_btn.setEnabled(ssh_mode and key_mode)
        self.passphrase_edit.setEnabled(ssh_mode and passphrase_mode)
        self.passphrase_note.setVisible(ssh_mode and passphrase_mode)
        self.password_edit.setEnabled(ssh_mode and password_mode)
        self.password_note.setVisible(ssh_mode and password_mode)
        self.tunnel_command_edit.setEnabled(tunnel_mode)
        self.wait_spin.setEnabled(tunnel_mode)
        self.base_url_edit.setEnabled(not ssh_mode or tunnel_mode)
        self.update_key_path_status()

    def load_selected_profile(self, row: int):
        if row < 0 or row >= len(self.profiles):
            return
        profile = self.profiles[row]
        self.name_edit.setText(profile.name)
        self.mode_combo.setCurrentIndex(0 if profile.mode == "ssh" else 1)
        self.ssh_target_edit.setText(profile.ssh_target)
        self.ssh_port_spin.setValue(int(profile.ssh_port or 22))
        auth_index = self.auth_mode_combo.findData(profile.ssh_auth_mode)
        self.auth_mode_combo.setCurrentIndex(auth_index if auth_index >= 0 else 0)
        self.key_path_edit.setText(profile.ssh_key_path)
        self.passphrase_edit.setText(profile.ssh_passphrase)
        self.password_edit.setText(profile.ssh_password)
        self.base_url_edit.setText(profile.base_url)
        self.tunnel_command_edit.setPlainText(profile.tunnel_command)
        self.wait_spin.setValue(profile.wait_seconds)
        self.on_mode_changed()
        self.update_key_path_status()

    def build_profile_from_inputs(self) -> Optional[RemoteProfile]:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, self.texts["msg_error"], self.texts["profile_missing_name"])
            return None
        mode = self.current_mode()
        ssh_target = self.ssh_target_edit.text().strip()
        base_url = self.base_url_edit.text().strip()
        auth_mode = self.current_auth_mode()
        ssh_password = self.password_edit.text()
        ssh_passphrase = self.passphrase_edit.text()
        ssh_port = int(self.ssh_port_spin.value())
        ssh_key_path = self.key_path_edit.text().strip()
        if auth_mode == "key_password" and not ssh_key_path:
            QMessageBox.warning(self, self.texts["msg_error"], self.texts["profile_key_path_required_passphrase"])
            return None
        if mode == "ssh" and not ssh_target and not base_url:
            QMessageBox.warning(self, self.texts["msg_error"], self.texts["profile_missing_target"])
            return None
        tunnel_command = self.tunnel_command_edit.toPlainText().strip()
        if mode == "tunnel" and not tunnel_command and ssh_target:
            port_flag = f" -p {ssh_port}" if ssh_port and ssh_port != 22 else ""
            tunnel_command = f"ssh -N{port_flag} -L 23750:127.0.0.1:2375 {ssh_target}"
        return RemoteProfile(
            name=name,
            mode=mode,
            ssh_target=ssh_target,
            ssh_port=ssh_port,
            ssh_auth_mode=auth_mode,
            ssh_password=ssh_password,
            ssh_passphrase=ssh_passphrase,
            ssh_key_path=ssh_key_path,
            base_url=base_url,
            tunnel_command=tunnel_command,
            wait_seconds=self.wait_spin.value(),
        )

    def add_profile(self):
        self.profiles.append(RemoteProfile(name="Nowy profil"))
        self.refresh_list()
        self.list_widget.setCurrentRow(len(self.profiles) - 1)

    def copy_current_profile(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.profiles):
            return
        source = self.profiles[row]
        copy_profile = RemoteProfile(**asdict(source))
        copy_profile.secret_id = uuid.uuid4().hex
        suffix = self.texts["profile_copy_suffix"]
        base_name = source.name.strip() or "Profile"
        candidate = f"{base_name} ({suffix})"
        existing = {profile.name for profile in self.profiles}
        index = 2
        while candidate in existing:
            candidate = f"{base_name} ({suffix} {index})"
            index += 1
        copy_profile.name = candidate
        self.profiles.append(copy_profile)
        self.refresh_list()
        self.list_widget.setCurrentRow(len(self.profiles) - 1)

    def import_profiles(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.texts["profiles_import_title"],
            "",
            self.texts["profiles_portable_filter"],
        )
        if not path:
            return
        try:
            imported = import_connection_profiles(Path(path))
            self.profiles = merge_imported_profiles(self.profiles, imported)
            self.refresh_list()
            self.list_widget.setCurrentRow(max(0, len(self.profiles) - len(imported)))
            missing_keys = sum(1 for profile in imported if profile_needs_ssh_key_path(profile))
            message = self.texts["profiles_import_done"].format(count=len(imported))
            if missing_keys:
                message += "\n\n" + self.texts["profiles_import_key_paths"].format(count=missing_keys)
            QMessageBox.information(
                self,
                self.texts["msg_info"],
                message,
            )
        except Exception:
            QMessageBox.warning(self, self.texts["msg_error"], self.texts["profiles_import_invalid"])

    def export_profiles(self):
        default_name = "DockerControlCenter-profiles.json"
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.texts["profiles_export_title"],
            default_name,
            self.texts["profiles_portable_filter"],
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            count = export_connection_profiles(Path(path), self.profiles)
            QMessageBox.information(
                self,
                self.texts["msg_info"],
                self.texts["profiles_export_done"].format(count=count),
            )
        except Exception as exc:
            QMessageBox.warning(self, self.texts["msg_error"], str(exc))

    def save_current_profile(self):
        row = self.list_widget.currentRow()
        if row < 0:
            self.add_profile()
            row = self.list_widget.currentRow()
        profile = self.build_profile_from_inputs()
        if not profile:
            return
        if 0 <= row < len(self.profiles):
            profile.secret_id = self.profiles[row].secret_id
        self.profiles[row] = profile
        self.refresh_list()
        self.list_widget.setCurrentRow(row)
        QMessageBox.information(self, self.texts["msg_info"], self.texts["profile_saved"])

    def delete_current_profile(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        self.profiles.pop(row)
        if not self.profiles:
            self.add_profile()
        self.refresh_list()
        self.list_widget.setCurrentRow(min(row, len(self.profiles) - 1))
        QMessageBox.information(self, self.texts["msg_info"], self.texts["profile_deleted"])

    def show_tutorial(self):
        profile = self.build_profile_from_inputs() or RemoteProfile.default()
        TutorialDialog(profile, self.texts, self).exec()


class FirstRunWizardDialog(QDialog):
    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window)
        self.main_window = main_window
        self.texts = main_window.texts
        self.setWindowTitle(self.texts["first_run_title"])
        self.resize(760, 520)

        layout = QVBoxLayout(self)
        intro = QLabel(self.texts["first_run_intro"])
        intro.setWordWrap(True)
        intro_font = intro.font()
        intro_font.setPointSize(max(11, intro_font.pointSize() + 1))
        intro_font.setBold(True)
        intro.setFont(intro_font)
        layout.addWidget(intro)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        system_tab = QWidget()
        system_layout = QVBoxLayout(system_tab)
        self.system_label = QLabel()
        self.system_label.setWordWrap(True)
        system_layout.addWidget(self.system_label)
        system_layout.addStretch()
        self.tabs.addTab(system_tab, self.texts["first_run_system_tab"])

        docker_tab = QWidget()
        docker_layout = QVBoxLayout(docker_tab)
        self.docker_status = QLabel()
        self.docker_status.setWordWrap(True)
        docker_layout.addWidget(self.docker_status)
        docker_actions = QHBoxLayout()
        self.docker_desktop_button = QPushButton()
        self.install_docker_button = QPushButton(self.texts["first_run_install_docker"])
        self.add_docker_group_button = QPushButton(self.texts["first_run_add_docker_group"])
        self.recheck_docker_button = QPushButton(self.texts["first_run_recheck_docker"])
        docker_actions.addWidget(self.docker_desktop_button)
        docker_actions.addWidget(self.install_docker_button)
        docker_actions.addWidget(self.add_docker_group_button)
        docker_actions.addWidget(self.recheck_docker_button)
        docker_actions.addStretch()
        docker_layout.addLayout(docker_actions)
        docker_layout.addStretch()
        self.tabs.addTab(docker_tab, self.texts["first_run_docker_tab"])

        profiles_tab = QWidget()
        profiles_layout = QVBoxLayout(profiles_tab)
        profiles_intro = QLabel(self.texts["first_run_profiles_intro"])
        profiles_intro.setWordWrap(True)
        profiles_layout.addWidget(profiles_intro)
        self.profiles_count_label = QLabel()
        self.key_paths_label = QLabel()
        self.key_paths_label.setWordWrap(True)
        profiles_layout.addWidget(self.profiles_count_label)
        profiles_layout.addWidget(self.key_paths_label)
        profile_actions = QHBoxLayout()
        self.import_profiles_button = QPushButton(self.texts["first_run_import_profiles"])
        self.edit_profiles_button = QPushButton(self.texts["first_run_edit_profiles"])
        profile_actions.addWidget(self.import_profiles_button)
        profile_actions.addWidget(self.edit_profiles_button)
        profile_actions.addStretch()
        profiles_layout.addLayout(profile_actions)
        profiles_layout.addStretch()
        self.tabs.addTab(profiles_tab, self.texts["first_run_profiles_tab"])

        footer = QHBoxLayout()
        self.later_button = QPushButton(self.texts["first_run_later"])
        self.finish_button = QPushButton(self.texts["first_run_finish"])
        footer.addWidget(self.later_button)
        footer.addStretch()
        footer.addWidget(self.finish_button)
        layout.addLayout(footer)

        self.docker_desktop_button.clicked.connect(self.handle_docker_desktop)
        self.install_docker_button.clicked.connect(self.install_docker)
        self.add_docker_group_button.clicked.connect(self.add_to_docker_group)
        self.recheck_docker_button.clicked.connect(self.refresh_state)
        self.import_profiles_button.clicked.connect(self.import_profiles)
        self.edit_profiles_button.clicked.connect(self.edit_profiles)
        self.later_button.clicked.connect(self.reject)
        self.finish_button.clicked.connect(self.accept)
        self.refresh_state()

    def refresh_state(self):
        self.system_label.setText(
            self.texts["first_run_system_detected"].format(system=detect_local_os_name())
        )
        docker_ready = self.main_window.is_local_docker_available()
        docker_binary = bool(shutil.which("docker"))
        supported = self.main_window.linux_docker_auto_install_supported()
        desktop_installed = self.main_window.linux_docker_desktop_installed()
        desktop_selected = self.main_window.linux_docker_desktop_selected()
        group_configured = self.main_window.linux_docker_group_configured()
        group_active = self.main_window.linux_docker_group_active()
        group_supported = self.main_window.linux_docker_group_setup_supported()
        system_socket = self.main_window.linux_docker_uses_system_socket() if docker_binary else False
        self.add_docker_group_button.setText(
            self.texts["first_run_docker_group_added"]
            if group_configured
            else self.texts["first_run_add_docker_group"]
        )
        if docker_ready:
            self.docker_status.setText(self.texts["first_run_docker_ready"])
            self.docker_status.setStyleSheet("color: #58d68d;")
        elif desktop_installed and desktop_selected:
            self.docker_status.setText(self.texts["docker_desktop_linux_stopped"])
            self.docker_status.setStyleSheet("color: #ffcc66;")
        elif docker_binary:
            if not system_socket:
                self.docker_status.setText(self.texts["dependencies_installed_not_running"])
                self.docker_status.setStyleSheet("color: #ffcc66;")
            elif group_configured:
                if group_active:
                    self.docker_status.setText(self.texts["dependencies_docker_group_active_no_daemon"])
                    self.docker_status.setStyleSheet("color: #ffcc66;")
                else:
                    self.docker_status.setText(self.texts["dependencies_docker_group_session"])
                    self.docker_status.setStyleSheet("color: #58d68d;")
            else:
                self.docker_status.setText(self.texts["dependencies_docker_group_missing"])
                self.docker_status.setStyleSheet("color: #ffcc66;")
        elif supported:
            self.docker_status.setText(self.texts["first_run_docker_missing"])
            self.docker_status.setStyleSheet("color: #ffcc66;")
        else:
            self.docker_status.setText(self.texts["first_run_docker_unsupported"])
            self.docker_status.setStyleSheet("color: #ff8c8c;")
        desktop_running = self.main_window.linux_docker_desktop_running() if desktop_installed else False
        self.docker_desktop_button.setText(
            self.texts["docker_local_open_desktop"]
            if desktop_installed
            else self.texts["dependencies_install_docker_desktop"]
        )
        self.docker_desktop_button.setEnabled((not desktop_running) if desktop_installed else True)
        self.install_docker_button.setText(self.texts["first_run_install_docker"])
        self.install_docker_button.setEnabled((not docker_binary) and supported)
        self.add_docker_group_button.setEnabled(
            docker_binary and (not group_configured) and group_supported
        )

        profiles = self.main_window.remote_profiles
        missing = sum(1 for profile in profiles if profile_needs_ssh_key_path(profile))
        self.profiles_count_label.setText(self.texts["first_run_profiles_count"].format(count=len(profiles)))
        self.key_paths_label.setText(self.texts["first_run_key_paths_missing"].format(count=missing))
        self.key_paths_label.setStyleSheet("color: #ffcc66;" if missing else "color: #58d68d;")

    def handle_docker_desktop(self):
        if self.main_window.linux_docker_desktop_installed():
            if self.main_window.try_start_docker_desktop():
                self.main_window.statusBar().showMessage(self.texts["docker_desktop_starting"])
                QTimer.singleShot(1800, self.main_window.reconnect_local_docker_after_desktop_start)
            else:
                QMessageBox.warning(self, self.texts["msg_error"], self.texts["docker_local_open_failed"])
        elif self.main_window.linux_docker_desktop_selected():
            opened = self.main_window.open_linux_docker_desktop_install_page()
            QMessageBox.information(
                self,
                self.texts["msg_info"],
                self.texts["docker_desktop_linux_install_opened"]
                if opened
                else self.texts["docker_desktop_linux_install_failed"],
            )
        self.refresh_state()

    def install_docker(self):
        if self.main_window.install_linux_docker_with_progress():
            QMessageBox.information(self, self.texts["msg_info"], self.texts["first_run_install_success"])
        self.refresh_state()

    def add_to_docker_group(self):
        if self.main_window.add_current_user_to_docker_group_with_progress():
            QMessageBox.information(self, self.texts["msg_info"], self.texts["docker_group_install_success"])
        self.refresh_state()

    def import_profiles(self):
        self.main_window.import_profiles_from_file()
        self.refresh_state()

    def edit_profiles(self):
        self.main_window.manage_profiles()
        self.refresh_state()


class DependencyManagerDialog(QDialog):
    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window)
        self.main_window = main_window
        self.texts = main_window.texts
        self.setWindowTitle(self.texts["dependencies_title"])
        self.resize(760, 420)

        layout = QVBoxLayout(self)
        intro = QLabel(self.texts["dependencies_intro"])
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.docker_frame = QFrame()
        self.docker_frame.setObjectName("dependencyCard")
        docker_layout = QVBoxLayout(self.docker_frame)
        self.docker_title = QLabel()
        docker_font = self.docker_title.font()
        docker_font.setBold(True)
        docker_font.setPointSize(max(10, docker_font.pointSize() + 1))
        self.docker_title.setFont(docker_font)
        self.docker_status = QLabel()
        self.docker_status.setWordWrap(True)
        docker_actions = QHBoxLayout()
        self.docker_action = QPushButton()
        self.docker_engine_action = QPushButton(self.texts["dependencies_install_docker_engine"])
        self.docker_group_action = QPushButton(self.texts["dependencies_add_docker_group"])
        self.docker_action.clicked.connect(self.handle_docker_action)
        self.docker_engine_action.clicked.connect(self.handle_docker_engine_action)
        self.docker_group_action.clicked.connect(self.handle_docker_group_action)
        docker_actions.addWidget(self.docker_action)
        docker_actions.addWidget(self.docker_engine_action)
        docker_actions.addWidget(self.docker_group_action)
        docker_actions.addStretch()
        docker_layout.addWidget(self.docker_title)
        docker_layout.addWidget(self.docker_status)
        docker_layout.addLayout(docker_actions)
        layout.addWidget(self.docker_frame)

        self.ssh_frame = QFrame()
        self.ssh_frame.setObjectName("dependencyCard")
        ssh_layout = QVBoxLayout(self.ssh_frame)
        ssh_title = QLabel(self.texts["dependencies_ssh"])
        ssh_title.setFont(docker_font)
        self.ssh_status = QLabel()
        self.ssh_status.setWordWrap(True)
        ssh_actions = QHBoxLayout()
        self.ssh_action = QPushButton(self.texts["dependencies_install_ssh"])
        self.ssh_action.clicked.connect(self.install_ssh_tools)
        ssh_actions.addWidget(self.ssh_action)
        ssh_actions.addStretch()
        ssh_layout.addWidget(ssh_title)
        ssh_layout.addWidget(self.ssh_status)
        ssh_layout.addLayout(ssh_actions)
        layout.addWidget(self.ssh_frame)

        layout.addStretch()
        footer = QHBoxLayout()
        self.recheck_button = QPushButton(self.texts["dependencies_recheck"])
        self.close_button = QPushButton(self.texts["dependencies_close"])
        self.recheck_button.clicked.connect(self.refresh_state)
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.recheck_button)
        footer.addStretch()
        footer.addWidget(self.close_button)
        layout.addLayout(footer)

        self.setStyleSheet(
            "QFrame#dependencyCard { border: 1px solid rgba(120, 180, 220, 70); border-radius: 8px; }"
        )
        self.refresh_state()

    def refresh_state(self):
        docker_ready = self.main_window.is_local_docker_available()
        if os.name == "nt":
            self.docker_group_action.setVisible(False)
            self.docker_engine_action.setVisible(False)
            self.docker_title.setText(self.texts["dependencies_docker_windows"])
            installed = self.main_window.windows_docker_desktop_installed()
            if docker_ready:
                self.docker_status.setText(self.texts["dependencies_ready"])
                self.docker_status.setStyleSheet("color: #58d68d;")
                self.docker_action.setText(self.texts["dependencies_start"])
                self.docker_action.setEnabled(False)
            elif installed:
                self.docker_status.setText(self.texts["dependencies_installed_not_running"])
                self.docker_status.setStyleSheet("color: #ffcc66;")
                self.docker_action.setText(self.texts["docker_local_open_desktop"])
                self.docker_action.setEnabled(True)
            else:
                self.docker_status.setText(self.texts["dependencies_missing"])
                self.docker_status.setStyleSheet("color: #ffcc66;")
                self.docker_action.setText(self.texts["dependencies_install_docker_desktop"])
                self.docker_action.setEnabled(True)
        else:
            self.docker_group_action.setVisible(True)
            self.docker_engine_action.setVisible(True)
            docker_binary = bool(shutil.which("docker"))
            supported = self.main_window.linux_docker_auto_install_supported()
            desktop_installed = self.main_window.linux_docker_desktop_installed()
            desktop_selected = self.main_window.linux_docker_desktop_selected()
            desktop_running = self.main_window.linux_docker_desktop_running() if desktop_installed else False
            group_configured = self.main_window.linux_docker_group_configured()
            group_active = self.main_window.linux_docker_group_active()
            group_supported = self.main_window.linux_docker_group_setup_supported()
            system_socket = self.main_window.linux_docker_uses_system_socket() if docker_binary else False
            self.docker_title.setText(
                self.texts["dependencies_docker_linux_desktop"]
                if desktop_installed or desktop_selected
                else self.texts["dependencies_docker_linux"]
            )
            if docker_ready:
                self.docker_status.setText(self.texts["dependencies_ready"])
                self.docker_status.setStyleSheet("color: #58d68d;")
            elif desktop_installed and (desktop_selected or not system_socket):
                self.docker_status.setText(self.texts["docker_desktop_linux_stopped"])
                self.docker_status.setStyleSheet("color: #ffcc66;")
            elif docker_binary:
                if not system_socket:
                    self.docker_status.setText(self.texts["dependencies_installed_not_running"])
                    self.docker_status.setStyleSheet("color: #ffcc66;")
                elif group_configured:
                    if group_active:
                        self.docker_status.setText(self.texts["dependencies_docker_group_active_no_daemon"])
                        self.docker_status.setStyleSheet("color: #ffcc66;")
                    else:
                        self.docker_status.setText(self.texts["dependencies_docker_group_session"])
                        self.docker_status.setStyleSheet("color: #58d68d;")
                else:
                    self.docker_status.setText(self.texts["dependencies_docker_group_missing"])
                    self.docker_status.setStyleSheet("color: #ffcc66;")
                self.docker_action.setText(self.texts["dependencies_install_docker"])
                self.docker_action.setEnabled(False)
            else:
                self.docker_status.setText(self.texts["docker_desktop_linux_missing"])
                self.docker_status.setStyleSheet("color: #ffcc66;")

            self.docker_action.setText(
                self.texts["docker_local_open_desktop"]
                if desktop_installed
                else self.texts["dependencies_install_docker_desktop"]
            )
            self.docker_action.setEnabled((not desktop_running) if desktop_installed else True)
            self.docker_engine_action.setEnabled((not docker_binary) and supported)
            self.docker_group_action.setText(
                self.texts["dependencies_docker_group_added"]
                if group_configured
                else self.texts["dependencies_add_docker_group"]
            )
            self.docker_group_action.setEnabled(
                docker_binary and (not group_configured) and group_supported
            )
            if group_configured:
                self.docker_group_action.setToolTip(self.texts["dependencies_docker_group_member"])
            else:
                self.docker_group_action.setToolTip(self.texts["docker_group_auth_info"])

        ssh_ready = self.main_window.is_ssh_client_available() and self.main_window.is_ssh_agent_available()
        if ssh_ready:
            self.ssh_status.setText(self.texts["dependencies_ready"])
            self.ssh_status.setStyleSheet("color: #58d68d;")
            self.ssh_action.setEnabled(False)
        else:
            supported = self.main_window.ssh_tools_auto_install_supported()
            self.ssh_status.setText(
                self.texts["dependencies_missing"] if supported else self.texts["dependencies_auto_unavailable"]
            )
            self.ssh_status.setStyleSheet("color: #ffcc66;")
            self.ssh_action.setEnabled(supported)

    def handle_docker_action(self):
        success = False
        if os.name == "nt":
            if self.main_window.windows_docker_desktop_installed():
                success = self.main_window.try_start_docker_desktop()
                if not success:
                    QMessageBox.warning(self, self.texts["msg_error"], self.texts["docker_local_open_failed"])
            else:
                success = self.main_window.install_windows_docker_desktop_with_progress()
                if success:
                    self.main_window.try_start_docker_desktop()
        else:
            if self.main_window.linux_docker_desktop_installed():
                success = self.main_window.try_start_docker_desktop()
                if not success:
                    QMessageBox.warning(self, self.texts["msg_error"], self.texts["docker_local_open_failed"])
                else:
                    self.main_window.statusBar().showMessage(self.texts["docker_desktop_starting"])
                    QTimer.singleShot(1800, self.main_window.reconnect_local_docker_after_desktop_start)
            else:
                success = self.main_window.open_linux_docker_desktop_install_page()
                QMessageBox.information(
                    self,
                    self.texts["msg_info"],
                    self.texts["docker_desktop_linux_install_opened"]
                    if success
                    else self.texts["docker_desktop_linux_install_failed"],
                )
        if success:
            if os.name == "nt":
                QMessageBox.information(self, self.texts["msg_info"], self.texts["dependencies_install_success"])
        self.refresh_state()

    def handle_docker_engine_action(self):
        if os.name == "nt":
            return
        if self.main_window.install_linux_docker_with_progress():
            QMessageBox.information(self, self.texts["msg_info"], self.texts["dependencies_install_success"])
        self.refresh_state()

    def handle_docker_group_action(self):
        if self.main_window.add_current_user_to_docker_group_with_progress():
            QMessageBox.information(self, self.texts["msg_info"], self.texts["docker_group_install_success"])
        self.refresh_state()

    def install_ssh_tools(self):
        if self.main_window.install_ssh_tools_with_progress():
            QMessageBox.information(self, self.texts["msg_info"], self.texts["dependencies_install_success"])
        self.refresh_state()


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        self._skip_persist_window_state = False
        self._last_normal_geometry = None
        self.lang = str(self.settings.value("language", "EN")).upper()
        if self.lang not in TEXTS:
            self.lang = "EN"
        self.texts = TEXTS[self.lang]
        self.secret_store = SecretStore(SECRET_FILE)
        self.profile_store = ProfileStore(PROFILE_FILE, self.secret_store)
        self.migrate_legacy_secret_settings()
        self.remote_profiles = self.profile_store.load()
        self.current_theme = self.settings.value("theme", "black")
        if self.current_theme not in {"light", "day", "dark", "black", "night"}:
            self.current_theme = "black"
        self.transparent_mode = str(self.settings.value("transparent_mode", "false")).lower() in {"1", "true", "yes"}
        self.transparency_level = int(self.settings.value("transparency_level", 72))
        try:
            self.container_table_zoom = int(self.settings.value("container_table_zoom", 100))
        except Exception:
            self.container_table_zoom = 100
        self.container_table_zoom = max(70, min(160, self.container_table_zoom))
        self.container_column_magnet = str(
            self.settings.value("containers/column_magnet", "true")
        ).lower() in {"1", "true", "yes"}
        self._container_column_base_widths: Optional[List[float]] = None
        self._restoring_container_column_widths = False
        self._applying_column_magnet = False
        self.music_enabled = str(self.settings.value("music_enabled", "true")).lower() in {"1", "true", "yes"}
        self.neon_animate = str(self.settings.value("neon_animate", "true")).lower() in {"1", "true", "yes"}
        self.accent_color = normalize_accent_color(str(self.settings.value("accent_color", "#33f0ff")))
        self.auto_start_docker_desktop = str(self.settings.value("auto_start_docker_desktop", "false")).lower() in {"1", "true", "yes"}
        self.auto_check_updates = str(self.settings.value("updates/auto_check", "true")).lower() in {"1", "true", "yes"}
        self.update_notifications = str(self.settings.value("updates/notifications", "true")).lower() in {"1", "true", "yes"}
        self.glow_phase = 0.52
        self.current_backend = "local"
        self.current_wsl_distro = ""
        self.active_remote_profile: Optional[RemoteProfile] = None
        self.status_icon_running = make_colored_icon(QColor("lime"))
        self.status_icon_stopped = make_colored_icon(QColor("red"))
        self.host_status_icon_running = make_colored_icon(QColor("lime"), size=12)
        self.host_status_icon_off = make_colored_icon(QColor("red"), size=12)
        self._container_metrics_text = ""
        self._host_metrics_tooltip_text = self.texts["host_metrics_unknown"]
        self._infra_activity_text = ""
        self.client: Optional[docker.DockerClient] = None
        self.last_containers: List[object] = []
        self.container_by_name: Dict[str, object] = {}
        self.container_sort_column: Optional[int] = None
        self.container_sort_direction: Optional[str] = None
        self.refresh_thread: Optional[QThread] = None
        self.worker: Optional[RefreshWorker] = None
        self.remote_connect_thread: Optional[QThread] = None
        self.remote_connect_worker: Optional[RemoteConnectWorker] = None
        self.connecting_profile: Optional[RemoteProfile] = None
        self.connecting_restart_mode = False
        self.tunnel_process: Optional[subprocess.Popen] = None
        self.audio_output = None
        self.media_player = None
        self.root_surface: Optional[BackgroundSurface] = None
        self.latest_release_tag = ""
        self.latest_release_url = GITHUB_RELEASES_URL
        self.latest_release_info: Dict = {}
        self.update_download_thread: Optional[QThread] = None
        self.update_download_worker: Optional[UpdateDownloadWorker] = None
        self.update_install_process: Optional[QProcess] = None
        self.startup_catalog_refresh_thread: Optional[QThread] = None
        self.startup_catalog_refresh_worker: Optional[CatalogRefreshWorker] = None
        self.group_mode = str(self.settings.value("containers/group_mode", "project") or "project")
        if self.group_mode not in {"project", "network", "none"}:
            self.group_mode = "project"
        self.collapsed_groups = set()
        self.restart_grace_until = 0.0
        self.restart_watch_active = False
        self.restart_watch_profile: Optional[RemoteProfile] = None
        self.restart_watch_attempt = 0
        self.restart_watch_deadline = 0.0
        self.restart_recovery_pending_refresh = False
        self.restart_notification: Optional[QMessageBox] = None
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(UPDATE_CHECK_INTERVAL_MS)
        self.update_timer.timeout.connect(self.check_for_updates)
        if self.auto_check_updates:
            self.update_timer.start()
        self.restart_watch_timer = QTimer(self)
        self.restart_watch_timer.setInterval(4000)
        self.restart_watch_timer.timeout.connect(self.retry_restart_connection)
        self.setWindowTitle(self.texts["app_title"])
        if ICON_FILE.exists():
            self.setWindowIcon(QIcon(str(ICON_FILE)))
        try:
            window_w = int(self.settings.value("window_width", 1120))
            window_h = int(self.settings.value("window_height", 640))
        except Exception:
            window_w, window_h = 1120, 640
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        if available is not None and available.isValid():
            max_width = max(640, available.width() - 32)
            max_height = max(360, available.height() - 32)
            window_w = min(max(640, window_w), max_width)
            window_h = min(max(360, window_h), max_height)
        self.setMinimumSize(640, 360)
        self.resize(window_w, window_h)
        self._last_normal_geometry = self.geometry()
        self._build_static_ui()
        self.update_infrastructure_ui(False)
        self._setup_audio()
        self._setup_fx()
        self._load_theme()
        self.reload_profiles_ui()
        QTimer.singleShot(0, self.initialize_runtime)
        QTimer.singleShot(1200, self.refresh_catalog_cache_on_startup)
        if self.auto_check_updates:
            QTimer.singleShot(4000, self.check_for_updates)

    def refresh_catalog_cache_on_startup(self):
        if self.startup_catalog_refresh_thread is not None and self.startup_catalog_refresh_thread.isRunning():
            return
        sources = load_deployment_repository_sources()
        cached = load_cached_deployment_catalog()
        previous_by_source: Dict[str, List[ImageTemplate]] = {}
        for item in cached:
            previous_by_source.setdefault(item.repository_source, []).append(item)
        self.startup_catalog_refresh_thread = QThread(self)
        self.startup_catalog_refresh_worker = CatalogRefreshWorker(sources, previous_by_source)
        self.startup_catalog_refresh_worker.moveToThread(self.startup_catalog_refresh_thread)
        self.startup_catalog_refresh_thread.started.connect(self.startup_catalog_refresh_worker.run)
        self.startup_catalog_refresh_worker.finished.connect(self.on_startup_catalog_refresh_finished)
        self.startup_catalog_refresh_worker.finished.connect(self.startup_catalog_refresh_thread.quit)
        self.startup_catalog_refresh_worker.finished.connect(self.startup_catalog_refresh_worker.deleteLater)
        self.startup_catalog_refresh_thread.finished.connect(self.on_startup_catalog_refresh_thread_finished)
        self.startup_catalog_refresh_thread.finished.connect(self.startup_catalog_refresh_thread.deleteLater)
        self.startup_catalog_refresh_thread.start()

    def on_startup_catalog_refresh_finished(self, refreshed: List[ImageTemplate], errors: List[str]):
        if refreshed:
            save_cached_deployment_catalog(refreshed)

    def on_startup_catalog_refresh_thread_finished(self):
        self.startup_catalog_refresh_worker = None
        self.startup_catalog_refresh_thread = None

    def initialize_runtime(self):
        first_run_shown = False
        if os.name != "nt" and str(self.settings.value("setup/first_run_complete", "false")).lower() not in {"1", "true", "yes"}:
            first_run_shown = self.run_first_run_wizard()

        if self.auto_start_docker_desktop and not self.is_local_docker_available():
            desktop_installed = (
                self.windows_docker_desktop_installed()
                if os.name == "nt"
                else self.linux_docker_desktop_installed()
            )
            if desktop_installed and self.try_start_docker_desktop():
                self.statusBar().showMessage(self.texts["docker_desktop_starting"])
                QTimer.singleShot(1800, self.reconnect_local_docker_after_desktop_start)
                return

        if os.name != "nt" and not self.is_local_docker_available() and first_run_shown:
            self.client = None
            self.update_infrastructure_ui(False)
            status = self.texts["first_run_docker_installed_no_access"] if shutil.which("docker") else self.texts["first_run_docker_missing"]
            self.statusBar().showMessage(status)
            return
        self.connect_local_docker()

    def run_first_run_wizard(self, force: bool = False) -> bool:
        if os.name == "nt" and not force:
            return False
        dialog = FirstRunWizardDialog(self, self)
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            self.settings.setValue("setup/first_run_complete", "true")
            self.settings.sync()
        return True

    def closeEvent(self, event):
        if not self._skip_persist_window_state:
            try:
                if self.isFullScreen() or self.isMaximized():
                    rect = self._last_normal_geometry or self.normalGeometry()
                    size = rect.size()
                else:
                    size = self.size()
                self.settings.setValue("window_width", size.width())
                self.settings.setValue("window_height", size.height())
            except Exception:
                pass
        if hasattr(self, "table"):
            self._save_container_column_widths()
        self.settings.sync()
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.isFullScreen() and not self.isMaximized():
            self._last_normal_geometry = self.geometry()
        timer = getattr(self, "_column_magnet_resize_timer", None)
        if self.container_column_magnet and timer is not None:
            timer.start()

    def moveEvent(self, event):
        super().moveEvent(event)
        if not self.isFullScreen() and not self.isMaximized():
            self._last_normal_geometry = self.geometry()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            restore_rect = self._last_normal_geometry
            self.showNormal()
            if restore_rect is not None and restore_rect.isValid():
                self.setGeometry(restore_rect)
            return
        normal_rect = self.normalGeometry() if self.isMaximized() else self.geometry()
        if normal_rect.isValid():
            self._last_normal_geometry = normal_rect
        self.showFullScreen()

    def eventFilter(self, watched, event):
        if hasattr(self, "table") and watched in {self.table, self.table.viewport()}:
            if event.type() == QEvent.Type.Wheel and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                if delta:
                    step = 10 if delta > 0 else -10
                    self.set_container_table_zoom(self.container_table_zoom + step)
                    event.accept()
                    return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.toggle_fullscreen()
            event.accept()
            return
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_0:
                self.set_container_table_zoom(100)
                event.accept()
                return
            if event.key() == Qt.Key.Key_F and hasattr(self, "container_search"):
                self.container_search.setFocus()
                self.container_search.selectAll()
                event.accept()
                return
        if event.key() == Qt.Key.Key_F5:
            self.refresh_containers()
            event.accept()
            return
        super().keyPressEvent(event)

    def set_container_table_zoom(self, percent: int):
        if not hasattr(self, "table"):
            return
        new_percent = max(70, min(160, int(percent)))
        old_percent = max(70, min(160, int(getattr(self, "container_table_zoom", 100) or 100)))
        if new_percent == old_percent:
            return
        ratio = new_percent / float(old_percent)
        self.container_table_zoom = new_percent

        base_font = QFont(getattr(self, "container_table_base_font", self.table.font()))
        base_size = base_font.pointSizeF()
        if base_size <= 0:
            base_size = 9.0
        table_font = QFont(base_font)
        table_font.setPointSizeF(max(7.0, base_size * new_percent / 100.0))
        self.table.setFont(table_font)

        header_font = QFont(table_font)
        header_font.setBold(True)
        self.table.horizontalHeader().setFont(header_font)
        self.table.verticalHeader().setDefaultSectionSize(max(28, round(34 * new_percent / 100.0)))

        self._restoring_container_column_widths = True
        try:
            for column in range(self.table.columnCount()):
                current_width = self.table.columnWidth(column)
                self.table.setColumnWidth(column, max(24, round(current_width * ratio)))
        finally:
            self._restoring_container_column_widths = False

        self.settings.setValue("container_table_zoom", new_percent)
        if self.container_column_magnet:
            QTimer.singleShot(0, self._apply_container_column_magnet)
        if self.last_containers:
            self.render_container_table(self.last_containers)
        self.statusBar().showMessage(self.texts["container_zoom_status"].format(percent=new_percent), 3500)

    def _restore_container_column_widths(self):
        if not hasattr(self, "table"):
            return False
        raw = self.settings.value("containers/column_widths_v1", "")
        if not raw:
            return False
        try:
            widths = json.loads(str(raw))
            if not isinstance(widths, list) or len(widths) != self.table.columnCount():
                return False
            self._container_column_base_widths = [max(24.0, float(value)) for value in widths]
            zoom_factor = max(0.01, self.container_table_zoom / 100.0)
            self._restoring_container_column_widths = True
            try:
                for column, base_width in enumerate(self._container_column_base_widths):
                    self.table.setColumnWidth(column, max(24, round(base_width * zoom_factor)))
            finally:
                self._restoring_container_column_widths = False
            return True
        except (TypeError, ValueError, json.JSONDecodeError):
            return False

    def _save_container_column_widths(self):
        if (
            not hasattr(self, "table")
            or getattr(self, "_restoring_container_column_widths", False)
            or getattr(self, "_applying_column_magnet", False)
        ):
            return
        zoom_factor = max(0.01, self.container_table_zoom / 100.0)
        widths = [
            round(self.table.columnWidth(column) / zoom_factor, 2)
            for column in range(self.table.columnCount())
        ]
        self._container_column_base_widths = list(widths)
        self.settings.setValue("containers/column_widths_v1", json.dumps(widths, separators=(",", ":")))

    def _queue_container_column_width_save(self, *_args):
        if (
            getattr(self, "_restoring_container_column_widths", False)
            or getattr(self, "_applying_column_magnet", False)
        ):
            return
        timer = getattr(self, "_column_width_save_timer", None)
        if timer is not None:
            timer.start()

    def _commit_container_column_widths(self):
        self._save_container_column_widths()
        if self.container_column_magnet:
            self._apply_container_column_magnet()

    def set_container_column_magnet(self, enabled: bool):
        self._save_container_column_widths()
        self.container_column_magnet = bool(enabled)
        self.settings.setValue("containers/column_magnet", "true" if self.container_column_magnet else "false")
        self.settings.sync()
        if self.container_column_magnet:
            QTimer.singleShot(0, self._apply_container_column_magnet)

    def _apply_container_column_magnet(self):
        if not self.container_column_magnet or not hasattr(self, "table"):
            return
        target_width = self.table.viewport().width()
        if target_width <= 0 or self.table.columnCount() <= 0:
            return
        zoom_factor = max(0.01, self.container_table_zoom / 100.0)
        base_widths = self._container_column_base_widths
        if not base_widths or len(base_widths) != self.table.columnCount():
            base_widths = [
                max(24.0, self.table.columnWidth(column) / zoom_factor)
                for column in range(self.table.columnCount())
            ]
            self._container_column_base_widths = list(base_widths)

        weights = [max(1.0, float(width)) for width in base_widths]
        minimum = 24
        if target_width <= minimum * len(weights):
            scaled = [minimum] * len(weights)
        else:
            total = sum(weights) or float(len(weights))
            scaled = [max(minimum, round(target_width * weight / total)) for weight in weights]
            delta = target_width - sum(scaled)
            visual_order = [
                self.table.horizontalHeader().logicalIndex(visual)
                for visual in range(self.table.columnCount())
            ]
            if delta > 0:
                index = 0
                while delta > 0:
                    logical = visual_order[index % len(visual_order)]
                    scaled[logical] += 1
                    delta -= 1
                    index += 1
            elif delta < 0:
                index = len(visual_order) - 1
                remaining = -delta
                guard = 0
                while remaining > 0 and guard < target_width * 2:
                    logical = visual_order[index % len(visual_order)]
                    if scaled[logical] > minimum:
                        scaled[logical] -= 1
                        remaining -= 1
                    index -= 1
                    guard += 1

        self._applying_column_magnet = True
        try:
            for column, width in enumerate(scaled):
                self.table.setColumnWidth(column, width)
        finally:
            self._applying_column_magnet = False

    def show_shortcuts_dialog(self):
        QMessageBox.information(
            self,
            self.texts["info_shortcuts_title"],
            self.texts["info_shortcuts_body"],
        )

    def _build_static_ui(self):
        menubar = QMenuBar(self)
        self.setMenuBar(menubar)
        self._build_menus()
        central = BackgroundSurface(self.current_theme, self.transparent_mode, self.transparency_level)
        central.setMinimumHeight(620)
        self.root_surface = central
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 6, 10, 6)
        main_layout.setSpacing(4)

        hero = QFrame()
        hero.setObjectName("heroPanel")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(12, 5, 12, 5)
        hero_layout.setSpacing(12)
        self.hero_title = QLabel(self.texts["hero_title"])
        self.hero_title.setObjectName("heroTitle")
        self.hero_subtitle = QLabel(self.platform_text("hero_subtitle"))
        self.hero_subtitle.setObjectName("heroSubtitle")
        self.hero_subtitle.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        hero_layout.addWidget(self.hero_title)
        hero_layout.addWidget(self.hero_subtitle, 1)
        hero.setMaximumHeight(44)
        main_layout.addWidget(hero)

        connection_panel = QFrame()
        connection_panel.setObjectName("controlPanel")
        connection_panel_layout = QVBoxLayout(connection_panel)
        connection_panel_layout.setContentsMargins(10, 3, 10, 3)
        connection_panel_layout.setSpacing(2)
        self.connection_section_title = QLabel(self.texts["controls_connection"])
        self.connection_section_title.setObjectName("sectionTitle")

        selector_layout = QHBoxLayout()
        selector_layout.setSpacing(5)
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(190)
        self.profile_combo.currentIndexChanged.connect(self.on_profile_changed)
        self.btn_profiles = QPushButton(self.texts["btn_profiles"])
        self.btn_profiles.setObjectName("profileAction")
        self.btn_start_profile = QPushButton(self.texts["btn_start_profile"])
        self.btn_start_profile.setObjectName("primaryAction")
        self.btn_ssh_terminal = QPushButton(self.texts["btn_ssh_terminal"])
        self.btn_ssh_terminal.setObjectName("profileAction")
        self.btn_transparency = QPushButton()
        self.btn_transparency.setObjectName("profileAction")
        self.btn_music = QPushButton()
        self.btn_music.setObjectName("profileAction")
        self.transparency_label = QLabel(self.texts["transparency_level"])
        self.transparency_slider = QSlider(Qt.Orientation.Horizontal)
        self.transparency_slider.setRange(35, 100)
        self.transparency_slider.setValue(self.transparency_level)
        self.transparency_slider.valueChanged.connect(self.set_transparency_level)
        self.remote_hint = QLabel(self.platform_text("remote_hint"))
        self.remote_hint.setWordWrap(False)
        self.remote_hint.setMaximumWidth(1)
        self.remote_hint.setVisible(False)
        self.remote_hint.setToolTip(self.platform_text("remote_hint"))
        self.remote_sysinfo_label = QLabel(self.texts["remote_sysinfo_unknown"])
        self.remote_sysinfo_label.setWordWrap(False)
        self.remote_sysinfo_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self.profile_label_widget = QLabel(self.texts["profile_label"])
        for button, compact, width in [
            (self.btn_profiles, "\u2630", 38),
            (self.btn_start_profile, "\u25b6", 38),
            (self.btn_ssh_terminal, ">_", 42),
        ]:
            button.setToolTip(button.text())
            button.setText(compact)
            button.setFixedWidth(width)
        selector_layout.addWidget(self.connection_section_title)
        selector_layout.addWidget(self.profile_label_widget)
        selector_layout.addWidget(self.profile_combo)
        selector_layout.addWidget(self.btn_profiles)
        selector_layout.addWidget(self.btn_start_profile)
        selector_layout.addWidget(self.btn_ssh_terminal)
        selector_layout.addWidget(self.remote_sysinfo_label)
        selector_layout.addStretch()
        connection_panel_layout.addLayout(selector_layout)

        local_layout = QHBoxLayout()
        local_layout.setSpacing(5)
        self.btn_local_profiles = QPushButton(self.texts["btn_local_profiles"])
        self.btn_local_profiles.setObjectName("infoAction")
        self.btn_local = QPushButton(self.texts["local_client"])
        self.btn_local.setObjectName("primaryAction")
        self.wsl_label = QLabel(self.texts["wsl_label"])
        self.wsl_combo = QComboBox()
        self.wsl_combo.setMinimumWidth(140)
        self.btn_wsl_refresh = QPushButton(self.texts["btn_wsl_refresh"])
        self.btn_wsl_refresh.setObjectName("profileAction")
        self.btn_wsl_profile = QPushButton(self.texts["btn_wsl_profile"])
        self.btn_wsl_profile.setObjectName("primaryAction")
        for button, compact, width in [
            (self.btn_local_profiles, "\u24d8", 38),
            (self.btn_local, "LOCAL", 100),
            (self.btn_wsl_profile, "WSL", 72),
            (self.btn_wsl_refresh, "\u21bb", 38),
        ]:
            button.setToolTip(button.text())
            button.setText(compact)
            button.setFixedWidth(width)
        if os.name != "nt":
            self.wsl_label.setVisible(False)
            self.wsl_combo.setVisible(False)
            self.btn_wsl_refresh.setVisible(False)
            self.btn_wsl_profile.setVisible(False)
        local_layout.addWidget(self.btn_local_profiles)
        local_layout.addWidget(self.btn_local)
        local_layout.addWidget(self.btn_wsl_profile)
        local_layout.addWidget(self.wsl_label)
        local_layout.addWidget(self.wsl_combo)
        local_layout.addWidget(self.btn_wsl_refresh)
        local_layout.addWidget(self.btn_transparency)
        local_layout.addWidget(self.btn_music)
        self.transparency_label.setVisible(False)
        self.transparency_slider.setMaximumWidth(130)
        local_layout.addWidget(self.transparency_slider)
        local_layout.addStretch()
        connection_panel_layout.addLayout(local_layout)
        main_layout.addWidget(connection_panel)

        container_panel = QFrame()
        container_panel.setObjectName("controlPanel")
        container_panel_layout = QVBoxLayout(container_panel)
        container_panel_layout.setContentsMargins(10, 4, 10, 4)
        container_panel_layout.setSpacing(0)
        self.container_section_title = QLabel(self.texts["controls_containers"])
        self.container_section_title.setObjectName("sectionTitle")
        top_layout = QHBoxLayout()
        top_layout.setSpacing(4)
        self.btn_refresh = QPushButton(self.texts["btn_refresh"])
        self.btn_start = QPushButton(self.texts["btn_start"])
        self.btn_stop = QPushButton(self.texts["btn_stop"])
        self.btn_restart = QPushButton(self.texts["btn_restart"])
        self.btn_autostart_on = QPushButton(self.texts["btn_autostart_on"])
        self.btn_autostart_off = QPushButton(self.texts["btn_autostart_off"])
        self.btn_pause = QPushButton(self.texts["btn_pause"])
        self.btn_unpause = QPushButton(self.texts["btn_unpause"])
        self.btn_remove = QPushButton(self.texts["btn_remove"])
        self.btn_logs = QPushButton(self.texts["btn_logs"])
        self.btn_edit_start = QPushButton(self.texts["btn_edit_start"])
        self.btn_new = QPushButton(self.texts["btn_new"])
        primary_container_buttons = [self.btn_refresh, self.btn_start, self.btn_stop, self.btn_restart, self.btn_new]
        secondary_container_buttons = [self.btn_autostart_on, self.btn_autostart_off, self.btn_pause, self.btn_unpause, self.btn_logs, self.btn_edit_start, self.btn_remove]
        compact_container_actions = [
            (self.btn_refresh, "\u21bb", 38),
            (self.btn_start, "\u25b6", 38),
            (self.btn_stop, "\u25a0", 38),
            (self.btn_restart, "\u21ba", 38),
            (self.btn_new, self.texts["btn_shop_short"], 88),
            (self.btn_autostart_on, "A\u2713", 42),
            (self.btn_autostart_off, "A\u00d7", 42),
            (self.btn_pause, "\u2161", 38),
            (self.btn_unpause, "\u25b7", 38),
            (self.btn_logs, "\u2261", 38),
            (self.btn_edit_start, "\u270e", 38),
            (self.btn_remove, "\u00d7", 38),
        ]
        for button, compact, width in compact_container_actions:
            button.setToolTip(button.text())
            button.setText(compact)
            button.setFixedWidth(width)
        for button in primary_container_buttons + secondary_container_buttons:
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            button.setObjectName("containerAction")
            button.setMaximumHeight(30)
        self.btn_new.setObjectName("shopButton")
        top_layout.addWidget(self.container_section_title)
        for button in primary_container_buttons:
            top_layout.addWidget(button)
        for button in secondary_container_buttons:
            top_layout.addWidget(button)
        top_layout.addStretch()
        container_panel_layout.addLayout(top_layout)
        main_layout.addWidget(container_panel)

        self.select_all_checkbox = QCheckBox(self.texts["select_all"])
        self.select_all_checkbox.stateChanged.connect(self.on_select_all)

        self.container_search = QLineEdit()
        self.container_search.setPlaceholderText(self.texts["container_search_placeholder"])
        self.container_search.setClearButtonEnabled(True)
        self.container_search.setMaximumWidth(320)
        self.container_search.textChanged.connect(self.filter_container_rows)

        self.group_by_label = QLabel(self.texts["group_by_label"])
        self.group_by_combo = QComboBox()
        self.group_by_combo.setMinimumWidth(120)
        self.populate_group_mode_combo()
        self.group_by_combo.currentIndexChanged.connect(self.on_group_mode_changed)

        self.infra_info_button = QPushButton(self.texts["infra_unknown"])
        self.infra_info_button.setObjectName("infoAction")
        self.infra_info_button.setMinimumWidth(300)
        self.infra_info_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.infra_info_button.setToolTip(self.texts["infra_unknown"])
        self.infra_info_button.setIcon(make_terminal_icon(QColor(effective_accent_color(self.current_theme, self.accent_color)), 16))
        self.infra_info_button.setIconSize(QSize(16, 16))

        self.btn_host_restart = QPushButton(self.texts["btn_host_restart"])
        self.btn_host_restart.setObjectName("profileAction")
        self.btn_host_restart.setIcon(self.host_status_icon_off)
        self.btn_host_restart.setIconSize(QPixmap(12, 12).size())
        self.btn_host_restart.setMinimumWidth(170)
        self.btn_host_restart.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.column_magnet_checkbox = QCheckBox(self.texts["column_magnet"])
        self.column_magnet_checkbox.setChecked(self.container_column_magnet)
        self.column_magnet_checkbox.setToolTip(self.texts["column_magnet_tooltip"])
        self.column_magnet_checkbox.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.column_magnet_checkbox.toggled.connect(self.set_container_column_magnet)

        view_panel = QFrame()
        view_panel.setObjectName("controlPanel")
        view_panel_layout = QVBoxLayout(view_panel)
        view_panel_layout.setContentsMargins(10, 4, 10, 4)
        view_panel_layout.setSpacing(0)
        self.view_section_title = QLabel(self.texts["controls_view"])
        self.view_section_title.setObjectName("sectionTitle")
        infra_layout = QHBoxLayout()
        infra_layout.setSpacing(5)
        infra_layout.addWidget(self.view_section_title)
        infra_layout.addWidget(self.select_all_checkbox)
        infra_layout.addWidget(self.container_search)
        infra_layout.addWidget(self.group_by_label)
        infra_layout.addWidget(self.group_by_combo)
        infra_layout.addStretch(1)
        infra_layout.addWidget(self.column_magnet_checkbox, 0)
        view_panel_layout.addLayout(infra_layout)

        host_actions_layout = QHBoxLayout()
        host_actions_layout.setSpacing(6)
        host_actions_layout.addWidget(self.infra_info_button, 1)
        host_actions_layout.addWidget(self.btn_host_restart, 0)
        view_panel_layout.addLayout(host_actions_layout)
        main_layout.addWidget(view_panel)

        self.table = QTableWidget(0, 12)
        self.table.setHorizontalHeader(ResizeGripHeader(Qt.Orientation.Horizontal, self.table))
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.container_table_base_font = QFont(self.table.font())
        base_font_size = self.container_table_base_font.pointSizeF()
        if base_font_size <= 0:
            base_font_size = 9.0
        table_font = QFont(self.container_table_base_font)
        table_font.setPointSizeF(max(7.0, base_font_size * self.container_table_zoom / 100.0))
        self.table.setFont(table_font)
        self._set_table_headers()
        header = self.table.horizontalHeader()
        header_font = QFont(table_font)
        header_font.setBold(True)
        header.setFont(header_font)
        header.setStretchLastSection(False)
        header.setSectionsMovable(True)
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self.on_container_header_clicked)
        header.setMinimumSectionSize(24)
        for column in range(12):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        base_widths = [28, 24, 125, 140, 70, 50, 135, 150, 38, 190, 95, 110]
        zoom_factor = self.container_table_zoom / 100.0
        for column, base_width in enumerate(base_widths):
            self.table.setColumnWidth(column, max(24, round(base_width * zoom_factor)))
        self._restoring_container_column_widths = False
        restored_widths = self._restore_container_column_widths()
        if not restored_widths:
            self._container_column_base_widths = [float(width) for width in base_widths]
        self._column_width_save_timer = QTimer(self)
        self._column_width_save_timer.setSingleShot(True)
        self._column_width_save_timer.setInterval(250)
        self._column_width_save_timer.timeout.connect(self._commit_container_column_widths)
        header.sectionResized.connect(self._queue_container_column_width_save)
        self._column_magnet_resize_timer = QTimer(self)
        self._column_magnet_resize_timer.setSingleShot(True)
        self._column_magnet_resize_timer.setInterval(35)
        self._column_magnet_resize_timer.timeout.connect(self._apply_container_column_magnet)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(max(28, round(34 * zoom_factor)))
        self.table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_row_context_menu)
        self.table.itemSelectionChanged.connect(self.update_link_widget_selection_states)
        self.table.cellClicked.connect(self.on_table_cell_clicked)
        self.table.installEventFilter(self)
        self.table.viewport().installEventFilter(self)
        main_layout.addWidget(self.table, 1)
        if self.container_column_magnet:
            QTimer.singleShot(0, self._apply_container_column_magnet)

        self.main_scroll_area = QScrollArea(self)
        self.main_scroll_area.setObjectName("mainScrollArea")
        self.main_scroll_area.setWidgetResizable(True)
        self.main_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.main_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.main_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.main_scroll_area.viewport().setAutoFillBackground(False)
        self.main_scroll_area.setWidget(central)
        self.setCentralWidget(self.main_scroll_area)
        status = QStatusBar(self)
        self.setStatusBar(status)
        status.showMessage(self.texts["status_ready"])

        self.btn_refresh.clicked.connect(self.refresh_containers)
        self.btn_start.clicked.connect(lambda: self.bulk_action("start"))
        self.btn_stop.clicked.connect(lambda: self.bulk_action("stop"))
        self.btn_restart.clicked.connect(lambda: self.bulk_action("restart"))
        self.btn_autostart_on.clicked.connect(lambda: self.bulk_action("autostart_on"))
        self.btn_autostart_off.clicked.connect(lambda: self.bulk_action("autostart_off"))
        self.btn_pause.clicked.connect(lambda: self.bulk_action("pause"))
        self.btn_unpause.clicked.connect(lambda: self.bulk_action("unpause"))
        self.btn_remove.clicked.connect(lambda: self.bulk_action("remove"))
        self.btn_logs.clicked.connect(self.show_selected_logs)
        self.btn_edit_start.clicked.connect(self.open_edit_start_wizard)
        self.btn_new.clicked.connect(self.open_new_container_wizard)
        self.btn_local.clicked.connect(self.connect_local_docker)
        self.btn_start_profile.clicked.connect(self.start_profile_connection)
        self.btn_ssh_terminal.clicked.connect(self.open_remote_terminal)
        self.btn_profiles.clicked.connect(self.manage_profiles)
        self.btn_local_profiles.clicked.connect(self.show_local_profiles_info)
        self.infra_info_button.clicked.connect(self.open_infra_terminal)
        self.btn_host_restart.clicked.connect(self.restart_host)
        self.btn_wsl_refresh.clicked.connect(self.load_wsl_distros)
        self.btn_wsl_profile.clicked.connect(self.connect_wsl_docker)
        self.btn_transparency.clicked.connect(self.toggle_transparency)
        self.btn_music.clicked.connect(self.toggle_music)
        self.load_wsl_distros()
        self.update_transparency_button()
        self.update_music_button()

    def _setup_fx(self):
        self.glow_timer = QTimer(self)
        self.glow_timer.timeout.connect(self.advance_glow)
        self.fx_animations = []
        for button, color in [
            (self.btn_start_profile, "#33f0ff"),
            (self.btn_local, "#4bffad"),
            (self.btn_wsl_profile, "#6ec8ff"),
        ]:
            shadow = QGraphicsDropShadowEffect(button)
            shadow.setBlurRadius(28)
            shadow.setOffset(0, 0)
            shadow.setColor(QColor(color))
            button.setGraphicsEffect(shadow)
            anim = QPropertyAnimation(shadow, b"blurRadius", self)
            anim.setStartValue(18)
            anim.setEndValue(42)
            anim.setDuration(1500)
            anim.setLoopCount(-1)
            anim.start()
            self.fx_animations.append(anim)
        self.update_glow_timer()
    def _build_menus(self):
        menubar = self.menuBar()
        menubar.clear()
        self.file_menu = QMenu(self.texts["menu_file"], self)
        menubar.addMenu(self.file_menu)
        self.action_store = self.file_menu.addAction(self.texts["menu_store"])
        store_action_font = self.action_store.font()
        store_action_font.setBold(True)
        self.action_store.setFont(store_action_font)
        self.action_store.setIcon(make_category_icon("all", QColor(effective_accent_color(self.current_theme, self.accent_color)), 16))
        self.action_store.triggered.connect(self.open_new_container_wizard)
        self.file_menu.addSeparator()
        self.action_profiles_import = self.file_menu.addAction(self.texts["menu_profiles_import"])
        self.action_profiles_import.triggered.connect(self.import_profiles_from_file)
        self.action_profiles_export = self.file_menu.addAction(self.texts["menu_profiles_export"])
        self.action_profiles_export.triggered.connect(self.export_profiles_to_file)
        self.file_menu.addSeparator()
        self.action_quit = self.file_menu.addAction(self.texts["menu_quit"])
        self.action_quit.triggered.connect(self.close)

        self.view_menu = QMenu(self.texts["menu_view"], self)
        menubar.addMenu(self.view_menu)
        self.action_fullscreen = self.view_menu.addAction(self.texts["menu_fullscreen"])
        self.action_fullscreen.setShortcut("F11")
        self.action_fullscreen.triggered.connect(self.toggle_fullscreen)
        self.view_menu.addSeparator()

        self.theme_menu = QMenu(self.texts["menu_theme"], self)
        self.view_menu.addMenu(self.theme_menu)
        self.action_theme_day = self.theme_menu.addAction(self.texts["theme_day"])
        self.action_theme_day.triggered.connect(lambda: self.set_theme("day"))
        self.action_theme_light = self.theme_menu.addAction(self.texts["theme_light"])
        self.action_theme_light.triggered.connect(lambda: self.set_theme("light"))
        self.action_theme_dark = self.theme_menu.addAction(self.texts["theme_dark"])
        self.action_theme_dark.triggered.connect(lambda: self.set_theme("dark"))
        self.action_theme_black = self.theme_menu.addAction(self.texts["theme_black"])
        self.action_theme_black.triggered.connect(lambda: self.set_theme("black"))
        self.action_theme_night = self.theme_menu.addAction(self.texts["theme_night"])
        self.action_theme_night.triggered.connect(lambda: self.set_theme("night"))

        self.lang_menu = QMenu(self.texts["menu_lang"], self)
        self.view_menu.addMenu(self.lang_menu)
        self.action_lang_en = self.lang_menu.addAction(self.texts["lang_en"])
        self.action_lang_en.triggered.connect(lambda: self.set_language("EN"))
        self.action_lang_pl = self.lang_menu.addAction(self.texts["lang_pl"])
        self.action_lang_pl.triggered.connect(lambda: self.set_language("PL"))

        self.config_menu = QMenu(self.texts["menu_config"], self)
        menubar.addMenu(self.config_menu)
        self.action_llm = self.config_menu.addAction(self.texts["menu_llm"])
        self.action_llm.triggered.connect(self.open_llm_settings_dialog)
        self.action_app_settings = self.config_menu.addAction(self.texts["menu_app"])
        self.action_app_settings.triggered.connect(self.open_app_settings_dialog)
        self.action_repo_builder = self.config_menu.addAction(self.texts["menu_repo_builder"])
        self.action_repo_builder.triggered.connect(self.open_repo_builder)
        self.action_dependencies = self.config_menu.addAction(self.texts["menu_dependencies"])
        self.action_dependencies.triggered.connect(self.open_dependencies_dialog)
        self.action_first_run_wizard = None
        if os.name != "nt":
            self.action_first_run_wizard = self.config_menu.addAction(self.texts["menu_first_run_wizard"])
            self.action_first_run_wizard.triggered.connect(lambda: self.run_first_run_wizard(force=True))
        self.config_menu.addSeparator()
        self.action_reset_settings = self.config_menu.addAction(self.texts["menu_reset_settings"])
        self.action_reset_settings.triggered.connect(self.reset_settings_to_defaults)
        self.action_factory_reset = self.config_menu.addAction(self.texts["menu_factory_reset"])
        self.action_factory_reset.triggered.connect(self.factory_reset)

        self.info_menu = QMenu(self.texts["menu_info"], self)
        menubar.addMenu(self.info_menu)
        self.action_info_app = self.info_menu.addAction(self.texts["info_app"])
        self.action_info_app.triggered.connect(self.show_app_info_dialog)
        self.action_check_updates = self.info_menu.addAction(self.texts["info_check_updates"])
        self.action_check_updates.triggered.connect(lambda: self.check_for_updates(True))
        self.action_shortcuts = self.info_menu.addAction(self.texts["info_shortcuts"])
        self.action_shortcuts.triggered.connect(self.show_shortcuts_dialog)
        self.info_menu.addSeparator()
        self.action_safe_danger = self.info_menu.addAction(self.texts["info_safe_danger"])
        self.action_safe_danger.triggered.connect(self.show_info_dialog)

    def _translate_menus(self):
        """Translate existing menu objects without deleting an active Linux QMenu."""
        if not hasattr(self, "file_menu"):
            return
        self.file_menu.setTitle(self.texts["menu_file"])
        self.action_store.setText(self.texts["menu_store"])
        self.action_store.setIcon(make_category_icon("all", QColor(effective_accent_color(self.current_theme, self.accent_color)), 16))
        self.action_profiles_import.setText(self.texts["menu_profiles_import"])
        self.action_profiles_export.setText(self.texts["menu_profiles_export"])
        self.action_quit.setText(self.texts["menu_quit"])
        self.view_menu.setTitle(self.texts["menu_view"])
        self.action_fullscreen.setText(self.texts["menu_fullscreen"])
        self.theme_menu.setTitle(self.texts["menu_theme"])
        self.action_theme_day.setText(self.texts["theme_day"])
        self.action_theme_light.setText(self.texts["theme_light"])
        self.action_theme_dark.setText(self.texts["theme_dark"])
        self.action_theme_black.setText(self.texts["theme_black"])
        self.action_theme_night.setText(self.texts["theme_night"])
        self.lang_menu.setTitle(self.texts["menu_lang"])
        self.action_lang_en.setText(self.texts["lang_en"])
        self.action_lang_pl.setText(self.texts["lang_pl"])
        self.config_menu.setTitle(self.texts["menu_config"])
        self.action_llm.setText(self.texts["menu_llm"])
        self.action_app_settings.setText(self.texts["menu_app"])
        self.action_repo_builder.setText(self.texts["menu_repo_builder"])
        self.action_dependencies.setText(self.texts["menu_dependencies"])
        if self.action_first_run_wizard is not None:
            self.action_first_run_wizard.setText(self.texts["menu_first_run_wizard"])
        self.action_reset_settings.setText(self.texts["menu_reset_settings"])
        self.action_factory_reset.setText(self.texts["menu_factory_reset"])
        self.info_menu.setTitle(self.texts["menu_info"])
        self.action_info_app.setText(self.texts["info_app"])
        self.action_check_updates.setText(self.texts["info_check_updates"])
        self.action_shortcuts.setText(self.texts["info_shortcuts"])
        self.action_safe_danger.setText(self.texts["info_safe_danger"])

    def _set_table_headers(self):
        def sortable_label(label: str, column: int) -> str:
            active_column = getattr(self, "container_sort_column", None)
            direction = getattr(self, "container_sort_direction", None)
            if active_column != column or direction not in {"asc", "desc"}:
                return f"{label} \u25b2\u25bc"
            marker = "\u25bc" if direction == "desc" else "\u25b2"
            return f"{label} {marker}"

        self.table.setHorizontalHeaderLabels([
            self.texts["col_select"],
            self.texts["col_status_icon"],
            self.texts["col_name"],
            self.texts["col_image"],
            self.texts["col_status"],
            sortable_label(self.texts["col_cpu"], 5),
            sortable_label(self.texts["col_memory"], 6),
            self.texts["col_ports"],
            self.texts["col_autostart"],
            self.texts["col_links"],
            self.texts["col_project"],
            self.texts["col_networks"],
        ])
        autostart_header = self.table.horizontalHeaderItem(8)
        if autostart_header is not None:
            autostart_header.setText("\u21bb")
            autostart_header.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
            autostart_header.setToolTip(self.texts["col_autostart"])

    def on_container_header_clicked(self, logical_index: int):
        if logical_index not in {5, 6}:
            return

        if self.container_sort_column != logical_index:
            self.container_sort_column = logical_index
            self.container_sort_direction = "desc"
        elif self.container_sort_direction == "desc":
            self.container_sort_direction = "asc"
        elif self.container_sort_direction == "asc":
            self.container_sort_column = None
            self.container_sort_direction = None
        else:
            self.container_sort_column = logical_index
            self.container_sort_direction = "desc"

        self._set_table_headers()
        self.render_container_table(self.last_containers)

    def sort_containers_for_view(self, containers: List[object]) -> List[object]:
        ordered = sorted(
            list(containers or []),
            key=lambda container: str(getattr(container, "name", "") or "").casefold(),
        )
        column = getattr(self, "container_sort_column", None)
        direction = getattr(self, "container_sort_direction", None)
        if column not in {5, 6} or direction not in {"asc", "desc"}:
            return ordered

        def metric_value(container) -> float:
            metrics = getattr(container, "_dcc_metrics", {}) or {}
            if column == 5:
                try:
                    return float(metrics.get("cpu_percent", 0.0) or 0.0)
                except (TypeError, ValueError):
                    return 0.0
            try:
                return float(metrics.get("memory_usage", 0) or 0)
            except (TypeError, ValueError):
                return 0.0

        return sorted(ordered, key=metric_value, reverse=direction == "desc")

    def populate_group_mode_combo(self):
        if not hasattr(self, "group_by_combo"):
            return
        current = self.group_mode
        self.group_by_combo.blockSignals(True)
        self.group_by_combo.clear()
        self.group_by_combo.addItem(self.texts["group_by_project"], "project")
        self.group_by_combo.addItem(self.texts["group_by_network"], "network")
        self.group_by_combo.addItem(self.texts["group_by_none"], "none")
        index = self.group_by_combo.findData(current)
        self.group_by_combo.setCurrentIndex(index if index >= 0 else 0)
        self.group_by_combo.blockSignals(False)

    def on_group_mode_changed(self):
        mode = self.group_by_combo.currentData() if hasattr(self, "group_by_combo") else "project"
        mode = str(mode or "project")
        if mode not in {"project", "network", "none"}:
            mode = "project"
        self.group_mode = mode
        self.settings.setValue("containers/group_mode", mode)
        self.render_container_table(self.last_containers)

    def _load_theme(self):
        base_theme = "light" if self.current_theme in {"day", "light"} else "dark"
        extra_qss = gaming_stylesheet(self.current_theme, self.glow_phase, self.transparent_mode, self.transparency_level, self.neon_animate, self.accent_color)
        if hasattr(qdarktheme, "setup_theme"):
            qdarktheme.setup_theme(base_theme, additional_qss=extra_qss)
        else:
            app = QApplication.instance()
            if app is not None:
                app.setStyleSheet(extra_qss)
        if self.root_surface is not None:
            self.root_surface.set_visual_state(self.current_theme, self.transparent_mode, self.transparency_level)
        self.refresh_dynamic_theme_elements()
        self.apply_window_surface()
        self.update_transparency_button()
        self.update_music_button()

    def refresh_dynamic_theme_elements(self):
        """Refresh widgets/items whose colors are stored outside the global QSS."""
        effective_accent = effective_accent_color(self.current_theme, self.accent_color)
        if hasattr(self, "infra_info_button"):
            self.infra_info_button.setIcon(make_terminal_icon(QColor(effective_accent), 16))
            self.infra_info_button.setIconSize(QSize(16, 16))
        table = getattr(self, "table", None)
        if table is None:
            return
        accent = QColor(effective_accent)
        background = QColor(accent)
        background.setAlpha(26 if self.current_theme in {"day", "light"} else 38)
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item is None:
                continue
            metadata = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(metadata, dict) or metadata.get("row_type") != "group":
                continue
            item.setBackground(QBrush(background))
            item.setForeground(QBrush(accent))
            header_widget = table.cellWidget(row, 0)
            if header_widget is None:
                continue
            group_button = header_widget.findChild(QPushButton, "containerGroupButton")
            if group_button is not None:
                group_button.style().unpolish(group_button)
                group_button.style().polish(group_button)
                group_button.update()
        table.viewport().update()

    def apply_window_surface(self):
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, self.transparent_mode)
        opacity = max(0.85, self.transparency_level / 100.0) if self.current_theme in {"day", "light"} else max(0.80, self.transparency_level / 100.0)
        self.setWindowOpacity(opacity if self.transparent_mode else 1.0)

    def update_transparency_button(self):
        label = self.texts["btn_transparency_on" if self.transparent_mode else "btn_transparency_off"]
        self.btn_transparency.setText("\u25d0" if self.transparent_mode else "\u25cf")
        self.btn_transparency.setToolTip(label)
        self.btn_transparency.setFixedWidth(38)
        self.transparency_slider.setEnabled(self.transparent_mode)


    def _setup_audio(self):
        if QMediaPlayer is None or QAudioOutput is None:
            self.audio_output = None
            self.media_player = None
            return
        try:
            self.audio_output = QAudioOutput(self)
            self.audio_output.setVolume(0.24)
            self.media_player = QMediaPlayer(self)
            self.media_player.setAudioOutput(self.audio_output)
            if MUSIC_FILE.exists():
                self.media_player.setSource(QUrl.fromLocalFile(str(MUSIC_FILE)))
                if hasattr(self.media_player, "setLoops"):
                    self.media_player.setLoops(QMediaPlayer.Loops.Infinite)
                if self.music_enabled:
                    self.media_player.play()
        except Exception:
            self.audio_output = None
            self.media_player = None

    def update_music_button(self):
        label = self.texts["btn_music_on" if self.music_enabled else "btn_music_off"]
        self.btn_music.setText("\u266b" if self.music_enabled else "\u266a")
        self.btn_music.setFixedWidth(38)
        self.neon_animate = str(self.settings.value("neon_animate", "true")).lower() in {"1", "true", "yes"}
        self.accent_color = normalize_accent_color(str(self.settings.value("accent_color", "#33f0ff")))
        self.btn_music.setEnabled(MUSIC_FILE.exists() and self.media_player is not None)
        if not MUSIC_FILE.exists():
            self.btn_music.setToolTip(self.texts["music_missing"])
        elif self.media_player is None:
            self.btn_music.setToolTip(self.texts["music_unavailable"])
        else:
            self.btn_music.setToolTip(label)

    def toggle_music(self):
        self.music_enabled = not self.music_enabled
        self.neon_animate = str(self.settings.value("neon_animate", "true")).lower() in {"1", "true", "yes"}
        self.accent_color = normalize_accent_color(str(self.settings.value("accent_color", "#33f0ff")))
        self.settings.setValue("music_enabled", "true" if self.music_enabled else "false")
        self.neon_animate = str(self.settings.value("neon_animate", "true")).lower() in {"1", "true", "yes"}
        self.accent_color = normalize_accent_color(str(self.settings.value("accent_color", "#33f0ff")))
        if self.media_player is not None:
            if self.music_enabled and MUSIC_FILE.exists():
                self.media_player.play()
            else:
                self.media_player.stop()
        self.update_music_button()

    def toggle_transparency(self):
        self.transparent_mode = not self.transparent_mode
        self.settings.setValue("transparent_mode", "true" if self.transparent_mode else "false")
        self._load_theme()

    def set_transparency_level(self, value: int):
        self.transparency_level = value
        self.settings.setValue("transparency_level", value)
        self._load_theme()

    def update_glow_timer(self):
        if not hasattr(self, "glow_timer") or self.glow_timer is None:
            return
        # Do not re-apply the global Qt stylesheet on a timer. Re-styling the
        # application while a QMenu is open makes popup menus flicker/disappear.
        self.glow_timer.stop()
        for animation in getattr(self, "fx_animations", []):
            animation.setPaused(not self.neon_animate)

    def advance_glow(self):
        return

    def set_theme(self, theme: str):
        if theme not in {"light", "day", "dark", "black", "night"}:
            theme = "black"
        self.current_theme = theme
        self.settings.setValue("theme", theme)
        self._load_theme()

    def platform_text(self, key: str) -> str:
        if os.name != "nt":
            linux_key = f"{key}_linux"
            if linux_key in self.texts:
                return self.texts[linux_key]
        return self.texts[key]

    def set_language(self, lang: str):
        lang = lang.upper()
        if lang not in TEXTS:
            return
        self.lang = lang
        self.texts = TEXTS[self.lang]
        self.settings.setValue("language", self.lang)
        if os.name != "nt":
            # Some Linux Qt/X11 combinations (including MX/Xfce) can crash if
            # widgets are translated while the QAction from an open popup menu
            # is still dispatching. Defer the entire UI refresh until after the
            # popup has had time to close and the menu event has fully unwound.
            QTimer.singleShot(120, self._apply_language_after_menu_close)
            return
        self.apply_language()
        QTimer.singleShot(0, self._build_menus)

    def _apply_language_after_menu_close(self):
        self.apply_language()
        # Do not clear/recreate the menu bar here. On MX Linux/Xfce this can
        # destroy the QMenu that emitted the language QAction and crash Qt.
        # Updating the existing menu/action captions in place is safe.
        self._translate_menus()

    def apply_compact_action_labels(self):
        actions = [
            (self.btn_profiles, "btn_profiles", "\u2630"),
            (self.btn_start_profile, "btn_start_profile", "\u25b6"),
            (self.btn_ssh_terminal, "btn_ssh_terminal", ">_"),
            (self.btn_local_profiles, "btn_local_profiles", "\u24d8"),
            (self.btn_local, "local_client", "LOCAL"),
            (self.btn_wsl_refresh, "btn_wsl_refresh", "\u21bb"),
            (self.btn_wsl_profile, "btn_wsl_profile", "WSL"),
            (self.btn_refresh, "btn_refresh", "\u21bb"),
            (self.btn_start, "btn_start", "\u25b6"),
            (self.btn_stop, "btn_stop", "\u25a0"),
            (self.btn_restart, "btn_restart", "\u21ba"),
            (self.btn_autostart_on, "btn_autostart_on", "A\u2713"),
            (self.btn_autostart_off, "btn_autostart_off", "A\u00d7"),
            (self.btn_pause, "btn_pause", "\u2161"),
            (self.btn_unpause, "btn_unpause", "\u25b7"),
            (self.btn_remove, "btn_remove", "\u00d7"),
            (self.btn_logs, "btn_logs", "\u2261"),
            (self.btn_edit_start, "btn_edit_start", "\u270e"),
            (self.btn_new, "btn_new", self.texts["btn_shop_short"]),
        ]
        for button, text_key, compact in actions:
            button.setText(compact)
            button.setToolTip(self.texts[text_key])
        self.btn_new.setToolTip(self.texts["menu_store"])
        self.btn_new.setFixedWidth(88)

    def apply_language(self):
        self.setWindowTitle(self.texts["app_title"])
        self.hero_title.setText(self.texts["hero_title"])
        self.hero_subtitle.setText(self.platform_text("hero_subtitle"))
        self.profile_label_widget.setText(self.texts["profile_label"])
        self.apply_compact_action_labels()
        if self.remote_arch:
            self.remote_sysinfo_label.setText(self.texts["remote_sysinfo_label"].format(os=self.remote_os_name or "Linux", arch=self.remote_arch))
        else:
            self.remote_sysinfo_label.setText(self.texts["remote_sysinfo_unknown"])
        self.transparency_label.setText(self.texts["transparency_level"])
        self.remote_hint.setText(self.platform_text("remote_hint"))
        self.remote_hint.setToolTip(self.platform_text("remote_hint"))
        self.wsl_label.setText(self.texts["wsl_label"])
        self.connection_section_title.setText(self.texts["controls_connection"])
        self.container_section_title.setText(self.texts["controls_containers"])
        self.view_section_title.setText(self.texts["controls_view"])
        self.select_all_checkbox.setText(self.texts["select_all"])
        if hasattr(self, "column_magnet_checkbox"):
            self.column_magnet_checkbox.setText(self.texts["column_magnet"])
            self.column_magnet_checkbox.setToolTip(self.texts["column_magnet_tooltip"])
        self.container_search.setPlaceholderText(self.texts["container_search_placeholder"])
        self.group_by_label.setText(self.texts["group_by_label"])
        self.populate_group_mode_combo()
        self._host_metrics_tooltip_text = self.texts["host_metrics_unknown"]
        self._container_metrics_text = ""
        self._infra_activity_text = ""
        self.btn_host_restart.setText(self.texts["btn_host_restart"])
        self.update_infrastructure_ui()
        self._set_table_headers()
        self.update_transparency_button()
        self.update_music_button()
        self.reload_profiles_ui()
        self.load_wsl_distros()
        message = self.texts["status_ready"]
        if self.current_backend == "remote" and isinstance(self.client, SshDockerClient):
            message = message + " - " + self.remote_engine_label()
        self.statusBar().showMessage(message)
        if self.client:
            self.refresh_containers()

    def migrate_legacy_secret_settings(self):
        legacy_openai_key = str(self.settings.value("llm/openai_api_key", ""))
        if legacy_openai_key:
            self.secret_store.set_secret("llm/openai_api_key", legacy_openai_key)
            self.settings.remove("llm/openai_api_key")

    def get_llm_settings(self) -> Dict[str, str]:
        values = {
            "provider": str(self.settings.value("llm/provider", "ollama")),
            "ollama_url": str(self.settings.value("llm/ollama_url", "http://127.0.0.1:11434")),
        }
        for provider in LLM_PROVIDER_ORDER:
            defaults = llm_default_models(provider)
            model = str(self.settings.value(llm_model_setting_key(provider), defaults[0] if defaults else "")).strip()
            values[f"{provider}_model"] = sanitize_openai_model_name(model) if provider == "openai" else model
            if provider != "ollama":
                values[f"{provider}_api_key"] = self.secret_store.get_secret(llm_secret_key(provider))
        return values

    def open_llm_settings_dialog(self):
        dialog = LlmSettingsDialog(self.settings, self.secret_store, self.texts, self)
        dialog.exec()

    def _confirm_reset(self, title_key: str, body_key: str, action_key: str, warning: bool = False) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle(self.texts[title_key])
        dialog.setIcon(QMessageBox.Icon.Warning if warning else QMessageBox.Icon.Question)
        dialog.setText(self.texts[body_key])
        reset_button = dialog.addButton(self.texts[action_key], QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = dialog.addButton(self.texts["reset_cancel"], QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(cancel_button)
        dialog.exec()
        return dialog.clickedButton() is reset_button

    def _restart_after_reset(self):
        if getattr(sys, "frozen", False):
            program = sys.executable
            arguments = list(sys.argv[1:])
            working_directory = str(Path(sys.executable).resolve().parent)
        else:
            program = sys.executable
            arguments = [str(Path(__file__).resolve()), *sys.argv[1:]]
            working_directory = str(Path(__file__).resolve().parent)
        started, _pid = QProcess.startDetached(program, arguments, working_directory)
        if not started:
            QMessageBox.warning(self, self.texts["msg_warning"], self.texts["reset_restart_failed"])
            return
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def reset_settings_to_defaults(self):
        if not self._confirm_reset(
            "reset_settings_title",
            "reset_settings_body",
            "reset_settings_action",
        ):
            return
        try:
            self.settings.clear()
            self.settings.sync()
            if self.settings.status() != QSettings.Status.NoError:
                raise RuntimeError(str(self.settings.status()))
        except Exception as exc:
            QMessageBox.critical(
                self,
                self.texts["reset_settings_title"],
                self.texts["reset_failed"].format(error=exc),
            )
            return
        self._skip_persist_window_state = True
        QMessageBox.information(self, self.texts["reset_settings_title"], self.texts["reset_settings_done"])
        self._restart_after_reset()

    def factory_reset(self):
        if not self._confirm_reset(
            "factory_reset_title",
            "factory_reset_body",
            "factory_reset_action",
            warning=True,
        ):
            return
        try:
            for path in (
                PROFILE_FILE,
                SECRET_FILE,
                DEPLOYMENT_REPOSITORIES_FILE,
                DEPLOYMENT_CATALOG_CACHE_FILE,
            ):
                path.unlink(missing_ok=True)
            self.settings.clear()
            self.settings.sync()
            if self.settings.status() != QSettings.Status.NoError:
                raise RuntimeError(str(self.settings.status()))
        except Exception as exc:
            QMessageBox.critical(
                self,
                self.texts["factory_reset_title"],
                self.texts["reset_failed"].format(error=exc),
            )
            return
        self._skip_persist_window_state = True
        QMessageBox.information(self, self.texts["factory_reset_title"], self.texts["factory_reset_done"])
        self._restart_after_reset()


    def open_app_settings_dialog(self):
        dialog = AppSettingsDialog(
            self.settings,
            self.texts,
            self,
            update_check_callback=lambda: self.check_for_updates(True),
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.auto_start_docker_desktop = dialog.auto_start_checkbox.isChecked()
            self.settings.setValue("auto_start_docker_desktop", "true" if self.auto_start_docker_desktop else "false")
            self.auto_check_updates = dialog.auto_updates_checkbox.isChecked()
            self.update_notifications = dialog.update_notifications_checkbox.isChecked()
            self.settings.setValue("updates/auto_check", "true" if self.auto_check_updates else "false")
            self.settings.setValue("updates/notifications", "true" if self.update_notifications else "false")
            if self.auto_check_updates:
                if not self.update_timer.isActive():
                    self.update_timer.start()
            else:
                self.update_timer.stop()
            selected_theme = dialog.theme_combo.currentData() or self.current_theme
            neon_animate = dialog.neon_checkbox.isChecked()
            accent_color = dialog.neon_color_combo.currentData() or self.accent_color
            self.settings.setValue("neon_animate", "true" if neon_animate else "false")
            self.settings.setValue("accent_color", accent_color)
            self.neon_animate = neon_animate
            self.accent_color = normalize_accent_color(str(accent_color))
            if selected_theme:
                self.current_theme = selected_theme
                self.settings.setValue("theme", selected_theme)
            self.update_glow_timer()
            self._load_theme()
            if self.auto_start_docker_desktop and self.current_backend == "local" and not self.is_local_docker_available():
                if self.try_start_docker_desktop():
                    self.statusBar().showMessage(self.texts["docker_desktop_starting"])
                    QTimer.singleShot(1800, self.reconnect_local_docker_after_desktop_start)

    def open_repo_builder(self):
        commands: List[List[str]] = []
        executable_dir = Path(sys.executable).resolve().parent
        if os.name == "nt":
            commands.append([str(executable_dir / "DCCRepoBuilder.exe")])
        else:
            commands.append(["/usr/bin/dcc-repo-builder"])
            commands.append([str(executable_dir / "dcc-repo-builder")])
        for path in (
            Path(__file__).resolve().parent / "RepoBuilder.py",
            RESOURCE_DIR / "RepoBuilder.py",
        ):
            if path.is_file():
                commands.append([sys.executable, str(path)])
        for command in commands:
            executable = Path(command[0]) if os.path.isabs(command[0]) else None
            if executable is not None and not executable.exists():
                continue
            try:
                subprocess.Popen(command, cwd=str(Path(__file__).resolve().parent), creationflags=CREATE_NO_WINDOW)
                return
            except Exception:
                continue
        QMessageBox.warning(self, self.texts["menu_repo_builder"], self.texts["repo_builder_missing"])

    def open_dependencies_dialog(self):
        DependencyManagerDialog(self, self).exec()

    def generate_ai_docker_command(self, provider: str, model: str, prompt: str, current_command: str, image: str = "", edit_mode: bool = False, runtime_context: str = "") -> str:
        settings = self.get_llm_settings()
        provider = (provider or settings.get("provider") or "ollama").strip().lower()
        model = llm_selected_model(settings, provider, model)
        preferred_cli = "balena" if str(current_command or "").strip().lower().startswith("balena run") else "docker"
        system_prompt = (
            "You edit docker or balena run commands for Docker Control Center. "
            "Return only one valid docker or balena run command in a single line. "
            f"Prefer {preferred_cli} run based on the current engine. "
            "Do not add markdown, bullets, explanations or code fences. "
            "Preserve every existing option, mount, environment variable, network setting, restart policy and command unless the user explicitly asks to change it or it is the cause of an error. "
            "Keep existing container name, image, ports and detach mode unless the user explicitly asks to change them. "
            "When choosing or changing a host port, never reuse a host port reported as occupied by another container. "
            "If the user asks to change IP, port, network, volume, environment, command or restart behavior, update the exact Docker option needed and keep unrelated configuration intact. "
            "If an installation error is provided, diagnose it from the error plus runtime context and return a corrected command that should actually start successfully. "
            "Do not remove security, persistence or required device options merely to make a command shorter. "
            "When a Windows host path is needed, use Docker-compatible forward slashes such as D:/Music. "
            "Prefer safe mounts such as :ro for media folders unless the user asks for write access."
        )
        user_prompt = (
            f"Current command: {current_command or 'docker run -d'}\n"
            f"Preferred CLI: {preferred_cli}\n"
            f"Target image: {image or 'unknown'}\n"
            f"Mode: {'edit existing container start' if edit_mode else 'create new container'}\n"
            f"Runtime context:\n{runtime_context or 'not available'}\n"
            f"User request: {prompt}\n\n"
            "Return only the final docker or balena run command in one line."
        )
        if provider != "ollama" and not str(settings.get(f"{provider}_api_key") or "").strip():
            provider_name = self.texts.get(LLM_PROVIDER_LABEL_KEYS.get(provider, ""), provider)
            raise RuntimeError(self.texts["llm_api_key_missing"].format(provider=provider_name))
        return call_provider_model(settings, provider, model, system_prompt, user_prompt)

    def show_app_info_dialog(self):
        version = APP_VERSION_TAG
        latest_tag = self.latest_release_tag or self.texts["info_app_latest_unknown_value"]
        latest_url = self.latest_release_url or GITHUB_RELEASES_URL
        message = QMessageBox(self)
        message.setWindowTitle(self.texts["info_app_title"])
        message.setIcon(QMessageBox.Icon.Information)
        message.setText(self.texts["info_app_title"])
        info_lines = [
            self.texts["info_app_version"].format(version=version),
            self.texts["info_app_repo"].format(repo=GITHUB_REPO_URL),
            self.texts["info_app_latest"].format(release=latest_tag),
        ]
        message.setInformativeText("\n".join(info_lines))
        message.setDetailedText(f"{self.texts['info_app_changelog_title']}\n{self.texts['info_app_changelog']}")
        btn_repo = message.addButton(self.texts["info_app_open_repo"], QMessageBox.ButtonRole.ActionRole)
        btn_release = message.addButton(self.texts["info_app_open_release"], QMessageBox.ButtonRole.ActionRole)
        btn_check = message.addButton(self.texts["info_app_check_updates"], QMessageBox.ButtonRole.ActionRole)
        message.addButton(QMessageBox.StandardButton.Ok)
        message.exec()
        clicked = message.clickedButton()
        if clicked == btn_repo:
            webbrowser.open(GITHUB_REPO_URL)
        elif clicked == btn_release:
            webbrowser.open(latest_url)
        elif clicked == btn_check:
            self.check_for_updates(True)

    def fetch_latest_release_info(self) -> Dict:
        try:
            request = Request(GITHUB_LATEST_RELEASE_API, headers={"User-Agent": f"DCC/{APP_VERSION}"})
            with urlopen(request, timeout=8) as response:
                payload = response.read().decode("utf-8")
            return json.loads(payload)
        except Exception:
            return {}

    def _parse_version_value(self, tag: str) -> List[int]:
        clean = (tag or "").strip()
        if clean.lower().startswith("v"):
            clean = clean[1:]
        parts = re.split(r"[^0-9]+", clean)
        numbers = []
        for part in parts:
            if part.isdigit():
                numbers.append(int(part))
            else:
                match = re.match(r"(\\d+)", part)
                if match:
                    numbers.append(int(match.group(1)))
        return numbers

    def _is_newer_version(self, latest_tag: str) -> bool:
        latest = self._parse_version_value(latest_tag)
        current = self._parse_version_value(APP_VERSION)
        if not latest:
            return False
        length = max(len(latest), len(current))
        latest += [0] * (length - len(latest))
        current += [0] * (length - len(current))
        return tuple(latest) > tuple(current)

    def select_update_installer_asset(self, release_info: Dict) -> Optional[Dict]:
        assets = list(release_info.get("assets", []) or [])
        if sys.platform.startswith("linux"):
            machine = platform.machine().lower()
            arch_aliases = {
                "x86_64": ("amd64", "x86_64"),
                "amd64": ("amd64", "x86_64"),
                "aarch64": ("arm64", "aarch64"),
                "arm64": ("arm64", "aarch64"),
                "armv7l": ("armhf", "armv7", "armv7l"),
            }.get(machine, (machine,))
            deb_assets = [asset for asset in assets if str(asset.get("name") or "").lower().endswith(".deb")]
            for asset in deb_assets:
                name = str(asset.get("name") or "").lower()
                if any(alias and alias in name for alias in arch_aliases):
                    return asset
            return deb_assets[0] if deb_assets else None
        for asset in assets:
            name = str(asset.get("name") or "")
            if name.lower().endswith("setup.exe"):
                return asset
        for asset in assets:
            name = str(asset.get("name") or "")
            if name.lower().endswith(".exe"):
                return asset
        return None

    def show_update_available(self, release_info: Dict, manual: bool = False):
        release_tag = str(release_info.get("tag_name") or "").strip()
        url = str(release_info.get("html_url") or GITHUB_RELEASES_URL)
        message = QMessageBox(self)
        message.setWindowTitle(self.texts["info_update_available_title"])
        message.setIcon(QMessageBox.Icon.Information)
        message.setText(self.texts["info_update_question"].format(release=release_tag))
        message.setInformativeText(url)
        update_button = message.addButton(self.texts["info_update_now"], QMessageBox.ButtonRole.AcceptRole)
        later_button = message.addButton(self.texts["info_update_later"], QMessageBox.ButtonRole.ActionRole)
        cancel_button = message.addButton(self.texts["info_update_cancel"], QMessageBox.ButtonRole.RejectRole)
        message.exec()
        clicked = message.clickedButton()
        if clicked == update_button:
            self.settings.remove("updates/ignored_release")
            self.settings.remove("updates/remind_after")
            self.install_release_update(release_info)
        elif clicked == later_button:
            self.settings.remove("updates/ignored_release")
            self.settings.setValue("updates/remind_after", str(time.time() + 6 * 60 * 60))
        elif clicked == cancel_button:
            self.settings.setValue("updates/ignored_release", release_tag)
            self.settings.remove("updates/remind_after")

    def install_release_update(self, release_info: Dict):
        asset = self.select_update_installer_asset(release_info)
        if not asset:
            QMessageBox.warning(
                self,
                self.texts["msg_error"],
                self.texts["info_update_no_installer"],
            )
            return
        url = str(asset.get("browser_download_url") or "").strip()
        default_name = "DockerControlCenter.deb" if sys.platform.startswith("linux") else "DockerControlCenter-Setup.exe"
        name = Path(str(asset.get("name") or default_name)).name
        if not url:
            QMessageBox.warning(self, self.texts["msg_error"], self.texts["info_update_download_failed"])
            return
        release_tag = str(release_info.get("tag_name") or "").strip()
        target = Path(tempfile.gettempdir()) / "DockerControlCenterUpdates" / name
        self.statusBar().showMessage(self.texts["info_update_downloading"].format(release=release_tag))
        self.update_download_thread = QThread(self)
        self.update_download_worker = UpdateDownloadWorker(url, str(target))
        self.update_download_worker.moveToThread(self.update_download_thread)
        self.update_download_thread.started.connect(self.update_download_worker.run)
        self.update_download_worker.finished.connect(self.on_update_download_finished)
        self.update_download_worker.finished.connect(self.update_download_thread.quit)
        self.update_download_worker.finished.connect(self.update_download_worker.deleteLater)

        def cleanup_thread():
            if self.update_download_thread is not None:
                self.update_download_thread.deleteLater()
            self.update_download_thread = None
            self.update_download_worker = None

        self.update_download_thread.finished.connect(cleanup_thread)
        self.update_download_thread.start()

    def on_update_download_finished(self, success: bool, path: str, error: str):
        if not success:
            self.statusBar().showMessage(self.texts["status_ready"])
            details = self.texts["info_update_download_failed"]
            if error:
                details += f"\n\n{error}"
            QMessageBox.warning(self, self.texts["msg_error"], details)
            return
        try:
            if sys.platform.startswith("linux"):
                package_path = str(Path(path).resolve())
                pkexec = shutil.which("pkexec")
                apt_get = shutil.which("apt-get")
                if pkexec and apt_get:
                    QMessageBox.information(
                        self,
                        self.texts["info_update_linux_auth_title"],
                        self.texts["info_update_linux_auth"],
                    )
                    process = QProcess(self)
                    process.setWorkingDirectory(str(Path(path).parent))
                    process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
                    process.finished.connect(self.on_linux_update_install_finished)
                    process.errorOccurred.connect(self.on_linux_update_install_error)
                    self.update_install_process = process
                    self.statusBar().showMessage(self.texts["info_update_linux_installing"])
                    process.start(pkexec, [apt_get, "install", "-y", package_path])
                    return
                elif shutil.which("xdg-open"):
                    QMessageBox.information(
                        self,
                        self.texts["info_update_linux_auth_title"],
                        self.texts["info_update_linux_auth"],
                    )
                    subprocess.Popen(["xdg-open", package_path], cwd=str(Path(path).parent))
                    self.statusBar().showMessage(self.texts["info_update_linux_installing"])
                    return
                else:
                    QMessageBox.information(
                        self,
                        self.texts["info_update_linux_auth_title"],
                        self.texts["info_update_linux_auth"],
                    )
                    launch_interactive_terminal(shell_command=f"sudo apt install {shlex.quote(package_path)}")
                    self.statusBar().showMessage(self.texts["info_update_linux_installing"])
                    return
            else:
                subprocess.Popen([path], cwd=str(Path(path).parent))
        except Exception as exc:
            QMessageBox.warning(
                self,
                self.texts["msg_error"],
                f"{self.texts['info_update_download_failed']}\n\n{exc}",
            )
            return
        QTimer.singleShot(500, self.close)

    def on_linux_update_install_error(self, error):
        process = self.update_install_process
        if process is None:
            return
        if error != QProcess.ProcessError.FailedToStart:
            return
        details = self.texts["info_update_linux_install_failed"]
        output = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace").strip()
        if output:
            details += f"\n\n{output}"
        QMessageBox.warning(self, self.texts["msg_error"], details)
        self.statusBar().showMessage(self.texts["status_ready"])
        process.deleteLater()
        self.update_install_process = None

    def on_linux_update_install_finished(self, exit_code: int, _exit_status):
        process = self.update_install_process
        if process is None:
            return
        output = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace").strip()
        process.deleteLater()
        self.update_install_process = None
        if exit_code == 0:
            self.statusBar().showMessage(self.texts["status_ready"])
            QMessageBox.information(
                self,
                self.texts["info_update_linux_auth_title"],
                self.texts["info_update_linux_installed"],
            )
            QTimer.singleShot(250, self.close)
            return
        details = self.texts["info_update_linux_install_failed"]
        if output:
            details += f"\n\n{output}"
        QMessageBox.warning(self, self.texts["msg_error"], details)
        self.statusBar().showMessage(self.texts["status_ready"])

    def check_for_updates(self, notify_always: bool = False):
        info = self.fetch_latest_release_info()
        release_tag = (info.get("tag_name") or "").strip()
        release_url = (info.get("html_url") or GITHUB_RELEASES_URL)
        if release_tag:
            self.latest_release_tag = release_tag
            self.latest_release_url = release_url
            self.latest_release_info = info
        if not release_tag:
            if notify_always:
                QMessageBox.information(self, self.texts["info_update_none_title"], self.texts["info_update_check_failed"])
            return
        if self._is_newer_version(release_tag):
            if notify_always:
                self.show_update_available(info, manual=True)
                return
            if not self.update_notifications:
                return
            ignored_release = str(self.settings.value("updates/ignored_release", ""))
            if ignored_release == release_tag:
                return
            try:
                remind_after = float(self.settings.value("updates/remind_after", "0") or 0)
            except Exception:
                remind_after = 0.0
            if remind_after and time.time() < remind_after:
                return
            self.show_update_available(info)
        elif notify_always:
            QMessageBox.information(self, self.texts["info_update_none_title"], self.texts["info_update_none"])

    def show_info_dialog(self):
        if self.lang == "PL":
            body = (
                "Docker Control Center to panel operatorski do pracy z Dockerem lokalnym, WSL i zdalnymi hostami.\n\n"
                "BEZPIECZNE:\n"
                "- start / stop / restart / logs / pause / unpause\n"
                "- podglad listy kontenerow, portow i inspect\n\n"
                "OSTROZNIE:\n"
                "- usuniecie kontenera\n"
                "- zmiana parametrow run i ponowne wdrozenie\n"
                "- prune nieuzywanych zasobow"
            )
        else:
            body = (
                "Docker Control Center is an operator panel for local Docker, WSL and remote hosts.\n\n"
                "SAFE:\n"
                "- start / stop / restart / logs / pause / unpause\n"
                "- container list, ports and inspect\n\n"
                "CAUTION:\n"
                "- removing a container\n"
                "- changing run parameters and redeploying\n"
                "- pruning unused resources"
            )
        QMessageBox.information(self, self.texts["info_title"], body)

    def reload_profiles_ui(self):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for profile in self.remote_profiles:
            mode_label = self.texts["profile_mode_ssh"] if profile.mode == "ssh" else self.texts["profile_mode_tunnel"]
            label = f"{profile.name} [{mode_label}]"
            self.profile_combo.addItem(label)
        saved = self.settings.value("last_remote_profile", self.remote_profiles[0].name if self.remote_profiles else "")
        index = next((i for i, p in enumerate(self.remote_profiles) if p.name == saved), 0)
        if self.remote_profiles:
            self.profile_combo.setCurrentIndex(index)
        self.profile_combo.blockSignals(False)
        self.update_remote_hint()

    def selected_profile(self) -> Optional[RemoteProfile]:
        index = self.profile_combo.currentIndex()
        if 0 <= index < len(self.remote_profiles):
            return self.remote_profiles[index]
        return None

    def on_profile_changed(self):
        profile = self.selected_profile()
        if profile:
            self.settings.setValue("last_remote_profile", profile.name)
        self.update_remote_hint()

    def update_remote_hint(self):
        profile = self.selected_profile()
        if not profile:
            self.remote_hint.setText(self.texts["profile_no_profiles"])
            return
        self.remote_hint.setText(profile.resolved_base_url() if profile.mode == "ssh" else profile.tunnel_command)

    def decode_wsl_output(self, data: bytes) -> str:
        for encoding in ("utf-16", "utf-16le", "utf-8", "cp852", "cp1250"):
            try:
                text = data.decode(encoding)
                if text:
                    return text
            except Exception:
                continue
        return ""

    def load_wsl_distros(self):
        self.wsl_combo.clear()
        if os.name != "nt":
            self.wsl_combo.addItem(self.texts["wsl_none"])
            return
        try:
            result = subprocess.run(["wsl.exe", "-l", "-q"], capture_output=True, timeout=10)
            stdout = self.decode_wsl_output(result.stdout)
            stderr = self.decode_wsl_output(result.stderr)
            if result.returncode != 0:
                self.wsl_combo.addItem(self.texts["wsl_none"])
                self.wsl_combo.setToolTip(stderr.strip())
                return
            distros = [line.strip() for line in stdout.splitlines() if line.strip() and "Windows Subsystem" not in line]
        except Exception as exc:
            distros = []
            self.wsl_combo.setToolTip(str(exc))
        if distros:
            self.wsl_combo.addItems(distros)
            self.wsl_combo.setToolTip("\n".join(distros))
        else:
            self.wsl_combo.addItem(self.texts["wsl_none"])

    def show_local_profiles_info(self):
        info = self.platform_text("local_profiles_text")
        if os.name != "nt":
            QMessageBox.information(self, self.texts["msg_info"], info)
            return
        distro = self.wsl_combo.currentText().strip() if hasattr(self, "wsl_combo") else ""
        if distro and distro != self.texts["wsl_none"]:
            info = info + "\n\n" + self.texts["local_profiles_wsl_command"].format(distro=distro)
        QMessageBox.information(self, self.texts["msg_info"], info)

    def show_wsl_profile_info(self):
        distro = self.wsl_combo.currentText().strip() if hasattr(self, "wsl_combo") else ""
        if not distro or distro == self.texts["wsl_none"]:
            QMessageBox.information(self, self.texts["msg_info"], self.texts["wsl_detect_error"])
            return
        command = f'wsl -d {distro} sh -lc "docker ps"'
        dialog = CommandInfoDialog(
            self.texts["wsl_help_title"],
            self.texts["wsl_help_text"].format(distro=distro),
            command,
            self.texts,
            self,
        )
        dialog.exec()
    def connect_wsl_docker(self):
        distro = self.wsl_combo.currentText().strip() if hasattr(self, "wsl_combo") else ""
        if not distro or distro == self.texts["wsl_none"]:
            QMessageBox.information(self, self.texts["msg_info"], self.texts["wsl_detect_error"])
            self.update_infrastructure_ui(False)
            return
        try:
            self.client = WslDockerClient(distro)
            self.client.ping()
            self.current_backend = "wsl"
            self.current_wsl_distro = distro
            self.active_remote_profile = None
            self.remote_arch = ""
            self.remote_os_name = ""
            self.remote_sysinfo_label.setText(self.texts["remote_sysinfo_unknown"])
            self.statusBar().showMessage(self.texts["status_wsl_connected"].format(distro=distro))
            self.update_infrastructure_ui(True)
            self.refresh_containers()
        except Exception:
            self.client = None
            QMessageBox.warning(self, self.texts["msg_error"], self.texts["wsl_connect_error"].format(distro=distro))
            self.update_infrastructure_ui(False)

    def autostart_supported(self, container) -> bool:
        attrs = container.attrs or {}
        host_config = attrs.get("HostConfig", {}) or {}
        if "RestartPolicy" in host_config:
            return True
        labels = (attrs.get("Config", {}) or {}).get("Labels", {}) or {}
        for key in labels.keys():
            if key.startswith("io.balena.") or key.startswith("io.resin."):
                return False
        if self.current_backend == "remote" and isinstance(self.client, SshDockerClient):
            if self.get_remote_cli_command() == "balena":
                return False
        if self.current_backend == "wsl" and isinstance(self.client, WslDockerClient):
            if getattr(self.client, "detected_cli", "") == "balena":
                return False
        return True

    def restart_policy_name(self, container) -> str:
        policy = ((container.attrs.get("HostConfig", {}) or {}).get("RestartPolicy", {}) or {})
        name = (policy.get("Name", "") or "").strip()
        return name

    def restart_policy_label(self, container) -> str:
        name = self.restart_policy_name(container)
        if not name:
            if not self.autostart_supported(container):
                return self.texts["autostart_status_managed"]
            return self.texts["autostart_status_unknown"]
        if name == "no":
            return self.texts["autostart_status_off"]
        return self.texts["autostart_status_on"].format(policy=name)

    def confirm_restart_policy_change(self, enable: bool) -> bool:
        title = self.texts["autostart_enable_title"] if enable else self.texts["autostart_disable_title"]
        body = self.texts["autostart_enable_confirm"] if enable else self.texts["autostart_disable_confirm"]
        reply = QMessageBox.question(
            self,
            title,
            body,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def validate_container_action(self, container, action: str) -> Optional[str]:
        container.reload()
        status = (container.status or "").lower()
        if action == "start" and status == "paused":
            return "Kontener jest w pauzie. Najpierw kliknij Wznow."
        if action == "pause" and status != "running":
            return "Pauza dziala tylko dla uruchomionego kontenera."
        if action == "unpause" and status != "paused":
            return "Wznow dziala tylko dla kontenera w stanie pauzy."
        if action == "stop" and status in {"exited", "created"}:
            return "Kontener jest juz zatrzymany."
        if action == "start" and status == "running":
            return "Kontener juz dziala."
        return None

    def execute_container_action(self, container, action: str) -> Optional[str]:
        blocked = self.validate_container_action(container, action) if action in {"start", "stop", "restart", "pause", "unpause"} else None
        if blocked:
            return blocked
        if action == "start":
            container.start()
        elif action == "stop":
            container.stop()
        elif action == "restart":
            container.restart()
        elif action == "pause":
            container.pause()
        elif action == "unpause":
            container.unpause()
        elif action == "remove":
            container.remove(force=True)
        elif action == "autostart_on":
            if not self.autostart_supported(container):
                return None
            container.update(restart_policy={"Name": "unless-stopped"})
        elif action == "autostart_off":
            if not self.autostart_supported(container):
                return None
            container.update(restart_policy={"Name": "no"})
        return None

    def show_action_feedback(self, messages: List[str], title: Optional[str] = None):
        unique = []
        for message in messages:
            if message and message not in unique:
                unique.append(message)
        if unique:
            QMessageBox.information(self, title or self.texts["msg_action_blocked"], "\n".join(unique))

    def container_run_args(self, container) -> List[str]:
        container.reload()
        attrs = container.attrs or {}
        config = attrs.get("Config", {}) or {}
        host_config = attrs.get("HostConfig", {}) or {}
        args = ["run", "-d", "--name", container.name]

        restart_name = ((host_config.get("RestartPolicy", {}) or {}).get("Name") or "").strip()
        if restart_name and restart_name != "no":
            args.extend(["--restart", restart_name])

        user = str(config.get("User") or "").strip()
        if user:
            args.extend(["--user", user])

        working_dir = str(config.get("WorkingDir") or "").strip()
        if working_dir:
            args.extend(["--workdir", working_dir])

        network_mode = str(host_config.get("NetworkMode") or "").strip()
        if network_mode and network_mode not in {"default", "bridge"}:
            args.extend(["--network", network_mode])

        if host_config.get("Privileged"):
            args.append("--privileged")
        if host_config.get("ReadonlyRootfs"):
            args.append("--read-only")
        if host_config.get("AutoRemove"):
            args.append("--rm")

        for capability in host_config.get("CapAdd", []) or []:
            if capability:
                args.extend(["--cap-add", str(capability)])
        for capability in host_config.get("CapDrop", []) or []:
            if capability:
                args.extend(["--cap-drop", str(capability)])
        for dns_server in host_config.get("Dns", []) or []:
            if dns_server:
                args.extend(["--dns", str(dns_server)])
        for extra_host in host_config.get("ExtraHosts", []) or []:
            if extra_host:
                args.extend(["--add-host", str(extra_host)])

        for device in host_config.get("Devices", []) or []:
            if not isinstance(device, dict):
                continue
            host_path = str(device.get("PathOnHost") or "").strip()
            container_path = str(device.get("PathInContainer") or "").strip()
            permissions = str(device.get("CgroupPermissions") or "").strip()
            if host_path and container_path:
                value = f"{host_path}:{container_path}"
                if permissions:
                    value += f":{permissions}"
                args.extend(["--device", value])

        memory_limit = int(host_config.get("Memory") or 0)
        if memory_limit > 0:
            args.extend(["--memory", str(memory_limit)])
        nano_cpus = int(host_config.get("NanoCpus") or 0)
        if nano_cpus > 0:
            args.extend(["--cpus", f"{nano_cpus / 1_000_000_000:g}"])
        shm_size = int(host_config.get("ShmSize") or 0)
        if shm_size and shm_size != 64 * 1024 * 1024:
            args.extend(["--shm-size", str(shm_size)])

        for key, value in sorted((config.get("Labels") or {}).items()):
            if key:
                args.extend(["--label", f"{key}={value}"])

        for env in config.get("Env", []) or []:
            if env:
                args.extend(["-e", env])

        for mount in attrs.get("Mounts", []) or []:
            mount_type = str(mount.get("Type") or "").strip().lower()
            if mount_type == "tmpfs":
                continue
            if mount_type == "volume":
                source = (mount.get("Name") or mount.get("Source") or "").strip()
            else:
                source = (mount.get("Source") or "").strip()
            destination = (mount.get("Destination") or "").strip()
            if not source or not destination:
                continue
            mode = (mount.get("Mode") or "").strip()
            suffix = f":{mode}" if mode else (":ro" if mount.get("RW") is False else "")
            args.extend(["-v", f"{source}:{destination}{suffix}"])

        for destination, options in sorted((host_config.get("Tmpfs") or {}).items()):
            value = str(destination)
            if options:
                value += f":{options}"
            args.extend(["--tmpfs", value])

        ports = attrs.get("NetworkSettings", {}).get("Ports", {}) or {}
        for cont_port, mappings in sorted(ports.items()):
            container_port = str(cont_port).split("/")[0]
            for mapping in mappings or []:
                host_port = (mapping.get("HostPort") or "").strip()
                if not host_port:
                    continue
                host_ip = (mapping.get("HostIp") or "").strip()
                publish_value = f"{host_port}:{container_port}"
                if host_ip and host_ip not in {"0.0.0.0", "::"}:
                    publish_value = f"{host_ip}:{publish_value}"
                args.extend(["-p", publish_value])

        entrypoint = config.get("Entrypoint") or []
        if isinstance(entrypoint, str):
            entrypoint_parts = shlex.split(entrypoint)
        else:
            entrypoint_parts = [str(part) for part in entrypoint if str(part)]
        if entrypoint_parts:
            args.extend(["--entrypoint", entrypoint_parts[0]])

        image = (config.get("Image") or attrs.get("Image") or "").strip()
        if image:
            args.append(image)

        cmd = config.get("Cmd") or []
        if len(entrypoint_parts) > 1:
            args.extend(entrypoint_parts[1:])
        if isinstance(cmd, str):
            args.extend(shlex.split(cmd))
        else:
            args.extend(cmd)
        return args

    def recreate_container_with_args(self, original_name: str, args: List[str], auto_fix: bool = True, allow_ai: bool = False):
        reply = QMessageBox.question(
            self,
            self.texts["wizard_recreate_title"],
            self.texts["wizard_recreate_confirm"],
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return False
        try:
            backup_args = self.container_run_args(self.client.containers.get(original_name))
        except Exception:
            backup_args = []
        dialog = CommandProgressDialog(
            self.texts["progress_title_recreate"],
            self.texts["progress_status_recreate"],
            lambda payload, emit_line: self.recreate_container_with_args_stream(payload, emit_line, backup_args, auto_fix=auto_fix, allow_ai=allow_ai),
            [original_name] + list(args),
            self.texts,
            self,
        )
        dialog.exec()
        return dialog.success is True

    def selected_container_name_for_edit(self) -> str:
        names = self.get_selected_names()
        if names:
            return names[0]
        row = self.table.currentRow()
        if row >= 0:
            item = self.table.item(row, 2)
            if item:
                return item.text()
        return ""

    def recreate_container_with_args_stream(self, payload: List[str], emit_line, backup_args: Optional[List[str]] = None, auto_fix: bool = True, allow_ai: bool = False):
        if not payload:
            return None
        original_name = payload[0]
        args = payload[1:]
        emit_line(f"docker rm -f {original_name}")
        self.client.containers.get(original_name).remove(force=True)
        try:
            return self.run_container_with_repair_stream(args, emit_line, ignore_name=original_name, auto_fix=auto_fix, allow_ai=allow_ai)
        except Exception as exc:
            if backup_args:
                emit_line("New configuration failed. Restoring the previous container configuration...")
                try:
                    self.cleanup_failed_container(args, emit_line)
                    self.run_backend_docker_command_stream(list(backup_args), emit_line)
                    emit_line("Previous container configuration restored.")
                except Exception as rollback_exc:
                    raise RuntimeError(f"{exc}\nRollback also failed: {rollback_exc}") from exc
            raise
    def manage_profiles(self):
        dialog = ProfileManagerDialog(self.remote_profiles, self.texts, self)
        dialog.exec()
        self.remote_profiles = dialog.profiles
        self.profile_store.save(self.remote_profiles)
        self.reload_profiles_ui()

    def import_profiles_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.texts["profiles_import_title"],
            "",
            self.texts["profiles_portable_filter"],
        )
        if not path:
            return
        try:
            imported = import_connection_profiles(Path(path))
            self.remote_profiles = merge_imported_profiles(self.remote_profiles, imported)
            self.profile_store.save(self.remote_profiles)
            self.reload_profiles_ui()
            missing_keys = sum(1 for profile in imported if profile_needs_ssh_key_path(profile))
            message = self.texts["profiles_import_done"].format(count=len(imported))
            if missing_keys:
                message += "\n\n" + self.texts["profiles_import_key_paths"].format(count=missing_keys)
            QMessageBox.information(
                self,
                self.texts["msg_info"],
                message,
            )
        except Exception:
            QMessageBox.warning(self, self.texts["msg_error"], self.texts["profiles_import_invalid"])

    def export_profiles_to_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.texts["profiles_export_title"],
            "DockerControlCenter-profiles.json",
            self.texts["profiles_portable_filter"],
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            count = export_connection_profiles(Path(path), self.remote_profiles)
            QMessageBox.information(
                self,
                self.texts["msg_info"],
                self.texts["profiles_export_done"].format(count=count),
            )
        except Exception as exc:
            QMessageBox.warning(self, self.texts["msg_error"], str(exc))

    def build_docker_client(self, profile: RemoteProfile):
        if profile.mode == "ssh":
            return SshDockerClient(profile, timeout=DOCKER_HTTP_TIMEOUT)
        return docker.DockerClient(base_url=profile.resolved_base_url(), timeout=DOCKER_HTTP_TIMEOUT)

    def _run_subprocess_stream(self, command: List[str], emit_line):
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=CREATE_NO_WINDOW,
        )
        collected = []
        if process.stdout is not None:
            for line in process.stdout:
                clean = line.rstrip()
                if clean:
                    collected.append(clean)
                    emit_line(clean)
        code = process.wait()
        output = "\n".join(collected)
        if code != 0:
            raise RuntimeError(output or "docker command failed")
        return subprocess.CompletedProcess(command, code, output, "")

    def remote_engine_label(self) -> str:
        if isinstance(self.client, SshDockerClient):
            cli = getattr(self.client, "detected_cli", "")
            if cli == "balena":
                return self.texts["engine_balena"]
            if cli == "docker":
                return self.texts["engine_docker"]
        return self.texts["engine_unknown"]

    def get_remote_cli_command(self) -> str:
        if isinstance(self.client, SshDockerClient):
            cli = getattr(self.client, "detected_cli", "")
            if cli:
                return f"sudo -n {cli}" if getattr(self.client, "use_sudo", False) else cli
        return "docker"

    def wizard_cli_settings(self) -> tuple[str, List[str]]:
        cli = "docker"
        choices = ["docker"]
        if self.current_backend == "remote" and isinstance(self.client, SshDockerClient):
            detected = getattr(self.client, "detected_cli", "")
            if detected == "balena":
                cli = "balena"
                choices = ["balena"]
            elif detected == "docker":
                cli = "docker"
                choices = ["docker"]
        elif self.current_backend == "wsl" and isinstance(self.client, WslDockerClient):
            detected = getattr(self.client, "detected_cli", "")
            if detected == "balena":
                cli = "balena"
                choices = ["balena"]
            elif detected == "docker":
                cli = "docker"
                choices = ["docker"]
        return cli, choices

    def deployment_target_label(self) -> str:
        if self.current_backend == "remote" and self.active_remote_profile:
            system = self.remote_os_name or "remote"
            return f"{self.active_remote_profile.name} · {system}"
        if self.current_backend == "wsl" and self.current_wsl_distro:
            return f"WSL · {self.current_wsl_distro}"
        if self.current_backend == "local":
            return f"Local · {detect_local_os_name()}"
        return self.current_backend or "Docker"

    def run_backend_docker_command_stream(self, args: List[str], emit_line):
        if not args:
            return None
        if self.current_backend == "wsl" and self.current_wsl_distro:
            cli = self.backend_cli_command()
            command = ["wsl.exe", "-d", self.current_wsl_distro, "sh", "-lc", f"{cli} " + " ".join(shlex.quote(str(arg)) for arg in args)]
            return self._run_subprocess_stream(command, emit_line)
        if self.current_backend == "remote" and self.active_remote_profile:
            if self.active_remote_profile.mode == "tunnel":
                command = ["docker", "--host", self.active_remote_profile.resolved_base_url()] + args
                return self._run_subprocess_stream(command, emit_line)
            if paramiko is None:
                raise RuntimeError("Missing paramiko package for SSH support.")
            cli = self.get_remote_cli_command()
            command = cli + " " + " ".join(shlex.quote(str(arg)) for arg in args)
            ssh_client = self.client._ensure_client() if hasattr(self.client, "_ensure_client") else None
            if ssh_client is None:
                raise RuntimeError("SSH client is not available.")
            stdin, stdout, stderr = ssh_client.exec_command(command, timeout=DOCKER_HTTP_TIMEOUT)
            channel = stdout.channel
            collected = []
            detached_run = bool(
                args
                and str(args[0]).lower() == "run"
                and any(str(part).lower() in {"-d", "--detach"} for part in args[1:])
            )
            detached_id = ""
            detached_seen_at = 0.0
            last_activity = time.monotonic()
            detached_scan_buffer = ""
            while True:
                made_progress = False
                if channel.recv_ready():
                    chunk = channel.recv(4096).decode("utf-8", errors="ignore")
                    detached_scan_buffer = (detached_scan_buffer + chunk)[-8192:]
                    for line in chunk.splitlines():
                        clean = line.rstrip()
                        if clean:
                            collected.append(clean)
                            emit_line(clean)
                    if detached_run and not detached_id:
                        matches = re.findall(r"(?<![0-9a-fA-F])([0-9a-fA-F]{64})(?![0-9a-fA-F])", detached_scan_buffer)
                        if matches:
                            detached_id = matches[-1].lower()
                            detached_seen_at = time.monotonic()
                    made_progress = True
                if channel.recv_stderr_ready():
                    chunk = channel.recv_stderr(4096).decode("utf-8", errors="ignore")
                    for line in chunk.splitlines():
                        clean = line.rstrip()
                        if clean:
                            collected.append(clean)
                            emit_line(clean)
                    made_progress = True
                if made_progress:
                    last_activity = time.monotonic()
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                    break
                if (
                    detached_id
                    and detached_seen_at
                    and time.monotonic() - detached_seen_at >= 2.0
                    and time.monotonic() - last_activity >= 1.0
                ):
                    verify_command = f"{cli} inspect --format '{{{{.State.Status}}}}' {shlex.quote(detached_id)}"
                    try:
                        _verify_stdin, verify_stdout, verify_stderr = ssh_client.exec_command(
                            verify_command,
                            timeout=min(DOCKER_HTTP_TIMEOUT, 6),
                        )
                        verify_output = verify_stdout.read().decode("utf-8", errors="ignore").strip()
                        verify_error = verify_stderr.read().decode("utf-8", errors="ignore").strip()
                        verify_code = verify_stdout.channel.recv_exit_status()
                        if verify_code == 0 and verify_output:
                            emit_line(self.texts["progress_ssh_verified"].format(id=detached_id[:12]))
                            try:
                                channel.close()
                            except Exception:
                                pass
                            return subprocess.CompletedProcess(command, 0, "\n".join(collected), verify_error)
                    except Exception:
                        pass
                    detached_seen_at = time.monotonic()
                if not made_progress:
                    time.sleep(0.05)
            code = channel.recv_exit_status()
            output = "\n".join(collected)
            if code != 0:
                raise RuntimeError(output or "docker command failed over SSH")
            return subprocess.CompletedProcess(command, code, output, "")
        command = ["docker"] + args
        return self._run_subprocess_stream(command, emit_line)

    def run_backend_docker_command(self, args: List[str]):
        return self.run_backend_docker_command_stream(args, lambda _line: None)

    def current_port_usage(self, ignore_name: str = "") -> Dict[str, List[str]]:
        usage: Dict[str, List[str]] = {}
        for container in self.client.containers.list(all=True):
            if ignore_name and getattr(container, "name", "") == ignore_name:
                continue
            attrs = getattr(container, "attrs", {}) or {}
            ports = (attrs.get("NetworkSettings", {}) or {}).get("Ports", {}) or {}
            for cont_port, mappings in ports.items():
                for mapping in mappings or []:
                    host_port = str(mapping.get("HostPort") or "").strip()
                    if host_port:
                        usage.setdefault(host_port, []).append(f"{getattr(container, 'name', '?')}({cont_port})")
        return usage

    def container_runtime_context(self, ignore_name: str = "") -> str:
        lines = []
        try:
            containers = self.client.containers.list(all=True)
        except Exception as exc:
            return f"Could not inspect containers: {exc}"
        for container in containers:
            attrs = getattr(container, "attrs", {}) or {}
            config = attrs.get("Config", {}) or {}
            image_name = str(config.get("Image") or attrs.get("Image") or "?")
            ports = []
            for cont_port, mappings in ((attrs.get("NetworkSettings", {}) or {}).get("Ports", {}) or {}).items():
                for mapping in mappings or []:
                    host_port = str(mapping.get("HostPort") or "").strip()
                    if host_port:
                        ports.append(f"{host_port}->{cont_port}")
            marker = " [ignore while editing]" if ignore_name and getattr(container, "name", "") == ignore_name else ""
            lines.append(
                f"- {getattr(container, 'name', '?')}{marker}: image={image_name}, "
                f"status={getattr(container, 'status', '?')}, ports={', '.join(ports) or 'none'}"
            )
        used_ports = self.current_port_usage(ignore_name)
        port_text = ", ".join(f"{port} ({'/'.join(users)})" for port, users in sorted(used_ports.items()))
        return (
            f"Backend={self.current_backend}; CLI={self.backend_cli_command()}; "
            f"architecture={self.remote_arch or platform.machine() or 'unknown'}\n"
            f"Occupied published host ports: {port_text or 'none'}\n"
            "Containers:\n" + ("\n".join(lines) if lines else "- none")
        )

    def validate_run_ports(self, args: List[str], ignore_name: str = ""):
        usage = self.current_port_usage(ignore_name)
        conflicts = []
        for port in published_host_ports(args):
            if port in usage:
                conflicts.append(f"{port} -> {', '.join(usage[port])}")
        if conflicts:
            raise RuntimeError("Host port conflict: " + "; ".join(conflicts))

    def cleanup_failed_container(self, args: List[str], emit_line, protected_names: Optional[set[str]] = None):
        name = ""
        for index, token in enumerate(args):
            token = str(token)
            if token == "--name" and index + 1 < len(args):
                name = str(args[index + 1]).strip()
                break
            if token.startswith("--name="):
                name = token.split("=", 1)[1].strip()
                break
        if not name:
            return
        if name in (protected_names or set()):
            emit_line(f"Keeping pre-existing container untouched: {name}")
            return
        try:
            container = self.client.containers.get(name)
            emit_line(f"Cleaning failed container: {name}")
            container.remove(force=True)
        except Exception:
            pass

    def verify_deployed_container(self, args: List[str], emit_line):
        name = ""
        for index, token in enumerate(args):
            token = str(token)
            if token == "--name" and index + 1 < len(args):
                name = str(args[index + 1]).strip()
                break
            if token.startswith("--name="):
                name = token.split("=", 1)[1].strip()
                break
        if not name:
            return
        emit_line(self.texts["progress_verify_start"])
        last_error = ""
        for _attempt in range(5):
            try:
                container = self.client.containers.get(name)
                try:
                    container.reload()
                except Exception:
                    pass
                status = str(getattr(container, "status", "") or "").strip()
                if not status:
                    attrs = getattr(container, "attrs", {}) or {}
                    status = str((attrs.get("State", {}) or {}).get("Status") or "created")
                emit_line(self.texts["progress_verify_found"].format(name=name, status=status))
                return
            except Exception as exc:
                last_error = str(exc)
                time.sleep(0.35)
        detail = self.texts["progress_verify_missing"].format(name=name)
        if last_error:
            detail += f" ({last_error})"
        raise RuntimeError(detail)

    def repair_run_args_with_ai(self, args: List[str], error_text: str, ignore_name: str, emit_line) -> List[str]:
        settings = self.get_llm_settings()
        provider = str(settings.get("provider") or "ollama").strip().lower()
        if provider not in LLM_PROVIDER_ORDER:
            provider = "ollama"
        model = llm_selected_model(settings, provider)
        cli = self.backend_cli_command()
        current_command = cli + " " + " ".join(shlex.quote(str(part)) for part in args)
        context = self.container_runtime_context(ignore_name)
        prompt = (
            "The container installation failed. Diagnose the real cause and return a corrected run command. "
            "Keep all unrelated configuration. Resolve port conflicts using a free host port when needed. "
            "If the image/options are incompatible with this engine or architecture, correct them without changing the intended service.\n"
            f"Execution error:\n{error_text}"
        )
        emit_line(f"AI diagnostics ({provider}/{model})...")
        repaired = self.generate_ai_docker_command(
            provider=provider,
            model=model,
            prompt=prompt,
            current_command=current_command,
            edit_mode=bool(ignore_name),
            runtime_context=context,
        )
        repaired = normalize_docker_command_text(extract_docker_run_command(repaired))
        _cli, repaired_args = parse_run_command_text(repaired)
        if not repaired_args or repaired_args == args:
            raise RuntimeError("AI did not produce a different valid container command.")
        emit_line("AI proposed corrected command:")
        emit_line(repaired)
        return repaired_args

    def run_container_with_repair_stream(self, args: List[str], emit_line, ignore_name: str = "", max_attempts: int = 3, auto_fix: bool = True, allow_ai: bool = False):
        current_args = list(args)
        last_error = ""
        for attempt in range(1, max_attempts + 1):
            try:
                protected_names = {
                    str(getattr(container, "name", "") or "").lstrip("/")
                    for container in self.client.containers.list(all=True)
                    if str(getattr(container, "name", "") or "").strip()
                }
            except Exception:
                protected_names = set()
            try:
                self.validate_run_ports(current_args, ignore_name)
                cli = self.backend_cli_command()
                emit_line(f"Attempt {attempt}/{max_attempts}: {cli} " + " ".join(shlex.quote(str(part)) for part in current_args))
                result = self.run_backend_docker_command_stream(current_args, emit_line)
                self.verify_deployed_container(current_args, emit_line)
                return result
            except Exception as exc:
                last_error = str(exc)
                emit_line(f"Attempt {attempt} failed: {last_error}")
                if attempt >= max_attempts:
                    raise RuntimeError(last_error) from exc
                self.cleanup_failed_container(current_args, emit_line, protected_names=protected_names)
                if auto_fix:
                    try:
                        usage = self.current_port_usage(ignore_name)
                        if re.search(r"port is already allocated|address already in use|bind.*failed", last_error, re.IGNORECASE):
                            for port in published_host_ports(current_args):
                                usage.setdefault(port, ["host listener / runtime conflict"])
                        names = [getattr(container, "name", "") for container in self.client.containers.list(all=True)]
                        repaired_args, changes = safe_repair_run_args(current_args, usage, names, ignore_name)
                        if changes and repaired_args != current_args:
                            for kind, old, new in changes:
                                emit_line(f"Safe repair: {kind} {old} -> {new}")
                            current_args = repaired_args
                            continue
                    except Exception as deterministic_exc:
                        emit_line(f"Deterministic repair could not continue: {deterministic_exc}")
                if allow_ai:
                    try:
                        current_args = self.repair_run_args_with_ai(current_args, last_error, ignore_name, emit_line)
                        continue
                    except Exception as repair_exc:
                        raise RuntimeError(f"{last_error}\nAutomatic AI repair failed: {repair_exc}") from exc
                raise RuntimeError(last_error) from exc
        raise RuntimeError(last_error or "Container installation failed.")

    def execute_backend_command_with_progress(self, args: List[str], title: str, status_text: str) -> bool:
        dialog = CommandProgressDialog(title, status_text, self.run_backend_docker_command_stream, args, self.texts, self)
        dialog.exec()
        return dialog.success is True

    def build_catalog_image_with_progress(self, template: ImageTemplate) -> bool:
        context = str(template.build_context or "").strip()
        image = str(template.image or "").strip()
        if not context or not image:
            return True
        args = ["build", "-t", image]
        dockerfile = str(template.build_dockerfile or "").strip()
        if dockerfile:
            args.extend(["-f", dockerfile])
        args.append(context)
        return self.execute_backend_command_with_progress(
            args,
            self.texts["progress_title_create"],
            self.texts["progress_status_build_source"].format(name=template.name),
        )

    def execute_smart_container_command_with_progress(self, args: List[str], title: str, status_text: str, auto_fix: bool = True, allow_ai: bool = False) -> bool:
        worker = lambda payload, emit_line: self.run_container_with_repair_stream(payload, emit_line, auto_fix=auto_fix, allow_ai=allow_ai)
        dialog = CommandProgressDialog(title, status_text, worker, args, self.texts, self)
        dialog.exec()
        return dialog.success is True

    def is_local_docker_available(self) -> bool:
        try:
            local_client = self.build_local_docker_client()
            local_client.ping()
            return True
        except Exception:
            return False

    def docker_desktop_path(self) -> Optional[Path]:
        if os.name != "nt":
            return None
        candidates = [
            Path(os.getenv("ProgramFiles", "C:/Program Files")) / "Docker/Docker/Docker Desktop.exe",
            Path(os.getenv("LocalAppData", "")) / "Programs/Docker/Docker/Docker Desktop.exe",
        ]
        for candidate in candidates:
            try:
                if candidate and candidate.is_file():
                    return candidate
            except Exception:
                continue
        return None

    def windows_docker_desktop_installed(self) -> bool:
        return self.docker_desktop_path() is not None

    def windows_docker_auto_install_supported(self) -> bool:
        return os.name == "nt" and bool(shutil.which("winget"))

    def linux_docker_desktop_path(self) -> Optional[Path]:
        if os.name == "nt":
            return None
        detected = shutil.which("docker-desktop")
        candidates = []
        if detected:
            candidates.append(Path(detected))
        candidates.extend(
            [
                Path("/opt/docker-desktop/bin/docker-desktop"),
                Path.home() / ".local/bin/docker-desktop",
            ]
        )
        for candidate in candidates:
            try:
                if candidate.is_file():
                    return candidate
            except Exception:
                continue
        return None

    def linux_docker_desktop_installed(self) -> bool:
        if os.name == "nt":
            return False
        if self.linux_docker_desktop_path() is not None:
            return True
        for marker in (
            Path("/usr/share/applications/docker-desktop.desktop"),
            Path("/opt/docker-desktop"),
        ):
            try:
                if marker.exists():
                    return True
            except Exception:
                pass
        dpkg_query = shutil.which("dpkg-query")
        if dpkg_query:
            try:
                result = subprocess.run(
                    [dpkg_query, "-W", "-f=${Status}", "docker-desktop"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                    creationflags=CREATE_NO_WINDOW,
                )
                return result.returncode == 0 and "install ok installed" in (result.stdout or "").lower()
            except Exception:
                pass
        return False

    def linux_docker_desktop_selected(self) -> bool:
        if os.name == "nt":
            return False
        try:
            endpoint, context_name = self._linux_docker_endpoint_info()
        except Exception:
            return False
        endpoint = endpoint.lower()
        context_name = context_name.lower()
        return "desktop" in context_name or "/.docker/desktop/" in endpoint or "docker-cli.sock" in endpoint

    def linux_docker_desktop_running(self) -> bool:
        if os.name == "nt" or not self.linux_docker_desktop_installed():
            return False
        if self.linux_docker_desktop_selected() and self.is_local_docker_available():
            return True
        systemctl = shutil.which("systemctl")
        if systemctl:
            try:
                result = subprocess.run(
                    [systemctl, "--user", "is-active", "--quiet", "docker-desktop"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                    creationflags=CREATE_NO_WINDOW,
                )
                if result.returncode == 0:
                    return True
            except Exception:
                pass
        return False

    def open_linux_docker_desktop_install_page(self) -> bool:
        if os.name == "nt":
            return False
        try:
            return bool(webbrowser.open("https://docs.docker.com/desktop/setup/install/linux/"))
        except Exception:
            return False

    def _ssh_program_path(self, program: str) -> Optional[str]:
        detected = shutil.which(program)
        if detected:
            return detected
        if os.name != "nt":
            return None
        windows_dir = Path(os.getenv("WINDIR", "C:/Windows"))
        for base in (windows_dir / "System32/OpenSSH", windows_dir / "Sysnative/OpenSSH"):
            candidate = base / program
            if candidate.suffix.lower() != ".exe":
                candidate = candidate.with_suffix(".exe")
            try:
                if candidate.is_file():
                    return str(candidate)
            except Exception:
                continue
        return None

    def is_ssh_client_available(self) -> bool:
        return bool(self._ssh_program_path("ssh"))

    def is_ssh_agent_available(self) -> bool:
        return bool(self._ssh_program_path("ssh-agent"))

    def ssh_tools_auto_install_supported(self) -> bool:
        if os.name == "nt":
            return bool(shutil.which("powershell") or shutil.which("powershell.exe"))
        return bool(shutil.which("apt-get")) and bool(shutil.which("pkexec"))

    def linux_docker_auto_install_supported(self) -> bool:
        return os.name != "nt" and bool(shutil.which("apt-get")) and bool(shutil.which("pkexec"))

    def linux_docker_group_setup_supported(self) -> bool:
        if os.name == "nt" or not shutil.which("pkexec"):
            return False
        return bool(shutil.which("usermod") or Path("/usr/sbin/usermod").is_file())

    def linux_target_username(self) -> str:
        """Return the real desktop user that should receive Docker permissions."""
        if os.name == "nt":
            return getpass.getuser().strip()

        sudo_user = os.getenv("SUDO_USER", "").strip()
        if sudo_user and sudo_user != "root":
            return sudo_user

        pkexec_uid = os.getenv("PKEXEC_UID", "").strip()
        if pkexec_uid.isdigit():
            try:
                import pwd

                username = pwd.getpwuid(int(pkexec_uid)).pw_name.strip()
                if username and username != "root":
                    return username
            except Exception:
                pass

        candidates = [
            getpass.getuser().strip(),
            os.getenv("USER", "").strip(),
            os.getenv("LOGNAME", "").strip(),
        ]
        for username in candidates:
            if username and username != "root":
                return username

        try:
            import pwd

            username = pwd.getpwuid(os.getuid()).pw_name.strip()
            if username and username != "root":
                return username
        except Exception:
            pass
        return ""

    def _linux_docker_endpoint_info(self, refresh: bool = False) -> tuple[str, str]:
        """Resolve the Docker endpoint exactly like the Linux Docker CLI context."""
        if os.name == "nt":
            return "", ""

        cached = getattr(self, "_linux_docker_endpoint_cache", None)
        now = time.monotonic()
        if not refresh and cached and now - cached[0] < 2.0:
            return cached[1], cached[2]

        endpoint = os.getenv("DOCKER_HOST", "").strip()
        source = "DOCKER_HOST" if endpoint else ""
        docker_cli = shutil.which("docker")
        if not endpoint and docker_cli:
            try:
                context_result = subprocess.run(
                    [docker_cli, "context", "show"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                    creationflags=CREATE_NO_WINDOW,
                )
                context_name = context_result.stdout.strip() if context_result.returncode == 0 else ""
                if context_name:
                    inspect_result = subprocess.run(
                        [docker_cli, "context", "inspect", context_name],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=False,
                        creationflags=CREATE_NO_WINDOW,
                    )
                    if inspect_result.returncode == 0:
                        payload = json.loads(inspect_result.stdout or "[]")
                        if isinstance(payload, list) and payload:
                            docker_endpoint = (payload[0].get("Endpoints") or {}).get("docker") or {}
                            endpoint = str(docker_endpoint.get("Host") or "").strip()
                            if endpoint:
                                source = context_name
            except Exception:
                pass

        if not endpoint:
            runtime_dir = os.getenv("XDG_RUNTIME_DIR", "").strip()
            candidates = []
            if runtime_dir:
                candidates.append((Path(runtime_dir) / "docker.sock", "rootless"))
            try:
                candidates.append((Path(f"/run/user/{os.getuid()}/docker.sock"), "rootless"))
            except Exception:
                pass
            candidates.extend(
                [
                    (Path.home() / ".docker/desktop/docker-cli.sock", "desktop-linux"),
                    (Path("/var/run/docker.sock"), "default"),
                    (Path("/run/docker.sock"), "default"),
                ]
            )
            for socket_path, socket_source in candidates:
                try:
                    if socket_path.exists():
                        endpoint = f"unix://{socket_path}"
                        source = socket_source
                        break
                except Exception:
                    continue

        if not endpoint:
            endpoint = "unix:///var/run/docker.sock"
            source = "default"

        self._linux_docker_endpoint_cache = (now, endpoint, source)
        return endpoint, source

    def linux_docker_endpoint(self, refresh: bool = False) -> str:
        return self._linux_docker_endpoint_info(refresh=refresh)[0]

    def linux_docker_uses_system_socket(self) -> bool:
        endpoint = self.linux_docker_endpoint().strip().lower()
        return endpoint in {
            "unix:///var/run/docker.sock",
            "unix://var/run/docker.sock",
            "unix:///run/docker.sock",
            "unix://run/docker.sock",
        }

    def _linux_user_groups(self, configured: bool = True) -> set[str]:
        if os.name == "nt":
            return set()
        id_program = shutil.which("id") or "/usr/bin/id"
        if not Path(id_program).is_file() and not shutil.which("id"):
            return set()
        command = [id_program, "-nG"]
        if configured:
            username = self.linux_target_username()
            if not username:
                return set()
            command.append(username)
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                creationflags=CREATE_NO_WINDOW,
            )
        except Exception:
            return set()
        if result.returncode != 0:
            return set()
        return {group.strip() for group in result.stdout.split() if group.strip()}

    def linux_docker_group_configured(self) -> bool:
        return "docker" in self._linux_user_groups(configured=True)

    def linux_docker_group_active(self) -> bool:
        return "docker" in self._linux_user_groups(configured=False)

    def linux_docker_group_requires_relaunch(self) -> bool:
        return (
            os.name != "nt"
            and self.linux_docker_uses_system_socket()
            and self.linux_docker_group_configured()
            and not self.linux_docker_group_active()
        )

    def linux_docker_group_relaunch_supported(self) -> bool:
        return self.linux_docker_group_requires_relaunch() and bool(shutil.which("sg"))

    def _linux_docker_group_relaunch_command(self) -> tuple[str, List[str], str]:
        sg_program = shutil.which("sg")
        if not sg_program:
            raise RuntimeError(self.texts["docker_group_restart_failed"])
        if getattr(sys, "frozen", False):
            app_command = [sys.executable, *sys.argv[1:]]
            working_directory = str(Path(sys.executable).resolve().parent)
        else:
            app_command = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]
            working_directory = str(Path(__file__).resolve().parent)
        return sg_program, ["docker", "-c", shlex.join(app_command)], working_directory

    def restart_with_linux_docker_group(self) -> bool:
        if not self.linux_docker_group_relaunch_supported():
            return False
        try:
            program, arguments, working_directory = self._linux_docker_group_relaunch_command()
            started, _pid = QProcess.startDetached(program, arguments, working_directory)
        except Exception:
            return False
        if not started:
            return False
        app = QApplication.instance()
        if app is not None:
            app.quit()
        return True

    def _run_linux_docker_group_setup_stream(self, _args: List[str], emit_line):
        if not self.linux_docker_group_setup_supported():
            raise RuntimeError(self.texts["docker_group_unsupported"])
        username = self.linux_target_username()
        if not username:
            raise RuntimeError("Could not determine the current user.")
        if self.linux_docker_group_configured():
            emit_line(self.texts["docker_group_already_member"])
            return subprocess.CompletedProcess([], 0, self.texts["docker_group_already_member"], "")
        pkexec = shutil.which("pkexec")
        usermod = shutil.which("usermod") or "/usr/sbin/usermod"
        if not pkexec or not Path(usermod).is_file():
            raise RuntimeError(self.texts["docker_group_unsupported"])
        emit_line(self.texts["docker_group_install_status"])
        quoted_user = shlex.quote(username)
        quoted_usermod = shlex.quote(usermod)
        script = "\n".join([
            "set -e",
            "getent group docker >/dev/null 2>&1 || groupadd docker",
            f"{quoted_usermod} -aG docker {quoted_user}",
        ])
        return self._run_subprocess_stream(
            [pkexec, "/bin/sh", "-c", script],
            emit_line,
        )

    def add_current_user_to_docker_group_with_progress(self) -> bool:
        if os.name == "nt":
            return False
        if self.linux_docker_group_configured():
            QMessageBox.information(self, self.texts["docker_group_auth_title"], self.texts["docker_group_already_member"])
            return False
        if not self.linux_docker_group_setup_supported():
            QMessageBox.warning(self, self.texts["msg_error"], self.texts["docker_group_unsupported"])
            return False
        QMessageBox.information(self, self.texts["docker_group_auth_title"], self.texts["docker_group_auth_info"])
        dialog = CommandProgressDialog(
            self.texts["docker_group_install_title"],
            self.texts["docker_group_install_status"],
            self._run_linux_docker_group_setup_stream,
            [],
            self.texts,
            self,
        )
        dialog.exec()
        return dialog.success is True

    def _run_windows_docker_desktop_install_stream(self, _args: List[str], emit_line):
        if os.name != "nt":
            raise RuntimeError("Docker Desktop automatic installation is available only on Windows.")
        winget = shutil.which("winget")
        if not winget:
            raise RuntimeError(self.texts["dependencies_docker_desktop_winget_missing"])
        emit_line(self.texts["dependencies_docker_desktop_install_status"])
        return self._run_subprocess_stream(
            [
                winget,
                "install",
                "--id",
                "Docker.DockerDesktop",
                "--exact",
                "--accept-source-agreements",
                "--accept-package-agreements",
            ],
            emit_line,
        )

    def install_windows_docker_desktop_with_progress(self) -> bool:
        if os.name != "nt":
            return False
        if not self.windows_docker_auto_install_supported():
            QMessageBox.information(
                self,
                self.texts["dependencies_title"],
                self.texts["dependencies_docker_desktop_winget_missing"],
            )
            webbrowser.open("https://docs.docker.com/desktop/setup/install/windows-install/")
            return False
        dialog = CommandProgressDialog(
            self.texts["dependencies_docker_desktop_install_title"],
            self.texts["dependencies_docker_desktop_install_status"],
            self._run_windows_docker_desktop_install_stream,
            [],
            self.texts,
            self,
        )
        dialog.exec()
        return dialog.success is True

    def _run_ssh_tools_install_stream(self, _args: List[str], emit_line):
        emit_line(self.texts["dependencies_ssh_install_status"])
        if os.name == "nt":
            powershell = shutil.which("powershell") or shutil.which("powershell.exe")
            if not powershell:
                raise RuntimeError(self.texts["dependencies_auto_unavailable"])
            elevated_command = (
                "Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0 | Out-Host; "
                "Set-Service -Name ssh-agent -StartupType Manual -ErrorAction SilentlyContinue; "
                "Start-Service -Name ssh-agent -ErrorAction SilentlyContinue"
            )
            script = (
                "$p = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru "
                "-ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-Command',"
                + repr(elevated_command)
                + "); exit $p.ExitCode"
            )
            return self._run_subprocess_stream(
                [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                emit_line,
            )

        apt_get = shutil.which("apt-get")
        pkexec = shutil.which("pkexec")
        if not apt_get or not pkexec:
            raise RuntimeError(self.texts["dependencies_auto_unavailable"])
        quoted_apt = shlex.quote(apt_get)
        script = "\n".join([
            "set -e",
            "export DEBIAN_FRONTEND=noninteractive",
            f"{quoted_apt} update",
            f"{quoted_apt} install -y openssh-client",
            "ssh -V 2>&1 || true",
            "ssh-agent -V >/dev/null 2>&1 || true",
        ])
        return self._run_subprocess_stream([pkexec, "/bin/sh", "-c", script], emit_line)

    def install_ssh_tools_with_progress(self) -> bool:
        if not self.ssh_tools_auto_install_supported():
            QMessageBox.warning(self, self.texts["msg_error"], self.texts["dependencies_auto_unavailable"])
            return False
        dialog = CommandProgressDialog(
            self.texts["dependencies_ssh_install_title"],
            self.texts["dependencies_ssh_install_status"],
            self._run_ssh_tools_install_stream,
            [],
            self.texts,
            self,
        )
        dialog.exec()
        return dialog.success is True

    def _run_linux_docker_install_stream(self, _args: List[str], emit_line):
        if os.name == "nt":
            raise RuntimeError("Automatic Docker installation is available only on Linux.")
        apt_get = shutil.which("apt-get")
        pkexec = shutil.which("pkexec")
        if not apt_get or not pkexec:
            raise RuntimeError(self.texts["first_run_docker_unsupported"])
        username = self.linux_target_username()
        if not username:
            raise RuntimeError("Could not determine the current user.")
        quoted_user = shlex.quote(username)
        quoted_apt = shlex.quote(apt_get)
        script = "\n".join([
            "set -e",
            "export DEBIAN_FRONTEND=noninteractive",
            f"{quoted_apt} update",
            f"{quoted_apt} install -y docker.io",
            "getent group docker >/dev/null 2>&1 || groupadd docker",
            f"usermod -aG docker {quoted_user}",
            "if command -v systemctl >/dev/null 2>&1; then systemctl enable docker >/dev/null 2>&1 || true; systemctl start docker >/dev/null 2>&1 || true; fi",
            "if ! docker info >/dev/null 2>&1 && command -v service >/dev/null 2>&1; then service docker start >/dev/null 2>&1 || true; fi",
            "docker --version",
        ])
        emit_line(self.texts["first_run_install_status"])
        return self._run_subprocess_stream([pkexec, "/bin/sh", "-c", script], emit_line)

    def install_linux_docker_with_progress(self) -> bool:
        if not self.linux_docker_auto_install_supported():
            QMessageBox.warning(self, self.texts["msg_error"], self.texts["first_run_docker_unsupported"])
            return False
        dialog = CommandProgressDialog(
            self.texts["first_run_install_title"],
            self.texts["first_run_install_status"],
            self._run_linux_docker_install_stream,
            [],
            self.texts,
            self,
        )
        dialog.exec()
        return dialog.success is True

    def try_start_docker_desktop(self) -> bool:
        if os.name == "nt":
            candidate = self.docker_desktop_path()
            if candidate is not None:
                try:
                    subprocess.Popen([str(candidate)])
                    return True
                except Exception:
                    pass
            try:
                subprocess.Popen("start \"\" \"docker-desktop:\"", shell=True, creationflags=CREATE_NO_WINDOW)
                return True
            except Exception:
                return False

        if not self.linux_docker_desktop_installed():
            return False
        systemctl = shutil.which("systemctl")
        if systemctl:
            try:
                result = subprocess.run(
                    [systemctl, "--user", "start", "docker-desktop"],
                    capture_output=True,
                    text=True,
                    timeout=12,
                    check=False,
                    creationflags=CREATE_NO_WINDOW,
                )
                if result.returncode == 0:
                    return True
            except Exception:
                pass
        candidate = self.linux_docker_desktop_path()
        if candidate is not None:
            try:
                subprocess.Popen(
                    [str(candidate)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return True
            except Exception:
                pass
        return False

    def reconnect_local_docker_after_desktop_start(self, attempt: int = 0):
        if self.is_local_docker_available():
            self.connect_local_docker()
            return
        if attempt >= 11:
            self.connect_local_docker()
            return
        self.statusBar().showMessage(self.texts["docker_desktop_starting"])
        QTimer.singleShot(1800, lambda: self.reconnect_local_docker_after_desktop_start(attempt + 1))

    def show_local_docker_unavailable(self, details: str = ""):
        self.update_infrastructure_ui(False)
        linux_group_pending = False
        linux_desktop_installed = False
        linux_desktop_selected = False
        if os.name != "nt" and shutil.which("docker"):
            linux_group_pending = self.linux_docker_group_requires_relaunch()
        if os.name != "nt":
            linux_desktop_installed = self.linux_docker_desktop_installed()
            linux_desktop_selected = self.linux_docker_desktop_selected()
        message = QMessageBox(self)
        message.setWindowTitle(self.texts["msg_error"])
        message.setIcon(QMessageBox.Icon.Critical)
        message.setText(
            self.texts["docker_group_relaunch_title"]
            if linux_group_pending
            else self.texts["docker_local_unavailable_title"]
        )
        info = (
            self.texts["docker_group_relaunch_hint"]
            if linux_group_pending
            else self.platform_text("docker_local_unavailable_hint")
        )
        if os.name != "nt" and not linux_group_pending:
            if linux_desktop_installed and linux_desktop_selected:
                info = self.texts["docker_desktop_linux_stopped"] + "\n\n" + info
            elif not linux_desktop_installed:
                info = self.texts["docker_desktop_linux_missing"] + "\n\n" + info
        if os.name != "nt" and not linux_group_pending:
            try:
                endpoint, context_name = self._linux_docker_endpoint_info(refresh=True)
                info += "\n\n" + self.texts["docker_local_endpoint_detected"].format(
                    context=context_name or "default",
                    endpoint=endpoint,
                )
            except Exception:
                pass
        if details and not linux_group_pending:
            info += f"\n\n{details}"
        message.setInformativeText(info)
        if self.current_backend == "local":
            primary_button = None
            primary_action = ""
            linux_engine_button = None
            if os.name == "nt":
                if self.windows_docker_desktop_installed():
                    primary_button = message.addButton(
                        self.texts["docker_local_open_desktop"], QMessageBox.ButtonRole.AcceptRole
                    )
                    primary_action = "start_windows"
                else:
                    primary_button = message.addButton(
                        self.texts["docker_local_install_desktop"], QMessageBox.ButtonRole.AcceptRole
                    )
                    primary_action = "install_windows"
            else:
                if linux_group_pending and self.linux_docker_group_relaunch_supported():
                    primary_button = message.addButton(
                        self.texts["docker_group_restart_app"], QMessageBox.ButtonRole.AcceptRole
                    )
                    primary_action = "restart_linux_group"
                elif linux_desktop_installed:
                    primary_button = message.addButton(
                        self.texts["docker_local_open_desktop"], QMessageBox.ButtonRole.AcceptRole
                    )
                    primary_action = "start_linux_desktop"
                else:
                    primary_button = message.addButton(
                        self.texts["docker_local_install_desktop"], QMessageBox.ButtonRole.AcceptRole
                    )
                    primary_action = "install_linux_desktop"
                    if not shutil.which("docker") and self.linux_docker_auto_install_supported():
                        linux_engine_button = message.addButton(
                            self.texts["dependencies_install_docker_engine"], QMessageBox.ButtonRole.ActionRole
                        )

            dependencies_button = message.addButton(
                self.texts["dependencies_open"], QMessageBox.ButtonRole.ActionRole
            )
            message.addButton(QMessageBox.StandardButton.Ok)
            message.exec()
            clicked = message.clickedButton()
            if clicked == dependencies_button:
                self.open_dependencies_dialog()
            elif linux_engine_button is not None and clicked == linux_engine_button:
                if self.install_linux_docker_with_progress():
                    QTimer.singleShot(1200, self.connect_local_docker)
            elif primary_button is not None and clicked == primary_button:
                if primary_action == "start_windows":
                    if not self.try_start_docker_desktop():
                        QMessageBox.warning(self, self.texts["msg_error"], self.texts["docker_local_open_failed"])
                    else:
                        QTimer.singleShot(1800, self.connect_local_docker)
                elif primary_action == "install_windows":
                    if self.install_windows_docker_desktop_with_progress():
                        self.try_start_docker_desktop()
                        QTimer.singleShot(2500, self.connect_local_docker)
                elif primary_action == "install_linux":
                    if self.install_linux_docker_with_progress():
                        QTimer.singleShot(1200, self.connect_local_docker)
                elif primary_action == "start_linux_desktop":
                    if not self.try_start_docker_desktop():
                        QMessageBox.warning(self, self.texts["msg_error"], self.texts["docker_local_open_failed"])
                    else:
                        self.statusBar().showMessage(self.texts["docker_desktop_starting"])
                        QTimer.singleShot(1800, self.reconnect_local_docker_after_desktop_start)
                elif primary_action == "install_linux_desktop":
                    opened = self.open_linux_docker_desktop_install_page()
                    QMessageBox.information(
                        self,
                        self.texts["msg_info"],
                        self.texts["docker_desktop_linux_install_opened"]
                        if opened
                        else self.texts["docker_desktop_linux_install_failed"],
                    )
                elif primary_action == "restart_linux_group":
                    if not self.restart_with_linux_docker_group():
                        QMessageBox.warning(
                            self,
                            self.texts["msg_error"],
                            self.texts["docker_group_restart_failed"],
                        )
            return
        message.addButton(QMessageBox.StandardButton.Ok)
        message.exec()

    def connect_local_docker(self):
        self.current_backend = "local"
        self.current_wsl_distro = ""
        self.active_remote_profile = None
        if os.name != "nt" and shutil.which("docker") and self.linux_docker_group_requires_relaunch():
            self.client = None
            self.update_infrastructure_ui(False)
            self.show_local_docker_unavailable()
            return
        try:
            self.client = self.build_local_docker_client()
            self.client.ping()
            self.remote_arch = ""
            self.remote_os_name = ""
            self.remote_sysinfo_label.setText(self.texts["remote_sysinfo_unknown"])
            self.statusBar().showMessage(self.texts["status_local_connected"])
            self.update_infrastructure_ui(True)
            self.refresh_containers()
        except Exception as exc:
            self.client = None
            self.update_infrastructure_ui(False)
            self.show_local_docker_unavailable(str(exc))

    def connect_remote_docker(self, profile: Optional[RemoteProfile] = None, restart_mode: bool = False, timeout: Optional[int] = None):
        profile = profile or self.selected_profile()
        if not profile:
            if not restart_mode:
                QMessageBox.warning(self, self.texts["msg_error"], self.texts["profile_no_profiles"])
            return
        if self.remote_connect_thread is not None and self.remote_connect_thread.isRunning():
            return

        self.connecting_profile = profile
        self.connecting_restart_mode = bool(restart_mode)
        if restart_mode:
            message = self.texts["host_restart_checking"].format(name=profile.name, attempt=max(1, self.restart_watch_attempt))
        else:
            message = self.texts["profile_connecting"].format(name=profile.name)
        self.statusBar().showMessage(message)
        if hasattr(self, "btn_start_profile"):
            self.btn_start_profile.setEnabled(False)

        self.remote_connect_thread = QThread(self)
        self.remote_connect_worker = RemoteConnectWorker(profile, timeout=timeout or (5 if restart_mode else 12))
        self.remote_connect_worker.moveToThread(self.remote_connect_thread)
        self.remote_connect_thread.started.connect(self.remote_connect_worker.run)
        self.remote_connect_worker.finished.connect(self.on_remote_connect_finished)
        self.remote_connect_worker.finished.connect(self.remote_connect_thread.quit)
        self.remote_connect_worker.finished.connect(self.remote_connect_worker.deleteLater)

        def connection_thread_finished():
            if self.remote_connect_thread is not None:
                self.remote_connect_thread.deleteLater()
            self.remote_connect_thread = None
            self.remote_connect_worker = None
            if hasattr(self, "btn_start_profile"):
                self.btn_start_profile.setEnabled(True)

        self.remote_connect_thread.finished.connect(connection_thread_finished)
        self.remote_connect_thread.start()

    def on_remote_connect_finished(self, client, error_message: str, os_name: str, arch: str):
        profile = self.connecting_profile
        restart_mode = bool(self.connecting_restart_mode)
        if profile is None:
            return

        # The user may cancel automatic restart recovery while an SSH attempt is
        # already in flight. Ignore that late result instead of reconnecting or
        # showing an error after cancellation.
        if restart_mode and not self.restart_watch_active:
            self.close_client_safely(client)
            return

        if error_message or client is None:
            if restart_mode and self.restart_watch_active:
                waiting = self.texts["host_restart_waiting_retry"]
                self.statusBar().showMessage(waiting)
                self.set_infrastructure_activity(waiting)
                self.update_restart_notification(waiting)
                if not self.restart_watch_timer.isActive():
                    self.restart_watch_timer.start()
            else:
                QMessageBox.critical(self, self.texts["msg_error"], error_message or self.texts["profile_no_profiles"])
            return

        old_client = self.client
        if old_client is not None and old_client is not client:
            self.close_client_safely(old_client)
        self.client = client
        self.current_backend = "remote"
        self.current_wsl_distro = ""
        self.active_remote_profile = profile
        self.remote_os_name = os_name
        self.remote_arch = arch
        if os_name or arch:
            self.remote_sysinfo_label.setText(self.texts["remote_sysinfo_label"].format(os=os_name or "Linux", arch=arch or "?"))
        else:
            self.remote_sysinfo_label.setText(self.texts["remote_sysinfo_fetch_failed"])
        self.update_infrastructure_ui(True)

        if restart_mode and self.restart_watch_active:
            self.restart_watch_timer.stop()
            self.restart_recovery_pending_refresh = True
            ready = self.texts["host_restart_engine_ready"]
            self.statusBar().showMessage(ready)
            self.set_infrastructure_activity(ready)
            self.update_restart_notification(ready)
            self.refresh_containers()
            return

        self.statusBar().showMessage(self.texts["profile_connected"].format(name=profile.name) + " - " + self.remote_engine_label())
        self.refresh_containers()

    def start_hidden_tunnel(self, profile: RemoteProfile):
        if self.tunnel_process and self.tunnel_process.poll() is None:
            return
        if not profile.tunnel_command.strip():
            raise RuntimeError("Brak komendy tunelu dla tego profilu.")
        self.tunnel_process = subprocess.Popen(profile.tunnel_command, cwd=str(PROFILE_FILE.parent), creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)

    def start_profile_connection(self):
        profile = self.selected_profile()
        if not profile:
            QMessageBox.warning(self, self.texts["msg_error"], self.texts["profile_no_profiles"])
            return
        self.statusBar().showMessage(self.texts["profile_starting"].format(name=profile.name))
        try:
            same_restart_profile = bool(
                self.restart_watch_active
                and self.restart_watch_profile is not None
                and self.restart_watch_profile.name == profile.name
            )
            if self.restart_watch_active and not same_restart_profile:
                self.stop_restart_watch(close_notice=True)
            if profile.mode == "tunnel":
                self.start_hidden_tunnel(profile)
                self.statusBar().showMessage(self.texts["profile_started"])
                QTimer.singleShot(
                    max(0, profile.wait_seconds) * 1000,
                    lambda selected=profile, retry=same_restart_profile: self.connect_remote_docker(selected, restart_mode=retry),
                )
            else:
                self.connect_remote_docker(profile, restart_mode=same_restart_profile)
        except Exception as exc:
            QMessageBox.critical(self, self.texts["msg_error"], str(exc))
    def open_remote_terminal(self):
        profile = self.selected_profile()
        if not profile:
            QMessageBox.warning(self, self.texts["msg_error"], self.texts["profile_no_profiles"])
            return
        if profile.mode != "ssh":
            QMessageBox.information(self, self.texts["msg_info"], self.texts["ssh_terminal_tunnel"])
            return
        target = f"{profile.resolved_ssh_user()}@{profile.resolved_ssh_host()}"
        port = profile.resolved_ssh_port()
        cmd = ["ssh"]
        if port:
            cmd.extend(["-p", str(port)])
        if profile.ssh_key_path and profile.ssh_auth_mode in {"key", "key_password"}:
            cmd.extend(["-i", profile.ssh_key_path])
        cmd.append(target)
        launch_interactive_terminal(cmd)

    def update_remote_system_info(self):
        self.remote_os_name = ""
        self.remote_arch = ""
        if not (self.current_backend == "remote" and self.client is not None):
            self.remote_sysinfo_label.setText(self.texts["remote_sysinfo_unknown"])
            return
        try:
            os_name, arch = detect_remote_system_info(self.client)
            self.remote_os_name = os_name.strip()
            self.remote_arch = arch.strip().lower()
            label = self.texts["remote_sysinfo_label"].format(os=self.remote_os_name or "Linux", arch=self.remote_arch or "?")
            self.remote_sysinfo_label.setText(label)
            self.update_infrastructure_ui(True)
        except Exception:
            self.remote_sysinfo_label.setText(self.texts["remote_sysinfo_fetch_failed"])
            self.remote_arch = ""
            self.update_infrastructure_ui(False)

    def build_local_docker_client(self) -> docker.DockerClient:
        if os.name == "nt":
            return docker.DockerClient(base_url="npipe:////./pipe/docker_engine", timeout=DOCKER_HTTP_TIMEOUT)
        endpoint = self.linux_docker_endpoint(refresh=True)
        return docker.DockerClient(base_url=endpoint, timeout=DOCKER_HTTP_TIMEOUT)

    def detect_local_system_info(self) -> tuple[str, str]:
        os_name = ""
        arch = ""
        if self.current_backend == "local" and isinstance(self.client, docker.DockerClient):
            try:
                info = self.client.info()
                os_name = str(info.get("OperatingSystem") or "").strip()
                arch = str(info.get("Architecture") or "").strip()
            except Exception:
                pass
        if not os_name:
            if os.name == "nt":
                os_name = "Docker Desktop"
            else:
                os_name = detect_local_os_name()
        if not arch:
            arch = platform.machine() or ""
        return os_name, arch

    def backend_cli_command(self) -> str:
        if self.current_backend == "remote":
            return self.get_remote_cli_command()
        if self.current_backend == "wsl" and isinstance(self.client, WslDockerClient):
            cli = getattr(self.client, "detected_cli", "") or ""
            if cli:
                return cli
        return "docker"

    def infrastructure_label(self) -> str:
        if self.current_backend == "remote":
            profile = self.active_remote_profile
            if profile and profile.mode != "ssh":
                return self.texts["infra_remote_tunnel"]
            os_name = self.remote_os_name or "Linux"
            arch = self.remote_arch or "?"
            return self.texts["infra_remote_label"].format(os=os_name, arch=arch)
        if self.current_backend == "wsl":
            distro = (self.current_wsl_distro or "").strip()
            if not distro and hasattr(self, "wsl_combo"):
                distro = self.wsl_combo.currentText().strip()
            if distro and distro != self.texts["wsl_none"]:
                return self.texts["infra_local_wsl"].format(distro=distro)
            return self.texts["infra_local_wsl"].format(distro="?")
        os_name, arch = self.detect_local_system_info()
        if not os_name:
            return self.texts["infra_local_fallback"]
        return self.texts["infra_local_label"].format(os=os_name, arch=arch or "?")

    def set_host_status_indicator(self, available: bool):
        if not hasattr(self, "btn_host_restart"):
            return
        icon = self.host_status_icon_running if available else self.host_status_icon_off
        self.btn_host_restart.setIcon(icon)
        tooltip = self.texts["host_status_running"] if available else self.texts["host_status_off"]
        self.btn_host_restart.setToolTip(tooltip)

    def update_infrastructure_ui(self, available: Optional[bool] = None):
        if hasattr(self, "infra_info_button"):
            label = self.infrastructure_label()
            metrics = str(getattr(self, "_container_metrics_text", "") or "").strip()
            activity = str(getattr(self, "_infra_activity_text", "") or "").strip()
            suffix = activity or metrics
            button_text = f"{label}  |  {suffix}" if suffix else label
            self.infra_info_button.setText(button_text)
            tooltip_parts = [
                label.replace("\n", " "),
                activity,
                str(getattr(self, "_host_metrics_tooltip_text", "") or "").strip(),
                self.texts["infra_terminal_tooltip"],
            ]
            self.infra_info_button.setToolTip("\n".join(part for part in tooltip_parts if part))
        if available is None:
            available = self.client is not None
        self.set_host_status_indicator(bool(available))

    def set_infrastructure_activity(self, text: str = ""):
        self._infra_activity_text = str(text or "").strip()
        self.update_infrastructure_ui()

    def close_client_safely(self, client):
        if client is None:
            return
        try:
            if isinstance(client, SshDockerClient):
                ssh_client = getattr(client, "_client", None)
                if ssh_client is not None:
                    ssh_client.close()
                client._client = None
            elif hasattr(client, "close"):
                client.close()
        except Exception:
            pass

    def show_restart_notification(self, text: str):
        if self.restart_notification is None:
            notice = QMessageBox(self)
            notice.setWindowTitle(self.texts["host_restart_notice_title"])
            notice.setIcon(QMessageBox.Icon.Information)
            notice.setStandardButtons(QMessageBox.StandardButton.Cancel)
            cancel_button = notice.button(QMessageBox.StandardButton.Cancel)
            if cancel_button is not None:
                cancel_button.setText(self.texts["host_restart_cancel_checks"])
            notice.setWindowModality(Qt.WindowModality.NonModal)
            notice.rejected.connect(self.cancel_restart_watch)
            self.restart_notification = notice
        self.restart_notification.setText(text)
        self.restart_notification.show()
        self.restart_notification.raise_()

    def update_restart_notification(self, text: str):
        if self.restart_notification is None:
            self.show_restart_notification(text)
            return
        self.restart_notification.setText(text)

    def stop_restart_watch(self, close_notice: bool = False):
        self.restart_watch_timer.stop()
        self.restart_watch_active = False
        self.restart_watch_profile = None
        self.restart_watch_attempt = 0
        self.restart_watch_deadline = 0.0
        self.restart_recovery_pending_refresh = False
        self.restart_grace_until = 0.0
        if close_notice and self.restart_notification is not None:
            self.restart_notification.close()
            self.restart_notification = None

    def cancel_restart_watch(self):
        if not self.restart_watch_active:
            return
        cancelled = self.texts["host_restart_cancelled"]
        notice = self.restart_notification
        self.stop_restart_watch(close_notice=False)
        if self.restart_notification is notice:
            self.restart_notification = None
        self.statusBar().showMessage(cancelled, 12000)
        self.set_infrastructure_activity(cancelled)
        self.set_host_status_indicator(False)

    def start_restart_watch(self, profile: RemoteProfile, text: str):
        self.close_client_safely(self.client)
        self.client = None
        self.current_backend = "remote"
        self.current_wsl_distro = ""
        self.active_remote_profile = profile
        self.restart_watch_active = True
        self.restart_watch_profile = profile
        self.restart_watch_attempt = 0
        self.restart_watch_deadline = time.time() + 300.0
        self.restart_grace_until = self.restart_watch_deadline
        self.restart_recovery_pending_refresh = False
        self.set_host_status_indicator(False)
        self.statusBar().showMessage(text)
        self.set_infrastructure_activity(text)
        self.show_restart_notification(text)
        self.restart_watch_timer.start()
        QTimer.singleShot(2000, self.retry_restart_connection)

    def retry_restart_connection(self):
        if not self.restart_watch_active or self.restart_watch_profile is None:
            return
        if self.restart_recovery_pending_refresh:
            return
        if time.time() >= self.restart_watch_deadline:
            timeout_text = self.texts["host_restart_timeout"]
            self.restart_watch_timer.stop()
            self.restart_watch_active = False
            self.restart_grace_until = 0.0
            self.statusBar().showMessage(timeout_text)
            self.set_infrastructure_activity(timeout_text)
            self.update_restart_notification(timeout_text)
            return
        if self.remote_connect_thread is not None and self.remote_connect_thread.isRunning():
            return
        self.restart_watch_attempt += 1
        checking = self.texts["host_restart_checking"].format(
            name=self.restart_watch_profile.name,
            attempt=self.restart_watch_attempt,
        )
        self.statusBar().showMessage(checking)
        self.set_infrastructure_activity(checking)
        self.update_restart_notification(checking)
        self.connect_remote_docker(self.restart_watch_profile, restart_mode=True, timeout=5)

    def finalize_restart_recovery(self):
        recovered = self.texts["host_restart_recovered"]
        notice = self.restart_notification
        self.stop_restart_watch(close_notice=False)
        self.set_host_status_indicator(True)
        self.statusBar().showMessage(recovered, 12000)
        self.update_restart_notification(recovered)
        if notice is not None:
            def close_recovered_notice():
                if self.restart_notification is notice:
                    notice.close()
                    self.restart_notification = None
            QTimer.singleShot(3500, close_recovered_notice)

    def open_powershell(self, command: str = ""):
        if os.name != "nt":
            launch_interactive_terminal(shell_command=command)
            return
        if command:
            subprocess.Popen(["powershell.exe", "-NoExit", "-Command", command])
        else:
            subprocess.Popen(["powershell.exe", "-NoExit"])

    def open_infra_terminal(self):
        if self.current_backend == "remote":
            profile = self.active_remote_profile or self.selected_profile()
            if not profile:
                QMessageBox.warning(self, self.texts["msg_error"], self.texts["profile_no_profiles"])
                return
            if profile.mode != "ssh":
                QMessageBox.information(self, self.texts["msg_info"], self.texts["ssh_terminal_tunnel"])
                return
            target = f"{profile.resolved_ssh_user()}@{profile.resolved_ssh_host()}"
            port = profile.resolved_ssh_port()
            cmd = ["ssh"]
            if port:
                cmd.extend(["-p", str(port)])
            if profile.ssh_key_path and profile.ssh_auth_mode in {"key", "key_password"}:
                cmd.extend(["-i", profile.ssh_key_path])
            cmd.append(target)
            cmdline = subprocess.list2cmdline(cmd) if os.name == "nt" else shlex.join(cmd)
            self.open_powershell(cmdline)
            return
        if self.current_backend == "wsl":
            distro = (self.current_wsl_distro or "").strip()
            if not distro and hasattr(self, "wsl_combo"):
                distro = self.wsl_combo.currentText().strip()
            if not distro or distro == self.texts["wsl_none"]:
                QMessageBox.information(self, self.texts["msg_info"], self.texts["wsl_detect_error"])
                return
            self.open_powershell(f"wsl -d {distro}")
            return
        self.open_powershell()

    def restart_host(self):
        reply = QMessageBox.question(
            self,
            self.texts["host_restart_title"],
            self.texts["host_restart_body"],
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self.current_backend == "remote":
            profile = self.active_remote_profile
            success = self.restart_remote_host()
            if success:
                restart_text = self.texts["host_restart_probable"] if getattr(self, "_last_restart_probable", False) else self.texts["host_restart_in_progress"]
                if profile is not None:
                    self.start_restart_watch(profile, restart_text)
                else:
                    self.statusBar().showMessage(restart_text, 20000)
                    self.set_host_status_indicator(False)
                return
        elif self.current_backend == "wsl":
            success = self.restart_wsl_host()
        else:
            success = self.restart_local_host()
        if success:
            QMessageBox.information(self, self.texts["msg_info"], self.texts["host_restart_sent"])
            self.set_host_status_indicator(False)
        else:
            QMessageBox.warning(self, self.texts["msg_error"], self.texts["host_restart_failed"])

    def restart_local_host(self) -> bool:
        commands = []
        if os.name == "nt":
            commands = [
                ["shutdown", "/r", "/t", "0"],
                ["powershell.exe", "-Command", "Restart-Computer -Force"],
            ]
        else:
            commands = []
            pkexec = shutil.which("pkexec")
            systemctl = shutil.which("systemctl")
            if pkexec and systemctl:
                commands.append([pkexec, systemctl, "reboot"])
            if systemctl:
                commands.append([systemctl, "reboot"])
            commands.extend([["reboot"], ["shutdown", "-r", "now"]])
        for cmd in commands:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
                if result.returncode == 0:
                    return True
            except Exception:
                continue
        return False

    def restart_wsl_host(self) -> bool:
        distro = (self.current_wsl_distro or "").strip()
        if not distro:
            return False
        commands = [
            "sudo reboot",
            "reboot",
            "sudo shutdown -r now",
            "shutdown -r now",
        ]
        for cmd in commands:
            try:
                result = subprocess.run(["wsl.exe", "-d", distro, "sh", "-lc", cmd], capture_output=True, text=True, timeout=8)
                if result.returncode == 0:
                    return True
            except Exception:
                continue
        try:
            result = subprocess.run(["wsl.exe", "-t", distro], capture_output=True, text=True, timeout=8)
            if result.returncode == 0:
                return True
        except Exception:
            pass
        return False

    def restart_remote_host(self) -> bool:
        profile = self.active_remote_profile
        if not (profile and isinstance(self.client, SshDockerClient) and profile.mode == "ssh"):
            return False
        self._last_restart_probable = False
        commands = []
        if self.get_remote_cli_command() == "balena":
            commands.append("balena reboot")
        commands.extend([
            "sudo systemctl reboot",
            "systemctl reboot",
            "sudo reboot",
            "reboot",
            "sudo shutdown -r now",
            "shutdown -r now",
        ])
        success, probable, _detail = self.client.dispatch_reboot(commands)
        self._last_restart_probable = probable
        return success

    def container_labels(self, container) -> Dict[str, str]:
        attrs = getattr(container, "attrs", {}) or {}
        return dict(((attrs.get("Config", {}) or {}).get("Labels", {}) or {}))

    def container_project(self, container) -> str:
        labels = self.container_labels(container)
        for key in (
            "com.docker.compose.project",
            "com.docker.stack.namespace",
            "io.balena.app-name",
            "io.resin.app-name",
        ):
            value = str(labels.get(key) or "").strip()
            if value:
                return value
        return ""

    def container_network_names(self, container) -> List[str]:
        attrs = getattr(container, "attrs", {}) or {}
        networks = (attrs.get("NetworkSettings", {}) or {}).get("Networks", {}) or {}
        names = sorted(str(name).strip() for name in networks.keys() if str(name).strip())
        if names:
            return names
        mode = str((attrs.get("HostConfig", {}) or {}).get("NetworkMode") or "").strip()
        return [mode] if mode else []

    def container_primary_network(self, container) -> str:
        networks = self.container_network_names(container)
        if not networks:
            return ""
        project = self.container_project(container)
        if project:
            expected = f"{project}_default"
            if expected in networks:
                return expected
        preferred = [name for name in networks if name not in {"bridge", "host", "none"}]
        return preferred[0] if preferred else networks[0]

    def container_group_key(self, container) -> str:
        if self.group_mode == "project":
            return self.container_project(container) or "__standalone__"
        if self.group_mode == "network":
            return self.container_primary_network(container) or "__no_network__"
        return ""

    def group_display_name(self, key: str) -> str:
        if key == "__standalone__":
            return self.texts["group_standalone"]
        if key == "__no_network__":
            return self.texts["group_no_network"]
        prefix = self.texts["group_project_prefix"] if self.group_mode == "project" else self.texts["group_network_prefix"]
        return f"{prefix}: {key}"

    def group_storage_key(self, key: str) -> str:
        return f"{self.group_mode}:{key}"

    def group_network_summary(self, containers: List[object]) -> str:
        sets = [set(self.container_network_names(container)) for container in containers]
        sets = [item for item in sets if item]
        if not sets:
            return "-"
        common = set.intersection(*sets) if len(sets) > 1 else set(sets[0])
        chosen = common if common else set.union(*sets)
        return ", ".join(sorted(chosen)) or "-"

    def build_container_groups(self, containers: List[object]) -> List[tuple]:
        if self.group_mode == "none":
            return [("", list(containers))]
        grouped: Dict[str, List[object]] = {}
        for container in containers:
            grouped.setdefault(self.container_group_key(container), []).append(container)
        def sort_key(item):
            key = item[0]
            special = key.startswith("__")
            return (special, self.group_display_name(key).casefold())
        return sorted(grouped.items(), key=sort_key)

    def insert_group_header(self, key: str, containers: List[object]):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setSpan(row, 0, 1, self.table.columnCount())
        running = sum(1 for container in containers if str(getattr(container, "status", "") or "").lower() in {"running", "up"} or str(getattr(container, "status", "") or "").lower().startswith("up"))
        networks = self.group_network_summary(containers)
        storage_key = self.group_storage_key(key)
        collapsed = storage_key in self.collapsed_groups
        arrow = "▶" if collapsed else "▼"
        summary = self.texts["group_summary"].format(count=len(containers), running=running, networks=networks)
        # Keep the spanning item only for metadata/background.  The visible
        # caption is rendered by the interactive button below.  Rendering the
        # same text in both places makes the two captions show through each
        # other because the cell widget is transparent (especially noticeable
        # on Linux and with non-100% table zoom).
        item = QTableWidgetItem("")
        item.setData(Qt.ItemDataRole.UserRole, {"row_type": "group", "key": key, "storage_key": storage_key})
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        font = QFont(item.font())
        font.setBold(True)
        item.setFont(font)
        accent = QColor(effective_accent_color(self.current_theme, self.accent_color))
        background = QColor(accent)
        background.setAlpha(26 if self.current_theme in {"day", "light"} else 38)
        item.setBackground(QBrush(background))
        item.setForeground(QBrush(accent))
        item.setToolTip(self.texts["group_summary"].format(count=len(containers), running=running, networks=networks))
        self.table.setItem(row, 0, item)

        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 0, 8, 0)
        header_layout.setSpacing(8)
        group_checkbox = QCheckBox()
        group_checkbox.setToolTip(self.texts["group_select_all"])
        group_checkbox.stateChanged.connect(
            lambda state, group=storage_key: self.on_group_checkbox_changed(group, state)
        )
        group_button = QPushButton(f"{arrow}  {self.group_display_name(key)}     {summary}")
        group_button.setObjectName("containerGroupButton")
        group_button.setFlat(True)
        group_button.setCursor(Qt.CursorShape.PointingHandCursor)
        group_button.setToolTip(
            self.texts["group_display_expand"] if collapsed else self.texts["group_display_collapse"]
        )
        group_button.clicked.connect(lambda _checked=False, group=storage_key: self.toggle_container_group(group))
        header_layout.addWidget(group_checkbox, 0)
        header_layout.addWidget(group_button, 1)
        self.table.setCellWidget(row, 0, header_widget)
        self.group_checkboxes[storage_key] = group_checkbox
        self.table.setRowHeight(row, max(28, round(34 * self.container_table_zoom / 100.0)))

    def toggle_container_group(self, storage_key: str):
        if not storage_key:
            return
        if storage_key in self.collapsed_groups:
            self.collapsed_groups.remove(storage_key)
        else:
            self.collapsed_groups.add(storage_key)
        self.render_container_table(self.last_containers)

    def on_group_checkbox_changed(self, storage_key: str, state):
        if not storage_key or getattr(self, "_updating_group_selection", False):
            return
        checked = int(state) == int(Qt.CheckState.Checked.value)
        self._updating_group_selection = True
        try:
            for row in range(self.table.rowCount()):
                name_item = self.table.item(row, 2)
                metadata = name_item.data(Qt.ItemDataRole.UserRole) if name_item else None
                if not isinstance(metadata, dict) or metadata.get("row_type") != "container":
                    continue
                if str(metadata.get("group") or "") != storage_key:
                    continue
                checkbox = self.table.cellWidget(row, 0)
                if isinstance(checkbox, QCheckBox):
                    checkbox.setChecked(checked)
        finally:
            self._updating_group_selection = False
        self.sync_group_checkbox(storage_key)
        self.sync_select_all_checkbox()

    def sync_group_checkbox(self, storage_key: str):
        if not storage_key or getattr(self, "_updating_group_selection", False):
            return
        group_checkbox = getattr(self, "group_checkboxes", {}).get(storage_key)
        if not isinstance(group_checkbox, QCheckBox):
            return
        child_states = []
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 2)
            metadata = name_item.data(Qt.ItemDataRole.UserRole) if name_item else None
            if not isinstance(metadata, dict) or metadata.get("row_type") != "container":
                continue
            if str(metadata.get("group") or "") != storage_key:
                continue
            checkbox = self.table.cellWidget(row, 0)
            if isinstance(checkbox, QCheckBox):
                child_states.append(checkbox.isChecked())
        group_checkbox.blockSignals(True)
        group_checkbox.setChecked(bool(child_states) and all(child_states))
        group_checkbox.blockSignals(False)
        self.sync_select_all_checkbox()

    def sync_select_all_checkbox(self):
        if not hasattr(self, "select_all_checkbox"):
            return
        child_states = []
        for row in range(self.table.rowCount()):
            if self.table.isRowHidden(row):
                continue
            name_item = self.table.item(row, 2)
            metadata = name_item.data(Qt.ItemDataRole.UserRole) if name_item else None
            if not isinstance(metadata, dict) or metadata.get("row_type") != "container":
                continue
            checkbox = self.table.cellWidget(row, 0)
            if isinstance(checkbox, QCheckBox):
                child_states.append(checkbox.isChecked())
        self.select_all_checkbox.blockSignals(True)
        self.select_all_checkbox.setChecked(bool(child_states) and all(child_states))
        self.select_all_checkbox.blockSignals(False)

    def on_table_cell_clicked(self, row: int, _column: int):
        item = self.table.item(row, 0)
        metadata = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not isinstance(metadata, dict) or metadata.get("row_type") != "group":
            return
        storage_key = str(metadata.get("storage_key") or "")
        self.toggle_container_group(storage_key)

    def on_select_all(self, state):
        checked = int(state) == int(Qt.CheckState.Checked.value)
        self._updating_group_selection = True
        try:
            for row in range(self.table.rowCount()):
                if self.table.isRowHidden(row):
                    continue
                name_item = self.table.item(row, 2)
                metadata = name_item.data(Qt.ItemDataRole.UserRole) if name_item else None
                if not isinstance(metadata, dict) or metadata.get("row_type") != "container":
                    continue
                widget = self.table.cellWidget(row, 0)
                if isinstance(widget, QCheckBox):
                    widget.setChecked(checked)
        finally:
            self._updating_group_selection = False
        for storage_key in getattr(self, "group_checkboxes", {}):
            self.sync_group_checkbox(storage_key)

    def filter_container_rows(self, text: str = ""):
        needle = (text or "").strip().casefold()
        self.select_all_checkbox.blockSignals(True)
        self.select_all_checkbox.setChecked(False)
        self.select_all_checkbox.blockSignals(False)
        current_group_row = None
        current_storage_key = ""
        group_visible_children: Dict[int, int] = {}
        for row in range(self.table.rowCount()):
            group_item = self.table.item(row, 0)
            metadata = group_item.data(Qt.ItemDataRole.UserRole) if group_item else None
            if isinstance(metadata, dict) and metadata.get("row_type") == "group":
                current_group_row = row
                current_storage_key = str(metadata.get("storage_key") or "")
                group_visible_children[row] = 0
                self.table.setRowHidden(row, False)
                continue

            item = self.table.item(row, 2)
            name = item.text().strip().casefold() if item else ""
            search_hidden = bool(needle and not name.startswith(needle))
            collapsed_hidden = bool(not needle and current_storage_key and current_storage_key in self.collapsed_groups)
            hidden = search_hidden or collapsed_hidden
            self.table.setRowHidden(row, hidden)
            if not hidden and current_group_row is not None:
                group_visible_children[current_group_row] = group_visible_children.get(current_group_row, 0) + 1
            if hidden:
                checkbox = self.table.cellWidget(row, 0)
                if isinstance(checkbox, QCheckBox):
                    checkbox.setChecked(False)

        for group_row, visible_count in group_visible_children.items():
            self.table.setRowHidden(group_row, bool(needle and visible_count == 0))

    def get_selected_names(self) -> List[str]:
        names = []
        for row in range(self.table.rowCount()):
            cb = self.table.cellWidget(row, 0)
            if isinstance(cb, QCheckBox) and cb.isChecked():
                item = self.table.item(row, 2)
                if item:
                    names.append(item.text())
        return names

    def render_container_table(self, containers: List[object]):
        if not hasattr(self, "table"):
            return
        self.group_checkboxes = {}
        self.container_by_name = {
            str(getattr(container, "name", "") or ""): container
            for container in (containers or [])
            if str(getattr(container, "name", "") or "")
        }
        self.table.setUpdatesEnabled(False)
        try:
            self.table.clearSpans()
            self.table.setRowCount(0)
            for group_key, group_containers in self.build_container_groups(list(containers or [])):
                ordered = self.sort_containers_for_view(group_containers)
                if self.group_mode != "none":
                    self.insert_group_header(group_key, ordered)
                storage_key = self.group_storage_key(group_key) if self.group_mode != "none" else ""
                for container in ordered:
                    row = self.table.rowCount()
                    self.table.insertRow(row)
                    row_checkbox = QCheckBox()
                    if storage_key:
                        row_checkbox.stateChanged.connect(
                            lambda _state, group=storage_key: self.sync_group_checkbox(group)
                        )
                    self.table.setCellWidget(row, 0, row_checkbox)

                    status = str(getattr(container, "status", "") or "")
                    icon_item = QTableWidgetItem()
                    if status.startswith("up") or status == "running":
                        icon_item.setIcon(self.status_icon_running)
                    else:
                        icon_item.setIcon(self.status_icon_stopped)
                    icon_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    self.table.setItem(row, 1, icon_item)

                    name_item = QTableWidgetItem(str(getattr(container, "name", "") or ""))
                    name_item.setToolTip(name_item.text())
                    name_item.setData(Qt.ItemDataRole.UserRole, {"row_type": "container", "group": storage_key})
                    try:
                        image = container.image
                        image_tags = getattr(image, "tags", None) or []
                        image_name = image_tags[0] if image_tags else (getattr(image, "short_id", "") or "")
                    except Exception:
                        attrs = getattr(container, "attrs", {}) or {}
                        config = attrs.get("Config", {}) or {}
                        image_name = str(config.get("Image") or attrs.get("Image") or "N/A")
                    image_item = QTableWidgetItem(image_name)
                    image_item.setToolTip(image_name)
                    status_item = QTableWidgetItem(status)
                    status_item.setToolTip(status)
                    metrics = getattr(container, "_dcc_metrics", {}) or {}
                    cpu_percent = float(metrics.get("cpu_percent", 0.0) or 0.0)
                    memory_usage = int(metrics.get("memory_usage", 0) or 0)
                    memory_limit = int(metrics.get("memory_limit", 0) or 0)
                    memory_percent = float(metrics.get("memory_percent", 0.0) or 0.0)
                    cpu_item = QTableWidgetItem(f"{cpu_percent:.1f}%")
                    if memory_limit > 0:
                        memory_item = QTableWidgetItem(
                            f"{memory_percent:.1f}% · {format_bytes(memory_usage)} / {format_bytes(memory_limit)}"
                        )
                    elif memory_usage > 0:
                        memory_item = QTableWidgetItem(format_bytes(memory_usage))
                    else:
                        memory_item = QTableWidgetItem("-")
                    memory_item.setToolTip(memory_item.text())

                    port_lines = self.port_lines(container)
                    ports_item = QTableWidgetItem("\n".join(port_lines) if port_lines else "-")
                    ports_font = QFont(self.table.font())
                    current_point_size = ports_font.pointSizeF()
                    if current_point_size <= 0:
                        current_point_size = 9.0
                    ports_font.setPointSizeF(max(7.0, current_point_size - 1.0))
                    ports_item.setFont(ports_font)
                    ports_item.setTextAlignment(int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop))
                    ports_item.setToolTip("\n".join(port_lines) if port_lines else "-")

                    project = self.container_project(container)
                    networks = self.container_network_names(container)
                    project_item = QTableWidgetItem(project or self.texts["group_standalone"])
                    project_item.setToolTip(project or self.texts["group_standalone"])
                    networks_item = QTableWidgetItem(" • ".join(networks) if networks else self.texts["group_no_network"])
                    networks_item.setToolTip("\n".join(networks) if networks else self.texts["group_no_network"])

                    self.table.setItem(row, 2, name_item)
                    self.table.setItem(row, 3, image_item)
                    self.table.setItem(row, 4, status_item)
                    self.table.setItem(row, 5, cpu_item)
                    self.table.setItem(row, 6, memory_item)
                    self.table.setItem(row, 7, ports_item)
                    restart_label = self.restart_policy_label(container)
                    restart_name = self.restart_policy_name(container)
                    if not self.autostart_supported(container):
                        restart_symbol = "\u2699"
                    elif restart_name in {"", "no"}:
                        restart_symbol = "\u2014"
                    else:
                        restart_symbol = "\u2713"
                    restart_item = QTableWidgetItem(restart_symbol)
                    restart_item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
                    restart_item.setToolTip(f"{self.texts['col_autostart']}: {restart_label}")
                    self.table.setItem(row, 8, restart_item)

                    urls = self.container_urls(container)
                    link_widget = self.build_link_widget(urls)
                    if link_widget is not None:
                        self.table.setCellWidget(row, 9, link_widget)
                    else:
                        link_item = QTableWidgetItem("-")
                        link_item.setTextAlignment(int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop))
                        self.table.setItem(row, 9, link_item)

                    self.table.setItem(row, 10, project_item)
                    self.table.setItem(row, 11, networks_item)
                    ports_metrics = QFontMetrics(ports_font)
                    zoom_factor = self.container_table_zoom / 100.0
                    ports_height = ports_metrics.lineSpacing() * max(1, len(port_lines)) + max(8, round(10 * zoom_factor))
                    links_height = max(20, round(24 * zoom_factor)) * max(1, len(urls)) + max(4, round(4 * zoom_factor))
                    height = max(max(28, round(34 * zoom_factor)), ports_height, links_height)
                    self.table.setRowHeight(row, height)
        finally:
            self.table.setUpdatesEnabled(True)
        self.filter_container_rows(self.container_search.text())
        self.update_link_widget_selection_states()

    def remote_access_host(self) -> str:
        profile = self.active_remote_profile
        if not profile:
            return ""
        if profile.mode == "ssh":
            return profile.resolved_ssh_host()
        if profile.ssh_target:
            return profile.resolved_ssh_host()
        base = profile.base_url.strip()
        for prefix in ("tcp://", "ssh://", "http://", "https://"):
            if base.startswith(prefix):
                base = base[len(prefix):]
        return base.split("/", 1)[0].split(":", 1)[0]

    def published_port_bindings(self, container) -> List[tuple]:
        attrs = getattr(container, "attrs", {}) or {}
        network_ports = (attrs.get("NetworkSettings", {}) or {}).get("Ports", {}) or {}
        configured_ports = (attrs.get("HostConfig", {}) or {}).get("PortBindings", {}) or {}
        bindings = []
        seen = set()
        for source in (network_ports, configured_ports):
            for cont_port, mappings in source.items():
                for mapping in mappings or []:
                    host_port = str(mapping.get("HostPort") or "").strip()
                    if not host_port:
                        continue
                    host_ip = str(mapping.get("HostIp") or "").strip()
                    key = (str(cont_port), host_ip, host_port)
                    if key in seen:
                        continue
                    seen.add(key)
                    bindings.append(key)
        return bindings

    def port_lines(self, container) -> List[str]:
        lines = []
        seen = set()
        for cont_port, host_ip, host_port in self.published_port_bindings(container):
            normalized_ip = "*" if host_ip in {"", "0.0.0.0", "::"} else host_ip
            key = (normalized_ip, host_port, cont_port)
            wildcard_key = ("*", host_port, cont_port)
            if key in seen or (normalized_ip == "*" and wildcard_key in seen):
                continue
            if normalized_ip == "*" and any(existing[1] == host_port and existing[2] == cont_port for existing in seen):
                continue
            seen.add(key)
            if normalized_ip == "*":
                lines.append(f"{host_port} -> {cont_port}")
            else:
                display_ip = f"[{normalized_ip}]" if ":" in normalized_ip and not normalized_ip.startswith("[") else normalized_ip
                lines.append(f"{display_ip}:{host_port} -> {cont_port}")
        return lines

    def container_urls(self, container) -> List[str]:
        urls = []
        seen = set()
        remote_host = self.remote_access_host() if self.current_backend == "remote" else ""
        for cont_port, host_ip, host_port in self.published_port_bindings(container):
            protocol = str(cont_port).split("/", 1)[1].lower() if "/" in str(cont_port) else "tcp"
            if protocol != "tcp":
                continue
            container_port = str(cont_port).split("/")[0]
            scheme = "https" if host_port in {"443", "8443", "9443"} or container_port in {"443", "8443", "9443"} else "http"
            normalized_ip = host_ip.strip()
            if normalized_ip in {"", "0.0.0.0", "::"}:
                target_host = remote_host or "127.0.0.1"
            elif normalized_ip in {"127.0.0.1", "::1"} and remote_host:
                target_host = remote_host
            else:
                target_host = normalized_ip
            if not target_host:
                continue
            if ":" in target_host and not target_host.startswith("["):
                target_host = f"[{target_host}]"
            url = f"{scheme}://{target_host}:{host_port}"
            if url not in seen:
                seen.add(url)
                urls.append(url)
        return urls

    def preferred_container_url(self, urls: List[str]) -> str:
        if not urls:
            return ""
        for url in urls:
            if "127.0.0.1" not in url and "localhost" not in url:
                return url
        return urls[0]

    def url_label(self, url: str) -> str:
        if "127.0.0.1" in url or "localhost" in url:
            if self.current_backend == "remote":
                return self.texts["link_device"]
            return self.texts["link_local"]
        return self.texts["link_lan"]

    def open_container_url(self, url: str):
        webbrowser.open(url)

    def copy_container_url(self, url):
        if isinstance(url, list):
            QApplication.clipboard().setText("\n".join(url))
        else:
            QApplication.clipboard().setText(url)

    def build_link_widget(self, urls: List[str]):
        if not urls:
            return None
        panel = QWidget()
        panel.setObjectName("linkPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        for url in urls:
            row = QFrame()
            row.setObjectName("linkRow")
            row.setFixedHeight(22)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 1, 3, 1)
            row_layout.setSpacing(3)

            display_url = re.sub(r"^https?://", "", url, flags=re.IGNORECASE)
            info = QLabel(f"{self.url_label(url)} · {display_url}")
            info.setObjectName("linkText")
            info.setWordWrap(False)
            info.setTextFormat(Qt.TextFormat.PlainText)
            info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            info.setToolTip(url)
            info.setMinimumWidth(0)
            info.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

            open_button = QPushButton("\u2197")
            open_button.setObjectName("linkAction")
            open_button.setToolTip(self.texts["ctx_open_link"])
            open_button.setAccessibleName(self.texts["ctx_open_link"])
            open_button.clicked.connect(lambda _=False, link=url: self.open_container_url(link))

            copy_button = QPushButton("\u29c9")
            copy_button.setObjectName("linkAction")
            copy_button.setToolTip(self.texts["ctx_copy_link"])
            copy_button.setAccessibleName(self.texts["ctx_copy_link"])
            copy_button.clicked.connect(lambda _=False, link=url: self.copy_container_url(link))

            row_layout.addWidget(info, 1)
            row_layout.addWidget(open_button)
            row_layout.addWidget(copy_button)
            layout.addWidget(row)
        return panel

    def update_link_widget_selection_states(self):
        selected_rows = set()
        if self.table.selectionModel() is not None:
            selected_rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 9)
            if widget is None:
                continue
            selected = row in selected_rows
            targets = [widget] + widget.findChildren(QWidget)
            for target in targets:
                target.setProperty("selected", selected)
                style = target.style()
                if style is not None:
                    style.unpolish(target)
                    style.polish(target)
                target.update()

    def container_actual_details(self, container) -> Dict[str, object]:
        attrs = getattr(container, "attrs", {}) or {}
        config = attrs.get("Config", {}) or {}
        state = attrs.get("State", {}) or {}
        host_config = attrs.get("HostConfig", {}) or {}
        mounts = attrs.get("Mounts", []) or []
        return {
            "name": str(getattr(container, "name", "") or attrs.get("Name") or "").lstrip("/"),
            "project": self.container_project(container) or self.texts["group_standalone"],
            "status": str(state.get("Status") or getattr(container, "status", "") or ""),
            "image": str(config.get("Image") or attrs.get("Image") or ""),
            "restart_policy": str(((host_config.get("RestartPolicy", {}) or {}).get("Name") or "no")),
            "networks": self.container_network_names(container),
            "ports": self.port_lines(container),
            "mounts": [
                {
                    "type": str(mount.get("Type") or ""),
                    "source": str(mount.get("Source") or mount.get("Name") or ""),
                    "destination": str(mount.get("Destination") or ""),
                    "rw": bool(mount.get("RW", True)),
                }
                for mount in mounts
            ],
        }

    def copy_container_details(self, container):
        payload = self.container_actual_details(container)
        QApplication.clipboard().setText(json.dumps(payload, indent=2, ensure_ascii=False))

    def show_row_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0 or not self.client:
            return
        group_item = self.table.item(row, 0)
        group_metadata = group_item.data(Qt.ItemDataRole.UserRole) if group_item else None
        if isinstance(group_metadata, dict) and group_metadata.get("row_type") == "group":
            storage_key = str(group_metadata.get("storage_key") or "")
            collapsed = storage_key in self.collapsed_groups
            menu = QMenu(self)
            label = self.texts["group_display_expand"] if collapsed else self.texts["group_display_collapse"]
            toggle = menu.addAction(label)
            action = menu.exec(self.table.viewport().mapToGlobal(pos))
            if action == toggle:
                if collapsed:
                    self.collapsed_groups.discard(storage_key)
                else:
                    self.collapsed_groups.add(storage_key)
                self.render_container_table(self.last_containers)
            return
        name_item = self.table.item(row, 2)
        if not name_item:
            return
        name = name_item.text()
        container = self.container_by_name.get(name)
        if container is None:
            QMessageBox.warning(self, self.texts["msg_error"], f"{name}: {self.texts['ctx_cached_data_missing']}")
            return

        details = self.container_actual_details(container)
        status = str(details.get("status") or "").lower()
        menu = QMenu(self)

        lifecycle_menu = menu.addMenu(self.texts["ctx_lifecycle"])
        act_start = lifecycle_menu.addAction(self.texts["ctx_start"])
        act_stop = lifecycle_menu.addAction(self.texts["ctx_stop"])
        act_restart = lifecycle_menu.addAction(self.texts["ctx_restart"])
        lifecycle_menu.addSeparator()
        act_pause = lifecycle_menu.addAction(self.texts["ctx_pause"])
        act_unpause = lifecycle_menu.addAction(self.texts["ctx_unpause"])
        act_start.setEnabled(status not in {"running", "paused"})
        act_stop.setEnabled(status in {"running", "paused", "restarting"})
        act_restart.setEnabled(status not in {"removing", "dead"})
        act_pause.setEnabled(status == "running")
        act_unpause.setEnabled(status == "paused")

        config_menu = menu.addMenu(self.texts["ctx_configuration"])
        act_edit_start = config_menu.addAction(self.texts["ctx_edit_start"])
        config_menu.addSeparator()
        act_autostart_on = config_menu.addAction(self.texts["ctx_autostart_on"])
        act_autostart_off = config_menu.addAction(self.texts["ctx_autostart_off"])
        autostart_supported = self.autostart_supported(container)
        restart_name = self.restart_policy_name(container)
        act_autostart_on.setEnabled(autostart_supported and restart_name in {"", "no"})
        act_autostart_off.setEnabled(autostart_supported and restart_name not in {"", "no"})

        diagnostics_menu = menu.addMenu(self.texts["ctx_diagnostics"])
        act_logs = diagnostics_menu.addAction(self.texts["ctx_logs"])
        act_exec = diagnostics_menu.addAction(self.texts["ctx_exec"])
        act_inspect = diagnostics_menu.addAction(self.texts["ctx_inspect"])
        act_exec.setEnabled(status == "running")

        urls = self.container_urls(container)
        links_menu = menu.addMenu(self.texts["ctx_links"])
        act_open_link = links_menu.addAction(self.texts["ctx_open_link"])
        act_copy_link = links_menu.addAction(self.texts["ctx_copy_link"])
        act_open_link.setEnabled(bool(urls))
        act_copy_link.setEnabled(bool(urls))

        data_menu = menu.addMenu(self.texts["ctx_actual_data"])
        networks = list(details.get("networks") or [])
        ports = list(details.get("ports") or [])
        mounts = list(details.get("mounts") or [])
        data_info = [
            data_menu.addAction(self.texts["ctx_project"].format(project=details.get("project") or "-")),
            data_menu.addAction(self.texts["ctx_networks"].format(networks=", ".join(networks) or "-")),
            data_menu.addAction(self.texts["ctx_ports"].format(ports=", ".join(ports) or "-")),
            data_menu.addAction(self.texts["ctx_mounts"].format(count=len(mounts))),
        ]
        for info_action in data_info:
            info_action.setEnabled(False)
        data_menu.addSeparator()
        act_copy_details = data_menu.addAction(self.texts["ctx_copy_details"])
        act_copy_ports = data_menu.addAction(self.texts["ctx_copy_ports"])
        act_copy_networks = data_menu.addAction(self.texts["ctx_copy_networks"])
        act_copy_ports.setEnabled(bool(ports))
        act_copy_networks.setEnabled(bool(networks))

        menu.addSeparator()
        act_remove = menu.addAction(self.texts["ctx_remove"])

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if not action:
            return

        mutated = False
        try:
            if action == act_logs:
                LogsDialog(self.client, name, self.texts, self).exec()
            elif action == act_inspect:
                self.show_inspect_dialog(container)
            elif action == act_exec:
                self.show_exec_shell_dialog(container)
            elif action == act_edit_start:
                self.open_edit_start_wizard(name)
                mutated = True
            elif action == act_open_link and urls:
                self.open_container_url(self.preferred_container_url(urls))
            elif action == act_copy_link and urls:
                self.copy_container_url(self.preferred_container_url(urls))
            elif action == act_copy_details:
                self.copy_container_details(container)
            elif action == act_copy_ports:
                QApplication.clipboard().setText("\n".join(ports))
            elif action == act_copy_networks:
                QApplication.clipboard().setText("\n".join(networks))
            elif action == act_autostart_on:
                if self.confirm_restart_policy_change(True):
                    self.show_action_feedback([self.execute_container_action(container, "autostart_on")])
                    mutated = True
            elif action == act_autostart_off:
                if self.confirm_restart_policy_change(False):
                    self.show_action_feedback([self.execute_container_action(container, "autostart_off")])
                    mutated = True
            elif action == act_remove:
                self.bulk_remove_single(name)
                mutated = True
            else:
                action_map = {
                    act_start: "start",
                    act_stop: "stop",
                    act_restart: "restart",
                    act_pause: "pause",
                    act_unpause: "unpause",
                }
                self.show_action_feedback([self.execute_container_action(container, action_map[action])])
                mutated = True
        except Exception as exc:
            QMessageBox.warning(self, self.texts["msg_error"], f"{name}: {exc}")
        if mutated:
            self.refresh_containers()

    def show_inspect_dialog(self, container):
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Inspect: {container.name}")
        dlg.resize(800, 600)
        layout = QVBoxLayout(dlg)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setPlainText(json.dumps(container.attrs, indent=2))
        layout.addWidget(txt)
        dlg.exec()

    def show_exec_shell_dialog(self, container):
        if self.current_backend == "wsl" and self.current_wsl_distro:
            shell_command = f'docker exec -it {container.name} /bin/bash || docker exec -it {container.name} /bin/sh'
            cmd = ["wsl.exe", "-d", self.current_wsl_distro, "sh", "-lc", shell_command]
            intro = self.texts["exec_shell_intro_wsl"].format(target=self.current_wsl_distro)
        elif self.current_backend == "remote" and self.active_remote_profile:
            if self.active_remote_profile.mode == "ssh":
                profile = self.active_remote_profile
                target = f"{profile.resolved_ssh_user()}@{profile.resolved_ssh_host()}"
                port = profile.resolved_ssh_port()
                cli = self.get_remote_cli_command()
                remote_cmd = f"{cli} exec -it {container.name} /bin/bash || {cli} exec -it {container.name} /bin/sh"
                cmd = ["ssh"]
                if port:
                    cmd.extend(["-p", str(port)])
                if profile.ssh_key_path and profile.ssh_auth_mode in {"key", "key_password"}:
                    cmd.extend(["-i", profile.ssh_key_path])
                cmd.extend([target, remote_cmd])
                intro = self.texts["exec_shell_intro_remote_ssh"].format(target=target)
            else:
                cmd = ["docker", "--host", self.active_remote_profile.resolved_base_url(), "exec", "-it", container.name, "/bin/bash"]
                intro = self.texts["exec_shell_intro_remote_tunnel"]
        else:
            cmd = ["docker", "exec", "-it", container.name, "/bin/bash"]
            intro = self.texts["exec_shell_intro_local"]

        command_text = " ".join(cmd)
        dialog = CommandInfoDialog(
            self.texts["exec_shell_title"],
            intro,
            command_text,
            self.texts,
            self,
            action_text=self.texts["command_run"],
            action_callback=lambda command=list(cmd): launch_interactive_terminal(command),
        )
        dialog.exec()

    def bulk_remove_single(self, name: str):
        reply = QMessageBox.question(self, self.texts["msg_info"], self.texts["msg_confirm_remove"], QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self.client.containers.get(name).remove(force=True)
        except Exception as exc:
            QMessageBox.warning(self, self.texts["msg_error"], f"{name}: {exc}")

    def refresh_containers(self):
        if not self.client:
            self.show_local_docker_unavailable(self.texts["docker_not_available"])
            return
        if self.refresh_thread is not None and self.refresh_thread.isRunning():
            return
        self.statusBar().showMessage(self.texts["status_loading"])
        self.select_all_checkbox.blockSignals(True)
        self.select_all_checkbox.setChecked(False)
        self.select_all_checkbox.blockSignals(False)
        self.refresh_thread = QThread()
        self.worker = RefreshWorker(self.client)
        self.worker.moveToThread(self.refresh_thread)
        self.refresh_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_refresh_finished)
        self.worker.finished.connect(self.refresh_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)

        def thread_finished():
            if self.refresh_thread is not None:
                self.refresh_thread.deleteLater()
                self.refresh_thread = None

        self.refresh_thread.finished.connect(thread_finished)
        self.refresh_thread.start()

    def refresh_monitoring(self):
        if self.restart_watch_active:
            self.retry_restart_connection()

    def on_refresh_finished(self, containers, error_message: str):
        if error_message:
            self.set_host_status_indicator(False)
            if self.restart_recovery_pending_refresh and self.restart_watch_active:
                self.close_client_safely(self.client)
                self.client = None
                self.restart_recovery_pending_refresh = False
                waiting = self.texts["host_restart_waiting_retry"]
                self.statusBar().showMessage(waiting)
                self.set_infrastructure_activity(waiting)
                self.update_restart_notification(waiting)
                if not self.restart_watch_timer.isActive():
                    self.restart_watch_timer.start()
                return
            if self.current_backend == "remote" and time.time() < float(getattr(self, "restart_grace_until", 0.0) or 0.0):
                restart_text = self.texts["host_restart_waiting_retry"]
                self.statusBar().showMessage(restart_text)
                self.set_infrastructure_activity(restart_text)
                if self.restart_watch_active and not self.restart_watch_timer.isActive():
                    self.restart_watch_timer.start()
                return
            QMessageBox.critical(self, self.texts["msg_error"], error_message)
            message = self.texts["status_ready"]
            if self.current_backend == "remote" and isinstance(self.client, SshDockerClient):
                message = message + " - " + self.remote_engine_label()
            self.statusBar().showMessage(message)
            return

        self.set_host_status_indicator(True)
        recovered_after_restart = bool(self.restart_recovery_pending_refresh and self.restart_watch_active)
        if self.current_backend == "remote" and self.restart_grace_until and not recovered_after_restart:
            self.restart_grace_until = 0.0
        summary = getattr(self.worker, "metrics_summary", {}) if self.worker is not None else {}
        host_metrics = getattr(self.worker, "host_metrics", {}) if self.worker is not None else {}
        container_cpu = float(summary.get("cpu_percent", 0.0) or 0.0)
        container_memory = int(summary.get("memory_usage", 0) or 0)
        container_metrics_text = self.texts["container_metrics_format"].format(
            container_cpu=container_cpu,
            container_mem=format_bytes(container_memory),
        )
        if host_metrics:
            host_cpu = float(host_metrics.get("cpu_percent", 0.0) or 0.0)
            host_mem = int(host_metrics.get("memory_usage", 0) or 0)
            host_total = int(host_metrics.get("memory_total", 0) or 0)
            host_mem_pct = float(host_metrics.get("memory_percent", 0.0) or 0.0)
            metrics_text = self.texts["host_metrics_format"].format(
                host_cpu=host_cpu,
                host_mem=format_bytes(host_mem),
                host_total=format_bytes(host_total),
                host_mem_pct=host_mem_pct,
                container_cpu=container_cpu,
                container_mem=format_bytes(container_memory),
            )
        else:
            metrics_text = container_metrics_text
        self._infra_activity_text = ""
        self._container_metrics_text = container_metrics_text
        self._host_metrics_tooltip_text = metrics_text
        self.update_infrastructure_ui(True)
        self.last_containers = list(containers)
        self.render_container_table(self.last_containers)
        message = self.texts["status_ready"]
        if self.current_backend == "remote" and isinstance(self.client, SshDockerClient):
            message = message + " - " + self.remote_engine_label()
        self.statusBar().showMessage(message)
        if recovered_after_restart:
            self.finalize_restart_recovery()

    def bulk_action(self, action: str):
        if not self.client:
            self.show_local_docker_unavailable(self.texts["docker_not_available"])
            return
        names = self.get_selected_names()
        if not names:
            QMessageBox.warning(self, self.texts["msg_error"], self.texts["msg_no_selection"])
            return
        if action == "remove":
            reply = QMessageBox.question(self, self.texts["msg_info"], self.texts["msg_confirm_remove"], QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
        if action == "autostart_on" and not self.confirm_restart_policy_change(True):
            return
        if action == "autostart_off" and not self.confirm_restart_policy_change(False):
            return
        blocked_messages = []
        error_messages = []
        for name in names:
            try:
                container = self.client.containers.get(name)
                message = self.execute_container_action(container, action)
                if message:
                    blocked_messages.append(message)
            except Exception as exc:
                error_messages.append(f"{name}: {exc}")
        self.show_action_feedback(blocked_messages)
        self.show_action_feedback(error_messages, self.texts["msg_error"])
        self.refresh_containers()

    def show_selected_logs(self):
        if not self.client:
            self.show_local_docker_unavailable(self.texts["docker_not_available"])
            return
        names = self.get_selected_names()
        if not names:
            QMessageBox.warning(self, self.texts["msg_error"], self.texts["msg_no_selection"])
            return
        LogsDialog(self.client, names[0], self.texts, self).exec()

    def open_edit_start_wizard(self, container_name: str = ""):
        if not self.client:
            self.show_local_docker_unavailable(self.texts["docker_not_available"])
            return
        target_name = container_name or self.selected_container_name_for_edit()
        if not target_name:
            QMessageBox.warning(self, self.texts["msg_error"], self.texts["wizard_select_one_edit"])
            return
        try:
            container = self.client.containers.get(target_name)
            initial_args = self.container_run_args(container)
        except Exception as exc:
            QMessageBox.critical(self, self.texts["msg_error"], f"{target_name}: {exc}")
            return
        cli_command, cli_choices = self.wizard_cli_settings()
        dlg = NewContainerDialog(
            self.client,
            self.texts,
            lambda args, auto_fix=True, allow_ai=False, original=target_name: self.recreate_container_with_args(original, args, auto_fix=auto_fix, allow_ai=allow_ai),
            self,
            initial_args=initial_args,
            edit_mode=True,
            existing_name=target_name,
            llm_settings_getter=self.get_llm_settings,
            ai_command_callback=self.generate_ai_docker_command,
            build_image_callback=self.build_catalog_image_with_progress,
            lang=self.lang,
            cli_command=cli_command,
            cli_choices=cli_choices,
            remote_arch=self.remote_arch if self.current_backend == "remote" else "",
            target_host_label=self.deployment_target_label(),
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh_containers()

    def open_new_container_wizard(self):
        if not self.client:
            self.show_local_docker_unavailable(self.texts["docker_not_available"])
            return
        cli_command, cli_choices = self.wizard_cli_settings()
        dlg = NewContainerDialog(
            self.client,
            self.texts,
            lambda args, auto_fix=True, allow_ai=False: self.execute_smart_container_command_with_progress(args, self.texts["progress_title_create"], self.texts["progress_status_create"], auto_fix=auto_fix, allow_ai=allow_ai),
            self,
            llm_settings_getter=self.get_llm_settings,
            ai_command_callback=self.generate_ai_docker_command,
            build_image_callback=self.build_catalog_image_with_progress,
            lang=self.lang,
            cli_command=cli_command,
            cli_choices=cli_choices,
            remote_arch=self.remote_arch if self.current_backend == "remote" else "",
            target_host_label=self.deployment_target_label(),
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh_containers()

def main():
    if "--self-check" in sys.argv:
        required = {
            "docker": bool(docker),
            "PyQt6": bool(QApplication),
            "qdarktheme": bool(qdarktheme),
            "paramiko": paramiko is not None,
        }
        payload = {
            "ok": all(required.values()),
            "version": APP_VERSION,
            "platform": sys.platform,
            "architecture": platform.machine(),
            "required": required,
        }
        print(json.dumps(payload, ensure_ascii=False))
        raise SystemExit(0 if payload["ok"] else 2)
    app = QApplication(sys.argv)
    app.setOrganizationName(APP_SETTINGS_ORG)
    app.setApplicationName(APP_SETTINGS_NAME)
    if sys.platform.startswith("linux") and hasattr(app, "setDesktopFileName"):
        app.setDesktopFileName("docker-control-center")
    if ICON_FILE.exists():
        app.setWindowIcon(QIcon(str(ICON_FILE)))
    settings = QSettings(APP_SETTINGS_ORG, APP_SETTINGS_NAME)
    window = MainWindow(settings)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
