import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { after, before, test } from "node:test";

const root = process.cwd();
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
let api;
let web;
let webBaseUrl;
let apiLogs = "";
let webLogs = "";

function capture(child, append) {
  child.stdout.on("data", (chunk) => append(String(chunk)));
  child.stderr.on("data", (chunk) => append(String(chunk)));
}

async function availablePort() {
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

async function waitFor(url, child, logs) {
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`process exited before ${url} was ready:\n${logs()}`);
    }
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // The child has not bound its port yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`timed out waiting for ${url}:\n${logs()}`);
}

async function stop(child) {
  if (!child) return;
  child.stdout.destroy();
  child.stderr.destroy();
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

before(async () => {
  const apiPort = await availablePort();
  const webPort = await availablePort();
  webBaseUrl = `http://127.0.0.1:${webPort}`;

  api = spawn(process.execPath, ["scripts/run-api.mjs", "start"], {
    cwd: root,
    env: {
      ...process.env,
      HE_DOCS_ENABLED: "false",
      HE_HOST: "127.0.0.1",
      HE_PORT: String(apiPort),
      PYTHONUNBUFFERED: "1"
    },
    detached: process.platform !== "win32",
    stdio: ["ignore", "pipe", "pipe"]
  });
  capture(api, (chunk) => {
    apiLogs += chunk;
  });
  await waitFor(`http://127.0.0.1:${apiPort}/api/health`, api, () => apiLogs);

  web = spawn(
    pnpm,
    ["--filter", "@harness/web", "exec", "vite", "--host", "127.0.0.1", "--port", String(webPort), "--strictPort"],
    {
      cwd: root,
      env: {
        ...process.env,
        HE_API_PROXY_URL: `http://127.0.0.1:${apiPort}`
      },
      detached: process.platform !== "win32",
      stdio: ["ignore", "pipe", "pipe"]
    }
  );
  capture(web, (chunk) => {
    webLogs += chunk;
  });
  await waitFor(webBaseUrl, web, () => webLogs);
});

after(async () => {
  await stop(web);
  await stop(api);
});

test("health succeeds through the Vite proxy with the shared contract", async () => {
  const response = await fetch(`${webBaseUrl}/api/health`);
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.match(response.headers.get("x-request-id") ?? "", /\S/);
  assert.deepEqual(body, {
    ok: true,
    phase: "scaffold",
    service: "harness-evolution"
  });
});

test("protected API failures keep the unified envelope through the proxy", async () => {
  const response = await fetch(`${webBaseUrl}/api/sessions`);
  const body = await response.json();

  assert.equal(response.status, 401);
  assert.deepEqual(body, {
    error: {
      code: "AUTH_REQUIRED",
      details: {},
      message: "authentication is required"
    }
  });
});
