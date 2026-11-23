# 文档地图

[English](README.en.md) | 中文

`docs/` 的唯一索引。新增常驻文档必须登记进本页表格；门禁 `verify-doc-index` 双向对账。层级与写作规则见 [AGENTS.md](AGENTS.md)。

## 地图

| 文档 | 回答什么 |
|---|---|
| [AGENTS.md](AGENTS.md) | 文档分层、写作规则与门禁 |
| [architecture.md](architecture.md) | 服务边界、数据流、数据层与 API |
| [ai-agent.md](ai-agent.md) | 自进化 AI 出站层、提交通道与观测事件 |
| [compatibility.md](compatibility.md) | V1 兼容面、触发版本与机械退役清单 |
| [roadmap.md](roadmap.md) | 产品阶段路线与各阶段验收 |
| [development.md](development.md) | 本地环境、日常循环与提交流程 |
| [deployment.md](deployment.md) | 阿里云部署与发布回滚 |
| [git-proxy.md](git-proxy.md) | 生产 Git 出网代理、Secret 与失效回退 |
| [git-workspace.md](git-workspace.md) | 自进化 Run 的单 ref 工作区缓存、推送目标与 git 可观测性 |
| [claude-code.md](claude-code.md) | 生产 Claude Code 安装、模型配置与验证 |
| [review.md](review.md) | PR 检视、证据要求与分流表 |
| [charter.md](charter.md) | 实验协议、进化判定与边界 |
| [metrics.md](metrics.md) | 主指标、护栏指标与记录要求 |
| [i18n/README.md](i18n/README.md) | 双语三件套、重录与豁免 |
| [i18n/terminology.md](i18n/terminology.md) | 中英术语对齐表与禁用替写 |
| [i18n/translation-prompt.md](i18n/translation-prompt.md) | 补英文侧的操作模板 |
| [postmortem/README.md](postmortem/README.md) | 事故复盘的结构与编号规则 |

## 阅读顺序

- 第一次接触项目：根 [README.md](../README.md) → [architecture.md](architecture.md) → [development.md](development.md)。
- 准备改代码：`.agents/flow/` 的 issue → 本文档地图 → 对应实现切片。
- 准备做实验： [charter.md](charter.md) → [metrics.md](metrics.md) → `research/experiments/_template`。
- 准备检视 PR：[review.md](review.md) → `.agents/skills/pr-review/SKILL.md`。

## 维护规则

- 一个事实只住一页；跨页只放链接，不复述。
- 常驻文档必须双语三件套齐备，并登记词数预算。
- 新增、移动或删除文档时同步本表；死链与未登记项由门禁拦截。
