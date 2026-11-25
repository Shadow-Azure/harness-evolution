<script setup lang="ts">
import { ElMessage } from "element-plus/es/components/message/index";
import { computed, ref, watch } from "vue";

import ErrorState from "../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import {
  useReplaceWorkspaceBadCaseLabels,
  useWorkspaceBadCaseLabels,
} from "../../../composables/useWorkspaces";

const LABEL_MAX_LENGTH = 128;

const props = defineProps<{
  workspaceId: string;
  canManage: boolean;
}>();

const labelsQuery = useWorkspaceBadCaseLabels(() => props.workspaceId);
const mutation = useReplaceWorkspaceBadCaseLabels(() => props.workspaceId);

const savedItems = computed<string[]>(() => labelsQuery.data.value?.items ?? []);
const assignedCount = computed(
  () => labelsQuery.data.value?.assignedBadCaseCount ?? 0,
);

const draft = ref<string[]>([]);
const inputValue = ref("");
const inputError = ref("");
const operationError = ref("");

// Reconcile the local draft once the server snapshot arrives, but keep any
// in-flight edits when the query refreshes in the background.
let syncedFromServer = false;
watch(
  savedItems,
  (items) => {
    if (!syncedFromServer) {
      draft.value = [...items];
      syncedFromServer = true;
    }
  },
  { immediate: true },
);

const isDirty = computed(
  () => draft.value.join("\u0000") !== savedItems.value.join("\u0000"),
);

/**
 * Validate one label and return the public Chinese message, or empty when valid.
 * @param value Raw label text.
 * @param existing Already-accepted labels for duplicate detection.
 * @returns Error copy, or an empty string when the label may be added.
 */
function validateLabel(value: string, existing: string[]): string {
  const trimmed = value.trim();
  if (!trimmed) return "label 不能为空。";
  if (trimmed !== value) return "label 首尾不能有空白。";
  if (trimmed.length > LABEL_MAX_LENGTH) {
    return `label 最多 ${LABEL_MAX_LENGTH} 个字符。`;
  }
  if (existing.includes(trimmed)) return "该 label 已经添加。";
  return "";
}

/**
 * Add the current input as a label after validation, keeping lexical order.
 * @returns No value.
 */
function addLabel(): void {
  inputError.value = validateLabel(inputValue.value, draft.value);
  if (inputError.value) return;
  draft.value = [...draft.value, inputValue.value.trim()].sort();
  inputValue.value = "";
}

/**
 * Remove one label from the pending draft.
 * @param label Label to remove.
 * @returns No value.
 */
function removeLabel(label: string): void {
  draft.value = draft.value.filter((item) => item !== label);
}

/**
 * Persist the pending draft as a full replacement and refresh the read boundary.
 * @returns No value.
 */
async function saveLabels(): Promise<void> {
  if (!props.canManage) return;
  operationError.value = "";
  try {
    await mutation.replaceLabels({ items: [...draft.value] });
    ElMessage.success("Badcase 类型已保存，历史数据已重新划分");
  } catch (error) {
    operationError.value = labelErrorMessage(error);
  }
}

/**
 * Map label mutation failures onto actionable Chinese copy.
 * @param error Unknown mutation failure.
 * @returns User-facing message.
 */
function labelErrorMessage(error: unknown): string {
  if (error && typeof error === "object" && "code" in error) {
    const code = String(error.code);
    if (code === "WORKSPACE_FORBIDDEN") return "当前角色没有配置 Badcase 类型的权限。";
    if (code === "VALIDATION_INVALID") return "label 不合法：需为 1–128 字符且首尾无空白。";
  }
  return "保存失败，请稍后重试。";
}
</script>

<template>
  <div data-testid="bad-case-labels-tab">
    <div class="admin-head">
      <div>
        <h2>Badcase 类型</h2>
        <p class="sub">
          选择当前空间从公共仓库接收的 badcase 大类型；未配置时公共 badcase 不会进入当前空间。
        </p>
      </div>
      <div
        v-if="canManage"
        class="actions"
      >
        <button
          class="btn primary"
          data-testid="save-bad-case-labels"
          :disabled="!isDirty || mutation.isPending.value"
          type="button"
          @click="saveLabels"
        >
          {{ mutation.isPending.value ? "保存中…" : "保存配置" }}
        </button>
      </div>
    </div>

    <p
      v-if="operationError"
      class="operation-error"
      role="alert"
      data-testid="bad-case-labels-operation-error"
    >
      {{ operationError }}
    </p>

    <LoadingSkeleton
      v-if="labelsQuery.isPending.value"
      label="正在读取 Badcase 类型"
      :rows="2"
    />
    <ErrorState
      v-else-if="labelsQuery.error.value"
      code="BAD_CASE_LABELS_UNAVAILABLE"
      message="Badcase 类型读取失败，请重试。"
      @retry="labelsQuery.refetch"
    />
    <div
      v-else
      class="ingest-card"
    >
      <h3>已配置 label <span class="badge">{{ savedItems.length }} 个</span></h3>

      <div
        v-if="draft.length === 0"
        class="empty-chips"
        data-testid="no-bad-case-labels"
      >
        还没有配置 label。未配置时，公共 badcase 不会进入当前空间。
      </div>
      <div
        v-else
        class="chip-list"
        data-testid="bad-case-label-chips"
      >
        <span
          v-for="label in draft"
          :key="label"
          class="chip"
          :data-testid="`bad-case-label-${label}`"
        >
          {{ label }}
          <button
            v-if="canManage"
            class="chip-remove"
            type="button"
            :aria-label="`移除 ${label}`"
            @click="removeLabel(label)"
          >
            ×
          </button>
        </span>
      </div>

      <div
        v-if="canManage"
        class="add-row"
      >
        <input
          v-model="inputValue"
          class="label-input"
          type="text"
          :maxlength="LABEL_MAX_LENGTH + 1"
          placeholder="输入 label"
          data-testid="bad-case-label-input"
          @keyup.enter="addLabel"
        >
        <button
          class="btn"
          type="button"
          data-testid="add-bad-case-label"
          @click="addLabel"
        >
          添加
        </button>
      </div>
      <p
        v-if="inputError"
        class="input-error"
        role="alert"
        data-testid="bad-case-label-input-error"
      >
        {{ inputError }}
      </p>

      <div class="rule-row">
        <div>
          <p class="rule-title">
            当前划分
          </p>
          <p
            class="rule-count"
            data-testid="bad-case-label-assigned-count"
          >
            已关联 {{ assignedCount }} 条
          </p>
        </div>
        <p
          v-if="isDirty"
          class="dirty-hint"
          data-testid="bad-case-label-dirty"
        >
          有未保存更改
        </p>
      </div>

      <p class="field-help">
        label 区分大小写、精确匹配；同一 label 可配置给多个空间，一条公共 badcase 会同时进入所有匹配空间。
      </p>
    </div>
  </div>
</template>

<style scoped>
.admin-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.admin-head h2 {
  margin: 0;
  color: var(--text);
  font-size: 15px;
  font-weight: 650;
}

.admin-head .sub {
  margin: 2px 0 0;
  color: var(--text-faint);
  font-size: 11px;
  line-height: 1.6;
}

.admin-head .actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
  margin-left: auto;
}

.operation-error {
  margin: 0 0 10px;
  padding: 8px 10px;
  border: 1px solid color-mix(in srgb, var(--red) 35%, var(--border));
  border-radius: 8px;
  background: color-mix(in srgb, var(--red) 6%, var(--bg-card));
  color: var(--red);
  font-size: 11px;
}

.ingest-card {
  padding: 12px 13px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-panel);
}

.ingest-card h3 {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0 0 8px;
  color: var(--text-dim);
  font-size: 11.5px;
  font-weight: 650;
}

.empty-chips {
  padding: 14px;
  border: 1px dashed var(--border);
  border-radius: 8px;
  color: var(--text-faint);
  font-size: 11px;
}

.chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 8px;
  border: 1px solid color-mix(in srgb, var(--blue) 30%, var(--border));
  border-radius: 999px;
  background: color-mix(in srgb, var(--blue) 7%, var(--bg-card));
  color: var(--blue);
  font-size: 11px;
}

.chip-remove {
  padding: 0 2px;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  line-height: 1;
}

.add-row {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.label-input {
  flex: 1;
  min-width: 0;
  padding: 5px 9px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-card);
  color: var(--text);
  font: inherit;
  font-size: 12px;
}

.label-input:focus {
  outline: none;
  border-color: var(--blue);
}

.input-error {
  margin: 6px 0 0;
  color: var(--red);
  font-size: 10.5px;
}

.rule-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}

.rule-title {
  margin: 0;
  color: var(--text-faint);
  font-size: 10px;
  font-weight: 650;
}

.rule-count {
  margin: 2px 0 0;
  color: var(--text);
  font-family: var(--mono);
  font-size: 13px;
  font-weight: 650;
}

.dirty-hint {
  margin: 0;
  color: var(--orange);
  font-size: 10.5px;
}

.field-help {
  margin: 10px 0 0;
  color: var(--text-faint);
  font-size: 10.5px;
  line-height: 1.6;
}

.badge {
  padding: 0 7px;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-faint);
  font-size: 9.5px;
  font-weight: 400;
  white-space: nowrap;
}

.btn {
  padding: 5px 11px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-card);
  color: var(--text-dim);
  cursor: pointer;
  font: inherit;
  font-size: 11.5px;
  white-space: nowrap;
}

.btn:hover {
  border-color: var(--border-strong);
  color: var(--text);
}

.btn.primary {
  border-color: var(--blue);
  background: var(--blue);
  color: white;
  font-weight: 600;
}

.btn.primary:hover {
  background: var(--blue-deep);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
