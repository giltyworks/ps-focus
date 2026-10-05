"""Write SHA-256 checksums for release files so downloaders can confirm their copy matches the published build"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checksum_lines(paths: list[Path]) -> list[str]:
    """Return one line per file in the sha256sum format, naming each file without its folder"""
    names = [path.name for path in paths]
    if len(set(names)) != len(names):
        raise ValueError("Release files must have different names")
    return [f"{sha256(path)} *{path.name}" for path in paths]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path, help="release files to fingerprint")
    parser.add_argument("--output", type=Path, default=Path("dist/SHA256SUMS.txt"), help="checksum file to write")
    args = parser.parse_args()
    lines = checksum_lines(args.files)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for line in lines:
        print(line)
    print(f"Checksums written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
