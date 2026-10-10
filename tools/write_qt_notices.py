"""Collect the exact installed Qt package notices for the release, with matching wheels as a fallback

Run by tools/build_release.py. Where PySide6 was installed without its package details, download the matching
wheels without installing them:
`py -m pip download --no-deps --dest build/qt-preview/wheels PySide6==6.11.2 PySide6_Essentials==6.11.2 shiboken6==6.11.2`
"""

from __future__ import annotations

import importlib.metadata
import sys
import zipfile
from pathlib import Path

import PySide6

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ('PySide6', 'PySide6_Essentials', 'shiboken6')
# The PySide6 package itself only gathers the others and its add-ons; a build with the essential modules alone has none
OPTIONAL = {'PySide6'}


RELEASE_HEADER = (
    'PS Focus includes the following third-party software. Each is provided under its own licence, reproduced below.\n'
    'Qt and Qt for Python (PySide6, Shiboken) are used under the GNU Lesser General Public License version 3. Their '
    'source code is available from https://download.qt.io and https://code.qt.io, and PySide6 from '
    'https://pypi.org/project/PySide6. Python\'s source code is available from https://www.python.org.'
)


def write_notices(header: str = RELEASE_HEADER, output: Path | None = None) -> Path:
    sections = [header]
    sections.append((Path(sys.base_prefix) / 'LICENSE.txt').read_text(encoding='utf-8', errors='replace'))
    for package in PACKAGES:
        try:
            distribution = importlib.metadata.distribution(package)
            if distribution.version != PySide6.__version__:
                raise RuntimeError(f'{package} version differs from the Qt runtime')
            files = [f for f in distribution.files or [] if '/licenses/' in str(f).replace('\\', '/') or any(word in f.name.upper() for word in ('LICENSE', 'COPYING', 'NOTICE'))]
            documents = [(str(f), Path(distribution.locate_file(f)).read_text(encoding='utf-8', errors='replace')) for f in files]
            metadata = distribution.read_text('METADATA') or ''
        except importlib.metadata.PackageNotFoundError:
            wheels = list((ROOT / 'build/qt-preview/wheels').glob(f'{package.lower()}-{PySide6.__version__}-*.whl'))
            if not wheels and package in OPTIONAL:
                continue
            if len(wheels) != 1:
                raise RuntimeError(f'No notices found for {package}; download its matching wheel into build/qt-preview/wheels')
            with zipfile.ZipFile(wheels[0]) as archive:
                documents = [(name, archive.read(name).decode('utf-8', errors='replace')) for name in archive.namelist() if '/licenses/' in name]
                metadata = archive.read(next(name for name in archive.namelist() if name.endswith('/METADATA'))).decode('utf-8')
        if not documents:
            raise RuntimeError(f'No licence documents found for {package}')
        license_fields = '\n'.join(line for line in metadata.splitlines() if line.startswith(('License:', 'License-Expression:', 'License-File:', 'Project-URL:')))
        sections.append(f'===== {package} {PySide6.__version__} =====\n{license_fields}')
        sections.extend(f'----- {name} -----\n{text}' for name, text in documents)
    output = output or ROOT / 'build/qt-preview/Third-Party Notices.txt'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('\n\n'.join(sections), encoding='utf-8')
    return output


if __name__ == '__main__':
    print(write_notices())
