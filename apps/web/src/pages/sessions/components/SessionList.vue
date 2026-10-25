<script setup lang="ts">
import type { SessionListItem } from "@harness/contracts";

import ErrorState from "../../../components/ui/ErrorState.vue";
import SessionCard from "./SessionCard.vue";

defineProps({
  items: {
    type: Array as () => SessionListItem[],
    default: () => [],
  },
  selectedId: {
    type: String,
    default: "",
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: Object as () => Error | null,
    default: null,
  },
});

const emit = defineEmits<{
  retry: [];
  select: [sessionId: string];
}>();
</script>

<template>
  <div
    class="session-list"
    role="listbox"
    aria-label="Session 列表"
  >
    <template v-if="loading">
      <div
        v-for="index in 4"
        :key="index"
        class="skeleton-card"
        aria-hidden="true"
      >
        <span />
        <span />
        <span />
      </div>
    </template>
    <ErrorState
      v-else-if="error"
      code="SESSIONS_UNAVAILABLE"
      message="Session 列表加载失败，请重试。"
      @retry="emit('retry')"
    />
    <div
      v-else-if="items.length === 0"
      class="empty-list"
    >
      <strong>没有匹配当前筛选的 session</strong>
      <span>调整搜索词或状态筛选后重试。</span>
    </div>
    <template v-else>
      <SessionCard
        v-for="item in items"
        :key="item.id"
        :item="item"
        :selected="item.id === selectedId"
        @select="emit('select', $event)"
      />
    </template>
  </div>
</template>

<style scoped>
.session-list {
  display: grid;
  align-content: start;
  gap: 8px;
  min-height: 0;
  overflow-y: auto;
  padding: 0 10px 12px;
}

.skeleton-card {
  display: grid;
  gap: 9px;
  height: 132px;
  padding: 13px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-card);
}

.skeleton-card span {
  height: 10px;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--bg-inset), var(--bg-card), var(--bg-inset));
}

.skeleton-card span:nth-child(1) {
  width: 72%;
}

.skeleton-card span:nth-child(2) {
  width: 52%;
}

.skeleton-card span:nth-child(3) {
  width: 90%;
}

.empty-list {
  display: grid;
  place-content: center;
  min-height: 210px;
  padding: 20px;
  border: 1px dashed var(--border);
  border-radius: 10px;
  color: var(--text-dim);
  text-align: center;
}

.empty-list strong {
  color: var(--text);
  font-size: 12.5px;
}

.empty-list span {
  margin-top: 4px;
  color: var(--text-faint);
  font-size: 11.5px;
}
</style>
