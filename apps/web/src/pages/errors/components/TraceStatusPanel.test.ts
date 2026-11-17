// @vitest-environment jsdom

import { mount, RouterLinkStub } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import TraceStatusPanel from "./TraceStatusPanel.vue";
import type { TraceStatusDetails } from "../traceStatus";

function details(overrides: Partial<TraceStatusDetails> = {}): TraceStatusDetails {
  return {
    badCaseId: "case-no-trace",
    sessionId: "root-no-trace",
    title: "SWE-bench astropy__astropy-12907 · not_scored",
    objectName: "claude-code",
    createdAt: "2026-11-17T09:00:00+08:00",
    sessionReady: false,
    syncStatus: "unavailable",
    lastError: "SESSION_QUERY_UNAVAILABLE",
    retryable: false,
    nextRetryAt: null,
    lastAttemptAt: "2026-11-17T09:05:00+08:00",
    ...overrides,
  };
}

function mountPanel(value: TraceStatusDetails = details()) {
  return mount(TraceStatusPanel, {
    props: {
      wid: "ws-test",
      caseId: value.badCaseId,
      sessionId: value.sessionId,
      details: value,
    },
    global: {
      stubs: { RouterLink: RouterLinkStub },
    },
  });
}

describe("trace status panel", () => {
  it("explains that the case still exists and shows the durable failure", () => {
    const wrapper = mountPanel();

    expect(wrapper.get("[data-testid='trace-status-panel']").text()).toContain(
      "没有被删除",
    );
    expect(wrapper.get("[data-testid='trace-status-chip']").text()).toBe(
      "无可用轨迹",
    );
    expect(wrapper.get("[data-testid='trace-last-error']").text()).toContain(
      "SESSION_QUERY_UNAVAILABLE",
    );
    expect(wrapper.get("[data-testid='trace-last-error']").text()).toContain(
      "轨迹查询服务未配置",
    );
    expect(wrapper.get("[data-testid='trace-retryable']").text()).toBe(
      "不会自动重试",
    );
  });

  it("labels pending and failed states with their retryability", () => {
    const pending = mountPanel(
      details({ syncStatus: "pending", lastError: null, retryable: true }),
    );
    expect(pending.text()).toContain("尚未同步");
    expect(pending.get("[data-testid='trace-retryable']").text()).toBe(
      "可自动重试",
    );

    const failed = mountPanel(
      details({
        syncStatus: "failed",
        lastError: "SESSION_QUERY_TIMEOUT",
        retryable: true,
        nextRetryAt: "2026-11-17T09:10:00+08:00",
      }),
    );
    expect(failed.text()).toContain("同步失败");
    expect(failed.text()).toContain("下次重试");
  });

  it("offers the sync entry, refresh and copy actions", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    const wrapper = mountPanel();
    await wrapper.get("[data-testid='trace-open-sync']").trigger("click");
    await wrapper.get("[data-testid='trace-refresh']").trigger("click");
    await wrapper.get("[data-testid='trace-copy-id']").trigger("click");

    expect(wrapper.emitted("open-sync")).toHaveLength(1);
    expect(wrapper.emitted("refresh")).toHaveLength(1);
    expect(writeText).toHaveBeenCalledWith("case-no-trace");
    expect(wrapper.get("[data-testid='trace-copy-id']").text()).toContain(
      "已复制",
    );
    const back = wrapper.getComponent(RouterLinkStub);
    expect(back.props("to")).toBe("/workspaces/ws-test/overview");
  });
});
