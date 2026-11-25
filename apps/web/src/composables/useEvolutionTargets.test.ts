// @vitest-environment jsdom

import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount, type VueWrapper } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, ref } from "vue";

import { createAppQueryClient } from "../api/queryClient";
import { queryKeys } from "../api/queryKeys";
import {
  useEvolutionTargets,
  useEvolutionTargetVersions,
} from "./useEvolutionTargets";
import { server } from "../test/server";

const workspaceId = "ws-test";
const base = `/api/workspaces/${workspaceId}/evolution/targets`;

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
  primaryMetricKey: "resolved_rate",
  enabled: true,
};
const body = {
  objectType: "skill" as const,
  objectName: target.objectName,
  repoUrl: target.repoUrl,
  subDir: target.subDir,
  defaultRef: target.defaultRef,
  validationProjectId: target.validationProjectId,
  testProjectId: target.testProjectId,
  primaryMetricKey: target.primaryMetricKey,
  enabled: true,
};
const selectedTarget = ref<string | null>(null);

let client: QueryClient;
let model: ReturnType<typeof useEvolutionTargets>;
let versions: ReturnType<typeof useEvolutionTargetVersions>;
let wrapper: VueWrapper;

const Page = defineComponent({
  setup() {
    model = useEvolutionTargets(workspaceId);
    versions = useEvolutionTargetVersions(workspaceId, selectedTarget);
    return () => null;
  },
});

beforeEach(() => {
  server.use(
    http.get(base, () => HttpResponse.json({ items: [target] })),
  );
  client = createAppQueryClient();
  vi.spyOn(client, "invalidateQueries").mockResolvedValue();
  selectedTarget.value = null;
  wrapper = mount(Page, {
    global: { plugins: [[VueQueryPlugin, { queryClient: client }]] },
  });
});

afterEach(() => wrapper.unmount());

describe("useEvolutionTargets", () => {
  it("exposes the collection query", async () => {
    server.use(
      http.get(base, () => HttpResponse.json({ items: [target] })),
    );
    await vi.waitFor(() => expect(model.data.value?.items).toEqual([target]));
  });

  it("invalidates target, Skill resource and catalog prefixes after every successful mutation", async () => {
    server.use(
      http.post(base, () => HttpResponse.json(target, { status: 201 })),
      http.put(`${base}/:id`, () =>
        HttpResponse.json({ ...target, enabled: false }),
      ),
      http.delete(`${base}/:id`, () =>
        new HttpResponse(null, { status: 204 }),
      ),
    );
    const invalidate = vi.mocked(client.invalidateQueries);

    await model.createTarget(body);
    await model.updateTarget(target.id, { ...body, enabled: false });
    await model.deleteTarget(target.id);

    expect(invalidate).toHaveBeenCalledTimes(9);
    expect(
      invalidate.mock.calls.map(([argument]) => {
        const filters = typeof argument === "function" ? argument() : argument;
        return filters?.queryKey;
      }),
    ).toEqual([
      queryKeys.evolutionTargets(workspaceId),
      ["skill-resource", workspaceId],
      queryKeys.catalogs(workspaceId),
      queryKeys.evolutionTargets(workspaceId),
      ["skill-resource", workspaceId],
      queryKeys.catalogs(workspaceId),
      queryKeys.evolutionTargets(workspaceId),
      ["skill-resource", workspaceId],
      queryKeys.catalogs(workspaceId),
    ]);
  });

  it("propagates ApiError and does not invalidate after a failed mutation", async () => {
    server.use(
      http.post(base, () =>
        HttpResponse.json(
          { error: { code: "REPO_INVALID", message: "repo invalid", details: {} } },
          { status: 422 },
        ),
      ),
    );

    await expect(model.createTarget(body)).rejects.toMatchObject({
      status: 422,
      code: "REPO_INVALID",
    });
    expect(client.invalidateQueries).not.toHaveBeenCalled();
  });

  it("does not invalidate after failed update or delete", async () => {
    server.use(
      http.put(`${base}/:id`, () =>
        HttpResponse.json(
          { error: { code: "REPO_INVALID", message: "repo invalid", details: {} } },
          { status: 422 },
        ),
      ),
      http.delete(`${base}/:id`, () =>
        HttpResponse.json(
          { error: { code: "TARGET_IN_USE", message: "target in use", details: {} } },
          { status: 409 },
        ),
      ),
    );

    await expect(
      model.updateTarget(target.id, { ...body, enabled: false }),
    ).rejects.toMatchObject({
      status: 422,
      code: "REPO_INVALID",
    });
    await expect(model.deleteTarget(target.id)).rejects.toMatchObject({
      status: 409,
      code: "TARGET_IN_USE",
    });
    expect(client.invalidateQueries).not.toHaveBeenCalled();
  });
});

describe("useEvolutionTargetVersions", () => {
  it("loads remote tags for the selected target", async () => {
    server.use(
      http.get(`${base}/:id/versions`, () =>
        HttpResponse.json({
          versions: ["v2.0.0", "v1.9.0"],
          defaultRef: "main",
        }),
      ),
    );
    selectedTarget.value = target.id;

    await vi.waitFor(() =>
      expect(versions.data.value).toEqual({
        versions: ["v2.0.0", "v1.9.0"],
        defaultRef: "main",
      }),
    );
  });
});
