# Round 5 UI review

范围：进化对象总览的对象维度分布补全，以及总览页「启动自进化」的浮窗化。

## 变更项

| # | 问题 | 修复 | 对照 |
|---|---|---|---|
| 1 | 进化对象总览只有「不同进化对象的潜在 bad case」一块对象分布，读者无法判断每个对象关联了多少 Session、其中多少 Session 真的产生了潜在 bad case | 趋势图注释下新增「不同进化对象的关联 Session」：柱长按关联 Session 数归一，蓝色为含潜在 bad case 的 Session、灰色为仅关联；数字写作 `6 · 含潜在 5 / 仅关联 1` | `before-targets.png` → `after-targets.png` |
| 2 | 潜在 bad case 只能按对象看，回答不了「这些 case 从哪些来源上报、去重后有多少」 | 卡片底部新增「潜在 bad case 来源分布」：柱长按未去重条数归一，去重键为 bad case ID；数字写作 `18（去重后：12）`，未去重合计等于统计条「潜在 bad case」 | `before-targets.png` → `after-targets.png` |
| 3 | 总览页点「启动自进化」会先跳到自进化历史页再弹向导，多一次整页切换，并丢掉总览当前的时间窗与对象筛选 | 入口改为直接打开向导浮窗：新增 `evWizardHost()`，自进化页内仍挂 `#modal-root`，其它页挂全局 `#v2Modal`；四步都在浮窗内完成，确认启动后才写运行 hash 并 `V2.setPage('evo')` 整页跳转 | `after-wizard-overlay.png` → `after-start-jump.png` |

## 证据

- `before-*.png`：本轮改动前（`e4aad41`）。
- `after-*.png`：本轮改动后。
- `after-wizard-overlay.png`、`after-start-jump.png`：浮窗与启动后落地，由 CDP 真实点击驱动；旧行为是直接换页，无法用同一静态帧对照。
- 浏览器视口：1440 × 1100（对照图）/ 1440 × 900（浮窗与落地图）。
