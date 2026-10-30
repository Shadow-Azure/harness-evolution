# 13 · 根会话 ID 的展示与检索

> 本文回答：根会话 ID 在数据模型里指什么、错误详情页的哪两个位置必须展示、Session 浏览器的搜索如何匹配它，以及为什么不动契约、不写 `search_text`、不加新接口。
> 前置：[05 接口设计](05-api-design.md) · [06 数据库设计](06-database-design.md) · [07 后端实现](07-backend-implementation.md) · [08 前端实现](08-frontend-implementation.md)。

## 1. 背景

根会话 ID 是问题上报、轨迹同步、深链、日志和工单共同使用的稳定键。`bad_cases.bad_case_session_id`、`probe_reports.session_id`、`GET /api/sessions/{sid}` 的 `sid` 以及 Session 卡片的 `id` 都指向同一个值。运维或开发拿到一个 ID 后，最常见的两个动作是“打开这个会话的错误页”和“在会话列表里找到它”。

当前页面对这两个动作都不友好：

- 错误详情页左栏只有一行没有标签的 `session · <id>`，右栏顶部 meta 只有开始时间、repo、错误数与已分析数。用户在两个面板之间对照时，无法确认这串 ID 是根会话 ID 还是某个 agent 的 ID，也无法直接在右栏读到它。
- Session 浏览器的左栏会话卡与右栏会话概览都没有根会话 ID；卡片的 `data-session-id` 只存在于 DOM 属性里，用户看不到。
- Session 浏览器的搜索只匹配 `session_families.search_text`，而该列由 `lower(title + repo)` 组成，不含 `id`。粘贴完整根会话 ID 搜索时结果为空，只能手工滚动列表。

本特性把根会话 ID 提升为一等信息：在错误详情页两处、Session 浏览器的卡片与概览各一处明确展示，并让会话搜索把 `id` 纳入匹配范围。

## 2. 术语与数据来源

| 名称 | 指什么 | 来源 |
|---|---|---|
| 根会话 ID | 一次根会话的稳定 UUID；主 agent 的 `agentId` 与它相同 | `session_families.id` |
| 子 agent ID | 某个子 agent 的真实 `agentId`，与根会话 ID 不同 | `agents.id`（`kind=subagent/workflow`） |
| 错误页 `sessionId` | 路由 `/sessions/:sessionId/errors` 解析出的根会话 ID | `parseSessionDeepLink` → 路由参数 |
| 问题所属根会话 | 一条 bad_case 上报到哪个根会话 | `bad_cases.bad_case_session_id` |
| 搜索文本 | 会话列表的标题与仓库检索列 | `session_families.search_text` = `lower(title + repo)` |

结论：错误详情页与会话概览都已经持有根会话 ID，不需要新增请求或响应字段；需要改的只是“怎么显示”和“搜索时匹配哪一列”。

边界：`agentId` 不是根会话 ID。主 agent 的 `agentId` 恰好等于根会话 ID，但子 agent 的 `agentId` 是另一套值；页面文案必须写“根会话 ID”，不能简写成“会话 ID”或“Agent ID”。

## 3. 页面展示

### 3.1 左栏会话信息框

左栏头部当前结构是“错误标题 + 数量 → 会话标题 → 无标签 ID → 返回入口”。改为：

```text
┌─ 错误                                  3 个 ─┐
│ AI agent + 视频播放结合的开源产品调研          │
│ 根会话 ID · cb819c5b-286f-4eab-a681-4ba5414b844d │
│ ← 返回 Session                                 │
└────────────────────────────────────────────────┘
```

规则：

- 保持一行紧凑布局，文案为“根会话 ID · ” + 完整 ID；标签使用 `--text-faint`，值使用 `--mono`、`--text-dim`。不新增第二行，也不把 ID 放进下方错误列表的卡片框。
- 值必须是完整 ID，不使用 `short` 截短；标准 UUID 在 340px 栏内可完整显示，超长 ID 允许 `overflow-wrap: anywhere` 换行，`title` 仍写完整 ID。
- 标签文案固定为“根会话 ID”，不使用“Session ID”，与失败态、空态文案保持一致。
- 返回链接、会话标题、错误数量与列表结构不变。

### 3.2 右栏顶部 meta

右栏 `header.error-head` 的 `error-meta` 是紧贴标题下方的一行身份信息（开始时间、repo、错误数、已分析数）。根会话 ID 放进这一行，紧跟开始时间，与时间同列；**不放进下方执行流面板的框内，也不新增独立信息卡**：

```text
错误详情                                      返回 Session
2026-08-30 08:00 开始  根会话 ID · cb819c5b-286f-4eab-a681-4ba5414b844d  harness-evolution  3 个错误  2 个已分析
```

规则：

- 根会话 ID 与开始时间同属身份信息，排在 `time` 之后、repo chip 之前；不改变现有那一行的高度与换行规则。
- 根会话 ID 作为一个完整的 meta 片段渲染，前缀文案“根会话 ID”，值等宽；不使用 repo chip 的样式，避免与仓库混淆。
- 值完整展示；meta 允许换行，ID 片段使用 `overflow-wrap: anywhere`，窄屏不横向溢出。
- 不增加复制按钮、悬浮卡片或跳转；用户可以直接选中文本复制。
- 若后续在错误页 meta 增加模型字段，根会话 ID 仍保持在时间之后、模型/仓库之前，不挪到下方框内。

### 3.3 Session 浏览器左栏会话卡

左栏每张 Session 卡在“repo / 时长 / 工具 / 子 agent”这一行下方、统计条之前增加一行根会话 ID：

```text
┌ AI agent + 视频播放结合的开源产品      09-05 17:17 ┐
│ llm-wiki  ⏱ 17h37m  工具 197  ⇢ 子 agent 57        │
│ 根会话 ID · cb819c5b-286f-4eab-a681-4ba5414b844d    │
│ 12 轮次   375 步骤   197 工具失败   1 Skill   3 问题 │
└────────────────────────────────────────────────────┘
```

规则：

- **每张卡都显示**，不只当前选中的卡；这样在列表里对照 bad_cases、日志或工单时不需要先点选。
- 文案为“根会话 ID · ” + 完整 ID；标签使用 `--text-faint`，值使用 `--mono`，字号 10px。标准 UUID 在 336px 卡片内可完整显示。
- 单行布局；超长 ID 用 `title` 保留完整值，视觉上按卡片宽度省略，不把卡片撑破。列表滚动与卡片高度变化是预期行为。
- 新行不改变卡片的点击、选中、键盘 Enter/Space 与 `role=option` 语义；不新增复制按钮。
- `data-testid="session-card-root-session-id"` 挂在 ID 行上，E2E 用卡片的 `data-session-id` 与 ID 行交叉校验。

### 3.4 Session 概览右栏顶部 meta

右栏 `SessionOverview` 的 `overview-head` 当前是“开始时间 → repo → 时长 → 模型 → 状态”。根会话 ID 插在开始时间之后、repo 之前，仍在标题下方同一行：

```text
AI agent + 视频播放结合的开源产品调研   [有失败]
09-05 17:17 开始  根会话 ID · cb819c5b-286f-4eab-a681-4ba5414b844d  llm-wiki  ⏱ 17h37m  模型 glm-5.3
```

规则：

- 与错误页右栏一致：ID 紧跟开始时间，不放到统计条、执行流面板或问题列表的框里。
- 值完整展示，meta 允许换行；ID 片段使用 `overflow-wrap: anywhere`，窄屏不横向溢出。
- 不新增复制按钮或跳转；用户直接选中文本复制。
- `data-testid="session-overview-root-session-id"` 挂在 ID 片段上；ID 必须等于 `SessionListItem.id`。

### 3.5 状态与可访问性

- 四处都使用真实文本，不做纯图标或 `title` 独占信息；屏幕阅读器能读到“根会话 ID + UUID”。
- 标签是文本节点，不依赖颜色；meta 项与现有 meta 同级，不放进 `aria-hidden` 容器。
- E2E 使用稳定钩子：错误页左栏 `data-testid="error-root-session-id"`、错误页右栏 `data-testid="error-meta-root-session-id"`、Session 卡 `data-testid="session-card-root-session-id"`、Session 概览 `data-testid="session-overview-root-session-id"`；四处文本都等于对应会话的根会话 ID。

## 4. Session 搜索

### 4.1 匹配语义

`GET /api/sessions?q=` 的 `q` 从“只匹配标题与仓库”扩展为“匹配标题、仓库或根会话 ID”：

- `q` 先去首尾空白；空字符串不产生条件。
- 匹配统一转小写；根会话 ID 按小写 UUID 处理。
- 同时匹配两个来源：`session_families.search_text` 与 `session_families.id`；任一命中即返回。
- 子串匹配：完整 ID、前缀、ID 中间片段都能命中；不要求用户从第一个字符开始输入。
- 大小写不敏感：用户粘贴大写 UUID 也能命中。
- `%`、`_`、`\` 按字面量处理，复用 `_escape_like`，与现有标题搜索一致。
- 与 `status`、`sort`、`limit` 组合时保持现有语义；排序仍由 `sort` 决定，命中 ID 不改变排序。
- 结果按 `session_families` 一行一会话，不存在重复卡片。

示例（假设 `SESSION_1 = 10000000-0000-4000-8000-000000000001`）：

| `q` | 结果 |
|---|---|
| `10000000-0000-4000-8000-000000000001` | 只返回 SESSION_1 |
| `10000000` | 返回所有 ID 以 `10000000` 开头的会话 |
| `4000-8000` | 返回 ID 含该片段的会话 |
| `10000000-0000-4000-8000-000000000001` 的大写形式 | 同上，大小写不敏感 |
| `100%` | 按字面量匹配，不把 `%` 当通配符 |
| `workflow` | 仍按标题/仓库命中，行为不变 |

### 4.2 SQL 条件

```python
query_text = _escape_like(query.lower())
pattern = f"%{query_text}%"
conditions.append(
    or_(
        session_families.c.search_text.like(pattern, escape="\\"),
        func.lower(session_families.c.id).like(pattern, escape="\\"),
    ),
)
```

- 使用 `func.lower(id)` 而不是直接 `id LIKE`：SQLite 的 `LIKE` 对 ASCII 大小写不敏感，MySQL 的行为取决于 collation；显式转小写让两个适配器结果一致。
- 不在 `id` 上新增索引：`%...%` 无法利用 B-Tree；当前 `search_text` 已经是同样的全表 `LIKE`，本特性不引入新的扫描复杂度。`session_families` 是根会话粒度，行数远小于 agent/event 表，按现有 `limit`（默认 100、上限 500）分页。
- 不引入 `q` 的最短长度限制：现有标题搜索也没有；若未来 ID 前缀过短导致结果过多，属于搜索体验问题，另立需求。

### 4.3 为什么把 `id` 放进查询条件，而不是写进 `search_text`

| 方案 | 代价 | 结论 |
|---|---|---|
| `search_text` 追加 id | 归一化写入路径要改；存量行要回填；fixtures 与迁移都要同步；id 不可变，重复存储没有收益 | 不采用 |
| 查询时 `OR lower(id) LIKE` | 只改一处读路径；无 schema/契约/回填；与标题搜索同一转义规则 | 采用 |
| 新增 `rootSessionId` 查询参数 | 前端要区分“ID 查询”和“标题查询”，还要定义互斥/组合语义；用户只有一个搜索框 | 不采用 |
| 只允许精确 ID | 无法前缀/片段搜索；与标题/仓库的模糊搜索不一致 | 不采用 |

`search_text` 的职责仍是“标题 + 仓库”的低成本模糊检索；根会话 ID 是主键列，查询时直接匹配，两者不混在同一列。

### 4.4 搜索框文案

- placeholder：`搜索标题、仓库或根会话 ID`
- `aria-label`：`搜索 Session（标题、仓库或根会话 ID）`
- 输入、300ms 防抖、URL `q` 同步、清空后的空态都与现状一致；不新增下拉建议或高亮。

## 5. 契约与边界

- **API 契约不变**：`SessionListItem.id` 已经是根会话 ID；不新增 `rootSessionId` 字段，不改 `GET /api/sessions` 的请求/响应模型，`packages/contracts` 无 diff。
- **数据库不变**：不改 `session_families` 表结构、索引与 `search_text` 写入逻辑；不回填存量行。
- **错误页数据流不变**：继续使用 `useSessionSummary` / `useSessionBadCases` / `useSessionTree`；根会话 ID 来自路由解析后的 `sessionId`，不额外请求。
- **Session 浏览器数据流不变**：卡片与概览继续使用 `SessionListItem`；根会话 ID 直接取 `item.id`，不新增请求或响应字段。
- **深链不变**：`/sessions/:sessionId/errors` 与 `/sessions/:sessionId` 的解析、规范化与归属校验保持原样。
- **不做 ID 专用搜索页、复制按钮、ID 高亮、跨页跳转**。

## 6. 文件改动

| 文件 | 改动 |
|---|---|
| `apps/api/app/db/crud/sessions.py` | `q` 条件增加 `lower(id) LIKE`，复用 `_escape_like` |
| `apps/api/tests/m2-06-session-query-api/test_sessions_api.py` | 完整 ID、前缀、片段、大小写、LIKE 元字符 |
| `apps/web/src/pages/errors/components/ErrorSidebar.vue` | 左栏“根会话 ID”标签 + 完整值 |
| `apps/web/src/pages/errors/Index.vue` | 右栏 meta 增加根会话 ID 项 |
| `apps/web/src/pages/errors/Index.test.ts` | 两处根会话 ID 渲染与 `data-testid` |
| `apps/web/src/pages/sessions/components/SessionCard.vue` | 每张卡增加根会话 ID 行 |
| `apps/web/src/pages/sessions/components/SessionOverview.vue` | 概览 meta 增加根会话 ID 项 |
| `apps/web/src/pages/sessions/Index.test.ts` | 卡片/概览根会话 ID、搜索框文案与按 ID 过滤的请求参数 |
| `apps/web/src/pages/sessions/components/SearchBox.vue` | placeholder 与 `aria-label` |
| `tests/e2e/m3-session-browser.test.mjs` | 卡片与概览根会话 ID；输入根会话 ID → 列表只剩目标会话 |
| `tests/e2e/m4-error-detail.test.mjs` | 错误页两处根会话 ID 文本 |
| `plans/fullstack-design/13-root-session-id.md` | 本文 |
| `plans/fullstack-design/README.md`、05/06/07/08/09 | 指向本文的最小修订 |
| `.agents/notes/` | 记录“id 不进 search_text”的取舍 |
| `plans/14-15-ui-prototype/harness-evolution.html` | 同步原型四处展示与搜索文案 |

## 7. 验证

### 7.1 自动化

```sh
pnpm test:api -- tests/m2-06-session-query-api
pnpm test:web
pnpm test:e2e --pattern "m3 session browser|m4 error detail"
pnpm typecheck:api && pnpm lint:api
pnpm typecheck:web && pnpm lint:web
pnpm verify:flow && pnpm lint:docs && pnpm verify:docs
pnpm contract:check
```

预期：

- API：`q=<完整 ID>` 只返回目标会话；`q=<前缀>` / `q=<片段>` 返回匹配集合；大写输入结果相同；`q=%`、`q=_` 返回空；`q=<标题>` 行为不变。
- Web：错误页左栏、右栏都渲染完整根会话 ID；Session 每张卡与概览都渲染完整根会话 ID；搜索框 placeholder 与 `aria-label` 含“根会话 ID”。
- E2E：错误页两处 ID 与路由参数一致；Session 卡与概览的 ID 与选中会话一致；在 Session 浏览器输入根会话 ID 后只保留目标卡片。
- 契约：`pnpm contract:check` 无 diff。

### 7.2 手工

1. 从 `bad_cases` 或日志取一个根会话 ID，打开 `/sessions/{id}/errors`，确认左栏与右栏显示同一完整 ID。
2. 返回 Session 浏览器，确认左栏每张卡、右栏概览顶部都显示各自/当前会话的完整 ID。
3. 把该 ID 粘贴到搜索框，确认列表只剩一条且标题正确；再输入 ID 前缀与中间片段，确认仍能命中。
4. 输入一个标题关键字，确认原有搜索不受影响；输入 `%`，确认不会匹配全部会话。
5. 在 390px 宽度下确认四处 ID 换行或省略且不横向溢出。

## 8. 原型差异

原型 [`harness-evolution.html`](../14-15-ui-prototype/harness-evolution.html) 当前：

- 错误页左栏 `.err-sid` 只显示 `session · <id>`，没有“根会话 ID”标签。
- 错误页右栏 `.err-head .meta` 只有开始时间、repo、错误数、已分析数。
- Session 浏览器的 `.scard` 没有根会话 ID；`.fam-head .meta` 只有开始时间、repo、时长、模型、状态。
- 搜索框 placeholder 为“搜索标题或仓库”。

本特性在原型中同步为：

- 错误页左栏 `.err-sid` 改成一行：“根会话 ID · <UUID>”。
- 错误页右栏 meta 在开始时间之后、repo 之前增加“根会话 ID · <UUID>”，仍在标题下方那一行，不进入下方的执行流框。
- Session 浏览器每张 `.scard` 在 repo/时长/工具/子 agent 行下面增加“根会话 ID · <UUID>”；`.fam-head .meta` 在开始时间之后、repo 之前增加同一 ID。
- 搜索框 placeholder 改为“搜索标题、仓库或根会话 ID”，输入根会话 ID 后列表按 ID 过滤。

修改前后截图：

| 修改点 | 修改前 | 修改后 |
|---|---|---|
| 错误页对照图 | — | [compare](../14-15-ui-prototype/screenshot-root-session-id-compare-error.png) |
| Session 浏览器对照图 | — | [compare](../14-15-ui-prototype/screenshot-root-session-id-compare-browser.png) |
| 搜索对照图 | — | [compare](../14-15-ui-prototype/screenshot-root-session-id-compare-search.png) |
| 错误页整页 | [before](../14-15-ui-prototype/screenshot-root-session-id-before-errors.png) | [after](../14-15-ui-prototype/screenshot-root-session-id-after-errors.png) |
| 错误页左栏特写 | [before](../14-15-ui-prototype/screenshot-root-session-id-before-errors-sidebar.png) | [after](../14-15-ui-prototype/screenshot-root-session-id-after-errors-sidebar.png) |
| 错误页右栏特写 | [before](../14-15-ui-prototype/screenshot-root-session-id-before-errors-header.png) | [after](../14-15-ui-prototype/screenshot-root-session-id-after-errors-header.png) |
| Session 浏览器整页 | [before](../14-15-ui-prototype/screenshot-root-session-id-before-browser.png) | [after](../14-15-ui-prototype/screenshot-root-session-id-after-browser.png) |
| Session 卡片特写 | [before](../14-15-ui-prototype/screenshot-root-session-id-before-browser-card.png) | [after](../14-15-ui-prototype/screenshot-root-session-id-after-browser-card.png) |
| Session 概览特写 | [before](../14-15-ui-prototype/screenshot-root-session-id-before-browser-header.png) | [after](../14-15-ui-prototype/screenshot-root-session-id-after-browser-header.png) |
| 搜索框 placeholder | [before](../14-15-ui-prototype/screenshot-root-session-id-before-search-empty.png) | [after](../14-15-ui-prototype/screenshot-root-session-id-after-search-empty.png) |
| 搜索 ID 结果 | [before](../14-15-ui-prototype/screenshot-root-session-id-before-search.png) | [after](../14-15-ui-prototype/screenshot-root-session-id-after-search.png) |

截图使用合成的 `cb819c5b-286f-4eab-a681-4ba5414b844d` 会话，1440px 宽；特写用于核对标签、完整值与位置。

## 9. 非目标

- 不新增根会话 ID 的专用查询参数或接口。
- 不把 ID 写入 `search_text`，不回填存量行，不改归一化写入。
- 不改错误页路由、归属校验、深链格式与数据加载。
- 不做复制按钮、ID 高亮、ID 跳转、搜索建议或结果高亮。
- 不改 Session 卡片的统计条、密度条、排序与分页；仅在卡片内增加根会话 ID 行。
