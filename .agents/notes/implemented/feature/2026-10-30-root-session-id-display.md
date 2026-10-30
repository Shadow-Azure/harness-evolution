# Agent Note: 根会话 ID 的展示与检索

Status: implemented

[English](2026-10-30-root-session-id-display.en.md) | 中文

## Problem

根会话 ID 是 bad_cases、轨迹同步、深链、日志与工单共用的稳定键，但页面没有把它当成一等信息：错误详情页左栏只有无标签的 `session · <id>`，右栏 meta 没有 ID；Session 浏览器的卡片与概览顶部也没有 ID；搜索框只匹配 `search_text`（`lower(title + repo)`），粘贴完整根会话 ID 搜不到任何会话。用户从外部系统拿到 ID 后，既无法在页面上核对，也无法在列表里定位。

## Decision

四处展示根会话 ID，统一使用“根会话 ID · <完整 UUID>”文案：错误详情页左栏一行、错误详情页右栏 meta 的开始时间之后、Session 浏览器每张卡的 meta 行下方、Session 概览 meta 的开始时间之后。卡片与概览直接取 `SessionListItem.id`，不新增字段或请求；不加复制按钮，用户直接选中文本复制。

`GET /api/sessions?q=` 的匹配范围扩展为 `search_text LIKE` 或 `lower(id) LIKE`：查询值统一小写，复用 `_escape_like` 处理 `%`、`_`、`\`，支持完整 ID、前缀与子串。`id` 不写入 `search_text`，不改表结构、索引、归一化写入或响应契约。

## Alternatives considered

- 把 `id` 追加进 `search_text`：需要改归一化写入、回填存量行并同步 fixtures；ID 不可变，重复存储没有收益。改为查询时直接匹配主键列。
- 新增 `rootSessionId` 查询参数：前端要区分“ID 查询”和“标题查询”，还要定义互斥/组合语义；用户只有一个搜索框，扩展现有 `q` 更简单。
- 只允许精确 ID 匹配：无法前缀/片段搜索，且与标题、仓库的模糊搜索不一致。
- 在 `SessionListItem` 增加 `rootSessionId`：`id` 已经是根会话 ID，增加别名字段只会制造两套事实。
- 为 ID 增加复制按钮：需要额外的交互状态、失败降级与 E2E，超出本次“展示 + 搜索”的最小范围。

## Consequences

搜索从单列 `LIKE` 变为两列 `OR LIKE`，`%...%` 仍无法利用索引；`session_families` 是根会话粒度，行数远小于 agent/event 表，按现有 `limit` 分页可接受，若后续 p95 回退再评审索引或全文方案。Session 卡多了一行 ID，卡片高度增加、列表可能提前出现滚动条；ID 行单行省略，`title` 保留完整值。错误页与概览 meta 变长，窄屏按现有 flex 换行规则折行。契约、数据库与深链均无变化。
