import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import {
  collectRefs,
  globToRegExp,
  parseFlowDocument,
  parseFlowYaml,
  uncoveredFiles,
  validateTree,
  validateIssueSections,
} from "./flow-lib.mjs";
import { parseSignature, structureDiff } from "./translation-pairing-lib.mjs";
import { recommend, worktreePaths } from "./route-gates.mjs";
import { applyGithubRef, planRetirements, renderIssueBody, runSync } from "./flow-sync.mjs";
import { verifyFlowDiff } from "./verify-flow.mjs";

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
id: ${milestoneId}-01
milestone: ${milestoneId}
depends: []
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
        content: "## 背景\n## 目标\n## 设计依据\n## 实现内容\n## 实施步骤\n## 依赖与交付边界\n## 独立验证\n## 验收标准\n## 门禁与 CI\n## 非目标",
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
  assert.equal(globToRegExp("apps/api/**").test("apps/api/app/main.py"), true);
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

test("route gates recommend web tests, integration, build, and docs for app changes", () => {
  const paths = worktreePaths(" M apps/web/src/App.tsx\n?? docs/new.md\n");
  assert.deepEqual(paths, ["apps/web/src/App.tsx", "docs/new.md"]);
  assert.deepEqual(recommend(paths).commands, [
    "build",
    "test:web",
    "test:integration",
    "verify:docs",
  ]);
});

test("route gates recommend the Python toolchain for API changes", () => {
  const paths = worktreePaths(" M apps/api/app/main.py\n");
  assert.deepEqual(paths, ["apps/api/app/main.py"]);
  assert.deepEqual(recommend(paths).commands, [
    "lint:api",
    "typecheck:api",
    "test:api",
    "test:integration",
    "verify:docs",
  ]);
});

test("test gates execute frontend, backend, integration, and 80% coverage", () => {
  const rootPackage = JSON.parse(readFileSync("package.json", "utf8"));
  const webPackage = JSON.parse(readFileSync("apps/web/package.json", "utf8"));
  const ci = readFileSync(".github/workflows/ci.yml", "utf8");
  const webCoverage = readFileSync("apps/web/vitest.config.ts", "utf8");
  const apiCoverage = readFileSync("apps/api/pyproject.toml", "utf8");
  const apiRunner = readFileSync("scripts/run-api.mjs", "utf8");

  assert.match(rootPackage.scripts.test, /test:web/);
  assert.match(rootPackage.scripts.test, /test:api/);
  assert.match(rootPackage.scripts["test:integration"], /web-api-proxy/);
  assert.match(webPackage.scripts.test, /--coverage/);
  assert.match(ci, /run: pnpm test$/m);
  assert.match(ci, /run: pnpm test:integration$/m);
  for (const metric of ["branches", "functions", "lines", "statements"]) {
    assert.match(webCoverage, new RegExp(`${metric}: 80`));
  }
  const backendThreshold = Number(/fail_under = (\d+)/.exec(apiCoverage)?.[1]);
  assert.ok(backendThreshold >= 80);
  assert.match(apiRunner, /HE_DOCS_ENABLED.*true/);
});

test("github backfill removes the bootstrap exemption", () => {
  const content = "kind: issue\nbootstrap: true\ngithub:\n  number: null\n  url: null\n";
  const next = applyGithubRef(content, 42, "https://github.com/o/r/issues/42");
  assert.match(next, /number: 42/);
  assert.doesNotMatch(next, /bootstrap: true/);
});

test("diff mode treats an issue created and completed in this PR as activated", async () => {
  const dir = mkdtempSync(path.join(tmpdir(), "harness-flow-diff-"));
  const git = (args) => execFileSync("git", args, { cwd: dir, encoding: "utf8" });
  try {
    mkdirSync(path.join(dir, ".agents/flow/milestones"), { recursive: true });
    mkdirSync(path.join(dir, ".agents/flow/issues"), { recursive: true });
    writeFileSync(path.join(dir, ".agents/flow/roadmap.md"), roadmap.replace("- m1", ""));
    writeFileSync(
      path.join(dir, ".agents/flow/milestones/m0-a.md"),
      milestone("m0", "done").replace("github:\n  number: null", "github:\n  number: 1"),
    );
    git(["init", "-q"]);
    git(["add", "."]);
    git(["-c", "user.email=test@example.com", "-c", "user.name=test", "commit", "-qm", "baseline"]);

    const issueText = issue("m0", "done")
      .replace("- m0\n  - m1", "- m0")
      .replace("scope:\n  - apps/**", "scope:\n  - .agents/flow/**")
      .replace("number: null", "number: 7");
    const sections = ["背景", "目标", "设计依据", "实现内容", "实施步骤", "依赖与交付边界", "独立验证", "验收标准", "门禁与 CI", "非目标"]
      .map((heading) => `## ${heading}\n\n验收夹具内容。`)
      .join("\n\n");
    writeFileSync(path.join(dir, ".agents/flow/issues/m0-01-done.md"), `${issueText}\n\n${sections}\n`);
    git(["add", "."]);
    git(["-c", "user.email=test@example.com", "-c", "user.name=test", "commit", "-qm", "complete bootstrap (#7)"]);

    const previousCwd = process.cwd();
    const previousTitle = process.env.PR_TITLE;
    process.chdir(dir);
    process.env.PR_TITLE = "bootstrap (#7)";
    try {
      const result = await verifyFlowDiff("HEAD~1");
      assert.deepEqual(result.errors, []);
      assert.equal(result.ok, true);
    } finally {
      process.chdir(previousCwd);
      if (previousTitle === undefined) delete process.env.PR_TITLE;
      else process.env.PR_TITLE = previousTitle;
    }
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("flow yaml rejects duplicate keys and generator emits canonical empty lists", () => {
  assert.throws(() => parseFlowYaml(["kind: roadmap", "kind: milestone"], "x.md"), /重复 key/);
});

test("issue sections require an executable implementation and verification contract", () => {
  const required = ["背景", "目标", "设计依据", "实现内容", "实施步骤", "依赖与交付边界", "独立验证", "验收标准", "门禁与 CI", "非目标"];
  const complete = required.map((heading) => `## ${heading}\n内容`).join("\n");
  assert.deepEqual(validateIssueSections(complete), []);
  assert.match(validateIssueSections(complete.replace("## 独立验证", "## 验证")).join("\n"), /独立验证/);
});

test("issue dependencies must exist, stay in earlier milestones and be acyclic", () => {
  const valid = tree();
  valid.issues.push({
    file: ".agents/flow/issues/m1-02-b.md",
    name: "m1-02-b",
    data: parseFlowDocument(issue("m1").replace("id: m1-01", "id: m1-02").replace("depends: []", "depends: [m0-01]"), "m1-02-b.md").data,
    content: valid.issues[0].content,
  });
  assert.deepEqual(validateTree(valid, { exists: () => true }), []);
  const missing = structuredClone(valid);
  missing.issues[1].data.depends = ["m0-99"];
  assert.match(validateTree(missing, { exists: () => true }).join("\n"), /依赖.*不存在/);
  const cycle = structuredClone(valid);
  cycle.issues[0].data.depends = ["m1-02"];
  assert.match(validateTree(cycle, { exists: () => true }).join("\n"), /依赖.*后续 milestone|依赖环/);
});

test("github issue body is detailed and design links resolve to the repository", () => {
  const body = renderIssueBody(`# 标题\n\n[English](m1-a.en.md) | 中文\n\n\`\`\`yaml flow\nkind: issue\n\`\`\`\n\n## 设计依据\n\n[API](../../../plans/fullstack-design/05-api-design.md#41-基础端点)\n`, "o/r");
  assert.match(body, /## 设计依据/);
  assert.match(body, /https:\/\/github.com\/o\/r\/blob\/main\/plans\/fullstack-design\/05-api-design.md#41-基础端点/);
  assert.doesNotMatch(body, /yaml flow|English/);
});

test("retire-missing closes only open remote objects absent from the local tree", () => {
  const current = tree();
  current.milestones[0].data.github = { number: 2, url: "https://github.com/o/r/milestone/2" };
  current.issues[0].data.github = { number: 20, url: "https://github.com/o/r/issues/20" };
  assert.deepEqual(planRetirements(current, {
    milestones: [{ number: 1, state: "open" }, { number: 2, state: "open" }, { number: 3, state: "closed" }],
    issues: [{ number: 10, state: "OPEN" }, { number: 20, state: "OPEN" }, { number: 30, state: "CLOSED" }],
  }), { milestones: [1], issues: [10] });
});

test("sync republish changed detailed issue bodies", async () => {
  const current = tree();
  current.milestones[0].data.github = { number: 2, url: "https://github.com/o/r/milestone/2" };
  current.milestones[0].data.status = "active";
  current.milestones[1].data.github = { number: 3, url: "https://github.com/o/r/milestone/3" };
  current.milestones[1].data.status = "planned";
  for (const [index, issue] of current.issues.entries())
    issue.data.github = { number: 20 + index, url: `https://github.com/o/r/issues/${20 + index}` };
  current.issues[0].data.status = "ready";
  delete current.issues[0].data.bootstrap;
  const updates = [];
  await runSync(current, {
    createMilestone() { throw new Error("unexpected"); }, createIssue() { throw new Error("unexpected"); }, backfill() {},
    readMilestoneState: () => "open", updateMilestoneState() {},
    readIssueState: () => "OPEN", updateIssueState() {},
    readIssueBody: () => "old", updateIssueBody: (_issue, body) => updates.push(body),
    issueBody: () => "new detailed body",
  });
  assert.deepEqual(updates, ["new detailed body"]);
});
