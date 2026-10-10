"""Talks to the PS Focus friends server (friends_server/), which passes figures between friends

Every call proves who is asking with a Google ID token and gets back the whole picture: the person's own friend code,
their friends with their latest figures, and friend requests both ways. Calls are made on a background thread
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable

from web import urlopen

# Address of the deployed friends server; friends cannot be turned on while this is empty
FRIENDS_SERVER_URL = ""


class FriendsError(RuntimeError):
    """A request the server turned down, with its explanation, or that could not reach it"""


class FriendsService:
    def __init__(self, identity_token: Callable[[], str], server_url: str | None = None) -> None:
        self.identity_token = identity_token
        self.server_url = (FRIENDS_SERVER_URL if server_url is None else server_url).rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.server_url)

    def _call(self, action: str, body: dict | None = None) -> dict:
        request = urllib.request.Request(
            f"{self.server_url}/v1/{action}",
            data=json.dumps(body or {}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.identity_token()}"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                message = json.loads(error.read().decode("utf-8")).get("error")
            except (OSError, ValueError, AttributeError):
                message = None
            finally:
                error.close()
            raise FriendsError(message if isinstance(message, str) and message else f"The friends server answered {error.code}") from error
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise FriendsError("Could not reach the friends server") from error
        if not isinstance(result, dict):
            raise FriendsError("The friends server sent something unexpected")
        return result

    def sync(self, name: str, stats: dict) -> dict:
        """Hand over the latest figures; the answer holds the friends' figures"""
        return self._call("sync", {"name": name, "stats": stats})

    def add(self, code: str) -> dict:
        return self._call("add", {"code": code})

    def accept(self, code: str) -> dict:
        return self._call("accept", {"code": code})

    def decline(self, code: str) -> dict:
        return self._call("decline", {"code": code})

    def remove(self, code: str) -> dict:
        """Unfriend, or cancel a request sent"""
        return self._call("remove", {"code": code})

    def leave(self) -> dict:
        """Delete everything the server keeps about this person"""
        return self._call("leave")


def format_code(code: str) -> str:
    """A friend code as shown: two groups of four"""
    return f"{code[:4]}-{code[4:]}" if len(code) == 8 else code
