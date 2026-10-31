# Agent Note: 进化对象绑定验证集与测试集测试工程 ID

Status: implemented

## Problem

进化对象配置只描述对象位置与基线，没有字段表达“验证集在哪个测试工程、测试集在哪个测试工程”。外部测试平台用两个独立工程承载这两类集合；如果只在界面或文档里约定，配置页不是事实源，刷新、换人或重建环境后信息就丢了。后续评测接入即使拿到 target，也没有可读取的持久化来源来区分验证集与测试集。

## Decision

- `evolution_targets` 增加 `validation_project_id` / `test_project_id` 两列，`VARCHAR(128) NOT NULL DEFAULT ''`；创建与编辑接口要求 trim 后非空、不含空白或控制字符，失败返回 `422 PROJECT_ID_INVALID` 与 `details.field` / `details.reason`。
- `evolution_runs` 增加同两列，创建 run 时从 target 快照；历史 run 为空串。run API、详情页与评测 gateway 本切片不改。
- 历史 target 的两列为空串，列表可读，编辑必须补齐；新 target 必须带两个 ID。
- 配置列表合并一列“测试工程”，两行展示验证集/测试集；不拆成两个表格列。
- 工程 ID 是不透明字符串：本服务不调用外部平台、不校验存在性、不加唯一约束。

## Alternatives considered

- **只放在 `evolution_runs.eval_config`**：run 创建时才填写，target 配置页没有事实源，管理员无法预先绑定；否决。
- **DB 允许 NULL、API 可选**：历史行与旧客户端更宽松，但编辑可以绕过必填，和“必填字段”的需求冲突；否决。
- **保存时调用外部测试平台校验工程存在**：当前没有稳定契约、凭据与错误语义，会把网络失败变成保存失败；本切片不引入出站调用；否决。
- **单独建 target 与测试工程的关联表**：当前是一对一、固定两类，独立表只增加 join 与迁移成本；否决。

## Consequences

- 迁移 `0013` 增加四列；回滚会丢失已填写的 ID，回滚前需导出。
- 不传两个字段的旧客户端会收到 422，这是一次有意的必填收紧。
- 历史 target 在补齐前不能保存编辑；历史 run 的快照为空串。
- 后续评测切片需要读取 `evolution_runs` 的两列，并把它们映射到外部请求；本切片只保证快照存在且稳定。
- 两个字段没有索引与唯一约束；按对象查询仍走 `(object_type, object_name)`。
