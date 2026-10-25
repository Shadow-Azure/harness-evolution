import { execFileSync, spawnSync } from "node:child_process";
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
import { checkContracts, compareContractFiles } from "./contract.mjs";
import { browserViolations } from "../tests/support/runtime.mjs";

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
  const paths = worktreePaths(" M apps/web/src/App.vue\n?? docs/new.md\n");
  assert.deepEqual(paths, ["apps/web/src/App.vue", "docs/new.md"]);
  assert.deepEqual(recommend(paths).commands, [
    "contract:check",
    "lint:web",
    "build",
    "test:web",
    "test:integration",
    "verify:web-style",
    "verify:bundle",
    "verify:docs",
  ]);
});

test("route gates recommend the Python toolchain for API changes", () => {
  const paths = worktreePaths(" M apps/api/app/main.py\n");
  assert.deepEqual(paths, ["apps/api/app/main.py"]);
  assert.deepEqual(recommend(paths).commands, [
    "contract:check",
    "lint:api",
    "typecheck:api",
    "test:api",
    "test:db",
    "test:integration",
    "verify:docs",
  ]);
});

test("route gates execute cross-stack integration tests", () => {
  const paths = worktreePaths(" M tests/integration/web-api-proxy.test.mjs\n");
  assert.deepEqual(recommend(paths).commands, ["test:integration", "verify:docs"]);
});

test("route gates recommend browser E2E and fixture seed validation", () => {
  assert.deepEqual(recommend(["tests/e2e/m1-shell.test.mjs"]).commands, [
    "test:integration",
    "test:e2e",
    "verify:docs",
  ]);
  assert.deepEqual(recommend(["tests/support/runtime.mjs"]).commands, [
    "test:integration",
    "test:e2e",
    "verify:docs",
  ]);
  assert.deepEqual(recommend(["fixtures/m1-shell.json"]).commands, [
    "test:api",
    "fixtures:check",
    "fixtures:seed",
    "verify:docs",
  ]);
  assert.deepEqual(recommend(["scripts/local-sessions.mjs"]).commands, [
    "test:gates",
    "verify:local-data",
    "verify:docs",
  ]);
});

test("browser log gate only ignores test-declared expected failures", () => {
  function sessionFor(listeners) {
    return {
      on(method, listener) {
        listeners.set(method, listener);
      },
    };
  }

  const strictListeners = new Map();
  const strictViolations = browserViolations(sessionFor(strictListeners));
  strictListeners.get("Log.entryAdded")({
    entry: {
      source: "network",
      level: "error",
      text: "Failed to load resource: the server responded with a status of 404",
      url: "http://127.0.0.1/missing.js",
    },
  });
  assert.equal(strictViolations.length, 1);

  const expectedListeners = new Map();
  const expectedViolations = browserViolations(sessionFor(expectedListeners), {
    isExpectedLogEntry: (entry) =>
      entry.url === "http://127.0.0.1/api/auth/refresh" && /status of 401/.test(entry.text),
  });
  expectedListeners.get("Log.entryAdded")({
    entry: {
      source: "network",
      level: "error",
      text: "Failed to load resource: the server responded with a status of 401",
      url: "http://127.0.0.1/api/auth/refresh",
    },
  });
  expectedListeners.get("Log.entryAdded")({
    entry: {
      source: "network",
      level: "error",
      text: "Failed to load resource: the server responded with a status of 404",
      url: "http://127.0.0.1/missing.js",
    },
  });
  assert.deepEqual(expectedViolations, [
    "error: Failed to load resource: the server responded with a status of 404 [http://127.0.0.1/missing.js]",
  ]);
});

test("E2E runner rejects an unmatched test-name pattern before starting services", () => {
  const pattern = "definitely-not-a-real-test";
  const result = spawnSync(process.execPath, ["scripts/run-e2e.mjs", pattern], {
    encoding: "utf8",
    timeout: 10_000,
  });

  assert.equal(result.error, undefined);
  assert.equal(result.signal, null);
  assert.equal(result.status, 2);
  assert.match(result.stderr, /no tests matched test-name pattern/);
  assert.doesNotMatch(result.stdout, /harness-e2e-|Starting development server/);
  const runner = readFileSync("scripts/run-e2e.mjs", "utf8");
  assert.match(runner, /timeout:/);
  assert.match(runner, /killSignal: "SIGTERM"/);
});

test("route gates require contract checks for API and shared contract changes", () => {
  assert.deepEqual(recommend(["apps/api/app/api/health.py"]).commands, [
    "contract:check",
    "lint:api",
    "typecheck:api",
    "test:api",
    "test:db",
    "test:integration",
    "verify:docs",
  ]);
  assert.deepEqual(recommend(["packages/contracts/openapi.json"]).commands, [
    "contract:check",
    "lint:web",
    "build",
    "test:web",
    "test:integration",
    "verify:web-style",
    "verify:bundle",
    "verify:docs",
  ]);
});

test("contract check detects stale and hand-edited generated files", () => {
  const expected = "/* @generated */\nexport type Version = 1;\n";
  const edited = "/* @generated */\nexport type Version = 2;\n";
  const missingMarker = "export type Version = 1;\n";

  assert.deepEqual(compareContractFiles(expected, expected, "api.d.ts"), []);
  assert.match(compareContractFiles(expected, edited, "api.d.ts").join("\n"), /真实 OpenAPI 不一致/);
  assert.match(
    compareContractFiles(expected, missingMarker, "api.d.ts").join("\n"),
    /@generated/,
  );
});

test("contract checker covers executable missing and stale artifact workflows", async () => {
  const directory = mkdtempSync(path.join(tmpdir(), "harness-contract-cli-"));
  try {
    const checkedSnapshot = path.resolve("packages/contracts/openapi.json");
    const checkedTypes = path.resolve("packages/contracts/src/generated/api.d.ts");
    const checkedFixtures = path.resolve("packages/contracts/fixtures/health.json");
    const missingSnapshot = path.join(directory, "missing-openapi.json");
    const missingTypes = path.join(directory, "missing-api.d.ts");
    const missingFixtures = path.join(directory, "missing-health.json");
    const staleTypes = path.join(directory, "stale-api.d.ts");
    const missingSnapshotResult = await checkContracts(missingSnapshot, checkedTypes, checkedFixtures);
    const missingTypesResult = await checkContracts(checkedSnapshot, missingTypes, checkedFixtures);
    const missingFixturesResult = await checkContracts(checkedSnapshot, checkedTypes, missingFixtures);

    assert.equal(missingSnapshotResult.ok, false);
    assert.match(missingSnapshotResult.errors.join("\n"), /missing-openapi\.json: 文件缺失/);
    assert.equal(missingTypesResult.ok, false);
    assert.match(missingTypesResult.errors.join("\n"), /missing-api\.d\.ts: 文件缺失/);
    assert.equal(missingFixturesResult.ok, false);
    assert.match(missingFixturesResult.errors.join("\n"), /missing-health\.json: 文件缺失/);

    writeFileSync(staleTypes, "/* @generated */\nexport type Stale = true;\n");
    const staleCli = spawnSync(process.execPath, [path.resolve("scripts/contract.mjs"), "check"], {
      encoding: "utf8",
      env: {
        ...process.env,
        HE_CONTRACT_SNAPSHOT: checkedSnapshot,
        HE_CONTRACT_TYPES: staleTypes,
        HE_CONTRACT_FIXTURES: checkedFixtures,
      },
    });
    assert.equal(staleCli.status, 1);
    assert.match(`${staleCli.stderr}${staleCli.stdout}`, /真实 OpenAPI 不一致/);
    assert.match(`${staleCli.stderr}${staleCli.stdout}`, /pnpm contract:generate/);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("smoke report renderer emits valid table fragments and coverage values", () => {
  const directory = mkdtempSync(path.join(tmpdir(), "harness-smoke-report-"));
  try {
    const dataPath = path.join(directory, "report-data.json");
    const outputPath = path.join(directory, "smoke-report.html");
    writeFileSync(
      dataPath,
      JSON.stringify({
        title: "Smoke report",
        summary: "Renderer regression fixture",
        metrics: [{ value: "1", label: "Scenario" }],
        facts: [{ label: "Commit", value: "abc1234" }],
        matrix: {
          columns: ["#", "Scenario", "Result", "Detail", "Evidence"],
          rows: [
            {
              id: "01",
              name: "Launch",
              status: { kind: "pass", label: "PASS" },
              detail: "Window rendered.",
              evidence: ["Accessibility tree"],
            },
          ],
        },
        coverage: {
          columns: ["Area", "Coverage", "Conclusion", "Recommendation"],
          rows: [
            {
              area: "识别",
              coverage: "UT",
              conclusion: "已验证",
              recommendation: "保持回归",
            },
          ],
        },
        conclusion: {
          kind: "pass",
          label: "通过",
          summary: "All checks passed.",
          points: ["No defects."],
        },
      }),
    );

    execFileSync(
      process.execPath,
      [
        path.resolve(".agents/skills/computer-use-smoke-reporting/scripts/render-smoke-report.mjs"),
        dataPath,
        outputPath,
      ],
      { encoding: "utf8" },
    );

    const report = readFileSync(outputPath, "utf8");
    assert.doesNotMatch(report, /<table>\s*<table>/i);
    for (const value of ["识别", "UT", "已验证", "保持回归"]) {
      assert.match(report, new RegExp(value));
    }
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("test gates execute frontend, backend, integration, and 80% coverage", () => {
  const rootPackage = JSON.parse(readFileSync("package.json", "utf8"));
  const webPackage = JSON.parse(readFileSync("apps/web/package.json", "utf8"));
  const ci = readFileSync(".github/workflows/ci.yml", "utf8");
  const webCoverage = readFileSync("apps/web/vitest.config.ts", "utf8");
  const apiCoverage = readFileSync("apps/api/pyproject.toml", "utf8");
  const apiRunner = readFileSync("scripts/run-api.mjs", "utf8");
  const webStyle = readFileSync("scripts/verify-web-style.mjs", "utf8");
  const bundle = readFileSync("scripts/verify-bundle.mjs", "utf8");

  assert.match(rootPackage.scripts.test, /test:web/);
  assert.match(rootPackage.scripts.test, /test:api/);
  assert.match(rootPackage.scripts["test:db"], /run-api\.mjs db/);
  assert.match(rootPackage.scripts["test:db:mysql"], /db-mysql/);
  assert.match(rootPackage.scripts["contract:generate"], /contract\.mjs generate/);
  assert.match(rootPackage.scripts["contract:check"], /contract\.mjs check/);
  assert.match(rootPackage.scripts["test:integration"], /web-api-proxy/);
  assert.match(rootPackage.scripts["test:e2e"], /run-e2e\.mjs/);
  assert.match(rootPackage.scripts["fixtures:check"], /fixtures-check\.mjs/);
  assert.match(rootPackage.scripts["fixtures:seed"], /fixtures-seed\.mjs/);
  assert.match(rootPackage.scripts["data:import:sessions"], /local-sessions\.mjs import/);
  assert.match(rootPackage.scripts["verify:local-sessions"], /local-sessions\.mjs verify/);
  assert.match(
    rootPackage.scripts["data:normalize:sessions"],
    /local-sessions\.mjs normalize/,
  );
  assert.match(rootPackage.scripts["data:tree:sessions"], /local-sessions\.mjs tree/);
  assert.match(rootPackage.scripts["data:replay:sessions"], /local-sessions\.mjs replay/);
  assert.match(rootPackage.scripts["verify:local-data"], /verify-local-data\.mjs/);
  assert.match(rootPackage.scripts["test:all"], /test:e2e/);
  assert.match(rootPackage.scripts["test:all"], /fixtures:check/);
  assert.match(webPackage.scripts.test, /--coverage/);
  assert.match(rootPackage.scripts["lint:web"], /filter @harness\/web lint/);
  assert.match(rootPackage.scripts["typecheck:web"], /filter @harness\/web typecheck/);
  assert.match(rootPackage.scripts["verify:web-style"], /verify-web-style\.mjs/);
  assert.match(rootPackage.scripts["verify:bundle"], /verify-bundle\.mjs/);
  assert.match(ci, /run: pnpm test$/m);
  assert.match(ci, /run: pnpm test:db$/m);
  assert.match(ci, /run: pnpm test:db:mysql$/m);
  assert.match(ci, /run: pnpm test:integration$/m);
  assert.match(ci, /run: pnpm test:e2e$/m);
  assert.match(ci, /pnpm fixtures:check$/m);
  assert.match(ci, /pnpm fixtures:seed$/m);
  assert.match(ci, /run: pnpm verify:local-data$/m);
  assert.match(ci, /run: pnpm test:gates$/m);
  assert.match(ci, /run: pnpm lint:web$/m);
  assert.match(ci, /run: pnpm typecheck:web$/m);
  assert.match(ci, /run: pnpm verify:web-style$/m);
  assert.match(ci, /run: pnpm verify:bundle$/m);
  const contractCheck = ci.indexOf("run: pnpm contract:check");
  const build = ci.indexOf("run: pnpm build");
  assert.ok(contractCheck >= 0);
  assert.ok(build > contractCheck, "contract:check must run before build");
  const gateTests = ci.indexOf("run: pnpm test:gates");
  const webLint = ci.indexOf("run: pnpm lint:web");
  const webStylePosition = ci.indexOf("run: pnpm verify:web-style");
  const bundlePosition = ci.indexOf("run: pnpm verify:bundle");
  assert.ok(bundlePosition > build, "bundle gate must run after build");
  for (const [label, position] of [
    ["gate tests", gateTests],
    ["web lint", webLint],
    ["web style", webStylePosition],
  ]) {
    assert.ok(position >= 0, `${label} must be wired into CI`);
  }
  assert.match(webStyle, /COLOR_PATTERN/);
  assert.match(bundle, /vendor-vue-flow/);
  for (const metric of ["branches", "functions", "lines", "statements"]) {
    assert.match(webCoverage, new RegExp(`${metric}: 80`));
  }
  const backendThreshold = Number(/fail_under = (\d+)/.exec(apiCoverage)?.[1]);
  assert.ok(backendThreshold >= 80);
  assert.match(apiRunner, /HE_DOCS_ENABLED.*true/);
});

test("focused backend tests forward path arguments through the API runner", async () => {
  const { execFile } = await import("node:child_process");
  const { promisify } = await import("node:util");
  const output = await promisify(execFile)("pnpm", ["test:api", "--", "tests/identity"], {
    cwd: process.cwd(),
    encoding: "utf8",
  });

  assert.match(output.stdout, /run-api\.mjs test -- tests\/identity/);
  assert.match(output.stdout, /\d+ passed/);
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
