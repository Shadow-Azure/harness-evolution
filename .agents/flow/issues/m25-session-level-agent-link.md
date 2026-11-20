# 会话级 Parser：can_parse 轨迹选型、成员变量与父子关联

[English](m25-session-level-agent-link.en.md) | 中文

```yaml flow
kind: issue
id: m25-01
milestone: m25
depends:
  - m9-06
  - m9-03
priority: P1
status: ready
scope:
  - apps/api/app/service/acquisition/**
  - apps/api/tests/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/**
  - scripts/doc-budgets.manifest.json
adr:
  - ../../notes/implemented/architecture/2026-11-20-session-scoped-parser-can-parse.md
github:
  number: 429
  url: https://github.com/Shadow-Azure/harness-evolution/issues/429
```

## 背景

生产 session `226504ab-f005-42ce-a9f5-8313c45d669e` 的执行流出现三个 `synthetic-agent`：三个子 Agent 都挂在 L1412–L1414，而不是各自的真实调用点 L1028 / L1202 / L1411；结构树标“合成”，lane DAG 三条子 lane 全部堆到约 78%。根因是 envelope 的 `agentMeta` 只透出 `name`、没有 `toolUseId`，而当前 parser 是单 transcript 无状态的，跨 transcript 的父子关联只能由 `agent_tree` 用弱字段兜底。

- 当前 `TraceParserFactory.create(runtime_key)` 只按 runtime 身份选子类；`BaseTraceParser.normalize(payload)` 一次只处理一个 Agent 的 JSONL；`ClaudeCodeTraceParser` 在归一化阶段看不到同 root 的其它 transcript，直到 `agent_tree.assemble_agent_trees` 才拿到全部 transcript。
- 这与“创建 `ClaudeCodeTraceParser` 时就把整个会话主 Agent + 所有子 Agent 的轨迹初始化到成员变量，父类加接口、子类实现”的设计意图不一致；上一版 issue 的 B 方案（无状态 parser + link 钩子）只解决了父子关联，没有落成该会话级模型。
- 原始数据里父 `toolUseResult.agentId` 与子 JSONL 顶层 `agentId` 是 3/3 精确对应的（`call_6424…→ad5308…`、`call_78b3…→a02a17…`、`call_b302…→a396a3…`），足以在子类内完成父子关联；`toolUseId` 存在时仍应优先作为 authoritative 证据。

按用户 2026-11-20 的要求，本 issue 改为方案 A：parser 以会话为生命周期，构造时把该 root 的全部轨迹初始化到成员变量；同时把 parser 选型从“只看 runtime_key”改为“根据轨迹判断”，在父类新增抽象函数 `can_parse`（即用户表述的 `can_parsed`），由子类实现“能否初始化这条轨迹”。

## 目标

- 把 `BaseTraceParser` 改为会话级 parser：构造函数接收同一个 root 的全部 `TracePayload`（主 Agent + 所有层级的子 Agent），初始化 `self.payloads`、`self.main`、`self.subagents` 等成员变量，并提供 `normalize_session()` 一次产出全部 transcript 与父子链接。
- 在父类新增抽象类方法 `can_parse(payloads) -> bool`；每个子类实现基于轨迹内容的判定，用于在不知道/不依赖 runtime_key 时选择 parser。
- `TraceParserFactory` 提供按轨迹选型：遍历已注册子类的 `can_parse`，唯一命中才实例化；零命中抛 `UnsupportedTraceRuntime`，多命中抛 `AmbiguousTraceRuntime`。`runtime_key` 保留为元数据/注册身份，不再作为唯一选择依据。
- `ClaudeCodeTraceParser` 实现 `can_parse`（识别 Claude Code JSONL 的主/子会话形态），在 `normalize_session()` 中使用 `self.main` / `self.subagents` 完成父子关联：优先 envelope 的 `toolUseId`（authoritative），缺失时用父 `toolUseResult.agentId` ↔ 子 JSONL 顶层 `agentId`（derived）。
- `replay` / `local` / `normalize` 三条入口改为“先按 root 取齐全部 payload，再创建会话级 parser，再 normalize_session”，把 transcript 与链接交给 `agent_tree`；无链接或歧义链接保留 `synthetic`。
- 更新 `plans/fullstack-design/01-architecture.md` §4.1 的 parser 选型与会话生命周期契约，补 Agent Note；`parser_version` 提升并重放存量 root。

## 设计依据

- [01 §4.1 原始轨迹接入与归一化链路](../../../plans/fullstack-design/01-architecture.md)：当前 `TraceParserFactory` 按 runtime 选子类、新增 runtime 只新增子类；本 issue 把选型升级为基于轨迹的 `can_parse`，并把 parser 生命周期提升为会话级，需同步修订该节。
- [06 §7.1 用户轮次/消息与 Agent 会话树派生](../../../plans/fullstack-design/06-database-design.md)：子 Agent 的 `*.meta.json.toolUseId` 指向父 Agent 调用，`agentId` 是子 Agent 身份；本 issue 在 envelope 缺 `toolUseId` 时用两处 `agentId` 兜底。
- [05 §10 轨迹查询接口](../../../plans/fullstack-design/05-api-design.md)：上游 payload 契约保持不变；本 issue 只改 HE 侧的选型、生命周期与降级语义。

## 实现内容

- `parsers/base.py`：`BaseTraceParser.__init__(payloads)` 保存会话级成员（`payloads`、`main`、`subagents`）；新增抽象类方法 `can_parse(payloads)`；新增模板方法 `normalize_session()`（逐 payload 归一化 → 调用子类 `link_transcripts()` → 返回 transcripts + `AgentLink`）。
- `parsers/factory.py`：新增 `for_trace(payloads)` 按 `can_parse` 唯一选型并实例化；保留 `create(runtime_key, payloads)` 作为显式/测试入口；`CURRENT_PARSER_VERSION` 改为读注册类的版本号，不再用无参实例探测。
- `parsers/claude_code.py`：实现 `can_parse`（探测首条 JSONL 的 `sessionId` / `uuid` / `type` / `message` / `toolUseResult` / `isSidechain` / `agentId` 等 Claude 形态）；`normalize_session` 用 `self.main` / `self.subagents` 做父子关联；优先 `toolUseId`，缺失时用两处 `agentId`；`parser_version` 6→7。
- `normalize.py` / `replay.py` / `local_sessions.py`：先按 root 取齐 payloads，再 `TraceParserFactory.for_trace(payloads)` 创建会话 parser，调用 `normalize_session`；单 transcript 的兼容入口保留为一次单 payload 会话。
- `agent_tree.py`：接收会话级 parser 返回的 transcripts + links，只应用链接；不读取 Claude 的 `agentId` / `toolUseResult` 字段；未命中/歧义保留 `synthetic`。
- 选型语义：`can_parse` 只做快速形态探测，不完整解析；多子类同时命中视为契约歧义，必须显式消歧，不能按注册顺序静默选择。
- 生命周期/内存：parser 每个 root 一个实例，只持有已加载 payloads 的引用，不复制原始 JSONL；会话结束后释放，不跨 root 复用；不引入跨请求缓存。
- 测试与文档：新增 `can_parse` / 选型 / 会话成员 / 父子链接 / 兼容入口测试；同步修订 01 §4.1 与 Agent Note；生产验收只读 226504ab，不提交其内容。

## 实施步骤

1. 在 `parsers/base.py` 定义会话级 `__init__`、抽象 `can_parse`、`normalize_session()` 模板与 `AgentLink` 返回契约。
2. 在 `parsers/factory.py` 实现 `for_trace(payloads)` 的唯一选型、`AmbiguousTraceRuntime`，并调整版本探测。
3. 在 `parsers/claude_code.py` 实现 `can_parse`、会话成员初始化与 `normalize_session` 的父子关联，提升 `parser_version`。
4. 改 `normalize.py` / `replay.py` / `local_sessions.py`：先取齐 root payloads，再创建会话 parser，再归一化。
5. 改 `agent_tree.py`：接收并应用会话 parser 返回的 links，保留 synthetic 兜底。
6. 补单测与 API 测试，跑聚焦门禁；部署后 replay/backfill，核对 226504ab。
7. 更新 01 §4.1、Agent Note 与流程状态；PR 附修复前后的真实应用截图。

## 依赖与交付边界

- 依赖：m9-06（parser 工厂）、m9-03（关系证据）；两者均已完成。
- 交付边界：只改 HE 的 acquisition parser/factory/agent_tree 与三条入口、测试与设计文档；不改上游 envelope；不改 DB schema / 共享契约 / 前端；不触碰其它 runtime 的语义；生产 Session 内容与截图不入库。

## 独立验证

```sh
pnpm test:api -- -k "parser_factory or claude_code_parser or agent_tree or sessions"
pnpm test:gates
pnpm verify:flow
pnpm verify:flow-online
```

- 预期：`can_parse` 能识别 Claude 轨迹、拒绝非 Claude；选型在缺失/错误 runtime_key 时仍正确，歧义/零命中报稳定错误；会话 parser 的 `self.main` / `self.subagents` 在 normalize_session 中可见；226504ab 形态 fixture 得到 4 个 transcript + 3 个链接，API tree 无 synthetic；兼容入口与其它 runtime 不回归。
- 生产验收：部署后对 226504ab 触发 replay，`GET .../tree` 的 3 个子 Agent `toolUseId` 为 `call_6424… / call_78b3… / call_b302…`，`relationConfidence=derived`，lane DAG 子 lane 起于 L1028 / L1202 / L1411；Before/After 截图入 PR。

## 验收标准

- `BaseTraceParser.can_parse` 是抽象类方法；`ClaudeCodeTraceParser` 实现基于轨迹内容的判定，非 Claude 轨迹不被接受；选型不依赖 runtime_key 也能完成。
- `TraceParserFactory.for_trace` 唯一命中才实例化；零命中抛 `UnsupportedTraceRuntime`，多命中抛 `AmbiguousTraceRuntime`，不按注册顺序静默选择。
- 会话 parser 构造时收到同 root 的全部 payload；`self.main` / `self.subagents` 在 `normalize_session` 中可用；一次产出 4 个 transcript 与 3 个父子链接。
- 226504ab 形态 fixture 的结构树与 lane DAG 不再出现 `synthetic-agent`，3 个子 Agent 挂到真实 `call_…`；缺失/重复/歧义仍保留 `synthetic` 并记录稳定 issue。
- 兼容入口（单 payload `normalize` / evidence）与其它 runtime 行为不变；`parser_version` 提升后 replay 可重建存量树；无 DB/契约/前端 diff。
- 聚焦测试、流程/文档门禁通过；01 §4.1 与 Agent Note 已更新；PR 含 Before/After 证据。

## 门禁与 CI

- 命中：`pnpm test:api`、`pnpm test:gates`、`pnpm verify:flow`、`pnpm verify:flow-online`、`pnpm lint:api`、`pnpm typecheck:api`、`pnpm verify:docs`。
- 不新增依赖；scope 覆盖 parser、factory、agent_tree、三条入口、测试、docs/flow；CI 使用合成/脱敏 fixture。

## 非目标

- 不修改评估平台会话包与 `toolUseId` 透传（另立上游 issue）。
- 不改前端 lane DAG / 结构树布局或共享契约字段。
- 不新增数据库列/迁移；不改 bad case 锚点、归因或自进化算法。
- 不把生产 Session 内容、截图或凭据提交到仓库；不引入跨 root 的 parser 缓存。
