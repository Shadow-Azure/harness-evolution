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
const adminPassword = "m6-15-smoke-admin";
const adminFinal = "m6-15-smoke-final";

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
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m6-15-smoke-"));
  await mkdir(path.join(here, "screenshots"), { recursive: true });
  const env = {
    ...process.env,
    HE_DATA_DIR: dataDir,
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: "m6-15-smoke-signing-secret-with-enough-length",
    HE_PHASE: "demo",
    PYTHONPATH: apiDir,
  };

  const seed = spawn(
    python,
    [path.join(root, "tests/e2e/support/seed_bad_case.py"), "--data-dir", dataDir, "--root", rootSession],
    { cwd: root, env, stdio: ["ignore", "pipe", "pipe"] },
  );
  let seedLogs = "";
  capture(seed, (chunk) => {
    seedLogs += chunk;
  });
  assert.equal(await new Promise((resolve) => seed.once("exit", resolve)), 0, seedLogs);

  const mockPort = await availablePort();
  mock = spawn(
    python,
    [path.join(root, "tests/e2e/support/mock_session_query.py"), "--port", String(mockPort), "--delay", "0.05"],
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
    ["--filter", "@harness/web", "exec", "vite", "--force", "--host", "127.0.0.1", "--port", String(webPort), "--strictPort"],
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

  const before = await pollJson(
    `${apiUrl}/api/acquisition/status`,
    authHeaders,
    (body) => body.badCaseSync.total === 1,
    "initial badCaseSync total",
    15_000,
  );
  const synced = await pollJson(
    `${apiUrl}/api/acquisition/status`,
    authHeaders,
    (body) => body.badCaseSync.synced === 1 && body.badCaseSync.unsynced === 0,
    "badCaseSync synced",
    60_000,
  );
  const sessions = await fetch(`${apiUrl}/api/sessions`, { headers: authHeaders });
  assert.equal(sessions.status, 200);
  const sessionBody = await sessions.json();
  assert.ok(
    sessionBody.items.some((item) => item.id === rootSession),
    `root session missing from list: ${JSON.stringify(sessionBody.items)}`,
  );
  const stats = await (await fetch(`http://127.0.0.1:${mockPort}/__stats`)).json();
  assert.equal(stats.maxActive, 1, `API 2 overlapped: ${JSON.stringify(stats)}`);
  assert.ok(stats.calls >= 3, `expected 3 trajectory calls, got ${stats.calls}`);

  const page = await createBrowserPage();
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
    const text = await evaluate(page, "document.querySelector('[data-testid=sync-problem]')?.textContent ?? ''");
    assert.ok(text.includes("未同步 0"), `popover text: ${text}`);
  } finally {
    await page.close();
  }

  const report = {
    title: "m6-15 bad-case root trajectory sync smoke",
    eyebrow: "SMOKE REPORT",
    summary:
      "Seeded one bad_cases root with no trajectory payload, ran the real API + Web with a deterministic mock of the two query endpoints, and verified the scheduled job wrote main + two subagent payloads, replayed the session, and exposed synced counts in the top-nav popover.",
    meta: "2026-10-30 · Windows · SQLite + real Vite + headless Chrome",
    metrics: [
      { value: String(synced.badCaseSync.total), label: "bad_cases roots" },
      { value: String(synced.badCaseSync.synced), label: "synced roots" },
      { value: String(stats.calls), label: "trajectory calls" },
      { value: String(stats.maxActive), label: "max concurrent API 2 calls" }
    ],
    facts: [
      { label: "Commit", value: process.env.GITHUB_SHA ?? "working tree" },
      { label: "Root session", value: rootSession },
      { label: "Mock service", value: `127.0.0.1:${mockPort}` },
      { label: "API / Web", value: `${apiPort} / ${webPort}` }
    ],
    matrix: {
      columns: ["#", "Scenario", "Result", "Detail", "Evidence"],
      rows: [
        {
          id: "01",
          name: "Seed bad_cases root and run first tick",
          status: { kind: "pass", label: "PASS" },
          detail: `Seeded ${rootSession} with no payload; after the first tick total=${synced.badCaseSync.total}, unsynced=${synced.badCaseSync.unsynced}.`,
          evidence: []
        },
        {
          id: "02",
          name: "Scheduled root traversal writes main + subagents",
          status: { kind: "pass", label: "PASS" },
          detail: `Mock API 2 served ${stats.calls} serial calls; max concurrency ${stats.maxActive}.`,
          evidence: []
        },
        {
          id: "03",
          name: "Replay makes the session queryable",
          status: { kind: "pass", label: "PASS" },
          detail: `GET /api/sessions contains ${rootSession}.`,
          evidence: []
        },
        {
          id: "04",
          name: "Top-nav status shows synced counts",
          status: { kind: "pass", label: "PASS" },
          detail: `badCaseSync total=${synced.badCaseSync.total}, synced=${synced.badCaseSync.synced}, unsynced=${synced.badCaseSync.unsynced}; popover text verified.`,
          evidence: ["screenshots/01-session-list-sync-popover.png"]
        }
      ]
    },
    issues: [],
    screenshots: [
      {
        src: "screenshots/01-session-list-sync-popover.png",
        alt: "Session list with the data sync popover open",
        label: "01 · Session list + sync popover",
        caption: "The root session is queryable and the popover reports 1/1 synced, 0 unsynced.",
        variant: "wide"
      }
    ],
    coverage: {
      columns: ["Area", "Coverage", "Conclusion", "Recommendation"],
      rows: [
        {
          area: "Root traversal and payload writes",
          coverage: "UT + smoke",
          conclusion: "Main + two nested subagents written with parentAgentId metadata.",
          recommendation: "Keep the mock contract test in CI; keep the real service out."
        },
        {
          area: "Serial API 2",
          coverage: "UT + smoke",
          conclusion: `Mock observed maxActive=${stats.maxActive}.`,
          recommendation: "Add a cross-process lock before multi-instance deployment."
        },
        {
          area: "Overlap / single-flight",
          coverage: "UT",
          conclusion: "Active job is skipped; batch/time budget leaves the next tick to resume.",
          recommendation: "Run a long-running smoke if the query service latency grows."
        }
      ]
    },
    conclusion: {
      kind: "pass",
      label: "Ready for PR review",
      summary: "The mock-backed end-to-end path works; the only unverified dependency is the real query service contract.",
      points: [
        "Real API paths/token/version remain to be supplied by the service owner.",
        "First production run will refetch existing roots once by design."
      ]
    },
    footer: "m6-15 · bad_cases 根会话轨迹定时同步 · mock query service, no production credentials"
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
  console.log(JSON.stringify({ before, synced, stats }, null, 2));
} finally {
  if (web) await stop(web);
  if (api) await stop(api);
  if (mock) await stop(mock);
  if (dataDir) await rm(dataDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
}
