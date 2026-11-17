import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";

import {
  availablePort,
  browserViolations,
  capture,
  createBrowserPage,
  stop,
  waitFor,
  waitForDocument,
} from "../support/runtime.mjs";

const root = process.cwd();
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const initialPassword = "m12-07-initial-password";
const secret = "m12-07-trace-state-signing-secret-with-length";
const ws = "/workspaces/ws-default";
const casesBase = `/api/workspaces/ws-default/bad-cases`;
let api;
let web;
let dataDir;
let baseUrl;
let apiUrl;
let apiLogs = "";
let webLogs = "";
let currentPassword = initialPassword;

async function cleanup() {
  await stop(web);
  await stop(api);
  if (dataDir) await rm(dataDir, { recursive: true, force: true });
}

async function loginSession() {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: currentPassword }),
  });
  assert.equal(response.status, 200);
  const login = await response.json();
  const initialCookie = response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(initialCookie);

  const replacement = "m12-07-replacement-password";
  const changed = await fetch(`${baseUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${login.accessToken}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      oldPassword: currentPassword,
      newPassword: replacement,
    }),
  });
  assert.equal(changed.status, 204);
  currentPassword = replacement;

  const refreshed = await fetch(`${baseUrl}/api/auth/refresh`, {
    method: "POST",
    headers: { cookie: `refresh_token=${initialCookie}` },
  });
  assert.equal(refreshed.status, 200);
  const access = await refreshed.json();
  const cookie = refreshed.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie);
  return { accessToken: access.accessToken, cookie };
}

async function installCookie(page, cookie) {
  await page.session.send("Network.enable");
  await page.session.send("Network.setCookie", {
    name: "refresh_token",
    value: cookie,
    url: `${baseUrl}/api/auth`,
    httpOnly: true,
    sameSite: "Strict",
  });
}

async function clientNavigate(page, pathname) {
  await page.session.send("Runtime.evaluate", {
    expression: `history.pushState({}, "", ${JSON.stringify(pathname)});
      window.dispatchEvent(new PopStateEvent("popstate"));`,
  });
}

async function detail(accessToken, caseId) {
  return await fetch(`${apiUrl}${casesBase}/${caseId}`, {
    headers: { authorization: `Bearer ${accessToken}` },
  });
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m12-07-e2e-"));
  const seedEnv = {
    ...process.env,
    HE_ADMIN_PASSWORD: initialPassword,
    HE_ADMIN_USERNAME: "admin",
    HE_DATA_DIR: dataDir,
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: secret,
    HE_PHASE: "demo",
  };
  const seed = spawn(pnpm, ["fixtures:seed"], {
    cwd: root,
    env: seedEnv,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let seedLogs = "";
  capture(seed, (chunk) => {
    seedLogs += chunk;
  });
  const seedExit = await new Promise((resolve) => {
    seed.once("exit", (code) => resolve(code));
  });
  assert.equal(seedExit, 0, seedLogs);

  const statusSeed = spawn(
    path.join(root, "apps/api/.venv/bin/python"),
    ["tests/e2e/support/m12_07_seed.py", "--data-dir", dataDir],
    { cwd: root, stdio: ["ignore", "pipe", "pipe"] },
  );
  let statusSeedLogs = "";
  capture(statusSeed, (chunk) => {
    statusSeedLogs += chunk;
  });
  const statusExit = await new Promise((resolve) => {
    statusSeed.once("exit", (code) => resolve(code));
  });
  assert.equal(statusExit, 0, statusSeedLogs);

  const apiPort = await availablePort();
  const webPort = await availablePort();
  apiUrl = `http://127.0.0.1:${apiPort}`;
  baseUrl = `http://127.0.0.1:${webPort}`;
  api = spawn(process.execPath, ["scripts/run-api.mjs", "start"], {
    cwd: root,
    env: {
      ...seedEnv,
      HE_DOCS_ENABLED: "false",
      HE_HOST: "127.0.0.1",
      HE_PORT: String(apiPort),
      HE_SYNC_INTERVAL_SECONDS: "0",
      HE_BAD_CASE_SYNC_INTERVAL_SECONDS: "0",
      PYTHONUNBUFFERED: "1",
    },
    detached: process.platform !== "win32",
    stdio: ["ignore", "pipe", "pipe"],
  });
  capture(api, (chunk) => {
    apiLogs += chunk;
  });
  await waitFor(`${apiUrl}/api/health`, api, () => apiLogs);

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
      detached: process.platform !== "win32",
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  capture(web, (chunk) => {
    webLogs += chunk;
  });
  await waitFor(baseUrl, web, () => webLogs);
});

after(cleanup);

test("m12-07 bad case without a Session shows trace state instead of 404", async () => {
  const auth = await loginSession();

  const list = await fetch(`${apiUrl}${casesBase}?pageSize=50`, {
    headers: { authorization: `Bearer ${auth.accessToken}` },
  });
  const listText = await list.text();
  assert.equal(list.status, 200, listText);
  const items = new Map(
    JSON.parse(listText).items.map((item) => [item.badCaseId, item]),
  );
  assert.equal(items.get("m12-07-ready")?.syncStatus, "ready");
  assert.equal(items.get("m12-07-pending")?.syncStatus, "pending");
  assert.equal(items.get("m12-07-syncing")?.syncStatus, "syncing");
  assert.equal(items.get("m12-07-failed")?.syncStatus, "failed");
  assert.equal(items.get("m12-07-unavailable")?.syncStatus, "unavailable");
  assert.equal(items.get("m12-07-unavailable")?.retryable, false);

  const pending = await detail(auth.accessToken, "m12-07-pending");
  assert.equal(pending.status, 409);
  assert.equal((await pending.json()).error.code, "BAD_CASE_SESSION_PENDING");
  const unavailable = await detail(auth.accessToken, "m12-07-unavailable");
  assert.equal(unavailable.status, 503);
  const unavailableError = (await unavailable.json()).error;
  assert.equal(unavailableError.code, "BAD_CASE_SESSION_UNAVAILABLE");
  assert.equal(unavailableError.details.syncStatus, "unavailable");
  assert.equal(unavailableError.details.lastError, "SESSION_QUERY_UNAVAILABLE");

  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: (entry) => {
        if (entry.source !== "network" || !entry.url) return false;
        if (/status of (409|503)/.test(entry.text)) {
          return entry.url.includes("/bad-cases/");
        }
        // The route names a reported root that has no normalized Session yet;
        // its summary/tree/list reads legitimately answer 404 and the page
        // renders the trace panel from the case error instead.
        return (
          /status of 404/.test(entry.text) &&
          /\/(30000000-0000-4000-8000-000000000(101|104))(\/|$)/.test(entry.url)
        );
      },
    });
    await installCookie(page, auth.cookie);
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1440,
      height: 960,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.session.send("Page.navigate", { url: `${baseUrl}/sessions` });
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector(".shell"))`,
      "authenticated shell",
    );
    await waitForDocument(
      page.session,
      `/^\\/workspaces\\/ws-default\\/sessions\\/[0-9a-f-]{36}$/.test(location.pathname)`,
      "session auto-selection settled",
    );
    await clientNavigate(page, `${ws}/overview`);
    const chips = await waitForDocument(
      page.session,
      `(() => {
        const rows = [...document.querySelectorAll("[data-testid='ov-case-row']")];
        if (rows.length === 0) return null;
        const text = document.body.textContent;
        const pending = document.querySelector("[data-testid='ov-case-view-m12-07-pending']");
        const unavailable = document.querySelector("[data-testid='ov-trace-m12-07-unavailable']");
        if (!pending || !unavailable) return null;
        return {
          text,
          unavailableChip: unavailable.textContent.trim(),
          pendingChip: document.querySelector("[data-testid='ov-trace-m12-07-pending']")?.textContent.trim(),
          readyLink: Boolean(document.querySelector("[data-testid='ov-case-link-m12-07-ready']")),
        };
      })()`,
      "overview trace chips",
    );
    assert.equal(chips.pendingChip, "未同步");
    assert.equal(chips.unavailableChip, "无可用轨迹");
    assert.equal(chips.readyLink, true);
    assert.doesNotMatch(chips.text, /问题不存在或已删除/);

    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector("[data-testid='ov-case-view-m12-07-pending']").click()`,
    });
    const pendingView = await waitForDocument(
      page.session,
      `(() => {
        const panel = document.querySelector("[data-testid='trace-status-panel']");
        if (!panel) return null;
        return {
          text: panel.textContent,
          chip: document.querySelector("[data-testid='trace-status-chip']")?.textContent.trim(),
          body: document.body.textContent,
        };
      })()`,
      "pending trace panel",
    );
    assert.equal(pendingView.chip, "未同步");
    assert.match(pendingView.text, /没有被删除/);
    assert.match(pendingView.text, /不会自动重试/);
    assert.match(pendingView.text, /m12-07-pending/);
    assert.doesNotMatch(pendingView.body, /问题不存在或已删除/);
    assert.equal(
      await page.session.send("Runtime.evaluate", {
        expression: `Boolean(document.querySelector("[data-testid='errors-agent-tree']"))`,
        returnByValue: true,
      }).then((result) => result.result.value),
      false,
    );

    await clientNavigate(page, `${ws}/overview`);
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-testid='ov-case-view-m12-07-unavailable']"))`,
      "overview restored",
    );
    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector("[data-testid='ov-case-view-m12-07-unavailable']").click()`,
    });
    const unavailableView = await waitForDocument(
      page.session,
      `(() => {
        const panel = document.querySelector("[data-testid='trace-status-panel']");
        if (!panel) return null;
        return {
          chip: document.querySelector("[data-testid='trace-status-chip']")?.textContent.trim(),
          text: panel.textContent,
        };
      })()`,
      "unavailable trace panel",
    );
    assert.equal(unavailableView.chip, "无可用轨迹");
    assert.match(unavailableView.text, /SESSION_QUERY_UNAVAILABLE/);
    assert.match(unavailableView.text, /不会自动重试/);

    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});
