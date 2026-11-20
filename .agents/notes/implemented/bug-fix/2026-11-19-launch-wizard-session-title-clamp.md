# Agent Note: 启动向导第 2 步 Session 标题截断与四列同屏

Status: implemented

[English](2026-11-19-launch-wizard-session-title-clamp.en.md) | 中文

## Problem

启动自进化第 2 步把 `session_families.title` 直接渲染成 Session 标题。SWE-bench 之类的会话首条 prompt 是整段任务描述，生产表格被撑宽，`对象出现`、`对象触发点时间`、`该 Session 的 bad case 数` 三列被推出弹窗，用户无法核对关联证据。

会话列表已经用 `short`（`session_families.short_title`，标题前 120 字符）加省略号显示标题，但 `preview/sessions` 只返回完整 `title`，第 2 步拿不到这个既有字段。表格同时用 `white-space: nowrap` 且没有宽度约束，长内容会直接参与表格宽度计算。

## Decision

`SessionPreviewItem` 增加 `short`，值来自 `SessionRecord.short_title`；`title` 继续返回完整标题。前端按 `short || title` 渲染单行省略的 Session 标签，并用 `title` 属性提供完整标题悬停；Session 短 ID 保持不变。

第 2 步的会话表格改为固定布局，标题列 38%、对象出现列 15%、触发点列 22%、bad case 数列 25%，表头允许换行；长标题只在标题列内省略，不再改变其它列的宽度。`.rep-scroll` 的横向滚动保留为窄视口兜底，1440 宽视口、720 宽弹窗下四列同屏。

关联算法、bad case 统计、分页和排序都不改；`short_title` 的生成也保持原状（标题前 120 字符）。

## Alternatives considered

- **只在前端 clamp 完整 `title`**：能解决溢出，但仍把完整 prompt 传给浏览器，且没有用上会话列表已有的短标题字段；后续还要再补契约。拒绝。
- **改 `short_title` 的生成算法**：会改变会话列表、搜索与其它消费者的既有语义，超出本缺陷的展示范围。拒绝。
- **标题两行 clamp**：能多显示一点文本，但行高随内容变化，与原型单行表格不一致；单行加悬停已能满足“可区分 + 可查全文”。拒绝。
- **Session 列改为完整 UUID**：原型确实显示完整 UUID，但会加宽 Session 列，是独立的产品取舍；本次保留首尾缩写的短 ID。拒绝。

## Consequences

- 预览响应同时携带 120 字符内的 `short` 与完整 `title`；完整标题仍可能很长，但只在悬停提示中出现。
- `short_title` 仍是“标题前 120 字符”，不是语义摘要；SWE-bench 会话的可见标签仍是 prompt 前缀，只是被截断且可悬停查看全文。
- `SessionPreviewItem` 的新字段是必填，所有生成契约与消费方随本次变更更新；旧服务端响应（缺 `short`）在前端按 `title` 兜底。
- 表格固定布局在极窄视口会压缩标题列，靠 `.rep-scroll` 横向滚动查看；验收目标是 1440 宽视口下的 720 宽弹窗。
