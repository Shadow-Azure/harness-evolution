# V2 原型 UI 可读性与交互优化

[English](m6-ui-prototype-v2-ui-polish.en.md) | 中文

```yaml flow
kind: issue
id: m6-24
milestone: m6
depends: []
priority: P1
status: in-progress
scope:
  - plans/ui-prototype-v2/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 204
  url: https://github.com/Shadow-Azure/harness-evolution/issues/204
```

## 背景

V2 原型承载多工作空间下的总览、Session 查看、自进化与空间管理。真实浏览器审阅发现顶栏导航在 1408px 下从词中间折行，家族树滚轮会缩放画布而不是滚动页面，浅灰辅助文字对比度不足，Session 页底部有 44px 空带，详情头按钮被长会话 ID 挤到第二行，来源汇总数字溢出卡片，进化对象右卡分页悬在卡片中段。这些问题直接影响原型评审时对信息层级和交互手势的判断。

## 目标

- 顶栏四个入口在桌面宽度下保持单行，主标题与副标题不折行。
- 家族树普通滚轮滚动页面，缩放交给右下角控件，避免误把图缩到不可读。
- 辅助文字与图表刻度达到可读对比度，关键数字不再被卡片边缘裁切。
- Session 视图填满顶栏以下视口，详情操作按钮与标题保持同一视觉分组。
- 进化对象侧卡的分页固定在卡片底部，列表在剩余高度内滚动。

## 设计依据

- [03-frontend-architecture.md](../../../plans/fullstack-design/03-frontend-architecture.md)：前端页面壳、顶栏与视图切换的归属。
- [02-features.md](../../../plans/fullstack-design/02-features.md)：总览、Session 错误查看与自进化的顶层信息架构。
- [design-v2.md](../../../plans/ui-prototype-v2/design-v2.md)：V2 原型的多工作空间与进化对象叙事。

## 实现内容

- 顶栏导航改为不可收缩单行，收紧水平内边距，并在 1340px 以下隐藏副标题。
- 两个 React Flow 实例关闭滚轮缩放、放开页面滚动，`minZoom` 提升到 0.5，图例手势文案同步。
- `--text-faint` 提升对比度，趋势图刻度与对象汇总数字增大到 10–10.5px。
- Session 壳层高度改为 `calc(100vh - 56px)`，详情头首列可收缩、会话 ID 超长省略。
- 总览来源汇总第三列扩到 120px；进化对象侧卡改为纵向 flex，分页贴底。
- 修复前后截图落在 `plans/ui-prototype-v2/_ui-review/round1/`，供逐轮对照。
- 第二轮补齐交互状态：页面与工作空间写入 URL；工作空间/用户/同步浮层支持外部点击、Esc 与互斥关闭；家族树与错误执行流画布按短视口压缩，图例置顶；切换空间关闭旧详情；时间线仅对有真实数据的 Session 渲染。
- 第二轮截图落在 `plans/ui-prototype-v2/_ui-review/round2/`。

## 实施步骤

1. 用本地静态服务打开 V2 原型，采集总览、进化对象、Session 与空间管理的整页基线。
2. 分析 subagent 输出按优先级排序的 UI 问题与截图证据。
3. 修复 subagent 按最小 diff 修改 `harness-evolution.html`，逐条回看现象。
4. 用浏览器复测导航单行、滚轮行为、底部空带、按钮行与数字溢出，并保存 before/after 截图。
5. 重复分析—修复循环，直到没有新的高置信度问题，再跑流程与文档门禁。

## 依赖与交付边界

- 依赖：无
- 交付边界：只改 V2 原型 HTML 与审阅截图；生产前端 `apps/web` 不在本 issue。

## 独立验证

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory plans/ui-prototype-v2
```

- 打开 `http://127.0.0.1:8765/harness-evolution.html?u=admin&page=overview`、`?tab=targets`、`?page=session`。
- 顶栏四个入口各只占一行；家族树内滚轮让外层滚动而 viewport transform 不变；Session 页底部无灰带；总览来源汇总最后一位数字完整可见。

```sh
pnpm verify:flow; pnpm lint:docs
```

- 全绿。

## 验收标准

- 1408px 视口下四个导航项均为单行，1340px 以下副标题隐藏且无横向溢出。
- 家族树与错误详情执行流中，普通滚轮滚动页面，右下角控件仍可缩放/适应。
- `--text-faint` 在白底与页面底色上的对比度均不低于 4.5:1；图表日期、刻度与对象计数清晰可读。
- Session 视图底边与视口底边对齐；详情操作按钮不再掉到第二行。
- 总览来源汇总与进化对象侧卡无文字裁切，分页贴卡片底部。
- 刷新后仍停留在当前页面与工作空间；切换工作空间后不再显示上一空间的错误详情；时间线标题与当前 Session 一致。
- 工作空间、用户、同步浮层在外部点击、Esc、切页后关闭且同一时刻只开一个；短视口下家族树图例与问题详情首屏可见。

## 门禁与 CI

- `pnpm verify:flow`：issue 三件套、状态机与 scope 覆盖。
- `pnpm lint:docs`：新增 Agent Note 双语配对与文档格式。
- 原型为静态 HTML，不触发 `apps/web` 构建与 E2E；手工截图作为验收证据。

## 非目标

- 不改生产 Vue 应用的路由、组件或样式。
- 不改后端接口、数据模型与额度校验逻辑。
- 不在本轮重做移动端布局；移动端仅保持不溢出。
