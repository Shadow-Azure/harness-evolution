# Fixture 语料

[English](README.en.md) | 中文

`fixtures/m2-synthetic/` 是 M2 的确定性开发数据。`corpus.json` 使用封闭 schema 描述四棵根会话和问题、归因、目标配置；`payloads/` 每个有转录的 agent 一行 JSONL 文件。哈希与行数由 loader 从文件推导，不写入 manifest。

先运行 `pnpm fixtures:check` 做 schema、路径、JSONL 和字节预算检查，再运行 `pnpm fixtures:seed` 写入真实 SQLite/MySQL 表。seed 只允许 demo 或测试环境，按稳定键幂等 upsert：同内容不写库，字段变化原位更新且不替换主键；它不会提交真实 Claude 会话、凭据或派生簇。
