<script setup lang="ts">
import type {
  EvolutionRunEvent,
  EvolutionRunStep,
  EvolutionStepKey,
} from "@harness/contracts";

import ErrorDetail from "./ErrorDetail.vue";

defineProps<{
  events: EvolutionRunEvent[];
  steps: EvolutionRunStep[];
}>();

const emit = defineEmits<{
  "select-step": [key: EvolutionStepKey];
  "focus-cluster": [clusterId: string];
}>();

const stepKeys: EvolutionStepKey[] = [
  "input",
  "clusters",
  "attribution",
  "severity",
  "iteration",
  "final",
];

const icons: Record<string, string> = {
  candidate_committed: "◆",
  eval_completed: "✓",
  cluster_accepted: "✓",
  cluster_rejected: "×",
  run_failed: "!",
  run_interrupted: "!",
  run_blocked: "△",
};

function formatTime(value: string): string {
  return value.replace("T", " ").slice(0, 19);
}

function selectStep(
  event: EvolutionRunEvent,
  steps: EvolutionRunStep[],
): void {
  if (event.stepIndex === null) return;
  const key = stepKeys[event.stepIndex];
  const step = steps.find((candidate) => candidate.key === key);
  if (step?.clickable) emit("select-step", step.key);
}
</script>

<template>
  <div class="event-list">
    <article
      v-for="event in events"
      :key="event.seq"
      class="event-row"
      :class="event.level"
      :data-event-seq="event.seq"
    >
      <span
        class="event-icon"
        aria-hidden="true"
      >{{ icons[event.eventType] ?? "·" }}</span>
      <time class="event-time mono">{{ formatTime(event.createdAt) }}</time>
      <div class="event-main">
        <div class="event-meta">
          <span class="stage">{{ event.stage }}</span>
          <span class="event-type mono">{{ event.eventType }}</span>
          <button
            v-if="
              event.stepIndex !== null &&
                steps[event.stepIndex]?.clickable
            "
            type="button"
            class="jump"
            @click="selectStep(event, steps)"
          >
            step {{ event.stepIndex + 1 }}
          </button>
          <button
            v-if="event.clusterId && steps[1]?.clickable"
            type="button"
            class="jump cluster"
            :title="event.clusterId"
            @click="emit('focus-cluster', event.clusterId)"
          >
            {{ event.clusterId.slice(0, 8) }}
          </button>
          <span
            v-if="event.payload?.durationMs"
            class="duration mono"
          >{{ event.payload.durationMs }}ms</span>
        </div>
        <p class="event-message">
          {{ event.message }}
        </p>
        <ErrorDetail
          v-if="event.error"
          :error="event.error"
        />
      </div>
      <span class="seq mono">#{{ event.seq }}</span>
    </article>
  </div>
</template>

<style scoped>
.event-list {
  display: grid;
  gap: 1px;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--border);
}

.event-row {
  display: grid;
  grid-template-columns: 22px 140px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: start;
  padding: 10px 12px;
  background: var(--bg-card);
}

.event-row.warn {
  background: color-mix(in srgb, var(--orange) 5%, var(--bg-card));
}

.event-row.error {
  background: color-mix(in srgb, var(--red) 5%, var(--bg-card));
}

.event-icon {
  display: grid;
  width: 20px;
  height: 20px;
  place-items: center;
  border-radius: 50%;
  background: var(--bg-inset);
  color: var(--text-faint);
  font-size: 11px;
}

.warn .event-icon {
  color: var(--orange);
}

.error .event-icon {
  color: var(--red);
}

.event-time,
.seq,
.duration {
  color: var(--text-faint);
  font-size: 10.5px;
}

.event-main {
  min-width: 0;
}

.event-meta {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
}

.stage,
.event-type,
.jump {
  font-family: var(--mono);
  font-size: 10.5px;
}

.stage {
  color: var(--cyan);
  text-transform: uppercase;
}

.event-type {
  color: var(--text-faint);
}

.jump {
  padding: 0 5px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: transparent;
  color: var(--blue);
  cursor: pointer;
}

.jump.cluster {
  color: var(--purple);
}

.event-message {
  margin: 4px 0 0;
  color: var(--text);
  font-size: 12px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.seq {
  padding-top: 2px;
}

@media (max-width: 720px) {
  .event-row {
    grid-template-columns: 20px minmax(0, 1fr) auto;
  }

  .event-time {
    display: none;
  }
}
</style>
