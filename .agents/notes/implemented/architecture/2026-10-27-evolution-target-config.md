# Agent Note: 自进化对象配置与目录边界

Status: implemented

[English](2026-10-27-evolution-target-config.en.md) | 中文

## Problem

自进化对象配置同时承载凭据敏感的远端地址、可越界的子目录、需要实时反馈的 git ref，以及只读 catalog 视图。若把校验散落在 HTTP 路由，用 shell 拼 git 命令，或为了模型清单重新解析 payload，就会出现安全边界漂移、不可测试的远端调用和重复数据源。

## Decision

`service/evolution/targets.py` 独占对象名、POSIX 子目录、ref 与 HTTPS/SSH/SCP remote 的规范化，保存和版本读取都通过注入的 `GitRemote` 验证。生产 adapter 位于 `third_party_api/git`，只用参数数组调用 `git ls-remote`，超时会终止并回收子进程，所有失败收敛为不含 stderr、凭据或路径的 `REPO_INVALID`。配置列表保留启用和停用对象；只有 catalog 过滤 `enabled=true`。目标写操作按 HTTP 方法与路径要求 admin，读操作只要求登录。模型 catalog 只聚合归一化 `agents.model`，不读取 JSONL payload。

## Alternatives considered

在路由层复制 URL/path/ref 校验会让其他调用者绕过规则；用 shell 拼接 remote/ref 会引入命令注入并难以回收子进程；在目标列表提前过滤停用项会让配置页无法重新启用；从 payload 实时聚合模型会复制归一化数据源并扩大读取成本。

## Consequences

target 保存和版本列表受 git 远端时延约束，并有固定超时；本切片不 clone 或缓存仓库。配置页读取完整 target 列表，未来向导只使用 enabled catalog。所有 git 行为由一个注入缝测试，未来缓存或批量读取只需替换 adapter，不改 API、catalog schema 或数据库表。
