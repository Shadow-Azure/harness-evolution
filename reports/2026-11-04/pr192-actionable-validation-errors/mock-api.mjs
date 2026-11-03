import { createServer } from "node:http";

const port = Number(process.env.MOCK_API_PORT ?? 18787);
const user = {
  id: "user-smoke",
  username: "smokeadmin",
  displayName: "冒烟管理员",
  role: "admin",
  mustChangePassword: false,
};

function json(response, status, payload) {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(payload));
}

function readBody(request) {
  return new Promise((resolve) => {
    let raw = "";
    request.on("data", (chunk) => {
      raw += chunk;
    });
    request.on("end", () => resolve(raw));
  });
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url, `http://127.0.0.1:${port}`);
  console.log(`${request.method} ${url.pathname}`);

  if (request.method === "POST" && url.pathname === "/api/auth/login") {
    const body = await readBody(request);
    const password = JSON.parse(body || "{}").password;
    if (password === "smoke-password") {
      return json(response, 200, { accessToken: "smoke-token", expiresIn: 3600, user });
    }
    return json(response, 422, {
      error: {
        code: "VALIDATION_INVALID",
        message: "request validation failed",
        details: {
          errors: [
            {
              loc: ["body", "password"],
              msg: "String should match pattern",
              type: "string_pattern_mismatch",
            },
          ],
        },
      },
    });
  }
  if (url.pathname === "/api/auth/me") return json(response, 200, user);
  if (url.pathname === "/api/health") {
    return json(response, 200, {
      service: "harness-evolution",
      version: "smoke",
      ok: true,
      phase: "demo",
      db: { ok: true, latencyMs: 1, dialect: "sqlite" },
    });
  }
  if (url.pathname === "/api/sessions") return json(response, 200, { items: [] });
  if (url.pathname === "/api/evolution/runs") {
    return json(response, 200, { running: [], history: [] });
  }
  if (url.pathname === "/api/catalogs/targets") {
    return json(response, 200, {
      skill: [
        {
          id: "tgt-smoke",
          name: "deep-research",
          repoUrl: "https://git.example.com/skills.git",
          subDir: "skills/deep-research",
          defaultRef: "v2.0.0",
          versions: ["v2.0.0", "v1.9.0"],
        },
      ],
      agent: [],
    });
  }
  if (url.pathname === "/api/catalogs/models") {
    return json(response, 200, { items: [] });
  }
  if (url.pathname === "/api/evolution/targets/tgt-smoke/versions") {
    return json(response, 200, {
      versions: ["v2.0.0", "v1.9.0"],
      defaultRef: "v2.0.0",
    });
  }
  if (request.method === "POST" && url.pathname === "/api/evolution/probes/query") {
    return json(response, 422, {
      error: {
        code: "VALIDATION_INVALID",
        message: "request validation failed",
        details: {
          errors: [{ loc: ["body", "to"], msg: "Field required", type: "missing" }],
        },
      },
    });
  }
  if (url.pathname === "/api/acquisition/status") {
    return json(response, 200, {
      activeJobId: null,
      status: "idle",
      payloadTable: "trajectory_payloads",
      pending: 3,
      processed: 8,
      imported: 4,
      skipped: 1,
      lastRunAt: "2026-11-04T00:00:00+08:00",
      nextRunAt: "2026-11-04T00:01:00+08:00",
      errors: [],
      badCaseSync: {
        total: 12,
        synced: 7,
        unsynced: 5,
        syncing: 0,
        failed: 0,
        status: "idle",
        lastRunAt: "2026-11-04T00:00:00+08:00",
        lastError: null,
      },
      badCaseCatalogSync: {
        synced: 128,
        unsynced: 8,
        lastBadCaseId: 128,
        status: "idle",
        lastRunAt: "2026-11-04T00:00:00+08:00",
        lastError: null,
      },
      badCaseAnalysis: {
        total: 136,
        analyzed: 96,
        pending: 40,
        issue: 58,
        nonIssue: 38,
      },
    });
  }
  if (request.method === "POST" && url.pathname === "/api/acquisition/sync") {
    return json(response, 500, {
      error: { code: "INTERNAL", message: "sync upstream unavailable" },
    });
  }
  if (request.method === "POST" && url.pathname === "/api/evolution/targets") {
    return json(response, 500, {
      error: { code: "INTERNAL", message: "target persistence failed" },
    });
  }
  if (url.pathname === "/api/evolution/targets") {
    return json(response, 200, { items: [] });
  }
  return json(response, 404, {
    error: { code: "NOT_FOUND", message: "route not found" },
  });
});

server.listen(port, "127.0.0.1", () => {
  console.log(`mock api listening on http://127.0.0.1:${port}`);
});
