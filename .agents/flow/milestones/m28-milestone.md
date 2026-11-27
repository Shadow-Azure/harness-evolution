# M28 同仓多成员进化对象

[English](m28-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m28
title: M28 同仓多成员进化对象
status: planned
github:
  number: 38
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/38
```

## 目标

- 进化对象从单对象升级为「一条配置 + 同仓多个成员」：仓库、基线、测试工程、主指标与归因 Skill 共享，成员各自冻结定义、各自关联 bad case。
- 一次 run 以配置为单位进化整组：成员快照、成员目录并集的 patch 范围、一次提交全部成员资产的评测。
- 旧列保留一版写首个成员，历史配置回填为单成员，V1 读端点与历史 run 不变。

## 范围

`apps/api` 的模型、迁移、仓储、配置、绑定、启动、匹配、patch、评测与投影；`packages/contracts`；`apps/web` 的配置、向导、run 详情与总览；`tests/e2e`；`plans/fullstack-design/18-multi-member-evolution-target.md`；原型与流程文件。

## 验收

- 一条配置保存同仓两个成员；重复成员、跨配置重复成员与缺失测试工程被拒绝。
- 向导单选配置；run 详情展示成员、共享测试工程与改动范围；第 2/3 步显示命中成员。
- 绑定归因按配置一批、成员并集；单成员缓存键逐字兼容。
- 评测一次提交全部成员资产；成员目录缺失时 prepare 即失败。
- 历史配置与 run 兼容；门禁与 PR 截图齐备。

## 非目标

不改评测平台资产契约；不支持跨仓成员；不允许同一成员属于多条配置；不改归因 Skill 协议、V1 六步映射与"每成员独立评测"。
