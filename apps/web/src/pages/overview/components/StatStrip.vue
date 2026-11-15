<script setup lang="ts">
import type { OverviewTotals } from "@harness/contracts";
import { computed } from "vue";

import ErrorState from "../../../components/ui/ErrorState.vue";

const props = defineProps({
  totals: {
    type: Object as () => OverviewTotals | null,
    default: null,
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
  "select-type": [value: "self" | "discovery"];
  "focus-sources": [];
}>();

const quotaRatio = computed(() => {
  const totals = props.totals;
  if (!totals || totals.quota <= 0) return 0;
  return totals.used / totals.quota;
});

const cells = computed(() => {
  const totals = props.totals;
  return [
    {
      key: "badcases",
      label: "bad case 总数",
      value: totals ? String(totals.badCases) : "—",
      tone: "",
    },
    {
      key: "self",
      label: "自身存在问题",
      value: totals ? String(totals.self) : "—",
      tone: "self",
    },
    {
      key: "discovery",
      label: "发现前置步骤问题",
      value: totals ? String(totals.discovery) : "—",
      tone: "discovery",
    },
    {
      key: "sessions",
      label: "关联 Session",
      value: totals ? String(totals.sessions) : "—",
      tone: "",
    },
    {
      key: "sources",
      label: "上报来源",
      value: totals ? String(totals.sources) : "—",
      tone: "",
    },
    {
      key: "quota",
      label: "空间额度",
      value: totals ? `${totals.used} / ${totals.quota}` : "—",
      tone: quotaRatio.value > 0.8 ? "bad" : "",
    },
  ];
});
</script>

<template>
  <ErrorState
    v-if="error"
    code="OVERVIEW_SUMMARY_UNAVAILABLE"
    message="总览统计加载失败，请重试；趋势与列表仍可独立查看。"
    @retry="emit('retry')"
  />
  <section
    v-else
    class="statstrip"
    aria-label="总览统计"
    :aria-busy="loading || undefined"
    data-testid="ov-statstrip"
  >
    <component
      :is="cell.key === 'self' || cell.key === 'discovery' ? 'button' : 'div'"
      v-for="cell in cells"
      :key="cell.key"
      class="ss"
      :class="cell.tone"
      :data-testid="`ov-stat-${cell.key}`"
      :type="cell.key === 'self' || cell.key === 'discovery' ? 'button' : undefined"
      :title="
        cell.key === 'self' || cell.key === 'discovery'
          ? `只看${cell.label}`
          : undefined
      "
      @click="
        cell.key === 'self' || cell.key === 'discovery'
          ? emit('select-type', cell.key)
          : undefined
      "
    >
      <b>{{ cell.value }}</b>
      <span>{{ cell.label }}</span>
    </component>
    <button
      class="ss-sources-focus"
      data-testid="ov-stat-sources-focus"
      type="button"
      title="聚焦来源筛选"
      @click="emit('focus-sources')"
    >
      来源筛选
    </button>
  </section>
</template>

<style scoped>
.statstrip {
  display: flex;
  flex-wrap: wrap;
  align-items: stretch;
  margin: 0 0 14px;
  padding: 7px 0;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.ss {
  flex: 1 1 0;
  min-width: 82px;
  padding: 1px 8px;
  border: 0;
  border-left: 1px solid var(--border);
  background: none;
  text-align: center;
}

.ss:first-child {
  border-left: 0;
}

button.ss {
  cursor: pointer;
}

button.ss:hover b {
  text-decoration: underline;
}

.ss b {
  display: block;
  color: var(--text);
  font-family: var(--mono);
  font-size: 15px;
  font-weight: 650;
  line-height: 1.35;
}

.ss span {
  color: var(--text-faint);
  font-size: 10px;
  white-space: nowrap;
}

.ss.self b {
  color: var(--blue);
}

.ss.discovery b {
  color: var(--purple);
}

.ss.bad b {
  color: var(--red);
}

.ss-sources-focus {
  align-self: center;
  margin: 0 8px;
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 10px;
  cursor: pointer;
}

.ss-sources-focus:hover {
  border-color: var(--blue);
  color: var(--text);
}

@media (max-width: 640px) {
  .statstrip {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .ss {
    border-left: 0;
  }

  .ss-sources-focus {
    grid-column: 1 / -1;
    justify-self: center;
  }
}
</style>
