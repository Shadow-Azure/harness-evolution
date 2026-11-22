# Agent Note: 真实浏览器 E2E 的超时上限按 runner 实测设定

Status: implemented

[English](2026-11-22-e2e-time-limit.en.md) | 中文

## Problem

真实浏览器 E2E（79 个用例，M1–M8）在 `scripts/run-e2e.mjs` 里有 10 分钟的内部上限。健康运行在本机约 8 分钟，但共享 GitHub runner 实测 8–13 分钟：2026-11-22 一天内多次在 600 秒处被杀（exit 124），而同一提交的 `pnpm test:e2e` 本地全绿。失败信息是「suite exceeded its time limit」，不是任何用例失败，维护者只能反复重跑，既浪费 CI 时间，也让「CI 红」失去诊断价值。

## Decision

- `scripts/run-e2e.mjs` 的内部上限从 600 秒提到 900 秒（`HE_E2E_TIMEOUT_MS` 默认值），仍可用环境变量覆盖。
- CI 的 e2e 步骤上限从 12 分钟提到 18 分钟，job 上限从 15 分钟提到 25 分钟，给 suite 上限留出 3 分钟与 10 分钟的余量。
- 上限仍是硬闸：真正的挂起在 15 分钟处被杀并返回 124，不把性能回归伪装成通过；只是把「慢 runner」与「用例失败」分开。
- 套件保持串行与原有性能断言；本决策只调整时间预算，不改测试内容。
- 2026-11-23 追加：单纯抬预算不能解释「TAP version 13 之后 15 分钟零输出」的挂起。`tests/support/runtime.mjs` 的 CDP WebSocket 握手与每条 CDP 命令现在都有 30 秒上限（`HE_E2E_CDP_TIMEOUT_MS` 可覆盖），`run-e2e.mjs` 加 `--test-timeout=180000` 兜底；CI 的 e2e 步骤失败/超时后重试一次。这样共享 runner 上偶发的 Chrome 握手停滞会变成一条具名失败并在重试中恢复，而不是吃掉整个套件预算。

## Alternatives considered

- **保留 10 分钟、失败就重跑**：事实证明确实能通过，但每次重跑要 10 分钟以上，且把「runner 慢」当成随机事件；维护者无法从失败信息判断是 flake 还是回归。
- **关掉 e2e 或按路径过滤**：会丢失 M1–M8 的真实浏览器覆盖，与「CI 必须执行测试」的仓库约束冲突。
- **并行化浏览器用例**：能压缩墙钟时间，但要重写共享浏览器/端口的 test harness，风险与工作量都远大于调预算；留作后续性能项。

## Consequences

- 真正的 E2E 挂起最多晚 5 分钟被发现（10 → 15 分钟），这是可接受的诊断延迟。
- 共享 runner 的慢启动不再被记为失败；失败的语义重新回到「用例断言失败」。
- 若套件继续增长、健康运行逼近 15 分钟，应优先并行化或拆分 lane，而不是继续抬上限。
