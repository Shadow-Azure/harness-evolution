<script setup lang="ts">
defineProps({
  description: {
    type: String,
    default: "",
  },
  title: {
    type: String,
    required: true,
  },
});
</script>

<template>
  <section class="empty-state">
    <span
      class="empty-mark"
      aria-hidden="true"
    >◇</span>
    <h2>{{ title }}</h2>
    <p v-if="description">
      {{ description }}
    </p>
    <div
      v-if="$slots.action"
      class="empty-action"
    >
      <slot name="action" />
    </div>
  </section>
</template>

<style scoped>
.empty-state {
  display: grid;
  justify-items: start;
  gap: 10px;
  padding: 28px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.empty-mark {
  color: var(--cyan);
  font-size: 26px;
}

h2 {
  margin: 0;
  color: var(--text);
  font-size: 15px;
  font-weight: 650;
}

p {
  max-width: 560px;
  margin: 0;
  color: var(--text-dim);
  font-size: 12.5px;
  line-height: 1.65;
}

.empty-action {
  margin-top: var(--space-sm);
}
</style>
