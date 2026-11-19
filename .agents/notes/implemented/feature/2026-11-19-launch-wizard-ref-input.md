# Agent Note: 启动向导版本改为输入优先组合框

Status: implemented

[English](2026-11-19-launch-wizard-ref-input.en.md) | 中文

## Problem

「启动自进化」第 1 步的版本字段只能从 tag 下拉中选择。用户无法在工作分支或未打 tag 的 commit 上先验证自进化，必须额外打 tag 才能启动；而进化对象配置的 `defaultRef` 明确允许分支或 tag，保存后却不一定出现在启动向导里（当仓库已有 tag 时，分支基线会被 tag 列表遮住）。V2 原型与 `08 §9.2` 当时也把版本写成 tag 列表，因此问题同时存在于原型、设计文档和生产实现。

## Decision

- V2 原型的启动向导版本字段改为输入优先的可编辑组合框：输入框本身就是 `targetVersion`，下拉只提供当前 target 的 tag 与 `defaultRef` 作为建议，不要求用户点选建议项。
- 默认值取 `defaultRef`，没有 `defaultRef` 时取第一个 tag；`defaultRef` 是分支且不在 tag 列表时，仍作为「基线」建议出现，不再被强制改成 tag。
- 点「下一步：关联 Session」和最终「启动自进化」时先校验 git ref 格式：非空、≤96 字符、无空白/`..`/`@{`/`~^:?*[` 等非法字符，不以 `-`、`/`、`.` 或 `.lock` 结尾；失败停在第 1 步并显示字段错误。格式通过后，服务端用 git 判定该 ref 在仓库中是否存在：缓存 mirror 上执行 `git rev-parse --verify <ref>^{commit}`，远端 ref 缺失时按需刷新 mirror；tag、分支和 commit 都必须解析到 commit。不存在返回 `TARGET_CONTENT_UNRESOLVED`（reason `ref_not_found`）；仓库不可达/超时也走同一错误（reason `repo_unreachable` / `content_timeout`），都回到第 1 步。存在后再解析该 ref 下的 `SKILL.md` / `AGENT.md` 并计算 body hash；不得回退到 tag 猜测。
- 版本身份仍是 body hash；tag 只是建议与显示值，不改变匹配和缓存语义。生产 `LaunchWizard.vue` 已按同一模式实现：输入框 + tag 建议菜单，输入值直接作为 `targetVersion` 提交；原型里的示例 ref 校验仍是演示，生产由服务端 git 校验。
- 同步更新 `plans/fullstack-design/08 §9.2`、`05 §4.11`、`15` 与 `design-v2`，明确 `versions` 端点只返回 tag 建议，`targetVersion` 接受 tag、分支名和 commit SHA。

## Alternatives considered

- **保持 tag-only，要求先打 tag**：拒绝。它把版本管理成本转嫁给用户，也无法解释对象配置页为什么允许分支或 tag；对未发布提交更不可用。
- **保留下拉，额外加一个「自定义」输入框**：拒绝。两个控件会让同一个语义出现两条路径，默认值和错误归属都更难解释；输入优先组合框更直接。
- **输入时即时校验并逐字符报错**：拒绝。用户输入分支名的中间状态必然短暂非法，逐字符报错会制造噪音；在「下一步」和最终启动两个真正的提交点校验即可。
- **在原型里模拟服务端 ref 存在性**：拒绝。原型没有仓库数据，伪造拒绝会掩盖真实的服务端解析语义；原型只演示格式校验与交互，存在性由服务端负责。

## Consequences

- 原型可以输入 `main`、`feature/foo`、`a3f9c21`，同时仍可从下拉选择 tag；格式非法或示例仓库中不存在的 ref 在同一位置显示错误，不会进入第 2 步。生产 `LaunchWizard.vue` 使用输入框 + 建议菜单提供 tag 建议，输入值在失焦/提交时保留；服务端 `TARGET_CONTENT_UNRESOLVED`（`ref_not_found` / `repo_unreachable`）回到第 1 步。
- 设计文档不再承诺「版本 = tag 列表」；后续生产实现可以直接复用对象配置页已经采用的输入优先组合框模式。
- 生产 `LaunchWizard.vue` 已按本决策实现；原型与实现的建议来源一致（`defaultRef` + tag），但生产存在性校验来自真实仓库，不使用原型示例 ref。
- 校验规则与后端 `TARGET_CONTENT_UNRESOLVED` / `REPO_INVALID` 的边界仍需在生产实现时补齐测试：格式错误由前端拦截，ref 不存在或内容无法读取由服务端返回并回到第 1 步。
