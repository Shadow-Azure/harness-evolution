# Session Family 快照与共享契约设计（#10）

状态：设计稿，待评审后进入实现计划。

## 1. 目标

为 M1 原型建立 Session Family 的共享契约与本地快照库。后续 #8（执行流程与 skill 追踪）、#9（归因解释）、#14（Session 浏览器）与 #15（时间线）共用这套契约和索引，不各自复制字段、不各自扫描原始 JSONL。

本切片只做三件事：

1. 在 `packages/contracts` 定义 Session Family 领域契约。
2. 在 `apps/web/src/prototype/snapshot` 建立可注入文件源的索引与懒加载库。
3. 提交脱敏的跨 agent 示例问题与可解析的证据锚点。

明确不做：浏览器 UI、Vite 中间件、正式 REST API、SQLite、模型分析、真实评测平台。

## 2. 数据事实与统计口径

样本为 2026-10-18 的 4 个 root rollout。统计以 `thread_spawn` 后代为家族成员，`source.subagent.other = guardian` 的 review thread 不计入：

| 家族 | root thread | agent 数 | 主段记录 | 续段记录 | 原始载荷 | 最大深度 |
|---|---|---:|---:|---:|---:|---:|
| 20:05 | `01a14ee6-d117-7c71-84a7-32b46bb3a99b` | 27 | 10,123 | 0 | 22.46 MB | 4 |
| 17:32 | `01a14e5b-5d48-7382-9fed-1d2295a163c1` | 9 | 6,437 | 0 | 28.60 MB | 1 |
| 08:46 | `01a14c79-9e02-7210-ada9-ae4ff5c6ae05` | 8 | 3,307 | 0 | 6.91 MB | 1 |
| 12:34 | `01a14d49-f4a0-7c31-ad9a-b6e3c034501a` | 20 | 5,303 | 12 | 14.27 MB | 1 |
| 合计 |  | 64 | 25,170 | 12 | 72.2 MB | 4 |

12:34 家族有 21 个文件：20 个主段加 1 个同 thread 的续段（`rollout-...-01a14d49-..._01a14e37-...jsonl`，12 条记录）。续段不能当独立 rollout，否则会变成 65 个 rollout、25,182 条记录。索引把它挂到同一 `AgentNode` 的 `segments`，`recordCount` 仍按主段统计，续段单独计入 `continuationRecordCount`。

## 3. 身份与树结构

### 3.1 三类 ID 各司其职

- `threadId`：`session_meta.payload.id`，一个逻辑 agent 的稳定主键。子 agent 即使复用父会话的 `session_id`，`threadId` 仍不同。
- `rolloutId`：相对 `~/.codex/sessions` 的文件路径，例如 `2026/10/18/rollout-....jsonl`。它是文件身份，用于区分同一 thread 的多个 segment。
- `sessionId`：`session_meta.payload.session_id`，只作展示和兼容字段，不作主键、不作覆盖键。

归因目标 ID 采用封闭格式：`agent:<threadId>`、`skill:<normalizedName>`。示例问题 ID 采用 `finding:<slug>`；证据 ID 采用 `<rolloutId>#<ordinal>`。

### 3.2 父子关系

家族父边只取 `session_meta.payload.source.subagent.thread_spawn.parent_thread_id`。`payload.parent_thread_id` 作为兼容字段保留在元数据里，用于识别 guardian 等非 `thread_spawn` 子线程；它们不进入 M1 的 Session Family。

索引从每个 root 出发，沿 `parentThreadId` 做广度优先遍历：

1. 按 `threadId` 聚合 segment，选出记录数最多、时间最早的 segment 为主段。
2. 建立 `threadId -> AgentNode`，再按父边挂 children。
3. 只保留从 root 可达的节点，防止无关线程混入。
4. 环路、缺失父节点、重复 root、无 `thread_spawn` 的孤儿节点写入 `diagnostics`，不阻断其余家族。

`depth` 优先取 `thread_spawn.depth`；缺失时按父链长度推导。`agentPath` 取 `thread_spawn.agent_path`，root 使用 `/`；`nickname` 取 `thread_spawn.agent_nickname`。

## 4. 契约

契约集中在 `packages/contracts/src/session-family.ts`，由 `packages/contracts/src/index.ts` 重导出。字段只描述跨端共享的稳定事实；原始 JSONL 记录仍由加载器返回，不塞进共享契约。

```ts
export interface SessionFamily {
  rootThreadId: string;
  rootSessionId: string;
  rootAgentPath: string;
  label: string | null;
  agents: AgentNode[];
  findings: Finding[];
  skills: SkillUse[];
  stats: FamilyStats;
  diagnostics: SnapshotDiagnostic[];
}

export interface AgentNode {
  threadId: string;
  sessionId: string;
  parentThreadId: string | null;
  depth: number;
  agentPath: string;
  nickname: string | null;
  role: string | null;
  kind: "root" | "subagent";
  segments: RolloutSegment[];
  children: string[];
  stats: AgentStats;
}

export interface AgentStats {
  segmentCount: number;
  recordCount: number | null;
  continuationRecordCount: number | null;
  byteCount: number;
  turnCount: number | null;
  toolCallCount: number | null;
  failureCount: number | null;
  findingCount: number;
}

export interface RolloutSegment {
  rolloutId: string;
  threadId: string;
  startedAt: string;
  byteCount: number;
  recordCount: number | null;
  primary: boolean;
}

export interface FamilyStats {
  rolloutCount: number;
  segmentCount: number;
  recordCount: number | null;
  continuationRecordCount: number | null;
  byteCount: number;
  maxDepth: number;
  agentCount: number;
  findingCount: number;
}

export interface EvidenceRef {
  id: string;
  rolloutId: string;
  agentThreadId: string;
  agentPath: string;
  ordinal: number;
  line: number;
  recordType: string;
  turnId: string | null;
  callId: string | null;
  itemId: string | null;
  excerpt: string;
}

export interface AttributionTarget {
  type: "skill" | "agent";
  id: string;
  name: string;
}

export interface Finding {
  id: string;
  familyRootThreadId: string;
  title: string;
  summary: string;
  impact: string;
  severity: "P0" | "P1" | "P2" | "P3";
  category: "agent-orchestration" | "skill-usage" | "tool-failure" | "verification-gap";
  sourceAgentThreadIds: string[];
  attribution: {
    target: AttributionTarget;
    reason: string;
    confidence: "confirmed" | "inferred" | "unknown";
    unverified: string | null;
  };
  evidence: EvidenceRef[];
  status: "example";
}

export interface SkillUse {
  id: string;
  agentThreadId: string;
  agentPath: string;
  target: AttributionTarget;
  occurrences: Array<{
    evidence: EvidenceRef;
    sourcePath: string;
  }>;
}

export interface SnapshotDiagnostic {
  code:
    | "missing-root"
    | "missing-parent"
    | "cycle"
    | "duplicate-root"
    | "invalid-meta"
    | "empty-rollout"
    | "unreadable-rollout";
  message: string;
  rolloutId: string | null;
  threadId: string | null;
}

export interface TimelineItem {
  id: string;
  agentThreadId: string;
  rolloutId: string;
  turnId: string | null;
  ordinal: number;
  timestamp: string | null;
  kind:
    | "user-message"
    | "developer-message"
    | "agent-message"
    | "reasoning"
    | "tool-call"
    | "tool-output"
    | "error"
    | "turn"
    | "token-usage"
    | "other";
  title: string;
  text: string | null;
  callId: string | null;
  status: "ok" | "error" | "unknown";
  evidence: EvidenceRef;
}
```

加载器内部还使用以下辅助类型；它们不进入跨端契约，只在 `apps/web/src/prototype/snapshot` 内导出：

```ts
export interface RolloutFileRef {
  rolloutId: string;
  byteCount: number;
  modifiedAt: string;
}

export interface RolloutSessionMeta {
  threadId: string;
  sessionId: string;
  declaredParentThreadId: string | null;
  familyParentThreadId: string | null;
  depth: number | null;
  agentPath: string | null;
  nickname: string | null;
  role: string | null;
  cwd: string | null;
  startedAt: string;
  kind: "root" | "subagent" | "review";
}

export interface RolloutRecord {
  rolloutId: string;
  line: number;
  ordinal: number;
  timestamp: string | null;
  type: string;
  payload: unknown;
}

export interface LoadedRollout {
  threadId: string;
  records: readonly RolloutRecord[];
  timeline: readonly TimelineItem[];
  status: "running" | "completed" | "failed" | "aborted" | "unknown";
  stats: AgentStats;
}

export interface FamilyIndex {
  families: readonly SessionFamily[];
  byRootThreadId: ReadonlyMap<string, SessionFamily>;
  diagnostics: readonly SnapshotDiagnostic[];
}

export interface ResolvedFinding {
  finding: Finding;
  target: AttributionTarget;
  evidence: readonly EvidenceRef[];
}
```

`TimelineItem` 在 #10 只提供稳定 envelope 与原始记录到 item 的最小映射；长文本折叠、卡片布局、虚拟滚动由 #15 实现。

## 5. 快照加载库

### 5.1 可注入文件源

```ts
export interface SnapshotSource {
  listRollouts(): Promise<readonly RolloutFileRef[]>;
  readMeta(rolloutId: string): Promise<RolloutSessionMeta>;
  readRecords(rolloutId: string): Promise<readonly RolloutRecord[]>;
}
```

- `createNodeSnapshotSource(sessionsRoot)`：Node 适配器，递归列 `*.jsonl`，`readMeta` 只读到第一行换行符为止，`readRecords` 只读指定文件。
- `createMemorySnapshotSource(files)`：测试与 fixture 适配器，记录 `readMeta` / `readRecords` 调用次数，用于证明索引阶段没有解析正文。

### 5.2 公开 API

```ts
export async function buildFamilyIndex(input: {
  roots: readonly string[];
  source: SnapshotSource;
  findings?: readonly Finding[];
}): Promise<FamilyIndex>;

export async function loadRollout(input: {
  threadId: string;
  family: SessionFamily;
  source: SnapshotSource;
  includeContinuation?: boolean;
}): Promise<LoadedRollout>;

export async function measureFamily(input: {
  family: SessionFamily;
  source: SnapshotSource;
}): Promise<SessionFamily>;

export function extractSkillUses(input: {
  agent: AgentNode;
  records: readonly RolloutRecord[];
}): SkillUse[];

export async function resolveFinding(input: {
  finding: Finding;
  family: SessionFamily;
  source: SnapshotSource;
}): Promise<ResolvedFinding>;
```

`buildFamilyIndex` 只读元数据，返回 `recordCount: null`、`continuationRecordCount: null` 的索引，并按 root 挂上传入的示例问题；`skills` 初始为空，由 `loadRollout` / `extractSkillUses` 填充。`measureFamily` 显式读取全部 segment，返回填好 `FamilyStats` 与各 `AgentStats` 的新 family；它不参与首屏索引。`loadRollout` 默认只读主段，`includeContinuation: true` 时按时间顺序追加续段。

### 5.3 性能边界

- 索引阶段每个文件只读第一条记录，读取量约为目录内全部候选 rollout 的 `session_meta`，不解析 72.2 MB 正文。
- 单个 rollout 的正文只在 `loadRollout` 或 `measureFamily` 时读取。
- 内存中只保留索引、元数据和当前 rollout；原始记录按调用返回，不由索引缓存。
- 目录不存在、文件为空、首行不是合法 JSON、缺少 `payload.id` 时跳过该文件并记录诊断，不抛出全局错误。

## 6. Skill 使用派生

M1 的 rollout 没有独立 SkillInvocation 事件。`extractSkillUses` 只承认显式的 `SKILL.md` 读取：扫描 `response_item` 中 `function_call` 与 `custom_tool_call` 的 `arguments` / `input`，提取每个 `<name>/SKILL.md` 路径。

- `skillName` 取 `SKILL.md` 前的目录名，按 basename 归一化；目标 ID 使用 `skill:<basename.toLowerCase()>`，显示名保留原始大小写。同一 skill 出现在 `.agents/skills`、`.codex/plugins/cache`、`.codex/.tmp/plugins` 时归为同一个目标。
- 一次调用读取多个 skill 时产生多条 `SkillUse` occurrence，每条都保留原命令的 `EvidenceRef`。
- 不从消息正文猜测 skill 使用，不把“提到 skill 名称”当成加载。
- 该能力只服务契约与快照索引；完整的 skill 追踪与 UI 展示归 #8。

## 7. 示例问题

示例问题存放在 `apps/web/src/prototype/snapshot/findings.fixture.ts`，全部为人工核对后的派生数据，不包含原始 JSONL。每个家族至少一条，共 4 条；每条至少引用 2 个 agent 的证据，且归因目标只能是 skill 或 agent。

| finding | 家族 | 类别 | 归因目标 | 跨 agent 证据 |
|---|---|---|---|---|
| `finding:gh-network-duplication` | 20:05 | agent-orchestration | `agent:<root>` | root、Cicero、Einstein、Lovelace、McClintock、Meitner、Aquinas 的 `gh pr view/status` 均以 GitHub 不可达失败 |
| `finding:skill-path-drift` | 17:32 | skill-usage | `skill:systematic-debugging` | root、Volta、Hubble、Descartes、James 从三种缓存路径读取同一 skill |
| `finding:walkthrough-skill-reload` | 08:46 | skill-usage | `skill:walkthrough-change-metadata-gen` | root 连续加载 31 次，Copernicus 又独立加载一次；首次路径错误 |
| `finding:parallel-patch-conflict` | 12:34 | agent-orchestration | `skill:subagent-driven-development` | Raman、Laplace、Wegener、Kierkegaard 在共享文件上反复出现 patch 上下文失效 |

证据锚点使用 `rolloutId + ordinal`，`line` 只作展示。实现时以 `ordinal` 重新定位记录并重算行号，避免文件追加后续段后行号漂移。

## 8. 测试策略

### 8.1 单元测试

使用内存文件源，覆盖：

- 4 个 root 的递归发现，guardian 不进家族。
- 两个 agent 复用同一 `session_id` 时不互相覆盖。
- 同一 `threadId` 的主段与续段合并，`rolloutCount` 不增加。
- 索引阶段 `readRecords` 调用次数为 0；加载单个 rollout 只读该文件。
- 缺失父节点、环路、空文件、坏 JSON 的诊断行为。
- skill 路径归一化、同一次调用读取多个 skill、证据锚点解析。
- 示例问题至少 3 条、每条至少引用 2 个不同 agent、目标 ID 可解析、证据 ordinal 存在。

### 8.2 本地集成测试

设置 `HARNESS_SNAPSHOT_ROOT` 时运行，断言：

- 4 个家族、64 个 rollout、25,170 条主段记录、12 条续段记录、72.2 MB、最大深度 4。
- 12:34 家族只有一个 root，续段挂在同一 `AgentNode` 下。
- 示例问题的每条证据都能在对应 rollout 中按 ordinal 命中，且 agent 属于该家族。
- 索引阶段没有读取任何 rollout 正文。

未设置环境变量时跳过集成测试；CI 仍执行单元测试、类型检查与构建。

### 8.3 门禁

实现完成后运行：

```sh
pnpm typecheck
pnpm test
pnpm build
pnpm verify:flow
pnpm verify:docs
```

## 9. 验收映射

| issue 验收 | 落地 |
|---|---|
| 4 家族 64 rollout、25,170 记录、72.2 MB、深度 4 | `measureFamily` + 本地集成测试 |
| 还原父子关系，不因 session_id 复用覆盖 | `threadId` 主键 + 重复 session_id 单元测试 |
| 按需读取单个 rollout，不启动解析全部 72.2 MB | `buildFamilyIndex` 只读首行；`readRecords` 计数测试 |
| 至少 3 条跨 agent 示例问题与稳定证据锚点 | 4 条 finding fixture + ordinal 解析测试 |
| 每条问题解析出 skill / agent 目标 ID 与名称 | `resolveFinding` + 目标格式校验 |
| 原始 JSONL 不进仓库，fixture 脱敏 | 只提交派生 findings 与小型内存 fixture |
| 自动化测试、类型检查、文档门禁通过 | 第 8.3 节命令 |

## 10. 已知边界与后续

- 浏览器读取路径未接：`NodeSnapshotSource` 只供 Node 脚本、测试和后续本地开发接线使用；#14/#15 决定通过生成物、开发服务器还是 File System Access API 接入。
- `recordCount` 按主段统计，续段单独报告；这是为了保持 #10 的验收口径，同时不丢数据。
- skill 派生只覆盖显式 `SKILL.md` 读取；隐式 skill 行为、工具调用归因和错误分类归 #8/#9。
- 示例问题为人工核对快照，不冒充实时模型诊断；后续真实分析替换时保持 `Finding` / `EvidenceRef` 契约不变。
