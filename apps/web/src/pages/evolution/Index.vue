<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query";
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import ErrorState from "../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../components/ui/LoadingSkeleton.vue";
import { queryKeys } from "../../api/queryKeys";
import { useEvolutionRuns } from "../../composables/useEvolutionRuns";
import { useWorkspaceId } from "../../composables/useWorkspaceId";
import { workspacePath } from "../../router/workspace";
import { useAuthStore } from "../../stores/auth";
import LaunchWizard from "./components/LaunchWizard.vue";
import RunGroup from "./components/RunGroup.vue";
import TargetConfigEntry from "./targets/components/TargetConfigEntry.vue";

defineOptions({ name: "EvolutionPage" });

const router = useRouter();
const route = useRoute();
const queryClient = useQueryClient();
const auth = useAuthStore();
const workspaceId = useWorkspaceId();
const workspaceName = computed(
  () => auth.workspaceById(workspaceId.value)?.name ?? "",
);
const { data, error, isPending, refetch } = useEvolutionRuns(workspaceId);
const focusCaseId = computed(() => {
  const value = route.query.case;
  return typeof value === "string" && value ? value : null;
});
const wizardOpen = ref(Boolean(focusCaseId.value));
const running = computed(() => data.value?.running ?? []);
const history = computed(() => data.value?.history ?? []);

watch(focusCaseId, (caseId) => {
  if (caseId) {
    wizardOpen.value = true;
  }
});

/**
 * Close the wizard and drop the one-shot focus-case query.
 * @returns A navigation promise when a query cleanup is needed.
 */
async function closeWizard(): Promise<void> {
  wizardOpen.value = false;
  if (!focusCaseId.value) {
    return;
  }
  const query = { ...route.query };
  delete query.case;
  await router.replace({ query });
}

function retry(): void {
  void refetch();
}

/**
 * Leave the wizard open-free and follow the accepted run to its detail page.
 * @param mode Launched run mode.
 * @param runId Accepted run identifier.
 */
async function onLaunched(
  mode: "full" | "cluster_only",
  runId: string,
): Promise<void> {
  wizardOpen.value = false;
  await queryClient.invalidateQueries({
    queryKey: queryKeys.evolutionRuns(workspaceId.value),
  });
  await router.push(
    workspacePath(
      workspaceId.value,
      mode === "full"
        ? `evolution/runs/${encodeURIComponent(runId)}`
        : `evolution/cluster/${encodeURIComponent(runId)}`,
    ),
  );
}

/**
 * Open one run detail while preserving backend-provided run identity.
 * @param path Backend-mode-specific detail path.
 * @returns A navigation promise after the route changes.
 */
async function openRun(path: string): Promise<void> {
  await router.push(
    path.startsWith("/workspaces/")
      ? path
      : workspacePath(workspaceId.value, path.replace(/^\/+/, "")),
  );
}
</script>

<template>
  <section
    class="evolution-page-frame run-list-page"
    data-testid="evolution-run-list"
  >
    <header class="page-intro">
      <div class="page-head">
        <h1>自进化</h1>
        <div class="page-actions">
          <TargetConfigEntry :wid="workspaceId" />
          <button
            class="launch-run"
            type="button"
            data-testid="open-launch-wizard"
            @click="wizardOpen = true"
          >
            ＋ 启动自进化
          </button>
        </div>
      </div>
      <p class="page-note">
        基于问题报告对 skill / agent 做「聚类 → 归因 → 按严重程度迭代打 patch → 评测接纳 → 测试集终评」的自动进化。
      </p>
    </header>

    <LoadingSkeleton
      v-if="isPending"
      label="正在读取自进化运行"
      :rows="4"
    />
    <ErrorState
      v-else-if="error"
      code="EVOLUTION_RUNS_UNAVAILABLE"
      message="自进化运行读取失败，请重试"
      @retry="retry"
    />
    <template v-else>
      <RunGroup
        :wid="workspaceId"
        :workspace-name="workspaceName"
        kind="running"
        :runs="running"
        @open="openRun"
      />
      <RunGroup
        :wid="workspaceId"
        :workspace-name="workspaceName"
        kind="history"
        :runs="history"
        @open="openRun"
      />
    </template>
  </section>

  <LaunchWizard
    v-if="wizardOpen"
    :wid="workspaceId"
    :focus-case-id="focusCaseId"
    @close="closeWizard"
    @launched="onLaunched"
  />
</template>

<style scoped>
.run-list-page {
  display: grid;
  gap: 14px;
}

.page-intro {
  min-width: 0;
  margin-bottom: 2px;
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 6px;
}

h1 {
  margin: 0;
  color: var(--text);
  font-size: 18px;
  font-weight: 700;
}

.page-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.launch-run {
  padding: 6px 14px;
  border: 1px solid var(--blue);
  border-radius: 8px;
  background: var(--blue);
  color: white;
  font-size: 12.5px;
  font-weight: 600;
}

.launch-run:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.page-note {
  margin: 0;
  color: var(--text-faint);
  font-size: 12px;
  line-height: 1.55;
}

@media (max-width: 640px) {
  .page-head {
    align-items: flex-start;
  }
}
</style>
