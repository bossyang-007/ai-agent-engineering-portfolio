# Changelog

All notable changes are recorded here, newest first. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

This repository is maintained in small daily increments. Each entry should name one verifiable improvement — not a cosmetic reshuffle.

## 2026-11-16

### Added

- `05-self-evolving-qc-agent/verify_gate.py` — an offline, read-only, standard-library-only
  script that turns the README claim "four independent gate checks, any one failing rejects"
  into executable, asserted evidence. It reads the committed `data/eval_set.json` (88 samples)
  and calls the same `gate.py` functions as `evolve.py`, then asserts: (1) the default 3.0pp
  regression budget REJECTS the candidate for exactly one reason; (2) relaxing the budget to
  20pp lets the same candidate PASS; (3) each of the four checks can be made to fail on its own
  and every single one rejects the change. 27 assertions, exit code 0/1. It never touches the
  versioned `SKILL.md`, `VERSION.json` or `logs/`, so running it cannot dirty the working tree.
- CI: new smoke-test step `Verify the four gate checks are independent` runs the script on every
  push / PR (`.github/workflows/ci.yml`).
- EN README, ZH docs, project-05 README and CONTRIBUTING now document the command and the
  "runnable evidence" section; both project-layout trees list `verify_gate.py`; the Roadmap
  item for reproducible gate evidence is checked off.

### Verified

- Full CI smoke set on Python 3.13.14 (deps installed from `requirements.txt`):
  `01-langgraph-agent/agent.py` (exit 0), `evolve.py` default (REJECT, exit 0),
  `evolve.py --dry-run` (REJECT, exit 0), `evolve.py --regression-budget 20` (PASS v1→v2,
  exit 0), the incremental-patch assertion (108 original lines preserved, +4), and the new
  `verify_gate.py` (27/27 assertions passed, exit 0).
- Static: `python -m py_compile` on all five `.py` files (OK); Markdown link / layout-tree
  consistency checked — no new broken links introduced by this change. (Five pre-existing
  relative links in the ZH project table still use root-level paths from `docs/`; left
  untouched as a separate future increment.)
- Runtime artifacts from the relaxed-budget run (`config/skills/.../SKILL.md` → v2,
  `VERSION.json`, `logs/evolution_log.jsonl`) were reverted before committing; SKILL.md is
  back to the 108-line v1 baseline and only the intended files remain modified.

### Repository baseline (GitHub REST API, this run)

- stars **1**, forks **0**, watchers **0** — vs 2026-11-14 baseline (0 / 0 / 0): stars +1,
  forks and watchers unchanged.
- `description` present and unchanged; all 11 `topics` present and unchanged. Metadata was
  intact, so no PATCH/PUT repair was needed today.

## 2026-11-14

### Added

- `CONTRIBUTING.md` — offline-first contribution rules, local verification commands, and good-first-issue ideas.
- `CHANGELOG.md` — this file, as the dated record of daily increments.
- README `At a glance` table (audience / reusable parts / time to first run / core idea) and a table of contents.
- README `Roadmap & contributing` section with concrete next increments and an explicit invitation to star or open an issue.
- Language switcher at the top of the README linking the Chinese documentation.

### Changed

- README badge row now makes the "no API key, fully offline" property visible up front.
- `Project layout` tree updated to list `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `LICENSE`, `requirements.txt` and the CI workflow.

### Repository metadata (GitHub settings, not files)

- Set the repository `description` to a keyword-rich one-line summary so it reads well in search results and link previews.
- Added 11 topics: `ai-agent`, `agentic-ai`, `langgraph`, `mcp`, `model-context-protocol`, `agent-skills`, `spec-driven-development`, `llm-evaluation`, `self-evolving-agent`, `regression-testing`, `python`.
- These live in GitHub's repository settings, not in the file tree — they cannot be reproduced by cloning this repository.

### Notes

- Repository baseline before this increment: 0 stars, 0 forks, 0 watchers, empty `description`, no `topics`, single commit, last pushed 2026-11-04. The missing metadata was filled in the same day, see above.
- No runtime behaviour changed. All existing scripts, evaluation data and gate thresholds are untouched.
