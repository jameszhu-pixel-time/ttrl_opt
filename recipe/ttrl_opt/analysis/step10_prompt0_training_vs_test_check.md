# Step 10 Prompt 0 Training-vs-Test Check

## Scope

- Checked `/Users/zhurui/Desktop/Chen_code/ttrl_opt` for bugs similar to the `extra_info` aliasing / dump filtering issue.
- Re-ran one real rollout group from:
  - `/Users/zhurui/Desktop/Chen_code/ttrl_opt/verl/checkpoints/TTRL-verl/test-OR-Qwen3-4B-ins/0324/TTRL-Len@16k-exp24-grpo-233421/10.jsonl`
- Generated real-sample subset:
  - `/Users/zhurui/Desktop/Chen_code/ttrl_opt/recipe/ttrl_opt/analysis/step10_prompt0_real_sample.jsonl`
- Generated local analysis outputs:
  - `/Users/zhurui/Desktop/Chen_code/ttrl_opt/recipe/ttrl_opt/analysis/step10_prompt0_real_sample_analysis.json`
  - `/Users/zhurui/Desktop/Chen_code/ttrl_opt/recipe/ttrl_opt/analysis/step10_prompt0_real_sample.readable.txt`

## Similar-Issue Scan

I checked `ttrl_opt` for:

- `repeat()` followed by rollout-level writes into object metadata
- dump-time filtering that can drop partially missing rollout fields
- cached reward paths that directly trust logged `code_exec_res` / `solved_objective`

Findings:

- The trainer copy at [ray_trainer.py](/Users/zhurui/Desktop/Chen_code/ttrl_opt/verl/trainer/exp_ppo/ray_trainer.py#L723) had the same two bug sites as the `training/` copy, and is now patched.
- I did not find a second independent `repeat()+object-dict overwrite` site elsewhere in `ttrl_opt`.
- There is still an analysis/tooling fragility: cached scoring in [group_score_gurobi.py](/Users/zhurui/Desktop/Chen_code/ttrl_opt/recipe/ttrl_opt/group_score_gurobi.py#L96) intentionally trusts logged rollout metadata, so old corrupted dumps will still disagree with local re-execution.
- `test_group_score_gurobi.py --mode original` is environment-sensitive in this shell because the current `python3` may not have `numpy`; for this check I used `analyze_rollout_groups.py`, which completed successfully.

## Real Sample Result

Sample:

- Step: `10`
- Prompt group: first prompt in `10.jsonl`
- Group size: `32`

Training-style cached path, using logged fields from the real dump:

- All `32/32` rows had the same logged `code_exec_res`:
  - `NameError: name 'GRB_OPTIMAL' is not defined`
- All `32/32` rows had `solved_objective = null`
- All `32/32` rows had the same logged reward:
  - `0.875`

Local test-style execution on the exact dumped `output` texts:

- `12/32` rows executed with local report `Done`
- `10/32` rows produced a non-null local objective
- local execution reports were mixed, not uniform:
  - `Done`: `12`
  - `SyntaxError: invalid syntax`: `6`
  - `NameError: name 'GRB_OPTIMAL' is not defined`: `3`
  - `AttributeError: type object 'GRB' has no attribute 'optimal'`: `2`
  - `Timeout Error`: `2`
  - `KeyError: (1, 1)`: `2`
  - plus several one-off failures

Objective distribution from local execution:

- computed majority label: `275`
- vote counts among non-null objectives:
  - `275`: `6`
  - `290`: `2`
  - `285`: `1`
  - `0`: `1`
- logged majority label: `275`
- ground truth: `290`

## Interpretation

This real sample still shows a strong training-vs-test inconsistency on the historical dump:

- the cached training-style view says every rollout failed the same way
- the local test-style view shows mixed behavior, with some rollouts finishing successfully and some producing valid objectives

That is consistent with the previously identified aliasing bug in rollout metadata:

- the old dump is not a trustworthy row-aligned snapshot of `output` + `code_exec_res` + `solved_objective`
- fixing the trainer now prevents this on future dumps
- it does not repair already dumped historical jsonl files

## Bottom Line

- I did not find another new bug of the same class in `ttrl_opt` beyond the trainer copy already patched.
- Using a real rollout group, inconsistency still exists on old step-10 logs.
- The inconsistency is explained by historical dump corruption, not by a fresh mismatch in the patched code path.
