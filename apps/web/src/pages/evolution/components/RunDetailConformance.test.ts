// @vitest-environment jsdom

import type {
  EvolutionStepAttribution,
  EvolutionStepClusters,
  EvolutionStepFinal,
  EvolutionStepIteration,
  StepRound,
} from "@harness/contracts";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import DiffView from "./DiffView.vue";
import EvalCompare from "./EvalCompare.vue";
import StepAttribution from "./StepAttribution.vue";
import StepClusters from "./StepClusters.vue";
import StepFinal from "./StepFinal.vue";
import StepIterations from "./StepIterations.vue";
import ProbeSourceTable from "./ProbeSourceTable.vue";

const RouterLinkStub = {
  props: ["to"],
  template: "<a :data-to='JSON.stringify(to)'><slot /></a>",
};

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
    potential: 2,
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

const probe = {
  probeId: "probe-1",
  sessionId: "session-1",
  sessionTitle: "研究运行",
  model: "glm-5.3",
  probeType: "skill",
  probeObject: "deep-research",
  objectVersion: "v2.0.0",
  attributeType: "error" as const,
  description: "读取越界",
  sourceBadCaseIds: ["case-1"],
};

const caseItem = {
  badCaseId: "case-1",
  title: "读取越界",
  objectName: "deep-research",
  badCaseType: "error",
  triggerAt: "2026-09-01T10:00:00+08:00",
  createdAt: "2026-09-01T10:05:00+08:00",
};

const clusterStep = {
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

function round(overrides: Partial<StepRound> = {}): StepRound {
  return {
    roundId: "round-1",
    clusterId: "C1",
    title: "检索索引读取失败",
    category: "error",
    caseCount: 1,
    confidence: 0.82,
    severity: 7.4,
    cases: [caseItem],
    status: "pending",
    candidate: null,
    patch: null,
    push: { status: "pending", attempts: 0, error: null },
    eval: { status: "pending", current: 84.6, candidate: null, nextPollAt: null },
    accepted: false,
    finalCommit: null,
    ...overrides,
  };
}

function iterationStep(rounds: StepRound[]): EvolutionStepIteration {
  return {
    key: "iteration",
    index: 5,
    title: "迭代优化",
    status: "active",
    clickable: true,
    payload: { rounds },
  } as EvolutionStepIteration;
}

describe("run detail conformance", () => {
  it("opens source report and problem IDs in safe new-window deep links", () => {
    const fullProbeId = "11111111-1111-4111-8111-111111111111";
    const fullBadCaseId = "22222222-2222-4222-8222-222222222222";
    const wrapper = mount(ProbeSourceTable, {
      props: {
        wid: "ws-test",
        rows: [
          {
            ...probe,
            probeId: fullProbeId,
            sourceBadCaseIds: [fullBadCaseId],
          },
        ],
        showCluster: false,
      },
    });

    const links = wrapper.findAll("a");
    expect(links).toHaveLength(2);
    expect(links.map((link) => link.text())).toEqual(["11111111", "22222222"]);

    for (const link of links) {
      expect(link.attributes("target")).toBe("_blank");
      expect(link.attributes("rel")).toBe("noopener noreferrer");
    }

    expect(links[0]?.attributes()).toMatchObject({
      href: `/workspaces/ws-test/sessions/session-1/errors?case=${fullBadCaseId}&tab=attr`,
      title: fullProbeId,
      "aria-label": "归因报告 11111111，在新窗口打开归因分析",
    });
    expect(links[1]?.attributes()).toMatchObject({
      href: `/workspaces/ws-test/sessions/session-1/errors?case=${fullBadCaseId}&tab=desc`,
      title: fullBadCaseId,
      "aria-label": "来源问题 22222222，在新窗口打开问题描述",
    });
  });

  it("renders cluster and iteration source-case tables from the cluster case shape", async () => {
    const clusters = mount(StepClusters, {
      props: {
        wid: "ws-test",
        step: clusterStep,
        focusCluster: "C1",
        caseSessions: { "case-1": "session-1" },
      },
      global: { stubs: { RouterLink: RouterLinkStub } },
    });
    await clusters.vm.$nextTick();

    for (const heading of [
      "bad case",
      "标题",
      "object_name",
      "类型",
      "触发点",
      "上报时间",
    ]) {
      expect(clusters.text()).toContain(heading);
    }
    expect(clusters.text()).toContain("按归因根因聚类");
    expect(clusters.text()).toContain("读取越界");
    expect(clusters.text()).toContain("deep-research");
    expect(clusters.text()).toContain("错误");
    expect(clusters.get("td.id a").attributes()).toMatchObject({
      href: "/workspaces/ws-test/sessions/session-1/errors?case=case-1&tab=attr",
      target: "_blank",
      rel: "noopener noreferrer",
      title: "case-1",
      "aria-label": "来源问题 case-1，在新窗口打开问题描述",
    });

    const iterations = mount(StepIterations, {
      props: { wid: "ws-test", step: iterationStep([round({ status: "evaluating" })]) },
      global: { stubs: { RouterLink: RouterLinkStub } },
    });
    expect(iterations.text()).toContain("bad case");
    expect(iterations.text()).toContain("case-1");
    expect(iterations.text()).toContain("读取越界");
  });

  it("expands a valid focused cluster and emits a cleanup request for a missing one", async () => {
    const present = mount(StepClusters, {
      props: { wid: "ws-test", step: clusterStep, focusCluster: "C1" },
      global: { stubs: { RouterLink: RouterLinkStub } },
    });
    await present.vm.$nextTick();
    expect(present.get(".cluster-head").attributes("aria-expanded")).toBe("true");

    const missing = mount(StepClusters, {
      props: { wid: "ws-test", step: clusterStep, focusCluster: "missing" },
      global: { stubs: { RouterLink: RouterLinkStub } },
    });
    await missing.vm.$nextTick();
    expect(missing.emitted("missing-focus")).toHaveLength(1);
  });

  it.each([
    ["pending", "待执行"],
    ["patching", "生成 patch 中"],
    ["pushing", "推送中"],
    ["evaluating", "评测中"],
    ["deciding", "决策中"],
    ["accepted", "已接纳"],
    ["rejected", "未接纳"],
    ["failed", "失败"],
  ])("maps round status %s to %s", (status, label) => {
    const wrapper = mount(StepIterations, {
      props: {
        wid: "ws-test",
        step: iterationStep([
          round({
            status: status as StepRound["status"],
            candidate:
              status === "pending" || status === "patching"
                ? null
                : {
                    ref: "refs/candidate",
                    commit: "abc123",
                    message: "candidate",
                  },
            push:
              status === "pushing"
                ? { status: "pushing", attempts: 1, error: null }
                : { status: "succeeded", attempts: 1, error: null },
            eval:
              status === "evaluating" || status === "deciding"
                ? {
                    status: status === "evaluating" ? "evaluating" : "completed",
                    current: 84.6,
                    candidate: status === "deciding" ? 85.1 : null,
                    nextPollAt: null,
                  }
                : { status: "pending", current: null, candidate: null, nextPollAt: null },
          }),
        ]),
      },
      global: { stubs: { RouterLink: RouterLinkStub } },
    });

    expect(wrapper.text()).toContain(label);
  });

  it.each([
    [
      "push",
      "pushing",
      { status: "failed" as const, attempts: 1, error: "远端拒绝" },
      { status: "pending" as const, current: 84.6, candidate: null, nextPollAt: null },
      "推送失败",
      "failed",
    ],
    [
      "eval",
      "evaluating",
      { status: "succeeded" as const, attempts: 1, error: null },
      { status: "failed" as const, current: 84.6, candidate: null, nextPollAt: null },
      "评测失败",
      "blocked",
    ],
    [
      "patch",
      "patching",
      { status: "pending" as const, attempts: 0, error: null },
      { status: "pending" as const, current: 84.6, candidate: null, nextPollAt: null },
      "patch 已阻塞",
      "blocked",
    ],
  ])(
    "uses run blocked stage %s before pending intermediate labels",
    (_stage, status, push, evaluation, label, className) => {
      const wrapper = mount(StepIterations, {
        props: {
          wid: "ws-test",
          step: iterationStep([
            round({
              status: status as StepRound["status"],
              push,
              eval: evaluation,
            }),
          ]),
          blockedStage: _stage === "patch" ? _stage : null,
        },
        global: { stubs: { RouterLink: RouterLinkStub } },
      });

      const badge = wrapper.get(".badge");
      expect(badge.text()).toBe(label);
      expect(badge.classes()).toContain(className);
      expect(badge.text()).not.toBe("推送中");
      expect(badge.text()).not.toBe("评测中");
    },
  );

  it("explains that patching has not created a candidate ref yet", () => {
    const wrapper = mount(StepIterations, {
      props: { wid: "ws-test", step: iterationStep([round({ status: "patching" })]) },
      global: { stubs: { RouterLink: RouterLinkStub } },
    });

    expect(wrapper.text()).toContain("正在生成并应用 patch");
    expect(wrapper.text()).not.toContain("尚未执行");
  });

  it("renders local-only candidates as skipped instead of remote push success", () => {
    const wrapper = mount(StepIterations, {
      props: {
        wid: "ws-test",
        step: iterationStep([
          round({
            status: "skipped",
            candidate: {
              ref: "evo/run/candidate/r1",
              commit: "abcdef1234567890",
              message: "candidate",
            },
            push: { status: "skipped", attempts: 0, error: null },
            eval: {
              status: "pending",
              current: null,
              candidate: null,
              nextPollAt: null,
            },
          }),
        ]),
      },
    });

    expect(wrapper.text()).toContain("本地候选（未推送）");
    expect(wrapper.text()).toContain("已跳过（本地模式）");
    expect(wrapper.text()).toContain("candidate 已生成 · 未推送");
    expect(wrapper.text()).not.toContain("candidate 已 push");
    expect(wrapper.text()).not.toContain("推送成功");
  });

  it("renders an explicit empty state when no iteration round exists", () => {
    const wrapper = mount(StepIterations, {
      props: { wid: "ws-test", step: iterationStep([]) },
    });

    expect(wrapper.text()).toContain("当前还没有进入迭代轮次");
  });

  it("uses acceptance rather than score direction for the evaluation outcome", () => {
    const rejected = mount(EvalCompare, {
      props: {
        evaluation: {
          status: "completed",
          current: 84.3,
          candidate: 88.9,
          nextPollAt: null,
        },
        accepted: false,
      },
    });
    expect(rejected.text()).toContain("未接纳");
    expect(rejected.text()).not.toContain("已提升为 current");

    const accepted = mount(EvalCompare, {
      props: {
        evaluation: {
          status: "completed",
          current: 84.3,
          candidate: 88.9,
          nextPollAt: null,
        },
        accepted: true,
      },
    });
    expect(accepted.text()).toContain("已提升为 current");

    const failed = mount(EvalCompare, {
      props: {
        evaluation: {
          status: "failed",
          current: 84.3,
          candidate: null,
          nextPollAt: null,
        },
        accepted: false,
      },
    });
    expect(failed.text()).toContain("评测失败");
    expect(failed.text()).not.toContain("无收益");

    const timeout = mount(EvalCompare, {
      props: {
        evaluation: {
          status: "timeout",
          current: 84.3,
          candidate: null,
          nextPollAt: null,
        },
        accepted: false,
      },
    });
    expect(timeout.text()).toContain("评测超时");
  });

  it("labels the evaluated candidate commit on an accepted round", () => {
    const evaluatedCommit = "abcdef1234567890";
    const finalCommit = "fedcba0987654321";
    const wrapper = mount(StepIterations, {
      props: {
        wid: "ws-test",
        step: iterationStep([
          round({
            status: "accepted",
            candidate: {
              ref: "refs/candidate",
              commit: evaluatedCommit,
              message: "candidate",
            },
            push: { status: "succeeded", attempts: 1, error: null },
            eval: {
              status: "completed",
              current: 84.6,
              candidate: 85.1,
              nextPollAt: null,
            },
            accepted: true,
            finalCommit: {
              hash: finalCommit,
              message: "accepted candidate",
            },
          }),
        ]),
      },
    });

    expect(wrapper.text()).toContain("Harness-Evaluated-Commit");
    expect(wrapper.text()).toContain(evaluatedCommit.slice(0, 12));
    expect(wrapper.text()).toContain(finalCommit.slice(0, 12));
    expect(wrapper.get(".commit-subject").text()).toBe("accepted candidate");
    expect(wrapper.find(".commit-toggle").exists()).toBe(false);
  });

  it("renders an accepted commit message as collapsible Markdown", async () => {
    const evaluatedCommit = "abcdef1234567890";
    const finalCommit = "fedcba0987654321";
    const message = [
      "evolve(deep-research@v2.0.0): 修复检索索引未校验导致的越界读取",
      "",
      "## 问题",
      "",
      "聚类「检索索引读取失败」包含 3 个来源 bad case。",
      "",
      "## 改动",
      "",
      "- 读取前校验 `chunk_count`",
      "- 补充边界测试",
      "",
      "## 追溯",
      "",
      "- https://example.com/run/1",
      "",
      "---",
      "",
      "Harness-Evaluated-Commit: abc",
    ].join("\n");
    const wrapper = mount(StepIterations, {
      props: {
        wid: "ws-test",
        step: iterationStep([
          round({
            status: "accepted",
            candidate: {
              ref: "refs/candidate",
              commit: evaluatedCommit,
              message: "candidate",
            },
            push: { status: "succeeded", attempts: 1, error: null },
            eval: {
              status: "completed",
              current: 84.6,
              candidate: 85.1,
              nextPollAt: null,
            },
            accepted: true,
            finalCommit: { hash: finalCommit, message },
          }),
        ]),
      },
    });

    const commit = wrapper.get(".commit");
    expect(commit.get(".commit-subject").text()).toBe(
      "evolve(deep-research@v2.0.0): 修复检索索引未校验导致的越界读取",
    );
    expect(commit.text()).not.toContain("##");
    expect(commit.text()).not.toContain("---");
    expect(commit.find(".commit-message").exists()).toBe(false);
    expect(commit.get(".commit-toggle").attributes("aria-expanded")).toBe("false");
    expect(commit.get(".commit-toggle").text()).toContain(
      "查看完整 commit message",
    );

    await commit.get(".commit-toggle").trigger("click");

    expect(commit.find(".commit-message").exists()).toBe(true);
    expect(
      commit.findAll(".commit-message h2").map((heading) => heading.text()),
    ).toEqual(["问题", "改动", "追溯"]);
    expect(commit.findAll(".commit-message li")).toHaveLength(3);
    const link = commit.get(".commit-message a");
    expect(link.attributes("href")).toBe("https://example.com/run/1");
    expect(link.attributes("target")).toBe("_blank");
    expect(link.attributes("rel")).toBe("noopener noreferrer");
    expect(commit.text()).not.toContain("##");
    expect(commit.text()).not.toContain("---");
    expect(commit.get(".commit-toggle").text()).toContain("收起完整 commit message");
    expect(commit.get(".commit-toggle").attributes("aria-expanded")).toBe("true");

    await commit.get(".commit-toggle").trigger("click");

    expect(commit.find(".commit-message").exists()).toBe(false);
    expect(wrapper.text()).toContain("Harness-Evaluated-Commit");
    expect(commit.text()).toContain(finalCommit.slice(0, 12));
  });

  it("colors only the content lines of the real unified diff", () => {
    const wrapper = mount(DiffView, {
      props: {
        patch: {
          files: [
            {
              file: "SKILL.md",
              lines: ["---", "- **所有模式**", "+ 新增说明"],
              overwrite: true,
            },
          ],
          note: "多文件修复",
          diff: [
            "diff --git a/SKILL.md b/SKILL.md",
            "index 1111111..2222222 100644",
            "--- a/SKILL.md",
            "+++ b/SKILL.md",
            "@@ -1,3 +1,3 @@",
            "---",
            "-**所有模式**",
            "+**新增模式**",
            " 保持不变",
            "diff --git a/config/synthetic-review.json b/config/synthetic-review.json",
            "--- a/config/synthetic-review.json",
            "+++ b/config/synthetic-review.json",
            "@@ -1 +1 @@",
            '-  "requestTimeoutSeconds": 30',
            '+  "requestTimeoutSeconds": 60',
          ],
        },
      },
    });

    expect(wrapper.findAll(".fhead").map((node) => node.text())).toEqual([
      "SKILL.md",
      "config/synthetic-review.json",
    ]);
    const lines = wrapper.findAll(".dline");
    expect(lines.map((node) => node.text())).toEqual([
      "@@ -1,3 +1,3 @@",
      "---",
      "-**所有模式**",
      "+**新增模式**",
      "保持不变",
      "@@ -1 +1 @@",
      '-  "requestTimeoutSeconds": 30',
      '+  "requestTimeoutSeconds": 60',
    ]);
    expect(lines[0]?.classes()).toContain("hunk");
    expect(lines[1]?.classes()).toContain("del");
    expect(lines[2]?.classes()).toContain("del");
    expect(lines[3]?.classes()).toContain("add");
    expect(lines[4]?.classes()).toContain("ctx");
    expect(lines[5]?.classes()).toContain("hunk");
    expect(lines[6]?.classes()).toContain("del");
    expect(lines[7]?.classes()).toContain("add");
    expect(wrapper.findAll(".dline.del")).toHaveLength(3);
  });

  it("renders a neutral whole-file preview when no diff was stored", () => {
    const wrapper = mount(DiffView, {
      props: {
        patch: {
          files: [
            {
              file: "SKILL.md",
              lines: [
                "---",
                "- **所有模式**",
                "+ 不是新增",
                "普通正文",
              ],
              overwrite: true,
            },
          ],
          note: "历史轮次",
          diff: null,
        },
      },
    });

    expect(wrapper.find(".preview-note").text()).toContain("整文件预览");
    expect(wrapper.findAll(".fhead").map((node) => node.text())).toEqual(["SKILL.md"]);
    expect(wrapper.findAll(".dline.del")).toHaveLength(0);
    expect(wrapper.findAll(".dline.add")).toHaveLength(0);
    expect(wrapper.findAll(".dline.preview")).toHaveLength(4);
  });

  it("renders attribution summary rows with cached and fresh sources", () => {
    const attribution = {
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
    const queryClient = new QueryClient({
      defaultOptions: { queries: { initialData: { items: [] }, staleTime: Infinity } },
    });
    const wrapper = mount(StepAttribution, {
      global: { plugins: [[VueQueryPlugin, { queryClient }]] },
      props: { wid: "ws-test", step: attribution, run },
    });

    expect(wrapper.text()).toContain("读取越界");
    expect(wrapper.text()).toContain("非该对象问题");
    expect(wrapper.text()).toContain("缓存");
    expect(wrapper.text()).toContain("新增");
    expect(wrapper.text()).toContain("82%");

    const sourceLinks = wrapper.findAll("td.id a");
    expect(sourceLinks).toHaveLength(2);
    expect(sourceLinks[0]?.attributes("href")).toBe(
      "/workspaces/ws-test/sessions/session-1/errors?case=case-1&tab=desc",
    );
    expect(sourceLinks[0]?.attributes("target")).toBe("_blank");
    expect(sourceLinks[0]?.attributes("rel")).toBe("noopener noreferrer");
    expect(sourceLinks[0]?.attributes("aria-label")).toBe(
      "来源问题 case-1，在新窗口打开问题描述",
    );

    const reportLinks = wrapper.findAll("td.report-id a");
    expect(reportLinks).toHaveLength(2);
    expect(reportLinks[0]?.attributes("href")).toBe(
      "/workspaces/ws-test/sessions/session-1/errors?case=case-1&tab=attr&at=attr-1",
    );
    expect(reportLinks[1]?.attributes("href")).toBe(
      "/workspaces/ws-test/sessions/session-2/errors?case=case-2&tab=attr&at=attr-2",
    );
    expect(reportLinks[0]?.attributes("target")).toBe("_blank");
    expect(reportLinks[0]?.attributes("rel")).toBe("noopener noreferrer");
    expect(reportLinks[0]?.attributes("aria-label")).toBe(
      "归因报告 attr-1，在新窗口打开归因分析",
    );
    expect(reportLinks[0]?.attributes("title")).toBe("归因报告 ID · 打开归因分析");
  });

  it("shows the final push status and timestamp", () => {
    const final = {
      key: "final",
      index: 6,
      title: "测试集终评",
      status: "done",
      clickable: true,
      payload: {
        verdict: true,
        bestVersion: "v2.0.1",
        bestScore: 88.9,
        initScore: 84.3,
        degraded: false,
        metrics: [],
        changes: [],
      },
    } satisfies EvolutionStepFinal;
    const wrapper = mount(StepFinal, {
      props: {
        step: final,
        targetVersion: "v2.0.0",
        pushStatus: "succeeded",
        pushedAt: "2026-10-27T12:00:00+08:00",
      },
    });

    expect(wrapper.text()).toContain("最终 push 成功");
    expect(wrapper.text()).toContain("2026-10-27 12:00");
  });
});
