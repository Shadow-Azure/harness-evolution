<script setup lang="ts">
import type { ProbePreviewItem } from "@harness/contracts";

import { badCaseDeepLink, shortBadCaseId } from "../../../utils/badCaseId";

defineProps<{
  rows: ProbePreviewItem[];
  showCluster?: boolean;
  clusterOfProbe?: Record<string, string | null>;
}>();

function typeLabel(type: ProbePreviewItem["attributeType"]): string {
  if (type === "prompt") return "prompt";
  if (type === "model") return "模型";
  return "错误";
}
</script>

<template>
  <div
    v-if="rows.length"
    class="table-scroll"
  >
    <table class="probe-rep">
      <thead>
        <tr>
          <th>报告 ID</th>
          <th>来源问题 ID</th>
          <th>问题现象</th>
          <th v-if="!showCluster">
            来源 session
          </th>
          <th>模型</th>
          <th>归因类型</th>
          <th v-if="showCluster">
            归属簇
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="probe in rows"
          :key="probe.probeId"
        >
          <td class="id">
            <a
              v-if="probe.sourceBadCaseIds[0]"
              :href="
                badCaseDeepLink(
                  probe.sessionId,
                  probe.sourceBadCaseIds[0],
                  'attr',
                )
              "
              :aria-label="`归因报告 ${shortBadCaseId(probe.probeId)}，在新窗口打开归因分析`"
              rel="noopener noreferrer"
              target="_blank"
              :title="probe.probeId"
            >
              {{ shortBadCaseId(probe.probeId) }}
            </a>
            <span v-else>—</span>
          </td>
          <td class="id">
            <a
              v-if="probe.sourceBadCaseIds[0]"
              :href="
                badCaseDeepLink(
                  probe.sessionId,
                  probe.sourceBadCaseIds[0],
                  'desc',
                )
              "
              :aria-label="`来源问题 ${shortBadCaseId(probe.sourceBadCaseIds[0])}，在新窗口打开问题描述`"
              rel="noopener noreferrer"
              target="_blank"
              :title="probe.sourceBadCaseIds[0]"
            >
              {{ shortBadCaseId(probe.sourceBadCaseIds[0]) }}
            </a>
            <span v-else>—</span>
          </td>
          <td>{{ probe.description }}</td>
          <td
            v-if="!showCluster"
            class="mono source-cell"
            :title="probe.sessionId"
          >
            {{ probe.sessionTitle ?? probe.sessionId }}
          </td>
          <td class="mono model-cell">
            {{ probe.model ?? "—" }}
          </td>
          <td>
            <span
              class="type-chip"
              :class="`type-${probe.attributeType}`"
            >{{ typeLabel(probe.attributeType) }}</span>
          </td>
          <td
            v-if="showCluster"
            class="mono"
          >
            {{ clusterOfProbe?.[probe.probeId] ?? "—" }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <p
    v-else
    class="empty-copy"
  >
    无关联问题报告。
  </p>
</template>

<style scoped>
.table-scroll {
  overflow-x: auto;
}

.probe-rep {
  width: 100%;
  border-collapse: collapse;
  font-size: 11.5px;
}

.probe-rep th {
  padding: 6px 9px;
  border-bottom: 1px solid var(--border);
  color: var(--text-faint);
  font-size: 10.5px;
  font-weight: 600;
  text-align: left;
  white-space: nowrap;
}

.probe-rep td {
  padding: 7px 9px;
  border-bottom: 1px solid var(--border);
  color: var(--text-dim);
  vertical-align: top;
}

.probe-rep tr:last-child td {
  border-bottom: 0;
}

.probe-rep a {
  color: var(--blue);
  font-family: var(--mono);
  text-decoration: none;
}

.probe-rep a:hover {
  text-decoration: underline;
}

.mono {
  font-family: var(--mono);
}

.source-cell {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-cell {
  color: var(--cyan);
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
