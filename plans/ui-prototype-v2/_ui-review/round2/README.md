# Round 2 UI review

范围：第 1 轮修复后的交互状态与短视口布局。

## 修复项

| # | 问题 | 修复 | 对照 |
|---|---|---|---|
| 1 | 顶栏切换与工作空间切换不写 URL，刷新丢失状态 | `v2SetPage` / `switchTab` / `v2SwitchWorkspace` 统一 `replaceState` 写入 `page/ws/u/sid/view` | `analysis-nav-refresh-loses-page.png` / `analysis-ws-refresh-resets.png` |
| 2 | 切换工作空间后旧空间的错误详情仍挂载 | 切换空间时关闭 `page-errors`，回到家族树并刷新新空间 Session | `analysis-ws-switch-on-error-detail.png` → `after-ws-switch.png` |
| 3 | “打开时间线”展示其他 Session 的硬编码时间线 | 仅对 `TL.sessionId` 渲染真实时间线；其他 Session 显示带正确标题的空态并隐藏过滤器 | `analysis-timeline-wrong-session.png` → `after-timeline-empty.png` |
| 4 | 工作空间、用户、同步浮层不响应外部点击/Esc，且可同时打开 | 新增统一关闭逻辑：外部点击、Esc、打开另一个浮层、切页时关闭 | `analysis-ws-persist-after-nav.png`、`analysis-two-popovers-open.png` → `after-popover-exclusive.png` |
| 5 | 家族树 720px 固定画布导致首屏空白，图例在折叠线以下 | 画布高度改为 `clamp(420px, calc(100vh - 280px), 720px)`；图例改为普通文档流置顶 | `before-tree.png` / `analysis-tree-first-screen.png` → `after-tree.png` |
| 6 | 1341–1396px 顶栏压缩，用户角色竖排折行 | 隐藏副标题断点提到 1400px；用户摘要与角色不收缩、不换行 | `analysis-1360-topbar-squeeze.png` |
| 7 | Case 深链首屏只露出执行流，问题详情在折叠线以下 | 错误执行流画布改为 `clamp(240px, calc(100vh - 380px), 413px)` | `analysis-err-detail-first.png` → `after-err-detail.png` |

## 证据

- `before-*.png`：第 2 轮修复前。
- `after-*.png`：第 2 轮修复后。
- `analysis-*.png`：分析 subagent 的局部证据。

浏览器视口：1408 × 611（DPR 2）。
