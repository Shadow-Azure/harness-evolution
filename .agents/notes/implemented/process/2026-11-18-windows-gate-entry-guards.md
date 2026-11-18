# Agent Note: Windows 本地门禁的跨平台入口守卫

Status: implemented

[English](2026-11-18-windows-gate-entry-guards.en.md) | 中文

## Problem

Windows 开发机上，`scripts/` 的 CLI 入口守卫把 `import.meta.url` 与 `` `file://${process.argv[1]}` `` 直接比较。Windows 的 `import.meta.url` 是 `file:///D:/...` 三斜杠正斜杠形态，模板串拼出的是 `file://D:\...` 两斜杠反斜杠路径，比较恒假：`node scripts/verify-flow.mjs` 等直接执行时主块静默跳过、exit 0，`pnpm verify:*` 成为假绿。另有独立一层：`verify-web-style.mjs` 用 `new URL(path, sourceRoot)` 读取 `readdir` 给出的 `entry.parentPath`，Windows 的反斜杠绝对路径以 `D:` 开头，被 URL 解析器当成 `d:` 协议并抛 `ERR_INVALID_URL_SCHEME`。CI 全部跑在 Ubuntu，守卫在 Linux 上成立，因此这个本地防线缺口不会被 CI 暴露。

## Decision

- 新增 `scripts/is-main.mjs` 的 `isMain(moduleUrl, entryPath = process.argv[1])`，用 `pathToFileURL(realpathSync(entryPath)).href` 与 `import.meta.url` 比较（`realpath` 同时消除经符号链接进入脚本时的路径差异）；全部 24 个脚本入口统一走它（22 个旧守卫，加上 `contract.mjs` 与 `performance-report.mjs` 两处既有安全守卫）。
- `verify-web-style.mjs` 的目录枚举仍以 `import.meta.url` 为锚；单个文件路径改为 `path.join(entry.parentPath, entry.name)` 后用 `pathToFileURL(...)` 读取，不再把 Windows 绝对路径拼进相对 URL。
- `gates.spec.mjs` 增加三层回归：`isMain` 对绝对、相对与含空格路径的等价判断；全脚本静态审计（禁止旧模板串、凡有入口守卫必须导入 helper）；在临时目录复制脚本并注入含字面色的 Vue 样本，真实执行 CLI，断言成功输出与报红退出。后两者防的是“入口可达但门禁主体没跑”。
- `.tmp/run-gate.mjs` 保持不入库：它只是 Windows 本机绕过旧守卫的临时 runner，仓库不依赖任何平台专用 runner。
- 门禁的判定逻辑零改动，`.github/workflows` 不变。

## Alternatives considered

- 每个脚本内联 `pathToFileURL`：少一个共享文件，但 24 份等价判断容易再次漂移，且回归测试只能逐个字符串匹配；否。
- 用 `fileURLToPath` + `path.resolve` 比较路径：语义等价，但偏离仓库已有的 `pathToFileURL(...).href` 范本，需要同时处理 URL 解码；否。
- 新增 Windows CI lane：m12-05 的非目标明确排除，且仓库已有“Windows 本机 e2e 冒烟”这一手动验证方式；否。

## Consequences

- Windows 上直接执行或经 `pnpm verify:*` 执行门禁会真正进入主块，静默 no-op 假绿消失；POSIX 与 CI 行为不变。
- 守卫正确性依赖 Node 的 `pathToFileURL` 语义。自测试在 POSIX 上覆盖入口可达、静态审计与子进程冒烟；Windows 运行时仍由 Windows 开发机按 issue 的独立验证复核，当前没有 Windows CI lane。
- 新增门禁脚本若带 CLI 入口，必须导入 `isMain` 并使用 `isMain(import.meta.url)`；静态审计会阻止旧写法回归。
- Windows 本机 e2e 冒烟继续是手动验证方式，不在 CI 覆盖范围。
