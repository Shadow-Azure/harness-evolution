# Server

本地后端服务骨架。

当前只提供 `GET /api/health`。业务模块尚未实现，计划按以下顺序加入：

1. `sessions`：session 列表与详情
2. `ingest`：导入 Codex rollout JSONL
3. `storage`：SQLite repository 层
4. `analysis`：轨迹诊断任务

新增模块时优先按垂直切片组织，避免先堆一层通用抽象。
