import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import {
  availablePort,
  browserViolations,
  capture,
  createBrowserPage,
  stop,
  waitFor,
  waitForDocument,
} from "../../../tests/support/runtime.mjs";

const root = process.cwd();
const reportDir = path.resolve("reports/2026-10-27/m5-04-run-list");
const screenshotDir = path.join(reportDir, "screenshots");
const runtimePath = path.join(tmpdir(), "harness-m5-04-smoke-runtime.json");
const apiDir = path.join(root, "apps/api");
const python = path.join(apiDir, ".venv", "bin", "python");
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const initialPassword = "m5-run-smoke-initial-password";
const finalPassword = "m5-run-smoke-final-password";
const secret = "m5-run-smoke-signing-secret-with-sufficient-length";
const results = [];
let api;
let web;
let dataDir;
let apiUrl;
let baseUrl;
let apiLogs = "";
let webLogs = "";

function record(id, name, detail, evidence) {
  results.push({ id, name, status: "pass", detail, evidence });
}

async function evaluate(page, expression) {
  const result = await page.session.send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
  return result.result.value;
}

async function screenshot(page, filename) {
  const { data } = await page.session.send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: false,
  });
  await writeFile(path.join(screenshotDir, filename), data, "base64");
}

async function installCookie(page, cookie) {
  await page.session.send("Network.enable");
  await page.session.send("Network.clearBrowserCookies");
  await page.session.send("Network.setCookie", {
    name: "refresh_token",
    value: cookie,
    url: `${baseUrl}/api/auth`,
    httpOnly: true,
    sameSite: "Strict",
  });
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
  return await currentCookie();
}

async function currentCookie() {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: finalPassword }),
  });
  assert.equal(response.status, 200);
  const cookie = response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie);
  return cookie;
}

async function seedRuns() {
  const child = spawn(
    python,
    [path.join(root, "tests/e2e/support/m5_run_list_fixture.py")],
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

async function startServices() {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m5-run-smoke-"));
  const env = {
    ...process.env,
    HE_ADMIN_PASSWORD: initialPassword,
    HE_ADMIN_USERNAME: "admin",
    HE_DATA_DIR: dataDir,
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: secret,
    HE_PHASE: "demo",
    PYTHONPATH: apiDir,
  };
  const seed = spawn(pnpm, ["fixtures:seed"], {
    cwd: root,
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let seedLogs = "";
  capture(seed, (chunk) => {
    seedLogs += chunk;
  });
  const seedExit = await new Promise((resolve) => seed.once("exit", resolve));
  assert.equal(seedExit, 0, seedLogs);

  const apiPort = await availablePort();
  const webPort = await availablePort();
  apiUrl = `http://127.0.0.1:${apiPort}`;
  baseUrl = `http://127.0.0.1:${webPort}`;
  api = spawn(process.execPath, ["scripts/run-api.mjs", "start"], {
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
}

async function collectCdpEvidence() {
  const cookie = await loginCookie();
  const page = await createBrowserPage();
  const violations = browserViolations(page.session);
  try {
    await installCookie(page, cookie);
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 960,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.session.send("Page.navigate", { url: `${baseUrl}/evolution` });
    await waitForDocument(
      page.session,
      `document.querySelector(".run-group-running .waiting") &&
        document.querySelector(".run-group-history .waiting")`,
      "empty run groups",
    );
    await screenshot(page, "01-empty-1408.png");
    record(
      "01",
      "空列表",
      "真实空库显示 running/history 两个明确空态，不出现空白页。",
      ["screenshots/01-empty-1408.png"],
    );

    await seedRuns();
    await installCookie(page, await currentCookie());
    await page.session.send("Page.navigate", { url: `${baseUrl}/evolution` });
    const populated = await waitForDocument(
      page.session,
      `(() => {
        const running = [...document.querySelectorAll(
          ".run-group-running [data-run-id]",
        )].map((node) => node.getAttribute("data-run-id"));
        const history = [...document.querySelectorAll(
          ".run-group-history [data-run-id]",
        )].map((node) => node.getAttribute("data-run-id"));
        if (running.length !== 3 || history.length !== 5) return null;
        return {
          running,
          history,
          labels: Object.fromEntries(
            [...document.querySelectorAll("[data-run-id]")].map((node) => [
              node.getAttribute("data-run-id"),
              node.querySelector(".badge")?.textContent.replace(/\s+/g, " ").trim(),
            ]),
          ),
          width: document.querySelector("[data-testid='evolution-run-list']")
            ?.getBoundingClientRect().width,
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
          kindColor: getComputedStyle(
            document.querySelector(".chip.kind"),
          ).color,
          modelColor: getComputedStyle(
            document.querySelector(".chip.model"),
          ).color,
          progressNow: document.querySelector(
            "[data-run-id='run-running'] [role='progressbar']",
          )?.getAttribute("aria-valuenow"),
          progressWidth: document.querySelector(
            "[data-run-id='run-running'] .fill",
          )?.style.width,
          hasVisibleErrorRow: Boolean(document.querySelector(".run-error")),
        };
      })()`,
      "populated run list",
    );
    assert.deepEqual(populated.running, [
      "run-running",
      "run-blocked",
      "run-preparing",
    ]);
    assert.deepEqual(populated.history, [
      "run-completed-effective",
      "run-failed",
      "run-interrupted",
      "run-completed-no-benefit",
      "run-completed-unknown",
    ]);
    assert.deepEqual(populated.labels, {
      "run-running": "正在执行",
      "run-blocked": "已阻塞",
      "run-preparing": "准备中",
      "run-completed-effective": "✓ 已完成 · 自进化有效",
      "run-failed": "失败",
      "run-interrupted": "已中断",
      "run-completed-no-benefit": "已完成 · 无收益",
      "run-completed-unknown": "已完成 · 终评未知",
    });
    assert.equal(populated.width, 1080);
    assert.equal(populated.scrollWidth, populated.clientWidth);
    assert.equal(populated.kindColor, "rgb(138, 85, 201)");
    assert.equal(populated.modelColor, "rgb(21, 138, 138)");
    assert.equal(populated.progressNow, "57");
    assert.equal(populated.progressWidth, "57%");
    assert.equal(populated.hasVisibleErrorRow, false);
    await screenshot(page, "02-desktop-1408.png");
    record(
      "02",
      "桌面运行列表",
      "running 3 张、history 5 张保持后端顺序，八种状态文案、紫色 target chip、青色 model chip、57% 进度与原型一致。",
      ["screenshots/02-desktop-1408.png"],
    );

    await evaluate(
      page,
      `document.querySelector("[data-run-id='run-failed'] .badge").click()`,
    );
    const tooltip = await waitForDocument(
      page.session,
      `(() => {
        const row = document.querySelector("[data-run-id='run-failed']");
        const trigger = row.querySelector(".badge");
        const tip = row.querySelector(".badge-tooltip");
        if (!trigger || !tip || !tip.classList.contains("is-open")) return null;
        return {
          tag: trigger.tagName,
          describedBy: trigger.getAttribute("aria-describedby"),
          text: tip.textContent.trim(),
          hasStageCode: /(^|\\s)(eval|push) ·/.test(document.body.textContent ?? ""),
        };
      })()`,
      "focused error tooltip",
    );
    assert.deepEqual(tooltip, {
      tag: "BUTTON",
      describedBy: "run-error-run-failed",
      text: "评测执行失败：sandbox timeout",
      hasStageCode: false,
    });
    await screenshot(page, "03-error-tooltip-1408.png");
    record(
      "03",
      "错误摘要",
      "失败 badge 可键盘聚焦，tooltip 显示脱敏原因；内部 eval/push 阶段码和常驻错误行均不出现。",
      ["screenshots/03-error-tooltip-1408.png"],
    );

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    const mobile = await waitForDocument(
      page.session,
      `(() => {
        const page = document.querySelector("[data-testid='evolution-run-list']");
        if (!page) return null;
        return {
          width: page.getBoundingClientRect().width,
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
          cards: page.querySelectorAll("[data-run-id]").length,
        };
      })()`,
      "mobile run list",
    );
    assert.equal(mobile.width, 390);
    assert.equal(mobile.scrollWidth, mobile.clientWidth);
    assert.equal(mobile.cards, 8);
    await screenshot(page, "04-mobile-390.png");
    record(
      "04",
      "390px 响应式",
      "八张运行卡在 390px 下自动换行，页面无横向溢出。",
      ["screenshots/04-mobile-390.png"],
    );

    await evaluate(
      page,
      `(() => {
        const badge = document.querySelector("[data-run-id='run-failed'] .badge");
        badge.scrollIntoView({ block: "center" });
        badge.click();
      })()`,
    );
    await waitForDocument(
      page.session,
      `document.querySelector(
        "[data-run-id='run-failed'] .badge-tooltip",
      )?.classList.contains("is-open")`,
      "mobile tooltip",
    );
    const mobileTooltip = await evaluate(
      page,
      `(() => {
        const tip = document.querySelector(
          "[data-run-id='run-failed'] .badge-tooltip",
        );
        const rect = tip.getBoundingClientRect();
        return {
          left: rect.left,
          right: rect.right,
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        };
      })()`,
    );
    assert.ok(mobileTooltip.left >= 0, JSON.stringify(mobileTooltip));
    assert.ok(mobileTooltip.right <= mobileTooltip.clientWidth);
    assert.equal(mobileTooltip.scrollWidth, mobileTooltip.clientWidth);
    await screenshot(page, "05-mobile-tooltip-390.png");
    record(
      "05",
      "触屏错误摘要",
      "点击失败 badge 后 tooltip 在 390px viewport 内完整显示，页面仍无横向溢出。",
      ["screenshots/05-mobile-tooltip-390.png"],
    );

    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
    record(
      "06",
      "Console / network",
      "浏览器会话未捕获 warning、error 或未处理异常。",
      ["cdp-evidence.json"],
    );
  } finally {
    await page.session.send("Emulation.clearDeviceMetricsOverride").catch(() => {});
    await page.close();
  }
  await writeFile(
    path.join(reportDir, "cdp-evidence.json"),
    JSON.stringify({ results, violations, baseUrl, apiUrl }, null, 2),
  );
  await writeFile(
    runtimePath,
    JSON.stringify(
      {
        baseUrl,
        apiUrl,
        adminUsername: "admin",
        adminPassword: finalPassword,
      },
      null,
      2,
    ),
  );
}

async function cleanup() {
  await stop(web);
  await stop(api);
  if (dataDir) {
    await rm(dataDir, { recursive: true, force: true, maxRetries: 10 });
  }
}

await mkdir(screenshotDir, { recursive: true });
try {
  await startServices();
  await collectCdpEvidence();
  process.stdout.write(`SMOKE_READY ${baseUrl}\n`);
  await new Promise((resolve) => {
    process.once("SIGINT", resolve);
    process.once("SIGTERM", resolve);
  });
} finally {
  await cleanup();
}
