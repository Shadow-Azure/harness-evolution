# Agent Note: 总览展示可定位的 bad case 触发行

Status: implemented

[English](2026-11-18-bad-case-trigger-line.en.md) | 中文

## Problem

bad case 总览的「触发点」列长期显示 `triggerAt`，而该字段在 m9-04 坐标落地前临时等于 `createdAt`。用户看到的日期时间既不能定位到执行流的日志行，又容易被误读为对象真实触发时间。项目原型在同一列展示 `L0`、`L58` 这类 0-based 日志行；错误详情执行流则按 `SessionTree.badCases[].anchor` 定位同一行。缺少的是一条从上报数据到总览读模型再到表格列的可空触发行通道，同时必须保持旧客户端读取 `triggerAt` 不崩溃。

## Decision

- `bad_cases` 新增可空 `trigger_line`（`INTEGER`），迁移 `0022` 只在列缺失时添加；历史行保持 `NULL`，不写猜测值。外部契约同步声明该列，`BadCaseIngest` 接受可选非负 `triggerLine`，目录同步也透传上游同名字段。
- `BadCaseListItem` 增加必填但可空的 `triggerLine`；总览 repository 在分页查询中直接投影 `bad_cases.trigger_line`，service 原样映射，不额外查询 Session，也不从 `createdAt`、`metaData.line` 或事件下标推导。
- `BadCaseTable` 的列名恢复为「触发点」：有行号显示 `L<n>`，为空显示「—」，并同时设置 `title` 与 `aria-label` 说明完整值或缺失原因。深链结构不变。
- `triggerAt` 保留在契约中供旧客户端兼容，但不再是总览「触发点」列的值；`triggerLine` 与错误详情 BC marker 指向同一份日志行坐标，写入方负责让同一 case 的两者一致。历史 NULL 在总览显示「—」，详情仍可按 `anchor` 回退定位。
- 测试覆盖 API 有值/空值、OpenAPI 契约快照、前端 `L<n>`/「—」与可访问说明，以及一条真实归一化 Session 的 E2E：总览行与错误详情选中的 BC marker 都显示同一 `L2`。

## Alternatives considered

- **用 `createdAt` 或 `triggerAt` 继续充当触发点**：这是当前缺陷本身，日期无法定位日志行，也会误导用户把上报时间当触发时间；拒绝。
- **从 `metaData.line` 自动回填 `trigger_line`**：`metaData` 是任意上报打点，`line` 可能指向源码文件而不是 Session 日志行；只有上报方显式给出 `triggerLine` 才写入，避免制造看似精确的错值。
- **用事件下标当触发行**：`eventIndex` 是某个 agent 内的事件序号，不是日志行；两者量纲不同，会直接把 marker 放到错误位置。
- **总览读时现算 anchor**：能复用详情逻辑，但每页每行都要加载 Session 事件，列表查询会退化为批量 N+1；触发行是上报时已知的稳定坐标，落在 `bad_cases` 一列即可。
- **在总览行复制详情 DTO 的 `anchor`**：同一坐标会出现两份字段，且总览只需要行号；保留 `triggerLine` 单字段，详情继续用既有 `anchor`。
- **为历史 NULL 行批量回填最近事件行**：没有证据时回填等于伪造定位；坚持 NULL 显示「—」，把回填留给有原始事实的后续数据路径。

## Consequences

- 生产部署需要执行迁移 `0022`；SQLite 与 MySQL 都走 batch add-column，列已存在时迁移幂等跳过。
- 升级后历史 bad case 的 `trigger_line` 为 NULL，总览会显示「—」而不是日期；这是诚实空值，不是数据丢失。上报方需要在数据可用后重新上报或由后续数据通道补写。
- `triggerLine` 与详情 `anchor` 的一致性依赖写入方提供正确行号；读取层不做纠正或猜测。若某条上报的 `triggerLine` 与 Session 事件不一致，总览显示上报值，详情仍按 anchor 定位，测试只覆盖一致数据。
- `triggerAt` 仍出现在 JSON 中并等于 `createdAt`，旧客户端不受影响；新客户端不得再把它渲染成「触发点」或用作排序键。
- 目录同步现在接受上游 `trigger_line`，但上游契约未提供时保持 NULL，不影响既有同步。
