<script setup lang="ts">
import type { EvolutionStepSessions } from "@harness/contracts";
import { computed } from "vue";

import { formatLocalDateTime } from "../runDetail";

const props = defineProps<{
  step: EvolutionStepSessions;
}>();

const emit = defineEmits<{
  "page-change": [page: number];
}>();

const payload = computed(() => props.step.payload);
const summary = computed(() => payload.value.summary);
const pageCount = computed(() =>
  Math.max(1, Math.ceil(payload.value.total / payload.value.pageSize)),
);

function changePage(delta: number): void {
  const next = payload.value.page + delta;
  if (next < 1 || next > pageCount.value) return;
  emit("page-change", next);
}
</script>

<template>
  <article class="card panel">
    <h3 class="sec-title">
      第 2 步 · Session 关联
      <span class="sub">只展示对象版本出现过的 Session；未出现的 Session 已跳过</span>
    </h3>
    <div class="wz-stats">
      <span class="st"><b>{{ summary.reported }}</b><span>上报过 bad case</span></span>
      <span class="st accent"><b>{{ summary.associated }}</b><span>关联</span></span>
      <span class="st"><b>{{ summary.skipped }}</b><span>跳过</span></span>
      <span class="st"><b>{{ summary.versionUnresolved }}</b><span>版本未知</span></span>
      <span class="st"><b>{{ summary.pending }}</b><span>待轨迹同步</span></span>
    </div>
    <div
      v-if="payload.rows.length"
      class="table-scroll"
    >
      <table class="rep">
        <thead>
          <tr>
            <th>Session</th>
            <th>对象触发点</th>
            <th>bad case</th>
            <th>潜在 bad case</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in payload.rows"
            :key="row.sessionId"
          >
            <td>
              <b>{{ row.title ?? "未命名 Session" }}</b>
              <span
                class="cell-sub mono"
                :title="row.sessionId"
              >{{ row.sessionId }}</span>
            </td>
            <td class="mono">
              {{ row.objectTriggerAt ? formatLocalDateTime(row.objectTriggerAt) : "—" }}
            </td>
            <td class="mono">
              {{ row.badCaseCount }}
            </td>
            <td class="mono">
              {{ row.potentialCount }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p
      v-else
      class="waiting"
    >
      没有对象版本出现过的 Session；可回第 1 步调整时间段或对象版本
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
        <b>{{ payload.total }}</b> 个关联 Session
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
}

table.rep tr:last-child td {
  border-bottom: 0;
}

.cell-sub {
  display: block;
  max-width: 260px;
  overflow: hidden;
  color: var(--text-faint);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mono {
  font-family: var(--mono);
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
