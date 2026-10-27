<script setup lang="ts">
import type { EvolutionStepClusters, StepCluster } from "@harness/contracts";
import { computed, nextTick, ref, watch } from "vue";

const props = defineProps<{
  step: EvolutionStepClusters;
  focusCluster?: string;
}>();

const expanded = ref<Set<string>>(new Set());
const highlighted = ref<string | null>(null);

const clusters = computed(() => props.step.payload.clusters);
const missingFocus = computed(
  () =>
    Boolean(props.focusCluster) &&
    !clusters.value.some(
      (cluster) => cluster.probeClusterId === props.focusCluster,
    ),
);

function toggle(clusterId: string): void {
  const next = new Set(expanded.value);
  if (next.has(clusterId)) next.delete(clusterId);
  else next.add(clusterId);
  expanded.value = next;
}

function typeLabel(type: StepCluster["type"]): string {
  return type === "prompt" ? "prompt" : type === "model" ? "模型" : "错误";
}

function sessionHref(probe: StepCluster["probes"][number]): string {
  const query = new URLSearchParams({
    case: probe.sourceBadCaseIds[0] ?? "",
    tab: "desc",
  });
  return `/sessions/${encodeURIComponent(probe.sessionId)}/errors?${query}`;
}

watch(
  () => [props.focusCluster, clusters.value] as const,
  async ([clusterId]) => {
    highlighted.value = null;
    if (!clusterId) return;
    await nextTick();
    highlighted.value = clusterId;
    const target = document.getElementById(`cluster-${clusterId}`);
    if (!target) return;
    target.scrollIntoView?.({ block: "center", behavior: "smooth" });
  },
  { immediate: true, flush: "post" },
);
</script>

<template>
  <article class="card panel">
    <h3 class="sec-title">
      第 2 步 · 问题聚类
      <span class="sub">
        M={{ clusters.length }} 类 · 不同类型的问题不聚为一簇 · 展开可查看来源问题
      </span>
    </h3>
    <p
      v-if="missingFocus"
      class="missing-focus"
      role="status"
    >
      目标簇已不存在。
    </p>
    <div
      v-for="cluster in clusters"
      :id="`cluster-${cluster.probeClusterId}`"
      :key="cluster.probeClusterId"
      class="cluster"
      :class="{
        open: expanded.has(cluster.probeClusterId),
        highlighted: highlighted === cluster.probeClusterId,
      }"
    >
      <button
        class="cluster-head"
        type="button"
        :aria-expanded="expanded.has(cluster.probeClusterId)"
        @click="toggle(cluster.probeClusterId)"
      >
        <span class="cid">{{ cluster.probeClusterId }}</span>
        <span class="ctitle">{{ cluster.title }}</span>
        <span
          class="type-chip"
          :class="`type-${cluster.type}`"
        >{{ typeLabel(cluster.type) }}</span>
        <span class="meta">probe ×{{ cluster.probeCount }}</span>
        <span
          v-if="cluster.confidence !== null"
          class="meta"
        >置信度 {{ (cluster.confidence * 100).toFixed(0) }}%</span>
        <span class="tail">
          <span class="caret">▶</span>
        </span>
      </button>
      <div
        v-if="expanded.has(cluster.probeClusterId)"
        class="cluster-body"
      >
        <p class="cb-label">
          来源问题（{{ cluster.probes.length }} 条 · 来自同一归因类型）
        </p>
        <div class="report-chips">
          <RouterLink
            v-for="probe in cluster.probes"
            :key="probe.probeId"
            class="report-chip"
            :to="sessionHref(probe)"
          >
            {{ probe.probeId }} · {{ probe.description }}
          </RouterLink>
        </div>
        <p
          v-if="cluster.probes.length === 0"
          class="empty-copy"
        >
          该簇暂无 probe 明细。
        </p>
      </div>
    </div>
    <p
      v-if="clusters.length === 0"
      class="waiting"
    >
      当前运行还没有生成问题簇。
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

.cluster {
  overflow: hidden;
  margin-bottom: 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-card);
}

.cluster.highlighted {
  border-color: var(--blue);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--blue) 16%, transparent);
}

.cluster-head {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 11px 14px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  flex-wrap: wrap;
  cursor: pointer;
}

.cluster-head:hover {
  background: var(--bg-panel);
}

.cid,
.meta {
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 11px;
}

.ctitle {
  color: var(--text);
  font-size: 13px;
  font-weight: 600;
}

.type-chip {
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 10.5px;
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

.tail {
  display: flex;
  margin-left: auto;
}

.caret {
  color: var(--text-faint);
  font-size: 11px;
  transition: transform 0.15s;
}

.cluster.open .caret {
  transform: rotate(90deg);
}

.cluster-body {
  padding: 14px 16px;
  border-top: 1px solid var(--border);
}

.cb-label {
  margin: 0 0 6px;
  color: var(--text-faint);
  font-size: 11px;
  font-weight: 600;
}

.report-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.report-chip {
  padding: 1px 7px;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: var(--bg-panel);
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 10.5px;
  text-decoration: none;
}

.empty-copy {
  color: var(--text-faint);
  font-size: 11.5px;
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

.missing-focus {
  margin: 0 0 10px;
  color: var(--orange);
  font-size: 11.5px;
}
</style>
