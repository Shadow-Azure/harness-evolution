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
const longSessionPrompt = "SWE-bench astropy-12907 修复任务 ".repeat(200).slice(0, 3337);
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
    HE_LOGIN_RATE_LIMIT: "100",
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
    const shell = await waitForDocument(
      page.session,
      `(() => {
        const page = document.querySelector("[data-testid='evolution-run-detail']");
        const info = page?.querySelector("[data-testid='run-info-panel']");
        const progress = page?.querySelector("[data-testid='run-progress']");
        const workspace = page?.querySelector("[data-testid='run-workspace']");
        const head = page?.querySelector(".detail-head");
        if (!page || !info || !progress || !workspace || !head) return null;
        const infoText = info.textContent;
        // The info panel first renders run stats, then fills the attribution
        // rows (non-target / cached / fresh) and the policy chips from the
        // step requests. Wait for all three so the assertions below never read
        // a half-filled panel on a slow CI runner.
        const policy = page.querySelector("[data-testid='run-policy-cache']")?.textContent ?? "";
        if (!infoText.includes("5 / 1") || !infoText.includes("本次新增 3")) return null;
        if (!policy.includes("默认策略") || !policy.includes("复用缓存归因")) return null;
        return {
          head: head.textContent,
          infoText,
          infoBeforeProgress: Boolean(
            info.compareDocumentPosition(progress) & Node.DOCUMENT_POSITION_FOLLOWING,
          ),
          workspaceInInfo: info.contains(workspace),
          standaloneWorkspace: Boolean(document.querySelector(".workspace-panel")),
          policy,
          branchCopy: Boolean(page.querySelector("[data-testid='copy-branch']")),
          tabs: [...page.querySelectorAll(".detail-tabs [role='tab']")].map((tab) =>
            tab.textContent.trim(),
          ),
        };
      })()`,
      "prototype-aligned run detail shell",
    );
    assert.match(shell.head, /默认空间/);
    assert.match(shell.head, /已完成/);
    assert.doesNotMatch(shell.head, /Administrator · /);
    assert.equal(shell.infoBeforeProgress, true);
    assert.equal(shell.workspaceInInfo, true);
    assert.equal(shell.standaloneWorkspace, false);
    assert.equal(shell.branchCopy, true);
    assert.match(shell.policy, /默认策略/);
    assert.match(shell.policy, /复用缓存归因/);
    assert.match(shell.infoText, /工作空间/);
    assert.match(shell.infoText, /可归因 \/ 非该对象/);
    assert.match(shell.infoText, /5 \/ 1/);
    assert.match(shell.infoText, /潜在 bad case 的归因结论分布（6 条）/);
    assert.match(shell.infoText, /非该对象 1/);
    assert.match(shell.infoText, /＝ 归因 5 · 复用缓存 2 · 本次新增 3/);
    assert.doesNotMatch(shell.infoText, /模型（多选）/);
    assert.ok(shell.tabs.some((tab) => tab.includes("七步详情")));
    assert.ok(shell.tabs.some((tab) => tab.includes("执行日志")));
    await clickStep(page, "sessions");
    const sessions = await waitForDocument(
      page.session,
      `(() => {
        const rows = [...document.querySelectorAll(".rep tbody tr")];
        if (rows.length !== 4) return null;
        const first = rows[0];
        const title = first.querySelector(".session-title");
        const table = first.closest("table");
        const scroll = first.closest(".table-scroll");
        const headers = [...table.querySelectorAll("thead th")].map((th) => {
          const rect = th.getBoundingClientRect();
          return { text: th.textContent.trim(), width: rect.width, left: rect.left };
        });
        return {
          rows: rows.length,
          pager: document.querySelector(".pager-info")?.textContent ?? "",
          text: rows.map((row) => row.textContent),
          title: title?.textContent ?? "",
          hover: title?.getAttribute("title") ?? "",
          height: first.getBoundingClientRect().height,
          sessionWidth: first.cells[0].getBoundingClientRect().width,
          tableWidth: table.getBoundingClientRect().width,
          scrollWidth: table.scrollWidth,
          clientWidth: scroll.clientWidth,
          headers,
        };
      })()`,
      "first Session page",
    );
    assert.equal(sessions.rows, 4);
    assert.match(sessions.pager, /第\s*1\s*\/\s*2\s*页/);
    assert.match(sessions.text.join(" "), /来源运行 A/);
    assert.equal(sessions.title, "来源运行 A");
    assert.equal(sessions.hover, longSessionPrompt);
    assert.ok(
      sessions.height <= 64,
      `long prompt grew the Session row to ${sessions.height}px`,
    );
    assert.ok(
      sessions.sessionWidth < sessions.tableWidth * 0.75,
      `Session column ${sessions.sessionWidth}px of ${sessions.tableWidth}px`,
    );
    assert.equal(sessions.headers.length, 4);
    for (const header of sessions.headers) {
      assert.ok(header.width >= 100, `${header.text} column is ${header.width}px`);
      assert.ok(header.left >= 0, `${header.text} column starts off screen`);
    }
    assert.ok(
      sessions.scrollWidth <= sessions.clientWidth + 1,
      `Session table overflows horizontally: ${sessions.scrollWidth} > ${sessions.clientWidth}`,
    );
    await screenshotStep(page, "01a-after-sessions-long-title.png");
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
        const sourceLinks = [...document.querySelectorAll("td.id a")];
        const reportLinks = [...document.querySelectorAll("td.report-id a")];
        if (sourceLinks.length !== 6 || reportLinks.length !== 6) return null;
        reportLinks[0].focus();
        return {
          text,
          rows: rows.length,
          cached: [...document.querySelectorAll(".source-chip.cached")].length,
          fresh: [...document.querySelectorAll(".source-chip.fresh")].length,
          sourceHrefs: sourceLinks.map((link) => link.getAttribute("href")),
          reports: reportLinks.map((link) => ({
            href: link.getAttribute("href"),
            target: link.target,
            rel: link.rel,
            label: link.getAttribute("aria-label"),
          })),
          focused: document.activeElement === reportLinks[0],
        };
      })()`,
      "attribution step",
    );
    assert.equal(attribution.rows, 6);
    assert.equal(attribution.cached, 2);
    assert.equal(attribution.fresh, 4);
    assert.equal(attribution.focused, true);
    assert.equal(attribution.sourceHrefs.length, 6);
    assert.equal(
      attribution.sourceHrefs[0],
      "/workspaces/ws-default/sessions/v2-session-1/errors?case=v2-case-1&tab=desc",
    );
    assert.equal(
      attribution.sourceHrefs[5],
      "/workspaces/ws-default/sessions/v2-session-5/errors?case=v2-case-6&tab=desc",
    );
    assert.deepEqual(
      attribution.reports.map((report) => report.href),
      [
        "/workspaces/ws-default/sessions/v2-session-1/errors?case=v2-case-1&tab=attr&at=v2-probe-1",
        "/workspaces/ws-default/sessions/v2-session-2/errors?case=v2-case-2&tab=attr&at=v2-probe-2",
        "/workspaces/ws-default/sessions/v2-session-1/errors?case=v2-case-3&tab=attr&at=v2-probe-3",
        "/workspaces/ws-default/sessions/v2-session-3/errors?case=v2-case-4&tab=attr&at=v2-probe-4",
        "/workspaces/ws-default/sessions/v2-session-4/errors?case=v2-case-5&tab=attr&at=v2-probe-5",
        "/workspaces/ws-default/sessions/v2-session-5/errors?case=v2-case-6&tab=attr&at=v2-probe-6",
      ],
    );
    assert.ok(
      attribution.reports.every(
        (report) =>
          report.target === "_blank" &&
          report.rel.includes("noopener") &&
          report.label?.includes("归因分析"),
      ),
    );
    assert.match(
      attribution.reports[0].label,
      /归因报告 v2-probe-1，在新窗口打开归因分析/,
    );
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
    await openRun(page, "run-v2-preparing");
    const preparing = await waitForDocument(
      page.session,
      `(() => {
        const page = document.querySelector("[data-testid='evolution-run-detail']");
        if (!page) return null;
        const text = page.textContent;
        if (!text.includes("已受理，正在准备筛选与聚类")) return null;
        return {
          badge: page.querySelector(".detail-head .badge")?.textContent ?? "",
          info: page.querySelector("[data-testid='run-info-panel']")?.textContent ?? "",
          tabs: [...page.querySelectorAll(".detail-tabs [role='tab']")].map((tab) =>
            tab.textContent.trim(),
          ),
        };
      })()`,
      "preparing run detail",
    );
    assert.match(preparing.badge, /准备中/);
    assert.match(preparing.info, /潜在 bad case 的归因结论分布（0 条）/);
    assert.equal(preparing.tabs.length, 2);
    await screenshot(page, "06-after-preparing.png");

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

test("m10-06 step-4 attribution links resolve to the description and analysis tabs", async () => {
  const page = await createBrowserPage();
  try {
    await installCookie(page, await currentLoginCookie());
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 960,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await openRun(page, "run-v2-completed", "?step=attribution");
    const links = await waitForDocument(
      page.session,
      `(() => {
        if (!document.body.textContent.includes("第 4 步 · 对象归因")) return null;
        const source = document.querySelector("td.id a")?.getAttribute("href");
        const report = document.querySelector("td.report-id a")?.getAttribute("href");
        return source && report ? { source, report } : null;
      })()`,
      "step-4 attribution links",
    );

    await installCookie(page, await currentLoginCookie());
    await page.session.send("Page.navigate", { url: `${baseUrl}${links.report}` });
    const report = await waitForDocument(
      page.session,
      `(() => {
        const tab = document.querySelector("#attr-tab");
        const report = document.querySelector("[data-testid='attribution-report']");
        const deepLink = document.querySelector("[data-testid='attribution-deep-link']");
        if (!tab || !report || !deepLink) return null;
        return {
          active: tab.getAttribute("aria-selected"),
          label: tab.textContent,
          attributionId: deepLink.getAttribute("title"),
          href: location.href,
        };
      })()`,
      "attribution analysis deep link",
    );
    assert.equal(report.active, "true");
    assert.match(report.label, /归因分析/);
    assert.equal(report.attributionId, "v2-probe-1");
    assert.match(report.href, /tab=attr&at=v2-probe-1$/);
    await screenshot(page, "07-after-attribution-link-target.png");

    await installCookie(page, await currentLoginCookie());
    await page.session.send("Page.navigate", { url: `${baseUrl}${links.source}` });
    const description = await waitForDocument(
      page.session,
      `(() => {
        const tab = document.querySelector("#desc-tab");
        if (!tab) return null;
        return {
          active: tab.getAttribute("aria-selected"),
          href: location.href,
        };
      })()`,
      "problem description deep link",
    );
    assert.equal(description.active, "true");
    assert.match(description.href, /case=v2-case-1&tab=desc$/);
    await screenshot(page, "08-after-attribution-source-target.png");
  } finally {
    await page.session.send("Emulation.clearDeviceMetricsOverride").catch(() => {});
    await page.close();
  }
});

test("m10-06 blocked attribution shows retry facts and does not request unreached steps, m12 attribution-jobs UI shows sanitized metrics and retries unfinished work", async () => {
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
    const blockedContent = await waitForDocument(
      page.session,
      `(() => {
        const text = document.body.textContent ?? "";
        return text.includes("v2-blocked-probe-1") ? text : null;
      })()`,
      "blocked attribution step content",
    );
    assert.match(blockedContent, /v2-blocked-probe-1/);
    assert.match(blockedContent, /失败 · 第 1\/3 次/);
    assert.match(blockedContent, /agent-skill-stub-v1/);
    assert.match(blockedContent, /P95 780ms/);
    assert.match(blockedContent, /Token 128/);
    assert.match(blockedContent, /证据覆盖 50%/);
    assert.match(blockedContent, /上下文 abcdef123456/);
    assert.doesNotMatch(blockedContent, /Authorization|Skill content|raw trace/i);
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
    assert.deepEqual(requestedKeys, ["range", "attribution"]);
    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
  } finally {
    await page.session.send("Emulation.clearDeviceMetricsOverride").catch(() => {});
    await page.close();
  }
});

test("m10-06 run detail owns the page scroll and keeps the V2 gutter", async () => {
  const page = await createBrowserPage();
  const violations = browserViolations(page.session);
  try {
    await installCookie(page, await currentLoginCookie());
    const viewports = [
      { width: 1500, height: 837, gutter: 24 },
      { width: 1440, height: 900, gutter: 24 },
      { width: 1366, height: 768, gutter: 24 },
      { width: 1920, height: 1080, gutter: 124 },
    ];
    for (const viewport of viewports) {
      await page.session.send("Emulation.setDeviceMetricsOverride", {
        width: viewport.width,
        height: viewport.height,
        deviceScaleFactor: 1,
        mobile: false,
      });
      await installCookie(page, await currentLoginCookie());
      await openRun(
        page,
        "run-v2-completed",
        `?step=clusters&g=${viewport.width}x${viewport.height}`,
      );
      const geometry = await waitForDocument(
        page.session,
        `(() => {
          const root = document.querySelector("[data-testid='evolution-run-detail']");
          const main = document.querySelector("main.workspace-main");
          const info = root?.querySelector("[data-testid='run-info-panel']");
          if (!root || !main || !info) return null;
          if (document.querySelectorAll("[data-step-key]").length !== 7) return null;
          if (root.querySelectorAll(".cluster").length !== 2) return null;
          const rect = root.getBoundingClientRect();
          const infoRect = info.getBoundingClientRect();
          const style = getComputedStyle(root);
          return {
            innerWidth,
            scrollWidth: root.scrollWidth,
            clientWidth: root.clientWidth,
            scrollHeight: root.scrollHeight,
            clientHeight: root.clientHeight,
            rectLeft: rect.left,
            rectRight: rect.right,
            paddingLeft: Number.parseFloat(style.paddingLeft),
            paddingRight: Number.parseFloat(style.paddingRight),
            overflowY: style.overflowY,
            mainOverflow: getComputedStyle(main).overflowY,
            infoLeft: infoRect.left,
            infoRight: infoRect.right,
            documentScrollWidth: document.documentElement.scrollWidth,
            documentClientWidth: document.documentElement.clientWidth,
          };
        })()`,
        `${viewport.width}x${viewport.height} run detail scroll geometry`,
      );
      assert.equal(geometry.overflowY, "auto", JSON.stringify(geometry));
      assert.equal(geometry.mainOverflow, "hidden", JSON.stringify(geometry));
      assert.ok(
        Math.abs(geometry.rectRight - geometry.innerWidth) <= 1,
        `scroll container right edge ${geometry.rectRight} must equal window width ${geometry.innerWidth}`,
      );
      assert.ok(
        Math.abs(geometry.rectLeft) <= 1,
        `scroll container must span the main column: left ${geometry.rectLeft}`,
      );
      assert.ok(
        Math.abs(geometry.paddingLeft - viewport.gutter) <= 1,
        `left gutter ${geometry.paddingLeft} must match ${viewport.gutter}`,
      );
      assert.ok(
        Math.abs(geometry.paddingRight - viewport.gutter) <= 1,
        `right gutter ${geometry.paddingRight} must match ${viewport.gutter}`,
      );
      assert.ok(
        geometry.infoRight - geometry.infoLeft <= 1720,
        `content column must cap at 1720px: ${geometry.infoRight - geometry.infoLeft}`,
      );
      assert.ok(
        geometry.scrollHeight > geometry.clientHeight,
        `run detail must overflow inside the page: ${geometry.scrollHeight} <= ${geometry.clientHeight}`,
      );
      assert.equal(
        geometry.scrollWidth,
        geometry.clientWidth,
        "the scroll container must not overflow horizontally",
      );
      assert.equal(
        geometry.documentScrollWidth,
        geometry.documentClientWidth,
        "the document must not scroll horizontally",
      );
    }

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1500,
      height: 837,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await installCookie(page, await currentLoginCookie());
    await openRun(page, "run-v2-completed", "?step=clusters");
    await waitForDocument(
      page.session,
      `document.querySelectorAll(".run-detail-page .cluster").length === 2`,
      "cluster step for input scrolling",
    );
    await page.session.send("Input.dispatchMouseEvent", {
      type: "mouseMoved",
      x: 750,
      y: 500,
      button: "none",
    });
    await page.session.send("Input.dispatchMouseEvent", {
      type: "mouseWheel",
      x: 750,
      y: 500,
      deltaX: 0,
      deltaY: 120,
      button: "none",
    });
    const wheeled = await waitForDocument(
      page.session,
      `(() => {
        const root = document.querySelector("[data-testid='evolution-run-detail']");
        return root.scrollTop > 0 ? root.scrollTop : null;
      })()`,
      "wheel scroll inside run detail",
    );
    assert.ok(wheeled > 0);

    const stepPoint = await evaluate(
      page,
      `(() => {
        const el = document.querySelector("[data-step-key='clusters']");
        const rect = el.getBoundingClientRect();
        return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
      })()`,
    );
    await page.session.send("Input.dispatchMouseEvent", {
      type: "mousePressed",
      x: stepPoint.x,
      y: stepPoint.y,
      button: "left",
      clickCount: 1,
    });
    await page.session.send("Input.dispatchMouseEvent", {
      type: "mouseReleased",
      x: stepPoint.x,
      y: stepPoint.y,
      button: "left",
      clickCount: 1,
    });
    for (const keyName of ["PageDown", "End"]) {
      const virtualKey = keyName === "End" ? 35 : 34;
      await page.session.send("Input.dispatchKeyEvent", {
        type: "rawKeyDown",
        key: keyName,
        code: keyName,
        windowsVirtualKeyCode: virtualKey,
        nativeVirtualKeyCode: virtualKey,
      });
      await page.session.send("Input.dispatchKeyEvent", {
        type: "keyUp",
        key: keyName,
        code: keyName,
        windowsVirtualKeyCode: virtualKey,
        nativeVirtualKeyCode: virtualKey,
      });
      await new Promise((resolve) => setTimeout(resolve, 150));
    }
    const bottom = await waitForDocument(
      page.session,
      `(() => {
        const root = document.querySelector("[data-testid='evolution-run-detail']");
        if (root.scrollHeight - root.scrollTop - root.clientHeight > 2) return null;
        return { scrollTop: root.scrollTop, scrollHeight: root.scrollHeight };
      })()`,
      "PageDown and End reach the run detail bottom",
    );
    assert.ok(
      bottom.scrollTop > wheeled,
      "PageDown and End must scroll past the wheel position",
    );

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 640,
      height: 900,
      deviceScaleFactor: 1,
      mobile: true,
    });
    await installCookie(page, await currentLoginCookie());
    await openRun(page, "run-v2-completed", "?step=clusters");
    await waitForDocument(
      page.session,
      `document.querySelectorAll(".run-detail-page .cluster").length === 2`,
      "mobile cluster step",
    );
    const mobile = await evaluate(
      page,
      `(() => {
        const root = document.querySelector("[data-testid='evolution-run-detail']");
        const main = document.querySelector("main.workspace-main");
        return {
          overflowY: getComputedStyle(root).overflowY,
          mainOverflow: getComputedStyle(main).overflowY,
          rootScrollHeight: root.scrollHeight,
          rootClientHeight: root.clientHeight,
          documentScrollHeight: document.scrollingElement.scrollHeight,
          documentClientHeight: document.scrollingElement.clientHeight,
        };
      })()`,
    );
    assert.equal(mobile.overflowY, "visible", JSON.stringify(mobile));
    assert.equal(mobile.mainOverflow, "visible", JSON.stringify(mobile));
    assert.ok(
      mobile.documentScrollHeight > mobile.documentClientHeight,
      "mobile documents must scroll instead of nesting a second scrollbar",
    );

    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
  } finally {
    await page.session.send("Emulation.clearDeviceMetricsOverride").catch(() => {});
    await page.close();
  }
});

test("m10-06 step 6 renders the accepted commit as collapsible Markdown", async () => {
  const page = await createBrowserPage();
  const violations = browserViolations(page.session);
  try {
    await installCookie(page, await currentLoginCookie());
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1500,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await openRun(page, "run-v2-completed");
    await waitForDocument(
      page.session,
      `document.querySelectorAll("[data-step-key]").length === 7`,
      "seven-step run detail",
    );
    await evaluate(
      page,
      `document.querySelector("[data-step-key='iteration']").click()`,
    );
    const collapsed = await waitForDocument(
      page.session,
      `(() => {
        const commit = document.querySelector(".commit");
        if (!commit) return null;
        const toggle = commit.querySelector(".commit-toggle");
        return {
          hash: commit.querySelector(".hash")?.textContent ?? "",
          subject: commit.querySelector(".commit-subject")?.textContent ?? "",
          text: commit.textContent,
          toggle: toggle?.textContent ?? "",
          expanded: toggle?.getAttribute("aria-expanded") ?? "",
          body: Boolean(commit.querySelector(".commit-message")),
          pageHorizontalScroll:
            document.documentElement.scrollWidth > document.documentElement.clientWidth,
        };
      })()`,
      "collapsed accepted commit",
    );
    assert.match(collapsed.hash, /^ef56ab12cd34$/);
    assert.match(collapsed.subject, /^evolve\(deep-research@v2\.0\.0\): /);
    assert.doesNotMatch(collapsed.text, /##|---|Harness-Verdict/);
    assert.equal(collapsed.body, false);
    assert.equal(collapsed.expanded, "false");
    assert.match(collapsed.toggle, /查看完整 commit message/);
    assert.equal(collapsed.pageHorizontalScroll, false);
    await evaluate(
      page,
      `document.querySelector(".commit").scrollIntoView({ block: "center" })`,
    );
    await screenshot(page, "07-after-step6-commit-collapsed.png");

    await evaluate(page, `document.querySelector(".commit-toggle").click()`);
    const expanded = await waitForDocument(
      page.session,
      `(() => {
        const body = document.querySelector(".commit-message");
        if (!body) return null;
        const toggle = document.querySelector(".commit-toggle");
        return {
          headings: [...body.querySelectorAll("h2")].map((node) =>
            node.textContent.trim(),
          ),
          items: body.querySelectorAll("li").length,
          links: [...body.querySelectorAll("a")].map((node) =>
            node.getAttribute("href"),
          ),
          bodyText: body.textContent,
          toggle: toggle?.textContent ?? "",
          expanded: toggle?.getAttribute("aria-expanded") ?? "",
          pageHorizontalScroll:
            document.documentElement.scrollWidth > document.documentElement.clientWidth,
        };
      })()`,
      "expanded commit markdown",
    );
    assert.deepEqual(expanded.headings, ["问题", "分析", "改动", "追溯"]);
    assert.ok(expanded.items >= 6, JSON.stringify(expanded));
    assert.ok(
      expanded.links.includes("https://example.com/badcases/BC-HC-0007"),
      JSON.stringify(expanded.links),
    );
    assert.doesNotMatch(expanded.bodyText, /##|---/);
    assert.match(expanded.toggle, /收起完整 commit message/);
    assert.equal(expanded.expanded, "true");
    assert.equal(expanded.pageHorizontalScroll, false);
    await evaluate(
      page,
      `document.querySelector(".commit").scrollIntoView({ block: "center" })`,
    );
    await screenshot(page, "07-after-step6-commit-expanded.png");

    await evaluate(page, `document.querySelector(".commit-toggle").click()`);
    await waitForDocument(
      page.session,
      `!document.querySelector(".commit-message")`,
      "collapsed commit markdown again",
    );

    await installCookie(page, await currentLoginCookie());
    await openRun(page, "run-v2-legacy");
    await waitForDocument(
      page.session,
      `document.querySelectorAll("[data-step-key]").length === 7`,
      "legacy seven-step run detail",
    );
    await evaluate(
      page,
      `document.querySelector("[data-step-key='iteration']").click()`,
    );
    const legacy = await waitForDocument(
      page.session,
      `(() => {
        const commit = document.querySelector(".commit");
        if (!commit) return null;
        return {
          text: commit.textContent,
          toggle: Boolean(commit.querySelector(".commit-toggle")),
        };
      })()`,
      "legacy accepted commit",
    );
    assert.match(legacy.text, /evolve\(deep-research\): 历史问题/);
    assert.equal(legacy.toggle, false);
    await evaluate(
      page,
      `document.querySelector(".commit").scrollIntoView({ block: "center" })`,
    );
    await screenshot(page, "08-after-step6-legacy-commit.png");

    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
  } finally {
    await page.session.send("Emulation.clearDeviceMetricsOverride").catch(() => {});
    await page.close();
  }
});

test("m10-06 step 6 iteration renders every stored bundle patch file", async () => {
  const page = await createBrowserPage();
  const violations = browserViolations(page.session);
  try {
    await installCookie(page, await currentLoginCookie());
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1500,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await openRun(page, "run-v2-completed");
    await waitForDocument(
      page.session,
      `document.querySelectorAll("[data-step-key]").length === 7`,
      "seven-step run detail",
    );
    await evaluate(
      page,
      `document.querySelector("[data-step-key='iteration']").click()`,
    );
    const bundle = await waitForDocument(
      page.session,
      `(() => {
        const round = document.querySelector("[data-round-id='v2-round-1']");
        const diff = round?.querySelector(".diff");
        if (!diff) return null;
        return {
          files: [...diff.querySelectorAll(".fhead")].map((node) => node.textContent.trim()),
          added: [...diff.querySelectorAll(".dline.add")].length,
          deleted: [...diff.querySelectorAll(".dline.del")].length,
          pageHorizontalScroll:
            document.documentElement.scrollWidth > document.documentElement.clientWidth,
        };
      })()`,
      "multi-file bundle patch diff",
    );
    assert.deepEqual(bundle.files, ["SKILL.md", "config/synthetic-review.json"]);
    assert.ok(bundle.added >= 2, JSON.stringify(bundle));
    assert.ok(bundle.deleted >= 2, JSON.stringify(bundle));
    assert.equal(bundle.pageHorizontalScroll, false);
    await evaluate(
      page,
      `document.querySelector("[data-round-id='v2-round-1'] .diff").scrollIntoView({ block: "center" })`,
    );
    await screenshot(page, "09-after-step6-iteration-patch.png");

    await evaluate(
      page,
      `document.querySelector("[data-round-id='v2-round-2'] .cluster-head").click()`,
    );
    const legacy = await waitForDocument(
      page.session,
      `(() => {
        const round = document.querySelector("[data-round-id='v2-round-2']");
        const diff = round?.querySelector(".diff");
        if (!diff) return null;
        return {
          files: [...diff.querySelectorAll(".fhead")].map((node) => node.textContent.trim()),
        };
      })()`,
      "legacy single-file patch diff",
    );
    assert.deepEqual(legacy.files, ["SKILL.md"]);
    await evaluate(
      page,
      `document.querySelector("[data-round-id='v2-round-2'] .diff").scrollIntoView({ block: "center" })`,
    );
    await screenshot(page, "10-after-step6-legacy-patch.png");

    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
  } finally {
    await page.session.send("Emulation.clearDeviceMetricsOverride").catch(() => {});
    await page.close();
  }
});
