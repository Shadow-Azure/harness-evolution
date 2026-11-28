import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
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
const initialPassword = "issue-674-initial-password";
const finalPassword = "issue-674-final-password";
const secret = "issue-674-signing-secret-with-sufficient-length";
const workspaceId = "ws-default";
const runId = "run-cluster-layout";
const runApi = `/api/workspaces/${workspaceId}/evolution/runs/${runId}`;
const longTargetName = `synthetic-review-${"long-name-".repeat(10)}`;
const evidenceDir = process.env.HE_EVIDENCE_DIR ?? "";
const evidencePrefix = process.env.HE_EVIDENCE_PREFIX ?? "after";
let api;
let web;
let dataDir;
let screenshotsDir;
let baseUrl;
let apiLogs = "";
let webLogs = "";
let fixture = {};
let mockFailures = [];

function runDetail(status, options = {}) {
  const completed = status === "completed";
  const stageLabel =
    status === "completed"
      ? "第 5/5 步 · 聚类完成"
      : status === "running"
        ? "第 2/5 步 · 关联 Session 中…"
        : "第 1/5 步 · 选择范围中…";
  return {
    runId,
    title: "synthetic cluster preview",
    mode: "cluster_only",
    target: {
      type: "skill",
      name: options.targetName ?? longTargetName,
      version: "synthetic-1",
    },
    window: { from: "2026-10-01", to: "2026-10-31" },
    models: ["glm-5.3"],
    policy: { preset: "default" },
    cacheEnabled: false,
    createdBy: "Administrator",
    createdAt: "2026-11-28T08:00:00+08:00",
    status,
    controlState: options.controlState ?? null,
    canPause: status === "preparing" || status === "running",
    canResume: false,
    error: options.error ?? null,
    stats: {
      sessions: 4,
      versionUnresolvedSessions: 0,
      badCases: 7,
      potential: 7,
      attributed: 7,
      reused: 0,
      clusters: options.clusters ?? 0,
      byCategory: { flow: 0, context: 0, model: 0, prompt: 7, error: 0 },
    },
    progress: {
      unit: completed ? 5 : status === "running" ? 2 : 0,
      total: 5,
      percent: completed ? 100 : status === "running" ? 40 : 0,
      stageLabel,
      doneRounds: 0,
      accepted: 0,
    },
    final: null,
    blockedStage: null,
    retryAttempts: 0,
    nextRetryAt: null,
    evalStatus: { verdict: null, bestScore: null, initScore: null },
    workspace: {
      repoUrl: "https://example.invalid/skills.git",
      pushRepoUrl: "https://example.invalid/fork/skills.git",
      subDir: "skills/synthetic-review",
      repoPath: null,
      baseRef: null,
      baseCommit: null,
      branchName: null,
      workspacePath: null,
      remote: "origin",
      pushStatus: "idle",
      pushedAt: null,
      pushError: null,
    },
    lastEventSeq: 0,
    steps: [],
  };
}

function rangeStep() {
  return {
    key: "range",
    index: 0,
    title: "选择范围",
    status: "done",
    clickable: true,
    detail: null,
    payload: {
      condition: {
        targetType: "skill",
        targetName: longTargetName,
        targetVersion: "synthetic-1",
        targetRevision: "digest:abc",
        from: "2026-10-01",
        to: "2026-10-31",
        policy: {
          preset: "default",
          includeSelfReport: true,
          includeAfterObject: false,
          sameObjectOnly: true,
        },
        cacheEnabled: false,
        workspaceId,
      },
      stats: { sessions: 4, badCases: 7, potential: 7 },
    },
  };
}

function clustersStep(count) {
  return {
    key: "clusters",
    index: 4,
    title: "聚类与严重度",
    status: "done",
    clickable: true,
    detail: null,
    payload: {
      clusters: Array.from({ length: count }, (_, index) => ({
        clusterId: `cluster-${index + 1}`,
        title: `聚类问题 ${index + 1}：长文档分块上下文丢失`,
        description:
          "长文档分块时上下文被截断，模型缺少前文；聚类按归因根因合并同类问题。",
        category: "prompt",
        caseCount: 1,
        confidence: 0.74,
        severity: 5.2 - index * 0.1,
        rank: index + 1,
        cases: [
          {
            badCaseId: `badcase-layout-${index + 1}`,
            title: `分块后缺少前文 ${index + 1}`,
            objectName: longTargetName,
            badCaseType: "prompt",
            triggerAt: "2026-10-20T10:00:00+08:00",
            createdAt: "2026-10-20T10:05:00+08:00",
          },
        ],
      })),
    },
  };
}

function attributionStep(count) {
  return {
    key: "attribution",
    index: 3,
    title: "对象归因",
    status: "done",
    clickable: true,
    detail: null,
    payload: {
      summary: { potential: count, reused: 0, fresh: count, nonTarget: 0 },
      rows: Array.from({ length: count }, (_, index) => ({
        badCaseId: `badcase-layout-${index + 1}`,
        sessionId: `session-layout-${index + 1}`,
        attributionId: `attr-layout-${index + 1}`,
        category: "prompt",
        description: "长文档分块时上下文被截断。",
        source: "fresh",
        confidence: 0.8,
      })),
    },
  };
}

async function loginCookie() {
  let password = initialPassword;
  let response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password }),
  });
  if (response.status === 401) {
    password = finalPassword;
    response = await fetch(`${baseUrl}/api/auth/login`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ username: "admin", password }),
    });
  }
  assert.equal(response.status, 200);
  const login = await response.json();
  const initialCookie = response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(initialCookie);
  if (password === initialPassword) {
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
  }
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

function responseFor(pathname) {
  if (pathname === runApi) return fixture.detail ?? null;
  if (pathname === `${runApi}/steps/range`) return fixture.range ?? null;
  if (pathname === `${runApi}/steps/clusters`) return fixture.clusters ?? null;
  if (pathname === `${runApi}/steps/attribution`) return fixture.attribution ?? null;
  return null;
}

async function installRunMocks(page) {
  await page.session.send("Fetch.enable", {
    patterns: [
      {
        urlPattern: `*api/workspaces/${workspaceId}/evolution/runs/${runId}*`,
        requestStage: "Request",
      },
    ],
  });
  page.session.on("Fetch.requestPaused", async ({ requestId, request }) => {
    try {
      const pathname = new URL(request.url).pathname;
      const body = responseFor(pathname);
      if (body === null) {
        await page.session.send("Fetch.continueRequest", { requestId });
        return;
      }
      await page.session.send("Fetch.fulfillRequest", {
        requestId,
        responseCode: 200,
        responseHeaders: [{ name: "Content-Type", value: "application/json" }],
        body: Buffer.from(JSON.stringify(body)).toString("base64"),
      });
    } catch (error) {
      mockFailures.push(String(error));
      await page.session
        .send("Fetch.continueRequest", { requestId })
        .catch(() => {});
    }
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
      result.exceptionDetails.exception?.description ??
        result.exceptionDetails.text,
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
  await writeFile(path.join(screenshotsDir, filename), data, "base64");
}

const snapshotExpression = (token, expectedClusters) => `(() => {
  if (!location.search.includes(${JSON.stringify(token)})) return null;
  const root = document.querySelector("[data-testid='evolution-cluster-preview']");
  const status = document.querySelector("[data-testid='cluster-status-detail']");
  const badge = document.querySelector("[data-testid='cluster-status']");
  const mode = document.querySelector(".mode-note");
  const head = document.querySelector(".detail-head");
  const back = document.querySelector(".back");
  const target = document.querySelector(".target-chip");
  if (!root || !status || !badge || !mode || !head || !back) return null;
  const clusters = [...document.querySelectorAll(".cluster")];
  if (clusters.length !== ${expectedClusters}) return null;
  const box = (node) => {
    if (!node) return null;
    const rect = node.getBoundingClientRect();
    return {
      top: rect.top,
      bottom: rect.bottom,
      left: rect.left,
      right: rect.right,
      width: rect.width,
      height: rect.height,
    };
  };
  const style = getComputedStyle(root);
  const rootBox = box(root);
  const statusBox = box(status);
  const modeBox = box(mode);
  const headBox = box(head);
  const children = [...root.children].map(box).filter(Boolean);
  const contentBottom = Math.max(...children.map((item) => item.bottom));
  return {
    viewport: { width: innerWidth, height: innerHeight },
    root: {
      ...rootBox,
      scrollTop: root.scrollTop,
      scrollHeight: root.scrollHeight,
      clientHeight: root.clientHeight,
      scrollWidth: root.scrollWidth,
      clientWidth: root.clientWidth,
      alignContent: style.alignContent,
      overflowY: style.overflowY,
      paddingTop: Number.parseFloat(style.paddingTop),
      paddingLeft: Number.parseFloat(style.paddingLeft),
    },
    back: box(back),
    head: headBox,
    mode: modeBox,
    status: statusBox,
    target: box(target),
    headToMode: modeBox.top - headBox.bottom,
    modeToStatus: statusBox.top - modeBox.bottom,
    bottomGap: rootBox.bottom - contentBottom,
    document: {
      scrollWidth: document.scrollingElement.scrollWidth,
      clientWidth: document.scrollingElement.clientWidth,
    },
    badge: badge.textContent.trim(),
    statusText: status.textContent.trim(),
    modeText: mode.textContent.replace(/\\s+/g, " ").trim(),
    targetText: target.textContent.trim(),
    targetTitle: target.getAttribute("title"),
    duplicatePreparing: document.body.textContent.includes("正在准备聚类结果"),
    clusterCount: clusters.length,
  };
})()`;

async function open(page, viewport, token, expectedClusters, mobile = false) {
  await page.session.send("Emulation.setDeviceMetricsOverride", {
    width: viewport.width,
    height: viewport.height,
    deviceScaleFactor: 1,
    mobile,
  });
  // Each navigation starts a fresh document; refresh the rotating cookie so a
  // prior page's refresh token cannot send the next load to /login.
  await installCookie(page, await loginCookie());
  await page.session.send("Page.navigate", { url: "about:blank" });
  await waitForDocument(
    page.session,
    `document.readyState === "complete"`,
    "blank document",
  );
  await page.session.send("Page.navigate", {
    url: `${baseUrl}/evolution/cluster/${runId}?geometry=${token}`,
  });
  try {
    return await waitForDocument(
      page.session,
      snapshotExpression(token, expectedClusters),
      `${token} ${viewport.width}x${viewport.height} cluster preview`,
    );
  } catch (error) {
    const state = await evaluate(
      page,
      `({ href: location.href, text: document.body.innerText.slice(0, 400) })`,
    ).catch(() => null);
    throw new Error(`${error.message}\n${JSON.stringify(state)}`);
  }
}

function check(condition, message, failures) {
  if (!condition) failures.push(message);
}

function expectTopAligned(snapshot, label, failures) {
  check(
    snapshot.root.overflowY === "auto",
    `${label}: page must own page-level scrolling, got ${snapshot.root.overflowY}`,
    failures,
  );
  check(
    snapshot.root.alignContent === "start",
    `${label}: grid tracks must keep content height, got align-content=${snapshot.root.alignContent}`,
    failures,
  );
  check(
    Math.abs(snapshot.back.top - snapshot.root.top - snapshot.root.paddingTop) <= 1,
    `${label}: back entry must start at the content box top`,
    failures,
  );
  check(
    snapshot.headToMode >= 10 && snapshot.headToMode <= 20,
    `${label}: header-to-mode gap must stay on the 14px detail rhythm, got ${snapshot.headToMode}`,
    failures,
  );
  check(
    snapshot.modeToStatus >= 10 && snapshot.modeToStatus <= 20,
    `${label}: mode-to-status gap must stay on the 14px detail rhythm, got ${snapshot.modeToStatus}`,
    failures,
  );
  check(
    snapshot.document.scrollWidth === snapshot.document.clientWidth,
    `${label}: the document must not overflow horizontally`,
    failures,
  );
  check(
    !snapshot.duplicatePreparing,
    `${label}: preparing state must not render the duplicate preparation card`,
    failures,
  );
}

function expectStable(short, tall, label, failures) {
  const pairs = [
    ["status height", short.status.height, tall.status.height],
    ["mode height", short.mode.height, tall.mode.height],
    ["head-to-mode gap", short.headToMode, tall.headToMode],
    ["mode-to-status gap", short.modeToStatus, tall.modeToStatus],
  ];
  for (const [name, first, second] of pairs) {
    check(
      Math.abs(first - second) <= 2,
      `${label}: ${name} must not follow viewport height (${first} vs ${second})`,
      failures,
    );
  }
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-issue-674-data-"));
  screenshotsDir = evidenceDir
    ? path.join(evidenceDir)
    : await mkdtemp(path.join(tmpdir(), "harness-issue-674-screenshots-"));
  await mkdir(screenshotsDir, { recursive: true });
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
      HE_LOGIN_RATE_LIMIT: "1000",
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

after(async () => {
  await stop(web);
  await stop(api);
  if (dataDir) await rm(dataDir, { recursive: true, force: true });
  if (!evidenceDir && screenshotsDir) {
    await rm(screenshotsDir, { recursive: true, force: true });
  }
});

test("issue-674 cluster preview keeps short states compact and multi-cluster results scrollable", async () => {
  const page = await createBrowserPage();
  const violations = browserViolations(page.session);
  const failures = [];
  mockFailures = [];
  try {
    await installCookie(page, await loginCookie());
    await installRunMocks(page);

    fixture = {
      detail: runDetail("preparing"),
    };
    const short = await open(page, { width: 1366, height: 768 }, "preparing", 0);
    expectTopAligned(short, "preparing 1366x768", failures);
    check(short.badge === "准备中", `preparing badge: ${short.badge}`, failures);
    check(
      short.statusText.includes("第 1/5 步 · 选择范围中…"),
      `preparing status copy must come from progress.stageLabel: ${short.statusText}`,
      failures,
    );
    check(
      short.targetTitle === short.targetText,
      `long object name must expose the full value: ${short.targetTitle}`,
      failures,
    );
    check(
      short.bottomGap > 100,
      `preparing 1366x768: the remaining space must sit below the content, got ${short.bottomGap}`,
      failures,
    );
    await screenshot(page, `${evidencePrefix}-preparing-1366x768.png`);

    const tall = await open(page, { width: 1366, height: 1080 }, "preparing-tall", 0);
    expectTopAligned(tall, "preparing 1366x1080", failures);
    expectStable(short, tall, "preparing 1366x768 vs 1366x1080", failures);
    await screenshot(page, `${evidencePrefix}-preparing-1366x1080.png`);

    const wide = await open(page, { width: 1920, height: 1080 }, "preparing-wide", 0);
    expectTopAligned(wide, "preparing 1920x1080", failures);
    expectStable(tall, wide, "preparing 1366x1080 vs 1920x1080", failures);
    await screenshot(page, `${evidencePrefix}-preparing-1920x1080.png`);

    const mobile = await open(
      page,
      { width: 390, height: 844 },
      "preparing-mobile",
      0,
      true,
    );
    check(
      mobile.root.overflowY === "visible",
      `preparing 390x844: the document must scroll, got ${mobile.root.overflowY}`,
      failures,
    );
    check(
      mobile.root.scrollHeight === mobile.root.clientHeight,
      "preparing 390x844: the page must not nest a second scroll container",
      failures,
    );
    check(
      mobile.document.scrollWidth === mobile.document.clientWidth,
      "preparing 390x844: the document must not overflow horizontally",
      failures,
    );
    await screenshot(page, `${evidencePrefix}-preparing-390x844.png`);

    const clusterCount = 10;
    fixture = {
      detail: runDetail("completed", { clusters: clusterCount }),
      range: rangeStep(),
      clusters: clustersStep(clusterCount),
      attribution: attributionStep(clusterCount),
    };
    const completed = await open(
      page,
      { width: 1366, height: 768 },
      "completed",
      clusterCount,
    );
    expectTopAligned(completed, "completed 1366x768", failures);
    check(
      completed.badge === "已完成",
      `completed badge: ${completed.badge}`,
      failures,
    );
    check(
      completed.statusText.includes("第 5/5 步 · 聚类完成"),
      `completed status copy: ${completed.statusText}`,
      failures,
    );
    check(
      completed.root.scrollHeight > completed.root.clientHeight,
      "completed 1366x768: multiple clusters must overflow the page scroller",
      failures,
    );
    check(
      completed.mode.height <= 48,
      `mode note must stay a compact strip, got ${completed.mode.height}`,
      failures,
    );
    await screenshot(page, `${evidencePrefix}-completed-1366x768.png`);
    const bottom = await evaluate(
      page,
      `(() => {
        const root = document.querySelector("[data-testid='evolution-cluster-preview']");
        root.scrollTop = root.scrollHeight;
        const clusters = [...document.querySelectorAll(".cluster")];
        const last = clusters[clusters.length - 1]?.getBoundingClientRect();
        return last
          ? { lastTop: last.top, lastBottom: last.bottom, innerHeight, scrollTop: root.scrollTop }
          : null;
      })()`,
    );
    check(
      bottom && bottom.scrollTop > 0,
      "completed multi-cluster page must scroll",
      failures,
    );
    check(
      bottom &&
        bottom.lastTop >= 0 &&
        bottom.lastBottom <= bottom.innerHeight + 1,
      `the last cluster must be reachable: ${JSON.stringify(bottom)}`,
      failures,
    );
    await screenshot(page, `${evidencePrefix}-completed-1366x768-scrolled.png`);

    const completedTall = await open(
      page,
      { width: 1366, height: 1080 },
      "completed-tall",
      clusterCount,
    );
    expectTopAligned(completedTall, "completed 1366x1080", failures);
    expectStable(
      completed,
      completedTall,
      "completed 1366x768 vs 1366x1080",
      failures,
    );
    await screenshot(page, `${evidencePrefix}-completed-1366x1080.png`);

    check(
      mockFailures.length === 0,
      `mock handler failures: ${mockFailures.join(" | ")}`,
      failures,
    );
    assert.deepEqual(
      failures,
      [],
      `${failures.join("\n")}\n\nVite:\n${webLogs}\n\nAPI:\n${apiLogs}`,
    );
    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
  } finally {
    await page.session.send("Emulation.clearDeviceMetricsOverride").catch(() => {});
    await page.close();
  }
});
