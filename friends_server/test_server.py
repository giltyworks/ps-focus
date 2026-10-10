"""Checks the friends server end to end, run against a local copy: `npm run dev` in this folder, then
`py test_server.py`. The local copy accepts "dev:<id>" in place of a Google sign-in"""

import json
import secrets
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8787"
# Fresh people on every run, so the local database can be reused
RUN = secrets.token_hex(4)


def call(person: str, action: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"{BASE}/v1/{action}", data=json.dumps(body or {}).encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token or f'dev:{person}-{RUN}'}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def ok(person: str, action: str, body: dict | None = None) -> dict:
    status, result = call(person, action, body)
    assert status == 200, (action, status, result)
    return result


stats = {"two_weeks": 12.34, "total": 456.78, "today": 1.5, "week": 6.2, "level": 23, "streak": 4, "active": "Krita"}
amy = ok("amy", "sync", {"name": "Amy", "stats": stats})
odd = {"two_weeks": 9999, "level": "x", "active": "Notepad"}
bo = ok("bo", "sync", {"name": "  Bo\n", "stats": odd})
code_amy, code_bo = amy["me"]["code"], bo["me"]["code"]
assert len(code_amy) == 8 and code_amy != code_bo
assert bo["me"]["name"] == "Bo"
# A second check-in keeps the code
assert ok("amy", "sync", {"name": "Amy", "stats": stats})["me"]["code"] == code_amy

# Errors are explained
assert call("amy", "add", {"code": code_amy})[0] == 400
assert call("amy", "add", {"code": "ZZZZZZZZ"})[0] == 404
assert call("amy", "add", {"code": "abc"})[0] == 400
assert call("nobody", "add", {"code": code_amy})[0] == 409
assert call("amy", "sync", {}, token="not-a-token")[0] == 401
assert call("amy", "sync", {}, token="a.b.c")[0] == 401

# A request, seen by both, then accepted; codes are typed any which way
after = ok("amy", "add", {"code": f"{code_bo[:4].lower()}-{code_bo[4:]}"})
assert after["outgoing"] == [{"code": code_bo, "name": "Bo"}], after
seen = ok("bo", "sync", {"name": "Bo", "stats": odd})
assert seen["incoming"] == [{"code": code_amy, "name": "Amy"}], seen
assert call("bo", "accept", {"code": code_bo})[0] == 404
friends = ok("bo", "accept", {"code": code_amy})
assert friends["incoming"] == [] and [f["name"] for f in friends["friends"]] == ["Amy"]
amy_seen = friends["friends"][0]["stats"]
assert amy_seen == {"two_weeks": 12.3, "total": 456.8, "today": 1.5, "week": 6.2, "level": 23, "streak": 4, "status": "online", "active": "Krita"}, amy_seen
bo_seen = ok("amy", "sync", {"name": "Amy", "stats": stats})["friends"][0]
assert bo_seen["stats"]["two_weeks"] == 336 and bo_seen["stats"]["level"] == 0 and bo_seen["stats"]["active"] is None, bo_seen
assert call("amy", "add", {"code": code_bo})[0] == 409
# Showing as offline hides drawing; an unknown status counts as online
ok("amy", "sync", {"name": "Amy", "stats": {**stats, "status": "offline"}})
assert ok("bo", "sync", {"name": "Bo", "stats": odd})["friends"][0]["stats"]["active"] is None
ok("amy", "sync", {"name": "Amy", "stats": {**stats, "status": "busy"}})
assert ok("bo", "sync", {"name": "Bo", "stats": odd})["friends"][0]["stats"]["status"] == "online"

# Two people adding each other become friends at once
cy = ok("cy", "sync", {"name": "Cy", "stats": {}})
ok("cy", "add", {"code": code_amy})
assert sorted(f["name"] for f in ok("amy", "add", {"code": cy["me"]["code"]})["friends"]) == ["Bo", "Cy"]
assert len(ok("amy", "sync", {"name": "Amy", "stats": stats})["friends"]) == 2

# Declining, cancelling, unfriending
dee = ok("dee", "sync", {"name": "Dee", "stats": {}})
ok("dee", "add", {"code": code_amy})
assert ok("amy", "decline", {"code": dee["me"]["code"]})["incoming"] == []
ok("dee", "add", {"code": code_amy})
assert ok("dee", "remove", {"code": code_amy})["outgoing"] == []
assert ok("amy", "sync", {"name": "Amy", "stats": stats})["incoming"] == []
assert [f["name"] for f in ok("bo", "remove", {"code": code_amy})["friends"]] == []
assert [f["name"] for f in ok("amy", "sync", {"name": "Amy", "stats": stats})["friends"]] == ["Cy"]

# Leaving deletes the person everywhere
assert ok("cy", "leave") == {"left": True}
assert ok("amy", "sync", {"name": "Amy", "stats": stats})["friends"] == []
assert call("amy", "add", {"code": cy["me"]["code"]})[0] == 404

# Wrong path and method
assert call("amy", "nope")[0] == 404
print("friends server: all checks passed")
