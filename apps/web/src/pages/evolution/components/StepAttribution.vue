<script setup lang="ts">
import type {
  AttributionJobView,
  EvolutionRunCard,
  EvolutionStepAttribution,
  StepAttributionRow,
} from "@harness/contracts";
import { ElMessage } from "element-plus/es/components/message/index";
import { computed, ref } from "vue";

import { formatApiError } from "../../../app/apiError";
import { useAttributionJobs } from "../../../composables/useAttributionJobs";

const props = defineProps<{
  workspaceId?: string;
  canWrite?: boolean;
  step: EvolutionStepAttribution;
  run: EvolutionRunCard;
}>();

const operationError = ref("");
const attributionJobs = props.workspaceId
  ? useAttributionJobs(
      computed(() => props.workspaceId ?? ""),
      computed(() => props.run.runId),
    )
  : null;
const latestJob = computed(() => attributionJobs?.jobs.data.value?.items[0] ?? null);
const canWrite = computed(() => props.canWrite ?? false);
const mutating = computed(
  () =>
    attributionJobs?.start.isPending.value === true ||
    attributionJobs?.retry.isPending.value === true ||
    attributionJobs?.cancel.isPending.value === true,
);

const summary = computed(() => props.step.payload.summary);
const targetLabel = computed(
  () => `${props.run.target.name}@${props.run.target.version}`,
);

function categoryLabel(category: StepAttributionRow["category"]): string {
  if (category === "flow") return "流程";
  if (category === "context") return "上下文";
  if (category === "prompt") return "prompt";
  if (category === "model") return "模型";
  if (category === "error") return "错误";
  return "非该对象问题";
}

function categoryClass(category: StepAttributionRow["category"]): string {
  return category ? `type-${category}` : "type-non-target";
}

function sourceLabel(source: StepAttributionRow["source"]): string {
  return source === "cached" ? "缓存" : "新增";
}

function confidenceLabel(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(0)}%`;
}

function statusLabel(status: AttributionJobView["status"]): string {
  const labels: Record<AttributionJobView["status"], string> = {
    queued: "排队中",
    running: "执行中",
    completed: "已完成",
    failed: "失败",
    interrupted: "已中断",
    cancelled: "已取消",
  };
  return labels[status];
}

async function startJob(): Promise<void> {
  if (!attributionJobs) return;
  operationError.value = "";
  try {
    await attributionJobs.start.mutateAsync();
    ElMessage.success("归因任务已进入队列");
  } catch (error) {
    operationError.value = formatApiError(error, "启动归因任务失败").message;
  }
}

async function retryJob(jobId: string): Promise<void> {
  if (!attributionJobs) return;
  operationError.value = "";
  try {
    await attributionJobs.retry.mutateAsync(jobId);
    ElMessage.success("归因任务已重新排队");
  } catch (error) {
    operationError.value = formatApiError(error, "重试归因任务失败").message;
  }
}

async function cancelJob(jobId: string): Promise<void> {
  if (!attributionJobs) return;
  operationError.value = "";
  try {
    await attributionJobs.cancel.mutateAsync(jobId);
    ElMessage.success("归因任务已取消");
  } catch (error) {
    operationError.value = formatApiError(error, "取消归因任务失败").message;
  }
}
</script>

<template>
  <article class="card panel">
    <h3 class="sec-title">
      第 4 步 · 对象归因
      <span class="sub">每条结论只作用于 {{ targetLabel }}</span>
    </h3>
    <div class="wz-stats">
      <span class="st"><b>{{ summary.potential }}</b><span>潜在 bad case</span></span>
      <span class="st"><b>{{ summary.reused }}</b><span>复用缓存</span></span>
      <span class="st accent"><b>{{ summary.fresh }}</b><span>本次新增</span></span>
      <span class="st"><b>{{ summary.nonTarget }}</b><span>非该对象问题</span></span>
    </div>
    <section
      v-if="latestJob"
      class="runtime-panel"
      data-testid="attribution-job-runtime"
    >
      <div class="runtime-head">
        <div>
          <b>{{ statusLabel(latestJob.status) }}</b>
          <span> · 第 {{ latestJob.attempt }}/{{ latestJob.maxAttempts }} 次</span>
          <span> · {{ latestJob.observation.executor }}</span>
          <span v-if="latestJob.observation.skillRevision"> · {{ latestJob.observation.skillRevision }}</span>
        </div>
        <div
          v-if="canWrite"
          class="runtime-actions"
        >
          <button
            v-if="latestJob.status === 'queued' || latestJob.status === 'running'"
            type="button"
            class="btn subtle"
            :disabled="mutating"
            @click="cancelJob(latestJob.jobId)"
          >
            取消
          </button>
          <button
            v-else-if="latestJob.status === 'failed' || latestJob.status === 'interrupted' || latestJob.status === 'cancelled'"
            type="button"
            class="btn primary"
            :disabled="mutating || latestJob.attempt >= latestJob.maxAttempts"
            @click="retryJob(latestJob.jobId)"
          >
            重试未完成项
          </button>
        </div>
      </div>
      <div class="progress-track">
        <span :style="{ width: `${Math.round(latestJob.progress * 100)}%` }" />
      </div>
      <div class="runtime-metrics">
        <span>完成 {{ latestJob.observation.completed }}/{{ latestJob.observation.total }}</span>
        <span>缓存 {{ latestJob.observation.reused }}</span>
        <span>失败 {{ latestJob.observation.failed }}</span>
        <span>P95 {{ latestJob.observation.p95LatencyMs.toFixed(0) }}ms</span>
        <span>Token {{ latestJob.observation.tokenCount }}</span>
        <span>证据覆盖 {{ (latestJob.observation.evidenceCoverageRate * 100).toFixed(0) }}%</span>
        <span>warning {{ latestJob.observation.warningCount }}</span>
        <span>上下文 {{ latestJob.observation.contextHash?.slice(0, 12) ?? "—" }}</span>
      </div>
      <p
        v-if="latestJob.error"
        class="runtime-error"
      >
        {{ latestJob.error }}
      </p>
    </section>
    <div
      v-else-if="canWrite && run.status === 'blocked'"
      class="runtime-empty"
    >
      <span>当前没有归因执行记录。</span>
      <button
        type="button"
        class="btn primary"
        :disabled="mutating"
        @click="startJob"
      >
        启动归因
      </button>
    </div>
    <p
      v-if="operationError"
      class="runtime-error"
      role="alert"
    >
      {{ operationError }}
    </p>
    <div
      v-if="step.payload.rows.length"
      class="table-scroll"
    >
      <table class="rep">
        <thead>
          <tr>
            <th>来源 bad case</th>
            <th>归因报告 ID</th>
            <th>分类</th>
            <th>问题现象 / 描述</th>
            <th>结果来源</th>
            <th>置信度</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in step.payload.rows"
            :key="row.attributionId"
          >
            <td
              class="id mono"
              :title="row.badCaseId"
            >
              {{ row.badCaseId }}
            </td>
            <td
              class="mono"
              :title="row.attributionId"
            >
              {{ row.attributionId }}
            </td>
            <td>
              <span
                class="type-chip"
                :class="categoryClass(row.category)"
              >{{ categoryLabel(row.category) }}</span>
            </td>
            <td class="desc">
              {{ row.description }}
            </td>
            <td>
              <span
                class="source-chip"
                :class="row.source"
              >{{ sourceLabel(row.source) }}</span>
            </td>
            <td class="mono">
              {{ confidenceLabel(row.confidence) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p
      v-else
      class="waiting"
    >
      没有需要归因的潜在 bad case
    </p>
  </article>
</template>

<style scoped>
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

.wz-stats {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.st {
  color: var(--text-faint);
  font-size: 11px;
}

.st b {
  margin-right: 3px;
  color: var(--text);
  font-family: var(--mono);
  font-size: 14px;
  font-weight: 650;
}

.st.accent b {
  color: var(--blue);
}

.runtime-panel,
.runtime-empty {
  margin-bottom: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-inset);
}

.runtime-head,
.runtime-empty {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--text-faint);
  font-size: 11.5px;
}

.runtime-head b {
  color: var(--text);
}

.runtime-actions {
  display: flex;
  gap: 6px;
}

.btn {
  padding: 5px 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-card);
  color: var(--text);
  cursor: pointer;
  font-size: 11px;
}

.btn.primary {
  border-color: var(--blue);
  background: var(--blue);
  color: var(--bg-card);
}

.btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.progress-track {
  height: 5px;
  margin: 9px 0;
  overflow: hidden;
  border-radius: 999px;
  background: var(--border);
}

.progress-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--blue);
  transition: width 180ms ease;
}

.runtime-metrics {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 10.5px;
}

.runtime-error {
  margin: 8px 0 0;
  color: var(--red);
  font-size: 11px;
}

.table-scroll {
  overflow-x: auto;
}

table.rep {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

table.rep th,
table.rep td {
  padding: 7px 9px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}

table.rep th {
  color: var(--text-faint);
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

table.rep tr:last-child td {
  border-bottom: 0;
}

.id {
  color: var(--blue);
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.desc {
  max-width: 320px;
}

.type-chip,
.source-chip {
  display: inline-block;
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 10.5px;
  white-space: nowrap;
}

.type-error {
  color: var(--red);
}

.type-prompt {
  color: var(--orange);
}

.type-model {
  color: var(--purple);
}

.type-non-target {
  color: var(--orange);
}

.source-chip.cached {
  border-color: color-mix(in srgb, var(--text-faint) 28%, transparent);
  color: var(--text-dim);
}

.source-chip.fresh {
  border-color: color-mix(in srgb, var(--green) 32%, transparent);
  background: color-mix(in srgb, var(--green) 7%, transparent);
  color: var(--green);
}

.mono {
  font-family: var(--mono);
}

.waiting {
  margin: 0;
  padding: 18px;
  border: 1px dashed var(--border);
  border-radius: 10px;
  color: var(--text-faint);
  font-size: 12.5px;
  text-align: center;
}
</style>
