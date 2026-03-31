# Not-even Sampled: servings 被建成连续变量

## 基本信息

- 来源文件: `82.jsonl`
- prompt_index: `11`
- 分类: `not-even sampled`
- ground truth / 正确答案: `7.5`
- majority answer: `6.16071428571`
- sampled answer 分布: `{'6.16071428571': 32}`
- 所有 `32/32` 个 sampled rollout 都输出了同一个错误答案

## majority 错误答案成因

这组样本的系统性错误是: **把“servings”建成了连续变量，而不是整数变量。**

从原始代码看，4 个决策变量都只是普通连续变量，没有 `vtype=GRB.INTEGER` 或 `GRB.INT`。这会允许出现分数份数，例如 `0.892857` 份米饭、`1.964286` 份汤，从而把最小成本压到 `6.16071428571`。

## 原始文本片段（标出错误点）

```python
# Define decision variables
x1 = model.addVar(name="Chicken_Breast", lb=0, ub=10)
x2 = model.addVar(name="Brown_Rice", lb=0, ub=15)
x3 = model.addVar(name="Avocado", lb=0, ub=5)
x4 = model.addVar(name="Lentil_Soup", lb=0, ub=12)
```

标注:

- `[错误点]` `addVar(...)` 默认是连续变量
- `[错误点]` 题目语义是 daily meals / servings，这份数据里的 ground truth 对应 **整数份数**；continuous relaxation 得到的是更低但不被接受的答案

## 正确答案与复核

我用同一组约束分别复算了连续版和整数版:

- continuous model: objective = `6.160714285714285`, solution = `[0.0, 0.8928571428571427, 0.35714285714285715, 1.9642857142857142]`
- integer model: objective = `7.5`, solution = `[1.0, 3.0, 0.0, 0.0]`

因此:

- sampled 的统一错误答案: `6.16071428571`
- 正确答案: `7.5`

## 结论

这是一个 **not-even sampled** 的典型例子:

- 所有 rollout 都共享同一种建模假设错误
- 因而整个样本组里根本没有出现正确答案
- majority vote 也就没有纠错空间
