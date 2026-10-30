# Session 错误页与浏览器展示根会话 ID 并支持按 ID 搜索

[English](m6-root-session-id.en.md) | 中文

```yaml flow
kind: issue
id: m6-18
milestone: m6
depends:
  - m3-01
  - m4-04
priority: P1
status: done
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
  - docs/**
  - reports/**
adr: []
github:
  number: 181
  url: https://github.com/Shadow-Azure/harness-evolution/issues/181
```

## 背景

根会话 ID 是问题上报、轨迹同步、深链和运维排障共用的稳定键，但页面没有把它当成一等信息：错误详情页左栏只有一行未加标签的 `session · <id>`，右栏顶部元信息完全没有根会话 ID；Session 浏览器的左栏会话卡和右栏会话概览顶部也没有根会话 ID，卡片只在 DOM 的 `data-session-id` 里藏着这个值。与此同时，Session 浏览器的搜索框只匹配标题与仓库（`session_families.search_text`），用户从 bad_cases、日志或工单里拿到一个根会话 ID 后粘贴进搜索框，得不到任何结果，只能手工翻列表。排查一个错误时，用户往往同时开着错误页、问题清单和上游系统，缺少可对照、可复制的根会话 ID 会直接增加定位成本。

## 目标

- 错误详情页左栏的会话信息框明确显示“根会话 ID”标签与完整值，不再只是一行无标签的 `session · id`。
- 错误详情页右栏顶部元信息增加根会话 ID，放在开始时间之后、repo 之前。
- Session 浏览器左栏每张会话卡增加一行“根会话 ID · <完整 ID>”，不只当前选中的卡。
- Session 浏览器右栏会话概览的顶部 meta 增加根会话 ID，放在开始时间之后、repo 之前。
- Session 浏览器搜索框支持按根会话 ID 过滤，完整 ID、前缀与子串都能命中；大小写不敏感；同时保留标题与仓库搜索。
- 后端只扩展 `GET /api/sessions` 的 `q` 匹配范围，不新增接口、不改响应字段。
- 搜索框 placeholder 与无障碍标签同步说明支持根会话 ID。
- 单元测试与浏览器 E2E 覆盖四处展示和搜索路径。

## 设计依据

- [13 根会话 ID 的展示与检索](../../../plans/fullstack-design/13-root-session-id.md)：根会话 ID 的数据来源、展示位置、搜索语义与边界。
- [03 §7 错误详情与归因](../../../plans/fullstack-design/03-frontend-architecture.md)：错误页左右栏的信息层级。
- [07 §3.1 会话列表](../../../plans/fullstack-design/07-backend-implementation.md)：`q` 的搜索实现与 `search_text` 的边界。
- [06 §3.2 session_families](../../../plans/fullstack-design/06-database-design.md)：`id` 是根会话主键，`search_text` 只含 `lower(title + repo)`。
- 实现冲突时以 13 章为准。

## 实现内容

- 后端 `app/db/crud/sessions.py`：`list_sessions` 在 `q` 非空时把条件改为 `search_text LIKE` 或根会话 `id LIKE`；查询值统一小写并复用现有 `_escape_like`，避免 `%`、`_` 被当成通配符；排序、`limit`、状态过滤不变。
- 前端 `pages/errors/components/ErrorSidebar.vue`：左栏会话信息框改成带“根会话 ID”标签的单独一行，`title` 与文本都使用完整 ID；保留现有标题与返回入口。
- 前端 `pages/errors/Index.vue`：`error-meta` 在开始时间之后增加根会话 ID 项（等宽字体），使用路由解析后的 `sessionId`，与现有元信息同一换行规则。
- 前端 `pages/sessions/components/SessionCard.vue`：每张卡在 repo/时长/工具/子 agent 行下面增加“根会话 ID · <完整 ID>”一行，使用 `item.id`，不改变点击/选中/键盘语义。
- 前端 `pages/sessions/components/SessionOverview.vue`：概览 meta 在开始时间之后增加根会话 ID，使用 `item.id`，与错误页同一格式。
- 前端 `pages/sessions/components/SearchBox.vue`：placeholder 改为“搜索标题、仓库或根会话 ID”，`aria-label` 同步；输入行为与 300ms 防抖不变。
- 测试：API 覆盖完整 ID、前缀、大小写与 LIKE 元字符；Web 组件测试覆盖错误页两处、Session 卡与概览；E2E 覆盖四处展示与搜索框按 ID 过滤。
- 文档：新增 13 章设计事实；补一条 Agent Note 记录“为什么把 id 放进查询条件而不是回填 search_text”。

## 实施步骤

1. 写失败测试：API `q=<session id>` 命中、`q=<前缀>` 命中、大小写不敏感、`%` / `_` 仍按字面量；Web 断言错误页两处与 Session 卡/概览的根会话 ID；E2E 断言卡/概览展示与搜索框按 ID 过滤。
2. 修改 `SessionRepository.list_sessions` 的 `q` 条件并跑聚焦 API 测试。
3. 修改错误页左栏、右栏、Session 卡、Session 概览与搜索框文案，跑 Web 组件测试。
4. 更新 13 章、Agent Note 与原型页面，跑文档与流程门禁。
5. 全量相关门禁与 E2E，确认无回归。

## 依赖与交付边界

- 依赖：m3-01（Session 浏览器搜索与列表）、m4-04（错误详情页）。
- 交付边界：只扩展搜索匹配与展示；不改 `SessionListItem` 契约、不改 `search_text` 写入与回填、不改错误页与 Session 浏览器数据流、不新增复制按钮或接口。
- 非目标见文末。

## 独立验证

```sh
pnpm test:api -- tests/m2-06-session-query-api
pnpm test:web -- src/pages/errors/Index.test.ts src/pages/sessions/Index.test.ts
pnpm test:e2e --pattern "m3 session browser|m4 error detail"
pnpm typecheck:api
pnpm lint:api
pnpm typecheck:web
pnpm lint:web
pnpm verify:flow
pnpm lint:docs
```

- `q` 传完整根会话 ID 时只返回该会话；传 ID 前缀或中间子串时返回匹配会话。
- `q` 与标题命中同时存在时按稳定排序合并结果，不出现重复卡片。
- 错误页左栏和右栏都渲染同一个根会话 ID，文本完整且带标签。
- Session 每张卡与右栏概览都渲染对应会话的完整根会话 ID。
- 搜索框输入根会话 ID 后列表只剩对应会话，placeholder 与 `aria-label` 提示支持 ID。

## 验收标准

- 错误详情页左栏会话信息框、右栏顶部元信息都显示“根会话 ID”和完整值。
- Session 浏览器左栏每张卡、右栏概览顶部都显示“根会话 ID”和完整值。
- Session 浏览器搜索框可按根会话 ID 的完整值、前缀、子串与任意大小写过滤。
- 标题与仓库搜索行为不变；`%`、`_` 仍需按字面量处理。
- 相关单测、E2E、类型检查与 lint 全绿。

## 门禁与 CI

- `pnpm test:api`、`pnpm test:web`、`pnpm test:e2e`
- `pnpm typecheck:api`、`pnpm lint:api`、`pnpm typecheck:web`、`pnpm lint:web`
- `pnpm verify:flow`、`pnpm lint:docs`、`pnpm verify:docs`
- `pnpm contract:check`（响应契约不变，预期无变化）

## 非目标

- 不新增“按根会话 ID 精确查询”的独立参数或接口。
- 不把根会话 ID 写进 `search_text`，也不回填存量行。
- 不改错误页的路由、数据加载、问题归属校验与深链格式。
- 不增加复制按钮、ID 高亮或跨页 ID 跳转。
- 不改 Session 卡片的统计条、密度条、排序与分页；仅在卡片内增加根会话 ID 行。
