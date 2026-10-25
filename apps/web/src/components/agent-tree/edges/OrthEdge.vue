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
</script>

<template>
  <path
    :id="id"
    class="vue-flow__edge-path"
    :d="path"
    :style="style"
  />
</template>
