# 14 · 进化对象的验证集与测试集测试工程 ID

> 本文回答：两个测试工程 ID 分别指什么、为什么挂在 `evolution_targets` 上、如何迁移与校验、前端浮窗如何呈现，以及本切片为什么不动 run 与评测链路。
> 前置：[05 接口设计](05-api-design.md) · [06 数据库设计](06-database-design.md) · [08 前端实现](08-frontend-implementation.md) · [02 功能清单](02-features.md)。

## 1. 背景

进化对象配置目前只描述“对象在哪里、基线是什么”：`objectType`、`objectName`、`repoUrl`、`subDir`、`defaultRef`、`enabled`。管理员在新增/编辑浮窗里填完这些字段，就能让对象进入启动向导的候选列表。

验证集与测试集是外部测试平台上的两类独立测试工程。配置层缺少两个工程的标识，导致：

- 管理员无法在配置页表达“这个 skill/agent 的验证集在哪个工程、测试集在哪个工程”。
- 后续评测接入即使拿到 target，也没有可读取的持久化来源来区分验证集与测试集。
- 工程 ID 只能散落在文档、工单或口头约定里，配置页不是事实源。

本切片把两个 ID 变成 `evolution_targets` 的一等字段，并在新增/编辑浮窗中设为必填；外部调用、run 快照与评测 gateway 留给后续切片。

## 2. 术语与语义

| 名称 | 指什么 | 示例 |
|---|---|---|
| 验证集测试工程 ID | 外部测试平台上承载验证集的测试工程标识 | `val-2026-q3` |
| 测试集测试工程 ID | 外部测试平台上承载测试集的测试工程标识 | `test-2026-q3` |
| 验证集 | 迭代过程中用于回归与候选决策的数据集合 | — |
| 测试集 | 最终验收或独立评估的数据集合，不参与逐轮 patch 决策 | — |

工作定义（待确认）：验证集用于“每轮候选是否比当前版本好”的迭代判断；测试集用于“最终版本是否可交付”的独立验收。两个 ID 都是**不透明字符串**，本服务只存储和回显，不解析、不校验存在性、不要求唯一。

规则：

- 两个 ID 属于 target 配置，但创建 run 时按 `repo_url` / `sub_dir` 的同一语义快照到 `evolution_runs`：run 使用创建时的值，后续 target 修改不影响已创建的 run。
- 同一个 ID 可以出现在多个 target 上；本切片不加唯一约束。
- 两个字段都必填；历史行允许暂时为空，但编辑保存前必须补齐。
- 数据库列名 `validation_project_id` / `test_project_id`，JSON 字段 `validationProjectId` / `testProjectId`，界面标签“验证集测试工程 ID”“测试集测试工程 ID”。

## 3. 数据模型

### 3.1 `evolution_targets` 新增列

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `validation_project_id` | `VARCHAR(128)` | NOT NULL DEFAULT `''` | 验证集测试工程 ID；创建/更新时由 API 要求非空 |
| `test_project_id` | `VARCHAR(128)` | NOT NULL DEFAULT `''` | 测试集测试工程 ID；创建/更新时由 API 要求非空 |

- 不加索引：两个字段不参与列表排序、过滤或 join。
- 不加唯一约束：一个测试工程可以被多个对象复用，唯一性属于外部平台。
- 不加 DB `CHECK (<> '')`：历史行需要先以空串存在，才能在不阻塞迁移的前提下由管理员逐个补齐；必填由 API 与表单两层保证。

### 3.2 `evolution_runs` 新增快照列

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `validation_project_id` | `VARCHAR(128)` | NOT NULL DEFAULT `''` | 创建 run 时从 target 配置快照；历史 run 为空串 |
| `test_project_id` | `VARCHAR(128)` | NOT NULL DEFAULT `''` | 创建 run 时从 target 配置快照；历史 run 为空串 |

- `LaunchTargetRecord` 暴露两个属性，`LaunchService._run_values` 把 `config.validation_project_id` / `config.test_project_id` 写入 `create_run`。
- `EvolutionRunRecord` 增加两个字段（末尾默认空串，兼容既有测试构造），repository 的 `_run_record` 映射两列。
- 本切片不在 run API/详情页暴露这两个字段，也不改 `EvalRequest`；快照先落库，供后续评测切片读取。
- 历史 run 的两列为空串；新 run 从创建时的 target 快照。若历史 target 尚未补齐两个 ID，新 run 的两列也会是空串；启动流程不额外拦截，必填收紧只发生在 target 创建/编辑。

### 3.3 迁移

新增 `apps/api/alembic/versions/0013_target_project_ids.py`，`down_revision = "0012"`：

```text
upgrade:
  ALTER TABLE evolution_targets ADD COLUMN validation_project_id VARCHAR(128) NOT NULL DEFAULT ''
  ALTER TABLE evolution_targets ADD COLUMN test_project_id        VARCHAR(128) NOT NULL DEFAULT ''
  ALTER TABLE evolution_runs     ADD COLUMN validation_project_id VARCHAR(128) NOT NULL DEFAULT ''
  ALTER TABLE evolution_runs     ADD COLUMN test_project_id        VARCHAR(128) NOT NULL DEFAULT ''
downgrade:
  ALTER TABLE evolution_runs     DROP COLUMN validation_project_id
  ALTER TABLE evolution_runs     DROP COLUMN test_project_id
  ALTER TABLE evolution_targets DROP COLUMN validation_project_id
  ALTER TABLE evolution_targets DROP COLUMN test_project_id
```

SQLite 与 MySQL 都走 `op.add_column`；SQLite 对带 `server_default` 的 `ADD COLUMN NOT NULL` 支持该形态。历史行迁移后四列均为空串，`GET /api/evolution/targets` 原样返回空串，不伪造默认工程 ID。

### 3.4 读取与写入

- `EvolutionTargetRecord` 增加两个 `str` 字段，repository 的 `_record`、`insert`、`update` 同步映射。
- `GET /api/evolution/targets` 返回两个字段；历史行返回 `""`。
- `POST` / `PUT` 的 `EvolutionTargetWrite` 增加两个字段；服务层 trim 后写库。
- `LaunchService` 创建 run 时快照两个字段；`EvolutionRunRecord` 读取它们供后续评测切片使用。
- 删除、启用/停用、按对象名唯一性冲突、活跃 run 保护均不变。

## 4. API 契约

### 4.1 字段

`EvolutionTargetWrite` 与 `EvolutionTarget` 增加：

```json
{
  "validationProjectId": "val-2026-q3",
  "testProjectId": "test-2026-q3"
}
```

完整创建请求示例：

```json
{
  "objectType": "skill",
  "objectName": "deep-research",
  "repoUrl": "https://git.example.com/agent-skills.git",
  "subDir": "skills/deep-research",
  "defaultRef": "main",
  "validationProjectId": "val-2026-q3",
  "testProjectId": "test-2026-q3",
  "enabled": true
}
```

`GET /api/evolution/targets` 的每一项同时返回两个字段；历史行返回空串。字段顺序不构成契约，前端按名称读取。

### 4.2 校验

服务层对两个字段做同一套归一化：

1. 去掉首尾空白；结果为空 → 拒绝。
2. 长度超过 128 → 拒绝（Pydantic 的 `max_length=128` 可能在进入服务前返回 `VALIDATION_INVALID`；前端 `maxlength` 也会阻止输入）。
3. 含任何空白字符（包括内部空格、制表符、换行）或控制字符（`\x00-\x1f`、`\x7f`）→ 拒绝。
4. 其他字符一律接受，不限制为数字、UUID 或特定前缀；工程 ID 是不透明字符串。

失败返回 `422 PROJECT_ID_INVALID`：

```json
{
  "error": {
    "code": "PROJECT_ID_INVALID",
    "message": "test project id is invalid",
    "details": {
      "field": "validationProjectId",
      "reason": "project_id_required"
    }
  }
}
```

- `field`：`validationProjectId` 或 `testProjectId`。
- `reason`：`project_id_required`（trim 后为空）或 `project_id_format`（含空白/控制字符、超长）。
- 两个字段同时失败时，按 `validationProjectId` 优先返回；前端本地校验会同时标出两个字段。
- 不新增 `PROJECT_ID_NOT_FOUND`：本服务不访问外部测试平台，无法判断 ID 是否存在。

### 4.3 错误码

`ErrorCode` 增加 `PROJECT_ID_INVALID`。不修改 `REPO_INVALID`、`TARGET_EXISTS`、`TARGET_NOT_FOUND`、`TARGET_IN_USE`、`VALIDATION_INVALID` 的现有语义。

选择独立错误码而不是复用 `VALIDATION_INVALID`：`VALIDATION_INVALID` 是请求形状/类型错误的通用出口，前端无法据此定位到具体输入；独立错误码让 API 客户端和后续字段级错误通道能直接读到 `field`。复用 `REPO_INVALID` 则会把工程 ID 错误误报成仓库/ref 错误。

## 5. 前端

### 5.1 表单结构

`TargetFormDialog.vue` 的顺序：

```text
对象类型
对象名称
仓库地址（整行）
子目录            基线分支或标签
验证集测试工程 ID   测试集测试工程 ID   ← 新增，两列
启用
```

- 两个新输入放在“子目录/基线”行之后、启用开关之前；与 `subDir`/`defaultRef` 共用 `.form-grid` 两列布局。
- 标签固定为“验证集测试工程 ID”“测试集测试工程 ID”；`ElFormItem` 设置 `required`，显示必填星号。
- `name` 属性分别为 `validationProjectId`、`testProjectId`，供测试与浏览器自动填充识别。
- `maxlength="128"`，placeholder 分别是 `如 val-2026-q3`、`如 test-2026-q3`。
- 帮助文案：“验证集与测试集分别对应外部测试平台的测试工程 ID；只保存标识，不在此处校验工程是否存在。”
- 640px 以下沿用现有单列规则，两个输入各占一行。

### 5.2 校验与错误

- 本地提交前 trim；空或纯空白 → 字段下显示“请填写验证集测试工程 ID”/“请填写测试集测试工程 ID”。
- 含内部空白或控制字符 → 字段下显示“工程 ID 不能包含空格或控制字符”。
- 超长由 `maxlength` 阻止；粘贴超长内容时浏览器截断。
- 提交时两个字段同时为空，两个字段都显示错误；不发送请求。
- 用户修改字段后清除该字段错误，与现有 `defaultRef` 的清除行为一致。
- 后端返回 `PROJECT_ID_INVALID` 时，`Index.vue` 把它映射为表单底部错误“测试工程 ID 无效，请检查是否为空、超长或包含空格”。字段级服务端错误通道留给结构化错误切片；本切片不扩展 `TargetFormDialog` 的 props。
- 编辑历史行：两个输入为空，提交被本地校验阻止；管理员补齐后才能保存。不额外弹确认框。

### 5.3 创建、编辑与重置

- `resetForm` 从 `target.validationProjectId` / `target.testProjectId` 回填；新增态为空。
- `submit` emit 的 `EvolutionTargetWrite` 包含 trim 后的两个字段。
- `Index.vue` 的 `targetWrite`（启用/停用）复制两个字段，保证 toggle 不会把已保存值清空。
- 版本建议、仓库变更提示、启用开关、服务端错误保留与现有行为不变。

### 5.4 配置列表表格

`TargetTable.vue` 增加一列“测试工程”，放在“基线”与“状态”之间，合并展示两个 ID：

```text
┌ 测试工程 ─────────────────────┐
│ 验证集 · val-2026-q3           │
│ 测试集 · test-2026-q3          │
└────────────────────────────────┘
```

- 标签“验证集”“测试集”用 `--text-faint`，值用 `--mono`；两行小字，不新增两个独立列。
- 历史行值为空时显示“未填写”，使用 `--text-faint`，不显示空白单元格。
- 长 ID 按单元格宽度省略，`title` 保留完整值；表格 `min-width` 从 820px 调整到 980px，窄屏仍由 `.target-table-scroll` 横向滚动。
- 不改变启用/停用、编辑、删除按钮与行操作顺序。

### 5.5 可访问性与测试钩子

- `ElFormItem` 的 `required` 负责星号；错误文本是真实 `<p>`，不只靠颜色。
- 字段错误元素使用现有 `.field-error` 样式；后续结构化错误切片可统一加 `aria-invalid`/`aria-describedby`，本切片不引入第二套机制。
- 测试用 `input[name="validationProjectId"]`、`input[name="testProjectId"]` 定位；表格列用 `data-testid="target-project-ids"` 定位。

## 6. 原型改造

文件：`plans/14-15-ui-prototype/harness-evolution.html`。

- `targetConfigs` 的三条示例数据补 `validationProjectId`、`testProjectId`，编辑态可见回填。
- `openTargetDialog` 的 `targetDialog.form` 增加两个字段，新增态为空。
- `renderTargetDialog` 在“子目录/基线”行后增加两个 `.f-row`，标签带 `<span class="req">*</span>`，输入带 `data-target-field` 与 `id`。
- `syncTargetForm` 读取两个输入。
- `saveTargetConfig` 校验 trim 后非空，错误通过现有 `form-error` 展示；保存对象包含两个字段。
- 配置列表增加“测试工程”列，按 5.4 的两行格式展示；表头与示例数据同步。
- 不改变 720px 表单宽度、两列网格、header/body/footer 分区与遮罩行为。

步骤 5 会提供修改前后的同视口截图（新增浮窗与编辑浮窗），确认后再进入实现。

## 7. 兼容性、回滚与数据边界

- **旧客户端**：不传两个字段的 `POST` / `PUT` 会得到 422；这是一次有意的必填收紧。前端与契约在同一 PR 更新。
- **历史 target**：迁移后两列为空串；列表可读，编辑必须补齐；删除与启停不要求补齐。
- **历史 run**：迁移后两列为空串；新 run 从 target 快照，后续 target 修改不影响已创建 run。
- **回滚**：`0013` 的 downgrade 直接删除四列，已填写的工程 ID 会丢失；回滚前应导出 target 与 run 的这两列。应用回滚后旧版本忽略这四列。
- **数据边界**：不把工程 ID 写入 run 事件、日志或评测 payload；本切片没有出站调用，因此没有新的脱敏面。
- **fixtures**：`EvolutionTargetFixture` 增加两个必填字段，`fixtures/m2-synthetic/corpus.json` 补示例值；seed 写入两列。fixtures 是开发数据，不代表真实工程。

## 8. 测试计划

### 8.1 后端

- 服务层参数化：空串、纯空白、内部空格、制表符、换行、控制字符、128 字符、129 字符；断言 `PROJECT_ID_INVALID` 的 `field`/`reason` 或 Pydantic 的 `VALIDATION_INVALID`。
- API：创建带两字段 → 201 并回读；更新只改一个 → 另一个不变；列表返回两字段；缺字段 → 422；历史行（直接插入空串）→ GET 返回空串，PUT 空值 → 422，补齐 → 200。
- Run 快照：用带两字段的 target 启动 run → `evolution_runs` 两列等于 target 值；创建后修改 target → 已创建 run 的两列不变。
- Repository：insert/update/记录映射包含两列；run 记录映射包含两列；迁移后四列存在、默认值为空串。
- 迁移：`test_database.py` 的 head 断言从 `0012` 更新为 `0013`；新增 target 与 run 的 upgrade/downgrade 用例。
- 契约：`pnpm contract:generate` 后 `pnpm contract:check` 无漂移。

### 8.2 前端

- 新增态渲染两个必填输入；空提交显示两条字段错误且不 emit。
- 填写后 emit 的 body 含 trim 后的两个字段；编辑态回填；重置清空。
- 内部空白触发格式错误；修改后错误清除。
- 服务端 `PROJECT_ID_INVALID` 映射为表单底部错误。
- `Index` 的 toggle 请求体保留两个字段。

### 8.3 E2E 与冒烟

- E2E：管理员新增对象时填写两个 ID，保存后列表可见；编辑回填并修改。
- 冒烟：真实前后端 + 模拟外部服务（会话查询接口 1/2）跑通配置页新增/编辑；报告落 `reports/`。

## 9. 非目标

- 不调用外部测试平台，不校验工程 ID 是否存在、是否可访问、是否有权限。
- 不改变 `POST /api/evolution/runs` 的请求字段、run API/详情页响应、评测 gateway 或 `EvalRequest`。
- 不把两个字段加入 `GET /api/catalogs/targets`、启动向导或运行详情页；只在 target 列表表格合并展示。
- 不做唯一性、跨对象一致性或“验证集/测试集不能相同”的校验。
- 不迁移或猜测历史 target/run 的真实工程 ID；历史值为空串，由管理员补齐。
- 不改变 `repoUrl`、`subDir`、`defaultRef` 的现有校验、错误码与安全边界。

## 10. 已确认决策

1. **字段命名与标签**：`validationProjectId` / `testProjectId`；界面“验证集测试工程 ID”“测试集测试工程 ID”。
2. **编辑历史行**：必须补齐两个 ID 才能保存；必填在创建与编辑两侧一致。
3. **Run 快照**：本切片给 `evolution_runs` 增加两列，创建 run 时从 target 快照；run API 与评测 gateway 不变。
4. **列表展示**：配置列表合并一列“测试工程”，两行展示验证集/测试集；不拆成两列。
5. **ID 字符集**：不透明字符串，仅拒绝空白/控制字符，长度 ≤128；不限制数字或前缀。
6. **必填星号**：本切片只给两个新字段加 `required` 星号；现有必填字段的视觉不在本切片统一调整。
