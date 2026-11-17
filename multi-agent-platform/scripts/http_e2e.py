"""Live HTTP end-to-end check against a running gateway (http://localhost:8080).

Verifies health, unauthenticated rejection, session creation, streaming chat with
citations, and owner-scoped history. Not part of the automated suite.
"""

from __future__ import annotations

import json
import sys

import httpx

BASE = "http://localhost:8080"
HEADERS = {"X-MS-CLIENT-PRINCIPAL-NAME": "e2e-user"}


def main() -> int:
    checks: list[tuple[str, bool]] = []

    health = httpx.get(f"{BASE}/health", timeout=10).json()
    checks.append(("health ok", health.get("status") == "ok"))

    unauth = httpx.post(f"{BASE}/chat", json={"text": "hi"}, timeout=10)
    checks.append(("unauth chat is 401", unauth.status_code == 401))

    created = httpx.post(f"{BASE}/sessions", headers=HEADERS, timeout=10)
    session_id = created.json()["session_id"]
    checks.append(("session created", bool(session_id)))

    body = {
        "text": "How does the platform ground answers and cite sources?",
        "session_id": session_id,
    }
    resp = httpx.post(f"{BASE}/chat", headers=HEADERS, json=body, timeout=90)
    types: list[str] = []
    answer = ""
    citations = 0
    for line in resp.text.splitlines():
        if line.startswith("data:"):
            event = json.loads(line[len("data:") :])
            types.append(event["type"])
            if event.get("text"):
                answer += event["text"]
            citations += len(event.get("citations") or [])
    checks.append(("stream starts with session", types[:1] == ["session"]))
    checks.append(("stream has citations", citations > 0))
    checks.append(("stream has text", bool(answer.strip())))
    checks.append(("stream completed", types[-1:] == ["completed"]))

    other = httpx.get(
        f"{BASE}/sessions/{session_id}/history",
        headers={"X-MS-CLIENT-PRINCIPAL-NAME": "someone-else"},
        timeout=10,
    )
    checks.append(("history is owner-scoped (404 for others)", other.status_code == 404))

    history = httpx.get(
        f"{BASE}/sessions/{session_id}/history", headers=HEADERS, timeout=10
    ).json()
    checks.append(("history has messages", len(history["messages"]) >= 2))

    print("answer:", answer.strip()[:300])
    print()
    all_ok = True
    for name, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        all_ok = all_ok and ok
    print("\nRESULT:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
