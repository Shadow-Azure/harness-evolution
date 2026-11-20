# Agent Note: 空间归因 Skill 包与执行 revision 分层管理

Status: implemented

[English](2026-11-18-attribution-skill-package-admin.en.md) | 中文

## Problem

空间管理员需要跨对象复用含多个文件的 Skill，也需要从报告追溯每个 Badcase 的分析依据。

## Decision

空间独立存放上传包。对象配置在同一事务中写入单一绑定与后台任务意图。后台固定对象版本及 Skill 快照。启动自进化时可复用已有报告，也可选包单次重算。历史报告保留产出时的 Skill 身份。

## Alternatives considered

空间级生效会影响无关对象。按全部历史报告计数会在重算后重复统计同一 Badcase。先按对象版本和 Badcase 取最新报告，再按 Skill 分组。

## Consequences

资源库可以列出并保护已绑定包。后台批次独立于下游聚类，重试时根据批次标识跳过已完成的 Badcase。
