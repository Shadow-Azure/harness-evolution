import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdir, readFile, mkdtemp, rm, writeFile } from "node:fs/promises";
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
const captureDir = process.env.HE_M12_13_CAPTURE_DIR;
const secret = "m12-13-admin-copy-signing-secret-with-sufficient-length";
const initialPassword = "m12-13-admin-initial-password";
const adminPassword = `${initialPassword}-next`;
let api;
let web;
let dataDir;
let baseUrl;
let apiLogs = "";
let webLogs = "";
let adminToken = "";
let adminId = "";
let workspaceId = "";
let adminCookie = "";

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
  return {
    body: await response.json(),
    cookie: response.headers
      .get("set-cookie")
      ?.match(/refresh_token=([^;]+)/)?.[1],
  };
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

async function openAdmin(page, tab) {
  await page.session.send("Page.navigate", {
    url: `${baseUrl}/workspaces/${workspaceId}/admin?tab=${tab}`,
  });
  return await waitForDocument(
    page.session,
    `(() => {
      const page = document.querySelector("[data-testid='workspace-admin-page']");
      const content = document.querySelector("[data-testid='admin-content']");
      if (!page || !content) return null;
      return { text: content.innerText };
    })()`,
    `workspace admin page tab ${tab}`,
  );
}

async function clickTestId(page, testId) {
  await waitForDocument(
    page.session,
    `(() => {
      const element = document.querySelector("[data-testid='${testId}']");
      if (!element) return null;
      element.click();
      return true;
    })()`,
    `click ${testId}`,
  );
}

async function screenshot(page, filename) {
  if (!captureDir) return;
  const directory = path.resolve(root, captureDir);
  await mkdir(directory, { recursive: true });
  // Let layout, fonts and the codebox settle before the capture.
  await new Promise((resolve) => setTimeout(resolve, 400));
  const result = await page.session.send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
  });
  await writeFile(
    path.join(directory, filename),
    Buffer.from(result.data, "base64"),
  );
}

async function evaluate(page, expression) {
  const result = await page.session.send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  return result.result.value;
}

async function jsonFile(relativePath) {
  return JSON.parse(await readFile(path.resolve(root, relativePath), "utf8"));
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m12-13-e2e-"));
  const baseEnv = {
    ...process.env,
    HE_ADMIN_PASSWORD: initialPassword,
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

  const first = await login("admin", initialPassword);
  const changed = await fetch(`${baseUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${first.body.accessToken}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      oldPassword: initialPassword,
      newPassword: adminPassword,
    }),
  });
  assert.equal(changed.status, 204);
  const second = await login("admin", adminPassword);
  assert.ok(second.cookie, "login must set a refresh cookie");
  adminToken = second.body.accessToken;
  adminId = second.body.user.id;
  adminCookie = second.cookie;

  const workspace = await apiJson("/api/workspaces", adminToken, {
    method: "POST",
    body: JSON.stringify({
      name: "M12-13 文案空间",
      mark: "MD",
      quota: 42,
      spaceAdminIds: [adminId],
    }),
  });
  workspaceId = workspace.id;
  await apiJson(`/api/workspaces/${workspaceId}/credentials`, adminToken, {
    method: "POST",
  });
});

after(cleanupRuntime);

test("m12-13 admin spaces copy states a global admin can add themself", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session);
    const session = await login("admin", adminPassword);
    await installBrowser(page, session.cookie);
    await openAdmin(page, "spaces");
    await waitForDocument(
      page.session,
      `(() => {
        const page = document.querySelector("[data-testid='workspace-admin-page']");
        const row = document.querySelector(
          "[data-testid='workspace-row-${workspaceId}']",
        );
        return page && row ? true : null;
      })()`,
      "global workspace table with the fixture workspace",
    );
    await screenshot(page, "01-spaces.png");
    const text = await evaluate(page, "document.body.innerText");
    assert.match(text, /任意用户（包括自己）/);
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m12-13 auth copy matches the username and access-token contract", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session);
    const session = await login("admin", adminPassword);
    await installBrowser(page, session.cookie);
    await openAdmin(page, "spaces");
    await clickTestId(page, "admin-tab-auth");
    await waitForDocument(
      page.session,
      `document.querySelector("[data-testid='auth-contract']")?.textContent.includes("GET /api/auth/session")
        ? true
        : null`,
      "auth contract block",
    );
    await screenshot(page, "02-auth-session.png");
    await evaluate(
      page,
      `(() => {
        const box = document.querySelector("[data-testid='auth-contract']");
        box.scrollTop = box.scrollHeight;
        document
          .querySelector("[data-testid='auth-tab'] .field-help")
          .scrollIntoView({ block: "end" });
        return true;
      })()`,
    );
    await screenshot(page, "03-auth-login.png");
    const text = await evaluate(page, "document.body.innerText");
    const contract = await evaluate(
      page,
      "document.querySelector(\"[data-testid='auth-contract']\").textContent",
    );
    assert.match(contract, /POST \/api\/auth\/login\s+\{ "username":/);
    assert.match(contract, /"accessToken"/);
    assert.match(contract, /"expiresIn"/);
    assert.match(contract, /refresh_token/);
    assert.match(contract, /SameSite=Strict/);
    assert.doesNotMatch(contract, /"global_role"/);
    assert.doesNotMatch(text, /演示账号/);
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m12-13 ingest copy uses the camelCase bad case contract", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session);
    const session = await login("admin", adminPassword);
    await installBrowser(page, session.cookie);
    await openAdmin(page, "spaces");
    await clickTestId(page, "admin-tab-ingest");
    await waitForDocument(
      page.session,
      `document.querySelector("[data-testid='ingest-body-example']")?.textContent.includes("badCaseId")
        ? true
        : null`,
      "ingest body example",
    );
    await evaluate(
      page,
      `document.querySelector("[data-testid='ingest-body-example']").scrollIntoView({ block: "center" })`,
    );
    await screenshot(page, "04-ingest.png");
    const example = await evaluate(
      page,
      "document.querySelector(\"[data-testid='ingest-body-example']\").textContent",
    );
    const text = await evaluate(page, "document.body.innerText");
    assert.match(example, /"badCaseId"/);
    assert.match(example, /"sessionId"/);
    assert.match(example, /"badCaseType"/);
    assert.doesNotMatch(example, /session_id|bad_case_type/);
    assert.match(text, /body 不接受 workspace 字段，多带会返回/);
    assert.match(text, /422/);
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});

test("m12-13 prototype and design copy stay aligned with OpenAPI", async () => {
  const openapi = await jsonFile("packages/contracts/openapi.json");
  const schemas = openapi.components.schemas;
  const authTab = await readFile(
    path.resolve(root, "apps/web/src/pages/workspaces/components/AuthTab.vue"),
    "utf8",
  );
  const spacesTab = await readFile(
    path.resolve(root, "apps/web/src/pages/workspaces/components/SpacesTab.vue"),
    "utf8",
  );
  const ingestHelper = await readFile(
    path.resolve(root, "apps/web/src/composables/useWorkspaces.ts"),
    "utf8",
  );
  const prototype = await readFile(
    path.resolve(root, "plans/ui-prototype-v2/harness-evolution.html"),
    "utf8",
  );
  const design = await readFile(
    path.resolve(root, "plans/ui-prototype-v2/design-v2.md"),
    "utf8",
  );

  assert.match(spacesTab, /任意用户（包括自己）/);
  assert.match(prototype, /任意用户（包括自己）/);

  for (const field of schemas.PublicUser.required) {
    assert.match(
      authTab,
      new RegExp(`"${field}"`),
      `auth contract must show PublicUser.${field}`,
    );
  }
  for (const field of schemas.SessionWorkspace.required) {
    assert.match(
      authTab,
      new RegExp(`"${field}"`),
      `auth contract must show SessionWorkspace.${field}`,
    );
  }
  for (const field of schemas.LoginRequest.required) {
    assert.match(authTab, new RegExp(`"${field}"`));
    assert.match(prototype, new RegExp(`"${field}"`));
  }
  for (const field of schemas.LoginResponse.required) {
    assert.match(authTab, new RegExp(`"${field}"`));
    assert.match(prototype, new RegExp(`"${field}"`));
  }
  assert.doesNotMatch(authTab, /globalRole|演示账号|he_session/);
  assert.doesNotMatch(prototype, /"email": "\.\.\.", "password"|global_role|he_session/);
  assert.doesNotMatch(design, /he_session|204 \+ Set-Cookie/);
  assert.match(design, /refresh_token/);
  assert.match(design, /accessToken/);

  for (const field of schemas.BadCaseIngest.required) {
    assert.match(
      ingestHelper,
      new RegExp(`\\b${field}:`),
      `ingest example must send BadCaseIngest.${field}`,
    );
    assert.match(
      prototype,
      new RegExp(`\\b${field}:`),
      `prototype ingest example must show ${field}`,
    );
  }
  assert.doesNotMatch(ingestHelper, /bad_case_type:/);
  assert.doesNotMatch(prototype, /session_id:|bad_case_type:/);
  assert.match(design, /badCaseId/);
  assert.doesNotMatch(design, /session_id \/ object_name \/ bad_case_type/);

  assert.match(design, /username/);
  assert.match(prototype, /包括自己/);
});
