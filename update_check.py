"""Asks the PS Focus web endpoint for the latest published version; nothing is downloaded or installed"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from feedback import FEEDBACK_ENDPOINT_URL
from web import urlopen

# The feedback web app also answers version requests, so releases need no separate hosting
UPDATE_CHECK_URL = FEEDBACK_ENDPOINT_URL
UPDATE_CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000
# The only places an update link may lead: the public site and the public repository's pages
DOWNLOAD_SITE_HOST = "giltyworks.github.io"
DOWNLOAD_REPOSITORY_PATH = "/giltyworks/ps-focus/"
_VERSION_PATTERN = re.compile(r"\d{1,5}(?:\.\d{1,5}){0,3}")


def parse_version(text: object) -> tuple[int, ...] | None:
    if not isinstance(text, str) or not _VERSION_PATTERN.fullmatch(text.strip()):
        return None
    parts = [int(part) for part in text.strip().split(".")]
    return tuple(parts + [0] * (4 - len(parts)))


def is_safe_download_url(url: object) -> bool:
    """Only PS Focus's own https pages may be opened, even if the endpoint were made to return something else

    To move downloads to another site, first publish a release from the current one that adds the new address here
    """
    if not isinstance(url, str) or len(url) > 2000:
        return False
    try:
        parsed = urllib.parse.urlsplit(url.strip())
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme != "https" or parsed.username or parsed.password or port not in (None, 443):
        return False
    host = (parsed.hostname or "").lower()
    if host == DOWNLOAD_SITE_HOST:
        return True
    # Dot segments, written plainly or encoded, could climb out of the repository to someone else's
    path = parsed.path.lower()
    if ".." in path or "%" in path or "\\" in path:
        return False
    return host == "github.com" and path.startswith(DOWNLOAD_REPOSITORY_PATH)


def available_update(current_version: str, endpoint_url: str = UPDATE_CHECK_URL) -> tuple[str, str] | None:
    """Return the newer version and its download page, or None when this build is current or nothing is published"""
    current = parse_version(current_version)
    if not endpoint_url or current is None:
        return None
    request = urllib.request.Request(endpoint_url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read(64 * 1024).decode("utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError(f"Could not check for updates: {error}") from error
    if not isinstance(payload, dict) or not payload.get("ok"):
        return None
    latest_version = payload.get("latest_version")
    download_url = payload.get("download_url")
    latest = parse_version(latest_version)
    if latest is None or latest <= current or not is_safe_download_url(download_url):
        return None
    return latest_version.strip(), download_url.strip()
