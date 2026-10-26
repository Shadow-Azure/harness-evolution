# Agent Note: Windows 开发入口的 spawn shell 与 tzdata 声明

Status: implemented

[English](2026-10-26-windows-dev-spawn-shell.en.md) | 中文

## Problem

在 Windows + Node ≥18.20/20.12/22 上，`scripts/dev.mjs` 以无 `shell` 方式 spawn `pnpm.cmd`，触发 Node 对 `.cmd`/`.bat` 的 CVE-2024-27980 加固，`pnpm dev` 抛 `spawn EINVAL`，m2 验收命令"一条命令起前后端"在 Windows 上不可用。同机第二处独立缺陷：`app/utils/time.py` 的 `ZoneInfo("Asia/Shanghai")` 依赖系统 tz 数据库，Windows 的 Python 不自带，任何导入链触及时区模块的命令（含 session 导入流水线）都直接崩溃。两个问题都只在本地开发机暴露，CI（Ubuntu）永远探不到。

## Decision

- `dev.mjs` 仅在 `process.platform === "win32"` 时给 spawn 加 `shell: true`，POSIX 分支保持原样；信号转发与退出码逻辑不动。shell 只用于启动 pnpm shim，不参与参数拼接之外的事。
- `tzdata` 进入 `apps/api` 的运行依赖，版本区间按仓库惯例设上限；Linux/macOS 上它只是 zoneinfo 的回退数据源，行为不变。
- 其他脚本的同类 Windows 入口缺陷（如 `flow-new-issue.mjs` 的 `import.meta.url` 反斜杠比较导致 CLI 静默退出）不在本次范围内，另立 issue 处理。

## Alternatives considered

- 全平台一律 `shell: true`：POSIX 上多一层 shell 只增加引号与信号转发的风险面，收益为零；否，按平台分支。
- 改用 `pnpm.cmd` 的完整路径或 `cmd /c` 前缀：与 `shell: true` 等价但更脆弱，Node 官方修复说明即推荐 shell 或改用 `.exe`；否。
- 在文档里要求 Windows 开发者手动 `pip install tzdata`：把平台差异转嫁给人，新机器必然再踩；否，声明依赖是唯一可靠位置。
- 把 `dev.mjs` 换成 `concurrently` 等进程管理依赖：为两个子进程引第三方依赖不值，现有零依赖方案只差一个 spawn 选项；否。

## Consequences

- Windows 与 POSIX 的 `pnpm dev` 行为对齐，但 Windows 下 Ctrl+C 信号经 shell 中转，极端情况下子进程树的终止依赖 cmd 的默认行为；若未来出现僵尸进程，优先怀疑这一层。
- `tzdata` 成为跨平台依赖后，升级 zoneinfo 数据随 PyPI 版本走，不再跟随操作系统 tzdata 更新；涉及时区规则变更的验证需关注该包版本。
- `flow-new-issue.mjs` 等脚本在 Windows 上仍不可用，维护者在该平台操作流程树需暂时借道模块调用，直到同类 issue 修复。
