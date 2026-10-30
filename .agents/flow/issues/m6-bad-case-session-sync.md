# bad_cases 根会话轨迹定时同步

[English](m6-bad-case-session-sync.en.md) | 中文

```yaml flow
kind: issue
id: m6-15
milestone: m6
depends:
  - m2-07
  - m4-01
priority: P1
status: backlog
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
  number: 173
  url: https://github.com/Shadow-Azure/harness-evolution/issues/173
```

## 背景

`bad_cases.bad_case_session_id` 已经指向问题所属的根会话，但本服务没有保证这些根会话的原始轨迹进入 `trajectory_payloads`。当前轨迹入库只有本地目录导入（开发用）与管理员手动 `POST /api/acquisition/pull` 两条路径；两者都依赖操作者知道 session id 或时间窗。bad_cases 持续增长时，问题详情、执行流图和自进化启动都可能因为缺少对应 payload 而看不到会话。

现有上游轨迹契约（`third_party_api/trajectory`）一次返回整棵 root package；本次对接的查询服务不同：接口 1 只返回某个 session（主 agent 或 subagent）直接触发的子 sessionId，必须逐层展开；接口 2 返回单个 agent 的轨迹，且禁止并发调用。因此不能直接复用现有 pull 的“一次拿整包”模型，需要新的客户端与调度路径。

## 目标

- 新增定时任务：从 `bad_cases` 取 distinct 根会话 sessionId，筛出未同步的根会话，逐个补齐主 agent 与全部 subagent 的原始轨迹到 `trajectory_payloads`。
- 轨迹补齐后复用现有归一化/重放管线，使会话、Agent 树与问题读模型立即可查。
- 新增根会话同步状态表，记录每个 root 的状态、尝试次数、最后错误、Agent 数与完成时间，支持幂等重跑与失败重试。
- 新增只读统计接口与共享契约：bad_cases 涉及根会话总数、已同步数、未同步数。
- 前端展示上述统计，并能区分未同步、同步中与失败。
- 定时任务单飞；上一次未结束时不得重复处理同一批根会话，具体跳过、排队或合并策略在设计文档确认。

## 设计依据

- [04 §5 数据接缝](../../../plans/fullstack-design/04-backend-architecture.md#L204-L214)：原始轨迹、外部表与 fixtures 的边界。
- [05 §4.8 原始轨迹接入](../../../plans/fullstack-design/05-api-design.md#L688-L708)：acquisition 现有接口与 job 语义。
- [06 §3.0 trajectory_payloads](../../../plans/fullstack-design/06-database-design.md#L105-L145)：原始 payload 的唯一存储与待处理判定。
- [02 F9 轨迹接入与归一化](../../../plans/fullstack-design/02-features.md)：能力边界与演示数据规则。
- 本 issue 的实现细节（状态表结构、查询服务适配、遍历与并发策略、前端位置）以开发前产出的 `plans/fullstack-design` 新章节为准；实现冲突时以该章节为准。

## 实现内容

- 新增查询服务客户端：接口 1（直接子 sessionId）与接口 2（单 agent 轨迹），严格响应模型、超时、重试与错误映射；接口 2 在同一进程内串行调用。
- 新增根会话补齐服务：按 `bad_cases` 根会话递归展开（主 agent → 直接子 → 孙），去重并防环；每个 agent 取轨迹后写入 `trajectory_payloads`，沿用 `(root_session_id, agent_id)` 一行一个 agent。
- 新增定时调度与 job kind：复用现有 scheduler 与 `JobRunner` 模式，实现单飞与重叠处理；批次大小、重试阶梯与状态流转在设计文档定稿。
- 新增状态表与 alembic 迁移：至少包含 root_session_id、状态、尝试次数、最后错误、agent 数、同步时间与更新时间，root_session_id 唯一。
- 新增统计 API 与共享契约：总数、已同步、未同步；前端展示加载、空态与失败态。
- 补充测试：多层遍历、重复与环、接口 2 串行约束、单飞与重叠、失败隔离、状态幂等、统计 API 与前端展示。

## 实施步骤

1. 产出设计文档与原型修改点，确认状态表、API 契约、重叠策略与前端位置，并提交截图确认。
2. 契约与模型：查询服务响应模型、统计 DTO、OpenAPI 与生成类型。
3. 数据库：状态表模型与 alembic 迁移，SQLite/MySQL 双库验证。
4. 客户端与遍历：接口 1 递归展开、接口 2 串行拉取、payload 写入与共享重放。
5. 调度与单飞：job kind、定时触发、重叠处理、失败重试与状态更新。
6. API 与前端：统计接口、页面展示、加载/空/失败态与刷新。
7. 测试与门禁；用 mock 查询服务完成本地冒烟。

## 依赖与交付边界

- 依赖：m2-07（调度与 job 基础设施）、m4-01（外部问题读模型）。
- 交付边界：只补齐 bad_cases 根会话的轨迹与状态/统计；bad_cases 继续按“外部写同库、本服务只读”处理；不改现有手动 pull 的契约与语义；CI 不调用真实查询服务。

## 独立验证

```sh
pnpm test:api -- tests/m6-15-bad-case-session-sync
pnpm test:db
pnpm test:web
pnpm test:e2e -- "m6 bad case sync"
pnpm verify:flow
pnpm lint:docs
```

- mock 查询服务下，给定 N 个根会话可补齐主/子 agent payload，状态计数正确。
- 上一次任务未结束时再次触发不会产生并发批次。
- 接口 2 的调用序列没有重叠。
- 前端统计与后端一致。

## 验收标准

- bad_cases 中每个未同步根会话最终都有完整 main + subagent payload，并能归一化为可见 Session/Agent 树。
- 状态表对同一根会话幂等；失败可重试且错误可见。
- 定时任务单飞，重叠时不重复拉取同一批数据。
- 接口 2 严格串行。
- 前端展示总数、已同步、未同步，刷新后与后端一致。
- 相关门禁全绿。

## 门禁与 CI

- `pnpm test:api` / `pnpm test:db[:mysql]` / `pnpm test` / `pnpm typecheck:api`
- `pnpm test:web` / `pnpm typecheck:web` / `pnpm lint:web`
- `pnpm test:e2e`
- `pnpm contract:check` / `pnpm verify:flow` / `pnpm lint:docs` / `pnpm verify:docs`

## 非目标

- 不改 bad_cases 的直接读库边界与外部写入方。
- 不替换或删除现有管理员手动 pull；本 issue 只新增自动补齐路径。
- 不在 CI 访问真实查询服务；真实联调走本地 mock 与冒烟。
- 不做轨迹内容变更检测与全量重拉；是否纳入增量重拉由设计文档明确。
