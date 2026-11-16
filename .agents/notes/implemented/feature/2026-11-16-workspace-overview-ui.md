# Agent Note: 工作空间总览页的 URL 契约、独立区块与默认落地

Status: implemented

[English](2026-11-16-workspace-overview-ui.en.md) | 中文

## Problem

m8-03 提供了 summary、trend、sources 与分页 bad-case 列表四个只读端点，但总览页要同时解决四件事：筛选条件必须可分享、可刷新恢复；趋势与列表必须互不阻塞（任何一个慢或失败都不能让整页变成 spinner）；bad case ID 要能直接落到错误详情的问题描述 Tab；以及 `/workspaces/:wid` 必须从 Session 列表改落到总览，同时不能让旧 Session 深链改道。此外 m8-03 只给「对象总量」与「时间桶总量」两组聚合，没有对象 × 桶的交叉计数，原型里的 SourceMatrix 因此没有诚实的数据来源。

## Decision

- URL 是筛选的唯一事实源：`tab=cases`、`range=7|30|90|custom`、`from`/`to`（仅 `range=custom`）、`grain=day|week|month`、`objects`（逗号分隔、去重、空 = 全部、多选取并集）、`page`（仅 >1 时写）、`type`（`self|discovery`）。默认 `range=90`、`grain=week`；非法、越界或不可排版的日期回落默认；页面在挂载时把缺失或非规范 URL 一次性 `replace` 成规范形式，所以刷新与分享都恢复同一组筛选。
- 自定义窗口用 `from`/`to` 表达，不发送 `range`；从「自定义」进入时用当前 summary 窗口预填起止日期；点击趋势桶直接把列表窗口切成该桶的闭区间（日桶当天、周桶周一到周日、月桶整月），并回到第 1 页。桶窗口按服务端实际粒度 `grainEffective` 换算，所以请求日粒度被服务端降级为周时，副标题与桶点击都按周处理。
- 筛选变更走 `router.replace`（不污染历史），翻页走 `router.push`；`objects` 的增删、chip 移除、清空筛选都只改 URL，组件不持有第二份筛选状态。
- `type` 是列表的额外筛选键：原型统计条不响应点击，但 08 §6.2 要求「自身存在问题 / 发现前置步骤问题」指标写入列表筛选并滚动到列表，因此两格是按钮，点击写入 `type`，再点一次取消；「来源数」格本身是聚焦来源多选的入口，不再另设独立按钮。
- 切换空间由空间选择器在导航时写入默认总览查询（`tab=cases&range=90&grain=week`），新空间的首次请求因此不会带上一空间的 `range`/`objects`/`type`；页面 watcher 只做 URL 规范化，不按 `wid` 变化重置筛选，所以浏览器后退能恢复上一空间自己的 URL 与列表。
- 统计条、趋势 + 来源分布、列表是三个独立请求区块：各自骨架、空态、区块级 `ErrorState` 与重试；空态文案区分「空间没有 bad case」与「当前筛选没有命中」，后者给清除入口。越界 `page` 在列表返回 `total` 后夹到最后一个有效页，夹取前用独立的「页码超出范围」状态保留分页入口；404 `WORKSPACE_NOT_FOUND` 整页跳 `/workspaces?reason=forbidden`；区块错误显示 `ApiError.code` 真码而不是页面自造码。
- 趋势用自研 SVG：`chartGeometry.ts` 只做纯几何（1/2/5×10ⁿ 刻度、`min(28, slot*0.6)` 柱宽、堆叠高度、占比），DOM 负责轴标签与 tooltip；`0` 值不画柱但仍保留可点击/可聚焦的桶区域；>60 桶进入 dense 模式并稀疏标签。
- 顶栏 `.tn-item` 不换行；「总览」副标题用原型措辞「bad case 趋势」，`tn-note` 与副标题在窄屏隐藏，使 1440px 下四项保持单行，窄屏导航在自身容器内横向滚动。
- bad case ID 是唯一行内链接，`target="_blank" rel="noopener"` 指向 `/workspaces/:wid/sessions/:sid/errors?case=<id>&tab=desc`；整行不可点。
- 只发布 bad case Tab：`tab=targets` 规范化回 `tab=cases` 并给出 M11 提示；「进化对象总览」按钮保持可见但 `disabled`，不用隐藏控件冒充未实现能力。
- 默认落地改为总览：`DEFAULT_WORKSPACE_PATH` 改为 `overview`，`/workspaces/:wid` 重定向 `overview`，登录与空间选择共用 `defaultLandingPath`；`legacyWorkspaceTarget` 对 `/sessions`、`/errors` 仍映射 Session 列表，只有 `/` 进入总览；`switchableWorkspaceChild` 切空间时仍保留 `/sessions`。总览路由懒加载，顶栏在 Sessions 之前新增「总览」。
- SourceMatrix 不做：m8-03 没有 per-object × bucket 字段，用当前页 8 行拼矩阵会得出错误总数。来源分布用 top 6 + 「其余 N 个来源」聚合行，可展开查看全部。
- 契约类型从 m8-03 生成的 `components["schemas"]` 经 `packages/contracts/src/overview.ts` 再导出；本 issue 不新增或修改 HTTP 接口。
- 页面没有任何写操作：筛选、图表、列表都是只读，viewer 与管理员看到同一套视图。

## Alternatives considered

- **用当前页 bad case 在前端拼对象 × 桶矩阵**：拒绝。列表每页只有 8 行，跨桶计数会系统性偏小且随翻页变化；这是伪造数据，不是降级。
- **保留 sessions 作为默认落地，只加导航项**：拒绝。issue 明确要求总览成为空间根页面；旧 `/sessions` 链接另行保留映射即可。
- **引入第三方图表库**：拒绝。趋势只是堆叠柱 + 轴 + tooltip，自研 SVG 可复用现有 token、不增加首屏 bundle，也避免把图表库主题与 Element Plus 主题叠加。
- **`type` 过滤只放组件内、不写 URL**：拒绝。刷新或分享后列表与图表口径会悄悄不一致；URL 单源是这一页最重要的可验证契约。
- **在页面 watcher 里按 `wid` 重置筛选**：拒绝。页面 watcher 分不清「选择器切换」与「浏览器后退」，两者都会重写 URL：后退时上一空间的筛选被默认值覆盖，历史条目也被就地改写。把重置放到空间选择器的导航上，页面 watcher 只规范化 URL，才能同时满足「新空间首请求无旧筛选」与「后退恢复原查询」。
- **`tab=targets` 静默回到 cases 或直接隐藏 Tab**：拒绝。静默会让用户以为链接失效；隐藏又无法表达 M11 的边界。保留禁用入口 + 一次性提示更诚实。
- **保留原型右侧「空间额度 / 上报接入 / 当前空间」侧栏**：拒绝。额度已在统计条第 6 格，上报与成员信息属于空间管理页；本 issue 不复制管理能力，也不引入第二处配额数字。
- **整页 spinner 或串行加载四个请求**：拒绝。矩阵与列表数据量差异大，任一失败都会拖垮整页；按区块独立请求才能满足「图表与列表互不阻塞」的验收。

## Consequences

- URL 比 issue 列出的键多一个 `type`；它只由统计条写入，缺省不出现。`objects` 中的未知来源名会原样传给 API（服务端自然过滤为空），切换空间时选择器以默认查询导航，因此不会跨空间泄漏；浏览器后退/前进恢复各空间自己的筛选。
- 旧 `/errors` 与 `/sessions` 链接仍落到 Session 列表；只有应用根 `/` 改到总览。若有外部书签指向 `/workspaces/:wid`（无子路径），行为从 Session 列表变为总览，这是本 issue 的预期变更。
- SourceMatrix 与「对象 × 时间桶」明细是明确欠账：需要 m8-03 增加按对象分桶的计数（或一个对象筛选下的 trend 复用），不能由前端拼装。
- 递延的 targets Tab 内容仍缺 F25；在 m11 落地前，任何 `tab=targets` 链接都只会看到 cases 与提示。
- 趋势密集模式在 >60 桶时压缩标签；60 桶以内保持完整标签。所有桶无论是否有数据都保留可点击区域，390px 仍靠页面级无横向溢出断言守卫，窄屏顶栏在自身容器内滚动。
- 越界 `page` 先显示「第 N 页没有数据」与分页条，随后被夹到最后一个有效页；404 `WORKSPACE_NOT_FOUND` 不再渲染成四个永远重试失败的区块，而是整页回到空间选择器。
- E2E 用独立空间 + 凭证写入 11 条「今天/昨天」的 bad case，断言不依赖 fixture 的固定历史日期；默认落地用例只在 ws-default 上验证结构，不断言具体计数。
- 页面没有任何写入口，viewer 角色不需要额外按钮级降级；后续若加入上报或启动入口，需要同时补只读态。
