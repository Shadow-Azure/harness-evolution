<script setup lang="ts">
import type {
  EvolutionRunDetail,
  EvolutionRunEvent,
  EvolutionStepKey,
} from "@harness/contracts";
import { useQueryClient } from "@tanstack/vue-query";
import { computed, onUnmounted, ref, watch } from "vue";
import { type LocationQueryRaw, useRoute, useRouter } from "vue-router";

import ErrorState from "../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../components/ui/LoadingSkeleton.vue";
import { retryEvolutionRun } from "../../api/evolutionRuns";
import { queryKeys } from "../../api/queryKeys";
import { formatApiError } from "../../app/apiError";
import { mergeRunEvents } from "../../composables/useEvolutionRunEventLog";
import {
  runDetailRefetchInterval,
  useEvolutionRunDetail,
} from "../../composables/useEvolutionRunDetail";
import { useEvolutionRunStep } from "../../composables/useEvolutionRunStep";
import { useRunEvents } from "../../composables/useRunEvents";
import { useEvolutionTargets } from "../../composables/useEvolutionTargets";
import { useWorkspaceId } from "../../composables/useWorkspaceId";
import { workspacePath } from "../../router/workspace";
import { useAuthStore } from "../../stores/auth";
import { attributionCategory } from "../../utils/attributionCategory";
import { canManageWorkspace } from "../../utils/workspaceDisplay";
import RunControl from "./components/RunControl.vue";
import RunStepContent from "./components/RunStepContent.vue";
import RunStepper from "./components/RunStepper.vue";
import RunLogPanel from "./components/RunLogPanel.vue";
import {
  caseSessionMap,
  formatLocalDateTime,
  resolveRunStepKey,
  runTargetLabel,
  runTargets,
  workspacePushStatusLabel,
} from "./runDetail";

defineOptions({ name: "EvolutionRunDetailPage" });

const route = useRoute();
const router = useRouter();
const queryClient = useQueryClient();
const auth = useAuthStore();
const workspaceId = useWorkspaceId();
const canManage = computed(() => canManageWorkspace(auth.workspaceById(workspaceId.value)?.role));

const runId = computed(() => String(route.params.runId ?? ""));
const {
  data: run,
  dataUpdatedAt: runUpdatedAt,
  error: runError,
  isPending: runPending,
  refetch: refetchRun,
} = useEvolutionRunDetail(workspaceId, runId, {
  refetchInterval: runDetailRefetchInterval,
});

const isActive = computed(
  () => run.value?.status === "preparing" || run.value?.status === "running",
);
const runMembers = computed(() => (run.value ? runTargets(run.value) : []));
const runConfigs = useEvolutionTargets(computed(() => workspaceId.value));
/**
 * Resolve the configuration that launched this run by its first member.
 *
 * Members are globally unique to one configuration, so the identity lookup is
 * stable even when the run shell predates `target_config_id` exposure.
 */
const runConfig = computed(() => {
  const first = runMembers.value[0];
  if (!first) return null;
  return (
    runConfigs.data.value?.items.find((item) =>
      item.members.some(
        (member) =>
          member.objectType === first.type && member.objectName === first.name,
      ),
    ) ?? null
  );
});
const sharedProject = computed(() => {
  const config = runConfig.value;
  if (!config) return null;
  return {
    validationProjectId: config.validationProjectId,
    testProjectId: config.testProjectId,
    primaryMetricKey: config.primaryMetricKey,
  };
});
const changeScope = computed(() => {
  const workspace = run.value?.workspace;
  if (!workspace) return [];
  return workspace.subDirs?.length ? workspace.subDirs : [workspace.subDir];
});
const loadedSeq = ref(0);
/**
 * Seed the SSE cursor once from the run snapshot's high-water mark.
 *
 * The log panel paginates from REST; replaying the whole durable history into
 * `liveEvents` would bypass that pagination. The snapshot seq lets the ticket
 * replay only the gap between the snapshot and the live stream.
 */
let cursorSeeded = false;
watch(
  () => run.value?.lastEventSeq,
  (seq) => {
    if (cursorSeeded || run.value === undefined) return;
    cursorSeeded = true;
    if (seq !== undefined && seq > loadedSeq.value) loadedSeq.value = seq;
  },
  { immediate: true },
);
const liveEvents = ref<EvolutionRunEvent[]>([]);
const logResetToken = ref(0);
const isRetrying = ref(false);
const retryAccepted = ref(false);
const retryError = ref("");
/** Blocked facts captured when a retry was accepted. */
const retryAcceptedFacts = ref<{ errorAt: string; nextRetryAt: string }>({
  errorAt: "",
  nextRetryAt: "",
});
let retryAcceptedTimer: ReturnType<typeof setTimeout> | null = null;

/** Accepted retries expire on their own so a fast failure never freezes the button. */
const RETRY_ACCEPTED_FALLBACK_MS = 10_000;

function currentBlockedFacts(): { errorAt: string; nextRetryAt: string } {
  const snapshot = queryClient.getQueryData<EvolutionRunDetail>(
    queryKeys.evolutionRun(workspaceId.value, runId.value),
  );
  return {
    errorAt: snapshot?.error?.at ?? "",
    nextRetryAt: snapshot?.nextRetryAt ?? "",
  };
}

function stopRetryAcceptedTimer(): void {
  if (retryAcceptedTimer !== null) {
    clearTimeout(retryAcceptedTimer);
    retryAcceptedTimer = null;
  }
}

function forgetRetryAccepted(): void {
  stopRetryAcceptedTimer();
  retryAccepted.value = false;
}

function markRetryAccepted(): void {
  stopRetryAcceptedTimer();
  retryAcceptedFacts.value = currentBlockedFacts();
  retryAccepted.value = true;
  retryAcceptedTimer = setTimeout(forgetRetryAccepted, RETRY_ACCEPTED_FALLBACK_MS);
}

onUnmounted(stopRetryAcceptedTimer);

function appendLiveEvent(event: EvolutionRunEvent): void {
  liveEvents.value = mergeRunEvents(liveEvents.value, [event]);
}

function acceptLoadedSeq(seq: number): void {
  if (seq > loadedSeq.value) loadedSeq.value = seq;
}

function resetRunSnapshot(): void {
  liveEvents.value = [];
  logResetToken.value += 1;
  void refetchRun();
}

useRunEvents(workspaceId, runId, loadedSeq, isActive, {
  onEvent: appendLiveEvent,
  onReset: resetRunSnapshot,
});

watch(
  () => [run.value?.status ?? "", run.value?.error?.at ?? "", run.value?.nextRetryAt ?? ""] as const,
  ([status, errorAt, nextRetryAt]) => {
    if (status !== "blocked") {
      forgetRetryAccepted();
      return;
    }
    if (!retryAccepted.value) return;
    const accepted = retryAcceptedFacts.value;
    if (accepted.errorAt !== errorAt || accepted.nextRetryAt !== nextRetryAt) {
      forgetRetryAccepted();
    }
  },
);

const stepPage = ref(1);
const steps = computed(() => run.value?.steps ?? []);
const selectedKey = computed(() => resolveRunStepKey(route.query.step, steps.value));
const selectedStep = computed(
  () => steps.value.find((step) => step.key === selectedKey.value) ?? null,
);
const rangeStep = computed(() => steps.value.find((step) => step.key === "range"));
const attributionStep = computed(
  () => steps.value.find((step) => step.key === "attribution"),
);
watch(selectedKey, () => {
  stepPage.value = 1;
});
const focusCluster = computed(() =>
  typeof route.query.cluster === "string" ? route.query.cluster : undefined,
);
const branchCopied = ref(false);
const activeTab = computed<"steps" | "logs">(() =>
  route.query.tab === "logs" ? "logs" : "steps",
);

const stepPageSize = computed(() => {
  if (selectedKey.value === "sessions") return 4;
  if (selectedKey.value === "potential") return 5;
  return undefined;
});
const stepPageParam = computed(() =>
  stepPageSize.value === undefined ? undefined : stepPage.value,
);

/**
 * Info-panel facts live on the range and attribution steps, not on the run
 * shell. Both queries share query keys with the selected step, so opening that
 * step reuses the cached payload instead of issuing a second request.
 */
const { data: rangeData } = useEvolutionRunStep(
  workspaceId,
  runId,
  "range",
  computed(() => activeTab.value === "steps" && rangeStep.value?.clickable === true),
);
const { data: attributionData, refetch: refetchAttribution } = useEvolutionRunStep(
  workspaceId,
  runId,
  "attribution",
  computed(
    () => activeTab.value === "steps" && attributionStep.value?.clickable === true,
  ),
);
// Steps 5 and 6 deep-link source cases by Session; attribution rows cover
// every selected case and are not paginated.
const caseSessions = computed(() =>
  caseSessionMap(attributionData.value),
);

// The run's REST fallback also refreshes partial reports when SSE is disconnected.
watch(runUpdatedAt, () => {
  if (
    activeTab.value === "steps" && attributionData.value?.status === "active" &&
    attributionStep.value?.clickable
  ) {
    void refetchAttribution({ cancelRefetch: false });
  }
});

const {
  data: stepData,
  error: stepError,
  isPending: stepPending,
  refetch: refetchStep,
} = useEvolutionRunStep(
  workspaceId,
  runId,
  selectedKey,
  computed(() => selectedStep.value?.clickable === true),
  stepPageParam,
  stepPageSize,
);

const statusLabel = computed(() => {
  if (run.value?.controlState === "paused") return "已暂停";
  if (run.value?.controlState === "pause_requested") return "暂停中";
  switch (run.value?.status) {
    case "preparing":
      return "准备中";
    case "running":
      return "正在执行";
    case "blocked":
      return "已阻塞";
    case "completed":
      if (!run.value.final) return "已完成 · 终评未知";
      if (run.value.degraded) return "已完成 · 聚类降级";
      return run.value.final.verdict ? "✓ 已完成 · 自进化有效" : "已完成 · 无收益";
    case "failed":
      return "失败";
    case "interrupted":
      return "已中断";
    default:
      return "";
  }
});

const statusClass = computed(() => {
  if (run.value?.controlState === "paused" || run.value?.controlState === "pause_requested") return "blocked";
  const status = run.value?.status;
  if (status === "completed") {
    if (!run.value?.final) return "pending";
    if (run.value.degraded) return "pending";
    return run.value.final.verdict ? "accepted" : "rejected";
  }
  if (status === "blocked" || status === "interrupted") return "blocked";
  if (status === "failed") return "failed";
  return "running";
});

const blockedStageLabel = computed(() => {
  switch (run.value?.blockedStage ?? run.value?.error?.stage) {
    case "patch":
      return "补丁生成（patch）阶段";
    case "push":
      return "推送（push）阶段";
    case "eval":
      return "评测（eval）阶段";
    case "attribution":
      return "归因（attribution）阶段";
    default:
      return "未知阶段";
  }
});

const windowLabel = computed(() => {
  const value = run.value?.window;
  if (!value) return "—";
  if (value.from && value.to) return `${value.from} ~ ${value.to}`;
  if (value.from) return `${value.from} ~ 至今`;
  if (value.to) return `起始未知 ~ ${value.to}`;
  return "时间窗未设置";
});

const workspaceName = computed(
  () => auth.workspaceById(workspaceId.value)?.name ?? "—",
);

const rangeCondition = computed(() => {
  const step = rangeData.value;
  return step?.key === "range" ? step.payload.condition : null;
});

const isDefaultPolicy = computed(() => {
  const policy = rangeCondition.value?.policy;
  if (!policy || typeof policy !== "object") return false;
  return (policy as { preset?: unknown }).preset === "default";
});

// Each linked report has one conclusion. The legend splits attributed reports by source.
const reportCounts = computed(() => {
  const step = attributionData.value;
  if (step?.key !== "attribution") return null;
  const { rows, summary } = step.payload;
  const byCategory = { error: 0, prompt: 0, flow: 0, context: 0, model: 0 };
  let reused = 0;
  let inconclusive = 0;
  for (const row of rows) {
    if (row.conclusion === "inconclusive") {
      inconclusive++;
      continue;
    }
    if (row.conclusion === "non_target" || row.category === null) continue;
    byCategory[row.category]++;
    if (row.source === "cached") reused++;
  }
  const attributed = rows.length - summary.nonTarget - inconclusive;
  return {
    total: summary.potential,
    reported: rows.length,
    attributed,
    nonTarget: summary.nonTarget,
    inconclusive,
    reused,
    fresh: attributed - reused,
    byCategory,
  };
});

const distributionTotal = computed(
  () => reportCounts.value?.total ?? run.value?.stats.potential ?? 0,
);
const panelAttributed = computed(
  () => reportCounts.value?.attributed ?? run.value?.stats.attributed ?? 0,
);
const pendingCount = computed(() =>
  Math.max(0, distributionTotal.value - (reportCounts.value?.reported ?? panelAttributed.value)),
);

const distribution = computed(() => {
  const stats = reportCounts.value?.byCategory ?? run.value?.stats.byCategory;
  if (!stats) return [];
  const items = [
    { key: "error", label: attributionCategory("error"), value: stats.error, color: "var(--red)" },
    { key: "prompt", label: attributionCategory("prompt"), value: stats.prompt, color: "var(--orange)" },
    { key: "flow", label: attributionCategory("flow"), value: stats.flow ?? 0, color: "var(--blue)" },
    { key: "context", label: attributionCategory("context"), value: stats.context ?? 0, color: "var(--green)" },
    { key: "model", label: attributionCategory("model"), value: stats.model, color: "var(--purple)" },
  ];
  if (reportCounts.value) {
    items.push({
      key: "nonTarget",
      label: "非该对象",
      value: reportCounts.value.nonTarget,
      color: "var(--text-faint)",
    });
  }
  if (reportCounts.value?.inconclusive) {
    items.push({
      key: "inconclusive",
      label: "证据不足",
      value: reportCounts.value.inconclusive,
      color: "var(--text-dim)",
    });
  }
  if (pendingCount.value > 0) {
    items.push({
      key: "pending",
      label: "未归因",
      value: pendingCount.value,
      color: "var(--border)",
    });
  }
  return items;
});

const stepErrorCode = computed(() => {
  const error = stepError.value;
  if (error && typeof error === "object" && "code" in error) {
    return String(error.code);
  }
  return "";
});

const runErrorCode = computed(() => {
  const error = runError.value;
  if (error && typeof error === "object" && "code" in error) {
    return String(error.code);
  }
  return "";
});

function selectStep(key: typeof selectedKey.value): void {
  const step = steps.value.find((candidate) => candidate.key === key);
  if (!step?.clickable) return;
  if (key !== selectedKey.value) stepPage.value = 1;
  const query: LocationQueryRaw = { ...route.query, step: key };
  delete query.tab;
  if (key !== "clusters") delete query.cluster;
  void router.replace({
    query,
  });
}

function openTab(tab: "steps" | "logs"): void {
  const query: LocationQueryRaw = { ...route.query };
  if (tab === "logs") query.tab = "logs";
  else delete query.tab;
  void router.replace({ query });
}

function selectEventStep(key: EvolutionStepKey): void {
  selectStep(key);
}

function focusEventCluster(clusterId: string): void {
  const clusterStep = steps.value.find((step) => step.key === "clusters");
  if (!clusterStep?.clickable) return;
  const query: LocationQueryRaw = {
    ...route.query,
    step: "clusters",
    cluster: clusterId,
  };
  delete query.tab;
  void router.replace({ query });
}

function retryRun(): void {
  void refetchRun();
}

function retryErrorMessage(error: unknown): string {
  const code =
    error && typeof error === "object" && "code" in error
      ? String(error.code)
      : "";
  if (code === "RUN_NOT_RETRYABLE") {
    return "运行状态已变化，当前不可重试，请稍后刷新。";
  }
  if (code === "RUN_NOT_FOUND") {
    return "运行不存在或已被删除。";
  }
  return formatApiError(error, "重试请求失败").message;
}

async function retryBlockedRun(): Promise<void> {
  if (isRetrying.value || retryAccepted.value) return;
  isRetrying.value = true;
  retryError.value = "";
  let accepted = false;
  try {
    await retryEvolutionRun(workspaceId.value, runId.value);
    accepted = true;
    await queryClient.invalidateQueries({
      queryKey: queryKeys.evolutionRun(workspaceId.value, runId.value),
    });
  } catch (caught) {
    if (!accepted) retryError.value = retryErrorMessage(caught);
  } finally {
    isRetrying.value = false;
    if (accepted) markRetryAccepted();
  }
}

function retryStep(): void {
  void refetchStep();
}

async function copyBranch(): Promise<void> {
  const branch = run.value?.workspace.branchName;
  if (!branch) return;
  try {
    await navigator.clipboard.writeText(branch);
    branchCopied.value = true;
  } catch {
    branchCopied.value = false;
  }
}

function clearMissingClusterFocus(): void {
  if (!("cluster" in route.query)) return;
  const query: LocationQueryRaw = { ...route.query };
  delete query.cluster;
  void router.replace({ query });
}
</script>

<template>
  <section
    class="run-detail-page"
    data-testid="evolution-run-detail"
  >
    <RouterLink
      class="back"
      :to="workspacePath(workspaceId, 'evolution')"
    >
      ← 返回自进化列表
    </RouterLink>

    <LoadingSkeleton
      v-if="runPending"
      label="正在读取运行详情"
      :rows="4"
    />
    <ErrorState
      v-else-if="runErrorCode === 'RUN_NOT_FOUND'"
      code="EVOLUTION_RUN_NOT_FOUND"
      message="运行不存在或已被删除"
      :retryable="false"
    />
    <ErrorState
      v-else-if="runError"
      code="EVOLUTION_RUN_UNAVAILABLE"
      message="运行详情读取失败，请重试"
      @retry="retryRun"
    />
    <template v-else-if="run">
      <header class="detail-head">
        <h1>{{ run.title }}</h1>
        <span
          v-if="runMembers.length > 1"
          class="badge members"
          data-testid="run-member-count"
        >{{ runMembers.length }} 个对象</span>
        <span
          class="badge"
          :class="statusClass"
        >{{ statusLabel }}</span>
        <span
          class="badge space"
          data-testid="run-workspace-badge"
        >{{ workspaceName }}</span>
        <RunControl
          v-if="run.controlState"
          :wid="workspaceId"
          :run="run"
          :can-manage="canManage"
        />
      </header>

      <div
        v-if="run.status === 'blocked'"
        class="blocked-banner"
        data-testid="blocked-banner"
        role="alert"
      >
        <span class="blocked-title">运行在{{ blockedStageLabel }}阻塞</span>
        <span>{{ run.error?.message ?? "错误详情暂不可用" }}</span>
        <span class="mono muted">自动重试 {{ run.retryAttempts }} 次</span>
        <span
          v-if="run.nextRetryAt"
          class="retry-copy mono muted"
          data-testid="next-retry-at"
        >等待自动重试 · {{ formatLocalDateTime(run.nextRetryAt) }}</span>
        <span
          v-else-if="run.retryAttempts >= 3"
          class="mono muted"
        >自动重试次数已用尽</span>
        <span
          v-if="run.error"
          class="mono muted"
        >{{ formatLocalDateTime(run.error.at) }}</span>
        <button
          type="button"
          class="retry-run"
          data-testid="run-retry"
          :disabled="isRetrying || retryAccepted"
          @click="retryBlockedRun"
        >
          {{ isRetrying ? "提交中…" : retryAccepted ? "已提交重试" : "重试" }}
        </button>
        <span
          v-if="retryAccepted"
          class="retry-note"
          data-testid="retry-accepted"
        >重试任务已受理，等待运行推进。</span>
        <span
          v-if="retryError"
          class="retry-error"
          data-testid="retry-error"
        >{{ retryError }}</span>
        <button
          type="button"
          class="log-jump"
          data-testid="open-error-log"
          @click="openTab('logs')"
        >
          查看执行日志
        </button>
      </div>
      <div
        v-else-if="run.status === 'interrupted'"
        class="interrupted-banner"
        data-testid="interrupted-banner"
        role="status"
      >
        <span class="blocked-title">任务被中断，系统将自动恢复；可查看最后事件</span>
        <span v-if="run.error">{{ run.error.message }}</span>
        <button
          type="button"
          class="log-jump"
          data-testid="open-error-log"
          @click="openTab('logs')"
        >
          查看执行日志
        </button>
      </div>
      <div
        v-else-if="run.error"
        class="error-banner"
        role="alert"
      >
        <b>{{ run.error.stage }}</b>
        <span>{{ run.error.message }}</span>
        <span class="mono muted">{{ run.error.at }}</span>
        <button
          type="button"
          class="log-jump"
          data-testid="open-error-log"
          @click="openTab('logs')"
        >
          查看执行日志
        </button>
      </div>

      <div
        class="detail-tabs"
        role="tablist"
        aria-label="运行详情视图"
      >
        <button
          type="button"
          role="tab"
          data-testid="steps-tab"
          :aria-selected="activeTab === 'steps'"
          :class="{ active: activeTab === 'steps' }"
          @click="openTab('steps')"
        >
          七步详情
        </button>
        <button
          type="button"
          role="tab"
          data-testid="logs-tab"
          :aria-selected="activeTab === 'logs'"
          :class="{ active: activeTab === 'logs' }"
          @click="openTab('logs')"
        >
          执行日志
          <span
            v-if="run.lastEventSeq"
            class="tab-count mono"
          >≤ {{ run.lastEventSeq }}</span>
        </button>
      </div>

      <template v-if="activeTab === 'steps'">
        <article
          class="card panel info-panel"
          data-testid="run-info-panel"
        >
          <h2 class="sec-title">
            目标与输入
            <span class="sub">时间段内当前空间上报的 bad case 是本次进化的候选集</span>
          </h2>
          <div class="kv-grid">
            <div class="kv">
              <div class="k">
                进化对象 · {{ runTargetLabel(run) }}
              </div>
              <div
                class="v target-chips"
                data-testid="run-target-members"
              >
                <span
                  v-for="member in runMembers"
                  :key="`${member.type}:${member.name}`"
                  class="chip kind"
                  :title="member.subDir || undefined"
                >{{ member.type }}:{{ member.name }}</span>
              </div>
            </div>
            <div class="kv">
              <div class="k">
                版本
              </div>
              <div class="v mono">
                <span>{{ run.target.version }}</span>
                <span
                  v-if="run.target.targetRevision"
                  class="revision"
                  data-testid="run-target-revision"
                  :title="run.target.targetRevision"
                >{{ run.target.targetRevision }}</span>
                <span
                  v-else
                  class="revision muted"
                  data-testid="run-target-revision-missing"
                >历史运行未记录 revision</span>
                <span
                  v-if="runMembers.length > 1"
                  class="muted"
                > · 全部成员共用</span>
              </div>
            </div>
            <div
              v-if="sharedProject"
              class="kv"
              data-testid="run-test-project"
            >
              <div class="k">
                测试工程
              </div>
              <div class="v">
                <span class="mono">验证集 {{ sharedProject.validationProjectId || "—" }} · 测试集 {{ sharedProject.testProjectId || "—" }} · 主指标 {{ sharedProject.primaryMetricKey || "—" }}</span>
                <span class="muted"> · 成员共用</span>
              </div>
            </div>
            <div class="kv">
              <div class="k">
                时间段（bad case 上报）
              </div>
              <div class="v mono">
                {{ windowLabel }}
              </div>
            </div>
            <div class="kv">
              <div class="k">
                工作空间
              </div>
              <div class="v">
                {{ workspaceName }}
              </div>
            </div>
            <div class="kv">
              <div class="k">
                关联 Session
              </div>
              <div class="v big">
                {{ run.stats.sessions }}
                <span class="muted">/ 版本未知 {{ run.stats.versionUnresolvedSessions }}</span>
              </div>
            </div>
            <div class="kv">
              <div class="k">
                时间段内 bad case
              </div>
              <div class="v big">
                {{ run.stats.badCases }}
              </div>
            </div>
            <div class="kv">
              <div class="k">
                潜在 bad case
              </div>
              <div class="v big accent">
                {{ distributionTotal }}
              </div>
            </div>
            <div class="kv">
              <div class="k">
                可归因 / 非该对象
              </div>
              <div class="v big">
                {{ panelAttributed }} <span class="muted">/ {{ reportCounts?.nonTarget ?? "—" }}</span>
              </div>
            </div>
            <div
              v-if="run.attributionSkill"
              class="kv"
              data-testid="run-attribution-skill"
            >
              <div class="k">
                归因 Skill 快照
              </div>
              <div class="v">
                <span class="mono">{{ run.attributionSkill.key }}@r{{ run.attributionSkill.revision }}</span>
                <span class="muted"> · {{ run.attributionSkill.engine }}</span>
                <span
                  class="mono muted"
                  :title="run.attributionSkill.contentHash"
                > · sha256:{{ run.attributionSkill.contentHash.slice(0, 12) }}</span>
              </div>
            </div>
          </div>
          <p class="cb-label">
            潜在 bad case 的归因结论分布（{{ distributionTotal }} 条）
          </p>
          <div
            class="typebar"
            aria-label="潜在 bad case 的归因结论分布"
          >
            <span
              v-for="item in distribution"
              :key="item.key"
              :style="{
                width: `${distributionTotal ? (item.value / distributionTotal) * 100 : 0}%`,
                background: item.color,
              }"
            />
          </div>
          <div class="legend">
            <span
              v-for="item in distribution"
              :key="item.key"
            >
              <span
                class="dot"
                :style="{ background: item.color }"
              />
              {{ item.label }} <b>{{ item.value }}</b>
            </span>
            <span class="muted">＝ 归因 {{ panelAttributed }} · 复用缓存 {{ reportCounts?.reused ?? "—" }} · 本次新增 {{ reportCounts?.fresh ?? "—" }}</span>
          </div>
          <div
            v-if="rangeCondition"
            class="f-inline policy-row"
            data-testid="run-policy-cache"
          >
            <span
              class="v2-badge"
              :class="{ ok: isDefaultPolicy }"
            >{{ isDefaultPolicy ? "默认策略 · 对象自身 self 上报 或 触发点在其后" : "自定义策略" }}</span>
            <span
              class="v2-badge"
              :class="rangeCondition.cacheEnabled ? 'ok' : 'warn'"
            >{{ rangeCondition.cacheEnabled ? "复用缓存归因" : "不复用缓存" }}</span>
          </div>
          <details
            class="workspace-detail"
            data-testid="run-workspace"
          >
            <summary>
              工作区
              <span class="sub">分支 / 基线 / 仓库 / 推送与评测状态</span>
            </summary>
            <div class="workspace-grid">
              <div class="kv">
                <div class="k">
                  run 分支
                </div>
                <div class="v">
                  <button
                    v-if="run.workspace.branchName"
                    class="branch-copy mono"
                    type="button"
                    data-testid="copy-branch"
                    :title="`点击复制分支名 ${run.workspace.branchName}`"
                    @click="copyBranch"
                  >
                    {{ run.workspace.branchName }}
                    <span aria-live="polite">{{ branchCopied ? " · 已复制" : " · 复制" }}</span>
                  </button>
                  <span
                    v-else
                    class="muted"
                  >尚未创建</span>
                </div>
              </div>
              <div class="kv">
                <div class="k">
                  基线 ref / commit
                </div>
                <div class="v mono">
                  {{ run.workspace.baseRef ?? "—" }} /
                  {{ run.workspace.baseCommit?.slice(0, 12) ?? "—" }}
                </div>
              </div>
              <div class="kv">
                <div class="k">
                  仓库
                </div>
                <div class="v mono workspace-path">
                  {{ run.workspace.repoUrl }}
                </div>
              </div>
              <div class="kv">
                <div class="k">
                  改动范围
                </div>
                <div
                  class="v mono"
                  data-testid="run-change-scope"
                >
                  <div
                    v-for="dir in changeScope"
                    :key="dir"
                  >
                    {{ dir }}/**
                  </div>
                </div>
              </div>
              <div class="kv">
                <div class="k">
                  推送状态
                </div>
                <div class="v mono">
                  {{ workspacePushStatusLabel(run.workspace.pushStatus) }}
                </div>
              </div>
              <div class="kv">
                <div class="k">
                  推送时间
                </div>
                <div class="v mono">
                  {{ run.workspace.pushedAt?.replace("T", " ").slice(0, 16) ?? "尚未推送" }}
                </div>
              </div>
              <div class="kv">
                <div class="k">
                  评测状态
                </div>
                <div class="v mono">
                  {{ run.evalStatus }}
                </div>
              </div>
              <div class="kv">
                <div class="k">
                  推送目标
                </div>
                <div
                  class="v mono workspace-path"
                  data-testid="run-push-repo"
                >
                  {{ run.workspace.pushRepoUrl }}
                </div>
              </div>
            </div>
            <p
              v-if="run.workspace.pushError"
              class="workspace-error"
            >
              推送错误：{{ run.workspace.pushError }}
            </p>
            <details
              v-if="run.workspace.workspacePath || run.workspace.repoPath"
              class="workspace-paths"
            >
              <summary>查看本地路径</summary>
              <p class="mono">
                workspace: {{ run.workspace.workspacePath ?? "—" }}<br>
                repo: {{ run.workspace.repoPath ?? "—" }}
              </p>
            </details>
          </details>
        </article>

        <article
          class="card panel"
          data-testid="run-progress"
        >
          <h2 class="sec-title">
            流程进度
            <span class="sub">
              当前查看：第 {{ (selectedStep?.index ?? 0) + 1 }} 步 ·
              {{ selectedStep?.title ?? "选择范围" }}
            </span>
          </h2>
          <RunStepper
            :steps="steps"
            :selected="selectedKey"
            :paused="run.controlState === 'paused'"
            @select="selectStep"
          />
        </article>

        <div
          v-if="run.status === 'preparing' && run.controlState !== 'paused'"
          class="preparing-copy"
        >
          <span class="pulse" />
          已受理，正在准备筛选与聚类。此步骤完成前后续节点保持禁用。
        </div>

        <ErrorState
          v-if="stepError && stepErrorCode !== 'STEP_NOT_READY'"
          code="EVOLUTION_RUN_STEP_UNAVAILABLE"
          message="当前步骤读取失败，请重试"
          @retry="retryStep"
        />
        <p
          v-else-if="stepErrorCode === 'STEP_NOT_READY'"
          class="pending-copy"
        >
          该步骤尚未到达。
        </p>
        <RunStepContent
          v-else
          :wid="workspaceId"
          :run="run"
          :step="stepData"
          :is-pending="selectedStep?.clickable === true && stepPending"
          :is-unreached="selectedStep?.clickable !== true"
          :focus-cluster="focusCluster"
          :can-write="canManage"
          :case-sessions="caseSessions"
          :shared-project="sharedProject"
          :sub-dirs="run.workspace.subDirs"
          @page-change="stepPage = $event"
          @missing-cluster-focus="clearMissingClusterFocus"
        />
      </template>
      <RunLogPanel
        v-else
        :wid="workspaceId"
        :run-id="run.runId"
        :steps="steps"
        :live-events="liveEvents"
        :reset-token="logResetToken"
        @loaded-seq="acceptLoadedSeq"
        @select-step="selectEventStep"
        @focus-cluster="focusEventCluster"
      />
    </template>
  </section>
</template>

<style scoped>
.run-detail-page {
  /* Page-level scroll container: the workspace shell fixes main's height and
     hides overflow, so the page owns the scrollbar. Full width keeps the
     classic scrollbar at the window's right edge; the symmetric inline
     padding centers the V2 prototype's 1720px content column. */
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 14px;
  min-width: 0;
  height: 100%;
  padding: 20px max(24px, calc((100% - 1720px) / 2 + 24px)) 64px;
  overflow-y: auto;
}

.back {
  color: var(--text-dim);
  font-size: 12px;
  text-decoration: none;
}

.back:hover {
  color: var(--blue);
}

.detail-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.detail-head :deep(.run-control) {
  margin-left: auto;
}

.detail-head h1 {
  margin: 0;
  color: var(--text);
  font-size: 17px;
  font-weight: 700;
}

.badge.space {
  background: color-mix(in srgb, var(--blue) 8%, transparent);
  color: var(--text-dim);
}

.badge.members {
  background: color-mix(in srgb, var(--purple) 10%, transparent);
  color: var(--purple);
}

.badge {
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}

.badge.running {
  background: color-mix(in srgb, var(--blue) 13%, transparent);
  color: var(--blue);
}

.badge.accepted {
  background: color-mix(in srgb, var(--green) 13%, transparent);
  color: var(--green);
}

.badge.rejected,
.badge.pending {
  background: color-mix(in srgb, var(--text-faint) 18%, transparent);
  color: var(--text-dim);
}

.badge.blocked {
  background: color-mix(in srgb, var(--orange) 12%, transparent);
  color: var(--orange);
}

.badge.failed {
  background: color-mix(in srgb, var(--red) 11%, transparent);
  color: var(--red);
}

.blocked-banner,
.interrupted-banner,
.error-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 14px;
  border-radius: 10px;
  flex-wrap: wrap;
  font-size: 12.5px;
}

.blocked-banner {
  border: 1px solid color-mix(in srgb, var(--orange) 42%, transparent);
  background: color-mix(in srgb, var(--orange) 8%, transparent);
  color: var(--text-dim);
}

.interrupted-banner {
  border: 1px solid color-mix(in srgb, var(--orange) 30%, transparent);
  background: color-mix(in srgb, var(--orange) 6%, transparent);
  color: var(--text-dim);
}

.error-banner {
  border: 1px solid color-mix(in srgb, var(--red) 38%, transparent);
  background: color-mix(in srgb, var(--red) 7%, transparent);
  color: var(--text-dim);
}

.log-jump {
  margin-left: auto;
  padding: 3px 8px;
  border: 1px solid color-mix(in srgb, var(--red) 35%, transparent);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--red);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}

.retry-run {
  padding: 3px 12px;
  border: 1px solid color-mix(in srgb, var(--orange) 45%, transparent);
  border-radius: 6px;
  background: color-mix(in srgb, var(--orange) 12%, transparent);
  color: var(--orange);
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.retry-run:disabled {
  cursor: wait;
  opacity: 0.6;
}

.retry-note {
  color: var(--green);
  font-size: 11px;
}

.retry-error {
  color: var(--red);
  font-size: 11.5px;
}

.detail-tabs {
  display: flex;
  gap: 3px;
  border-bottom: 1px solid var(--border);
}

.detail-tabs button {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px 8px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-faint);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.detail-tabs button.active {
  border-bottom-color: var(--blue);
  color: var(--text);
  font-weight: 650;
}

.tab-count {
  color: var(--text-faint);
  font-size: 10px;
}

.blocked-title {
  color: var(--orange);
  font-weight: 700;
}

.retry-copy {
  margin-left: auto;
  color: var(--text-faint);
  font-size: 11.5px;
}

.card {
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.panel {
  padding: 16px 18px;
}

.sec-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  color: var(--text);
  font-size: 13.5px;
  font-weight: 650;
}

.sub {
  color: var(--text-faint);
  font-size: 11.5px;
  font-weight: 400;
}

.kv-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px 20px;
  margin-bottom: 14px;
}

.target-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.kv .v .chip {
  display: inline-block;
  padding: 1px 9px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 10.5px;
  white-space: nowrap;
}

.kv .v .chip.kind {
  border-color: color-mix(in srgb, var(--purple) 35%, transparent);
  background: color-mix(in srgb, var(--purple) 9%, transparent);
  color: var(--purple);
  font-family: var(--mono);
}

.workspace-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px 20px;
}

.workspace-path {
  word-break: break-all;
}

.branch-copy {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-dim);
  font-size: inherit;
  text-align: left;
  cursor: pointer;
}

.branch-copy:hover,
.branch-copy:focus-visible {
  color: var(--blue);
}

.branch-copy span {
  color: var(--text-faint);
  font-size: 10.5px;
}

.workspace-paths {
  margin-top: 12px;
  color: var(--text-dim);
  font-size: 11.5px;
}

.workspace-error {
  margin: 10px 0 0;
  color: var(--red);
  font-size: 11.5px;
}

.workspace-paths summary {
  cursor: pointer;
  color: var(--text-faint);
}

.workspace-paths p {
  margin: 8px 0 0;
  word-break: break-all;
}

.k,
.cb-label {
  margin: 0 0 2px;
  color: var(--text-faint);
  font-size: 11px;
}

.v {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
  color: var(--text);
  font-size: 13px;
  font-weight: 600;
}

.v.big {
  font-family: var(--mono);
  font-size: 15px;
}

.v.accent {
  color: var(--blue);
}

.chip {
  display: inline-block;
  padding: 1px 9px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 10.5px;
}

.chip.kind {
  border-color: color-mix(in srgb, var(--purple) 35%, transparent);
  background: color-mix(in srgb, var(--purple) 9%, transparent);
  color: var(--purple);
  font-family: var(--mono);
}

.f-inline {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.policy-row {
  margin-top: 10px;
}

.v2-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 10.5px;
  white-space: nowrap;
}

.v2-badge.ok {
  border-color: color-mix(in srgb, var(--green) 38%, transparent);
  background: color-mix(in srgb, var(--green) 8%, transparent);
  color: var(--green);
}

.v2-badge.warn {
  border-color: color-mix(in srgb, var(--orange) 40%, transparent);
  background: color-mix(in srgb, var(--orange) 8%, transparent);
  color: var(--orange);
}

.workspace-detail {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.workspace-detail > summary {
  cursor: pointer;
  color: var(--text-dim);
  font-size: 12px;
  font-weight: 600;
}

.workspace-detail > summary .sub {
  margin-left: 8px;
}

.workspace-detail .workspace-grid {
  margin-top: 12px;
}

.typebar {
  display: flex;
  height: 10px;
  margin: 6px 0 8px;
  overflow: hidden;
  border-radius: 5px;
}

.typebar span {
  display: block;
  height: 100%;
}

.legend {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  color: var(--text-dim);
  font-size: 11.5px;
}

.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 5px;
  border-radius: 2px;
}

.legend b {
  font-family: var(--mono);
}

.mono {
  font-family: var(--mono);
}

.muted {
  color: var(--text-faint);
}

.revision {
  display: block;
  max-width: 260px;
  margin-top: 2px;
  overflow-wrap: anywhere;
  color: var(--text-faint);
  font-size: 10.5px;
}

.preparing-copy,
.pending-copy {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 12px 14px;
  border: 1px dashed var(--border);
  border-radius: 10px;
  color: var(--text-dim);
  font-size: 12.5px;
}

.pulse {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--blue);
  animation: pulse 1.4s infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.25;
  }
}

@media (max-width: 640px) {
  /* The workspace shell switches main to document flow at this breakpoint,
     so the page must stop owning scrolling and let the document scroll. */
  .run-detail-page {
    height: auto;
    padding: 14px 12px 48px;
    overflow-y: visible;
  }
}

@media (max-width: 860px) {
  .kv-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .workspace-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .kv-grid {
    grid-template-columns: 1fr;
  }

  .workspace-grid {
    grid-template-columns: 1fr;
  }

  .retry-copy {
    width: 100%;
    margin-left: 0;
  }
}
</style>
