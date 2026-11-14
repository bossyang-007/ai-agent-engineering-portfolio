# Contributing

Thanks for taking the time. This repository is a compact reference implementation, so the bar for a change is **"can a reader verify this in two minutes on a laptop with no credentials?"**

## Ground rules

1. **Stay offline by default.** Every script must run without an API key, a cloud account or network access. If you add an integration that needs a live service, put it behind an explicit flag and keep the deterministic path as the default.
2. **Never invent results.** If you change the evaluation set, the gate thresholds or the reported scores, include the exact command and its real output. Synthetic data must be labelled as synthetic.
3. **Keep the admission gate honest.** Changes to `05-self-evolving-qc-agent/gate.py` need a counter-example that shows which check would otherwise have been bypassed.
4. **Patches to versioned skills are incremental.** Append to the designated anchor paragraphs; do not rewrite `SKILL.md`. CI verifies that every original line survives.
5. **Keep EN / ZH in sync.** If you change a section of `README.md`, mirror it in `docs/README.zh-CN.md` (a short translated summary is fine for minor edits).

## Local setup

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt

python 01-langgraph-agent/agent.py
python 02-mcp-server/server.py
python 05-self-evolving-qc-agent/evolve.py
python 05-self-evolving-qc-agent/evolve.py --dry-run
python 05-self-evolving-qc-agent/evolve.py --regression-budget 20
```

The last command deliberately relaxes the regression budget so you can watch a candidate ship. CI runs the same set on Python 3.11 — see `.github/workflows/ci.yml`.

## Proposing a change

- **Small, single-purpose PRs** are easiest to review. One idea per PR.
- Describe: the failure mode you observed, the minimal change, and how you verified it.
- Add a dated line to `CHANGELOG.md` under `Unreleased` (or the current date).
- For a new example or design document, explain which of the five projects it belongs to and what question it answers.

## Good first contributions

- A second evaluation set with a documented generation procedure
- A diagram of the four-stage loop for the README roadmap
- A port of one example to a different agent framework, kept behind its own directory
- Translations and typo fixes in `docs/`

Open an issue first if you are unsure whether an idea fits. A concrete counter-example or a failing command is the most useful thing you can bring.
