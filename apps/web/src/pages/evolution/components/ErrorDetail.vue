<script setup lang="ts">
import type { EvolutionRunEventError } from "@harness/contracts";
import { computed, ref } from "vue";

const props = defineProps<{
  error: EvolutionRunEventError;
}>();

const copied = ref(false);

const copyText = computed(() =>
  [props.error.type, props.error.message, props.error.detail]
    .filter((part): part is string => Boolean(part))
    .join("\n"),
);

async function copyDetail(): Promise<void> {
  try {
    await navigator.clipboard.writeText(copyText.value);
    copied.value = true;
  } catch {
    copied.value = false;
  }
}
</script>

<template>
  <details class="error-detail">
    <summary>
      <span class="error-label">
        {{ error.type ?? "执行错误" }}
      </span>
      <span class="error-message">{{ error.message ?? "无错误摘要" }}</span>
    </summary>
    <div class="error-body">
      <button
        type="button"
        class="copy-detail"
        @click="copyDetail"
      >
        {{ copied ? "已复制" : "复制脱敏详情" }}
      </button>
      <pre v-if="error.detail">{{ error.detail }}</pre>
      <p v-else>
        没有更详细的错误信息。
      </p>
    </div>
  </details>
</template>

<style scoped>
.error-detail {
  margin-top: 7px;
  border-left: 2px solid var(--red);
  padding-left: 9px;
  color: var(--text-dim);
  font-size: 11.5px;
}

summary {
  display: flex;
  gap: 8px;
  cursor: pointer;
  list-style: none;
}

summary::-webkit-details-marker {
  display: none;
}

summary::before {
  content: "▸";
  color: var(--red);
}

details[open] summary::before {
  content: "▾";
}

.error-label {
  flex-shrink: 0;
  color: var(--red);
  font-family: var(--mono);
  font-weight: 650;
}

.error-message {
  overflow-wrap: anywhere;
}

.error-body {
  position: relative;
  margin-top: 7px;
}

.copy-detail {
  float: right;
  margin-left: 8px;
  padding: 2px 7px;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: var(--bg-inset);
  color: var(--text-faint);
  font: inherit;
  cursor: pointer;
}

.copy-detail:hover {
  color: var(--text);
}

pre {
  margin: 7px 0 0;
  padding: 9px;
  overflow: auto;
  border-radius: 7px;
  background: var(--bg-inset);
  color: var(--text-dim);
  font: 11px/1.55 var(--mono);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

p {
  margin: 7px 0 0;
}
</style>
