<script setup lang="ts">
import { computed } from "vue";

import { densityWidth, formatDensity } from "../../utils/sessionDisplay";

const props = defineProps({
  label: {
    type: String,
    required: true,
  },
  tone: {
    type: String,
    default: "fail",
    validator: (value: string) => value === "fail" || value === "problem",
  },
  value: {
    type: Number,
    required: true,
  },
});

const width = computed(() => densityWidth(props.value));
const valueText = computed(() => formatDensity(props.value));
</script>

<template>
  <div
    class="density-row"
    data-testid="density-bar"
  >
    <span class="density-label">{{ label }}</span>
    <span class="density-track">
      <span
        class="density-fill"
        :class="tone"
        :style="{ width }"
      />
    </span>
    <span class="density-value">{{ valueText }}</span>
  </div>
</template>

<style scoped>
.density-row {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) 64px;
  align-items: center;
  gap: 6px;
  font-size: 10.5px;
}

.density-label,
.density-value {
  color: var(--text-faint);
}

.density-value {
  font-family: var(--mono);
  text-align: right;
}

.density-track {
  height: 5px;
  overflow: hidden;
  border-radius: 3px;
  background: var(--density-track);
}

.density-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
}

.density-fill.fail {
  background: linear-gradient(90deg, color-mix(in srgb, var(--red) 55%, var(--bg-card)), var(--red));
}

.density-fill.problem {
  background: linear-gradient(90deg, color-mix(in srgb, var(--orange) 55%, var(--bg-card)), var(--orange));
}
</style>
