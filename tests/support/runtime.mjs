import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";

const chromeCandidates = [
  process.env.CHROME_BIN,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome",
  "/usr/bin/google-chrome-stable",
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
].filter(Boolean);

/**
 * Forward child output without blocking the test process.
 * @param {import("node:child_process").ChildProcess} child Process to observe.
 * @param {(chunk: string) => void} append Destination for decoded output.
 * @returns {void}
 */
export function capture(child, append) {
  child.stdout?.on("data", (chunk) => append(String(chunk)));
  child.stderr?.on("data", (chunk) => append(String(chunk)));
}

/**
 * Allocate one loopback port that can be handed to a child process.
 * @returns {Promise<number>} Available TCP port.
 */
export async function availablePort() {
  return await new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close();
        reject(new Error("failed to allocate a local port"));
        return;
      }
      const { port } = address;
      server.close((error) => (error ? reject(error) : resolve(port)));
    });
  });
}

/**
 * Poll a URL until the expected response arrives or the child exits.
 * @param {string} url Loopback URL to probe.
 * @param {import("node:child_process").ChildProcess} child Process owning the URL.
 * @param {() => string} logs Current child output for diagnostics.
 * @param {(response: Response) => boolean} [accept] Accepted response predicate.
 * @returns {Promise<Response>} First accepted response.
 */
export async function waitFor(
  url,
  child,
  logs,
  accept = (response) => response.ok,
) {
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`process exited before ${url} was ready:\n${logs()}`);
    }
    try {
      const response = await fetch(url);
      if (accept(response)) return response;
    } catch {
      // The child has not bound its port yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`timed out waiting for ${url}:\n${logs()}`);
}

/**
 * Terminate one detached process tree with a bounded kill escalation.
 * @param {import("node:child_process").ChildProcess | undefined} child Process to stop.
 * @returns {Promise<void>} Resolves after exit or forced kill.
 */
export async function stop(child) {
  if (!child) return;
  child.stdout?.destroy();
  child.stderr?.destroy();
  if (child.exitCode !== null) return;
  const signal = (command) => {
    if (process.platform === "win32") {
      child.kill(command);
      return;
    }
    try {
      process.kill(-child.pid, command);
    } catch {
      child.kill(command);
    }
  };
  await new Promise((resolve) => {
    const timer = setTimeout(() => {
      signal("SIGKILL");
      resolve();
    }, 5_000);
    child.once("exit", () => {
      clearTimeout(timer);
      resolve();
    });
    signal("SIGTERM");
  });
}

async function waitForValue(read, label, timeout = 20_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const value = await read();
    if (value) return value;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`timed out waiting for ${label}`);
}

function chromeExecutable() {
  const executable = chromeCandidates.find((candidate) => existsSync(candidate));
  if (!executable) {
    throw new Error(`Chrome executable not found; checked ${chromeCandidates.join(", ")}`);
  }
  return executable;
}

class CdpSession {
  constructor(url) {
    this.socket = new WebSocket(url);
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();
    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data));
      if (message.id) {
        const pending = this.pending.get(message.id);
        if (!pending) return;
        this.pending.delete(message.id);
        if (message.error) {
          pending.reject(new Error(`${pending.method}: ${message.error.message}`));
        } else {
          pending.resolve(message.result);
        }
        return;
      }
      for (const listener of this.listeners.get(message.method) ?? []) {
        listener(message.params);
      }
    });
  }

  async open() {
    if (this.socket.readyState === WebSocket.OPEN) return this;
    await new Promise((resolve, reject) => {
      this.socket.addEventListener("open", resolve, { once: true });
      this.socket.addEventListener("error", () => reject(new Error("CDP websocket failed")), {
        once: true,
      });
    });
    return this;
  }

  on(method, listener) {
    const listeners = this.listeners.get(method) ?? [];
    listeners.push(listener);
    this.listeners.set(method, listeners);
  }

  async send(method, params = {}) {
    const id = this.nextId++;
    const response = new Promise((resolve, reject) => {
      this.pending.set(id, { method, resolve, reject });
    });
    this.socket.send(JSON.stringify({ id, method, params }));
    return await response;
  }

  close() {
    this.socket.close();
  }
}

/**
 * Start an isolated headless Chrome page with Runtime and Log enabled.
 * @returns {Promise<{session: CdpSession, close: () => Promise<void>}>} Browser page.
 */
export async function createBrowserPage() {
  const debuggingPort = await availablePort();
  const profileDir = await mkdtemp(path.join(tmpdir(), "harness-chrome-"));
  let logs = "";
  const browser = spawn(
    chromeExecutable(),
    [
      "--headless=new",
      "--no-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
      "--disable-background-networking",
      "--no-first-run",
      "--no-default-browser-check",
      `--remote-debugging-port=${debuggingPort}`,
      `--user-data-dir=${profileDir}`,
      "about:blank",
    ],
    {
      detached: process.platform !== "win32",
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  capture(browser, (chunk) => {
    logs += chunk;
  });
  await waitFor(
    `http://127.0.0.1:${debuggingPort}/json/version`,
    browser,
    () => logs,
  );
  const response = await fetch(
    `http://127.0.0.1:${debuggingPort}/json/new?about:blank`,
    { method: "PUT" },
  );
  assert.equal(response.ok, true, `failed to create Chrome target:\n${logs}`);
  const target = await response.json();
  const session = await new CdpSession(target.webSocketDebuggerUrl).open();
  await Promise.all([
    session.send("Page.enable"),
    session.send("Runtime.enable"),
    session.send("Log.enable"),
  ]);
  return {
    session,
    async close() {
      session.close();
      await stop(browser);
      await rm(profileDir, {
        recursive: true,
        force: true,
        maxRetries: 10,
        retryDelay: 100,
      });
    },
  };
}

/**
 * Evaluate a browser expression until it returns a truthy value.
 * @param {CdpSession} session Browser session.
 * @param {string} expression JavaScript expression with serializable result.
 * @param {string} label Human-readable wait reason.
 * @returns {Promise<unknown>} First truthy expression result.
 */
export async function waitForDocument(session, expression, label) {
  return await waitForValue(async () => {
    const result = await session.send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    return result.result.value;
  }, label);
}

/**
 * Collect browser console, exception, and unexpected log entries.
 * @param {CdpSession} session Browser session.
 * @returns {string[]} Mutable violation list.
 */
export function browserViolations(session) {
  const violations = [];
  session.on("Runtime.consoleAPICalled", ({ type, args }) => {
    if (type === "warning" || type === "error") {
      violations.push(
        `${type}: ${args.map((arg) => arg.value ?? arg.description ?? "").join(" ")}`,
      );
    }
  });
  session.on("Runtime.exceptionThrown", ({ exceptionDetails }) => {
    violations.push(`exception: ${exceptionDetails.text} ${exceptionDetails.exception?.description ?? ""}`);
  });
  session.on("Log.entryAdded", ({ entry }) => {
    const expectedAuthProbe =
      entry.source === "network" &&
      /Failed to load resource: the server responded with a status of (401|404)/.test(
        entry.text,
      );
    if (!expectedAuthProbe && (entry.level === "warning" || entry.level === "error")) {
      violations.push(`${entry.level}: ${entry.text}`);
    }
  });
  return violations;
}
