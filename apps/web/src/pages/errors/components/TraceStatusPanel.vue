<script setup lang="ts">
import type { BadCaseTraceStatus } from "@harness/contracts";
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";

import { workspacePath } from "../../../router/workspace";
import { formatStartedAt } from "../../../utils/sessionDisplay";
import { badCaseSyncErrorLabel } from "../../../utils/syncStatus";
import type { TraceStatusDetails } from "../traceStatus";

const props = defineProps<{
  wid: string;
  caseId: string;
  sessionId: string;
  details: TraceStatusDetails;
}>();

const emit = defineEmits<{
  refresh: [];
  "open-sync": [];
}>();

const statusLabels: Record<BadCaseTraceStatus, string> = {
  ready: "就绪",
  pending: "未同步",
  syncing: "同步中",
  failed: "同步失败",
  unavailable: "无可用轨迹",
};
const statusLabel = computed(() => statusLabels[props.details.syncStatus]);
const title = computed(() => props.details.title || "该 bad case");
const lastError = computed(() => props.details.lastError);
const lastErrorLabel = computed(() =>
  lastError.value ? `${lastError.value} · ${badCaseSyncErrorLabel(lastError.value)}` : "—",
);
const headline = computed(() => {
  switch (props.details.syncStatus) {
    case "pending":
      return "该 bad case 的 Session 轨迹尚未同步";
    case "syncing":
      return "该 bad case 的 Session 轨迹正在同步";
    case "failed":
      return "该 bad case 的 Session 轨迹同步失败";
    default:
      return "该 bad case 还没有可用的 Session 轨迹";
  }
});
const explanation = computed(() => {
  if (props.details.retryable) {
    return "问题本身已上报，没有被删除；系统会按退避计划自动重试，同步成功后刷新即可恢复执行流与归因，不需要重新创建 case。";
  }
  return "问题本身已上报，没有被删除；当前配置下无法自动恢复，修改轨迹查询配置后会重新触发同步，不需要重新创建 case。";
});
const copied = ref(false);

async function copyCaseId() {
  const value = props.caseId || props.details.badCaseId;
  try {
    await navigator.clipboard?.writeText(value);
    copied.value = true;
    window.setTimeout(() => {
      copied.value = false;
    }, 2_000);
  } catch {
    copied.value = false;
  }
}
</script>

<template>
  <section
    class="trace-panel"
    data-testid="trace-status-panel"
  >
    <header class="trace-hero">
      <span
        class="trace-icon"
        aria-hidden="true"
      >!</span>
      <div>
        <h1>{{ headline }}</h1>
        <p>{{ explanation }}</p>
      </div>
    </header>

    <div class="trace-meta">
      <span
        class="trace-badge"
        :class="`trace-${details.syncStatus}`"
        data-testid="trace-status-chip"
      >{{ statusLabel }}</span>
      <span>lastError <code data-testid="trace-last-error">{{ lastErrorLabel }}</code></span>
      <span data-testid="trace-retryable">{{ details.retryable ? "可自动重试" : "不会自动重试" }}</span>
      <span>上次尝试 {{ details.lastAttemptAt ? formatStartedAt(details.lastAttemptAt) : "—" }}</span>
      <span v-if="details.nextRetryAt">下次重试 {{ formatStartedAt(details.nextRetryAt) }}</span>
    </div>

    <div class="trace-actions">
      <button
        class="trace-action primary"
        data-testid="trace-open-sync"
        type="button"
        @click="emit('open-sync')"
      >
        查看同步状态
      </button>
      <button
        class="trace-action"
        data-testid="trace-refresh"
        type="button"
        @click="emit('refresh')"
      >
        刷新状态
      </button>
      <RouterLink
        class="trace-action"
        data-testid="trace-back-overview"
        :to="workspacePath(wid, 'overview')"
      >
        返回总览
      </RouterLink>
      <button
        class="trace-action"
        data-testid="trace-copy-id"
        type="button"
        @click="copyCaseId"
      >
        {{ copied ? "已复制 bad case ID" : "复制 bad case ID" }}
      </button>
    </div>

    <div class="trace-note">
      <b>bad case</b> {{ caseId || details.badCaseId }} · {{ title }}<br>
      上报来源 {{ details.objectName || "—" }} · 上报时间 {{ details.createdAt ? formatStartedAt(details.createdAt) : "—" }} · 关联 Session {{ sessionId || details.sessionId }}<br>
      处理建议：确认上游 session query 是否配置，或让上报方补充 sessionSource；同步状态入口在顶部「同步」弹层。
    </div>
  </section>
</template>

<style scoped>
.trace-panel {
  display: grid;
  gap: 16px;
  margin: 16px 0 0;
  padding: 24px 26px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-card);
  box-shadow: 0 1px 3px rgb(30 40 60 / 5%);
}

.trace-hero {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--border);
}

.trace-icon {
  display: grid;
  flex: none;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--orange) 12%, transparent);
  color: var(--orange);
  font-size: 18px;
  font-weight: 700;
}

.trace-hero h1 {
  margin: 0 0 4px;
  color: var(--text);
  font-size: 17px;
  font-weight: var(--weight-bold);
}

.trace-hero p {
  margin: 0;
  color: var(--text-dim);
  font-size: 12.5px;
  line-height: 1.7;
}

.trace-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: center;
  padding: 11px 13px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-panel);
  color: var(--text-dim);
  font-size: 11.5px;
}

.trace-meta code {
  color: var(--text);
  font-family: var(--mono);
  font-size: 10.5px;
}

.trace-badge {
  display: inline-flex;
  padding: 1px 8px;
  border: 1px solid currentColor;
  border-radius: 999px;
  color: var(--orange);
  font-size: 10px;
  white-space: nowrap;
}

.trace-badge.trace-ready {
  color: var(--green);
}

.trace-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.trace-action {
  display: inline-flex;
  align-items: center;
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-card);
  color: var(--text-dim);
  cursor: pointer;
  font: inherit;
  font-size: 11.5px;
  text-decoration: none;
}

.trace-action:hover {
  border-color: var(--border-strong);
  color: var(--text);
}

.trace-action.primary {
  border-color: var(--blue);
  background: var(--blue);
  color: #fff;
}

.trace-action.primary:hover {
  color: #fff;
}

.trace-note {
  padding: 12px 14px;
  border-left: 3px solid var(--border);
  color: var(--text-faint);
  font-size: 11.5px;
  line-height: 1.8;
}

.trace-note b {
  color: var(--text-dim);
}
</style>
