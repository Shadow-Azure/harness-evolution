# 归因工作目录

[English](README.en.md) | 中文

本目录记录本地 Agent 每次归因实际使用的输入和产出的报告。开发环境的默认根目录是仓库的 `attribute/`，生产环境默认使用 `HE_DATA_DIR/attribute/`；管理员可用 `HE_ATTRIBUTION_PACKAGE_DIR` 指定绝对路径。下列路径相对 `<workspace_id>/`。运行数据由 API 写入，不入 Git。

## 目录结构

```text
<workspace_id>/
├── attribute_skill/
│   ├── uploads/<package_id>/
│   └── snapshots/<skill_hash>/
│       ├── manifest.json
│       └── skill/{SKILL.md,make_probe_report.py,...}
├── attribute_source/
│   ├── <definition_key>/definition.md
│   └── snapshots/<source_hash>/attribute_source.md
├── attribute_input/
│   ├── sessions/<session_key>/<evidence_hash>/
│   │   ├── session_tree.json
│   │   ├── traces.json
│   │   └── trace_coverage.json
│   └── batches/<batch_id>/<case_key>/
│       ├── input_badcase.json
│       └── manifest.json
└── attribute_output/<batch_id>/<case_key>/
    ├── attempt-<random>/
    ├── logs/<attempt>/attribute_log.json
    ├── attribute_log.json
    └── probe_report.json
```

## 批次、重算和缓存

| 触发方式 | batch_id | 文件行为 |
| --- | --- | --- |
| 新增或变更对象绑定，后台分析当前 Badcase | 绑定代际 `binding_generation` | 同一批次处理多个 Session、多个 Badcase，无需创建自进化 Run |
| 向导关闭缓存，选择空间 Skill 重新归因 | 新建自进化 Run 的 ID | 为本次 Run 创建输入和输出，保留此前的报告和对象绑定 |
| 一个批次失败后重试 | 原批次 ID | 继续使用该 case 已冻结的输入；再次执行 Claude 时创建新的临时 attempt |
| 向导开启缓存 | 关联已有报告 | 缓存命中沿用原报告的输入和批次；缺报告的 Badcase 跳过 |

目录名默认使用原 Session ID 和 Badcase ID。含路径分隔符等特殊字符或超过 128 字符时，使用 `~` 加原 ID 的 UTF-8 SHA-256；原值保存在输入清单中。

## 输入如何生成

1. 整棵 Session 树中有目标类型和名称的调用或节点即入选，版本未知或不同均可。每条 Badcase 单独生成输入。`input_badcase.json` 中的 `selected_target` 是分析对象，`bad_cases[0]` 保留问题上报对象、位置和元数据。
2. 一次 Runner 调用内，同一 Session 的待处理 case 共享一次证据读取。`session_tree.json` 保存已归一化的 Agent 节点及事件；`traces.json` 以 Agent ID 为键保存已采集的脱敏轨迹。`trace_coverage.json` 的 `available_agent_ids` 和 `missing_agent_ids` 列出有非空轨迹的节点和缺轨迹的已知节点。`available`、`partial`、`normalized_events_only` 分别表示已知节点都有轨迹、部分缺失、只有归一化证据。覆盖状态反映轨迹是否存在，消息内容仍可能截断。补采或树变更后，新分析可生成新的证据版本。
3. 保存 Git Agent 或 Skill 对象时，平台从选定提交读取定义，按原文哈希存入 `attribute_source/<definition_key>/definition.md`。绑定批次固定该提交与文件，执行时校验并脱敏。默认归因 Skill 来自平台内置包，自定义 Skill 来自当前空间上传包；同一对象绑定批次首次解析 Skill 时固定快照，包含包内文件、平台脚本、执行约定、Agent 和模型身份。向导关闭缓存并选择当前绑定包时，使用同一份快照重新分析。显式选择其他包时，仅为本次 Run 冻结所选包。
4. 调用 Agent 前原子发布输入目录。清单记录工作空间、批次、触发来源、Badcase、Session、对象版本、Skill 及各项哈希。重试复用并校验该归档；多个批次可引用同一份 Session 证据或提示词。

## Claude 的工作目录与报告

后台与向导用 `run_skill` 执行冻结的 Provider、模型和 Skill，提示词为 `/<skill_name> input_badcase.json，请分析并生成归因报告`。Linux 默认用 bubblewrap，macOS 用 Seatbelt，从 `.claude/skills/<skill_name>/`（别名 `.cac/skills/`）加载 Skill。仅 Linux 显式设 `HE_ATTRIBUTION_BWRAP_ENABLED=false` 时，Claude 才接收冻结的 `SKILL.md` 原文，用 `read_evidence` 分页读取五份输入及 `skill/` 资料，用 `write_probe_report` 以本条 ID 和固定路径调用平台脚本。每次尝试独享 HOME。两种模式均核验回执、按原始输入重算后入库。

`attribute_log.json` 记录最近一次结果，`logs/<attempt>/` 保留历史。`execution.executionMode` 标明 `case-tools`、`bubblewrap` 或 `seatbelt`。日志包含提示词、输入清单、Claude 会话 ID、可见对话、工具调用和用量。主会话限读 8 MiB，见 `transcript.status`。`report_validated` 表示复核通过，入库查数据库。

## 从报告查回输入

1. 从 `attribute_output/<batch_id>/<case_key>/probe_report.json` 取相同的两个路径段，打开 `attribute_input/batches/<batch_id>/<case_key>/manifest.json` 及同目录的 `input_badcase.json`。
2. 取清单的 `sessionId`（按上述规则转换为目录名）和 `evidenceHash`，到 `attribute_input/sessions/<session_key>/<evidenceHash>/` 查看当时的树、轨迹和覆盖清单。
3. `gitSource` 记录仓库和提交。绑定批次另存文件路径；Run 另存对象子目录，并按启动时解析的提交读取原文。`definitionKey` 定位定义原文；`sourceHash` 定位当次模型看到的提示词副本。用 `skill.snapshotHash` 到 `attribute_skill/snapshots/` 查看实际使用的 Skill 文件和模型身份。
4. 用数据库报告的 `execution_manifest.contextSnapshotHash` 对照输入清单的 `inputHash`，用 `execution_manifest.skill.contentHash` 对照 `skill.snapshotHash`。SQLite 可按数据库报告 ID 查询批次来源：

```sql
SELECT p.workspace_id, p.session_id, a.bad_case_id,
       COALESCE(p.binding_generation, p.created_run_id) AS batch_id,
       p.attribution_skill_name
FROM probe_reports AS p
JOIN bad_case_analysis AS a ON a.probe_id = p.probe_id
WHERE p.probe_id = :probe_id;
```

查询参数 `:probe_id` 取平台数据库的报告 ID。脚本在 `probe_report.json` 中生成的 `probe_id` 由 Session、归因对象和 Badcase 组成，同一条 Badcase 重算时可能重复。

`sourceHash` 是脱敏提示词 UTF-8 字节的 SHA-256。`evidenceHash` 对三个证据文件的“文件名 → 字节 SHA-256”映射做规范 JSON 哈希；`inputHash` 对五个运行时输入的“文件名 → 实际文本”映射做规范 JSON 哈希。历史报告继续可读，启用归档前的报告可能没有对应的输入清单。备份和清理时请按工作空间保留数据库与这些共享快照，删除仍被清单引用的快照会导致重试校验失败。
