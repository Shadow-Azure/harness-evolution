import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";

import {
  availablePort,
  browserViolations,
  capture,
  createBrowserPage,
  stop,
} from "../support/runtime.mjs";

const root = process.cwd();
const apiDir = path.join(root, "apps/api");
const python = path.join(
  apiDir,
  ".venv",
  process.platform === "win32" ? "Scripts" : "bin",
  process.platform === "win32" ? "python.exe" : "python",
);
function spawnPnpm(args, options) {
  return process.env.npm_execpath
    ? spawn(process.execPath, [process.env.npm_execpath, ...args], options)
    : spawn("pnpm", args, options);
}
const initialPassword = "pause-436-initial-password";
const finalPassword = "pause-436-final-password";
const secret = "pause-436-signing-secret-with-sufficient-length";
const ws = "/workspaces/ws-default";
let api;
let web;
let dataDir;
let screenshotDir;
let baseUrl;
let apiLogs = "";
let webLogs = "";

async function waitForReady(url, child, logs) {
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`server exited: ${logs()}`);
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(2_000) });
      if (response.ok) return;
    } catch { /* Cold Windows imports can take longer than the shared 20s budget. */ }
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  throw new Error(`server readiness deadline exceeded: ${url}\n${logs()}`);
}

async function stopOwnedProcess(child) {
  if (process.platform !== "win32" || !child?.pid || child.exitCode !== null) return stop(child);
  // Windows venv and pnpm launchers have child servers that outlive their parent.
  const killer = spawn("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error(`process cleanup timed out: ${child.pid}`)), 10_000);
    killer.once("error", error => { clearTimeout(timeout); reject(error); });
    killer.once("exit", code => { clearTimeout(timeout); resolve(code); });
  });
}

async function cleanup() {
  await stopOwnedProcess(web);
  await stopOwnedProcess(api);
  if (dataDir) await rm(dataDir, { recursive: true, force: true, maxRetries: 20, retryDelay: 200 });
  if (screenshotDir && process.env.HE_KEEP_E2E_ARTIFACTS !== "1") {
    await rm(screenshotDir, { recursive: true, force: true });
  } else if (screenshotDir) {
    console.log(`issue-436 pause screenshots: ${screenshotDir}`);
  }
}

async function loginCookie() {
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
      newPassword: finalPassword,
    }),
  });
  assert.equal(changed.status, 204);
  const refreshed = await fetch(`${baseUrl}/api/auth/refresh`, {
    method: "POST",
    headers: { cookie: `refresh_token=${initialCookie}` },
  });
  assert.equal(refreshed.status, 200);
  return refreshed.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
}

async function installCookie(page, cookie) {
  await page.session.send("Network.enable");
  await page.session.send("Network.setCookie", {
    name: "refresh_token",
    value: cookie,
    url: `${baseUrl}/api/auth`,
    path: "/api/auth",
    httpOnly: true,
    sameSite: "Strict",
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
      result.exceptionDetails.exception?.description ?? result.exceptionDetails.text,
    );
  }
  return result.result.value;
}

async function clickControl(page, selector) {
  const point = await evaluate(page, `(() => { const r=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2}; })()`);
  await page.session.send("Input.dispatchMouseEvent", {type:"mousePressed",...point,button:"left",clickCount:1});
  await page.session.send("Input.dispatchMouseEvent", {type:"mouseReleased",...point,button:"left",clickCount:1});
}

async function screenshot(page, filename) {
  const { data } = await page.session.send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: false,
  });
  await writeFile(path.join(screenshotDir, filename), data, "base64");
}

async function seedRunDetail() {
  const child = spawn(
    python,
    [path.join(root, "tests/e2e/support/issue_436_pause_fixture.py")],
    {
      cwd: root,
      env: {
        ...process.env,
        HE_DATA_DIR: dataDir,
        HE_DB_DIALECT: "sqlite",
        HE_JWT_SECRET: secret,
        PYTHONPATH: apiDir,
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  let output = "";
  capture(child, (chunk) => {
    output += chunk;
  });
  const code = await new Promise((resolve) => child.once("exit", resolve));
  assert.equal(code, 0, output);
}

async function waitForUI(session, expression) {
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    const result = await session.send("Runtime.evaluate", { expression, returnByValue: true });
    if (result.result.value) return result.result.value;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`UI readiness deadline exceeded: ${expression}`);
}

async function openLogs(page) {
  await evaluate(page, `document.querySelector("[data-testid='logs-tab']").click()`);
}

async function openRun(page, runId, query = "") {
  await page.session.send("Page.navigate", {
    url: `${baseUrl}${ws}/evolution/runs/${runId}${query}`,
  });
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-pause-436-e2e-"));
  screenshotDir = await mkdtemp(
    path.join(tmpdir(), "harness-pause-436-screenshots-"),
  );
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
  const setup = spawnPnpm(["fixtures:seed"], {
    cwd: root,
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let setupOutput = "";
  capture(setup, (chunk) => {
    setupOutput += chunk;
  });
  const setupExit = await new Promise((resolve) => setup.once("exit", resolve));
  assert.equal(setupExit, 0, setupOutput);

  const apiPort = await availablePort();
  const webPort = await availablePort();
  baseUrl = `http://127.0.0.1:${webPort}`;
  api = spawn(python, ["tests/e2e/support/issue_436_pause_server.py"], {
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
  await waitForReady(`http://127.0.0.1:${apiPort}/api/health`, api, () => apiLogs);
  await seedRunDetail();

  web = spawnPnpm(
    [
      "--filter",
      "@harness/web",
      "exec",
      "vite",
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
  await waitForReady(baseUrl, web, () => webLogs);
});

after(cleanup);

test("issue-436 pauses a run from its card, preserves it across reload, and continues from detail", async () => {
  const page = await createBrowserPage();
  const violations = browserViolations(page.session);
  const pendingRequests = new Map();
  await page.session.send("Network.enable");
  page.session.on("Network.requestWillBeSent", ({ requestId, request }) => pendingRequests.set(requestId, new URL(request.url).pathname));
  page.session.on("Network.loadingFinished", ({ requestId }) => pendingRequests.delete(requestId));
  page.session.on("Network.loadingFailed", ({ requestId }) => pendingRequests.delete(requestId));
  try {
    await installCookie(page, await loginCookie());
    await page.session.send("Emulation.setDeviceMetricsOverride", { width: 1408, height: 960, deviceScaleFactor: 1, mobile: false });
    await page.session.send("Page.navigate", { url: `${baseUrl}${ws}/evolution` });
    const card = `[data-run-id="run-v2-completed"]`;
    await waitForUI(page.session, `document.querySelector('${card} .control-button')?.textContent.trim() === '暂停'`);
    await clickControl(page, `${card} .control-button`);
    await waitForUI(page.session, `document.querySelector('${card} .badge')?.textContent.trim() === '已暂停'`);
    assert.equal(await evaluate(page, `location.pathname`), `${ws}/evolution`, "the card action must not navigate");
    assert.equal(await evaluate(page, `!!document.querySelector('${card} .run-progress')`), true);
    assert.equal(await evaluate(page, `!!document.querySelector('${card} .pulse')`), false);
    await screenshot(page, "01-paused-card.png");
    await openRun(page, "run-v2-completed");
    await waitForUI(page.session, `document.querySelector('.control-button')?.textContent.trim() === '继续执行'`);
    await page.session.send("Page.reload");
    await waitForUI(page.session, `document.querySelector('.detail-head .badge')?.textContent.trim() === '已暂停'`);
    await screenshot(page, "02-paused-after-reload.png");
    await evaluate(page, `document.querySelector('.control-button').click()`);
    await waitForUI(page.session, `document.querySelector('.detail-head .badge')?.textContent.trim() === '正在执行'`);
    assert.equal(await evaluate(page, `location.pathname`), `${ws}/evolution/runs/run-v2-completed`);
    await screenshot(page, "03-continued-detail.png");
    await openLogs(page);
    await waitForUI(page.session, `document.body.textContent.includes('运行已暂停') && document.body.textContent.includes('运行已继续')`);
    await screenshot(page, "04-durable-control-log.png");
    assert.deepEqual(violations, []);
  } catch (error) {
    await screenshot(page, "failure.png");
    console.error(JSON.stringify({ url: await evaluate(page, "location.href"),
      body: await evaluate(page, "document.body.innerText.slice(0, 6000)"), pendingRequests: [...pendingRequests.values()], violations, apiLogs, webLogs }));
    throw error;
  } finally {
    await page.close();
  }
});
