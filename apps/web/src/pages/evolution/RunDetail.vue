<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

import ErrorState from "../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../components/ui/LoadingSkeleton.vue";
import { useEvolutionRuns } from "../../composables/useEvolutionRuns";

defineOptions({ name: "EvolutionRunDetailPage" });

const route = useRoute();
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

const statusLabel = computed(() => {
  if (!run.value) {
    return "";
  }
  if (run.value.status === "preparing") {
    return "准备中";
  }
  if (run.value.status === "running") {
    return "正在执行";
  }
  return run.value.status;
});

function retry(): void {
  void refetch();
}
</script>

<template>
  <section
    class="run-detail-page"
    data-testid="evolution-run-detail"
  >
    <header class="page-intro">
      <h1>{{ run ? run.title : "自进化运行" }}</h1>
      <p class="page-note">
        运行 ID <span class="mono">{{ runId }}</span>
      </p>
    </header>

    <LoadingSkeleton
      v-if="isPending"
      label="正在读取运行详情"
      :rows="3"
    />
    <ErrorState
      v-else-if="error"
      code="EVOLUTION_RUN_UNAVAILABLE"
      message="运行详情读取失败，请重试"
      @retry="retry"
    />
    <template v-else-if="run">
      <div
        class="status-banner preparing"
        data-testid="run-status"
      >
        <span class="badge">{{ statusLabel }}</span>
        <span v-if="run.status === 'preparing'">已受理，正在准备筛选与聚类，完成后此处展示六步进度。</span>
        <span v-else>{{ run.progress.stageLabel }}（{{ run.progress.percent }}%）</span>
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
        <div class="kv">
          <span class="k">模型</span>
          <span class="mono">{{ run.models.length ? run.models.join(", ") : "全部模型" }}</span>
        </div>
        <div class="kv">
          <span class="k">模式</span>
          <span>{{ run.mode === "cluster_only" ? "仅聚类预览" : "完整自进化" }}</span>
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
.run-detail-page {
  display: grid;
  gap: 14px;
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
  border: 1px solid color-mix(in srgb, var(--blue) 40%, transparent);
  background: color-mix(in srgb, var(--blue) 8%, transparent);
  border-radius: 10px;
  padding: 11px 14px;
  font-size: 12.5px;
  color: var(--text-dim);
}

.badge {
  font-weight: 600;
  color: var(--blue);
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
