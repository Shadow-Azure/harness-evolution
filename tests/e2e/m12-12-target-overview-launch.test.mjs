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
const captureDir = process.env.HE_M12_12_CAPTURE_DIR;
const secret = "m12-12-target-launch-signing-secret-with-sufficient-length";
const initialPassword = "m12-12-target-launch-initial-password";
const adminPassword = "m12-12-target-launch-admin-password";
const viewerInitialPassword = "m12-12-target-launch-viewer-initial";
const viewerPassword = "m12-12-target-launch-viewer-password";
const workspaceId = "ws-default";
let api;
let web;
let dataDir;
let baseUrl;
let apiLogs = "";
let webLogs = "";
let adminToken = "";
let adminId = "";
let emptyWorkspaceId = "";

async function cleanupRuntime() {
  await stop(web);
  await stop(api);
  if (dataDir) await rm(dataDir, { recursive: true, force: true });
}

for (const [signal, exitCode] of [
  ["SIGINT", 130],
  ["SIGTERM", 143],
]) {
  process.once(signal, () => {
    void cleanupRuntime().finally(() => process.exit(exitCode));
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

async function login(username, password) {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  assert.equal(response.status, 200);
  const body = await response.json();
  const cookie = response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie, "login must set a refresh cookie");
  return { body, cookie };
}

async function changePassword(token, oldPassword, newPassword) {
  const response = await fetch(`${baseUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({ oldPassword, newPassword }),
  });
  if (response.status !== 204) {
    assert.fail(
      `change-password returned ${response.status}: ${await response.text()}`,
    );
  }
}

async function installBrowser(page, cookie, size = { width: 1408, height: 788 }) {
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
    ...size,
    deviceScaleFactor: 2,
    mobile: false,
  });
}

async function nextFrame(page) {
  await page.session.send("Runtime.evaluate", {
    expression:
      "new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))",
    awaitPromise: true,
  });
}

async function captureScreenshot(page, name) {
  if (!captureDir) return;
  await mkdir(captureDir, { recursive: true });
  const { data } = await page.session.send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
  });
  await writeFile(path.join(captureDir, name), Buffer.from(data, "base64"));
}

async function click(page, selector) {
  await waitForDocument(
    page.session,
    `(() => {
      const element = document.querySelector(${JSON.stringify(selector)});
      if (!element) return null;
      element.click();
      return true;
    })()`,
    `click ${selector}`,
  );
}

async function openTargets(page, wid = workspaceId) {
  await page.session.send("Page.navigate", {
    url: `${baseUrl}/workspaces/${wid}/overview?tab=targets`,
  });
  return await waitForDocument(
    page.session,
    `(() => {
      const stats = document.querySelector("[data-testid='ov-target-stats']");
      const tab = document.querySelector("[data-testid='ov-tab-targets']");
      if (!stats || !tab || !tab.classList.contains("active")) return null;
      return {
        search: location.search,
        create: Boolean(
          document.querySelector("[data-testid='ov-target-create']"),
        ),
        launch: Boolean(
          document.querySelector("[data-testid='ov-target-launch']"),
        ),
        readonly: Boolean(document.querySelector(".head-actions .readonly")),
      };
    })()`,
    "target overview header",
  );
}

function expectedLogEntry(entry) {
  return (
    entry.text.includes("Download the Vue Devtools extension") ||
    entry.text.includes("Failed to load resource")
  );
}

async function seedAdmin() {
  const first = await login("admin", initialPassword);
  await changePassword(first.body.accessToken, initialPassword, adminPassword);
  const second = await login("admin", adminPassword);
  adminToken = second.body.accessToken;
  const session = await apiJson("/api/auth/session", adminToken);
  adminId = session.user.id;

  const empty = await apiJson("/api/workspaces", adminToken, {
    method: "POST",
    body: JSON.stringify({
      name: "M12-12 空对象",
      mark: "M1212",
      quota: 20,
      spaceAdminIds: [adminId],
    }),
  });
  emptyWorkspaceId = empty.id;

  const viewer = await apiJson("/api/users", adminToken, {
    method: "POST",
    body: JSON.stringify({
      username: "m12-12-viewer",
      displayName: "只读成员",
      password: viewerInitialPassword,
      role: "member",
    }),
  });
  const viewerLogin = await login("m12-12-viewer", viewerInitialPassword);
  await changePassword(
    viewerLogin.body.accessToken,
    viewerInitialPassword,
    viewerPassword,
  );
  await apiJson(`/api/workspaces/${workspaceId}/members`, adminToken, {
    method: "POST",
    body: JSON.stringify({ userId: viewer.id, role: "viewer" }),
  });
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m12-12-e2e-"));
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
  await seedAdmin();
});

after(cleanupRuntime);

test("m12-12 admin target overview exposes create and launch actions", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    const adminCookie = await login("admin", adminPassword);
    await installBrowser(page, adminCookie.cookie);
    const header = await openTargets(page);
    await waitForDocument(
      page.session,
      `document.querySelectorAll("[data-testid^='ov-target-side-item-']").length > 0`,
      "target rows before capture",
    );
    await nextFrame(page);
    await captureScreenshot(page, "after-target-overview-admin.png");

    assert.equal(header.create, true);
    assert.equal(header.launch, true);
    assert.equal(header.readonly, false);
    assert.equal(
      await page.session
        .send("Runtime.evaluate", {
          expression:
            "document.querySelector(\"[data-testid='ov-target-launch']\").className",
          returnByValue: true,
        })
        .then((result) => result.result.value),
      "head-btn primary",
    );
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m12-12 target overview opens the existing empty-config guard, closes, and keeps the workspace", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    const adminCookie = await login("admin", adminPassword);
    await installBrowser(page, adminCookie.cookie);
    const header = await openTargets(page, emptyWorkspaceId);
    assert.equal(header.create, true);
    assert.equal(header.launch, true);

    await click(page, "[data-testid='ov-target-launch']");
    await waitForDocument(
      page.session,
      `(() => {
        const empty = document.querySelector("[data-testid='wizard-config-empty']");
        if (!empty) return null;
        return { text: empty.textContent ?? "" };
      })()`,
      "empty target configuration guard",
    );
    await nextFrame(page);
    await captureScreenshot(page, "after-target-overview-config-guard.png");

    await click(page, "[aria-label='关闭向导']");
    const closed = await waitForDocument(
      page.session,
      `(() => {
        if (document.querySelector("[data-testid='launch-wizard']")) return null;
        const tab = document.querySelector("[data-testid='ov-tab-targets']");
        if (!tab || !tab.classList.contains("active")) return null;
        return { search: location.search };
      })()`,
      "wizard closed on the empty target overview",
    );
    assert.match(closed.search, /tab=targets/);
    assert.equal(
      await page.session
        .send("Runtime.evaluate", {
          expression:
            "location.pathname.includes(\"/overview\") && Boolean(document.querySelector(\"[data-testid='ov-target-launch']\"))",
          returnByValue: true,
        })
        .then((result) => result.result.value),
      true,
    );

    await click(page, "[data-testid='ov-target-launch']");
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-testid='wizard-target-config-link']"))`,
      "empty configuration link after reopening the wizard",
    );
    await click(page, "[data-testid='wizard-target-config-link']");
    await waitForDocument(
      page.session,
      `(() => {
        if (location.pathname !== ${JSON.stringify(
          `/workspaces/${emptyWorkspaceId}/evolution/targets`,
        )}) {
          return null;
        }
        return { path: location.pathname };
      })()`,
      "target configuration jump keeps the current workspace",
    );
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m12-12 target overview hides write actions from a read-only member", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: expectedLogEntry,
    });
    const viewer = await login("m12-12-viewer", viewerPassword);
    await installBrowser(page, viewer.cookie);
    const header = await openTargets(page);
    await waitForDocument(
      page.session,
      `document.querySelectorAll("[data-testid^='ov-target-side-item-']").length > 0`,
      "target rows before read-only capture",
    );
    await nextFrame(page);
    await captureScreenshot(page, "after-target-overview-viewer.png");

    assert.equal(header.create, false);
    assert.equal(header.launch, false);
    assert.equal(header.readonly, true);
    const readonly = await waitForDocument(
      page.session,
      `document.querySelector(".head-actions .readonly")?.textContent ?? null`,
      "read-only target overview notice",
    );
    assert.match(readonly, /只读访问/);
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});
