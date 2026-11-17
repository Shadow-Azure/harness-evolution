<script setup lang="ts">
import type { EvolutionStepRange } from "@harness/contracts";
import { computed } from "vue";

const props = defineProps<{
  step: EvolutionStepRange;
}>();

const condition = computed(() => props.step.payload.condition);
const stats = computed(() => props.step.payload.stats);

const targetLabel = computed(
  () =>
    `${condition.value.targetType}:${condition.value.targetName}@${condition.value.targetVersion}`,
);

const windowLabel = computed(() => {
  const { from, to } = condition.value;
  if (from && to) return `${from} ~ ${to}`;
  if (from) return `${from} ~ 至今`;
  if (to) return `起始未知 ~ ${to}`;
  return "时间窗未设置";
});

const policyPreset = computed(() => {
  const preset = condition.value.policy.preset;
  return typeof preset === "string" ? preset : "";
});

const isDefaultPolicy = computed(
  () =>
    policyPreset.value === "default" ||
    Object.keys(condition.value.policy).length === 0,
);

const policyLabel = computed(() =>
  isDefaultPolicy.value ? "默认策略" : "自定义策略",
);

const policyDetail = computed(() =>
  isDefaultPolicy.value
    ? "对象自身 self 上报 或 触发点在对象之后"
    : JSON.stringify(condition.value.policy),
);

const cacheLabel = computed(() =>
  condition.value.cacheEnabled ? "复用最近一次成功归因" : "全部重新归因",
);
</script>

<template>
  <article class="card panel">
    <h3 class="sec-title">
      第 1 步 · 选择范围
      <span class="sub">进化对象 + 版本 + bad case 时间段</span>
    </h3>
    <div class="wz-stats">
      <span class="st"><b>{{ stats.sessions }}</b><span>时间段内 Session</span></span>
      <span class="st"><b>{{ stats.badCases }}</b><span>时间段内 bad case</span></span>
      <span class="st accent"><b>{{ stats.potential }}</b><span>潜在 bad case</span></span>
    </div>
    <table class="rep">
      <tbody>
        <tr>
          <th>进化对象</th>
          <td><span class="chip kind">{{ targetLabel }}</span></td>
          <th>工作空间</th>
          <td
            class="mono"
            :title="condition.workspaceId"
          >
            {{ condition.workspaceId }}
          </td>
        </tr>
        <tr>
          <th>bad case 时间段</th>
          <td class="mono">
            {{ windowLabel }}
          </td>
          <th>缓存归因</th>
          <td>{{ cacheLabel }}</td>
        </tr>
        <tr>
          <th>潜在策略</th>
          <td colspan="3">
            <span
              class="policy-badge"
              :class="{ default: isDefaultPolicy }"
            >{{ policyLabel }}</span>
            <span class="policy-detail">{{ policyDetail }}</span>
          </td>
        </tr>
      </tbody>
    </table>
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
  vertical-align: top;
}

table.rep th {
  width: 150px;
  color: var(--text-faint);
  font-size: 11px;
  font-weight: 600;
}

table.rep tr:last-child th,
table.rep tr:last-child td {
  border-bottom: 0;
}

.chip {
  display: inline-block;
  padding: 1px 9px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 10.5px;
  white-space: nowrap;
}

.chip.kind {
  border-color: color-mix(in srgb, var(--purple) 35%, transparent);
  background: color-mix(in srgb, var(--purple) 9%, transparent);
  color: var(--purple);
  font-family: var(--mono);
}

.policy-badge {
  display: inline-block;
  margin-right: 8px;
  padding: 1px 9px;
  border: 1px solid color-mix(in srgb, var(--orange) 35%, transparent);
  border-radius: 999px;
  color: var(--orange);
  font-size: 10.5px;
  white-space: nowrap;
}

.policy-badge.default {
  border-color: color-mix(in srgb, var(--green) 32%, transparent);
  color: var(--green);
}

.policy-detail {
  color: var(--text-dim);
  font-size: 11.5px;
  word-break: break-all;
}

.mono {
  font-family: var(--mono);
}
</style>
