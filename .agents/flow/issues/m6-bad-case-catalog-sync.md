# bad_cases 目录数据定时同步

[English](m6-bad-case-catalog-sync.en.md) | 中文

```yaml flow
kind: issue
id: m6-16
milestone: m6
depends:
  - m2-07
  - m4-01
  - m6-15
priority: P1
status: done
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - fixtures/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
  - reports/**
  - docs/**
adr: []
github:
  number: 176
  url: https://github.com/Shadow-Azure/harness-evolution/issues/176
```

## 背景

当前 `bad_cases` 被当作"数据库里已经存在"的既有数据：本服务只读，写入方在外部；开发期靠 fixtures 灌演示数据，生产上依赖上游系统直写同库。问题列表、错误详情和根会话轨迹同步都建立在"bad_cases 已经在我们表里"这个前提上，一旦上游改为独立查询接口、不再直写本库，整条链路就没有数据来源。m6-15 只补齐 bad_cases 根会话的原始轨迹，不负责 bad_cases 本身入库。

上游服务提供一个分页查询接口：`bad_case_id` 必填，只返回 id 大于该值的记录，按 id 升序；`offset` 默认 0；`limit` 默认 20、范围 1–200。响应包含 `total`（受 bad_case_id 影响、不受 offset/limit 影响）、回显的 offset/limit 和 `items`。items 的字段与 `bad_cases` 表列一一对应，唯一差异是标题：接口里叫 `bad_case_title`，库里叫 `title`。上游坏例 id 单调递增，因此可以用"已同步最大 id"作为游标做增量拉取。

## 目标

- 新增上游坏例分页查询客户端：严格校验响应，具备超时、重试与错误映射，且同一进程内串行调用。
- 新增同步状态表（单行游标）：记录已同步最大 `bad_case_id`、已同步数量、上游未同步数量、状态、尝试次数、最后错误与时间戳。
- 新增定时任务（job kind `bad_case_catalog_sync`）：单飞、串行；启动时若上一次任务已经结束则按配置开始执行；按游标调用接口，逐页写入 `bad_cases`，每页成功后推进游标与计数。
- `bad_cases` 写入按 `bad_case_id` 幂等 upsert：不存在则插入；已存在则更新全部上游字段（含 `title` ↔ `bad_case_title` 映射），不产生重复行，也不影响本服务已有的关联数据（如 `bad_case_analysis`）。
- 冷启动游标策略：状态表无记录时游标从 0 开始，首轮全量重拉并 upsert 更新存量（设计文档 §4.2 已确认）。
- 扩展 `GET /api/acquisition/status` 与共享契约：新增 bad_cases 目录同步统计块（已同步、未同步、游标、状态、最后时间、最后错误）。
- 前端"数据同步"浮层固定四段顺序：**问题数量 → 问题轨迹 → 会话归一化 → 归因分析**；问题数量展示 bad_cases 目录同步的总量/已同步/未同步与状态，不新增页面。
- 归因分析段只读 `bad_case_analysis` 展示整体进度（已分析、待分析、问题、非问题），不在本特性实现归因逻辑或改变归因状态机。
- 定时任务串行且不并发；上一次未结束时下一次跳过或复用，具体策略在设计文档确认。

## 设计依据

- [04 §5 数据接缝](../../../plans/fullstack-design/04-backend-architecture.md)：外部表、原始数据与 fixtures 的写读边界。
- [05 §4.8 原始轨迹接入](../../../plans/fullstack-design/05-api-design.md)：acquisition 现有接口、status 响应与 job 语义。
- [06 §4.1 bad_cases](../../../plans/fullstack-design/06-database-design.md)：`bad_cases` 列定义、主键与外部写入约定。
- [02 F9 轨迹接入与归一化](../../../plans/fullstack-design/02-features.md)：能力边界与演示数据规则。
- [11 bad_cases 根会话轨迹定时同步](../../../plans/fullstack-design/11-bad-case-session-sync.md)：单飞调度、状态表与顶栏浮层的既有范式。
- [12 bad_cases 目录数据定时同步](../../../plans/fullstack-design/12-bad-case-catalog-sync.md)：本 issue 实施前先产出的设计文档，定义游标、分页、upsert、统计口径与浮层文案。
- [原型 harness-evolution.html](../../../plans/14-15-ui-prototype/harness-evolution.html)：顶栏"数据同步"浮层是前端展示基准。
- 实现冲突时以第 12 章和确认后的原型为准。

## 实现内容

- 配置：新增坏例查询 base URL/token、超时、重试、目录同步间隔、页大小（1–200）、单次时间预算等环境变量；未配置时状态为 `unavailable`，定时任务不触发。
- 客户端：`apps/api/app/third_party_api/bad_case_query/` 适配分页查询接口；严格解析 `total/offset/limit/items`，逐条校验字段并完成 `bad_case_title` → `title` 映射；4xx 不重试，401/403 映射鉴权错误，429/5xx/超时有限重试；调用串行。
- 数据库：新增 `bad_case_catalog_sync` 单行表（固定主键）与 alembic 迁移，SQLite/MySQL 双库验证；`bad_cases` 新增按主键 upsert 的仓储方法（按方言使用 `ON CONFLICT DO UPDATE` / `ON DUPLICATE KEY UPDATE`）。
- 服务：读取游标 → 拉取一页 → 单事务内 upsert 该页全部 items → 更新游标、计数与时间 → 继续下一页，直到没有更多数据或达到单次预算；页内失败整页回滚、游标不前进，记录错误与下次重试时间。
- 调度：复用 `JobRunner` 新增 job kind 与 coordinator，实现单飞、启动恢复、定时循环串行执行。
- API 与契约：`AcquisitionStatusResponse` 增加 `badCaseCatalogSync` 与只读的 `badCaseAnalysis` 统计块，运行 `pnpm contract:generate` 再生 OpenAPI 与生成类型。
- Web：`TopNav` 数据同步浮层按"问题数量 → 问题轨迹 → 会话归一化 → 归因分析"重排；问题数量行展示目录同步统计，归因分析行展示整体进度；扩展 `syncStatus` 工具并补组件测试。
- 归因统计：按 `analysis_status` 聚合 `analyzed_issue` / `analyzed_nonissue`，以 `COUNT(bad_cases)` 为分母计算待分析数；只读查询，不写归因表。
- 测试：mock 上游分页服务，覆盖翻页、upsert 新增/更新、标题映射、空页停止、游标推进、重复触发单飞、失败回滚与重试、未配置降级、归因统计、统计接口与前端展示。

## 实施步骤

1. 产出 `plans/fullstack-design/12-bad-case-catalog-sync.md` 并确认：冷启动游标、页大小、单次预算、失败重试、未同步数量口径与浮层文案。
2. 契约与配置：状态 DTO、环境变量、OpenAPI 与生成类型。
3. 数据库：状态表与 upsert 仓储，alembic 迁移与双库测试。
4. 客户端：分页查询客户端、严格响应模型、串行约束与错误映射。
5. 服务与调度：同步服务、job kind、单飞与启动恢复。
6. Web：浮层按四段重排，新增问题数量与归因分析展示与状态，补组件测试。
7. 测试与门禁；用 mock 上游完成本地冒烟。

## 依赖与交付边界

- 依赖：m2-07（调度与 job 基础设施）、m4-01（外部问题读模型）、m6-15（浮层位置与状态表/调度复用范式）。
- 交付边界：新增 bad_cases 的自动入库路径；`bad_cases` 从"仅外部写"变为"外部写与同步写入并存、按主键幂等覆盖"；不改 m6-15 的轨迹同步语义、不改现有手动 pull、不改问题读接口的字段语义。CI 不访问真实上游。

## 独立验证

```sh
pnpm test:api -- tests/m6-16-bad-case-catalog-sync
pnpm test:db
pnpm test:web
pnpm test:e2e -- "m6-16"
pnpm contract:check
pnpm verify:flow
pnpm lint:docs
```

- mock 上游返回三页数据时，`bad_cases` 行数与内容同上游一致，状态表游标等于最大 id。
- 同一批数据重复同步不新增行；上游修改某条记录后再次同步，该行字段被更新。
- items 为空或不足一页时停止翻页；失败页不推进游标、不留下半页数据。
- 上一次任务运行中再次触发不会产生并发批次。
- 状态接口与浮层展示的已同步/未同步数量与数据库、上游 total 一致。
- 归因统计（已分析/待分析/问题/非问题）与 `bad_cases` / `bad_case_analysis` 的手工计数一致；缺分析行计入待分析。

## 验收标准

- 定时任务按配置串行运行，游标单调递增；重启后从持久化游标继续。
- `bad_cases` 主键幂等 upsert：新增插入、已存在更新，重复同步不产生重复行。
- 上游 `bad_case_title` 正确写入 `bad_cases.title`，其余字段一一对应。
- 失败可重试、错误可见，且不会把半页数据留在表里。
- `GET /api/acquisition/status` 返回目录同步统计与归因整体进度，浮层按四段顺序展示且与后端一致。
- 未配置上游时任务不启动、状态显示不可用，且不影响现有功能。
- 相关门禁全绿。

## 门禁与 CI

- `pnpm contract:generate` / `pnpm contract:check`
- `pnpm typecheck:api` / `pnpm test:api` / `pnpm test:db[:mysql]`
- `pnpm test` / `pnpm test:web` / `pnpm typecheck:web` / `pnpm lint:web`
- `pnpm test:e2e`
- `pnpm verify:flow` / `pnpm lint:docs` / `pnpm verify:docs`

## 非目标

- 不处理上游删除：本服务不做行删除或墓碑同步。
- 不替换 m6-15 的根会话轨迹同步，也不改变其状态表。
- 不在 CI 调用真实上游服务；真实联调走本地 mock 与冒烟。
- 不新增面向业务的问题写接口；同步是唯一新增写路径。
- 不实现归因分析流程，不改变 `bad_case_analysis` 状态机；只在浮层做只读汇总。
- 不做字段级差异检测或变更审计，只按主键覆盖。
