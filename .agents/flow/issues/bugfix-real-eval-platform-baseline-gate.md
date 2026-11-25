# 真实评测接入：评测平台工厂化适配与 SkillOpt 式基线门控

[English](bugfix-real-eval-platform-baseline-gate.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-62
milestone: bugfix
depends:
  - m12-03
priority: P2
status: ready
scope:
  - apps/api/**
  - apps/web/src/**
  - tests/**
  - packages/contracts/**
  - docs/**
  - plans/**
  - deploy/**
  - .github/workflows/**
  - .env.example
  - .agents/flow/**
  - .agents/notes/**
  - scripts/doc-budgets.manifest.json
adr:
  - ../../notes/implemented/architecture/2026-11-17-real-patch-eval-seams.md
github:
  number: 620
  url: https://github.com/Shadow-Azure/harness-evolution/issues/620
```

## 背景

### 特性诉求

自进化运行的评测目前仍是占位网关：`fake` 返回配置里的占位分数，`http` 模式对接的是设计稿里的通用 `/evals` 协议，没有真实平台实现它。需要把候选评测切到真实评测平台，并满足以下四点诉求。

- 换评测平台时只新增一个子类、在工厂类注册、修改 `.env`；每个平台的对接细节全部封装在子类里，上游只通过父类接口调用。
- 生产环境由 GitHub Secrets 配置平台选项，Deploy 流水线把它注入服务器 `.env`。
- 评测指标 key 按验证与测试分别配置，在配置进化对象时与两个评测工程一起维护。
- 评测循环按 SkillOpt 的方式运行：初始版本评一次作为基线，每轮改完评一次并与之比较；接纳后的修改基于已接纳的 Skill 生成 edit patch，基线变为被接纳那次的分数。

### 现状分析

- 接缝已存在但不是目标形态：`EvalGateway` 是 `Protocol`，`FakeEvalGateway` 放在 service 层，`HttpEvalGateway` 是 dataclass，`build_eval_gateway_factory` 用 `if mode == "fake"` 分支选择，`HE_EVAL_MODE` 的合法值在 `config.py` 里硬编码。
- `HttpEvalGateway` 与 `EvalMapper` 说的是虚构协议：`POST /evals`、camelCase 字段，响应直接返回 `currentScore` 与 `externalVerdict`。
- 裁决入口已经是 `external_verdict == "accept"`；每轮已有 `eval_current` 与 `eval_candidate`，终评的初始分取第 1 轮的 `eval_current`。数据模型已经为基线留了位置，只是基线值目前假定由平台返回。
- 编辑基于上一个已接纳状态这一点已经满足：接纳时 run 分支快进，拒绝时 run 分支不变，下一轮候选仍从 run 分支切出。
- 对象配置已有验证集与测试集测试工程 ID，并已快照到 run，但运行时没有任何代码消费它们。
- 两个缺口：幂等键不含尝试次数，平台侧失败后重试会重放同一个评测；`HE_EVAL_*` 的 Secret 删除后服务器旧值仍然生效。

### 评测平台契约与生产核查

评测平台 PR #431 已合入并部署，提供了机器触发所需的全部接口；契约方向是 HE 适配平台，平台不提供 verdict。

- launch：`POST /api/v1/eval-templates/{template_id}/launch`，Bearer 服务令牌；body 含 `asset_override`（repo_url、ref、commit、asset_paths、asset_types）与 `lineage`；202 返回 `run_id`、`created` 与 `asset.resolved_commit`。
- status 与 results：`GET /api/v1/eval-runs/{run_id}/status` 有 11 个状态与 `terminal`；`results` 只返回指标项，SWE-bench 数据集的指标项为 `resolved_rate`、`resolved_rate_scored`、`resolved_count`、`execution_failure_rate` 与 token、成本类。
- 生产平台现状：4 个模板全部绑定 OpenSpec-cn 资产源，其中 3 个开启了指向 HE 的自进化上报；SuperPower 只登记为资产源，没有模板；数据集只有 6 用例与单用例两种规模，6 用例一轮实测约 34 分钟与 35 美元。
- 候选仓库：实测确认 GitHub 允许经上游仓库的 API 读取 fork 独有的 commit、文件树与文件内容，所以子类不传 `repo_url`，继承模板的资产源即可，不需要登记 HE 的推送 fork。
- 令牌：生产前端包里没有任何服务令牌界面，创建只能走 `POST /api/v1/service-tokens`，需要管理员会话；令牌需同时具备 `eval:launch` 与 `eval:read`。

| 核查项 | 结果 | 影响 |
|---|---|---|
| 现有模板能否直接用于候选评测 | 不能：3 个开启自进化上报，唯一关闭的用竞价竞争态资源池，附加指令均为 OpenSpec 专用 | 需求方在评测平台控制台新建 HE 专用的验证与测试模板 |
| SuperPower 资产源是否够用 | 够用：fork 独有的候选 commit 可经上游仓库读取 | 不需要登记推送 fork |
| 令牌创建方式 | 仅 API，没有界面 | 运维用管理员会话创建后写入 GitHub Secrets |
| 验证集分辨率 | 6 用例的解决率步长为 16.7 个百分点 | 数据集版本后续由需求方在平台侧更换 |

### SkillOpt 对照

[microsoft/SkillOpt](https://github.com/microsoft/SkillOpt) 的论文路径与诉求一致：训练前先把初始 Skill 在选择集上评一次，`current_score` 与 `best_score` 都初始化为它；每步的候选只在选择集上评一次，严格高于当前分才接纳，接纳后当前 Skill 与当前分换成候选的，拒绝则什么都不动；最后把初始与最终 Skill 在留出测试集上各评一次。

| SkillOpt 机制 | HE 现状 | 本 issue |
|---|---|---|
| 初始基线评测 | 没有 | 新增运行级基线评测 |
| 基线顺延为被接纳那次的分数 | 没有 | service 层按已接纳轮计算 |
| 严格高于才接纳 | 采信网关返回的 verdict | 平台无关的裁决组件 |
| 编辑基于已接纳的 Skill | 已满足 | 不变 |
| 测试集终评 | 终评只是各轮验证分的汇总 | 新增测试集终评 |

### 讨论记录

以下条目于 2026-11-25 与需求方逐项讨论，D5、P1、P2、P6 于同日第二轮确认。状态为「待确认」的条目在实现前需要拍板，方案里已给出默认取值。

| 编号 | 议题 | 结论 | 状态 |
|---|---|---|---|
| D1 | 接入形态 | 工厂类加 ABC 父类，每个平台一个子类并在工厂注册，由 `HE_EVAL_MODE` 选择 | 已确认 |
| D2 | 契约方向 | HE 适配平台的 launch、status、results 与服务令牌，不沿用虚构的 `/evals` 协议 | 已确认 |
| D3 | 主指标 key 的位置 | 对象配置，与验证集、测试集测试工程 ID 同组；工程 ID 即平台评测模板 ID | 已确认 |
| D4 | 推送 fork 是否登记为资产源 | 不需要，子类不传 `repo_url` | 已核实 |
| D5 | 平台模板 | 不复用现有模板；需求方后续在评测平台控制台新增专用的验证与测试模板，并关闭自进化上报 | 已确认 |
| D6 | 令牌创建 | 经 `/api/v1/service-tokens` 用管理员会话创建，scopes 含 `eval:launch` 与 `eval:read` | 已核实 |
| D7 | 基线来源 | 真实评测：初始版本评一次，基线随接纳顺延 | 已确认 |
| D8 | 基线与第 1 轮 | 并行启动 | 已确认 |
| D9 | 接纳规则 | 严格大于，平票拒绝，后续再优化 | 已确认 |
| D10 | 测试集终评 | 纳入第一期 | 已确认 |
| P1 | 验证集与测试集规模 | 会调整：数据集版本后续由需求方在平台侧更换，HE 不绑定用例数 | 已确认 |
| P2 | 主指标 key 是否验证、测试各一个 | 不保证共用：验证与测试分别配置主指标 key | 已确认 |
| P3 | `partial` 与 `paused_budget` 的口径 | 默认加最低完成率护栏，预算暂停直接判失败 | 待确认 |
| P4 | 旧 `http` 模式 | 默认退役并删除 | 待确认 |
| P5 | `knowledge` 目标 | 默认本期不支持，子类显式拒绝 | 待确认 |
| P6 | 终评 verdict 口径 | 有接纳轮且测试集终评分严格高于测试集基线分 | 已确认 |

## 目标

- 评测网关改为工厂类加父类加子类：新增平台只加子类与注册，`.env` 的 `HE_EVAL_MODE` 选择实现。
- 新增 ai-eval-platform 子类，封装 launch、status、results、错误信封与服务令牌的全部细节。
- 运行开始时对初始版本做真实基线评测，并与第 1 轮候选评测并行。
- 裁决放在 service 层：候选分严格高于基线才接纳，接纳后基线顺延。
- 全部迭代结束后用测试集做终评，verdict 取有接纳轮且测试集终评分严格高于测试集基线分。
- 对象配置为验证与测试分别新增主指标 key，两个测试工程 ID 在创建运行时进入评测配置快照。
- GitHub Secrets 经 Deploy 流水线注入 `.env`，文档与 `.env.example` 同步。

## 设计依据

- [14 §2 术语与语义](../../../plans/fullstack-design/14-target-project-ids.md)：验证集用于逐轮候选决策，测试集用于最终独立验收；该切片把评测 gateway 留给后续，本 issue 即该后续。
- [07 §5.7 评测接入与轮询](../../../plans/fullstack-design/07-backend-implementation.md)：现有网关接缝与 `HE_EVAL_*` 兜底；本 issue 把 mode 分支改为注册表，需同步修订。
- [07 §5.8 应用评测结果、重试与终评](../../../plans/fullstack-design/07-backend-implementation.md)：裁决、重试与终评的现有流程；本 issue 在其中加入基线、门控与测试集终评。
- [05 §4.11 进化对象配置](../../../plans/fullstack-design/05-api-design.md)：对象配置接口；本 issue 为验证与测试各增加一个主指标 key。
- [06 §5.2 evolution_runs](../../../plans/fullstack-design/06-database-design.md)：`eval_config` 与测试工程 ID 快照；本 issue 新增运行级评测存储。
- [04 §9 配置项清单](../../../plans/fullstack-design/04-backend-architecture.md)：`HE_EVAL_*` 的语义随本 issue 更新。
- [Agent Note：真实 patch 与评测接缝](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/architecture/2026-11-17-real-patch-eval-seams.md)：记录现有 mode 工厂与 Secrets 通道的决策，本 issue 更新其事实。
- 外部依据：[评测平台 PR #431](https://github.com/Shadow-Azure/ai-eval-platform/pull/431)、[评测平台 issue #429](https://github.com/Shadow-Azure/ai-eval-platform/issues/429)、[microsoft/SkillOpt](https://github.com/microsoft/SkillOpt)。

## 实现内容

### 方案总览

```text
run start
  ├─ baseline        (validation template @ base commit)  ─┐
  ├─ baseline-test   (test template       @ base commit)  ─┤ in parallel
  └─ iteration 1     (validation template @ candidate)     ─┘
iteration N
  candidate eval → gate: candidate > baseline ? accept : reject
  accept  → run branch fast-forwards, baseline := accepted score
  reject  → run branch and baseline stay unchanged
after the last iteration
  final-test (test template @ final commit) → evolution_finals
```

换平台时只动子类与注册表；裁决、基线顺延与终评都在 service 层，平台子类只负责协议与字段映射。

### 评测网关工厂化

- `third_party_api/eval_gateway/base.py`：`BaseEvalGateway(ABC)` 声明 `provider`、冻结配置与 `submit`、`get_status`、`get_result`，并承载脱敏后的 HTTP 与错误处理。
- `third_party_api/eval_gateway/factory.py`：`EvalGatewayFactory` 维护注册表，提供 `register`、`create` 与 `registered`；装配期按 Settings 与 run 快照产出子类实例。
- `FakeEvalGateway` 改为父类子类并迁入 `third_party_api`，原位置保留 re-export。
- `gateway_factory.py` 改为查注册表，保留 `build_eval_gateway_factory(settings)` 签名；`config.py` 的 `eval_mode` 合法值来自注册表。
- 旧的 `HttpEvalGateway` 与 `EvalMapper` 随虚构协议一并退役，桩测试迁到真实契约。

### ai-eval-platform 子类

- 提交：`POST /api/v1/eval-templates/{validationProjectId}/launch`，Bearer 服务令牌；`Idempotency-Key` 由 run、轮序号、候选 commit 与尝试次数组成；body 携带 `asset_override` 的 commit、ref、asset_paths 与 asset_types，以及 `lineage`。
- 提交后断言 `asset.resolved_commit` 等于候选 commit，`warnings` 记为 run 事件。
- 状态映射：平台 11 态折到 HE 的 5 态，未知状态显式判失败。

| 平台状态 | HE 状态 | 说明 |
|---|---|---|
| `preparing`、`queued` | `queued` | 等待 |
| `running`、`finalizing`、`cancelling` | `running` | 执行中 |
| `completed` | `completed` | 取结果 |
| `partial` | `completed` | 受最低完成率护栏约束，不达标判失败 |
| `failed`、`cancelled` | `failed` | 终态失败 |
| `pausing_budget`、`paused_budget` | `failed` | 平台不会自愈，直接失败并给出可操作信息 |

- 结果与错误：`results` 的指标项原样进入测量值，由 service 层取主指标；错误信封映射为带平台错误码的网关错误，401、403、404、422 判不可重试，5xx、429 与网络错误标为可重试。
- 资产映射：`skill` 取 `asset_paths=[subDir]`；`agent` 以 `asset_types` 显式声明为 subagent；`knowledge` 显式拒绝。

### 基线、门控与测试集终评

- 新增运行级评测表，保存不属于任何一轮的评测：验证集基线、测试集基线与测试集终评；字段与轮上的评测列同构，含外部 ID、状态、轮询时间、尝试次数、分数与原始指标项。
- 创建运行后立即并行提交验证集基线与测试集基线；第 1 轮候选照常提交，其裁决等待验证集基线完成。
- 门控：轮次 N 的基线取最近一个已接纳轮的候选分，没有则取验证集基线分；候选分严格高于基线才接纳，按验证主指标 key 与指标方向比较，平票拒绝。
- `EvalGateway.get_result` 改为返回测量值；service 层的裁决组件产出 `EvalResult` 后再落库，`apply`、终评与前端读到的结构不变。
- 最后一个迭代终结后提交测试集终评，写入 `evolution_finals`：初始分取测试集基线分，最佳分取测试集终评分，verdict 取有接纳轮且终评分严格高于基线分。
- 提交信息里的 `Harness-Decision-Rule` 与裁决文案改为真实规则。

### 对象配置、快照与契约

- `evolution_targets` 新增 `validation_metric_key` 与 `test_metric_key` 两列并补迁移；请求模型、仓储与 OpenAPI 契约同步再生。
- 创建运行时把 `validationProjectId`、`validationMetricKey`、`testProjectId`、`testMetricKey` 与 `subDir` 写入 `eval_config` 快照，向导传入的 `eval` 覆盖优先。
- 选中真实平台而缺少模板 ID 或主指标 key 时，创建运行返回 422 并定位到字段。
- 前端对象配置表单在验证集、测试集测试工程 ID 旁各增加一个「主指标 key」，列表与错误文案同步。

### 配置、部署与文档

```text
HE_EVAL_MODE=fake or ai-eval-platform
HE_EVAL_BASE_URL=<platform base URL>
HE_EVAL_API_KEY=<service token; inject via GitHub Secrets only>
```

- `.env.example` 更新三个 `HE_EVAL_*` 键的说明；流水线注入已覆盖这三个键，不新增 Secret。
- `deploy.yml` 在 Secret 为空时显式移除对应键，避免删除 Secret 后旧值继续生效。
- `docs/architecture.md` 去掉「未具备：真实评测」并描述新接缝；`docs/deployment.md` 与部署手册同步。
- Agent Note：更新「真实 patch 与评测接缝」的事实，并新增一条记录基线门控与测试集终评的决策。

## 实施步骤

1. 新增运行级评测表的迁移、模型与仓储，补双方言数据库测试。
2. 把 `FakeEvalGateway` 迁为 `BaseEvalGateway` 子类，引入 `EvalGatewayFactory`，让默认配置下的行为与现状一致。
3. 实现裁决组件与基线顺延，`get_result` 改为返回测量值，fake 模式走同一套裁决。
4. 实现 ai-eval-platform 子类与真实契约桩，覆盖提交、状态表、结果与错误信封。
5. 接入基线评测与第 1 轮并行提交，以及迭代结束后的测试集终评。
6. 对象配置为验证与测试分别新增主指标 key，运行快照带上模板 ID 与两个指标 key，再生契约。
7. 更新 `.env.example`、`deploy.yml`、文档与 Agent Note，跑全部门禁。
8. 平台侧运维前置：需求方在评测平台控制台新建验证与测试模板，创建服务令牌并配置 GitHub Secrets，再用真实运行验收。

## 依赖与交付边界

- 依赖：m12-03（评测网关接缝与 `HE_EVAL_*` 的 Secrets 通道），已完成。
- 平台侧前置（不在本仓代码范围）：需求方在评测平台控制台配置的、关闭自进化上报的验证与测试模板，含两个 scope 的服务令牌，GitHub Secrets 中的 `HE_EVAL_MODE`、`HE_EVAL_BASE_URL` 与 `HE_EVAL_API_KEY`。
- 交付边界：只交付 HE 侧的网关、裁决、存储、对象配置与部署文档；评测平台的代码与模板由平台仓库或控制台维护。
- 「待确认」事项按讨论记录中的默认取值实施，拍板后如有变化在同一 PR 内调整。

## 独立验证

```sh
pnpm test:api -- -k "eval_gateway or gateway_factory or eval_gate or evolution_evaluations"
pnpm test:db
pnpm contract:check
pnpm verify:flow
pnpm lint:docs
```

- 数据：按平台真实契约编写的本地桩（launch、status、results 三个端点、11 个状态与错误信封），加上测试里已有的 bare 远端与种子仓库。
- 预期：运行开始后基线与第 1 轮候选的幂等键不同且并发在途；候选分等于基线时拒绝，高于时接纳且下一轮基线更新；拒绝后 run 分支不变；终评行含测试集基线分与终评分，verdict 按口径计算；fake 模式的结果与现状一致。

## 验收标准

- `HE_EVAL_MODE=ai-eval-platform` 时网关是注册表里的子类，未知取值启动失败；`fake` 下行为与现状一致。
- 真实运行中，验证集基线与第 1 轮候选评测并行在途，第 1 轮裁决晚于基线完成。
- 接纳当且仅当候选分严格高于基线；接纳后下一轮基线等于被接纳轮的候选分，拒绝后基线不变。
- 提交后 `asset.resolved_commit` 与候选 commit 一致；平台的 4xx 配置类错误进入 `blocked(stage=eval)` 并带平台错误码。
- 运行结束后 `evolution_finals` 记录测试集上的初始分与最终分，verdict 为有接纳轮且终评分严格高于基线分。
- 对象配置分别保存验证与测试的主指标 key，缺失时创建运行返回 422；契约无漂移。
- 覆盖率不低于 80%，流程与文档门禁通过。

## 门禁与 CI

- 命中：`pnpm test:api`、`pnpm test:db`、`pnpm test:gates`、`pnpm contract:check`、`pnpm lint:api`、`pnpm typecheck:api`、`pnpm verify:flow`、`pnpm verify:flow-online`、`pnpm lint:docs`、`pnpm verify:docs`。
- 同一 PR 内新增或更新 Agent Note；不新增门禁脚本。

## 非目标

- 不改评测平台的代码与契约；专用模板由需求方在控制台配置，HE 不自动创建。
- 不做自动合并；晋升仍由人工审阅 PR。
- 不优化接纳规则：最小提升量、重复评测与噪声处理留待后续。
- 不登记 HE 的推送 fork 为平台资产源，不引入通用的 `/evals` 协议。
- 不把生产地址、令牌或控制台凭据写入仓库。
