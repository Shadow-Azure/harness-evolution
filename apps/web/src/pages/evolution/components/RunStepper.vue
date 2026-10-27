<script setup lang="ts">
import type { EvolutionStepKey } from "@harness/contracts";

import type { RunStep } from "../runDetail";

defineProps<{
  steps: RunStep[];
  selected: EvolutionStepKey;
}>();

const emit = defineEmits<{
  select: [key: EvolutionStepKey];
}>();
</script>

<template>
  <div
    class="stepper"
    aria-label="运行步骤"
  >
    <template
      v-for="(step, index) in steps"
      :key="step.key"
    >
      <span
        v-if="index"
        class="conn"
        :class="{ done: steps[index - 1]?.status === 'done' }"
        aria-hidden="true"
      />
      <button
        class="xstep"
        :class="[
          step.status,
          {
            clickable: step.clickable,
            selected: selected === step.key,
          },
        ]"
        type="button"
        :data-step-key="step.key"
        :disabled="!step.clickable"
        :aria-current="selected === step.key ? 'step' : undefined"
        :title="step.clickable ? '点击查看该步骤的产出' : '该步骤尚未到达'"
        @click="emit('select', step.key)"
      >
        <span
          class="ico"
          aria-hidden="true"
        >
          <span
            v-if="step.status === 'active'"
            class="pulse"
          />
          <template v-else>{{ step.status === "done" ? "✓" : index + 1 }}</template>
        </span>
        <span class="lbl">
          {{ step.title }}<template v-if="step.detail">（{{ step.detail }}）</template>
        </span>
      </button>
    </template>
  </div>
  <p class="step-hint">
    已完成 / 进行中的节点可点击，下方内容切换为该步骤的产出；未到达的节点不可点击。
  </p>
</template>

<style scoped>
.stepper {
  display: flex;
  align-items: center;
  gap: 0;
  overflow-x: auto;
  padding: 4px 2px;
}

.xstep {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-shrink: 0;
  padding: 4px 8px;
  margin: -4px -8px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  font: inherit;
}

.xstep.clickable {
  cursor: pointer;
}

.xstep.clickable:hover {
  background: color-mix(in srgb, var(--blue) 8%, transparent);
}

.xstep:disabled {
  cursor: not-allowed;
}

.ico {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: 1.5px solid var(--border);
  border-radius: 50%;
  background: var(--bg-card);
  color: var(--text-faint);
  font-size: 11px;
  font-weight: 700;
}

.xstep.done .ico {
  border-color: var(--green);
  background: var(--green);
  color: white;
}

.xstep.active .ico {
  border-color: var(--blue);
  color: var(--blue);
}

.xstep.selected .ico {
  border-color: var(--blue);
  background: var(--blue);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--blue) 22%, transparent);
  color: white;
}

.lbl {
  color: var(--text-faint);
  font-size: 12px;
  white-space: nowrap;
}

.xstep.done .lbl {
  color: var(--text);
}

.xstep.active .lbl,
.xstep.selected .lbl {
  color: var(--blue);
  font-weight: 700;
}

.conn {
  width: 34px;
  height: 1.5px;
  margin: 0 8px;
  flex-shrink: 0;
  background: var(--border);
}

.conn.done {
  background: var(--green);
}

.pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--blue);
  animation: pulse 1.4s infinite;
}

.step-hint {
  margin: 8px 0 0;
  color: var(--text-faint);
  font-size: 11px;
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
