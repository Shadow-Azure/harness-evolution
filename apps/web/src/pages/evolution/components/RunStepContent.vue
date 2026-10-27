<script setup lang="ts">
import type {
  EvolutionRunCard,
  EvolutionStep,
  StepCondition,
} from "@harness/contracts";

import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import StepAttribution from "./StepAttribution.vue";
import StepClusters from "./StepClusters.vue";
import StepFinal from "./StepFinal.vue";
import StepInput from "./StepInput.vue";
import StepIterations from "./StepIterations.vue";
import StepSeverity from "./StepSeverity.vue";

defineProps<{
  run: EvolutionRunCard;
  step: EvolutionStep | undefined;
  condition: StepCondition;
  isPending: boolean;
  focusCluster?: string;
}>();
</script>

<template>
  <LoadingSkeleton
    v-if="isPending"
    label="正在读取当前步骤"
    :rows="3"
  />
  <StepInput
    v-else-if="step?.key === 'input'"
    :step="step"
    :condition="condition"
  />
  <StepClusters
    v-else-if="step?.key === 'clusters'"
    :step="step"
    :focus-cluster="focusCluster"
  />
  <StepAttribution
    v-else-if="step?.key === 'attribution'"
    :step="step"
    :run="run"
  />
  <StepSeverity
    v-else-if="step?.key === 'severity'"
    :step="step"
  />
  <StepIterations
    v-else-if="step?.key === 'iteration'"
    :step="step"
  />
  <StepFinal
    v-else-if="step?.key === 'final'"
    :step="step"
    :target-version="run.target.version"
  />
</template>
