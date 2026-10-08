# -*- mode: python ; coding: utf-8 -*-
"""Separate Qt preview package; the existing Tk release specification remains independent."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, SPECPATH)
from tools.version_resource import write_version_file

version_file = write_version_file(Path('build/qt-preview/version.txt'), 'PS Focus Qt preview', 'PS Focus Qt Preview.exe')
oauth_datas = []
credential_source = Path('credentials.json')
oauth_json = os.environ.get('PSFOCUS_OAUTH_CREDENTIALS')
if oauth_json or credential_source.is_file():
    config = json.loads(oauth_json or credential_source.read_text(encoding='utf-8-sig')).get('installed')
    if not isinstance(config, dict) or not isinstance(config.get('client_id'), str) or not config['client_id'].endswith('.apps.googleusercontent.com') or not isinstance(config.get('client_secret'), str) or not config['client_secret']:
        raise RuntimeError('Preview OAuth configuration must be a Google Desktop app client')
    bundled_config = Path('build/qt-preview/oauth/desktop-client.json')
    bundled_config.parent.mkdir(parents=True, exist_ok=True)
    bundled_config.write_text(json.dumps({'installed': {key: config[key] for key in ('client_id', 'client_secret')}}), encoding='utf-8')
    oauth_datas = [(str(bundled_config), 'assets/oauth')]

a = Analysis(
    ['tools/qt_preview_entry.py'],
    pathex=[SPECPATH],
    binaries=[],
    datas=[('assets/icons/PSFocus.ico', 'assets/icons'), ('assets/icons/PSFocus_Settings_64.png', 'assets/icons'), ('assets/sounds/celebration.wav', 'assets/sounds'), ('build/qt-preview/Third-Party Notices.txt', '.')] + oauth_datas,
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['tkinter', 'PIL', 'pystray', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6.QtNetwork', 'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets', 'PySide6.QtSvg', 'PySide6.QtSvgWidgets',
              # Optional shutil/zipfile archive codecs: backups are SQLite copies,
              # and Shiboken's embedded signature ZIP uses standard zlib.
              'bz2', '_bz2', 'lzma', '_lzma', 'compression.zstd', '_zstd'],
    noarchive=False, optimize=0,
)
a.binaries = [entry for entry in a.binaries if not (entry[0].lower().startswith('api-ms-win-') or entry[0].lower() == 'ucrtbase.dll')]
# This interface uses raster QPainter, PNG/ICO assets, English text and stdlib HTTPS.
# Qt's broad GUI hooks also collect optional graphics/network plugins that it never loads.
def needed_qt_file(name):
    normalized = name.replace('\\', '/').lower()
    if normalized.endswith(('/opengl32sw.dll', '/qt6network.dll', '/qtnetwork.pyd', '/qt6svg.dll')):
        return False
    if '/translations/' in normalized:
        return False
    if '/plugins/' in normalized:
        return normalized.endswith((
            '/platforms/qwindows.dll', '/platforms/qoffscreen.dll',
            '/imageformats/qico.dll', '/styles/qmodernwindowsstyle.dll',
        ))
    return True

a.binaries = [entry for entry in a.binaries if needed_qt_file(entry[0])]
a.datas = [entry for entry in a.datas if needed_qt_file(entry[0])]
pyz = PYZ(a.pure)
folder_build = os.environ.get('PSFOCUS_QT_ONEDIR') == '1'
embedded_runtime = [] if folder_build else [a.binaries, a.datas]
exe = EXE(
    pyz, a.scripts, *embedded_runtime, [],
    exclude_binaries=folder_build,
    name='PS Focus Qt Preview', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, upx_exclude=[], runtime_tmpdir=None,
    console=False, disable_windowed_traceback=False,
    icon=['assets/icons/PSFocus.ico'], version=version_file,
)
if folder_build:
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='PS Focus Qt Preview')
