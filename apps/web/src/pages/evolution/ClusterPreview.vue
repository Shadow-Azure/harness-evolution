<script setup lang="ts">
import type { PotentialPolicy, StepRangeCondition } from "@harness/contracts";
import { useQueryClient } from "@tanstack/vue-query";
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { startEvolutionRun } from "../../api/evolutionRuns";
import { queryKeys } from "../../api/queryKeys";
import { formatApiError } from "../../app/apiError";
import ErrorState from "../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../components/ui/LoadingSkeleton.vue";
import {
  runDetailRefetchInterval,
  useEvolutionRunDetail,
} from "../../composables/useEvolutionRunDetail";
import { useEvolutionRunStep } from "../../composables/useEvolutionRunStep";
import { useWorkspaceId } from "../../composables/useWorkspaceId";
import { workspacePath } from "../../router/workspace";
import { useAuthStore } from "../../stores/auth";
import { canManageWorkspace } from "../../utils/workspaceDisplay";
import RunControl from "./components/RunControl.vue";
import StepClusters from "./components/StepClusters.vue";
import { caseSessionMap } from "./runDetail";

defineOptions({ name: "ClusterPreviewPage" });

const route = useRoute();
const router = useRouter();
const queryClient = useQueryClient();
const workspaceId = useWorkspaceId();
const auth = useAuthStore();
const canManage = computed(() => canManageWorkspace(auth.workspaceById(workspaceId.value)?.role));
const runId = computed(() => String(route.params.runId ?? ""));
const { data, error, isPending, refetch } = useEvolutionRunDetail(
  workspaceId,
  runId,
  { refetchInterval: runDetailRefetchInterval },
);

const run = computed(() => data.value ?? null);
const completed = computed(() => run.value?.status === "completed");
const launching = ref(false);
const launchError = ref("");

const {
  data: rangeData,
  error: rangeError,
  refetch: refetchRange,
} = useEvolutionRunStep(workspaceId, runId, "range", completed);
const {
  data: clustersData,
  error: clustersError,
  isPending: clustersPending,
  refetch: refetchClusters,
} = useEvolutionRunStep(workspaceId, runId, "clusters", completed);
const { data: attributionData } = useEvolutionRunStep(
  workspaceId,
  runId,
  "attribution",
  completed,
);

const rangeCondition = computed<StepRangeCondition | null>(() => {
  const step = rangeData.value;
  return step?.key === "range" ? step.payload.condition : null;
});
const clustersStep = computed(() => {
  const step = clustersData.value;
  return step?.key === "clusters" ? step : null;
});
const clusterSessions = computed(() => caseSessionMap(attributionData.value));
const clusterCount = computed(
  () =>
    clustersStep.value?.payload.clusters.length ??
    run.value?.stats.clusters ??
    0,
);
const clusterHeading = computed(() =>
  clusterCount.value > 0
    ? `聚类出的 ${clusterCount.value} 类问题`
    : "聚类结果",
);

const statusLabel = computed(() => {
  if (run.value?.controlState === "paused") return "已暂停";
  if (run.value?.controlState === "pause_requested") return "暂停中";
  switch (run.value?.status) {
    case "preparing":
      return "准备中";
    case "running":
      return "正在聚类";
    case "blocked":
      return "已阻塞";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    case "interrupted":
      return "已中断";
    default:
      return "";
  }
});

const statusTone = computed(() => {
  if (run.value?.controlState === "paused" || run.value?.controlState === "pause_requested") {
    return "paused";
  }
  switch (run.value?.status) {
    case "preparing":
    case "running":
      return "running";
    case "blocked":
      return "blocked";
    case "completed":
      return "completed";
    case "failed":
    case "interrupted":
      return "failed";
    default:
      return "idle";
  }
});

const statusActive = computed(
  () =>
    run.value?.controlState !== "paused" &&
    (run.value?.status === "preparing" || run.value?.status === "running"),
);

const incompleteMessage = computed(() => {
  if (run.value?.status === "interrupted") {
    return "运行已中断，聚类结果未产出。";
  }
  return run.value?.error?.message ?? "运行未给出失败原因，请查看执行日志或重试。";
});

const statusDetail = computed(() => {
  const value = run.value;
  if (!value) return "";
  if (value.controlState === "paused") return "进度已保留，继续后从原检查点恢复。";
  if (value.controlState === "pause_requested") return "等待当前操作结束后暂停。";
  if (
    value.status === "failed" ||
    value.status === "blocked" ||
    value.status === "interrupted"
  ) {
    return incompleteMessage.value;
  }
  if (value.status === "preparing") {
    return value.progress.stageLabel || "正在关联 Session / 筛选潜在 bad case / 生成归因 / 聚类…";
  }
  if (value.status === "running") {
    return value.progress.stageLabel || "正在按严重程度聚类与排序问题簇…";
  }
  return value.progress.stageLabel;
});

const windowLabel = computed(() => {
  const condition = rangeCondition.value;
  if (condition) {
    if (condition.from && condition.to) return `${condition.from} ~ ${condition.to}`;
    if (condition.from) return `${condition.from} ~ 至今`;
    if (condition.to) return `起始未知 ~ ${condition.to}`;
    return "未设置";
  }
  const value = run.value?.window;
  if (!value) return "—";
  if (value.from && value.to) return `${value.from} ~ ${value.to}`;
  return `${value.from ?? "起始未知"} ~ ${value.to ?? "至今"}`;
});

const modelsLabel = computed(() => {
  const models = run.value?.models ?? [];
  return models.length > 0 ? models.join(" / ") : "全部";
});

const policyLabel = computed(() => {
  const preset =
    rangeCondition.value?.policy.preset ?? run.value?.policy.preset ?? "default";
  return preset === "custom" ? "自定义潜在策略" : "默认潜在策略";
});

const targetLabel = computed(() =>
  run.value
    ? `${run.value.target.type}:${run.value.target.name}@${run.value.target.version}`
    : "",
);

const canLaunch = computed(
  () =>
    completed.value &&
    rangeCondition.value !== null &&
    !launching.value,
);

const launchDisabledReason = computed(() => {
  if (canLaunch.value || launching.value) return "";
  if (!completed.value) return "聚类完成后可启动完整自进化。";
  if (rangeCondition.value === null) return "条件快照读取失败，暂时无法启动完整自进化。";
  return "";
});


/**
 * Create a full run from the completed cluster-only run's selection snapshot.
 * @returns Nothing; navigation follows the accepted run.
 */
async function launchFullRun(): Promise<void> {
  const condition = rangeCondition.value;
  if (!condition || launching.value) return;
  launching.value = true;
  launchError.value = "";
  try {
    const accepted = await startEvolutionRun(workspaceId.value, {
      targetType: condition.targetType,
      targetName: condition.targetName,
      targetVersion: condition.targetVersion,
      from: condition.from ?? undefined,
      to: condition.to ?? undefined,
      models: run.value?.models ?? [],
      mode: "full",
      policy: condition.policy as PotentialPolicy,
      cacheEnabled: condition.cacheEnabled,
      ...(!condition.cacheEnabled && condition.attributionPackageId && {
        attributionPackageId: condition.attributionPackageId,
      }),
      page: 1,
      pageSize: 5,
    });
    await queryClient.invalidateQueries({
      queryKey: queryKeys.evolutionRuns(workspaceId.value),
    });
    await router.push(
      workspacePath(
        workspaceId.value,
        `evolution/runs/${encodeURIComponent(accepted.runId)}`,
      ),
    );
  } catch (failure) {
    launchError.value = formatApiError(failure, "启动自进化失败").message;
  } finally {
    launching.value = false;
  }
}

function retry(): void {
  void refetch();
}

function retryRange(): void {
  void refetchRange();
}

function retryClusters(): void {
  void refetchClusters();
}

function backToList(): void {
  void router.push(workspacePath(workspaceId.value, "evolution"));
}
</script>

<template>
  <section
    class="cluster-preview-page"
    data-testid="evolution-cluster-preview"
  >
    <button
      class="back"
      type="button"
      @click="backToList"
    >
      ← 返回运行列表
    </button>

    <LoadingSkeleton
      v-if="isPending"
      label="正在读取仅聚类预览"
      :rows="3"
    />
    <ErrorState
      v-else-if="error"
      code="EVOLUTION_CLUSTER_UNAVAILABLE"
      message="仅聚类预览读取失败，请重试"
      @retry="retry"
    />
    <template v-else-if="run">
      <header class="detail-head">
        <h1>问题聚类结果</h1>
        <span
          class="target-chip"
          :title="targetLabel"
        >{{ targetLabel }}</span>
        <span
          class="badge"
          :class="`status-${statusTone}`"
          data-testid="cluster-status"
        >{{ statusLabel }}</span>
        <RunControl
          v-if="run.controlState"
          :wid="workspaceId"
          :run="run"
          :can-manage="canManage"
        />
      </header>

      <div class="mode-note">
        <span>
          仅聚类分析 · 展示该对象在所选条件下识别出的问题，未执行
          patch 生成与评测迭代。
        </span>
        <span
          v-if="launchDisabledReason"
          class="mode-reason"
        >{{ launchDisabledReason }}</span>
        <button
          class="btn primary"
          type="button"
          data-testid="cluster-launch-full"
          :disabled="!canLaunch"
          :title="launchDisabledReason || '以这批问题创建完整自进化运行'"
          @click="launchFullRun"
        >
          {{ launching ? "正在启动…" : "以这批问题启动自进化 →" }}
        </button>
      </div>
      <p
        v-if="launchError"
        class="inline-error"
        role="alert"
      >
        {{ launchError }}
      </p>

      <div
        class="status-area"
        :class="`is-${statusTone}`"
        :role="statusTone === 'failed' ? 'alert' : 'status'"
        data-testid="cluster-status-detail"
      >
        <span
          v-if="statusActive"
          class="pulse"
        />
        <span class="status-copy">{{ statusDetail }}</span>
      </div>

      <template v-if="completed">
        <section class="card panel">
          <h2 class="sec-title">
            输入概况
            <span class="sub">聚类输入与产出规模</span>
          </h2>
          <div class="run-stats">
            <span class="stat"><b>{{ run.stats.sessions }}</b><span>关联 Session</span></span>
            <span class="stat"><b>{{ run.stats.badCases }}</b><span>问题报告</span></span>
            <span class="stat"><b>{{ run.stats.potential }}</b><span>潜在 bad case</span></span>
            <span class="stat accent"><b>{{ clusterCount }}</b><span>聚类数</span></span>
          </div>
          <p class="condition-line">
            时间段 <span class="mono">{{ windowLabel }}</span>
            · 模型 <span class="mono">{{ modelsLabel }}</span>
            · {{ policyLabel }}
          </p>
        </section>

        <LoadingSkeleton
          v-if="clustersPending"
          label="正在读取聚类结果"
          :rows="3"
        />
        <ErrorState
          v-else-if="clustersError"
          code="EVOLUTION_CLUSTERS_UNAVAILABLE"
          message="聚类结果读取失败，请重试"
          @retry="retryClusters"
        />
        <StepClusters
          v-else-if="clustersStep"
          :wid="workspaceId"
          :step="clustersStep"
          :case-sessions="clusterSessions"
          :title="clusterHeading"
          subtitle="按严重程度降序 · 同类问题才聚为一簇"
        />
      </template>

      <p
        v-if="completed && rangeError"
        class="inline-error"
        role="status"
      >
        条件快照读取失败，暂时无法启动完整自进化。
        <button
          class="link-button"
          type="button"
          @click="retryRange"
        >
          重试
        </button>
      </p>
    </template>
    <ErrorState
      v-else
      code="EVOLUTION_RUN_NOT_FOUND"
      message="运行不存在或已被删除"
      :retryable="false"
    />
  </section>
</template>

<style scoped>
.cluster-preview-page {
  /* Page-level scroll container: the workspace shell fixes main's height and
     hides overflow, so this page owns the scrollbar and centers the same
     1720px content column as run detail. */
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 14px;
  min-width: 0;
  height: 100%;
  padding: 20px max(24px, calc((100% - 1720px) / 2 + 24px)) 64px;
  overflow-y: auto;
  align-content: start;
}

.back {
  justify-self: start;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-dim);
  font-size: 12px;
  cursor: pointer;
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

.detail-head h1 {
  margin: 0;
  color: var(--text);
  font-size: 17px;
  font-weight: 700;
}

.detail-head :deep(.run-control) {
  margin-left: auto;
}

.target-chip {
  min-width: 0;
  max-width: 100%;
  padding: 2px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 11px;
  line-height: 1.5;
  white-space: normal;
  overflow-wrap: anywhere;
}

.mode-note {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-panel);
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1.5;
}

.mode-note > span:first-child {
  flex: 1 1 420px;
  min-width: 0;
  overflow-wrap: anywhere;
}

.mode-reason {
  color: var(--text-faint);
  font-size: 11.5px;
}

.btn {
  padding: 5px 12px;
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 12px;
  white-space: nowrap;
  cursor: pointer;
}

.mode-note .btn {
  margin-left: auto;
}

.btn:hover:not(:disabled) {
  border-color: var(--blue);
  color: var(--text);
}

.btn.primary {
  border-color: var(--blue);
  background: var(--blue);
  color: white;
  font-weight: 600;
}

.btn:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.status-area {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 9px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1.6;
}

.status-copy {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}

.status-area.is-running {
  border-color: color-mix(in srgb, var(--blue) 30%, var(--border));
}

.status-area.is-paused,
.status-area.is-blocked {
  border-color: color-mix(in srgb, var(--orange) 35%, var(--border));
  background: color-mix(in srgb, var(--orange) 5%, var(--bg-card));
}

.status-area.is-failed {
  border-color: color-mix(in srgb, var(--red) 35%, var(--border));
  background: color-mix(in srgb, var(--red) 5%, var(--bg-card));
}

.badge {
  flex: none;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}

.badge.status-running {
  background: color-mix(in srgb, var(--blue) 13%, transparent);
  color: var(--blue);
}

.badge.status-completed {
  background: color-mix(in srgb, var(--green) 13%, transparent);
  color: var(--green);
}

.badge.status-paused,
.badge.status-blocked {
  background: color-mix(in srgb, var(--orange) 13%, transparent);
  color: var(--orange);
}

.badge.status-failed {
  background: color-mix(in srgb, var(--red) 13%, transparent);
  color: var(--red);
}

.card {
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

.run-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  margin-bottom: 8px;
}

.stat {
  color: var(--text-faint);
  font-size: 11px;
}

.stat b {
  margin-right: 3px;
  color: var(--text);
  font-family: var(--mono);
  font-size: 14px;
  font-weight: 650;
}

.stat.accent b {
  color: var(--blue);
}

.condition-line {
  margin: 0;
  color: var(--text-faint);
  font-size: 11.5px;
}

.mono {
  font-family: var(--mono);
}

.pulse {
  flex: none;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--blue);
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 0.3;
    transform: scale(0.85);
  }

  50% {
    opacity: 1;
    transform: scale(1.1);
  }
}

.inline-error {
  margin: 0;
  color: var(--red);
  font-size: 12px;
}

.link-button {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--blue);
  font-size: 12px;
  cursor: pointer;
}

@media (prefers-reduced-motion: reduce) {
  .pulse {
    animation: none;
  }
}

@media (max-width: 640px) {
  /* The workspace shell switches main to document flow at this breakpoint,
     so the page must stop owning scrolling and let the document scroll. */
  .cluster-preview-page {
    height: auto;
    padding: 14px 12px 48px;
    overflow-y: visible;
  }

  .mode-note {
    align-items: flex-start;
  }

  .mode-note .btn {
    margin-left: 0;
  }
}
</style>
