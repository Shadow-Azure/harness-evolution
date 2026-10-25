<script setup lang="ts">
import { computed, type CSSProperties } from "vue";

import { orthPath } from "../layout";

const props = defineProps<{
  id: string;
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
  data?: {
    trunkX?: number;
  };
  style?: CSSProperties;
}>();

const path = computed(() =>
  orthPath({
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    targetX: props.targetX,
    targetY: props.targetY,
    trunkX: props.data?.trunkX,
  }),
);

const markerId = computed(
  () => `agent-tree-arrow-${props.id.replace(/[^a-zA-Z0-9_-]/g, "-")}`,
);
const markerEnd = computed(() => `url(#${markerId.value})`);
</script>

<template>
  <g>
    <defs>
      <marker
        :id="markerId"
        markerWidth="8"
        markerHeight="8"
        refX="7"
        refY="4"
        orient="auto"
        markerUnits="strokeWidth"
      >
        <path
          d="M 0 0 L 8 4 L 0 8 z"
          fill="var(--graph-branch)"
        />
      </marker>
    </defs>
    <path
      :id="id"
      class="vue-flow__edge-path"
      :d="path"
      :marker-end="markerEnd"
      :style="style"
    />
  </g>
</template>
