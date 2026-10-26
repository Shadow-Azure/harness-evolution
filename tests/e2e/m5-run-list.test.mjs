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
const apiDir = path.join(root, "apps/api");
const python = path.join(apiDir, ".venv", "bin", "python");
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const initialPassword = "m5-run-list-initial-password";
const finalPassword = "m5-run-list-final-password";
const secret = "m5-run-list-signing-secret-with-sufficient-length";
let api;
let web;
let dataDir;
let baseUrl;
let apiLogs = "";
let webLogs = "";

async function cleanup() {
  await stop(web);
  await stop(api);
  if (dataDir) await rm(dataDir, { recursive: true, force: true });
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
  const cookie = refreshed.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie);
  return cookie;
}

async function currentLoginCookie() {
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

async function installCookie(page, cookie) {
  await page.session.send("Network.enable");
  await page.session.send("Network.setCookie", {
    name: "refresh_token",
    value: cookie,
    url: `${baseUrl}/api/auth`,
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
    throw new Error(result.exceptionDetails.text);
  }
  return result.result.value;
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

async function screenshot(page, filename) {
  const { data } = await page.session.send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: false,
  });
  await (await import("node:fs/promises")).writeFile(
    path.join(
      root,
      "reports/2026-10-27/m5-04-run-list/screenshots",
      filename,
    ),
    data,
    "base64",
  );
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m5-run-list-e2e-"));
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
  const setup = spawn(pnpm, ["fixtures:seed"], {
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
});

after(cleanup);

test("m5 run list consumes backend groups and matches the prototype", async () => {
  await (await import("node:fs/promises")).mkdir(
    path.join(root, "reports/2026-10-27/m5-04-run-list/screenshots"),
    { recursive: true },
  );
  const page = await createBrowserPage();
  const violations = browserViolations(page.session);
  try {
    await installCookie(page, await loginCookie());
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 960,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.session.send("Page.navigate", { url: `${baseUrl}/evolution` });
    await waitForDocument(
      page.session,
      `document.body.textContent.includes("当前没有正在执行的自进化") &&
        document.body.textContent.includes("暂无历史记录")`,
      "empty run groups",
    );

    await seedRuns();
    await installCookie(page, await currentLoginCookie());
    await page.session.send("Page.navigate", { url: `${baseUrl}/evolution` });
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-testid='evolution-run-list']"))`,
      "reloaded run list page",
    );
    await new Promise((resolve) => setTimeout(resolve, 500));
    const desktop = await evaluate(
      page,
      `(() => {
        const page = document.querySelector("[data-testid='evolution-run-list']");
        const running = [...document.querySelectorAll(".run-group-running [data-run-id]")];
        const history = [...document.querySelectorAll(".run-group-history [data-run-id]")];
        if (!page) return null;
        const rect = page.getBoundingClientRect();
        const firstCard = running[0];
        const cardStyle = firstCard ? getComputedStyle(firstCard) : null;
        const kind = firstCard
          ? getComputedStyle(firstCard.querySelector(".chip.kind"))
          : null;
        const model = firstCard
          ? getComputedStyle(firstCard.querySelector(".chip.model"))
          : null;
        const badge = firstCard
          ? getComputedStyle(firstCard.querySelector(".badge"))
          : null;
        const progress = firstCard?.querySelector("[role='progressbar']");
        return {
          body: page.textContent.slice(0, 1600),
          width: rect.width,
          pageScrollWidth: document.documentElement.scrollWidth,
          pageClientWidth: document.documentElement.clientWidth,
          runningIds: running.map((item) => item.getAttribute("data-run-id")),
          historyIds: history.map((item) => item.getAttribute("data-run-id")),
          heading: page.querySelector("h1")?.textContent.trim(),
          launchDisabled: page.querySelector(".launch-run")?.disabled,
          hasCanvas: Boolean(page.querySelector(".canvas")),
          cardPadding: cardStyle?.padding,
          cardRadius: cardStyle?.borderRadius,
          kindColor: kind?.color,
          modelColor: model?.color,
          runningBadgeBackground: badge?.backgroundColor,
          progressNow: progress?.getAttribute("aria-valuenow"),
          progressWidth: progress?.querySelector(".fill")?.style.width,
          firstMeta: firstCard?.querySelector(".time")?.textContent.trim(),
          errorTitle: history
            .find((item) => item.getAttribute("data-run-id") === "run-failed")
            ?.querySelector(".run-error")?.getAttribute("title"),
          failedErrorColor: getComputedStyle(
            history
              .find((item) => item.getAttribute("data-run-id") === "run-failed")
              ?.querySelector(".run-error"),
          ).color,
          interruptedErrorColor: getComputedStyle(
            history
              .find((item) => item.getAttribute("data-run-id") === "run-interrupted")
              ?.querySelector(".run-error"),
          ).color,
        };
      })()`,
    );

    assert.equal(desktop.heading, "自进化");
    assert.equal(desktop.width, 1080);
    assert.equal(desktop.pageScrollWidth, desktop.pageClientWidth);
    assert.deepEqual(desktop.runningIds, [
      "run-running",
      "run-blocked",
      "run-preparing",
    ]);
    assert.deepEqual(desktop.historyIds, [
      "run-completed-effective",
      "run-failed",
      "run-interrupted",
      "run-completed-no-benefit",
    ]);
    assert.equal(desktop.launchDisabled, true);
    assert.equal(desktop.hasCanvas, false);
    assert.equal(desktop.cardPadding, "14px 16px");
    assert.equal(desktop.cardRadius, "12px");
    assert.equal(desktop.kindColor, "rgb(138, 85, 201)");
    assert.equal(desktop.modelColor, "rgb(21, 138, 138)");
    assert.notEqual(desktop.runningBadgeBackground, "rgba(0, 0, 0, 0)");
    assert.equal(desktop.progressNow, "57");
    assert.equal(desktop.progressWidth, "57%");
    assert.match(desktop.firstMeta, /^Administrator · /);
    assert.equal(desktop.errorTitle, "评测执行失败：sandbox timeout");
    assert.equal(desktop.failedErrorColor, "rgb(214, 60, 60)");
    assert.equal(desktop.interruptedErrorColor, "rgb(217, 123, 28)");
    await screenshot(page, "01-desktop-1408.png");

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
        const rect = page.getBoundingClientRect();
        return {
          width: rect.width,
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
          cards: document.querySelectorAll(".run-card").length,
        };
      })()`,
      "mobile run list",
    );
    assert.equal(mobile.width, 390);
    assert.equal(mobile.scrollWidth, mobile.clientWidth);
    assert.equal(mobile.cards, 7);
    await screenshot(page, "02-mobile-390.png");
    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
  } finally {
    await page.session.send("Emulation.clearDeviceMetricsOverride").catch(() => {});
    await page.close();
  }
});
