import assert from "node:assert/strict";
import { spawn } from "node:child_process";
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
    ["--filter", "@harness/web", "exec", "vite", "--host", "127.0.0.1", "--port", String(webPort), "--strictPort"],
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
