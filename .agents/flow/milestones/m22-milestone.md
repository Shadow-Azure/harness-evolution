# M22 归因列表版本显示与 V2 原型对齐

[English](m22-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m22
title: M22 归因列表版本显示与 V2 原型对齐
status: done
github:
  number: 31
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/31
```

## 目标

把 Session 错误查看页左侧归因列表的版本标识从内容 digest 收敛为与总览一致的可读 ref + 短 commit；只有 digest 证据的历史归因保留 digest 兜底，并支持截断、悬停查看完整值、一键复制，避免长版本号挤掉对象名或压住状态标签。原型先落地，生产 API 与前端随后对齐。

## 范围

`plans/ui-prototype-v2/harness-evolution.html`、错误详情归因列表的 API 契约与读取路径、`apps/web/src/pages/errors/**`、对应的契约生成、API / 组件 / E2E 测试、Agent Note、设计文档 08 §7.1 与流程文件。后续归因列表版本展示的同源偏差沿用本 milestone；同页 Session 浏览器壳层的低内容填充与执行流占位也随本 milestone 交付。

## 验收

归因项有 ref 时显示 ref + 短 commit，只有 commit 时显示短 commit，只有 digest 时保留截断的 digest 兜底；长版本号不挤掉对象名、不压住缓存 / 结论标签；悬停截断值可在其上方查看完整值，复制按钮复制完整版本标识；原型改动含同视口 Before / After 截图；归因匹配、缓存键、统计与结论语义不变。

## 非目标

不改变 `digest:<sha256>` 作为匹配与缓存规范键的口径；不为只有 digest 的历史归因反查 git ref；不重排归因列表其它字段或改变分页交互；不把生产 Session 内容或截图提交到仓库。
