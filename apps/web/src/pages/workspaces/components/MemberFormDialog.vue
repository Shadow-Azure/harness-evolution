<script setup lang="ts">
import type {
  WorkspaceMemberCreateRequest,
  WorkspaceMemberRole,
} from "@harness/contracts";
import { computed, onBeforeUnmount, ref, watch } from "vue";

import { useMemberCandidates } from "../../../composables/useWorkspaces";

const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    workspaceId: string;
    workspaceName?: string;
    canGrantSpaceAdmin?: boolean;
    submitting?: boolean;
    serverError?: string;
  }>(),
  {
    workspaceName: "",
    canGrantSpaceAdmin: false,
    submitting: false,
    serverError: "",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submit: [body: WorkspaceMemberCreateRequest];
}>();

const search = ref("");
const debouncedSearch = ref("");
const selectedUserId = ref("");
const role = ref<WorkspaceMemberRole>("member");
const localError = ref("");
let searchTimer: ReturnType<typeof setTimeout> | undefined;

const candidatesQuery = useMemberCandidates(
  () => props.workspaceId,
  debouncedSearch,
  () => props.modelValue,
);
const candidates = computed(
  () => candidatesQuery.data.value?.items ?? [],
);
const loading = computed(
  () => props.modelValue && candidatesQuery.isFetching.value,
);
const roleOptions = computed<Array<{ value: WorkspaceMemberRole; label: string }>>(
  () => [
    ...(props.canGrantSpaceAdmin
      ? [{ value: "space_admin" as const, label: "空间管理员" }]
      : []),
    { value: "member", label: "成员" },
    { value: "viewer", label: "只读成员" },
  ],
);

function close(): void {
  if (props.submitting) return;
  emit("update:modelValue", false);
}

function onSearchInput(value: string): void {
  search.value = value;
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    debouncedSearch.value = value.trim();
  }, 250);
}

function submit(): void {
  localError.value = "";
  if (!selectedUserId.value) {
    localError.value = "请选择要添加的用户";
    return;
  }
  emit("submit", {
    userId: selectedUserId.value,
    role: role.value,
  });
}

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    search.value = "";
    debouncedSearch.value = "";
    selectedUserId.value = "";
    role.value = "member";
    localError.value = "";
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer);
});
</script>

<template>
  <ElDialog
    class="member-form-dialog"
    body-class="member-dialog-body"
    :close-on-click-modal="!submitting"
    footer-class="member-dialog-foot"
    header-class="member-dialog-head"
    :model-value="modelValue"
    :show-close="!submitting"
    :teleported="false"
    title="添加成员"
    width="min(520px, calc(100vw - 32px))"
    @close="close"
  >
    <form
      id="member-form"
      class="member-form"
      @submit.prevent="submit"
    >
      <ElForm label-position="top">
        <ElFormItem label="搜索用户">
          <ElInput
            :model-value="search"
            data-testid="member-search-input"
            name="memberSearch"
            placeholder="输入用户名或显示名搜索非成员账号"
            @update:model-value="onSearchInput"
          />
          <p class="field-help">
            只搜索尚未加入空间的账号；服务端不会返回全局用户目录。
          </p>
        </ElFormItem>

        <ElFormItem label="用户">
          <ElSelect
            v-model="selectedUserId"
            data-testid="member-candidate-select"
            :loading="loading"
            placeholder="选择一个用户"
            style="width: 100%"
          >
            <ElOption
              v-for="candidate in candidates"
              :key="candidate.id"
              :label="`${candidate.displayName} · ${candidate.username}`"
              :value="candidate.id"
            />
          </ElSelect>
          <p
            v-if="!loading && candidates.length === 0"
            class="field-help"
            data-testid="member-candidates-empty"
          >
            没有可添加的用户；所有账号都已在该空间中。
          </p>
        </ElFormItem>

        <ElFormItem label="空间角色">
          <ElSelect
            v-model="role"
            data-testid="member-role-select"
            style="width: 100%"
          >
            <ElOption
              v-for="option in roleOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </ElSelect>
          <p class="field-help">
            {{
              canGrantSpaceAdmin
                ? "全局管理员可以任命空间管理员。"
                : "空间管理员只能授予管理员以下的权限。"
            }}
          </p>
        </ElFormItem>
      </ElForm>

      <p class="notice">
        添加后该用户可在顶栏切换到 {{ workspaceName || "当前空间" }}；成员默认不能管理空间。
      </p>
      <p
        v-if="localError || serverError"
        class="server-error"
        role="alert"
        data-testid="member-form-error"
      >
        {{ localError || serverError }}
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
          :disabled="submitting"
          form="member-form"
          type="submit"
        >
          {{ submitting ? "添加中…" : "添加成员" }}
        </button>
      </footer>
    </template>
  </ElDialog>
</template>

<style scoped>
:global(.el-dialog.member-form-dialog) {
  overflow: hidden;
  border-radius: 14px;
}

:global(.member-form-dialog .member-dialog-head) {
  margin-right: 0;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
}

:global(.member-form-dialog .member-dialog-head .el-dialog__title) {
  font-size: 15px;
  font-weight: 700;
}

:global(.member-form-dialog .member-dialog-body) {
  padding: 18px;
}

:global(.member-form-dialog .member-dialog-foot) {
  padding: 13px 18px;
  border-top: 1px solid var(--border);
  background: var(--bg-panel);
}

.member-form {
  display: grid;
  gap: 12px;
}

.field-help,
.server-error {
  margin: 4px 0 0;
  font-size: 10.5px;
  line-height: 1.5;
}

.field-help {
  color: var(--text-faint);
}

.notice {
  margin: 0;
  padding: 9px 11px;
  border: 1px solid color-mix(in srgb, var(--blue) 22%, var(--border));
  border-radius: 8px;
  background: color-mix(in srgb, var(--blue) 5%, var(--bg-card));
  color: var(--text-dim);
  font-size: 10.5px;
  line-height: 1.55;
}

.server-error {
  color: var(--red);
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
