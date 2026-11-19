# M15 生产环境 Claude Code 运维

[English](m15-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m15
title: M15 生产环境 Claude Code 运维
status: active
github:
  number: 23
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/23
```

## 目标

让生产部署流水线在发布前自动安装并配置 Claude Code：安装包在 GitHub Actions runner 侧获取并校验，服务器以 deploy 用户解包到 `/opt/harness/shared/claude-code`，模型、端点和密钥经 GitHub Secrets 写入 `~/.claude`。不依赖服务器访问 `claude.ai`，不引入 root 或 Node.js。

## 范围

`deploy/` 的安装与配置脚本、`.github/workflows/deploy.yml` 的安装步骤、`docs/deployment.*` 与部署手册、对应 Agent Note 和流程文件；模型提供商先支持 MiniMax 国内版 Anthropic 兼容端点。

## 验收

三个 Claude Code Secret 配置后，一次正常 `Deploy` 即可在服务器得到可执行的 `~/.local/bin/claude`，`claude -p` 能返回模型结果；密钥不出现在仓库、日志、`settings.json` 或 SSH 命令行；Secret 全缺时部署行为与现状一致；安装失败发生在切换 `current` 之前；重跑幂等。

## 非目标

不把 Claude Code 接进 `harness-api`，不做系统级 `/usr/bin` 安装、不扩大 deploy 的 sudo 权限、不引入 Node.js，不启用自动更新，不做多用户共享配置。

## 已知待收敛项

真实 `claude -p` 冒烟需要用户把占位 API key 换成 MiniMax 的真实 key；当前流水线只校验安装与配置结构，不把外部模型可用性作为发布硬门禁。
