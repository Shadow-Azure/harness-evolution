import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
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
const secret = "m7-09-workspace-admin-signing-secret-with-sufficient-length";
const adminPassword = "m7-09-workspace-admin-initial-password";
const spaceAdminPassword = "m7-09-space-admin-initial-password";
const viewerPassword = "m7-09-viewer-initial-password";
let api;
let web;
let dataDir;
let baseUrl;
let apiLogs = "";
let webLogs = "";
let adminToken = "";
let adminId = "";
let spaceAdminId = "";
let viewerId = "";
let managedWorkspaceId = "";
let spaceAdminCookie = "";
let viewerCookie = "";
let spaceAdminToken = "";
let viewerToken = "";

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
  if (response.status !== 200) {
    assert.fail(
      `login ${username} returned ${response.status}: ${await response.text()}`,
    );
  }
  return {
    body: await response.json(),
    cookie: response.headers
      .get("set-cookie")
      ?.match(/refresh_token=([^;]+)/)?.[1],
  };
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

async function userSession(username, initialPassword, finalPassword) {
  const first = await login(username, initialPassword);
  await changePassword(first.body.accessToken, initialPassword, finalPassword);
  const second = await login(username, finalPassword);
  assert.ok(second.cookie, "expected a refresh cookie after login");
  return {
    accessToken: second.body.accessToken,
    cookie: second.cookie,
    userId: second.body.user.id,
  };
}

async function createUser(adminAccessToken, username, displayName, password) {
  return await apiJson("/api/users", adminAccessToken, {
    method: "POST",
    body: JSON.stringify({
      username,
      displayName,
      password,
      role: "member",
    }),
  });
}

async function installBrowser(page, cookie) {
  await page.session.send("Network.enable");
  await page.session.send("Network.setCookie", {
    name: "refresh_token",
    value: cookie,
    url: `${baseUrl}/api/auth`,
    httpOnly: true,
    sameSite: "Strict",
  });
  await page.session.send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 960,
    deviceScaleFactor: 1,
    mobile: false,
  });
}

async function openAdmin(page, workspaceId, tab = "spaces") {
  await page.session.send("Page.navigate", {
    url: `${baseUrl}/workspaces/${workspaceId}/admin?tab=${tab}`,
  });
  return await waitForDocument(
    page.session,
    `(() => {
      const page = document.querySelector("[data-testid='workspace-admin-page']");
      if (!page) return null;
      const tabs = document.querySelectorAll(".admin-nav button").length;
      if (tabs !== 5) return null;
      return {
        path: location.pathname,
        tabs,
        text: document.body.innerText,
      };
    })()`,
    `workspace admin page for ${workspaceId}`,
  );
}

async function clickTestId(page, testId) {
  await waitForDocument(
    page.session,
    `(() => {
      const element = document.querySelector(
        "[data-testid='${testId}']",
      );
      if (!element) return null;
      element.click();
      return true;
    })()`,
    `click ${testId}`,
  );
}

async function fillInput(page, testId, value) {
  await waitForDocument(
    page.session,
    `(() => {
      const input =
        document.querySelector("[data-testid='${testId}'] input") ??
        document.querySelector("input[data-testid='${testId}']");
      if (!input) return null;
      const setter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      ).set;
      setter.call(input, ${JSON.stringify(value)});
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    })()`,
    `fill ${testId}`,
  );
}

async function screenshot(page, filename) {
  await new Promise((resolve) => setTimeout(resolve, 600));
  const result = await page.session.send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
  });
  const { mkdir, writeFile } = await import("node:fs/promises");
  const directory = path.join(
    root,
    "reports",
    "2026-11-15",
    "m7-09-workspace-admin",
  );
  await mkdir(directory, { recursive: true });
  await writeFile(
    path.join(directory, filename),
    Buffer.from(result.data, "base64"),
  );
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m7-09-e2e-"));
  const baseEnv = {
    ...process.env,
    HE_ADMIN_PASSWORD: adminPassword,
    HE_ADMIN_USERNAME: "admin",
    HE_DATA_DIR: dataDir,
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: secret,
    HE_PHASE: "demo",
  };
  const seed = spawnSync(pnpm, ["fixtures:seed"], {
    cwd: root,
    env: baseEnv,
    encoding: "utf8",
  });
  assert.equal(seed.status, 0, seed.stderr || seed.stdout);

  const apiPort = await availablePort();
  const webPort = await availablePort();
  baseUrl = `http://127.0.0.1:${webPort}`;
  api = spawn(process.execPath, ["scripts/run-api.mjs", "start"], {
    cwd: root,
    env: {
      ...baseEnv,
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

  const admin = await login("admin", adminPassword);
  await changePassword(admin.body.accessToken, adminPassword, `${adminPassword}-next`);
  const adminRelogin = await login("admin", `${adminPassword}-next`);
  adminToken = adminRelogin.body.accessToken;
  adminId = adminRelogin.body.user.id;

  const spaceAdmin = await createUser(
    adminToken,
    "m709-space-admin",
    "空间管理员甲",
    spaceAdminPassword,
  );
  const viewer = await createUser(
    adminToken,
    "m709-viewer",
    "只读成员乙",
    viewerPassword,
  );
  const spaceAdminSession = await userSession(
    "m709-space-admin",
    spaceAdminPassword,
    `${spaceAdminPassword}-next`,
  );
  const viewerSession = await userSession(
    "m709-viewer",
    viewerPassword,
    `${viewerPassword}-next`,
  );
  spaceAdminId = spaceAdminSession.userId;
  viewerId = viewerSession.userId;
  spaceAdminCookie = spaceAdminSession.cookie;
  viewerCookie = viewerSession.cookie;
  spaceAdminToken = spaceAdminSession.accessToken;
  viewerToken = viewerSession.accessToken;

  const workspace = await apiJson("/api/workspaces", adminToken, {
    method: "POST",
    body: JSON.stringify({
      name: "E2E 管理空间",
      mark: "E2E",
      quota: 42,
      spaceAdminIds: [adminId, spaceAdminId],
    }),
  });
  managedWorkspaceId = workspace.id;
  await apiJson(`/api/workspaces/${managedWorkspaceId}/members`, adminToken, {
    method: "POST",
    body: JSON.stringify({ userId: viewerId, role: "viewer" }),
  });
});

after(cleanupRuntime);

test("m7-09 workspace-admin renders the global table and creates a workspace", async () => {
  const chat = await (async () => {
    const relogin = await login("admin", `${adminPassword}-next`);
    return relogin.cookie;
  })();
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: (entry) =>
        entry.text.includes("Download the Vue Devtools extension") ||
        entry.text.includes("Failed to load resource"),
    });
    await installBrowser(page, chat);
    const initial = await openAdmin(page, "ws-default");
    assert.equal(initial.path, "/workspaces/ws-default/admin");
    assert.match(initial.text, /全部工作空间/);
    assert.match(initial.text, /默认空间/);
    assert.match(initial.text, /E2E 管理空间/);
    await screenshot(page, "01-global-workspace-table.png");

    await clickTestId(page, "create-workspace");
    await waitForDocument(
      page.session,
      `document.querySelector("[data-testid='workspace-name-input'] input") !== null ||
        document.querySelector("input[data-testid='workspace-name-input']") !== null`,
      "workspace creation dialog",
    );
    await fillInput(page, "workspace-name-input", "E2E 新建空间");
    await fillInput(page, "workspace-mark-input", "NEW");
    await fillInput(page, "workspace-quota-input", "24");
    await screenshot(page, "02-create-workspace-dialog.png");
    await clickTestId(page, "workspace-form-submit");
    const created = await waitForDocument(
      page.session,
      `(() => {
        const rows = [...document.querySelectorAll("tbody tr")];
        const row = rows.find((item) => item.innerText.includes("E2E 新建空间"));
        if (!row) return null;
        return { text: row.innerText };
      })()`,
      "created workspace row",
    );
    assert.match(created.text, /24/);
    await screenshot(page, "02-workspace-created.png");

    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m7-09 workspace-admin gives space admins quota and member management", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: (entry) =>
        entry.text.includes("Download the Vue Devtools extension") ||
        entry.text.includes("Failed to load resource"),
    });
    await installBrowser(page, spaceAdminCookie);
    const pageState = await openAdmin(page, managedWorkspaceId);
    assert.match(pageState.text, /空间管理/);
    assert.match(pageState.text, /调整额度/);
    assert.match(pageState.text, /管理成员/);
    assert.doesNotMatch(pageState.text, /创建工作空间/);
    await screenshot(page, "03-space-admin-quota.png");

    await clickTestId(page, "admin-tab-members");
    const members = await waitForDocument(
      page.session,
      `(() => {
        const tab = document.querySelector("[data-testid='members-tab']");
        if (!tab) return null;
        if (!document.querySelector("[data-testid^='member-row-']")) return null;
        return { text: tab.innerText };
      })()`,
      "space-admin member table",
    );
    assert.match(members.text, /空间管理员甲/);
    assert.match(members.text, /只读成员乙/);
    assert.ok(spaceAdminToken);
    assert.equal(
      await page.session.send("Runtime.evaluate", {
        expression: `document.querySelectorAll("[data-testid='member-role-${spaceAdminId}']").length`,
        returnByValue: true,
      }).then((result) => result.result.value),
      0,
    );
    assert.ok(
      await page.session.send("Runtime.evaluate", {
        expression: `Boolean(document.querySelector("[data-testid='member-role-${viewerId}']"))`,
        returnByValue: true,
      }).then((result) => result.result.value),
    );
    const lockedTitle = await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector("[data-testid='member-locked-role']")?.getAttribute("title")`,
      returnByValue: true,
    });
    assert.match(String(lockedTitle.result.value), /空间管理员不能修改/);
    await screenshot(page, "04-members-role-lock.png");

    await clickTestId(page, "admin-tab-ingest");
    await clickTestId(page, "rotate-credential");
    const credential = await waitForDocument(
      page.session,
      `(() => {
        const secret = document.querySelector(
          "[data-testid='new-credential-plaintext']",
        );
        if (!secret) return null;
        return { text: secret.textContent };
      })()`,
      "one-time credential plaintext",
    );
    assert.match(credential.text, /^whk_/);
    await screenshot(page, "05-credential-once.png");
    await clickTestId(page, "acknowledge-credential");
    await waitForDocument(
      page.session,
      `document.querySelector("[data-testid='new-credential-plaintext']") === null`,
      "credential dialog closed",
    );
    const bodyText = await page.session.send("Runtime.evaluate", {
      expression: "document.body.innerText",
      returnByValue: true,
    });
    assert.ok(!String(bodyText.result.value).includes(credential.text));

    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m7-09 workspace-admin hides writes from viewers and the API still enforces roles", async () => {
  const credentialsResponse = await fetch(
    `${baseUrl}/api/workspaces/${managedWorkspaceId}/credentials`,
    {
      headers: { authorization: `Bearer ${viewerToken}` },
    },
  );
  assert.equal(credentialsResponse.status, 403);

  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: (entry) =>
        entry.text.includes("Download the Vue Devtools extension") ||
        entry.text.includes("Failed to load resource"),
    });
    await installBrowser(page, viewerCookie);
    const pageState = await openAdmin(page, managedWorkspaceId);
    assert.match(pageState.text, /只读/);
    assert.doesNotMatch(pageState.text, /创建工作空间/);

    await clickTestId(page, "admin-tab-members");
    const members = await waitForDocument(
      page.session,
      `(() => {
        const readonly = document.querySelector("[data-testid='members-readonly']");
        if (!readonly) return null;
        return {
          text: readonly.textContent,
          add: Boolean(document.querySelector("[data-testid='add-workspace-member']")),
          role: Boolean(document.querySelector("[data-testid='member-role-${viewerId}']")),
        };
      })()`,
      "viewer member table",
    );
    assert.equal(members.add, false);
    assert.equal(members.role, false);
    assert.match(members.text, /只读成员不能查看成员列表/);

    await clickTestId(page, "admin-tab-ingest");
    const ingest = await waitForDocument(
      page.session,
      `(() => {
        const readonly = document.querySelector("[data-testid='ingest-readonly']");
        if (!readonly) return null;
        return {
          text: readonly.textContent,
          rotate: Boolean(document.querySelector("[data-testid='rotate-credential']")),
        };
      })()`,
      "viewer ingest read-only state",
    );
    assert.equal(ingest.rotate, false);
    assert.match(ingest.text, /只有空间管理员及以上/);
    await screenshot(page, "06-viewer-readonly.png");

    await clickTestId(page, "admin-tab-attribution-skills");
    const skills = await waitForDocument(
      page.session,
      `(() => {
        const tab = document.querySelector("[data-testid='attribution-skills-tab']");
        const prompt = tab?.querySelector("[data-testid='skill-resource-prompt']");
        if (!prompt) return null;
        const download = tab.querySelector("[data-testid='download-skill-default-attribute-badcases']");
        return {
          prompt: prompt.textContent,
          files: tab.querySelector("[data-testid='skill-directory-tree']")?.textContent,
          canDownload: Boolean(download),
          canUpload: Boolean(tab.querySelector("[data-testid='upload-attribution-skill']")),
        };
      })()`,
      "viewer attribution Skill package and default prompt",
    );
    assert.match(skills.files, /make_probe_report\.py/);
    assert.match(skills.prompt, /name: attribute-badcases/);
    assert.equal(skills.canDownload, true);
    assert.equal(skills.canUpload, false);
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});
