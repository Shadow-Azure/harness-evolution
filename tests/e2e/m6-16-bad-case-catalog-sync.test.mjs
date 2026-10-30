import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";

import {
  availablePort,
  capture,
  stop,
  waitFor,
} from "../support/runtime.mjs";

const root = process.cwd();
const apiDir = path.join(root, "apps/api");
const python = path.join(
  apiDir,
  ".venv",
  process.platform === "win32" ? "Scripts" : "bin",
  process.platform === "win32" ? "python.exe" : "python",
);
const rootSession = "11111111-1111-4111-8111-111111111111";
const adminPassword = "m6-16-catalog-admin";
const replacementPassword = "m6-16-catalog-replacement";
const secret = "m6-16-catalog-sync-signing-secret-with-sufficient-length";

let api;
let mock;
let dataDir;
let apiUrl;
let mockUrl;
let apiLogs = "";
let mockLogs = "";

async function waitForStatus(token, predicate) {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    const response = await fetch(`${apiUrl}/api/acquisition/status`, {
      headers: { authorization: `Bearer ${token}` },
    });
    assert.equal(response.status, 200);
    const payload = await response.json();
    if (predicate(payload)) return payload;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`catalog sync did not converge:\n${apiLogs}`);
}

async function waitForSession(token) {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    const response = await fetch(`${apiUrl}/api/sessions`, {
      headers: { authorization: `Bearer ${token}` },
    });
    assert.equal(response.status, 200);
    const payload = await response.json();
    if (payload.items.some((item) => item.id === rootSession)) {
      return payload;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`root session was not normalized:\n${apiLogs}`);
}

async function authenticate() {
  const login = await fetch(`${apiUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: adminPassword }),
  });
  assert.equal(login.status, 200);
  const initial = await login.json();
  const changed = await fetch(`${apiUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${initial.accessToken}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      oldPassword: adminPassword,
      newPassword: replacementPassword,
    }),
  });
  assert.equal(changed.status, 204);
  const authenticated = await fetch(`${apiUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      username: "admin",
      password: replacementPassword,
    }),
  });
  assert.equal(authenticated.status, 200);
  return (await authenticated.json()).accessToken;
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m6-16-catalog-e2e-"));
  const mockPort = await availablePort();
  const apiPort = await availablePort();
  mockUrl = `http://127.0.0.1:${mockPort}`;
  apiUrl = `http://127.0.0.1:${apiPort}`;
  const pythonEnv = { ...process.env, PYTHONPATH: apiDir };

  mock = spawn(
    python,
    [
      path.join(root, "tests/e2e/support/mock_catalog_upstream.py"),
      "--port",
      String(mockPort),
      "--delay",
      "0.01",
    ],
    {
      cwd: root,
      env: pythonEnv,
      detached: process.platform !== "win32",
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  capture(mock, (chunk) => {
    mockLogs += chunk;
  });
  await waitFor(`${mockUrl}/__stats`, mock, () => mockLogs);

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
    {
      cwd: root,
      env: pythonEnv,
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  let prepareLogs = "";
  capture(prepare, (chunk) => {
    prepareLogs += chunk;
  });
  const prepareExit = await new Promise((resolve) => {
    prepare.once("exit", (code) => resolve(code));
  });
  assert.equal(prepareExit, 0, prepareLogs);

  api = spawn(process.execPath, ["scripts/run-api.mjs", "start"], {
    cwd: root,
    env: {
      ...process.env,
      HE_ADMIN_PASSWORD: adminPassword,
      HE_ADMIN_USERNAME: "admin",
      HE_BAD_CASE_CATALOG_SYNC_INTERVAL_SECONDS: "0",
      HE_BAD_CASE_QUERY_BASE_URL: mockUrl,
      HE_BAD_CASE_QUERY_RETRY_ATTEMPTS: "0",
      HE_BAD_CASE_QUERY_TOKEN: "mock-token",
      HE_BAD_CASE_SYNC_INTERVAL_SECONDS: "1",
      HE_DATA_DIR: dataDir,
      HE_DB_DIALECT: "sqlite",
      HE_DOCS_ENABLED: "false",
      HE_HOST: "127.0.0.1",
      HE_JWT_SECRET: secret,
      HE_PORT: String(apiPort),
      HE_SESSION_QUERY_BASE_URL: mockUrl,
      HE_SESSION_QUERY_RETRY_ATTEMPTS: "0",
      HE_SESSION_QUERY_TOKEN: "mock-token",
      HE_SYNC_INTERVAL_SECONDS: "0",
      PYTHONUNBUFFERED: "1",
    },
    detached: process.platform !== "win32",
    stdio: ["ignore", "pipe", "pipe"],
  });
  capture(api, (chunk) => {
    apiLogs += chunk;
  });
  await waitFor(`${apiUrl}/api/health`, api, () => apiLogs);
});

after(async () => {
  await stop(api);
  await stop(mock);
  if (dataDir) await rm(dataDir, { recursive: true, force: true });
});

test("m6-16 catalog sync fills bad_cases and the root trace chain", async () => {
  const token = await authenticate();
  const headers = { authorization: `Bearer ${token}` };

  const status = await waitForStatus(
    token,
    (payload) =>
      payload.badCaseCatalogSync.synced === 3 &&
      payload.badCaseCatalogSync.unsynced === 0 &&
      payload.badCaseSync.synced === 1,
  );

  assert.equal(status.badCaseCatalogSync.lastBadCaseId, 3);
  assert.equal(status.badCaseCatalogSync.status, "idle");
  assert.equal(status.badCaseSync.total, 1);

  const sessionBody = await waitForSession(token);
  assert.ok(
    sessionBody.items.some((item) => item.id === rootSession),
    "root session should be normalized after the trace backfill",
  );

  const problems = await fetch(
    `${apiUrl}/api/sessions/${rootSession}/bad-cases`,
    { headers },
  );
  assert.equal(problems.status, 200);
  const problemBody = await problems.json();
  assert.equal(problemBody.items.length, 3);
  assert.deepEqual(
    problemBody.items.map((item) => item.title).sort(),
    ["Mock problem 1", "Mock problem 2", "Mock problem 3"],
  );

  const stats = await fetch(`${mockUrl}/__stats`);
  const counters = await stats.json();
  assert.ok(counters.catalogCalls >= 1);
  assert.ok(counters.trajectoryCalls >= 3);
  assert.equal(
    counters.maxActive <= 1,
    true,
    "trajectory calls must stay serial",
  );
});
