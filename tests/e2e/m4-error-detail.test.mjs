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
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const initialPassword = "m4-error-detail-initial-password";
const secret = "m4-error-detail-signing-secret-with-sufficient-length";
const ws = "/workspaces/ws-default";
let api;
let web;
let dataDir;
let baseUrl;
let apiUrl;
let apiLogs = "";
let webLogs = "";
let currentPassword = initialPassword;
let passwordRevision = 0;

async function cleanup() {
  await stop(web);
  await stop(api);
  if (dataDir) await rm(dataDir, { recursive: true, force: true });
}

async function loginSession() {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: currentPassword }),
  });
  assert.equal(response.status, 200);
  const login = await response.json();
  const initialCookie = response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(initialCookie);

  const replacement = `m4-error-detail-password-${++passwordRevision}`;
  const changed = await fetch(`${baseUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${login.accessToken}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      oldPassword: currentPassword,
      newPassword: replacement,
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
  currentPassword = replacement;
  return { accessToken: access.accessToken, cookie };
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

async function apiGet(pathname, accessToken) {
  const response = await fetch(`${apiUrl}${pathname}`, {
    headers: { authorization: `Bearer ${accessToken}` },
  });
  if (response.status !== 200) {
    assert.fail(`${pathname}: ${await response.text()}`);
  }
  return response.json();
}


async function defaultToTree(page) {
  await page.session.send("Page.addScriptToEvaluateOnNewDocument", {
    source: `try { localStorage.setItem("he:flow-mode", "tree"); } catch {}`,
  });
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m4-errors-e2e-"));
  const seedEnv = {
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
    env: seedEnv,
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
      ...seedEnv,
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
});

after(cleanup);


test("m4 error detail restores five states, folded attributions, tabs, unfiltered flow and ownership", async () => {
  const auth = await loginSession();
  const sessions = await apiGet("/api/sessions", auth.accessToken);
  assert.equal(sessions.items.length, 4);

  const casesBySession = new Map();
  for (const session of sessions.items) {
    const response = await apiGet(
      `/api/sessions/${encodeURIComponent(session.id)}/bad-cases`,
      auth.accessToken,
    );
    casesBySession.set(session.id, response.items);
  }

  const states = new Set(
    [...casesBySession.values()]
      .flat()
      .map((item) => item.analysis.displayState),
  );
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

  const selectedSession = [...casesBySession.entries()].find(([, items]) =>
    items.some((item) => item.analysis.status === "analyzed_issue"));
  assert.ok(selectedSession);
  const [sessionId, sessionCases] = selectedSession;
  const selected = sessionCases.find(
    (item) => item.analysis.status === "analyzed_issue",
  );
  assert.ok(selected);
  const selectedAttributions = await apiGet(
    `/api/workspaces/ws-default/bad-cases/${encodeURIComponent(selected.badCaseId)}/attributions?page=1&pageSize=2`,
    auth.accessToken,
  );
  assert.ok(selectedAttributions.total > 0);
  const selectedAttribution = selectedAttributions.items[0];
  assert.ok(selectedAttribution);
  const otherSession = sessions.items.find((item) => item.id !== sessionId);
  assert.ok(otherSession);

  const page = await createBrowserPage();
    await defaultToTree(page);
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: (entry) =>
        entry.source === "network" &&
        entry.url?.includes(`/bad-cases/${selected.badCaseId}`) &&
        /status of (404|409)/.test(entry.text),
    });
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
    await waitForDocument(
      page.session,
      `/^\\/workspaces\\/ws-default\\/sessions\\/[0-9a-f-]{36}$/.test(location.pathname)`,
      "session auto-selection settled",
    );
    await clientNavigate(page, `${ws}/sessions/${sessionId}/errors`);

    const all = await waitForDocument(
      page.session,
      `(() => {
        const workspace = document.querySelector("[data-testid='errors-workspace']");
        const groups = [...document.querySelectorAll("[data-testid='case-group']")];
        const ids = [...document.querySelectorAll("[data-testid='case-id']")];
        const titles = [...document.querySelectorAll("[data-testid='case-title-link']")];
        const tree = document.querySelector("[data-testid='agent-tree']");
        if (
          !workspace ||
          !tree ||
          groups.length !== ${sessionCases.length} ||
          ids.length !== ${sessionCases.length}
        ) return null;
        const heading = document.querySelector(".error-heading h1");
        const main = document.querySelector(".error-main");
        const sidebar = document.querySelector(".error-sidebar");
        const empty = document.querySelector(".err-empty");
        return {
          groups: groups.length,
          ids: ids.map((link) => ({
            text: link.textContent,
            href: link.getAttribute("href"),
            title: link.getAttribute("title"),
            target: link.getAttribute("target"),
            rel: link.getAttribute("rel"),
            insideButton: Boolean(link.closest("button")),
          })),
          titles: titles.map((link) => ({
            href: link.getAttribute("href"),
            title: link.getAttribute("title"),
          })),
          findingCards: tree.querySelectorAll(".rf-finding").length,
          diagnosticsText:
            tree.querySelector(".diagnostics")?.textContent?.trim() ?? "",
          detailEmpty: document
            .querySelector(".detail-panel")
            ?.textContent.includes("从左侧选择一个 bad case，查看问题描述与归因分析。"),
          title: document.querySelector(".error-heading h1")?.textContent,
          sidebarRootId: sidebar
            ?.querySelector("[data-testid='error-root-session-id']")
            ?.textContent.trim(),
          metaRootId: document
            .querySelector("[data-testid='error-meta-root-session-id']")
            ?.textContent.trim(),
          meta: document.querySelector(".error-meta")?.textContent,
          tabs: document.querySelectorAll(".detail-tabs [role='tab']").length,
          body: getComputedStyle(document.body).backgroundColor,
          sidebarWidth: sidebar?.getBoundingClientRect().width,
          headingFontSize: heading ? getComputedStyle(heading).fontSize : null,
          mainPadding: main ? getComputedStyle(main).padding : null,
          emptyMinHeight: empty ? getComputedStyle(empty).minHeight : null,
        };
      })()`,
      "all errors",
    ).catch(async (error) => {
      const evaluated = await page.session.send("Runtime.evaluate", {
        expression: `({
          href: location.href,
          text: document.body.textContent.slice(0, 2000),
          groups: document.querySelectorAll("[data-testid='case-group']").length,
          workspaces: document.querySelectorAll("[data-testid='errors-workspace']").length,
          trees: document.querySelectorAll("[data-testid='agent-tree']").length
        })`,
        returnByValue: true,
      });
      throw new Error(
        `${error.message}: ${JSON.stringify(evaluated.result.value)}\n\nAPI:\n${apiLogs}\n\nVite:\n${webLogs}`,
      );
    });
    assert.equal(all.groups, sessionCases.length);
    assert.deepEqual(
      all.ids.map((link) => link.text),
      sessionCases.map((item) => item.badCaseId.slice(0, 8)),
    );
    assert.deepEqual(
      all.ids.map((link) => link.title),
      sessionCases.map((item) => item.badCaseId),
    );
    assert.equal(
      all.ids.every(
        (link) =>
          link.href ===
            `${ws}/sessions/${sessionId}/errors?case=${link.title}&tab=desc` &&
          link.target === "_blank" &&
          link.rel === "noopener noreferrer" &&
          !link.insideButton,
      ),
      true,
    );
    assert.equal(
      all.titles.every(
        (link, index) =>
          link.href ===
            `${ws}/sessions/${sessionId}/errors?case=${sessionCases[index].badCaseId}&tab=desc` &&
          link.title === sessionCases[index].badCaseId,
      ),
      true,
    );
    assert.equal(all.findingCards, sessionCases.length);
    assert.equal(all.diagnosticsText, "");
    assert.equal(all.detailEmpty, true);
    assert.equal(all.title, "错误详情");
    assert.equal(all.sidebarRootId, `根会话 ID · ${sessionId}`);
    assert.equal(all.metaRootId, `根会话 ID · ${sessionId}`);
    assert.match(all.meta, new RegExp(`${sessionCases.length} 个 bad case`));
    assert.equal(all.tabs, 2);
    assert.equal(all.body, "rgb(244, 245, 247)");
    assert.equal(all.sidebarWidth, 340);
    assert.equal(all.headingFontSize, "17px");
    assert.equal(all.mainPadding, "16px 20px 24px");
    assert.equal(all.emptyMinHeight, "260px");

    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector(${JSON.stringify(
        `[data-bad-case-id='${selected.badCaseId}'] [data-testid='case-title-link']`,
      )}).click()`,
    });
    const selectedView = await waitForDocument(
      page.session,
      `(() => {
        const tree = document.querySelector("[data-testid='agent-tree']");
        if (!tree || location.search !== ${JSON.stringify(
          `?case=${selected.badCaseId}&tab=desc`,
        )}) return null;
        const group = document.querySelector(
          ${JSON.stringify(`[data-bad-case-id='${selected.badCaseId}']`)},
        );
        const items = group?.querySelectorAll("[data-testid='attribution-item']").length ?? 0;
        if (items !== ${selected.attributionCount}) return null;
        return {
          findingCards: tree.querySelectorAll(".rf-finding").length,
          text: document.body.textContent,
          title: document.querySelector(".description .problem-title")?.textContent,
          detail: document.querySelector(".description [data-testid='problem-detail']")?.textContent,
          summary: document.querySelector("[data-testid='problem-attribution-summary']")?.textContent,
          expanded: group?.querySelector("[data-testid='case-toggle']")?.getAttribute("aria-expanded"),
          items,
          selected: group?.classList.contains("active"),
        };
      })()`,
      "selected problem",
    );
    assert.equal(selectedView.findingCards, 1);
    assert.equal(selectedView.selected, true);
    assert.equal(selectedView.expanded, "true");
    assert.equal(selectedView.items, selected.attributionCount);
    assert.equal(selectedView.title, selected.title);
    assert.equal(selectedView.detail, selected.reason);
    assert.match(selectedView.summary ?? "", /已生成 \d+ 条归因/);
    assert.doesNotMatch(selectedView.text, /问题 ID/);
    assert.equal(
      selectedView.text.includes("从左侧选择一个 bad case"),
      false,
    );

    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector("#attr-tab").click()`,
    });
    const attribution = await waitForDocument(
      page.session,
      `(() => {
        const report = document.querySelector("[data-testid='attribution-report']");
        if (!report || !location.search.includes("tab=attr")) return null;
        const conclusion = report.querySelector(".conclusion");
        return {
          text: report.textContent,
          conclusionStrong: conclusion?.querySelector("strong")?.textContent,
          conclusionChips: [...conclusion.querySelectorAll(".state-chip")]
            .map((chip) => chip.textContent),
          html: report.querySelector(".markdown")?.innerHTML,
          deepLink: (() => {
            const link = report.querySelector("[data-testid='attribution-deep-link']");
            return link ? {
              text: link.textContent,
              href: link.getAttribute("href"),
              title: link.getAttribute("title"),
              target: link.getAttribute("target"),
              rel: link.getAttribute("rel"),
            } : null;
          })(),
          position: report.querySelector("[data-testid='attribution-position']")?.textContent,
        };
      })()`,
      "attribution tab",
    );
    assert.equal(attribution.conclusionStrong, "可归因到本对象");
    assert.deepEqual(attribution.conclusionChips, [
      {
        error: "错误",
        model: "模型问题",
        prompt: "prompt缺失某些提示词",
      }[selectedAttribution.category],
    ]);
    assert.match(attribution.text, /归因结论说明/);
    assert.match(attribution.text, /推导过程/);
    assert.match(attribution.text, /结论边界/);
    assert.match(attribution.html ?? "", /<p>/);
    assert.equal(attribution.position, undefined);
    assert.deepEqual(attribution.deepLink, {
      text: selectedAttribution.attributionId.slice(0, 8),
      href: `${ws}/sessions/${sessionId}/errors?case=${selected.badCaseId}&tab=attr&at=${selectedAttribution.attributionId}`,
      title: selectedAttribution.attributionId,
      target: "_blank",
      rel: "noopener noreferrer",
    });

    const unanalyzedSession = [...casesBySession.entries()].find(([, items]) =>
      items.some((item) => item.analysis.status === "unanalyzed"));
    assert.ok(unanalyzedSession);
    const [unanalyzedSessionId, unanalyzedCases] = unanalyzedSession;
    const unanalyzed = unanalyzedCases.find(
      (item) => item.analysis.status === "unanalyzed",
    );
    assert.ok(unanalyzed);
    await clientNavigate(
      page,
      `${ws}/sessions/${unanalyzedSessionId}/errors?case=${unanalyzed.badCaseId}&tab=attr`,
    );
    const unanalyzedView = await waitForDocument(
      page.session,
      `(() => {
        const empty = document.querySelector("[data-testid='attribution-empty']");
        if (!empty) return null;
        return {
          text: empty.textContent,
          start: Boolean(document.querySelector("[data-testid='start-evolution-from-case']")),
          groupStart: Boolean(document.querySelector("[data-testid='case-start-evolution']")),
        };
      })()`,
      "unanalyzed presentation",
    );
    assert.match(unanalyzedView.text, /尚未归因/);
    assert.match(unanalyzedView.text, /该 bad case 还没有被任何自进化运行归因/);
    assert.doesNotMatch(unanalyzedView.text, /非该对象问题/);
    assert.equal(unanalyzedView.start, true);
    assert.equal(unanalyzedView.groupStart, true);

    await clientNavigate(
      page,
      `${ws}/sessions/${sessionId}/errors?case=${selected.badCaseId}&tab=attr&at=${selectedAttribution.attributionId}`,
    );
    await waitForDocument(
      page.session,
      `location.search.includes("tab=attr") &&
        Boolean(document.querySelector("[data-testid='attribution-report']"))`,
      "selected attribution before reload",
    );

    const reloadAuth = await loginSession();
    await installCookie(page, reloadAuth.cookie);
    await page.session.send("Page.reload");
    const reloaded = await waitForDocument(
      page.session,
      `(() => {
        if (location.pathname !== "${ws}/sessions/${sessionId}/errors") return null;
        if (!location.search.includes("case=${selected.badCaseId}")) return null;
        if (!location.search.includes("at=${selectedAttribution.attributionId}")) return null;
        if (document.querySelector("#attr-tab")?.getAttribute("aria-selected") !== "true") return null;
        const report = document.querySelector("[data-testid='attribution-report']");
        return report ? report.textContent : null;
      })()`,
      "reloaded error detail",
    );
    assert.match(reloaded, /可归因到本对象/);

    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-testid='all-bad-cases']"))`,
      "all bad cases control",
    );
    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector("[data-testid='all-bad-cases']").click()`,
    });
    await waitForDocument(
      page.session,
      `location.search === "" &&
        document.querySelector("[data-testid='agent-tree']")
          ?.querySelectorAll(".rf-finding").length === ${sessionCases.length}`,
      "all errors restored",
    ).catch(async (error) => {
      const evaluated = await page.session.send("Runtime.evaluate", {
        expression: `({
          href: location.href,
          groups: document.querySelectorAll("[data-testid='case-group']").length,
          cards: document.querySelectorAll("[data-testid='agent-tree'] .rf-finding").length,
          text: document.body.textContent.slice(0, 1200),
        })`,
        returnByValue: true,
      });
      throw new Error(
        `${error.message}: ${JSON.stringify(evaluated.result.value)}`,
      );
    });

    await clientNavigate(
      page,
      `${ws}/sessions/${otherSession.id}/errors?case=${selected.badCaseId}&tab=desc`,
    );
    await waitForDocument(
      page.session,
      `document.body.textContent.includes("问题不属于当前 Session")`,
      "cross-session mismatch",
    );
    const conflictPresentation = await page.session.send("Runtime.evaluate", {
      expression: `[...document.querySelectorAll(".el-message")]
        .map((message) => message.textContent.trim())`,
      returnByValue: true,
    });
    assert.deepEqual(conflictPresentation.result.value, []);

    await clientNavigate(
      page,
      `${ws}/sessions/${sessionId}/errors?case=${selected.badCaseId}&tab=attr&at=${selectedAttribution.attributionId}`,
    );
    await waitForDocument(
      page.session,
      `location.search.includes("tab=attr") && document.querySelector("[data-testid='attribution-report']")`,
      "narrow error detail",
    );
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    const mobile = await waitForDocument(
      page.session,
      `(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
        hasSidebar: Boolean(document.querySelector(".error-sidebar")),
        hasDetail: Boolean(document.querySelector(".detail-panel")),
      }))()`,
      "mobile error detail",
    );
    assert.equal(mobile.scrollWidth, mobile.clientWidth);
    assert.equal(mobile.hasSidebar, true);
    assert.equal(mobile.hasDetail, true);
    assert.deepEqual(violations, [], violations.join("\n"));
  } finally {
    await page.close();
  }
});
