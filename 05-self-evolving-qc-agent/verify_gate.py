"""Reproducible evidence for the admission gate's four independent checks.

Why this file exists
--------------------
The README claims: "The gate enforces four independent checks ... Any one
failing rejects the change." A claim in prose is not evidence. This script
turns it into an executable, self-checking proof that anyone can re-run in
two minutes with no credentials.

It is deliberately:
  * offline and standard-library only -- no API key, no network, no 3rd party;
  * read-only -- unlike evolve.py it never touches SKILL.md, VERSION.json or
    logs/, so running it cannot dirty the working tree;
  * built on the *same* gate.py functions and the committed data/eval_set.json
    that evolve.py uses, so the numbers cannot drift from real behaviour.

What it asserts
---------------
  1. The baseline / candidate scores are reproducible from the committed
     evaluation set (recomputed live, never pasted as a claim).
  2. With the default regression budget (3.0pp) the candidate is REJECTED for
     exactly one reason -- the regression budget (matches a plain evolve.py run).
  3. Relaxing the budget to 20pp lets the *same* candidate PASS (matches
     `evolve.py --regression-budget 20`).
  4. Each of the four checks can be made to fail on its own; every single one
     of them rejects the change. This is the "four independent checks, any one
     failing rejects" property, demonstrated rather than asserted in prose.

No result is invented: every number printed below is computed by
gate.run_evaluation / evaluate_gate from data/eval_set.json. Thresholds used in
the scenarios are explicit, reproducible inputs, not tuned "results".

Usage (from the repo root or this directory):
    python 05-self-evolving-qc-agent/verify_gate.py
    python verify_gate.py

Exit code 0 = all assertions hold; 1 = evidence broke (fail loudly).
"""

from __future__ import annotations

import sys
from pathlib import Path

# gate.py sits next to this file. Python puts the script's own directory on
# sys.path[0], so this import works from both the repo root and this dir.
from gate import GateConfig, evaluate_gate, load_eval_set, run_evaluation

BASE = Path(__file__).parent
EVAL_FILE = BASE / "data" / "eval_set.json"

# Human-readable labels for the four checks, in evaluate_gate()'s order.
CHECKS = (
    "sample-size prerequisite",
    "target-subset gain",
    "regression budget",
    "held-out generalization",
)


class Evidence:
    """Tiny assertion collector: prints every check and tracks pass/fail."""

    def __init__(self) -> None:
        self.total = 0
        self.failed = 0

    def expect(self, condition: bool, label: str) -> None:
        self.total += 1
        if condition:
            print(f"    [OK]   {label}")
        else:
            self.failed += 1
            print(f"    [FAIL] {label}")


def which_checks_fail(result, cfg: GateConfig) -> list[str]:
    """Return which of the four checks are violated, by recomputing each
    comparison from the *measured* numbers and the given thresholds.

    We intentionally do NOT inspect result.failed_checks (which are Chinese
    human-readable strings). Recomputing the four boolean conditions keeps the
    evidence independent of message wording / translation, and lets us verify
    that failed_checks has exactly the right length.
    """
    violated: list[str] = []
    if result.target_samples < cfg.min_target_samples:
        violated.append(CHECKS[0])
    if result.target_gain < cfg.min_target_gain:
        violated.append(CHECKS[1])
    if result.regression > cfg.regression_budget:
        violated.append(CHECKS[2])
    if result.holdout_gain < cfg.min_holdout_gain:
        violated.append(CHECKS[3])
    return violated


def run_scenario(
    ev: Evidence,
    label: str,
    cfg: GateConfig,
    baseline,
    candidate,
    expect_pass: bool,
    expect_only_failing: str | None,
) -> None:
    """Run one gate evaluation and assert its verdict plus independence."""
    result = evaluate_gate(candidate, baseline, cfg)
    violated = which_checks_fail(result, cfg)

    print(f"\n  {label}")
    print(f"    verdict      : {'PASS' if result.passed else 'REJECT'}")
    print(f"    reason       : {result.reason}")
    print(f"    checks failed: {violated or ['(none)']}")

    ev.expect(result.passed == expect_pass,
              f"verdict is {'PASS' if expect_pass else 'REJECT'}")
    # Core invariant: the gate's own failed_checks list must agree exactly with
    # the checks we independently recomputed from the measured numbers.
    ev.expect(len(result.failed_checks) == len(violated),
              f"failed_checks count == independently violated count ({len(violated)})")
    if expect_only_failing is not None:
        # "Any one failing rejects the change": a single violated check must be
        # enough on its own to reject, with no other check spuriously firing.
        ev.expect(violated == [expect_only_failing],
                  f"exactly one check fires, and it is '{expect_only_failing}'")
        ev.expect(not result.passed,
                  "that single failing check rejects the change")


def main() -> int:
    ev = Evidence()

    # ---- Load the committed evaluation set (no synthetic data is created) ----
    eval_set = load_eval_set(EVAL_FILE)
    n_target = len(eval_set["target"])
    n_holdout = len(eval_set["holdout"])
    n_regression = len(eval_set["regression"])

    # Same two evaluations evolve.py performs in stage 3.
    baseline = run_evaluation("v1", eval_set)
    candidate = run_evaluation("v2", eval_set)

    print("=" * 72)
    print("Admission gate - reproducible evidence (offline, read-only)")
    print("=" * 72)
    print(f"eval set : {EVAL_FILE.relative_to(BASE)}")
    print(f"          target={n_target}  holdout={n_holdout}  "
          f"regression={n_regression}  total={n_target + n_holdout + n_regression}")
    print("\nMeasured scores (computed now by gate.run_evaluation):")
    print(f"  baseline  v1 : target={baseline.target_accuracy:.4f}  "
          f"holdout={baseline.holdout_accuracy:.4f}  "
          f"regression={baseline.regression_accuracy:.4f}")
    print(f"  candidate v2 : target={candidate.target_accuracy:.4f}  "
          f"holdout={candidate.holdout_accuracy:.4f}  "
          f"regression={candidate.regression_accuracy:.4f}")

    # ---- 1. Scores are reproducible, not hardcoded claims -------------------
    print("\n[1/4] Reproducibility of the committed eval set")
    ev.expect(n_target + n_holdout + n_regression == 88,
              "eval set holds 88 samples, as documented in README")
    ev.expect(n_target >= 10,
              "target subset clears the default sample-size floor of 10")
    ev.expect(baseline.target_accuracy == 0.0 and candidate.target_accuracy > 0.5,
              "baseline misses the target subset, candidate fixes most of it")
    ev.expect(candidate.regression_accuracy < baseline.regression_accuracy,
              "candidate regresses on the historical set (the trap the gate must catch)")

    # ---- 2. Default budget rejects for exactly one reason -------------------
    print("\n[2/4] Default gate (regression budget 3.0pp)")
    default = GateConfig()
    ev.expect(default.regression_budget == 3.0,
              "default regression budget is 3.0pp")
    run_scenario(ev, "default settings", default, baseline, candidate,
                 expect_pass=False, expect_only_failing=CHECKS[2])

    # ---- 3. Relaxing the budget lets the same candidate ship ----------------
    print("\n[3/4] Relaxed gate (regression budget 20pp)")
    relaxed = GateConfig(regression_budget=20.0)
    run_scenario(ev, "--regression-budget 20", relaxed, baseline, candidate,
                 expect_pass=True, expect_only_failing=None)

    # ---- 4. Each of the four checks fails independently ---------------------
    print("\n[4/4] The four checks are independent (each fires alone)")

    # Baseline cfg = relaxed (so the regression check passes) then we push one
    # threshold at a time far enough to violate exactly that one dimension.
    many_samples = GateConfig(regression_budget=20.0, min_target_samples=n_target + 1)
    run_scenario(ev, "sample-size only", many_samples, baseline, candidate,
                 expect_pass=False, expect_only_failing=CHECKS[0])

    huge_gain = GateConfig(regression_budget=20.0,
                           min_target_gain=(candidate.target_accuracy -
                                            baseline.target_accuracy) * 100 + 1)
    run_scenario(ev, "target-subset gain only", huge_gain, baseline, candidate,
                 expect_pass=False, expect_only_failing=CHECKS[1])

    tiny_budget = GateConfig(regression_budget=-1.0)
    run_scenario(ev, "regression budget only", tiny_budget, baseline, candidate,
                 expect_pass=False, expect_only_failing=CHECKS[2])

    huge_holdout = GateConfig(regression_budget=20.0,
                              min_holdout_gain=(candidate.holdout_accuracy -
                                                baseline.holdout_accuracy) * 100 + 1)
    run_scenario(ev, "held-out generalization only", huge_holdout, baseline, candidate,
                 expect_pass=False, expect_only_failing=CHECKS[3])

    # ---- Summary ------------------------------------------------------------
    print("\n" + "=" * 72)
    if ev.failed:
        print(f"FAILED: {ev.failed}/{ev.total} assertions broke. "
              "Gate evidence is stale -- fix before trusting these numbers.")
        return 1
    print(f"OK: {ev.total}/{ev.total} assertions passed.")
    print("    - scores recomputed live from data/eval_set.json")
    print("    - default gate REJECTS (regression budget exceeded)")
    print("    - relaxed gate PASSES the same candidate")
    print("    - all four checks fire independently; any single one rejects")
    print('    "Allow evolution, forbid silent regression" is now executable evidence.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
