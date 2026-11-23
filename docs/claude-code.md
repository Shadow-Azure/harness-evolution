# Claude Code

[English](claude-code.en.md) | 中文

部署在切换 `current` 前以 `deploy` 安装 Claude Code，并用 GitHub Secrets 写入模型配置。安装包由 runner 从官方 apt 下载、校验 SHA256 后上传；服务器只解包，不访问 `claude.ai`，不需要 root 或 Node.js。

## GitHub Secrets

| Secret | 必填 | 内容 |
|---|---|---|
| `CLAUDE_CODE_MODEL` | 是 | 模型 ID，例如 `MiniMax-M3.1-Flash[1m]` |
| `CLAUDE_CODE_API_KEY` | 是 | 模型 API key |
| `CLAUDE_CODE_BASE_URL` | 否（MiniMax 必填） | Anthropic 兼容端点，必须 `https://`（loopback 可 `http://`）；MiniMax 国内版为 `https://api.minimax.cn/anthropic` |

`CLAUDE_CODE_VERSION` 是 Variable，不是 Secret；留空取 stable 最新。

## 配置

安装包解包到 `/opt/harness/shared/claude-code/<version>`（0755），并原子创建稳定软链 `current`；`~/.local/bin/claude` 只作 `deploy` 的手工入口。服务用 `current/usr/bin/claude`，升级只切软链，保留当前和上一个版本。重跑同版本（含 `need_install=false`）会修复版本目录及 `usr`、`usr/bin` 权限。

服务配置在 `/opt/harness/shared/claude-code/config/settings.json`（0644）：保存 `model`、可选 `ANTHROPIC_BASE_URL`、模型别名与 MiniMax 的 512K/heavy 参数，不含 `apiKeyHelper` 或密钥。`deploy` 的 `~/.claude` 只供手工 CLI。Deploy 把 `HE_AI_AGENT_CLAUDE_BIN`、`HE_AI_AGENT_CLAUDE_SETTINGS`、`CLAUDE_CONFIG_DIR` 与 `ANTHROPIC_API_KEY`（复用 `CLAUDE_CODE_API_KEY`，仅 base64/stdin）注入 0600 `.env`；服务只把环境传给 CLI。

切换 `current` 前预检：二进制 other 可执行、settings other 可读，且从 `prefix` 到二进制的每一级（版本目录、`usr`、`usr/bin`）other 可穿越；失败即中止，旧 release 继续服务。Deploy 再用 `stat` 复核（`test -x` 以 deploy 视角必然通过），有权限时 `sudo -u harness ... --version` 冒烟。三个 Secret 全缺时告警跳过；部分配置失败。

## 验证

```sh
ver=$(ssh deploy@<host> 'readlink -f /opt/harness/shared/claude-code/current')
ssh deploy@<host> "stat -c '%a %U:%G %n' '$ver' '$ver/usr' '$ver/usr/bin' /opt/harness/shared/claude-code/config/settings.json"
ssh deploy@<host> 'sudo -u harness /opt/harness/shared/claude-code/current/usr/bin/claude --version'
```

版本目录、`usr`、`usr/bin` 应为 `755`；最后一条是 harness 视角验收。

`claude -p` 需要真实 API key，属于人工验收；流水线只校验安装、共享权限与配置结构。生产验收看 `ai_agent_call.outcome=ok`、tokens>0、`model` 非 `unknown`，且无 `degraded`。

## 回滚

把 `/opt/harness/shared/claude-code/current` 指回上一版本目录，或重跑带所需 `CLAUDE_CODE_VERSION` 的 `Deploy`。共享 settings 与 `.env` 原子写入，失败保留上一份；`current` 与 `HE_AI_AGENT_CLAUDE_BIN` 解耦，回滚不需要改 `.env`。步骤见 [plans/deploy-aliyun-playbook.md](../plans/deploy-aliyun-playbook.md)。
