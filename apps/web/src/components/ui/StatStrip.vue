<script setup lang="ts">
defineProps({
  items: {
    type: Array as () => Array<{
      label: string;
      value: string | number;
      tone?: "bad" | "warn";
    }>,
    default: () => [],
  },
});
</script>

<template>
  <dl class="stat-strip">
    <div
      v-for="item in items"
      :key="String(item.label)"
      class="stat"
      :class="item.tone"
    >
      <dt>{{ item.label }}</dt>
      <dd>{{ item.value }}</dd>
    </div>
  </dl>
</template>

<style scoped>
.stat-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(88px, 1fr));
  margin: 0;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-card);
}

.stat {
  min-width: 0;
  padding: 10px 12px;
  border-right: 1px solid var(--border);
}

.stat:last-child {
  border-right: 0;
}

.stat dt {
  color: var(--text-faint);
  font-size: 10.5px;
}

.stat dd {
  margin: 2px 0 0;
  color: var(--text);
  font-family: var(--mono);
  font-size: 14px;
  font-weight: 650;
}

.stat.bad dd {
  color: var(--red);
}

.stat.warn dd {
  color: var(--orange);
}
</style>
