# Round 4 UI review

范围：默认策略文案一致性、向导滚动可见性、登录与鉴权说明的可读性。

## 修复项

| # | 问题 | 修复 | 对照 |
|---|---|---|---|
| 1 | 默认潜在策略在运行详情与向导里混用 `+` 与 `∪`，`+` 容易被读成加分或叠加 | 统一为「对象自身 self 上报 或 触发点在对象触发点之后」 | `before-wizard-scroll.png` → `after-wizard-scroll.png` |
| 2 | 向导第 3 步内容超出 `66vh`，macOS overlay 滚动条不可见，末行被底栏截断且没有提示 | 为弹窗正文提供常驻的 10px 滚动条轨道，内容溢出时始终可见 | `before-wizard-scroll.png` → `after-wizard-scroll.png` |
| 3 | 登录页第三条说明只剩「话。」独占一行；页脚仍指向旧的 `plans/14-15-ui-prototype/` | 说明改为均衡两行；基线路径改为 `plans/ui-prototype-v2/harness-evolution.html` | `before-login-copy.png` → `after-login-copy.png` |
| 4 | 鉴权接入说明混用英文 `membership`，短视口下副标题挤占标题行 | 统一为「成员关系」并收紧表述，标题与副标题恢复主次层级 | `before-auth-copy.png` → `after-auth-copy.png` |
| 5 | 自定义策略说明写成「在默认策略上叠加规则」，与「勾选规则重新组合」的实现语义不符 | 改为「勾选规则组合成策略；与默认策略不同时会在运行详情中记录策略快照。」 | `after-custom-policy.png` |

## 证据

- `before-*.png`：第 4 轮修复前。
- `after-*.png`：第 4 轮修复后。
- `after-custom-policy.png`：自定义策略说明无独立 before，旧文案位于向导第 1 步，修复后随本次截图复核。
- `after-run-policy.png`：运行详情策略徽标，确认统一文案在窄卡片内不溢出。

浏览器视口：1408 × 611（默认桌面短视口），用于复现向导正文超出与鉴权页副标题拥挤。

> 注：第 6 轮复核确认 V1 原型才是视觉基线，页脚路径已在 round6 恢复为 `plans/14-15-ui-prototype/harness-evolution.html`。
