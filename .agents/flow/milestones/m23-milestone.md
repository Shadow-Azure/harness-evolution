# M23 Session 页低内容填充与原型对齐

[English](m23-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m23
title: M23 Session 页低内容填充与原型对齐
status: active
github:
  number: 33
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/33
```

## 目标

让 Session 浏览器在生产上报的低内容场景下保持与 V2 原型一致的视口行为：页面壳层固定为窗口高度，左右两栏各自撑满并内部滚动，文档本身不滚动；右栏在内容不足一屏时由最后一个区块填满剩余高度，执行流区域的加载、失败与缺失状态都保留与原型同量级的全高占位，不再在视口底部留下整条页面背景空白。

## 范围

`apps/web/src/pages/sessions/` 的壳层与右栏容器、`tests/e2e/m3-session-browser.test.mjs` 的低内容回归、`plans/fullstack-design/08-frontend-implementation.md` §5、V2 原型同区域的既有规则，以及对应的流程文件与 Agent Note。后续 Session 页布局与 V2 原型的同源偏差沿用本 milestone。

## 验收

1500×837 视口、1 轮 / 1 消息 / 0 工具 / 0 子 Agent / 1 case 的合成 Session：文档无窗口级滚动条；`.session-browser`、`.sidebar`、`.overview` 底边贴合视口；右栏滚到底后最后内容距视口底不超过 24px；1500×1100 视口下问题列表占满剩余高度且同样满足 24px 间距；390×844 移动端单列布局与执行流加载 / 失败 / 缺失态无回归；不改 API 契约、Session 数据与问题卡内容结构；PR 描述含生产 Before 截图、修复后 After 截图与 V2 原型同区域对照。

## 非目标

不改 Session 列表 / 概览的数据口径与查询参数；不为填满而拉伸问题卡正文或重排卡片内容；不把全局 `body` 滚动一刀切掉以影响总览、自进化等需要文档滚动的页面；不把生产 Session 内容或截图提交到仓库。
