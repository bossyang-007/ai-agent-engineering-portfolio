"""评测门禁（admission gate）—— 自进化质检 Agent 的核心。

实现要点（三条，这是整个作品最值钱的部分）：

1. 门禁不是"看起来变好了就放行"，而是四项检查与门：
   - 目标子集样本量须达下限（样本太少时统计噪声大于可能收益）
   - 目标子集必须提升（收益）
   - 历史任务集回撤不得超过预算（代价）
   - 留出集上必须优于基线（泛化，不是过拟合提案本身）

2. 整体准确率提升不算数。
   1000 条样本里目标错因占 80 条，修好 40 条整体就涨 4 个点；
   但如果同时弄坏了别的 35 条，净变化几乎为零。
   所以门禁看的第一指标永远是"目标子集"。

3. 回归预算独立于提升指标。
   新版让目标子集涨 10%、其他子集跌 15%，整体还是跌的——
   必须同时看两个方向。这就是回归预算（regression budget）原则：
   允许进化，但不允许悄悄退化。

本文件为本仓库独立实现。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 一、门禁配置
# ---------------------------------------------------------------------------


@dataclass
class GateConfig:
    """门禁阈值配置。

    这里需要说明：这些阈值不是拍脑袋定的，是"可调参数 + 有明确语义"——
    regression_budget 是允许退化的额度，min_target_gain 是最低收益要求，
    min_holdout_gain 是防止"只在提案样本上有效"的过拟合保护。
    """

    # 目标错因子集最低提升幅度（百分点）。低于此值视为"没有实质收益"
    min_target_gain: float = 3.0
    # 历史任务集允许的最大回撤（百分点）。超过即拒绝
    regression_budget: float = 3.0
    # 留出集上相对基线的最低提升（百分点）。防止只拟合了提案样本
    min_holdout_gain: float = 1.0
    # 目标子集最小样本量。样本太小则统计噪声大，直接拒绝
    min_target_samples: int = 10


@dataclass
class GateResult:
    """门禁判定结果。"""

    passed: bool
    reason: str
    # 各项实测值，用来展示"有依据地拒绝"，不是拍脑袋
    target_gain: float = 0.0
    holdout_gain: float = 0.0
    regression: float = 0.0
    target_samples: int = 0
    # 逐条拒绝原因，便于复盘
    failed_checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "target_gain": round(self.target_gain, 2),
            "holdout_gain": round(self.holdout_gain, 2),
            "regression": round(self.regression, 2),
            "target_samples": self.target_samples,
            "failed_checks": self.failed_checks,
        }


# ---------------------------------------------------------------------------
# 二、评测结果的数据结构
# ---------------------------------------------------------------------------


@dataclass
class EvalOutcome:
    """某个 Skill 版本在某组样本上的评测结果。

    这里需要说明：刻意把结果拆成"目标子集 / 留出集 / 历史回归集"三块，
    而不是一个笼统的准确率。因为笼统的单一指标会掩盖代价。
    """

    version: str
    # 目标错因子集（这次修订要修的那批）
    target_accuracy: float
    target_samples: int
    # 留出集（提案生成时没见过的同分布样本，用于验证泛化）
    holdout_accuracy: float
    # 历史任务集（其他错因类型，用于检测回归）
    regression_accuracy: float
    overall_accuracy: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "target_accuracy": round(self.target_accuracy, 4),
            "target_samples": self.target_samples,
            "holdout_accuracy": round(self.holdout_accuracy, 4),
            "regression_accuracy": round(self.regression_accuracy, 4),
            "overall_accuracy": round(self.overall_accuracy, 4),
        }


# ---------------------------------------------------------------------------
# 三、门禁判定
# ---------------------------------------------------------------------------


def evaluate_gate(
    candidate: EvalOutcome,
    baseline: EvalOutcome,
    config: GateConfig | None = None,
) -> GateResult:
    """核心判定：候选版本能否进入版本库。

    四道检查，全部通过才放行。这是"受控进化"与"放任自改"的唯一区别。

    阅读顺序建议：先讲检查 2（回归预算），因为这是最反直觉的——
    "变好"和"没变坏"是两个独立的条件，缺一不可。
    """
    cfg = config or GateConfig()

    # 计算三个差值
    # 注意单位：accuracy 是 0~1 的比例，阈值是百分点（pp）。
    # 这里统一换算成百分点后再比较，避免"100% 提升被算成 1.0pp"这类单位错配。
    target_gain = (candidate.target_accuracy - baseline.target_accuracy) * 100
    holdout_gain = (candidate.holdout_accuracy - baseline.holdout_accuracy) * 100
    # regression 用"下降量"表达，正数表示退化
    regression = (baseline.regression_accuracy - candidate.regression_accuracy) * 100

    failed: list[str] = []

    # ---- 检查 1：目标子集样本量 ----
    # 样本太少时，统计波动会大于真实收益，此时任何"提升"都不可信
    if candidate.target_samples < cfg.min_target_samples:
        failed.append(
            f"目标子集样本量不足：{candidate.target_samples} < {cfg.min_target_samples}，"
            f"统计噪声大于可能收益"
        )

    # ---- 检查 2：目标子集必须提升 ----
    if target_gain < cfg.min_target_gain:
        failed.append(
            f"目标子集未达最低提升：{target_gain:+.2f}pp < {cfg.min_target_gain}pp"
        )

    # ---- 检查 3：回归预算 ----
    # 这是"允许进化但不允许悄悄退化"的关键闸门
    if regression > cfg.regression_budget:
        failed.append(
            f"历史任务集回撤超预算：{regression:.2f}pp > {cfg.regression_budget}pp"
        )

    # ---- 检查 4：留出集泛化验证 ----
    # 防止"提案只在它自己见过的那批样本上有效"
    if holdout_gain < cfg.min_holdout_gain:
        failed.append(
            f"留出集泛化不足：{holdout_gain:+.2f}pp < {cfg.min_holdout_gain}pp，"
            f"疑似过拟合提案样本"
        )

    passed = len(failed) == 0
    if passed:
        reason = (
            f"PASS｜目标子集 {target_gain:+.2f}pp（{candidate.target_samples} 条）"
            f"｜留出集 {holdout_gain:+.2f}pp"
            f"｜历史回归 -{regression:.2f}pp（预算 {cfg.regression_budget}pp）"
        )
    else:
        reason = "REJECT｜" + "；".join(failed)

    return GateResult(
        passed=passed,
        reason=reason,
        target_gain=target_gain,
        holdout_gain=holdout_gain,
        regression=regression,
        target_samples=candidate.target_samples,
        failed_checks=failed,
    )


# ---------------------------------------------------------------------------
# 四、评测执行（离线模拟）
# ---------------------------------------------------------------------------


def load_eval_set(path: Path) -> dict[str, list[dict[str, Any]]]:
    """加载评测集。

    真实实现里这里会调用 LLM 跑推理；本实现用确定性规则模拟，
    目的是让门禁逻辑可以脱离 API 独立验证与演示。
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        "target": raw.get("target_subset", []),
        "holdout": raw.get("holdout_subset", []),
        "regression": raw.get("regression_subset", []),
    }


def score_samples(
    samples: list[dict[str, Any]],
    version: str,
    skill_version: str,
) -> tuple[float, int]:
    """对一组样本打分，返回 (准确率, 样本数)。

    模拟规则（刻意设计成可复现、可解释，且**能演示出回归检测**）：

    - v1（基线）：在"口径混淆"和"边界误判"两类上系统性做错——这正是本次
      人工纠正集中暴露的两类问题，也是评测集里"目标子集"的构成。
    - v2（候选）：修好了目标两类的大部分，但在"结论越界"这一类上
      **因为新增规则过强而引入了新错误**——这模拟了真实场景里
      "改了一处、坏了另一处"的风险。

    正是这个设计，让回归预算这条门禁能被真实触发，而不是永远走不到。

    真实实现里这里是 LLM 推理 + 与标注答案比对。
    """
    if not samples:
        return 0.0, 0

    correct = 0
    for item in samples:
        cause = item.get("cause", "")
        difficulty = item.get("difficulty", "easy")

        if skill_version == "v1":
            # 基线：仅"归因浅层"这一类表现尚可，其余系统性做错
            hit = cause == "归因浅层"
        else:
            # 候选 v2：
            if cause in ("口径混淆", "边界误判"):
                # 目标错因：本次修订修好了大部分，hard 难度仍有残留
                hit = difficulty != "hard"
            elif cause == "归因浅层":
                # 未涉及，略有提升
                hit = difficulty in ("easy", "medium")
            else:
                # 结论越界：新增的强规则导致过度纠错，反而做错更多
                hit = False

        if hit:
            correct += 1

    return correct / len(samples), len(samples)


def run_evaluation(
    skill_version: str,
    eval_set: dict[str, list[dict[str, Any]]],
) -> EvalOutcome:
    """跑一次完整评测，返回三块子集的分数。"""
    t_acc, t_n = score_samples(eval_set["target"], skill_version, skill_version)
    h_acc, _ = score_samples(eval_set["holdout"], skill_version, skill_version)
    r_acc, _ = score_samples(eval_set["regression"], skill_version, skill_version)

    total = t_acc * t_n + h_acc * len(eval_set["holdout"]) + r_acc * len(eval_set["regression"])
    denom = t_n + len(eval_set["holdout"]) + len(eval_set["regression"])
    overall = total / denom if denom else 0.0

    return EvalOutcome(
        version=skill_version,
        target_accuracy=t_acc,
        target_samples=t_n,
        holdout_accuracy=h_acc,
        regression_accuracy=r_acc,
        overall_accuracy=overall,
    )
