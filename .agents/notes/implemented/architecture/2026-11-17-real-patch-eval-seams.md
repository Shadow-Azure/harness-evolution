# Agent Note: 真实 patch 与评测的可插拔接缝

Status: implemented

[English](2026-11-17-real-patch-eval-seams.en.md) | 中文

## Problem

自进化闭环里的 patch 与评测都是占位事实（占位 markdown 文件、FakeEvalGateway 占位分数）。闭环会真实落盘、真实 push、真实决策，但产物不是真实修复，评测分数也不是真实平台结论（09 R11 的误当真实结论风险）。同时两个接缝都没有扩展位：换生成策略或接真实评测平台都要改业务代码。

## Decision

patch 生成收敛到 `service/evolution/patch_source.py` 的 `PatchSource` 接缝：工厂 + Protocol + 子类。占位 source 保持 V1 行为与标注；新增 `MinimalConfigPatchSource` 针对 bad case 证据文本做确定性规则匹配，向目标仓库的 `config/<target>.json` 合并一个参数（timeout/retry/索引校验/权限检查），以 `Patch.overwrite` 语义真实落盘并进 candidate commit。写进的键名/键值是 harness 侧约定，不是目标仓库配置 schema，真实目标是否接受以评测平台实测为准；关键词表序即优先级，规则表外置成配置留给真实平台接入时再做。选择按 run 快照 `eval_config["patchMode"]` 优先、`HE_PATCH_SOURCE_MODE` 兜底；显式未知 mode 报 `ConfigError`，不静默降级。「改动」段描述由 source 提供（`patch` 列持久化 `note`），接纳后重建 message 时保持真实描述。

评测接入升级为注册表驱动工厂 `build_eval_gateway_factory(settings)`：`third_party_api/eval_gateway/factory.py` 的 `EvalGatewayFactory` 持有 provider 注册表，`BaseEvalGateway(ABC)` 承载冻结配置、鉴权、超时与错误边界，平台子类只做协议与字段映射。内置 `fake` 与 `ai-eval-platform` 两个子类；run 快照 `eval_config["mode"]` 优先、`HE_EVAL_MODE` 兜底；`HE_EVAL_BASE_URL`/`HE_EVAL_API_KEY` 缺失或 `apiKeyRef` 悬空时报 `EvalGatewayConfigError`，由既有 `blocked(stage=eval)` 路径吸收（首次提交、轮询、基线与重试重提同语义），不新增 event_type。创建期快照对 `apiKeyRef` 只存变量名并做脱敏豁免（该键不是凭据，空白引用整键移除），同时把 `validationProjectId`/`testProjectId`/`primaryMetricKey`/`subDir` 写入快照，向导 `eval` 覆盖优先。网关 `get_result` 只返回测量值（主指标、方向、原始指标项），裁决在 service 层；轮询请求自身的瞬态失败（网络超时/连接失败/HTTP 429/5xx）由网关层标注 `retryable`，轮询侧只消费该布尔并推迟 `next_poll_at`，既有 2h `eval_timeout` 兜底封顶；4xx 等语义错误才判评测失败转 blocked。旧的通用 `/evals` `HttpEvalGateway` 与 `EvalMapper` 随虚构协议删除。

用户拍板的生产配置通道：`HE_EVAL_*` 经 GitHub Secrets 在 `Deploy` 流水线注入服务器 `/opt/harness/shared/.env`（secrets 未配置时步骤跳过）；issue #244 scope 相应扩入 `deploy/**` 与 `.github/workflows/**`。密钥不落仓库与数据库。

## Alternatives considered

把真实修复做成 LLM 生成代码：超出"最小配置变更"边界且不可确定性验收，保留为后续 patch source 子类。把密钥明文存进 run 快照：`eval_config` 会落库并被事件/日志读出，改为 apiKeyRef 间接引用。在 gateway 缺配置时退回 fake：会把配置错误伪装成占位结论，违反 R11。让 deploy 流水线在 secrets 缺失时失败：阻塞既有部署，与 opt-in 语义冲突。

## Consequences

换生成策略 = 新增一个 `PatchSource` 子类 + `.env`/run 配置一行；接真实评测平台 = 新增 `BaseEvalGateway` 子类并在工厂注册 + `.env` 配置，业务代码不动。终评落库（`write_final`）在 同 事务把游标推进到 `5+M+1`，完成的 run 终评步从此可读；retry 的重入只更新终评行。真实闭环（真实 git push、真实 HTTP 评测、真实决策）在 `tests/m12-03-real-patch-eval/test_real_loop_evidence.py` 以本地 bare remote 固化，可重复执行。默认配置下 fake 模式仍走同一套裁决（基线 80、候选 85 时首轮接纳，后续平票拒绝）；`docs/deployment.md` 预算 740→800 用于新增「评测配置注入」节（搬层与压缩后仍不足，理由见 PR 描述）。
