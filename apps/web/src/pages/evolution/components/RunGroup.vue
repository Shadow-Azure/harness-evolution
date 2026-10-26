<script setup lang="ts">
import type { EvolutionRunCard } from "@harness/contracts";
import { computed } from "vue";

import RunCard from "./RunCard.vue";

const props = defineProps<{
  kind: "running" | "history";
  runs: EvolutionRunCard[];
}>();

const title = computed(() => props.kind === "running"
  ? `正在执行（${props.runs.length}）`
  : `历史记录（${props.runs.length}）`);
</script>

<template>
  <section
    class="run-group"
    :class="`run-group-${kind}`"
    :aria-label="title"
  >
    <h2 class="group-label">
      <span
        v-if="kind === 'running'"
        class="pulse"
        aria-hidden="true"
      />
      {{ title }}
    </h2>
    <div
      v-if="runs.length"
      class="run-list"
    >
      <RunCard
        v-for="run in runs"
        :key="run.runId"
        :run="run"
      />
    </div>
    <p
      v-else
      class="waiting"
    >
      {{ kind === "running"
        ? "当前没有正在执行的自进化"
        : "暂无历史记录" }}
    </p>
  </section>
</template>

<style scoped>
.run-group {
  display: grid;
  gap: 10px;
}

.group-label {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0 0;
  color: var(--text-faint);
  font-size: 12px;
  font-weight: 600;
}

.run-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.waiting {
  margin: 0;
  padding: 15px 16px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-card);
  color: var(--text-faint);
  font-size: 12px;
}

.pulse {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--blue);
  animation: pulse 1.4s infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.25;
  }
}
</style>
