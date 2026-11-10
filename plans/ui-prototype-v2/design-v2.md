# Harness Evolution V2 前端原型设计

> 可点击原型：`harness-evolution.html`。本目录从 `plans/14-15-ui-prototype` 完整拷贝后迭代；V1 文件保留为对照基线。所有数据为打桩样例，不进入生产代码。

## 1. 目标与范围

V2 在 V1 的「Session 错误查看 × 自进化」单页原型上增加四类能力：

1. 多用户登录与角色（唯一全局管理员 + 普通用户，不开放注册）。
2. 多工作空间、成员与空间管理员、bad case 上报额度。
3. 工作空间总览：按 `object_name` / 时间维度看 `self` 与 `discovery`，并支持组合筛选的分页列表与下钻。
4. 把归因从错误详情页移入自进化启动流程；错误详情承载「一个 bad case × 多个进化对象」的归因集合。

V2 不是重做一套设计系统。原型的目标是验证信息架构和交互，因此尽可能复用 V1 的壳层、视觉 token、卡片、表格、流程图和演化详情组件。

## 2. 与 V1 的连续性

### 2.1 直接复用

| V1 资产 | V2 处理 |
|---|---|
| 顶栏、品牌、页签下划线选中态、`--bg/--card/--blue/--purple` 等 token | 原样保留；只在右侧增加工作空间切换器与用户菜单 |
| Session 卡片、状态点、密度条、统计条、家族树 React Flow | 原样保留；列表默认改为最新 10 条，搜索改为回车精确查询 |
| 错误详情左右分栏、执行流、问题描述 / 归因分析双 Tab | 保留布局；左栏由错误卡改为可折叠的 bad case 组，组内增加归因分页列表 |
| 自进化列表 run-card、详情 panel/stepper/cluster/diff/eval/commit | 保留组件；流程步骤改为「选择范围 → Session 关联 → 潜在 bad case → 对象归因 → 迭代 → 终评」 |
| 启动向导 modal、条件摘要条、分页表格 | 保留 modal 结构；新增 Session 关联与潜在策略预览 |
| 进化对象配置 targets 表格与编辑弹窗 | 保留；配置按工作空间隔离 |
| 亮色、13px 正文、圆角 8–12px、低饱和边框、红/橙/紫语义色 | 全部沿用，新增页面不引入第二套色彩 |

### 2.2 V2 新增但仍使用 V1 语言

- 登录页是独立的轻量卡片，左侧说明、右侧账号列表；品牌色和圆角与主应用一致，没有换成深色营销页。
- 工作空间总览沿用 V1 的 `statstrip` 数字条、`card panel`、`chip`、`table.rep`、`pager` 语言；图表只用 V1 的蓝/紫两色。
- 空间管理沿用 V1 的 `targets` 表格、`evov/modal` 弹窗、`btn` 与 `badge`；没有另造一套后台框架。
- 新增的权限提示、只读态、空态使用 V1 的 `.waiting` / `.empty` 语气。

### 2.3 迁移表

| V1 | V2 | 迁移动作 |
|---|---|---|
| `I-XXXX-NN` / `R-XXXX-NN` 双 ID | `BC-<空间>-NNN` bad case ID；`AT-…` 归因 ID | 旧深链参数 `issue/report` 仍可解析到对应 bad case；新深链用 `case/at` |
| `?page=session&view=errors&sid=&issue=&dtab=` | `?page=session&view=errors&ws=&sid=&case=&dtab=&at=` | 保留 `sid` 与 `dtab` 语义；新增 `ws` 以明确空间 |
| 错误详情 `ERROR_META` 内嵌唯一归因 | `bad_case_attributions` 集合，按对象版本多条 | 单条旧结论作为迁移数据写入默认对象版本；视图改为集合 |
| 自进化输入「问题报告」 | 自进化输入「时间段内该空间的 bad case + 关联 Session」 | 报告聚类改为归因后聚类；来源表改用 bad case |
| 全局 `targetConfigs` | 按 `workspace_id` 隔离的 targets | 配置读写都带 workspace 约束 |
| 无空间上下文的 URL | `/workspaces/:workspaceId/*` 等价 query | 旧路由按「用户最近访问且有权限的空间」重定向；解析不到时进入空间选择 |

## 3. 身份与权限

### 3.1 账号模型

- 全局管理员只有一个账号，原型中为 `林澈 / admin@harness.dev`；不提供注册入口。
- 普通用户由管理员创建或由预留的鉴权接入映射；角色为 `user`。
- 空间角色放在 `workspace_members`：`space_admin` / `member` / `viewer`。全局管理员在任意空间拥有管理权限，且可以被加入某个空间成为空间管理员。

### 3.2 权限矩阵

| 能力 | 全局管理员 | 空间管理员 | 成员 | 只读成员 |
|---|---:|---:|---:|---:|
| 创建/删除工作空间、调整初始额度 | ✓ | — | — | — |
| 查看有权限的空间与数据 | ✓ | ✓ | ✓ | ✓ |
| 调整当前空间额度、上报凭据 | ✓ | ✓ | — | — |
| 添加成员、授予成员/只读 | ✓ | ✓ | — | — |
| 任命/撤销空间管理员 | ✓ | — | — | — |
| 配置进化对象、启动自进化 | ✓ | ✓ | — | — |
| 查看 Session、bad case、归因、运行历史 | ✓ | ✓ | ✓ | ✓ |

原型在界面上隐藏无权限入口，同时在 `v2SetPage` / `evWizardOpen` / `startEvolutionFromCase` 做前端护栏；生产必须在服务端按 `workspace_id + user_id` 再校验一次。

### 3.3 鉴权接入预留

登录页和「空间管理 → 鉴权接入」展示了最小接入契约：

```text
GET  /api/auth/session   -> { user, workspaces[] }
POST /api/auth/login     -> 204 + Set-Cookie: he_session=<opaque>; HttpOnly; SameSite=Lax
POST /api/auth/logout    -> 204 + 清除 Cookie
GET  /api/auth/callback  -> SSO/OIDC 回调，按 sub/email 匹配用户
```

前端只依赖 `GET /api/auth/session` 的 `user + workspaces` 结构；把 `v2Boot` 里的演示账号替换成该返回值即可。用户信息存储、Cookie 刷新、401 重放属于接入层，不进入页面组件。`POST /api/auth/register` 不提供。

## 4. 工作空间

### 4.1 数据与额度

- `workspaces`：`id / name / mark / quota / createdAt / status`。
- `workspace_members`：`workspace_id / user_id / role / joinedAt`，唯一约束防重复。
- `workspace_ingest_credentials`：只存凭据摘要，支持轮换/撤销。
- 额度是 bad case 的累计数量上限，创建时设置、创建后可调整；达到上限时写入返回 `409 QUOTA_EXCEEDED`，不自动丢弃旧数据。

原型中 `ws-harness` / `ws-agent` / `ws-research` 三个空间的 `used` 直接由样例 bad case 计算，避免“额度数字与列表数量不一致”的假数据问题。

### 4.2 上报接口

每个空间生成独立地址：

```text
POST /api/workspaces/{workspaceId}/bad-cases
Authorization: Bearer <workspace credential>
Content-Type: application/json
```

请求体沿用 `bad_cases` 类型：`session_id / object_name / bad_case_type / title / detail / trigger_line / facts / created_at`。空间身份只从 URL 与服务端凭据解析，不信任 body 里的 `workspace_id`。原型在「上报接入」页展示地址、凭据、额度与请求示例，并支持复制。

### 4.3 空间管理交互

- 全局管理员看到全部空间表：额度使用、空间管理员、成员数、进入/成员/额度操作。
- 空间管理员只看到当前空间的额度与成员，不能创建空间。
- 创建空间时选择初始空间管理员（可多选，包括自己）；一个空间允许多个管理员。
- 成员页可添加成员、改成员/只读；全局管理员可任命空间管理员，空间管理员只能授予管理员以下权限。
- 当前账号不是空间管理员时，提供「把自己设为空间管理员」按钮（对应“管理员可以给自己加为某个空间的管理员”）。

## 5. 工作空间总览

### 5.1 指标与筛选

- 顶部 `statstrip`：bad case 总数、self、discovery、关联 Session、object_name 数、额度使用。
- 时间：近 7 / 30 / 90 天或自定义区间；粒度：日 / 周 / 月。
- `object_name` 多选；不选表示全部，多选表示并集。对象 chip 可逐项移除。
- 图表按时间桶堆叠 self（蓝）/ discovery（紫）；下方按对象列出总量与两类占比，并可展开 `object_name × 时间` 明细矩阵。
- 列表筛选独立于图表：时间段、`object_name`、`bad_case_type` 都可为空；空值不限制。分页 8 条/页。

### 5.2 下钻

点击列表行：

```text
?page=session&view=errors&ws=<ws>&sid=<session>&case=<badCase>&dtab=desc
```

进入当前空间的 Session 错误详情，并选中该 bad case 的「问题描述」Tab。左侧自动展开该 bad case 的归因列表。

## 6. Session 错误查看

- 进入页面只请求当前空间最新 10 个 root Session；标题显示「最新 10 / 总数」，不默认拉全量树。
- 搜索框接收 root session ID，回车精确查询（允许 ID 子串）；命中后左侧替换为该结果并选中。
- 清空输入再回车恢复最新 10 个。
- 未命中时左侧与右侧都显示明确的空态，不保留旧选中。
- 选中 Session 后才加载概览与执行流；沿用 V1 的「打开时间线 / 打开错误详情」。

## 7. 归因进入自进化

### 7.1 流程状态

```text
选择进化对象 + 版本 + bad case 时间段
  → 找出该空间在时间段内上报了 bad case 的 Session
  → 判断对象版本是否在这些 Session 中出现（出现才关联）
  → 对关联 Session 找对象触发点与所有 bad case 触发点
  → 按潜在策略筛选潜在 bad case
  → 对每个潜在 bad case 生成「对象版本级」归因
  → 归因后的 bad case 进入聚类 / 迭代 / 终评
```

原型把 Session 关联与潜在 bad case 拆成向导第 2、3 步：第 2 步只看关联 Session（分页），第 3 步只看潜在 bad case（分页），第 4 步才做归因预览与启动。

实现上，`association` 只包含对象出现过的 Session；未出现的 Session 显示“跳过”。潜在 bad case 默认策略：

```text
(object_name == target.name && bad_case_type == self)
OR (bad_case.trigger_line > object.trigger_line)
```

即「对象自身 self 上报」并集「触发点在对象触发点之后」。自定义策略在默认规则上叠加：

- 是否包含对象自身 self；
- 是否包含触发点在对象之后的 bad case；
- 是否仅纳入同 `object_name`。

策略作为运行快照保存，历史运行详情可解释每个候选的命中原因。

### 7.2 缓存

启动向导第四步提供「复用缓存归因」开关。缓存键至少包含：

```text
workspace_id + bad_case_id + object_identity + object_version + policy_version + attribution_model/prompt_version
```

命中时复用最近一次成功归因，不命中时生成新归因；预览展示「潜在 / 复用 / 新增 / 非该对象」四类数量。归因结论只作用于当前对象版本，不修改 bad case 本身，也不影响它与其他对象的潜在关系。

### 7.3 非该对象问题

如果潜在 bad case 无法归因到当前对象（触发时序、输入来源或证据不支持），该对象版本的结论记为「非该对象问题」。它不是“未分析”，也不是对 bad case 的否定；同一 bad case 仍可以归属于其他对象。

## 8. 错误详情：一个 bad case × 多条归因

- 左栏从 V1 的错误卡改为可折叠的 bad case 组：
  - 父行：`#no`、bad case ID、标题、object_name、self/discovery、归因数。
  - 展开后：按「进化对象 · 版本」列出归因子项（结论、时间、缓存标记），每页 2 条。
- 点击父行 → 问题描述 Tab；点击归因子项 → 归因分析 Tab，并定位到该条归因。
- 右栏保留执行流；选中 bad case 时只显示它的 finding 卡。
- 归因分析展示：结论（可归因 / 非该对象问题）、分类、对象版本、运行 ID、时间、缓存来源、置信度、策略、对象触发点 vs bad case 触发点、推导过程与结论边界。
- 没有归因的 bad case 显示“尚未归因”，说明归因在自进化流程中生成；有权限的用户可直接以该 bad case 启动自进化。

## 9. 数据与契约边界

建议新增/扩展：

| 表 | 关键字段 |
|---|---|
| `workspaces` | `id, name, mark, quota, status, created_at` |
| `workspace_members` | `workspace_id, user_id, role, joined_at` |
| `workspace_ingest_credentials` | `workspace_id, credential_hash, created_at, revoked_at` |
| `bad_cases` | 现有字段 + `workspace_id`，`object_name`、`bad_case_type`、`trigger_line`、`created_at` 建索引 |
| `bad_case_attributions` | `bad_case_id, object_identity, object_version, conclusion, category, policy_version, model_version, run_id, is_cached, created_at` |
| `evolution_runs` | 现有字段 + `workspace_id, potential_policy, cache_enabled, attribution_snapshot` |
| `evolution_run_candidates` | `run_id, session_id, bad_case_id, object_trigger_line, bad_case_trigger_line, included_reason, cached_attribution_id` |

所有读接口在服务端追加 `workspace_id` 约束；前端 query key 也以 `workspaceId` 开头，切换空间不得复用旧空间缓存。

## 10. 路由与兼容

```text
/workspaces/:workspaceId/overview
/workspaces/:workspaceId/overview?object=...&type=...&from=...&to=...&page=
/workspaces/:workspaceId/sessions
/workspaces/:workspaceId/sessions/:sessionId/errors?badCaseId=...&tab=problem|attribution&attributionId=...
/workspaces/:workspaceId/evolution
/workspaces/:workspaceId/evolution/:runId
/workspaces/:workspaceId/settings/{workspace,members,ingestion,auth}
```

迁移期旧 `/sessions/**`、`/evolution/**` 按“用户最近访问且有权限的空间”重定向；解析失败进入空间选择页，不静默选择第一个空间。旧 `issue/report` 深链先解析到 bad case 再重定向；一旦历史数据允许多归属，停止自动猜测。

## 11. 原型验收与边界

- 已验证：登录 / 空间切换 / 总览筛选与分页 / 总览下钻 / 最新 10 条与空态 / 错误详情多归因折叠与分页 / 向导四步与缓存 / 空间创建与额度调整 / 成员添加与角色 / 上报接入 / 鉴权接入。
- 渲染：headless Chrome 1440/1600 宽，无 console error；执行流依赖 CDN 的 React / React Flow。
- 未实现：真实鉴权、持久化、统计聚合 SQL、上报写入事务、归因算法、SSO 回调、跨空间 403/404 的服务端测试。前端权限仅是体验护栏。
