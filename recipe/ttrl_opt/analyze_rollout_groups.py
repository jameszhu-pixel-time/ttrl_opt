import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from statistics import mean

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
DEFAULT_ANALYSIS_DIR = SCRIPT_DIR / "analysis"

for candidate in (SCRIPT_DIR, PROJECT_ROOT):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from content_utils import extract_block  # noqa: E402

EXECUTOR_IMPORT_ERROR = None
try:
    from executor import PythonExecutor as SharedPythonExecutor  # noqa: E402
except Exception as exc:  # pragma: no cover - depends on local env
    SharedPythonExecutor = None
    EXECUTOR_IMPORT_ERROR = repr(exc)


class FallbackPythonExecutor:
    def __init__(self, timeout_length):
        self.timeout_length = timeout_length

    def batch_apply(self, batch_code):
        batch_obj = []
        batch_sol = []
        batch_report = []
        for code in batch_code:
            try:
                completed = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=str(PROJECT_ROOT),
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_length,
                )
                report = "Done" if completed.returncode == 0 else (completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else "Execution failed")
            except subprocess.TimeoutExpired:
                report = "Timeout Error"
            batch_obj.append(None)
            batch_sol.append([None])
            batch_report.append(report)
        return batch_obj, batch_sol, batch_report


def make_executor(timeout_length):
    if SharedPythonExecutor is not None:
        return SharedPythonExecutor(timeout_length=timeout_length), "shared_executor"
    return FallbackPythonExecutor(timeout_length=timeout_length), "fallback_executor"


def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_no} of {path}: {exc}") from exc
    return rows


def format_repo_relative_path(pathlike):
    if pathlike is None:
        return None
    path = Path(pathlike)
    if not path.is_absolute():
        path = path.resolve()
    try:
        return path.relative_to(WORKSPACE_ROOT).as_posix()
    except ValueError:
        return str(path)


def safe_to_float(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "" or stripped.lower() == "none":
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def canonical_label(value):
    numeric = safe_to_float(value)
    if numeric is not None:
        return format(numeric, ".12g")
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def answer_correct(prediction, ground_truth, code_exec_res, cri=1e-6):
    pred = safe_to_float(prediction)
    gt = safe_to_float(ground_truth)
    if code_exec_res != "Done":
        return False
    if pred is None or gt is None:
        return False
    rel_err = abs(pred - gt) / (abs(gt) + 1.0)
    return rel_err < cri


def compute_majority(labels):
    valid_labels = [label for label in labels if label is not None]
    if not valid_labels:
        return {
            "label": "None",
            "count": 0,
            "ratio": 0.0,
            "vote_counts": {},
        }

    counter = Counter(valid_labels)
    majority_label, majority_count = counter.most_common(1)[0]
    return {
        "label": majority_label,
        "count": majority_count,
        "ratio": majority_count / len(labels),
        "vote_counts": dict(sorted(counter.items(), key=lambda item: (-item[1], item[0]))),
    }


def normalize_prompt_text(text):
    return " ".join(str(text).split())


def extract_raw_python_code(llm_output):
    code = extract_block(llm_output, "python")
    if code:
        code = code.strip()
        fenced_match = re.search(r"```python(.*?)```", code, re.DOTALL)
        if fenced_match:
            code = fenced_match.group(1).strip()
        return code or None

    fenced_match = re.search(r"```python(.*?)```", str(llm_output), re.DOTALL)
    if fenced_match:
        code = fenced_match.group(1).strip()
        return code or None
    return None


def hash_code(code):
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def inject_lp_write(code, lp_path):
    model_pattern = r"^(\s*)(\w+)\.(optimize|solve)\(\)\s*$"
    model_match = re.search(model_pattern, code, re.M)
    if not model_match:
        return None

    indent = model_match.group(1)
    model_name = model_match.group(2)
    prefix = code[:model_match.start()]
    write_only_suffix = (
        f"{indent}{model_name}.update()\n"
        f"{indent}{model_name}.write({json.dumps(str(lp_path))})\n"
        f"{indent}print('LP file written:', {json.dumps(str(lp_path))})\n"
    )
    return prefix + write_only_suffix


def parse_lp_direction(lp_path):
    if not lp_path.exists():
        return None

    with lp_path.open("r", encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            line = raw_line.strip().lower()
            if not line or line.startswith("\\"):
                continue
            if line == "maximize":
                return "max"
            if line == "minimize":
                return "min"
    return None


def parse_lp_variable_types(lp_path):
    if not lp_path.exists():
        return {
            "binary_variables": [],
            "integer_variables": [],
        }

    current_section = None
    binary_variables = []
    integer_variables = []
    section_alias = {
        "binary": "binary",
        "binaries": "binary",
        "general": "integer",
        "generals": "integer",
        "integer": "integer",
        "integers": "integer",
    }

    with lp_path.open("r", encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            line = raw_line.strip()
            lower = line.lower()
            if not line or lower.startswith("\\"):
                continue

            if lower in {"maximize", "minimize", "subject to", "such that", "bounds", "end", "sos"}:
                current_section = None
                continue

            if lower in section_alias:
                current_section = section_alias[lower]
                continue

            if current_section == "binary":
                binary_variables.extend(token for token in line.split() if token)
            elif current_section == "integer":
                integer_variables.extend(token for token in line.split() if token)

    return {
        "binary_variables": sorted(set(binary_variables)),
        "integer_variables": sorted(set(integer_variables)),
    }


def build_lp_metadata(rows, cache_dir, executor_timeout, force_regenerate):
    cache_dir.mkdir(parents=True, exist_ok=True)

    row_metadata = []
    pending_by_code_hash = {}
    executor, executor_mode = make_executor(timeout_length=executor_timeout)
    cache_summary = {
        "cache_dir": str(cache_dir),
        "executor_mode": executor_mode,
        "executor_import_error": EXECUTOR_IMPORT_ERROR,
        "num_rows": len(rows),
        "num_rows_with_python": 0,
        "num_unique_codes": 0,
        "cache_hits": 0,
        "generated": 0,
        "missing_code": 0,
        "inject_failed": 0,
        "exec_failed": 0,
        "lp_parse_failed": 0,
    }

    for row in rows:
        raw_code = extract_raw_python_code(row.get("output", ""))
        if not raw_code:
            cache_summary["missing_code"] += 1
            row_metadata.append(
                {
                    "raw_code": None,
                    "code_hash": None,
                    "lp_path": None,
                    "lp_write_status": "missing_code",
                    "lp_exec_report": None,
                    "direction": None,
                    "binary_variables": [],
                    "integer_variables": [],
                }
            )
            continue

        cache_summary["num_rows_with_python"] += 1
        code_hash = hash_code(raw_code)
        lp_path = cache_dir / f"{code_hash}.lp"

        metadata = {
            "raw_code": raw_code,
            "code_hash": code_hash,
            "lp_path": str(lp_path),
            "lp_write_status": "pending",
            "lp_exec_report": None,
            "direction": None,
            "binary_variables": [],
            "integer_variables": [],
        }

        if lp_path.exists() and not force_regenerate:
            metadata["lp_write_status"] = "cache_hit"
            metadata["direction"] = parse_lp_direction(lp_path)
            variable_types = parse_lp_variable_types(lp_path)
            metadata["binary_variables"] = variable_types["binary_variables"]
            metadata["integer_variables"] = variable_types["integer_variables"]
            if metadata["direction"] is None:
                cache_summary["lp_parse_failed"] += 1
            else:
                cache_summary["cache_hits"] += 1
        else:
            pending_by_code_hash.setdefault(
                code_hash,
                {
                    "raw_code": raw_code,
                    "lp_path": lp_path,
                },
            )

        row_metadata.append(metadata)

    cache_summary["num_unique_codes"] = len(
        {item["code_hash"] for item in row_metadata if item["code_hash"] is not None}
    )

    if pending_by_code_hash:
        executable_items = []
        executable_codes = []

        for code_hash, item in pending_by_code_hash.items():
            instrumented_code = inject_lp_write(item["raw_code"], item["lp_path"])
            if instrumented_code is None:
                cache_summary["inject_failed"] += 1
                pending_by_code_hash[code_hash]["exec_report"] = "inject_lp_write_failed"
                continue
            executable_items.append((code_hash, item["lp_path"]))
            executable_codes.append(instrumented_code)

        if executable_codes:
            _, _, exec_reports = executor.batch_apply(executable_codes)
            for (code_hash, lp_path), exec_report in zip(executable_items, exec_reports):
                pending_by_code_hash[code_hash]["exec_report"] = exec_report
                if lp_path.exists():
                    cache_summary["generated"] += 1
                else:
                    cache_summary["exec_failed"] += 1

    for metadata in row_metadata:
        code_hash = metadata["code_hash"]
        if code_hash is None or metadata["lp_write_status"] == "cache_hit":
            continue

        pending_item = pending_by_code_hash.get(code_hash)
        if pending_item is None:
            metadata["lp_write_status"] = "missing_code"
            continue

        exec_report = pending_item.get("exec_report")
        lp_path = Path(metadata["lp_path"])
        metadata["lp_exec_report"] = exec_report

        if exec_report == "inject_lp_write_failed":
            metadata["lp_write_status"] = "inject_failed"
            continue

        if lp_path.exists():
            metadata["lp_write_status"] = "generated"
            metadata["direction"] = parse_lp_direction(lp_path)
            variable_types = parse_lp_variable_types(lp_path)
            metadata["binary_variables"] = variable_types["binary_variables"]
            metadata["integer_variables"] = variable_types["integer_variables"]
            if metadata["direction"] is None:
                cache_summary["lp_parse_failed"] += 1
        else:
            metadata["lp_write_status"] = "exec_failed"

    return row_metadata, cache_summary


def unique_non_null(values):
    result = []
    seen = set()
    for value in values:
        if value is None:
            continue
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def summarize_group(rows, group_index, preview_chars, lp_metadata_rows):
    prompt = rows[0].get("input")
    prompt_texts = unique_non_null([row.get("input") for row in rows])
    warnings = []
    if len(prompt_texts) > 1:
        warnings.append("group contains multiple prompt texts")

    gt_values = unique_non_null([row.get("original_gt") for row in rows])
    if not gt_values:
        gt_values = unique_non_null([row.get("ground_truth") for row in rows])
    ground_truth = gt_values[0] if gt_values else None
    if len(gt_values) > 1:
        warnings.append("group contains multiple ground-truth values")

    logged_majority_values = unique_non_null([row.get("majority_gt") for row in rows])
    logged_majority = logged_majority_values[0] if logged_majority_values else None
    if len(logged_majority_values) > 1:
        warnings.append("group contains multiple logged majority labels")

    score_values = [row.get("score") for row in rows]
    obj_results = [row.get("solved_objective") for row in rows]
    directions = [metadata.get("direction") for metadata in lp_metadata_rows]
    binary_var_counts = [len(metadata.get("binary_variables", [])) for metadata in lp_metadata_rows]
    integer_var_counts = [len(metadata.get("integer_variables", [])) for metadata in lp_metadata_rows]
    obj_labels = [canonical_label(value) for value in obj_results]
    majority = compute_majority(obj_labels)
    direction_majority = compute_majority([direction for direction in directions if direction is not None])
    ground_truth_label = canonical_label(ground_truth)
    logged_majority_label = canonical_label(logged_majority)
    valid_obj_flags = [safe_to_float(value) is not None for value in obj_results]
    valid_obj_labels = [obj_labels[i] for i in range(len(obj_labels)) if valid_obj_flags[i]]
    unique_obj_count = len(set(valid_obj_labels))
    vote_counts = sorted(majority["vote_counts"].values(), reverse=True)
    top1_count = vote_counts[0] if vote_counts else 0
    top2_count = vote_counts[1] if len(vote_counts) > 1 else 0
    top2_vote_gap = (top1_count - top2_count) / len(rows)
    direction_known_count = sum(direction is not None for direction in directions)
    direction_consistency = (
        direction_majority["count"] / direction_known_count if direction_known_count else 0.0
    )
    binary_lp_rate = sum(count > 0 for count in binary_var_counts) / len(rows)
    integer_lp_rate = sum(count > 0 for count in integer_var_counts) / len(rows)

    rollouts = []
    code_successes = []
    answer_successes = []
    for rollout_index, row in enumerate(rows):
        code_exec_res = row.get("code_exec_res")
        code_success = code_exec_res == "Done"
        matches_gt = answer_correct(row.get("solved_objective"), ground_truth, code_exec_res)
        matches_logged_majority = answer_correct(row.get("solved_objective"), logged_majority, code_exec_res)
        matches_computed_majority = answer_correct(row.get("solved_objective"), majority["label"], code_exec_res)
        code_successes.append(code_success)
        answer_successes.append(matches_gt)
        rollouts.append(
            {
                "response_index": rollout_index,
                "score": row.get("score"),
                "obj_result": row.get("solved_objective"),
                "obj_vote_label": obj_labels[rollout_index],
                "direction": lp_metadata_rows[rollout_index].get("direction"),
                "binary_variables": lp_metadata_rows[rollout_index].get("binary_variables"),
                "integer_variables": lp_metadata_rows[rollout_index].get("integer_variables"),
                "binary_var_count": binary_var_counts[rollout_index],
                "integer_var_count": integer_var_counts[rollout_index],
                "lp_path": lp_metadata_rows[rollout_index].get("lp_path"),
                "lp_write_status": lp_metadata_rows[rollout_index].get("lp_write_status"),
                "lp_exec_report": lp_metadata_rows[rollout_index].get("lp_exec_report"),
                "code_exec_res": code_exec_res,
                "code_success": code_success,
                "matches_ground_truth": matches_gt,
                "matches_logged_majority": matches_logged_majority,
                "matches_computed_majority": matches_computed_majority,
                "output_preview": normalize_prompt_text(row.get("output", ""))[:preview_chars],
            }
        )

    prompt_metrics = {
        "code_pass_rate": sum(code_successes) / len(rows),
        "sample_answer_accuracy": sum(answer_successes) / len(rows),
        f"pass@{len(rows)}": 1.0 if any(answer_successes) else 0.0,
        "score_mean": mean(score_values) if score_values else None,
        "score_max": max(score_values) if score_values else None,
        "majority_label_accuracy": 1.0 if answer_correct(majority["label"], ground_truth, "Done") else 0.0,
        "logged_majority_label_accuracy": 1.0 if answer_correct(logged_majority, ground_truth, "Done") else 0.0,
        "unique_obj_count": unique_obj_count,
        "top2_vote_gap": top2_vote_gap,
        "valid_obj_rate": sum(valid_obj_flags) / len(rows),
        "direction_consistency": direction_consistency,
        "direction_known_rate": direction_known_count / len(rows),
        "binary_lp_rate": binary_lp_rate,
        "integer_lp_rate": integer_lp_rate,
        "max_binary_var_count": max(binary_var_counts) if binary_var_counts else 0,
        "max_integer_var_count": max(integer_var_counts) if integer_var_counts else 0,
        "any_binary_variables": any(count > 0 for count in binary_var_counts),
        "any_integer_variables": any(count > 0 for count in integer_var_counts),
    }

    return {
        "prompt_index": group_index,
        "prompt": prompt,
        "num_rollouts": len(rows),
        "obj": obj_results,
        "direction": directions,
        "binary_var_count_results": binary_var_counts,
        "integer_var_count_results": integer_var_counts,
        "maj": majority["label"],
        "maj_ratio": majority["ratio"],
        "ground_truth": ground_truth,
        "ground_truth_label": ground_truth_label,
        "logged_majority_gt": logged_majority,
        "logged_majority_label": logged_majority_label,
        "obj_results": obj_results,
        "obj_vote_labels": obj_labels,
        "direction_results": directions,
        "direction_majority": direction_majority,
        "computed_majority": {
            **majority,
            "matches_ground_truth": prompt_metrics["majority_label_accuracy"] == 1.0,
            "matches_logged_majority": answer_correct(majority["label"], logged_majority, "Done"),
        },
        "metrics": prompt_metrics,
        "warnings": warnings,
        "rollouts": rollouts,
    }


def build_prompt_feature_row(prompt_data):
    metrics = prompt_data["metrics"]
    direction_majority = prompt_data["direction_majority"]
    row = {
        "prompt_index": prompt_data["prompt_index"],
        "prompt": prompt_data["prompt"],
        "num_rollouts": prompt_data["num_rollouts"],
        "ground_truth": prompt_data["ground_truth"],
        "logged_majority_gt": prompt_data["logged_majority_gt"],
        "maj": prompt_data["maj"],
        "maj_ratio": prompt_data["maj_ratio"],
        "majority_count": prompt_data["computed_majority"]["count"],
        "majority_matches_ground_truth": prompt_data["computed_majority"]["matches_ground_truth"],
        "majority_matches_logged_majority": prompt_data["computed_majority"]["matches_logged_majority"],
        "direction_majority": direction_majority["label"],
        "direction_majority_ratio": direction_majority["ratio"],
        "code_pass_rate": metrics["code_pass_rate"],
        "sample_answer_accuracy": metrics["sample_answer_accuracy"],
        f"pass@{prompt_data['num_rollouts']}": metrics[f"pass@{prompt_data['num_rollouts']}"],
        "score_mean": metrics["score_mean"],
        "score_max": metrics["score_max"],
        "majority_label_accuracy": metrics["majority_label_accuracy"],
        "logged_majority_label_accuracy": metrics["logged_majority_label_accuracy"],
        "unique_obj_count": metrics["unique_obj_count"],
        "top2_vote_gap": metrics["top2_vote_gap"],
        "valid_obj_rate": metrics["valid_obj_rate"],
        "direction_consistency": metrics["direction_consistency"],
        "direction_known_rate": metrics["direction_known_rate"],
        "binary_lp_rate": metrics["binary_lp_rate"],
        "integer_lp_rate": metrics["integer_lp_rate"],
        "max_binary_var_count": metrics["max_binary_var_count"],
        "max_integer_var_count": metrics["max_integer_var_count"],
        "any_binary_variables": metrics["any_binary_variables"],
        "any_integer_variables": metrics["any_integer_variables"],
    }

    for rollout in prompt_data.get("rollouts", []):
        idx = rollout["response_index"]
        prefix = f"rollout_{idx}"
        row[f"{prefix}_score"] = rollout.get("score")
        row[f"{prefix}_obj_result"] = rollout.get("obj_result")
        row[f"{prefix}_obj_vote_label"] = rollout.get("obj_vote_label")
        row[f"{prefix}_direction"] = rollout.get("direction")
        row[f"{prefix}_binary_var_count"] = rollout.get("binary_var_count")
        row[f"{prefix}_integer_var_count"] = rollout.get("integer_var_count")
        row[f"{prefix}_binary_variables"] = "|".join(rollout.get("binary_variables", []))
        row[f"{prefix}_integer_variables"] = "|".join(rollout.get("integer_variables", []))
        row[f"{prefix}_lp_path"] = rollout.get("lp_path")
        row[f"{prefix}_lp_write_status"] = rollout.get("lp_write_status")
        row[f"{prefix}_lp_exec_report"] = rollout.get("lp_exec_report")
        row[f"{prefix}_code_exec_res"] = rollout.get("code_exec_res")
        row[f"{prefix}_code_success"] = rollout.get("code_success")
        row[f"{prefix}_matches_ground_truth"] = rollout.get("matches_ground_truth")
        row[f"{prefix}_matches_logged_majority"] = rollout.get("matches_logged_majority")
        row[f"{prefix}_matches_computed_majority"] = rollout.get("matches_computed_majority")
        row[f"{prefix}_output_preview"] = rollout.get("output_preview")

    return row


def build_readable_prompt_row(prompt_data):
    metrics = prompt_data["metrics"]
    direction_majority = prompt_data["direction_majority"]
    return {
        "prompt_index": prompt_data["prompt_index"],
        "prompt": prompt_data["prompt"],
        "answers": prompt_data["obj_results"],
        "maj_result": prompt_data["maj"],
        "ground_truth": prompt_data["ground_truth"],
        "direction_list": prompt_data["direction_results"],
        "direction_majority": direction_majority["label"],
        "int_var_count_list": prompt_data["integer_var_count_results"],
        "bin_var_count_list": prompt_data["binary_var_count_results"],
        "pass@k": metrics[f"pass@{prompt_data['num_rollouts']}"],
        "sample_answer_accuracy": metrics["sample_answer_accuracy"],
    }


def render_readable_text(prompt_rows):
    blocks = []
    for row in prompt_rows:
        lines = [
            f"[prompt {row['prompt_index']}]",
            f"prompt: {row['prompt']}",
            f"answers: {row['answers']}",
            f"maj_result: {row['maj_result']}",
            f"ground_truth: {row['ground_truth']}",
            f"direction: {row['direction_list']} -> maj={row['direction_majority']}",
            f"int_var_count: {row['int_var_count_list']}",
            f"bin_var_count: {row['bin_var_count_list']}",
            f"pass@k: {row['pass@k']}",
            f"sample_answer_accuracy: {row['sample_answer_accuracy']}",
        ]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def analyze_rows(rows, group_size, preview_chars, lp_metadata_rows):
    if group_size <= 0:
        raise ValueError("--group-size must be positive")
    if len(rows) % group_size != 0:
        raise ValueError(
            f"row count {len(rows)} is not divisible by group size {group_size}; "
            "the formatted rollout dump is not batch-aligned"
        )

    prompts = []
    for start in range(0, len(rows), group_size):
        group_rows = rows[start:start + group_size]
        group_lp_metadata = lp_metadata_rows[start:start + group_size]
        prompts.append(
            summarize_group(
                group_rows,
                group_index=start // group_size,
                preview_chars=preview_chars,
                lp_metadata_rows=group_lp_metadata,
            )
        )

    summary = {
        "num_prompts": len(prompts),
        "num_rollouts": len(rows),
        "group_size": group_size,
        "avg_majority_ratio": mean(prompt["computed_majority"]["ratio"] for prompt in prompts),
        "avg_code_pass_rate": mean(prompt["metrics"]["code_pass_rate"] for prompt in prompts),
        "avg_sample_answer_accuracy": mean(prompt["metrics"]["sample_answer_accuracy"] for prompt in prompts),
        "majority_label_accuracy": mean(prompt["metrics"]["majority_label_accuracy"] for prompt in prompts),
        "logged_majority_label_accuracy": mean(prompt["metrics"]["logged_majority_label_accuracy"] for prompt in prompts),
        "avg_direction_known_rate": mean(
            sum(direction is not None for direction in prompt["direction_results"]) / len(prompt["direction_results"])
            for prompt in prompts
        ),
        f"pass@{group_size}": mean(prompt["metrics"][f"pass@{group_size}"] for prompt in prompts),
    }
    return {
        "summary": summary,
        "prompts": prompts,
        "prompt_feature_rows": [build_prompt_feature_row(prompt) for prompt in prompts],
        "readable_prompt_rows": [build_readable_prompt_row(prompt) for prompt in prompts],
    }


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path, rows):
    fieldnames = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def relativize_analysis_result(result):
    cloned = json.loads(json.dumps(result))
    cloned["source_file"] = format_repo_relative_path(cloned["source_file"])
    if cloned.get("lp_cache", {}).get("cache_dir") is not None:
        cloned["lp_cache"]["cache_dir"] = format_repo_relative_path(cloned["lp_cache"]["cache_dir"])
    for prompt in cloned.get("prompts", []):
        for rollout in prompt.get("rollouts", []):
            rollout["lp_path"] = format_repo_relative_path(rollout.get("lp_path"))
    for row in cloned.get("prompt_feature_rows", []):
        for key, value in list(row.items()):
            if key.endswith("_lp_path"):
                row[key] = format_repo_relative_path(value)
    return cloned


def build_argparser():
    parser = argparse.ArgumentParser(
        description="Analyze formatted rollout JSONL by prompt group and compute majority-vote metrics."
    )
    parser.add_argument("--input", required=True, help="Path to the formatted rollout JSONL file.")
    parser.add_argument("--group-size", type=int, default=4, help="Number of rollouts per prompt.")
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=160,
        help="Number of characters to keep in each rollout output preview.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write the pretty JSON analysis.",
    )
    parser.add_argument(
        "--prompt-features-jsonl",
        help="Optional path to write prompt-level flat features as JSONL.",
    )
    parser.add_argument(
        "--prompt-features-csv",
        help="Optional path to write prompt-level flat features as CSV.",
    )
    parser.add_argument(
        "--readable-output",
        help="Optional path to write a compact readable prompt summary text file.",
    )
    parser.add_argument(
        "--lp-cache-dir",
        help="Directory used to store reusable LP files keyed by code hash.",
    )
    parser.add_argument(
        "--executor-timeout",
        type=int,
        default=20,
        help="Timeout in seconds for each unique code execution while generating LP files.",
    )
    parser.add_argument(
        "--force-regenerate-lp",
        action="store_true",
        help="Regenerate LP files even if a cached file already exists.",
    )
    return parser


def main():
    args = build_argparser().parse_args()
    input_path = Path(args.input)
    rows = load_jsonl(input_path)
    DEFAULT_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    if args.lp_cache_dir:
        lp_cache_dir = Path(args.lp_cache_dir)
    else:
        lp_cache_dir = DEFAULT_ANALYSIS_DIR / f"{input_path.stem}_lp_cache"

    lp_metadata_rows, lp_cache_summary = build_lp_metadata(
        rows,
        cache_dir=lp_cache_dir,
        executor_timeout=args.executor_timeout,
        force_regenerate=args.force_regenerate_lp,
    )
    analysis = analyze_rows(
        rows,
        group_size=args.group_size,
        preview_chars=args.preview_chars,
        lp_metadata_rows=lp_metadata_rows,
    )
    result = {
        "source_file": str(input_path),
        "lp_cache": lp_cache_summary,
        **analysis,
    }
    result = relativize_analysis_result(result)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)

    prompt_feature_rows = result["prompt_feature_rows"]
    readable_prompt_rows = result["readable_prompt_rows"]

    output_path = Path(args.output) if args.output else DEFAULT_ANALYSIS_DIR / f"{input_path.stem}_analysis.json"
    prompt_jsonl_path = (
        Path(args.prompt_features_jsonl)
        if args.prompt_features_jsonl
        else output_path.with_name(f"{output_path.stem}.prompt_features.jsonl")
    )
    prompt_csv_path = (
        Path(args.prompt_features_csv)
        if args.prompt_features_csv
        else output_path.with_name(f"{output_path.stem}.prompt_features.csv")
    )
    readable_output_path = (
        Path(args.readable_output)
        if args.readable_output
        else output_path.with_name(f"{output_path.stem}.readable.txt")
    )

    for path in (output_path, prompt_jsonl_path, prompt_csv_path, readable_output_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(rendered + "\n", encoding="utf-8")
    write_jsonl(prompt_jsonl_path, prompt_feature_rows)
    write_csv(prompt_csv_path, prompt_feature_rows)
    readable_output_path.write_text(render_readable_text(readable_prompt_rows), encoding="utf-8")

    print(rendered)


if __name__ == "__main__":
    main()
