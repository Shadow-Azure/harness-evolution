// @vitest-environment jsdom

import type { EvolutionRunCard } from "@harness/contracts";
import { mount } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { describe, expect, it } from "vitest";

import RunCard from "./RunCard.vue";

const run = (overrides: Partial<EvolutionRunCard> = {}): EvolutionRunCard => ({
  runId: "run-1",
  controlState: "running", canPause: false, canResume: false,
  title: "deep-research v2.0.0 自进化",
  mode: "full",
  target: {
    type: "skill",
    name: "deep-research",
    version: "v2.0.0",
  },
  window: {
    from: "2026-08-20",
    to: "2026-09-10",
  },
  models: ["glm-5.3", "gpt-5"],
  policy: { preset: "default" },
  cacheEnabled: false,
  createdBy: "Ada",
  createdAt: "2026-10-19T18:42:00+08:00",
  status: "running",
  degraded: false,
  error: null,
  stats: {
    sessions: 128,
    versionUnresolvedSessions: 3,
    badCases: 46,
    potential: 28,
    attributed: 16,
    reused: 9,
    clusters: 2,
    byCategory: {
      flow: 0,
      context: 0,
      model: 6,
      prompt: 5,
      error: 5,
    },
  },
  progress: {
    unit: 4,
    total: 7,
    percent: 57,
    stageLabel: "第 6/7 步 · 迭代优化 · 第 1/2 轮",
    doneRounds: 0,
    accepted: 1,
  },
  final: null,
  ...overrides,
});

describe("RunCard", () => {
  it("keeps paused progress visible without an active pulse or member actions", () => {
    const wrapper = mount(RunCard, {
      props: { wid: "ws-test", workspaceName: "测试空间", run: run({
        controlState: "paused", canPause: false, canResume: true,
        pauseRequestedAt: null, pausedAt: null, pausedBy: null,
      }) },
      global: { plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }]] },
    });
    expect(wrapper.get(".badge").text()).toBe("已暂停");
    expect(wrapper.find(".pulse").exists()).toBe(false);
    expect(wrapper.text()).toContain("第 6/7 步");
    expect(wrapper.find(".control-button").exists()).toBe(false);
    wrapper.unmount();
  });

  it("renders the preparing status explicitly", () => {
    const wrapper = mount(RunCard, {
      props: {
        wid: "ws-test",
        workspaceName: "测试空间",
        run: run({
          status: "preparing",
          progress: {
            unit: 0,
            total: 7,
            percent: 0,
            stageLabel: "第 1/7 步 · 选择范围中…",
            doneRounds: 0,
            accepted: 0,
          },
        }),
      },
    });

    expect(wrapper.get(".badge").text()).toBe("准备中");
    expect(wrapper.get(".badge").classes()).toContain("running");
  });

  it("renders prototype metadata and uses backend progress verbatim", () => {
    const wrapper = mount(RunCard, {
      props: { wid: "ws-test", workspaceName: "测试空间", run: run() },
    });

    expect(wrapper.get(".run-card").classes()).toContain("run-card");
    expect(wrapper.get(".title").text()).toBe("deep-research v2.0.0 自进化");
    expect(wrapper.get(".time").text()).toBe("2026-10-19 18:42");
    expect(wrapper.get("[data-testid='run-workspace-chip']").text()).toBe(
      "测试空间",
    );
    expect(wrapper.get("[data-testid='run-policy-chip']").text()).toBe(
      "默认潜在策略",
    );
    expect(wrapper.get("[data-testid='run-cache-chip']").text()).toBe(
      "不复用缓存",
    );
    expect(
      wrapper.get("[data-testid='run-cache-chip']").classes(),
    ).not.toContain("is-on");
    expect(wrapper.get(".chip.kind").text()).toBe(
      "skill:deep-research@v2.0.0",
    );
    expect(wrapper.text()).toContain("2026-08-20 ~ 2026-09-10");
    expect(wrapper.findAll(".run-meta > *").map((chip) => chip.text())).toEqual([
      "skill:deep-research@v2.0.0",
      "2026-08-20 ~ 2026-09-10",
      "测试空间",
      "默认潜在策略",
      "不复用缓存",
      "glm-5.3",
      "gpt-5",
    ]);
    expect(wrapper.text()).toContain("128关联 Session");
    expect(wrapper.text()).toContain("46bad case");
    expect(wrapper.text()).toContain("28潜在 bad case");
    expect(wrapper.text()).toContain("16可归因");
    expect(wrapper.text()).toContain("9复用归因");
    expect(wrapper.text()).toContain("0/2已跑轮次");
    expect(wrapper.text()).not.toContain("已接纳");
    expect(wrapper.text()).toContain(
      "第 6/7 步 · 迭代优化 · 第 1/2 轮 · 57%",
    );
    expect(wrapper.get(".run-progress .fill").attributes("style")).toContain(
      "width: 57%",
    );
    expect(wrapper.get("[role='progressbar']").attributes()).toMatchObject({
      "aria-label": "第 6/7 步 · 迭代优化 · 第 1/2 轮",
      "aria-valuemax": "100",
      "aria-valuemin": "0",
      "aria-valuenow": "57",
    });
    expect(wrapper.get(".badge").classes()).toContain("running");
    expect(wrapper.get(".badge").text()).toContain("正在执行");
  });

  it("falls back to the default policy when an old payload has no policy", () => {
    const legacy = { ...run(), policy: undefined } as unknown as EvolutionRunCard;
    const wrapper = mount(RunCard, {
      props: { wid: "ws-test", workspaceName: "测试空间", run: legacy },
    });

    expect(wrapper.get("[data-testid='run-policy-chip']").text()).toBe(
      "默认潜在策略",
    );
  });

  it("renders a custom policy and cache reuse from the run snapshot", () => {
    const wrapper = mount(RunCard, {
      props: {
        wid: "ws-test",
        workspaceName: "测试空间",
        run: run({
          policy: { preset: "custom" },
          cacheEnabled: true,
        }),
      },
    });

    expect(wrapper.get("[data-testid='run-policy-chip']").text()).toBe(
      "自定义潜在策略",
    );
    expect(wrapper.get("[data-testid='run-cache-chip']").text()).toBe(
      "复用缓存",
    );
    expect(wrapper.get("[data-testid='run-cache-chip']").classes()).toContain(
      "is-on",
    );
  });

  it("renders the effective history summary from backend values", () => {
    const wrapper = mount(RunCard, {
      props: {
        wid: "ws-test",
        workspaceName: "测试空间",
        run: run({
          status: "completed",
          progress: {
            unit: 7,
            total: 7,
            percent: 100,
            stageLabel: "第 7/7 步 · 测试集终评中…",
            doneRounds: 2,
            accepted: 1,
          },
          final: {
            bestVersion: "v2.0.1-best",
            branchName: "evo/run-1",
            pushStatus: "succeeded",
            verdict: true,
            bestScore: 88.9,
            initScore: 84.3,
          },
        }),
      },
    });

    expect(wrapper.get(".badge").text()).toBe("✓ 已完成 · 自进化有效");
    expect(wrapper.get(".final-line").text()).toContain(
      "best 88.9 vs 初始 84.3",
    );
    expect(wrapper.get(".final-line").text()).toContain("+4.6");
    expect(wrapper.get(".final-line").text()).toContain("接纳 1/2 个 patch");
    expect(wrapper.find("[role='progressbar']").exists()).toBe(false);
  });

  it("marks a completed degraded run without claiming model-backed success", () => {
    const wrapper = mount(RunCard, {
      props: {
        wid: "ws-test",
        workspaceName: "测试空间",
        run: run({
          status: "completed",
          degraded: true,
          final: {
            bestVersion: "v2.0.1-best",
            branchName: "evo/run-1",
            pushStatus: "succeeded",
            verdict: true,
            bestScore: 88.9,
            initScore: 84.3,
          },
        }),
      },
    });

    expect(wrapper.get(".badge").text()).toBe("已完成 · 聚类降级");
    expect(wrapper.get(".badge").classes()).toContain("done-pending");
  });

  it("marks completed runs without improvement without claiming success", () => {
    const wrapper = mount(RunCard, {
      props: {
        wid: "ws-test",
        workspaceName: "测试空间",
        run: run({
          status: "completed",
          final: {
            bestVersion: "v2.0.0",
            branchName: "evo/run-1",
            pushStatus: "succeeded",
            verdict: false,
            bestScore: 80.1,
            initScore: 80.1,
          },
        }),
      },
    });

    expect(wrapper.get(".badge").text()).toBe("已完成 · 无收益");
    expect(wrapper.get(".final-line").text()).toContain("+0.0");
  });

  it("keeps a completed run with no final neutral instead of claiming no benefit", () => {
    const wrapper = mount(RunCard, {
      props: {
        wid: "ws-test",
        workspaceName: "测试空间",
        run: run({
          status: "completed",
          final: null,
        }),
      },
    });

    expect(wrapper.get(".badge").text()).toBe("已完成 · 终评未知");
    expect(wrapper.get(".badge").classes()).toContain("done-pending");
    expect(wrapper.text()).not.toContain("无收益");
    expect(wrapper.text()).toContain("终评数据暂不可用");
  });

  it("makes failed and interrupted error details available through a focusable tooltip", async () => {
    const failed = mount(RunCard, {
      props: {
        wid: "ws-test",
        workspaceName: "测试空间",
        run: run({
          status: "failed",
          error: {
            stage: "eval",
            message: "评测执行失败：sandbox timeout",
            at: "2026-10-19T19:00:00+08:00",
          },
        }),
      },
    });
    const interrupted = mount(RunCard, {
      props: {
        wid: "ws-test",
        workspaceName: "测试空间",
        run: run({
          status: "interrupted",
          error: {
            stage: "push",
            message: "推送连接中断",
            at: "2026-10-19T19:00:00+08:00",
          },
        }),
      },
    });

    expect(failed.get(".badge").classes()).toContain("failed");
    expect(failed.get(".badge").element.tagName).toBe("BUTTON");
    expect(failed.get(".badge").attributes("title")).toBe(
      "评测执行失败：sandbox timeout",
    );
    const failedTooltipId = failed.get(".badge").attributes("aria-describedby");
    expect(failedTooltipId).toMatch(/^run-error-/);
    expect(failed.get(".badge-tooltip").attributes("id")).toBe(failedTooltipId);
    expect(failed.get(".badge-tooltip").attributes("role")).toBe("tooltip");
    expect(failed.get(".badge-tooltip").classes()).not.toContain("is-open");
    await failed.get(".badge").trigger("focus");
    expect(failed.get(".badge-tooltip").classes()).toContain("is-open");
    expect(failed.get(".badge-tooltip").text()).toBe(
      "评测执行失败：sandbox timeout",
    );
    await failed.get(".badge").trigger("blur");
    expect(failed.get(".badge-tooltip").classes()).not.toContain("is-open");
    expect(failed.find(".final-line").exists()).toBe(false);
    expect(interrupted.get(".badge").classes()).toContain("interrupted");
    expect(interrupted.get(".badge").attributes("title")).toBe(
      "推送连接中断",
    );
    expect(interrupted.find(".final-line").exists()).toBe(false);
    expect(failed.find(".run-error").exists()).toBe(false);
    expect(interrupted.find(".run-error").exists()).toBe(false);
    expect(failed.text()).not.toContain("eval");
    expect(interrupted.text()).not.toContain("push");
  });

  it("marks blocked active runs with a focusable warning tooltip", async () => {
    const wrapper = mount(RunCard, {
      props: {
        wid: "ws-test",
        workspaceName: "测试空间",
        run: run({
          status: "blocked",
          error: {
            stage: "eval",
            message: "评测队列暂停",
            at: "2026-10-19T19:00:00+08:00",
          },
        }),
      },
    });

    expect(wrapper.get(".badge").classes()).toContain("blocked");
    expect(wrapper.text()).toContain("已阻塞");
    expect(wrapper.find("[role='progressbar']").exists()).toBe(true);
    expect(wrapper.get(".badge").attributes("title")).toBe("评测队列暂停");
    await wrapper.get(".badge").trigger("click");
    expect(wrapper.get(".badge-tooltip").classes()).toContain("is-open");
    expect(wrapper.get(".badge-tooltip").text()).toBe("评测队列暂停");
    expect(wrapper.find(".run-error").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("eval");
  });

  it("keeps status badges non-interactive when no error is present", () => {
    const wrapper = mount(RunCard, {
      props: { wid: "ws-test", workspaceName: "测试空间", run: run() },
    });

    expect(wrapper.get(".badge").element.tagName).toBe("SPAN");
    expect(wrapper.find(".badge-tooltip").exists()).toBe(false);
  });

  it("opens the run detail with pointer and keyboard semantics", async () => {
    const wrapper = mount(RunCard, {
      props: { wid: "ws-test", workspaceName: "测试空间", run: run() },
    });

    expect(wrapper.get(".run-card-link").attributes("href")).toBe(
      "/workspaces/ws-test/evolution/runs/run-1",
    );
    expect(wrapper.get(".run-card-link").attributes("aria-label")).toBe(
      "查看运行 deep-research v2.0.0 自进化",
    );
    await wrapper.get(".run-card-link").trigger("click");
    expect(wrapper.emitted("open")).toEqual([
      ["/workspaces/ws-test/evolution/runs/run-1"],
    ]);
  });

  it("routes cluster-only cards to the dedicated preview page", () => {
    const wrapper = mount(RunCard, {
      props: { wid: "ws-test", workspaceName: "测试空间", run: run({ mode: "cluster_only" }) },
    });

    expect(wrapper.get(".run-card-link").attributes("href")).toBe(
      "/workspaces/ws-test/evolution/cluster/run-1",
    );
  });

  it("labels a completed cluster-only card without iteration or final facts", () => {
    const wrapper = mount(RunCard, {
      props: {
        wid: "ws-test",
        workspaceName: "测试空间",
        run: run({
          mode: "cluster_only",
          status: "completed",
          progress: {
            unit: 5,
            total: 5,
            percent: 100,
            stageLabel: "第 5/5 步 · 聚类完成",
            doneRounds: 0,
            accepted: 0,
          },
        }),
      },
    });

    expect(wrapper.get(".badge").text()).toBe("✓ 已完成 · 仅聚类");
    expect(wrapper.get(".badge").classes()).toContain("done-ok");
    expect(wrapper.text()).toContain("仅聚类分析 · 未执行 patch 生成与评测迭代");
    expect(wrapper.text()).toContain("聚类");
    expect(wrapper.text()).not.toContain("已跑轮次");
    expect(wrapper.text()).not.toContain("终评数据暂不可用");
  });

  it("keeps the error tooltip button from opening the detail", async () => {
    const wrapper = mount(RunCard, {
      props: {
        wid: "ws-test",
        workspaceName: "测试空间",
        run: run({
          status: "blocked",
          error: {
            stage: "eval",
            message: "评测队列暂停",
            at: "2026-10-19T19:00:00+08:00",
          },
        }),
      },
    });

    await wrapper.get(".error-trigger").trigger("click");
    expect(wrapper.emitted("open")).toBeUndefined();
  });
});
