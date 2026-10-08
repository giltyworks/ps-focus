"""HTTPS requests through Windows' own WinHTTP, so the app needs no copy of OpenSSL

urlopen takes the same urllib.request.Request and timeout as urllib.request.urlopen and gives back a response to read,
raising urllib.error.HTTPError for an error status and urllib.error.URLError when the request cannot be made, so code
written for urllib works unchanged. WinHTTP checks certificates against Windows' own store and uses the proxy Windows
is set to. Redirects are followed as urllib follows them: a POST answered with 301, 302 or 303 is repeated as a GET
without its body. Away from Windows, urllib itself is used
"""

from __future__ import annotations

import ctypes
import io
import os
import urllib.error
import urllib.parse
import urllib.request
from ctypes import wintypes
from email.message import Message

# The most redirects followed for one request, as urllib's HTTPRedirectHandler.max_redirections
MAX_REDIRECTS = 10
USER_AGENT = "PS Focus"

if os.name == "nt":
    _winhttp = ctypes.WinDLL("winhttp", use_last_error=True)
    HINTERNET = ctypes.c_void_p
    _winhttp.WinHttpOpen.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    _winhttp.WinHttpOpen.restype = HINTERNET
    _winhttp.WinHttpConnect.argtypes = [HINTERNET, wintypes.LPCWSTR, wintypes.WORD, wintypes.DWORD]
    _winhttp.WinHttpConnect.restype = HINTERNET
    _winhttp.WinHttpOpenRequest.argtypes = [
        HINTERNET, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD,
    ]
    _winhttp.WinHttpOpenRequest.restype = HINTERNET
    _winhttp.WinHttpSetTimeouts.argtypes = [HINTERNET, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    _winhttp.WinHttpSetTimeouts.restype = wintypes.BOOL
    _winhttp.WinHttpSetOption.argtypes = [HINTERNET, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    _winhttp.WinHttpSetOption.restype = wintypes.BOOL
    _winhttp.WinHttpSendRequest.argtypes = [
        HINTERNET, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t,
    ]
    _winhttp.WinHttpSendRequest.restype = wintypes.BOOL
    _winhttp.WinHttpReceiveResponse.argtypes = [HINTERNET, ctypes.c_void_p]
    _winhttp.WinHttpReceiveResponse.restype = wintypes.BOOL
    _winhttp.WinHttpQueryHeaders.argtypes = [
        HINTERNET, wintypes.DWORD, wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
    ]
    _winhttp.WinHttpQueryHeaders.restype = wintypes.BOOL
    _winhttp.WinHttpReadData.argtypes = [HINTERNET, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    _winhttp.WinHttpReadData.restype = wintypes.BOOL
    _winhttp.WinHttpCloseHandle.argtypes = [HINTERNET]
    _winhttp.WinHttpCloseHandle.restype = wintypes.BOOL

WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY = 4
WINHTTP_ACCESS_TYPE_DEFAULT_PROXY = 0
WINHTTP_FLAG_SECURE = 0x00800000
WINHTTP_OPTION_DISABLE_FEATURE = 63
WINHTTP_DISABLE_REDIRECTS = 0x00000002
WINHTTP_QUERY_STATUS_CODE = 19
WINHTTP_QUERY_STATUS_TEXT = 20
WINHTTP_QUERY_RAW_HEADERS_CRLF = 22
WINHTTP_QUERY_FLAG_NUMBER = 0x20000000
# What the commonest failures mean, for messages people can act on
ERROR_MEANINGS = {
    12002: "the connection timed out",
    12007: "the server name could not be found",
    12029: "the server could not be reached",
    12030: "the connection was closed",
    12175: "the server's security certificate could not be checked",
    12057: "the server's security certificate could not be checked",
}


class Response(io.BytesIO):
    """The whole body of a response, read like the one urllib returns"""

    def __init__(self, body: bytes, status: int, reason: str, headers: Message, url: str) -> None:
        super().__init__(body)
        self.status = self.code = status
        self.reason = reason
        self.headers = headers
        self.url = url

    def getcode(self) -> int:
        return self.status

    def geturl(self) -> str:
        return self.url

    def info(self) -> Message:
        return self.headers


def _failure(what: str) -> urllib.error.URLError:
    code = ctypes.get_last_error()
    meaning = ERROR_MEANINGS.get(code, f"WinHTTP error {code}")
    return urllib.error.URLError(f"{what}: {meaning}")


def _query_text(request, query: int) -> str:
    size = wintypes.DWORD(0)
    _winhttp.WinHttpQueryHeaders(request, query, None, None, ctypes.byref(size), None)
    if not size.value:
        return ""
    buffer = ctypes.create_unicode_buffer(size.value // 2 + 1)
    if not _winhttp.WinHttpQueryHeaders(request, query, None, buffer, ctypes.byref(size), None):
        return ""
    return buffer.value


def _parse_headers(raw: str) -> Message:
    headers = Message()
    for line in raw.split("\r\n")[1:]:
        name, separator, value = line.partition(":")
        if separator and name.strip():
            headers[name.strip()] = value.strip()
    return headers


def _send_once(session, method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float) -> Response:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise urllib.error.URLError(f"unsupported address: {url}")
    secure = parts.scheme == "https"
    port = parts.port or (443 if secure else 80)
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    connection = _winhttp.WinHttpConnect(session, parts.hostname, port, 0)
    if not connection:
        raise _failure("Could not connect")
    try:
        request = _winhttp.WinHttpOpenRequest(connection, method, path, None, None, None, WINHTTP_FLAG_SECURE if secure else 0)
        if not request:
            raise _failure("Could not start the request")
        try:
            milliseconds = max(1, int(timeout * 1000))
            _winhttp.WinHttpSetTimeouts(request, milliseconds, milliseconds, milliseconds, milliseconds)
            # Redirects are followed here, as urllib follows them, rather than by WinHTTP
            disable = wintypes.DWORD(WINHTTP_DISABLE_REDIRECTS)
            _winhttp.WinHttpSetOption(request, WINHTTP_OPTION_DISABLE_FEATURE, ctypes.byref(disable), ctypes.sizeof(disable))
            header_text = "".join(f"{name}: {value}\r\n" for name, value in headers.items())
            data = body or b""
            buffer = ctypes.create_string_buffer(data, len(data)) if data else None
            if not _winhttp.WinHttpSendRequest(
                request, header_text or None, len(header_text) if header_text else 0, buffer, len(data), len(data), 0
            ):
                raise _failure("The request could not be sent")
            if not _winhttp.WinHttpReceiveResponse(request, None):
                raise _failure("No response came")
            status = wintypes.DWORD(0)
            size = wintypes.DWORD(ctypes.sizeof(status))
            if not _winhttp.WinHttpQueryHeaders(
                request, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, None, ctypes.byref(status), ctypes.byref(size), None
            ) or not status.value:
                raise _failure("The response had no status")
            reason = _query_text(request, WINHTTP_QUERY_STATUS_TEXT)
            response_headers = _parse_headers(_query_text(request, WINHTTP_QUERY_RAW_HEADERS_CRLF))
            chunks = []
            chunk = ctypes.create_string_buffer(64 * 1024)
            while True:
                read = wintypes.DWORD(0)
                if not _winhttp.WinHttpReadData(request, chunk, len(chunk), ctypes.byref(read)):
                    raise _failure("The response could not be read")
                if not read.value:
                    break
                chunks.append(chunk.raw[:read.value])
            return Response(b"".join(chunks), status.value, reason, response_headers, url)
        finally:
            _winhttp.WinHttpCloseHandle(request)
    finally:
        _winhttp.WinHttpCloseHandle(connection)


def _open_session():
    session = _winhttp.WinHttpOpen(USER_AGENT, WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY, None, None, 0)
    if not session:
        # Windows before 8.1 has no automatic proxy access; its default proxy setting is used instead
        session = _winhttp.WinHttpOpen(USER_AGENT, WINHTTP_ACCESS_TYPE_DEFAULT_PROXY, None, None, 0)
    if not session:
        raise _failure("Could not start a web session")
    return session


def urlopen(request: urllib.request.Request, timeout: float = 30) -> Response:
    if os.name != "nt":
        return urllib.request.urlopen(request, timeout=timeout)
    method = request.get_method()
    url = request.full_url
    body = request.data
    headers = {"User-Agent": USER_AGENT, **{name.title(): value for name, value in request.header_items()}}
    session = _open_session()
    try:
        for _ in range(MAX_REDIRECTS + 1):
            response = _send_once(session, method, url, headers, body, timeout)
            location = response.headers.get("Location")
            if response.status in (301, 302, 303, 307, 308) and location:
                url = urllib.parse.urljoin(url, location)
                if response.status in (301, 302, 303) and method not in ("GET", "HEAD"):
                    # As browsers and urllib do, the request goes on as a GET without its body
                    method, body = "GET", None
                    headers = {name: value for name, value in headers.items() if name.lower() not in ("content-type", "content-length")}
                continue
            if response.status >= 400:
                raise urllib.error.HTTPError(url, response.status, response.reason, response.headers, response)
            return response
        raise urllib.error.HTTPError(url, response.status, "Too many redirects", response.headers, response)
    finally:
        _winhttp.WinHttpCloseHandle(session)
