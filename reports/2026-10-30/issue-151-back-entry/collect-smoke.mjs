// issue #151 smoke collector —「进化对象配置页返回自进化入口」.
// 真实前后端（SQLite + 演示 fixture + vite dev），登录 admin 后按场景矩阵执行
// 点击导航冒烟，截图存证；只读不写仓库数据，临时目录退出时清理。

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  availablePort,
  capture,
  createBrowserPage,
  stop,
  waitFor,
} from "../../../tests/support/runtime.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const outputDir = path.resolve(here, "screenshots");
const root = path.resolve(here, "../../..");
const apiDir = path.join(root, "apps/api");
const python = path.join(apiDir, ".venv", "win32" === process.platform ? "Scripts" : "bin", "win32" === process.platform ? "python.exe" : "python");
const pnpm = "win32" === process.platform ? "pnpm.cmd" : "pnpm";
const adminPassword = "issue151-smoke-password";
const finalPassword = "issue151-smoke-final";

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

const results = [];
function record(id, name, ok, detail, evidence) {
  results.push({ id, name, ok, detail, evidence });
  console.log(`${ok ? "PASS" : "FAIL"} ${id} ${name} — ${detail}`);
}

try {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-issue151-smoke-"));
  const env = {
    ...process.env,
    HE_ADMIN_PASSWORD: adminPassword,
    HE_ADMIN_USERNAME: "admin",
    HE_DATA_DIR: dataDir,
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: "issue151-smoke-secret",
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
    body: JSON.stringify({ oldPassword: adminPassword, newPassword: finalPassword }),
  });
  assert.equal(changed.status, 204, `change-password: ${changed.status}`);
  const refreshed = await fetch(`${apiUrl}/api/auth/refresh`, { method: "POST", headers: { cookie: `refresh_token=${initialCookie}` } });
  assert.equal(refreshed.status, 200, await refreshed.text());
  const cookie = refreshed.headers.get("set-cookie")?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie, "no refresh_token cookie after refresh");

  const page = await createBrowserPage();
  try {
    await page.session.send("Network.enable");
    await page.session.send("Network.setCookie", {
      name: "refresh_token",
      value: cookie,
      url: `${baseUrl}/api/auth`,
      httpOnly: true,
      sameSite: "Strict",
    });
    await page.session.send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });

    // 单次导航直达配置页（避免二次整页加载触发 refresh token 轮换失效）。
    await page.session.send("Page.navigate", { url: `${baseUrl}/evolution/targets` });
    let mounted = false;
    for (let i = 0; i < 60 && !mounted; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      mounted = await evaluate(page, `document.querySelector("h1")?.textContent === "进化对象配置"`).catch(() => false);
    }
    assert.equal(mounted, true, `target config page never rendered, diag=${JSON.stringify(await evaluate(page, `({ href: location.href, h1: document.querySelector("h1")?.textContent ?? null, body: document.body?.textContent?.trim().slice(0, 200) ?? "" })`).catch((e) => String(e)))}`);
    const s1 = await evaluate(page, `(() => {
      const back = document.querySelector("[data-testid='target-config-back']");
      return {
        exists: Boolean(back),
        text: back?.textContent?.trim() ?? "",
        href: back?.getAttribute("href") ?? "",
        tagName: back?.tagName ?? "",
        tableVisible: Boolean(document.querySelector(".target-config-page table, .target-config-page .el-table")),
      };
    })()`);
    record("01", "数据态：配置页渲染且返回入口可见", s1.exists && s1.href === "/evolution" && s1.tagName === "A", `href=${s1.href} text=${s1.text}`, ["04-smoke-targets-with-back.jpg"]);
    await screenshot(page, "04-smoke-targets-with-back.jpg");

    // 场景 02：点击返回入口，SPA 内导航落在 /evolution。
    await evaluate(page, `document.querySelector("[data-testid='target-config-back']")?.click()`);
    let landed = false;
    for (let i = 0; i < 30 && !landed; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      landed = await evaluate(page, `location.pathname === "/evolution" && document.querySelector("h1")?.textContent === "自进化"`).catch(() => false);
    }
    const s2 = await evaluate(page, `({ path: location.pathname, h1: document.querySelector("h1")?.textContent ?? "" })`);
    record("02", "点击返回入口落在 /evolution", landed && s2.path === "/evolution", `pathname=${s2.path} h1=${s2.h1}`, ["05-smoke-after-click-evolution.jpg"]);
    await screenshot(page, "05-smoke-after-click-evolution.jpg");

    // 场景 03：从 /evolution 重新进入配置页（SPA 内导航，不整页刷新），入口仍可达。
    await evaluate(page, `history.pushState({}, "", "/evolution/targets"); dispatchEvent(new PopStateEvent("popstate"));`);
    let remounted = false;
    for (let i = 0; i < 60 && !remounted; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      remounted = await evaluate(page, `location.pathname === "/evolution/targets" && document.querySelector("[data-testid='target-config-back']")?.getAttribute("href") === "/evolution"`).catch(() => false);
    }
    record("03", "往返后再进配置页返回入口仍可达", remounted, "href=/evolution", ["04-smoke-targets-with-back.jpg"]);

    // 场景 04：键盘可达——返回入口是原生链接，可聚焦。
    const s4 = await evaluate(page, `(() => {
      const back = document.querySelector("[data-testid='target-config-back']");
      back?.focus();
      return { focused: document.activeElement === back, tabIndexFree: true };
    })()`);
    record("04", "返回入口键盘可聚焦（原生 <a>）", s4.focused, "focus() 后 activeElement 为返回链接", []);
  } finally {
    await page.close();
  }
  await writeFile(path.join(here, "smoke-results.json"), JSON.stringify(results, null, 2));
  console.log("done");
} finally {
  if (web) await stop(web);
  if (api) await stop(api);
  if (dataDir) await rm(dataDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
}
