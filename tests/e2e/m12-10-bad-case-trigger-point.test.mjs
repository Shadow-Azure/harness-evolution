import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";

import {
  availablePort,
  capture,
  createBrowserPage,
  stop,
  waitFor,
  waitForDocument,
} from "../support/runtime.mjs";

const root = process.cwd();
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const secret = "m12-10-trigger-point-signing-secret-with-length";
const initialPassword = "m12-10-initial-password";
const replacementPassword = "m12-10-replacement-password";
const workspaceId = "ws-default";
const sessionId = "10000000-0000-4000-8000-000000000001";
const casesBase = `/api/workspaces/${workspaceId}/bad-cases`;
let api;
let web;
let dataDir;
let baseUrl;
let apiUrl;
let apiLogs = "";
let webLogs = "";
let auth = {};

async function cleanup() {
  await stop(web);
  await stop(api);
  if (dataDir) await rm(dataDir, { recursive: true, force: true });
}

async function loginSession() {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: initialPassword }),
  });
  assert.equal(response.status, 200);
  const login = await response.json();
  const initialCookie = response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(initialCookie);

  const changed = await fetch(`${baseUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${login.accessToken}`,
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

async function installCookie(page) {
  await page.session.send("Network.enable");
  await page.session.send("Network.setCookie", {
    name: "refresh_token",
    value: auth.cookie,
    url: `${baseUrl}/api/auth`,
    path: "/api/auth",
    httpOnly: true,
    sameSite: "Strict",
  });
  await page.session.send("Emulation.setDeviceMetricsOverride", {
    width: 1408,
    height: 900,
    deviceScaleFactor: 1,
    mobile: false,
  });
}

async function getJson(pathname) {
  const response = await fetch(`${apiUrl}${pathname}`, {
    headers: { authorization: `Bearer ${auth.accessToken}` },
  });
  const text = await response.text();
  assert.equal(response.status, 200, text);
  return JSON.parse(text);
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m12-10-e2e-"));
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
  const seedExit = await new Promise((resolve) => seed.once("exit", resolve));
  assert.equal(seedExit, 0, seedLogs);

  const triggerSeed = spawn(
    path.join(root, "apps/api/.venv/bin/python"),
    ["tests/e2e/support/m12_10_seed.py", "--data-dir", dataDir],
    { cwd: root, stdio: ["ignore", "pipe", "pipe"] },
  );
  let triggerLogs = "";
  capture(triggerSeed, (chunk) => {
    triggerLogs += chunk;
  });
  const triggerExit = await new Promise((resolve) =>
    triggerSeed.once("exit", resolve),
  );
  assert.equal(triggerExit, 0, triggerLogs);

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

test("m12-10 overview trigger point matches the error-detail marker", async () => {
  auth = await loginSession();

  const list = await getJson(`${casesBase}?pageSize=50`);
  const items = new Map(list.items.map((item) => [item.badCaseId, item]));
  const anchored = items.get("m12-10-anchored");
  const missing = items.get("m12-10-null");
  assert.equal(anchored?.triggerLine, 2);
  assert.equal(missing?.triggerLine, null);
  assert.equal(anchored?.triggerAt, anchored?.createdAt);

  const tree = await getJson(
    `/api/workspaces/${workspaceId}/sessions/${sessionId}/tree`,
  );
  const treeCase = tree.badCases.find(
    (item) => item.badCaseId === "m12-10-anchored",
  );
  assert.ok(treeCase);
  const host = tree.agents.find(
    (agent) => agent.agentId === treeCase.anchor.agentId,
  );
  assert.ok(host);
  const anchorEvent = host.events[treeCase.anchor.eventIndex];
  assert.ok(anchorEvent);
  assert.equal(anchorEvent.line, anchored.triggerLine);
  assert.equal(anchorEvent.name, "m12-10-anchor-skill");

  const page = await createBrowserPage();
  try {
    await installCookie(page);
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/workspaces/${workspaceId}/overview`,
    });
    const cells = await waitForDocument(
      page.session,
      `(() => {
        const anchored = document.querySelector(
          "[data-testid='ov-trigger-line-m12-10-anchored']",
        );
        const missing = document.querySelector(
          "[data-testid='ov-trigger-line-m12-10-null']",
        );
        if (!anchored || !missing) return null;
        return {
          anchored: anchored.textContent.trim(),
          missing: missing.textContent.trim(),
        };
      })()`,
      "overview trigger line values",
    );
    assert.equal(cells.anchored, "L2");
    assert.equal(cells.missing, "—");

    await page.session.send("Page.navigate", {
      url: `${baseUrl}/workspaces/${workspaceId}/sessions/${sessionId}/errors?case=m12-10-anchored&tab=desc`,
    });
    const selected = await waitForDocument(
      page.session,
      `(() => {
        const marker = document.querySelector("[data-testid='lane-selected-case']");
        if (!marker) return null;
        const text = marker.textContent.trim();
        return text.includes("L2") ? text : null;
      })()`,
      "error-detail selected BC marker",
    );
    assert.match(selected, /m12-10 m12-10-anchored/);
    assert.match(selected, /L2/);
  } finally {
    await page.close();
  }
});
