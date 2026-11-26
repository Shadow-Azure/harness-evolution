<script setup lang="ts">
import type {
  EvolutionRunDetail,
  EvolutionStep,
} from "@harness/contracts";

import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import StepAttribution from "./StepAttribution.vue";
import StepClusters from "./StepClusters.vue";
import StepFinal from "./StepFinal.vue";
import StepIterations from "./StepIterations.vue";
import StepPotential from "./StepPotential.vue";
import StepRange from "./StepRange.vue";
import StepSessions from "./StepSessions.vue";

defineProps<{
  wid: string;
  run: EvolutionRunDetail;
  step: EvolutionStep | undefined;
  isPending: boolean;
  isUnreached: boolean;
  focusCluster?: string;
  canWrite?: boolean;
  caseSessions?: Record<string, string>;
  sharedProject?: {
    validationProjectId: string;
    testProjectId: string;
    primaryMetricKey: string;
  } | null;
  subDirs?: string[];
}>();
defineEmits<{
  "missing-cluster-focus": [];
  "page-change": [page: number];
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
  <StepRange
    v-else-if="step?.key === 'range'"
    :step="step"
    :target-revision="run.target.targetRevision"
    :shared-project="sharedProject"
    :sub-dirs="subDirs"
  />
  <StepSessions
    v-else-if="step?.key === 'sessions'"
    :step="step"
    @page-change="$emit('page-change', $event)"
  />
  <StepPotential
    v-else-if="step?.key === 'potential'"
    :wid="wid"
    :step="step"
    @page-change="$emit('page-change', $event)"
  />
  <StepAttribution
    v-else-if="step?.key === 'attribution'"
    :wid="wid"
    :can-write="canWrite"
    :step="step"
    :run="run"
  />
  <StepClusters
    v-else-if="step?.key === 'clusters'"
    :wid="wid"
    :step="step"
    :focus-cluster="focusCluster"
    :case-sessions="caseSessions"
    @missing-focus="$emit('missing-cluster-focus')"
  />
  <StepIterations
    v-else-if="step?.key === 'iteration'"
    :wid="wid"
    :step="step"
    :blocked-stage="run.blockedStage"
    :case-sessions="caseSessions"
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
