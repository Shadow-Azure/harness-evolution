# Claude Code

[English](claude-code.en.md) | 中文

生产部署流水线在切换 `current` 之前为 `deploy` 用户安装 Claude Code，并用 GitHub Secrets 写入模型配置。安装包在 GitHub Actions runner 侧从官方 apt 仓库下载、校验 SHA256 后上传；服务器只解包，不访问 `claude.ai`，不需要 root 或 Node.js。

## GitHub Secrets

| Secret | 必填 | 内容 |
|---|---|---|
| `CLAUDE_CODE_MODEL` | 是 | 模型 ID，例如 `MiniMax-M3.1-Flash[1m]` |
| `CLAUDE_CODE_API_KEY` | 是 | 模型 API key |
| `CLAUDE_CODE_BASE_URL` | 否（MiniMax 必填） | Anthropic 兼容端点，必须 `https://`（loopback 可 `http://`）；MiniMax 国内版为 `https://api.minimax.cn/anthropic` |

`CLAUDE_CODE_VERSION` 是 Variable，不是 Secret；留空取 stable 最新。

## 配置

安装包解包到 `/opt/harness/shared/claude-code/<version>`，`~/.local/bin/claude` 原子切到当前版本，保留当前和上一个版本。`~/.claude/settings.json`（600）保存 `model`、可选的 `ANTHROPIC_BASE_URL` 和 `apiKeyHelper`；真实 key 在 `~/.claude/api-key`（600），helper 脚本（700）读取，不进入 settings。`~/.claude.json`（600）合并 `hasCompletedOnboarding: true`，保留已有键。MiniMax 按文档写入 512K 自动压缩窗口（`524288`）与 `effort=max`，并把 Sonnet/Opus/Haiku 别名指向同一模型。

三个 Secret 全缺时该步骤告警跳过；只配一部分时失败；安装或配置失败在切换 `current` 前中止，旧 release 继续服务。重跑同一版本只重写配置，不重复下载或解包。

## 验证

```sh
ssh deploy@<host> '~/.local/bin/claude --version'
ssh deploy@<host> '~/.local/bin/claude doctor'
ssh deploy@<host> '~/.local/bin/claude -p "只回复 OK"'
```

`claude -p` 需要真实 API key，属于人工验收；流水线只校验安装与配置结构。

## 回滚

把 `~/.local/bin/claude` 软链指回上一版本目录，或重新触发一次带所需 `CLAUDE_CODE_VERSION` 的 `Deploy`。`~/.claude/settings.json` 与 `api-key` 是原子写入，失败时保留上一份。操作步骤见 [plans/deploy-aliyun-playbook.md](../plans/deploy-aliyun-playbook.md)。
