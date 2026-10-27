<script setup lang="ts">
import type {
  EvolutionStepInput,
  StepCondition,
  StepInputRow,
} from "@harness/contracts";
import { computed } from "vue";

const props = defineProps<{
  step: EvolutionStepInput;
  condition: StepCondition;
}>();

const uniqueRows = computed(() => {
  const seen = new Set<string>();
  return props.step.payload.rows.filter((row) => {
    if (seen.has(row.probeId)) return false;
    seen.add(row.probeId);
    return true;
  });
});

const duplicateCount = computed(
  () => props.step.payload.rows.length - uniqueRows.value.length,
);

const distribution = computed(() => {
  const values = props.step.payload.hits.byAttributeType;
  return [
    { key: "error", label: "错误", value: values.error, color: "var(--red)" },
    { key: "prompt", label: "prompt", value: values.prompt, color: "var(--orange)" },
    { key: "model", label: "模型", value: values.model, color: "var(--purple)" },
    { key: "nonIssue", label: "非问题", value: values.nonIssue, color: "var(--text-faint)" },
  ];
});

const analyzed = computed(() =>
  distribution.value.reduce((total, item) => total + item.value, 0),
);

function typeLabel(type: StepInputRow["attributeType"]): string {
  if (type === "prompt") return "prompt";
  if (type === "model") return "模型";
  return "错误";
}

function typeClass(type: StepInputRow["attributeType"]): string {
  return `type-${type}`;
}

function reportHref(row: StepInputRow): string {
  const query = new URLSearchParams({
    case: row.sourceBadCaseIds[0] ?? "",
    tab: "attr",
  });
  return `/sessions/${encodeURIComponent(row.sessionId)}/errors?${query}`;
}

function issueHref(row: StepInputRow): string {
  const query = new URLSearchParams({
    case: row.sourceBadCaseIds[0] ?? "",
    tab: "desc",
  });
  return `/sessions/${encodeURIComponent(row.sessionId)}/errors?${query}`;
}
</script>

<template>
  <article class="card panel">
    <h3 class="sec-title">
      第 1 步 · 筛选输入
      <span class="sub">筛选条件命中的问题报告即本次进化的输入</span>
    </h3>
    <div class="hidden">
      {{ condition.targetType }}:{{ condition.targetName }}@{{ condition.targetVersion }}
    </div>
    <div class="f-inline">
      <span class="chip kind">
        {{ condition.targetType }}:{{ condition.targetName }}@{{ condition.targetVersion }}
      </span>
      <span class="chip mono">
        {{ condition.from ?? "—" }} ~ {{ condition.to ?? "—" }}
      </span>
      <span
        v-for="model in condition.models"
        :key="model"
        class="chip model"
      >
        {{ model }}
      </span>
    </div>
    <p class="summary">
      命中 session <b class="mono">{{ step.payload.hits.sessions }}</b> 个 · 问题报告
      <b class="mono">{{ step.payload.hits.probes }}</b> 份；已分析
      <b class="mono">{{ analyzed }}</b> 份（其中非问题
      <b class="mono">{{ step.payload.hits.byAttributeType.nonIssue }}</b> 份），最终
      <b class="mono blue">{{ step.payload.hits.usedProbes }}</b> 份「是问题」报告进入聚类。
    </p>
    <p
      v-if="duplicateCount"
      class="duplicate-note"
    >
      检测到 {{ duplicateCount }} 条重复 probe 输入，已按 probe ID 合并展示。
    </p>
    <div
      v-if="uniqueRows.length"
      class="table-scroll"
    >
      <table class="rep">
        <thead>
          <tr>
            <th>报告 ID</th>
            <th>来源问题 ID</th>
            <th>问题现象</th>
            <th>模型</th>
            <th>归因类型</th>
            <th>归属簇</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in uniqueRows"
            :key="row.probeId"
          >
            <td class="id">
              <RouterLink :to="reportHref(row)">
                {{ row.probeId }}
              </RouterLink>
            </td>
            <td class="id">
              <RouterLink :to="issueHref(row)">
                {{ row.sourceBadCaseIds[0] ?? "—" }}
              </RouterLink>
            </td>
            <td>{{ row.description }}</td>
            <td class="mono model-cell">
              {{ row.model ?? "—" }}
            </td>
            <td>
              <span
                class="type-chip"
                :class="typeClass(row.attributeType)"
              >{{ typeLabel(row.attributeType) }}</span>
            </td>
            <td class="mono">
              {{ row.clusterId ?? "—" }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p
      v-else
      class="waiting"
    >
      当前条件下没有已分析的问题 probe。
    </p>
  </article>
</template>

<style scoped>
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
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

.hidden {
  display: none;
}

.f-inline {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.chip,
.type-chip {
  display: inline-block;
  padding: 1px 9px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 10.5px;
  white-space: nowrap;
}

.chip.kind {
  border-color: color-mix(in srgb, var(--purple) 35%, transparent);
  background: color-mix(in srgb, var(--purple) 9%, transparent);
  color: var(--purple);
  font-family: var(--mono);
}

.chip.model {
  border-color: color-mix(in srgb, var(--cyan) 35%, transparent);
  background: color-mix(in srgb, var(--cyan) 9%, transparent);
  color: var(--cyan);
  font-family: var(--mono);
}

.summary {
  margin: 0 0 10px;
  color: var(--text-dim);
  font-size: 12.5px;
}

.duplicate-note {
  margin: 0 0 10px;
  color: var(--orange);
  font-size: 11.5px;
}

.blue {
  color: var(--blue);
}

.mono {
  font-family: var(--mono);
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
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  text-align: left;
}

table.rep th {
  color: var(--text-faint);
  font-size: 11px;
  font-weight: 600;
}

table.rep td.id {
  color: var(--blue);
  font-family: var(--mono);
}

table.rep td.id a {
  color: inherit;
  text-decoration: none;
}

.model-cell {
  color: var(--cyan);
}

.type-error {
  border-color: color-mix(in srgb, var(--red) 35%, transparent);
  background: color-mix(in srgb, var(--red) 8%, transparent);
  color: var(--red);
}

.type-prompt {
  border-color: color-mix(in srgb, var(--orange) 35%, transparent);
  background: color-mix(in srgb, var(--orange) 8%, transparent);
  color: var(--orange);
}

.type-model {
  border-color: color-mix(in srgb, var(--purple) 35%, transparent);
  background: color-mix(in srgb, var(--purple) 8%, transparent);
  color: var(--purple);
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
