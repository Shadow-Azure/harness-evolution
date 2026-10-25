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
  gap: var(--space-sm);
  padding: var(--space-xl) var(--space-lg);
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-lg);
  background: var(--surface-overlay);
}

.empty-mark {
  color: var(--brand-accent);
  font-size: 30px;
}

h2 {
  margin: 0;
  font-size: 18px;
}

p {
  max-width: 560px;
  margin: 0;
  color: var(--text-muted);
  line-height: 1.7;
}

.empty-action {
  margin-top: var(--space-sm);
}
</style>
