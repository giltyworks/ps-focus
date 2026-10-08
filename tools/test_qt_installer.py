"""Install/uninstall the preview in a temporary workspace folder; leave existing installs untouched."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import tempfile
import time
import winreg
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREVIEW_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B9608271-5AC7-486C-934C-59B68AC34739}_is1'


def registry_values(path):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            values = {}
            for index in range(winreg.QueryInfoKey(key)[1]):
                name, value, kind = winreg.EnumValue(key, index)
                values[name] = (value, kind)
            return values
    except FileNotFoundError:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('installer', type=Path)
    parser.add_argument('--max-installed-bytes', type=int, help='Fail if installed allocation exceeds this budget')
    args = parser.parse_args()
    if registry_values(PREVIEW_KEY) is not None:
        raise RuntimeError('A Qt preview is already installed; refusing to change its registration for a test')
    startup_key = r'Software\Microsoft\Windows\CurrentVersion\Run'
    startup_before = registry_values(startup_key)
    tk = Path(os.environ['LOCALAPPDATA']) / 'Programs/PS Focus/PS Focus.exe'
    tk_before = hashlib.sha256(tk.read_bytes()).digest() if tk.exists() else None
    test_root = (ROOT / 'build/qt-preview').resolve()
    test_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='installer-test-', dir=test_root) as folder:
        target = Path(folder).resolve()
        assert target.is_relative_to(test_root)
        app = target / 'installed'
        installed = False
        try:
            subprocess.run([str(args.installer.resolve()), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOCLOSEAPPLICATIONS', '/NOICONS', '/TASKS=', f'/DIR={app}', f'/LOG={target / "install.log"}'], check=True, timeout=60)
            installed = True
            values = registry_values(PREVIEW_KEY)
            assert values and Path(values['InstallLocation'][0]).resolve() == app.resolve()
            assert values['DisplayName'][0] == 'PS Focus Qt Preview'
            executable = app / 'PS Focus Qt Preview.exe'
            assert executable.is_file()
            from qt_disk_usage import disk_usage
            footprint = disk_usage(app)
            print(f'Installed program footprint: {footprint}')
            (test_root / 'installed-footprint.json').write_text(json.dumps(footprint, indent=2), encoding='utf-8')
            if args.max_installed_bytes is not None:
                assert footprint['allocated_bytes'] <= args.max_installed_bytes, 'Installed program exceeds the disk budget'
            isolated_data = target / 'appdata'
            temporary_runtime = target / 'runtime-temp'
            temporary_runtime.mkdir()
            runtime_env = {**os.environ, 'APPDATA': str(isolated_data), 'TMP': str(temporary_runtime), 'TEMP': str(temporary_runtime)}
            for platform in ('offscreen', 'windows'):
                subprocess.run([str(executable), '--smoke-test'], env={**runtime_env, 'QT_QPA_PLATFORM': platform}, check=True, timeout=30)
            assert not list(temporary_runtime.glob('_MEI*')), 'Runtime extraction should not leave files behind'
        finally:
            uninstaller = app / 'unins000.exe'
            if uninstaller.exists():
                subprocess.run([str(uninstaller), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', f'/LOG={target / "uninstall.log"}'], check=True, timeout=60)
                # Inno's uninstaller relaunches from a temporary copy; wait for that process too.
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if registry_values(PREVIEW_KEY) is None and not uninstaller.exists():
                        try:
                            with (target / 'uninstall.log').open('ab'):
                                pass
                        except PermissionError:
                            pass
                        else:
                            break
                    time.sleep(0.1)
                else:
                    raise RuntimeError('Uninstaller did not finish within 15 seconds')
            elif installed:
                raise RuntimeError('Installer did not create its uninstaller')
        assert registry_values(PREVIEW_KEY) is None
        assert not (app / 'PS Focus Qt Preview.exe').exists()
        assert (isolated_data / 'PS Focus Qt Preview/activity.sqlite3').exists(), 'Uninstall must preserve preview data'
    assert registry_values(startup_key) == startup_before, 'Windows startup entries changed'
    if tk_before is not None:
        assert hashlib.sha256(tk.read_bytes()).digest() == tk_before, 'Installed Tk executable changed'
    print('Preview install, installed-app startup, uninstall, retained data, unchanged startup entries and unchanged Tk executable: passed')


if __name__ == '__main__':
    main()
