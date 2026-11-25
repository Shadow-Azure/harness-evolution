# Agent Note: 第 6 步从落库 bundle 投影 round patch

Status: implemented

[English](2026-11-23-iteration-patch-projection.en.md) | 中文

## Problem

运行详情第 6 步把数据库 `round.patch` 原样交给 `StepRoundPatch.model_validate()`，而读模型只有 `file / lines / note`，且继承 `IdentityModel` 的 `extra="forbid"`。写侧已经两次扩容：`#436` 为暂停恢复增加 `overwrite`，`#488` 为 agent 编辑增加 `files[] / intent / report`，单文件时再合并 legacy 的 `file / lines / overwrite`。于是最新 run 的 patch 字典多出 4 个键，读取时抛 `extra_forbidden`，异常冒泡成 500 `INTERNAL`，前端把任何非 `STEP_NOT_READY` 错误统一显示为 `EVOLUTION_RUN_STEP_UNAVAILABLE`。生产上最新一次运行的「改了什么、评测涨了多少、commit 是什么」整块不可见。

同一条契约在两个地方各写一遍：写侧 `_stored_patch()` 决定落库形状，读侧用封闭读模型猜同一个形状。单文件 legacy 用例能过测试，多文件与新增审计字段没有进入读路径，所以 CI 全绿。

读模型恢复成 200 之后又暴露了第二个契约缺口：agent-edit 的 `files[].lines` 是**整文件**，而 `DiffView.vue` 仍按行首 `+` / `-` / `@@` 着色。2026-11-25 生产 run `01M8957ATHZX4K48K9PGXSVSVK` 第 4 轮因此把 478 行整文件里 147 行 Markdown 列表与 `---` 渲染成红色删除，真实 diff（72 行新增、0 行删除）只存在于 `candidate_committed` 事件里。`intent`、`report` 与 candidate 的真实 `unified_diff` 都已存在，却都没有进入第 6 步读模型。

## Decision

- 把「落库字典 → `PatchBundle`」的还原逻辑从 `git_candidate.py` 抽到 `round_patch.py` 的 `stored_bundle()`，写侧与读侧共用同一份解析规则；读侧不再直接校验原始字典。
- `StepRoundPatch` 改为 `{files: [{file, lines, overwrite}], note?, diff?}`；`_round_item()` 先还原 bundle，再显式投影成 DTO。`note` 只从原始字典读取，缺失或空白保持 `null`，与 legacy 语义一致。无法还原的 patch 返回 `patch: null`，不再让读取链抛异常。
- 写侧在 candidate commit 成功后把 `CandidateWorkspace.unified_diff` 写入 `round.patch.diff`；`PatchBundle.unified_diff` 只承载这份提交后的 git 真值，patch source 不提前填充。`stored_bundle()` 读回 `diff`，`_round_patch()` 把它拆成行数组。
- 历史轮次没有 `diff` 时，读侧按 `intent` 中 `report.status == "applied"` 的编辑合成 `-` / `+` / `@@` 变更块；没有 applied 编辑或没有 intent 时 `diff` 为 `null`。两种情况都不把 `files[].lines` 当 diff。
- `DiffView.vue` 改为 diff 优先：按 `diff --git` 切文件块，`@@` 标 hunk，内容行按 `+` / `-` 着色，`index` / `---` / `+++` 等文件头行不参与增删计数；`diff` 为 `null` 时显示中性整文件预览并明说“不对行着色”。
- 多文件 bundle 按 `files[]` 顺序原样投影，单文件 bundle 与历史 `{file, lines, note}` 都规整为一个 `files` 项；`files[]` 只作为无 diff 时的整文件预览，不再承担 diff 语义。
- 回归测试直接使用 `_stored_patch()` 的真实输出构造 1 文件、2 文件与 legacy 三种 round，断言 `steps/iteration` 返回 200 和 `patch.files` 内容；另加真实 diff 往返、applied/skipped 编辑合成的历史轮次、无 diff 无 intent 的 `null` 三种用例。E2E fixture 的已接纳轮次带真实 diff，历史轮次断言中性预览且红色删除行归零。

## Alternatives considered

- **用 `try/except` 把校验异常吞成 `patch: null`**：拒绝。能让 500 消失，但第 6 步失去 patch 预览，而 patch 正是该步的核心信息；这是把错误变成静默缺内容。
- **给 `StepRoundPatch` 开 `extra="ignore"`**：拒绝。当前单文件 run 能过，但多文件 bundle 仍缺必填的 `file / lines`，agent 编辑产生的轮次继续 500；它只延长旧形状的寿命，没有建立投影边界。
- **在读侧复制一份归一化逻辑**：拒绝。写侧和读侧各维护一份 `files`/legacy 解析，正是这次契约漂移的根因；共享 `stored_bundle()` 才能让后续扩容只有一处适配。
- **只改前端错误码或错误卡文案**：拒绝。错误码粒度可以另开 issue，但它不会让第 6 步显示轮次内容。
- **按 `overwrite` 判断后继续把 `files[].lines` 当 diff 着色**：拒绝。`overwrite` 只描述写入方式，整文件内容里的 `-` / `---` 与真实删除从字节上无法区分；继续着色就是这次误报的根因。
- **让前端从整文件猜 diff 或剥掉文件头**：拒绝。没有上一版内容，猜出来的 diff 会伪造变更；真实 diff 已由 git 产出并存在 candidate 上，没必要重算。
- **只把历史轮次改成中性预览、不落库新 diff**：拒绝。误报会消失，但新轮次仍看不到真实变更，`intent` 与实际 diff 的对照也继续丢失。
- **迁移历史 round 到统一新结构**：拒绝。旧 row 一直合法，读取侧本就应兼容；迁移会扩大改动面并带来一次性数据风险。

## Consequences

- 第 6 步对当前多文件 bundle、单文件 bundle 与历史 legacy 三种合法形状都返回 200；第四种不可还原形状降级为 `patch: null`，其余轮次字段照常返回。落库再增加读模型不用的字段时，读取链不会因为 `extra="forbid"` 而整步失败。
- `round_patch.py` 成为写读共享的还原缝：`git_candidate._patch_file/_patch_note/_patch_hash` 与 `stages._round_patch()` 都从 `stored_bundle()` 取事实，后续改存储形状只需改这一处。
- 无法还原的 patch 现在降级为 `patch: null`；轮次卡其余字段仍然显示。API 回归测试已覆盖这一形状；读取层暂不加告警日志，UI 上表现为 patch 预览缺失。
- `packages/contracts` 与 `05 §3.6` 已切到 `files[]`；使用旧 `patch.file` 的客户端必须读取 `files[0]`。仓库内只有 `DiffView.vue` 一处消费该 DTO，已同步；`DiffView` 对缺失 `files` 的响应也做了空数组兜底，跨越滚动发布窗口不会在渲染期抛错。
- 新轮次的 `patch.diff` 直接来自 candidate commit 的真实 git diff，页面只对内容行着色，文件头与元数据不进入增删计数；历史轮次用 applied 编辑合成变更块，没有可用数据时退回中性整文件预览，不再产生红色删除误报。
- `patch.diff` 在落库与响应中不截断（事件载荷仍按 20k 字符截断），所以整文件覆盖型轮次会多存一份 diff；这是保留真实审计面的代价，换来的是页面与 `candidate_committed` 不再各说各话。
- 生产验证需要一次部署；本 issue 不迁移数据、不改 patch 生成/评测/推送逻辑，也不统一前端错误码。
