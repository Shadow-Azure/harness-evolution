<script setup lang="ts">
import type { EvolutionStepClusters, StepCluster } from "@harness/contracts";
import { computed, nextTick, ref, watch } from "vue";

import StepCaseTable from "./StepCaseTable.vue";

const props = defineProps<{
  wid: string;
  step: EvolutionStepClusters;
  focusCluster?: string;
  title?: string;
  subtitle?: string;
  caseSessions?: Record<string, string>;
}>();
const emit = defineEmits<{
  "missing-focus": [];
}>();

const clusters = computed(() => props.step.payload.clusters);
const expanded = ref<Set<string>>(
  new Set(clusters.value[0] ? [clusters.value[0].clusterId] : []),
);
const highlighted = ref<string | null>(null);
const missingNotice = ref(false);

const totalCases = computed(
  () =>
    new Set(
      clusters.value.flatMap((cluster) =>
        cluster.cases.map((item) => item.badCaseId),
      ),
    ).size,
);

const averageConfidence = computed(() => {
  const values = clusters.value
    .map((cluster) => cluster.confidence)
    .filter((value): value is number => value !== null);
  if (values.length === 0) return null;
  return values.reduce((total, value) => total + value, 0) / values.length;
});

const maxSeverity = computed(() => {
  const values = clusters.value
    .map((cluster) => cluster.severity)
    .filter((value): value is number => value !== null);
  return values.length === 0 ? null : Math.max(...values);
});

const degradedLabel = computed(() => (props.step.payload.degraded ?? []).join("、"));

const failurePolicyLabel = computed(() =>
  props.step.payload.failurePolicy === "strict" ? "严格（失败即中止）" : "允许降级",
);

function toggle(clusterId: string): void {
  const next = new Set(expanded.value);
  if (next.has(clusterId)) next.delete(clusterId);
  else next.add(clusterId);
  expanded.value = next;
}

function categoryLabel(category: StepCluster["category"]): string {
  return category === "prompt" ? "prompt" : category === "model" ? "模型" : "错误";
}

watch(
  () => [props.focusCluster, clusters.value] as const,
  async ([clusterId]) => {
    highlighted.value = null;
    if (!clusterId) return;
    const exists = clusters.value.some(
      (cluster) => cluster.clusterId === clusterId,
    );
    if (!exists) {
      missingNotice.value = true;
      emit("missing-focus");
      return;
    }
    missingNotice.value = false;
    expanded.value = new Set([...expanded.value, clusterId]);
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
      {{ title ?? "第 5 步 · 聚类与严重度" }}
      <span class="sub">{{ subtitle ?? "按问题类型聚类，按严重程度降序；每簇含标题与聚类问题描述" }}</span>
    </h3>
    <div class="wz-stats">
      <span class="st"><b>{{ clusters.length }}</b><span>聚类问题</span></span>
      <span class="st"><b>{{ totalCases }}</b><span>来源 bad case</span></span>
      <span class="st">
        <b>{{ averageConfidence === null ? "—" : `${(averageConfidence * 100).toFixed(0)}%` }}</b>
        <span>平均置信度</span>
      </span>
      <span class="st accent"><b>{{ maxSeverity === null ? "—" : maxSeverity.toFixed(1) }}</b><span>最高严重度</span></span>
    </div>
    <p
      v-if="step.payload.algorithm || step.payload.failurePolicy"
      class="ai-audit"
    >
      <span v-if="step.payload.algorithm">聚类算法 <code>{{ step.payload.algorithm }}</code></span>
      <span v-if="step.payload.failurePolicy">失败策略 <code>{{ failurePolicyLabel }}</code></span>
    </p>
    <p
      v-if="(step.payload.degraded?.length ?? 0) > 0"
      class="ai-warning"
      role="status"
    >
      <b>AI 聚类使用了确定性回退。</b>
      <span>回退任务：{{ degradedLabel }}。该步骤的置信度与严重度不代表真实模型参与。</span>
    </p>
    <p
      v-if="step.payload.failure"
      class="ai-failure"
      role="alert"
    >
      <b>真实 AI 聚类失败，运行已显式中止。</b>
      <span>{{ step.payload.failure }}</span>
    </p>
    <p
      v-if="missingNotice"
      class="missing-focus"
      role="status"
    >
      目标簇已不存在。
    </p>
    <div
      v-for="(cluster, index) in clusters"
      :id="`cluster-${cluster.clusterId}`"
      :key="cluster.clusterId"
      class="cluster"
      :class="{
        open: expanded.has(cluster.clusterId),
        highlighted: highlighted === cluster.clusterId,
      }"
    >
      <button
        class="cluster-head"
        type="button"
        :aria-expanded="expanded.has(cluster.clusterId)"
        @click="toggle(cluster.clusterId)"
      >
        <span class="rank">#{{ cluster.rank ?? index + 1 }}</span>
        <span class="cid">{{ cluster.clusterId }}</span>
        <span class="ctitle">{{ cluster.title }}</span>
        <span
          class="type-chip"
          :class="`type-${cluster.category}`"
        >{{ categoryLabel(cluster.category) }}</span>
        <span class="meta">bad case ×{{ cluster.caseCount }}</span>
        <span
          v-if="cluster.confidence !== null"
          class="meta"
        >置信度 {{ (cluster.confidence * 100).toFixed(0) }}%</span>
        <span
          v-if="cluster.severity !== null"
          class="meta"
        >严重程度 {{ cluster.severity.toFixed(1) }}</span>
        <span class="tail">
          <span class="caret">▶</span>
        </span>
      </button>
      <div
        v-if="expanded.has(cluster.clusterId)"
        class="cluster-body"
      >
        <section class="cb-sec">
          <p class="cb-label">
            聚类问题描述
          </p>
          <p class="cluster-desc">
            {{ cluster.description || "暂无聚类问题描述" }}
          </p>
        </section>
        <section class="cb-sec">
          <p class="cb-label">
            来源 bad case（{{ cluster.cases.length }} 个 · 由归因结论聚类而来）
          </p>
          <StepCaseTable
            :cases="cluster.cases"
            :wid="wid"
            :case-sessions="caseSessions"
          />
        </section>
      </div>
    </div>
    <p
      v-if="clusters.length === 0 && !step.payload.failure"
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

.cluster {
  overflow: hidden;
  margin-bottom: 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-card);
}

.cluster:last-of-type {
  margin-bottom: 0;
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

.rank {
  padding: 1px 7px;
  border-radius: 6px;
  background: var(--orange);
  color: white;
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 700;
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

.cb-sec {
  margin-bottom: 14px;
}

.cb-sec:last-child {
  margin-bottom: 0;
}

.cb-label {
  margin: 0 0 6px;
  color: var(--text-faint);
  font-size: 11px;
  font-weight: 600;
}

.cluster-desc {
  margin: 0;
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1.6;
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

.ai-audit {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  margin: -4px 0 10px;
  color: var(--text-faint);
  font-size: 11px;
}

.ai-audit code {
  font-family: var(--mono);
}

.ai-warning,
.ai-failure {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin: 0 0 10px;
  padding: 9px 12px;
  border-radius: 8px;
  font-size: 11.5px;
  line-height: 1.5;
}

.ai-warning {
  border: 1px solid color-mix(in srgb, var(--orange) 45%, var(--border));
  background: color-mix(in srgb, var(--orange) 9%, transparent);
  color: var(--orange);
}

.ai-failure {
  border: 1px solid color-mix(in srgb, var(--red) 45%, var(--border));
  background: color-mix(in srgb, var(--red) 9%, transparent);
  color: var(--red);
}
</style>
