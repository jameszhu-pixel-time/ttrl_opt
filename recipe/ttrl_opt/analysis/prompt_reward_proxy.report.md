# Prompt Reward Proxy Summary

## Dataset

- Prompts: `3288`
- Steps: `103`
- `predicted_correct`: `2662` (80.96%)
- `majority_but_wrong`: `365` (11.10%)
- `not_even_sampled`: `261` (7.94%)

## Observable Proxy

- Observability formula: `0.45*z(numeric_answer_rate) + 0.30*z(execution_success_rate) + 0.15*z(text_answer_extract_rate) + 0.10*z(execution_answer_recovery_rate)`
- Consensus formula: `0.55*z(answer_consensus_margin) + 0.25*z(mean_rollout_score) - 0.20*z(answer_diversity_rate)`
- Reward proxy formula: `reward_proxy = tanh((0.60 * observability_score + 0.40 * consensus_score) / 2.0)`
- Label-free bucket cut 1: `observability_score <= -0.039`
- Label-free bucket cut 2: `consensus_score <= 0.610`
- Offline accuracy against labels: `0.482`
- Offline macro-F1 against labels: `0.377`
- Top observable separating features: `execution_answer_recovery_rate, numeric_answer_rate, text_answer_extract_rate, execution_success_rate, answer_consensus_margin, mean_rollout_score`

## Step Highlights

- Best step by predicted-correct rate: `87` (96.88%)
- Worst step by predicted-correct rate: `31` (62.50%)

## Files

- HTML dashboard: `/Users/zhurui/Desktop/Chen_code/ttrl_opt/recipe/ttrl_opt/analysis/prompt_reward_proxy.report.html`
- Prompt dataset: `/Users/zhurui/Desktop/Chen_code/ttrl_opt/recipe/ttrl_opt/analysis/prompt_reward_proxy.dataset.csv`
- Step summary: `/Users/zhurui/Desktop/Chen_code/ttrl_opt/recipe/ttrl_opt/analysis/prompt_reward_proxy.step_summary.csv`
- Feature separation: `/Users/zhurui/Desktop/Chen_code/ttrl_opt/recipe/ttrl_opt/analysis/prompt_reward_proxy.feature_separation.csv`

