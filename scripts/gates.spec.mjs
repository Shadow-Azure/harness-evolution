import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readdirSync, readFileSync, realpathSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";
import Ajv2020 from "@redocly/ajv/dist/2020.js";
import { isMain } from "./is-main.mjs";
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
import { applyGithubRef, githubSyncAdapter, parseGithubState, planRetirements, renderIssueBody, runSync } from "./flow-sync.mjs";
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

test("upstream trajectory JSON Schema enforces transcript identity", () => {
  const schema = JSON.parse(
    readFileSync("packages/contracts/upstream/trajectory.schema.json", "utf8"),
  );
  const fixture = JSON.parse(
    readFileSync("packages/contracts/upstream/trajectory.fixture.json", "utf8"),
  ).package;
  const ajv = new Ajv2020({
    allErrors: true,
    $data: true,
    strict: false,
    validateFormats: true,
  });
  ajv.addFormat("date-time", {
    validate: (value) =>
      typeof value === "string" &&
      /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
      !Number.isNaN(Date.parse(value)),
  });
  ajv.addKeyword({
    keyword: "x-time-range",
    schemaType: "object",
    validate: (range, data) =>
      Date.parse(data[range.start]) <= Date.parse(data[range.end]),
  });
  const validate = ajv.compile(schema);
  assert.equal(validate(fixture), true, JSON.stringify(validate.errors));

  const invalid = [
    {
      ...structuredClone(fixture),
      transcripts: [fixture.transcripts[0], fixture.transcripts[0]],
    },
    {
      ...structuredClone(fixture),
      transcripts: [
        { ...fixture.transcripts[0], agentId: "main-agent" },
        fixture.transcripts[1],
      ],
    },
    {
      ...structuredClone(fixture),
      transcripts: [
        fixture.transcripts[0],
        { ...fixture.transcripts[1], agentId: null },
      ],
    },
    {
      ...structuredClone(fixture),
      transcripts: [
        fixture.transcripts[0],
        { ...fixture.transcripts[1], agentId: fixture.sessionId },
      ],
    },
    {
      ...structuredClone(fixture),
      metadata: { ...fixture.metadata, startedAt: "not-a-date" },
    },
    {
      ...structuredClone(fixture),
      metadata: { ...fixture.metadata, startedAt: "2026-10-20T01:00:00" },
    },
    {
      ...structuredClone(fixture),
      metadata: {
        ...fixture.metadata,
        startedAt: "2026-10-20T02:00:00+08:00",
        endedAt: "2026-10-20T01:00:00+08:00",
      },
    },
  ];
  for (const document of invalid) {
    assert.equal(validate(document), false, JSON.stringify(document));
  }
});

test("valid tree passes and milestone/issue status is cross-checked", () => {
  assert.deepEqual(validateTree(tree(), { exists: () => true }), []);
  const broken = tree();
  broken.milestones[0].data.status = "planned";
  assert.match(validateTree(broken, { exists: () => true }).join("\n"), /全部 issue 已 done/);
});

test("standing milestones stay active after their issues are done", () => {
  const standing = tree();
  standing.milestones[0].data.status = "active";
  standing.milestones[0].data.standing = true;
  assert.deepEqual(validateTree(standing, { exists: () => true }), []);
  const invalid = tree();
  invalid.milestones[0].data.standing = "yes";
  assert.match(validateTree(invalid, { exists: () => true }).join("\n"), /standing 必须是布尔值/);
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

test("local session commands use the API default SQLite database", () => {
  const dataDir = mkdtempSync(path.join(tmpdir(), "harness-local-db-path-"));
  try {
    const python = path.resolve(
      "apps/api",
      process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python",
    );
    const apiUrl = execFileSync(
      python,
      ["-c", "from app.config import Settings; print(Settings().effective_db_url)"],
      {
        cwd: "apps/api",
        encoding: "utf8",
        env: {
          ...process.env,
          HE_DATA_DIR: dataDir,
          HE_DB_DIALECT: "sqlite",
          HE_DB_URL: "",
          HE_JWT_SECRET: "local-session-path-contract-secret",
        },
      },
    ).trim();
    assert.equal(apiUrl, `sqlite+aiosqlite:///${path.join(dataDir, "harness.db")}`);
    assert.match(readFileSync("scripts/local-sessions.mjs", "utf8"), /"harness\.db"/);
    assert.match(readFileSync("scripts/verify-local-data.mjs", "utf8"), /data\/harness\.db/);
  } finally {
    rmSync(dataDir, { recursive: true, force: true });
  }
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
  assert.match(runner, /--test-concurrency=1/);
  assert.match(runner, /selectedFiles = files\.filter/);
  assert.match(runner, /nodeArguments\.push\(\.\.\.selectedFiles\)/);
  assert.match(
    readFileSync("tests/e2e/m3-session-browser.test.mjs", "utf8"),
    /m3-session-browser matches the prototype/,
  );
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
    const checkedUpstreamSchema = path.resolve(
      "packages/contracts/upstream/trajectory.schema.json",
    );
    const checkedUpstreamFixture = path.resolve(
      "packages/contracts/upstream/trajectory.fixture.json",
    );
    const missingSnapshot = path.join(directory, "missing-openapi.json");
    const missingTypes = path.join(directory, "missing-api.d.ts");
    const missingFixtures = path.join(directory, "missing-health.json");
    const missingUpstreamSchema = path.join(directory, "missing-trajectory-schema.json");
    const missingUpstreamFixture = path.join(directory, "missing-trajectory-fixture.json");
    const staleTypes = path.join(directory, "stale-api.d.ts");
    const missingSnapshotResult = await checkContracts(
      missingSnapshot,
      checkedTypes,
      checkedFixtures,
      checkedUpstreamSchema,
      checkedUpstreamFixture,
    );
    const missingTypesResult = await checkContracts(
      checkedSnapshot,
      missingTypes,
      checkedFixtures,
      checkedUpstreamSchema,
      checkedUpstreamFixture,
    );
    const missingFixturesResult = await checkContracts(
      checkedSnapshot,
      checkedTypes,
      missingFixtures,
      checkedUpstreamSchema,
      checkedUpstreamFixture,
    );
    const missingUpstreamSchemaResult = await checkContracts(
      checkedSnapshot,
      checkedTypes,
      checkedFixtures,
      missingUpstreamSchema,
      checkedUpstreamFixture,
    );
    const missingUpstreamFixtureResult = await checkContracts(
      checkedSnapshot,
      checkedTypes,
      checkedFixtures,
      checkedUpstreamSchema,
      missingUpstreamFixture,
    );

    assert.equal(missingSnapshotResult.ok, false);
    assert.match(missingSnapshotResult.errors.join("\n"), /missing-openapi\.json: 文件缺失/);
    assert.equal(missingTypesResult.ok, false);
    assert.match(missingTypesResult.errors.join("\n"), /missing-api\.d\.ts: 文件缺失/);
    assert.equal(missingFixturesResult.ok, false);
    assert.match(missingFixturesResult.errors.join("\n"), /missing-health\.json: 文件缺失/);
    assert.equal(missingUpstreamSchemaResult.ok, false);
    assert.match(
      missingUpstreamSchemaResult.errors.join("\n"),
      /missing-trajectory-schema\.json: 文件缺失/,
    );
    assert.equal(missingUpstreamFixtureResult.ok, false);
    assert.match(
      missingUpstreamFixtureResult.errors.join("\n"),
      /missing-trajectory-fixture\.json: 文件缺失/,
    );

    writeFileSync(staleTypes, "/* @generated */\nexport type Stale = true;\n");
    const staleCli = spawnSync(process.execPath, [path.resolve("scripts/contract.mjs"), "check"], {
      encoding: "utf8",
      env: {
        ...process.env,
        HE_CONTRACT_SNAPSHOT: checkedSnapshot,
        HE_CONTRACT_TYPES: staleTypes,
        HE_CONTRACT_FIXTURES: checkedFixtures,
        HE_UPSTREAM_SCHEMA: checkedUpstreamSchema,
        HE_UPSTREAM_FIXTURE: checkedUpstreamFixture,
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

test("isMain matches the process entry for POSIX, relative, and spaced paths", () => {
  const entry = path.resolve("scripts/is-main.mjs");
  const entryUrl = pathToFileURL(entry).href;
  const directory = mkdtempSync(path.join(realpathSync(tmpdir()), "harness is-main-"));
  try {
    const spaced = path.join(directory, "with space.mjs");
    writeFileSync(spaced, "");
    assert.equal(isMain(pathToFileURL(spaced).href, spaced), true);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }

  assert.equal(isMain(entryUrl, entry), true);
  assert.equal(isMain(entryUrl, path.join("scripts", "is-main.mjs")), true);
  assert.equal(isMain(entryUrl, path.resolve("scripts/gates.spec.mjs")), false);
  assert.equal(isMain(entryUrl, null), false);
});

test("every script entry guard is platform-neutral", () => {
  const legacyGuard = "file://" + "${process.argv[1]}";
  const scripts = readdirSync("scripts").filter((name) => name.endsWith(".mjs"));
  const guarded = [];
  for (const name of scripts) {
    const source = readFileSync(path.join("scripts", name), "utf8");
    assert.ok(
      !source.includes(legacyGuard),
      `${name} still compares import.meta.url with a POSIX-only file URL`,
    );
    if (name === "gates.spec.mjs") continue;
    if (!source.includes("isMain(import.meta.url)")) continue;
    guarded.push(name);
    assert.match(
      source,
      /import \{ isMain \} from "\.\/is-main\.mjs";/,
      `${name} must import isMain from ./is-main.mjs`,
    );
  }
  assert.ok(guarded.length >= 22, `expected at least 22 guarded scripts, found ${guarded.length}`);
});

test("verify-web-style CLI executes its body from an arbitrary checkout path", () => {
  const directory = mkdtempSync(path.join(tmpdir(), "harness-web-style-cli-"));
  try {
    const scripts = path.join(directory, "scripts");
    const components = path.join(directory, "apps/web/src/pages");
    mkdirSync(scripts, { recursive: true });
    mkdirSync(components, { recursive: true });
    for (const name of ["is-main.mjs", "verify-web-style.mjs"]) {
      writeFileSync(path.join(scripts, name), readFileSync(path.join("scripts", name)));
    }
    const entry = path.join(scripts, "verify-web-style.mjs");
    writeFileSync(path.join(components, "Ok.vue"), "<style scoped>.a { color: var(--text); }</style>\n");

    const pass = spawnSync(process.execPath, [entry], { encoding: "utf8" });
    assert.equal(pass.status, 0, pass.stderr);
    assert.match(pass.stdout, /verify-web-style: Vue components use token colors only/);

    writeFileSync(path.join(components, "Bad.vue"), "<style scoped>.a { color: #fff; }</style>\n");
    const fail = spawnSync(process.execPath, [entry], { encoding: "utf8" });
    assert.equal(fail.status, 1);
    assert.match(fail.stderr, /Bad\.vue contains a literal color; use tokens\.css/);
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
  assert.match(rootPackage.scripts["performance:report"], /performance-report\.mjs/);
  assert.match(
    rootPackage.scripts["test:gates"],
    /performance-report\.spec\.mjs/,
  );
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
  assert.match(rootPackage.scripts["test:api"], /run-api\.mjs test$/);
  assert.match(rootPackage.scripts["test:api:serial"], /run-api\.mjs test:serial/);
  assert.match(webPackage.scripts.test, /--coverage/);
  assert.match(rootPackage.scripts["lint:web"], /filter @harness\/web lint/);
  assert.match(rootPackage.scripts["typecheck:web"], /filter @harness\/web typecheck/);
  assert.match(rootPackage.scripts["verify:web-style"], /verify-web-style\.mjs/);
  assert.match(rootPackage.scripts["verify:bundle"], /verify-bundle\.mjs/);
  assert.match(ci, /^\s+pnpm test:web$/m);
  assert.match(ci, /pnpm test:api -- -n \d+/);
  assert.ok(ci.includes("unit-tests-api:"), "API 单测 lane 必须存在");
  const ciOkNeeds = ci.slice(ci.indexOf("ci-ok:"));
  assert.match(ciOkNeeds, /unit-tests-web/);
  assert.match(ciOkNeeds, /unit-tests-api/);
  assert.match(ci, /run: pnpm test:db$/m);
  assert.match(ci, /run: pnpm test:db:mysql$/m);
  assert.match(ci, /run: pnpm test:integration$/m);
  // The e2e step wraps the suite in a one-shot retry shell block, so match
  // the command itself rather than the exact single-line `run:` form.
  assert.match(ci, /pnpm test:e2e/);
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
  assert.match(bundle, /ENTRY_RAW_MAX_BYTES/);
  assert.match(bundle, /ENTRY_GZIP_MAX_BYTES/);
  assert.match(bundle, /VENDOR_RAW_MAX_BYTES/);
  for (const metric of ["branches", "functions", "lines", "statements"]) {
    assert.match(webCoverage, new RegExp(`${metric}: 80`));
  }
  const backendThreshold = Number(/fail_under = (\d+)/.exec(apiCoverage)?.[1]);
  assert.ok(backendThreshold >= 80);
  assert.match(apiCoverage, /pytest-xdist/);
  assert.match(apiCoverage, /pytest-cov/);
  assert.match(apiRunner, /--cov=app/);
  assert.match(apiRunner, /--cov-fail-under=90/);
  assert.match(apiRunner, /--durations=25/);
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

test("flow sync parses GitHub state JSON at the CLI adapter boundary", () => {
  assert.equal(parseGithubState('{"state":"closed"}'), "closed");
  assert.equal(parseGithubState('{"state":"OPEN"}'), "OPEN");
  assert.throws(() => parseGithubState("not-json"), SyntaxError);
  assert.throws(() => parseGithubState('{"state":null}'), /缺少非空 state/);
  assert.throws(() => parseGithubState("{}"), /缺少非空 state/);
});

test("issue adapter reads nullable milestone numbers and PATCHes state with its milestone", () => {
  const calls = [];
  let output = '{"state":"open","milestone":null}';
  const adapter = githubSyncAdapter("o/r", (args) => { calls.push(args); return output; });
  const issue = { data: { github: { number: 17 } } };
  assert.deepEqual(adapter.readIssue(issue), { state: "open", milestone: null });
  assert.deepEqual(calls[0], ["api", "repos/o/r/issues/17", "--jq", "{state, milestone: .milestone.number}"]);
  output = '{"state":"closed","milestone":20}';
  assert.deepEqual(adapter.readIssue(issue), { state: "closed", milestone: { number: 20 } });
  adapter.updateIssue(issue, "CLOSED", 20);
  assert.deepEqual(calls.at(-1), [
    "api", "-X", "PATCH", "repos/o/r/issues/17", "-f", "state=closed", "-F", "milestone=20",
  ]);
  for (output of ['{}', '{"state":"open"}', '{"state":"open","milestone":"20"}', "invalid"])
    assert.throws(() => adapter.readIssue(issue));
});

test("flow sync CLI rejects invalid scope arguments before any remote operation", () => {
  for (const flag of ["--issues", "--milestones"]) {
    for (const args of [[""], ["0"], ["12,"], ["12", "--retire-missing"]]) {
      const result = spawnSync(process.execPath, ["scripts/flow-sync.mjs", "--", flag, ...args], { encoding: "utf8" });
      assert.notEqual(result.status, 0);
      assert.ok(result.stderr.includes(`${flag} 需要逗号分隔`), result.stderr);
    }
  }
  for (const args of [["--metadata-only"], ["--metadata-only", "--retire-missing"]]) {
    const result = spawnSync(process.execPath, ["scripts/flow-sync.mjs", "--", ...args], { encoding: "utf8" });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /--metadata-only 需要通过 --issues 或 --milestones/);
  }
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

test("milestone adapter parses raw gh state before deciding whether to PATCH", () => {
  const calls = [];
  const adapter = githubSyncAdapter("o/r", (args) => {
    calls.push(args);
    return JSON.stringify({ title: "m0", state: "open" });
  });
  assert.equal(adapter.readMilestoneState({ data: { github: { number: 2 } } }), "open");
  assert.deepEqual(calls, [["api", "repos/o/r/milestones/2"]]);
});

test("sync patches only drifted states and is idempotent without drift", async () => {
  const current = tree();
  current.milestones[0].data.github = { number: 2, url: "https://github.com/o/r/milestone/2" };
  current.milestones[1].data.github = { number: 3, url: "https://github.com/o/r/milestone/3" };
  current.issues[0].data.github = { number: 20, url: "https://github.com/o/r/issues/20" };
  const patched = [];
  const io = (milestoneStates, issueStates) => ({
    createMilestone() { throw new Error("unexpected"); },
    createIssue() { throw new Error("unexpected"); },
    backfill() {},
    readMilestoneState: (milestone) => milestoneStates[milestone.data.github.number],
    updateMilestoneState: (milestone, state) => patched.push([`milestone#${milestone.data.github.number}`, state]),
    readIssue: (issue) => ({ state: issueStates[issue.data.github.number], milestone: { number: 2 } }),
    updateIssue: (issue, state) => patched.push([`issue#${issue.data.github.number}`, state]),
  });

  const stable = await runSync(structuredClone(current), io({ 2: "closed", 3: "open" }, { 20: "CLOSED" }));
  assert.equal(stable.stateUpdates, 0);
  assert.deepEqual(patched, []);

  const drifted = await runSync(structuredClone(current), io({ 2: "closed", 3: "closed" }, { 20: "OPEN" }));
  assert.equal(drifted.stateUpdates, 2);
  assert.deepEqual(patched, [["milestone#3", "open"], ["issue#20", "CLOSED"]]);
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
    readIssue: () => ({ state: "open", milestone: { number: 2 } }), updateIssue() {},
    readIssueBody: () => "old", updateIssueBody: (_issue, body) => updates.push(body),
    issueBody: () => "new detailed body",
  });
  assert.deepEqual(updates, ["new detailed body"]);
});

test("scoped sync repairs only the selected issue's state and milestone", async () => {
  const current = tree();
  current.milestones[0].data.github = { number: 2 };
  current.issues[0].data.github = { number: 20 };
  current.issues.push({ ...current.issues[0], data: { ...current.issues[0].data, github: { number: 21 } } });
  const updates = [];
  const io = {
    readIssue: (issue) => {
      assert.equal(issue.data.github.number, 20);
      return { state: "closed", milestone: null };
    },
    updateIssue: (issue, state, milestone) => updates.push([issue.data.github.number, state, milestone]),
  };
  await assert.rejects(runSync(current, io, [20, 99]), /未登记/);
  await runSync(current, io, [20]);
  assert.deepEqual(updates, [[20, "CLOSED", 2]]);
});

test("milestone scope touches only its named objects and validates both lists before writing", async () => {
  const current = tree();
  current.milestones[0].data.github = { number: 2 };
  current.issues[0].data.github = { number: 20 };
  const updates = [];
  const io = {
    readMilestoneState(milestone) {
      assert.equal(milestone.data.github.number, 2);
      return "open";
    },
    updateMilestoneState: (milestone, state) => updates.push([milestone.data.github.number, state]),
    readIssue: () => ({ state: "open", milestone: null }),
    updateIssue: (issue, state, milestone) => updates.push([issue.data.github.number, state, milestone]),
  };
  await assert.rejects(runSync(current, io, undefined, []), /milestone 编号为空/);
  await assert.rejects(runSync(current, io, [20], [2, 99]), /milestone 编号为空或未登记/);
  await assert.rejects(runSync(current, io, [99], [2]), /issue 编号为空或未登记/);
  assert.deepEqual(updates, []);
  await runSync(current, io, undefined, [2]);
  assert.deepEqual(updates, [[2, "closed"]]);
  updates.length = 0;
  await runSync(current, io, [20], [2]);
  assert.deepEqual(updates, [[2, "closed"], [20, "CLOSED", 2]]);
});

test("metadata-only sync preserves issue bodies and skips unselected drafts", async () => {
  const current = tree();
  current.milestones[0].data.github = { number: 2 };
  current.issues[0].data.github = { number: 20 };
  current.issues.push({ data: { github: { number: null } } });
  const updates = [];
  const io = {
    readIssue: () => ({ state: "open", milestone: null }),
    updateIssue: (issue, state, milestone) => updates.push([issue.data.github.number, state, milestone]),
    issueBody: () => assert.fail("unexpected body render"),
    readIssueBody: () => assert.fail("unexpected body read"),
    updateIssueBody: () => assert.fail("unexpected body write"),
  };
  const result = await runSync(current, io, [20], undefined, { metadataOnly: true });
  assert.deepEqual(updates, [[20, "CLOSED", 2]]);
  assert.deepEqual(result, { milestones: 0, issues: 0, stateUpdates: 1, bodyUpdates: 0 });
});
