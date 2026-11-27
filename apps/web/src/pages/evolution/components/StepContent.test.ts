// @vitest-environment jsdom

import type {
  EvolutionStepAttribution,
  EvolutionStepClusters,
  EvolutionStepFinal,
  EvolutionStepIteration,
  EvolutionStepPotential,
  EvolutionStepRange,
  EvolutionStepSessions,
} from "@harness/contracts";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import StepAttribution from "./StepAttribution.vue";
import StepCaseTable from "./StepCaseTable.vue";
import StepClusters from "./StepClusters.vue";
import StepFinal from "./StepFinal.vue";
import StepIterations from "./StepIterations.vue";
import StepPotential from "./StepPotential.vue";
import StepRange from "./StepRange.vue";
import StepSessions from "./StepSessions.vue";

const caseItem = {
  badCaseId: "bc-1",
  title: "读取越界",
  objectName: "deep-research",
  badCaseType: "self",
  triggerAt: "2026-09-01T10:00:00+08:00",
  createdAt: "2026-09-01T10:05:00+08:00",
};

const rangeStep = {
  key: "range",
  index: 0,
  title: "选择范围",
  status: "done",
  clickable: true,
  payload: {
    condition: {
      targetType: "skill",
      targetName: "deep-research",
      targetVersion: "v2.0.0",
      from: "2026-08-20",
      to: "2026-09-10",
      policy: { preset: "default" as const },
      cacheEnabled: true,
      workspaceId: "ws-test",
    },
    stats: { sessions: 2, badCases: 2, potential: 1 },
  },
} satisfies EvolutionStepRange;

const sessionsStep = {
  key: "sessions",
  index: 1,
  title: "Session 关联",
  status: "done",
  clickable: true,
  payload: {
    summary: {
      reported: 9,
      associated: 5,
      skipped: 3,
      versionUnresolved: 1,
      pending: 0,
    },
    rows: [
      {
        sessionId: "session-1",
        title: "研究运行",
        objectTriggerAt: "2026-09-01T09:00:00+08:00",
        badCaseCount: 2,
        potentialCount: 1,
      },
    ],
    total: 9,
    page: 1,
    pageSize: 4,
  },
} satisfies EvolutionStepSessions;

const potentialStep = {
  key: "potential",
  index: 2,
  title: "潜在 bad case",
  status: "done",
  clickable: true,
  payload: {
    summary: {
      badCases: 6,
      potential: 3,
      byReason: {
        selfReport: 1,
        afterObject: 1,
        both: 1,
        policyExcluded: 2,
        orderUnknown: 1,
      },
    },
    rows: [
      {
        badCaseId: "case-1",
        objectName: "deep-research",
        badCaseType: "self",
        triggerAt: "2026-09-01T10:00:00+08:00",
        sessionId: "session-1",
        hitReason: "after_object",
        orderState: "unknown",
        anchorSource: "event",
      },
    ],
    total: 6,
    page: 1,
    pageSize: 5,
  },
} satisfies EvolutionStepPotential;

const clustersStep = {
  key: "clusters",
  index: 4,
  title: "聚类与严重度",
  status: "done",
  clickable: true,
  payload: {
    clusters: [
      {
        clusterId: "C1",
        title: "检索索引读取失败",
        description: "读取越界",
        category: "error",
        caseCount: 1,
        cases: [caseItem],
        confidence: 0.82,
        severity: 7.4,
        rank: 1,
      },
    ],
  },
} satisfies EvolutionStepClusters;

const attributionStep = {
  key: "attribution",
  index: 3,
  title: "对象归因",
  status: "done",
  clickable: true,
  payload: {
    summary: { potential: 2, reused: 1, fresh: 1, nonTarget: 1 },
    rows: [
      {
        badCaseId: "case-1",
        sessionId: "session-1",
        attributionId: "attr-1",
        category: "error",
        description: "读取越界",
        source: "cached",
        confidence: 0.82,
      },
      {
        badCaseId: "case-2",
        sessionId: "session-2",
        attributionId: "attr-2",
        category: null,
        description: "与所选对象无关",
        source: "fresh",
        confidence: null,
      },
    ],
  },
} satisfies EvolutionStepAttribution;

const iterationStep = {
  key: "iteration",
  index: 5,
  title: "迭代优化",
  status: "active",
  clickable: true,
  payload: {
    rounds: [
      {
        roundId: "round-1",
        clusterId: "C1",
        title: "检索索引读取失败",
        category: "error",
        caseCount: 1,
        confidence: 0.82,
        severity: 7.4,
        cases: [caseItem],
        status: "evaluating",
        candidate: {
          ref: "evo/run/candidate/r1",
          commit: "abc123",
          message: "candidate",
        },
        patch: {
          files: [
            {
              file: "SKILL.md",
              lines: ["@@ -1 +1 @@", "- 读取索引", "+ 读取索引前校验快照"],
              overwrite: false,
            },
          ],
        },
        push: { status: "succeeded", attempts: 1, error: null },
        eval: {
          status: "evaluating",
          current: 84.6,
          candidate: null,
          nextPollAt: null,
        },
        accepted: false,
        finalCommit: null,
      },
    ],
  },
} satisfies EvolutionStepIteration;

const finalStep = {
  key: "final",
  index: 6,
  title: "测试集终评",
  status: "done",
  clickable: true,
  payload: {
    verdict: true,
    degraded: false,
    bestVersion: "v2.0.1-best",
    bestScore: 88.9,
    initScore: 84.3,
    metrics: [
      { name: "任务完成率", init: 78, best: 84, delta: 6, unit: "%" },
    ],
    changes: [
      {
        commit: "cd34ab12ef56",
        clusterId: "C1",
        title: "检索索引读取失败",
        category: "error",
        reportCount: 1,
      },
    ],
  },
} satisfies EvolutionStepFinal;

const run = {
  runId: "run-1",
  controlState: "running" as const, canPause: false, canResume: false,
  title: "run",
  mode: "full" as const,
  target: { type: "skill" as const, name: "deep-research", version: "v2.0.0", subDir: "skills/deep-research", matchByName: false },
  window: { from: "2026-08-20", to: "2026-09-10" },
  models: ["glm-5.3"],
  policy: { preset: "default" as const },
  cacheEnabled: false,
  createdBy: "Ada",
  createdAt: "2026-10-19T18:42:00+08:00",
  status: "running" as const,
  degraded: false,
  error: null,
  stats: {
    sessions: 2,
    versionUnresolvedSessions: 0,
    badCases: 2,
    potential: 1,
    attributed: 1,
    reused: 0,
    clusters: 1,
    byCategory: { flow: 0, context: 0, model: 0, prompt: 0, error: 1 },
  },
  progress: {
    unit: 5,
    total: 7,
    percent: 80,
    stageLabel: "第 6/7 步 · 迭代优化 · 第 1/1 轮",
    doneRounds: 0,
    accepted: 0,
  },
  final: null,
};

describe("evolution step content", () => {
  it("summarizes the selection condition and headline counts", () => {
    const wrapper = mount(StepRange, {
      props: {
        step: rangeStep,
        targetRevision: "digest:9080a1b2",
      },
    });

    expect(wrapper.text()).toContain("skill:deep-research@v2.0.0");
    expect(wrapper.text()).toContain("2026-08-20 ~ 2026-09-10");
    expect(wrapper.text()).toContain("默认策略");
    expect(wrapper.text()).toContain("复用最近一次成功归因");
    expect(wrapper.text()).toContain("ws-test");
    expect(wrapper.text()).toContain("时间段内 bad case");
    expect(wrapper.text()).toContain("潜在 bad case");
    expect(wrapper.get("[data-testid='step-target-revision']").text()).toBe(
      "digest:9080a1b2",
    );
  });

  it("shows every configuration member, the shared test project, and the change scope", () => {
    const multiStep = {
      ...rangeStep,
      payload: {
        ...rangeStep.payload,
        condition: {
          ...rangeStep.payload.condition,
          targetVersion: "v2.4.0",
          targets: [
            {
              objectType: "skill",
              objectName: "deep-research",
              targetVersion: "v2.4.0",
              targetRevision: "digest:member-a",
              subDir: "skills/deep-research",
            },
            {
              objectType: "skill",
              objectName: "code-review",
              targetVersion: "v2.4.0",
              targetRevision: "digest:member-b",
              subDir: "skills/code-review",
            },
          ],
        },
      },
    } satisfies EvolutionStepRange;
    const wrapper = mount(StepRange, {
      props: {
        step: multiStep,
        targetRevision: "digest:member-a",
        subDirs: ["skills/deep-research", "skills/code-review"],
        sharedProject: {
          validationProjectId: "val-skills-2026q4",
          testProjectId: "test-skills-2026q4",
          primaryMetricKey: "resolved_rate",
        },
      },
    });

    expect(wrapper.text()).toContain("skill:deep-research +1@v2.4.0");
    const members = wrapper.get("[data-testid='step-range-members']");
    expect(members.text()).toContain("skills/deep-research");
    expect(members.text()).toContain("skills/code-review");
    expect(members.text()).toContain("digest:member-a");
    expect(members.text()).toContain("digest:member-b");
    const project = wrapper.get("[data-testid='step-range-test-project']");
    expect(project.text()).toContain("val-skills-2026q4");
    expect(project.text()).toContain("test-skills-2026q4");
    expect(project.text()).toContain("resolved_rate");
    const scope = wrapper.get("[data-testid='step-range-change-scope']");
    expect(scope.text()).toContain("skills/deep-research/**");
    expect(scope.text()).toContain("skills/code-review/**");
  });

  it("keeps a missing target revision explicit instead of guessing a tag", () => {
    const wrapper = mount(StepRange, {
      props: { step: rangeStep },
    });

    expect(
      wrapper.get("[data-testid='step-target-revision-missing']").text(),
    ).toContain("历史运行未记录 revision");
    expect(wrapper.text()).not.toContain("digest:");
  });

  it("prefers the step-condition revision over the run-target snapshot", () => {
    const step = {
      ...rangeStep,
      payload: {
        ...rangeStep.payload,
        condition: {
          ...rangeStep.payload.condition,
          targetRevision: "digest:condition",
        },
      },
    } satisfies EvolutionStepRange;
    const wrapper = mount(StepRange, {
      props: { step, targetRevision: "digest:snapshot" },
    });

    expect(wrapper.get("[data-testid='step-target-revision']").text()).toBe(
      "digest:condition",
    );
  });

  it("falls back to the run-target snapshot when the condition has no revision", () => {
    const step = {
      ...rangeStep,
      payload: {
        ...rangeStep.payload,
        condition: {
          ...rangeStep.payload.condition,
          targetRevision: null,
        },
      },
    } satisfies EvolutionStepRange;
    const wrapper = mount(StepRange, {
      props: { step, targetRevision: "digest:snapshot" },
    });

    expect(wrapper.get("[data-testid='step-target-revision']").text()).toBe(
      "digest:snapshot",
    );
  });

  it("shows a custom potential policy verbatim", () => {
    const wrapper = mount(StepRange, {
      props: {
        step: {
          ...rangeStep,
          payload: {
            ...rangeStep.payload,
            condition: {
              ...rangeStep.payload.condition,
              policy: { includeSelfReport: true, includeAfterObject: false },
              cacheEnabled: false,
            },
          },
        },
      },
    });

    expect(wrapper.text()).toContain("自定义策略");
    expect(wrapper.text()).toContain("includeSelfReport");
    expect(wrapper.text()).toContain("全部重新归因");
  });

  it("renders the session partition and pages through associated Sessions", async () => {
    const wrapper = mount(StepSessions, {
      props: { step: sessionsStep },
    });

    expect(wrapper.text()).toContain("研究运行");
    expect(wrapper.text()).toContain("session-1");
    expect(wrapper.text()).toContain("上报过 bad case");
    expect(wrapper.text()).toContain("版本未知");
    expect(wrapper.text()).toContain("共 9 个关联 Session");

    const buttons = wrapper.findAll(".pager button");
    expect(buttons[0]?.attributes("disabled")).toBeDefined();
    expect(buttons[1]?.attributes("disabled")).toBeUndefined();

    await buttons[1]?.trigger("click");
    expect(wrapper.emitted("page-change")).toEqual([[2]]);
  });

  it("renders potential rows with hit reasons and order-state caveats", async () => {
    const wrapper = mount(StepPotential, {
      props: { wid: "ws-test", step: potentialStep },
    });

    expect(wrapper.text()).toContain("时间段内 bad case");
    expect(wrapper.text()).toContain("策略排除");
    expect(wrapper.text()).toContain("触发点在对象后");
    expect(wrapper.text()).toContain("触发点顺序待轨迹时间戳重放");
    expect(wrapper.text()).toContain("deep-research");
    expect(wrapper.text()).toContain("锚点来源");
    expect(wrapper.get("[data-anchor-source='event']").text()).toBe("事件锚点");

    const link = wrapper.get("td.id a");
    expect(link.attributes("href")).toBe(
      "/workspaces/ws-test/sessions/session-1/errors?case=case-1&tab=desc",
    );

    const buttons = wrapper.findAll(".pager button");
    await buttons[1]?.trigger("click");
    expect(wrapper.emitted("page-change")).toEqual([[2]]);
  });

  it("shows the post-process anchor source badge from the required row field", () => {
    const withAnchorSource = {
      ...potentialStep,
      payload: {
        ...potentialStep.payload,
        rows: [
          {
            ...potentialStep.payload.rows[0]!,
            anchorSource: "post_process" as const,
          },
        ],
      },
    } satisfies EvolutionStepPotential;
    const wrapper = mount(StepPotential, {
      props: { wid: "ws-test", step: withAnchorSource },
    });

    expect(
      wrapper.get("[data-anchor-source='post_process']").text(),
    ).toBe("后处理上报");
    expect(wrapper.text()).not.toContain("2147483647");
  });

  it("opens the first cluster and expands its source bad cases", async () => {
    const wrapper = mount(StepClusters, {
      props: { wid: "ws-test", step: clustersStep },
    });

    expect(wrapper.text()).toContain("聚类问题描述");
    expect(wrapper.text()).toContain("读取越界");
    expect(wrapper.text()).toContain("bc-1");
    expect(wrapper.get(".cluster-head").attributes("aria-expanded")).toBe("true");

    await wrapper.get(".cluster-head").trigger("click");
    expect(wrapper.get(".cluster-head").attributes("aria-expanded")).toBe("false");
    expect(wrapper.text()).not.toContain("bc-1");
  });

  it("deep-links step 5 source cases to their Session error detail", () => {
    const wrapper = mount(StepClusters, {
      props: {
        wid: "ws-test",
        step: clustersStep,
        caseSessions: { "bc-1": "session-9" },
      },
    });

    const link = wrapper.get("td.id a");
    expect(link.attributes("href")).toBe(
      "/workspaces/ws-test/sessions/session-9/errors?case=bc-1&tab=attr",
    );
    expect(link.attributes("target")).toBe("_blank");
    expect(link.attributes("rel")).toBe("noopener noreferrer");
    expect(link.text()).toBe("bc-1");
  });

  it("deep-links step 6 source cases to their Session error detail", () => {
    const wrapper = mount(StepIterations, {
      props: {
        wid: "ws-test",
        step: iterationStep,
        caseSessions: { "bc-1": "session-9" },
      },
    });

    const link = wrapper.get("td.id a");
    expect(link.attributes("href")).toBe(
      "/workspaces/ws-test/sessions/session-9/errors?case=bc-1&tab=attr",
    );
    expect(link.attributes("target")).toBe("_blank");
    expect(link.attributes("rel")).toBe("noopener noreferrer");
  });

  it("falls back to plain text when a source case has no Session mapping", () => {
    const wrapper = mount(StepIterations, {
      props: { wid: "ws-test", step: iterationStep },
    });

    expect(wrapper.find("td.id a").exists()).toBe(false);
    expect(wrapper.get("td.id").text()).toBe("bc-1");
  });

  it("shows the algorithm, fallback tasks and strict failure reason", () => {
    const degraded = mount(StepClusters, {
      props: {
        wid: "ws-test",
        step: {
          ...clustersStep,
          payload: {
            ...clustersStep.payload,
            algorithm: "hybrid-lexical-llm-v1",
            failurePolicy: "degrade" as const,
            degraded: ["cluster.review"],
          },
        },
      },
    });
    const failed = mount(StepClusters, {
      props: {
        wid: "ws-test",
        step: {
          ...clustersStep,
          payload: {
            ...clustersStep.payload,
            failurePolicy: "strict" as const,
            failure: "cluster.review failed: AgentProviderError: could not start",
          },
        },
      },
    });

    expect(degraded.text()).toContain("hybrid-lexical-llm-v1");
    expect(degraded.text()).toContain("AI 聚类使用了确定性回退");
    expect(degraded.text()).toContain("cluster.review");
    expect(failed.text()).toContain("真实 AI 聚类失败");
    expect(failed.text()).toContain("could not start");
    expect(failed.text()).not.toContain("当前运行还没有生成问题簇");
  });

  it("highlights an addressed cluster and reports a missing target", async () => {
    const highlighted = mount(StepClusters, {
      props: { wid: "ws-test", step: clustersStep, focusCluster: "C1" },
    });
    const missing = mount(StepClusters, {
      props: { wid: "ws-test", step: clustersStep, focusCluster: "missing" },
    });
    await highlighted.vm.$nextTick();

    expect(highlighted.get("#cluster-C1").classes()).toContain("highlighted");
    expect(missing.text()).toContain("目标簇已不存在");
    expect(missing.emitted("missing-focus")).toHaveLength(1);
  });

  it("renders attribution rows with cached and fresh sources", () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { initialData: { items: [] }, staleTime: Infinity } },
    });
    const wrapper = mount(StepAttribution, {
      global: { plugins: [[VueQueryPlugin, { queryClient }]] },
      props: { wid: "ws-test", step: attributionStep, run },
    });

    expect(wrapper.text()).toContain("读取越界");
    expect(wrapper.text()).toContain("缓存");
    expect(wrapper.text()).toContain("新增");
    expect(wrapper.text()).toContain("82%");
    expect(wrapper.text()).toContain("非该对象问题");
    expect(wrapper.text()).toContain("attr-1");
    expect(
      wrapper.get("td.report-id a").attributes("href"),
    ).toContain("tab=attr&at=attr-1");
    expect(wrapper.get("td.id a").attributes("href")).toContain("tab=desc");
  });

  it("renders an empty case table for clusters without source cases", () => {
    const wrapper = mount(StepCaseTable, {
      props: { cases: [] },
    });

    expect(wrapper.text()).toContain("无来源 bad case");
  });

  it("marks a degraded final step as not model-backed", () => {
    const wrapper = mount(StepFinal, {
      props: {
        step: {
          ...finalStep,
          payload: {
            ...finalStep.payload,
            degraded: true,
          },
        },
        targetVersion: "v2.0.0",
      },
    });

    expect(wrapper.text()).toContain("聚类降级 · 结果不代表真实模型参与");
    expect(wrapper.text()).toContain("终评分数不能作为真实模型参与的证据");
    expect(wrapper.text()).not.toContain("✓ 自进化有效");
  });

  it("renders the final verdict against the original target version", () => {
    const wrapper = mount(StepFinal, {
      props: {
        step: finalStep,
        targetVersion: "v2.0.0",
      },
    });

    expect(wrapper.text()).toContain("✓ 自进化有效");
    expect(wrapper.text()).toContain("测试集终评得分");
    expect(wrapper.text()).toContain("测试集基线（初始版本）");
    expect(wrapper.text()).toContain("测试集基线 v2.0.0");
    expect(wrapper.text()).toContain("任务完成率");
    expect(wrapper.text()).toContain("cd34ab12ef56");
    expect(wrapper.text()).toContain("错误");
  });
});
