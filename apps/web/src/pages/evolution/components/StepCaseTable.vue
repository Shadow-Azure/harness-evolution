<script setup lang="ts">
import type { StepClusterCase } from "@harness/contracts";

import { formatLocalDateTime } from "../runDetail";
import { shortBadCaseId } from "../../../utils/badCaseId";

defineProps<{
  cases: StepClusterCase[];
}>();

function typeLabel(type: string): string {
  if (type === "prompt") return "prompt";
  if (type === "model") return "模型";
  if (type === "error") return "错误";
  return type;
}
</script>

<template>
  <div
    v-if="cases.length"
    class="table-scroll"
  >
    <table class="case-rep">
      <thead>
        <tr>
          <th>bad case</th>
          <th>标题</th>
          <th>object_name</th>
          <th>类型</th>
          <th>触发点</th>
          <th>上报时间</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="item in cases"
          :key="item.badCaseId"
        >
          <td
            class="id mono"
            :title="item.badCaseId"
          >
            {{ shortBadCaseId(item.badCaseId) }}
          </td>
          <td>{{ item.title }}</td>
          <td class="mono">
            {{ item.objectName }}
          </td>
          <td>
            <span
              class="type-chip"
              :class="`type-${item.badCaseType}`"
            >{{ typeLabel(item.badCaseType) }}</span>
          </td>
          <td class="mono">
            {{ item.triggerAt ? formatLocalDateTime(item.triggerAt) : "—" }}
          </td>
          <td class="mono">
            {{ item.createdAt ? formatLocalDateTime(item.createdAt) : "—" }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <p
    v-else
    class="empty-copy"
  >
    无来源 bad case。
  </p>
</template>

<style scoped>
.table-scroll {
  overflow-x: auto;
}

.case-rep {
  width: 100%;
  border-collapse: collapse;
  font-size: 11.5px;
}

.case-rep th {
  padding: 6px 9px;
  border-bottom: 1px solid var(--border);
  color: var(--text-faint);
  font-size: 10.5px;
  font-weight: 600;
  text-align: left;
  white-space: nowrap;
}

.case-rep td {
  padding: 7px 9px;
  border-bottom: 1px solid var(--border);
  color: var(--text-dim);
  vertical-align: top;
}

.case-rep tr:last-child td {
  border-bottom: 0;
}

.mono {
  font-family: var(--mono);
}

.id {
  color: var(--blue);
  white-space: nowrap;
}

.type-chip {
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

.empty-copy {
  margin: 0;
  color: var(--text-faint);
  font-size: 11.5px;
}
</style>
