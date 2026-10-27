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
  waitFor,
  waitForDocument,
} from "../support/runtime.mjs";

const root = process.cwd();
const apiDir = path.join(root, "apps/api");
const python = path.join(apiDir, ".venv", "bin", "python");
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const initialPassword = "m5-detail-initial-password";
const finalPassword = "m5-detail-final-password";
const secret = "m5-detail-signing-secret-with-sufficient-length";
let api;
let web;
let dataDir;
let screenshotDir;
let baseUrl;
let apiLogs = "";
let webLogs = "";

async function cleanup() {
  await stop(web);
  await stop(api);
  if (dataDir) await rm(dataDir, { recursive: true, force: true });
  if (screenshotDir && process.env.HE_KEEP_E2E_ARTIFACTS !== "1") {
    await rm(screenshotDir, { recursive: true, force: true });
  } else if (screenshotDir) {
    console.log(`m5 run detail screenshots: ${screenshotDir}`);
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
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
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
  await writeFile(path.join(screenshotDir, filename), data, "base64");
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m5-detail-e2e-"));
  screenshotDir = await mkdtemp(
    path.join(tmpdir(), "harness-m5-detail-screenshots-"),
  );
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
  await seedRuns();
});

after(cleanup);

test("m5 run detail exposes six steps, candidate state, blocked state and final verdict", async () => {
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

    await page.session.send("Page.navigate", {
      url: `${baseUrl}/evolution`,
    });
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-run-id='run-running'] .run-card-link"))`,
      "running run card",
    );
    await evaluate(
      page,
      `document.querySelector("[data-run-id='run-running'] .run-card-link").click()`,
    );
    const running = await waitForDocument(
      page.session,
      `(() => {
        if (location.pathname !== "/evolution/runs/run-running") return null;
        const page = document.querySelector("[data-testid='evolution-run-detail']");
        if (!page || !page.textContent.includes("evo/run-running/candidate/r1")) return null;
        return {
          steps: document.querySelectorAll("[data-step-key]").length,
          current: document.querySelector("[aria-current='step']")?.getAttribute("data-step-key"),
          finalDisabled: document.querySelector("[data-step-key='final']")?.disabled,
          text: page.textContent,
          overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        };
      })()`,
      "running run detail with candidate",
    );
    assert.equal(running.steps, 6);
    assert.equal(running.current, "iteration");
    assert.equal(running.finalDisabled, true);
    assert.match(running.text, /candidate 已 push/);
    assert.match(running.text, /评测中/);
    assert.match(running.text, /cluster 1/);
    assert.match(running.text, /最终用于进化的问题数\s*2/);
    assert.equal(running.overflow, 0);

    await evaluate(
      page,
      `document.querySelector("[data-step-key='clusters']").click()`,
    );
    await waitForDocument(
      page.session,
      `location.search === "?step=clusters" &&
        document.body.textContent.includes("M=2 类")`,
      "reached cluster step through query string",
    );
    await screenshot(page, "01-running-iteration-to-clusters.png");

    await installCookie(page, await currentLoginCookie());
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/evolution/runs/run-running?step=clusters&cluster=run-running-cluster-1`,
    });
    const clusterDeepLink = await waitForDocument(
      page.session,
      `(() => {
        if (!location.search.includes("cluster=run-running-cluster-1")) return null;
        const target = document.querySelector("#cluster-run-running-cluster-1");
        if (!target?.classList.contains("highlighted")) return null;
        return {
          href: location.href,
          highlighted: target.className,
          text: target.textContent,
          sourceRows: target.querySelectorAll("tbody tr").length,
        };
      })()`,
      "cluster deep link highlight",
    );
    assert.match(clusterDeepLink.href, /step=clusters/);
    assert.match(clusterDeepLink.highlighted, /highlighted/);
    assert.match(clusterDeepLink.text, /报告 ID/);
    assert.match(clusterDeepLink.text, /来源问题 ID/);
    assert.match(clusterDeepLink.text, /来源运行 1/);
    assert.match(clusterDeepLink.text, /glm-5\.3/);
    assert.equal(clusterDeepLink.sourceRows, 1);

    await installCookie(page, await currentLoginCookie());
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/evolution/runs/run-blocked`,
    });
    let blocked;
    try {
      blocked = await waitForDocument(
        page.session,
        `(() => {
          const text = document.body.textContent;
          if (!text.includes("run-blocked 自进化")) return null;
          const banner = document.querySelector("[data-testid='blocked-banner']");
          return {
            banner: banner?.textContent ?? "",
            current: document.querySelector("[aria-current='step']")?.getAttribute("data-step-key"),
            badge: document.querySelector("[data-round-id='round-blocked-1'] .badge")?.textContent ?? "",
            badgeClass: document.querySelector("[data-round-id='round-blocked-1'] .badge")?.className ?? "",
            body: text,
          };
        })()`,
        "blocked run detail",
      );
    } catch (error) {
      const debug = await evaluate(
        page,
        `({ url: location.href, body: document.body.textContent, html: document.body.innerHTML.slice(0, 3000) })`,
      );
      throw new Error(`${error.message}\n${JSON.stringify(debug)}`);
    }
    assert.match(blocked.banner, /eval/);
    assert.match(blocked.banner, /评测队列暂停/);
    assert.equal(blocked.current, "iteration");
    assert.equal(blocked.badge.trim(), "评测失败");
    assert.match(blocked.badgeClass, /\bblocked\b/);
    assert.match(blocked.body, /评测失败/);
    assert.match(blocked.body, /评测状态\s*failed/);
    await screenshot(page, "02-blocked.png");

    await installCookie(page, await currentLoginCookie());
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/evolution/runs/run-completed-effective`,
    });
    const completed = await waitForDocument(
      page.session,
      `(() => {
        const text = document.body.textContent;
        if (!text.includes("✓ 自进化有效") || !text.includes("任务完成率")) return null;
        return {
          current: document.querySelector("[aria-current='step']")?.getAttribute("data-step-key"),
          done: document.querySelectorAll("[data-step-key='done'], [data-step-key].done").length,
          text,
        };
      })()`,
      "completed run final verdict",
    );
    assert.equal(completed.current, "final");
    assert.match(completed.text, /ef56ab12cd34/);
    assert.match(completed.text, /来源 1 份报告/);
    assert.match(completed.text, /最终 push 成功/);
    await screenshot(page, "03-completed-final.png");

    await installCookie(page, await currentLoginCookie());
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/evolution/runs/run-blocked`,
    });
    const mobile = await waitForDocument(
      page.session,
      `(() => {
        const detail = document.querySelector("[data-testid='evolution-run-detail']");
        const stepper = document.querySelector(".stepper");
        if (!detail || !stepper) return null;
        const offenders = [...document.querySelectorAll("body *")]
          .map((element) => {
            const rect = element.getBoundingClientRect();
            const style = getComputedStyle(element);
            return {
              tag: element.tagName,
              className: String(element.className),
              right: Math.round(rect.right),
              width: Math.round(rect.width),
              scrollWidth: element.scrollWidth,
              overflowX: style.overflowX,
            };
          })
          .filter((item) =>
            item.right > document.documentElement.clientWidth &&
            !["auto", "scroll"].includes(item.overflowX)
          )
          .sort((a, b) => b.right - a.right)
          .slice(0, 8);
        return {
          page: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          stepperScrollable: stepper.scrollWidth > stepper.clientWidth,
          offenders,
        };
      })()`,
      "mobile run detail",
    );
    assert.equal(mobile.page, 0, JSON.stringify(mobile.offenders));
    assert.equal(mobile.stepperScrollable, true);
    await screenshot(page, "04-mobile-blocked.png");

    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
  } finally {
    await page.session.send("Emulation.clearDeviceMetricsOverride").catch(() => {});
    await page.close();
  }
});
