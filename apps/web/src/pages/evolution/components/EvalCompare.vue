<script setup lang="ts">
import type { StepRoundEval } from "@harness/contracts";
import { computed } from "vue";

const props = defineProps<{
  evaluation: StepRoundEval;
}>();

const normalizedMax = computed(() => {
  const current = props.evaluation.current ?? 0;
  const candidate = props.evaluation.candidate ?? 0;
  return Math.max(current, candidate) * 1.06;
});

const currentWidth = computed(() => widthFor(props.evaluation.current));
const candidateWidth = computed(() => widthFor(props.evaluation.candidate));
const improved = computed(
  () =>
    props.evaluation.candidate !== null &&
    props.evaluation.current !== null &&
    props.evaluation.candidate >= props.evaluation.current,
);

function widthFor(value: number | null): string {
  if (value === null || normalizedMax.value <= 0) return "0%";
  return `${((value / normalizedMax.value) * 100).toFixed(1)}%`;
}

function score(value: number | null): string {
  return value === null ? "—" : value.toFixed(1);
}
</script>

<template>
  <div class="evalcmp">
    <div class="evalrow">
      <span class="who">current skill</span>
      <span class="bar">
        <span
          class="fill current"
          :style="{ width: currentWidth }"
        />
      </span>
      <span class="val">{{ score(evaluation.current) }}</span>
    </div>
    <div class="evalrow">
      <span class="who">candidate</span>
      <span class="bar">
        <span
          class="fill candidate"
          :class="{ worse: !improved }"
          :style="{ width: candidateWidth }"
        />
      </span>
      <span class="val">{{ score(evaluation.candidate) }}</span>
    </div>
    <div class="eval-note">
      {{ evaluation.status === "evaluating"
        ? "评测中，等待 candidate 得分"
        : improved
          ? "评测有收益，candidate 已提升为 current"
          : "评测无收益，current 保持不变" }}
    </div>
  </div>
</template>

<style scoped>
.evalcmp {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-width: 560px;
}

.evalrow {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 11.5px;
}

.who {
  width: 92px;
  flex-shrink: 0;
  color: var(--text-dim);
}

.bar {
  flex: 1;
  height: 8px;
  overflow: hidden;
  border-radius: 4px;
  background: var(--density-track);
}

.fill {
  display: block;
  height: 100%;
  border-radius: 4px;
}

.fill.current {
  background: var(--text-faint);
}

.fill.candidate {
  background: var(--green);
}

.fill.candidate.worse {
  background: var(--red);
}

.val {
  width: 44px;
  color: var(--text);
  font-family: var(--mono);
  font-weight: 600;
  text-align: right;
}

.eval-note {
  color: var(--text-dim);
  font-size: 11.5px;
}
</style>
