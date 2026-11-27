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
const python = path.join(
  apiDir,
  ".venv",
  process.platform === "win32" ? "Scripts" : "bin",
  process.platform === "win32" ? "python.exe" : "python",
);
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const initialPassword = "m11-02-initial-password";
const secret = "m11-02-signing-secret-with-sufficient-length";
const ws = "/workspaces/ws-default";
const sessionId = "10000000-0000-4000-8000-000000000001";
const caseId = "badcase-synthetic-0001";
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

  const replacement = `m11-02-password-${++passwordRevision}`;
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

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m11-02-e2e-"));
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
  const seedExit = await new Promise((resolve) => {
    seed.once("exit", (code) => resolve(code));
  });
  assert.equal(seedExit, 0, seedLogs);

  const attributeSeed = spawn(
    python,
    [
      path.join(root, "tests/e2e/support/m11_02_attribution_seed.py"),
      "--data-dir",
      dataDir,
      "--case-id",
      caseId,
      "--session-id",
      sessionId,
    ],
    {
      cwd: root,
      env,
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  let attributeLogs = "";
  capture(attributeSeed, (chunk) => {
    attributeLogs += chunk;
  });
  const attributeExit = await new Promise((resolve) => {
    attributeSeed.once("exit", (code) => resolve(code));
  });
  assert.equal(attributeExit, 0, attributeLogs);

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
});

after(cleanup);

test("m11-02 multi-attribution error detail folds groups, pages by two and restores the at deep link", async () => {
  const auth = await loginSession();
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session);
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

    await clientNavigate(
      page,
      `${ws}/sessions/${sessionId}/errors?case=${caseId}&tab=desc`,
    );
    const folded = await waitForDocument(
      page.session,
      `(() => {
        const group = document.querySelector(${JSON.stringify(
          `[data-bad-case-id='${caseId}']`,
        )});
        if (!group) return null;
        const items = [...group.querySelectorAll("[data-testid='attribution-item']")];
        if (items.length !== 2) return null;
        return {
          count: group.querySelector(".case-count")?.textContent,
          items: items.map((item) => ({
            id: item.getAttribute("data-attribution-id"),
            text: item.textContent,
            href: item.querySelector(".attr-link")?.getAttribute("href"),
          })),
          pager: group.querySelector(".attr-pager")?.textContent?.replace(/\\s+/g, " ").trim(),
          filter: document.querySelector(".sidebar-filter")?.textContent,
          header: document.querySelector(".error-meta")?.textContent,
          tab: document.querySelector("#attr-tab")?.textContent,
        };
      })()`,
      "folded attribution page one",
    );
    assert.equal(folded.count, "4");
    assert.deepEqual(
      folded.items.map((item) => item.id),
      ["probe-m11-02-0003", "probe-m11-02-0002"],
    );
    assert.match(folded.items[0].text, /project-knowledge/);
    assert.match(folded.items[0].text, /可归因/);
    assert.match(folded.items[1].text, /非该对象问题/);
    assert.equal(
      folded.items[0].href,
      `${ws}/sessions/${sessionId}/errors?case=${caseId}&tab=attr&at=probe-m11-02-0003`,
    );
    assert.match(folded.pager, /1 \/ 2/);
    assert.match(folded.filter, /有归因 2/);
    assert.match(folded.filter, /待归因 0/);
    assert.match(folded.header, /2 个 bad case/);
    assert.match(folded.header, /2 个已归因/);
    assert.equal(folded.tab, "归因分析 (4)");

    await evaluate(
      page,
      `document.querySelector(${JSON.stringify(
        `[data-bad-case-id='${caseId}'] [data-testid='attribution-page-next']`,
      )}).click()`,
    );
    const pageTwo = await waitForDocument(
      page.session,
      `(() => {
        const group = document.querySelector(${JSON.stringify(
          `[data-bad-case-id='${caseId}']`,
        )});
        const items = [...group.querySelectorAll("[data-testid='attribution-item']")];
        if (items.length !== 2 || !group.textContent.includes("checklist-skill")) return null;
        return {
          items: items.map((item) => item.getAttribute("data-attribution-id")),
          pager: group.querySelector(".attr-pager")?.textContent?.replace(/\\s+/g, " ").trim(),
        };
      })()`,
      "folded attribution page two",
    );
    assert.deepEqual(pageTwo.items, [
      "probe-m11-02-0001",
      "probe-synthetic-0001",
    ]);
    assert.match(pageTwo.pager, /2 \/ 2/);

    await evaluate(
      page,
      `document.querySelector(${JSON.stringify(
        `[data-attribution-id='probe-m11-02-0001']`,
      )}).querySelector(".attr-link").click()`,
    );
    const selected = await waitForDocument(
      page.session,
      `(() => {
        const report = document.querySelector("[data-testid='attribution-report']");
        if (!report || !location.search.includes("at=probe-m11-02-0001")) return null;
        return {
          position: report.querySelector("[data-testid='attribution-position']")?.textContent,
          text: report.textContent,
          category: report.querySelector(".conclusion .state-chip")?.textContent,
          active: document.querySelector(
            ${JSON.stringify(`[data-attribution-id='probe-m11-02-0001']`)},
          )?.classList.contains("active"),
        };
      })()`,
      "selected checklist attribution",
    );
    assert.equal(selected.position, "3 / 4");
    assert.match(selected.text, /checklist-skill/);
    assert.match(selected.text, /可归因到本对象/);
    assert.equal(selected.category, "流程");
    assert.match(selected.text, /归因来源/);
    assert.equal(selected.active, true);

    await clientNavigate(
      page,
      `${ws}/sessions/${sessionId}/errors?case=${caseId}&tab=attr&at=probe-m11-02-0003`,
    );
    await waitForDocument(
      page.session,
      `document.querySelector("[data-testid='attribution-report'] .conclusion .state-chip")?.textContent === "上下文"`,
      "context category from the knowledge attribution",
    );

    await clientNavigate(
      page,
      `${ws}/sessions/${sessionId}/errors?case=${caseId}&tab=attr&at=probe-m11-02-0002`,
    );
    const nonTarget = await waitForDocument(
      page.session,
      `(() => {
        const report = document.querySelector("[data-testid='attribution-report']");
        if (!report || !report.textContent.includes("非该对象问题")) return null;
        return {
          position: report.querySelector("[data-testid='attribution-position']")?.textContent,
          text: report.textContent,
          chips: report.querySelectorAll(".conclusion .state-chip").length,
        };
      })()`,
      "non-target attribution deep link",
    );
    assert.equal(nonTarget.position, "2 / 4");
    assert.match(nonTarget.text, /review-agent/);
    assert.equal(nonTarget.chips, 0);
    assert.doesNotMatch(nonTarget.text, /尚未归因/);

    await evaluate(
      page,
      `document.querySelector("[data-testid='attribution-next']").click()`,
    );
    const moved = await waitForDocument(
      page.session,
      `location.search.includes("at=probe-m11-02-0001") &&
        document.querySelector("[data-testid='attribution-position']")?.textContent === "3 / 4"`,
      "next attribution",
    );
    assert.equal(moved, true);

    await clientNavigate(
      page,
      `${ws}/sessions/${sessionId}/errors?case=${caseId}&tab=desc`,
    );
    await waitForDocument(
      page.session,
      `Boolean(document.querySelector("[data-testid='problem-attribution-summary']"))`,
      "problem summary",
    );
    const summary = await evaluate(
      page,
      `document.querySelector("[data-testid='problem-attribution-summary']").textContent`,
    );
    assert.match(summary, /已生成 4 条归因/);
    assert.match(summary, /3 可归因/);
    assert.match(summary, /1 非该对象/);

    await clientNavigate(
      page,
      `${ws}/sessions/10000000-0000-4000-8000-000000000004/errors?case=badcase-synthetic-0004&tab=attr`,
    );
    const empty = await waitForDocument(
      page.session,
      `(() => {
        const node = document.querySelector("[data-testid='attribution-empty']");
        if (!node) return null;
        return {
          text: node.textContent,
          cta: Boolean(document.querySelector("[data-testid='start-evolution-from-case']")),
          groupCta: Boolean(document.querySelector("[data-testid='case-start-evolution']")),
        };
      })()`,
      "empty attribution state",
    );
    assert.match(empty.text, /尚未归因/);
    assert.match(empty.text, /该 bad case 还没有被任何自进化运行归因/);
    assert.equal(empty.cta, true);
    assert.equal(empty.groupCta, true);

    await clientNavigate(
      page,
      `${ws}/sessions/${sessionId}/errors?case=${caseId}&tab=attr&at=probe-m11-02-0001`,
    );
    await waitForDocument(
      page.session,
      `location.search.includes("at=probe-m11-02-0001") &&
        Boolean(document.querySelector("[data-testid='attribution-report']"))`,
      "deep link before reload",
    );
    const reloadAuth = await loginSession();
    await installCookie(page, reloadAuth.cookie);
    await page.session.send("Page.reload");
    const reloaded = await waitForDocument(
      page.session,
      `(() => {
        if (!location.search.includes("case=${caseId}")) return null;
        if (!location.search.includes("at=probe-m11-02-0001")) return null;
        const report = document.querySelector("[data-testid='attribution-report']");
        const group = document.querySelector(
          ${JSON.stringify(`[data-bad-case-id='${caseId}']`)},
        );
        if (!report || !group) return null;
        if (!group.querySelector("[data-testid='attribution-page-prev']")) return null;
        return {
          position: report.querySelector("[data-testid='attribution-position']")?.textContent,
          text: report.textContent,
          pager: group.querySelector(".attr-pager")?.textContent?.replace(/\s+/g, " ").trim(),
          active: group.querySelector(
            ${JSON.stringify(`[data-attribution-id='probe-m11-02-0001']`)},
          )?.classList.contains("active"),
        };
      })()`,
      "reloaded attribution deep link",
    );
    assert.equal(reloaded.position, "3 / 4");
    assert.match(reloaded.text, /checklist-skill/);
    assert.match(reloaded.pager, /2 \/ 2/);
    assert.equal(reloaded.active, true);

    assert.deepEqual(violations, [], violations.join("\n"));
  } finally {
    await page.close();
  }
});
