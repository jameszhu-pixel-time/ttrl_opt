# TTRL Recipe Notes

这个目录主要放两类内容：

- OR/Gurobi 任务的 reward 计算逻辑
- TTRL 训练链路相对原始 `ray_trainer` 的增量逻辑和 debug 工具

下面重点说明 `recipe` 和 `ttrl_utils` 到底在模拟什么，以及它们和原本训练流程的差异。

## 最常用脚本指令

下面这些命令默认从仓库根目录 `ttrl_opt/` 执行。

### 1. 测试 cached reward 路径

```bash
python3 recipe/ttrl_opt/test_group_score_gurobi.py
python3 recipe/ttrl_opt/test_group_score_gurobi.py --gt-key majority_gt
python3 recipe/ttrl_opt/test_group_score_gurobi.py --gt-key original_gt
```

适合：

- 检查 `compute_score_simplified`
- 验证 `majority_gt` / `original_gt` 切换后的 reward 差异

### 2. 测试真实执行路径

```bash
python3 recipe/ttrl_opt/test_group_score_gurobi.py --mode original
python3 recipe/ttrl_opt/test_group_score_gurobi.py --mode both --gt-key majority_gt
```

适合：

- 验证 `compute_score()` 是否真的执行了 Python / Gurobi
- 对比 cached path 和 original path

### 3. 分析 batch rollout 样本

```bash
python3 recipe/ttrl_opt/analyze_rollout_groups.py \
  --input recipe/ttrl_opt/debug_rollout_batch4_sample.jsonl \
  --group-size 4
```

默认输出目录：

- `recipe/ttrl_opt/analysis/`

默认生成：

- `recipe/ttrl_opt/analysis/debug_rollout_batch4_sample_analysis.json`
- `recipe/ttrl_opt/analysis/debug_rollout_batch4_sample_analysis.prompt_features.jsonl`
- `recipe/ttrl_opt/analysis/debug_rollout_batch4_sample_analysis.prompt_features.csv`
- `recipe/ttrl_opt/analysis/debug_rollout_batch4_sample_analysis.readable.txt`

### 4. 只看更易读的汇总结果

```bash
sed -n '1,120p' recipe/ttrl_opt/analysis/debug_rollout_batch4_sample_analysis.readable.txt
```

这个文本只保留：

- `answers`
- `maj_result`
- `ground_truth`
- `direction`
- `int_var_count`
- `bin_var_count`

### 5. 强制重建 LP 缓存

```bash
python3 recipe/ttrl_opt/analyze_rollout_groups.py \
  --input recipe/ttrl_opt/debug_rollout_batch4_sample.jsonl \
  --group-size 4 \
  --force-regenerate-lp
```

适合：

- 重新导出 `.lp`
- 怀疑旧缓存不一致时重新分析

### 6. 跑 TTRL 训练入口

```bash
bash recipe/ttrl_opt/test.sh \
  trainer.logger="['console']" \
  trainer.total_epochs=1 \
  trainer.test_freq=1
```

适合：

- 测试 TTRL majority vote + cached reward + TTRL metrics

### 7. 跑 baseline 训练入口

```bash
bash recipe/ttrl_opt/baseline/grpo322.sh \
  trainer.logger="['console']" \
  trainer.total_epochs=1 \
  trainer.test_freq=1

bash recipe/ttrl_opt/baseline/rpp319.sh \
  trainer.logger="['console']" \
  trainer.total_epochs=1 \
  trainer.test_freq=1
```

适合：

- 对比不开 TTRL 的训练链路
- 验证 reward 逻辑是否影响不同算法

## 文件定位

- `group_score_gurobi.py`
  - OR 任务的 reward 计算
- `content_utils.py`
  - 从 rollout 文本里提取 `<python>` 代码、objective、solution
- `test_group_score_gurobi.py`
  - 离线测试 reward 逻辑
- `analyze_rollout_groups.py`
  - 离线分析一组 rollout 的多数投票、pass rate、LP 特征
- `debug_rollout_sample.jsonl`
  - 小规模手工 reward 测试样本
- `debug_rollout_batch4_sample.jsonl`
  - 更接近真实 rollout dump 的 4-sample/group 样本

训练期真正的 TTRL 增量逻辑不在这个目录，而在：

- `verl/trainer/exp_ppo/ttrl_utils.py`
- `verl/trainer/exp_ppo/ray_trainer.py`

## 原始 RayTrainer 和 TTRL RayTrainer 的区别

### 原始流程

不启用 TTRL 时，训练阶段大致是：

1. `gen_batch` 生成 rollout
2. 把 rollout 拼回 batch
3. 调 reward function
4. 直接用当前 ground truth 打分
5. 计算 advantage
6. 更新 actor / critic

这条路径里没有“先生成更多样本再投票”的步骤，也没有“同一批 rollout 先用 majority GT 打一次分、再用 original GT 回算指标”的过程。

### TTRL 增量流程

启用 `ttrl.enable=True` 后，`ray_trainer.py` 在生成阶段会走另一条分支。

关键位置在：

- `ray_trainer.py` 中 `if self.config.get("ttrl", {}).get("enable", False):`
- 这里会调用：
  - `select_top_k_per_prompt`
  - `apply_ttrl_gt`
  - `select_top_k_per_prompt_result`
  - `apply_original_gt`
  - `compute_ttrl_metrics`

TTRL 训练阶段比原始流程多了这几步：

1. 先为每个 prompt 生成 `n_votes_per_prompt` 条 rollout
2. 对这批 rollout 执行代码，提取 `solved_objective / solution / code_exec_res`
3. 用 objective 做 majority vote，得到新的 `majority_gt`
4. 用 `majority_gt` 覆盖当前 batch 的 `ground_truth`
5. 只保留前 `n_samples_per_prompt` 条 rollout 进入后续 PPO/GRPO
6. 训练完成后，再把 GT 切回 `original_gt`
7. 再算一次 reward，用来记录 TTRL 相关指标

所以 TTRL 相对原始 `ray_trainer` 的核心差异，不是 reward 公式本身，而是：

- 训练时的标签可能不再是数据集原始 GT，而是 rollout 多数票得到的 `majority_gt`
- rollout 生成和筛选变成“两阶段”：先投票、再下采样
- 训练日志里会多出一套“majority GT vs original GT”的对照指标

## `ttrl_utils.py` 的具体职责

### 1. `apply_ttrl_gt`

这是 TTRL 最关键的函数。

它做的事：

1. 从一整批生成结果里 decode 出文本
2. 调 `get_solver_feedback` 执行代码，拿到：
   - `solved_objective`
   - `solution`
   - `code_exec_res`
3. 对每个 prompt 的 objective 做 majority vote
4. 把结果写回 batch：
   - `reward_model.ground_truth = majority_gt`
   - `reward_model.majority_gt = majority_gt`
   - `reward_model.original_gt = 原始 ground_truth`
5. 把 rollout-level solver 反馈缓存到 `extra_info`

这一步是原始 `ray_trainer` 没有的。

### 2. `select_top_k_per_prompt`

这一步做的是下采样。

因为投票阶段可能先生成了 `n_votes_per_prompt` 条 rollout，但真正训练不一定要把全部 rollout 都保留。  
这个函数只取每个 prompt 的前 `n_samples_per_prompt` 条，用于后续训练。

对应有两个版本：

- `select_top_k_per_prompt`
  - 处理 rollout 输出本身
- `select_top_k_per_prompt_result`
  - 处理缓存回 batch 的 `extra_info`

### 3. `apply_original_gt`

训练结束后，为了评估“如果回到数据集原始标签，这批 rollout 实际表现如何”，会把：

- `reward_model.ground_truth`

重新切回：

- `reward_model.original_gt`

这一步只是为了统计，不参与当前 step 的主训练目标。

### 4. `compute_ttrl_metrics`

这是 TTRL 相对原版 `ray_trainer` 多出来的一整套日志指标。

当前会统计：

- `label_accuracy`
  - 当前 `majority_gt` 相对 `original_gt` 是否按 `answer_reward` 判定为正确
- `reward_accuracy`
  - majority GT reward 和 original GT reward 是否逐条一致
- `majority_voting_reward`
  - majority GT 下的平均 reward
- `ground_truth_reward`
  - original GT 下的平均 reward
- `sample_answer_accuracy`
  - 组内单条 rollout 的真实答对率
- `sample_code_pass_rate`
  - 组内代码成功率
- `pass@k`
  - 组内是否至少有一条 rollout 满足 `answer_reward`
- `reward_pass@k`
  - 旧 reward-based 口径，保留用于对照
- `majority_ratio`
  - 多数票占比

注意：

- 现在 `pass@k` 已经不是旧的 `sum(gt_reward) >= 1`
- 现在它按 `compute_score` 里的 `answer_reward` 口径判断

## `group_score_gurobi.py` 的计算逻辑

### reward 由三部分组成

`group_score_gurobi.py` 里的总 reward 是：

- `answer_reward * 1.0`
- `format_reward * 0.5`
- `code_reward * 1.0`

所以就算答案错了，只要：

- 标签完整
- 代码执行成功

仍然可以拿到非零 reward。

这也是为什么：

- `reward` 很快变高
- 但 `sample_answer_accuracy` 不一定同步变高

### `compute_score` 和 `compute_score_simplified` 的区别

#### `compute_score`

这是原始路径。

它会：

1. 从 rollout 文本提取 `<python>` 代码
2. 调 `executor.py` 真执行代码
3. 从 stdout 提取 objective / solution
4. 再按 reward 公式打分

所以这条路径会真的跑 Gurobi。

#### `compute_score_simplified`

这是 TTRL 常用的 cached 路径。

它优先读取 `extra_infos` 里已经缓存好的：

- `solved_objective`
- `solution`
- `code_exec_res`

然后直接打分，不再重新执行代码。

只有当 `extra_infos` 没有这些字段时，它才会回退到 `compute_score`。

也就是说：

- 原始 `ray_trainer` 更接近 `compute_score`
- TTRL 改造后的训练链路更偏向 `compute_score_simplified`

## 为什么你会看到“分数高，但正确率不一定高”

这是当前 recipe 里最容易混淆的一点。

因为总 reward 不是纯正确率，它混合了：

- 格式
- 代码执行
- objective 正确性

所以：

- `reward_pass@k` 高，不代表 objective 真答对
- validation 里的 `reward/best@N` 高，也不代表真实正确率高

更能代表“真实做对”的指标是：

- `sample_answer_accuracy`
- `pass@k`
- `label_accuracy`

其中：

- `sample_answer_accuracy` 看单条 rollout 的正确率
- `pass@k` 看组内至少一个是否答对
- `label_accuracy` 看 majority GT 相对 original GT 是否正确

## TTRL 相对原始训练的新增副作用

这些是看日志时需要特别注意的地方。

### 1. reward 的标签来源变了

原始训练直接对 dataset GT 打分。  
TTRL 训练先对 `majority_gt` 打分，再额外回算 `original_gt` 指标。

所以同一条 rollout 可能出现：

- `majority_gt` 下 reward 很高
- `original_gt` 下其实 answer 是错的

### 2. rollout 数量和训练样本数量不再相等

TTRL 里：

- 先生成 `n_votes_per_prompt`
- 再保留 `n_samples_per_prompt`

所以真正进入 PPO/GRPO 更新的 rollout，只是投票阶段 rollout 的子集。

### 3. 训练指标里会同时混有两套口径

你现在至少会同时看到：

- reward 口径
- answer correctness 口径
- majority vote 口径

如果不区分这些字段，很容易误判模型“已经学会了”。

## 推荐怎样读日志

如果你想判断 TTRL 有没有真的提高解题能力，建议优先看：

1. `train/sample_answer_accuracy`
2. `train/pass@k`
3. `train/label_accuracy`
4. `train/majority_ratio`

然后再把它们和下面这些对照着看：

1. `train/reward_pass@k`
2. `critic/score/mean`
3. validation 里的 `reward/mean@N`
4. validation 里的 `reward/best@N`

经验上：

- 如果只有 reward 相关指标涨，answer accuracy 不涨，通常说明模型只学会了“写对格式/写出能跑的代码”
- 如果 `majority_ratio` 很高但 `label_accuracy` 不高，通常说明 rollout 已经收敛到某个一致答案，但这个答案未必是原始 GT

## 配套 debug 脚本

### `test_group_score_gurobi.py`

用于离线验证 reward 逻辑。

最适合排查：

- `majority_gt` 和 `original_gt` 为什么算出来分数不一样
- 某个样本到底是格式分、代码分还是答案分在起作用

### `analyze_rollout_groups.py`

用于离线分析一组 rollout。

最适合排查：

- 多数票是否可靠
- 组内真实正确率是否和 reward 口径一致
- 某个 prompt 的代码是否稳定生成了同一类 LP

## 一句话总结

这个 recipe 相对原始 `ray_trainer` 的本质变化只有三件事：

1. 训练标签从固定 GT 变成了“rollout 多数票 GT”
2. reward 计算优先走 cached solver feedback，而不是每次重新执行代码
3. 训练日志里新增了一套“majority GT vs original GT”的对照指标，用来区分“分高”和“真答对”
