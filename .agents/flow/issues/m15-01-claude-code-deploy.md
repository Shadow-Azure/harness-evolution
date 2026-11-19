This is by an automated agent, not a human.

# 部署流水线自动安装并配置 Claude Code（模型经 GitHub Secrets 注入）

[English](m15-01-claude-code-deploy.en.md) | 中文

```yaml flow
kind: issue
id: m15-01
milestone: m15
depends:
  - m6-22
priority: P1
status: in-progress
scope:
  - .github/workflows/**
  - deploy/**
  - docs/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
  - scripts/doc-budgets.manifest.json
  - apps/api/tests/**
adr: []
github:
  number: 376
  url: https://github.com/Shadow-Azure/harness-evolution/issues/376
```

## 背景

生产 `Deploy` 以 `deploy` 用户经 SSH 发布，免密 sudo 只有 `systemctl restart/start harness-api`，服务器没有 Node.js；`claude.ai/install.sh` 在当前网络被区域拦截，而官方 apt 仓库可达。官方 `claude-code` deb 只包含 `./usr/bin/claude` 一个文件、无 postinst，且只依赖 `libc6`，可以在用户目录解包后直接运行。用户选择 MiniMax 国内版 Anthropic 兼容端点，模型和 API key 放 GitHub Secrets；`harness-api` 目前不调用 Claude Code，本 issue 只交付生产服务器上的可用安装与模型配置。

## 目标

- `Deploy` 在切换 `current` 之前自动安装/更新 Claude Code，并写好 `deploy` 用户的模型配置；失败不破坏当前 release。
- 安装包在 runner 侧获取并校验，服务器侧只解包；不依赖服务器直连 `claude.ai`，不需要 root 或 Node.js。
- 模型、端点和密钥只来自 GitHub Secrets；密钥不进 `settings.json`、日志、仓库或 SSH 命令行。
- Secret 全缺时跳过且不影响既有发布；只配一部分时显式失败。
- 文档、部署手册和 Agent Note 记录操作、验证与回滚。

## 设计依据

- [plans/fullstack-design/01-architecture.md §6 部署形态](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/01-architecture.md)：单实例 SaaS、nginx + uvicorn、GitHub Secrets 与服务器本地配置的边界。
- [docs/deployment.md](https://github.com/Shadow-Azure/harness-evolution/blob/main/docs/deployment.md)：现有发布、Secrets、探活与回滚约定。
- MiniMax Claude Code 文档：国内版端点、M3.1-Flash 模型与默认 Sonnet/Opus/Haiku 别名。

## 实现内容

- `deploy/fetch-claude-code-deb.sh`（runner 侧）：按服务器 `dpkg --print-architecture` 解析官方 apt `Packages`，下载对应版本、校验 SHA256、按版本缓存；支持 `--resolve-only` 只返回版本。
- `deploy/install-claude-code.py`（服务器侧）：从 stdin 读取 base64 变量；把 deb 解包到 `/opt/harness/shared/claude-code/<version>`，先自检再原子切换 `~/.local/bin/claude`；原子写 `~/.claude/settings.json`、`~/.claude/api-key`、`~/.claude/api-key.sh`，并把 `hasCompletedOnboarding: true` 合并进 `~/.claude.json`；校验 JSON、权限和 `claude --version`。
- `.github/workflows/deploy.yml`：在“上传 release 与配置”之后、发布之前新增准备与安装两步；缓存 deb，探测服务器版本，仅版本变化时传输；Secret 全缺跳过、部分缺失失败。
- `docs/deployment.*` 与 `plans/deploy-aliyun-playbook.md`：补 Secret 清单、安装/配置/验证/回滚步骤；新增 Agent Note 记录“runner 下载 + 用户级解包 + apiKeyHelper”的取舍。
- `apps/api/tests/deploy/test_install_claude_code.py`：覆盖解码、版本规范化、settings 构造、权限与 base URL 校验等纯函数。

## 实施步骤

1. 建 m15/m15-01 流程文件与分支，确认 m6-22 已完成。
2. 实现 runner 与服务器脚本，补齐单元测试。
3. 接入 `deploy.yml`，保持 Secret 缺失时的既有行为。
4. 更新中英部署文档、操作手册和 Agent Note。
5. 跑静态门禁与聚焦测试，提交 PR，按 CI 与检视意见修复。

## 依赖与交付边界

- 依赖：m6-22（现有 GitHub Actions 发布通道）。
- 交付边界：只改部署流水线、`deploy/` 脚本、部署文档/手册、Agent Note、流程文件和对应测试；不改 `apps/` 业务代码、契约、数据库或前端。
- 真实 `claude -p` 冒烟需要用户把占位 `CLAUDE_CODE_API_KEY` 换成 MiniMax 真实 key；流水线只校验安装与配置结构，不把外部模型可用性作为发布硬门禁。
- 不在本 issue 把 Claude Code 接入 `harness-api`；如后续需要，另立 issue 处理运行用户与配置目录权限。

## 独立验证

```sh
bash -n deploy/fetch-claude-code-deb.sh
python3 -m py_compile deploy/install-claude-code.py
pnpm test:api -- tests/deploy
pnpm verify:flow
pnpm verify:docs
pnpm test:gates
```

- 单元测试覆盖 base64 解码、版本比较、settings 构造与权限；`--resolve-only` 能返回官方 apt 当前 stable 版本。
- Secret 全缺：安装步骤 warning 跳过，`Deploy` 其余步骤与现状一致。
- Secret 配齐：服务器 `~/.local/bin/claude --version` 成功；`claude doctor` 无 settings 错误；`claude -p "只回复 OK"` 返回模型结果（人工，需真实 key）。
- 重跑同一版本不重复下载/解包；换版本只切换软链；失败发生在 `current` 切换之前。

## 验收标准

- 配好三个 Secret 后一次正常 `Deploy` 得到可执行的 Claude Code 和 MiniMax 模型配置。
- `~/.claude/settings.json`、`~/.claude/api-key` 与 `~/.claude.json` 权限为 600，`api-key` 不出现在 settings、日志或仓库。
- Secret 全缺时部署与现状一致；部分缺失显式失败；安装失败不切换 `current`。
- 服务器不需要 root 或 Node.js；`harness-api` 与现有发布流程不受影响。
- 文档与操作手册包含 Secret 清单、验证命令和回滚步骤。

## 门禁与 CI

- `docs-flow`（`verify:flow --diff`）：PR 标题与提交含 `(#376)`，改动落在本 issue scope。
- `static`、`test`、`docs`、`flow-online` 等既有 lane；`pnpm verify:docs`、`pnpm test:gates`、`bash -n`、`py_compile`。
- `deploy.yml` 不在 PR lane 执行；真实部署在合并后由人工触发或等待 main CI 全绿，人工验收 `claude -p`。

## 非目标

- 不把 Claude Code 接进 `harness-api`，不改 `apps/`、`packages/contracts`、数据库或前端。
- 不做系统级 `/usr/bin` 安装，不扩大 `deploy` 的 sudo 权限，不引入 Node.js。
- 不启用 Claude Code 自动更新，不做多用户共享配置，不做多模型路由/自动降级。
- 不把生产密钥写进 `.env`、仓库、镜像或日志；不把真实 key 贴到 issue/PR。
- 不把外部模型可用性做成发布硬门禁；真实调用由人工冒烟验收。
