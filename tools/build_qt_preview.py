"""Build an isolated Qt preview executable without changing the Tk installer/release."""

from __future__ import annotations

import subprocess
import sys
import os
import tempfile
import argparse
import shutil
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installer', action='store_true', help='Also build the separate per-user preview installer')
    parser.add_argument('--compact', action='store_true', help='Build a folder package and compress installed files to avoid runtime extraction')
    args = parser.parse_args()
    package_root = ROOT / ('build/qt-preview/folder-package' if args.compact else 'build/qt-preview/package')
    staged = package_root / ('PS Focus Qt Preview/PS Focus Qt Preview.exe' if args.compact else 'PS Focus Qt Preview.exe')
    environment = {**os.environ, 'PSFOCUS_QT_ONEDIR': '1' if args.compact else '0', 'PYINSTALLER_ZLIB_COMPRESSION_LEVEL': '9'}
    for arguments in (
        [sys.executable, '-m', 'unittest', 'test_qt_layout', 'test_qt_settings', 'test_qt_preview', 'test_tracker', 'test_credentials', '-q'],
        [sys.executable, 'tools/write_qt_notices.py'],
        [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--log-level', 'WARN', '--distpath', str(package_root), '--workpath', 'build/qt-preview/cache', 'PS Focus Qt Preview.spec'],
        [sys.executable, 'tools/check_credentials.py', '--archive', str(staged), '--verify-qt-binaries'],
    ):
        subprocess.run(arguments, cwd=ROOT, env=environment, check=True)
    if args.compact:
        subprocess.run([sys.executable, 'tools/check_credentials.py', '--directory', str(staged.parent / '_internal'), '--verify-qt-binaries'], cwd=ROOT, check=True)
    for platform in ('offscreen', 'windows'):
        with tempfile.TemporaryDirectory(prefix='qt-smoke-', dir=ROOT / 'build/qt-preview') as folder:
            environment = {**os.environ, 'APPDATA': folder, 'QT_QPA_PLATFORM': platform}
            subprocess.run([str(staged), '--smoke-test'], cwd=ROOT, env=environment, check=True, timeout=30)
    output = ROOT / 'dist/qt-preview'
    output.mkdir(parents=True, exist_ok=True)
    if args.compact:
        output = output / 'compact-build'
        output.mkdir(parents=True, exist_ok=True)
        # Publish into a new directory so a running folder build is never partially replaced.
        app_output = Path(tempfile.mkdtemp(prefix='app-', dir=output))
        shutil.copytree(staged.parent, app_output, dirs_exist_ok=True)
        executable = app_output / staged.name
    else:
        executable = output / staged.name
    try:
        if not args.compact:
            shutil.copy2(staged, executable)
    except PermissionError:
        output = output / 'next-build'
        output.mkdir(parents=True, exist_ok=True)
        executable = output / staged.name
        shutil.copy2(staged, executable)
        print('Current preview executable is locked; new build is in next-build.')
    files = sorted(p for p in executable.parent.rglob('*') if p.is_file()) if args.compact else [executable]
    if args.installer:
        from app_config import APP_VERSION
        from tools.build_release import find_inno_setup
        notices = ROOT / 'build/qt-preview/Third-Party Notices.txt'
        runtime_args = [f'/DAppRuntimeDir={staged.parent / "_internal"}'] if args.compact else []
        subprocess.run([find_inno_setup(), '/Q', f'/O{output}', f'/DAppVersion={APP_VERSION}', f'/DNoticesFile={notices}', f'/DAppExecutable={staged}', *runtime_args, 'installer/PS Focus Qt Preview.iss'], cwd=ROOT, check=True)
        files.append(output / f'PS-Focus-Qt-Preview-Setup-{APP_VERSION}.exe')
    if args.compact:
        # Runtime DLL basenames repeat; preserve relative paths in the manifest.
        (output / 'SHA256SUMS.txt').write_text(''.join(
            f'{hashlib.sha256(path.read_bytes()).hexdigest()} *{path.relative_to(output).as_posix()}\n'
            for path in files), encoding='utf-8')
    else:
        subprocess.run([sys.executable, 'tools/write_checksums.py', *map(str, files), '--output', str(output / 'SHA256SUMS.txt')], cwd=ROOT, check=True)
    program_bytes = sum(p.stat().st_size for p in executable.parent.rglob('*') if p.is_file()) if args.compact else executable.stat().st_size
    print(f'Qt preview ready: {executable} ({program_bytes / 1048576:.1f} MiB program files before installed compression)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
