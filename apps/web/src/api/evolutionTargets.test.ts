// @vitest-environment jsdom

import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import {
  createEvolutionTarget,
  deleteEvolutionTarget,
  listEvolutionTargets,
  listEvolutionTargetVersions,
  updateEvolutionTarget,
} from "./evolutionTargets";
import { getModelCatalog, getTargetCatalog } from "./catalogs";
import { server } from "../test/server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const target = {
  id: "target-1",
  objectType: "skill" as const,
  objectName: "deep-research",
  repoUrl: "https://git.example.com/agent-skills.git",
  subDir: "skills/deep-research",
  defaultRef: "main",
  enabled: true,
};

describe("evolution target API", () => {
  it("lists targets and reads both catalogs", async () => {
    server.use(
      http.get("/api/evolution/targets", () => HttpResponse.json({ items: [target] })),
      http.get("/api/catalogs/targets", () =>
        HttpResponse.json({ skill: [{ ...target, name: target.objectName, versions: ["v1"] }], agent: [] }),
      ),
      http.get("/api/catalogs/models", () =>
        HttpResponse.json({ items: [{ model: "glm-5.3", sessionCount: 2, agentCount: 3 }] }),
      ),
    );

    await expect(listEvolutionTargets()).resolves.toEqual({ items: [target] });
    await expect(getTargetCatalog()).resolves.toMatchObject({
      skill: [{ id: "target-1", versions: ["v1"] }],
      agent: [],
    });
    await expect(getModelCatalog()).resolves.toEqual({
      items: [{ model: "glm-5.3", sessionCount: 2, agentCount: 3 }],
    });
  });

  it("creates a target with the exact JSON body", async () => {
    let received: unknown;
    server.use(
      http.post("/api/evolution/targets", async ({ request }) => {
        received = await request.json();
        expect(request.headers.get("content-type")).toContain("application/json");
        return HttpResponse.json(target, { status: 201 });
      }),
    );
    const body = {
      objectType: "skill" as const,
      objectName: target.objectName,
      repoUrl: target.repoUrl,
      subDir: target.subDir,
      defaultRef: target.defaultRef,
      enabled: true,
    };

    await expect(createEvolutionTarget(body)).resolves.toEqual(target);
    expect(received).toEqual(body);
  });

  it("encodes target ids for update, delete, and versions", async () => {
    const seen: Array<{ method: string; path: string }> = [];
    let received: unknown;
    server.use(
      http.put("/api/evolution/targets/:id", async ({ params, request }) => {
        seen.push({
          method: request.method,
          path: new URL(request.url).pathname,
        });
        received = await request.json();
        return HttpResponse.json({ ...target, id: String(params.id) });
      }),
      http.delete("/api/evolution/targets/:id", ({ request }) => {
        seen.push({
          method: request.method,
          path: new URL(request.url).pathname,
        });
        return new HttpResponse(null, { status: 204 });
      }),
      http.get("/api/evolution/targets/:id/versions", ({ request }) => {
        seen.push({
          method: request.method,
          path: new URL(request.url).pathname,
        });
        return HttpResponse.json({ versions: ["v2.0.0", "v1.9.0"], defaultRef: "main" });
      }),
    );
    const body = {
      objectType: "skill" as const,
      objectName: target.objectName,
      repoUrl: target.repoUrl,
      subDir: target.subDir,
      defaultRef: target.defaultRef,
      enabled: false,
    };

    await updateEvolutionTarget("target/with space", body);
    expect(received).toEqual(body);
    await deleteEvolutionTarget("target/with space");
    await expect(listEvolutionTargetVersions("target/with space")).resolves.toEqual({
      versions: ["v2.0.0", "v1.9.0"],
      defaultRef: "main",
    });
    expect(seen).toEqual([
      {
        method: "PUT",
        path: "/api/evolution/targets/target%2Fwith%20space",
      },
      {
        method: "DELETE",
        path: "/api/evolution/targets/target%2Fwith%20space",
      },
      {
        method: "GET",
        path: "/api/evolution/targets/target%2Fwith%20space/versions",
      },
    ]);
  });
});
