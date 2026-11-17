<script setup lang="ts">
import type {
  TargetOverviewItem,
  TargetState,
  TargetTrendBucket,
} from "@harness/contracts";
import { computed } from "vue";

const STATES: TargetState[] = ["attributed", "nonTarget", "unanalyzed"];

const STATE_LABELS: Record<TargetState, string> = {
  attributed: "是",
  nonTarget: "非",
  unanalyzed: "未",
};

const props = defineProps({
  items: {
    type: Array as () => TargetOverviewItem[],
    default: () => [],
  },
  buckets: {
    type: Array as () => TargetTrendBucket[],
    default: () => [],
  },
  selectedTargets: {
    type: Array as () => string[],
    default: () => [],
  },
  selectedStates: {
    type: Array as () => TargetState[],
    default: () => [],
  },
});

const chosen = computed<TargetState[]>(() =>
  props.selectedStates.length > 0 ? props.selectedStates : STATES,
);
const activeItems = computed(() => {
  if (props.selectedTargets.length === 0) return props.items;
  const selected = new Set(props.selectedTargets);
  return props.items.filter((item) => selected.has(item.targetId));
});

const maxSessions = computed(() =>
  Math.max(1, ...activeItems.value.map((item) => item.sessions)),
);

const potentialById = computed(() => {
  const totals = new Map<
    string,
    Record<TargetState, number> & { total: number }
  >();
  for (const bucket of props.buckets) {
    for (const row of bucket.byTarget) {
      const current = totals.get(row.targetId) ?? {
        attributed: 0,
        nonTarget: 0,
        unanalyzed: 0,
        total: 0,
      };
      for (const state of chosen.value) {
        current[state] += row[state];
        current.total += row[state];
      }
      totals.set(row.targetId, current);
    }
  }
  return totals;
});

const maxPotential = computed(() =>
  Math.max(
    1,
    ...activeItems.value.map(
      (item) => potentialById.value.get(item.targetId)?.total ?? 0,
    ),
  ),
);

function sessionsWidth(item: TargetOverviewItem): string {
  return `${(item.sessions / maxSessions.value) * 100}%`;
}

function potentialWidth(item: TargetOverviewItem): string {
  const total = potentialById.value.get(item.targetId)?.total ?? 0;
  return `${(total / maxPotential.value) * 100}%`;
}

function sharePercent(item: TargetOverviewItem, state: TargetState): number {
  const row = potentialById.value.get(item.targetId);
  if (!row || row.total <= 0) return 0;
  return (row[state] / row.total) * 100;
}

function potentialTotal(item: TargetOverviewItem): number {
  return potentialById.value.get(item.targetId)?.total ?? 0;
}

function potentialCount(item: TargetOverviewItem, state: TargetState): number {
  return potentialById.value.get(item.targetId)?.[state] ?? 0;
}
</script>

<template>
  <div
    class="distributions"
    data-testid="ov-target-distributions"
  >
    <section class="dist">
      <div class="dist-title">
        不同进化对象的关联 Session
        <span>按对象汇总；柱长按最大值归一，一个 Session 可同时出现在多个对象下</span>
      </div>
      <p
        v-if="activeItems.length === 0"
        class="waiting"
      >
        当前空间还没有进化对象
      </p>
      <div
        v-for="item in activeItems"
        :key="`session-${item.targetId}`"
        class="row"
        data-testid="ov-target-assoc-row"
        :title="`${item.objectName} · ${item.sessions} 关联 Session · ${potentialTotal(item)} 潜在 bad case`"
      >
        <span class="name">{{ item.objectName }}</span>
        <span class="bar">
          <span
            class="fill sessions"
            :style="{ width: sessionsWidth(item) }"
          />
        </span>
        <span class="num">
          <b>{{ item.sessions }}</b> 关联 · {{ potentialTotal(item) }} 潜在
        </span>
      </div>
    </section>

    <section class="dist">
      <div class="dist-title">
        不同进化对象的潜在 bad case
        <span>按对象聚合，柱长按最大值归一；同一 bad case 可能出现在多个对象下</span>
      </div>
      <p
        v-if="activeItems.length === 0"
        class="waiting"
      >
        当前空间还没有进化对象
      </p>
      <div
        v-for="item in activeItems"
        :key="`potential-${item.targetId}`"
        class="row"
        data-testid="ov-target-potential-row"
        :title="`${item.objectName} · 潜在 ${potentialTotal(item)} · ${chosen
          .map((state) => `${STATE_LABELS[state]} ${potentialCount(item, state)}`)
          .join(' / ')}`"
      >
        <span class="name">{{ item.objectName }}</span>
        <span class="bar">
          <span
            class="fill potential"
            :style="{ width: potentialWidth(item) }"
          >
            <span
              v-for="state in chosen"
              :key="state"
              class="segment"
              :class="state"
              :style="{ width: `${sharePercent(item, state)}%` }"
            />
          </span>
        </span>
        <span class="num">
          <b>{{ potentialTotal(item) }}</b> · 是 {{ potentialCount(item, 'attributed') }}
          / 非 {{ potentialCount(item, 'nonTarget') }}
          / 未 {{ potentialCount(item, 'unanalyzed') }}
        </span>
      </div>
    </section>
  </div>
</template>

<style scoped>
.distributions {
  margin-top: 12px;
  border-top: 1px solid var(--border);
  padding-top: 10px;
}

.dist + .dist {
  margin-top: 12px;
}

.dist-title {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 7px;
  margin-bottom: 5px;
  color: var(--text);
  font-size: 12px;
  font-weight: 650;
}

.dist-title span {
  color: var(--text-faint);
  font-size: 10px;
  font-weight: 400;
}

.row {
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr) 178px;
  gap: 10px;
  align-items: center;
  padding: 4px 0;
}

.name {
  overflow: hidden;
  color: var(--text-dim);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bar {
  height: 7px;
  overflow: hidden;
  border-radius: 4px;
  background: var(--density-track);
}

.fill {
  display: flex;
  height: 100%;
  overflow: hidden;
  border-radius: 4px;
}

.fill.sessions {
  background: var(--blue);
}

.fill.potential {
  background: var(--density-track);
}

.segment {
  height: 100%;
}

.segment.attributed {
  background: var(--green);
}

.segment.nonTarget {
  background: var(--orange);
}

.segment.unanalyzed {
  background: var(--border-strong);
}

.num {
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 9.5px;
  white-space: nowrap;
}

.num b {
  color: var(--text);
  font-size: 11px;
  font-weight: 600;
}

.waiting {
  margin: 4px 0;
  color: var(--text-faint);
  font-size: 10.5px;
}

@media (max-width: 760px) {
  .row {
    grid-template-columns: 90px minmax(0, 1fr);
  }

  .num {
    grid-column: 2;
    white-space: normal;
  }
}
</style>
