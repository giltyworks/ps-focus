# -*- mode: python ; coding: utf-8 -*-
"""The release: PS Focus on Qt, built as a folder (the program and its _internal runtime) that the installer
compresses on disk. Built by tools/build_release.py"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, SPECPATH)
from tools.version_resource import write_version_file

version_file = write_version_file(Path('build/version/PS Focus.txt'), 'PS Focus activity tracker', 'PS Focus.exe')

# Desktop OAuth configuration is public client metadata, not a server secret.
# Generate a minimal release asset without adding credential values to Git.
oauth_datas = []
credential_source = Path('credentials.json')
oauth_json = os.environ.get('PSFOCUS_OAUTH_CREDENTIALS')
if oauth_json or credential_source.is_file():
    config = json.loads(oauth_json or credential_source.read_text(encoding='utf-8-sig')).get('installed')
    if not isinstance(config, dict) or not isinstance(config.get('client_id'), str) or not config['client_id'].endswith('.apps.googleusercontent.com') or not isinstance(config.get('client_secret'), str) or not config['client_secret']:
        raise RuntimeError('Release OAuth configuration must be a Google Desktop app client')
    bundled_config = Path('build/oauth/desktop-client.json')
    bundled_config.parent.mkdir(parents=True, exist_ok=True)
    bundled_config.write_text(json.dumps({'installed': {key: config[key] for key in ('client_id', 'client_secret')}}), encoding='utf-8')
    oauth_datas = [(str(bundled_config), 'assets/oauth')]
else:
    print('No Desktop OAuth configuration supplied; this build cannot provide Google sign-in.')

a = Analysis(
    ['qt/__main__.py'],
    pathex=[SPECPATH],
    binaries=[],
    datas=[
        ('assets/icons/PSFocus.ico', 'assets/icons'),
        ('assets/icons/PSFocus_Settings_64.png', 'assets/icons'),
        ('assets/sounds/celebration.wav', 'assets/sounds'),
    ] + oauth_datas,
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=[
        # The Tk app's toolkit and image and tray libraries
        'tkinter', 'PIL', 'pystray',
        'PyQt5', 'PyQt6', 'PySide2', 'PySide6.QtNetwork', 'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets', 'PySide6.QtSvg', 'PySide6.QtSvgWidgets',
        # Optional archive codecs: backups are SQLite copies, and Shiboken's embedded signature ZIP uses zlib
        'bz2', '_bz2', 'lzma', '_lzma', 'compression.zstd', '_zstd',
        # Web requests go through Windows' WinHTTP (web.py), so Python's OpenSSL is not needed; hashlib falls back
        # to Python's built-in SHA-256 for sign-in
        'ssl', '_ssl', '_hashlib',
        # Never loaded: it does no decimal arithmetic. (unicodedata stays: Windows host names go through the idna
        # encoding, which needs it, when Google sign-in opens its local listener)
        'decimal', '_decimal', '_pydecimal',
    ],
    # Python's documentation text left out of the bundled code; the app relies on neither docstrings nor asserts
    noarchive=False, optimize=2,
)
# Windows 10 and later carry the C runtime themselves (Python 3.14 needs Windows 10). Build machines with the Windows
# SDK installed would otherwise pack its copies, about 1 MB more for nothing
a.binaries = [entry for entry in a.binaries if not (entry[0].lower().startswith('api-ms-win-') or entry[0].lower() == 'ucrtbase.dll')]


# The interface is painted with QPainter, uses PNG and ICO images, English text and Windows' WinHTTP. Qt's broad hooks
# also collect graphics and network plugins it never loads, and Python brings OpenSSL
def needed_file(name):
    normalized = name.replace('\\', '/').lower()
    if normalized.endswith(('/opengl32sw.dll', '/qt6network.dll', '/qtnetwork.pyd', '/qt6svg.dll')):
        return False
    if normalized.rsplit('/', 1)[-1].startswith(('libcrypto-', 'libssl-')):
        return False
    if '/translations/' in normalized:
        return False
    if '/plugins/' in normalized:
        # The offscreen platform is kept for the build's own start-up check
        return normalized.endswith((
            '/platforms/qwindows.dll', '/platforms/qoffscreen.dll',
            '/imageformats/qico.dll', '/styles/qmodernwindowsstyle.dll',
        ))
    return True


a.binaries = [entry for entry in a.binaries if needed_file(entry[0])]
a.datas = [entry for entry in a.datas if needed_file(entry[0])]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='PS Focus', debug=False, bootloader_ignore_signals=False,
    # UPX-packed executables are flagged by antivirus far more often, so builds are left uncompressed
    strip=False, upx=False, upx_exclude=[], runtime_tmpdir=None,
    console=False, disable_windowed_traceback=False,
    icon=['assets/icons/PSFocus.ico'], version=version_file,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='PS Focus')
