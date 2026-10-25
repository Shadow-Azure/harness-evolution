# Agent Note: Session 浏览器原型落地

Status: implemented

[English](2026-10-26-session-browser.en.md) | 中文

## Problem

Session 查询 API 已返回真实 root session 与整树统计，但前端仍是占位页。原型要求用户在 360px 左栏直接按状态、失败密度和问题密度分诊，并在右侧查看统计概览；如果由前端重新排序或聚合，URL、API 真值和原型视觉会分叉。

## Decision

Session 浏览器以后端返回顺序为唯一列表顺序，所有搜索、状态和排序值写回 URL query，选中根会话写入 `/sessions/:sessionId`。`/sessions` 有数据时自动选中第一项；筛选后不存在的选中项会替换为当前结果首项。列表与概览各自请求，概览以 detail 响应为准，只有 detail 尚在途中时才以当前列表项承接骨架；任一侧失败不会阻断另一侧。问题数使用 `stats.badCases`，双密度条直接使用后端百消息统计并按 3/100 满格截断。

Session 路由使用全宽 workspace，在 56px 顶栏下直接铺设 360px `--bg-panel` 左栏与自适应右栏，不再套圆角浮层。状态和排序各占一行标签，九项 StatStrip 下的执行流占位沿用原型 720px 面板尺度，错误详情 CTA 位于概览标题区。Session 卡只在 option 数据态启用 listbox/option 语义，使用 roving tabindex、方向键与 Home/End、`aria-selected` 和可读状态文本；搜索 timer 在路由外部变化时作废，避免历史导航被旧输入覆盖。执行流不请求 `/tree`，错误详情 CTA 在 m4 页面就绪前保持禁用，避免假链接。

## Alternatives considered

- 前端拉取 `/tree` 自行计算：会重复后端口径，并让列表被未来图能力阻塞。
- 选中状态只存组件内存：刷新和前进后退无法恢复，违反原型验收。
- 问题数硬编码为零：外部 `bad_cases` 已是只读真值，硬编码会误导分诊。

## Consequences

列表与概览共享同一契约但保留独立状态，URL 可直接分享和恢复。移动端在 860px 以下改为单列，四张卡仍在同一工作区内可达。执行流和错误详情由后续 issue 交付；当前页面不会伪造图或问题详情。
