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

const workspaceId = "ws-test";

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
  validationProjectId: "val-deep-research",
  testProjectId: "test-deep-research",
  enabled: true,
};

describe("evolution target API", () => {
  it("lists workspace targets and reads both workspace catalogs", async () => {
    server.use(
      http.get(`/api/workspaces/${workspaceId}/evolution/targets`, () =>
        HttpResponse.json({ items: [target] }),
      ),
      http.get(`/api/workspaces/${workspaceId}/catalogs/targets`, () =>
        HttpResponse.json({
          skill: [
            { ...target, name: target.objectName, versions: ["v1"] },
          ],
          agent: [],
        }),
      ),
      http.get(`/api/workspaces/${workspaceId}/catalogs/models`, () =>
        HttpResponse.json({
          items: [{ model: "glm-5.3", sessionCount: 2, agentCount: 3 }],
        }),
      ),
    );

    await expect(listEvolutionTargets(workspaceId)).resolves.toEqual({
      items: [target],
    });
    await expect(getTargetCatalog(workspaceId)).resolves.toMatchObject({
      skill: [{ id: "target-1", versions: ["v1"] }],
      agent: [],
    });
    await expect(getModelCatalog(workspaceId)).resolves.toEqual({
      items: [{ model: "glm-5.3", sessionCount: 2, agentCount: 3 }],
    });
  });

  it("creates a target with the exact JSON body", async () => {
    let received: unknown;
    server.use(
      http.post(
        `/api/workspaces/${workspaceId}/evolution/targets`,
        async ({ request }) => {
          received = await request.json();
          expect(request.headers.get("content-type")).toContain(
            "application/json",
          );
          return HttpResponse.json(target, { status: 201 });
        },
      ),
    );
    const body = {
      objectType: "skill" as const,
      objectName: target.objectName,
      repoUrl: target.repoUrl,
      subDir: target.subDir,
      defaultRef: target.defaultRef,
      validationProjectId: target.validationProjectId,
      testProjectId: target.testProjectId,
      enabled: true,
    };

    await expect(createEvolutionTarget(workspaceId, body)).resolves.toEqual(
      target,
    );
    expect(received).toEqual(body);
  });

  it("encodes workspace and target ids for update, delete, and versions", async () => {
    const seen: Array<{ method: string; path: string }> = [];
    let received: unknown;
    const base = `/api/workspaces/${workspaceId}/evolution/targets`;
    server.use(
      http.put(`${base}/:id`, async ({ params, request }) => {
        seen.push({
          method: request.method,
          path: new URL(request.url).pathname,
        });
        received = await request.json();
        return HttpResponse.json({ ...target, id: String(params.id) });
      }),
      http.delete(`${base}/:id`, ({ request }) => {
        seen.push({
          method: request.method,
          path: new URL(request.url).pathname,
        });
        return new HttpResponse(null, { status: 204 });
      }),
      http.get(`${base}/:id/versions`, ({ request }) => {
        seen.push({
          method: request.method,
          path: new URL(request.url).pathname,
        });
        return HttpResponse.json({
          versions: ["v2.0.0", "v1.9.0"],
          defaultRef: "main",
        });
      }),
    );
    const body = {
      objectType: "skill" as const,
      objectName: target.objectName,
      repoUrl: target.repoUrl,
      subDir: target.subDir,
      defaultRef: target.defaultRef,
      validationProjectId: target.validationProjectId,
      testProjectId: target.testProjectId,
      enabled: false,
    };

    await updateEvolutionTarget(workspaceId, "target/with space", body);
    expect(received).toEqual(body);
    await deleteEvolutionTarget(workspaceId, "target/with space");
    await expect(
      listEvolutionTargetVersions(workspaceId, "target/with space"),
    ).resolves.toEqual({
      versions: ["v2.0.0", "v1.9.0"],
      defaultRef: "main",
    });
    expect(seen).toEqual([
      {
        method: "PUT",
        path: `${base}/target%2Fwith%20space`,
      },
      {
        method: "DELETE",
        path: `${base}/target%2Fwith%20space`,
      },
      {
        method: "GET",
        path: `${base}/target%2Fwith%20space/versions`,
      },
    ]);
  });
});
