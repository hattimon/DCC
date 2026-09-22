# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parents[1]
datas = [
    (str(ROOT / 'upstream_assets/icon.png'), '.'),
    (str(ROOT / 'upstream_assets/bg.mp3'), '.'),
    (str(ROOT / 'backgrounds'), 'backgrounds'),
    (str(ROOT / 'dcc-catalog.json'), '.'),
    (str(ROOT / 'catalog/media'), 'catalog/media'),
]
binaries = []
hiddenimports = []
tmp_ret = collect_all('qdarktheme')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

a = Analysis(
    [str(ROOT / 'DockerControlCenter.py')],
    pathex=[], binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [], name='DockerControlCenter',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True, upx_exclude=[],
    runtime_tmpdir=None, console=False, disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None, codesign_identity=None, entitlements_file=None,
)
