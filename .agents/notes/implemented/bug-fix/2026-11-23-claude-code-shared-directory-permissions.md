# Agent Note: Claude Code 共享版本目录的权限修复

Status: implemented

[English](2026-11-23-claude-code-shared-directory-permissions.en.md) | 中文

## Problem

生产 run 的 `cluster.review` 在 spawn 阶段失败（`AgentProviderError: claude-code analysis call could not start`，10ms、0 tokens），而 Deploy 仍为绿色。直接原因是安装器用 `tempfile.mkdtemp()` 解包 deb（默认 0700），再用 `os.replace()` 把它改名为 `/opt/harness/shared/claude-code/<version>`；版本目录保留 0700、属主 deploy，而服务以 `harness` 运行，无法穿越该目录执行 `current/usr/bin/claude`。

既有预检只检查 `prefix`、`config`、settings 和二进制 other 位，漏掉 `<version>`、`usr`、`usr/bin`；Deploy 的 `test -x` 以 deploy 身份执行，deploy 是目录属主，必然通过。更关键的是，重复部署走 `need_install=false` 的仅配置路径，根本不调用 `install_from_deb()`，所以即使修好预检，历史 0700 目录仍然不会被修复。

## Decision

安装器在解包后、改名前把 staging 及 `usr`、`usr/bin` 显式设为 0755；`install_from_deb()` 的 `binary.exists()` 早返回分支和仅配置路径都会调用同一个修复函数，重跑 Deploy 即可修复历史目录。`preflight_shared_access()` 从 `prefix` 到二进制逐级检查 other-exec，并保留 settings 的 other-read；失败发生在 `switch_current` 之前。

Deploy 流水线的预检不再用 `test -x`，而是用 `stat` 复核每一级 other 位。`sudo -u harness` 冒烟只在 deploy 已有该 sudo 权限时执行，否则显式告警并退化为位检查；bootstrap 只授予 deploy 操作 systemctl 的权限，不为本次修复扩大 sudo 面。

## Alternatives considered

- **只改 preflight**：能阻止下一次坏部署，但修不了线上已经存在的 0700 目录，且仅配置路径不会进入安装函数。
- **ACL / root / `LoadCredential`**：需要 root 或 `setfacl` 的一次性手工初始化，违背“优先纯流水线”的要求。
- **0777**：能让 harness 穿越，但扩大了写权限，违背最小权限边界。
- **让服务直接用 deploy 运行**：服务被利用时会连带拿到 deploy 的 home、SSH 部署凭据与发布写权限，不可接受。
- **给 deploy 增加 `sudo -u harness` 权限**：需要 root 改 sudoers，扩大部署账号的横向权限；位检查已能覆盖可移植子集。

## Consequences

- 重跑一次 Deploy 会修复已存在的 0700 版本目录，无需人工 chmod。
- 新的解包不会再产生 0700 版本目录；预检失败会发生在切换 `current` 之前，旧 release 继续服务。
- deploy 无法冒充 harness，流水线只能证明 other 位；harness 视角的 `sudo -u harness ... --version` 仍是独立验收步骤，最终以真实 run 的 `cluster.review` 为准。
- 版本目录、`usr`、`usr/bin` 的权限被统一为 0755，安装器假设 deb 内的 `usr` 结构存在；缺失时显式失败而不是静默跳过。
