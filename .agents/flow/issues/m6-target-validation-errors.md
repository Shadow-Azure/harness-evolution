# 进化对象配置：展示具体校验原因、修改建议与 git 失败输出

[English](m6-target-validation-errors.en.md) | 中文

```yaml flow
kind: issue
id: m6-19
milestone: m6
depends:
  - m5-02
  - m5-03
  - m6-07
priority: P1
status: ready
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - docs/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 185
  url: https://github.com/Shadow-Azure/harness-evolution/issues/185
```

## 背景

### 问题是什么

“新增进化对象”和“编辑进化对象”共用同一个浮窗，一次提交对象名、仓库地址、子目录和基线（`defaultRef`）四项。后端只要任一校验失败就统一返回 `422 REPO_INVALID`，`message` 固定为 `repository or ref is invalid`，`details` 为空；前端又把所有 `REPO_INVALID` 替换成同一句“仓库或 ref 无效，请检查地址、子目录与基线”，并且只在表单底部渲染一条 `server-error`。用户因此知道“有问题”，却不知道是哪个字段、哪条规则、该怎么改。

### 问题现象

- 仓库地址使用 `http://`、包含用户名密码、带 query/fragment 或端口非法时，看到同一句通用错误。
- 子目录使用绝对路径、包含 `..` 或以反斜杠分隔时，看到同一句通用错误。
- 基线包含非法字符、`..`、以 `.` 或 `/` 结尾时，看到同一句通用错误。
- 远端仓库不可达、无读取权限、DNS 失败或超时时，看到同一句通用错误；`git ls-remote` 的实际 stderr 在 `_run` 中被整段丢弃。
- 基线分支或 tag 在远端不存在（`git ls-remote --exit-code` 退出码 2）时，无法与“仓库不可达”区分。
- 对象名为空、超长或含控制字符时，后端同样返回 `REPO_INVALID`，前端文案却引导用户检查仓库、子目录和基线。
- 子目录格式合法但目录实际不存在时，保存成功，直到 run 准备阶段才报 `target subdirectory is missing`。

### 问题影响

- 管理员需要反复试错，最常见的地址格式、ref 拼写和权限问题无法一次定位。
- “请检查地址、子目录与基线”把三个字段混在一起，且子目录存在性并未在保存时校验，文案承诺了不存在的检查。
- 远端失败没有任何命令执行信息，无法判断是 DNS、TLS、认证、仓库不存在还是 ref 不存在。
- 现有测试把通用文案固化成预期，后续修改缺少字段级回归断言。

### 根因分析

- 后端三层收敛：`_normalize_text`、`_validate_sub_dir`、`_validate_repo_url` 的所有规则失败都抛同一个 `_repo_invalid()`；`_validate_remote` 捕获 `RepoInvalid` 后也映射成同一个 `AppError`，`details` 为空。
- `GitProcessResult` 已经保存 `stdout` 和 `stderr`，但 `SubprocessGitRemote._run` 在非零退出、超时或 `OSError` 时直接抛 `RepoInvalid`，没有携带退出码和输出。
- 前端 `targetErrorMessage` 只按错误码分支，不读取 `ApiError.details`；`TargetFormDialog` 只接收一个 `serverError` 字符串，没有字段级错误通道。
- 现有 Agent Note 把“不含 stderr、凭据或路径”作为安全边界，但没有区分“不可展示的原始输出”和“可脱敏展示的诊断摘要”。

### 建议

- 保持 `REPO_INVALID` 错误码不变，在 `details` 中增加 `field` 与 `reason`，前端按 reason 映射原因和建议，并把错误落到对应字段。
- 远端失败时在 `details.command` 中返回命令名、退出码和有界脱敏后的 `output`；只对 admin 的 create/update 返回，member 可读的 versions 接口不返回。
- `output` 复用运行日志的脱敏链路：去 token、Bearer、URL userinfo、私钥和 provider key，去控制字符，替换本机绝对路径，并按行数与字节数截断。
- 保存时不 clone 仓库校验子目录存在性；表单明确说明“目录存在性在启动运行时校验”。
- 用参数化测试覆盖每类 reason、远端退出码和脱敏边界；前端覆盖字段锚点、建议文案、技术输出块和无 details 回退。

## 目标

- `REPO_INVALID` 返回可区分的 `field` 和 `reason`，前端在对应字段下显示具体原因与修改建议。
- 远端命令失败时，管理员能在浮窗中看到有界、脱敏后的实际 git 输出和退出码。
- 对象名、仓库地址、子目录、基线四类错误不再共用一句“仓库或 ref 无效”。
- 无 `details` 的旧响应仍回退到现有通用文案，保持兼容。
- 表单文案和文档说明子目录存在性的校验时机，不再暗示保存时会检查目录。

## 设计依据

- [plans/fullstack-design/05-api-design.md §4.11](../../../plans/fullstack-design/05-api-design.md#411-进化对象配置仅配置后可自进化)：`REPO_INVALID` 表示仓库或 ref 不可用，保存与 versions 共用该错误。
- [plans/fullstack-design/08-frontend-implementation.md §9.5](../../../plans/fullstack-design/08-frontend-implementation.md#95-进化对象配置页evolutiontargets)：保存前做必填校验，仓库、ref、subDir 的合法性由后端返回 `422 REPO_INVALID`，表单展示错误。
- [2026-10-27-evolution-target-config.md](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/architecture/2026-10-27-evolution-target-config.md)：现有安全边界要求 `REPO_INVALID` 不含 stderr、凭据或路径；本 issue 将其细化为“admin 写接口返回有界、脱敏、去路径的 git 输出，读接口不含”。
- 实现冲突时以当前 `GitRemote` 校验语义和上述安全边界为准。

## 实现内容

- 后端 `service/evolution/targets.py`：引入字段与原因的封闭集合，把每条本地规则映射到 `field` 和 `reason`，保持 `422 REPO_INVALID` 与现有 message 不变。
- `field` 取值：`objectName`、`repoUrl`、`subDir`、`defaultRef`；`reason` 取值：`object_name_invalid`、`repo_url_format`、`repo_url_credentials`、`sub_dir_format`、`ref_format`、`ref_not_found`、`repo_unreachable`、`git_timeout`、`git_unavailable`。
- 后端 `third_party_api/git/remote.py`：`RepoInvalid` 携带 `reason`、`exit_code`、`stderr`；超时映射 `git_timeout`，`OSError` 映射 `git_unavailable`，退出码 2 映射 `ref_not_found`，其他非零映射 `repo_unreachable`；`list_tags` 不产生 `ref_not_found`。
- 后端 `utils/redaction.py`：新增命令输出清洗函数，复用 `redact_text`，替换 POSIX/Windows 绝对路径，保留 URL 路径，去控制字符，按末尾 40 行和 4096 字节截断。
- 前端 `pages/evolution/targets/Index.vue`：解析 `details`，把 reason 映射为 `{field, message, suggestion, command}`；未知 reason 或无 details 回退到通用文案与检查清单。
- 前端 `pages/evolution/targets/components/TargetFormDialog.vue`：接收结构化服务端错误，在对应字段下显示红字并设置 `aria-invalid`/`aria-describedby`；提交失败后聚焦第一个错误字段；字段修改后清除该错误；命令失败时渲染可展开、可滚动的等宽输出块。
- 文档与 Note：更新 05 §4.11 的错误明细形状、08 §9.5 的字段级错误与“子目录运行时校验”说明，并更新 Agent Note 中关于 stderr 的安全边界。
- 测试：后端参数化字段/原因、远端退出码、脱敏与截断；前端 reason 映射、字段锚点、技术输出块、无 details 回退；E2E 更新不可达仓库断言。

新增的诊断字段不改变错误码，线上响应形状如下：

```json
{
  "error": {
    "code": "REPO_INVALID",
    "message": "repository or ref is invalid",
    "details": {
      "field": "repoUrl",
      "reason": "repo_unreachable",
      "command": { "name": "git ls-remote", "exitCode": 128 },
      "output": "fatal: unable to access 'https://...': Could not resolve host: ..."
    }
  }
}
```

## 实施步骤

1. 先补失败测试：每类本地规则返回对应 `field`/`reason`，远端退出码 2/128、超时、`OSError` 分别映射，脱敏后的输出不含凭据与本机路径。
2. 在后端 target service 引入 `field`/`reason` 封闭集合，逐条替换 `_repo_invalid()` 调用点。
3. 在 git remote 边界携带退出码和 stderr，并在 target service 中组装 `details.command` 与 `details.output`。
4. 在 redaction 工具中实现命令输出清洗与截断，覆盖 URL 路径保留和本机路径替换。
5. 改造前端错误映射、字段锚点、聚焦/清除行为和 git 输出块，补 web 单测与 E2E。
6. 更新 05/08 文档与 Agent Note，运行聚焦测试、类型、lint、流程和文档门禁。

## 依赖与交付边界

- 依赖：m5-02、m5-03、m6-07。
- 交付边界：只改 target 配置保存错误的结构化明细、前端展示和相应测试；不改 git 调用方式、错误码集合或子目录的运行时校验。
- 兼容性：`details` 为增量字段；无 details 的旧响应和旧测试保持可用。

## 独立验证

```sh
pnpm test:api -- tests/m5-02-target-config-api
pnpm --filter @harness/web exec vitest run src/pages/evolution/targets
pnpm typecheck:api
pnpm typecheck:web
pnpm lint:api
pnpm lint:web
pnpm test:e2e -- "m5 target configuration"
pnpm verify:flow
pnpm verify:docs
```

- 本地规则参数化用例逐条断言 `field` 与 `reason`，且 `details.output` 为空。
- 远端不可达用例断言 `reason=repo_unreachable`、退出码 128，`output` 不含 token、URL userinfo 或本机绝对路径。
- ref 不存在用例断言 `reason=ref_not_found`、退出码 2，前端提示与“仓库不可达”不同。
- 前端用例断言字段下红字、汇总文案、git 输出块、无 details 回退和字段修改后清除。
- 全部类型、lint、E2E、流程与文档门禁通过。

## 验收标准

- 仓库地址为 `http://`、含用户名密码、带 query/fragment 或端口非法时，`repoUrl` 字段下显示格式/凭据类错误与修改建议，不显示 git 输出块。
- 子目录为绝对路径、含 `..` 或反斜杠时，`subDir` 字段下显示相对路径要求。
- 基线含非法字符、`..` 或以 `.`/`/` 结尾时，`defaultRef` 字段下显示合法示例。
- 远端仓库不可达时，`repoUrl` 字段与汇总显示“无法访问仓库”，技术详情显示退出码和脱敏后的 git 输出。
- 基线分支或 tag 不存在时，`defaultRef` 字段显示“仓库可达但找不到该 ref”，技术详情显示退出码 2，且不出现“检查子目录与基线”的通用句。
- 对象名为空、超长或含控制字符时，`objectName` 字段显示名称规则，而不是仓库/ref 文案。
- 编辑浮窗与新增浮窗行为一致；422 后浮窗保持打开且输入不丢失。
- 服务端没有 `details` 时，前端回退到现有通用文案并给出四项检查清单。
- 表单子目录帮助文案明确“格式保存时校验，目录存在性启动运行时校验”。

## 门禁与 CI

- `pnpm test:api`
- `pnpm test:web`
- `pnpm typecheck:api` / `pnpm typecheck:web`
- `pnpm lint:api` / `pnpm lint:web`
- `pnpm test:e2e -- "m5 target configuration"`
- `pnpm contract:check`
- `pnpm verify:flow`
- `pnpm verify:docs`
- CI 全部 lane 通过，覆盖率不低于 80%。

## 非目标

- 不新增或重命名错误码，`REPO_INVALID` 保持稳定。
- 不在保存时 clone 或拉取仓库校验子目录存在性；目录存在性仍由 run 准备阶段校验。
- 不向 member 可读的 versions 接口返回 git 原始输出。
- 不做任意未保存 `repoUrl` 的浏览器探测。
- 不把 git 输出持久化到数据库或运行事件。
- 不重构整个配置页、启动向导或 git 工作区实现。
- 不改变 `git ls-remote` 的 argv、超时和非交互约束。
