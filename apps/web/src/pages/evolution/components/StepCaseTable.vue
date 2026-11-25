<script setup lang="ts">
import type { StepClusterCase } from "@harness/contracts";

import { badCaseDeepLink, shortBadCaseId } from "../../../utils/badCaseId";
import { formatLocalDateTime } from "../runDetail";

const props = defineProps<{
  cases: StepClusterCase[];
  wid?: string;
  caseSessions?: Record<string, string>;
}>();

function typeLabel(type: string): string {
  if (type === "prompt") return "prompt";
  if (type === "model") return "模型";
  if (type === "error") return "错误";
  return type;
}

/**
 * Build the error-detail deep link for a source bad case.
 * @param badCaseId Source bad case identifier.
 * @returns Workspace error-detail path, or null when the owning Session is unknown.
 */
function caseLink(badCaseId: string): string | null {
  const sessionId = props.caseSessions?.[badCaseId];
  if (!props.wid || !sessionId) return null;
  return badCaseDeepLink(props.wid, sessionId, badCaseId, "attr");
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
            <a
              v-if="caseLink(item.badCaseId)"
              :href="caseLink(item.badCaseId)!"
              :title="item.badCaseId"
              :aria-label="`来源问题 ${item.badCaseId}，在新窗口打开问题描述`"
              target="_blank"
              rel="noopener noreferrer"
            >{{ shortBadCaseId(item.badCaseId) }}</a>
            <template v-else>
              {{ shortBadCaseId(item.badCaseId) }}
            </template>
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
  color: var(--text-dim);
  white-space: nowrap;
}

.id a {
  border-bottom: 1px dashed color-mix(in srgb, var(--blue) 45%, transparent);
  color: var(--blue);
  cursor: pointer;
  text-decoration: none;
}

.id a:hover {
  border-bottom-style: solid;
}

.id a:focus-visible {
  border-radius: 2px;
  outline: 2px solid var(--blue);
  outline-offset: 1px;
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
