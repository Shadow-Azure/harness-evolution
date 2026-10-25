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
let api;
let web;
let webBaseUrl;
let apiLogs = "";
let webLogs = "";
let dataDir;

async function integrationAdmin() {
  for (const password of [
    "integration-initial-password",
    "integration-replacement-password",
  ]) {
    const response = await fetch(`${webBaseUrl}/api/auth/login`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ username: "admin", password }),
    });
    if (response.status === 200) return await response.json();
    if (response.status !== 401) {
      throw new Error(`unexpected admin login status ${response.status}`);
    }
  }
  throw new Error("integration administrator credentials are unavailable");
}

before(async () => {
  const apiPort = await availablePort();
  const webPort = await availablePort();
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-integration-"));
  webBaseUrl = `http://127.0.0.1:${webPort}`;

  api = spawn(process.execPath, ["scripts/run-api.mjs", "start"], {
    cwd: root,
    env: {
      ...process.env,
      HE_DOCS_ENABLED: "false",
      HE_DATA_DIR: dataDir,
      HE_DB_DIALECT: "sqlite",
      HE_JWT_SECRET: "integration-signing-secret-with-sufficient-length",
      HE_ADMIN_USERNAME: "admin",
      HE_ADMIN_PASSWORD: "integration-initial-password",
      HE_SSE_HEARTBEAT_SECONDS: "0.2",
      HE_HOST: "127.0.0.1",
      HE_PORT: String(apiPort),
      PYTHONUNBUFFERED: "1"
    },
    detached: process.platform !== "win32",
    stdio: ["ignore", "pipe", "pipe"]
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
      env: {
        ...process.env,
        HE_API_PROXY_URL: `http://127.0.0.1:${apiPort}`
      },
      detached: process.platform !== "win32",
      stdio: ["ignore", "pipe", "pipe"]
    }
  );
  capture(web, (chunk) => {
    webLogs += chunk;
  });
  await waitFor(webBaseUrl, web, () => webLogs);
});

after(async () => {
  await stop(web);
  await stop(api);
  if (dataDir) await rm(dataDir, { recursive: true, force: true });
});

test("health succeeds through the Vite proxy with the shared contract", async () => {
  const response = await fetch(`${webBaseUrl}/api/health`);
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.match(response.headers.get("x-request-id") ?? "", /\S/);
  assert.equal(body.ok, true);
  assert.equal(body.phase, "scaffold");
  assert.equal(body.service, "harness-evolution");
  assert.equal(body.version, "0.1.0");
  assert.equal(body.db.dialect, "sqlite");
  assert.equal(body.db.ok, true);
  assert.equal(typeof body.db.latencyMs, "number");
});

test("protected API failures keep the unified envelope through the proxy", async () => {
  const response = await fetch(`${webBaseUrl}/api/sessions`);
  const body = await response.json();

  assert.equal(response.status, 401);
  assert.deepEqual(body, {
    error: {
      code: "AUTH_REQUIRED",
      details: {},
      message: "authentication is required"
    }
  });
});

test("seeded admin completes forced password change through the proxy", async () => {
  const login = await fetch(`${webBaseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      username: "admin",
      password: "integration-initial-password"
    })
  });
  assert.equal(login.status, 200);
  const loginBody = await login.json();
  assert.equal(loginBody.user.username, "admin");
  assert.equal(loginBody.user.mustChangePassword, true);
  assert.equal("passwordHash" in loginBody.user, false);
  const refreshCookie = login.headers
    .get("set-cookie")
    ?.split(";")
    .find((part) => part.startsWith("refresh_token="));
  assert.match(refreshCookie ?? "", /refresh_token=\S+/);

  const before = await fetch(`${webBaseUrl}/api/auth/me`, {
    headers: { authorization: `Bearer ${loginBody.accessToken}` }
  });
  assert.equal(before.status, 200);
  assert.equal((await before.json()).mustChangePassword, true);

  const changed = await fetch(`${webBaseUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${loginBody.accessToken}`,
      "content-type": "application/json"
    },
    body: JSON.stringify({
      oldPassword: "integration-initial-password",
      newPassword: "integration-replacement-password"
    })
  });
  assert.equal(changed.status, 204);

  const refreshed = await fetch(`${webBaseUrl}/api/auth/refresh`, {
    method: "POST",
    headers: { cookie: refreshCookie }
  });
  assert.equal(refreshed.status, 200);
  const refreshBody = await refreshed.json();
  assert.deepEqual(Object.keys(refreshBody).sort(), ["accessToken", "expiresIn"]);

  const after = await fetch(`${webBaseUrl}/api/auth/me`, {
    headers: { authorization: `Bearer ${refreshBody.accessToken}` }
  });
  assert.equal(after.status, 200);
  assert.equal((await after.json()).mustChangePassword, false);
});

test("job lookup and one-time SSE ticket work through the real proxy", async () => {
  const admin = await integrationAdmin();
  const headers = { authorization: `Bearer ${admin.accessToken}` };
  const missing = await fetch(`${webBaseUrl}/api/jobs/not-a-real-job`, { headers });
  assert.equal(missing.status, 404);
  assert.equal((await missing.json()).error.code, "JOB_NOT_FOUND");

  const issued = await fetch(`${webBaseUrl}/api/events/ticket`, {
    method: "POST",
    headers: { ...headers, "content-type": "application/json" },
    body: JSON.stringify({ topics: ["run:integration-smoke"], lastEventId: 0 }),
  });
  assert.equal(issued.status, 200);
  const ticket = (await issued.json()).ticket;
  assert.match(ticket, /\S/);

  const controller = new AbortController();
  const stream = await fetch(
    `${webBaseUrl}/api/events?ticket=${encodeURIComponent(ticket)}`,
    { signal: controller.signal },
  );
  assert.equal(stream.status, 200);
  assert.match(stream.headers.get("content-type") ?? "", /text\/event-stream/);
  const reader = stream.body?.getReader();
  assert.ok(reader);
  let payload = "";
  const deadline = Date.now() + 5_000;
  while (!payload.includes("event: ping") && Date.now() < deadline) {
    const chunk = await reader.read();
    if (chunk.done) break;
    payload += new TextDecoder().decode(chunk.value);
  }
  controller.abort();
  assert.match(payload, /event: ping\r?\ndata: \{\}/);

  const replay = await fetch(
    `${webBaseUrl}/api/events?ticket=${encodeURIComponent(ticket)}`,
  );
  assert.equal(replay.status, 401);
  assert.equal((await replay.json()).error.code, "TICKET_INVALID");
});

test("database failure returns a sanitized 503 through the real proxy", async () => {
  const brokenApiPort = await availablePort();
  const brokenWebPort = await availablePort();
  const brokenDataDir = await mkdtemp(path.join(tmpdir(), "harness-broken-db-"));
  const brokenDbPath = path.join(brokenDataDir, "missing", "harness.db");
  const brokenWebUrl = `http://127.0.0.1:${brokenWebPort}`;
  let brokenApi;
  let brokenWeb;
  let brokenApiLogs = "";
  let brokenWebLogs = "";

  try {
    brokenApi = spawn(process.execPath, ["scripts/run-api.mjs", "start"], {
      cwd: root,
      env: {
        ...process.env,
        HE_DOCS_ENABLED: "false",
        HE_DB_DIALECT: "sqlite",
        HE_DB_URL: `sqlite+aiosqlite:///${brokenDbPath}`,
        HE_JWT_SECRET: "integration-signing-secret-with-sufficient-length",
        HE_HOST: "127.0.0.1",
        HE_PORT: String(brokenApiPort),
        PYTHONUNBUFFERED: "1"
      },
      detached: process.platform !== "win32",
      stdio: ["ignore", "pipe", "pipe"]
    });
    capture(brokenApi, (chunk) => {
      brokenApiLogs += chunk;
    });
    await waitFor(
      `http://127.0.0.1:${brokenApiPort}/api/health`,
      brokenApi,
      () => brokenApiLogs,
      (response) => response.status === 503
    );

    brokenWeb = spawn(
      pnpm,
      [
        "--filter",
        "@harness/web",
        "exec",
        "vite",
        "--host",
        "127.0.0.1",
        "--port",
        String(brokenWebPort),
        "--strictPort"
      ],
      {
        cwd: root,
        env: {
          ...process.env,
          HE_API_PROXY_URL: `http://127.0.0.1:${brokenApiPort}`
        },
        detached: process.platform !== "win32",
        stdio: ["ignore", "pipe", "pipe"]
      }
    );
    capture(brokenWeb, (chunk) => {
      brokenWebLogs += chunk;
    });
    await waitFor(brokenWebUrl, brokenWeb, () => brokenWebLogs);

    const response = await fetch(`${brokenWebUrl}/api/health`);
    const rawBody = await response.text();
    const body = JSON.parse(rawBody);

    assert.equal(response.status, 503);
    assert.equal(body.ok, false);
    assert.equal(body.db.dialect, "sqlite");
    assert.equal(body.db.ok, false);
    assert.equal(typeof body.db.error, "string");
    assert.doesNotMatch(rawBody, /super-secret|db\.internal/);
    const escapedDbPath = brokenDbPath.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    assert.doesNotMatch(rawBody, new RegExp(escapedDbPath));
    assert.doesNotMatch(brokenApiLogs, new RegExp(escapedDbPath));
  } finally {
    await stop(brokenWeb);
    await stop(brokenApi);
    await rm(brokenDataDir, { recursive: true, force: true });
  }
});

test("browser renders the login form and narrow shell without console or layout errors", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: (entry) =>
        entry.source === "network" &&
        entry.url?.endsWith("/api/auth/refresh") &&
        /status of 401/.test(entry.text),
    });
    const webLogOffset = webLogs.length;
    await page.session.send("Page.navigate", {
      url: `${webBaseUrl}/login?redirect=/sessions`,
    });
    await waitForDocument(
      page.session,
      "document.readyState === 'complete' && Boolean(document.querySelector('form'))",
      "login page",
    );
    await page.session.send("Runtime.evaluate", {
      expression: `(() => {
        for (const [selector, value] of [
          ['#login-username', 'admin'],
          ['#login-password', 'temporary-password'],
        ]) {
          const input = document.querySelector(selector);
          const setter = Object.getOwnPropertyDescriptor(
            HTMLInputElement.prototype,
            'value',
          ).set;
          setter.call(input, value);
          input.dispatchEvent(new InputEvent('input', { bubbles: true }));
        }
      })()`,
    });
    await new Promise((resolve) => setTimeout(resolve, 2_500));
    const browserWebLogs = webLogs.slice(webLogOffset);
    assert.doesNotMatch(
      browserWebLogs,
      /optimized dependencies changed\. reloading/i,
      `First browser page must load without a dependency reload:\n${browserWebLogs}`,
    );
    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);

    let login = await fetch(`${webBaseUrl}/api/auth/login`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        username: "admin",
        password: "integration-initial-password",
      }),
    });
    if (login.status === 200) {
      const body = await login.json();
      assert.equal(body.user.mustChangePassword, true);
      const changed = await fetch(`${webBaseUrl}/api/auth/change-password`, {
        method: "POST",
        headers: {
          authorization: `Bearer ${body.accessToken}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({
          oldPassword: "integration-initial-password",
          newPassword: "integration-replacement-password",
        }),
      });
      assert.equal(changed.status, 204);
      const initialRefreshCookie = login.headers
        .get("set-cookie")
        ?.match(/refresh_token=([^;]+)/)?.[1];
      assert.ok(initialRefreshCookie);
      login = await fetch(`${webBaseUrl}/api/auth/refresh`, {
        method: "POST",
        headers: { cookie: `refresh_token=${initialRefreshCookie}` },
      });
    }
    if (login.status === 401) {
      login = await fetch(`${webBaseUrl}/api/auth/login`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          username: "admin",
          password: "integration-replacement-password",
        }),
      });
    }
    assert.equal(login.status, 200);
    const refreshCookie = login.headers
      .get("set-cookie")
      ?.match(/refresh_token=([^;]+)/)?.[1];
    assert.ok(refreshCookie);
    await page.session.send("Network.enable");
    await page.session.send("Network.setCookie", {
      name: "refresh_token",
      value: refreshCookie,
      url: `${webBaseUrl}/api/auth`,
      httpOnly: true,
      sameSite: "Strict",
    });
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    await page.session.send("Page.navigate", { url: `${webBaseUrl}/sessions` });
    const layout = await waitForDocument(
      page.session,
      `(() => {
        const menu = document.querySelector(".user-menu");
        if (!menu) return null;
        return {
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
          menuRight: menu.getBoundingClientRect().right,
        };
      })()`,
      "authenticated narrow shell",
    );
    const layoutContext = `${JSON.stringify(layout)}\n\nVite:\n${webLogs}`;
    assert.ok(layout.scrollWidth <= layout.clientWidth, layoutContext);
    assert.ok(layout.menuRight <= layout.clientWidth, layoutContext);
    const userMenu = await page.session.send("Runtime.evaluate", {
      expression: `(() => {
        const menu = document.querySelector(".user-menu");
        menu.open = true;
        const button = menu.querySelector("button[data-testid='logout']");
        const bounds = button.getBoundingClientRect();
        return {
          open: menu.open,
          buttonLeft: bounds.left,
          buttonRight: bounds.right,
          buttonWidth: bounds.width,
        };
      })()`,
      returnByValue: true,
    });
    const menu = userMenu.result.value;
    assert.equal(menu.open, true);
    assert.ok(menu.buttonWidth > 0, JSON.stringify(menu));
    assert.ok(menu.buttonLeft >= 0, JSON.stringify(menu));
    assert.ok(menu.buttonRight <= layout.clientWidth, JSON.stringify(menu));
    assert.deepEqual(violations, []);
  } finally {
    await page.close();
  }
});
