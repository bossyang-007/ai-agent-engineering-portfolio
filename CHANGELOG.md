# Changelog

All notable changes are recorded here, newest first. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

This repository is maintained in small daily increments. Each entry should name one verifiable improvement — not a cosmetic reshuffle.

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
