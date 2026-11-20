<script setup lang="ts">
import type {
  AttributionDetail,
  AttributionItem,
  BadCase,
} from "@harness/contracts";
import { computed } from "vue";

import ErrorState from "../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import { workspacePath } from "../../../router/workspace";
import {
  badCaseDeepLink,
  shortBadCaseId,
} from "../../../utils/badCaseId";
import { renderMarkdown } from "../../../utils/markdown";
import { formatStartedAt } from "../../../utils/sessionDisplay";
import {
  attributionCategory,
  attributionConclusion,
  attributionTriggerOrder,
} from "./attributionDisplay";

const props = defineProps<{
  wid: string;
  sessionId: string;
  problem: BadCase;
  attribution: AttributionDetail | null;
  attributions: AttributionItem[];
  selectedIndex: number;
  loading: boolean;
  error: Error | null;
  canStart: boolean;
}>();

const emit = defineEmits<{
  select: [attributionId: string];
  retry: [];
  start: [];
}>();

const conclusion = computed(() =>
  props.attribution
    ? attributionConclusion(props.attribution.conclusion)
    : null,
);
const version = computed(
  () => props.attribution?.objectVersion ?? "版本未固定",
);
const rootObject = computed(() => props.attribution?.objectName ?? "");
const category = computed(() =>
  props.attribution ? attributionCategory(props.attribution.category) : "",
);
const currentLink = computed(() =>
  props.attribution
    ? badCaseDeepLink(
        props.wid,
        props.sessionId,
        props.problem.badCaseId,
        "attr",
        props.attribution.attributionId,
      )
    : "",
);
const runLink = computed(() => {
  const runId = props.attribution?.runId;
  return runId
    ? workspacePath(props.wid, `evolution/runs/${encodeURIComponent(runId)}`)
    : "";
});
const reasoningHtml = computed(() =>
  props.attribution ? renderMarkdown(props.attribution.reasoning) : "",
);
const confidencePercent = computed(() =>
  props.attribution
    ? `${Math.round(props.attribution.confidence * 100)}%`
    : "",
);
const triggerOrder = computed(() =>
  props.attribution
    ? attributionTriggerOrder(props.attribution.triggerCompare.order)
    : "",
);
const objectTrigger = computed(() => {
  const value = props.attribution?.triggerCompare.objectTriggerAt;
  return value ? formatStartedAt(value) : "未知（时间戳待重放）";
});
const caseTrigger = computed(() => {
  const value = props.attribution?.triggerCompare.caseTriggerAt;
  return value ? formatStartedAt(value) : "未知（时间戳待重放）";
});
const versionUnknown = computed(
  () => props.attribution?.triggerCompare.versionState === "unknown",
);
const total = computed(() => props.attributions.length);
const hasPrevious = computed(() => props.selectedIndex > 0);
const hasNext = computed(
  () => props.selectedIndex >= 0 && props.selectedIndex < total.value - 1,
);
const canStartHere = computed(
  () => props.canStart && total.value === 0 && !props.loading && !props.error,
);

function move(direction: -1 | 1): void {
  const target = props.attributions[props.selectedIndex + direction];
  if (target) emit("select", target.attributionId);
}
</script>

<template>
  <LoadingSkeleton
    v-if="loading"
    label="正在读取归因分析"
    :rows="3"
  />
  <ErrorState
    v-else-if="error"
    code="ATTRIBUTION_UNAVAILABLE"
    message="归因详情读取失败，请重试。"
    @retry="emit('retry')"
  />
  <section
    v-else-if="attribution && conclusion"
    class="attribution"
    data-testid="attribution-report"
    aria-labelledby="attribution-title"
  >
    <h2
      id="attribution-title"
      class="sr-only"
    >
      归因分析
    </h2>
    <div class="attr-multi-nav">
      <span class="nav-note">该 bad case 的归因</span>
      <template v-if="total > 1">
        <button
          type="button"
          class="nav-button"
          data-testid="attribution-prev"
          title="上一条归因"
          :disabled="!hasPrevious"
          @click="move(-1)"
        >
          ←
        </button>
        <span
          class="nav-count"
          data-testid="attribution-position"
        >{{ selectedIndex + 1 }} / {{ total }}</span>
        <button
          type="button"
          class="nav-button"
          data-testid="attribution-next"
          title="下一条归因"
          :disabled="!hasNext"
          @click="move(1)"
        >
          →
        </button>
      </template>
      <span class="nav-spacer" />
      <a
        class="attr-id"
        :href="currentLink"
        rel="noopener noreferrer"
        target="_blank"
        data-testid="attribution-deep-link"
        :aria-label="`归因 ${shortBadCaseId(attribution.attributionId)}，在新窗口打开`"
        :title="attribution.attributionId"
      >
        {{ shortBadCaseId(attribution.attributionId) }}
      </a>
    </div>

    <div
      class="conclusion"
      :class="attribution.conclusion"
    >
      <span class="conclusion-label">结论</span>
      <strong>
        {{ attribution.conclusion === "attributed"
          ? "可归因到本对象"
          : attribution.conclusion === "non_target"
            ? "非该对象问题"
            : "归因证据不足" }}
      </strong>
      <span
        v-if="attribution.conclusion === 'attributed'"
        class="state-chip"
        :class="attribution.category ?? 'neutral'"
      >{{ category }}</span>
      <span class="cache-badge">
        {{ attribution.isCached ? "复用缓存归因" : "本次新增" }}
      </span>
    </div>

    <div class="meta-grid">
      <div class="meta-row">
        <span class="label">进化对象</span>
        <span class="value mono">{{ rootObject }} · {{ version }}</span>
        <span class="label spaced">归因来源</span>
        <RouterLink
          v-if="runLink"
          class="run-link"
          :to="runLink"
          :title="attribution.runId ?? ''"
        >
          {{ attribution.runId }}
        </RouterLink>
        <span
          v-else
          class="value"
        >—</span>
        <span class="label spaced">时间</span>
        <span class="value">{{ formatStartedAt(attribution.createdAt) }}</span>
      </div>
      <div class="meta-row">
        <span class="label">置信度</span>
        <span class="value mono">{{ confidencePercent }}</span>
        <span class="label spaced">策略</span>
        <span class="value">{{ attribution.policyVersion }} · {{ attribution.attributionEngine }}</span>
      </div>
    </div>

    <div class="trigger-compare">
      <div class="trigger-cell">
        <div class="label">
          对象触发点
        </div>
        <div class="value">
          {{ objectTrigger }}
        </div>
      </div>
      <div class="trigger-cell">
        <div class="label">
          bad case 触发点
        </div>
        <div class="value">
          {{ caseTrigger }}
        </div>
      </div>
      <div class="trigger-order">
        {{ triggerOrder }}
      </div>
      <p
        v-if="versionUnknown"
        class="trigger-note"
      >
        该归因没有固定的对象版本，不能视为精确版本命中；轨迹时间戳待重放。
      </p>
      <p
        v-else-if="attribution.triggerCompare.order === 'unknown'"
        class="trigger-note"
      >
        两处触发点无法比较，轨迹时间戳待重放。
      </p>
    </div>

    <div
      class="cache-note"
      :class="{ cached: attribution.isCached }"
    >
      <span class="cache-icon">{{ attribution.isCached ? "♻" : "＋" }}</span>
      <span>
        <b>{{ attribution.isCached ? "复用缓存" : "本次新增" }}</b>：
        <template v-if="attribution.isCached">
          {{ attribution.objectName }} {{ version }} 已对该 bad case 生成过归因，本次直接复用最近一次成功结果；缓存键包含工作空间、对象版本、策略版本与归因模型。
        </template>
        <template v-else>
          缓存未命中，本次运行对该 bad case 执行完整归因；结论写回后可供后续运行复用。
        </template>
      </span>
    </div>

    <div class="attr-block">
      <div class="label">
        归因结论说明
      </div>
      <p class="value-copy">
        {{ attribution.reason }}
      </p>
    </div>

    <div class="attr-block">
      <div class="label">
        推导过程
      </div>
      <!-- eslint-disable vue/no-v-html -- MarkdownIt raw HTML is disabled and links are hardened. -->
      <div
        class="markdown"
        v-html="reasoningHtml"
      />
      <!-- eslint-enable vue/no-v-html -->
    </div>

    <div
      v-if="attribution.warnings.length"
      class="warnings"
    >
      <div class="label">
        证据缺口
      </div>
      <ul>
        <li
          v-for="warning in attribution.warnings"
          :key="warning.code"
        >
          <span class="warning-code">{{ warning.code }}</span>
          {{ warning.message }}
        </li>
      </ul>
    </div>

    <div class="boundary">
      <b>结论边界</b>：该结论只作用于 {{ attribution.objectName }} {{ version }}，不会修改 bad case 本身，也不影响它与其他进化对象的潜在关系。
    </div>
  </section>

  <section
    v-else-if="attributions.length === 0"
    class="attribution no-attribution"
    data-testid="attribution-empty"
    aria-labelledby="attribution-title"
  >
    <h2
      id="attribution-title"
      class="sr-only"
    >
      归因分析
    </h2>
    <div class="conclusion unanalyzed">
      <span class="conclusion-label">结论</span>
      <strong>尚未归因</strong>
      <span class="state-chip neutral">未进入自进化</span>
    </div>
    <p class="empty-copy">
      该 bad case 还没有被任何自进化运行归因。启动自进化后，会先判断它是否属于所选对象的潜在 bad case，再生成对象级归因。
    </p>
    <button
      v-if="canStartHere"
      type="button"
      class="start-evolution"
      data-testid="start-evolution-from-case"
      @click="emit('start')"
    >
      以该 bad case 启动自进化 →
    </button>
  </section>
  <ErrorState
    v-else
    code="ATTRIBUTION_UNAVAILABLE"
    message="归因详情读取失败，请重试。"
    @retry="emit('retry')"
  />
</template>

<style scoped>
.attribution {
  position: relative;
  display: grid;
  gap: 13px;
  padding: 12px 18px 18px;
}

.attr-multi-nav {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-faint);
  font-size: 10.5px;
}

.nav-note {
  font-weight: 600;
}

.nav-spacer {
  flex: 1;
}

.nav-button {
  width: 21px;
  height: 19px;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: var(--bg-card);
  color: var(--text-dim);
  cursor: pointer;
  font: inherit;
  font-size: 10px;
}

.nav-button:disabled {
  cursor: default;
  opacity: 0.4;
}

.nav-count {
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 10px;
}

.attr-id {
  color: var(--purple);
  font-family: var(--mono);
  font-size: 10px;
  text-decoration: none;
  border-bottom: 1px dashed color-mix(in srgb, var(--purple) 45%, transparent);
}

.attr-id:hover {
  border-bottom-style: solid;
}

.conclusion {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  border: 1px solid currentColor;
  border-radius: 8px;
  color: var(--green);
  background: color-mix(in srgb, var(--green) 5%, var(--bg-card));
  font-size: 12px;
}

.conclusion.non_target,
.conclusion.inconclusive {
  color: var(--orange);
  background: color-mix(in srgb, var(--orange) 5%, var(--bg-card));
}

.conclusion.unanalyzed {
  color: var(--text-faint);
  background: var(--bg-inset);
  border-color: var(--border);
}

.conclusion strong {
  font-size: 14px;
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

.state-chip {
  padding: 0 7px;
  border: 1px solid currentColor;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 400;
  text-transform: none;
}

.state-chip.model {
  color: var(--purple);
}

.state-chip.prompt {
  color: var(--orange);
}

.state-chip.error {
  color: var(--red);
}

.state-chip.neutral {
  color: var(--text-faint);
}

.cache-badge {
  margin-left: auto;
  padding: 0 7px;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-faint);
  font-size: 9.5px;
}

.meta-grid {
  display: grid;
  gap: 5px;
}

.meta-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 11px;
}

.label.spaced {
  margin-left: 12px;
}

.value {
  color: var(--text-dim);
  font-size: 11px;
}

.mono {
  font-family: var(--mono);
}

.run-link {
  color: var(--blue);
  font-family: var(--mono);
  font-size: 10px;
  text-decoration: none;
  border-bottom: 1px dashed color-mix(in srgb, var(--blue) 45%, transparent);
}

.run-link:hover {
  border-bottom-style: solid;
}

.trigger-compare {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px 12px;
  padding: 9px 11px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-inset);
}

.trigger-cell .value {
  color: var(--text);
  font-family: var(--mono);
  font-size: 10.5px;
}

.trigger-order {
  grid-column: 1 / -1;
  color: var(--text-dim);
  font-size: 10.5px;
}

.trigger-note {
  grid-column: 1 / -1;
  margin: 0;
  color: var(--orange);
  font-size: 10.5px;
}

.cache-note {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-inset);
  color: var(--text-faint);
  font-size: 10.5px;
  line-height: 1.6;
}

.cache-note.cached {
  border-color: color-mix(in srgb, var(--green) 35%, var(--border));
}

.cache-icon {
  flex-shrink: 0;
  color: var(--green);
  font-size: 12px;
}

.cache-note b {
  color: var(--text-dim);
}

.attr-block {
  display: grid;
  gap: 4px;
}

.value-copy {
  margin: 0;
  color: var(--text);
  font-size: 12.5px;
  line-height: 1.75;
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

.warnings {
  display: grid;
  gap: 3px;
}

.warnings ul {
  margin: 0;
  padding-left: 17px;
  color: var(--orange);
  font-size: 11px;
  line-height: 1.6;
}

.warning-code {
  margin-right: 5px;
  font-family: var(--mono);
  font-size: 9.5px;
  opacity: 0.75;
}

.boundary {
  padding: 8px 10px;
  border: 1px dashed var(--border);
  border-radius: 7px;
  color: var(--text-faint);
  font-size: 10.5px;
  line-height: 1.6;
}

.no-attribution {
  justify-items: start;
}

.empty-copy {
  margin: 0;
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1.7;
}

.start-evolution {
  padding: 6px 11px;
  border: 1px solid var(--blue);
  border-radius: 6px;
  background: color-mix(in srgb, var(--blue) 8%, var(--bg-card));
  color: var(--blue);
  cursor: pointer;
  font: inherit;
  font-size: 11.5px;
}

.start-evolution:hover {
  background: color-mix(in srgb, var(--blue) 14%, var(--bg-card));
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
