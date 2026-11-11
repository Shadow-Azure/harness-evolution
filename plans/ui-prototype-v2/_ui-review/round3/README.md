# Round 3 UI review

范围：内容自洽、危险默认值与 1280px 桌面宽度下的布局。

## 修复项

| # | 问题 | 修复 | 对照 |
|---|---|---|---|
| 1 | 已完成运行的未接纳轮次显示「未接纳 +2.6」，与「评测无收益」文案矛盾 | 被拒绝轮次的候选分改为低于 current（81.2 → 80.8），拒绝态与分差方向一致 | `before-reject-eval.png` → `after-reject-eval.png` |
| 2 | 测试集终评副标题出现字面量「M 轮迭代」 | 改为实际聚类轮数 `run.clusters.length` | `before-final-metrics.png` → `after-final-metrics.png` |
| 3 | 问题复现率上升 1.2pp 被标成代表收益的绿色 | `evDelta` 支持 `lowerBetter`，复现率越低越好，上升显示为红色 | `before-final-metrics.png` → `after-final-metrics.png` |
| 4 | 添加成员默认角色为权限最高的「空间管理员」 | 默认选中「成员」，空间管理员仍可由全局管理员显式授予 | `before-member-default.png` → `after-member-default.png` |
| 5 | 空间管理内容卡 `min-height: 420px`，列表页底部留出约 107px 空白 | 最小高度收到 340px，工作空间与成员页贴合内容 | `before-admin-height.png` → `after-admin-height.png` |
| 6 | 运行卡同时显示「第 5/7 步」和「44%」，读者容易理解为进度矛盾 | 百分比标注为「总进度」，与内部阶段数区分 | `before-run-progress.png` → `after-run-progress.png` |
| 7 | 1280px 下 Session 统计条末项「bad case/百步」折成两行 | 标签禁止换行并收紧单元格内边距 | `before-statstrip-1280.png` → `after-statstrip-1280.png` |

## 证据

- `before-*.png`：第 3 轮修复前。
- `after-*.png`：第 3 轮修复后。

浏览器视口：1280 × 800（DPR 2），用于覆盖 1280px 笔记本宽度；短视口 1408 × 611 的回归见第 1、2 轮证据。
