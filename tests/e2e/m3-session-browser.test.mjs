import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
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
const secret = "m3-session-browser-signing-secret-with-sufficient-length";
let api;
let web;
let dataDir;
let baseUrl;
let apiLogs = "";
let webLogs = "";
let currentAdminPassword = "m3-session-browser-initial-password";
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

async function browserRefreshCookie(page) {
  const cookies = await page.session.send("Network.getCookies", {
    urls: [`${baseUrl}/api/auth`],
  });
  const cookie = cookies.cookies.find(
    (candidate) => candidate.name === "refresh_token",
  );
  assert.ok(cookie, "expected a refresh cookie in the browser");
  return cookie.value;
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
  const seeded = spawnSync(pnpm, ["fixtures:seed"], {
    cwd: root,
    env: baseEnv,
    encoding: "utf8",
  });
  assert.equal(seeded.status, 0, seeded.stderr || seeded.stdout);

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
          return selected && nodes > 0 ? { path: location.pathname, nodes } : null;
        })()`,
        `Agent tree for session ${index + 1}`,
      );
      assert.match(tree.path, /^\/sessions\/.+/);
      treeCounts.push(tree.nodes);
      if (!keyboardCheck && tree.nodes > 1) {
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
          const button = [...document.querySelectorAll("[data-testid='agent-tree'] .rf-agent")]
            .find((candidate) =>
              candidate.querySelector(".rf-cnode.skill, .rf-cnode.agent, .rf-cnode.workflow")
            );
          const node = button?.closest(".vue-flow__node");
          const agentId = node?.getAttribute("data-id");
          const triggerCount = button?.querySelectorAll(".rf-cnode.skill, .rf-cnode.agent, .rf-cnode.workflow").length ?? 0;
          const rootId = location.pathname.split("/").filter(Boolean).at(-1);
          return agentId && rootId && triggerCount > 0
            ? { agentId, rootId, triggerCount, path: location.pathname }
            : null;
        })()`,
        returnByValue: true,
      });
      target = candidate.result.value;
    }
    assert.ok(target, "expected a Session Agent with an evidence trigger");
    cookie = await browserRefreshCookie(first);
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

    cookie = await browserRefreshCookie(first);
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
    cookie = await browserRefreshCookie(first);

    const otherAgent = await first.session.send("Runtime.evaluate", {
      expression: `(() => {
        const selected = document.querySelector("[data-testid='agent-tree'] .rf-agent[aria-pressed='true']");
        const other = [...document.querySelectorAll("[data-testid='agent-tree'] .rf-agent")]
          .find((node) => node !== selected);
        const id = other?.closest(".vue-flow__node")?.getAttribute("data-id");
        other?.click();
        return id ?? null;
      })()`,
      returnByValue: true,
    });
    assert.ok(otherAgent.result.value);
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
