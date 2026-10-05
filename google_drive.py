"""Small Google OAuth and Drive app-data sync client using the standard library"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from ctypes import wintypes
from pathlib import Path

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.appdata"
USERINFO_SCOPE = "https://www.googleapis.com/auth/userinfo.email"
SCOPE = f"{DRIVE_SCOPE} {USERINFO_SCOPE} openid"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
DRIVE_API = "https://www.googleapis.com/drive/v3"
UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
USERINFO_API = "https://openidconnect.googleapis.com/v1/userinfo"


# Marks a token file whose contents are encrypted for the current Windows user
PROTECTED_TOKEN_KEY = "protected"


class GoogleAccountAccessRequired(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_char))]


def _windows_data_protection(function_name: str, content: bytes) -> bytes:
    """Encrypt or decrypt with Windows DPAPI, so the result is readable only by the current Windows user"""
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    function = getattr(crypt32, function_name)
    function.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(content, len(content))
    source = _DataBlob(len(content), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    result = _DataBlob()
    # Flag 0x1 forbids any prompt, so a failure is reported instead of showing a dialog
    if not function(ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(result)):
        raise OSError(f"Windows data protection failed: error {ctypes.get_last_error()}")
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel32.LocalFree(ctypes.cast(result.data, ctypes.c_void_p))


class GoogleDriveSync:
    def __init__(self, app_data: Path, credentials_file: Path) -> None:
        self.token_file = app_data / "google-token.json"
        self.credentials_file = credentials_file
        self._token_lock = threading.RLock()

    @property
    def connected(self) -> bool:
        return self.token_file.exists()

    def _client(self) -> tuple[str, str]:
        credential_paths = [self.token_file.parent / "credentials.json", self.credentials_file]
        if getattr(sys, "frozen", False):
            credential_paths.append(Path(sys.executable).with_name("credentials.json"))
            credential_paths.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "assets" / "oauth" / "desktop-client.json")
        else:
            credential_paths.append(Path(__file__).resolve().with_name("credentials.json"))
        credentials_file = next((path for path in credential_paths if path.is_file()), None)
        if credentials_file is None:
            raise RuntimeError("Add a Google OAuth Desktop app credentials.json beside the executable (or main.py)")
        data = json.loads(credentials_file.read_text(encoding="utf-8-sig"))
        config = data.get("installed")
        if not isinstance(config, dict) or not config.get("client_id") or not config.get("client_secret"):
            raise RuntimeError("credentials.json must contain an installed Google OAuth Desktop app client; web clients are not supported")
        return config["client_id"], config["client_secret"]

    def _save_token(self, token: dict) -> None:
        with self._token_lock:
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(token)
            if os.name == "nt":
                protected = _windows_data_protection("CryptProtectData", content.encode("utf-8"))
                content = json.dumps({PROTECTED_TOKEN_KEY: base64.b64encode(protected).decode("ascii")})
            temporary = self.token_file.with_suffix(".tmp")
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(self.token_file)

    def _read_token(self) -> dict:
        with self._token_lock:
            try:
                token = json.loads(self.token_file.read_text(encoding="utf-8"))
                if not isinstance(token, dict):
                    raise ValueError("The saved Google sign-in is not a token")
                if PROTECTED_TOKEN_KEY in token:
                    protected = base64.b64decode(token[PROTECTED_TOKEN_KEY])
                    token = json.loads(_windows_data_protection("CryptUnprotectData", protected).decode("utf-8"))
                elif os.name == "nt":
                    # Tokens saved by earlier versions were plain text; protect them the first time they are read
                    self._save_token(token)
                return token
            except (OSError, ValueError, TypeError, AttributeError) as error:
                raise GoogleAccountAccessRequired("Google sign-in has expired, connect your account again") from error

    def _request_token(self, form: dict[str, str]) -> dict:
        request = urllib.request.Request(
            TOKEN_URL,
            data=urllib.parse.urlencode(form).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if form.get("grant_type") == "refresh_token" and error.code == 400:
                self.token_file.unlink(missing_ok=True)
                raise GoogleAccountAccessRequired("Google sign-in expired, reconnect your account") from error
            raise RuntimeError(f"Google token request failed: {error}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Google token request failed: {error}") from error

    def sign_in(self) -> None:
        client_id, client_secret = self._client()
        state = secrets.token_urlsafe(24)
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
        result: dict[str, str] = {}
        completed = threading.Event()

        class CallbackHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if not secrets.compare_digest(query.get("state", [""])[0], state):
                    # Not Google's redirect for this sign-in, such as a favicon request or another program
                    # probing the port, so it must neither complete nor cancel the sign-in
                    self.send_error(400)
                    return
                if query.get("code", [""])[0] and not query.get("error"):
                    result["code"] = query["code"][0]
                    message = "PS Focus is connected, you can close this browser tab"
                else:
                    result["error"] = query.get("error", ["Google did not return an authorization code"])[0]
                    message = "Google sign-in was not completed, you can close this browser tab"
                body = f"<html><body style='font:16px sans-serif'>{message}</body></html>".encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                completed.set()

            def log_message(self, format: str, *args: object) -> None:
                return

        # The literal loopback address cannot be redirected the way the name "localhost" can
        server = http.server.HTTPServer(("127.0.0.1", 0), CallbackHandler)
        server.timeout = 1
        redirect_uri = f"http://127.0.0.1:{server.server_port}/"
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
        webbrowser.open(auth_url)
        try:
            deadline = time.monotonic() + 180
            while not completed.is_set() and time.monotonic() < deadline:
                server.handle_request()
            if not completed.is_set():
                raise RuntimeError("Google sign-in timed out, please try again")
            if "error" in result:
                raise RuntimeError(f"Google sign-in failed: {result['error']}")
            token = self._request_token({
                "code": result["code"],
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            })
            token["expires_at"] = time.time() + int(token.get("expires_in", 3600))
            self._save_token(token)
        finally:
            server.server_close()

    def _access_token(self) -> str:
        with self._token_lock:
            client_id, client_secret = self._client()
            token = self._read_token()
            if float(token.get("expires_at", 0)) <= time.time() + 60:
                refresh_token = token.get("refresh_token")
                if not refresh_token:
                    raise RuntimeError("Google sign-in needs to be renewed, connect your account again")
                refreshed = self._request_token({
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                })
                refreshed["expires_at"] = time.time() + int(refreshed.get("expires_in", 3600))
                refreshed["refresh_token"] = refresh_token
                refreshed["scope"] = refreshed.get("scope", token.get("scope", ""))
                token = refreshed
                self._save_token(token)
            return token["access_token"]

    def account_email(self) -> str:
        token = self._read_token()
        granted_scopes = token.get("scope", "").split()
        if USERINFO_SCOPE not in granted_scopes:
            raise GoogleAccountAccessRequired("Reconnect Google to grant access to your account email")

        request = urllib.request.Request(
            USERINFO_API,
            headers={"Authorization": f"Bearer {self._access_token()}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                profile = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise GoogleAccountAccessRequired("Reconnect Google to grant access to your account email") from error
            raise RuntimeError(f"Google account lookup failed: {error}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Google account lookup failed: {error}") from error

        email = profile.get("email")
        if not isinstance(email, str) or not email:
            raise RuntimeError("Google did not return an account email")
        return email

    def sign_out(self) -> bool:
        with self._token_lock:
            try:
                token = self._read_token()
            except RuntimeError:
                token = {}

            revoke_token = token.get("refresh_token") or token.get("access_token")
            revocation_confirmed = True
            try:
                if revoke_token:
                    request = urllib.request.Request(
                        REVOKE_URL,
                        data=urllib.parse.urlencode({"token": revoke_token}).encode("utf-8"),
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                        method="POST",
                    )
                    with urllib.request.urlopen(request, timeout=10):
                        pass
            except OSError:
                revocation_confirmed = False
            finally:
                self.token_file.unlink(missing_ok=True)
            return revocation_confirmed

    def _api(self, url: str, method: str = "GET", body: bytes | None = None, content_type: str = "application/json") -> dict:
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Authorization": f"Bearer {self._access_token()}", "Content-Type": content_type},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = response.read()
                return json.loads(payload.decode("utf-8")) if payload else {}
        except urllib.error.HTTPError as error:
            try:
                payload = json.loads(error.read().decode("utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            details = payload.get("error", {})
            reasons = {item.get("reason") for item in details.get("errors", []) if isinstance(item, dict)}
            if error.code == 403 and "SERVICE_DISABLED" in reasons:
                raise RuntimeError("Enable the Google Drive API in Google Cloud Console, then retry") from error
            raise RuntimeError(f"Google Drive sync failed: {error}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Google Drive sync failed: {error}") from error

    def _find_file(self, name: str) -> str | None:
        """Return the id of the named file in the private Drive app-data area"""
        query = urllib.parse.urlencode({
            "spaces": "appDataFolder",
            "q": f"name='{name}'",
            "fields": "files(id)",
        })
        files = self._api(f"{DRIVE_API}/files?{query}").get("files", [])
        return files[0]["id"] if files else None

    def _upload_file(self, name: str, content: bytes, content_type: str) -> None:
        """Replace the named app-data file, creating it on the first upload"""
        file_id = self._find_file(name)
        if file_id:
            self._api(
                f"{UPLOAD_API}/files/{file_id}?uploadType=media",
                method="PATCH",
                body=content,
                content_type=content_type,
            )
            return

        boundary = "ps-focus-" + secrets.token_hex(12)
        metadata = json.dumps({"name": name, "parents": ["appDataFolder"]}).encode("utf-8")
        body = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
            + metadata
            + f"\r\n--{boundary}\r\nContent-Type: {content_type}\r\n\r\n".encode()
            + content
            + f"\r\n--{boundary}--".encode()
        )
        self._api(
            f"{UPLOAD_API}/files?uploadType=multipart",
            method="POST",
            body=body,
            content_type=f"multipart/related; boundary={boundary}",
        )

    def upload_settings(self, settings: dict) -> None:
        self._upload_file("settings.json", json.dumps(settings, indent=2).encode("utf-8"), "application/json")

    def upload_activity_backup(self, content: bytes) -> None:
        self._upload_file("activity.sqlite3", content, "application/x-sqlite3")

    def download_activity_backup(self) -> bytes | None:
        file_id = self._find_file("activity.sqlite3")
        if file_id is None:
            return None

        request = urllib.request.Request(
            f"{DRIVE_API}/files/{file_id}?alt=media",
            headers={"Authorization": f"Bearer {self._access_token()}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError) as error:
            raise RuntimeError(f"Google Drive backup download failed: {error}") from error
