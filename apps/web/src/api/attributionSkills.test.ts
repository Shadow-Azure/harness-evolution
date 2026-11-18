// @vitest-environment jsdom

import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { server } from "../test/server";
import {
  bindTargetAttributionSkill,
  getTargetAttributionSkill,
  listAttributionSkills,
  unbindTargetAttributionSkill,
} from "./attributionSkills";

const workspaceId = "ws skill";
const targetId = "target/one";
const base = "/api/workspaces/:workspaceId/evolution";

const effective = {
  id: "revision-2",
  skillId: "skill-1",
  workspaceId: "ws skill",
  skillKey: "root-cause",
  displayName: "Root cause",
  description: "",
  builtIn: false,
  enabled: true,
  revision: 2,
  content: { instructions: "analyze" },
  contentHash: "a".repeat(64),
  executorType: "agent_stub",
  outputSchemaVersion: "probe-report/v2",
  status: "published",
  source: "target",
};

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("attribution Skill API", () => {
  it("lists revisions and encodes workspace identity", async () => {
    server.use(
      http.get(`${base}/attribution-skills`, ({ params }) => {
        expect(params.workspaceId).toBe(workspaceId);
        return HttpResponse.json({ items: [effective] });
      }),
    );

    const result = await listAttributionSkills(workspaceId);

    expect(result.items[0]?.skillKey).toBe("root-cause");
  });

  it("reads, binds, and unbinds the target revision", async () => {
    let selected = "";
    let removed = false;
    server.use(
      http.get(`${base}/targets/:targetId/attribution-skill`, ({ params }) => {
        expect(params.targetId).toBe(targetId);
        return HttpResponse.json(effective);
      }),
      http.put(`${base}/targets/:targetId/attribution-skill`, async ({ request }) => {
        selected = String((await request.json() as { skillRevisionId: string }).skillRevisionId);
        return HttpResponse.json(effective);
      }),
      http.delete(`${base}/targets/:targetId/attribution-skill`, () => {
        removed = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    expect((await getTargetAttributionSkill(workspaceId, targetId)).source).toBe("target");
    await bindTargetAttributionSkill(workspaceId, targetId, {
      skillRevisionId: "revision-2",
    });
    await unbindTargetAttributionSkill(workspaceId, targetId);

    expect(selected).toBe("revision-2");
    expect(removed).toBe(true);
  });
});
