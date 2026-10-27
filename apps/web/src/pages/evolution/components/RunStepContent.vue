<script setup lang="ts">
import type {
  EvolutionRunDetail,
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
  run: EvolutionRunDetail;
  step: EvolutionStep | undefined;
  condition: StepCondition;
  isPending: boolean;
  isUnreached: boolean;
  focusCluster?: string;
}>();
defineEmits<{
  "missing-cluster-focus": [];
}>();
</script>

<template>
  <LoadingSkeleton
    v-if="isPending"
    label="正在读取当前步骤"
    :rows="3"
  />
  <p
    v-else-if="isUnreached"
    class="unreached-copy"
  >
    该步骤尚未到达。<template v-if="run.status === 'failed' || run.status === 'interrupted'">
      运行在第 1 步完成前已终止。
    </template>
  </p>
  <StepInput
    v-else-if="step?.key === 'input'"
    :step="step"
    :condition="condition"
  />
  <StepClusters
    v-else-if="step?.key === 'clusters'"
    :step="step"
    :focus-cluster="focusCluster"
    @missing-focus="$emit('missing-cluster-focus')"
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
    :blocked-stage="run.blockedStage"
  />
  <StepFinal
    v-else-if="step?.key === 'final'"
    :step="step"
    :target-version="run.target.version"
    :push-status="run.workspace.pushStatus"
    :pushed-at="run.workspace.pushedAt"
  />
</template>

<style scoped>
.unreached-copy {
  margin: 0;
  padding: 18px;
  border: 1px dashed var(--border);
  border-radius: 10px;
  color: var(--text-faint);
  font-size: 12.5px;
  text-align: center;
}
</style>
