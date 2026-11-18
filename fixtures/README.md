# Fixture 语料

[English](README.en.md) | 中文

`fixtures/m2-synthetic/` 是 M2 的确定性开发数据。`corpus.json` 使用封闭 schema 描述四棵根会话和问题、归因、目标配置；`payloads/` 每个有转录的 agent 一行 JSONL 文件。哈希与行数由 loader 从文件推导，不写入 manifest。

`fixtures/attribution-golden/cases.json` 是脱敏归因质量基线，只保存合成标题、顺序、对象 occurrence、报告点和 Agent 关系坐标，不保存原始消息、用户/仓库名或凭据。它覆盖 self/discovery、非根因、多 occurrence、多对象、缺 Trace、关系降级、非 Skill 问题和提示注入；`pnpm attribution:evaluate -- --engine agent-skill-stub-v1 --output <file>` 生成隔离对照报告。

先运行 `pnpm fixtures:check` 校验两套语料的 schema、路径、JSONL 和预算，再运行 `pnpm fixtures:seed` 写入 M2 SQLite/MySQL 表。项目路径只能位于合成的 `/workspace/` 下，仓库 URL 不得带凭据；每行 JSONL 的会话身份必须与 manifest 一致，子 Agent 还必须声明匹配的 `agentId`，重复 JSON 键会被拒绝。seed 只允许 demo 或测试环境，按稳定键幂等 upsert：同内容不写库，fixture-owned 字段变化原位更新且不替换主键，首次接收时间与归一化状态不被覆盖；它不会提交真实 Claude 会话、凭据或派生簇。
