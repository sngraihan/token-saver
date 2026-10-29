---
name: token-saver
description: "Cut agent token spend without losing results: thin large command output, skip repeated work, gate scheduled LLM sessions on real state changes, and measure daily usage per profile. Trigger: 'tokens too expensive', 'why is this agent burning tokens', 'reduce token use', a cron job that wakes an agent every few minutes, or raw log output filling the context."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [token, cost, context, cron, supervisor, measurement]
---

# Token Saver

## When to use
- Token or cost per day jumps while the amount of real work stays the same.
- A scheduled job starts an agent session on a fixed timer.
- Command output dominates the conversation.
- You need proof a saving actually happened, not a claim.

## Rules to paste (agent instructions)

1. One shell call per step: combine related checks with `;` instead of poking one command at a time.
2. Cut output at the source: `| head -40`, a match filter, or `thin.py`. Never dump a full log or table.
3. Load a skill file at most once per session. Never re-read the same skill.
4. Read a file once; keep the facts in notes instead of reading it again.
5. Identical work repeated -> `once.py --key <name> -- <cmd>`.
6. Stop when the answer is in hand. No extra confirmation passes.

Quality gates (money, auth, visual checks, live verification) stay in full. Only duplicate
sending is cut.

## Step 1: measure before touching anything

```bash
python3 scripts/measure.py 7                  # last 7 days, all profiles
python3 scripts/measure.py 7 --pattern "Lifeline"   # split out one loop
python3 scripts/measure.py 7 --quality        # plus completed work per day, if a board table exists
```

Record the numbers somewhere durable. Without a baseline, "it feels cheaper" is the only
thing you will ever be able to report.

## Step 2: find the loop, not the answer

A quiet loop is usually the biggest line item. Detection:

```bash
sqlite3 file:~/.hermes/state.db?mode=ro \
 "select date(started_at,'unixepoch','localtime') d, source, count(*),
  sum(input_tokens+cache_read_tokens)/1e6
  from sessions where started_at is not null group by d, source order by d desc limit 20"
```

Many short sessions with `source='cli'` means a script or cron is starting agent runs.
Group the first user message of those sessions to find which prompt repeats. Then count how
many of those runs produced anything:

```bash
grep -L '\[SILENT\]' ~/.hermes/logs/<loop>/*.log | wc -l
```

If that count is zero, the loop is pure spend and a gate is the fix.

## Step 3: gate the loop

`scripts/gate.py` hashes the state you name in a small JSON config. The expensive session is
only started when the hash changed, or when a heartbeat interval has passed.

```bash
python3 scripts/gate.py --config gate-loop.json           # exit 0 = run, exit 1 = skip
python3 scripts/gate.py --config gate-loop.json --force   # ignore state, run anyway
```

Three source types, mix them freely:

| type | meaning |
|---|---|
| `sqlite` | `path` + `query`, rows are hashed; use it for a work board or task table |
| `file` | `path`, content is hashed; use it for an alert or inbox file |
| `cmd` | `cmd`, stdout is hashed; use it for `pgrep -c` worker counts |

Rules that keep a gate honest:
- The cheap sensor stays on its fast timer. The gate only guards the expensive session.
- Keep a heartbeat (30-45 min) so a silent stall cannot hide forever.
- Prefer reading the state file directly with sqlite over calling a CLI on every tick.

## Step 4: verify after a few days

Report three numbers, never one: tokens per day, expensive runs per day, and completed work
per day. If work went down, the gate is too aggressive.

## Pitfalls

- **Gating on a stale state file.** If an alert file keeps entries that were already handled,
  the "everything is healthy" branch never fires and the gate never skips. Clear or age out
  handled entries.
- **Switching models mid-conversation** to save money. It invalidates the cached prefix and
  usually costs more. Route at task start, not per turn.
- **Counting raw tokens as money.** Most of the total is cache reads. Report fresh input,
  cache read and output separately, and say which one you cut.
- **Compressing the instruction files** (memory, rules) for a quick 40%. It removes decisions
  the agent relied on. Do it only with the owner's approval, one section at a time, and diff
  the content afterwards.
- **Session rows get re-attributed** when a session is resumed or merged, so a same-day total
  read from sessions can move. Prefer the gateway's own usage log for a stable daily total.

## Support files
- `references/case-scheduled-loop.md` - the measured case: 696 runs, 1.35 B tokens, zero output,
  and the three cause worth checking first.
