"""自进化质检 Agent —— 经验回流闭环主程序。

设计目标：
实现"人工纠正 → Skill 提炼 → 评测门禁 → 受控发布 → 下一轮自动生效"的完整闭环，
并说明每一环为什么必须存在（尤其是门禁不能省）。

四个阶段：
  [1/4] 采集纠正   —— 读人工纠正记录，按错因类型聚类
  [2/4] 生成提案   —— 从纠正中归纳"这类错该怎么改"，产出增量 patch
  [3/4] 评测门禁   —— 样本量 / 目标子集 / 回归预算 / 留出集四项检查
  [4/4] 受控发布   —— 通过则写版本库并留下评测报告；不通过则完整留痕回退

实现说明：
  闭环采用受控变更与回归预算的通用工程原则，本文件为本仓库独立实现。
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from gate import (
    GateConfig,
    GateResult,
    evaluate_gate,
    load_eval_set,
    run_evaluation,
)

BASE = Path(__file__).parent
DATA_DIR = BASE / "data"
LOG_DIR = BASE / "logs"
SKILL_DIR = BASE / "config" / "skills" / "complaint-badcase-attribution"
SKILL_FILE = SKILL_DIR / "SKILL.md"
VERSION_FILE = SKILL_DIR / "VERSION.json"


# ---------------------------------------------------------------------------
# 阶段一：采集纠正
# ---------------------------------------------------------------------------


def collect_corrections(path: Path) -> list[dict[str, Any]]:
    """读取人工纠正记录。

    这里需要说明：这一层的输入是"人已经纠正过的结果"，而不是模型自评。
    区别很关键——模型自评会强化模型自己的偏见（模型倾向于认为自己是对的），
    而人的纠正才是真正的外部信号。这也是自进化能成立的前提。
    """
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def summarize_corrections(records: list[dict[str, Any]]) -> Counter:
    """按错因类型统计。

    这里需要说明：这一步不是简单计数。分布信息决定"这次修订该优先修哪一类"，
    也决定评测时"目标子集"怎么划。
    """
    return Counter(r.get("cause", "未知") for r in records)


# ---------------------------------------------------------------------------
# 阶段二：生成 Skill 提案（增量 patch）
# ---------------------------------------------------------------------------

# 每类错因对应的修复策略。这是本实现里"业务知识"的部分——
# 属于领域规则，不是模型可以从通用语料里推出的。
REPAIR_PLAYBOOK: dict[str, dict[str, str]] = {
    "口径混淆": {
        "action": "补充口径定义到 Resource，分类逻辑不动",
        "patch_anchor": "## 第 1 步：确认输入完整性（必做，不要跳过）",
        "patch_note": "新增口径自检清单：动手分类前先确认本条涉及的业务口径定义是否已加载",
    },
    "边界误判": {
        "action": "补 few-shot 样本，显式标注边界",
        "patch_anchor": "## 常见陷阱（Pitfalls）",
        "patch_note": "新增边界案例处理规则：语义相近但根因不同的表述必须二次确认，不得直接归类",
    },
    "归因浅层": {
        "action": "强制归因链路，拆到流程环节",
        "patch_anchor": "## 交付格式",
        "patch_note": "新增归因深度要求：结论必须落到具体流程环节，只描述现象的归因视为无效",
    },
    "结论越界": {
        "action": "增加统计显著性检查与反向指标",
        "patch_anchor": "## 验证清单（交付前自查）",
        "patch_note": "新增反向指标检查：任何单指标结论必须附对应反向指标，缺一不予交付",
    },
}


def propose_skill_patch(
    records: list[dict[str, Any]],
    current_skill: str,
) -> dict[str, Any]:
    """从纠正记录生成增量 Skill patch。

    为什么是增量 patch 而不是整条重写？
    生成的完整重写会替换整份文档，输出里没重复出现的规则会永久丢失，
    包括历次迭代积累的查询与归档方法，且这种丢失是静默的。
    所以这里只对"需要改的锚点段落"做追加，其余原文逐字保留。
    """
    by_cause: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        by_cause.setdefault(r.get("cause", "未知"), []).append(r)

    # 只对样本量足够的错因类型提案（样本太少归纳出的规则不可靠）
    patches: list[dict[str, Any]] = []
    for cause, items in by_cause.items():
        if cause not in REPAIR_PLAYBOOK:
            continue
        if len(items) < 3:
            continue
        playbook = REPAIR_PLAYBOOK[cause]
        anchor = playbook["patch_anchor"]
        if anchor not in current_skill:
            # 锚点找不到 → 拒绝这个 patch，而不是盲改
            continue
        patches.append(
            {
                "cause": cause,
                "count": len(items),
                "anchor": anchor,
                "action": playbook["action"],
                "addition": playbook["patch_note"],
                "examples": [i.get("sample_id") for i in items[:3]],
            }
        )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "base_skill_version": read_current_version(),
        "patch_count": len(patches),
        "patches": patches,
    }


def apply_patch(current_skill: str, patch: dict[str, Any]) -> str:
    """把 patch 应用到 Skill 原文（增量追加，不重写）。"""
    anchor = patch["anchor"]
    idx = current_skill.find(anchor)
    if idx == -1:
        return current_skill
    insert_at = idx + len(anchor)
    addition = f"\n- **{patch['cause']}（新增规则）**：{patch['addition']}"
    return current_skill[:insert_at] + addition + current_skill[insert_at:]


# ---------------------------------------------------------------------------
# 版本管理
# ---------------------------------------------------------------------------


def read_current_version() -> str:
    if VERSION_FILE.exists():
        return json.loads(VERSION_FILE.read_text(encoding="utf-8")).get("version", "v1")
    return "v1"


def read_version_history() -> list[dict[str, Any]]:
    if not VERSION_FILE.exists():
        return []
    return json.loads(VERSION_FILE.read_text(encoding="utf-8")).get("history", [])


def write_version(
    new_version: str,
    patch: dict[str, Any],
    gate_result: GateResult,
) -> None:
    """写入版本记录 + 评测报告。

    这里需要说明：每一条被采纳的修订都必须带着"它的评测证据"入库。
    这样任何时候都能回答"这版Skill 为什么比上一版好"，
    出问题时也能回滚到已知良好版本——这是可回滚的前提。
    """
    history = read_version_history()
    history.append(
        {
            "version": new_version,
            "published_at": datetime.now().isoformat(timespec="seconds"),
            "patch_summary": {
                "patch_count": patch["patch_count"],
                "causes": [p["cause"] for p in patch["patches"]],
            },
            "evaluation": gate_result.to_dict(),
            "evidence_file": f"evaluations/{new_version}_report.json",
        }
    )
    VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    VERSION_FILE.write_text(
        json.dumps({"version": new_version, "history": history}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_log(record: dict[str, Any]) -> None:
    """追加留痕。所有提案与判定都留记录，包括被拒绝的。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "evolution_log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="自进化质检 Agent —— 经验回流闭环")
    ap.add_argument("--dry-run", action="store_true", help="只提案不发布")
    ap.add_argument("--eval-only", action="store_true", help="跳过提案，直接跑门禁")
    ap.add_argument(
        "--regression-budget",
        type=float,
        default=3.0,
        help="历史任务集允许的最大回撤（百分点）",
    )
    ap.add_argument(
        "--min-target-gain",
        type=float,
        default=3.0,
        help="目标子集最低提升（百分点）",
    )
    args = ap.parse_args()

    cfg = GateConfig(
        min_target_gain=args.min_target_gain,
        regression_budget=args.regression_budget,
    )

    print("=" * 68)
    print("自进化质检 Agent · 经验回流闭环")
    print("=" * 68)

    # ---- 阶段 1：采集纠正 ----
    records = collect_corrections(DATA_DIR / "corrections.jsonl")
    dist = summarize_corrections(records)
    print(f"\n[1/4] 采集纠正：{len(records)} 条纠正记录，涉及 {len(dist)} 类错因")
    for cause, cnt in dist.most_common():
        print(f"        · {cause}: {cnt} 条")

    current_skill = SKILL_FILE.read_text(encoding="utf-8")
    base_version = read_current_version()

    # ---- 阶段 2：生成提案 ----
    if args.eval_only:
        patch = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "base_skill_version": base_version,
            "patch_count": 0,
            "patches": [],
        }
        candidate_skill = current_skill
        print("\n[2/4] 生成提案：--eval-only 模式，跳过提案")
    else:
        patch = propose_skill_patch(records, current_skill)
        candidate_skill = current_skill
        for p in patch["patches"]:
            candidate_skill = apply_patch(candidate_skill, p)
        print(f"\n[2/4] 生成提案：{patch['patch_count']} 个增量 patch，覆盖 "
              f"{', '.join(p['cause'] for p in patch['patches']) or '（无）'}")

    # ---- 阶段 3：评测门禁 ----
    eval_set = load_eval_set(DATA_DIR / "eval_set.json")
    baseline = run_evaluation(base_version, eval_set)
    candidate = run_evaluation("v2", eval_set)
    result = evaluate_gate(candidate, baseline, cfg)

    print(f"\n[3/4] 评测门禁")
    print(f"        基线 {base_version}：目标 {baseline.target_accuracy:.1%}"
          f" / 留出 {baseline.holdout_accuracy:.1%}"
          f" / 历史 {baseline.regression_accuracy:.1%}")
    print(f"        候选 v2   ：目标 {candidate.target_accuracy:.1%}"
          f" / 留出 {candidate.holdout_accuracy:.1%}"
          f" / 历史 {candidate.regression_accuracy:.1%}")
    print(f"        判定：{result.reason}")

    write_log(
        {
            "at": datetime.now().isoformat(timespec="seconds"),
            "base_version": base_version,
            "patch": patch,
            "baseline": baseline.to_dict(),
            "candidate": candidate.to_dict(),
            "gate": result.to_dict(),
            "published": False,
        }
    )

    # ---- 阶段 4：受控发布 ----
    if not result.passed:
        print(f"\n[4/4] 受控发布：门禁未通过，Skill 保持 {base_version} 不变")
        print("        已记录完整证据至 logs/evolution_log.jsonl，便于复盘")
        return

    if args.dry_run:
        print(f"\n[4/4] 受控发布：--dry-run 模式，不写入")
        return

    new_version = f"v{int(base_version.lstrip('v')) + 1}"
    SKILL_FILE.write_text(candidate_skill, encoding="utf-8")
    write_version(new_version, patch, result)
    print(f"\n[4/4] 受控发布：Skill {base_version} → {new_version}")
    print(f"        变更：{patch['patch_count']} 个增量 patch（未重写原有段落）")
    print("        评测证据已随版本入库，可回滚")


if __name__ == "__main__":
    main()
