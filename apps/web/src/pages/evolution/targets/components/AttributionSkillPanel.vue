<script setup lang="ts">
import type { EvolutionTarget } from "@harness/contracts";
import { ElMessage } from "element-plus/es/components/message/index";
import { computed, ref, watch } from "vue";

import { formatApiError } from "../../../../app/apiError";
import { useAttributionSkills } from "../../../../composables/useAttributionSkills";
import EmptyState from "../../../../components/ui/EmptyState.vue";
import ErrorState from "../../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../../components/ui/LoadingSkeleton.vue";

const props = defineProps<{
  workspaceId: string;
  targets: EvolutionTarget[];
  canWrite: boolean;
}>();

const selectedTargetId = ref("");
const selectedRevisionId = ref("");
const operationError = ref("");

watch(
  () => props.targets,
  (targets) => {
    if (targets.some((target) => target.id === selectedTargetId.value)) return;
    selectedTargetId.value = targets[0]?.id ?? "";
  },
  { immediate: true },
);

const { bindTarget, effective, isMutating, skills, useDefault } =
  useAttributionSkills(
    computed(() => props.workspaceId),
    selectedTargetId,
  );

const revisions = computed(() =>
  (skills.data.value?.items ?? []).filter(
    (item) =>
      item.enabled &&
      item.status === "published" &&
      item.outputSchemaVersion === "probe-report/v2" &&
      item.executorType !== "agent",
  ),
);

watch(
  () => effective.data.value?.id,
  (revisionId) => {
    selectedRevisionId.value = revisionId ?? "";
  },
  { immediate: true },
);

watch(selectedTargetId, () => {
  operationError.value = "";
});

const loading = computed(
  () => skills.isPending.value || effective.isPending.value,
);
const readError = computed(
  () => skills.error.value ?? effective.error.value,
);
const current = computed(() => effective.data.value ?? null);
const sourceLabel = computed(() => {
  switch (current.value?.source) {
    case "target":
      return "对象覆盖";
    case "workspace":
      return "空间默认";
    case "platform":
      return "平台默认";
    default:
      return "未解析";
  }
});
const selectedIsCurrentOverride = computed(
  () =>
    current.value?.source === "target" &&
    selectedRevisionId.value === current.value.id,
);

function shortHash(value: string): string {
  return value.slice(0, 12);
}

async function bindRevision(): Promise<void> {
  if (!selectedRevisionId.value || !selectedTargetId.value) return;
  operationError.value = "";
  try {
    await bindTarget(selectedRevisionId.value);
    ElMessage.success("归因 Skill 已绑定到对象");
  } catch (error) {
    operationError.value = formatApiError(
      error,
      "绑定归因 Skill 失败",
    ).message;
  }
}

async function restoreDefault(): Promise<void> {
  if (!selectedTargetId.value) return;
  operationError.value = "";
  try {
    await useDefault();
    ElMessage.success("已恢复空间或平台默认 Skill");
  } catch (error) {
    operationError.value = formatApiError(
      error,
      "恢复默认归因 Skill 失败",
    ).message;
  }
}

function retryReads(): void {
  void skills.refetch();
  void effective.refetch();
}
</script>

<template>
  <section
    class="skill-panel"
    aria-labelledby="attribution-skill-title"
    data-testid="attribution-skill-panel"
  >
    <header class="panel-head">
      <div>
        <h2 id="attribution-skill-title">
          归因 Skill
        </h2>
        <p>选择已发布 revision；新 Run 固化当前结果，历史 Run 不随绑定变化。</p>
      </div>
      <label
        v-if="targets.length"
        class="target-picker"
      >
        <span>进化对象</span>
        <select
          v-model="selectedTargetId"
          data-testid="skill-target-select"
        >
          <option
            v-for="target in targets"
            :key="target.id"
            :value="target.id"
          >
            {{ target.objectType }} · {{ target.objectName }}
          </option>
        </select>
      </label>
    </header>

    <EmptyState
      v-if="targets.length === 0"
      description="新增进化对象后可配置它使用的归因 Skill。"
      title="暂无可绑定对象"
    />
    <LoadingSkeleton
      v-else-if="loading"
      label="正在解析归因 Skill"
      :rows="2"
    />
    <ErrorState
      v-else-if="readError"
      code="ATTRIBUTION_SKILL_UNAVAILABLE"
      message="归因 Skill 读取失败，请重试。"
      @retry="retryReads"
    />
    <template v-else-if="current">
      <div class="effective-card">
        <div>
          <span
            class="source-chip"
            :class="current.source"
          >{{ sourceLabel }}</span>
          <strong>{{ current.displayName }}</strong>
          <span class="mono">{{ current.skillKey }}@r{{ current.revision }}</span>
        </div>
        <div class="skill-meta">
          <span>{{ current.executorType }}</span>
          <span
            class="mono"
            :title="current.contentHash"
          >sha256:{{ shortHash(current.contentHash) }}</span>
          <span>{{ current.outputSchemaVersion }}</span>
        </div>
        <p>{{ current.description || "该 revision 未填写说明。" }}</p>
      </div>

      <div
        v-if="canWrite"
        class="binding-controls"
      >
        <label>
          <span>绑定 revision</span>
          <select
            v-model="selectedRevisionId"
            data-testid="skill-revision-select"
          >
            <option
              v-for="revision in revisions"
              :key="revision.id"
              :value="revision.id"
            >
              {{ revision.displayName }} · r{{ revision.revision }} · {{ revision.executorType }}
            </option>
          </select>
        </label>
        <button
          class="bind-skill"
          type="button"
          :disabled="isMutating || !selectedRevisionId || selectedIsCurrentOverride"
          @click="bindRevision"
        >
          {{ isMutating ? "保存中…" : "绑定到对象" }}
        </button>
        <button
          class="restore-default"
          type="button"
          :disabled="isMutating || current.source !== 'target'"
          @click="restoreDefault"
        >
          使用默认
        </button>
      </div>
      <p
        v-else
        class="read-only-note"
      >
        仅空间管理员可修改绑定。
      </p>
      <p
        v-if="operationError"
        class="operation-error"
        role="alert"
      >
        {{ operationError }}
      </p>
    </template>
  </section>
</template>

<style scoped>
.skill-panel {
  display: grid;
  min-width: 0;
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.panel-head,
.binding-controls,
.effective-card > div {
  display: flex;
  align-items: center;
  gap: 10px;
}

.panel-head {
  justify-content: space-between;
  align-items: flex-start;
}

h2 {
  margin: 0;
  color: var(--text);
  font-size: 14px;
}

.panel-head p,
.effective-card p,
.read-only-note {
  margin: 4px 0 0;
  color: var(--text-dim);
  font-size: 11.5px;
}

.target-picker,
.binding-controls label {
  display: grid;
  gap: 5px;
  color: var(--text-faint);
  font-size: 10px;
  font-weight: 650;
}

select {
  min-width: 220px;
  padding: 7px 9px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-inset);
  color: var(--text);
  font: inherit;
  font-size: 11.5px;
}

.effective-card {
  display: grid;
  gap: 7px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-inset);
}

.effective-card strong {
  color: var(--text);
  font-size: 12.5px;
}

.effective-card .mono,
.skill-meta {
  color: var(--text-dim);
  font-size: 10.5px;
}

.skill-meta {
  flex-wrap: wrap;
}

.source-chip {
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-dim);
  font-size: 10px;
}

.source-chip.target {
  border-color: color-mix(in srgb, var(--blue) 45%, var(--border));
  color: var(--blue);
}

.binding-controls {
  flex-wrap: wrap;
  align-items: flex-end;
}

.binding-controls button {
  padding: 7px 11px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-card);
  color: var(--text-dim);
  cursor: pointer;
  font: inherit;
  font-size: 11px;
}

.binding-controls .bind-skill {
  border-color: var(--blue);
  background: var(--blue);
  color: white;
}

.binding-controls button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.operation-error {
  margin: 0;
  color: var(--red);
  font-size: 11.5px;
}

@media (max-width: 760px) {
  .panel-head {
    display: grid;
  }

  select,
  .target-picker {
    width: 100%;
  }
}
</style>
