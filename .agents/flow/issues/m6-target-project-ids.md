# 进化对象配置：新增验证集与测试集测试工程 ID

[English](m6-target-project-ids.en.md) | 中文

```yaml flow
kind: issue
id: m6-20
milestone: m6
depends:
  - m5-02
  - m5-03
priority: P1
status: in-progress
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - fixtures/**
  - tests/**
  - plans/**
  - docs/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 187
  url: https://github.com/Shadow-Azure/harness-evolution/issues/187
```

## 背景

### 问题是什么

`evolution_targets` 目前只保存对象类型、对象名、仓库地址、子目录、基线分支或标签和启用状态，新增与编辑浮窗也只有这五组输入。验证集与测试集在外部测试平台上分别由两个测试工程承载，但配置里没有字段可以记录这两个工程的 ID，管理员无法表达“这个对象用哪个验证集工程、哪个测试集工程”。

### 问题现象

- 新增进化对象时，表单没有验证集测试工程 ID 与测试集测试工程 ID 输入项。
- `GET /api/evolution/targets` 响应、`POST` 与 `PUT` 请求体、`evolution_targets` 表都没有对应字段。
- 不同 skill/agent 只能共用隐式约定，无法在配置层区分验证集与测试集工程。
- 后续评测接入若要按对象选择测试工程，没有可读取的持久化来源。

### 问题影响

- 配置不完整，评测侧无法从 target 配置获得测试工程标识。
- 管理员只能把工程 ID 写在文档或口头约定里，配置页不是事实源。
- 后续增加评测接入时需要再次改表、改接口、改表单，返工成本高。

### 根因

- `EvolutionTargetWrite` 与 `EvolutionTarget` 只声明六个字段；`EvolutionTargetRecord` 与 repository 的 insert/update 只读写六列。
- `evolution_targets` 表没有两个工程 ID 列，迁移链止于 0012。
- 前端 `TargetFormDialog` 的表单模型、必填校验、reset 与 emit 都只覆盖现有字段；`Index.vue` 的 `targetWrite` 也只复制现有字段。
- 契约由 FastAPI OpenAPI 生成，后端模型不变，前端类型就不会出现新字段。

### 建议

- 在 `evolution_targets` 增加 `validation_project_id` 与 `test_project_id` 两列，`VARCHAR(128) NOT NULL`，迁移时以空串回填历史行。
- 写入接口把两个字段设为必填：去空白后非空、长度不超过 128、不含控制字符与空白；失败返回新的 `422 PROJECT_ID_INVALID`，`details` 给出 `field` 与 `reason`。
- 新增与编辑浮窗增加两个必填输入，校验与后端一致；编辑态回填已保存值；历史行为空串时提示必须补齐后才能保存。
- 列表接口返回两个字段；`GET /catalogs/targets`、启动向导与评测链路本切片不变。
- 更新契约、fixtures、迁移、单测、E2E、原型与设计文档。

## 目标

- 新增进化对象浮窗包含两个必填字段：“验证集测试工程 ID”“测试集测试工程 ID”，skill 与 agent 一致。
- 编辑浮窗回填并允许修改这两个字段；历史行空串在表单中显示为空并要求填写。
- `POST` 与 `PUT /api/evolution/targets` 接收并持久化两个字段；`GET /api/evolution/targets` 返回它们。
- `evolution_targets` 与 `evolution_runs` 各存在两列，SQLite 与 MySQL 迁移一致；创建 run 时从 target 快照。
- 配置列表合并一列“测试工程”，两行展示验证集/测试集。
- 空、纯空白、超长、含控制字符或空白的输入被前端与后端拒绝，并给出字段级提示。
- 契约、fixtures、原型和测试同步；已有对象 CRUD 与仓库校验行为不变。

## 设计依据

- [05 §4.11 进化对象配置](../../../plans/fullstack-design/05-api-design.md#411-进化对象配置仅配置后可自进化)：target 配置的端点、字段与错误码；本 issue 在其 body 与响应中增加两个字段。
- [06 §5.1 evolution_targets](../../../plans/fullstack-design/06-database-design.md#51-evolution_targets--可自进化的对象配置)：现有列、约束与 run 快照边界；本 issue 扩 target 表并在 run 创建期快照。
- [08 §9.5 进化对象配置页](../../../plans/fullstack-design/08-frontend-implementation.md#95-进化对象配置页evolutiontargets)：表单结构、必填校验与错误展示。
- [02 F19](../../../plans/fullstack-design/02-features.md)：进化对象配置的能力边界。
- [14 验证集与测试集测试工程 ID](../../../plans/fullstack-design/14-target-project-ids.md)：字段语义、target/run 列、API 校验、前端与原型规则；实现冲突时以该章为准。
- 实现冲突时以当前 `EvolutionTargetService` 的归一化与错误封装方式为准。

## 实现内容

- 数据库：新增迁移 `0013_target_project_ids.py`，为 `evolution_targets` 与 `evolution_runs` 各增加 `validation_project_id`、`test_project_id`（`VARCHAR(128)`，`NOT NULL DEFAULT ''`）；`domain.py` 与 `evolution.py` 同步列定义。
- 后端 target：`EvolutionTargetWrite` 与 `EvolutionTarget` 增加 `validation_project_id`、`test_project_id`；`EvolutionTargetRecord`、repository 的 insert/update/get/list 映射两列；`_normalize_write` 校验并归一化两个字段。
- 后端 run 快照：`LaunchTargetRecord` 暴露两个 ID；`LaunchService._run_values` 把它们写入 `evolution_runs`；`EvolutionRunRecord` 与 repository 的 `create_run`/`_run_record` 映射两列。
- 校验：trim 后非空；长度不超过 128；不允许任何空白字符与控制字符。失败抛 `AppError(422, PROJECT_ID_INVALID, "test project id is invalid")`，`details` 含 `field`（`validationProjectId` / `testProjectId`）与 `reason`（`project_id_required` / `project_id_format`）。
- 错误码：`ErrorCode` 增加 `PROJECT_ID_INVALID`；OpenAPI 错误响应描述同步。
- 契约：运行 `pnpm contract:generate`，更新 `packages/contracts/openapi.json` 与生成类型。
- 前端：`TargetFormDialog.vue` 增加两个 `ElInput`，放在“子目录/基线”行之后、启用开关之前，两列布局；表单模型、reset、必填校验、字段错误、emit 全部覆盖；`Index.vue` 的 `targetWrite` 与 `targetErrorMessage` 同步。
- 前端表格：`TargetTable.vue` 在“基线”与“状态”之间增加合并列“测试工程”，两行展示验证集/测试集；空值显示“未填写”。
- 表单文案：帮助文案说明“验证集与测试集分别对应外部测试平台的测试工程 ID”；历史行空值时提示“请补充后才能保存”。
- fixtures：`EvolutionTargetFixture` 增加两个必填字段；`fixtures/m2-synthetic/corpus.json` 的 evolutionTargets 补齐；seed 写入两列。
- 原型：`plans/14-15-ui-prototype/harness-evolution.html` 的新增与编辑浮窗增加两个必填字段与校验提示，配置列表增加“测试工程”合并列，保持 720px 两列表单布局。
- 文档：更新 05 §4.11、06 §5.1/§5.2、08 §9.5、02 F19；新增 `plans/fullstack-design/14-target-project-ids.md`；新增 Agent Note 记录字段语义与 target/run 双快照边界。
- 测试：API 创建、更新、列表、必填、格式、历史行；run 创建快照；repository 与迁移；Web 表单必填、回填、emit、错误与表格列；E2E 新增与编辑。

## 实施步骤

1. 先写失败测试：API 创建缺字段返回 422 `PROJECT_ID_INVALID`；纯空白、超长、控制字符、内部空白返回字段级错误；创建与更新后 GET 返回两字段；迁移后历史 target/run 为空串。
2. 加迁移与 ORM 列，更新 target record/repository 与 run record/create_run，跑数据库测试。
3. 扩展 service 模型与归一化，加错误码与 details，跑聚焦 API 测试。
4. 改 launch 快照，断言 run 两列来自 target 且后续 target 修改不影响已创建 run。
5. 运行 `pnpm contract:generate`，更新契约快照。
6. 改前端表单、reset、校验、emit、表格列与 Index 映射，补 Web 单测。
7. 更新 fixtures 与 seed，跑 fixtures 门禁。
8. 更新原型、05/06/08/02 与 14 章、Agent Note。
9. 跑聚焦测试、类型、lint、E2E、流程与文档门禁。

## 依赖与交付边界

- 依赖：m5-02（target CRUD API）、m5-03（target 配置 UI）。
- 交付边界：改 target 配置的表、API、契约、表单、表格、fixtures、原型与测试，并在 run 创建期增加两个快照列；不改变 run API/详情响应、评测 gateway、`EvalRequest`、`/catalogs/targets` 与启动向导。
- 兼容性：四列为增量列；历史 target/run 读回空串，写 target 要求非空；旧客户端不传字段会得到 422。
- 非目标：见文末。

## 独立验证

```sh
pnpm test:api -- tests/m5-02-target-config-api
pnpm test:db
pnpm --filter @harness/web exec vitest run src/pages/evolution/targets
pnpm test:e2e -- "m5 target configuration"
pnpm typecheck:api
pnpm typecheck:web
pnpm lint:api
pnpm lint:web
pnpm contract:check
pnpm verify:flow
pnpm verify:docs
```

- 创建缺少任一工程 ID 的 target 返回 422，`details.field` 指向缺失字段，DB 不落行。
- 创建带合法两字段返回 201，GET 列表返回相同值；DB 两列可查。
- 更新只改一个工程 ID 返回新值，另一个保持不变。
- 历史 target 在迁移后 GET 返回空串；编辑提交空值返回 422；补齐后保存成功。
- 用带两字段的 target 启动 run 后，`evolution_runs` 两列等于 target 值；修改 target 不影响已创建 run。
- 前端两个输入为空时不能提交；填写后 emit 的 body 含两个字段；编辑态回填；表格“测试工程”列展示两行。
- 全部类型、lint、E2E、契约、流程与文档门禁通过。

## 验收标准

- 新增进化对象浮窗显示“验证集测试工程 ID”“测试集测试工程 ID”两个必填输入，skill 与 agent 都有。
- 两个输入为空或纯空白时提交被阻止，字段下显示“请填写”；输入超长或含空白、控制字符时字段下显示格式要求。
- 编辑浮窗回填已保存的两个值；修改后保存，列表接口返回新值。
- `evolution_targets` 与 `evolution_runs` 在 SQLite 与 MySQL 迁移后都有两列，历史行值为空串；新 run 的两列来自创建时的 target。
- `POST` 与 `PUT` 缺少字段返回 422 `PROJECT_ID_INVALID`，`details.field` 为 `validationProjectId` 或 `testProjectId`。
- `GET /api/evolution/targets` 返回 `validationProjectId`、`testProjectId`。
- 配置列表“测试工程”列以两行展示验证集/测试集，历史空值显示“未填写”。
- 现有对象 CRUD、仓库/子目录/基线校验、启用开关与删除保护行为不变。
- 原型与实现表单的字段顺序、标签、必填标记和错误位置一致；列表列一致。
- 相关单测、E2E、类型、lint、契约、流程与文档门禁全绿。

## 门禁与 CI

- `pnpm test:api`、`pnpm test:web`、`pnpm test:db`、`pnpm test:e2e`
- `pnpm typecheck:api`、`pnpm typecheck:web`、`pnpm lint:api`、`pnpm lint:web`
- `pnpm contract:check`、`pnpm verify:flow`、`pnpm verify:docs`
- CI 全部 lane 通过，覆盖率不低于 80%。

## 非目标

- 不在本切片调用外部测试工程接口，不校验工程 ID 是否真实存在。
- 不改变 run API/详情响应、评测 gateway 或 `EvalRequest`；只增加 run 创建期快照列。
- 不把两个字段加入 `GET /api/catalogs/targets`、启动向导或运行详情页。
- 不拆成两个表格列；只增加合并的“测试工程”列。
- 不迁移或猜测历史 target/run 的真实工程 ID；历史值统一为空串，由管理员补齐。
- 不改变 `repoUrl`、`subDir`、`defaultRef` 的现有校验与错误码。
