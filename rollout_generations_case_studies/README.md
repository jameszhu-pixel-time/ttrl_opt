# Rollout Case Studies

这个目录从 `ttrl_opt/rollout_generations` 中挑了 4 个代表性案例:

- `01_majority_vote_correct`: 多数票正确，但有单条 rollout 把 total 写成 average
- `02_majority_vote_wrong`: 多数票错误，主因是漏掉固定成本；同时保留 minority correct 证据
- `03_not_even_sampled`: 全组都把 servings 建成连续变量，因此正确答案根本没有被 sample 到
- `04_min_max_inconsistent_prompt`: 同一 prompt 内同时出现 maximize / minimize 两种方向，并分裂出三类代表性回复

每个子目录里至少包含:

- `analysis.md`: 文字说明与原始文本片段
- `answer_distribution.png`: 该组 sampled answer 分布图
