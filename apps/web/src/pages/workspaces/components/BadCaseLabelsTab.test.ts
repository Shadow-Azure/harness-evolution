// @vitest-environment jsdom

import type {
  WorkspaceBadCaseLabelConfiguration,
  WorkspaceBadCaseLabelSuggestion,
} from "@harness/contracts";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { server } from "../../../test/server";
import { elementPlusComponents } from "../../../test/setup";
import BadCaseLabelsTab from "./BadCaseLabelsTab.vue";

const workspaceId = "ws-labels";
const base = `/api/workspaces/${workspaceId}`;
const suggestionsPath = `${base}/bad-case-labels/suggestions`;
const inputSelector = "[data-testid='bad-case-label-input']";
const wrappers: VueWrapper[] = [];

/** Debounce wired into the suggestion lookup; tests advance exactly this much. */
const SUGGESTION_DEBOUNCE_MS = 200;

/** Real timer captured before any test installs fake ones. */
const realSetTimeout = globalThis.setTimeout;

const topSuggestions: WorkspaceBadCaseLabelSuggestion[] = [
  { label: "review", badCaseCount: 12 },
  { label: "tool-use", badCaseCount: 7 },
  { label: "performance", badCaseCount: 2 },
];

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

/**
 * Register the empty candidate response every test starts from.
 * @returns No value.
 */
function registerDefaultSuggestions(): void {
  server.use(
    http.get(suggestionsPath, () => HttpResponse.json({ items: [] })),
  );
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

function suggestionLabels(wrapper: VueWrapper): string[] {
  return wrapper
    .findAll(".label-suggestion .label-suggestion-label")
    .map((node) => node.text());
}

/**
 * Let real macrotasks run so mocked fetch promises settle under fake timers.
 * @returns No value.
 */
async function settleRealTimers(): Promise<void> {
  for (let round = 0; round < 4; round += 1) {
    await new Promise<void>((resolve) => {
      realSetTimeout(resolve, 0);
    });
  }
}

/**
 * Advance the debounce and flush the mocked request behind it.
 * @returns No value.
 */
async function advanceSuggestions(): Promise<void> {
  await vi.advanceTimersByTimeAsync(SUGGESTION_DEBOUNCE_MS);
  await settleRealTimers();
}

beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
  registerDefaultSuggestions();
});
afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  server.resetHandlers();
  registerDefaultSuggestions();
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
    let current = config([]);
    server.use(
      http.get(`${base}/bad-case-labels`, () => HttpResponse.json(current)),
      http.put(`${base}/bad-case-labels`, async ({ request }) => {
        savedBody = await request.json();
        current = config(["review"], 3);
        return HttpResponse.json(current);
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

describe("Badcase 类型 label candidate dropdown", () => {
  it("shows the most common catalog labels when the empty input takes focus", async () => {
    server.use(
      http.get(`${base}/bad-case-labels`, () => HttpResponse.json(config([]))),
      http.get(suggestionsPath, () =>
        HttpResponse.json({ items: topSuggestions }),
      ),
    );
    const wrapper = await mountTab();
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    try {
      await wrapper.get(inputSelector).trigger("focus");
      await advanceSuggestions();

      const list = wrapper.get("[data-testid='bad-case-label-suggestions']");
      expect(list.attributes("role")).toBe("listbox");
      expect(suggestionLabels(wrapper)).toEqual([
        "review",
        "tool-use",
        "performance",
      ]);
      expect(
        wrapper.get("[data-testid='bad-case-label-suggestion-review']").text(),
      ).toContain("12 条");
      expect(wrapper.get(inputSelector).attributes("aria-expanded")).toBe(
        "true",
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("queries the typed prefix only after the 200ms debounce", async () => {
    const queries: Array<string | null> = [];
    server.use(
      http.get(`${base}/bad-case-labels`, () => HttpResponse.json(config([]))),
      http.get(suggestionsPath, ({ request }) => {
        const q = new URL(request.url).searchParams.get("q");
        queries.push(q);
        return HttpResponse.json({
          items:
            q === "rev"
              ? [{ label: "review", badCaseCount: 12 }]
              : topSuggestions,
        });
      }),
    );
    const wrapper = await mountTab();
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    try {
      await wrapper.get(inputSelector).setValue("rev");
      await vi.advanceTimersByTimeAsync(SUGGESTION_DEBOUNCE_MS - 1);
      expect(queries).toEqual([]);

      await vi.advanceTimersByTimeAsync(1);
      await settleRealTimers();
      expect(queries).toEqual(["rev"]);
      expect(suggestionLabels(wrapper)).toEqual(["review"]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("hides labels already configured in the draft", async () => {
    server.use(
      http.get(`${base}/bad-case-labels`, () =>
        HttpResponse.json(config(["review"])),
      ),
      http.get(suggestionsPath, () =>
        HttpResponse.json({ items: topSuggestions }),
      ),
    );
    const wrapper = await mountTab();
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    try {
      await wrapper.get(inputSelector).trigger("focus");
      await advanceSuggestions();

      expect(suggestionLabels(wrapper)).toEqual(["tool-use", "performance"]);
      expect(chipLabels(wrapper)).toEqual(["review"]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("adds a clicked candidate to the draft without saving", async () => {
    let putCalls = 0;
    server.use(
      http.get(`${base}/bad-case-labels`, () => HttpResponse.json(config([]))),
      http.put(`${base}/bad-case-labels`, () => {
        putCalls += 1;
        return HttpResponse.json(config(["review"], 1));
      }),
      http.get(suggestionsPath, () =>
        HttpResponse.json({ items: topSuggestions }),
      ),
    );
    const wrapper = await mountTab();
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    try {
      await wrapper.get(inputSelector).trigger("focus");
      await advanceSuggestions();

      await wrapper
        .get("[data-testid='bad-case-label-suggestion-review']")
        .trigger("click");

      expect(chipLabels(wrapper)).toEqual(["review"]);
      expect(putCalls).toBe(0);
      expect(wrapper.find("[data-testid='bad-case-label-dirty']").exists()).toBe(
        true,
      );
      expect(
        wrapper.get("[data-testid='save-bad-case-labels']").attributes("disabled"),
      ).toBeUndefined();
      expect(
        wrapper.find("[data-testid='bad-case-label-suggestion-review']").exists(),
      ).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it("adds the highlighted candidate on Enter", async () => {
    let putCalls = 0;
    server.use(
      http.get(`${base}/bad-case-labels`, () => HttpResponse.json(config([]))),
      http.put(`${base}/bad-case-labels`, () => {
        putCalls += 1;
        return HttpResponse.json(config(["review"], 1));
      }),
      http.get(suggestionsPath, () =>
        HttpResponse.json({ items: topSuggestions }),
      ),
    );
    const wrapper = await mountTab();
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    try {
      await wrapper.get(inputSelector).trigger("focus");
      await advanceSuggestions();
      await wrapper.get(inputSelector).trigger("keydown.down");

      expect(
        wrapper
          .get("[data-testid='bad-case-label-suggestion-review']")
          .attributes("aria-selected"),
      ).toBe("true");

      await wrapper.get(inputSelector).trigger("keyup.enter");

      expect(chipLabels(wrapper)).toEqual(["review"]);
      expect(putCalls).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("falls back to the typed label on Enter without a highlight", async () => {
    const wrapper = await mountTab();

    await wrapper.get(inputSelector).setValue("brand-new");
    await wrapper.get(inputSelector).trigger("keyup.enter");

    expect(chipLabels(wrapper)).toEqual(["brand-new"]);
    expect(wrapper.find("[data-testid='bad-case-label-dirty']").exists()).toBe(
      true,
    );
  });

  it("closes the dropdown on Escape without touching the input", async () => {
    server.use(
      http.get(`${base}/bad-case-labels`, () => HttpResponse.json(config([]))),
      http.get(suggestionsPath, () =>
        HttpResponse.json({ items: topSuggestions }),
      ),
    );
    const wrapper = await mountTab();
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    try {
      await wrapper.get(inputSelector).trigger("focus");
      await advanceSuggestions();
      expect(
        wrapper.find("[data-testid='bad-case-label-suggestions']").exists(),
      ).toBe(true);

      await wrapper.get(inputSelector).trigger("keydown.esc");

      expect(
        wrapper.find("[data-testid='bad-case-label-suggestions']").exists(),
      ).toBe(false);
      expect(wrapper.get(inputSelector).attributes("aria-expanded")).toBe(
        "false",
      );
      expect(chipLabels(wrapper)).toEqual([]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("degrades silently when the candidate endpoint fails", async () => {
    let savedBody: unknown = null;
    server.use(
      http.get(`${base}/bad-case-labels`, () => HttpResponse.json(config([]))),
      http.put(`${base}/bad-case-labels`, async ({ request }) => {
        savedBody = await request.json();
        return HttpResponse.json(config(["review"], 1));
      }),
      http.get(suggestionsPath, () =>
        HttpResponse.json(
          { error: { code: "INTERNAL_ERROR", message: "boom" } },
          { status: 500 },
        ),
      ),
    );
    const wrapper = await mountTab();
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    try {
      await wrapper.get(inputSelector).trigger("focus");
      await advanceSuggestions();

      expect(
        wrapper.find("[data-testid='bad-case-label-suggestions']").exists(),
      ).toBe(false);
      expect(wrapper.get(inputSelector).attributes("aria-expanded")).toBe(
        "false",
      );

      await wrapper.get(inputSelector).setValue("review");
      await wrapper.get(inputSelector).trigger("keyup.enter");
      expect(chipLabels(wrapper)).toEqual(["review"]);

      await wrapper.get("[data-testid='save-bad-case-labels']").trigger("click");
      await settleRealTimers();
      expect(savedBody).toEqual({ items: ["review"] });
    } finally {
      vi.useRealTimers();
    }
  });

  it("restores an empty input and closed dropdown after leaving the tab", async () => {
    server.use(
      http.get(`${base}/bad-case-labels`, () => HttpResponse.json(config([]))),
      http.get(suggestionsPath, () =>
        HttpResponse.json({ items: topSuggestions }),
      ),
    );
    const client = newClient(30_000);
    const first = await mountTab(true, client);
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    try {
      await first.get(inputSelector).trigger("focus");
      await advanceSuggestions();
      await first.get(inputSelector).setValue("rev");
      await advanceSuggestions();
      expect(
        first.find("[data-testid='bad-case-label-suggestions']").exists(),
      ).toBe(true);

      first.unmount();
      wrappers.splice(wrappers.indexOf(first), 1);
    } finally {
      vi.useRealTimers();
    }

    const second = await mountTab(true, client);
    const input = second.get(inputSelector);
    expect((input.element as HTMLInputElement).value).toBe("");
    expect(input.attributes("aria-expanded")).toBe("false");
    expect(
      second.find("[data-testid='bad-case-label-suggestions']").exists(),
    ).toBe(false);
    expect(chipLabels(second)).toEqual([]);
    expect(second.get("[data-testid='no-bad-case-labels']").text()).toContain(
      "还没有配置 label",
    );
  });
});
