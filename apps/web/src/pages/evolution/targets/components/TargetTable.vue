<script setup lang="ts">
import type { EvolutionTarget } from "@harness/contracts";
import { computed } from "vue";

import EmptyState from "../../../../components/ui/EmptyState.vue";
import ErrorState from "../../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../../components/ui/LoadingSkeleton.vue";

const props = withDefaults(
  defineProps<{
    targets: EvolutionTarget[];
    loading?: boolean;
    error?: Error | null;
    canWrite: boolean;
  }>(),
  {
    loading: false,
    error: null,
  },
);

const emit = defineEmits<{
  create: [];
  edit: [target: EvolutionTarget];
  delete: [target: EvolutionTarget];
  retry: [];
}>();

const hasRows = computed(() => props.targets.length > 0);

function toggle(target: EvolutionTarget): void {
  emit("edit", {
    ...target,
    enabled: !target.enabled,
  });
}
</script>

<template>
  <section
    class="target-table-panel"
    aria-labelledby="target-table-title"
  >
    <header class="target-table-head">
      <div>
        <h2 id="target-table-title">
          已配置对象
        </h2>
        <p>配置列表包含停用项；启动向导只读取已启用对象。</p>
      </div>
      <button
        v-if="canWrite"
        class="target-create"
        type="button"
        @click="emit('create')"
      >
        新增配置
      </button>
    </header>

    <LoadingSkeleton
      v-if="loading"
      label="正在读取进化对象配置"
      :rows="4"
    />
    <ErrorState
      v-else-if="error"
      code="EVOLUTION_TARGETS_UNAVAILABLE"
      message="进化对象配置读取失败，请重试。"
      @retry="emit('retry')"
    />
    <EmptyState
      v-else-if="!hasRows"
      description="新增一个 skill 或 agent，启动向导才会显示候选对象。"
      title="暂无进化对象配置"
    />
    <div
      v-else
      class="target-table-scroll"
    >
      <table class="target-table">
        <thead>
          <tr>
            <th>对象类型</th>
            <th>对象名称</th>
            <th>仓库</th>
            <th>子目录</th>
            <th>基线</th>
            <th>状态</th>
            <th v-if="canWrite">
              操作
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="target in targets"
            :key="target.id"
          >
            <td>
              <span class="kind-chip">{{ target.objectType }}</span>
            </td>
            <td class="object-name">
              {{ target.objectName }}
            </td>
            <td
              class="repo-url"
              :title="target.repoUrl"
            >
              {{ target.repoUrl }}
            </td>
            <td class="mono">
              {{ target.subDir }}
            </td>
            <td class="mono">
              {{ target.defaultRef }}
            </td>
            <td>
              <span
                class="state-chip"
                :class="{ enabled: target.enabled }"
              >
                {{ target.enabled ? "已启用" : "已停用" }}
              </span>
            </td>
            <td
              v-if="canWrite"
              class="row-actions"
            >
              <button
                class="edit-target"
                type="button"
                @click="emit('edit', target)"
              >
                编辑
              </button>
              <button
                class="toggle-target"
                type="button"
                @click="toggle(target)"
              >
                {{ target.enabled ? "停用" : "启用" }}
              </button>
              <button
                class="delete-target"
                type="button"
                @click="emit('delete', target)"
              >
                删除
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.target-table-panel {
  display: grid;
  min-width: 0;
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.target-table-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.target-table-head h2 {
  margin: 0;
  color: var(--text);
  font-size: 14px;
  font-weight: 650;
}

.target-table-head p {
  margin: 4px 0 0;
  color: var(--text-dim);
  font-size: 11.5px;
}

.target-create {
  flex-shrink: 0;
  padding: 6px 12px;
  border: 1px solid var(--blue);
  border-radius: 7px;
  background: var(--blue);
  color: white;
  cursor: pointer;
  font: inherit;
  font-size: 11.5px;
  font-weight: 600;
}

.target-table-scroll {
  min-width: 0;
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: 9px;
}

.target-table {
  width: 100%;
  min-width: 820px;
  border-collapse: collapse;
  color: var(--text-dim);
  font-size: 11.5px;
}

.target-table th,
.target-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: middle;
}

.target-table th {
  background: var(--bg-inset);
  color: var(--text-faint);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.target-table tbody tr:last-child td {
  border-bottom: 0;
}

.kind-chip,
.state-chip {
  display: inline-flex;
  align-items: center;
  padding: 1px 7px;
  border: 1px solid var(--border-strong);
  border-radius: 999px;
  white-space: nowrap;
}

.kind-chip {
  color: var(--blue);
}

.state-chip {
  color: var(--text-faint);
}

.state-chip.enabled {
  color: var(--green);
  border-color: color-mix(in srgb, var(--green) 45%, var(--border));
}

.object-name {
  color: var(--text);
  font-weight: 600;
}

.repo-url {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mono {
  font-family: var(--mono);
}

.row-actions {
  display: flex;
  gap: 6px;
  white-space: nowrap;
}

.row-actions button {
  padding: 2px 6px;
  border: 0;
  background: transparent;
  color: var(--blue);
  cursor: pointer;
  font: inherit;
}

.row-actions .delete-target {
  color: var(--red);
}

@media (max-width: 640px) {
  .target-table-panel {
    padding: 12px;
  }

  .target-table-head {
    display: grid;
  }

  .target-create {
    width: fit-content;
  }
}
</style>
