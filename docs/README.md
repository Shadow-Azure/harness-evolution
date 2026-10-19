# 文档地图

[English](README.en.md) | 中文

`docs/` 的唯一索引。新增常驻文档必须登记进本页表格；门禁 `verify-doc-index` 双向对账。层级与写作规则见 [AGENTS.md](AGENTS.md)。

## 地图

| 文档 | 回答什么 |
|---|---|
| [AGENTS.md](AGENTS.md) | 文档分层、写作规则与门禁入口 |
| [architecture.md](architecture.md) | 服务边界、数据流、数据层策略与当前 API |
| [development.md](development.md) | 本地环境、日常循环、提交与流程操作 |
| [review.md](review.md) | PR 结构化检视、证据要求与分流表 |
| [charter.md](charter.md) | 实验协议、进化判定与安全边界 |
| [metrics.md](metrics.md) | 主指标、护栏指标与运行记录要求 |
| [i18n/README.md](i18n/README.md) | 双语三件套、重录与豁免规则 |
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
