# 修复 Windows 开发入口与本地时区依赖

[English](m6-windows-dev-entry.en.md) | 中文

```yaml flow
kind: issue
id: m6-05
milestone: m6
depends: []
priority: P1
status: in-progress
scope:
  - scripts/dev.mjs
  - apps/api/pyproject.toml
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 118
  url: https://github.com/Shadow-Azure/harness-evolution/issues/118
```

## 背景

在 Windows 11 + Node.js 22 的开发机上，`pnpm dev` 直接崩溃：`scripts/dev.mjs` 以 `spawn("pnpm.cmd", …)` 且不带 `shell` 启动子进程，Node 自 CVE-2024-27980 修复起拒绝无 shell 地 spawn `.cmd`/`.bat`，抛 `spawn EINVAL`（Node ≥18.20/20.12/22）。roadmap m2 的验收命令即 `pnpm dev` 起前后端，该入口在 Windows 上完全不可用。同机还暴露第二个独立缺陷：`app/utils/time.py` 依赖 `ZoneInfo("Asia/Shanghai")`，而 Windows 的 Python 没有 zoneinfo 系统数据库，未安装 `tzdata` PyPI 包时任何导入该模块的命令（含 `pnpm data:import:sessions`）直接 `ZoneInfoNotFoundError` 崩溃。此外 `flow-new-issue.mjs` 的 CLI 入口判断 `import.meta.url === \`file://${process.argv[1]}\`` 在 Windows 路径（反斜杠）下恒为 false，脚本静默退出，虽不在本 issue scope 内，但同属 Windows 兼容缺陷，记录于验证段。

## 目标

- `pnpm dev` 在 Windows + Node ≥18.20/20.12/22 上能同时拉起 API 与 Web 子进程，Ctrl+C 一并退出，行为与 POSIX 一致。
- Windows 上无需手动 `pip install tzdata`：`apps/api` 的声明依赖覆盖 zoneinfo 数据，`python -m app`、`python -m app.cli` 全部命令开箱可用。

## 设计依据

- [plans/fullstack-design/10-roadmap-draft.md](../../../plans/fullstack-design/10-roadmap-draft.md)：m2 验收行 "`pnpm dev` 起前后端"——`dev.mjs` 是该验收命令的唯一实现。
- [plans/fullstack-design/04-backend-architecture.md](../../../plans/fullstack-design/04-backend-architecture.md)："时间统一 Asia/Shanghai" 决策依赖 `ZoneInfo("Asia/Shanghai")` 可解析，是 `tzdata` 成为声明依赖的依据。
- 实现与上述章节冲突时，以链接章节为准；本 issue 只补平台兼容，不改变任何已设计行为。

## 实现内容

- `scripts/dev.mjs`：Windows 分支的 spawn 增加 `shell: true`（POSIX 分支维持 `spawn("pnpm", …)` 不变），使 `.cmd` shim 经 shell 启动；信号转发与退出码逻辑不动。
- `apps/api/pyproject.toml`：在运行依赖中声明 `tzdata`（版本区间按仓库惯例设上限，与其余依赖一致）；Linux/macOS 上该包仅作为 zoneinfo 的回退数据源，不改变行为。

## 实施步骤

1. 修改 `scripts/dev.mjs` 的 spawn 选项：`process.platform === "win32"` 时 `spawn(pnpm, [script], { stdio: "inherit", shell: true })`。
2. 在 `apps/api/pyproject.toml` 的 `[project] dependencies` 中加入 `tzdata`。
3. 在 Windows 开发机执行 `pnpm setup:api` 后验证 `python -m app --help` 与 `pnpm dev` 双子进程启动。

## 依赖与交付边界

- 依赖：无（m2 平台骨架已落地）。
- 非目标：不改造 `pnpm dev` 为进程管理器、不引入 `concurrently` 等依赖；不修复 `flow-new-issue.mjs` 等 CI 专用脚本的 Windows 入口判断（另立 issue）；不处理 MySQL 本地安装。

## 独立验证

```sh
pnpm dev
```

- Windows 11 + Node 22：约 15 秒内 `http://127.0.0.1:8787/api/health` 返回 `{"ok":true,…}`，`http://localhost:5173` 返回 200；Ctrl+C 后两个子进程均退出。

```sh
pnpm setup:api; pnpm data:import:sessions
```

- 全新 `apps/api/.venv`（未手动 `pip install tzdata`）上不再出现 `ZoneInfoNotFoundError: 'No time zone found with key Asia/Shanghai'`，import 命令输出 `{"status": …}` JSON。

## 验收标准

- Windows 上 `pnpm dev` 一次命令起 API(8787) 与 Web(5173)，退出码 0、无 `spawn EINVAL`。
- 全新 venv 中 `import app.main` 成功，zoneinfo 无需系统 tz 数据库。
- POSIX（CI）行为不变：`pnpm dev`、`pnpm test:api` 等命令结果与改动前一致。

## 门禁与 CI

- `pnpm test:gates`（含 `scripts/gates.spec.mjs`，本 issue 未改门禁脚本，须保持绿）。
- `pnpm lint:api` / `pnpm typecheck:api`：`pyproject.toml` 变更后依赖解析须通过。
- CI（Ubuntu）上 `pnpm dev` 路径不受 `shell: true` 分支影响；现有覆盖率 ≥80% 红线不放松。

## 非目标

- 不统一各脚本的跨平台 spawn 策略（如全局 `shell: true` 审计）。
- 不为 `flow-new-issue.mjs` / 其他 `import.meta.url` 入口判断做 Windows 兼容（另行立 issue）。
- 不引入本地 MySQL 或生产部署相关改动。
