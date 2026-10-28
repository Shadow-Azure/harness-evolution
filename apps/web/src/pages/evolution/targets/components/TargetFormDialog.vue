<script setup lang="ts">
import type {
  EvolutionTarget,
  EvolutionTargetWrite,
} from "@harness/contracts";
import { computed, reactive, watch } from "vue";

const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    target: EvolutionTarget | null;
    versions?: string[];
    versionsLoading?: boolean;
    versionsError?: boolean;
    submitting?: boolean;
    serverError?: string;
  }>(),
  {
    versions: () => [],
    versionsLoading: false,
    versionsError: false,
    submitting: false,
    serverError: "",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submit: [body: EvolutionTargetWrite];
}>();

type FormErrors = Partial<
  Record<"objectName" | "repoUrl" | "subDir" | "defaultRef", string>
>;

const form = reactive<EvolutionTargetWrite>({
  objectType: "skill",
  objectName: "",
  repoUrl: "",
  subDir: "",
  defaultRef: "",
  enabled: true,
});
const errors = reactive<FormErrors>({});

const title = computed(() => (props.target ? "编辑进化对象" : "新增进化对象"));
const versionOptions = computed(() => {
  const values = new Set(props.versions);
  if (props.target?.defaultRef) values.add(props.target.defaultRef);
  return [...values].sort((left, right) => left.localeCompare(right));
});
const targetRepoChanged = computed(
  () =>
    Boolean(props.target) &&
    form.repoUrl.trim() !== props.target?.repoUrl.trim(),
);
const versionHelp = computed(() => {
  if (!props.target) {
    return "可直接输入分支或 tag；保存后可基于已保存仓库选择标签。";
  }
  if (targetRepoChanged.value) {
    return "标签建议来自已保存配置；仓库地址保存后会重新读取。";
  }
  if (props.versionsLoading) return "正在读取仓库版本…";
  if (props.versionsError) {
    return "暂时无法获取标签建议，可直接输入分支或 tag。";
  }
  if (props.versions.length) {
    return "可从仓库标签中选择，也可直接输入分支或 tag。";
  }
  return "可直接输入分支或 tag。";
});

function resetForm(): void {
  form.objectType = props.target?.objectType ?? "skill";
  form.objectName = props.target?.objectName ?? "";
  form.repoUrl = props.target?.repoUrl ?? "";
  form.subDir = props.target?.subDir ?? "";
  form.defaultRef = props.target?.defaultRef ?? "";
  form.enabled = props.target?.enabled ?? true;
  clearErrors();
}

function clearErrors(): void {
  for (const key of Object.keys(errors) as (keyof FormErrors)[]) {
    delete errors[key];
  }
}

function close(): void {
  emit("update:modelValue", false);
}

function fetchVersionSuggestions(
  _query: string,
  callback: (suggestions: Array<{ value: string }>) => void,
): void {
  callback(
    versionOptions.value.map((value) => ({ value })),
  );
}

function clearDefaultRefError(): void {
  if (form.defaultRef.trim()) delete errors.defaultRef;
}

function submit(): void {
  clearErrors();
  const objectName = form.objectName.trim();
  const repoUrl = form.repoUrl.trim();
  const subDir = form.subDir.trim();
  const defaultRef = form.defaultRef.trim();
  if (!objectName) errors.objectName = "请填写对象名称";
  if (!repoUrl) errors.repoUrl = "请填写仓库地址";
  if (!subDir) errors.subDir = "请填写子目录";
  if (!defaultRef) errors.defaultRef = "请填写基线分支或标签";
  if (Object.keys(errors).length > 0) return;
  emit("submit", {
    objectType: form.objectType,
    objectName,
    repoUrl,
    subDir,
    defaultRef,
    enabled: form.enabled,
  });
}

watch(
  () => [props.modelValue, props.target] as const,
  ([open]) => {
    if (open) resetForm();
  },
  { immediate: true },
);
</script>

<template>
  <ElDialog
    class="target-form-dialog"
    body-class="target-dialog-body"
    footer-class="target-dialog-foot"
    header-class="target-dialog-head"
    :model-value="modelValue"
    :show-close="!submitting"
    :teleported="false"
    :title="title"
    width="min(720px, calc(100vw - 32px))"
    @close="close"
  >
    <form
      id="target-form"
      class="target-form"
      @submit.prevent="submit"
    >
      <ElForm label-position="top">
        <ElFormItem label="对象类型">
          <ElRadioGroup v-model="form.objectType">
            <ElRadioButton value="skill">
              Skill
            </ElRadioButton>
            <ElRadioButton value="agent">
              Agent
            </ElRadioButton>
          </ElRadioGroup>
        </ElFormItem>

        <ElFormItem label="对象名称">
          <ElInput
            v-model="form.objectName"
            maxlength="128"
            name="objectName"
            placeholder="如 deep-research"
          />
          <p
            v-if="errors.objectName"
            class="field-error"
          >
            {{ errors.objectName }}
          </p>
        </ElFormItem>

        <ElFormItem label="仓库地址">
          <ElInput
            v-model="form.repoUrl"
            maxlength="1024"
            name="repoUrl"
            placeholder="https://git.example.com/agent-skills.git"
          />
          <p class="field-help">
            仅填写无凭据的 HTTPS 或 SSH 地址，不要写入 token。
          </p>
          <p
            v-if="errors.repoUrl"
            class="field-error"
          >
            {{ errors.repoUrl }}
          </p>
        </ElFormItem>

        <div class="form-grid">
          <ElFormItem label="子目录">
            <ElInput
              v-model="form.subDir"
              maxlength="512"
              name="subDir"
              placeholder="skills/deep-research"
            />
            <p
              v-if="errors.subDir"
              class="field-error"
            >
              {{ errors.subDir }}
            </p>
          </ElFormItem>

          <ElFormItem label="基线分支或标签">
            <ElAutocomplete
              v-model="form.defaultRef"
              autocomplete="off"
              class="target-version-select"
              data-testid="target-version-select"
              :debounce="0"
              :fetch-suggestions="fetchVersionSuggestions"
              name="defaultRef"
              placeholder="main / v2.0.0"
              show-arrow
              trigger-on-focus
              @input="clearDefaultRefError"
              @select="clearDefaultRefError"
            />
            <p class="field-help">
              {{ versionHelp }}
            </p>
            <p
              v-if="errors.defaultRef"
              class="field-error"
            >
              {{ errors.defaultRef }}
            </p>
          </ElFormItem>
        </div>

        <ElFormItem label="启用">
          <div class="switch-row">
            <ElSwitch v-model="form.enabled" />
            <span>{{ form.enabled ? "进入启动向导候选" : "保留配置但不进入向导" }}</span>
          </div>
        </ElFormItem>
      </ElForm>

      <p
        v-if="serverError"
        class="server-error"
        role="alert"
      >
        {{ serverError }}
      </p>
    </form>

    <template #footer>
      <footer class="form-actions">
        <ElButton
          :disabled="submitting"
          @click="close"
        >
          取消
        </ElButton>
        <ElButton
          form="target-form"
          :loading="submitting"
          native-type="submit"
          type="primary"
        >
          {{ target ? "保存修改" : "新增配置" }}
        </ElButton>
      </footer>
    </template>
  </ElDialog>
</template>

<style scoped>
:global(.el-dialog.target-form-dialog) {
  overflow: hidden;
  border-radius: 14px;
}

:global(.target-form-dialog .target-dialog-head) {
  margin-right: 0;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
}

:global(.target-form-dialog .target-dialog-head .el-dialog__title) {
  font-size: 15px;
  font-weight: 700;
}

:global(.target-form-dialog .target-dialog-body) {
  padding: 18px;
  max-height: 66vh;
  overflow-y: auto;
}

:global(.target-form-dialog .target-dialog-foot) {
  padding: 13px 18px;
  border-top: 1px solid var(--border);
  background: var(--bg-panel);
}

.target-form {
  display: grid;
  gap: 12px;
}

.form-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 0.8fr);
  gap: 12px;
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

.switch-row {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-dim);
  font-size: 11.5px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 640px) {
  .form-grid {
    grid-template-columns: 1fr;
    gap: 0;
  }
}
</style>
