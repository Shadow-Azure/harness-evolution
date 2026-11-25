# Agent Note: 上游目录同步的 bad case 类型与标题归一化

Status: implemented

[English](2026-11-25-bad-case-sync-type-title-normalization.en.md) | 中文

## Problem

目录同步把上游 bad_cases 按页塞进 `BadCasePage` 严格校验，而 `BadCaseItem` 把上游数据当成已满足本地 `bad_cases` 约束的成品：`bad_case_type` 必须是 1–16 字符的非空字符串，`title` 上限 255。上游真实数据里已经出现 `bad_case_type` 为 null 与 `title` 超长的条目，页级校验又是全有或全无——页内只要有一条这样的 item，整页 `model_validate` 即失败并被收敛为 `BAD_CASE_QUERY_INVALID_RESPONSE`，该页回滚、游标不动，下一轮定时任务从同一游标重试同一页，单条脏数据成为 poison pill，后续所有 bad case 都同步不进来。m6-17 已为 `object_name` / `object_type` 做空值降级（[2026-10-30-bad-case-catalog-sync.md](../feature/2026-10-30-bad-case-catalog-sync.md)），但把这两个字段明确列为非目标；200 口径当时在代码里并不存在，实测的截断阈值就是列宽 255。

## Decision

沿用 m6-17 的「传输放宽、写入归一」分层，只改两处。传输层 `BadCaseItem`：`bad_case_type` 改为可空（None 或缺失放行，非空仍校验 1–16 字符），`title` 去掉 255 上限、保留非空；`extra="forbid"`、时间戳时区校验与 `BadCasePage` 的排序、唯一、limit/total 校验全部不动。写入层 `_row`：`bad_case_type=item.bad_case_type or "self"`，`title=item.title[:200]`；命中任一条时记录一次结构化 info 日志，extra 携带 `badCaseId` 与命中的字段名，不新增状态列。表结构与列宽、读路径、页级事务与游标语义都不变。

## Alternatives considered

- **把默认值与截断做进传输模型**：解析层改写值会让模型不再忠实表达上游形状，上游漂移在这一层就不可见，未来的其他消费方拿到的是被改写过的数据；归一化是本地写入策略，不属于上游契约。拒绝。
- **维持严格模型，等上游修复数据**：缺陷的成因正是上游与本地契约错位而同步层无处容身；上游不配合时同步永久停滞，每轮重试消耗预算，浮层只剩一个稳定错误码，定位不到具体 case 或字段。拒绝。
- **跳过坏行、其余照常落库**：破坏页级原子性与游标推进语义，制造静默数据空洞；本 issue 明确列为非目标。拒绝。
- **title 按 255 截断（跟随列宽）**：205–255 字符的标题会原样落库，与需求的 200 口径不符；200 是归因侧短标题预算的既有口径（`attribution.py` 与 `attribution_executor.py` 都取 `[:200]`），读路径按 200 消费。拒绝。
- **把 `title` 列宽收紧到 200 并加迁移**：截断后写入上限 200，永远触碰不到 255 列宽；改列宽牵动存量行与迁移，本 issue 不做任何表变更。拒绝。

## Consequences

- null/缺失 type 与超长标题的页都能解析并落库，同步继续推进；显式 `self` / `discovery` 与不超过 200 字符的标题保持原样。
- 标题截断是有损的：超出 200 的尾部被永久丢弃，游标只增不减、旧 id 不会重推，被截内容无法回捞；可接受是因为 `title` 的设计语义就是短标题，读路径展示与归因预算都按 200 口径消费。
- 列宽保持 255：写入上限 200 留有余量，本次修复不引入迁移、不触碰存量行。
- 归一化的可观测性只有 info 日志（`badCaseId` + 字段名），用于区分上游漂移与本地逻辑错误；截断值不回写上游。
- 两个字段之外的非法形状（缺必填字段、空 `title`、type 超 16 字符、naive 时间戳等）仍整页拒绝并回滚，坏页不推进游标的既有语义不变。
