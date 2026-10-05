# -*- mode: python ; coding: utf-8 -*-
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
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/icons/PSFocus.ico', 'assets/icons'),
        ('assets/icons/PSFocus_AppWindow_32.png', 'assets/icons'),
        ('assets/icons/PSFocus_Master_1024.png', 'assets/icons'),
        ('assets/icons/PSFocus_Settings_64.png', 'assets/icons'),
        ('assets/icons/PSFocus_Taskbar_48.png', 'assets/icons'),
        ('assets/sounds/celebration.wav', 'assets/sounds'),
    ] + oauth_datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Parts of Pillow the app never uses: it only draws shapes and text and reads and writes PNG.
    # The AVIF decoder alone is a fifth of the executable. Pillow skips image formats that are missing
    excludes=[
        'PIL._avif', 'PIL.AvifImagePlugin',
        'PIL._webp', 'PIL.WebPImagePlugin',
        'PIL._imagingcms', 'PIL.ImageCms',
        'PIL._imagingtk', 'PIL.ImageTk',
        'PIL._imagingmath', 'PIL.ImageMath',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PS Focus',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX-packed executables are flagged by antivirus far more often, so builds are left uncompressed
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icons/PSFocus.ico'],
    version=version_file,
)
