#!/usr/bin/env node
// 改动面路由器：看本次改动的路径，机械回答"该跑哪组门禁"（蓝本 change-scope
// 的单用途裁剪）。默认看工作树（git status --porcelain，含未跟踪）；--base <ref>
// 看 <ref>..工作树的累计改动。输出命令 + 每组一行理由；这是建议不是门禁——
// 穷尽覆盖归 CI。

import { execFileSync } from "node:child_process";

/**
 * 路由表：glob 前缀/精确名 → { commands, reason }。命中多组时命令并集，
 * 文档档就高（doc-quick 被命中的 verify:docs 覆盖则不再单独建议）。
 * 加新门禁命令时同步本表（spec 用例钉住代表路径）。
 */
export const ROUTES = [
  {
    match: (p) => p.startsWith("apps/api/"),
    commands: [
      "lint:api",
      "typecheck:api",
      "test:api",
      "test:db",
      "test:integration",
      "verify:docs",
    ],
    reason: "Python API：ruff、mypy、pytest/coverage、数据库测试、跨栈集成与文档门禁",
  },
  {
    match: (p) =>
      (p.startsWith("apps/") && !p.startsWith("apps/api/")) || p.startsWith("packages/"),
    commands: ["build", "test:web", "test:integration", "verify:docs"],
    reason: "TS 源码：Web 单测/80% 覆盖率、跨栈集成测试、构建与文档门禁",
  },
  {
    match: (p) => p.startsWith("tests/integration/"),
    commands: ["test:integration", "verify:docs"],
    reason: "跨栈测试：真实启动 Web 与 API",
  },
  {
    match: (p) => p.startsWith("scripts/"),
    commands: ["test:gates", "verify:docs"],
    reason: "门禁脚本：自测试必跑，全量文档档兜底",
  },
  {
    match: (p) => p.startsWith(".agents/flow/"),
    commands: ["verify:flow", "verify:docs"],
    reason: "流程树：状态机校验 + 配对/预算全量档",
  },
  {
    match: (p) => p.startsWith("docs/") || p.startsWith(".agents/") || p.endsWith(".md") || p === "AGENTS.md",
    commands: ["verify:docs"],
    reason: "文档语料：配对、预算、索引、编译围栏全量档",
  },
  {
    match: (p) => p === "package.json" || p === "pnpm-lock.yaml" || p.startsWith(".github/"),
    commands: ["test:gates", "verify:docs"],
    reason: "接线与依赖：CI/命令清单/钩子安装的自测试对账",
  },
];

/** 无命中时的默认建议（轻档）。 */
export const FALLBACK = {
  commands: ["lint:docs"],
  reason: "未命中路由表：快速档兜底（穷尽覆盖归 CI）",
};

/** 分类改动路径 → 命中的路由组（保持 ROUTES 顺序）。 */
export function classify(paths) {
  return ROUTES.filter((route) => paths.some((p) => route.match(p)));
}

const COMMAND_ORDER = [
  "build",
  "lint:api",
  "typecheck:api",
  "test:api",
  "test:db",
  "test:web",
  "test:integration",
  "test:gates",
  "verify:flow",
  "verify:docs",
  "lint:docs",
];

/** 命中组的命令并集（按固定顺序去重），无命中回退 FALLBACK。 */
export function recommend(paths) {
  const hits = classify(paths);
  const source = hits.length ? hits : [FALLBACK];
  const commands = [...new Set(source.flatMap((hit) => hit.commands))].sort(
    (a, b) => COMMAND_ORDER.indexOf(a) - COMMAND_ORDER.indexOf(b),
  );
  return { commands, hits: source };
}

/** git status --porcelain 的路径（重命名取两侧，去状态前缀）。 */
export function worktreePaths(statusOutput) {
  return [
    ...new Set(
      statusOutput
        .split("\n")
        .filter(Boolean)
        .map((line) => {
          const rename = line.slice(3).match(/^(.*?) -> (.*)$/);
          return rename ? [rename[1], rename[2]] : line.slice(3);
        })
        .flat(),
    ),
  ];
}

function changedPaths() {
  const args = process.argv.slice(2);
  const baseIdx = args.indexOf("--base");
  if (baseIdx === -1)
    return worktreePaths(execFileSync("git", ["status", "--porcelain"], { encoding: "utf8" }));
  const base = args[baseIdx + 1];
  if (!base) {
    console.error("route-gates: --base 需要一个 ref 参数（如 --base main）");
    process.exit(2);
  }
  const committed = execFileSync("git", ["diff", "--name-only", base], { encoding: "utf8" });
  const untracked = execFileSync("git", ["status", "--porcelain"], { encoding: "utf8" });
  return [...new Set([...committed.split("\n").filter(Boolean), ...worktreePaths(untracked)])];
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const paths = changedPaths();
  if (!paths.length) {
    console.log("route-gates: 无改动。");
    process.exit(0);
  }

  const { commands, hits } = recommend(paths);
  console.log(`改动面（${paths.length} 条路径）命中：`);
  for (const hit of hits) console.log(`  - ${hit.reason}`);
  console.log("\n建议按序跑：");
  for (const command of commands) console.log(`  pnpm ${command}`);
}
