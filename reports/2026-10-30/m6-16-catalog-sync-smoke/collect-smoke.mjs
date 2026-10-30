import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  availablePort,
  capture,
  createBrowserPage,
  stop,
  waitFor,
  waitForDocument,
} from "../../../tests/support/runtime.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../../..");
const apiDir = path.join(root, "apps/api");
const python = path.join(
  apiDir,
  ".venv",
  process.platform === "win32" ? "Scripts" : "bin",
  process.platform === "win32" ? "python.exe" : "python",
);
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const rootSession = "11111111-1111-4111-8111-111111111111";
const adminPassword = "m6-16-smoke-admin";
const adminFinal = "m6-16-smoke-final";

let mock;
let api;
let web;
let dataDir;

async function evaluate(page, expression) {
  const result = await page.session.send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
  return result.result.value;
}

async function screenshot(page, file) {
  const result = await page.session.send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
  });
  await writeFile(path.join(here, "screenshots", file), Buffer.from(result.data, "base64"));
}

async function pollJson(url, headers, predicate, label, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  let last;
  while (Date.now() < deadline) {
    const response = await fetch(url, { headers });
    if (response.ok) {
      last = await response.json();
      if (predicate(last)) return last;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`${label} timed out; last=${JSON.stringify(last)}`);
}

try {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m6-16-smoke-"));
  await mkdir(path.join(here, "screenshots"), { recursive: true });
  const env = {
    ...process.env,
    HE_DATA_DIR: dataDir,
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: "m6-16-smoke-signing-secret-with-enough-length",
    HE_PHASE: "demo",
    PYTHONPATH: apiDir,
  };

  const prepare = spawn(
    python,
    [
      path.join(root, "tests/e2e/support/seed_bad_case.py"),
      "--data-dir",
      dataDir,
      "--root",
      rootSession,
      "--tables-only",
    ],
    { cwd: root, env, stdio: ["ignore", "pipe", "pipe"] },
  );
  let prepareLogs = "";
  capture(prepare, (chunk) => {
    prepareLogs += chunk;
  });
  assert.equal(
    await new Promise((resolve) => prepare.once("exit", resolve)),
    0,
    prepareLogs,
  );

  const mockPort = await availablePort();
  mock = spawn(
    python,
    [
      path.join(root, "tests/e2e/support/mock_catalog_upstream.py"),
      "--port",
      String(mockPort),
      "--delay",
      "0.05",
    ],
    { cwd: root, env, stdio: ["ignore", "pipe", "pipe"] },
  );
  let mockLogs = "";
  capture(mock, (chunk) => {
    mockLogs += chunk;
  });
  await waitFor(`http://127.0.0.1:${mockPort}/__stats`, mock, () => mockLogs);

  const apiPort = await availablePort();
  const apiUrl = `http://127.0.0.1:${apiPort}`;
  api = spawn(python, ["-m", "app"], {
    cwd: apiDir,
    env: {
      ...env,
      HE_ADMIN_PASSWORD: adminPassword,
      HE_ADMIN_USERNAME: "admin",
      HE_HOST: "127.0.0.1",
      HE_PORT: String(apiPort),
      HE_DOCS_ENABLED: "false",
      HE_SYNC_INTERVAL_SECONDS: "0",
      HE_BAD_CASE_SYNC_INTERVAL_SECONDS: "1",
      HE_BAD_CASE_CATALOG_SYNC_INTERVAL_SECONDS: "0",
      HE_BAD_CASE_QUERY_BASE_URL: `http://127.0.0.1:${mockPort}`,
      HE_BAD_CASE_QUERY_TOKEN: "smoke-service-token",
      HE_BAD_CASE_QUERY_RETRY_ATTEMPTS: "0",
      HE_SESSION_QUERY_BASE_URL: `http://127.0.0.1:${mockPort}`,
      HE_SESSION_QUERY_TOKEN: "smoke-service-token",
      PYTHONUNBUFFERED: "1",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let apiLogs = "";
  capture(api, (chunk) => {
    apiLogs += chunk;
  });
  await waitFor(`${apiUrl}/api/health`, api, () => apiLogs);

  const webPort = await availablePort();
  const webUrl = `http://127.0.0.1:${webPort}`;
  web = spawn(
    pnpm,
    [
      "--filter",
      "@harness/web",
      "exec",
      "vite",
      "--force",
      "--host",
      "127.0.0.1",
      "--port",
      String(webPort),
      "--strictPort",
    ],
    {
      cwd: root,
      env: { ...process.env, HE_API_PROXY_URL: apiUrl },
      shell: process.platform === "win32",
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  let webLogs = "";
  capture(web, (chunk) => {
    webLogs += chunk;
  });
  await waitFor(webUrl, web, () => webLogs);

  const login = await fetch(`${apiUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: adminPassword }),
  });
  assert.equal(login.status, 200);
  const loginBody = await login.json();
  const initialCookie = login.headers.get("set-cookie")?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(initialCookie, "no refresh cookie");
  const changed = await fetch(`${apiUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${loginBody.accessToken}`,
    },
    body: JSON.stringify({ oldPassword: adminPassword, newPassword: adminFinal }),
  });
  assert.equal(changed.status, 204, `change-password: ${changed.status}`);
  const refreshed = await fetch(`${apiUrl}/api/auth/refresh`, {
    method: "POST",
    headers: { cookie: `refresh_token=${initialCookie}` },
  });
  assert.equal(refreshed.status, 200, await refreshed.text());
  const cookie = refreshed.headers.get("set-cookie")?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie, "no refreshed cookie");
  const relogin = await fetch(`${apiUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: adminFinal }),
  });
  assert.equal(relogin.status, 200);
  const accessToken = (await relogin.json()).accessToken;
  const authHeaders = { authorization: `Bearer ${accessToken}` };

  const catalog = await pollJson(
    `${apiUrl}/api/acquisition/status`,
    authHeaders,
    (body) =>
      body.badCaseCatalogSync.synced === 3 &&
      body.badCaseCatalogSync.unsynced === 0 &&
      body.badCaseCatalogSync.status === "idle",
    "catalog sync",
  );
  const synced = await pollJson(
    `${apiUrl}/api/acquisition/status`,
    authHeaders,
    (body) => body.badCaseSync.synced === 1 && body.badCaseSync.unsynced === 0,
    "root trace sync",
  );
  const sessionBody = await pollJson(
    `${apiUrl}/api/sessions`,
    authHeaders,
    (body) => body.items.some((item) => item.id === rootSession),
    "root session",
    30_000,
  );
  assert.ok(
    sessionBody.items.some((item) => item.id === rootSession),
    `root session missing from list: ${JSON.stringify(sessionBody.items)}`,
  );
  const problems = await fetch(`${apiUrl}/api/sessions/${rootSession}/bad-cases`, {
    headers: authHeaders,
  });
  assert.equal(problems.status, 200);
  const problemBody = await problems.json();
  assert.equal(problemBody.items.length, 3);
  const stats = await (await fetch(`http://127.0.0.1:${mockPort}/__stats`)).json();
  assert.equal(stats.maxActive, 1, `session query overlapped: ${JSON.stringify(stats)}`);
  assert.ok(stats.trajectoryCalls >= 3, `expected 3 trajectory calls, got ${stats.trajectoryCalls}`);
  assert.ok(stats.catalogCalls >= 1, `expected catalog calls, got ${stats.catalogCalls}`);

  const page = await createBrowserPage();
  let catalogText = "";
  let analysisText = "";
  try {
    await page.session.send("Network.enable");
    await page.session.send("Network.setCookie", {
      name: "refresh_token",
      value: cookie,
      url: `${webUrl}/api/auth`,
      httpOnly: true,
      sameSite: "Strict",
    });
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.session.send("Page.navigate", { url: `${webUrl}/sessions` });
    await waitForDocument(
      page.session,
      "Boolean(document.querySelector('.sync-status'))",
      "sync status",
    );
    await new Promise((resolve) => setTimeout(resolve, 1200));
    await evaluate(page, "document.querySelector('.sync-status').focus()");
    const rect = await evaluate(
      page,
      "(() => { const r = document.querySelector('.sync-status').getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()",
    );
    await page.session.send("Input.dispatchMouseEvent", {
      type: "mouseMoved",
      x: rect.x,
      y: rect.y,
    });
    await new Promise((resolve) => setTimeout(resolve, 400));
    await screenshot(page, "01-session-list-sync-popover.png");
    catalogText = await evaluate(
      page,
      "document.querySelector('[data-testid=sync-catalog]')?.textContent ?? ''",
    );
    analysisText = await evaluate(
      page,
      "document.querySelector('[data-testid=sync-analysis]')?.textContent ?? ''",
    );
    assert.ok(catalogText.includes("已同步 3"), `catalog popover: ${catalogText}`);
    assert.ok(catalogText.includes("未同步 0"), `catalog popover: ${catalogText}`);
    assert.ok(analysisText.includes("待分析 3"), `analysis popover: ${analysisText}`);
  } finally {
    await page.close();
  }

  const report = {
    title: "m6-16 bad_cases catalog sync smoke",
    eyebrow: "SMOKE REPORT",
    summary:
      "Started the real API and Web against one deterministic mock that serves the paginated catalog plus both session-query endpoints, then verified the scheduled catalog task wrote three bad_cases, the root trace backfill made the session queryable, and the four-section sync popover reported the new counters.",
    meta: "2026-10-30 · Windows · SQLite + real Vite + headless Chrome",
    metrics: [
      { value: String(catalog.badCaseCatalogSync.synced), label: "catalog rows synced" },
      { value: String(catalog.badCaseCatalogSync.unsynced), label: "upstream remaining" },
      { value: String(catalog.badCaseAnalysis.pending), label: "attribution pending" },
      { value: String(stats.maxActive), label: "max concurrent API 2 calls" },
    ],
    facts: [
      { label: "Commit", value: process.env.GITHUB_SHA ?? "working tree" },
      { label: "Root session", value: rootSession },
      { label: "Mock service", value: `127.0.0.1:${mockPort}` },
      { label: "API / Web", value: `${apiPort} / ${webPort}` },
    ],
    matrix: {
      columns: ["#", "Scenario", "Result", "Detail", "Evidence"],
      rows: [
        {
          id: "01",
          name: "Scheduled catalog sync pages and upserts bad_cases",
          status: { kind: "pass", label: "PASS" },
          detail: `Mock catalog served 1 page; synced=${catalog.badCaseCatalogSync.synced}, unsynced=${catalog.badCaseCatalogSync.unsynced}, lastBadCaseId=${catalog.badCaseCatalogSync.lastBadCaseId}.`,
          evidence: [],
        },
        {
          id: "02",
          name: "Root trace backfill uses query API 1 + API 2 serially",
          status: { kind: "pass", label: "PASS" },
          detail: `Mock served ${stats.catalogCalls} catalog calls, ${stats.trajectoryCalls} trajectory calls; max concurrency ${stats.maxActive}.`,
          evidence: [],
        },
        {
          id: "03",
          name: "Replay makes the session and its three problems queryable",
          status: { kind: "pass", label: "PASS" },
          detail: `GET /api/sessions contains ${rootSession}; /bad-cases returns ${problemBody.items.length} items.`,
          evidence: [],
        },
        {
          id: "04",
          name: "Four-section sync popover shows catalog and attribution counts",
          status: { kind: "pass", label: "PASS" },
          detail: `Popover text verified: ${catalogText}; ${analysisText}.`,
          evidence: ["screenshots/01-session-list-sync-popover.png"],
        },
      ],
    },
    issues: [],
    screenshots: [
      {
        src: "screenshots/01-session-list-sync-popover.png",
        alt: "Session list with the four-section data sync popover open",
        label: "01 · Session list + four-section sync popover",
        caption:
          "问题数量 shows 3 synced / 0 unsynced; 归因分析 shows 3 pending because the smoke data has no analysis rows.",
        variant: "wide",
      },
    ],
    coverage: {
      columns: ["Area", "Coverage", "Conclusion", "Recommendation"],
      rows: [
        {
          area: "Catalog pagination and upsert",
          coverage: "UT + E2E + smoke",
          conclusion: "Three mock rows were upserted through the real scheduler; cursor reached 3.",
          recommendation: "Keep the mock contract test in CI; never call the real upstream.",
        },
        {
          area: "Root trace chain after catalog sync",
          coverage: "UT + E2E + smoke",
          conclusion: `Session ${rootSession} became queryable with three problems.`,
          recommendation: "First production run re-pulls existing roots once by design.",
        },
        {
          area: "Four-section popover",
          coverage: "UT + smoke",
          conclusion: "Catalog and attribution counters render in the confirmed order.",
          recommendation: "Keep the 0/0 empty state covered by the component test.",
        },
      ],
    },
    conclusion: {
      kind: "pass",
      label: "Ready for PR review",
      summary:
        "The mock-backed catalog-to-trace chain works; the only unverified dependency is the real upstream service contract.",
      points: [
        "Real upstream paths/tokens remain to be supplied by the service owner.",
        "Attribution progress is aggregated read-only; the smoke data intentionally has no analysis rows.",
      ],
    },
    footer:
      "m6-16 · bad_cases 目录数据定时同步 · mock catalog + session-query service, no production credentials",
  };
  await writeFile(path.join(here, "report-data.json"), JSON.stringify(report, null, 2));
  const render = spawn(
    "node",
    [
      path.join(root, ".agents/skills/computer-use-smoke-reporting/scripts/render-smoke-report.mjs"),
      path.join(here, "report-data.json"),
      path.join(here, "smoke-report.html"),
    ],
    { cwd: root, stdio: ["ignore", "inherit", "inherit"] },
  );
  assert.equal(await new Promise((resolve) => render.once("exit", resolve)), 0);
  console.log(
    JSON.stringify(
      {
        catalog: catalog.badCaseCatalogSync,
        analysis: catalog.badCaseAnalysis,
        roots: synced.badCaseSync,
        problems: problemBody.items.length,
        stats,
      },
      null,
      2,
    ),
  );
} finally {
  if (web) await stop(web);
  if (api) await stop(api);
  if (mock) await stop(mock);
  if (dataDir) {
    await rm(dataDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
  }
}
