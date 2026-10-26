import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
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
import {
  PERFORMANCE_BUDGETS,
  SYNTHETIC_LARGEST_TREE,
} from "../../scripts/performance-budgets.mjs";

const root = process.cwd();
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const secret = "m3-session-browser-signing-secret-with-sufficient-length";
let api;
let web;
let dataDir;
let baseUrl;
let apiLogs = "";
let webLogs = "";
let currentAdminPassword = "m3-session-browser-initial-password";
let passwordRevision = 0;
const performanceSource =
  process.env.HE_PERF_SOURCE === "local" ? "local" : "fixture";
let largestLocalSession = null;

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
      password: currentAdminPassword,
    }),
  });
  assert.equal(login.status, 200);
  const body = await login.json();
  passwordRevision += 1;
  const replacement = `m3-session-browser-replacement-password-${passwordRevision}`;
  const changed = await fetch(`${baseUrl}/api/auth/change-password`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${body.accessToken}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      oldPassword: currentAdminPassword,
      newPassword: replacement,
    }),
  });
  assert.equal(changed.status, 204);
  const refresh = await fetch(`${baseUrl}/api/auth/refresh`, {
    method: "POST",
    headers: {
      cookie: login.headers.get("set-cookie")?.match(/refresh_token=([^;]+)/)?.[1]
        ? `refresh_token=${login.headers.get("set-cookie").match(/refresh_token=([^;]+)/)[1]}`
        : "",
    },
  });
  assert.equal(refresh.status, 200);
  const cookie = refresh.headers.get("set-cookie")?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie);
  currentAdminPassword = replacement;
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

async function sessionCookie() {
  const response = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      username: "admin",
      password: currentAdminPassword,
    }),
  });
  assert.equal(response.status, 200);
  const cookie = response.headers
    .get("set-cookie")
    ?.match(/refresh_token=([^;]+)/)?.[1];
  assert.ok(cookie, "expected a login refresh cookie");
  return cookie;
}

before(async () => {
  dataDir = await mkdtemp(path.join(tmpdir(), "harness-m3-e2e-"));
  const baseEnv = {
    ...process.env,
    HE_ADMIN_PASSWORD: "m3-session-browser-initial-password",
    HE_ADMIN_USERNAME: "admin",
    HE_DATA_DIR: dataDir,
    HE_DB_DIALECT: "sqlite",
    HE_JWT_SECRET: secret,
    HE_PHASE: "demo",
  };
  const setupCommands =
    performanceSource === "local"
      ? [["data:import:sessions"], ["data:replay:sessions"]]
      : [["fixtures:seed"]];
  for (const args of setupCommands) {
    const setup = spawnSync(pnpm, args, {
      cwd: root,
      env: baseEnv,
      encoding: "utf8",
    });
    assert.equal(setup.status, 0, setup.stderr || setup.stdout);
  }
  if (performanceSource === "local") {
    const databasePath = path.join(dataDir, "harness.db");
    const python = process.env.PYTHON ?? "python3";
    const largest = spawnSync(
      python,
      [
        "-c",
        [
          "import json, sqlite3, sys",
          "connection = sqlite3.connect(sys.argv[1])",
          "rows = connection.execute(",
          "  'select root_session_id as id, count(*) as agents, sum(lines) as lines '",
          "  'from agents group by root_session_id order by agents desc, lines desc limit 1'",
          ").fetchall()",
          "print(json.dumps([dict(zip(('id', 'agents', 'lines'), row)) for row in rows]))",
          "connection.close()",
        ].join("\n"),
        databasePath,
      ],
      { encoding: "utf8" },
    );
    assert.equal(largest.status, 0, largest.stderr);
    [largestLocalSession] = JSON.parse(largest.stdout);
    assert.ok(largestLocalSession?.id);
  }

  const apiPort = await availablePort();
  const webPort = await availablePort();
  baseUrl = `http://127.0.0.1:${webPort}`;
  api = spawn(process.execPath, ["scripts/run-api.mjs", "start"], {
    cwd: root,
    env: {
      ...baseEnv,
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

test("m3-session-browser matches the prototype and restores URL state", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session);
    const cookie = await loginCookie();
    await page.session.send("Network.enable");
    await page.session.send("Network.setCookie", {
      name: "refresh_token",
      value: cookie,
      url: `${baseUrl}/api/auth`,
      httpOnly: true,
      sameSite: "Strict",
    });
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.session.send("Page.navigate", { url: `${baseUrl}/sessions` });
    const initial = await waitForDocument(
      page.session,
      `(() => {
        const cards = [...document.querySelectorAll("[data-testid='session-card']")];
        const sidebar = document.querySelector(".sidebar");
        const card = cards.find((candidate) => candidate.dataset.selected === "false");
        const detailCta = document.querySelector(".overview-head [data-testid='detail-cta']");
        if (cards.length !== 4 || !sidebar || !card || !detailCta) return null;
        return {
          path: location.pathname,
          query: location.search,
          cards: cards.length,
          densities: document.querySelectorAll("[data-testid='density-bar']").length,
          sidebarWidth: sidebar.getBoundingClientRect().width,
          browserWidth: document.querySelector(".session-browser").getBoundingClientRect().width,
          browserRadius: getComputedStyle(document.querySelector(".session-browser")).borderRadius,
          filterLabels: [...document.querySelectorAll(".filter-label")].map((node) => node.textContent.trim()),
          ctaInHeader: Boolean(detailCta),
          cardBackground: getComputedStyle(card).backgroundColor,
          bodyBackground: getComputedStyle(document.body).backgroundColor,
        };
      })()`,
      "four session cards",
    );
    assert.equal(initial.cards, 4);
    assert.equal(initial.densities, 8);
    assert.match(initial.path, /^\/sessions\/.+/);
    assert.ok(Math.abs(initial.sidebarWidth - 360) < 1, JSON.stringify(initial));
    assert.equal(initial.cardBackground, "rgb(255, 255, 255)");
    assert.equal(initial.bodyBackground, "rgb(244, 245, 247)");
    assert.ok(initial.browserWidth >= 1390, JSON.stringify(initial));
    assert.equal(initial.browserRadius, "0px");
    assert.deepEqual(initial.filterLabels, ["状态", "排序"]);
    assert.equal(initial.ctaInHeader, true);

    const initialTree = await waitForDocument(
      page.session,
      `(() => {
        const tree = document.querySelector("[data-testid='agent-tree']");
        const nodes = tree?.querySelectorAll(".vue-flow__node").length ?? 0;
        if (!tree || nodes === 0) return null;
        return {
          height: tree.getBoundingClientRect().height,
          nodes,
          legend: (() => {
            const node = document.querySelector(".tree-legend");
            if (!node) return null;
            const box = node.getBoundingClientRect();
            const treeBox = tree.getBoundingClientRect();
            return {
              bottomGap: treeBox.bottom - box.bottom,
              leftGap: box.left - treeBox.left,
            };
          })(),
        };
      })()`,
      "production Agent tree",
    );
    assert.ok(Math.abs(initialTree.height - 720) < 1, JSON.stringify(initialTree));
    assert.ok(initialTree.nodes > 0, JSON.stringify(initialTree));
    assert.ok(initialTree.legend, JSON.stringify(initialTree));
    assert.ok(initialTree.legend.leftGap >= 0 && initialTree.legend.leftGap <= 24, JSON.stringify(initialTree));
    assert.ok(initialTree.legend.bottomGap >= 0 && initialTree.legend.bottomGap <= 24, JSON.stringify(initialTree));

    const pressKey = async (key, code, windowsVirtualKeyCode) => {
      await page.session.send("Input.dispatchKeyEvent", {
        type: key === "Enter" ? "rawKeyDown" : "keyDown",
        key,
        code,
        windowsVirtualKeyCode,
      });
      if (key === "Enter") {
        await page.session.send("Input.dispatchKeyEvent", {
          type: "char",
          key,
          code,
          text: "\r",
          unmodifiedText: "\r",
          windowsVirtualKeyCode,
        });
      }
      await page.session.send("Input.dispatchKeyEvent", {
        type: "keyUp",
        key,
        code,
        windowsVirtualKeyCode,
      });
    };
    const treeCounts = [];
    let keyboardCheck = null;
    for (let index = 0; index < initial.cards; index += 1) {
      await page.session.send("Runtime.evaluate", {
        expression: `document.querySelectorAll("[data-testid='session-card']")[${index}].click()`,
      });
      const tree = await waitForDocument(
        page.session,
        `(() => {
          const selected = document.querySelector("[data-testid='session-card'][data-selected='true']");
          const nodes = document.querySelectorAll("[data-testid='agent-tree'] .vue-flow__node").length;
          const agents = document.querySelectorAll("[data-testid='agent-tree'] .rf-agent").length;
          return selected && agents > 0
            ? { path: location.pathname, nodes, agents }
            : null;
        })()`,
        `Agent tree for session ${index + 1}`,
      );
      assert.match(tree.path, /^\/sessions\/.+/);
      treeCounts.push(tree.agents);
      if (!keyboardCheck && tree.agents > 1) {
        const focusState = await page.session.send("Runtime.evaluate", {
          expression: `(() => {
            const tree = document.querySelector("[data-testid='agent-tree']");
            tree.tabIndex = -1;
            tree.focus();
            return {
              edgeTabStops: [...document.querySelectorAll(".vue-flow__edge")].filter((node) => node.tabIndex >= 0).length,
              nodeWrapperTabStops: [...document.querySelectorAll(".vue-flow__node")].filter((node) => node.tabIndex >= 0).length,
            };
          })()`,
          returnByValue: true,
        });
        assert.equal(focusState.result.value.edgeTabStops, 0);
        assert.equal(focusState.result.value.nodeWrapperTabStops, 0);
        await pressKey("Tab", "Tab", 9);
        const firstFocus = await page.session.send("Runtime.evaluate", {
          expression: `(() => {
            const active = document.activeElement;
            return {
              className: active?.className ?? "",
              label: active?.getAttribute?.("aria-label") ?? "",
              tagName: active?.tagName ?? "",
            };
          })()`,
          returnByValue: true,
        });
        assert.equal(firstFocus.result.value.tagName, "BUTTON", JSON.stringify(firstFocus));
        assert.match(firstFocus.result.value.className, /rf-agent/);
        await pressKey("Tab", "Tab", 9);
        const secondFocus = await page.session.send("Runtime.evaluate", {
          expression: `(() => {
            const active = document.activeElement;
            return {
              className: active?.className ?? "",
              label: active?.getAttribute?.("aria-label") ?? "",
              tagName: active?.tagName ?? "",
            };
          })()`,
          returnByValue: true,
        });
        assert.equal(secondFocus.result.value.tagName, "BUTTON", JSON.stringify(secondFocus));
        assert.match(secondFocus.result.value.className, /rf-agent/);
        assert.notEqual(secondFocus.result.value.label, "主会话", JSON.stringify(secondFocus));
        await pressKey("Enter", "Enter", 13);
        const selectedNode = await waitForDocument(
          page.session,
          `(() => {
            const active = [...document.querySelectorAll("[data-testid='agent-tree'] .rf-agent")]
              .filter((node) => node.getAttribute("aria-pressed") === "true");
            return active.length === 1
              ? {
                  border: getComputedStyle(document.querySelector("[data-testid='agent-tree']")).borderTopWidth,
                  label: active[0].getAttribute("aria-label"),
                }
              : null;
          })()`,
          "selected Agent node",
        );
        assert.ok(selectedNode.label, JSON.stringify(selectedNode));
        assert.equal(selectedNode.border, "0px", JSON.stringify(selectedNode));
        keyboardCheck = selectedNode;
      }
    }
    assert.equal(treeCounts.length, 4);
    assert.equal(treeCounts.reduce((sum, count) => sum + count, 0), 8);
    assert.ok(keyboardCheck, "expected at least one multi-Agent Session");

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
        columns: getComputedStyle(document.querySelector(".session-browser")).gridTemplateColumns,
        cards: document.querySelectorAll("[data-testid='session-card']").length
      }))()`,
      "mobile session browser with four cards",
    );
    assert.ok(mobile.scrollWidth <= mobile.clientWidth, JSON.stringify(mobile));
    assert.equal(mobile.cards, 4);
    assert.doesNotMatch(mobile.columns, /360px/);

    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });

    await page.session.send("Runtime.evaluate", {
      expression: `(async () => {
        const input = document.querySelector("[data-testid='search-input']");
        input.value = "example-repo";
        input.dispatchEvent(new Event("input", { bubbles: true }));
      })()`,
    });
    const searched = await waitForDocument(
      page.session,
      `Boolean(location.search.includes("q=example-repo") && document.querySelector("[data-testid='session-card']"))`,
      "debounced URL search",
    );
    assert.equal(searched, true);

    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelector("[data-testid='session-sort']").value = "messages";
        document.querySelector("[data-testid='session-sort']").dispatchEvent(new Event("change", { bubbles: true }));`,
    });
    const sorted = await waitForDocument(
      page.session,
      `Boolean(location.search.includes("sort=messages") && document.querySelector("[data-testid='session-overview']"))`,
      "sort URL state",
    );
    assert.equal(sorted, true);

    await page.session.send("Runtime.evaluate", {
      expression: `history.back()`,
    });
    const wentBack = await waitForDocument(
      page.session,
      `!location.search.includes("sort=messages")`,
      "browser back state",
    );
    assert.equal(wentBack, true);
    await page.session.send("Runtime.evaluate", {
      expression: `history.forward()`,
    });
    const wentForward = await waitForDocument(
      page.session,
      `location.search.includes("sort=messages")`,
      "browser forward state",
    );
    assert.equal(wentForward, true);

    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
  } finally {
    await page.close();
  }
});

test("m3 Session and Agent deep links survive refresh and new-window navigation", async () => {
  let cookie = await loginCookie();
  const first = await createBrowserPage();
  let second;
  try {
    await installCookie(first, cookie);
    await first.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await first.session.send("Page.navigate", { url: `${baseUrl}/sessions` });
    let target = null;
    for (let index = 0; index < 4 && !target; index += 1) {
      await waitForDocument(
        first.session,
        `Boolean(document.querySelectorAll("[data-testid='session-card']")[${index}])`,
        `session card ${index + 1}`,
      );
      await first.session.send("Runtime.evaluate", {
        expression: `document.querySelectorAll("[data-testid='session-card']")[${index}].click()`,
      });
      await waitForDocument(
        first.session,
        `Boolean(
          document.querySelector("[data-testid='session-card'][data-selected='true']") &&
          document.querySelectorAll("[data-testid='agent-tree'] .rf-agent").length
        )`,
        `Agent tree for deep-link session ${index + 1}`,
      );
      await new Promise((resolve) => setTimeout(resolve, 250));
      const candidate = await first.session.send("Runtime.evaluate", {
        expression: `(() => {
          const agents = document.querySelectorAll("[data-testid='agent-tree'] .rf-agent");
          const button = [...document.querySelectorAll("[data-testid='agent-tree'] .rf-agent")]
            .find((candidate) =>
              candidate.querySelector(".rf-cnode.skill, .rf-cnode.agent, .rf-cnode.workflow")
            );
          const node = button?.closest(".vue-flow__node");
          const agentId = node?.getAttribute("data-id");
          const triggerCount = button?.querySelectorAll(".rf-cnode.skill, .rf-cnode.agent, .rf-cnode.workflow").length ?? 0;
          const rootId = location.pathname.split("/").filter(Boolean).at(-1);
          return agentId && rootId && triggerCount > 0 && agents.length > 1
            ? { agentId, rootId, triggerCount, path: location.pathname }
            : null;
        })()`,
        returnByValue: true,
      });
      target = candidate.result.value;
    }
    assert.ok(target, "expected a Session Agent with an evidence trigger");
    cookie = await sessionCookie();
    await installCookie(first, cookie);
    await first.session.send("Runtime.evaluate", {
      expression: `(() => {
        const button = [...document.querySelectorAll("[data-testid='agent-tree'] .rf-agent")]
          .find((candidate) =>
            candidate.querySelector(".rf-cnode.skill, .rf-cnode.agent, .rf-cnode.workflow")
          );
        button?.click();
      })()`,
    });
    const agentUrl = await waitForDocument(
      first.session,
      `location.search.includes("agent=") ? location.href : null`,
      "node click writes Agent deep-link state",
    );
    const parsedAgentUrl = new URL(agentUrl);
    const targetAgentId = parsedAgentUrl.searchParams.get("agent");
    assert.ok(targetAgentId, agentUrl);
    parsedAgentUrl.searchParams.set("evidence", "0");
    const deepLink = parsedAgentUrl.href;
    await first.session.send("Page.navigate", { url: deepLink });
    await new Promise((resolve) => setTimeout(resolve, 1_200));
    const navigationState = await first.session.send("Runtime.evaluate", {
      expression: `({
        href: location.href,
        path: location.pathname,
        body: document.body.textContent.slice(0, 300),
        agents: document.querySelectorAll("[data-testid='agent-tree'] .rf-agent").length,
      })`,
      returnByValue: true,
    });
    assert.ok(
      navigationState.result.value.agents > 0,
      JSON.stringify({ deepLink, ...navigationState.result.value }),
    );
    const activeState = await waitForDocument(
      first.session,
      `(() => {
        const agents = [...document.querySelectorAll("[data-testid='agent-tree'] .rf-agent")];
        const notice = document.querySelector("[data-testid='deep-link-notice']")?.textContent ?? null;
        const hardError = document.querySelector("[data-testid='deep-link-error']")?.textContent ?? null;
        if (!agents.length && !notice && !hardError) return null;
        const selected = agents
          .find((node) => node.getAttribute("aria-pressed") === "true");
        const evidence = document.querySelectorAll("[data-testid='agent-tree'] .rf-cnode.evidence").length;
        return {
          agentId: selected?.closest(".vue-flow__node")?.getAttribute("data-id") ?? null,
          agents: agents.map((node) => ({
            active: node.getAttribute("aria-pressed"),
            id: node.closest(".vue-flow__node")?.getAttribute("data-id") ?? null,
          })),
          evidence,
          href: location.href,
          notice,
          hardError,
          body: getComputedStyle(document.body).backgroundColor,
          topbar: getComputedStyle(document.querySelector(".topbar")).backgroundColor,
        };
      })()`,
      "deep-linked Agent and evidence",
    );
    assert.equal(activeState.evidence, 1, JSON.stringify(activeState));
    const active = activeState;
    assert.equal(active.agentId, targetAgentId, JSON.stringify(active));
    assert.match(active.href, /agent=/);
    assert.match(active.href, /evidence=0/);
    assert.equal(active.body, "rgb(244, 245, 247)", JSON.stringify(active));
    assert.equal(active.topbar, "rgb(250, 251, 252)", JSON.stringify(active));

    cookie = await sessionCookie();
    await installCookie(first, cookie);
    await first.session.send("Page.reload");
    const refreshed = await waitForDocument(
      first.session,
      `(() => {
        const selected = [...document.querySelectorAll("[data-testid='agent-tree'] .rf-agent")]
          .find((node) => node.getAttribute("aria-pressed") === "true");
        return selected?.closest(".vue-flow__node")?.getAttribute("data-id") ?? null;
      })()`,
      "deep link after refresh",
    );
    assert.equal(refreshed, targetAgentId);

    const otherAgentId = await waitForDocument(
      first.session,
      `(() => {
        const selected = document.querySelector("[data-testid='agent-tree'] .rf-agent[aria-pressed='true']");
        const agents = [...document.querySelectorAll("[data-testid='agent-tree'] .rf-agent")];
        const other = agents.find((node) => node !== selected);
        const id = other?.closest(".vue-flow__node")?.getAttribute("data-id");
        if (!id) return null;
        other.click();
        return id;
      })()`,
      "another renderable Agent",
    );
    assert.ok(otherAgentId);
    const selectedOther = await waitForDocument(
      first.session,
      `Boolean(
        location.search.includes("agent=") &&
        !location.search.includes("evidence=") &&
        document.querySelector("[data-testid='agent-tree'] .rf-agent[aria-pressed='true']")
      )`,
      "Agent click replaces deep-link Agent and clears evidence",
    );
    assert.equal(selectedOther, true);

    await first.session.send("Runtime.evaluate", { expression: "history.back()" });
    const restoredHistory = await waitForDocument(
      first.session,
      `Boolean(location.search.includes("evidence=0") &&
        document.querySelector("[data-testid='agent-tree'] .rf-cnode.evidence"))`,
      "history restores original deep link",
    );
    assert.equal(restoredHistory, true);

    await first.session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    const mobileDeepLink = await waitForDocument(
      first.session,
      `(() => {
        const tree = document.querySelector("[data-testid='agent-tree']");
        const selected = document.querySelector(
          "[data-testid='agent-tree'] .rf-agent[aria-pressed='true']",
        );
        const evidence = document.querySelector(
          "[data-testid='agent-tree'] .rf-cnode.evidence",
        );
        if (!tree || !selected || !evidence) return null;
        const treeBox = tree.getBoundingClientRect();
        const selectedBox = selected.getBoundingClientRect();
        const visible = selectedBox.right > treeBox.left
          && selectedBox.left < treeBox.right
          && selectedBox.bottom > treeBox.top
          && selectedBox.top < treeBox.bottom;
        return visible
          ? {
              evidence: document.querySelectorAll(
                "[data-testid='agent-tree'] .rf-cnode.evidence",
              ).length,
              scrollWidth: document.documentElement.scrollWidth,
              clientWidth: document.documentElement.clientWidth,
            }
          : null;
      })()`,
      "390px deep-linked Agent and evidence",
    );
    assert.equal(mobileDeepLink.evidence, 1, JSON.stringify(mobileDeepLink));
    assert.ok(
      mobileDeepLink.scrollWidth <= mobileDeepLink.clientWidth,
      JSON.stringify(mobileDeepLink),
    );
    await first.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });

    const copiedUrl = await first.session.send("Runtime.evaluate", {
      expression: "location.href",
      returnByValue: true,
    });

    cookie = await sessionCookie();
    second = await createBrowserPage();
    await installCookie(second, cookie);
    await second.session.send("Page.navigate", {
      url: copiedUrl.result.value ?? deepLink,
    });
    const copied = await waitForDocument(
      second.session,
      `(() => {
        const selected = [...document.querySelectorAll("[data-testid='agent-tree'] .rf-agent")]
          .find((node) => node.getAttribute("aria-pressed") === "true");
        return selected?.closest(".vue-flow__node")?.getAttribute("data-id") ?? null;
      })()`,
      "new window restores copied deep link",
    );
    assert.equal(copied, targetAgentId);
  } finally {
    await second?.close();
    await first.close();
  }
});

test("m3 folded Agent deep links expand ancestors before locating", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session);
    const cookie = await loginCookie();
    await installCookie(page, cookie);
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: true,
    });
    await page.session.send("Page.navigate", { url: `${baseUrl}/sessions` });
    const sessionPath = await waitForDocument(
      page.session,
      `location.pathname.startsWith("/sessions/") &&
        document.querySelectorAll("[data-testid='session-card']").length >= 1
        ? location.pathname
        : null`,
      "initial Session selection",
    );
    const sessionId = decodeURIComponent(sessionPath.split("/").at(-1));
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
          lines: 10,
          messagesCount: 9,
          toolUseId: null,
          skillName: null,
          teamName: null,
          events: Array.from({ length: 9 }, (_, index) => ({
            kind: "agent",
            line: index + 1,
            messageOffset: index,
            name: `Agent ${index + 1}`,
            desc: `子任务 ${index + 1}`,
            toolUseId: `tool-${index + 1}`,
          })),
        },
        ...Array.from({ length: 9 }, (_, index) => ({
          agentId: `child-${index + 1}`,
          parentAgentId: "main",
          kind: "subagent",
          agentType: "general-purpose",
          taskKind: null,
          spawnDepth: 1,
          label: `general-purpose · 子任务 ${index + 1}`,
          desc: `子任务 ${index + 1}`,
          lines: 2,
          messagesCount: 1,
          toolUseId: `tool-${index + 1}`,
          skillName: null,
          teamName: null,
          events: [],
        })),
      ],
      badCases: [],
    };

    await page.session.send("Fetch.enable", {
      patterns: [
        {
          urlPattern: "*://*/api/sessions/*/tree",
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
        body: Buffer.from(JSON.stringify(foldedTree)).toString("base64"),
      });
    });

    await installCookie(page, await sessionCookie());
    await page.session.send("Page.navigate", {
      url: `${baseUrl}/sessions/${encodeURIComponent(sessionId)}?agent=child-9`,
    });
    const restored = await waitForDocument(
      page.session,
      `(() => {
        const tree = document.querySelector("[data-testid='agent-tree']");
        const notice = document.querySelector("[data-testid='deep-link-notice']");
        const hardError = document.querySelector("[data-testid='deep-link-error']");
        const login = document.querySelector("[data-testid='login-submit']");
        if (notice || hardError || login) {
          return {
            agentId: null,
            collapseNodes: document.querySelectorAll(
              "[data-testid='agent-tree'] .rf-agent.collapse",
            ).length,
            notice: notice?.textContent ?? null,
            hardError: hardError?.textContent ?? null,
            login: Boolean(login),
            body: document.body.textContent?.slice(0, 500) ?? null,
            href: location.href,
            treeText: tree?.textContent?.slice(0, 500) ?? null,
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth: document.documentElement.clientWidth,
          };
        }
        if (!tree) return null;
        const selected = document.querySelector(
          "[data-testid='agent-tree'] .rf-agent[aria-pressed='true']",
        );
        const node = selected?.closest(".vue-flow__node");
        if (!node || node.getAttribute("data-id") !== "child-9") return null;
        const treeBox = tree.getBoundingClientRect();
        const nodeBox = selected.getBoundingClientRect();
        const visible = nodeBox.right > treeBox.left
          && nodeBox.left < treeBox.right
          && nodeBox.bottom > treeBox.top
          && nodeBox.top < treeBox.bottom;
        if (!visible) return null;
        return {
          agentId: node.getAttribute("data-id"),
          collapseNodes: document.querySelectorAll(
            "[data-testid='agent-tree'] .rf-agent.collapse",
          ).length,
          visible,
          href: location.href,
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        };
      })()`,
      "folded deep-linked Agent expansion",
    );

    assert.equal(restored.agentId, "child-9", JSON.stringify(restored));
    assert.equal(restored.collapseNodes, 0, JSON.stringify(restored));
    assert.equal(restored.visible, true, JSON.stringify(restored));
    assert.match(restored.href, /agent=child-9/);
    assert.ok(restored.scrollWidth <= restored.clientWidth, JSON.stringify(restored));
    assert.deepEqual(violations, [], `${violations.join("\n")}\n\nVite:\n${webLogs}`);
    await page.session.send("Fetch.disable");
  } finally {
    await page.close();
  }
});

test("m3-session-browser stays within performance budgets", async () => {
  const page = await createBrowserPage();
  try {
    const violations = browserViolations(page.session);
    const cookie = await loginCookie();
    await installCookie(page, cookie);
    await page.session.send("Emulation.setDeviceMetricsOverride", {
      width: 1408,
      height: 360,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await page.session.send("Page.addScriptToEvaluateOnNewDocument", {
      source: `window.__perfLongTasks = [];
        window.__perfCardsReadyAt = null;
        new PerformanceObserver((list) => {
          window.__perfLongTasks.push(...list.getEntries().map((entry) => entry.duration));
        }).observe({ type: "longtask", buffered: true });
        const watchCards = () => {
          const markCards = () => {
            if (
              window.__perfCardsReadyAt === null &&
              document.querySelectorAll("[data-testid='session-card']").length === 4
            ) {
              window.__perfCardsReadyAt = Date.now();
            }
          };
          new MutationObserver(markCards).observe(document.documentElement, {
            childList: true,
            subtree: true,
          });
          markCards();
        };
        if (document.documentElement) watchCards();
        else document.addEventListener("DOMContentLoaded", watchCards, { once: true });`,
    });

    const detailRequests = [];
    const treeRequests = [];
    page.session.on("Network.requestWillBeSent", ({ request }) => {
      const match = new URL(request.url).pathname.match(
        /^\/api\/sessions\/([^/]+)(\/tree)?$/,
      );
      if (!match) return;
      const entry = {
        at: Date.now(),
        sessionId: decodeURIComponent(match[1]),
        url: request.url,
      };
      if (match[2]) {
        treeRequests.push(entry);
      } else {
        detailRequests.push(entry);
      }
    });
    await page.session.send("Network.enable");
    const navigationStarted = Date.now();
    await page.session.send("Page.navigate", { url: `${baseUrl}/sessions` });
    const cards = await waitForDocument(
      page.session,
      `(() => {
        const cards = [...document.querySelectorAll("[data-testid='session-card']")];
        return cards.length === 4
          ? {
              cards: cards.length,
              at: performance.now(),
              readyAt: window.__perfCardsReadyAt,
            }
          : null;
      })()`,
      "Session cards before graph",
    );
    const cardsReadyAt = cards.readyAt ?? Date.now();
    const readyMs = cardsReadyAt - navigationStarted;
    assert.equal(cards.cards, 4);
    assert.ok(readyMs <= PERFORMANCE_BUDGETS.cardsReadyMs, JSON.stringify({ readyMs }));

    const initialTree = await waitForDocument(
      page.session,
      `(() => {
        const tree = document.querySelector("[data-testid='agent-tree']");
        if (!tree || tree.querySelectorAll(".vue-flow__node").length === 0) return null;
        return {
          nodes: tree.querySelectorAll(".vue-flow__node").length,
          flowResource: Boolean(tree.querySelector(".vue-flow")),
        };
      })()`,
      "lazy performance tree",
    );
    assert.ok(initialTree.nodes > 0, JSON.stringify(initialTree));
    assert.equal(initialTree.flowResource, true, JSON.stringify(initialTree));
    assert.ok(treeRequests.length >= 1, JSON.stringify(treeRequests));
    assert.ok(
      treeRequests[0].at >= cardsReadyAt,
      JSON.stringify({ cardsReadyAt, firstTreeRequest: treeRequests[0] }),
    );

    const interaction = await page.session.send("Runtime.evaluate", {
      expression: `(async () => {
        const cards = [...document.querySelectorAll("[data-testid='session-card']")];
        const id = cards[1].dataset.sessionId;
        const started = performance.now();
        cards[1].click();
        while (performance.now() - started < 1000) {
          if (cards[1].dataset.selected === "true") {
            return { id, ms: performance.now() - started };
          }
          await new Promise(requestAnimationFrame);
        }
        return { id, ms: 1000 };
      })()`,
      awaitPromise: true,
      returnByValue: true,
    });
    const interactionMs = interaction.result.value.ms;
    assert.ok(
      interactionMs <= PERFORMANCE_BUDGETS.interactionMs,
      JSON.stringify({ interactionMs }),
    );
    const selectedSessionId = interaction.result.value.id;
    assert.equal(
      detailRequests.filter((entry) => entry.sessionId === selectedSessionId).length,
      1,
      JSON.stringify(detailRequests),
    );
    assert.equal(
      treeRequests.filter((entry) => entry.sessionId === selectedSessionId).length,
      1,
      JSON.stringify(treeRequests),
    );

    const secondScroll = await page.session.send("Runtime.evaluate", {
      expression: `(async () => {
        const list = document.querySelector(".session-list");
        const overview = document.querySelector(".overview");
        await new Promise((resolve) => setTimeout(resolve, 320));
        for (const [panel, height] of [[list, 600], [overview, 600]]) {
          const probe = document.createElement("div");
          probe.dataset.scrollProbe = "true";
          probe.style.height = height + "px";
          probe.setAttribute("aria-hidden", "true");
          panel.appendChild(probe);
        }
        list.scrollTop = Math.min(80, list.scrollHeight - list.clientHeight);
        overview.scrollTop = Math.min(180, overview.scrollHeight - overview.clientHeight);
        await new Promise(requestAnimationFrame);
        await new Promise(requestAnimationFrame);
        return {
          path: location.pathname,
          list: list.scrollTop,
          listClient: list.clientHeight,
          listScroll: list.scrollHeight,
          overview: overview.scrollTop,
          overviewClient: overview.clientHeight,
          overviewScroll: overview.scrollHeight,
        };
      })()`,
      awaitPromise: true,
      returnByValue: true,
    });
    assert.ok(
      secondScroll.result.value.list > 0,
      JSON.stringify(secondScroll.result.value),
    );
    assert.ok(
      secondScroll.result.value.overview > 0,
      JSON.stringify(secondScroll.result.value),
    );
    await page.session.send("Runtime.evaluate", {
      expression: `document.querySelectorAll("[data-testid='session-card']")[0].click()`,
    });
    const firstScroll = await waitForDocument(
      page.session,
      `(async () => {
        const selected = document.querySelector("[data-testid='session-card'][data-selected='true']");
        const list = document.querySelector(".session-list");
        const overview = document.querySelector(".overview");
        if (!selected || location.pathname === ${JSON.stringify(secondScroll.result.value.path)}) return null;
        await new Promise((resolve) => setTimeout(resolve, 320));
        for (const [panel, height] of [[list, 600], [overview, 600]]) {
          const probe = document.createElement("div");
          probe.dataset.scrollProbe = "true";
          probe.style.height = height + "px";
          probe.setAttribute("aria-hidden", "true");
          panel.appendChild(probe);
        }
        list.scrollTop = Math.min(40, list.scrollHeight - list.clientHeight);
        overview.scrollTop = Math.min(90, overview.scrollHeight - overview.clientHeight);
        await new Promise(requestAnimationFrame);
        await new Promise(requestAnimationFrame);
        return {
          path: location.pathname,
          list: list.scrollTop,
          overview: overview.scrollTop,
        };
      })()`,
      "first Session scroll state",
    );
    assert.ok(firstScroll.list > 0, JSON.stringify(firstScroll));
    assert.ok(firstScroll.overview > 0, JSON.stringify(firstScroll));
    await page.session.send("Runtime.evaluate", {
      expression: "history.back()",
    });
    const restoredSecond = await waitForDocument(
      page.session,
      `(() => {
        const list = document.querySelector(".session-list");
        const overview = document.querySelector(".overview");
        if (location.pathname !== ${JSON.stringify(secondScroll.result.value.path)}) return null;
        if (
          list.scrollTop !== ${secondScroll.result.value.list} ||
          overview.scrollTop !== ${secondScroll.result.value.overview}
        ) return null;
        return { list: list.scrollTop, overview: overview.scrollTop };
      })()`,
      "restored second Session scroll",
    );
    assert.equal(restoredSecond.list, secondScroll.result.value.list, JSON.stringify(restoredSecond));
    assert.equal(
      restoredSecond.overview,
      secondScroll.result.value.overview,
      JSON.stringify(restoredSecond),
    );
    await page.session.send("Runtime.evaluate", {
      expression: "history.forward()",
    });
    const restoredFirst = await waitForDocument(
      page.session,
      `(() => {
        const list = document.querySelector(".session-list");
        const overview = document.querySelector(".overview");
        if (location.pathname !== ${JSON.stringify(firstScroll.path)}) return null;
        if (
          list.scrollTop !== ${firstScroll.list} ||
          overview.scrollTop !== ${firstScroll.overview}
        ) return null;
        return { list: list.scrollTop, overview: overview.scrollTop };
      })()`,
      "restored first Session scroll through history",
    );
    assert.equal(restoredFirst.list, firstScroll.list, JSON.stringify(restoredFirst));
    assert.equal(restoredFirst.overview, firstScroll.overview, JSON.stringify(restoredFirst));

    await installCookie(page, await sessionCookie());
    await page.session.send("Page.reload");
    await new Promise((resolve) => setTimeout(resolve, 1000));
    const reloadDiagnostics = await page.session.send("Runtime.evaluate", {
      expression: `({
        href: location.href,
        list: Boolean(document.querySelector(".session-list")),
        text: document.body.textContent.slice(0, 120),
        overview: Boolean(document.querySelector(".overview"))
      })`,
      returnByValue: true,
    });
    assert.equal(reloadDiagnostics.result.value.list, true, JSON.stringify(reloadDiagnostics.result.value));
    assert.equal(reloadDiagnostics.result.value.overview, true, JSON.stringify(reloadDiagnostics.result.value));
    const reloadedScroll = await waitForDocument(
      page.session,
      `(() => {
        const list = document.querySelector(".session-list");
        const overview = document.querySelector(".overview");
        if (!list || !overview || list.scrollTop !== 0 || overview.scrollTop !== 0) {
          return null;
        }
        return { list: list.scrollTop, overview: overview.scrollTop };
      })()`,
      "reloaded scroll reset",
    );
    assert.equal(reloadedScroll.list, 0, JSON.stringify(reloadedScroll));
    assert.equal(reloadedScroll.overview, 0, JSON.stringify(reloadedScroll));

    const scroll = await page.session.send("Runtime.evaluate", {
      expression: `(async () => {
        const overview = document.querySelector(".overview");
        const started = performance.now();
        const frames = [];
        let previous = started;
        for (let index = 0; index < 120; index += 1) {
          await new Promise(requestAnimationFrame);
          const now = performance.now();
          frames.push(now - previous);
          previous = now;
          overview.scrollTop = (overview.scrollHeight - overview.clientHeight) *
            (index / 119);
        }
        return {
          average: frames.reduce((sum, value) => sum + value, 0) / frames.length,
          max: Math.max(...frames),
        };
      })()`,
      awaitPromise: true,
      returnByValue: true,
    });
    assert.ok(
      scroll.result.value.average <= PERFORMANCE_BUDGETS.scrollFrameAverageMs,
      JSON.stringify(scroll.result.value),
    );

    await installCookie(page, await sessionCookie());
    const largestTargetAgents =
      performanceSource === "local"
        ? Number(largestLocalSession.agents)
        : SYNTHETIC_LARGEST_TREE.agents;
    const largestReadyStarted = Date.now();
    await page.session.send("Page.navigate", {
      url:
        performanceSource === "local"
          ? `${baseUrl}/sessions/${encodeURIComponent(largestLocalSession.id)}`
          : `${baseUrl}/agent-tree-demo?variant=stress`,
    });
    const collapsed = await waitForDocument(
      page.session,
      `(() => {
        const collapse = document.querySelector("[data-testid='agent-tree'] .rf-agent.collapse");
        const nodes = document.querySelectorAll("[data-testid='agent-tree'] .vue-flow__node").length;
        return collapse ? { label: collapse.textContent.trim(), nodes } : null;
      })()`,
      "61-agent collapse node",
    );
    const largestReadyMs = Date.now() - largestReadyStarted;
    assert.ok(
      largestReadyMs <= PERFORMANCE_BUDGETS.largestTreeReadyMs,
      JSON.stringify({ largestReadyMs }),
    );
    assert.match(collapsed.label, /子 agent/);
    const expansion = await page.session.send("Runtime.evaluate", {
      expression: `(async () => {
        const target = ${largestTargetAgents};
        const collapse = document.querySelector("[data-testid='agent-tree'] .rf-agent.collapse");
        const started = performance.now();
        collapse.click();
        while (performance.now() - started < 1000) {
          const count = document.querySelectorAll("[data-testid='agent-tree'] .vue-flow__node").length;
          if (count === target) return { count, duration: performance.now() - started };
          await new Promise(requestAnimationFrame);
        }
        return {
          count: document.querySelectorAll("[data-testid='agent-tree'] .vue-flow__node").length,
          duration: performance.now() - started,
        };
      })()`,
      awaitPromise: true,
      returnByValue: true,
    });
    assert.equal(
      expansion.result.value.count,
      largestTargetAgents,
      JSON.stringify(expansion.result.value),
    );
    assert.ok(
      expansion.result.value.duration <= PERFORMANCE_BUDGETS.treeExpandMs,
      JSON.stringify(expansion.result.value),
    );

    const longTasks = await page.session.send("Runtime.evaluate", {
      expression: `window.__perfLongTasks ?? []`,
      returnByValue: true,
    });
    const maxLongTask = Math.max(0, ...longTasks.result.value);
    assert.ok(
      maxLongTask <= PERFORMANCE_BUDGETS.longTaskMs,
      JSON.stringify({ maxLongTask }),
    );
    assert.deepEqual(violations, [], violations.join("\n"));

    const browserVersion = await page.session.send("Browser.getVersion");
    const largestAgents =
      performanceSource === "local"
        ? Number(largestLocalSession.agents)
        : SYNTHETIC_LARGEST_TREE.agents;
    const largestLines =
      performanceSource === "local"
        ? Number(largestLocalSession.lines)
        : SYNTHETIC_LARGEST_TREE.lines;
    const report = {
      source: performanceSource,
      budgets: PERFORMANCE_BUDGETS,
      dataOrigin:
        performanceSource === "local"
          ? "local-import-replay"
          : "synthetic-fixture",
      browser: {
        deviceScaleFactor: 1,
        product: browserVersion.product,
        protocolVersion: browserVersion.protocolVersion,
        userAgent: browserVersion.userAgent,
      },
      largestTree: {
        agents: largestAgents,
        lines: largestLines,
        expandMs: Math.round(expansion.result.value.duration),
        readyMs: largestReadyMs,
      },
      navigation: {
        cardsReadyMs: readyMs,
        graphReadyMs: Date.now() - navigationStarted,
        treeRequestAfterCards: treeRequests[0].at >= cardsReadyAt,
      },
      phases: {
        cardsReady: { at: cardsReadyAt, ms: readyMs },
        collapseExpand: {
          at: largestReadyStarted,
          ms: Math.round(expansion.result.value.duration),
        },
        interaction: { at: cardsReadyAt, ms: Math.round(interactionMs) },
        largestReady: { at: largestReadyStarted, ms: largestReadyMs },
        scroll: { ms: Number(scroll.result.value.average.toFixed(2)) },
      },
      requests: {
        selectedSessionId,
        detailCount: detailRequests.filter(
          (entry) => entry.sessionId === selectedSessionId,
        ).length,
        treeCount: treeRequests.filter(
          (entry) => entry.sessionId === selectedSessionId,
        ).length,
      },
      interactionMs: Math.round(interactionMs),
      scrollFrameAverageMs: Number(scroll.result.value.average.toFixed(2)),
      maxLongTaskMs: Number(maxLongTask.toFixed(2)),
      viewport: { height: 360, width: 1408 },
    };
    const artifactDir = process.env.HE_E2E_ARTIFACT_DIR;
    if (artifactDir) {
      await mkdir(artifactDir, { recursive: true });
      await writeFile(
        path.join(artifactDir, "m3-session-performance.json"),
        `${JSON.stringify(report, null, 2)}\n`,
      );
    }
  } finally {
    await page.close();
  }
});
