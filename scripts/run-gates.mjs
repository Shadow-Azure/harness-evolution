#!/usr/bin/env node
// 门禁总调度：检查是叶子，模式是叶子组合。CI 的静态 lane 内嵌 doc-sync，
// 因此不存在"CI 忘配文档门禁"的路径。用法：
//   node scripts/run-gates.mjs --mode doc-quick|doc-sync

import verifyAgentNotes from "./verify-agent-notes.mjs";
import verifyFlow from "./verify-flow.mjs";
import verifyDocIndex from "./verify-doc-index.mjs";
import verifyDocBudgets from "./verify-doc-budgets.mjs";
import verifyMdWrap from "./verify-md-wrap.mjs";
import verifyMdLinks from "./verify-md-links.mjs";
import verifyTranslationPairing from "./verify-translation-pairing.mjs";
import verifyTerminology from "./verify-terminology.mjs";
import verifyTypeEquiv from "./verify-type-equiv.mjs";
import verifyExportDocs from "./verify-export-docs.mjs";
import verifyDocRefs from "./verify-doc-refs.mjs";
import verifyArchivedAgentNotes from "./verify-archived-agent-notes.mjs";
import docTypecheck from "./doc-typecheck.mjs";

export const LEAVES = {
  "verify-agent-notes": verifyAgentNotes,
  "verify-flow": verifyFlow,
  "verify-archived-agent-notes": verifyArchivedAgentNotes,
  "verify-doc-index": verifyDocIndex,
  "verify-doc-budgets": verifyDocBudgets,
  "verify-md-wrap": verifyMdWrap,
  "verify-terminology": verifyTerminology,
  "verify-translation-pairing": () => verifyTranslationPairing([]),
  "verify-type-equiv": verifyTypeEquiv,
  "verify-export-docs": verifyExportDocs,
  "verify-doc-refs": verifyDocRefs,
  "doc-typecheck": docTypecheck,
  "verify-md-links": verifyMdLinks,
  "gate-self-tests": async () => {
    const { execFileSync } = await import("node:child_process");
    try {
      execFileSync(process.execPath, ["--test", "scripts/gates.spec.mjs"], { stdio: "inherit" });
      return { ok: true, errors: [] };
    } catch {
      return { ok: false, errors: ["node --test scripts/gates.spec.mjs 退出非零（门禁自测试失败）"] };
    }
  },
};

const QUICK = [
  "verify-agent-notes",
  "verify-flow",
  "verify-archived-agent-notes",
  "verify-doc-index",
  "verify-doc-budgets",
  "verify-md-wrap",
  "verify-terminology",
  "verify-translation-pairing",
  "verify-type-equiv",
  "verify-export-docs",
  "verify-doc-refs",
];

export const MODES = {
  // 快速档：无构建、秒级，提交前随手跑。
  "doc-quick": QUICK,
  // 全量文档档：死链 + ts 围栏真实编译 + 门禁自测试。
  "doc-sync": [...QUICK, "doc-typecheck", "verify-md-links", "gate-self-tests"],
};

if (import.meta.url === `file://${process.argv[1]}`) {
  const args = process.argv.slice(2);
  const modeIdx = args.indexOf("--mode");
  const mode = modeIdx >= 0 ? args[modeIdx + 1] : "doc-quick";
  if (!MODES[mode]) {
    console.error(`未知模式 "${mode}"，可选：${Object.keys(MODES).join(" | ")}`);
    process.exit(2);
  }

  const failures = [];
  for (const leaf of MODES[mode]) {
    const result = await LEAVES[leaf]();
    if (result.ok) {
      console.log(`✓ ${leaf}${result.summary ? ` — ${result.summary}` : ""}`);
    } else {
      failures.push(leaf);
      console.error(`✗ ${leaf}\n    ${result.errors.join("\n    ")}`);
    }
  }

  if (failures.length) {
    console.error(`\n${failures.length} 个门禁失败：${failures.join(", ")}`);
    process.exit(1);
  }
  console.log(`\n${mode}: 全绿（${MODES[mode].length} 叶）`);
}
