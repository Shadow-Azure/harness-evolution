# M17 对象卡版本显示与 V2 原型对齐

[English](m17-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m17
title: M17 对象卡版本显示与 V2 原型对齐
status: active
github:
  number: 25
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/25
```

## 目标

单个进化对象分析的版本行与版本多选按 V2 原型显示可读的 git ref 与短 commit，而不是内容 digest；同一版本的 ref 与 digest 证据合并为一行，只有 digest 证据的历史版本保留 digest 兜底。

## 范围

对象总览的版本发现与聚合、run 版本证据回填、目标详情契约、总览对象卡与侧栏的版本展示、对应单测与浏览器 E2E、Agent Note 和流程文件。

## 验收

- 版本来自 tag、分支或 commit id 时，版本行与多选显示该 ref；有 run 记录时同时显示短 commit。
- 同一版本被同时记录为 ref 与 digest 时只出现一行，优先 ref，不重复计数。
- 只有 digest 证据的历史版本仍可见、不丢计数；版本筛选、Session 关联、归因与缓存语义不变。
- 修复前后截图与 V2 原型同区域可比，PR 描述含 Before / After 证据。

## 非目标

不改变 PotentialMatcher、归因缓存键与 Session 关联口径；不为只有 digest 的历史版本反查 git ref；不重排对象卡其它区块，也不新增版本筛选交互。
