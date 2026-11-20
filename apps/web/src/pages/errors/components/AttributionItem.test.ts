// @vitest-environment jsdom

import { flushPromises, mount, RouterLinkStub } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AttributionItem as AttributionItemContract } from "@harness/contracts";

import AttributionItem from "./AttributionItem.vue";

const DIGEST = "digest:580c97cf8ca79018df6692fd4db3cc8193b44cc91e51d1f9127b5818f1bf107";

function attribution(
  overrides: Partial<AttributionItemContract> = {},
): AttributionItemContract {
  return {
    attributionId: "AT-0001",
    badCaseId: "case-1",
    objectType: "skill",
    objectName: "systematic-debugging",
    objectVersion: DIGEST,
    objectRef: "v6.4.1",
    objectCommit: "580c97c",
    conclusion: "attributed",
    category: "error",
    confidence: 0.8,
    runId: "run-1",
    isCached: true,
    reusedCount: 2,
    createdAt: "2026-11-19T23:00:00+08:00",
    updatedAt: "2026-11-19T23:00:00+08:00",
    ...overrides,
  };
}

function mountItem(overrides: Partial<AttributionItemContract> = {}) {
  return mount(AttributionItem, {
    attachTo: document.body,
    props: {
      wid: "ws-1",
      sessionId: "session-1",
      badCaseId: "case-1",
      attribution: attribution(overrides),
      active: false,
    },
    global: {
      stubs: { RouterLink: RouterLinkStub },
    },
  });
}

describe("AttributionItem", () => {
  beforeEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = "";
  });

  it("shows the run ref and short commit while keeping the digest copyable", () => {
    const wrapper = mountItem();
    const item = wrapper.get("[data-testid='attribution-item']");
    expect(item.text()).toContain("systematic-debugging");
    expect(item.text()).toContain("v6.4.1");
    expect(item.text()).toContain("580c97c");
    expect(item.text()).not.toContain(DIGEST);
    expect(wrapper.getComponent(RouterLinkStub).props("to")).toBe(
      "/workspaces/ws-1/sessions/session-1/errors?case=case-1&tab=attr&at=AT-0001",
    );
    expect(wrapper.get(".attr-link").attributes("aria-label")).toContain("v6.4.1 580c97c");
  });

  it("copies the full commit and reports success", async () => {
    const wrapper = mountItem();
    await wrapper.get(".ver-copy").trigger("click");
    await flushPromises();
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("580c97c");
    expect(wrapper.get(".ver-copy").classes()).toContain("copied");
  });

  it("falls back to the full digest when the run has no readable ref", async () => {
    const wrapper = mountItem({ objectRef: null, objectCommit: null });
    expect(wrapper.text()).toContain(DIGEST);
    await wrapper.get(".ver-copy").trigger("click");
    await flushPromises();
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(DIGEST);
  });

  it("reveals the full version in a page-level tooltip", async () => {
    const wrapper = mountItem();
    await wrapper.get("[data-testid='attribution-item']").trigger("mouseenter");
    await flushPromises();
    const tip = document.body.querySelector(".version-tip");
    expect(tip?.textContent).toContain("v6.4.1 580c97c");
    wrapper.unmount();
  });

  it("renders an unpinned version without a copy button", () => {
    const wrapper = mountItem({ objectVersion: null, objectRef: null, objectCommit: null });
    expect(wrapper.text()).toContain("版本未固定");
    expect(wrapper.find(".ver-copy").exists()).toBe(false);
  });
});
