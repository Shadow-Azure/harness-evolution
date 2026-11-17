<script setup lang="ts">
import type { BadCase } from "@harness/contracts";
import { computed, watch } from "vue";

import ErrorState from "../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import { useAttributionPage } from "../../../composables/useBadCases";
import {
  badCaseDeepLink,
  shortBadCaseId,
} from "../../../utils/badCaseId";
import AttributionItem from "./AttributionItem.vue";

const props = defineProps<{
  wid: string;
  sessionId: string;
  problem: BadCase;
  index: number;
  expanded: boolean;
  page: number;
  active: boolean;
  selectedAttributionId: string | null;
  canStart: boolean;
}>();

const emit = defineEmits<{
  toggle: [];
  page: [page: number];
  start: [];
}>();

const pageSize = 2;
const pageRequest = computed(() => (props.expanded ? props.page : 0));
const attributionsQuery = useAttributionPage(
  () => props.wid,
  () => props.problem.badCaseId,
  pageRequest,
  pageSize,
);
const total = computed(
  () => attributionsQuery.data.value?.total ?? props.problem.attributionCount,
);
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));
const items = computed(() => attributionsQuery.data.value?.items ?? []);
const descriptionLink = computed(() =>
  badCaseDeepLink(
    props.wid,
    props.sessionId,
    props.problem.badCaseId,
    "desc",
  ),
);
const panelId = computed(
  () => `case-attributions-${props.problem.badCaseId}`,
);

watch(
  [total, pageCount, () => props.expanded],
  ([nextTotal, nextPages, expanded]) => {
    if (!expanded) return;
    if (nextTotal === 0 && props.page !== 1) {
      emit("page", 1);
      return;
    }
    if (props.page > nextPages) {
      emit("page", nextPages);
    }
  },
);
</script>

<template>
  <section
    class="case-group"
    :class="{ active, expanded }"
    data-testid="case-group"
    :data-bad-case-id="problem.badCaseId"
  >
    <div class="case-head">
      <button
        class="case-toggle"
        type="button"
        data-testid="case-toggle"
        :aria-expanded="expanded"
        :aria-controls="panelId"
        :aria-label="`${expanded ? '折叠' : '展开'} ${shortBadCaseId(problem.badCaseId)} 的归因`"
        @click="emit('toggle')"
      >
        {{ expanded ? "▾" : "▸" }}
      </button>
      <div class="case-main">
        <RouterLink
          class="case-title-link"
          :to="descriptionLink"
          data-testid="case-title-link"
          :aria-current="active && selectedAttributionId === null ? 'page' : undefined"
          :title="problem.badCaseId"
        >
          <span class="case-no">BC{{ index }}</span>
          <span class="tt">{{ problem.title }}</span>
        </RouterLink>
        <div class="case-meta">
          <a
            class="case-id"
            :href="descriptionLink"
            rel="noopener noreferrer"
            target="_blank"
            data-testid="case-id"
            :aria-label="`bad case ${shortBadCaseId(problem.badCaseId)}，在新窗口打开问题描述`"
            :title="problem.badCaseId"
          >
            {{ shortBadCaseId(problem.badCaseId) }}
          </a>
          <span
            class="type-badge"
            :class="problem.badCaseType"
          >{{ problem.badCaseType }}</span>
          <span class="object-name">{{ problem.objectName }}</span>
        </div>
      </div>
      <span
        class="case-count"
        :title="`${total} 条归因`"
      >{{ total }}</span>
    </div>

    <div
      v-if="expanded"
      :id="panelId"
      class="attr-list"
    >
      <div class="attr-list-title">
        归因分析 · 按进化对象
      </div>
      <LoadingSkeleton
        v-if="attributionsQuery.isPending.value"
        label="正在读取归因"
        :rows="2"
      />
      <ErrorState
        v-else-if="attributionsQuery.error.value"
        code="ATTRIBUTIONS_UNAVAILABLE"
        message="归因列表读取失败，请重试。"
        @retry="attributionsQuery.refetch()"
      />
      <template v-else>
        <AttributionItem
          v-for="attribution in items"
          :key="attribution.attributionId"
          :wid="wid"
          :session-id="sessionId"
          :bad-case-id="problem.badCaseId"
          :attribution="attribution"
          :active="
            active && selectedAttributionId === attribution.attributionId
          "
        />
        <div
          v-if="total === 0"
          class="attr-empty"
          data-testid="case-attributions-empty"
        >
          <span>暂无归因。尚未进入自进化。</span>
          <button
            v-if="canStart"
            class="attr-start"
            type="button"
            data-testid="case-start-evolution"
            @click="emit('start')"
          >
            启动自进化后生成 →
          </button>
        </div>
      </template>
      <div
        v-if="total > pageSize"
        class="attr-pager"
      >
        <button
          type="button"
          data-testid="attribution-page-prev"
          :disabled="page <= 1"
          @click="emit('page', page - 1)"
        >
          ← 上一页
        </button>
        <span>{{ page }} / {{ pageCount }}</span>
        <button
          type="button"
          data-testid="attribution-page-next"
          :disabled="page >= pageCount"
          @click="emit('page', page + 1)"
        >
          下一页 →
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.case-group {
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-card);
}

.case-group.active {
  border-color: var(--blue);
}

.case-head {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  padding: 7px 7px 6px 4px;
}

.case-toggle {
  flex-shrink: 0;
  width: 20px;
  height: 22px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
  font: inherit;
  font-size: 11px;
  line-height: 1;
}

.case-toggle:hover {
  color: var(--text);
}

.case-main {
  display: grid;
  min-width: 0;
  flex: 1;
  gap: 2px;
}

.case-title-link {
  display: flex;
  min-width: 0;
  align-items: baseline;
  gap: 6px;
  color: var(--text);
  text-decoration: none;
}

.case-title-link:hover .tt {
  color: var(--blue);
}

.case-title-link:focus-visible {
  outline: 2px solid var(--blue);
  outline-offset: 1px;
}

.case-no {
  flex-shrink: 0;
  color: var(--red);
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 700;
}

.tt {
  min-width: 0;
  overflow: hidden;
  font-size: 11.5px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.case-meta {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 5px;
  color: var(--text-faint);
  font-size: 9.5px;
}

.case-id {
  flex-shrink: 0;
  color: var(--blue);
  font-family: var(--mono);
  font-size: 9.5px;
  text-decoration: none;
  border-bottom: 1px dashed color-mix(in srgb, var(--blue) 45%, transparent);
}

.case-id:hover {
  border-bottom-style: solid;
}

.type-badge {
  flex-shrink: 0;
  padding: 0 5px;
  border: 1px solid currentColor;
  border-radius: 999px;
  font-size: 8.5px;
}

.type-badge.self {
  color: var(--purple);
}

.type-badge.discovery {
  color: var(--blue);
}

.object-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.case-count {
  flex-shrink: 0;
  padding: 1px 6px;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 9.5px;
}

.attr-list {
  display: grid;
  gap: 3px;
  padding: 0 7px 7px 24px;
}

.attr-list-title {
  padding: 3px 0 2px;
  color: var(--text-faint);
  font-size: 9.5px;
}

.attr-empty {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 2px;
  color: var(--text-faint);
  font-size: 10px;
}

.attr-start {
  padding: 0;
  border: 0;
  background: none;
  color: var(--blue);
  cursor: pointer;
  font: inherit;
  font-size: 10px;
}

.attr-pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 4px;
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 9.5px;
}

.attr-pager button {
  padding: 2px 6px;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: var(--bg-inset);
  color: var(--text-dim);
  cursor: pointer;
  font: inherit;
  font-size: 9.5px;
}

.attr-pager button:disabled {
  cursor: default;
  opacity: 0.45;
}
</style>
