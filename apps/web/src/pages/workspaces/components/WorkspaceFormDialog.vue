<script setup lang="ts">
import type {
  PublicUser,
  Workspace,
  WorkspaceCreateRequest,
  WorkspaceUpdateRequest,
} from "@harness/contracts";
import { computed, reactive, ref, watch } from "vue";

const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    workspace: Workspace | null;
    users?: PublicUser[];
    currentUserId: string;
    submitting?: boolean;
    serverError?: string;
  }>(),
  {
    users: () => [],
    submitting: false,
    serverError: "",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submit: [body: WorkspaceCreateRequest | WorkspaceUpdateRequest];
}>();

const editing = computed(() => props.workspace !== null);
const title = computed(() =>
  editing.value ? "调整工作空间额度" : "创建工作空间",
);
const used = computed(() => props.workspace?.used ?? 0);
const quotaInput = ref("100");
const name = ref("");
const mark = ref("");
const selectedAdminIds = ref<string[]>([]);
const fieldErrors = reactive<Record<string, string>>({});

const selectableUsers = computed(() =>
  [...props.users].sort((left, right) =>
    left.displayName.localeCompare(right.displayName, "zh-CN"),
  ),
);

function resetForm(): void {
  name.value = props.workspace?.name ?? "";
  mark.value = props.workspace?.mark ?? "";
  quotaInput.value = String(props.workspace?.quota ?? 100);
  selectedAdminIds.value = props.currentUserId ? [props.currentUserId] : [];
  clearErrors();
}

function clearErrors(): void {
  for (const key of Object.keys(fieldErrors)) {
    delete fieldErrors[key];
  }
}

function close(): void {
  if (props.submitting) return;
  emit("update:modelValue", false);
}

function toggleAdmin(userId: string, checked: boolean): void {
  const next = new Set(selectedAdminIds.value);
  if (checked) next.add(userId);
  else next.delete(userId);
  selectedAdminIds.value = [...next];
  if (next.size > 0) delete fieldErrors.spaceAdminIds;
}

/**
 * Validate local fields and emit the workspace payload.
 * @returns No value.
 */
function submit(): void {
  clearErrors();
  const trimmedName = name.value.trim();
  const trimmedMark = mark.value.trim();
  const quota = Number(quotaInput.value);
  if (!editing.value && !trimmedName) {
    fieldErrors.name = "请填写空间名称";
  }
  if (!Number.isInteger(quota) || quota < 0) {
    fieldErrors.quota = "额度必须为非负整数";
  } else if (editing.value && quota < used.value) {
    fieldErrors.quota = `额度不能低于当前已上报的 ${used.value} 条`;
  }
  if (!editing.value && selectedAdminIds.value.length === 0) {
    fieldErrors.spaceAdminIds = "请至少选择一名初始空间管理员";
  }
  if (Object.keys(fieldErrors).length > 0) {
    return;
  }
  if (editing.value) {
    emit("submit", { quota });
    return;
  }
  emit("submit", {
    name: trimmedName,
    mark: trimmedMark,
    quota,
    spaceAdminIds: [...selectedAdminIds.value],
  });
}

watch(
  () => [props.modelValue, props.workspace] as const,
  ([open]) => {
    if (open) resetForm();
  },
  { immediate: true },
);
</script>

<template>
  <ElDialog
    class="workspace-form-dialog"
    body-class="workspace-dialog-body"
    :close-on-click-modal="!submitting"
    footer-class="workspace-dialog-foot"
    header-class="workspace-dialog-head"
    :model-value="modelValue"
    :show-close="!submitting"
    :teleported="false"
    :title="title"
    width="min(560px, calc(100vw - 32px))"
    @close="close"
  >
    <form
      id="workspace-form"
      class="workspace-form"
      @submit.prevent="submit"
    >
      <ElForm label-position="top">
        <template v-if="editing">
          <ElFormItem label="工作空间">
            <span class="workspace-name">{{ workspace?.name }}</span>
            <p class="field-help">
              当前已上报 {{ used }} 条 bad case；额度不会清空已有数据。
            </p>
          </ElFormItem>
        </template>
        <template v-else>
          <ElFormItem label="空间名称">
            <ElInput
              v-model="name"
              data-testid="workspace-name-input"
              maxlength="128"
              name="workspaceName"
              placeholder="例如：客服 Copilot"
            />
            <p
              v-if="fieldErrors.name"
              class="field-error"
            >
              {{ fieldErrors.name }}
            </p>
          </ElFormItem>

          <ElFormItem label="空间标识">
            <ElInput
              v-model="mark"
              data-testid="workspace-mark-input"
              maxlength="255"
              name="workspaceMark"
              placeholder="例如：HC（用于空间卡片的短标记）"
            />
            <p class="field-help">
              可选；留空时按空间名称生成短标记。
            </p>
          </ElFormItem>
        </template>

        <ElFormItem label="bad case 数量上限">
          <ElInput
            v-model="quotaInput"
            data-testid="workspace-quota-input"
            min="0"
            name="workspaceQuota"
            style="width: 180px"
            type="number"
          />
          <p class="field-help">
            创建后可随时调整；不能小于已上报数量（当前 {{ used }}）。
          </p>
          <p
            v-if="fieldErrors.quota"
            class="field-error"
          >
            {{ fieldErrors.quota }}
          </p>
        </ElFormItem>

        <ElFormItem
          v-if="!editing"
          label="初始空间管理员"
        >
          <div
            class="admin-picker"
            data-testid="workspace-admin-picker"
          >
            <label
              v-for="user in selectableUsers"
              :key="user.id"
              class="switch-row"
            >
              <input
                :checked="selectedAdminIds.includes(user.id)"
                :data-testid="`workspace-admin-option-${user.id}`"
                type="checkbox"
                :value="user.id"
                @change="toggleAdmin(user.id, ($event.target as HTMLInputElement).checked)"
              >
              <span>
                {{ user.displayName }}
                <span class="user-name">{{ user.username }}</span>
              </span>
            </label>
            <p
              v-if="selectableUsers.length === 0"
              class="field-help"
            >
              暂无可选用户。
            </p>
          </div>
          <p class="field-help">
            管理员可以把自己加入空间并任命为空间管理员；一个空间允许多个管理员。
          </p>
          <p
            v-if="fieldErrors.spaceAdminIds"
            class="field-error"
          >
            {{ fieldErrors.spaceAdminIds }}
          </p>
        </ElFormItem>
      </ElForm>

      <p
        v-if="serverError"
        class="server-error"
        role="alert"
        data-testid="workspace-form-error"
      >
        {{ serverError }}
      </p>
    </form>

    <template #footer>
      <footer class="form-actions">
        <button
          class="btn"
          :disabled="submitting"
          type="button"
          @click="close"
        >
          取消
        </button>
        <button
          class="btn primary"
          data-testid="workspace-form-submit"
          :disabled="submitting"
          form="workspace-form"
          type="submit"
        >
          {{ submitting ? "保存中…" : editing ? "保存额度" : "创建工作空间" }}
        </button>
      </footer>
    </template>
  </ElDialog>
</template>

<style scoped>
:global(.el-dialog.workspace-form-dialog) {
  overflow: hidden;
  border-radius: 14px;
}

:global(.workspace-form-dialog .workspace-dialog-head) {
  margin-right: 0;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
}

:global(.workspace-form-dialog .workspace-dialog-head .el-dialog__title) {
  font-size: 15px;
  font-weight: 700;
}

:global(.workspace-form-dialog .workspace-dialog-body) {
  padding: 18px;
  max-height: 66vh;
  overflow-y: auto;
}

:global(.workspace-form-dialog .workspace-dialog-foot) {
  padding: 13px 18px;
  border-top: 1px solid var(--border);
  background: var(--bg-panel);
}

.workspace-form {
  display: grid;
  gap: 12px;
}

.workspace-name {
  color: var(--text);
  font-size: 13px;
  font-weight: 600;
}

.field-help,
.field-error {
  margin: 4px 0 0;
  font-size: 10.5px;
  line-height: 1.5;
}

.field-help {
  color: var(--text-faint);
}

.field-error,
.server-error {
  color: var(--red);
}

.server-error {
  margin: 0;
  padding: 9px 11px;
  border: 1px solid color-mix(in srgb, var(--red) 35%, var(--border));
  border-radius: 8px;
  background: color-mix(in srgb, var(--red) 6%, var(--bg-card));
  font-size: 11.5px;
}

.admin-picker {
  display: grid;
  max-height: 168px;
  width: 100%;
  gap: 2px;
  padding: 8px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-panel);
}

.switch-row {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 3px 2px;
  color: var(--text-dim);
  font-size: 11.5px;
  cursor: pointer;
}

.switch-row input {
  accent-color: var(--blue);
}

.user-name {
  margin-left: 4px;
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 10px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.btn {
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-card);
  color: var(--text-dim);
  cursor: pointer;
  font: inherit;
  font-size: 11.5px;
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
  cursor: not-allowed;
  opacity: 0.65;
}
</style>
