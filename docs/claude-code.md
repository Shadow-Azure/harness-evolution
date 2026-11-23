# Claude Code

[English](claude-code.en.md) | 中文

Deploy 安装 Claude Code 并用 GitHub Secrets 写入模型配置。runner 下载校验官方 apt 包后上传；服务器只解包，不访问 `claude.ai`，无需 root/Node.js。

## GitHub Secrets

| Secret | 必填 | 内容 |
|---|---|---|
| `CLAUDE_CODE_MODEL` | 是 | 模型 ID，例如 `MiniMax-M3.1-Flash[1m]` |
| `CLAUDE_CODE_API_KEY` | 是 | 模型 API key |
| `CLAUDE_CODE_BASE_URL` | 否（MiniMax 必填） | Anthropic 兼容端点，`https://`（loopback 可 `http://`）；MiniMax 国内版为 `https://api.minimax.cn/anthropic` |

`CLAUDE_CODE_VERSION` 是 Variable，非 Secret；留空取 stable 最新。

## 配置

安装包解包到 `/opt/harness/shared/claude-code/<version>`（0755），原子创建 `current` 软链；服务用 `current/usr/bin/claude`，升级只切软链并保留上一版本。重跑同版本修复版本目录及 `usr`、`usr/bin` 权限。

服务配置在 `/opt/harness/shared/claude-code/config/settings.json`（0644）：`model`、可选 `ANTHROPIC_BASE_URL`、模型别名与 MiniMax 512K/heavy 参数，不含密钥。Deploy 把 `HE_AI_AGENT_CLAUDE_BIN`、`HE_AI_AGENT_CLAUDE_SETTINGS`、`CLAUDE_CONFIG_DIR` 与 `ANTHROPIC_API_KEY`（复用 Secret）注入 0600 `.env`；服务只透传环境。

切换 `current` 前预检二进制 other 可执行、settings other 可读、路径各级 other 可穿越；失败中止并保留旧 release。Deploy 再用 `stat` 复核，有权限时跑 `sudo -u harness ... --version`。Secret 全缺告警跳过；部分配置失败。

## analyze 工具面与权限

analyze 不用 `--bare`，固定传 `--safe-mode`、`--restricted`、`--strict-mcp-config` 与 `--tools Read,Write`，只让模型读 `schema.json`、写 `result.json5`。

权限规则按任务目录绝对路径构造：`Read(//<task>/schema.json)` 与 `Edit(//<task>/result.json5)`。文件写入只认 `Edit(path)`；`Bash`、`Edit` 工具与任务目录外写入被 `dontAsk` 拒绝。`--output-format stream-json --verbose` 读取工具列表与 `permission_denials`/`stop_reason`/`num_turns`，工具缺失或写被拒立即失败。

验收：

```sh
HE_AI_AGENT_CLAUDE_E2E=1 \
HE_AI_AGENT_CLAUDE_BIN=/opt/harness/shared/claude-code/current/usr/bin/claude \
  pnpm test:api -- tests/test_ai_agent_claude_code.py -k e2e_real_cli
```

## 验证

```sh
ver=$(ssh deploy@<host> 'readlink -f /opt/harness/shared/claude-code/current')
ssh deploy@<host> "stat -c '%a %U:%G %n' '$ver' '$ver/usr' '$ver/usr/bin' /opt/harness/shared/claude-code/config/settings.json"
ssh deploy@<host> 'sudo -u harness /opt/harness/shared/claude-code/current/usr/bin/claude --version'
```

版本目录、`usr`、`usr/bin` 应为 `755`；最后一条是 harness 视角验收。

`claude -p` 需要真实 API key，属人工验收；流水线只校验安装与配置结构。生产验收看 `ai_agent_call.outcome=ok`、tokens>0、`model` 非 `unknown`，且无 `degraded`。

## 回滚

把 `current` 指回上一版本目录，或重跑带所需 `CLAUDE_CODE_VERSION` 的 `Deploy`。共享 settings 与 `.env` 原子写入；`current` 与 `HE_AI_AGENT_CLAUDE_BIN` 解耦，回滚不改 `.env`。步骤见 [plans/deploy-aliyun-playbook.md](../plans/deploy-aliyun-playbook.md)。
