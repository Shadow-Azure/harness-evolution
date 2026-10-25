# M2 轨迹数据与归一化

[English](m2-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m2
title: M2 轨迹数据与归一化
status: active
github:
  number: 10
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/10
```

## 目标

把 payload 接入、解析、Agent 树和幂等查询做成可验证数据底座。

## 范围

fixtures、本地导入、归一化、树、重放、API 和调度

## 验收

4 个本地会话导入 SQLite 且重复导入零副作用；API 统计与基线一致。

## 非目标

不做会话图 UI 和问题卡。
