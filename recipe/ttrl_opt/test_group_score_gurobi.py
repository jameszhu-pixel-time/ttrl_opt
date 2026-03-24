#!/usr/bin/env python3
import argparse
import importlib
import json
import math
import sys
import types
from collections import defaultdict
from pathlib import Path


THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parents[1]

# group_score_gurobi.py imports `content_utils` from this directory and
# `executor`/`utils` from the project root via absolute module names.
for path in (THIS_DIR, PROJECT_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at line {line_no} in {path}: {exc}") from exc
    return rows


def load_reward_module(mode: str):
    if mode == "simplified":
        try:
            importlib.import_module("numpy")
        except ModuleNotFoundError:
            numpy_stub = types.ModuleType("numpy")
            numpy_stub.integer = int
            numpy_stub.floating = float
            sys.modules.setdefault("numpy", numpy_stub)
        try:
            importlib.import_module("requests")
        except ModuleNotFoundError:
            requests_stub = types.ModuleType("requests")
            sys.modules.setdefault("requests", requests_stub)

        executor_stub = types.ModuleType("executor")

        class PythonExecutor:  # noqa: D401
            def __init__(self, *args, **kwargs):
                pass

            def batch_apply(self, *args, **kwargs):
                raise RuntimeError("PythonExecutor stub is only for simplified mode.")

        executor_stub.PythonExecutor = PythonExecutor
        sys.modules.setdefault("executor", executor_stub)

    return importlib.import_module("group_score_gurobi")


def build_inputs(rows: list[dict], gt_key: str) -> tuple[list[str], list[str], list[str], list[dict]]:
    data_sources = [row.get("input", "") for row in rows]
    solution_strs = [row["output"] for row in rows]
    ground_truths = [str(row[gt_key]) for row in rows]
    extra_infos = [
        {
            "solved_objective": row.get("solved_objective"),
            "solution": row.get("solution"),
            "code_exec_res": row.get("code_exec_res"),
        }
        for row in rows
    ]
    return data_sources, solution_strs, ground_truths, extra_infos


def format_number(value) -> str:
    if value is None:
        return "None"
    if isinstance(value, float) and math.isnan(value):
        return "nan"
    return f"{value:.6f}" if isinstance(value, float) else str(value)


def compute_components(reward_mod, rows: list[dict], gt_key: str, rewards: list[float]) -> list[dict]:
    details = []
    for row, reward in zip(rows, rewards):
        format_score = reward_mod.format_reward(row["output"], False)
        code_ok = bool(reward_mod.code_reward(row.get("code_exec_res")))
        answer_ok = bool(
            reward_mod.answer_reward(
                row.get("solved_objective"),
                row.get(gt_key),
                row.get("code_exec_res"),
            )
        )
        details.append(
            {
                "reward": reward,
                "format_score": format_score,
                "format_ok": math.isclose(format_score, 2.0),
                "code_ok": code_ok,
                "answer_ok": answer_ok,
            }
        )
    return details


def print_report(rows: list[dict], rewards: list[float], details: list[dict], gt_key: str, mode: str) -> None:
    total_abs_diff = 0.0
    print(f"mode={mode}, gt_key={gt_key}, sample_count={len(rows)}")
    print("-" * 120)
    for idx, (row, reward, detail) in enumerate(zip(rows, rewards, details), start=1):
        expected = row.get("score")
        diff = None if expected is None else reward - expected
        if diff is not None:
            total_abs_diff += abs(diff)
        print(
            f"[{idx}] reward={format_number(reward)}"
            f" expected={format_number(expected)}"
            f" diff={format_number(diff)}"
            f" gt={row.get(gt_key)}"
            f" majority_gt={row.get('majority_gt')}"
            f" original_gt={row.get('original_gt')}"
            f" answer_ok={detail['answer_ok']}"
            f" code_ok={detail['code_ok']}"
            f" format_score={format_number(detail['format_score'])}"
            f" solved_objective={row.get('solved_objective')}"
            f" code_exec_res={row.get('code_exec_res')}"
        )
    print("-" * 120)
    if rows:
        print(f"mean_abs_diff={total_abs_diff / len(rows):.6f}")


def print_summary(rows: list[dict], details: list[dict], group_key: str | None) -> None:
    sample_count = len(details)
    if sample_count == 0:
        return

    sample_accuracy = sum(item["answer_ok"] for item in details) / sample_count
    sample_code_pass_rate = sum(item["code_ok"] for item in details) / sample_count
    sample_format_full_rate = sum(item["format_ok"] for item in details) / sample_count
    sample_reward_mean = sum(item["reward"] for item in details) / sample_count

    print("summary")
    print(f"sample_answer_accuracy={sample_accuracy:.6f}")
    print(f"sample_code_pass_rate={sample_code_pass_rate:.6f}")
    print(f"sample_full_format_rate={sample_format_full_rate:.6f}")
    print(f"sample_reward_mean={sample_reward_mean:.6f}")

    if not group_key:
        return

    grouped = defaultdict(list)
    for row, detail in zip(rows, details):
        grouped[row.get(group_key, f"__missing_{group_key}__")].append(detail)

    actual_group_pass = []
    current_group_pass = []
    group_sizes = []
    for group_details in grouped.values():
        group_sizes.append(len(group_details))
        actual_group_pass.append(1.0 if any(item["answer_ok"] for item in group_details) else 0.0)
        current_group_pass.append(1.0 if sum(item["reward"] for item in group_details) >= 1.0 else 0.0)

    print(f"group_key={group_key}")
    print(f"group_count={len(grouped)}")
    print(f"group_size_set={sorted(set(group_sizes))}")
    print(f"actual_group_pass_rate={sum(actual_group_pass) / len(actual_group_pass):.6f}")
    print(f"current_metric_group_pass_rate={sum(current_group_pass) / len(current_group_pass):.6f}")


def run_simplified(reward_mod, rows: list[dict], gt_key: str) -> list[float]:
    data_sources, solution_strs, ground_truths, extra_infos = build_inputs(rows, gt_key)
    return reward_mod.compute_score_simplified(data_sources, solution_strs, ground_truths, extra_infos)


def run_original(reward_mod, rows: list[dict], gt_key: str) -> list[float]:
    data_sources, solution_strs, ground_truths, extra_infos = build_inputs(rows, gt_key)
    return reward_mod.compute_score(data_sources, solution_strs, ground_truths, extra_infos)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test recipe/ttrl_opt/group_score_gurobi.py with a debug rollout JSONL file."
    )
    parser.add_argument(
        "--jsonl",
        type=Path,
        default=THIS_DIR / "debug_rollout_sample.jsonl",
        help="Path to the rollout debug JSONL file.",
    )
    parser.add_argument(
        "--mode",
        choices=("simplified", "original", "both"),
        default="simplified",
        help="Which reward function path to test.",
    )
    parser.add_argument(
        "--gt-key",
        choices=("ground_truth", "majority_gt", "original_gt"),
        default="ground_truth",
        help="Which field in the JSONL is used as ground truth.",
    )
    parser.add_argument(
        "--group-key",
        default="input",
        help="Field used to group rows when reporting prompt-level pass rate. Use '' to disable grouping.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = load_jsonl(args.jsonl)
    if not rows:
        print(f"No samples found in {args.jsonl}")
        return 1

    missing_gt = [idx for idx, row in enumerate(rows, start=1) if args.gt_key not in row]
    if missing_gt:
        raise KeyError(f"Missing gt key '{args.gt_key}' in rows: {missing_gt}")

    if args.mode in ("simplified", "both"):
        reward_mod = load_reward_module("simplified")
        rewards = run_simplified(reward_mod, rows, args.gt_key)
        details = compute_components(reward_mod, rows, args.gt_key, rewards)
        print_report(rows, rewards, details, args.gt_key, "simplified")
        print_summary(rows, details, args.group_key or None)

    if args.mode in ("original", "both"):
        try:
            sys.modules.pop("group_score_gurobi", None)
            sys.modules.pop("executor", None)
            reward_mod = load_reward_module("original")
            rewards = run_original(reward_mod, rows, args.gt_key)
        except Exception as exc:
            print(f"original mode failed: {type(exc).__name__}: {exc}")
            return 2 if args.mode == "original" else 0
        details = compute_components(reward_mod, rows, args.gt_key, rewards)
        print_report(rows, rewards, details, args.gt_key, "original")
        print_summary(rows, details, args.group_key or None)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
