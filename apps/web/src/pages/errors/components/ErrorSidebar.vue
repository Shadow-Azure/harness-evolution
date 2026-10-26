<script setup lang="ts">
import type { BadCase, SessionListItem } from "@harness/contracts";

import BadCaseList from "../../../components/bad-cases/BadCaseList.vue";

defineProps<{
  problems: BadCase[];
  session: SessionListItem | null;
  sessionId: string;
  activeBadCaseId: string | null;
  loading: boolean;
  error: Error | null;
}>();

const emit = defineEmits<{
  all: [];
  retry: [];
  select: [badCaseId: string];
}>();
</script>

<template>
  <aside
    class="error-sidebar"
    aria-label="问题列表"
  >
    <header class="sidebar-heading">
      <div class="sidebar-title">
        <h1>错误</h1>
        <span class="count">{{ problems.length }} 个</span>
      </div>
      <div
        class="session-title"
        :title="session?.title ?? problems[0]?.sessionTitle ?? sessionId"
      >
        {{ session?.title ?? problems[0]?.sessionTitle ?? sessionId }}
      </div>
      <div
        class="session-id"
        :title="`session id: ${sessionId}`"
      >
        session · {{ sessionId }}
      </div>
      <RouterLink
        class="sidebar-back"
        :to="`/sessions/${encodeURIComponent(sessionId)}`"
      >
        ← 返回 Session
      </RouterLink>
    </header>
    <div class="sidebar-list">
      <button
        class="all-errors"
        :class="{ active: activeBadCaseId === null }"
        type="button"
        @click="emit('all')"
      >
        <span>全部错误</span>
        <b>{{ problems.length }}</b>
      </button>
      <BadCaseList
        compact
        :active-bad-case-id="activeBadCaseId"
        :error="error"
        :loading="loading"
        :problems="problems"
        :show-header="false"
        @retry="emit('retry')"
        @select="emit('select', $event)"
      />
    </div>
  </aside>
</template>

<style scoped>
.error-sidebar {
  display: flex;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  border-right: 1px solid var(--border);
  background: var(--bg-panel);
}

.sidebar-heading {
  display: grid;
  gap: 3px;
  padding: 14px 14px 10px;
  border-bottom: 1px solid var(--border);
}

.sidebar-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.sidebar-title h1 {
  margin: 0;
  color: var(--text);
  font-size: 14px;
  font-weight: 650;
}

.count {
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 11.5px;
}

.session-title,
.session-id {
  overflow: hidden;
  color: var(--text-dim);
  font-size: 11.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-id {
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 10px;
}

.sidebar-back {
  width: fit-content;
  margin-top: 5px;
  color: var(--blue);
  font-size: 11.5px;
  text-decoration: none;
}

.sidebar-back:hover {
  text-decoration: underline;
}

.sidebar-list {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  padding: 10px;
}

.all-errors {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: space-between;
  padding: 8px 11px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  color: var(--text-dim);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
}

.all-errors.active,
.all-errors:hover {
  border-color: var(--blue);
  background: color-mix(in srgb, var(--blue) 8%, var(--bg-card));
  color: var(--text);
}

.all-errors b {
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 11px;
}
</style>
