"""Track server HEAD and per-peer pull acknowledgments."""

import json
import os
import time

SYNC_STATE_FILE = os.path.expanduser("~/.lab-sharing/sync_state.json")


def _load():
    if not os.path.exists(SYNC_STATE_FILE):
        return {"server_head": None, "peers": {}}
    try:
        with open(SYNC_STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"server_head": None, "peers": {}}


def _save(state):
    os.makedirs(os.path.dirname(SYNC_STATE_FILE), exist_ok=True)
    with open(SYNC_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def record_server_head(commit_hash: str):
    state = _load()
    state["server_head"] = (commit_hash or "")[:8]
    state["server_head_time"] = time.time()
    _save(state)


def record_pull_ack(peer_ip: str, hostname: str, commit_hash: str):
    state = _load()
    peers = state.setdefault("peers", {})
    peers[peer_ip] = {
        "hostname": hostname,
        "last_ack": (commit_hash or "")[:8],
        "time": time.time(),
    }
    _save(state)


def peer_sync_summary(server_head: str | None = None) -> list[dict]:
    """Return peer rows: ip, hostname, last_ack, synced (bool)."""
    state = _load()
    head = (server_head or state.get("server_head") or "")[:8]
    rows = []
    for ip, info in state.get("peers", {}).items():
        ack = (info.get("last_ack") or "")[:8]
        rows.append({
            "ip": ip,
            "hostname": info.get("hostname", ip),
            "last_ack": ack,
            "synced": bool(head and ack and head == ack),
            "time": info.get("time"),
        })
    return rows


def format_sync_status_line(server_head: str | None = None) -> str:
    state = _load()
    head = (server_head or state.get("server_head") or "?")[:8]
    peers = peer_sync_summary(head)
    if not peers:
        return f"Server @ {head} — no client pull confirmations yet"
    parts = []
    for p in peers:
        if p["synced"]:
            parts.append(f"{p['hostname']}: synced @ {p['last_ack']}")
        else:
            parts.append(f"{p['hostname']}: not synced (at {p['last_ack'] or '?'})")
    return f"Server @ {head} | " + " · ".join(parts)
