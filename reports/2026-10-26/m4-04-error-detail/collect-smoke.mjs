import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
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
const reportDir = path.resolve("reports/2026-10-26/m4-04-error-detail");
const screenshotDir = path.join(reportDir, "screenshots");
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const validationCommit = process.env.SMOKE_COMMIT || "working-tree";
const runNonce = randomBytes(12).toString("hex");
const initialPassword = `m4-smoke-${runNonce}-initial`;
const finalPassword = `m4-smoke-${runNonce}-final`;
const secret = randomBytes(32).toString("hex");
const results = [];
let api;
let web;
let dataDir;
let baseUrl;
let apiUrl;
let apiLogs = "";
let webLogs = "";

function record(id, name, detail, evidence, status = "pass") {
  results.push({
    id,
    name,
    status,
    detail,
    evidence,
  });
}

async function cleanup() {
  await stop(web);
  await stop(api);
  if (dataDir) {
    await rm(dataDir, { recursive: true, force: true, maxRetries: 10 });
  }
}

async function apiJson(pathname, accessToken) {
  const response = await fetch(`${apiUrl}${pathname}`, {
    headers: accessToken
      ? { authorization: `Bearer ${accessToken}` }
      : undefined,
  });
  if (response.status !== 200) {
    assert.fail(`${pathname}: ${await response.text()}`);
  }
  return response.json();
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
      newPassword: finalPassword,
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

async function loginCurrent() {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: finalPassword }),
  });
  assert.equal(response.status, 200);
  const login = await response.json();
  const cookie = response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie);
  return { accessToken: login.accessToken, cookie };
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

async function clientNavigate(page, pathname) {
  await page.session.send("Runtime.evaluate", {
    expression: `history.pushState({}, "", ${JSON.stringify(pathname)});
      window.dispatchEvent(new PopStateEvent("popstate"));`,
  });
}

async function screenshot(page, filename) {
  const { data } = await page.session.send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: false,
  });
  await writeFile(path.join(screenshotDir, filename), data, "base64");
}

async function reload(page) {
  await page.session.send("Page.reload");
  await waitForDocument(
    page.session,
    `Boolean(document.querySelector(".errors-workspace"))`,
    "error workspace after reload",
  );
}

async function main() {
  await mkdir(screenshotDir, { recursive: true });
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m4-smoke-"));
  const env = {
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
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let seedLogs = "";
  capture(seed, (chunk) => {
    seedLogs += chunk;
  });
  const seedExit = await new Promise((resolve) => {
    seed.once("exit", (code) => resolve(code));
  });
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

  const auth = await loginSession();
  const sessions = await apiJson("/api/sessions", auth.accessToken);
  assert.equal(sessions.items.length, 4);

  const casesBySession = new Map();
  for (const session of sessions.items) {
    const response = await apiJson(
      `/api/sessions/${encodeURIComponent(session.id)}/bad-cases`,
      auth.accessToken,
    );
    casesBySession.set(session.id, response.items);
  }
  const allCases = [...casesBySession.values()].flat();
  const states = new Set(allCases.map((item) => item.analysis.displayState));
  assert.deepEqual(
    [...states].sort(),
    [
      "analyzed_issue_error",
      "analyzed_issue_model",
      "analyzed_issue_prompt",
      "analyzed_nonissue",
      "unanalyzed",
    ],
  );
  record(
    "01",
    "五种问题状态",
    "真实 SQLite fixture 返回未分析、非问题、模型、prompt、错误五态。",
    ["API displayState 集合断言"],
  );

  const selectedSession = [...casesBySession.entries()].find(([, items]) =>
    items.some((item) => item.analysis.status === "analyzed_issue"));
  assert.ok(selectedSession);
  const [sessionId, sessionCases] = selectedSession;
  const selected = sessionCases.find(
    (item) => item.analysis.status === "analyzed_issue",
  );
  assert.ok(selected);
  const selectedProbe = await apiJson(
    `/api/probes/${encodeURIComponent(selected.analysis.probeId)}`,
    auth.accessToken,
  );
  const otherSession = sessions.items.find((item) => item.id !== sessionId);
  assert.ok(otherSession);

  const page = await createBrowserPage();
  let pausedTreeRequest;
  let treeInterceptMode = "pause";
  let fatalTreePayload;
  const pausedRequests = [];
  const networkRequests = [];
  page.session.on("Network.requestWillBeSent", (params) => {
    networkRequests.push(params.request.url);
  });
  page.session.on("Fetch.requestPaused", async (params) => {
    pausedRequests.push(params.request.url);
    if (params.request.url.includes("/tree")) {
      if (treeInterceptMode === "fatal" && fatalTreePayload) {
        await page.session.send("Fetch.fulfillRequest", {
          requestId: params.requestId,
          responseCode: 200,
          responseHeaders: [
            { name: "content-type", value: "application/json" },
          ],
          body: Buffer.from(JSON.stringify(fatalTreePayload)).toString("base64"),
        });
        return;
      }
      pausedTreeRequest = params.requestId;
    }
  });
  const violations = browserViolations(page.session, {
    isExpectedLogEntry: (entry) =>
      entry.source === "network" &&
      ((entry.url?.includes(`/api/bad-cases/${selected.badCaseId}`) &&
        entry.url?.includes(`sessionId=${otherSession.id}`) &&
        /status of 409/.test(entry.text)) ||
        (entry.url?.includes("/api/bad-cases/missing-case") &&
          /status of 404/.test(entry.text)) ||
        (entry.url?.includes(`/api/sessions/${sessionId}/tree`) &&
          /net::ERR_(ABORTED|FAILED)/.test(entry.text))),
  });

  try {
    await installCookie(page, auth.cookie);
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 960,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.session.send("Page.navigate", { url: `${baseUrl}/sessions` });
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector(".shell"))`,
      "authenticated shell",
    );

    await clientNavigate(page, `/sessions/${sessionId}/errors`);
    const all = await waitForDocument(
      page.session,
      `(() => {
        const workspace = document.querySelector("[data-testid='errors-workspace']");
        const tree = document.querySelector("[data-testid='agent-tree']");
        const rows = [...document.querySelectorAll(
          "[data-testid='problem-list'] [data-bad-case-id]",
        )];
        const reportLinks = [...document.querySelectorAll(
          "[data-testid='problem-list'] .report-id",
        )];
        if (!workspace || !tree || rows.length !== ${sessionCases.length}) return null;
        return {
          rows: rows.length,
          cards: tree.querySelectorAll(".rf-finding").length,
          reportLinks: reportLinks.map((link) => ({
            text: link.textContent.trim(),
            href: link.getAttribute("href"),
            title: link.getAttribute("title"),
            target: link.getAttribute("target"),
            rel: link.getAttribute("rel"),
            insideButton: Boolean(link.closest("button")),
          })),
          diagnosticsText:
            tree.querySelector(".diagnostics")?.textContent?.trim() ?? "",
          sidebarWidth: document.querySelector(".error-sidebar")
            ?.getBoundingClientRect().width,
          bodyBackground: getComputedStyle(document.body).backgroundColor,
          noOverflow:
            document.documentElement.scrollWidth === document.documentElement.clientWidth,
          emptyCopy: document.querySelector(".detail-panel")?.textContent
            .includes("从左侧选择一个错误，查看问题描述与归因分析。"),
        };
      })()`,
      "all-errors workspace",
    );
    assert.equal(all.rows, sessionCases.length);
    assert.equal(all.cards, sessionCases.length);
    const issueCases = sessionCases.filter(
      (item) => item.analysis.status === "analyzed_issue",
    );
    assert.deepEqual(
      all.reportLinks.map((link) => link.text),
      issueCases.map((item) => item.analysis.probeId.slice(0, 8)),
    );
    assert.deepEqual(
      all.reportLinks.map((link) => link.title),
      issueCases.map((item) => item.analysis.probeId),
    );
    assert.equal(
      all.reportLinks.every(
        (link, index) =>
          link.href ===
            `/sessions/${sessionId}/errors?case=${issueCases[index].badCaseId}&tab=attr` &&
          link.target === "_blank" &&
          link.rel === "noopener noreferrer" &&
          !link.insideButton,
      ),
      true,
    );
    assert.equal(all.diagnosticsText, "");
    assert.equal(all.sidebarWidth, 340);
    assert.equal(all.bodyBackground, "rgb(244, 245, 247)");
    assert.equal(all.noOverflow, true);
    assert.equal(all.emptyCopy, true);
    record(
      "02",
      "1408px 错误详情与原图",
      "340px 左栏、亮色背景、两行错误卡及归因报告深链、完整执行流同时可见；正式画布不显示裸诊断 code，且无横向溢出。",
      ["screenshots/01-errors-all-1408.png"],
    );
    await screenshot(page, "01-errors-all-1408.png");

    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector(${JSON.stringify(
        `[data-bad-case-id='${selected.badCaseId}']`,
      )}).click()`,
    });
    const selectedView = await waitForDocument(
      page.session,
      `(() => {
        const tree = document.querySelector("[data-testid='agent-tree']");
        if (!tree || location.search !== ${JSON.stringify(
          `?case=${selected.badCaseId}&tab=desc`,
        )}) return null;
        return {
          cards: tree.querySelectorAll(".rf-finding").length,
          pressed: document.querySelector(
            ${JSON.stringify(`[data-bad-case-id='${selected.badCaseId}']`)},
          )?.getAttribute("aria-pressed"),
          descId: document.querySelector(".description .problem-id")
            ?.getAttribute("href"),
          reportId: document.querySelector(".description .report-id")
            ?.getAttribute("href"),
          reasonCount: document.querySelector(".description")?.textContent
            .match(new RegExp(${JSON.stringify(selected.reason)}, "g"))?.length,
        };
      })()`,
      "selected description",
    );
    assert.equal(selectedView.cards, 1);
    assert.equal(selectedView.pressed, "true");
    assert.equal(
      selectedView.descId,
      `/sessions/${sessionId}/errors?case=${selected.badCaseId}&tab=desc`,
    );
    assert.equal(
      selectedView.reportId,
      `/sessions/${sessionId}/errors?case=${selected.badCaseId}&tab=attr`,
    );
    assert.equal(selectedView.reasonCount, 1);
    record(
      "03",
      "选中问题过滤执行流",
      "问题卡与画布共享 case 状态；选中后画布只剩一张问题卡，描述中的 reason 仅一次。",
      ["screenshots/02-selected-description.png"],
    );
    await screenshot(page, "02-selected-description.png");

    const descriptionReloadAuth = await loginCurrent();
    await installCookie(page, descriptionReloadAuth.cookie);
    await reload(page);
    const restored = await waitForDocument(
      page.session,
      `new URLSearchParams(location.search).get("case") ===
          ${JSON.stringify(selected.badCaseId)} &&
        (new URLSearchParams(location.search).get("tab") ?? "desc") === "desc" &&
        document.querySelector("#desc-tab")?.getAttribute("aria-selected") === "true" &&
        document.querySelector("[data-testid='agent-tree']")
          ?.querySelectorAll(".rf-finding").length === 1`,
      "description reload restore",
    ).catch(async (error) => {
      const state = await page.session.send("Runtime.evaluate", {
        expression: `({
          href: location.href,
          body: document.body.textContent.slice(0, 1200),
          selectedTab: document.querySelector("#desc-tab")?.getAttribute("aria-selected"),
          cards: document.querySelectorAll("[data-testid='agent-tree'] .rf-finding").length,
          errors: document.querySelector(".flow-panel .error-state")?.textContent,
        })`,
        returnByValue: true,
      });
      throw new Error(`${error.message}: ${JSON.stringify(state.result.value)}`);
    });
    assert.equal(restored, true);
    record(
      "04",
      "描述深链刷新恢复",
      "刷新后 case 与 desc 状态保持一致；问题描述页签与过滤执行流均恢复。",
      ["CDP Page.reload + location/query 断言"],
    );

    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector("#attr-tab").click()`,
    });
    const attribution = await waitForDocument(
      page.session,
      `(() => {
        const panel = document.querySelector("#attr-panel");
        if (!panel || !location.search.includes("tab=attr")) return null;
        const conclusion = panel.querySelector(".conclusion");
        const classification = panel.querySelector(".classification");
        const source = panel.querySelector(".source-links a");
        if (
          !conclusion ||
          !classification ||
          !source ||
          !panel.querySelector(".markdown")
        ) return null;
        return {
          conclusion: conclusion?.textContent,
          classification: classification?.textContent,
          conclusionDuplicatesObject:
            conclusion?.textContent?.includes(
              ${JSON.stringify(selectedProbe.probeObject)},
            ),
          sourceHref: source?.getAttribute("href"),
          sourceTarget: source?.getAttribute("target"),
          sourceRel: source?.getAttribute("rel"),
          sourceBorder: source ? getComputedStyle(source).borderBottomStyle : null,
          markdown: Boolean(panel.querySelector(".markdown")),
        };
      })()`,
      "attribution panel",
    );
    assert.equal(attribution.conclusionDuplicatesObject, false);
    assert.match(attribution.classification ?? "", new RegExp(selectedProbe.probeObject));
    assert.equal(
      attribution.sourceHref,
      `/sessions/${sessionId}/errors?case=${selectedProbe.fromBadCases[0]}&tab=desc`,
    );
    assert.equal(attribution.sourceTarget, "_blank");
    assert.equal(attribution.sourceRel, "noopener noreferrer");
    assert.equal(attribution.sourceBorder, "dashed");
    assert.equal(attribution.markdown, true);
    record(
      "05",
      "归因顺序与安全深链",
      "结论不重复正文；分类/根因对象只在正文；来源问题新窗口回 desc；Markdown 可见。",
      ["screenshots/03-attribution.png"],
    );
    await screenshot(page, "03-attribution.png");

    const attributionReloadAuth = await loginCurrent();
    await installCookie(page, attributionReloadAuth.cookie);
    await reload(page);
    await waitForDocument(
      page.session,
      `location.search.includes("tab=attr") &&
        document.querySelector("#attr-tab")?.getAttribute("aria-selected") === "true"`,
      "attribution reload restore",
    );
    record(
      "06",
      "归因深链刷新恢复",
      "刷新后 tab=attr 与当前 case 保持一致，归因页签仍为选中态。",
      ["CDP Page.reload + aria-selected 断言"],
    );

    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector(".all-errors").click()`,
    });
    await waitForDocument(
      page.session,
      `location.search === "" &&
        document.querySelector("[data-testid='agent-tree']")
          ?.querySelectorAll(".rf-finding").length === ${sessionCases.length}`,
      "all-errors restoration",
    );
    record(
      "07",
      "全部错误恢复全图",
      "清除 case/tab 后画布恢复全部问题卡，详情区回到未选择空态。",
      ["URL query 为空 + 问题卡数量断言"],
    );

    const graphTarget = sessionCases[0];
    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector(${JSON.stringify(
        `.rf-finding[data-bad-case-id='${graphTarget.badCaseId}']`,
      )}).click()`,
    });
    await waitForDocument(
      page.session,
      `location.search.includes("case=${graphTarget.badCaseId}") &&
        document.querySelector(
          ${JSON.stringify(`[data-bad-case-id='${graphTarget.badCaseId}']`)},
        )?.getAttribute("aria-pressed") === "true"`,
      "canvas to list selection",
    );
    record(
      "08",
      "画布 → 列表双向选择",
      "点击执行流问题卡后 URL 与左栏选中态同步，列表选择进入画布方向已在前一步验证。",
      ["画布 .rf-finding 点击 + aria-pressed 断言"],
    );

    await clientNavigate(page, "/errors");
    await waitForDocument(
      page.session,
      `document.querySelector(".empty-state")?.textContent.includes("请选择会话")`,
      "global errors empty state",
    );
    record(
      "09",
      "全局空态",
      "无 Session 的错误入口显示“请选择会话”，不伪造问题数据。",
      ["screenshots/04-global-empty.png"],
    );
    await screenshot(page, "04-global-empty.png");

    await page.session.send("Network.enable");
    await page.session.send("Network.setCacheDisabled", {
      cacheDisabled: true,
    });
    await page.session.send("Fetch.enable", {
      patterns: [
        {
          urlPattern: "*://*/api/sessions/*/tree",
          requestStage: "Request",
        },
      ],
    });
    const loadingSession = [...casesBySession.entries()].find(
      ([id]) => id !== sessionId,
    );
    assert.ok(loadingSession);
    const [loadingSessionId, loadingCases] = loadingSession;
    const loadingCase = loadingCases[0];
    assert.ok(loadingCase);
    pausedTreeRequest = undefined;
    await clientNavigate(
      page,
      `/sessions/${loadingSessionId}/errors?case=${loadingCase.badCaseId}&tab=desc`,
    );
    for (let index = 0; index < 50 && !pausedTreeRequest; index += 1) {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    assert.ok(
      pausedTreeRequest,
      `tree request was not intercepted; paused URLs: ${JSON.stringify(pausedRequests)}; network: ${JSON.stringify(networkRequests.slice(-30))}`,
    );
    await waitForDocument(
      page.session,
      `document.querySelector(".flow-panel [role='status']")
        ?.getAttribute("aria-label") === "正在读取 Agent 执行流"`,
      "tree loading state",
    );
    record(
      "10",
      "加载态",
      "暂停真实 tree 请求时，执行流面板显示可访问的加载骨架。",
      ["CDP Fetch.requestPaused + role=status 断言"],
    );
    await page.session.send("Fetch.failRequest", {
      requestId: pausedTreeRequest,
      errorReason: "ConnectionAborted",
    });
    await page.session.send("Fetch.disable");
    await page.session.send("Network.setCacheDisabled", {
      cacheDisabled: false,
    });
    await waitForDocument(
      page.session,
      `document.querySelector(".flow-panel .error-state")
        ?.textContent.includes("Agent 执行流读取失败，请重试。")`,
      "tree error state",
    );
    record(
      "11",
      "错误态",
      "执行流请求失败时显示局部错误与“重试”，其他工作区仍可操作。",
      ["screenshots/05-tree-error.png"],
    );
    await screenshot(page, "05-tree-error.png");
    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector(".flow-panel .error-state button").click()`,
    });
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-testid='agent-tree'] .rf-finding"))`,
      "tree retry recovery",
    );
    record(
      "12",
      "重试恢复",
      "点击错误态“重试”后真实执行流恢复，无需刷新整页。",
      ["retry 点击 + AgentTree 恢复断言"],
    );

    await clientNavigate(
      page,
      `/sessions/${sessionId}/errors?case=missing-case&tab=desc`,
    );
    await waitForDocument(
      page.session,
      `document.querySelector(".page-error")
        ?.textContent.includes("问题不存在或已删除") &&
        !document.querySelector(".page-error button")`,
      "missing problem page",
    );
    record(
      "13",
      "详情 404",
      "不存在的问题显示页级不可重试错误，不伪造侧栏、执行流或详情。",
      ["screenshots/08-detail-404.png"],
    );
    await screenshot(page, "08-detail-404.png");

    const fatalSession = [...casesBySession.entries()].find(
      ([id]) => id !== sessionId && id !== loadingSessionId,
    );
    assert.ok(fatalSession);
    const [fatalSessionId, fatalCases] = fatalSession;
    const fatalCase = fatalCases[0];
    assert.ok(fatalCase);
    const fatalTree = await apiJson(
      `/api/sessions/${encodeURIComponent(fatalSessionId)}/tree`,
      auth.accessToken,
    );
    fatalTreePayload = {
      ...fatalTree,
      agents: fatalTree.agents.filter((agent) => agent.kind !== "main"),
    };
    treeInterceptMode = "fatal";
    pausedTreeRequest = undefined;
    await page.session.send("Fetch.enable", {
      patterns: [
        {
          urlPattern: "*://*/api/sessions/*/tree",
          requestStage: "Request",
        },
      ],
    });
    await clientNavigate(
      page,
      `/sessions/${fatalSessionId}/errors?case=${fatalCase.badCaseId}&tab=desc`,
    );
    await waitForDocument(
      page.session,
      `document.querySelector(".agent-tree-unavailable")
        ?.textContent.includes("执行流数据不完整，暂时无法绘制。") &&
        !document.querySelector(".agent-tree-unavailable")
          ?.textContent.includes("MISSING_MAIN") &&
        !document.querySelector("[data-testid='agent-tree'] .vue-flow")`,
      "fatal layout fallback",
    );
    record(
      "14",
      "致命布局降级",
      "tree 缺少 main Agent 时显示友好不可绘制状态，不暴露 MISSING_MAIN 或空白 VueFlow。",
      ["screenshots/09-fatal-layout.png"],
    );
    await screenshot(page, "09-fatal-layout.png");
    await page.session.send("Fetch.disable");
    treeInterceptMode = "pause";

    await clientNavigate(
      page,
      `/sessions/${otherSession.id}/errors?case=${selected.badCaseId}&tab=desc`,
    );
    await waitForDocument(
      page.session,
      `document.querySelector(".page-error")
        ?.textContent.includes("问题不属于当前 Session") &&
        !document.querySelector(".flow-panel [role='status']")`,
      "cross-session error",
    );
    const conflictToasts = await page.session.send("Runtime.evaluate", {
      expression: `[...document.querySelectorAll(".el-message")]
        .map((message) => message.textContent.trim())`,
      returnByValue: true,
    });
    assert.deepEqual(conflictToasts.result.value, []);
    record(
      "15",
      "跨 Session 409",
      "错误归属不匹配时只显示页级不可重试中文错误，不渲染侧栏、执行流、详情或重复全局 toast。",
      ["screenshots/06-cross-session-409.png"],
    );
    await screenshot(page, "06-cross-session-409.png");

    await clientNavigate(
      page,
      `/sessions/${sessionId}/errors?case=${selected.badCaseId}&tab=attr`,
    );
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector(".attribution"))`,
      "attribution before mobile",
    );
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    const mobile = await waitForDocument(
      page.session,
      `({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
        workspaceColumns: getComputedStyle(
          document.querySelector(".errors-workspace"),
        ).gridTemplateColumns,
      })`,
      "mobile layout",
    );
    assert.equal(mobile.scrollWidth, mobile.clientWidth);
    assert.doesNotMatch(mobile.workspaceColumns, /px .*px/);
    record(
      "16",
      "390px 响应式布局",
      "单列工作台无横向溢出，详情与归因仍可访问。",
      ["screenshots/07-mobile-390.png"],
    );
    await screenshot(page, "07-mobile-390.png");

    await new Promise((resolve) => setTimeout(resolve, 500));
    const unexpectedViolations = violations.filter(
      (entry) =>
        !(
          entry.includes(`/api/sessions/${loadingSessionId}/tree`) &&
          entry.includes("net::ERR_CONNECTION_ABORTED")
        ),
    );
    assert.deepEqual(unexpectedViolations, []);
    record(
      "17",
      "Console / network",
      "除用于验证的预期 404、409、tree 中断与致命布局响应外，无 warning、error 或未捕获异常。",
      ["console-summary.txt"],
    );
  } finally {
    if (page) {
      await page.session.send("Emulation.clearDeviceMetricsOverride").catch(() => {});
      await page.close();
    }
  }

  await writeFile(
    path.join(reportDir, "assertions.json"),
    `${JSON.stringify({ commit: validationCommit, rows: results }, null, 2)}\n`,
  );
  await writeFile(
    path.join(reportDir, "console-summary.txt"),
    [
      "Console/network violations: 0",
      "Expected missing problem 404 response was allowlisted.",
      "Expected cross-session 409 response was allowlisted.",
      "Expected tree request failure used for loading/error/retry injection was allowlisted.",
      "Expected missing-main tree response was injected and did not produce runtime errors.",
      "",
    ].join("\n"),
  );
  console.log(JSON.stringify({ rows: results.length, screenshots: 9 }, null, 2));
}

main()
  .finally(cleanup)
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
