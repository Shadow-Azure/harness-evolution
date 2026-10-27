<script setup lang="ts">
import type {
  EvolutionRunCard,
  EvolutionStepAttribution,
  StepAttributionItem,
} from "@harness/contracts";

defineProps<{
  step: EvolutionStepAttribution;
  run: EvolutionRunCard;
}>();

function typeLabel(type: StepAttributionItem["attributeType"]): string {
  return type === "prompt" ? "prompt" : type === "model" ? "模型" : "错误";
}
</script>

<template>
  <article class="card panel">
    <h3 class="sec-title">
      第 3 步 · LLM 归因置信度
      <span class="sub">
        拉取 {{ run.target.name }}@{{ run.target.version }}，逐条判定问题在对象中是否真实存在
      </span>
    </h3>
    <div
      v-for="item in step.payload.items"
      :key="item.probeId"
      class="attr-card"
    >
      <div class="r1">
        <span class="cid">{{ item.clusterId }}</span>
        <b>{{ item.probeObject }}@{{ item.objectVersion ?? "—" }}</b>
        <span
          class="type-chip"
          :class="`type-${item.attributeType}`"
        >{{ typeLabel(item.attributeType) }}</span>
        <span class="badge">✓ 问题真实存在</span>
        <span class="confidence">
          <span class="bar">
            <span
              class="fill"
              :style="{ width: `${(item.confidence ?? 0) * 100}%` }"
            />
          </span>
          <span class="meta">
            置信度 {{ item.confidence === null ? "—" : `${(item.confidence * 100).toFixed(0)}%` }}
          </span>
        </span>
      </div>
      <p class="attr-line">
        <b>{{ item.description }}</b>
      </p>
      <p class="analysis">
        {{ item.analysis }}
      </p>
    </div>
    <p
      v-if="step.payload.items.length === 0"
      class="waiting"
    >
      当前运行还没有归因结果。
    </p>
  </article>
</template>

<style scoped>
.card {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.panel {
  padding: 16px 18px;
}

.sec-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  color: var(--text);
  font-size: 13.5px;
  font-weight: 650;
}

.sub {
  color: var(--text-faint);
  font-size: 11.5px;
  font-weight: 400;
}

.attr-card {
  margin-bottom: 10px;
  padding: 11px 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
}

.r1 {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 6px;
  flex-wrap: wrap;
  color: var(--text);
  font-size: 13px;
}

.cid {
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 11px;
}

.type-chip,
.badge {
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 10.5px;
}

.type-error {
  color: var(--red);
}

.type-prompt {
  color: var(--orange);
}

.type-model {
  color: var(--purple);
}

.badge {
  border-color: color-mix(in srgb, var(--green) 32%, transparent);
  background: color-mix(in srgb, var(--green) 8%, transparent);
  color: var(--green);
}

.confidence {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.bar {
  width: 56px;
  height: 5px;
  overflow: hidden;
  border-radius: 3px;
  background: var(--density-track);
}

.fill {
  display: block;
  height: 100%;
  border-radius: 3px;
  background: var(--blue);
}

.meta {
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 11.5px;
}

.attr-line,
.analysis {
  margin: 5px 0 0;
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.attr-line b {
  color: var(--text);
}

.analysis {
  max-height: 180px;
  overflow-y: auto;
  padding: 8px 10px;
  border-radius: 7px;
  background: var(--bg-panel);
  font-family: var(--mono);
  font-size: 11px;
}

.waiting {
  margin: 0;
  padding: 18px;
  border: 1px dashed var(--border);
  border-radius: 10px;
  color: var(--text-faint);
  font-size: 12.5px;
  text-align: center;
}
</style>
