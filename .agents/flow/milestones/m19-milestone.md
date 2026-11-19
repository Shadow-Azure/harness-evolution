# M19 生产目标内容单 ref 读取

[English](m19-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m19
title: M19 生产目标内容单 ref 读取
status: planned
github:
  number: 26
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/26
```

## 目标

让生产读取目标仓库单个 ref 时不再执行全量 mirror：按（仓库, ref）缓存浅仓库，只 fetch 目标 ref，读文件时只按需拉取一个 blob。出网代理是后续独立任务，不在本阶段实现。

## 范围

`apps/api/app/third_party_api/git/` 的只读目标内容读取、对应单测、Agent Note 与流程文件。

## 验收

- 冷读一个 tag、分支或完整 commit 只 fetch 该 ref（`--depth 1 --single-branch --filter=blob:none`），不再 `--mirror`；`git show` 只按需拉取目标 blob。
- tag/分支保持最新、完整 SHA 复用缓存；缺失 ref/文件与网络失败保持既有稳定错误分类。
- 旧 mirror 缓存目录不受影响，不需要数据迁移；`read_file` 接口与 20 秒上限不变。

## 非目标

不实现出网代理、Secret 与 Xray 部署（设计见 #394）；不改 `preview/*` 同步契约或异步化、不改前端、不改 run workspace 的 mirror 与 push 模型。
