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
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const initialPassword = "m4-problem-cards-initial-password";
const secret = "m4-problem-cards-signing-secret-with-sufficient-length";
const ws = "/workspaces/ws-default";
let api;
let web;
let dataDir;
let baseUrl;
let apiLogs = "";
let webLogs = "";
let currentPassword = initialPassword;
let passwordRevision = 0;

async function cleanup() {
  await stop(web);
  await stop(api);
  if (dataDir) await rm(dataDir, { recursive: true, force: true });
}

async function loginCookie() {
  const login = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      username: "admin",
      password: currentPassword,
    }),
  });
  assert.equal(login.status, 200);
  const body = await login.json();
  const initialCookie = login.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(initialCookie);
  const nextPassword =
    `m4-problem-cards-replacement-password-${++passwordRevision}`;

  const changed = await fetch(`${baseUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${body.accessToken}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      oldPassword: currentPassword,
      newPassword: nextPassword,
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
  currentPassword = nextPassword;
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


async function defaultToTree(page) {
  await page.session.send("Page.addScriptToEvaluateOnNewDocument", {
    source: `try { localStorage.setItem("he:flow-mode", "tree"); } catch {}`,
  });
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m4-problems-e2e-"));
  const env = {
    ...process.env,
    HE_ADMIN_PASSWORD: initialPassword,
    HE_ADMIN_USERNAME: "admin",
    HE_DATA_DIR: dataDir,
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: secret,
    HE_PHASE: "demo",
  };
  const setup = spawn(pnpm, ["fixtures:seed"], {
    cwd: root,
    env,
    encoding: "utf8",
  });
  let setupOutput = "";
  capture(setup, (chunk) => {
    setupOutput += chunk;
  });
  const setupExit = await new Promise((resolve) => {
    setup.once("exit", (code) => resolve(code));
  });
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

test("m4 problem cards match the prototype and link list and canvas", async () => {
  const page = await createBrowserPage();
    await defaultToTree(page);
  try {
    const violations = browserViolations(page.session);
    await installCookie(page, await loginCookie());
    await page.session.send("Page.navigate", { url: `${baseUrl}/sessions` });
    await waitForDocument(
      page.session,
      `document.querySelectorAll("[data-testid='session-card']").length === 4`,
      "seeded Session list for problem cards",
    );
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 960,
      deviceScaleFactor: 1,
      mobile: false,
    });

    const sessions = {
      prompt: "10000000-0000-4000-8000-000000000001",
      nonissue: "10000000-0000-4000-8000-000000000002",
      error: "10000000-0000-4000-8000-000000000003",
      unanalyzed: "10000000-0000-4000-8000-000000000004",
    };
    const statesBySession = {
      [sessions.prompt]: [
        "是问题-提示词问题",
        "是问题-模型问题",
      ],
      [sessions.nonissue]: ["非问题"],
      [sessions.error]: ["是问题-错误"],
      [sessions.unanalyzed]: ["未分析"],
    };

    const observedBySession = {};
    for (const [sessionId, expectedStates] of Object.entries(statesBySession)) {
      await page.session.send("Runtime.evaluate", {
        expression: `document.querySelector(${JSON.stringify(
          `[data-session-id='${sessionId}']`,
        )}).click()`,
      });
      const observed = await waitForDocument(
        page.session,
        `(() => {
          const selected = document.querySelector(
            ${JSON.stringify(`[data-session-id='${sessionId}']`)},
          );
          if (selected?.getAttribute("data-selected") !== "true") return null;
          const list = document.querySelector("[data-testid='problem-list']");
          const tree = document.querySelector("[data-testid='agent-tree']");
          if (!list || !tree) return null;
          const rows = [...list.querySelectorAll("[data-bad-case-id]")];
          const cards = [...tree.querySelectorAll(".rf-finding")];
          if (rows.length !== ${expectedStates.length}) return null;
          return {
            ids: rows.map((row) => row.getAttribute("data-bad-case-id")),
            cardIds: cards.map((card) => card.getAttribute("data-bad-case-id")),
            text: rows.map((row) => row.closest(".problem-row-card")?.textContent ?? ""),
            details: rows.map((row) => {
              const card = row.closest(".problem-row-card");
              return {
                no: card?.querySelector(".problem-no")?.textContent?.trim(),
                type: card?.querySelector(".type-badge")?.textContent?.trim(),
                object: card?.querySelector(".object-badge")?.textContent?.trim(),
                caseId: card?.querySelector(".problem-id")?.textContent?.trim(),
                description:
                  card?.querySelector(".problem-detail")?.textContent?.trim(),
                descriptionItems:
                  card?.querySelectorAll(".problem-detail ul li").length ?? 0,
                meta: card?.querySelector(".problem-meta")?.textContent?.trim(),
              };
            }),
          };
        })()`,
        `problem cards for ${sessionId}`,
      );
      observedBySession[sessionId] = observed;

      assert.deepEqual(
        observed.cardIds,
        observed.ids,
        `${sessionId}: ${JSON.stringify(observed)}`,
      );
      for (const state of expectedStates) {
        assert.ok(
          observed.text.some((text) => text.includes(state)),
          `${sessionId} should show ${state}`,
        );
      }
    }

    assert.deepEqual(
      observedBySession[sessions.prompt].details.map((detail) => ({
        no: detail.no,
        type: detail.type,
        object: detail.object,
        caseId: detail.caseId,
        description: detail.description,
        meta: detail.meta,
      })),
      [
        {
          no: "BC1",
          type: "self",
          object: "Explore",
          caseId: "badcase-synthetic-0001",
          description: "合成示例：检查结论缺少目标文件。",
          meta: "关联：agent · Explore",
        },
        {
          no: "BC2",
          type: "discovery",
          object: "Explore",
          caseId: "badcase-synthetic-0005",
          description: "合成示例：推理步骤越过工具边界。",
          meta: "关联：agent · Explore",
        },
      ],
    );

    const markdownCard = observedBySession[sessions.nonissue].details[0];
    assert.equal(markdownCard.no, "BC1");
    assert.equal(markdownCard.type, "discovery");
    assert.equal(markdownCard.object, "review-workflow");
    assert.equal(markdownCard.caseId, "badcase-synthetic-0002");
    assert.equal(markdownCard.meta, "关联：agent · review-workflow");
    assert.match(
      markdownCard.description,
      /F2P 失败（4 项）[\s\S]*P2P 回退（6 项）/,
      markdownCard.description,
    );
    assert.equal(markdownCard.descriptionItems, 10);

    for (const detail of [
      ...observedBySession[sessions.error].details,
      ...observedBySession[sessions.unanalyzed].details,
    ]) {
      assert.equal(detail.descriptionItems, 0, JSON.stringify(detail));
      assert.ok(
        detail.description?.startsWith("合成示例："),
        JSON.stringify(detail),
      );
    }

    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector(${JSON.stringify(
        `[data-session-id='${sessions.prompt}']`,
      )}).click()`,
    });
    await waitForDocument(
      page.session,
      `document.querySelector(
        ${JSON.stringify(`[data-session-id='${sessions.prompt}']`)},
      )?.getAttribute("data-selected") === "true" &&
        document.querySelectorAll(
          "[data-testid='problem-list'] [data-bad-case-id]",
        ).length === 2 &&
        document.querySelectorAll(
          "[data-testid='agent-tree'] .rf-finding",
        ).length === 2`,
      "prompt Session problems",
    );

    const firstId = await waitForDocument(
      page.session,
      `(() => {
        const row = document.querySelector(
          "[data-testid='problem-list'] [data-bad-case-id]",
        );
        if (!row) return null;
        row.click();
        return row.getAttribute("data-bad-case-id");
      })()`,
      "select the first problem from the list",
    );
    const listSelection = await waitForDocument(
      page.session,
      `(() => {
        const rows = [...document.querySelectorAll(
          "[data-testid='problem-list'] [data-bad-case-id]",
        )];
        const cards = [...document.querySelectorAll(
          "[data-testid='agent-tree'] .rf-finding",
        )];
        const activeRows = rows.filter(
          (row) => row.getAttribute("aria-pressed") === "true",
        );
        const activeCards = cards.filter(
          (card) => card.getAttribute("aria-pressed") === "true",
        );
        const card = cards.find(
          (item) => item.getAttribute("data-bad-case-id") === ${JSON.stringify(firstId)},
        );
        const canvas = document.querySelector("[data-testid='agent-tree']");
        if (
          activeRows.length !== 1 ||
          activeCards.length !== 1 ||
          !card ||
          !canvas
        ) return null;
        const cardBox = card.getBoundingClientRect();
        const canvasBox = canvas.getBoundingClientRect();
        if (
          cardBox.right <= canvasBox.left ||
          cardBox.left >= canvasBox.right ||
          cardBox.bottom <= canvasBox.top ||
          cardBox.top >= canvasBox.bottom
        ) return null;
        return {
          rowId: activeRows[0].getAttribute("data-bad-case-id"),
          cardId: activeCards[0].getAttribute("data-bad-case-id"),
        };
      })()`,
      "list selection locates one graph card",
    );
    assert.deepEqual(listSelection, {
      rowId: firstId,
      cardId: firstId,
    });

    const secondCardId = await waitForDocument(
      page.session,
      `(() => {
        const card = [...document.querySelectorAll(
          "[data-testid='agent-tree'] .rf-finding",
        )].find(
          (item) => item.getAttribute("aria-pressed") !== "true",
        );
        if (!card) return null;
        card.click();
        return card.getAttribute("data-bad-case-id");
      })()`,
      "select the second problem from the graph",
    );
    const graphSelection = await waitForDocument(
      page.session,
      `(() => {
        const rows = [...document.querySelectorAll(
          "[data-testid='problem-list'] [data-bad-case-id]",
        )];
        const cards = [...document.querySelectorAll(
          "[data-testid='agent-tree'] .rf-finding",
        )];
        const activeRows = rows.filter(
          (row) => row.getAttribute("aria-pressed") === "true",
        );
        const activeCards = cards.filter(
          (card) => card.getAttribute("aria-pressed") === "true",
        );
        if (activeRows.length !== 1 || activeCards.length !== 1) return null;
        const row = activeRows[0];
        const rowBox = row?.getBoundingClientRect();
        const clickedId = ${JSON.stringify(secondCardId)};
        const rowId = row?.getAttribute("data-bad-case-id");
        const cardId = activeCards[0]?.getAttribute("data-bad-case-id");
        const rowVisible = Boolean(
          rowBox &&
          rowBox.bottom >= 0 &&
          rowBox.top <= document.documentElement.clientHeight,
        );
        if (
          rowId !== clickedId ||
          cardId !== clickedId ||
          !rowVisible
        ) return null;
        return {
          clickedId,
          rowIds: activeRows.map(
            (item) => item.getAttribute("data-bad-case-id"),
          ),
          cardIds: activeCards.map(
            (item) => item.getAttribute("data-bad-case-id"),
          ),
          rowVisible,
          rowBox: rowBox
            ? {
                top: rowBox.top,
                bottom: rowBox.bottom,
                height: rowBox.height,
              }
            : null,
        };
      })()`,
      "graph selection scrolls and highlights the matching problem row",
    );
    assert.equal(graphSelection.clickedId, secondCardId);
    assert.deepEqual(graphSelection.rowIds, [secondCardId]);
    assert.deepEqual(graphSelection.cardIds, [secondCardId]);
    assert.equal(
      graphSelection.rowVisible,
      true,
      JSON.stringify(graphSelection),
    );
    if (process.env.HE_SCREENSHOT_DIR) {
      await mkdir(process.env.HE_SCREENSHOT_DIR, { recursive: true });
      const screenshot = await page.session.send("Page.captureScreenshot", {
        format: "png",
        captureBeyondViewport: false,
      });
      await writeFile(
        path.join(
          process.env.HE_SCREENSHOT_DIR,
          "m4-03-problem-cards-desktop.png",
        ),
        Buffer.from(screenshot.data, "base64"),
      );
    }

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    await waitForDocument(
      page.session,
      `document.documentElement.scrollWidth <=
        document.documentElement.clientWidth`,
      "problem cards stay within the mobile viewport",
    );
    if (process.env.HE_SCREENSHOT_DIR) {
      const screenshot = await page.session.send("Page.captureScreenshot", {
        format: "png",
        captureBeyondViewport: false,
      });
      await writeFile(
        path.join(
          process.env.HE_SCREENSHOT_DIR,
          "m4-03-problem-cards-mobile.png",
        ),
        Buffer.from(screenshot.data, "base64"),
      );
    }
    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
  } finally {
    await page.close();
  }
});

test("m4 problem cards reveal a selected problem inside a folded branch", async () => {
  const page = await createBrowserPage();
    await defaultToTree(page);
  try {
    const violations = browserViolations(page.session);
    await installCookie(page, await loginCookie());
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 960,
      deviceScaleFactor: 1,
      mobile: false,
    });
    const sessionId = "10000000-0000-4000-8000-000000000001";
    const children = Array.from({ length: 9 }, (_, index) => ({
      agentId: `folded-${index + 1}`,
      parentAgentId: "main",
      kind: "subagent",
      agentType: "general-purpose",
      taskKind: null,
      spawnDepth: 1,
      label: `Folded Agent ${index + 1}`,
      desc: `Folded Agent ${index + 1}`,
      lines: 2,
      messagesCount: 1,
      toolUseId: `folded-tool-${index + 1}`,
      skillName: null,
      teamName: null,
      events: [],
    }));
    const foldedTree = {
      sessionId,
      agents: [
        {
          agentId: "main",
          parentAgentId: null,
          kind: "main",
          agentType: null,
          taskKind: null,
          spawnDepth: 0,
          label: "主会话",
          desc: "主会话",
          lines: 9,
          messagesCount: 9,
          toolUseId: null,
          skillName: null,
          teamName: null,
          events: children.map((child, index) => ({
            kind: "agent",
            line: index + 1,
            messageOffset: index,
            name: child.label,
            desc: child.desc,
            toolUseId: child.toolUseId,
          })),
        },
        ...children,
      ],
      badCases: [
        {
          badCaseId: "case-folded-host",
          badCaseAgent: { sessionId, agentId: "folded-9" },
          badCaseType: "self",
          objectType: "agent",
          objectName: "Folded Agent 9",
          objectVersion: null,
          title: "折叠分支问题",
          reason:
            "folded branch problem: 折叠宿主展开后问题卡仍需可见。",
          anchor: { agentId: "folded-9", eventIndex: -1, kind: "node" },
        },
      ],
    };
    const problem = {
      badCaseId: "case-folded-host",
      sessionId,
      sessionTitle: "示例会话一",
      badCaseType: "self",
      objectType: "agent",
      objectName: "Folded Agent 9",
      objectVersion: null,
      title: "折叠分支问题",
      reason: "folded branch problem: 折叠宿主展开后问题卡仍需可见。",
      metaData: { source: "e2e" },
      degraded: false,
      diagnosticCode: null,
      anchor: { agentId: "folded-9", eventIndex: -1, kind: "node" },
      badCaseAgent: { sessionId, agentId: "folded-9" },
      analysis: {
        probeId: null,
        attributeType: null,
        displayState: "unanalyzed",
        result: null,
        status: "unanalyzed",
      },
    };

    await page.session.send("Fetch.enable", {
      patterns: [
        {
          urlPattern: `*://*/api/workspaces/*/sessions/${sessionId}/tree`,
          requestStage: "Request",
        },
        {
          urlPattern: `*://*/api/workspaces/*/sessions/${sessionId}/bad-cases`,
          requestStage: "Request",
        },
      ],
    });
    page.session.on("Fetch.requestPaused", (event) => {
      const body = event.request.url.endsWith("/tree")
        ? foldedTree
        : { items: [problem] };
      void page.session.send("Fetch.fulfillRequest", {
        requestId: event.requestId,
        responseCode: 200,
        responseHeaders: [
          { name: "content-type", value: "application/json" },
        ],
        body: Buffer.from(JSON.stringify(body)).toString("base64"),
      });
    });

    await page.session.send("Page.navigate", {
      url: `${baseUrl}${ws}/sessions/${sessionId}`,
    });
    const beforeSelection = await waitForDocument(
      page.session,
      `(() => {
        const row = document.querySelector(
          "[data-bad-case-id='case-folded-host']",
        );
        const list = document.querySelector("[data-testid='problem-list']");
        const tree = document.querySelector("[data-testid='agent-tree']");
        if (!row || !list || !tree) return null;
        return {
          cards: tree.querySelectorAll(".rf-finding").length,
          collapseNodes: tree.querySelectorAll(".rf-agent.collapse").length,
        };
      })()`,
      "folded problem list before selection",
    );
    assert.equal(beforeSelection.cards, 0, JSON.stringify(beforeSelection));
    assert.equal(
      beforeSelection.collapseNodes,
      1,
      JSON.stringify(beforeSelection),
    );

    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector(
        "[data-bad-case-id='case-folded-host']",
      ).click()`,
    });
    const afterSelection = await waitForDocument(
      page.session,
      `(() => {
        const tree = document.querySelector("[data-testid='agent-tree']");
        const row = document.querySelector(
          "[data-testid='problem-list'] [data-bad-case-id='case-folded-host']",
        );
        const card = tree?.querySelector(
          ".rf-finding[data-bad-case-id='case-folded-host']",
        );
        if (!tree || !row || !card) return null;
        const cardBox = card.getBoundingClientRect();
        const treeBox = tree.getBoundingClientRect();
        const visible = cardBox.right > treeBox.left
          && cardBox.left < treeBox.right
          && cardBox.bottom > treeBox.top
          && cardBox.top < treeBox.bottom;
        if (!visible) return null;
        return {
          active: card.getAttribute("aria-pressed"),
          collapseNodes: tree.querySelectorAll(".rf-agent.collapse").length,
          visible,
          edgeCount: tree.querySelectorAll(
            ".vue-flow__edge-path",
          ).length,
        };
      })()`,
      "selected folded problem expands",
    );
    await new Promise((resolve) => setTimeout(resolve, 500));
    const centeredResult = await page.session.send("Runtime.evaluate", {
      expression: `(() => {
        const tree = document.querySelector("[data-testid='agent-tree']");
        const card = tree?.querySelector(
          ".rf-finding[data-bad-case-id='case-folded-host']",
        );
        if (!tree || !card) return null;
        const cardBox = card.getBoundingClientRect();
        const treeBox = tree.getBoundingClientRect();
        return {
          dx: Math.abs(
            cardBox.left + cardBox.width / 2 -
            (treeBox.left + treeBox.width / 2),
          ),
          dy: Math.abs(
            cardBox.top + cardBox.height / 2 -
            (treeBox.top + treeBox.height / 2),
          ),
          cardBox: {
            left: cardBox.left,
            top: cardBox.top,
            width: cardBox.width,
            height: cardBox.height,
          },
          treeBox: {
            left: treeBox.left,
            top: treeBox.top,
            width: treeBox.width,
            height: treeBox.height,
          },
        };
      })()`,
      returnByValue: true,
    });
    const centerMetrics = centeredResult.result.value;
    assert.ok(centerMetrics, "selected folded problem remains visible");
    assert.ok(
      centerMetrics.dx <= 8 && centerMetrics.dy <= 8,
      JSON.stringify(centerMetrics),
    );
    assert.deepEqual(
      {
        active: afterSelection.active,
        collapseNodes: afterSelection.collapseNodes,
        visible: afterSelection.visible,
      },
      {
      active: "true",
      collapseNodes: 0,
      visible: true,
      },
    );
    assert.ok(afterSelection.edgeCount >= 10, JSON.stringify(afterSelection));
    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
    await page.session.send("Fetch.disable");
  } finally {
    await page.close();
  }
});

test("m4 problem cards keep a long case id and object name inside the card", async () => {
  const page = await createBrowserPage();
  await defaultToTree(page);
  try {
    const violations = browserViolations(page.session);
    await installCookie(page, await loginCookie());
    const sessionId = "10000000-0000-4000-8000-000000000001";
    const longId = `case-${"x".repeat(59)}`;
    const longObjectName = `runtime-object-${"y".repeat(40)}`;
    const problem = {
      badCaseId: longId,
      sessionId,
      sessionTitle: "示例会话一",
      badCaseType: "discovery",
      objectType: "agent",
      objectName: longObjectName,
      objectVersion: null,
      title: "长标识问题",
      reason: "长 case ID 与长对象名仍需留在卡片内，不撑破 390px 视口。",
      metaData: { source: "e2e" },
      degraded: false,
      diagnosticCode: null,
      anchor: {
        agentId: "agent-s1-review-0001",
        eventIndex: -1,
        kind: "unknown",
      },
      badCaseAgent: { sessionId, agentId: "agent-s1-review-0001" },
      analysis: {
        probeId: null,
        attributeType: null,
        displayState: "unanalyzed",
        result: null,
        status: "unanalyzed",
      },
    };

    await page.session.send("Fetch.enable", {
      patterns: [
        {
          urlPattern: `*://*/api/workspaces/*/sessions/${sessionId}/bad-cases`,
          requestStage: "Request",
        },
      ],
    });
    page.session.on("Fetch.requestPaused", (event) => {
      void page.session.send("Fetch.fulfillRequest", {
        requestId: event.requestId,
        responseCode: 200,
        responseHeaders: [
          { name: "content-type", value: "application/json" },
        ],
        body: Buffer.from(JSON.stringify({ items: [problem] })).toString(
          "base64",
        ),
      });
    });

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    await page.session.send("Page.navigate", {
      url: `${baseUrl}${ws}/sessions/${sessionId}`,
    });
    await waitForDocument(
      page.session,
      `document.querySelectorAll(
        "[data-testid='problem-list'] [data-bad-case-id]",
      ).length === 1`,
      "long identifier problem card",
    );
    const measured = await page.session.send("Runtime.evaluate", {
      expression: `(() => {
        const card = document.querySelector(
          "[data-testid='problem-list'] [data-bad-case-id]",
        )?.closest(".problem-row-card");
        const idLink = card?.querySelector(".problem-id");
        const objectBadge = card?.querySelector(".object-badge");
        if (!card || !idLink || !objectBadge) return null;
        const cardBox = card.getBoundingClientRect();
        const idBox = idLink.getBoundingClientRect();
        const objectBox = objectBadge.getBoundingClientRect();
        return {
          idText: idLink.textContent.trim(),
          objectText: objectBadge.textContent.trim(),
          cardLeft: cardBox.left,
          cardRight: cardBox.right,
          idLeft: idBox.left,
          idRight: idBox.right,
          objectLeft: objectBox.left,
          objectRight: objectBox.right,
          viewportWidth: document.documentElement.clientWidth,
          scrollWidth: document.documentElement.scrollWidth,
        };
      })()`,
      returnByValue: true,
    });
    const box = measured.result.value;
    assert.ok(box, "long identifier card rendered");
    assert.equal(box.idText, longId);
    assert.equal(box.objectText, longObjectName);
    assert.ok(
      box.scrollWidth <= box.viewportWidth,
      `no horizontal overflow: ${JSON.stringify(box)}`,
    );
    assert.ok(box.cardLeft >= -1, JSON.stringify(box));
    assert.ok(box.cardRight <= box.viewportWidth + 1, JSON.stringify(box));
    assert.ok(box.idLeft >= box.cardLeft - 1, JSON.stringify(box));
    assert.ok(box.idRight <= box.cardRight + 1, JSON.stringify(box));
    assert.ok(box.objectLeft >= box.cardLeft - 1, JSON.stringify(box));
    assert.ok(box.objectRight <= box.cardRight + 1, JSON.stringify(box));
    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
    await page.session.send("Fetch.disable");
  } finally {
    await page.close();
  }
});

test("m4 problem cards keep description links clickable above the select button", async () => {
  const page = await createBrowserPage();
  await defaultToTree(page);
  try {
    const violations = browserViolations(page.session);
    await installCookie(page, await loginCookie());
    const sessionId = "10000000-0000-4000-8000-000000000001";
    const problem = {
      badCaseId: "case-link-host",
      sessionId,
      sessionTitle: "示例会话一",
      badCaseType: "self",
      objectType: "agent",
      objectName: "Explore",
      objectVersion: null,
      title: "描述内链接问题",
      reason: "失败清单见 [完整报告](#problem-description)。",
      metaData: { source: "e2e" },
      degraded: false,
      diagnosticCode: null,
      anchor: {
        agentId: "agent-s1-review-0001",
        eventIndex: -1,
        kind: "node",
      },
      badCaseAgent: { sessionId, agentId: "agent-s1-review-0001" },
      analysis: {
        probeId: null,
        attributeType: null,
        displayState: "unanalyzed",
        result: null,
        status: "unanalyzed",
      },
    };

    await page.session.send("Fetch.enable", {
      patterns: [
        {
          urlPattern: `*://*/api/workspaces/*/sessions/${sessionId}/bad-cases`,
          requestStage: "Request",
        },
      ],
    });
    page.session.on("Fetch.requestPaused", (event) => {
      void page.session.send("Fetch.fulfillRequest", {
        requestId: event.requestId,
        responseCode: 200,
        responseHeaders: [
          { name: "content-type", value: "application/json" },
        ],
        body: Buffer.from(JSON.stringify({ items: [problem] })).toString(
          "base64",
        ),
      });
    });

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 1600,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.session.send("Page.navigate", {
      url: `${baseUrl}${ws}/sessions/${sessionId}`,
    });
    await waitForDocument(
      page.session,
      `document.querySelectorAll(
        "[data-testid='problem-list'] [data-bad-case-id]",
      ).length === 1`,
      "description link problem card",
    );
    await page.session.send("Runtime.evaluate", {
      expression: `document.addEventListener("click", (event) => {
        if (event.target.closest(".problem-detail a")) event.preventDefault();
      }, true)`,
    });
    const linkBox = await page.session.send("Runtime.evaluate", {
      expression: `(() => {
        const link = document.querySelector(
          "[data-testid='problem-list'] .problem-detail a",
        );
        if (!link) return null;
        const rect = link.getBoundingClientRect();
        return {
          x: rect.left + rect.width / 2,
          y: rect.top + rect.height / 2,
          hit: document.elementFromPoint(
            rect.left + rect.width / 2,
            rect.top + rect.height / 2,
          )?.tagName,
          href: link.getAttribute("href"),
        };
      })()`,
      returnByValue: true,
    });
    const link = linkBox.result.value;
    assert.ok(link, "description link rendered");
    assert.equal(link.hit, "A", JSON.stringify(link));
    assert.equal(link.href, "#problem-description");

    await page.session.send("Input.dispatchMouseEvent", {
      type: "mousePressed",
      x: link.x,
      y: link.y,
      button: "left",
      clickCount: 1,
    });
    await page.session.send("Input.dispatchMouseEvent", {
      type: "mouseReleased",
      x: link.x,
      y: link.y,
      button: "left",
      clickCount: 1,
    });
    const afterClick = await waitForDocument(
      page.session,
      `(() => {
        const row = document.querySelector(
          "[data-testid='problem-list'] [data-bad-case-id='case-link-host']",
        );
        if (!row) return null;
        return {
          pressed: row.getAttribute("aria-pressed"),
          activeCards: document.querySelectorAll(
            "[data-testid='problem-list'] .problem-row-card.active",
          ).length,
        };
      })()`,
      "description link click state",
    );
    assert.equal(afterClick.pressed, "false", JSON.stringify(afterClick));
    assert.equal(afterClick.activeCards, 0, JSON.stringify(afterClick));

    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
    await page.session.send("Fetch.disable");
  } finally {
    await page.close();
  }
});
