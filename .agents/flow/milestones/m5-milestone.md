# M5 自进化闭环

[English](m5-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m5
title: M5 自进化闭环
status: done
github:
  number: 13
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/13
```

## 目标

用占位 patch/评测但真实 git 与持久事件完成自动闭环。

## 范围

状态、配置、运行、六步、事件、git、评测和恢复

## 验收

一条占位 run 自动完成 candidate→push→eval→accept/reject 且可恢复。

## 非目标

不承诺 patch 内容或评分真实。
