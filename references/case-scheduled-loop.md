# Case: a supervisor loop that burned 1.35 B tokens

Context: a Hermes agent office. The lead agent ran a supervisor loop meant to check that
worker agents were not stuck. A root cron entry ran the supervisor script every 2 minutes.

## What the numbers said

| day | tokens for the lead agent | of which the loop | loop runs |
|---|---|---|---|
| day 1 | 287 M | 174 M | 87 |
| day 2 | 749 M | 259 M | 151 |
| day 3 | 267 M | 256 M | 160 |
| day 4 | 300 M | 294 M | 133 |
| day 5 | 373 M | 368 M | 165 |

Five days, 696 runs, 1.35 B tokens. Of the last 60 runs, 60 printed `[SILENT]`. Nothing was
found, nothing was done.

Per run: about 2.2 M tokens, 19 model calls, 46 messages, roughly 115 k tokens of context per
call.

## Why the existing "healthy" guard never fired

The script already had a branch: if there were no alerts, skip when the last healthy run was
less than 10 minutes ago. The alert file still contained two tasks that had already been
acknowledged, so the alert count was never zero and the branch never applied. A guard that
depends on a file nobody cleans is not a guard.

## The fix

`gate.py` in front of the expensive session. Fingerprint sources:

- `sqlite` on the work board, rows with status running / ready / review / blocked / triage,
  including claim expiry (an expired claim means a worker died, which must wake the agent)
- `file` on the alert file
- `cmd` on `pgrep -fc "worker process"`

Skip when the fingerprint is unchanged and the heartbeat (45 min) is not due. The one-minute
sensor stays untouched.

## What happened after

In the first hour, the loop went from 11 runs and 22-31 M tokens per hour to 1 run and 0.3 M.
Runs still happen when the board actually changes, which is the point: the agent wakes for
work, not for the clock.

Note on reading totals: same-day numbers taken from session rows can shift, because resumed
sessions get re-attributed to their original row. Use the gateway usage log for stable daily
totals.
