#!/usr/bin/env python3
"""thin - run a command, print only the lines that matter plus a summary.

Keeps a 40 KB log out of the context window. Same result, a fraction of the tokens.

  thin "go test ./..." --match "FAIL|PASS|ok " --max 20
  thin "ssh host 'tail -100 app.log'" --match "ERROR|panic" --max 15
  thin "git -C repo log --oneline" --tail 8
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", help="shell command to run")
    ap.add_argument("--match", default="", help="regex; print only matching lines")
    ap.add_argument("--tail", type=int, default=0, help="print the last N lines (ignores --match)")
    ap.add_argument("--max", type=int, default=25, help="hard cap on printed lines (default 25)")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    p = subprocess.run(args.command, shell=True, capture_output=True, text=True, timeout=args.timeout)
    out = (p.stdout or "") + (p.stderr or "")
    lines = out.splitlines()

    if args.tail:
        picked = lines[-args.tail:]
        why = f"last {args.tail} lines"
    elif args.match:
        rx = re.compile(args.match)
        picked = [ln for ln in lines if rx.search(ln)]
        why = f"match /{args.match}/"
    else:
        picked = lines[-args.max:]
        why = f"last {args.max} lines"

    print(f"[thin] rc={p.returncode} total_lines={len(lines)} shown={min(len(picked), args.max)} ({why})")
    for ln in picked[: args.max]:
        print(ln[:400])
    if len(picked) > args.max:
        print(f"[thin] ... {len(picked) - args.max} more lines hidden")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.TimeoutExpired:
        print("[thin] command timed out", file=sys.stderr)
        raise SystemExit(124)
