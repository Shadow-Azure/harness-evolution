# Agent Note: Session 浏览器性能预算

Status: implemented

[English](2026-10-26-session-performance.en.md) | 中文

## Problem

Vue Flow 已按路由懒加载，Session 列表与详情也独立请求，但体积阈值只验证“懒加载存在”，没有约束入口、gzip 与 vendor 的实际大小；最大的本地 Agent 树也缺少可重复的 CI 场景。列表和概览是两个独立滚动容器，切换 Session 或使用浏览器 History 后会回到顶部，破坏长树浏览上下文。

## Decision

`scripts/verify-bundle.mjs` 把设计稿预算变成硬门禁：同步入口不超过 250KB raw 和 90KB gzip，每个手动 vendor chunk 不超过 400KB raw，并保留 Vue Flow 不在首屏同步闭包的检查。`tests/e2e/m3-session-browser.test.mjs` 使用真实 FastAPI、SQLite、Vite 与 Chrome 记录卡片就绪、交互、滚动帧、长任务、请求时序和懒加载证据；CI 用开发态 `/agent-tree-demo?variant=stress` 的 61-Agent 合成树，`pnpm performance:report --local` 改为导入、重放本地会话并选择最大真实树。两种模式的报告都含浏览器、阶段与来源字段，且不含正文与本地路径。

Session 页面用内存中的 `SessionScrollMemory` 分别保存 `.session-list` 与 `.overview` 的滚动位置。切换 Session 或 History 前进后退时，先保存离开的 Session，再在 DOM 与概览数据就绪后恢复目标 Session；刷新会重置位置，不把临时 UI 状态写入 URL 或跨标签共享存储。

## Alternatives considered

- 只测 Vue Flow 是否动态加载：无法发现入口体积膨胀或单个 vendor 失控。
- 依赖本地 61-Agent 轨迹做 CI：本地数据被 gitignore，CI 结果不可复现。
- 把滚动位置写进 URL：会话深链已承载 Agent 与 evidence，再混入视口临时状态会扩大 canonical contract。

## Consequences

CI 能阻断体积和明显性能回归，同时用合成大树保持稳定。预算失败会指出具体阶段与原始读数；真实本地极大树的绝对 TTFB 不进入硬门禁，而由性能报告单独观察。滚动位置只在当前 SPA 生命周期和标签内有效，刷新后的重置行为明确且可测试。
