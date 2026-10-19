# Skills

从 StudyWiki 移植的可复用技能，供 Codex 在明确触发时读取对应 `SKILL.md`。

| Skill | 用途 | 本仓库接线 |
|---|---|---|
| `pr-review` | 结构化 PR 检视，产出 `plans/` 检视文档 | 直接可用；规范见 [docs/review.md](../../docs/review.md) |
| `pr-review-fix` | 分析、修复并回复 PR 检视意见 | 直接可用；依赖子代理能力 |
| `computer-use` | 通过 `node_repl` 读取与操作 macOS 应用界面 | 直接可用；需 `@oai/sky` 运行环境 |
| `computer-use-smoke-reporting` | 把 GUI 冒烟证据渲染为独立 HTML 报告 | 直接可用；报告目录建议放 `reports/` |
| `walkthrough-change-metadata-gen` | 生成讲解站变更页元数据 | 仅保留技能本体；本仓库尚未接入 walkthrough 站点与校验脚本 |

技能文件保持参考工程原样，避免与上游漂移；本仓库特定的路径与命令以根 `AGENTS.md` 和 `docs/` 为准。
