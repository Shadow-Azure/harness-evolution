import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
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
const apiDir = path.join(root, "apps/api");
const python = path.join(
  apiDir,
  ".venv",
  process.platform === "win32" ? "Scripts" : "bin",
  process.platform === "win32" ? "python.exe" : "python",
);
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const initialPassword = "m11-04-smoke-initial-password";
const replacementPassword = "m11-04-smoke-replacement-password";
const secret = "m11-04-smoke-signing-secret-with-sufficient-length";
const screenshotDir = process.env.M11_04_SCREENSHOT_DIR ?? "";
const workspaceId = "ws-default";
let api;
let web;
let dataDir;
let baseUrl;
let apiLogs = "";
let webLogs = "";
let emptyWorkspaceId = "";
let authSession = null;
let currentPassword = initialPassword;

async function cleanup() {
  await stop(web);
  await stop(api);
  if (dataDir) await rm(dataDir, { recursive: true, force: true });
}

for (const [signal, exitCode] of [
  ["SIGINT", 130],
  ["SIGTERM", 143],
]) {
  process.once(signal, () => {
    void cleanup().finally(() => process.exit(exitCode));
  });
}

async function apiJson(pathname, token, init = {}) {
  const response = await fetch(`${baseUrl}${pathname}`, {
    ...init,
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  if (!response.ok) {
    assert.fail(
      `${pathname} returned ${response.status}: ${await response.text()}`,
    );
  }
  return response.status === 204 ? null : await response.json();
}

async function loginAndRotatePassword() {
  const login = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: initialPassword }),
  });
  assert.equal(login.status, 200);
  const loginBody = await login.json();
  assert.ok(loginBody.accessToken);
  const changed = await fetch(`${baseUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${loginBody.accessToken}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      oldPassword: initialPassword,
      newPassword: replacementPassword,
    }),
  });
  assert.equal(changed.status, 204);

  const refreshed = await fetch(`${baseUrl}/api/auth/refresh`, {
    method: "POST",
    headers: {
      cookie: `refresh_token=${
        login.headers.get("set-cookie")?.match(/refresh_token=([^;]+)/)?.[1]
      }`,
    },
  });
  assert.equal(refreshed.status, 200);
  const access = await refreshed.json();
  const cookie = refreshed.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie);
  currentPassword = replacementPassword;
  return { accessToken: access.accessToken, cookie };
}

async function loginCookie() {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: currentPassword }),
  });
  assert.equal(response.status, 200);
  const cookie = response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie, "login must set a refresh cookie");
  return cookie;
}

async function installBrowser(page, cookie) {
  await page.session.send("Network.enable");
  await page.session.send("Network.setCookie", {
    name: "refresh_token",
    value: cookie,
    url: `${baseUrl}/api/auth`,
    path: "/api/auth",
    httpOnly: true,
    sameSite: "Strict",
  });
  await page.session.send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 980,
    deviceScaleFactor: 1,
    mobile: false,
  });
}

async function evaluate(page, expression) {
  const result = await page.session.send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (result.exceptionDetails) {
    throw new Error(
      result.exceptionDetails.exception?.description ??
        result.exceptionDetails.text,
    );
  }
  return result.result.value;
}

async function click(page, selector) {
  await waitForDocument(
    page.session,
    `(() => {
      const element = document.querySelector(${JSON.stringify(selector)});
      if (!element) return null;
      element.dispatchEvent(
        new MouseEvent("click", { bubbles: true, cancelable: true, view: window }),
      );
      return true;
    })()`,
    `click ${selector}`,
  );
}

async function setControl(page, selector, value) {
  await waitForDocument(
    page.session,
    `(() => {
      const element = document.querySelector(${JSON.stringify(selector)});
      if (!element) return null;
      element.value = ${JSON.stringify(value)};
      element.dispatchEvent(new Event("input", { bubbles: true }));
      element.dispatchEvent(new Event("change", { bubbles: true }));
      return element.value === ${JSON.stringify(value)};
    })()`,
    `set ${selector}`,
  );
}

async function navigateTargets(page, wid = workspaceId) {
  await page.session.send("Page.navigate", {
    url: `${baseUrl}/workspaces/${wid}/overview?tab=targets`,
  });
  return await waitForDocument(
    page.session,
    `(() => {
      const stats = document.querySelector("[data-testid='ov-target-stats']");
      const tab = document.querySelector("[data-testid='ov-tab-targets']");
      if (!stats || !tab || !tab.classList.contains("active")) return null;
      if (document.querySelectorAll("[data-testid='ov-target-case-row']").length === 0) {
        return null;
      }
      return {
        search: location.search,
        targets: document.querySelector("[data-testid='ov-target-stat-targets']")?.textContent?.trim(),
        sessions: document.querySelector("[data-testid='ov-target-stat-sessions']")?.textContent?.trim(),
        potential: document.querySelector("[data-testid='ov-target-stat-potential']")?.textContent?.trim(),
        attributed: document.querySelector("[data-testid='ov-target-stat-attributed']")?.textContent?.trim(),
        nonTarget: document.querySelector("[data-testid='ov-target-stat-nontarget']")?.textContent?.trim(),
        unanalyzed: document.querySelector("[data-testid='ov-target-stat-unanalyzed']")?.textContent?.trim(),
        sideItems: document.querySelectorAll("[data-testid^='ov-target-side-item-']").length,
        caseRows: document.querySelectorAll("[data-testid='ov-target-case-row']").length,
      };
    })()`,
    "target overview data",
  );
}

async function waitForUrlParam(page, key, value) {
  await waitForDocument(
    page.session,
    `new URLSearchParams(location.search).get(${JSON.stringify(key)}) === ${JSON.stringify(value)}`,
    `URL parameter ${key}=${value}`,
  );
}

function expectedLogEntry(entry) {
  return (
    entry.text.includes("Download the Vue Devtools extension") ||
    entry.text.includes("Failed to load resource")
  );
}

async function screenshot(page, name, full = true) {
  if (!screenshotDir) return;
  await mkdir(screenshotDir, { recursive: true });
  await page.session.send("Page.enable");
  const contentHeight = await evaluate(
    page,
    `document.querySelector("[data-testid='overview-page']")?.scrollHeight ?? 0`,
  );
  await page.session.send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: full ? Math.max(980, Number(contentHeight) + 70) : 980,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await new Promise((resolve) => setTimeout(resolve, 200));
  const result = await page.session.send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: true,
  });
  await writeFile(
    path.join(screenshotDir, name),
    Buffer.from(result.data, "base64"),
  );
  await page.session.send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 980,
    deviceScaleFactor: 1,
    mobile: false,
  });
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m11-04-e2e-"));
  const env = {
    ...process.env,
    HE_ADMIN_PASSWORD: initialPassword,
    HE_ADMIN_USERNAME: "admin",
    HE_DATA_DIR: dataDir,
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: secret,
    HE_LOGIN_RATE_LIMIT: "100",
    HE_PHASE: "demo",
    PYTHONPATH: apiDir,
  };
  const seed = spawnSync(pnpm, ["fixtures:seed"], {
    cwd: root,
    env,
    encoding: "utf8",
  });
  assert.equal(seed.status, 0, seed.stderr || seed.stdout);
  const targetSeed = spawnSync(
    python,
    [
      path.join(root, "tests/e2e/support/m11_04_target_overview_seed.py"),
      "--data-dir",
      dataDir,
    ],
    { cwd: root, env, encoding: "utf8" },
  );
  assert.equal(targetSeed.status, 0, targetSeed.stderr || targetSeed.stdout);

  const apiPort = await availablePort();
  const webPort = await availablePort();
  baseUrl = `http://127.0.0.1:${webPort}`;
  api = spawn(process.execPath, ["scripts/run-api.mjs", "start"], {
    cwd: root,
    env: {
      ...env,
      HE_DOCS_ENABLED: "false",
      HE_HOST: "127.0.0.1",
      HE_PORT: String(apiPort),
      HE_SYNC_INTERVAL_SECONDS: "0",
      PYTHONUNBUFFERED: "1",
    },
    detached: process.platform !== "win32",
    stdio: ["ignore", "pipe", "pipe"],
  });
  capture(api, (chunk) => {
    apiLogs += chunk;
  });
  await waitFor(`http://127.0.0.1:${apiPort}/api/health`, api, () => apiLogs);

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
      env: { ...process.env, HE_API_PROXY_URL: `http://127.0.0.1:${apiPort}` },
      detached: process.platform !== "win32",
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  capture(web, (chunk) => {
    webLogs += chunk;
  });
  await waitFor(baseUrl, web, () => webLogs);

  const session = await loginAndRotatePassword();
  const me = await apiJson("/api/auth/session", session.accessToken);
  const created = await apiJson("/api/workspaces", session.accessToken, {
    method: "POST",
    body: JSON.stringify({
      name: "M11-04 空空间",
      mark: "M1104",
      quota: 10,
      spaceAdminIds: [me.user.id],
    }),
  });
  emptyWorkspaceId = created.id;
  authSession = session;
});

after(cleanup);

test("m11-04 target overview renders, filters, paginates, and analyses one object", async () => {
  const page = await createBrowserPage();
  const violations = browserViolations(page.session, {
    isExpectedLogEntry: expectedLogEntry,
  });
  try {
    await installBrowser(page, await loginCookie());
    const ready = await navigateTargets(page);
    assert.equal(ready.targets, "6");
    assert.equal(ready.sessions, "1");
    assert.equal(ready.potential, "3");
    assert.equal(ready.attributed, "1");
    assert.equal(ready.nonTarget, "1");
    assert.equal(ready.unanalyzed, "1");
    assert.equal(ready.sideItems, 5);
    assert.equal(ready.caseRows, 3);
    const scrollable = await evaluate(
      page,
      `(() => {
        const pageRoot = document.querySelector("[data-testid='overview-page']");
        if (!pageRoot || pageRoot.scrollHeight <= pageRoot.clientHeight) return null;
        pageRoot.scrollTop = pageRoot.scrollHeight;
        return {
          scrollTop: pageRoot.scrollTop,
          detailVisible: document.querySelector("[data-testid='ov-target-detail']").getBoundingClientRect().top < innerHeight,
          listVisible: document.querySelector("[data-testid='ov-target-case-list']").getBoundingClientRect().top < innerHeight,
        };
      })()`,
    );
    assert.ok(scrollable && scrollable.scrollTop > 0, "overview page must scroll");
    assert.equal(scrollable.detailVisible, true);
    assert.equal(scrollable.listVisible, true);
    await evaluate(
      page,
      `document.querySelector("[data-testid='overview-page']").scrollTop = 0`,
    );
    await screenshot(page, "01-targets-overview.png", false);
    await screenshot(page, "06-targets-overview-full.png", true);

    await click(page, "[data-testid='ov-target-side-next']");
    await waitForUrlParam(page, "tpage", "2");
    await waitForDocument(
      page.session,
      `document.querySelectorAll("[data-testid^='ov-target-side-item-']").length === 1`,
      "second target page",
    );
    await screenshot(page, "02-targets-side-page-2.png");
    await click(page, "[data-testid='ov-target-side-prev']");
    await waitForDocument(
      page.session,
      `document.querySelectorAll("[data-testid^='ov-target-side-item-']").length === 5`,
      "first target page",
    );

    await click(page, "[data-testid='ov-target-metric-unanalyzed']");
    await waitForUrlParam(page, "states", "attributed,nonTarget");
    await click(page, "[data-testid='ov-target-metric-unanalyzed']");
    await waitForDocument(
      page.session,
      `!new URLSearchParams(location.search).has("states")`,
      "all target states restored",
    );

    await click(page, "[data-bucket='2026-10-19']");
    await waitForUrlParam(page, "cfrom", "2026-10-19");
    await waitForUrlParam(page, "cto", "2026-10-25");
    await setControl(page, "[data-testid='ov-target-case-state']", "nonTarget");
    await waitForUrlParam(page, "cstate", "nonTarget");
    await waitForDocument(
      page.session,
      `document.querySelectorAll("[data-testid='ov-target-case-row']").length === 1`,
      "one non-target case row",
    );
    await screenshot(page, "03-targets-filtered.png");
    await click(page, "[data-testid='ov-target-case-reset']");
    await waitForDocument(
      page.session,
      `document.querySelectorAll("[data-testid='ov-target-case-row']").length === 3`,
      "reset case filters",
    );

    await setControl(page, "[data-testid='ov-target-detail-from']", "2026-10-20");
    await waitForUrlParam(page, "dfrom", "2026-10-20");
    await setControl(page, "[data-testid='ov-target-detail-to']", "2026-10-31");
    await waitForUrlParam(page, "dto", "2026-10-31");
    await evaluate(
      page,
      `(() => {
        const details = document.querySelector("[data-testid='ov-target-detail-versions']");
        if (details) details.open = true;
        return true;
      })()`,
    );
    await click(page, "input[data-version='main']");
    await waitForUrlParam(page, "dversions", "main");
    await waitForDocument(
      page.session,
      `document.querySelector("[data-testid='ov-target-detail-potential']")?.textContent?.trim() === "0"`,
      "independent version scope",
    );
    await click(page, "input[data-version='main']");
    await waitForDocument(
      page.session,
      `document.querySelector("[data-testid='ov-target-detail-potential']")?.textContent?.trim() === "3"`,
      "restored version scope",
    );

    await click(page, "[data-testid='ov-tab-cases']");
    await waitForDocument(
      page.session,
      `location.search.includes("tab=cases") &&
       location.search.includes("range=90") &&
       document.querySelector("[data-testid='ov-case-list']") !== null`,
      "cases tab with the shared window",
    );
    await click(page, "[data-testid='ov-tab-targets']");
    await waitForDocument(
      page.session,
      `location.search.includes("tab=targets") &&
       new URLSearchParams(location.search).get("range") === "90" &&
       document.querySelector("[data-testid='ov-target-stats']") !== null`,
      "targets tab restores the shared window",
    );

    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m11-04 target overview prompts for configuration when no target exists", async () => {
  const page = await createBrowserPage();
  const violations = browserViolations(page.session, {
    isExpectedLogEntry: expectedLogEntry,
  });
  try {
    await installBrowser(page, await loginCookie());
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/workspaces/${emptyWorkspaceId}/overview?tab=targets`,
    });
    await waitForDocument(
      page.session,
      `(() => {
        if (!document.querySelector("[data-testid='ov-target-side-empty']")) return null;
        if (!document.querySelector("[data-testid='ov-target-detail-empty']")) return null;
        return document.querySelector("[data-testid='ov-target-stat-targets']")?.textContent?.trim();
      })()`,
      "empty target overview",
    );
    await screenshot(page, "04-targets-empty.png");
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});
