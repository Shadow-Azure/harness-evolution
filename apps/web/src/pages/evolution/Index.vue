<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query";
import { computed, ref } from "vue";
import { useRouter } from "vue-router";

import ErrorState from "../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../components/ui/LoadingSkeleton.vue";
import { queryKeys } from "../../api/queryKeys";
import { useEvolutionRuns } from "../../composables/useEvolutionRuns";
import LaunchWizard from "./components/LaunchWizard.vue";
import RunGroup from "./components/RunGroup.vue";
import TargetConfigEntry from "./targets/components/TargetConfigEntry.vue";

defineOptions({ name: "EvolutionPage" });

const router = useRouter();
const queryClient = useQueryClient();
const { data, error, isPending, refetch } = useEvolutionRuns();
const wizardOpen = ref(false);
const running = computed(() => data.value?.running ?? []);
const history = computed(() => data.value?.history ?? []);

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
  await queryClient.invalidateQueries({ queryKey: queryKeys.evolutionRuns });
  await router.push(
    mode === "full" ? `/evolution/runs/${runId}` : `/evolution/cluster/${runId}`,
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
          <TargetConfigEntry />
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
        kind="running"
        :runs="running"
      />
      <RunGroup
        kind="history"
        :runs="history"
      />
    </template>
  </section>

  <LaunchWizard
    v-if="wizardOpen"
    @close="wizardOpen = false"
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
