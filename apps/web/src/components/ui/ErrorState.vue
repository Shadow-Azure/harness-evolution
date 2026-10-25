<script setup lang="ts">
defineProps({
  code: {
    type: String,
    default: "",
  },
  message: {
    type: String,
    required: true,
  },
  retryLabel: {
    type: String,
    default: "重试",
  },
  retryable: {
    type: Boolean,
    default: true,
  },
  title: {
    type: String,
    default: "加载失败",
  },
});

defineEmits(["retry"]);
</script>

<template>
  <section
    class="error-state"
    role="alert"
  >
    <p class="error-eyebrow">
      <span v-if="code">{{ code }}</span>
      <span>{{ title }}</span>
    </p>
    <p class="error-message">
      {{ message }}
    </p>
    <button
      v-if="retryable"
      type="button"
      @click="$emit('retry')"
    >
      {{ retryLabel }}
    </button>
  </section>
</template>

<style scoped>
.error-state {
  display: grid;
  justify-items: start;
  gap: var(--space-sm);
  padding: var(--space-xl) var(--space-lg);
  border: 1px solid var(--state-error-border);
  border-radius: var(--radius-lg);
  background: var(--state-error-surface);
}

.error-eyebrow {
  display: flex;
  gap: var(--space-xs);
  margin: 0;
  color: var(--state-error-text);
  font-size: 12px;
  font-weight: var(--weight-bold);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.error-message {
  margin: 0;
  color: var(--text-secondary);
}

button {
  padding: 7px 14px;
  border: 1px solid var(--state-error-border);
  border-radius: var(--radius-pill);
  background: var(--surface-overlay);
  color: var(--text-primary);
  cursor: pointer;
}
</style>
