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
const python = path.join(
  apiDir,
  ".venv",
  process.platform === "win32" ? "Scripts" : "bin",
  process.platform === "win32" ? "python.exe" : "python",
);
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const initialPassword = "m10-detail-initial-password";
const finalPassword = "m10-detail-final-password";
const secret = "m10-detail-signing-secret-with-sufficient-length";
const ws = "/workspaces/ws-default";
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
    console.log(`m10-06 run detail screenshots: ${screenshotDir}`);
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

async function currentLoginCookie() {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: finalPassword }),
  });
  if (response.status === 401) return loginCookie();
  assert.equal(response.status, 200);
  return response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
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
    throw new Error(
      result.exceptionDetails.exception?.description ?? result.exceptionDetails.text,
    );
  }
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

async function screenshotStep(page, filename) {
  await evaluate(
    page,
    `[...document.querySelectorAll(".run-detail-page .card.panel")].at(-1)
      ?.scrollIntoView({ block: "start" })`,
  );
  await screenshot(page, filename);
}

async function seedRunDetail() {
  const child = spawn(
    python,
    [path.join(root, "tests/e2e/support/m10_06_run_detail_fixture.py")],
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

async function openRun(page, runId, query = "") {
  await page.session.send("Page.navigate", {
    url: `${baseUrl}${ws}/evolution/runs/${runId}${query}`,
  });
}

async function clickStep(page, key) {
  await evaluate(
    page,
    `document.querySelector("[data-step-key='${key}']").click()`,
  );
}

async function openLogs(page) {
  await evaluate(
    page,
    `document.querySelector("[data-testid='logs-tab']").click()`,
  );
}

async function clickButton(page, text) {
  await evaluate(
    page,
    `(() => {
      const button = [...document.querySelectorAll("button")]
        .find((item) => item.textContent.trim() === ${JSON.stringify(text)});
      if (!button) throw new Error("missing button: " + ${JSON.stringify(text)});
      button.click();
    })()`,
  );
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m10-06-e2e-"));
  screenshotDir = await mkdtemp(
    path.join(tmpdir(), "harness-m10-06-screenshots-"),
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
  await seedRunDetail();

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

test("m10-06 run detail pages sessions and potential, explains attribution sources, and expands the highest-severity cluster", async () => {
  const page = await createBrowserPage();
  const violations = browserViolations(page.session);
  try {
    const cookie = await loginCookie();
    await installCookie(page, cookie);
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 960,
      deviceScaleFactor: 1,
      mobile: false,
    });

    await openRun(page, "run-v2-completed");
    await waitForDocument(
      page.session,
      `document.querySelectorAll("[data-step-key]").length === 7`,
      "seven-step run detail",
    );
    await clickStep(page, "sessions");
    const sessions = await waitForDocument(
      page.session,
      `(() => {
        const rows = [...document.querySelectorAll(".rep tbody tr")];
        if (rows.length !== 4) return null;
        return {
          rows: rows.length,
          pager: document.querySelector(".pager-info")?.textContent ?? "",
          text: rows.map((row) => row.textContent),
        };
      })()`,
      "first Session page",
    );
    assert.equal(sessions.rows, 4);
    assert.match(sessions.pager, /第\s*1\s*\/\s*2\s*页/);
    assert.match(sessions.text.join(" "), /来源运行 A/);
    await clickButton(page, "下一页 →");
    const sessionPageTwo = await waitForDocument(
      page.session,
      `(() => {
        const rows = [...document.querySelectorAll(".rep tbody tr")];
        if (rows.length !== 1) return null;
        return rows[0].textContent;
      })()`,
      "second Session page",
    );
    assert.match(sessionPageTwo, /来源运行 E/);
    await screenshotStep(page, "01-after-sessions.png");

    await clickStep(page, "potential");
    let potential;
    try {
      potential = await waitForDocument(
        page.session,
        `(() => {
          const rows = [...document.querySelectorAll(".rep tbody tr")];
          if (rows.length !== 5) return null;
          return {
            rows: rows.length,
            pager: document.querySelector(".pager-info")?.textContent ?? "",
            text: rows.map((row) => row.textContent).join(" "),
          };
        })()`,
        "first potential page",
      );
    } catch (error) {
      const debug = await evaluate(
        page,
        `({
          url: location.href,
          body: document.body.textContent,
          tables: [...document.querySelectorAll("table")].map((table) => table.outerHTML.slice(0, 1200)),
        })`,
      );
      throw new Error(`${error.message}\n${JSON.stringify(debug)}`);
    }
    assert.equal(potential.rows, 5);
    assert.match(potential.pager, /第\s*1\s*\/\s*2\s*页/);
    assert.match(potential.text, /顺序未知/);
    await clickButton(page, "下一页 →");
    const potentialPageTwo = await waitForDocument(
      page.session,
      `(() => {
        const rows = [...document.querySelectorAll(".rep tbody tr")];
        if (rows.length !== 1) return null;
        return {
          text: rows[0].textContent,
          title: rows[0].querySelector(".id a")?.getAttribute("title") ?? "",
        };
      })()`,
      "second potential page",
    );
    assert.equal(potentialPageTwo.title, "v2-case-6");
    await screenshotStep(page, "02-after-potential.png");

    await clickStep(page, "attribution");
    const attribution = await waitForDocument(
      page.session,
      `(() => {
        const text = document.body.textContent;
        if (!text.includes("第 4 步 · 对象归因")) return null;
        const rows = document.querySelectorAll(".rep tbody tr");
        if (rows.length !== 6) return null;
        return {
          text,
          rows: rows.length,
          cached: [...document.querySelectorAll(".source-chip.cached")].length,
          fresh: [...document.querySelectorAll(".source-chip.fresh")].length,
        };
      })()`,
      "attribution step",
    );
    assert.equal(attribution.rows, 6);
    assert.equal(attribution.cached, 2);
    assert.equal(attribution.fresh, 4);
    assert.match(attribution.text, /非该对象问题/);
    assert.match(attribution.text, /6\s*潜在 bad case/);
    assert.match(attribution.text, /2\s*复用缓存/);
    await screenshotStep(page, "03-after-attribution.png");

    await clickStep(page, "clusters");
    const clusters = await waitForDocument(
      page.session,
      `(() => {
        const cards = [...document.querySelectorAll(".cluster")];
        if (cards.length !== 2) return null;
        return {
          firstId: cards[0].id,
          firstOpen: cards[0].classList.contains("open"),
          firstText: cards[0].textContent,
          secondId: cards[1].id,
          secondOpen: cards[1].classList.contains("open"),
          body: document.body.textContent,
        };
      })()`,
      "cluster step",
    );
    assert.equal(clusters.firstId, "cluster-v2-cluster-1");
    assert.equal(clusters.firstOpen, true);
    assert.equal(clusters.secondId, "cluster-v2-cluster-2");
    assert.equal(clusters.secondOpen, false);
    assert.match(clusters.firstText, /严重程度 9\.1/);
    assert.doesNotMatch(clusters.body, /另一个对象的问题/);
    await screenshotStep(page, "04-after-clusters.png");

    await installCookie(page, await currentLoginCookie());
    await openRun(page, "run-v2-legacy");
    const legacy = await waitForDocument(
      page.session,
      `(() => {
        const page = document.querySelector("[data-testid='evolution-run-detail']");
        if (!page) return null;
        const steps = [...document.querySelectorAll("[data-step-key]")];
        if (steps.length !== 7) return null;
        return {
          current: document.querySelector("[aria-current='step']")?.getAttribute("data-step-key"),
          text: page.textContent,
        };
      })()`,
      "legacy seven-step run",
    );
    assert.equal(legacy.current, "final");
    assert.match(legacy.text, /第 7 步 · 测试集终评/);
    assert.match(legacy.text, /自进化有效|未产生收益/);

    await installCookie(page, await currentLoginCookie());
    await openRun(page, "run-v2-completed", "?tab=logs");
    const logs = await waitForDocument(
      page.session,
      `(() => {
        const rows = [...document.querySelectorAll("[data-event-seq]")];
        if (rows.length !== 6) return null;
        return {
          rows: rows.length,
          hasStepJump: Boolean(rows[1]?.querySelector(".jump:not(.cluster)")),
          hasClusterJump: Boolean(rows[4]?.querySelector(".jump.cluster")),
        };
      })()`,
      "execution log",
    );
    assert.equal(logs.rows, 6);
    assert.equal(logs.hasStepJump, true);
    assert.equal(logs.hasClusterJump, true);
    await screenshot(page, "05-after-logs.png");

    await evaluate(
      page,
      `document.querySelector("[data-event-seq='3'] .jump:not(.cluster)").click()`,
    );
    const stepJump = await waitForDocument(
      page.session,
      `(() => {
        if (!location.search.includes("step=potential")) return null;
        return document.body.textContent.includes("第 3 步 · 潜在 bad case");
      })()`,
      "event to step jump",
    );
    assert.equal(stepJump, true);

    await openLogs(page);
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-event-seq='5'] .jump.cluster"))`,
      "cluster jump target",
    );
    await evaluate(
      page,
      `document.querySelector("[data-event-seq='5'] .jump.cluster").click()`,
    );
    const clusterJump = await waitForDocument(
      page.session,
      `(() => {
        if (!location.search.includes("step=clusters") ||
            !location.search.includes("cluster=v2-cluster-1")) return null;
        const target = document.querySelector("#cluster-v2-cluster-1");
        return target?.classList.contains("highlighted") ?? false;
      })()`,
      "event to cluster jump",
    );
    assert.equal(clusterJump, true);

    await openLogs(page);
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-event-seq='4'] details.error-detail"))`,
      "error detail",
    );
    await evaluate(
      page,
      `document.querySelector("[data-event-seq='4'] details.error-detail summary").click()`,
    );
    const errorDetail = await waitForDocument(
      page.session,
      `(() => {
        const detail = document.querySelector("[data-event-seq='4'] details.error-detail");
        if (!detail?.open) return null;
        return detail.textContent;
      })()`,
      "expanded error detail",
    );
    assert.match(errorDetail, /部分候选未返回结论/);
    assert.match(errorDetail, /token=<redacted>/);

    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
  } finally {
    await page.session.send("Emulation.clearDeviceMetricsOverride").catch(() => {});
    await page.close();
  }
});

test("m12 attribution-jobs UI shows sanitized metrics and retries unfinished work", async () => {
  const page = await createBrowserPage();
  const violations = browserViolations(page.session);
  const stepRequests = [];
  try {
    await installCookie(page, await currentLoginCookie());
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 960,
      deviceScaleFactor: 1,
      mobile: false,
    });
    page.session.on("Network.requestWillBeSent", ({ request }) => {
      if (request.url.includes("/evolution/runs/run-v2-blocked-attribution/steps/")) {
        stepRequests.push(request.url);
      }
    });
    await openRun(page, "run-v2-blocked-attribution");
    const blocked = await waitForDocument(
      page.session,
      `(() => {
        const banner = document.querySelector("[data-testid='blocked-banner']");
        const runtime = document.querySelector("[data-testid='attribution-job-runtime']");
        const text = document.body.textContent;
        if (!banner || !runtime || !text.includes("v2-blocked-probe-1")) return null;
        return {
          banner: banner.textContent,
          current: document.querySelector("[aria-current='step']")?.getAttribute("data-step-key"),
          clustersDisabled:
            document.querySelector("[data-step-key='clusters']")?.disabled ?? null,
          nextRetry: Boolean(document.querySelector("[data-testid='next-retry-at']")),
          retry: document.querySelector("[data-testid='run-retry']")?.textContent?.trim() ?? "",
          text,
        };
      })()`,
      "blocked attribution detail",
    );
    assert.match(blocked.banner, /归因（attribution）阶段阻塞/);
    assert.match(blocked.banner, /归因引擎暂时不可用/);
    assert.match(blocked.banner, /自动重试 2 次/);
    assert.equal(blocked.nextRetry, true);
    assert.equal(blocked.retry, "重试");
    assert.equal(blocked.current, "attribution");
    assert.equal(blocked.clustersDisabled, true);
    assert.match(blocked.text, /第 4 步 · 对象归因/);
    assert.match(blocked.text, /v2-blocked-probe-1/);
    assert.match(blocked.text, /失败 · 第 1\/3 次/);
    assert.match(blocked.text, /agent-skill-stub-v1/);
    assert.match(blocked.text, /P95 780ms/);
    assert.match(blocked.text, /Token 128/);
    assert.match(blocked.text, /证据覆盖 50%/);
    assert.match(blocked.text, /上下文 abcdef123456/);
    assert.doesNotMatch(blocked.text, /Authorization|Skill content|raw trace/i);
    await screenshot(page, "06-after-blocked-attribution.png");

    await clickButton(page, "重试未完成项");
    const completed = await waitForDocument(
      page.session,
      `(() => {
        const panel = document.querySelector("[data-testid='attribution-job-runtime']");
        if (!panel?.textContent.includes("已完成")) return null;
        return panel.textContent;
      })()`,
      "completed attribution retry",
    );
    assert.match(completed, /已完成 · 第 2\/3 次/);

    const requestedKeys = [
      ...new Set(
        stepRequests.map((url) => url.split("/steps/")[1]?.split("?")[0]),
      ),
    ];
    assert.deepEqual(requestedKeys, ["attribution"]);
    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
  } finally {
    await page.session.send("Emulation.clearDeviceMetricsOverride").catch(() => {});
    await page.close();
  }
});
