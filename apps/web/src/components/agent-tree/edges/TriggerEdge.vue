<script setup lang="ts">
import { computed, type CSSProperties } from "vue";

import { triggerPath } from "../layout";

const props = defineProps<{
  id: string;
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
  style?: CSSProperties;
}>();

const path = computed(() =>
  triggerPath({
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    targetX: props.targetX,
    targetY: props.targetY,
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
