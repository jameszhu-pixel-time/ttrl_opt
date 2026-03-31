# Min/Max Inconsistent Prompt: 同题分裂成 340 / 360 / 410 三类回复

## 基本信息

- 来源文件: `14.jsonl`
- prompt_index: `28`
- 分类: `min/max inconsistent prompt`
- ground truth / 正确答案: `340`
- majority answer: `410`
- sampled answer 分布: `{'410': 9, '360': 7, '340': 7, '290': 2, 'None / exec error': 4, '320': 1, '-290': 1, '-360': 1}`
- 方向统计: `{'GRB.MAXIMIZE': 20, 'GRB.MINIMIZE': 12}`
- majority 错误 rollout: `local_idx=3`, `solved_objective=410.0`
- min-direction 代表 rollout: `local_idx=0`, `solved_objective=360.0`
- correct 代表 rollout: `local_idx=25`, `solved_objective=340.0`

## 错误答案成因

这是一个很典型的 **prompt 级 min/max 漂移**:

- 一部分 rollout 保留了题面 objective 的写法 `700 - cost`，直接做 `GRB.MAXIMIZE`
- 一部分 rollout 把它改写成“等价的最小化 cost”，转成 `GRB.MINIMIZE`
- 但真正的错误不只在方向上，还在于 **不同分支后续输出的量已经不是同一个量**

这组样本里至少稳定出现了三类回复:

1. `max + 原题 4 变量模型`，输出正确答案 `340`
2. `min + 原题 4 变量模型`，求出来的是最小成本 `360`，但没有再换回题目要的 `700 - cost`，所以错把 `360` 当最终答案
3. `max + 重建成 8 变量 f_ijt 模型`，把原题的 4 个变量改成按 stage 展开的 8 个变量，并把成本系数改写为逐期价格，最后得到 majority 错误答案 `410`

因此，这不是单一 bug，而是 **同一 prompt 被不同 rollout 重解释之后，分裂成多个彼此不兼容的求解模板**。

## 三类回复概览

- `A. 正确保留原题`: `GRB.MAXIMIZE`，目标仍是 `700 - (3f00 + 7f01 + 11f10 + 15f11)`，答案 `340`
- `B. 改写成最小成本后直接报 cost`: `GRB.MINIMIZE`，模型本身接近等价，但最后输出的是 `360` 而不是 `340`
- `C. 重新发明变量和成本结构`: `GRB.MAXIMIZE`，把 4 变量改成 8 变量 `f_ijt`，majority 稳定落在 `410`

这三类已经覆盖了这个 prompt 里最主要的回答形态；其余 `290 / 320 / -290 / -360 / exec error` 只是更边缘的派生错误。

## 原始文本片段（标出错误点）

代表类 A: `max + correct (340)`

```python
# Objective function: Maximize (Total Yield - Total Cost)
# Total yield = 700
# Total cost = 3*f00 + 7*f01 + 11*f10 + 15*f11
model.setObjective(700 - (3*f00 + 7*f01 + 11*f10 + 15*f11), GRB.MAXIMIZE)
```

标注:

- `[正确]` 保留了题面给出的 `700 - cost` 形式
- `[正确]` 仍然使用原题的 4 个变量 `f00, f01, f10, f11`

代表类 B: `min + wrong (360)`

```python
# Objective: minimize total cost
model.setObjective(3*f00 + 7*f01 + 11*f10 + 15*f11, GRB.MINIMIZE)

print(f"\nTotal Fertilizer Cost = {total_cost:.2f}")
print(f"Total Crop Yield = {total_yield}")
print(f"Objective Value = {total_yield - total_cost:.2f}")
```

标注:

- `[分歧点]` 这里把题面 objective 改写成了 `GRB.MINIMIZE`
- `[错误点]` 实际被 `solved_objective` 记录下来的量是 **最小成本 `360`**，不是题目要求的净收益 `340`
- `[结果]` 所以这一路 rollout 虽然常常能算出同一组可行解，但上报答案时口径错了

代表类 C: `max + majority wrong (410)`

```python
# Decision variables: f[i][j][t] for i=0,1; j=0,1; t=0,1
f[0, 0, 0] = model.addVar(vtype=GRB.CONTINUOUS, name="f_000", lb=0)
f[0, 0, 1] = model.addVar(vtype=GRB.CONTINUOUS, name="f_001", lb=0)
...

cost = f[0,0,0] + 2*f[0,0,1] + 3*f[0,1,0] + 4*f[0,1,1] + 5*f[1,0,0] + 6*f[1,0,1] + 7*f[1,1,0] + 8*f[1,1,1]
model.setObjective(700 - cost, GRB.MAXIMIZE)
```

标注:

- `[错误点]` 原题变量是 `f_ij`，这里只有 4 个；这一支把它重建成了 8 个 `f_ijt`
- `[错误点]` 原题成本已经按题目写成 `3, 7, 11, 15` 四个聚合系数；这里又改写成逐 stage 的 `1..8`
- `[结果]` 这相当于求解了一个 **不同的问题**，于是 majority 稳定输出 `410`

## 正确答案与复核

正确 rollout 保留的是原题 4 变量模型:

- objective: `max 700 - (3f00 + 7f01 + 11f10 + 15f11)`
- 正确最优值: `340`

把它等价改写成最小化 cost 也不是不可以，但必须满足两件事:

- 约束不能被重写成另一个问题
- 最终回报给题目的答案必须再换回 `700 - cost`

这个 prompt 的 min 分支没有稳定做到第二点，而 majority 的 max 分支里又有相当一部分直接改成了 8 变量新模型，所以最后主答案被拉到了 `410`。

## 结论

这是一个比普通 `majority wrong` 更细的例子:

- 同一道题内部先发生了 `maximize / minimize` 的建模分叉
- 分叉后又进一步衍生出“正确 max 模板”“报错口径的 min 模板”“重建变量的 max 模板”三类主回复
- 结果不是简单地围绕一个错误答案波动，而是分裂成 `340 / 360 / 410` 三个主峰
