# token-saver

What actually makes an agent expensive is not long answers. It is the same large context
being sent again on every model call, and scheduled jobs that wake an expensive session
when nothing has changed. This skill bundles the four pieces that fix that in practice,
plus the measurement script that proves whether it worked.

Measured on a live agent office (Oct 2026), after the gate below went in:

| metric | before | after |
|---|---|---|
| scheduled supervisor runs per day | 148 | <= 32 |
| tokens per day for that agent | 438 M | 76 M in the first hour of gating (98% drop in that hour) |
| supervisor runs that produced any output | 0 of the last 60 | same (they were pure waste) |

Method and the full case: `references/case-scheduled-loop.md`.

## What is inside

| file | what it does |
|---|---|
| `scripts/thin.py` | run a command, print only the lines that matter plus a summary line |
| `scripts/once.py` | skip a repeated command whose inputs have not changed |
| `scripts/gate.py` | wake an expensive scheduled session only when state actually changed |
| `scripts/measure.py` | daily token report per profile, with an optional split for one loop |
| `SKILL.md` | the rules an agent should follow, ready to drop into its instructions |

## Install

```bash
git clone https://github.com/<owner>/token-saver ~/.hermes/skills/token-saver
python3 ~/.hermes/skills/token-saver/scripts/measure.py 7    # baseline, save the numbers
```

Copy the rule block from `SKILL.md` (section "Rules to paste") into the agent's instruction
file, for example `SOUL.md` or `AGENTS.md`.

Put the gate in front of any scheduled job that starts an LLM session:

```bash
python3 ~/.hermes/skills/token-saver/scripts/gate.py --config ~/.hermes/gate-loop.json || exit 0
```

See `examples/gate-example.json` for the config shape.

## The one rule that matters

Cost per turn = number of model calls x size of the context sent. Cutting the number of
calls wins more than cutting the text. Cutting the text that gets re-sent wins more than
cutting the final answer.

## License

MIT, (c) Raihan Andi Saungnaga.
