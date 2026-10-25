<script setup lang="ts">
import type { SessionListItem } from "@harness/contracts";
import { computed, nextTick, ref, watch } from "vue";

import ErrorState from "../../../components/ui/ErrorState.vue";
import SessionCard from "./SessionCard.vue";

const props = defineProps({
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

const activeIndex = ref(0);
const hasOptions = computed(
  () => !props.loading && !props.error && props.items.length > 0,
);

function syncActiveIndex() {
  if (props.items.length === 0) {
    activeIndex.value = 0;
    return;
  }
  const selectedIndex = props.items.findIndex(
    (item) => item.id === props.selectedId,
  );
  if (selectedIndex >= 0) {
    activeIndex.value = selectedIndex;
    return;
  }
  activeIndex.value = Math.min(activeIndex.value, props.items.length - 1);
}

watch(
  [() => props.items, () => props.selectedId],
  syncActiveIndex,
  { immediate: true },
);

function focusOption(index: number) {
  activeIndex.value = index;
  const item = props.items[index];
  if (!item) return;
  emit("select", item.id);
  void nextTick(() => {
    document.getElementById(`session-option-${item.id}`)?.focus();
  });
}

function handleKeydown(event: KeyboardEvent) {
  if (!hasOptions.value) return;
  let nextIndex: number | null = null;
  if (event.key === "ArrowDown") {
    nextIndex = (activeIndex.value + 1) % props.items.length;
  } else if (event.key === "ArrowUp") {
    nextIndex =
      (activeIndex.value - 1 + props.items.length) % props.items.length;
  } else if (event.key === "Home") {
    nextIndex = 0;
  } else if (event.key === "End") {
    nextIndex = props.items.length - 1;
  }
  if (nextIndex === null) return;
  event.preventDefault();
  focusOption(nextIndex);
}
</script>

<template>
  <div
    class="session-list"
    :aria-busy="loading || undefined"
    :aria-label="hasOptions ? 'Session 列表' : undefined"
    :role="hasOptions ? 'listbox' : undefined"
    @keydown="handleKeydown"
  >
    <div
      v-if="loading"
      class="loading-list"
      role="status"
      aria-label="正在加载 Session 列表"
    >
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
    </div>
    <ErrorState
      v-else-if="error"
      code="SESSIONS_UNAVAILABLE"
      message="Session 列表加载失败，请重试。"
      @retry="emit('retry')"
    />
    <div
      v-else-if="items.length === 0"
      class="empty-list"
      role="status"
    >
      <strong>没有匹配当前筛选的 session</strong>
      <span>调整搜索词或状态筛选后重试。</span>
    </div>
    <template v-else>
      <SessionCard
        v-for="(item, index) in items"
        :key="item.id"
        :focusable="index === activeIndex"
        :item="item"
        :selected="item.id === selectedId"
        @focus="activeIndex = index"
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

.loading-list {
  display: grid;
  gap: 8px;
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
