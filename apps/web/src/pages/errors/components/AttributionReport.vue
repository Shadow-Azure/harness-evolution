<script setup lang="ts">
import type {
  BadCaseAnalysis,
  ProbeReport,
} from "@harness/contracts";
import { computed } from "vue";

import ErrorState from "../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import {
  badCaseDeepLink,
  shortBadCaseId,
} from "../../../utils/badCaseId";
import { renderMarkdown } from "../../../utils/markdown";

const props = defineProps<{
  analysis: BadCaseAnalysis | null;
  analysisLoading: boolean;
  analysisError: Error | null;
  probe: ProbeReport | null;
  probeLoading: boolean;
  probeError: Error | null;
  sessionId: string;
  fallbackObject: string;
}>();

const emit = defineEmits<{
  retry: [];
  probeRetry: [];
}>();

const issueTone = computed(() => {
  const type = props.probe?.attributeType;
  return type === "model" ? "model" : type === "prompt" ? "prompt" : "error";
});

const issueLabel = computed(() => {
  const type = props.probe?.attributeType;
  return type === "model"
    ? "是问题 · 模型问题"
    : type === "prompt"
      ? "是问题 · prompt 缺失提示词"
      : "是问题 · 错误";
});

const issueCategory = computed(() => {
  const type = props.probe?.attributeType;
  return type === "model"
    ? "模型问题"
    : type === "prompt"
      ? "prompt 缺失提示词"
      : "错误";
});

const rootObject = computed(() => {
  if (!props.probe) return props.fallbackObject;
  return props.probe.objectVersion
    ? `${props.probe.probeObject} @ ${props.probe.objectVersion}`
    : props.probe.probeObject;
});

const analysisHtml = computed(() =>
  props.probe ? renderMarkdown(props.probe.probeAnalysis) : "",
);
</script>

<template>
  <LoadingSkeleton
    v-if="analysisLoading || probeLoading"
    label="正在读取归因分析"
    :rows="3"
  />
  <ErrorState
    v-else-if="analysisError"
    code="BAD_CASE_ANALYSIS_UNAVAILABLE"
    message="归因状态读取失败，请重试。"
    @retry="emit('retry')"
  />
  <ErrorState
    v-else-if="probeError"
    code="PROBE_UNAVAILABLE"
    message="归因报告读取失败，请重试。"
    @retry="emit('probeRetry')"
  />
  <section
    v-else-if="analysis"
    class="attribution"
    aria-labelledby="attribution-title"
  >
    <h2
      id="attribution-title"
      class="sr-only"
    >
      归因分析
    </h2>
    <div
      v-if="analysis.status === 'unanalyzed'"
      class="conclusion unanalyzed"
    >
      <span class="conclusion-label">结论</span>
      <strong>尚未分析</strong>
      <span class="state-chip neutral">未分析</span>
    </div>
    <div
      v-else-if="analysis.status === 'analyzed_nonissue'"
      class="conclusion nonissue"
    >
      <span class="conclusion-label">结论</span>
      <strong>非问题</strong>
    </div>
    <div
      v-else
      class="conclusion"
      :class="issueTone"
    >
      <span class="conclusion-label">结论</span>
      <strong>{{ issueLabel }}</strong>
    </div>

    <div
      v-if="analysis.status === 'unanalyzed'"
      class="unanalyzed-note"
    >
      该错误还没有归因分析，尚不能判断是否为问题。
    </div>

    <template v-if="analysis.status === 'analyzed_nonissue'">
      <div>
        <div class="label">
          非问题的分析原因
        </div>
        <p class="value-copy">
          {{ analysis.result.reason }}
        </p>
      </div>
      <div>
        <div class="label">
          分析推导过程
        </div>
        <ol class="reasoning">
          <li
            v-for="step in analysis.result.reasoning"
            :key="step"
          >
            {{ step }}
          </li>
        </ol>
      </div>
    </template>

    <template v-else-if="analysis.status === 'analyzed_issue' && probe">
      <div class="classification">
        <div class="attr-row">
          <span class="label">问题分类</span>
          <span
            class="state-chip"
            :class="issueTone"
          >{{ issueCategory }}</span>
        </div>
        <div class="attr-row">
          <span class="label">定位到的问题对象</span>
          <span class="object-name">{{ rootObject }}</span>
        </div>
      </div>
      <div>
        <div class="label">
          分析出的问题描述
        </div>
        <p class="value-copy pre-wrap">
          {{ probe.probeDescription }}
        </p>
      </div>
      <div>
        <div class="label">
          分析推导过程
        </div>
        <!-- eslint-disable vue/no-v-html -- MarkdownIt raw HTML is disabled and links are hardened. -->
        <div
          class="markdown"
          v-html="analysisHtml"
        />
        <!-- eslint-enable vue/no-v-html -->
      </div>
      <div v-if="probe.fromBadCases.length">
        <div class="label">
          来源问题
        </div>
        <div class="source-links">
          <a
            v-for="source in probe.fromBadCases"
            :key="source"
            :href="badCaseDeepLink(sessionId, source, 'desc')"
            :aria-label="`来源问题 ${shortBadCaseId(source)}，在新窗口打开问题描述`"
            rel="noopener noreferrer"
            target="_blank"
            :title="source"
          >
            {{ shortBadCaseId(source) }}
          </a>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.attribution {
  display: grid;
  gap: 14px;
  padding: 14px 18px 18px;
}

.conclusion {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  border: 1px solid currentColor;
  border-radius: 8px;
  font-size: 12px;
}

.conclusion.issue,
.conclusion.error {
  color: var(--red);
  background: color-mix(in srgb, var(--red) 5%, var(--bg-card));
}

.conclusion .state-chip {
  padding: 0 7px;
  border: 1px solid currentColor;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 400;
  text-transform: none;
}

.conclusion.model,
.conclusion.prompt {
  color: var(--purple);
  background: color-mix(in srgb, var(--purple) 5%, var(--bg-card));
}

.conclusion.prompt {
  color: var(--orange);
  background: color-mix(in srgb, var(--orange) 5%, var(--bg-card));
}

.conclusion.nonissue {
  color: var(--green);
  background: color-mix(in srgb, var(--green) 5%, var(--bg-card));
}

.conclusion.unanalyzed {
  color: var(--text-faint);
  background: var(--bg-inset);
  border-color: var(--border);
}

.conclusion-label,
.label {
  color: var(--text-faint);
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.conclusion-label {
  color: currentColor;
  opacity: 0.7;
}

.classification {
  display: grid;
  gap: 5px;
}

.unanalyzed-note {
  padding: 28px 4px;
  color: var(--text-faint);
  font-size: 12px;
  text-align: center;
}

.attr-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.classification .label {
  margin: 0;
}

.object-name {
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 11.5px;
}

.value-copy,
.reasoning {
  margin: 0;
  color: var(--text);
  font-size: 12.5px;
  line-height: 1.75;
}

.pre-wrap {
  white-space: pre-wrap;
}

.reasoning {
  padding-left: 20px;
}

.markdown {
  color: var(--text-dim);
  font-size: 12.5px;
  line-height: 1.75;
}

.markdown :deep(pre) {
  overflow-x: auto;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-inset);
  color: var(--text);
}

.markdown :deep(a) {
  color: var(--blue);
}

.source-links {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.source-links a {
  color: var(--blue);
  border-bottom: 1px dashed color-mix(in srgb, var(--blue) 45%, transparent);
  font-family: var(--mono);
  font-size: 11px;
  text-decoration: none;
}

.source-links a:hover {
  border-bottom-style: solid;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
