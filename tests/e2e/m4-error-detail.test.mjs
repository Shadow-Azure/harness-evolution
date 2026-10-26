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

test("m4 error detail restores five states, tabs, filtered flow and ownership", async () => {
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
  const selectedProbe = await apiGet(
    `/api/probes/${encodeURIComponent(selected.analysis.probeId)}`,
    auth.accessToken,
  );
  const otherSession = sessions.items.find((item) => item.id !== sessionId);
  assert.ok(otherSession);

  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session, {
      isExpectedLogEntry: (entry) =>
        entry.source === "network" &&
        entry.url?.includes(`/api/bad-cases/${selected.badCaseId}`) &&
        entry.url?.includes(`sessionId=${otherSession.id}`) &&
        /status of 409/.test(entry.text),
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
    await clientNavigate(page, `/sessions/${sessionId}/errors`);

    const all = await waitForDocument(
      page.session,
      `(() => {
        const workspace = document.querySelector("[data-testid='errors-workspace']");
        const rows = [...document.querySelectorAll(
          "[data-testid='problem-list'] [data-bad-case-id]",
        )];
        const idLinks = [...document.querySelectorAll(
          "[data-testid='problem-list'] .problem-id",
        )];
        const tree = document.querySelector("[data-testid='agent-tree']");
        if (
          !workspace ||
          !tree ||
          rows.length !== ${sessionCases.length} ||
          idLinks.length !== ${sessionCases.length}
        ) return null;
        const heading = document.querySelector(".error-heading h1");
        const main = document.querySelector(".error-main");
        const sidebar = document.querySelector(".error-sidebar");
        const detail = document.querySelector(".detail-panel");
        const empty = document.querySelector(".err-empty");
        return {
          rows: rows.length,
          idLinks: idLinks.map((link) => ({
            text: link.textContent,
            href: link.getAttribute("href"),
            title: link.getAttribute("title"),
            target: link.getAttribute("target"),
            rel: link.getAttribute("rel"),
            insideButton: Boolean(link.closest("button")),
          })),
          findingCards: tree.querySelectorAll(".rf-finding").length,
          detailEmpty: document
            .querySelector(".detail-panel")
            ?.textContent.includes("从左侧选择一个错误，查看问题描述与归因分析。"),
          title: document.querySelector(".error-heading h1")?.textContent,
          tabs: document.querySelectorAll(".detail-tabs [role='tab']").length,
          innerProblemHeader: Boolean(document.querySelector(".problem-list-head")),
          body: getComputedStyle(document.body).backgroundColor,
          sidebarWidth: sidebar?.getBoundingClientRect().width,
          headingFontSize: heading ? getComputedStyle(heading).fontSize : null,
          headingMarginTop: heading ? getComputedStyle(heading).marginTop : null,
          mainPadding: main ? getComputedStyle(main).padding : null,
          detailMarginTop: detail ? getComputedStyle(detail).marginTop : null,
          emptyMinHeight: empty ? getComputedStyle(empty).minHeight : null,
        };
      })()`,
      "all errors",
    ).catch(async (error) => {
      const evaluated = await page.session.send("Runtime.evaluate", {
        expression: `({
          href: location.href,
          text: document.body.textContent.slice(0, 2000),
          rows: document.querySelectorAll("[data-bad-case-id]").length,
          workspaces: document.querySelectorAll("[data-testid='errors-workspace']").length,
          trees: document.querySelectorAll("[data-testid='agent-tree']").length
        })`,
        returnByValue: true,
      });
      throw new Error(
        `${error.message}: ${JSON.stringify(evaluated.result.value)}\n\nAPI:\n${apiLogs}\n\nVite:\n${webLogs}`,
      );
    });
    assert.equal(all.rows, sessionCases.length);
    assert.deepEqual(
      all.idLinks.map((link) => link.text),
      sessionCases.map((item) => item.badCaseId.slice(0, 8)),
    );
    assert.deepEqual(
      all.idLinks.map((link) => link.title),
      sessionCases.map((item) => item.badCaseId),
    );
    assert.equal(
      all.idLinks.every(
        (link) =>
          link.href ===
            `/sessions/${sessionId}/errors?case=${link.title}&tab=desc` &&
          link.target === "_blank" &&
          link.rel === "noopener noreferrer" &&
          !link.insideButton,
      ),
      true,
    );
    assert.equal(all.findingCards, sessionCases.length);
    assert.equal(all.detailEmpty, true);
    assert.equal(all.title, "错误详情");
    assert.equal(all.tabs, 2);
    assert.equal(all.innerProblemHeader, false);
    assert.equal(all.body, "rgb(244, 245, 247)");
    assert.equal(all.sidebarWidth, 340);
    assert.equal(all.headingFontSize, "17px");
    assert.equal(all.headingMarginTop, "0px");
    assert.equal(all.mainPadding, "16px 20px 24px");
    assert.equal(all.detailMarginTop, "14px");
    assert.equal(all.emptyMinHeight, "260px");

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
          findingCards: tree.querySelectorAll(".rf-finding").length,
          text: document.body.textContent,
          detailId: (() => {
            const link = document.querySelector(".description .problem-id");
            const style = link ? getComputedStyle(link) : null;
            return link ? {
              text: link.textContent,
              href: link.getAttribute("href"),
              title: link.getAttribute("title"),
              target: link.getAttribute("target"),
              rel: link.getAttribute("rel"),
              textDecoration: style?.textDecorationLine,
              borderStyle: style?.borderBottomStyle,
              borderWidth: style?.borderBottomWidth,
            } : null;
          })(),
          reportLink: (() => {
            const link = document.querySelector(".description .report-id");
            const style = link ? getComputedStyle(link) : null;
            return link ? {
              text: link.textContent,
              href: link.getAttribute("href"),
              title: link.getAttribute("title"),
              target: link.getAttribute("target"),
              rel: link.getAttribute("rel"),
              textDecoration: style?.textDecorationLine,
              borderStyle: style?.borderBottomStyle,
              borderWidth: style?.borderBottomWidth,
            } : null;
          })(),
          selected: document.querySelector(
            ${JSON.stringify(`[data-bad-case-id='${selected.badCaseId}']`)},
          )?.getAttribute("aria-pressed"),
        };
      })()`,
      "selected problem",
    );
    assert.equal(selectedView.findingCards, 1);
    assert.equal(selectedView.selected, "true");
    assert.match(selectedView.text, /问题 ID/);
    assert.deepEqual(selectedView.detailId, {
      text: selected.badCaseId.slice(0, 8),
      href: `/sessions/${sessionId}/errors?case=${selected.badCaseId}&tab=desc`,
      title: selected.badCaseId,
      target: "_blank",
      rel: "noopener noreferrer",
      textDecoration: "none",
      borderStyle: "dashed",
      borderWidth: "1px",
    });
    assert.deepEqual(selectedView.reportLink, {
      text: selected.analysis.probeId.slice(0, 8),
      href: `/sessions/${sessionId}/errors?case=${selected.badCaseId}&tab=attr`,
      title: selected.analysis.probeId,
      target: "_blank",
      rel: "noopener noreferrer",
      textDecoration: "none",
      borderStyle: "dashed",
      borderWidth: "1px",
    });

    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector("#attr-tab").click()`,
    });
    const attribution = await waitForDocument(
      page.session,
      `(() => {
        const attribution = document.querySelector(".attribution");
        if (!attribution || !location.search.includes("tab=attr")) return null;
        return {
          text: attribution.textContent,
          conclusion: attribution.querySelector(".conclusion")?.textContent,
          classification: attribution.querySelector(".classification")?.textContent,
          html: attribution.querySelector(".markdown")?.innerHTML,
          sourceLinks: [...attribution.querySelectorAll(".source-links a")].map(
            (link) => ({
              text: link.textContent,
              href: link.getAttribute("href"),
              title: link.getAttribute("title"),
              target: link.getAttribute("target"),
              rel: link.getAttribute("rel"),
            }),
          ),
        };
      })()`,
      "attribution tab",
    );
    assert.match(attribution.text, /分析出的问题描述/);
    assert.match(attribution.text, /分析推导过程/);
    assert.match(attribution.html ?? "", /<p>/);
    assert.equal(
      attribution.conclusion?.includes(selectedProbe.probeObject),
      false,
    );
    assert.equal(
      attribution.conclusion?.includes(selectedProbe.probeDescription),
      false,
    );
    assert.equal(
      attribution.classification?.includes(selectedProbe.probeObject),
      true,
    );
    assert.equal(
      attribution.sourceLinks.length,
      selectedProbe.fromBadCases.length,
    );
    assert.equal(
      attribution.sourceLinks.every(
        (link) =>
          link.text === link.title.slice(0, 8) &&
          link.href ===
            `/sessions/${sessionId}/errors?case=${link.title}&tab=desc` &&
          link.target === "_blank" &&
          link.rel === "noopener noreferrer",
      ),
      true,
    );

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
      `/sessions/${unanalyzedSessionId}/errors?case=${unanalyzed.badCaseId}&tab=attr`,
    );
    const unanalyzedView = await waitForDocument(
      page.session,
      `(() => {
        const note = document.querySelector(".unanalyzed-note");
        if (!note) return null;
        const style = getComputedStyle(note);
        return {
          text: note.textContent.trim(),
          borderTopStyle: style.borderTopStyle,
          borderTopWidth: style.borderTopWidth,
          backgroundColor: style.backgroundColor,
          padding: style.padding,
          textAlign: style.textAlign,
          fontSize: style.fontSize,
        };
      })()`,
      "unanalyzed presentation",
    );
    assert.deepEqual(unanalyzedView, {
      text: "该错误还没有归因分析，尚不能判断是否为问题。",
      borderTopStyle: "none",
      borderTopWidth: "0px",
      backgroundColor: "rgba(0, 0, 0, 0)",
      padding: "28px 4px",
      textAlign: "center",
      fontSize: "12px",
    });

    const reloadAuth = await loginSession();
    await installCookie(page, reloadAuth.cookie);
    await page.session.send("Page.reload");
    await waitForDocument(
      page.session,
      `location.pathname === "/sessions/${sessionId}/errors" &&
        location.search.includes("case=${selected.badCaseId}") &&
        location.search.includes("tab=attr") &&
        document.querySelector("#attr-tab")?.getAttribute("aria-selected") === "true"`,
      "reloaded error detail",
    );

    await waitForDocument(
      page.session,
      `Boolean(document.querySelector(".all-errors"))`,
      "all-errors control",
    );
    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector(".all-errors").click()`,
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
          rows: document.querySelectorAll("[data-testid='problem-list'] [data-bad-case-id]").length,
          cards: document.querySelectorAll("[data-testid='agent-tree'] .rf-finding").length,
          text: document.body.textContent.slice(0, 1200),
          button: (() => {
            const button = document.querySelector(".all-errors");
            return button ? {
              outerHTML: button.outerHTML,
              disabled: button.disabled,
            } : null;
          })()
        })`,
        returnByValue: true,
      });
      throw new Error(
        `${error.message}: ${JSON.stringify(evaluated.result.value)}`,
      );
    });

    await clientNavigate(
      page,
      `/sessions/${otherSession.id}/errors?case=${selected.badCaseId}&tab=desc`,
    );
    await waitForDocument(
      page.session,
      `document.body.textContent.includes("问题不属于当前 Session")`,
      "cross-session mismatch",
    );

    await clientNavigate(
      page,
      `/sessions/${sessionId}/errors?case=${selected.badCaseId}&tab=attr`,
    );
    await waitForDocument(
      page.session,
      `location.search.includes("tab=attr") && document.querySelector(".attribution")`,
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
