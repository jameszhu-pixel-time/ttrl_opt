# TTRL OR Debug README

这个目录下除了训练脚本，也放了一组用于排查 reward、rollout 聚合和 LP 结构问题的 debug 脚本。下面按“它在模拟训练流程中的哪一段”来说明。

## 常用指令

下面这些命令默认都从仓库根目录 `ttrl_opt/` 执行。

### 1. 离线重算 reward

```bash
python3 recipe/ttrl_opt/test_group_score_gurobi.py
python3 recipe/ttrl_opt/test_group_score_gurobi.py --gt-key majority_gt
python3 recipe/ttrl_opt/test_group_score_gurobi.py --gt-key original_gt
python3 recipe/ttrl_opt/test_group_score_gurobi.py --mode original
```

用途：

- 检查 `group_score_gurobi.py` 的打分是否符合预期
- 对比 `majority_gt` 和 `original_gt` 两种口径
- 验证 cached reward 路径和真实执行路径的差别

### 2. 分析 rollout group

```bash
python3 recipe/ttrl_opt/analyze_rollout_groups.py \
  --input recipe/ttrl_opt/debug_rollout_batch4_sample.jsonl \
  --group-size 4
```

默认输出会写到：

- `recipe/ttrl_opt/analysis/debug_rollout_batch4_sample_analysis.json`
- `recipe/ttrl_opt/analysis/debug_rollout_batch4_sample_analysis.prompt_features.jsonl`
- `recipe/ttrl_opt/analysis/debug_rollout_batch4_sample_analysis.prompt_features.csv`
- `recipe/ttrl_opt/analysis/debug_rollout_batch4_sample_analysis.readable.txt`

用途：

- 看 objective 多数票
- 看组内真实正确率
- 看 LP 方向、整数变量、二进制变量

### 3. 直接看可读版分析结果

```bash
sed -n '1,120p' recipe/ttrl_opt/analysis/debug_rollout_batch4_sample_analysis.readable.txt
```

用途：

- 连续阅读每个 prompt 的 `answers / maj_result / ground_truth / direction / int/bin var count`

### 4. 跑 TTRL smoke test

```bash
bash recipe/ttrl_opt/test.sh \
  trainer.logger="['console']" \
  trainer.val_before_train=False \
  trainer.total_epochs=1 \
  trainer.test_freq=1
```

用途：

- 测试 TTRL 开启时的 rollout -> majority GT -> cached reward -> metrics 全链路

### 5. 跑 baseline smoke test

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

用途：

- 对比 TTRL 和非 TTRL 的训练行为
- 测试 reward/debug 逻辑是否兼容不同 advantage estimator

## 1. Reward 重算

### `group_score_gurobi.py`
训练和验证时实际调用的自定义 reward 函数。

- `compute_score_simplified`
  - 模拟 TTRL cached path
  - 不重新执行代码
  - 直接读取 `extra_info` 里的 `solved_objective` / `solution` / `code_exec_res`
- `compute_score`
  - 模拟原始 reward path
  - 会提取 `<python>...</python>` 代码并通过 `executor.py` 执行
  - 如果代码里调用 `gurobipy`，就是真实跑 Gurobi

### `test_group_score_gurobi.py`
离线测试 `group_score_gurobi.py` 的脚本。

它模拟的是“reward manager 已经拿到 rollout 文本和额外字段之后，如何打分”。

- `--mode simplified`
  - 模拟 TTRL 训练中最常走的 cached reward 路径
  - 不运行 Gurobi
- `--mode original`
  - 模拟 `compute_score()` 真执行代码的路径
  - 会真实执行 Python / Gurobi
- `--gt-key`
  - 用来切换 reward 参考标签
  - 可选 `ground_truth` / `majority_gt` / `original_gt`

常用命令：

```bash
python3 recipe/ttrl_opt/test_group_score_gurobi.py
python3 recipe/ttrl_opt/test_group_score_gurobi.py --gt-key majority_gt
python3 recipe/ttrl_opt/test_group_score_gurobi.py --mode original
```

关键输出含义：

- `reward`: 当前脚本重算出来的 reward
- `expected`: JSONL 里原先保存的 score
- `diff`: 两者差值
- `answer_ok`: 是否满足 `compute_score` 里的 `answer_reward`
- `actual_group_pass_rate`: 按“组内至少一个 answer 正确”定义的 pass rate
- `current_metric_group_pass_rate`: 旧 reward 口径下的组通过率

## 2. Rollout 组分析

### `analyze_rollout_groups.py`
这个脚本模拟的是：

1. 已经有一份 rollout dump JSONL
2. 现在想离线分析每个 prompt 的 rollout group
3. 看 majority vote、真实正确率、代码成功率、LP 结构特征

它会把同一个 prompt 的多条 rollout 聚合成一组，输出 prompt 级别统计。

它能做的事：

- 统计 `maj_ratio`、`majority_matches_ground_truth`
- 统计 `sample_answer_accuracy`、`pass@k`
- 分析 objective 多样性、top2 vote gap
- 尝试把代码写成 `.lp` 文件并缓存
- 统计 LP 方向、整数变量、二进制变量

常用命令：

```bash
python3 recipe/ttrl_opt/analyze_rollout_groups.py \
  --input recipe/ttrl_opt/debug_rollout_batch4_sample.jsonl \
  --group-size 4 \
  --output recipe/ttrl_opt/debug_rollout_batch4_analysis.json
```

常见输出文件：

- `debug_rollout_batch4_analysis.json`
  - 完整的层级分析结果
- `debug_rollout_batch4_analysis.prompt_features.jsonl`
  - 每个 prompt 一行，适合进一步处理
- `debug_rollout_batch4_analysis.prompt_features.csv`
  - 适合直接看表
- `debug_rollout_batch4_sample_lp_cache/`
  - 由代码哈希索引的 LP 缓存目录

## 3. Debug 样本数据

### `debug_rollout_sample.jsonl`
小规模、手工构造的 reward 测试集。

用途：

- 验证 `compute_score_simplified` 是否按预期计分
- 验证 `majority_gt` 和 `original_gt` 切换后，reward / pass rate 怎么变化
- 覆盖答对、答错、执行失败、格式扣分、非数值 objective 等情况

适合配合：

- `test_group_score_gurobi.py`

### `debug_rollout_batch4_sample.jsonl`
更接近真实 rollout dump 的小样本。

用途：

- 模拟“每个 prompt 有 4 条 rollout”
- 看组内多数投票、pass@4、代码成功率、LP 缓存

适合配合：

- `analyze_rollout_groups.py`

### `debug_rollout_batch4_sample_lp_cache/`
离线分析时生成的 LP 缓存。

用途：

- 避免每次分析都重复执行同一段代码来导出 `.lp`
- 便于直接打开 LP 文件检查变量类型、目标方向、约束结构

## 4. 训练时的 debug 指标

### `verl/trainer/exp_ppo/ttrl_utils.py`
这里不是单独的脚本，但现在包含了 TTRL 训练时的额外统计逻辑。

它模拟的是“训练过程中，rollout 已经生成并拿到 reward 之后，如何把组级别信息写成日志指标”。

目前关键指标包括：

- `label_accuracy`
  - 现在按 `compute_score` 中的 `answer_reward` 口径判断
- `sample_answer_accuracy`
  - 当前 prompt 组内，单条 rollout 的真实答对率
- `pass@k`
  - 当前 prompt 组内，是否至少有一条 rollout 的 answer 正确
- `reward_pass@k`
  - 旧 reward-based 口径，保留用于对照
- `sample_code_pass_rate`
  - 当前 prompt 组内的代码执行成功率
- `majority_ratio`
  - 多数票占比

如果你在训练日志里看到 rate 很快满分，先区分你看的到底是：

- `reward_pass@k`
- `pass@k`
- `sample_answer_accuracy`
- validation 里的 `reward/best@N`

它们不是一个东西。

### `executor.py`
这是 `compute_score()` 真执行代码时的底层执行器。

用途：

- 批量执行提取出的 Python 代码
- 捕获 stdout
- 抽取 objective / solution / execution report

如果你要验证“测试脚本有没有真的跑 Gurobi”，最终要看是否走到了这里。

## 5. 训练入口脚本

这些脚本不是 debug 脚本本身，但常被当作 smoke test 入口。

### `test.sh`
TTRL 开启版本的主测试脚本。

关键配置：

- `custom_reward_function.path="recipe/ttrl_opt/group_score_gurobi.py"`
- `custom_reward_function.name=compute_score_simplified`
- `ttrl.enable=True`

适合测试：

- rollout -> TTRL majority GT -> cached reward -> TTRL metrics

### `baseline/grpo322.sh`
baseline GRPO 训练入口。

关键配置：

- `ttrl.enable=False`

适合测试：

- 不带 TTRL majority GT 的常规 reward 训练链路

### `baseline/rpp319.sh`
baseline Reinforce++ 训练入口。

适合测试：

- 非 GRPO 的另一条训练链路是否仍和 reward/debug 逻辑兼容

### `baseline/ttrl_exp24.sh`
TTRL 实验脚本，带 `trainer.rollout_intervals`

适合测试：

- 周期性 rollout dump
- 配合离线分析脚本检查生成质量

## 6. 推荐使用顺序

如果只是想快速定位问题，建议按下面顺序：

1. 先跑 `test_group_score_gurobi.py`
   - 看 reward 是否符合预期
2. 再跑 `analyze_rollout_groups.py`
   - 看组内多数投票和真实正确率
3. 再跑 `test.sh` 或 baseline 脚本做小规模 smoke test
   - 看训练日志里 `pass@k` / `sample_answer_accuracy` 是否合理
4. 如需检查求解模型本身，再打开 `*_lp_cache/*.lp`
   - 看目标方向、变量类型、约束结构

## 7. 一句话速查

- 想测 reward 公式：`test_group_score_gurobi.py`
- 想测真实执行 Gurobi：`test_group_score_gurobi.py --mode original`
- 想看 rollout group / majority vote：`analyze_rollout_groups.py`
- 想看 LP 文件：`debug_rollout_batch4_sample_lp_cache/`
- 想跑 TTRL 全链路：`test.sh`
- 想跑非 TTRL baseline：`baseline/grpo322.sh` 或 `baseline/rpp319.sh`
