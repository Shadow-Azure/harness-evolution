# Round 12 UI review

范围：进化对象侧卡改为按「可进化潜在 bad case」排序，并补上该口径的明细。

## 变更项

| # | 问题 | 修复 | 对照 |
|---|---|---|---|
| 1 | 侧卡按添加顺序排列，读者看不出先处理哪个对象 | 按「是该对象问题 + 未分析」的数量降序；相同则按潜在 bad case 总数降序、再按对象名排序；分页在排序后的列表上 | `before-side.png` → `after-side.png`（近 30 天，Explore 4 排到 code-review 3 之前） |
| 2 | 侧卡只有「关联 Session / 潜在 bad case」两个数字，缺少「可进化量」口径 | 每项下方新增「可进化潜在 bad case 数量 N（是问题 X；未分析 Y）」 | `after-side.png` |
| 3 | 抬头说明没有表达排序依据 | 抬头改为「按可进化潜在 bad case 排序」 | `after-side.png` |

## 证据

- `before-side.png`：改动前（`f46c245`），近 30 天，顺序为 deep-research → code-review → Explore。
- `after-side.png`：改动后，同一时间窗顺序变为 deep-research（5）→ Explore（4）→ code-review（3）。
