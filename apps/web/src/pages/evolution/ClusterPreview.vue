<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";

import ErrorState from "../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../components/ui/LoadingSkeleton.vue";
import { useEvolutionRuns } from "../../composables/useEvolutionRuns";

defineOptions({ name: "ClusterPreviewPage" });

const route = useRoute();
const router = useRouter();
const runId = computed(() => String(route.params.runId ?? ""));
const { data, error, isPending, refetch } = useEvolutionRuns();

const run = computed(() => {
  const list = data.value;
  if (!list) {
    return null;
  }
  return (
    list.running.find((card) => card.runId === runId.value) ??
    list.history.find((card) => card.runId === runId.value) ??
    null
  );
});

function retry(): void {
  void refetch();
}
</script>

<template>
  <section
    class="cluster-preview-page"
    data-testid="evolution-cluster-preview"
  >
    <div class="banner">
      仅聚类分析：未执行 patch 生成与评测迭代。
      <span class="spacer" />
      <button
        class="btn primary"
        type="button"
        @click="router.push('/evolution')"
      >
        返回运行列表
      </button>
    </div>

    <LoadingSkeleton
      v-if="isPending"
      label="正在读取仅聚类预览"
      :rows="3"
    />
    <ErrorState
      v-else-if="error"
      code="EVOLUTION_CLUSTER_UNAVAILABLE"
      message="仅聚类预览读取失败，请重试"
      @retry="retry"
    />
    <template v-else-if="run">
      <header class="page-intro">
        <h1>{{ run.title }}</h1>
        <p class="page-note">
          运行 ID <span class="mono">{{ runId }}</span>
        </p>
      </header>
      <div
        class="status-banner"
        data-testid="cluster-status"
      >
        <span class="badge">{{ run.status === "preparing" ? "准备中" : run.status }}</span>
        <span v-if="run.status === 'preparing'">正在筛选与聚类，完成后此处展示问题簇。</span>
        <span v-else>{{ run.progress.stageLabel }}</span>
      </div>
      <div class="info-panel">
        <div class="kv">
          <span class="k">进化对象</span>
          <span class="mono">{{ run.target.type }}:{{ run.target.name }}@{{ run.target.version }}</span>
        </div>
        <div class="kv">
          <span class="k">时间窗口</span>
          <span class="mono">{{ run.window.from ?? "—" }} ~ {{ run.window.to ?? "—" }}</span>
        </div>
      </div>
    </template>
    <ErrorState
      v-else
      code="EVOLUTION_RUN_NOT_FOUND"
      message="运行不存在或已被删除"
      :retryable="false"
    />
  </section>
</template>

<style scoped>
.cluster-preview-page {
  display: grid;
  gap: 14px;
}

.banner {
  border: 1px solid color-mix(in srgb, var(--orange) 40%, transparent);
  background: color-mix(in srgb, var(--orange) 8%, transparent);
  border-radius: 10px;
  padding: 11px 14px;
  font-size: 12.5px;
  color: var(--text-dim);
  display: flex;
  align-items: center;
  gap: 12px;
}

.banner .spacer {
  flex: 1;
}

h1 {
  margin: 0;
  color: var(--text);
  font-size: 18px;
  font-weight: 700;
}

.page-note {
  margin: 4px 0 0;
  color: var(--text-faint);
  font-size: 12px;
}

.mono {
  font-family: var(--mono);
}

.status-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid color-mix(in srgb, var(--orange) 40%, transparent);
  background: color-mix(in srgb, var(--orange) 8%, transparent);
  border-radius: 10px;
  padding: 11px 14px;
  font-size: 12.5px;
  color: var(--text-dim);
}

.badge {
  font-weight: 600;
  color: var(--orange);
}

.info-panel {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-card);
  padding: 14px 16px;
  font-size: 12.5px;
}

.kv {
  display: flex;
  gap: 8px;
  min-width: 0;
}

.kv .k {
  color: var(--text-faint);
  flex: none;
}
</style>
