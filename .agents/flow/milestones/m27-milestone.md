# M27 项目介绍与 README 展示

[English](m27-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m27
title: M27 项目介绍与 README 展示
status: active
github:
  number: 37
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/37
```

## 目标

把根 README 从“M1 工程骨架推进中”的旧状态页改成面向新读者的项目介绍：一句话定位、核心能力、一张关键界面截图、快速开始与文档入口；中英两侧成对，截图只使用本地合成 fixtures。

## 范围

`README.md`、`README.en.md`、`README.i18n.yaml`、`docs/assets/readme/**`、`scripts/doc-budgets.manifest.json`、`.agents/notes/**` 与 `.agents/flow/**` 的同步。

## 验收

- README 展示当前 V2 能力，不再以 M1 状态与生产部署步骤为主体。
- 恰好一张产品截图，来自本地 fixtures 演示数据；不含生产 Session 内容、凭据或真实用户数据。
- 中英两侧结构镜像、配对记录重录，文档与流程门禁通过；PR 说明预算调整理由。

## 非目标

不改应用 UI 与功能；不移除 `docs/` 的部署、架构与开发文档；不新增多张截图或视频；不把生产截图写入仓库。
