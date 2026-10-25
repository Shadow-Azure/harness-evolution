import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";

const root = process.cwd();
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
let api;
let web;
let webBaseUrl;
let apiLogs = "";
let webLogs = "";
let dataDir;

const chromeCandidates = [
  process.env.CHROME_BIN,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome",
  "/usr/bin/google-chrome-stable",
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
].filter(Boolean);

function chromeExecutable() {
  const executable = chromeCandidates.find((candidate) => existsSync(candidate));
  if (!executable) {
    throw new Error(`Chrome executable not found; checked ${chromeCandidates.join(", ")}`);
  }
  return executable;
}

function capture(child, append) {
  child.stdout.on("data", (chunk) => append(String(chunk)));
  child.stderr.on("data", (chunk) => append(String(chunk)));
}

async function availablePort() {
  return await new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close();
        reject(new Error("failed to allocate a local port"));
        return;
      }
      const { port } = address;
      server.close((error) => (error ? reject(error) : resolve(port)));
    });
  });
}

async function waitFor(url, child, logs, accept = (response) => response.ok) {
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`process exited before ${url} was ready:\n${logs()}`);
    }
    try {
      const response = await fetch(url);
      if (accept(response)) return response;
    } catch {
      // The child has not bound its port yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`timed out waiting for ${url}:\n${logs()}`);
}

async function stop(child) {
  if (!child) return;
  child.stdout.destroy();
  child.stderr.destroy();
  if (child.exitCode !== null) return;
  const signal = (command) => {
    if (process.platform === "win32") {
      child.kill(command);
      return;
    }
    try {
      process.kill(-child.pid, command);
    } catch {
      child.kill(command);
    }
  };
  await new Promise((resolve) => {
    const timer = setTimeout(() => {
      signal("SIGKILL");
      resolve();
    }, 5_000);
    child.once("exit", () => {
      clearTimeout(timer);
      resolve();
    });
    signal("SIGTERM");
  });
}

async function waitForValue(read, label, timeout = 20_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const value = await read();
    if (value) return value;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`timed out waiting for ${label}`);
}

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

class CdpSession {
  constructor(url) {
    this.socket = new WebSocket(url);
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();
    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data));
      if (message.id) {
        const pending = this.pending.get(message.id);
        if (!pending) return;
        this.pending.delete(message.id);
        if (message.error) {
          pending.reject(new Error(`${pending.method}: ${message.error.message}`));
        } else {
          pending.resolve(message.result);
        }
        return;
      }
      for (const listener of this.listeners.get(message.method) ?? []) {
        listener(message.params);
      }
    });
  }

  async open() {
    if (this.socket.readyState === WebSocket.OPEN) return this;
    await new Promise((resolve, reject) => {
      this.socket.addEventListener("open", resolve, { once: true });
      this.socket.addEventListener("error", () => reject(new Error("CDP websocket failed")), {
        once: true,
      });
    });
    return this;
  }

  on(method, listener) {
    const listeners = this.listeners.get(method) ?? [];
    listeners.push(listener);
    this.listeners.set(method, listeners);
  }

  async send(method, params = {}) {
    const id = this.nextId++;
    const response = new Promise((resolve, reject) => {
      this.pending.set(id, { method, resolve, reject });
    });
    this.socket.send(JSON.stringify({ id, method, params }));
    return await response;
  }

  close() {
    this.socket.close();
  }
}

async function createBrowserPage() {
  const debuggingPort = await availablePort();
  const profileDir = await mkdtemp(path.join(tmpdir(), "harness-chrome-"));
  let logs = "";
  const browser = spawn(
    chromeExecutable(),
    [
      "--headless=new",
      "--no-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
      "--disable-background-networking",
      "--no-first-run",
      "--no-default-browser-check",
      `--remote-debugging-port=${debuggingPort}`,
      `--user-data-dir=${profileDir}`,
      "about:blank",
    ],
    {
      detached: process.platform !== "win32",
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  capture(browser, (chunk) => {
    logs += chunk;
  });
  await waitFor(
    `http://127.0.0.1:${debuggingPort}/json/version`,
    browser,
    () => logs,
  );
  const response = await fetch(
    `http://127.0.0.1:${debuggingPort}/json/new?about:blank`,
    { method: "PUT" },
  );
  assert.equal(response.ok, true, `failed to create Chrome target:\n${logs}`);
  const target = await response.json();
  const session = await new CdpSession(target.webSocketDebuggerUrl).open();
  await Promise.all([
    session.send("Page.enable"),
    session.send("Runtime.enable"),
    session.send("Log.enable"),
  ]);
  return {
    session,
    async close() {
      session.close();
      await stop(browser);
      await rm(profileDir, {
        recursive: true,
        force: true,
        maxRetries: 10,
        retryDelay: 100,
      });
    },
  };
}

async function waitForDocument(session, expression, label) {
  return await waitForValue(async () => {
    const result = await session.send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    return result.result.value;
  }, label);
}

function browserViolations(session) {
  const violations = [];
  session.on("Runtime.consoleAPICalled", ({ type, args }) => {
    if (type === "warning" || type === "error") {
      violations.push(
        `${type}: ${args.map((arg) => arg.value ?? arg.description ?? "").join(" ")}`,
      );
    }
  });
  session.on("Runtime.exceptionThrown", ({ exceptionDetails }) => {
    violations.push(`exception: ${exceptionDetails.text} ${exceptionDetails.exception?.description ?? ""}`);
  });
  session.on("Log.entryAdded", ({ entry }) => {
    const expectedAuthProbe =
      entry.source === "network" &&
      /Failed to load resource: the server responded with a status of (401|404)/.test(
        entry.text,
      );
    if (!expectedAuthProbe && (entry.level === "warning" || entry.level === "error")) {
      violations.push(`${entry.level}: ${entry.text}`);
    }
  });
  return violations;
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
    const violations = browserViolations(page.session);
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
