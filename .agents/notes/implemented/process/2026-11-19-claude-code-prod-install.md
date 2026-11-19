# Agent Note: 生产环境 Claude Code 安装与模型配置

Status: implemented

[English](2026-11-19-claude-code-prod-install.en.md) | 中文

## Problem

生产 `Deploy` 以 `deploy` 用户经 SSH 发布，免密 sudo 只有 `systemctl restart/start harness-api`，服务器没有 Node.js。需要在发布前提供可用的 Claude Code，并用 GitHub Secrets 配置 MiniMax 模型；同时 `claude.ai/install.sh` 在当前网络被区域拦截，服务器侧直连安装不可靠。

## Decision

安装包在 GitHub Actions runner 侧从官方 apt 仓库解析、下载并按 `Packages` 的 SHA256 校验，服务器只用 `deploy` 用户把 deb 解包到 `/opt/harness/shared/claude-code/<version>`，原子切换 `~/.local/bin/claude`。模型配置写到 `~/.claude`：`settings.json`（600）保存 `model`、可选的 `ANTHROPIC_BASE_URL` 和 `apiKeyHelper`；真实 key 放 `api-key`（600），由 `api-key.sh`（700）读取，不进入 settings。MiniMax 国内版端点 `https://api.minimax.cn/anthropic`、模型 `MiniMax-M3.1-Flash[1m]`，同时按官方文档写 512K 自动压缩窗口（`524288`）、`effort=max` 和 Sonnet/Opus/Haiku 别名；`~/.claude.json` 合并 `hasCompletedOnboarding: true`。三个 Secret 全缺时步骤跳过；只配一部分时失败；安装/配置失败在切换 `current` 前中止。

## Alternatives considered

服务器侧 `curl https://claude.ai/install.sh | bash`：当前网络被区域拦截，且把安装时网络风险带进发布。`npm install -g @anthropic-ai/claude-code`：需要额外的 Node.js 运行时与更大的攻击面。用官方 apt 源做系统级安装：需要给 `deploy` 扩大 sudo，违背现有最小权限。把 key 直接写进 `settings.json` 的 `env`：会被 Claude Code 启动的 Bash 子进程继承；改用 `apiKeyHelper`。把 Claude Code 接进 `harness-api`：超出本 issue 的运维边界，另立 issue。

## Consequences

首次安装或换版本时 runner 上传约 128MB deb，服务器保留当前和上一个版本（约 560MB）；同版本重跑只重写配置。真实 `claude -p` 需要用户把占位 key 换成 MiniMax 真实 key，流水线只校验安装与配置结构。MiniMax 的额外环境变量按 provider 判断写入，换 provider 时需调整 `build_settings` 的分支。自动更新关闭，版本由 `CLAUDE_CODE_VERSION` Variable 或 stable 最新决定。
