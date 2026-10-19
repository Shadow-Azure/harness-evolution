import test from "node:test";
import assert from "node:assert/strict";
import {
  collectRefs,
  globToRegExp,
  parseFlowDocument,
  uncoveredFiles,
  validateTree,
} from "./flow-lib.mjs";
import { parseSignature, structureDiff } from "./translation-pairing-lib.mjs";
import { recommend, worktreePaths } from "./route-gates.mjs";
import { applyGithubRef } from "./flow-sync.mjs";

const roadmap = `# Roadmap

\`\`\`yaml flow
kind: roadmap
milestones:
  - m0
  - m1
\`\`\`
`;

const milestone = (id, status = "planned") => `# ${id}

\`\`\`yaml flow
kind: milestone
id: ${id}
title: ${id}
status: ${status}
github:
  number: null
  url: null
\`\`\`
`;

const issue = (milestoneId, status = "backlog", extra = "") => `# Issue

\`\`\`yaml flow
kind: issue
milestone: ${milestoneId}
priority: P0
status: ${status}
${extra}scope:
  - apps/**
adr: []
github:
  number: null
  url: null
\`\`\`
`;

function tree() {
  return {
    roadmap: { file: ".agents/flow/roadmap.md", data: parseFlowDocument(roadmap, "roadmap.md").data },
    milestones: [
      { file: ".agents/flow/milestones/m0-a.md", name: "m0-a", data: parseFlowDocument(milestone("m0", "done"), "m0-a.md").data },
      { file: ".agents/flow/milestones/m1-b.md", name: "m1-b", data: parseFlowDocument(milestone("m1"), "m1-b.md").data },
    ],
    issues: [
      {
        file: ".agents/flow/issues/m0-01-a.md",
        name: "m0-01-a",
        data: parseFlowDocument(issue("m0", "done", "bootstrap: true\n"), "m0-01-a.md").data,
      },
    ],
  };
}

test("flow document requires exactly one yaml flow fence", () => {
  assert.throws(() => parseFlowDocument("# no fence\n", "x.md"), /恰好一个/);
  assert.equal(parseFlowDocument(roadmap, "roadmap.md").kind, "roadmap");
});

test("valid tree passes and milestone/issue status is cross-checked", () => {
  assert.deepEqual(validateTree(tree(), { exists: () => true }), []);
  const broken = tree();
  broken.milestones[0].data.status = "planned";
  assert.match(validateTree(broken, { exists: () => true }).join("\n"), /全部 issue 已 done/);
});

test("bootstrap is limited to the first milestone", () => {
  const broken = tree();
  broken.issues[0].data.milestone = "m1";
  assert.match(validateTree(broken, { exists: () => true }).join("\n"), /第一个 milestone/);
});

test("scope globs cover intended files only", () => {
  assert.equal(globToRegExp("apps/server/src/**").test("apps/server/src/ingest/a.ts"), true);
  assert.equal(globToRegExp("apps/**").test("apps/web/src/App.tsx"), true);
  assert.deepEqual(uncoveredFiles(["apps/a.ts", "docs/b.md"], ["apps/**"]), ["docs/b.md"]);
});

test("issue references accept (#N) and [#N]", () => {
  assert.deepEqual(collectRefs("feat: add ingest (#12)"), [12]);
  assert.deepEqual(collectRefs("fix: gate [#7]"), [7]);
  assert.deepEqual(collectRefs("docs: no ref"), []);
});

test("structure signature mirrors headings, fences and links", () => {
  const zh = "# 标题\n\n[English](x.en.md) | 中文\n\n## 节\n\n- a\n- b\n\n```text\nsame\n```\n";
  const en = "# Title\n\nEnglish | [中文](x.md)\n\n## Section\n\n- a\n- b\n\n```text\nsame\n```\n";
  assert.deepEqual(structureDiff(parseSignature(zh), parseSignature(en)), []);
  assert.notDeepEqual(parseSignature(zh), parseSignature(en.replace("- b", "- b\n- c")));
});

test("route gates recommend build and docs for app changes", () => {
  const paths = worktreePaths(" M apps/web/src/App.tsx\n?? docs/new.md\n");
  assert.deepEqual(paths, ["apps/web/src/App.tsx", "docs/new.md"]);
  assert.deepEqual(recommend(paths).commands, ["build", "verify:docs"]);
});

test("github backfill removes the bootstrap exemption", () => {
  const content = "kind: issue\nbootstrap: true\ngithub:\n  number: null\n  url: null\n";
  const next = applyGithubRef(content, 42, "https://github.com/o/r/issues/42");
  assert.match(next, /number: 42/);
  assert.doesNotMatch(next, /bootstrap: true/);
});
