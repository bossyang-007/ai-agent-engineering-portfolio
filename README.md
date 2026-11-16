# AI Agent Engineering Portfolio — From Analytics to Self-Evolving Systems

[English](README.md) · [简体中文](docs/README.zh-CN.md) · [环境搭建 / 踩坑记录](docs/environment-setup.md)

> From data-quality engineering to safely self-improving agents.
> Three runnable implementations and two design documents covering LangGraph orchestration, MCP protocol layer, Skill design,
> Spec-Driven Development, and a self-evolving agent with an admission gate.
> **Everything runs fully offline — no API key, no cloud account, no paid service.**

[![CI](https://github.com/bossyang-007/ai-agent-engineering-portfolio/actions/workflows/ci.yml/badge.svg)](https://github.com/bossyang-007/ai-agent-engineering-portfolio/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.x-green.svg)](https://langchain-ai.github.io/langgraph/)
[![MCP](https://img.shields.io/badge/MCP-2.x-purple.svg)](https://modelcontextprotocol.io/)
[![No API key needed](https://img.shields.io/badge/API%20key-none-success.svg)](#quick-start)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

---

## At a glance

| | |
|---|---|
| **Who this is for** | Engineers moving past "the agent demos well" toward agents that can be **evaluated, versioned and trusted**. |
| **What you can copy** | A stateful LangGraph graph, an MCP server with dual transports, a Skill specification, an SDD acceptance-criteria walkthrough, and a gated self-improvement loop. |
| **Time to first run** | About two minutes: `pip install -r requirements.txt`, then run any script below. No credentials. |
| **The one idea** | **Allow evolution, forbid silent regression** — every self-modification has to pass an admission gate first. |

## Contents

- [Why this repository exists](#why-this-repository-exists)
- [The five projects](#the-five-projects)
- [Project 05 — the one that ties them together](#project-05--the-one-that-ties-them-together)
- [Quick start](#quick-start)
- [Project layout](#project-layout)
- [Why a QC-attribution scenario](#why-a-qc-attribution-scenario)
- [Scope and limitations](#scope-and-limitations)
- [Roadmap & contributing](#roadmap--contributing)
- [License](#license)

---

## Why this repository exists

Most agent demos stop at *"the agent works"*. This repository focuses on a harder question:
**how can an agent improve from feedback without silently regressing?**

Four recurring failure modes motivate the design: misaligned metric definitions, boundary
misclassification, shallow root-cause analysis, and overconfident conclusions. Each can look like an
improvement in aggregate metrics while degrading a specific subset — which is why the fifth project
puts an admission gate, a regression budget and target-subset scoring in front of every
self-modification.

---

## The five projects

| # | Project | Stack | The question it answers |
|---|---------|-------|------------------------|
| 01 | [LangGraph Stateful Agent](01-langgraph-agent/) | LangGraph, TypedDict State, reducers, checkpoint, conditional edges | How do you build an agent that holds state, branches, and resumes after interruption? |
| 02 | [MCP Server](02-mcp-server/) | MCP Python SDK 2.x, Tools / Resources / Prompts, annotations | How do you expose capabilities to any MCP host as a protocol-level primitive? |
| 03 | [Skill Definition](03-skill/) | Progressive disclosure, procedural knowledge, pitfalls, verification checklist | How do you write a skill a model triggers correctly and executes correctly? |
| 04 | [Spec-Driven Development](04-sdd-demo/) | Spec Kit methodology, acceptance criteria, failure modes | When code gets cheap, defining "what counts as correct" becomes the scarce skill. |
| 05 | [Self-Evolving QC Agent](05-self-evolving-qc-agent/) | Experience feedback loop, admission gate, regression budget, incremental patch | How do you let an agent improve from human corrections **without letting it silently regress?** |

---

## Project 05 — the one that ties them together

```
human corrections → skill patch proposal → evaluation gate → versioned release
        ↑                                                          │
        └──────────────── next run loads the winner ─────────────┘
```

The gate enforces **four independent checks** — a sample-size prerequisite, target-subset gain,
regression budget, and held-out generalization. Any one failing rejects the change. The log below is
translated from the program's Chinese output:

```
[1/4] Collecting corrections : 18 records across 4 error-cause categories
[2/4] Proposing skill patch  : 4 incremental patches
[3/4] Evaluation gate
      baseline v1 : target 0.0% / holdout 0.0% / regression 50.0%
      candidate v2: target 68.2% / holdout 65.4% / regression 32.5%
      verdict     : REJECT | regression budget exceeded: 17.50pp > 3.0pp
[4/4] Controlled release     : skill stays at v1, full evidence retained
```

### Four design decisions worth arguing about

**1. A proposed skill is untrusted until proven.**
An agent-generated skill patch may be right — or it may be a hallucinated rule. Adopting it unchecked
lets one bad revision poison every later task, and the error gets baked into the skill.
So every patch must beat the baseline on a held-out set.

**2. Overall accuracy improvement does not count.**
With 1,000 samples where the target error cause covers only 80, fixing 40 of them moves the overall
number by 4 points — but if the same change broke 35 unrelated samples, the net effect is nearly zero.
The gate therefore always scores the **target subset first**. Overall accuracy is reference only.

**3. The regression budget is independent of the gain metric.**
A revision can lift the target subset by 10% while dropping everything else by 15% — overall still down.
Both directions must be checked. This is the **regression budget** principle:
**allow evolution, forbid silent regression.**

**4. Patches are incremental, never full rewrites.**
A generated rewrite replaces a whole document, so any rule not repeated in the output is lost —
including entries accumulated over earlier iterations. The loss is silent: the result still looks
complete and passes a quick read. To make that structurally impossible, proposals may only append
to four designated anchor paragraphs; the "Pitfalls" section is read-only for the proposer, because
accumulated counter-examples are the most expensive content to reconstruct.

Verified: the skill goes from **108 lines to 112 lines**, four anchors each gaining one line,
with every existing paragraph preserved byte-for-byte.

### Verify the gate yourself (runnable evidence)

The four checks above are not just described — they are **executable evidence**. `verify_gate.py`
recomputes the baseline and candidate scores from the committed `data/eval_set.json` (88 samples)
using the very same `gate.py` functions as `evolve.py`, then asserts that:

- the default 3.0pp regression budget **rejects** the candidate for exactly one reason;
- relaxing the budget to 20pp lets the **same** candidate **pass**;
- each of the four checks can be made to fail **on its own**, and every single one rejects the change.

It uses only the standard library, runs offline, and is read-only — it never touches the versioned
skill or the logs, so running it cannot dirty your working tree. Run it and read the verdict per
scenario:

```bash
python 05-self-evolving-qc-agent/verify_gate.py
# OK: 27/27 assertions passed.
```

Any broken assertion makes the script exit non-zero, and CI runs it on every push — so the
"allow evolution, forbid silent regression" claim cannot silently rot.

---

## Quick start

```bash
# Python 3.11+
pip install -r requirements.txt

# 01 — LangGraph agent (runs with a mock LLM, no API key needed)
python 01-langgraph-agent/agent.py

# 02 — MCP server
python 02-mcp-server/server.py              # stdio transport
python 02-mcp-server/server.py --http       # Streamable HTTP transport

# 05 — self-evolving loop (deterministic, offline)
python 05-self-evolving-qc-agent/evolve.py
python 05-self-evolving-qc-agent/evolve.py --dry-run
python 05-self-evolving-qc-agent/evolve.py --regression-budget 20   # relax and let it ship

# 05 — reproduce the four gate checks as executable evidence (offline, read-only)
python 05-self-evolving-qc-agent/verify_gate.py
```

---

## Project layout

```
.
├── README.md                       # English landing page (this file)
├── CONTRIBUTING.md                 # how to propose a change
├── CHANGELOG.md                    # dated log of each increment
├── LICENSE
├── requirements.txt
├── .github/workflows/ci.yml         # offline smoke test on every push / PR
├── 01-langgraph-agent/
│   └── agent.py                    # stateful agent: reducer-merged state, conditional edges, checkpoint resume
├── 02-mcp-server/
│   └── server.py                   # MCP server: 3 tools / 2 resources / 1 prompt, dual transport
├── 03-skill/
│   └── SKILL.md                    # skill definition: progressive disclosure + pitfalls + checklist
├── 04-sdd-demo/
│   └── README.md                   # spec-driven development walkthrough
├── 05-self-evolving-qc-agent/
│   ├── evolve.py                   # four-stage loop: collect → propose → gate → release
│   ├── gate.py                     # admission gate: regression budget + target-subset scoring
│   ├── verify_gate.py              # runnable evidence: recomputes & asserts all four gate checks
│   ├── config/skills/.../SKILL.md  # versioned skill under management
│   ├── data/                       # corrections + three-way split evaluation set
│   └── logs/                       # full audit trail of every proposal and verdict
└── docs/
    ├── README.zh-CN.md             # 中文版说明
    └── environment-setup.md        # 环境搭建与踩坑记录
```

---

## Why a QC-attribution scenario

The scenario is **complaint bad-case attribution**: given a mis-classified case, decide which of
four error causes applies and what repair it needs. It was chosen because it makes the loop
measurable:

1. **The evaluation set has distinct, checkable failure modes.** The four categories
   (misaligned definitions / boundary misclassification / shallow attribution / overconfident
   conclusions) each have an unambiguous expected label.
2. **The extracted rules have operational meaning.** A learned rule is "how to fix this class of
   error", not a stylistic preference.
3. **The loop is measurable.** Held-out bad-case batches let you quantify whether a revision helped.

Critically, the four error causes require **different** repairs: some need a definition fix, some need
new few-shot examples, some need a process change. A system that applied the same "fix" every time
would not actually have learned attribution.

---

## Scope and limitations

Implemented and verified in this repository:
- A complete closed loop — correction ingestion, patch proposal, gated evaluation, controlled
  release — with all four stages kept independent
- Why both a regression budget and target-subset scoring are required
- Why incremental patching is used, and how a full rewrite can discard accumulated rules
- How the three-way evaluation set is built, and where the four error-cause categories come from

Limitations:
- The design applies general engineering principles for controlled change and regression budgets;
  this repository does not propose a new paradigm.
- This is a compact, fully offline reference implementation. It has not been run against production
  traffic or a live model API.
- The evaluation set is synthetic, self-built and small (88 samples); scoring is deterministic.
  The result demonstrates that the gate rejects a regressing change, not a general improvement in
  model accuracy.

---

## Roadmap & contributing

Next increments we would like to add — PRs welcome, see [CONTRIBUTING.md](CONTRIBUTING.md):

- [x] Reproducible, executable evidence for the four gate checks — added as [`verify_gate.py`](05-self-evolving-qc-agent/verify_gate.py), run on every push; see [Verify the gate yourself](#verify-the-gate-yourself-runnable-evidence)
- [ ] A real LLM-backed adapter behind the same admission gate, so the deterministic mock can be compared against a live model
- [ ] CI matrix across Python 3.11 / 3.12 / 3.13
- [ ] A second gate dimension: cost and latency budget alongside the quality budget
- [ ] Larger evaluation sets with documented provenance
- [ ] A short architecture diagram for the four-stage loop

Each dated change is recorded in [CHANGELOG.md](CHANGELOG.md).

If this repository saved you design time, **a star is the cheapest way to say so** — it also helps other engineers find the regression-budget pattern. Found a flaw in the gate? Please open an issue instead: a concrete counter-example is worth more than a star.

---

## License

MIT — see [LICENSE](LICENSE). Scenario data is synthetic and contains no real customer information.
