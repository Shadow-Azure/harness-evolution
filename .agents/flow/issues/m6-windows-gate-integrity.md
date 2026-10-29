# Windows 本地门禁假绿与 verify-web-style 兼容修复

[English](m6-windows-gate-integrity.en.md) | 中文

```yaml flow
kind: issue
id: m6-11
milestone: m6
depends:
  - m6-05
priority: P2
status: backlog
scope:
  - scripts/**
  - .agents/flow/**
  - .agents/notes/**
  - docs/**
adr: []
github:
  number: 163
  url: https://github.com/Shadow-Azure/harness-evolution/issues/163
```

## 背景

`scripts/` 下 22 个门禁/工具脚本的 CLI 入口守卫写成 ``if (import.meta.url === `file://${process.argv[1]}`)``。该比较是 POSIX-only：`import.meta.url` 是三斜杠正斜杠的 `file:///D:/...` 形态，模板串拼出的却是两斜杠反斜杠路径（`file://D:\...\x.mjs`），Windows 上恒假——直接 `node scripts/xxx.mjs` 时主块静默跳过、exit 0。于是 Windows 本机的 `pnpm verify:web-style`、`pnpm verify:docs`、`pnpm verify:flow` 等一律假绿（no-op exit 0），"本地跑过门禁"无法自证；CI 全部 `runs-on: ubuntu-latest`，守卫在 Linux 上成立，CI 结果不受影响，但 Windows 开发者的本地防线形同缺席。m6-05（GitHub #118）当年已记录该缺陷并在非目标里承诺"另立 issue"，至今没有落地。另有独立一层：`scripts/verify-web-style.mjs:22-28` 经 runner 修好入口后仍跑不了——主块用 `new URL(path, sourceRoot)` 拼文件 URL，而 Windows 上 `readdir(…, { recursive: true, withFileTypes: true })` 给出的 `entry.parentPath` 是带反斜杠的绝对路径，拼出的字符串以 `D:` 开头，被 URL 解析器当成 `d:` 协议，抛 `TypeError [ERR_INVALID_URL_SCHEME]`。

## 目标

- 22 处入口守卫统一为跨平台写法 ``import.meta.url === pathToFileURL(process.argv[1]).href``（或抽公共 `isMain()` 工具逐处替换），Windows 上直接执行脚本能真实进入主块。
- `pnpm verify:web-style` 在 Windows 上可真实执行到出结果：文件路径经 `pathToFileURL(path.join(entry.parentPath, entry.name))` 转 URL，不再把反斜杠绝对路径喂给 `new URL`。
- Windows 本地门禁恢复防线意义：`pnpm verify:*` 系列在本机跑出与 CI 同构的真实结果，假绿路径消失。

## 设计依据

- [plans/2026-10-29-pr160-review.md §6-1/§6-2](../../../plans/2026-10-29-pr160-review.md)：22 处守卫的波及面统计与 Windows 本机实测证据（no-op exit 0、`ERR_INVALID_URL_SCHEME` 栈）。
- `scripts/contract.mjs:259` 与 `scripts/performance-report.mjs:73`：仓库内已有的 `pathToFileURL(...).href` 安全守卫范本。
- [m6-windows-dev-entry.md](m6-windows-dev-entry.md)：m6-05（GitHub #118）非目标中"另立 issue"的承诺出处。

## 实现内容

- 统一 22 处守卫为 ``import.meta.url === pathToFileURL(process.argv[1]).href``（参照 `scripts/contract.mjs:259`，可加 `process.argv[1] &&` 前置）；若重复成本过高，抽公共 `isMain()` 工具逐脚本替换。
- `scripts/verify-web-style.mjs:27-28` 一行修复：改用 `pathToFileURL(path.join(entry.parentPath, entry.name))` 构造读取路径与 URL。
- `pnpm test:gates` 自测试纳入 verify-web-style 的 Windows 冒烟断言：注入含字面色的样本、断言门禁报红，防"入口可达但门禁主体没跑"的回归。
- 处置 `.tmp/run-gate.mjs`：守卫修复后它失去存在意义，按需转正为 `scripts/` 正式工具或直接删除。

## 实施步骤

1. 定稿守卫写法（内联 `pathToFileURL` 或公共 `isMain()`），逐脚本替换 22 处，只改"主块是否可达"，不动任何判定逻辑。
2. 修 `verify-web-style.mjs` 的 `entry.parentPath` URL 拼接（一行）。
3. 在 `scripts/gates.spec.mjs` 补 Windows 守卫可达性断言与 web-style 冒烟样本。
4. Windows 开发机按独立验证逐条实测，随后处置 `.tmp/run-gate.mjs`。

## 依赖与交付边界

- 依赖：m6-05（Windows 开发入口已可用；本 issue 兑现其"另立 issue"承诺）。
- 交付边界：仅 `scripts/` 的入口守卫与 Windows 路径兼容、相应自测试与流程文档同步；不改变任何门禁的判定语义与 CI 工作流。

## 独立验证

```sh
pnpm verify:web-style
```

- Windows 上有真实输出（`verify-web-style: Vue components use token colors only`），不再是静默 no-op；对注入字面色的临时样本报红。

```sh
pnpm verify:flow
pnpm verify:docs
```

- 两者在 Windows 上有真实输出且通过（修复前静默 exit 0）。

```sh
pnpm test:gates
```

- 全绿，含新增的守卫可达性断言。

## 验收标准

- Windows 上直接 `node scripts/verify-web-style.mjs`（不经任何 runner）真实执行并产生与 CI 同构的输出。
- 22 处守卫在 Windows 下全部可达；POSIX/CI 行为与改动前一致。
- `pnpm test:gates` 全绿；`.tmp/run-gate.mjs` 已转正或删除，仓库不再依赖 Windows 专用 runner 跑门禁。

## 门禁与 CI

- `pnpm test:gates`（守卫改动须同步 `scripts/gates.spec.mjs`）。
- `pnpm verify:flow` / `pnpm lint:docs` / `pnpm verify:docs`。
- CI（ubuntu）不受影响：两种守卫写法在 POSIX 上等价，判定逻辑零改动。

## 非目标

- 不改任何门禁的判定逻辑（只改"主块是否可达"与文件路径的 URL 化方式）。
- 不给 e2e 加 Windows CI lane；「Windows 本机 e2e 冒烟」作为该环境的已知验证方式在 Agent Note 登记。
- 不处理 fixtures 假域名导致的 catalog 422 与逐 target 容错（plans/2026-10-29-pr160-review.md §6-7 已留档 backlog）。
