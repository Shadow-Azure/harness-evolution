# Agent Note: 错误详情与归因双 Tab

Status: implemented

[English](2026-10-26-error-detail.en.md) | 中文

## Problem

问题卡和归因 API 已能提供真实数据，但用户需要一个可刷新、可分享的错误详情入口，同时避免把问题描述、归因推导、执行流过滤和跨会话归属判断散落到多个页面。

## Decision

`/sessions/:sid/errors?case=<id>&tab=desc|attr` 是错误详情的状态源。页面固定使用左侧问题列表、右上过滤后的 Agent 执行流、右下“问题描述/归因分析”双 Tab；`case` 与 `tab` 从 URL 恢复，选择“全部错误”时清除二者。执行流只保留选中问题的 anchor 和原有 Agent/Skill 结构。跨 Session 归属由 bad-case API 的 `409 BAD_CASE_SESSION_MISMATCH` 权威判定，404 与加载失败分别在页面层降级。

问题描述依次展示真实 ID、状态、摘要、关键事实和关联对象。归因 Tab 固定按结论、分类或非问题原因、定位对象、问题描述、推导过程排列；未分析、失败和 Probe 缺失都有独立状态。Markdown 只允许安全链接与内容，不执行外部 HTML。

## Alternatives considered

- 把错误详情放在 Session 概览弹窗：拒绝，无法承载长归因和可分享深链。
- 前端按 caseId 猜测会话归属：拒绝，重复外部契约且可能错误放行跨会话数据。
- 保留完整执行流再高亮问题：拒绝，问题较多时无法聚焦当前证据链，也不符合原型的三栏阅读顺序。

## Consequences

错误详情可刷新、前进后退和新窗口恢复，且不会提前引入 AI 归因生成。页面依赖 bad-case 查询与 Agent tree 两条读链；新增 Tab、问题字段或 anchor 规则时必须同步 URL parser、组件测试和真实 Chrome E2E。错误详情不改变外部三表只读边界。
