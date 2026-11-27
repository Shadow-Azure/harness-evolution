<script setup lang="ts">
import type {
  EvolutionTarget,
  EvolutionTargetWrite,
} from "@harness/contracts";
import { computed, nextTick, reactive, ref, watch } from "vue";

import type {
  TargetMemberFieldName,
  TargetServerError,
  TargetTopField,
} from "../targetErrors";
import {
  targetMembers,
  type TargetMember,
} from "../targetMembers";

const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    target: EvolutionTarget | null;
    packages?: {id: string; skillName: string}[];
    runtimeEnabled?: boolean;
    packagesLoading?: boolean;
    versions?: string[];
    versionsLoading?: boolean;
    versionsError?: boolean;
    submitting?: boolean;
    serverError?: TargetServerError | null;
  }>(),
  {
    packages: () => [],
    runtimeEnabled: undefined,
    packagesLoading: false,
    versions: () => [],
    versionsLoading: false,
    versionsError: false,
    submitting: false,
    serverError: () => ({ summary: "" }),
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submit: [body: EvolutionTargetWrite];
}>();

type FormErrors = Partial<Record<TargetTopField, string>>;

type MemberErrors = Record<
  number,
  Partial<Record<TargetMemberFieldName, string>>
>;

interface MemberDraft extends TargetMember {
  key: number;
}

const PROJECT_ID_INVALID = (value: string): boolean =>
  Array.from(value).some((character) => {
    const code = character.codePointAt(0) ?? 0;
    return /\s/u.test(character) || code <= 0x1f || code === 0x7f;
  });

const form = reactive({
  repoUrl: "",
  defaultRef: "",
  validationProjectId: "",
  testProjectId: "",
  primaryMetricKey: "",
  attributionPackageId: null as string | null,
  enabled: true,
});
const members = ref<MemberDraft[]>([]);
const errors = reactive<FormErrors>({});
const memberErrors = reactive<MemberErrors>({});
const memberListError = ref("");
const versionAutocomplete = ref<{ focus: () => void } | null>(null);
const formElement = ref<HTMLFormElement | null>(null);
const serverErrorDismissed = ref(false);
const visibleServerError = computed<TargetServerError | null>(() => {
  const value = serverErrorDismissed.value
    ? null
    : (props.serverError ?? null);
  return value?.summary ? value : null;
});

const unboundLabel = computed(() => {
  if (props.target) return props.target.attributionPackageId ? null : props.target.attributionSkillName ?? "未绑定";
  return props.runtimeEnabled ? null : "未绑定 · 使用内置归因规则";
});
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

function serverErrorFor(field: TargetTopField): TargetServerError | null {
  return visibleServerError.value?.field === field
    ? visibleServerError.value
    : null;
}

function hasFieldError(field: TargetTopField): boolean {
  return Boolean(errors[field] || serverErrorFor(field));
}

function fieldMessage(field: TargetTopField): string {
  return serverErrorFor(field)?.message ?? errors[field] ?? "";
}

function fieldSuggestion(field: TargetTopField): string {
  return serverErrorFor(field)?.suggestion ?? "";
}

function fieldAriaInvalid(field: TargetTopField): "true" | undefined {
  return hasFieldError(field) ? "true" : undefined;
}

function fieldDescribedBy(field: TargetTopField): string | undefined {
  return hasFieldError(field) ? `target-${field}-error` : undefined;
}

function onFieldInput(field: TargetTopField, value: string): void {
  if (value.trim()) delete errors[field];
  if (serverErrorFor(field)) serverErrorDismissed.value = true;
}

function memberFieldPath(
  index: number,
  field: TargetMemberFieldName,
): string {
  return `members[${index}].${field}`;
}

function memberErrorId(
  index: number,
  field: TargetMemberFieldName,
): string {
  return `target-members-${index}-${field}-error`;
}

function memberServerError(
  index: number,
  field: TargetMemberFieldName,
): TargetServerError | null {
  const value = visibleServerError.value;
  return value?.field === memberFieldPath(index, field) ? value : null;
}

function hasMemberError(
  index: number,
  field: TargetMemberFieldName,
): boolean {
  return Boolean(memberErrors[index]?.[field] || memberServerError(index, field));
}

function memberMessage(
  index: number,
  field: TargetMemberFieldName,
): string {
  return memberServerError(index, field)?.message
    ?? memberErrors[index]?.[field]
    ?? "";
}

function memberSuggestion(
  index: number,
  field: TargetMemberFieldName,
): string {
  return memberServerError(index, field)?.suggestion ?? "";
}

function memberAriaInvalid(
  index: number,
  field: TargetMemberFieldName,
): "true" | undefined {
  return hasMemberError(index, field) ? "true" : undefined;
}

function memberDescribedBy(
  index: number,
  field: TargetMemberFieldName,
): string | undefined {
  return hasMemberError(index, field)
    ? memberErrorId(index, field)
    : undefined;
}

function onMemberInput(
  index: number,
  field: TargetMemberFieldName,
  value: string,
): void {
  if (value.trim()) {
    const row = memberErrors[index];
    if (row) delete row[field];
  }
  if (memberServerError(index, field)) serverErrorDismissed.value = true;
}

let nextMemberKey = 0;

function memberDraft(member: TargetMember): MemberDraft {
  return { key: nextMemberKey++, ...member };
}

function emptyMember(): MemberDraft {
  return memberDraft({
    objectType: "skill",
    objectName: "",
    subDir: "",
    matchByName: false,
  });
}

function addMember(): void {
  members.value.push(emptyMember());
  memberListError.value = "";
  if (visibleServerError.value) serverErrorDismissed.value = true;
}

function removeMember(index: number): void {
  if (members.value.length <= 1) return;
  members.value.splice(index, 1);
  clearMemberErrors();
  if (visibleServerError.value) serverErrorDismissed.value = true;
}

function resetForm(): void {
  form.attributionPackageId = props.target?.attributionPackageId ?? null;
  if (!props.target && props.runtimeEnabled) form.attributionPackageId = "default-attribute-badcases";
  form.repoUrl = props.target?.repoUrl ?? "";
  form.defaultRef = props.target?.defaultRef ?? "";
  form.validationProjectId = props.target?.validationProjectId ?? "";
  form.testProjectId = props.target?.testProjectId ?? "";
  form.primaryMetricKey = props.target?.primaryMetricKey ?? "";
  form.enabled = props.target?.enabled ?? true;
  const rows = targetMembers(props.target);
  members.value = rows.length ? rows.map(memberDraft) : [emptyMember()];
  serverErrorDismissed.value = false;
  clearErrors();
  clearMemberErrors();
}

function clearErrors(): void {
  for (const key of Object.keys(errors) as TargetTopField[]) {
    delete errors[key];
  }
}

function clearMemberErrors(): void {
  for (const key of Object.keys(memberErrors)) {
    delete memberErrors[Number(key)];
  }
  memberListError.value = "";
}

function setMemberError(
  index: number,
  field: TargetMemberFieldName,
  message: string,
): void {
  const row = memberErrors[index] ?? {};
  row[field] = message;
  memberErrors[index] = row;
}

function memberErrorsPresent(): boolean {
  return Object.values(memberErrors).some(
    (row) => Object.keys(row).length > 0,
  );
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

function updateDefaultRef(value: string | number): void {
  const normalized = String(value);
  form.defaultRef = normalized;
  if (normalized.trim()) delete errors.defaultRef;
  if (serverErrorFor("defaultRef")) serverErrorDismissed.value = true;
}

function openVersionSuggestions(): void {
  versionAutocomplete.value?.focus();
}

function submit(): void {
  if (props.packagesLoading) return;
  clearErrors();
  clearMemberErrors();
  const repoUrl = form.repoUrl.trim();
  const defaultRef = form.defaultRef.trim();
  const validationProjectId = form.validationProjectId.trim();
  const testProjectId = form.testProjectId.trim();
  const primaryMetricKey = form.primaryMetricKey.trim();
  if (!repoUrl) errors.repoUrl = "请填写仓库地址";
  if (!defaultRef) errors.defaultRef = "请填写基线分支或标签";
  if (!validationProjectId) {
    errors.validationProjectId = "请填写验证集测试工程 ID";
  } else if (PROJECT_ID_INVALID(validationProjectId)) {
    errors.validationProjectId = "工程 ID 不能包含空格或控制字符";
  }
  if (!testProjectId) {
    errors.testProjectId = "请填写测试集测试工程 ID";
  } else if (PROJECT_ID_INVALID(testProjectId)) {
    errors.testProjectId = "工程 ID 不能包含空格或控制字符";
  }
  if (!primaryMetricKey) {
    errors.primaryMetricKey = "请填写主指标 key";
  } else if (PROJECT_ID_INVALID(primaryMetricKey)) {
    errors.primaryMetricKey = "主指标 key 不能包含空格或控制字符";
  }
  if (!members.value.length) {
    memberListError.value = "请至少添加一个成员";
  }
  const seen = new Set<string>();
  members.value.forEach((member, index) => {
    const objectName = member.objectName.trim();
    const subDir = member.subDir.trim();
    if (!objectName) {
      setMemberError(index, "objectName", "请填写成员名称");
    }
    if (!subDir) {
      setMemberError(index, "subDir", "请填写成员子目录");
    }
    if (objectName) {
      const key = `${member.objectType}:${objectName}`;
      if (seen.has(key)) {
        setMemberError(index, "objectName", "同一配置中成员重复");
      } else {
        seen.add(key);
      }
    }
  });
  if (
    Object.keys(errors).length > 0
    || memberErrorsPresent()
    || memberListError.value
  ) {
    return;
  }
  emit("submit", {
    repoUrl,
    defaultRef,
    validationProjectId,
    testProjectId,
    primaryMetricKey,
    enabled: form.enabled,
    attributionPackageId: form.attributionPackageId,
    members: members.value.map(({ objectType, objectName, subDir, matchByName }) => ({
      objectType,
      objectName: objectName.trim(),
      subDir: subDir.trim(),
      matchByName: objectType === "knowledge" ? false : matchByName,
    })),
  });
}

watch(
  () => [props.modelValue, props.target] as const,
  ([open]) => {
    if (open) resetForm();
  },
  { immediate: true },
);

watch(
  () => props.runtimeEnabled,
  (enabled) => {
    if (props.modelValue && enabled && !props.target && !form.attributionPackageId) {
      form.attributionPackageId = "default-attribute-badcases";
    }
  },
);

watch(
  () => props.serverError,
  async (value) => {
    serverErrorDismissed.value = false;
    if (!value?.field) return;
    await nextTick();
    formElement.value
      ?.querySelector<HTMLElement>(`[name="${value.field}"]`)
      ?.focus();
  },
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
    width="min(760px, calc(100vw - 32px))"
    @close="close"
  >
    <form
      id="target-form"
      ref="formElement"
      class="target-form"
      @submit.prevent="submit"
    >
      <ElForm label-position="top">
        <details v-if="target?.definition">
          <summary>查看已保存的对象原文</summary>
          <p>{{ target.definition.path }} · {{ target.definition.commit }}</p>
          <pre class="definition-preview">{{ target.definition.preview }}</pre>
        </details>
        <div class="target-shared-block">
          <ElFormItem label="仓库地址">
            <ElInput
              v-model="form.repoUrl"
              :aria-describedby="fieldDescribedBy('repoUrl')"
              :aria-invalid="fieldAriaInvalid('repoUrl')"
              maxlength="1024"
              name="repoUrl"
              placeholder="https://git.example.com/agent-skills.git"
              @input="onFieldInput('repoUrl', $event)"
            />
            <p class="field-help">
              仅填写无凭据的 HTTPS 或 SSH 地址，不要写入 token。
            </p>
            <p
              v-if="hasFieldError('repoUrl')"
              id="target-repoUrl-error"
              class="field-error"
            >
              {{ fieldMessage("repoUrl") }}
              <span
                v-if="fieldSuggestion('repoUrl')"
                class="field-suggestion"
              >{{ fieldSuggestion("repoUrl") }}</span>
            </p>
          </ElFormItem>

          <div class="target-shared-row">
            <ElFormItem label="基线分支或标签">
              <ElAutocomplete
                ref="versionAutocomplete"
                :aria-describedby="fieldDescribedBy('defaultRef')"
                :aria-invalid="fieldAriaInvalid('defaultRef')"
                autocomplete="off"
                class="target-version-select"
                data-testid="target-version-select"
                :debounce="0"
                :fetch-suggestions="fetchVersionSuggestions"
                :model-value="form.defaultRef"
                name="defaultRef"
                placeholder="main / v2.0.0"
                show-arrow
                trigger-on-focus
                @update:model-value="updateDefaultRef"
              >
                <template #suffix>
                  <button
                    aria-label="展开标签建议"
                    class="version-suggestion-toggle"
                    type="button"
                    @click.stop="openVersionSuggestions"
                    @mousedown.prevent
                  >
                    <span
                      aria-hidden="true"
                      class="version-suggestion-toggle-chevron"
                    />
                  </button>
                </template>
              </ElAutocomplete>
              <p class="field-help">
                {{ versionHelp }}
              </p>
              <p
                v-if="hasFieldError('defaultRef')"
                id="target-defaultRef-error"
                class="field-error"
              >
                {{ fieldMessage("defaultRef") }}
                <span
                  v-if="fieldSuggestion('defaultRef')"
                  class="field-suggestion"
                >{{ fieldSuggestion("defaultRef") }}</span>
              </p>
            </ElFormItem>

            <ElFormItem label="归因 Skill">
              <select
                v-model="form.attributionPackageId"
                aria-label="归因 Skill"
                :disabled="packagesLoading"
                class="skill-select"
              >
                <option
                  v-if="unboundLabel"
                  :value="null"
                >
                  {{ unboundLabel }}
                </option>
                <option
                  v-if="!packages.length"
                  value="default-attribute-badcases"
                >
                  attribute-badcases
                </option>
                <option
                  v-for="item in packages"
                  :key="item.id"
                  :value="item.id"
                >
                  {{ item.skillName }}
                </option>
              </select>
              <p
                v-if="form.attributionPackageId && runtimeEnabled !== undefined"
                class="field-help"
              >
                {{ runtimeEnabled ? "保存绑定后，后台将分析当前与该配置成员关联的 Badcase。" : "归因运行时不可用。绑定会保存，运行时恢复并重启后开始后台归因。" }}<span v-if="form.attributionPackageId">保存绑定时从指定版本读取每个成员的目录定义并保存原文快照。</span>
              </p>
            </ElFormItem>
          </div>

          <div class="target-shared-row">
            <ElFormItem
              label="验证集测试工程 ID"
              required
            >
              <ElInput
                v-model="form.validationProjectId"
                :aria-describedby="fieldDescribedBy('validationProjectId')"
                :aria-invalid="fieldAriaInvalid('validationProjectId')"
                maxlength="128"
                name="validationProjectId"
                placeholder="如 val-2026-q3"
                @input="onFieldInput('validationProjectId', $event)"
              />
              <p
                v-if="hasFieldError('validationProjectId')"
                id="target-validationProjectId-error"
                class="field-error"
              >
                {{ fieldMessage("validationProjectId") }}
                <span
                  v-if="fieldSuggestion('validationProjectId')"
                  class="field-suggestion"
                >{{ fieldSuggestion("validationProjectId") }}</span>
              </p>
            </ElFormItem>

            <ElFormItem
              label="测试集测试工程 ID"
              required
            >
              <ElInput
                v-model="form.testProjectId"
                :aria-describedby="fieldDescribedBy('testProjectId')"
                :aria-invalid="fieldAriaInvalid('testProjectId')"
                maxlength="128"
                name="testProjectId"
                placeholder="如 test-2026-q3"
                @input="onFieldInput('testProjectId', $event)"
              />
              <p
                v-if="hasFieldError('testProjectId')"
                id="target-testProjectId-error"
                class="field-error"
              >
                {{ fieldMessage("testProjectId") }}
                <span
                  v-if="fieldSuggestion('testProjectId')"
                  class="field-suggestion"
                >{{ fieldSuggestion("testProjectId") }}</span>
              </p>
            </ElFormItem>
          </div>

          <p class="field-help project-id-help">
            验证集与测试集分别对应外部测试平台的测试工程 ID；只保存标识，不在此处校验工程是否存在。
          </p>

          <ElFormItem
            label="主指标 key"
            required
          >
            <ElInput
              v-model="form.primaryMetricKey"
              :aria-describedby="fieldDescribedBy('primaryMetricKey')"
              :aria-invalid="fieldAriaInvalid('primaryMetricKey')"
              maxlength="128"
              name="primaryMetricKey"
              placeholder="如 resolved_rate"
              @input="onFieldInput('primaryMetricKey', $event)"
            />
            <p class="field-help">
              对比验证集与测试集时使用的平台指标 metric_key；按平台给出的方向比较，候选必须严格更优才接纳。
            </p>
            <p
              v-if="hasFieldError('primaryMetricKey')"
              id="target-primaryMetricKey-error"
              class="field-error"
            >
              {{ fieldMessage("primaryMetricKey") }}
              <span
                v-if="fieldSuggestion('primaryMetricKey')"
                class="field-suggestion"
              >{{ fieldSuggestion("primaryMetricKey") }}</span>
            </p>
          </ElFormItem>
        </div>

        <ElFormItem required>
          <template #label>
            <span class="member-label">成员</span>
            <span class="member-label-hint">同一仓库里的 skill / agent；成员共享上面的仓库、基线、测试工程与主指标，但各自冻结定义、分别关联 bad case。</span>
          </template>
          <div class="member-list">
            <div
              v-for="(member, index) in members"
              :key="member.key"
              class="member-item"
              :data-testid="`target-member-${index}`"
            >
              <div class="member-row">
                <select
                  v-model="member.objectType"
                  :aria-describedby="memberDescribedBy(index, 'objectType')"
                  :aria-invalid="memberAriaInvalid(index, 'objectType')"
                  :aria-label="`成员 ${index + 1} 类型`"
                  class="member-type"
                  :name="memberFieldPath(index, 'objectType')"
                  @change="onMemberInput(index, 'objectType', String(member.objectType))"
                >
                  <option value="skill">
                    skill
                  </option>
                  <option value="agent">
                    agent
                  </option>
                </select>
                <ElInput
                  v-model="member.objectName"
                  :aria-describedby="memberDescribedBy(index, 'objectName')"
                  :aria-invalid="memberAriaInvalid(index, 'objectName')"
                  :aria-label="`成员 ${index + 1} 名称`"
                  maxlength="128"
                  :name="memberFieldPath(index, 'objectName')"
                  placeholder="如 deep-research"
                  @input="onMemberInput(index, 'objectName', $event)"
                />
                <ElInput
                  v-model="member.subDir"
                  :aria-describedby="memberDescribedBy(index, 'subDir')"
                  :aria-invalid="memberAriaInvalid(index, 'subDir')"
                  :aria-label="`成员 ${index + 1} 子目录`"
                  class="member-subdir-input"
                  maxlength="512"
                  :name="memberFieldPath(index, 'subDir')"
                  placeholder="如 skills/deep-research"
                  @input="onMemberInput(index, 'subDir', $event)"
                />
                <span
                  v-if="member.objectType !== 'knowledge'"
                  class="member-match"
                  title="关闭：按定义正文摘要匹配；开启：按名称关联，忽略同名不同正文的版本差异"
                >
                  <span>名称匹配</span>
                  <ElSwitch
                    v-model="member.matchByName"
                    aria-label="名称匹配"
                    size="small"
                  />
                </span>
                <button
                  class="member-remove"
                  type="button"
                  :aria-label="`移除成员 ${index + 1}`"
                  :disabled="members.length === 1"
                  :title="members.length === 1 ? '至少保留一个成员' : '移除这个成员'"
                  @click="removeMember(index)"
                >
                  ✕
                </button>
              </div>
              <p
                v-if="hasMemberError(index, 'objectName')"
                :id="memberErrorId(index, 'objectName')"
                class="field-error"
              >
                {{ memberMessage(index, "objectName") }}
                <span
                  v-if="memberSuggestion(index, 'objectName')"
                  class="field-suggestion"
                >{{ memberSuggestion(index, "objectName") }}</span>
              </p>
              <p
                v-if="hasMemberError(index, 'subDir')"
                :id="memberErrorId(index, 'subDir')"
                class="field-error"
              >
                {{ memberMessage(index, "subDir") }}
                <span
                  v-if="memberSuggestion(index, 'subDir')"
                  class="field-suggestion"
                >{{ memberSuggestion(index, "subDir") }}</span>
              </p>
              <p
                v-if="hasMemberError(index, 'objectType')"
                :id="memberErrorId(index, 'objectType')"
                class="field-error"
              >
                {{ memberMessage(index, "objectType") }}
                <span
                  v-if="memberSuggestion(index, 'objectType')"
                  class="field-suggestion"
                >{{ memberSuggestion(index, "objectType") }}</span>
              </p>
            </div>
          </div>
          <p
            v-if="memberListError"
            class="field-error"
          >
            {{ memberListError }}
          </p>
          <button
            class="member-add"
            type="button"
            @click="addMember"
          >
            再加一个成员
          </button>
          <p class="member-notice">
            保存后，后台会为<b>每个成员</b>关联当前已上报的 bad case；启动自进化时整条配置一起进化，评测把全部成员目录作为资产一次提交。
          </p>
        </ElFormItem>
      </ElForm>

      <div
        v-if="visibleServerError"
        class="server-error"
        role="alert"
        data-testid="target-server-error"
      >
        <p class="server-error-title">
          {{ visibleServerError.summary }}
        </p>
        <p
          v-if="visibleServerError.suggestion && !visibleServerError.field"
          class="server-error-suggestion"
        >
          {{ visibleServerError.suggestion }}
        </p>
        <details
          v-if="visibleServerError.command || visibleServerError.output"
          class="git-output"
          data-testid="target-git-output"
        >
          <summary>
            <span>{{ visibleServerError.command?.name ?? "git" }}</span>
            <span
              v-if="visibleServerError.command?.exitCode !== undefined"
              class="git-exit-code"
            >
              退出码 {{ visibleServerError.command.exitCode }}
            </span>
          </summary>
          <pre v-if="visibleServerError.output">{{ visibleServerError.output }}</pre>
        </details>
      </div>
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
          :disabled="packagesLoading"
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

.target-shared-row {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 0 14px;
  align-items: start;
}

.target-shared-block {
  padding: 12px 14px 2px;
  margin-bottom: 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-panel);
}

.member-label {
  display: block;
}

.member-label-hint {
  display: block;
  margin-top: 2px;
  color: var(--text-faint);
  font-size: 10.5px;
  font-weight: 400;
  line-height: 1.5;
}

.member-notice {
  margin: 10px 0 0;
  padding: 9px 11px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-panel);
  color: var(--text-dim);
  font-size: 11px;
  line-height: 1.6;
}

.member-list {
  display: grid;
  width: 100%;
  gap: 8px;
}

.member-item {
  display: grid;
  gap: 4px;
}

.member-row {
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr) minmax(0, 1.25fr) 108px 28px;
  gap: 8px;
  align-items: center;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-card);
}

.member-row :deep(.el-input) {
  min-width: 0;
}

.member-match {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-dim);
  font-size: 11.5px;
  white-space: nowrap;
  cursor: pointer;
  user-select: none;
}

.member-match :deep(.el-switch) {
  --el-switch-on-color: var(--blue);
  --el-switch-off-color: var(--border);
  --el-switch-button-size: 14px;
  height: 18px;
}

.member-match :deep(.el-switch__core) {
  min-width: 34px;
  height: 18px;
}

.member-type {
  width: 100%;
  height: 32px;
  padding: 0 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text);
  font: inherit;
  font-size: 12px;
}

.member-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-faint);
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
}

.member-remove:hover:not(:disabled) {
  color: var(--red);
  background: color-mix(in srgb, var(--red) 8%, transparent);
}

.member-remove:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.member-add {
  justify-self: start;
  margin-top: 8px;
  padding: 5px 10px;
  border: 1px dashed color-mix(in srgb, var(--blue) 45%, var(--border));
  border-radius: 7px;
  background: transparent;
  color: var(--blue);
  cursor: pointer;
  font: inherit;
  font-size: 11.5px;
  font-weight: 600;
}

.member-add::before {
  margin-right: 4px;
  content: "＋";
}

.member-add:hover {
  background: color-mix(in srgb, var(--blue) 7%, transparent);
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

.project-id-help {
  margin: -2px 0 0;
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

.server-error p {
  margin: 0;
}

.server-error-title {
  font-weight: 650;
}

.server-error-suggestion {
  margin-top: 3px;
  color: var(--text-dim);
}

.field-suggestion {
  display: block;
  margin-top: 2px;
  color: var(--text-dim);
  font-weight: 400;
}

.git-output {
  margin-top: 8px;
  padding-top: 7px;
  border-top: 1px solid color-mix(in srgb, var(--red) 20%, var(--border));
}

.git-output summary {
  color: var(--text-dim);
  font-size: 10.5px;
  cursor: pointer;
}

.git-exit-code {
  margin-left: 6px;
  font-family: var(--mono);
}

.git-output pre {
  max-height: 160px;
  margin: 6px 0 0;
  padding: 8px;
  overflow: auto;
  border-radius: 6px;
  background: var(--bg-panel);
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 10.5px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.version-suggestion-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  padding: 0;
  color: var(--text-faint);
  background: transparent;
  border: 0;
  border-radius: 4px;
  cursor: pointer;
}

.version-suggestion-toggle:hover {
  color: var(--blue);
  background: color-mix(in srgb, var(--blue) 8%, transparent);
}

.version-suggestion-toggle-chevron {
  width: 6px;
  height: 6px;
  border-right: 1.5px solid currentColor;
  border-bottom: 1.5px solid currentColor;
  transform: translateY(-2px) rotate(45deg);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 640px) {
  .target-shared-row {
    grid-template-columns: 1fr;
    gap: 0;
  }

  .member-row {
    grid-template-columns: 1fr;
  }

  .member-remove {
    justify-self: end;
  }
}
.definition-preview { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
