# Majority Vote Wrong: 固定成本被整体漏掉

## 基本信息

- 来源文件: `12.jsonl`
- prompt_index: `4`
- 分类: `majority vote wrong`
- ground truth / 正确答案: `13835`
- majority answer: `13905`
- sampled answer 分布: `{'13905': 30, "None | gurobipy._exception.GurobiError: Unknown parameter 'OptimizeLevel'": 1, '13835': 1}`
- majority 错误 rollout: `local_idx=0`, `solved_objective=13905.0`
- minority 正确 rollout: `local_idx=23`, `solved_objective=13835.0`

## majority 错误答案成因

这组 rollout 的主错误非常集中: **把固定 operating cost `30 + 40 = 70` 从真正求解的 objective 里删掉了。**

题目给出的目标是:

`(50 * Q1 - 30 - 1 * L1 - 1 * E1) + (60 * Q2 - 40 - 1 * L2 - 1 * E2) - 2 * S`

但 majority rollout 真正送进 Gurobi 的 objective 变成了:

`50*Q1 + 60*Q2 - L1 - L2 - E1 - E2 - 2*S`

因此 objective 被系统性高估 `70`:

- majority 错误答案: `13905`
- 正确答案: `13835`
- 差值: `70`

## 原始文本片段（majority wrong，标出错误点）

```python
# Objective function: maximize net economic benefit
# Z = 50Q1 + 60Q2 - L1 - L2 - E1 - E2 - 2*S
model.setObjective(50*Q1 + 60*Q2 - L1 - L2 - E1 - E2 - 2*S, GRB.MAXIMIZE)

print(f"Total Net Economic Benefit: {{model.objVal:.2f}}")
```

标注:

- `[错误点]` `model.setObjective(...)` 里 **缺少 `-70`**，也就是漏掉了两段管道的固定成本 `-30` 和 `-40`。
- `[错误点]` 后续 `model.objVal` 直接被当成最终答案输出，于是整组大多数样本都稳定落在 `13905`。

## minority correct 的原始文本

```python
# Set objective: maximize total net benefit
model.setObjective(
    50*Q1 + 60*Q2 - L1 - L2 - E1 - E2 - 2*S - 70,
    GRB.MAXIMIZE
)
```

这个 minority correct rollout 明确把固定成本并入 objective，所以得到的结果是 `13835`，与 ground truth 一致。

## 结论

这是一个典型的 **stable-but-wrong majority**:

- 多数样本共享同一个错误建模模板
- 少数样本把固定成本保留下来，答案正确
- 因为错误模板占了 `30/32`，所以 majority vote 被带偏
