# 修复 case-tools 归因通道与显式结论 writer 的契约错位

[English](bugfix-case-tools-explicit-conclusion.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-60
milestone: bugfix
depends: []
priority: P2
status: ready
scope:
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/tests/**
  - .agents/**
  - plans/**
  - docs/**
adr: []
github:
  number: 608
  url: https://github.com/Shadow-Azure/harness-evolution/issues/608
```

## 背景

### 问题现象

`origin/main` 在 `744f4f57` 之后 `unit-tests-api` 持续红（4 个用例），main 自己的 push CI 同样失败，`ci-ok` 聚合红，所有 PR 被连带阻断：

- `tests/attribution/test_case_tools.py::test_only_platform_writer_chooses_paths_and_case_identity` —— `ValueError: platform writer rejected the report: usage: make_probe_report.py ... --input-badcase ... --bad-case-id`。
- `tests/m5-05-launch-wizard/test_launch_api.py::test_startup_claims_existing_binding_with_shared_provider` —— 期望 `(generation, 0)` 实得 `(generation, 1)`。
- `test_local_attribution_from_wizard_to_cluster[bubblewrap-bound-bubblewrap]` / `[case-tools-other-case-tools]` —— TimeoutError。

### 根因：两个各自为绿的 PR 在合并时语义冲突

- `f9ad7434`（PR #562，03:09Z 合入）新增 `apps/api/app/third_party_api/ai_agent/attribution_case_tools.py`（Linux 无 bwrap 时的 MCP 工具通道）与 `tests/attribution/test_case_tools.py`。该通道按**旧 writer CLI** 调用 `attribute-badcases/make_probe_report.py`：只传 `--probe_object` / `--probe_type` / `--attribute-type` / `--probe-description` / `--probe-analysis` 等。
- `744f4f57`（PR #589，06:21Z 合入）把 writer 改成**显式结论契约**：`--conclusion`、`--root-cause` 变为必填，新增可重复的 `--evidence-ref`，并同步改了 bubblewrap 路径的 `canonical_report` 与 SKILL 指令；但**没有**更新 `CaseTools`、`tests/attribution/case_cli_fixture.py`、`tests/attribution/test_case_tools.py`。
- PR #589 的 CI 跑在 02:03Z–02:16Z（head `6adde1d4`），当时 base 还没有 `f9ad7434` 的 CaseTools，因此全绿；4 小时后合入时 base 已包含 CaseTools，但仓库当时**没有 required status checks**，旧绿检查被直接采信（该配置缺口已由 ruleset `Protect main` 补齐，另见 merge queue issue）。

结果：case-tools 归因通道（以及 bubblewrap 测试用的 fixture CLI）仍按旧 CLI 调用新 writer，writer 以 usage 错误拒绝，归因批次失败，launch 用例超时。

### 影响

- 生产上 `HE_ATTRIBUTION_BWRAP_ENABLED=false` / 无 bubblewrap 的 Linux 归因路径不可用（`CaseTools.write_probe_report` 必然被 writer 拒绝）。
- main CI 红，所有 PR 无法合入。

## 目标

- `CaseTools` 适配显式结论 writer 契约：`ReportFields` 增加 `conclusion`（`attributed` / `non_target` / `inconclusive`，必填）、`root_cause`（必填）、`evidence_references`（可选列表），并把 `--conclusion` / `--root-cause` / 重复 `--evidence-ref` 传给 writer；保留 `probe_object` / `probe_type` / `object_version` / proposal 等可选参数的既有语义。
- 更新 `tests/attribution/case_cli_fixture.py`：sandbox 与 case-tools 两种 fixture 调用都提供新必填参数与证据引用。
- 更新 `tests/attribution/test_case_tools.py` 的字段与断言（结论、根因、证据引用进入报告）。
- 让 main 的 4 个失败用例恢复绿色；不改变 bubblewrap 路径与 writer 契约本身。

## 设计依据

- [07 §5.5.3](../../../plans/fullstack-design/07-backend-implementation.md)：提交通道与平台 writer 是确定性收货契约；writer 契约变更必须同步所有调用方。
- [attribute-badcases/make_probe_report.py](../../../attribute-badcases/make_probe_report.py)：显式结论 CLI 的唯一事实源（`--conclusion`/`--root-cause`/`--evidence-ref` 必填、`--probe_object` 与 `--object-version` 的跨字段规则）。

## 实现内容

- `attribution_case_tools.py`：
  - `ReportFields` 增加 `conclusion: Literal["attributed","non_target","inconclusive"]`、`root_cause: str`、`evidence_references: list[str] = []`；`extra="forbid"` 保持。
  - `write_probe_report` 参数拼接改为：`--conclusion`、`--root-cause`、每个 `--evidence-ref`；`attribute_type`/`probe_description`/`probe_analysis` 仍走 `--attribute-type`/`--probe-description`/`--probe-analysis`；`probe_object`/`probe_type` 走下划线形式，`object_version` 走 `--object-version`，proposal 走 `--proposal-*`；`detail_description` 走 `--detail-description`。
  - 读取 case 行的方式不变（仍由平台持有 `bad_case_id`）。
- `case_cli_fixture.py`：sandbox 分支的 writer 调用补 `--conclusion attributed --root-cause ... --evidence-ref L1`；case-tools 分支的 `report` 参数补 `conclusion`/`root_cause`/`evidence_references`。
- `test_case_tools.py`：成功用例断言 `conclusion`/`root_cause`/`evidence_references` 进入报告；`probe_object` 与选中对象不一致且缺 `--object-version` 仍应被 writer 拒绝；收据与符号链接防护断言保持不变。
- 文档：若 writer 契约在 docs 中有描述，补一句 case-tools 通道同样遵守显式结论契约。

## 实施步骤

1. 改 `ReportFields` 与 `write_probe_report` 的参数映射，跑 `test_case_tools.py`。
2. 改 `case_cli_fixture.py` 两处调用，跑 `test_launch_api.py` 的两个参数化用例。
3. 跑聚焦用例与 `pnpm test:api -- -k "case_tools or local_runtime or launch_api"`，确认 4 个失败用例恢复。
4. 跑 `pnpm lint:api`、`pnpm typecheck:api`、`pnpm test:gates`，提交并走 PR。

## 依赖与交付边界

- 依赖：无（`bugfix-57`/`bugfix-58` 等无关）。
- 交付边界：只改 `ai_agent/attribution_case_tools.py` 与相关测试 fixture/用例；不改 writer 契约、不改 bubblewrap/`local_attribution` 主路径、不改报告结构与业务判定语义。

## 独立验证

```sh
pnpm test:api -- -k "case_tools or local_runtime or launch_api"
pnpm test:api -- -k "m5_05 or attribution"
pnpm lint:api
pnpm typecheck:api
```

- 预期：`test_case_tools.py` 全绿；`test_launch_api.py` 的 `bubblewrap` 与 `case-tools` 参数化用例通过；`probe_reports` 行数与归因日志断言恢复；main 的 `unit-tests-api` 转绿。

## 验收标准

- `CaseTools.write_probe_report` 生成的新报告包含 `conclusion`/`root_cause`/`evidence_references`，writer 退出码 0。
- 4 个失败用例恢复通过；`tests/attribution` 与 `tests/m5-05-launch-wizard` 无回归。
- 不改变 writer 的必填/跨字段规则；`probe_object` 与选中对象不一致时仍要求 `--object-version`。
- 聚焦门禁与 `test:gates` 通过；无新增依赖。

## 门禁与 CI

- 命中：`pnpm test:api`、`pnpm lint:api`、`pnpm typecheck:api`、`pnpm test:gates`、`pnpm verify:flow`。
- CI 使用 fake/stub 与 fixture CLI，不触网、不依赖真实 `claude`。

## 非目标

- 不改 `make_probe_report.py` 的 CLI/报告结构；不恢复旧字段兼容。
- 不改 bubblewrap 主路径、`local_attribution` 的结论判定与聚类逻辑。
- 不放宽 `ReportFields.extra="forbid"` 或路径防护。
