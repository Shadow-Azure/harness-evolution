<script setup lang="ts">
import type {
  EvolutionStepPotential,
  StepPotentialRow,
} from "@harness/contracts";
import { computed } from "vue";

import { badCaseDeepLink, shortBadCaseId } from "../../../utils/badCaseId";
import { formatLocalDateTime } from "../runDetail";

const props = defineProps<{
  wid: string;
  step: EvolutionStepPotential;
}>();

const emit = defineEmits<{
  "page-change": [page: number];
}>();

const payload = computed(() => props.step.payload);
const summary = computed(() => payload.value.summary);
const anchorSourceLabels: Record<StepPotentialRow["anchorSource"], string> = {
  event: "事件锚点",
  node: "节点锚点",
  post_process: "后处理上报",
  unknown: "锚点未知",
};
const pageCount = computed(() =>
  Math.max(1, Math.ceil(payload.value.total / payload.value.pageSize)),
);

const reasonItems = computed(() => {
  const counts = summary.value.byReason;
  return [
    { key: "selfReport", label: "self 上报", value: counts.selfReport },
    { key: "afterObject", label: "触发点在对象后", value: counts.afterObject },
    { key: "both", label: "两者命中", value: counts.both },
    { key: "policyExcluded", label: "策略排除", value: counts.policyExcluded },
    { key: "orderUnknown", label: "顺序未知", value: counts.orderUnknown },
  ];
});

const reasonLabels: Record<StepPotentialRow["hitReason"], string> = {
  self_report: "self 上报",
  after_object: "触发点在对象后",
  both: "两者命中",
  policy_excluded: "策略排除",
  order_unknown: "顺序未知",
};

function changePage(delta: number): void {
  const next = payload.value.page + delta;
  if (next < 1 || next > pageCount.value) return;
  emit("page-change", next);
}
</script>

<template>
  <article class="card panel">
    <h3 class="sec-title">
      第 3 步 · 潜在 bad case
      <span class="sub">默认策略：对象自身 self 上报 或 触发点在对象触发点之后</span>
    </h3>
    <div class="wz-stats">
      <span class="st"><b>{{ summary.badCases }}</b><span>时间段内 bad case</span></span>
      <span class="st accent"><b>{{ summary.potential }}</b><span>潜在 bad case</span></span>
      <span
        v-for="reason in reasonItems"
        :key="reason.key"
        class="st reason"
      >
        <b>{{ reason.value }}</b><span>{{ reason.label }}</span>
      </span>
    </div>
    <div
      v-if="payload.rows.length"
      class="table-scroll"
    >
      <table class="rep">
        <thead>
          <tr>
            <th>bad case</th>
            <th>上报来源</th>
            <th>类型</th>
            <th>触发点</th>
            <th>来源 Session</th>
            <th>命中原因</th>
            <th>锚点来源</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in payload.rows"
            :key="row.badCaseId"
          >
            <td class="id">
              <a
                :href="badCaseDeepLink(wid, row.sessionId, row.badCaseId, 'desc')"
                :title="row.badCaseId"
                :aria-label="`来源问题 ${shortBadCaseId(row.badCaseId)}，在新窗口打开问题描述`"
                rel="noopener noreferrer"
                target="_blank"
              >
                {{ shortBadCaseId(row.badCaseId) }}
              </a>
            </td>
            <td>
              <span class="chip object">{{ row.objectName }}</span>
            </td>
            <td>
              <span class="type-chip">{{ row.badCaseType }}</span>
            </td>
            <td class="mono">
              {{ row.triggerAt ? formatLocalDateTime(row.triggerAt) : "—" }}
            </td>
            <td
              class="mono session-cell"
              :title="row.sessionId"
            >
              {{ row.sessionId }}
            </td>
            <td>
              <span class="reason-chip">{{ reasonLabels[row.hitReason] }}</span>
              <span
                v-if="row.orderState === 'unknown'"
                class="order-note"
              >触发点顺序待轨迹时间戳重放</span>
            </td>
            <td>
              <span
                class="anchor-source"
                :class="{ post: row.anchorSource === 'post_process' }"
                :data-anchor-source="row.anchorSource"
              >{{ anchorSourceLabels[row.anchorSource] }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p
      v-else
      class="waiting"
    >
      当前策略没有命中潜在 bad case；可返回调整时间段或策略
    </p>
    <div
      v-if="payload.total > 0"
      class="pager"
    >
      <button
        class="btn"
        type="button"
        :disabled="payload.page <= 1"
        @click="changePage(-1)"
      >
        ← 上一页
      </button>
      <span class="pager-info">
        第 <b>{{ payload.page }}</b> / {{ pageCount }} 页 · 共
        <b>{{ payload.total }}</b> 个潜在 bad case
      </span>
      <button
        class="btn"
        type="button"
        :disabled="payload.page >= pageCount"
        @click="changePage(1)"
      >
        下一页 →
      </button>
    </div>
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
  gap: 16px;
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

.st.reason b {
  font-size: 12.5px;
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

td.id a {
  color: var(--blue);
  font-family: var(--mono);
  text-decoration: none;
}

td.id a:hover {
  text-decoration: underline;
}

.chip,
.type-chip,
.reason-chip {
  display: inline-block;
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 10.5px;
  white-space: nowrap;
}

.chip.object {
  border-color: color-mix(in srgb, var(--cyan) 32%, transparent);
  color: var(--cyan);
}

.reason-chip {
  border-color: color-mix(in srgb, var(--green) 32%, transparent);
  background: color-mix(in srgb, var(--green) 7%, transparent);
  color: var(--green);
}

.order-note {
  display: block;
  margin-top: 3px;
  color: var(--orange);
  font-size: 10.5px;
}

.anchor-source {
  display: inline-block;
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-faint);
  font-size: 10.5px;
  white-space: nowrap;
}

.anchor-source.post {
  border-color: color-mix(in srgb, var(--orange) 38%, var(--border));
  background: color-mix(in srgb, var(--orange) 7%, transparent);
  color: var(--orange);
}

.mono {
  font-family: var(--mono);
}

.session-cell {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pager {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 11px;
  flex-wrap: wrap;
}

.btn {
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-dim);
  font: inherit;
  font-size: 11.5px;
  cursor: pointer;
}

.btn:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.pager-info {
  color: var(--text-faint);
  font-size: 11.5px;
}

.pager-info b {
  color: var(--text);
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
