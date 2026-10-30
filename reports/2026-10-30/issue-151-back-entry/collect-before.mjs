// issue #151 BEFORE evidence collector —「进化对象配置页缺返回自进化入口」.
// 与 tests/e2e/m5-target-config.test.mjs 同一套真实前后端启动方式：
// SQLite + 演示 fixture + 真实 vite dev server，登录 admin 后截 /evolution/targets。
// 只做只读截图，不改仓库文件；临时数据目录在退出时清理。

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  availablePort,
  browserViolations,
  capture,
  createBrowserPage,
  stop,
  waitFor,
  waitForDocument,
} from "../../../tests/support/runtime.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const outputDir = path.resolve(here, "screenshots");
const root = path.resolve(here, "../../..");
const apiDir = path.join(root, "apps/api");
const python = path.join(apiDir, ".venv", "win32" === process.platform ? "Scripts" : "bin", "win32" === process.platform ? "python.exe" : "python");
const pnpm = "win32" === process.platform ? "pnpm.cmd" : "pnpm";
const adminPassword = "issue151-admin-password";

let api;
let web;
let dataDir;

async function evaluate(page, expression) {
  const result = await page.session.send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.text);
  }
  return result.result.value;
}

async function screenshot(page, file) {
  const result = await page.session.send("Page.captureScreenshot", {
    format: "jpeg",
    quality: 80,
  });
  await writeFile(path.join(outputDir, file), Buffer.from(result.data, "base64"));
}

try {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-issue151-"));
  const env = {
    ...process.env,
    HE_ADMIN_PASSWORD: adminPassword,
    HE_ADMIN_USERNAME: "admin",
    HE_DATA_DIR: dataDir,
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: "issue151-secret",
    HE_PHASE: "demo",
    PYTHONPATH: apiDir,
  };
  const seed = spawn(pnpm, ["fixtures:seed"], { cwd: root, env, shell: process.platform === "win32", stdio: ["ignore", "pipe", "pipe"] });
  let seedLogs = "";
  capture(seed, (chunk) => { seedLogs += chunk; });
  assert.equal(await new Promise((resolve) => seed.once("exit", resolve)), 0, seedLogs);

  const apiPort = await availablePort();
  const webPort = await availablePort();
  const apiUrl = `http://127.0.0.1:${apiPort}`;
  const baseUrl = `http://127.0.0.1:${webPort}`;

  api = spawn(python, [path.join(root, "tests/e2e/support/m5_target_server.py")], {
    cwd: root,
    env: { ...env, HE_DOCS_ENABLED: "false", HE_HOST: "127.0.0.1", HE_PORT: String(apiPort), HE_SYNC_INTERVAL_SECONDS: "0", PYTHONUNBUFFERED: "1" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let apiLogs = "";
  capture(api, (chunk) => { apiLogs += chunk; });
  await waitFor(`${apiUrl}/api/health`, api, () => apiLogs);

  web = spawn(pnpm, ["--filter", "@harness/web", "exec", "vite", "--force", "--host", "127.0.0.1", "--port", String(webPort), "--strictPort"], {
    cwd: root,
    env: { ...process.env, HE_API_PROXY_URL: apiUrl },
    shell: process.platform === "win32",
    stdio: ["ignore", "pipe", "pipe"],
  });
  let webLogs = "";
  capture(web, (chunk) => { webLogs += chunk; });
  await waitFor(baseUrl, web, () => webLogs);

  const login = await fetch(`${apiUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: adminPassword }),
  });
  assert.equal(login.status, 200);
  const loginBody = await login.json();
  const initialCookie = login.headers.get("set-cookie")?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(initialCookie, "no refresh_token cookie on login");
  const changed = await fetch(`${apiUrl}/api/auth/change-password`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${loginBody.accessToken}` },
    body: JSON.stringify({ oldPassword: adminPassword, newPassword: "issue151-admin-final" }),
  });
  assert.equal(changed.status, 204, `change-password: ${changed.status}`);
  const refreshed = await fetch(`${apiUrl}/api/auth/refresh`, { method: "POST", headers: { cookie: `refresh_token=${initialCookie}` } });
  assert.equal(refreshed.status, 200, await refreshed.text());
  const cookie = refreshed.headers.get("set-cookie")?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie, "no refresh_token cookie after refresh");

  const page = await createBrowserPage();
  const violations = browserViolations(page.session);
  try {
    page.session.send("Network.enable");
    page.session.send("Network.setCookie", {
      name: "refresh_token",
      value: cookie,
      url: `${baseUrl}/api/auth`,
      httpOnly: true,
      sameSite: "Strict",
    });
    await page.session.send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
    await page.session.send("Page.navigate", { url: `${baseUrl}/` });
    await new Promise((resolve) => setTimeout(resolve, 6000));
    await page.session.send("Page.navigate", { url: `${baseUrl}/evolution/targets` });
    let mounted = false;
    for (let i = 0; i < 60 && !mounted; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      mounted = await evaluate(page, `document.querySelector("h1")?.textContent === "进化对象配置"`).catch(() => false);
      if (i === 19) {
        const diag = await evaluate(page, `(() => ({
          href: location.href,
          h1: document.querySelector("h1")?.textContent ?? null,
          body: document.body?.textContent?.trim().slice(0, 300) ?? "",
          readyState: document.readyState,
        }))()`).catch((e) => ({ diagError: String(e) }));
        console.error("DIAG@20s", JSON.stringify(diag), "violations:", violations);
      }
    }
    assert.equal(mounted, true, "target config page never rendered");
    await new Promise((resolve) => setTimeout(resolve, 800));
    const state = await evaluate(page, `(() => ({
      url: location.pathname,
      backLinkCount: [...document.querySelectorAll("a")].filter((a) => a.textContent.includes("返回自进化")).length,
      headerHtml: document.querySelector(".page-intro")?.outerHTML?.slice(0, 400) ?? "",
    }))()`);
    console.log(JSON.stringify(state, null, 2));
    await screenshot(page, process.argv[2] ?? "02-real-targets-before.jpg");
    console.log("violations:", violations.length);
  } finally {
    await page.close();
  }
  console.log("done");
} finally {
  if (web) await stop(web);
  if (api) await stop(api);
  if (dataDir) await rm(dataDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
}
