// @vitest-environment jsdom
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import type { EvolutionRunControl } from "@harness/contracts";
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { pauseEvolutionRun, resumeEvolutionRun } from "../../../api/evolutionRuns";
import { ApiError } from "../../../api/http";
import RunControl from "./RunControl.vue";

vi.mock("../../../api/evolutionRuns", () => ({
  pauseEvolutionRun: vi.fn(), resumeEvolutionRun: vi.fn(),
}));

const running = {
  runId: "run-1", controlState: "running" as const,
  pauseRequestedAt: null, pausedAt: null, pausedBy: null,
  canPause: true, canResume: false,
};
const paused = { ...running, controlState: "paused" as const, canPause: false, canResume: true };
function render(run = running as typeof running | typeof paused, canManage = true) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidation = vi.spyOn(queryClient, "invalidateQueries");
  const wrapper = mount(RunControl, {
    props: { wid: "ws-1", run, canManage },
    global: { plugins: [[VueQueryPlugin, { queryClient }]] },
  });
  return { wrapper, invalidation };
}

describe("RunControl", () => {
  beforeEach(() => vi.resetAllMocks());

  it("uses the acknowledged state and disables duplicate pause requests", async () => {
    let accept!: (value: EvolutionRunControl) => void;
    vi.mocked(pauseEvolutionRun).mockImplementation(() => new Promise(resolve => { accept = resolve; }));
    const { wrapper, invalidation } = render();
    await wrapper.get("button").trigger("click");
    expect(wrapper.get("button").attributes("disabled")).toBeDefined();
    expect(pauseEvolutionRun).toHaveBeenCalledWith("ws-1", "run-1");
    accept({ ...running, controlState: "pause_requested", canPause: false });
    await flushPromises();
    expect(wrapper.text()).toContain("等待当前操作结束");
    expect(wrapper.text()).not.toContain("继续执行");
    expect(invalidation).toHaveBeenCalled();
    wrapper.unmount();
  });

  it("continues the same run and accepts a refreshed paused snapshot", async () => {
    vi.mocked(resumeEvolutionRun).mockResolvedValue(running);
    const { wrapper } = render(paused);
    expect(wrapper.text()).toContain("已暂停");
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(resumeEvolutionRun).toHaveBeenCalledWith("ws-1", "run-1");
    expect(wrapper.text()).toContain("暂停");
    await wrapper.setProps({ run: { ...paused, pausedAt: "2026-11-20T00:01:00Z" } });
    expect(wrapper.text()).toContain("继续执行");
    wrapper.unmount();
  });

  it("shows paused facts to members without management actions", () => {
    const { wrapper } = render(paused, false);
    expect(wrapper.text()).toContain("已暂停");
    expect(wrapper.find("button").exists()).toBe(false);
    wrapper.unmount();
  });

  it("retains paused facts on conflict and refreshes authoritative availability", async () => {
    vi.mocked(resumeEvolutionRun).mockRejectedValue(new ApiError(409, "RUN_NOT_RESUMABLE", "运行状态已变化"));
    const { wrapper, invalidation } = render(paused);
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("运行状态已变化");
    expect(wrapper.text()).toContain("已暂停");
    expect(invalidation).toHaveBeenCalled();
    wrapper.unmount();
  });
});
