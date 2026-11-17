<script setup lang="ts">
import type {
  EvolutionRunCard,
  EvolutionStepAttribution,
  StepAttributionRow,
} from "@harness/contracts";
import { computed } from "vue";

const props = defineProps<{
  step: EvolutionStepAttribution;
  run: EvolutionRunCard;
}>();

const summary = computed(() => props.step.payload.summary);
const targetLabel = computed(
  () => `${props.run.target.name}@${props.run.target.version}`,
);

function categoryLabel(category: StepAttributionRow["category"]): string {
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
