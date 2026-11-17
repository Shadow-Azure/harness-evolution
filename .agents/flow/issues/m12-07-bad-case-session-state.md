# bad case 无 Session 时的状态处理：区分未同步、无轨迹与不存在

[English](m12-07-bad-case-session-state.en.md) | 中文

```yaml flow
kind: issue
id: m12-07
milestone: m12
depends: []
priority: P1
status: in-progress
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - docs/**
  - .agents/notes/**
  - .agents/flow/**
adr: []
github:
  number: 324
  url: https://github.com/Shadow-Azure/harness-evolution/issues/324
```

## 背景

生产环境上报了一条 bad case（`swe-2bb86…`，`[SWE-bench] astropy__astropy-12907 · not_scored`）：HE 的「bad case 列表」能看到它，但点击后错误详情返回 `404 BAD_CASE_NOT_FOUND`，页面显示「问题不存在或已删除」。实际上 case 没有被删除；它对应的 Session 从未落库，root-sync 因没有可用的 `sessionSource` 而回退到未配置的全局 session query，以 `SESSION_QUERY_UNAVAILABLE` 失败。

同一条 case 的四个读口径不一致：总览列表直接读 `bad_cases`，返回 200 和该行；Session 列表返回 `items: []` 且 `pendingSessions: 1`；Session 详情/问题列表返回 `SESSION_NOT_FOUND`；bad case 详情返回 `BAD_CASE_NOT_FOUND`，前端再把它翻译成「问题不存在或已删除」。

这不是单次脏数据。ai-eval-platform#266 对没有 native main trace 的用例会回退 attempt id，并**故意不带** `sessionSource`；即使 HE 配置了全局 session query，attempt id 也不是 native session id，仍然查不到。HE 目前没有表达「case 存在、但轨迹未就绪 / 无轨迹」的状态，所以只能落成 404。

### 问题影响

- 用户看到可点击的 bad case，点进去却是「不存在/已删除」，误以为数据丢失。
- 运维无法从错误页区分「同步中」「同步失败」「上游无轨迹」与「case 真不存在」。
- root-sync 对确定性失败继续按 1m/5m/15m/1h 重试，产生无意义任务和噪声日志。
- 前端死链把「上游集成缺口」伪装成「数据不存在」，掩盖真实根因。

### 根因分析

- `ProblemRepository.case_snapshot` 先读 case，再要求 `_family(session)` 存在；session 不存在直接返回 `None`，`ProblemService.get_case` 映射为 `404 BAD_CASE_NOT_FOUND`。
- 总览列表 `OverviewRepository.page_cases` 只读 `bad_cases`，不校验 session，与详情口径不一致。
- `bad_case_root_sync` 已经保存 `status / attempts / last_error / next_retry_at / source_kind`，但列表和详情都没有消费它。
- 前端 `apps/web/src/pages/errors/Index.vue` 把所有 404 统一显示为「问题不存在或已删除」。
- 平台侧 trace-less fallback 没有显式 `traceAvailable / noTrace` 信号；HE 只能从「无 session + 无 session_source」推断，而当前推断结果被折叠成 404。

## 目标

- 列表和详情都能表达 bad case 的轨迹状态：同步中、同步失败、无可用轨迹、未同步、已就绪。
- case 存在但 session 未就绪时，详情返回可区分的稳定错误码与结构化状态，不再返回 `BAD_CASE_NOT_FOUND`。
- 前端把「同步中 / 同步失败 / 无可用轨迹」显示成可操作的状态说明（含 `lastError`、下次重试或上游状态入口），不再显示「问题不存在或已删除」。
- 真正的 case 不存在仍返回 404 `BAD_CASE_NOT_FOUND`，语义保持不变。
- 对确定性不可同步的 root 暴露 `retryable=false`，避免用户误以为「等一会就会好」；是否停止重试由实现阶段按状态机决定。
- 契约、单测、跨栈 E2E 与文档同步更新。

## 设计依据

- [05 §3.8 空间 bad case 上报](../../../plans/fullstack-design/05-api-design.md#38-bad-case-上报)：上报字段与 `sessionSource` 契约。
- [05 §10.5 上报绑定的会话信息 envelope](../../../plans/fullstack-design/05-api-design.md#105-上报绑定的会话信息-envelopem9-07)：envelope 与错误码。
- [11 §3.4 上报绑定的 envelope](../../../plans/fullstack-design/11-bad-case-session-sync.md#34-上报绑定的-envelopem9-07)：来源选择、首次 claim 固定与重试语义。
- [06 数据库设计](../../../plans/fullstack-design/06-database-design.md)：`bad_cases` 与 `bad_case_root_sync` 字段。
- [docs/architecture.md](../../../docs/architecture.md)：鉴权、错误边界与问题/归因读路径。
- [per-report session source Note](../../notes/implemented/architecture/2026-11-16-per-report-session-source.md)：m9-07 的来源快照与失败码。

## 实现内容

- **契约**：在 `packages/contracts` 增加轨迹状态枚举与 bad case 列表项字段（建议 `syncStatus: "pending" | "syncing" | "failed" | "unavailable" | "ready"`、`sessionReady: boolean`、`lastError: string | null`、`retryable: boolean`）；新增错误码 `BAD_CASE_SESSION_PENDING` 与 `BAD_CASE_SESSION_UNAVAILABLE`（或 `BAD_CASE_NO_TRACE`），并重新生成 OpenAPI 与 TS 类型。
- **仓储**：新增 `case_visibility`（只读 case，不要求 session）与 `root_sync_states`（按 root 批量读取 `bad_case_root_sync`）；总览列表按页批量 join/补齐状态，避免 N+1。
- **服务**：`ProblemService.get_case` 先判断 case 是否存在；存在但 `case_snapshot` 为空时，按 `bad_case_root_sync` 状态映射为 409（pending/syncing）或 409/503（failed/unavailable），`details` 带 `syncStatus`、`lastError`、`nextRetryAt`、`retryable`；只有 case 不存在才返回 404。
- **同步状态**：`BadCaseRootSyncService`/repository 暴露 `retryable` 与稳定 `lastError`；对「无 `session_source` 且 global 未配置」这类确定性失败标记 `retryable=false`，并保留后续配置变化后的重新触发入口。
- **前端**：总览列表行显示状态 chip；`sessionReady=false` 时点击进入状态说明而不是错误详情，或进入错误详情但展示状态面板而不是 404 文案；`errors/Index.vue` 增加 409/503 分支，展示「轨迹同步中 / 同步失败 / 无可用轨迹」与 `lastError`，并提供 `/api/acquisition/status` 或重试入口。
- **兼容**：旧的 404 `BAD_CASE_NOT_FOUND` 保留给真正不存在的 case；无 session 的既有数据在下一次读取时自动获得状态，不需要数据回填。
- **测试**：API 覆盖 pending / syncing / failed / no-trace / missing 五种输入；前端覆盖状态 chip 与文案；E2E 覆盖「ingest → 列表 → 点击 → 状态页」；契约快照与类型检查。
- **文档**：更新 API 错误矩阵、架构错误边界与部署 runbook，明确「无轨迹」不是 404。

## 原型修改

原型文件：`plans/ui-prototype-v2/harness-evolution.html`。本次只改原型，不进入生产代码；实现阶段按同一信息架构落到 `apps/web`。

- 总览 bad case 列表新增「轨迹」列：`就绪` / `同步中` / `同步失败` / `无可用轨迹`；未就绪时 ID 不再作为错误详情深链，改为「查看」进入状态面板。
- 错误详情新增无轨迹状态面板：明确「问题已上报、没有被删除」，展示 `lastError`、`retryable`、上次尝试、同步状态入口，以及返回总览 / 复制 ID。
- 无轨迹 case 不再生成归因占位（原型中 `attributionsFor` 返回空），避免「0 个已归因」与侧栏归因条目矛盾。
- 进入状态面板的深链仍使用 `page=session&view=errors&ws=…&sid=…&case=…&dtab=desc`，生产实现可复用。

**修改前 / 修改后**

**总览列表（左：修改前，右：修改后）**

![总览列表修改前/后](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-07-prototype-evidence/composite-overview.png)

**错误详情（左：修改前，右：修改后）**

![错误详情修改前/后](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-07-prototype-evidence/composite-detail.png)

说明：before 截图用同一份合成数据（`BC-HC-026`，`not_scored`，`SESSION_QUERY_UNAVAILABLE`）在原原型上注入；after 截图是修改后的原型。两轮截图使用同一 1440×913 视口、浅色主题和同一滚动位置。

## 实施步骤

1. 在 contracts 中定义状态枚举、列表字段与两个错误码，重新生成 OpenAPI/TS。
2. 增加 case-only 可见性查询与 root-sync 批量状态查询，补仓储层测试。
3. 实现 `ProblemService.get_case` 的状态映射与 `details`，保留 404 仅给缺失 case。
4. 前端列表状态 chip、详情状态面板与 409/503 文案，补组件测试。
5. 增加 fixture：case 有/无 session、pending、failed、no-trace、missing；补 API 与 E2E。
6. 更新 API/架构/runbook 文档，跑门禁并补 Agent Note。

## 依赖与交付边界

- 依赖：无；本 issue 只改 HE 的读模型与前端，不依赖 ai-eval-platform 的改动，也不依赖 #242 的全局上游配置。
- 与平台的分工：平台侧的 `traceAvailable / noTrace` 显式信号是后续跨仓契约，本 issue 先用现有字段（`session_source` 是否存在、`bad_case_root_sync` 状态）把 HE 侧状态做诚实。
- 数据：优先从 `bad_cases`、`sessions`、`bad_case_root_sync` 派生，不新增迁移；若实现阶段决定持久化 `blocked` 状态，再单独补迁移。
- 非目标：不改 happy-path 的同步、归因、probe 与问题列表；不修 #242 的全局 session query 配置；不重做错误页视觉。

## 独立验证

```sh
pnpm test:api -- tests/m12-07-bad-case-session-state
pnpm test:web
pnpm test:e2e -- --pattern m12-07
pnpm contract:check
pnpm typecheck
pnpm verify:flow
```

- `test:api`：五种状态各自的 HTTP 状态、错误码与 `details` 断言通过；缺失 case 仍 404。
- `test:web`：列表 chip、详情状态面板、404 与 409/503 文案分支通过。
- `test:e2e`：总览列表点击无 session 的 case 不再出现「问题不存在或已删除」。
- `contract:check`：OpenAPI 与生成的 TS 类型无漂移。

## 验收标准

- 总览列表对无 session 的 case 显示明确状态；点击后看到「同步中 / 同步失败 / 无可用轨迹」之一，而不是 404。
- API 对存在但无 session 的 case 返回 409（或 503）并带 `syncStatus/lastError/retryable`；只有真正不存在的 case 返回 404 `BAD_CASE_NOT_FOUND`。
- 前端不再把 404 文案用于「未同步 / 无轨迹」场景；状态页提供 `lastError` 与下一步入口。
- 确定性失败在状态中标记 `retryable=false`，不误导用户等待。
- 新增测试与文档在 CI 通过；既有 happy-path 行为不回归。

## 门禁与 CI

- `pnpm test:api`、`pnpm test:web`、`pnpm test:e2e`、`pnpm contract:check`、`pnpm typecheck`、`pnpm lint:docs`、`pnpm verify:flow`。
- CI 的静态 lane、单测覆盖率 ≥80% 与文档门禁保持全绿；如新增 e2e，纳入 `test:e2e` 串行套件。

## 非目标

- 不在本 issue 修改 ai-eval-platform 的上报 payload 或 trace 生成；跨仓 `traceAvailable/noTrace` 由后续 issue 承接。
- 不负责配置 #242 的 `HE_SESSION_QUERY_*` 或补历史 Session。
- 不改变 bad case 的归因、probe、目标匹配与问题列表排序。
- 不重做总览或错误详情的整体信息架构，只在现有页面上增加状态与分支。
