#!/usr/bin/env python3
"""measure - daily token usage per Hermes profile, with an optional split for one loop.

  measure.py                 last 7 days
  measure.py 14              last N days
  measure.py 7 --pattern "Lifeline"    split sessions whose first user message matches
  measure.py 7 --quality               add completed work per day when a board db exists
  measure.py 7 --json                  machine readable

Token columns come from the sessions table (input_tokens, output_tokens, cache_read_tokens).
Raw cache reads dominate every total; fresh input and output are shown separately because
they are the parts that cost real money.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import glob
import json
import os
import sqlite3

HOME = os.path.expanduser("~")
HERMES = os.path.join(HOME, ".hermes")


def databases() -> dict:
    dbs = {"default": os.path.join(HERMES, "state.db")}
    for p in glob.glob(os.path.join(HERMES, "profiles", "*", "state.db")):
        dbs[os.path.basename(os.path.dirname(p))] = p
    return {k: v for k, v in dbs.items() if os.path.exists(v)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("days", nargs="?", type=int, default=7)
    ap.add_argument("--pattern", default="", help="substring of the first user message to split out")
    ap.add_argument("--quality", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    per_day = collections.defaultdict(collections.Counter)
    split = collections.defaultdict(int)
    split_runs = collections.defaultdict(int)

    for name, db in databases().items():
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        q = ("select id, started_at, coalesce(input_tokens,0), coalesce(output_tokens,0),"
             " coalesce(cache_read_tokens,0), coalesce(api_call_count,0) from sessions"
             " where started_at is not null")
        for sid, st, fresh, out, cached, calls in con.execute(q):
            day = datetime.datetime.fromtimestamp(float(st)).strftime("%Y-%m-%d")
            c = per_day[day]
            c["tokens"] += fresh + out + cached
            c["fresh"] += fresh
            c["output"] += out
            c["calls"] += calls
            c["sessions"] += 1
            c[name] += fresh + out + cached
            if args.pattern:
                hit = con.execute(
                    "select 1 from messages where session_id=? and role='user' and content like ? limit 1",
                    (sid, f"%{args.pattern}%"),
                ).fetchone()
                if hit:
                    split[day] += fresh + out + cached
                    split_runs[day] += 1

    days = sorted(per_day)[-args.days:]
    if args.json:
        print(json.dumps({d: dict(per_day[d]) for d in days}, indent=1, default=int))
        return 0

    head = f"{'date':11s} {'tokens':>9s} {'fresh':>8s} {'output':>8s} {'calls':>7s} {'tok/call':>9s}"
    if args.pattern:
        head += f" {'split':>9s} {'runs':>5s}"
    print(head + "   (millions of tokens)")
    for d in days:
        c = per_day[d]
        line = (f"{d} {c['tokens']/1e6:9.1f} {c['fresh']/1e6:8.2f} {c['output']/1e6:8.2f} "
                f"{c['calls']:7d} {c['tokens']/max(c['calls'],1)/1000:8.0f}k")
        if args.pattern:
            line += f" {split[d]/1e6:9.1f} {split_runs[d]:5d}"
        print(line)

    if args.quality:
        print("\ncompleted work per day:")
        for db in glob.glob(os.path.join(HERMES, "kanban", "boards", "*", "kanban.db")):
            board = os.path.basename(os.path.dirname(db))
            try:
                con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
                rows = con.execute(
                    "select date(completed_at,'unixepoch','localtime') d, count(*) from tasks"
                    " where completed_at is not null group by d order by d desc limit 5"
                ).fetchall()
                print(f"  {board}: {dict(rows)}")
            except sqlite3.Error:
                continue
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
