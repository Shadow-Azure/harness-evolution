# Agent Note: 运行详情第 2 步的短 Session 标签与固定列宽

Status: implemented

[English](2026-11-20-run-detail-session-short-title.en.md) | 中文

## Problem

「自进化 → 运行详情 → 第 2 步 Session 关联」把 `sessionRows[].title` 原样渲染为 Session 单元格标题。Session 的 `title` 按设计就是首条用户 prompt 全文，SWE-bench 类样本是 3337 字符的整段任务 prompt；在 1500×837 下首行被撑到 329px、Session 列占 1247px，`对象触发点 / bad case / 潜在 bad case` 三列被压到 43–79px。关联证据无法核对，两条 Session 除 ID 外也不可区分。生产/原型量化对照与根因见 GitHub #440。

短标签数据本身已经存在：`session_families.short_title` 与关联结果 `AssociatedSession.short` 都有值。但准备阶段写 `stats.sessionRows` 时只持久化 `sessionId/title/objectTriggerAt/badCaseCount`，`StepSessionRow` 契约也没有 `short`；前端只能拿到完整标题。展示层又是自动布局、允许换行，长 prompt 参与列宽计算。启动向导第 2 步（#404）已用「短标签 + 完整标题悬停 + 固定列宽」修过同一类问题，运行详情的这条数据通路当时没有覆盖。

## Decision

- 数据通路补齐：准备阶段把 `AssociatedSession.short` 写入 `stats.sessionRows[].short`；`StepSessionRow` 增加可空 `short`，`steps/sessions` 原样返回。存量 run 的持久化行没有 `short` 时，读取侧回退 `title[:120]`，不要求重新准备历史 run。
- 展示层收口：`StepSessions.vue` 用 `row.short || row.title || "未命名 Session"` 渲染可见标签，`title` 属性保留完整 `title`；标题单行省略。表格改 `table-layout: fixed`，用 `colgroup` 固定触发点列 220px、两个计数列各 130px，并在窄容器保留横向滚动（`min-width: 680px`）。
- 保持四列与既有语义：不加原型多出的「对象出现」列，不改关联算法、bad case 统计、分页排序与 Session ID 格式。
- 回归分三层：API 断言准备阶段持久化 `short`、阶段接口返回 `short`、存量行回退；组件测试用超长标题断言可见短标签与完整悬停文本；真实浏览器 E2E 断言首行高度受控、Session 列不占满、四列表头宽度与表格无横向溢出。

## Alternatives considered

- **只在前端截断 `row.title`**：能压住高度，但显示的是 prompt 前缀而不是数据侧已有的短标签，还把 120 字符截断规则复制到前端；数据通路仍缺字段。拒绝。
- **保留完整标题并做两行 clamp**：行高仍会被长 prompt 推高，自动布局下长字符串也继续参与列宽计算；issue 要求单行/两行量级并保证四列同屏，固定单行加短标签更直接。拒绝。
- **只加 `max-width`、继续自动布局**：`title` 是不可断行的长文本时仍可能扩列，列宽也无法稳定。固定布局才能保证三列证据列不被挤出。拒绝。
- **重新准备历史 run 以回填 `short`**：成本高且没有必要；读取侧回退 `title[:120]` 已能让存量 run 正常渲染，新 run 才使用真正的 `short_title`。拒绝。
- **补齐原型多出的「对象出现」列**：列口径差异不是本 issue 的根因，也会改变表格信息架构；留给单独设计确认。拒绝。

## Consequences

- 1440/1500 宽视口下第 2 步四列同屏，超长 prompt 的 Session 行保持单行量级，完整标题仍可悬停查看；关联 Session 数、分页、排序与跳过统计不变。
- 新 run 的短标签来自 `session_families.short_title`；存量 run 回退到 `title[:120]`，仍可能是 prompt 前缀，真正的语义标题需要另开问题从上游或首条 prompt 提取。
- `StepSessionRow` 新增可选字段，接口向后兼容；`openapi.json` 与生成类型由 `pnpm contract:generate` 产出。
- E2E fixture 使用合成 3337 字符 prompt 验证布局，不读取或提交生产 Session 内容。
