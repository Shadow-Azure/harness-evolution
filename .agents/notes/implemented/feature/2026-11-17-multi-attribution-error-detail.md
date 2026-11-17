# Agent Note: 折叠式多归因错误详情

Status: implemented

[English](2026-11-17-multi-attribution-error-detail.en.md) | 中文

## Problem

m11-01 让一个 bad case 可以按「进化对象 · 版本」读取多条归因，但错误详情仍是 V1 的单卡片左栏加单条 probe 分析：同一 case 的多条结论无法同时可见，刷新只能恢复 case 和 tab，没有 `at` 定位；「非该对象问题」与「尚未归因」也共用旧文案，用户会把一条非目标结论误读成未分析。空归因 case 只能在自进化页重新选对象，错误详情没有就地启动入口。若整页照抄原型把所有归因一次拉回，会绕开服务端分页；若继续用 `/analysis` 和 `/probes/{id}`，则又把 probe 抬成产品概念，与 m11-01 的契约方向相反。

## Decision

- 左栏改为 `CaseGroup` + `AttributionItem`：父行给 `BC<no>`、短 bad case ID、标题、self/discovery、object_name 与归因数，子项按服务端 `pageSize=2` 分页；展开态和页码是组件本地状态，选中 case 由 URL 驱动并自动展开，筛选 chips 只过滤列表，不改变展开态与右侧详情。
- 深链固定为 `case`、`tab`、`at`，`at` 只允许出现在归因 tab 且必须同时有 `case`；`at` 命中用它，否则回落到 `obj`（原型兼容）同名对象，再落到第一条。解析仍在 `router/deepLink.ts` 统一校验，页面只消费规范化状态。打开`at`时保留 URL，不把解析出的第一条偷偷写回地址栏。
- 详情导航需要 `N / total` 与前后切换，因此选中 case 时另取一次 `pageSize=50` 的归因全集（超过 50 行按 `total` 有界补页），用于定位 `at` 和下一条；左栏分页仍由服务端 2 条一页，两者不共享缓存键，避免把「当前页」和「全集」混成一个语义。
- `AttributionReport` 按 08 §7.3 的固定顺序渲染：结论横幅、对象·版本/来源 run/时间/缓存、置信度与策略、触发点对照、结论说明、Markdown 推导与固定证据缺口、结论边界。`reason` 只作纯文本，`reasoning` 走已有安全 Markdown 管线；非该对象问题不显示分类 chip。
- 无归因时显示「尚未归因」、说明归因在自进化中生成，并只在 `space_admin`/`global_admin` 时提供「以该 bad case 启动自进化」；向导以浮窗挂在本页并预填 `focusCaseId`，启动成功再跳到运行详情，开启向导本身不离开错误详情。
- 所有归因 query key 以 `["ws", workspaceId, "case", badCaseId, ...]` 开头；切换空间时 reset 展开/页码/筛选/向导，旧空间的归因与详情不会复用。
- `ProblemDescription` 用「已生成 N 条归因 · X 可归因 / Y 非该对象 →」取代旧单 probe 报告链接和五态 chip；旧 `analysis` 只保留在列表与兼容 API，错误详情不再请求 `/analysis` 或 `/probes`。

## Alternatives considered

- **左栏也一次拉回全部归因、前端分页**：实现更简单，但违背 `pageSize=2` 的服务端分页契约，case 多了会放大首屏请求；拒绝，只让详情导航申请全集。
- **把 `at` 直接当详情请求、列表页找不到就 404**：刷新一个不在当前页的 `at` 会误报不存在；拒绝，先用全集定位再取详情。
- **继续复用 `BadCaseAnalysis` 与 `ProbeReport`**：把「对象级归因集合」压回单条 probe，无法表达 non_target 和缓存/触发点；拒绝，错误详情改用 m11-01 的 attribution 契约。
- **空归因 CTA 跳去自进化页**：原型在错误详情内就地启动，离开页面会丢失当前 case 与筛选上下文；拒绝，浮窗挂在本页。
- **默认自动选中第一条 case**：原型这样，但现有错误详情以「全部 bad case + 空详情」为默认，直接改会破坏深链和键盘路径；拒绝，保留全量空态，选中由 URL 决定。
- **客户端按字符串拼 `at` 深链**：会绕过 `obj` 兼容和非法值校验；拒绝，统一走 `badCaseDeepLink` 与 `parseSessionDeepLink`。

## Consequences

- 选中 case 会多发一次 50 条的归因列表请求；总量以 `total` 为界，只有超过 50 行才继续补页，且只在错误详情停留期间发生。
- 左栏页码会跟随详情 `at` 自动切到选中归因所在页；页码只由选中归因驱动，不写入 URL，刷新与复制链接仍以 `at` 为准。
- 归因结论本身仍只由自进化写入；错误详情只读，不做手动归因，也不修改 bad case。
- 执行流布局、选中态保留全部并发分支仍归 m11-07；本页当前仍按选中 case 过滤执行流。
- V1 `/analysis`、`/probes/{id}` 与 `BadCase.analysis` 保留给列表和兼容期页面，m11-06 退役时需同时移除错误详情的旧读法。
