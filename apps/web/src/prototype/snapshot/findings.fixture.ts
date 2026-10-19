import type { EvidenceRef, Finding } from "@harness/contracts";

function anchor(input: {
  agentThreadId: string;
  agentPath: string;
  rolloutId: string;
  ordinal: number;
  line: number;
  callId: string | null;
  turnId: string | null;
  excerpt: string;
}): EvidenceRef {
  return {
    id: `${input.rolloutId}#${input.ordinal}`,
    rolloutId: input.rolloutId,
    agentThreadId: input.agentThreadId,
    agentPath: input.agentPath,
    ordinal: input.ordinal,
    line: input.line,
    recordType: "response_item",
    turnId: input.turnId,
    callId: input.callId,
    itemId: null,
    excerpt: input.excerpt,
  };
}

/**
 * Hand-curated cross-agent findings derived from the four M1 session families.
 * The fixture contains identifiers and short excerpts, never raw JSONL.
 */
export const EXAMPLE_FINDINGS: readonly Finding[] = [
  {
    id: "finding:gh-network-duplication",
    familyRootThreadId: "01a14ee6-d117-7c71-84a7-32b46bb3a99b",
    title: "多个子 agent 重复执行 gh 查询，网络不可达时未短路",
    summary:
      "主 agent 并行派发 review 子任务后，多个子 agent 各自执行 gh pr view，均因 api.github.com 不可达失败；没有先集中探测网络或共享 PR 元数据。",
    impact: "子 agent 在启动阶段浪费轮次，证据收集被同一基础设施故障阻塞。",
    severity: "P1",
    category: "agent-orchestration",
    sourceAgentThreadIds: [
      "01a14ee6-d117-7c71-84a7-32b46bb3a99b",
      "01a14f27-84f3-73f2-a259-7525d73bbdff",
      "01a14f27-b7f1-7391-b6fd-f38afb01ced5",
      "01a14f28-0adb-7b31-b8fe-ff99dd8dabb0",
      "01a14f2b-bdaa-7582-9710-a14af43f8016",
      "01a14f2f-4288-7452-ae4d-93d570c13801",
      "01a14f43-0227-7811-aa2b-ab6efe3e146d",
    ],
    attribution: {
      target: {
        type: "agent",
        id: "agent:01a14ee6-d117-7c71-84a7-32b46bb3a99b",
        name: "root",
      },
      reason: "根 agent 负责派发与共享上下文，未在派发前验证 GitHub 可达性，也未缓存 PR 元数据。",
      confidence: "confirmed",
      unverified: "未验证是否存在可用的离线 PR 元数据缓存。",
    },
    evidence: [
      anchor({
        agentThreadId: "01a14ee6-d117-7c71-84a7-32b46bb3a99b",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T20-05-12-01a14ee6-d117-7c71-84a7-32b46bb3a99b.jsonl",
        ordinal: 25,
        line: 26,
        callId: "call_02_RR3gdCv9Z23GipOosQkQ0942",
        turnId: "01a14ee6-d4b9-71d1-9dd3-af81c724edd4",
        excerpt: "Process exited with code 1; error connecting to api.github.com",
      }),
      anchor({
        agentThreadId: "01a14f27-84f3-73f2-a259-7525d73bbdff",
        agentPath: "/root/v64_dependency_semantics",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T21-15-52-01a14f27-84f3-73f2-a259-7525d73bbdff.jsonl",
        ordinal: 70,
        line: 71,
        callId: "call_01_uE9THjcJtyIpTHlZwYi89204",
        turnId: "01a14f27-855b-78d2-b7cb-2ae5997a0d60",
        excerpt: "gh pr view 62; error connecting to api.github.com",
      }),
      anchor({
        agentThreadId: "01a14f27-b7f1-7391-b6fd-f38afb01ced5",
        agentPath: "/root/v64_dependency_semantics/analyze_64_inject_semantics",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T21-16-05-01a14f27-b7f1-7391-b6fd-f38afb01ced5.jsonl",
        ordinal: 79,
        line: 80,
        callId: "call_01_kNk1cNocLJyVn0tYAkkP4862",
        turnId: "01a14f27-b84e-7843-a2d8-5a2ca558cd16",
        excerpt: "gh pr view 62; error connecting to api.github.com",
      }),
      anchor({
        agentThreadId: "01a14f28-0adb-7b31-b8fe-ff99dd8dabb0",
        agentPath: "/root/v64_dependency_semantics/analyze_64_inject_semantics/analyze_6_4",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T21-16-26-01a14f28-0adb-7b31-b8fe-ff99dd8dabb0.jsonl",
        ordinal: 78,
        line: 79,
        callId: "call_03_bt0whwYZhOh95u8dKWWT0571",
        turnId: "01a14f28-0b28-7631-9294-da443573a418",
        excerpt: "gh pr view 62; error connecting to api.github.com",
      }),
      anchor({
        agentThreadId: "01a14f2b-bdaa-7582-9710-a14af43f8016",
        agentPath: "/root/v64_dependency_semantics/fix_64_inject_semantics",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T21-20-29-01a14f2b-bdaa-7582-9710-a14af43f8016.jsonl",
        ordinal: 80,
        line: 81,
        callId: "call_01_tdk3BPVAcHynM1CoTYiH0441",
        turnId: "01a14f2b-be01-76e1-9c87-5b3ec167712e",
        excerpt: "gh pr view 62; error connecting to api.github.com",
      }),
      anchor({
        agentThreadId: "01a14f2f-4288-7452-ae4d-93d570c13801",
        agentPath:
          "/root/v64_dependency_semantics/fix_64_inject_semantics/fix_64_contract_wording",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T21-24-19-01a14f2f-4288-7452-ae4d-93d570c13801.jsonl",
        ordinal: 78,
        line: 79,
        callId: "call_02_ArRAT7LvNooyyhZxJfOC7017",
        turnId: "01a14f2f-42d8-7dc3-849a-954c5ef86d7b",
        excerpt: "gh pr view 62; error connecting to api.github.com",
      }),
      anchor({
        agentThreadId: "01a14f43-0227-7811-aa2b-ab6efe3e146d",
        agentPath: "/root/v64_review_with_context",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T21-45-54-01a14f43-0227-7811-aa2b-ab6efe3e146d.jsonl",
        ordinal: 71,
        line: 72,
        callId: "call_02_XYSCb47a9L53KhexqKQH9216",
        turnId: "01a14f43-02e6-71a3-b02a-11700fa5db08",
        excerpt: "gh pr view 62; error connecting to api.github.com",
      }),
    ],
    status: "example",
  },
  {
    id: "finding:skill-path-drift",
    familyRootThreadId: "01a14e5b-5d48-7382-9fed-1d2295a163c1",
    title: "同一 skill 通过三种缓存路径加载",
    summary:
      "根 agent 与 4 个子 agent 都读取 systematic-debugging，但路径分别落在 claude-plugins cache、.tmp/plugins 与 openai-api-curated cache。",
    impact: "按路径统计会把同一 skill 拆成多个目标，归因与自进化聚合会断裂。",
    severity: "P1",
    category: "skill-usage",
    sourceAgentThreadIds: [
      "01a14e5b-5d48-7382-9fed-1d2295a163c1",
      "01a14e89-414a-7bb3-80bb-20c8eaa8a434",
      "01a14e91-3dbe-7840-98d0-a24878372cf6",
      "01a14e92-3207-7ed0-ab92-226edf2d4bf4",
      "01a14e92-33a1-74a1-8366-9fbe66c1aee3",
    ],
    attribution: {
      target: {
        type: "skill",
        id: "skill:systematic-debugging",
        name: "systematic-debugging",
      },
      reason: "5 个 agent 的显式 SKILL.md 读取都指向同一 basename，差异只在缓存根。",
      confidence: "confirmed",
      unverified: null,
    },
    evidence: [
      anchor({
        agentThreadId: "01a14e5b-5d48-7382-9fed-1d2295a163c1",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T17-32-52-01a14e5b-5d48-7382-9fed-1d2295a163c1.jsonl",
        ordinal: 1131,
        line: 1132,
        callId: "call_00_kLCFOMMftAqnOORf2c3J7472",
        turnId: "01a14e83-4785-7053-b0e0-0715541f0db2",
        excerpt: ".../claude-plugins-official/superpowers/6.4.1/skills/systematic-debugging/SKILL.md",
      }),
      anchor({
        agentThreadId: "01a14e89-414a-7bb3-80bb-20c8eaa8a434",
        agentPath: "/root/debug_nested_sources2",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T18-23-00-01a14e89-414a-7bb3-80bb-20c8eaa8a434.jsonl",
        ordinal: 62,
        line: 63,
        callId: "call_00_uNhhDyI8MTVY0nHc1n2p7569",
        turnId: "01a14e89-421d-7803-bb7d-46a065876f78",
        excerpt: ".../.tmp/plugins/plugins/superpowers/skills/systematic-debugging/SKILL.md",
      }),
      anchor({
        agentThreadId: "01a14e91-3dbe-7840-98d0-a24878372cf6",
        agentPath: "/root/review_pr62_fixes",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T18-31-43-01a14e91-3dbe-7840-98d0-a24878372cf6.jsonl",
        ordinal: 63,
        line: 64,
        callId: "call_00_hx58WmK0KfuMDvTuAfCV4524",
        turnId: "01a14e91-3e0e-74f0-8a5f-096cb7cbcb13",
        excerpt: ".../claude-plugins-official/superpowers/6.4.1/skills/systematic-debugging/SKILL.md",
      }),
      anchor({
        agentThreadId: "01a14e92-3207-7ed0-ab92-226edf2d4bf4",
        agentPath: "/root/explain_arch_flow2",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T18-32-46-01a14e92-3207-7ed0-ab92-226edf2d4bf4.jsonl",
        ordinal: 100,
        line: 101,
        callId: "call_00_fpQl4sx1Tc87VkIMUmkT1185",
        turnId: "01a14e92-3262-7891-acab-64faf3a4476d",
        excerpt: ".../claude-plugins-official/superpowers/6.4.1/skills/systematic-debugging/SKILL.md",
      }),
      anchor({
        agentThreadId: "01a14e92-33a1-74a1-8366-9fbe66c1aee3",
        agentPath: "/root/explain_design_flow2",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T18-32-46-01a14e92-33a1-74a1-8366-9fbe66c1aee3.jsonl",
        ordinal: 49,
        line: 50,
        callId: "call_00_oRi853rCVqQHXo9Jexvs2853",
        turnId: "01a14e92-33f4-73b2-82c5-ad1f5de9bc83",
        excerpt: ".../openai-api-curated/superpowers/0722921d/skills/systematic-debugging/SKILL.md",
      }),
    ],
    status: "example",
  },
  {
    id: "finding:walkthrough-skill-reload",
    familyRootThreadId: "01a14c79-9e02-7210-ada9-ae4ff5c6ae05",
    title: "walkthrough skill 被根 agent 反复加载 31 次",
    summary:
      "根 agent 在同一 turn 内多次读取 walkthrough-change-metadata-gen/SKILL.md，首次还因路径错误失败；子 agent Copernicus 又独立加载一次。",
    impact: "重复读取挤占上下文与轮次，且暴露 skill 路径与缓存策略不一致。",
    severity: "P1",
    category: "skill-usage",
    sourceAgentThreadIds: [
      "01a14c79-9e02-7210-ada9-ae4ff5c6ae05",
      "01a14d0b-a483-7443-aa78-1fd24e70f1b2",
    ],
    attribution: {
      target: {
        type: "skill",
        id: "skill:walkthrough-change-metadata-gen",
        name: "walkthrough-change-metadata-gen",
      },
      reason: "显式读取证据集中在根 agent，子 agent 未复用同一 skill 上下文。",
      confidence: "confirmed",
      unverified: "31 次计数来自 SKILL.md 调用匹配，未区分读取片段大小。",
    },
    evidence: [
      anchor({
        agentThreadId: "01a14c79-9e02-7210-ada9-ae4ff5c6ae05",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T08-46-41-01a14c79-9e02-7210-ada9-ae4ff5c6ae05.jsonl",
        ordinal: 14,
        line: 15,
        callId: "exec_command_2_96bf433e",
        turnId: "01a14c7a-2b62-78e2-b2c3-9c4cf582b8c0",
        excerpt: "cat ~/.agents/skills/walkthrough-change-metadata-gen/SKILL.md",
      }),
      anchor({
        agentThreadId: "01a14c79-9e02-7210-ada9-ae4ff5c6ae05",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T08-46-41-01a14c79-9e02-7210-ada9-ae4ff5c6ae05.jsonl",
        ordinal: 19,
        line: 20,
        callId: "exec_command_2_96bf433e",
        turnId: "01a14c7a-2b62-78e2-b2c3-9c4cf582b8c0",
        excerpt: "Process exited with code 1; cat: .../SKILL.md",
      }),
      anchor({
        agentThreadId: "01a14c79-9e02-7210-ada9-ae4ff5c6ae05",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T08-46-41-01a14c79-9e02-7210-ada9-ae4ff5c6ae05.jsonl",
        ordinal: 52,
        line: 53,
        callId: "exec_command_10_98bc8746",
        turnId: "01a14c7a-2b62-78e2-b2c3-9c4cf582b8c0",
        excerpt: "cat .agents/skills/walkthrough-change-metadata-gen/SKILL.md",
      }),
      anchor({
        agentThreadId: "01a14c79-9e02-7210-ada9-ae4ff5c6ae05",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T08-46-41-01a14c79-9e02-7210-ada9-ae4ff5c6ae05.jsonl",
        ordinal: 70,
        line: 71,
        callId: "exec_command_14_e499f71a",
        turnId: "01a14c7a-2b62-78e2-b2c3-9c4cf582b8c0",
        excerpt: "cat .agents/skills/walkthrough-change-metadata-gen/SKILL.md",
      }),
      anchor({
        agentThreadId: "01a14c79-9e02-7210-ada9-ae4ff5c6ae05",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T08-46-41-01a14c79-9e02-7210-ada9-ae4ff5c6ae05.jsonl",
        ordinal: 79,
        line: 80,
        callId: "exec_command_16_04d76d52",
        turnId: "01a14c7a-2b62-78e2-b2c3-9c4cf582b8c0",
        excerpt: "cat .agents/skills/walkthrough-change-metadata-gen/SKILL.md",
      }),
      anchor({
        agentThreadId: "01a14d0b-a483-7443-aa78-1fd24e70f1b2",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T11-26-11-01a14d0b-a483-7443-aa78-1fd24e70f1b2.jsonl",
        ordinal: 10,
        line: 11,
        callId: "call_118a1f53b8364a49a71440a6",
        turnId: "01a14d0b-a58e-7ee0-a2b2-38c31d85beec",
        excerpt: "sed -n '1,240p' .agents/skills/walkthrough-change-metadata-gen/SKILL.md",
      }),
    ],
    status: "example",
  },
  {
    id: "finding:parallel-patch-conflict",
    familyRootThreadId: "01a14d49-f4a0-7c31-ad9a-b6e3c034501a",
    title: "并行子 agent 在共享文件上反复 patch 失败",
    summary:
      "根 agent 使用 subagent-driven-development 并行派发任务，多个子 agent 对同一批文件执行 apply_patch，出现 expected lines 找不到与上下文失效。",
    impact: "子 agent 反复重试同一 patch，主 agent 需要额外轮次收敛，验证证据被稀释。",
    severity: "P1",
    category: "agent-orchestration",
    sourceAgentThreadIds: [
      "01a14d49-f4a0-7c31-ad9a-b6e3c034501a",
      "01a14da6-7e05-7c33-b31d-24e1c536a0b1",
      "01a14db0-def4-7f11-b141-3b975cfa1966",
      "01a14dd4-d983-79a2-989a-9020266b6b50",
      "01a14de9-8a81-7ab3-a39f-40cddf00c34f",
    ],
    attribution: {
      target: {
        type: "skill",
        id: "skill:subagent-driven-development",
        name: "subagent-driven-development",
      },
      reason: "并行工作流由该 skill 指导，但没有按文件分区或串行化共享文件写入。",
      confidence: "inferred",
      unverified: "未验证每个 patch 失败是否都源于同一文件的并发写入。",
    },
    evidence: [
      anchor({
        agentThreadId: "01a14d49-f4a0-7c31-ad9a-b6e3c034501a",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T12-34-14-01a14d49-f4a0-7c31-ad9a-b6e3c034501a.jsonl",
        ordinal: 586,
        line: 587,
        callId: "call_adcd2b1d64a94184b26b6c25",
        turnId: "01a14d92-92b9-7922-9d6b-cd0695c86952",
        excerpt: ".../claude-plugins-official/superpowers/6.4.1/skills/subagent-driven-development/SKILL.md",
      }),
      anchor({
        agentThreadId: "01a14da6-7e05-7c33-b31d-24e1c536a0b1",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T14-15-19-01a14da6-7e05-7c33-b31d-24e1c536a0b1.jsonl",
        ordinal: 154,
        line: 155,
        callId: "call_d72feafbe6e84c3cb2646636",
        turnId: "01a14da6-7e8b-7480-b419-0de0ca9a831f",
        excerpt: "apply_patch verification failed: Failed to find expected lines",
      }),
      anchor({
        agentThreadId: "01a14db0-def4-7f11-b141-3b975cfa1966",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T14-26-39-01a14db0-def4-7f11-b141-3b975cfa1966.jsonl",
        ordinal: 208,
        line: 209,
        callId: "call_ac6fd8dbc41f4e299388529c",
        turnId: "01a14db0-df74-7ca0-9001-96ad351cc28e",
        excerpt: "Process exited with code 1; Failed to find expected lines",
      }),
      anchor({
        agentThreadId: "01a14dd4-d983-79a2-989a-9020266b6b50",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T15-05-57-01a14dd4-d983-79a2-989a-9020266b6b50.jsonl",
        ordinal: 264,
        line: 265,
        callId: "call_1e777787e4bc4dd9b9f0c523",
        turnId: "01a14dd4-d9de-7700-867b-17b1ab13f7e8",
        excerpt: "Process exited with code 1; Failed to find expected lines",
      }),
      anchor({
        agentThreadId: "01a14de9-8a81-7ab3-a39f-40cddf00c34f",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T15-28-33-01a14de9-8a81-7ab3-a39f-40cddf00c34f.jsonl",
        ordinal: 386,
        line: 387,
        callId: "call_f9b31f29185a404d886be322",
        turnId: "01a14de9-8af7-79d1-89e9-cd2884421806",
        excerpt: "apply_patch verification failed: Failed to find expected lines",
      }),
    ],
    status: "example",
  },
];
