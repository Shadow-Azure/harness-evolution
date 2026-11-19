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
| 自进化列表 run-card、详情 panel/stepper/cluster/diff/eval/commit | 保留组件；流程步骤改为「选择范围 → Session 关联 → 潜在 bad case → 对象归因 → 聚类与严重度排序 → 迭代 → 终评」 |
| 启动向导 modal、条件摘要条、分页表格 | 保留 modal 结构；新增 Session 关联与潜在策略预览 |
| 进化对象配置 targets 表格与编辑弹窗 | 保留；配置按工作空间隔离 |
| 亮色、13px 正文、圆角 8–12px、低饱和边框、红/橙/紫语义色 | 全部沿用，新增页面不引入第二套色彩 |

### 2.2 V2 新增但仍使用 V1 语言

- 登录页是独立的轻量卡片，左侧说明、右侧账号列表；品牌色和圆角与主应用一致，没有换成深色营销页。账号列表只用于原型演示，生产登录页保留同样的双栏信息层级但只渲染用户名/密码表单，不枚举账号。
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
| 查看当前空间的归因 Skill 包、下载及查看生效提示词 | ✓ | ✓ | ✓ | ✓ |
| 上传、切换生效项及删除自定义归因 Skill 包 | ✓ | ✓ | — | — |
| 添加成员、授予成员/只读 | ✓ | ✓ | — | — |
| 任命/撤销空间管理员 | ✓ | — | — | — |
| 配置进化对象、启动自进化 | ✓ | ✓ | — | — |
| 查看 Session、bad case、归因、运行历史 | ✓ | ✓ | ✓ | ✓ |

原型在界面上隐藏无权限入口，同时在 `v2SetPage` / `evWizardOpen` / `startEvolutionFromCase` 做前端护栏；生产必须在服务端按 `workspace_id + user_id` 再校验一次。

### 3.3 鉴权接入预留

登录页和「空间管理 → 鉴权接入」展示了最小接入契约：

```text
GET  /api/auth/session   -> 200 { user, workspaces[], truncated }
POST /api/auth/login     -> body {username, password}；200 {accessToken, expiresIn, user}，
                            并写 refresh_token Cookie（HttpOnly; SameSite=Strict; 14 天）
POST /api/auth/refresh   -> 读取 refresh Cookie，200 {accessToken, expiresIn}
POST /api/auth/logout    -> 204 + 清除 refresh Cookie
GET  /api/auth/callback  -> SSO/OIDC 回调，按 sub/email 匹配用户
```

前端只依赖 `GET /api/auth/session` 的 `user + workspaces` 结构；登录页只渲染用户名/密码表单，不读取用户目录，也不提供演示账号选择。演示账号只存在于原型。用户信息存储、Cookie 刷新、401 重放属于接入层，不进入页面组件。`POST /api/auth/register` 不提供。

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

请求体使用 camelCase `BadCaseIngest` 契约：`badCaseId / sessionId / badCaseType / objectName / objectType / title / reason / createdAt` 必填，`objectVersion / badCaseAgentId / triggerLine / metaData / source / sessionSource` 可选。空间身份只从 URL 与服务端凭据解析；body 不接受 `workspaceId` / `workspace_id`，多带会返回 `422`。原型在「上报接入」页展示地址、凭据、额度与请求示例，并支持复制。

### 4.3 空间管理交互

- 全局管理员看到全部空间表：额度使用、空间管理员、成员数、进入/成员/额度操作。
- 空间管理员只看到当前空间的额度与成员，不能创建空间。
- 创建空间时选择初始空间管理员（可多选，包括自己）；一个空间允许多个管理员。
- 成员页可添加成员、改成员/只读；全局管理员可任命空间管理员，空间管理员只能授予管理员以下权限。
- 当前账号不是空间管理员时，提供「把自己设为空间管理员」按钮（对应“管理员可以给自己加为某个空间的管理员”）。

### 4.4 归因 Skill

- 入口：在空间管理的「上报接入」与「鉴权接入」之间打开「归因 Skill」。页头展示当前空间，管理员可以上传、设为生效、下载及删除；成员和只读成员通过深链查看，只有下载操作。切换工作空间时，列表和提示词都跟随当前空间。
- 上传：文件选择器接收 ZIP。包上限为 200 个文件、10 MiB 压缩大小、20 MiB 解压大小，须含唯一的 UTF-8 `SKILL.md`，文件上限 512 KiB。其 frontmatter 的 `name` 是空间内唯一包名。上传成功后新增「未生效」行，并提示管理员可手动设为生效。
- 列表：展示 Skill 名、上传者、文件数、ZIP 大小、生效状态和操作。每个空间有一项「当前生效」。平台默认包 `attribute-badcases` 始终可下载、可在未生效时重新启用。自定义包显示「删除」，确认框在删除当前项前提示会立即回退至平台默认包。
- 生效提示词：列表下方展示当前生效包名及 `SKILL.md` 原文，以只读纯文本呈现，跟随启用和回退同步更新。生效状态用于空间包配置。生产 Run 使用通过 Golden 质量门禁并在启动时固化的 registry revision。
- 反馈：读取列表时展示骨架屏，读取失败时提供重试。上传、启用与删除在请求期间禁用写操作。操作失败时在页内提示原因，包括格式错误、超限、重名、包不存在及权限不足。
- 原型验收：在[归因 Skill 演示页](harness-evolution.html?u=admin&page=admin&tab=attribution-skills)下载并上传示例 ZIP，确认列表增加一行，当前提示词保持不变。设为生效后检查提示词，再取消一次删除并确认一次删除，检查是否回退至默认包。切换到 Agent 平台检查空间隔离，用[只读演示](harness-evolution.html?u=wanghao&ws=ws-harness&page=admin&tab=attribution-skills)确认只有查看和下载。原型只接受页面提供的示例 ZIP，变更保存在当前页面内存中，刷新恢复样例数据。生产交互依据 [#374](https://github.com/Shadow-Azure/harness-evolution/issues/374)。

## 5. 工作空间总览

### 5.1 指标与筛选

- 顶部 `statstrip`：bad case 总数、自身存在问题、发现前置步骤问题、关联 Session、bad case 上报来源数、额度使用。
- 时间：近 7 / 30 / 90 天或自定义区间；粒度：日 / 周 / 月。选择近 7 天时默认切到日粒度，30/90 天默认周粒度；用户仍可手动改粒度。
- `bad case 上报来源` 多选；不选表示全部，多选表示并集。来源 chip 可逐项移除。
- 图表按时间桶堆叠自身存在问题（蓝）/ 发现前置步骤问题（紫）；下方按来源列出总量与两类占比，并可展开 `bad case 上报来源 × 时间` 明细矩阵。
- 列表筛选独立于图表：时间段、`bad case 上报来源`、`bad_case_type` 都可为空；空值不限制。分页 8 条/页。

### 5.1.1 页面文案

- `self` 展示为「自身存在问题」。
- `discovery` 展示为「发现前置步骤问题」。
- `object_name` 展示为「bad case 上报来源」。
- 内部字段仍保留原名，展示层统一映射。

### 5.2 下钻

点击列表行：

```text
?page=session&view=errors&ws=<ws>&sid=<session>&case=<badCase>&dtab=desc
```

进入当前空间的 Session 错误详情，并选中该 bad case 的「问题描述」Tab。左侧自动展开该 bad case 的归因列表。

### 5.3 双视角：bad case / 进化对象

- 总览标题下方用二级 Tab 切换「bad case 总览」「进化对象总览」，共享空间与时间上下文。
- 布局沿用 bad case 总览：左侧趋势图 + 下方不同进化对象的潜在 bad case 分布，右侧原「空间额度」位置改为分页的进化对象列表，底部仍是潜在 bad case 列表。
- 进化对象总览展示：对象数、关联 Session、潜在 bad case、已分析（是该对象 / 非该对象）、未分析。
- 右侧对象列表保持紧凑，每项只显示对象/版本、关联 Session、潜在 bad case；三种状态的数量与占比统一在图表下方分布中展示。可直接新增、编辑、移除，每页 5 个，超过时分页。
- 趋势图支持多选进化对象、时间范围、粒度，以及多选查看信息（是该对象 / 非该对象 / 未分析）。
- 不同进化对象分布按对象聚合潜在 bad case 数量，柱长按最大值归一，显示是该对象/非该对象/未分析三种状态。
- 列表支持进化对象、上报来源、状态、时间段筛选；已分析记录展示归因报告 ID，可点击跳转归因分析。

## 6. Session 错误查看

- 进入页面只请求当前空间最新 10 个 root Session；标题显示「最新 10 / 总数」，不默认拉全量树。
- 搜索框接收 root session ID，回车精确查询（允许 ID 子串）；命中后左侧替换为该结果并选中。
- 清空输入再回车恢复最新 10 个。
- 未命中时左侧与右侧都显示明确的空态，不保留旧选中。
- 选中 Session 后才加载概览与执行流；只保留「打开错误详情」，不再提供「打开时间线」。
- 执行流默认小窗口 lane DAG（日志行区间、`A1/A1.1` 深度、跨 lane 并发、BC marker、全部 lane 展开、缩放/平移）；结构树保留为切换视图。

## 7. 归因进入自进化

### 7.1 流程状态

```text
选择进化对象 + 版本 + bad case 时间段
  → 找出该空间在时间段内上报了 bad case 的 Session
  → 判断对象版本是否在这些 Session 中出现（出现才关联）
  → 对关联 Session 找对象触发点与所有 bad case 触发点
  → 按潜在策略筛选潜在 bad case
  → 对每个潜在 bad case 生成「对象版本级」归因
  → 对归因后的 bad case 按问题类型聚类，按严重程度降序排序
  → 按聚类结果逐轮打 patch / 评测 / 接纳
  → 测试集终评
```

原型把 Session 关联与潜在 bad case 拆成向导第 2、3 步：第 2 步只看关联 Session（分页），第 3 步只看潜在 bad case（分页），第 4 步才做归因预览与启动。

运行详情的聚类步骤按严重程度降序展示簇卡片；每簇有标题与聚类问题描述，可折叠，展开后在簇下方列出全部来源 bad case（ID、标题、object_name、类型、触发点、上报时间），默认展开第一簇。

实现上，关联表只列对象出现过的 Session；未出现的 Session 只在统计中计为“跳过”，不进入表格。潜在 bad case 默认策略：

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

### 7.4 启动版本输入与校验

启动向导第 1 步的「版本」是输入优先的组合框，不是只能选的 tag 下拉：

- **建议列表**：当前 target 的 `defaultRef` 与 tag 列表；`defaultRef` 不在 tag 列表时仍以「基线」建议出现。
- **默认值**：`defaultRef`，缺省时取第一个 tag。
- **直接输入**：接受 tag、分支名和 commit SHA；输入值就是提交的 `targetVersion`，不要求命中建议列表。
- **校验时机**：点「下一步：关联 Session」和最终「启动自进化」时执行。先校验 git ref 格式（非空、≤96 字符、无空白/`..`/`@{`/`~^:?*[` 等非法字符，且不以 `-`、`/`、`.` 或 `.lock` 结尾）；失败停在第 1 步并显示字段错误。服务端再解析该 ref 下的 `SKILL.md` / `AGENT.md` 并计算 body hash；解析失败返回第 1 步，不回退到 tag 猜测。
- **身份不变**：版本身份仍是 body hash；tag 只是建议和显示值，不改变匹配与缓存语义。

## 8. 错误详情：一个 bad case × 多条归因

- 左栏从 V1 的错误卡改为可折叠的 bad case 组：
  - 父行：`#no`、bad case ID、标题、object_name、self/discovery、归因数。
  - 展开后：按「进化对象 · 版本」列出归因子项（结论、时间、缓存标记），每页 2 条。
- 点击父行 → 问题描述 Tab；点击归因子项 → 归因分析 Tab，并定位到该条归因。
- 问题描述正文按 Markdown 渲染：段落、列表、行内代码、强调、链接、代码块有层级，单换行保留；禁用原始 HTML、外链加固，Markdown 图片降级为 alt 文本；无 Markdown 语法的纯文本仍是普通段落。
- 右栏保留执行流；选中 bad case 时保留全部并发分支，只高亮对应 BC 和定位线，不过滤其它分支和 lane。
- 归因分析展示：结论（可归因 / 非该对象问题）、分类、对象版本、运行 ID、时间、缓存来源、置信度、策略、对象触发点 vs bad case 触发点、推导过程与结论边界。
- 运行详情第 4 步的对象归因表不再重复「结论 / 分类」，改为：来源 bad case、归因报告 ID、分类、问题现象/描述、结果来源、置信度；归因对象版本保留在第 4 步标题中，不在表格内重复。
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
/workspaces/:workspaceId/admin?tab=attribution-skills
```

迁移期旧 `/sessions/**`、`/evolution/**` 按“用户最近访问且有权限的空间”重定向；解析失败进入空间选择页，不静默选择第一个空间。旧 `issue/report` 深链先解析到 bad case 再重定向；一旦历史数据允许多归属，停止自动猜测。

## 11. 原型验收与边界

- 已验证：登录 / 空间切换 / 总览筛选与分页 / 总览下钻 / 最新 10 条与空态 / 错误详情多归因折叠与分页 / 向导四步与缓存 / 空间创建与额度调整 / 成员添加与角色 / 上报接入 / 鉴权接入。
- 渲染：headless Chrome 1440/1600 宽，无 console error；执行流依赖 CDN 的 React / React Flow。
- 未实现：真实鉴权、持久化、统计聚合 SQL、上报写入事务、归因算法、SSO 回调、跨空间 403/404 的服务端测试。前端权限仅是体验护栏。
