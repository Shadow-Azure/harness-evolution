// @vitest-environment jsdom

import type { WorkspaceBadCaseLabelConfiguration } from "@harness/contracts";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { server } from "../../../test/server";
import { elementPlusComponents } from "../../../test/setup";
import BadCaseLabelsTab from "./BadCaseLabelsTab.vue";

const workspaceId = "ws-labels";
const base = `/api/workspaces/${workspaceId}`;
const wrappers: VueWrapper[] = [];

function config(
  items: string[],
  assignedBadCaseCount = 0,
): WorkspaceBadCaseLabelConfiguration {
  return { items, assignedBadCaseCount };
}

function newClient(gcTime = 0): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { gcTime, retry: false } },
  });
}

async function mountTab(
  canManage = true,
  client: QueryClient = newClient(),
  wid: string = workspaceId,
): Promise<VueWrapper> {
  const wrapper = mount(BadCaseLabelsTab, {
    props: { workspaceId: wid, canManage },
    global: {
      components: elementPlusComponents,
      plugins: [[VueQueryPlugin, { queryClient: client }]],
    },
  });
  wrappers.push(wrapper);
  await flushPromises();
  return wrapper;
}

function chipLabels(wrapper: VueWrapper): string[] {
  return wrapper
    .findAll("[data-testid='bad-case-label-chips'] .chip")
    .map((chip) => chip.text().replace("×", "").trim());
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  server.resetHandlers();
});
afterAll(() => server.close());

describe("Badcase 类型 label management tab", () => {
  it("renders sorted chips and the assigned case count from the server", async () => {
    server.use(
      http.get(`${base}/bad-case-labels`, () =>
        HttpResponse.json(config(["code-review", "tool-use"], 142)),
      ),
    );
    const wrapper = await mountTab();

    const chips = wrapper
      .findAll("[data-testid='bad-case-label-chips'] .chip")
      .map((chip) => chip.text().replace("×", "").trim());
    expect(chips).toEqual(["code-review", "tool-use"]);
    expect(wrapper.get("[data-testid='bad-case-label-assigned-count']").text()).toBe(
      "已关联 142 条",
    );
  });

  it("adds a label through both the button and Enter, keeping lexical order", async () => {
    server.use(
      http.get(`${base}/bad-case-labels`, () => HttpResponse.json(config([]))),
    );
    const wrapper = await mountTab();

    await wrapper.get("[data-testid='bad-case-label-input']").setValue("zebra");
    await wrapper.get("[data-testid='bad-case-label-input']").trigger("keyup.enter");
    await flushPromises();

    await wrapper.get("[data-testid='bad-case-label-input']").setValue("alpha");
    await wrapper.get("[data-testid='add-bad-case-label']").trigger("click");
    await flushPromises();

    const chips = wrapper
      .findAll("[data-testid='bad-case-label-chips'] .chip")
      .map((chip) => chip.text().replace("×", "").trim());
    expect(chips).toEqual(["alpha", "zebra"]);
  });

  it("rejects duplicate, whitespace, empty, and oversize labels inline", async () => {
    server.use(
      http.get(`${base}/bad-case-labels`, () =>
        HttpResponse.json(config(["review"])),
      ),
    );
    const wrapper = await mountTab();

    const input = () => wrapper.get("[data-testid='bad-case-label-input']");
    const add = () => wrapper.get("[data-testid='add-bad-case-label']");
    const error = () => wrapper.get("[data-testid='bad-case-label-input-error']");

    await input().setValue("review");
    await add().trigger("click");
    expect(error().text()).toContain("已经添加");

    await input().setValue("  review  ");
    await add().trigger("click");
    expect(error().text()).toContain("首尾不能有空白");

    await input().setValue("   ");
    await add().trigger("click");
    expect(error().text()).toContain("不能为空");

    await input().setValue("x".repeat(129));
    await add().trigger("click");
    expect(error().text()).toContain("最多 128 个字符");

    expect(wrapper.findAll("[data-testid='bad-case-label-chips'] .chip")).toHaveLength(1);
  });

  it("tracks a dirty draft and saves a full replacement atomically", async () => {
    let savedBody: unknown = null;
    server.use(
      http.get(`${base}/bad-case-labels`, () => HttpResponse.json(config([]))),
      http.put(`${base}/bad-case-labels`, async ({ request }) => {
        savedBody = await request.json();
        return HttpResponse.json(config(["review"], 3));
      }),
    );
    const wrapper = await mountTab();

    expect(wrapper.find("[data-testid='bad-case-label-dirty']").exists()).toBe(false);

    await wrapper.get("[data-testid='bad-case-label-input']").setValue("review");
    await wrapper.get("[data-testid='add-bad-case-label']").trigger("click");
    await flushPromises();

    expect(wrapper.find("[data-testid='bad-case-label-dirty']").exists()).toBe(true);

    await wrapper.get("[data-testid='save-bad-case-labels']").trigger("click");
    await flushPromises();

    expect(savedBody).toEqual({ items: ["review"] });
    expect(wrapper.find("[data-testid='bad-case-label-dirty']").exists()).toBe(false);
  });

  it("shows the empty hint when no label is configured", async () => {
    server.use(
      http.get(`${base}/bad-case-labels`, () => HttpResponse.json(config([]))),
    );
    const wrapper = await mountTab();

    expect(wrapper.get("[data-testid='no-bad-case-labels']").text()).toContain(
      "还没有配置 label",
    );
  });

  it("keeps the save button disabled until a change is made", async () => {
    server.use(
      http.get(`${base}/bad-case-labels`, () =>
        HttpResponse.json(config(["review"], 2)),
      ),
    );
    const wrapper = await mountTab();
    const save = () => wrapper.get("[data-testid='save-bad-case-labels']");

    expect(save().attributes("disabled")).toBeDefined();

    await wrapper.get("[data-testid='bad-case-label-input']").setValue("tool-use");
    await wrapper.get("[data-testid='add-bad-case-label']").trigger("click");
    await flushPromises();
    expect(save().attributes("disabled")).toBeUndefined();

    await wrapper.get("[aria-label='移除 tool-use']").trigger("click");
    await flushPromises();
    expect(save().attributes("disabled")).toBeDefined();
  });

  it("discards unsaved edits when the tab is left and re-entered", async () => {
    server.use(
      http.get(`${base}/bad-case-labels`, () => HttpResponse.json(config([]))),
    );
    const client = newClient(30_000);

    const first = await mountTab(true, client);
    await first.get("[data-testid='bad-case-label-input']").setValue("review");
    await first.get("[data-testid='add-bad-case-label']").trigger("click");
    await flushPromises();
    expect(chipLabels(first)).toEqual(["review"]);
    expect(first.find("[data-testid='bad-case-label-dirty']").exists()).toBe(true);

    // Leaving the tab unmounts the editor; coming back must hydrate the saved
    // server snapshot (still empty) instead of the abandoned draft.
    first.unmount();
    wrappers.splice(wrappers.indexOf(first), 1);

    const second = await mountTab(true, client);
    expect(chipLabels(second)).toEqual([]);
    expect(second.find("[data-testid='bad-case-label-dirty']").exists()).toBe(false);
    expect(second.get("[data-testid='no-bad-case-labels']").text()).toContain(
      "还没有配置 label",
    );
  });

  it("keeps write controls hidden for read-only members while showing chips", async () => {
    server.use(
      http.get(`${base}/bad-case-labels`, () =>
        HttpResponse.json(config(["review"], 5)),
      ),
    );
    const wrapper = await mountTab(false);

    expect(wrapper.find("[data-testid='save-bad-case-labels']").exists()).toBe(false);
    expect(wrapper.find("[data-testid='bad-case-label-input']").exists()).toBe(false);
    expect(wrapper.find("[data-testid='add-bad-case-label']").exists()).toBe(false);
    expect(wrapper.find(".chip-remove").exists()).toBe(false);
    expect(wrapper.findAll("[data-testid='bad-case-label-chips'] .chip")).toHaveLength(1);
  });
});
