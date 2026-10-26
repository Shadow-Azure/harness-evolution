<script setup lang="ts">
import type { BadCase } from "@harness/contracts";
import { computed } from "vue";

import { badCaseFactEntries, badCaseState } from "../../../components/bad-cases/badCaseDisplay";
import {
  badCaseDeepLink,
  shortBadCaseId,
} from "../../../utils/badCaseId";

const props = defineProps<{
  problem: BadCase;
  index: number | null;
}>();

const facts = computed(() => badCaseFactEntries(props.problem.metaData));
const reporter = computed(() =>
  props.problem.badCaseAgent.agentId
    ? `${props.problem.badCaseType} · ${props.problem.badCaseAgent.agentId}`
    : `${props.problem.badCaseType} · 主 Agent`,
);
const reportId = computed(() =>
  props.problem.analysis.status === "analyzed_issue"
    ? props.problem.analysis.probeId
    : null,
);
</script>

<template>
  <section
    class="description"
    aria-labelledby="problem-description-title"
  >
    <header class="problem-heading">
      <span
        v-if="index !== null"
        class="problem-number"
      >#{{ index }}</span>
      <a
        class="problem-id"
        :href="badCaseDeepLink(
          problem.sessionId,
          problem.badCaseId,
          'desc',
        )"
        :aria-label="`问题 ${shortBadCaseId(problem.badCaseId)}，在新窗口打开问题描述`"
        rel="noopener noreferrer"
        target="_blank"
        :title="problem.badCaseId"
      >
        {{ shortBadCaseId(problem.badCaseId) }}
      </a>
      <span
        id="problem-description-title"
        class="problem-title"
      >{{ problem.reason }}</span>
      <a
        v-if="reportId"
        class="report-id"
        :href="badCaseDeepLink(
          problem.sessionId,
          problem.badCaseId,
          'attr',
        )"
        :aria-label="`归因报告 ${shortBadCaseId(reportId)}，在新窗口打开归因分析`"
        rel="noopener noreferrer"
        target="_blank"
        :title="reportId"
      >
        {{ shortBadCaseId(reportId) }}
      </a>
      <span
        class="state-chip"
        :class="badCaseState(problem.analysis.displayState).tone"
      >
        {{ badCaseState(problem.analysis.displayState).label }}
      </span>
      <span
        v-if="problem.degraded"
        class="degraded-chip"
      >
        数据降级
      </span>
    </header>
    <div v-if="facts.length">
      <div class="facts">
        <span
          v-for="fact in facts"
          :key="fact.key"
          class="fact-chip"
        >
          <span class="fact-key">{{ fact.key }}</span>
          <span class="fact-value">{{ fact.value }}</span>
        </span>
      </div>
    </div>
    <div class="association">
      关联：{{ reporter }} · {{ problem.objectType }} · {{ problem.objectName }}
      <span v-if="problem.objectVersion">@{{ problem.objectVersion }}</span>
      · 会话：{{ problem.sessionTitle }}
    </div>
    <p
      v-if="problem.degraded"
      class="diagnostic"
    >
      外部字段存在漂移，当前以安全占位展示。
      <span v-if="problem.diagnosticCode">({{ problem.diagnosticCode }})</span>
    </p>
  </section>
</template>

<style scoped>
.description {
  display: grid;
  gap: 9px;
  padding: 14px 18px 18px;
}

.problem-heading {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.problem-number,
.problem-id,
.report-id {
  flex-shrink: 0;
  font-family: var(--mono);
  font-weight: 700;
}

.problem-number {
  padding: 1px 8px;
  border: 1px solid var(--red);
  border-radius: 999px;
  background: color-mix(in srgb, var(--red) 8%, var(--bg-card));
  color: var(--red);
  font-size: 11px;
}

.problem-id {
  color: var(--blue);
  font-size: 10.5px;
  border-bottom: 1px dashed color-mix(in srgb, var(--blue) 45%, transparent);
  text-decoration: none;
}

.problem-id:hover {
  border-bottom-style: solid;
}

.report-id {
  color: var(--purple);
  font-size: 10.5px;
  border-bottom: 1px dashed color-mix(in srgb, var(--purple) 45%, transparent);
  text-decoration: none;
}

.report-id:hover {
  border-bottom-style: solid;
}

.problem-title {
  color: var(--text);
  font-size: 15px;
  font-weight: 650;
}

.state-chip {
  padding: 1px 8px;
  border: 1px solid currentColor;
  border-radius: 999px;
  font-size: 10px;
}

.state-chip.neutral {
  color: var(--text-faint);
}

.state-chip.green {
  color: var(--green);
}

.state-chip.purple {
  color: var(--purple);
}

.state-chip.orange {
  color: var(--orange);
}

.state-chip.red {
  color: var(--red);
}

.degraded-chip {
  padding: 1px 7px;
  border: 1px solid currentColor;
  border-radius: 999px;
  background: color-mix(in srgb, var(--orange) 8%, var(--bg-card));
  color: var(--orange);
  font-size: 10px;
}

.facts {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}

.fact-chip {
  display: inline-flex;
  align-items: flex-start;
  gap: 5px;
  max-width: 100%;
  padding: 1px 6px;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: var(--bg-inset);
  font-size: 10.5px;
  line-height: 1.5;
}

.fact-key {
  flex-shrink: 0;
  color: var(--text-faint);
}

.fact-value {
  min-width: 0;
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 10px;
  overflow-wrap: anywhere;
}

.diagnostic {
  margin: 0;
  color: var(--orange);
  font-size: 11.5px;
}

.association {
  color: var(--text-faint);
  font-size: 11px;
  line-height: 1.6;
}
</style>
