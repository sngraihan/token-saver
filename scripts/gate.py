#!/usr/bin/env python3
"""gate - start an expensive scheduled session only when state actually changed.

A cron entry can stay on a fast timer while the costly agent session behind it is skipped
until something moves. The gate hashes the state you describe in a JSON config and compares
it with the previous run.

  gate.py --config loop.json            # exit 0 = run the expensive part, 1 = skip
  gate.py --config loop.json --force    # ignore the stored state
  gate.py --config loop.json --show     # print the fingerprint and the verdict, never skip

Config:

  {
    "name": "supervisor-loop",
    "heartbeat_minutes": 45,
    "sources": [
      {"type": "sqlite",
       "path": "~/.hermes/kanban/boards/main/kanban.db",
       "query": "select id,status from tasks where status in ('running','ready','blocked') order by id"},
      {"type": "file", "path": "~/.hermes/state/alerts.json"},
      {"type": "cmd",  "cmd": "pgrep -fc worker"}
    ]
  }

Source types: sqlite (rows are hashed), file (content is hashed), cmd (stdout is hashed).
State lives in ~/.hermes/state/<name>-gate.json. A failed source makes the gate run rather
than skip: a broken check must never hide work.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

STATE_DIR = Path.home() / ".hermes/state"


def expand(p: str) -> str:
    return os.path.expanduser(p)


def from_sqlite(src: dict) -> str:
    path = expand(src["path"])
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    rows = con.execute(src["query"]).fetchall()
    con.close()
    return json.dumps([list(r) for r in rows], default=str)


def from_file(src: dict) -> str:
    path = expand(src["path"])
    if not os.path.exists(path):
        return "missing"
    return Path(path).read_text(errors="replace")


def from_cmd(src: dict) -> str:
    out = subprocess.run(src["cmd"], shell=True, capture_output=True, text=True, timeout=60)
    return (out.stdout or "") + (out.stderr or "")


READERS = {"sqlite": from_sqlite, "file": from_file, "cmd": from_cmd}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    cfg = json.loads(Path(expand(args.config)).read_text())
    name = cfg.get("name", "gate")
    heartbeat = int(cfg.get("heartbeat_minutes", 45)) * 60
    state_path = STATE_DIR / f"{name}-gate.json"

    parts = []
    for src in cfg.get("sources", []):
        kind = src.get("type")
        if kind not in READERS:
            print(f"gate: unknown source type {kind}", file=sys.stderr)
            return 0  # fail open: run the expensive part
        try:
            parts.append(f"{kind}:{READERS[kind](src)}")
        except Exception as exc:  # noqa: BLE001 - any reader failure must fail open
            print(f"gate: source failed ({kind}: {exc}); running anyway", file=sys.stderr)
            return 0

    fp = hashlib.sha256("\u00a7".join(parts).encode()).hexdigest()[:16]
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except ValueError:
            state = {}

    age = time.time() - float(state.get("last_run", 0))
    changed = state.get("fp") != fp
    verdict = args.force or changed or age > heartbeat

    if args.show:
        print(f"gate: fp={fp} changed={changed} age={int(age)}s heartbeat={int(heartbeat)}s")
        return 0

    if verdict:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({"fp": fp, "last_run": time.time()}))
        print(f"gate: run (changed={changed} age={int(age)}s fp={fp})")
        return 0

    print(f"gate: skip (unchanged, age={int(age)}s fp={fp})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
