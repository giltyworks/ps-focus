"""Measure logical and allocated program-file bytes, including Windows compression."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from pathlib import Path


def disk_usage(root: Path) -> dict[str, int]:
    api = ctypes.WinDLL('kernel32', use_last_error=True).GetCompressedFileSizeW
    api.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    api.restype = wintypes.DWORD
    logical = allocated = count = 0
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        high = wintypes.DWORD()
        ctypes.set_last_error(0)
        low = api(str(path.resolve()), ctypes.byref(high))
        if low == 0xFFFFFFFF and ctypes.get_last_error():
            raise ctypes.WinError(ctypes.get_last_error())
        allocated += (high.value << 32) | low
        logical += path.stat().st_size
        count += 1
    return {'files': count, 'logical_bytes': logical, 'allocated_bytes': allocated}


if __name__ == '__main__':
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    if not args.folder.is_dir():
        parser.error('folder must exist')
    print(json.dumps(disk_usage(args.folder), indent=2))
