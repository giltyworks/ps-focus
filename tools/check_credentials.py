"""Reject credential files and recognizable secrets without printing their values."""
from __future__ import annotations

import argparse
import json
import hashlib
import re
import subprocess
from pathlib import Path

SENSITIVE_NAME = re.compile(
    r"(?i)(^|/)(?:\.env(?:\..*)?|credentials[^/]*\.json|client_secret[^/]*\.json|"
    r"[^/]*service-account[^/]*\.json|google-token\.(?:json|tmp)|[^/]+\.(?:pem|key|pfx|p12|jks|keystore))$"
)
SIGNATURES = {
    "Google OAuth secret": rb"GOCSPX-[A-Za-z0-9_-]{10,}",
    "Google API key": rb"AIza[0-9A-Za-z_-]{35}",
    "AWS access key": rb"(?:AKIA|ASIA)[A-Z0-9]{16}",
    "GitHub token": rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})",
    "private key": rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----",
    "Slack token": rb"xox[baprs]-[A-Za-z0-9-]{20,}",
    "Stripe secret": rb"(?:sk|rk)_live_[A-Za-z0-9]{20,}",
    "credential JSON": rb'"(?:client_secret|private_key|refresh_token|access_token)"\s*:\s*"(?!test-[^"]*"|example[^"]*")[^"\r\n]{10,}"',
}


def inspect(name: str, data: bytes, *, allow_desktop_client: bool = False, allow_verified_qt_pem_markers: bool = False) -> list[str]:
    issues = []
    if allow_desktop_client:
        try:
            document = json.loads(data)
            config = document['installed']
            valid = set(document) == {'installed'} and set(config) == {'client_id', 'client_secret'} and isinstance(config['client_id'], str) and config['client_id'].endswith('.apps.googleusercontent.com') and isinstance(config['client_secret'], str) and bool(config['client_secret'])
        except (ValueError, KeyError, TypeError):
            valid = False
        if not valid:
            return [f'{name}: invalid bundled Desktop OAuth configuration']
    if SENSITIVE_NAME.search(name.replace("\\", "/")):
        issues.append(f"{name}: credential filename")
    for label, pattern in SIGNATURES.items():
        if allow_verified_qt_pem_markers and label == 'private key':
            continue
        if allow_desktop_client and label in {'Google OAuth secret', 'credential JSON'}:
            continue
        if re.search(pattern, data):
            issues.append(f"{name}: {label}")
    return issues


def verified_qt_binary(name: str, data: bytes) -> bool:
    """Qt's TLS libraries contain PEM format markers; accept only unchanged installed copies."""
    name = name.replace('\\', '/')
    allowed = {'PySide6/Qt6Network.dll', 'PySide6/plugins/tls/qopensslbackend.dll', 'PySide6/plugins/tls/qschannelbackend.dll'}
    if name not in allowed:
        return False
    import PySide6
    source = Path(PySide6.__file__).parent / name.removeprefix('PySide6/')
    return source.is_file() and hashlib.sha256(source.read_bytes()).digest() == hashlib.sha256(data).digest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", action="append", default=[], help="PyInstaller executable or package to inspect")
    parser.add_argument("--directory", action="append", default=[], help="Inspect extracted runtime files in a folder package")
    parser.add_argument("--verify-qt-binaries", action="store_true", help="Verify Qt TLS DLL copies before allowing their PEM marker strings")
    args = parser.parse_args()
    paths = subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
    issues = []
    for name in filter(None, paths):
        path = Path(name)
        if not path.is_file():
            continue
        if path.suffix.lower() in {".exe", ".pkg"} or name.startswith(("build/", "dist/")):
            issues.append(f"{name}: build artifact tracked in source control")
        issues.extend(inspect(name, path.read_bytes()))
    if args.archive:
        from PyInstaller.archive.readers import CArchiveReader

        for filename in args.archive:
            archive = CArchiveReader(filename)
            for name in archive.toc:
                data = archive.extract(name) or b""
                issues.extend(inspect(f"{filename}/{name}", data, allow_desktop_client=name.replace('\\', '/') == 'assets/oauth/desktop-client.json', allow_verified_qt_pem_markers=args.verify_qt_binaries and verified_qt_binary(name, data)))
    for directory in args.directory:
        root = Path(directory)
        if not root.is_dir():
            raise FileNotFoundError(root)
        for path in root.rglob('*'):
            if path.is_file():
                name = path.relative_to(root).as_posix()
                data = path.read_bytes()
                issues.extend(inspect(str(path), data, allow_desktop_client=name == 'assets/oauth/desktop-client.json', allow_verified_qt_pem_markers=args.verify_qt_binaries and verified_qt_binary(name, data)))
    for issue in issues:
        print(issue)
    print(f"Credential check: {'FAILED' if issues else 'passed'}")
    return int(bool(issues))


if __name__ == "__main__":
    raise SystemExit(main())
