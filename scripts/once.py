#!/usr/bin/env python3
"""once - do not run the same command twice under the same conditions.

Key = task name + hash of the command + hash of any file the command names.
If the previous run succeeded and the cache is fresh, print its summary instead of running.

  once --key unit-tests -- go test ./service
  once --key build-web --ttl 168 -- npm run build
  once --key unit-tests --ttl 0 -- go test ./service    # force a re-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

STORE = Path.home() / ".hermes/state/once"
KEEP_LINES = 12


def file_stamp(path: str) -> str:
    try:
        st = Path(path).stat()
        return f"{path}:{int(st.st_mtime)}:{st.st_size}"
    except OSError:
        return f"{path}:none"


def key_hash(cmd: str) -> str:
    h = hashlib.sha256(cmd.encode())
    for token in cmd.split():
        if ("/" in token or token.endswith((".go", ".ts", ".tsx", ".py", ".json"))) and Path(token).exists():
            h.update(file_stamp(token).encode())
    return h.hexdigest()[:20]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True)
    ap.add_argument("--ttl", type=int, default=24, help="hours the cached result stays valid")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    cmd = " ".join(args.cmd).lstrip("- ")
    if not cmd:
        print("[once] empty command", file=__import__("sys").stderr)
        return 2

    STORE.mkdir(parents=True, exist_ok=True)
    path = STORE / f"{args.key}.json"
    digest = key_hash(cmd)

    try:
        prev = json.loads(path.read_text())
    except (OSError, ValueError):
        prev = None

    if prev and prev.get("hash") == digest and prev.get("rc") == 0:
        age_h = (time.time() - prev.get("at", 0)) / 3600
        if age_h <= args.ttl:
            print(f"[once] SKIPPED (passed {age_h:.1f}h ago, same inputs): {cmd}")
            for line in prev.get("tail", []):
                print(line[:300])
            print("[once] use --ttl 0 to force a re-run.")
            return 0

    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=args.timeout)
    out = ((p.stdout or "") + (p.stderr or "")).splitlines()
    print(f"[once] RAN rc={p.returncode} lines={len(out)}: {cmd}")
    for line in out[-KEEP_LINES:]:
        print(line[:300])

    if p.returncode == 0:
        path.write_text(json.dumps({"hash": digest, "rc": 0, "at": time.time(), "tail": out[-KEEP_LINES:]}))
    return p.returncode


if __name__ == "__main__":
    raise SystemExit(main())
