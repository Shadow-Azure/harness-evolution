<script setup lang="ts">
import type {
  AttributionPreviewResult,
  PotentialPolicy,
  PotentialPreviewItem,
  PotentialPreviewResult,
  PotentialPreviewSummary,
  SessionPreviewResult,
  SessionPreviewSummary,
} from "@harness/contracts";
import { useQuery } from "@tanstack/vue-query";
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";

import { getBadCase } from "../../../api/badCases";
import { getTargetCatalog } from "../../../api/catalogs";
import {
  previewAttribution,
  previewPotential,
  previewSessions,
  startClusterPreview,
  startEvolutionRun,
} from "../../../api/evolutionRuns";
import { ApiError } from "../../../api/http";
import { queryKeys } from "../../../api/queryKeys";
import { formatApiError } from "../../../app/apiError";
import { useEvolutionTargetVersions } from "../../../composables/useEvolutionTargets";
import { workspacePath } from "../../../router/workspace";
import { useAuthStore } from "../../../stores/auth";

const props = defineProps<{
  wid: string;
  focusCaseId?: string | null;
}>();

const emit = defineEmits<{
  close: [];
  launched: [mode: "full" | "cluster_only", runId: string];
}>();

type WizardStep = 1 | 2 | 3 | 4;
type PendingAction = "" | "sessions" | "potential" | "attribution" | "launch";

const SESSION_PAGE_SIZE = 4;
const POTENTIAL_PAGE_SIZE = 5;
const SHORT_ID_HEAD = 4;
const SHORT_ID_TAIL = 4;
const SHORT_ID_MIN_LENGTH = SHORT_ID_HEAD + SHORT_ID_TAIL + 1;

const HIT_REASON_LABELS: Record<string, string> = {
  self_report: "self 上报",
  after_object: "对象之后",
  both: "两者命中",
  policy_excluded: "策略排除",
  order_unknown: "顺序未知",
};

const auth = useAuthStore();
const router = useRouter();

const step = ref<WizardStep>(1);
const targetType = ref<"skill" | "agent">("skill");
const targetId = ref<string | null>(null);
const targetVersion = ref("");
const versionPinned = ref(false);
const windowFrom = ref("");
const windowTo = ref("");
const policyPreset = ref<"default" | "custom">("default");
const includeSelfReport = ref(true);
const includeAfterObject = ref(true);
const sameObjectOnly = ref(false);
const cacheEnabled = ref(true);

const sessionPreview = ref<SessionPreviewResult | null>(null);
const sessionEmptySummary = ref<SessionPreviewSummary | null>(null);
const potentialPreview = ref<PotentialPreviewResult | null>(null);
const potentialEmpty = ref(false);
const attributionPreview = ref<AttributionPreviewResult | null>(null);
const sessionPage = ref(1);
const potentialPage = ref(1);
const pending = ref<PendingAction>("");
const requestError = ref("");
const launchError = ref("");
const focusApplied = ref(false);
const focusTargetMissing = ref(false);

const fieldErrors = reactive({
  target: false,
  version: false,
  from: false,
  to: false,
  policy: false,
});

const WIZARD_TITLE_ID = "launch-wizard-title";
const closeButton = ref<HTMLButtonElement | null>(null);
let triggerElement: HTMLElement | null = null;

const workspaceName = computed(
  () => auth.workspaceById(props.wid)?.name ?? "当前空间",
);

/** Treat Escape like the overlay click so the dialog can be dismissed from the keyboard. */
function handleKeydown(event: KeyboardEvent): void {
  if (event.key !== "Escape") {
    return;
  }
  event.preventDefault();
  emit("close");
}

onMounted(() => {
  triggerElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  window.addEventListener("keydown", handleKeydown);
  closeButton.value?.focus();
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleKeydown);
  if (triggerElement?.isConnected) {
    triggerElement.focus();
  }
  triggerElement = null;
});

const catalogs = useQuery({
  queryKey: computed(() => queryKeys.targetCatalog(props.wid)),
  queryFn: () => getTargetCatalog(props.wid),
});
const versions = useEvolutionTargetVersions(
  computed(() => props.wid),
  computed(() => (step.value === 1 ? targetId.value : null)),
);
const focusCase = useQuery({
  queryKey: computed(() =>
    queryKeys.badCase(props.wid, props.focusCaseId ?? "none"),
  ),
  queryFn: () => getBadCase(props.wid, props.focusCaseId as string),
  enabled: computed(() => Boolean(props.focusCaseId)),
  retry: false,
});

const targetOptions = computed(
  () => catalogs.data.value?.[targetType.value] ?? [],
);
const hasAnyTarget = computed(() => {
  const data = catalogs.data.value;
  if (!data) {
    return false;
  }
  return data.skill.length + data.agent.length > 0;
});
const selectedTarget = computed(
  () => targetOptions.value.find((target) => target.id === targetId.value) ?? null,
);
const versionOptions = computed(() => {
  if (versions.data.value?.versions.length) {
    return versions.data.value.versions;
  }
  return selectedTarget.value?.versions ?? [];
});

/**
 * Pick the default version for one option list.
 * @param options Versions currently offered by the remote query or catalog fallback.
 * @returns The remote `defaultRef` when present, otherwise the first option.
 */
function defaultVersion(options: string[]): string {
  const remoteDefault = versions.data.value?.defaultRef;
  if (remoteDefault && options.includes(remoteDefault)) {
    return remoteDefault;
  }
  return options[0] ?? "";
}

watch(
  versionOptions,
  (options) => {
    if (versionPinned.value && options.includes(targetVersion.value)) {
      return;
    }
    targetVersion.value = defaultVersion(options);
    versionPinned.value = false;
  },
  { immediate: true },
);

watch(targetId, () => {
  fieldErrors.target = false;
});
watch(targetVersion, () => {
  fieldErrors.version = false;
});
watch(windowFrom, () => {
  fieldErrors.from = false;
});
watch(windowTo, () => {
  fieldErrors.to = false;
});
watch([includeSelfReport, includeAfterObject], () => {
  fieldErrors.policy = false;
});
watch([policyPreset, sameObjectOnly], () => {
  fieldErrors.policy = false;
  resetDownstream();
});

const policyRuleError = computed(
  () =>
    policyPreset.value === "custom" &&
    !includeSelfReport.value &&
    !includeAfterObject.value,
);

const focusCaseError = computed(() => {
  const error = focusCase.error.value;
  if (!error) {
    return "";
  }
  return error instanceof Error ? error.message : String(error);
});

const catalogError = computed(() => {
  const error = catalogs.error.value;
  if (!error) {
    return "";
  }
  return error instanceof Error ? error.message : String(error);
});
const versionError = computed(() => {
  const error = versions.error.value;
  if (!error) {
    return "";
  }
  return error instanceof Error ? error.message : String(error);
});

const isBusy = computed(() => pending.value !== "");
const sessionSummary = computed(
  () => sessionPreview.value?.summary ?? sessionEmptySummary.value,
);
const hasAssociatedSessions = computed(
  () => (sessionSummary.value?.associated ?? 0) > 0,
);
const potentialSummary = computed<PotentialPreviewSummary | null>(
  () => potentialPreview.value?.summary ?? null,
);
const hasPotential = computed(
  () => (potentialSummary.value?.potential ?? 0) > 0,
);
const sessionPageCount = computed(() =>
  sessionPreview.value
    ? Math.max(
        1,
        Math.ceil(sessionPreview.value.total / sessionPreview.value.pageSize),
      )
    : 1,
);
const potentialPageCount = computed(() =>
  potentialPreview.value
    ? Math.max(
        1,
        Math.ceil(potentialPreview.value.total / potentialPreview.value.pageSize),
      )
    : 1,
);
const attributionSummary = computed(() => attributionPreview.value?.summary ?? null);

/**
 * Apply the focus case's object and version clues once both catalogs are ready.
 * @returns No value.
 */
function applyFocusCase(): void {
  if (focusApplied.value) {
    return;
  }
  const caseData = focusCase.data.value;
  const data = catalogs.data.value;
  if (!caseData || !data) {
    return;
  }
  focusApplied.value = true;
  targetType.value = caseData.objectType;
  const target = data[caseData.objectType]?.find(
    (item) => item.name === caseData.objectName,
  );
  if (!target) {
    focusTargetMissing.value = true;
    return;
  }
  targetId.value = target.id;
  versionPinned.value = true;
  targetVersion.value =
    caseData.objectVersion &&
    (target.versions.includes(caseData.objectVersion) ||
      target.defaultRef === caseData.objectVersion)
      ? caseData.objectVersion
      : target.defaultRef || target.versions[0] || "";
  focusTargetMissing.value = false;
}

watch(
  [() => catalogs.data.value, () => focusCase.data.value],
  applyFocusCase,
  { immediate: true },
);

/** Clear every preview that depended on the previous step-1 condition. */
function resetDownstream(): void {
  sessionPreview.value = null;
  sessionEmptySummary.value = null;
  potentialPreview.value = null;
  potentialEmpty.value = false;
  attributionPreview.value = null;
  sessionPage.value = 1;
  potentialPage.value = 1;
  requestError.value = "";
  launchError.value = "";
  if (step.value !== 1) {
    step.value = 1;
  }
}

/** Reset the cascading name and version selections when the type changes. */
function selectType(next: "skill" | "agent"): void {
  if (targetType.value === next) {
    return;
  }
  targetType.value = next;
  targetId.value = null;
  targetVersion.value = "";
  versionPinned.value = false;
  resetDownstream();
}

/** Record the chosen target id and reset its dependent version. */
function selectTargetId(id: string): void {
  targetId.value = id || null;
  targetVersion.value = "";
  versionPinned.value = false;
  resetDownstream();
}

/** Retry the failed remote version list without leaving step 1. */
function retryVersions(): void {
  void versions.refetch();
}

/** Retry reading the focus case's object/version clues. */
function retryFocusCase(): void {
  void focusCase.refetch();
}

/** Keep both ends of an id so rows from the same family stay distinguishable. */
function shortId(id: string): string {
  if (id.length < SHORT_ID_MIN_LENGTH) {
    return id;
  }
  return `${id.slice(0, SHORT_ID_HEAD)}…${id.slice(-SHORT_ID_TAIL)}`;
}

/** Render an API timestamp without applying the browser's local timezone. */
function formatMoment(value: string): string {
  return value.includes("T") ? value.replace("T", " ").slice(0, 16) : value;
}

/** Close the wizard and open the target configuration page. */
function goTargetConfig(): void {
  emit("close");
  void router.push(workspacePath(props.wid, "evolution/targets"));
}

/** Build the shared preview/launch condition from the current step-1 form. */
function condition() {
  return {
    targetType: targetType.value,
    targetName: selectedTarget.value?.name ?? "",
    targetVersion: targetVersion.value || undefined,
    from: windowFrom.value || undefined,
    to: windowTo.value || undefined,
  };
}

/** Build the raw policy payload sent to preview and launch endpoints. */
function currentPolicy(): PotentialPolicy {
  if (policyPreset.value === "default") {
    return { preset: "default" };
  }
  return {
    preset: "custom",
    includeSelfReport: includeSelfReport.value,
    includeAfterObject: includeAfterObject.value,
    sameObjectOnly: sameObjectOnly.value,
  };
}

/** Show every failed requirement beside its own control before querying. */
function validateStep1(): boolean {
  const reversed = Boolean(
    windowFrom.value && windowTo.value && windowFrom.value > windowTo.value,
  );
  fieldErrors.target = !selectedTarget.value;
  fieldErrors.version = !targetVersion.value;
  fieldErrors.from = !windowFrom.value || reversed;
  fieldErrors.to = !windowTo.value || reversed;
  fieldErrors.policy = policyRuleError.value;
  return (
    !fieldErrors.target &&
    !fieldErrors.version &&
    !fieldErrors.from &&
    !fieldErrors.to &&
    !fieldErrors.policy
  );
}

/** Extract the Session partition carried by a `NO_ASSOCIATED_SESSIONS` conflict. */
function conflictSessionSummary(error: unknown): SessionPreviewSummary | null {
  if (!(error instanceof ApiError) || !error.details) {
    return null;
  }
  const details = error.details as { summary?: SessionPreviewSummary };
  return details.summary ?? null;
}

/** Return whether one API failure carries the requested stable code. */
function hasCode(error: unknown, code: string): boolean {
  return error instanceof ApiError && error.code === code;
}

/** Run the Session association preview and advance to step 2. */
async function goToSessions(): Promise<void> {
  if (!validateStep1()) {
    return;
  }
  pending.value = "sessions";
  requestError.value = "";
  try {
    const result = await previewSessions(props.wid, {
      ...condition(),
      page: 1,
      pageSize: SESSION_PAGE_SIZE,
    });
    sessionPreview.value = result;
    sessionEmptySummary.value = null;
    sessionPage.value = result.page;
    potentialPreview.value = null;
    potentialEmpty.value = false;
    attributionPreview.value = null;
    step.value = 2;
  } catch (error) {
    if (hasCode(error, "NO_ASSOCIATED_SESSIONS")) {
      sessionPreview.value = null;
      sessionEmptySummary.value = conflictSessionSummary(error);
      sessionPage.value = 1;
      step.value = 2;
      return;
    }
    requestError.value = formatApiError(error, "加载 Session 关联失败").message;
  } finally {
    pending.value = "";
  }
}

/** Fetch another page of associated Sessions without re-running the match. */
async function changeSessionPage(next: number): Promise<void> {
  if (!sessionPreview.value || next < 1 || next > sessionPageCount.value) {
    return;
  }
  pending.value = "sessions";
  requestError.value = "";
  try {
    const result = await previewSessions(props.wid, {
      ...condition(),
      page: next,
      pageSize: SESSION_PAGE_SIZE,
    });
    sessionPreview.value = result;
    sessionPage.value = result.page;
  } catch (error) {
    requestError.value = formatApiError(error, "加载 Session 关联失败").message;
  } finally {
    pending.value = "";
  }
}

/** Run the potential preview with the current policy and advance to step 3. */
async function goToPotential(): Promise<void> {
  if (!hasAssociatedSessions.value) {
    return;
  }
  pending.value = "potential";
  requestError.value = "";
  try {
    const result = await previewPotential(props.wid, {
      ...condition(),
      policy: currentPolicy(),
      page: 1,
      pageSize: POTENTIAL_PAGE_SIZE,
    });
    potentialPreview.value = result;
    potentialEmpty.value = false;
    potentialPage.value = result.page;
    attributionPreview.value = null;
    step.value = 3;
  } catch (error) {
    if (hasCode(error, "NO_POTENTIAL_MATCHED")) {
      potentialPreview.value = null;
      potentialEmpty.value = true;
      potentialPage.value = 1;
      step.value = 3;
      return;
    }
    if (hasCode(error, "NO_ASSOCIATED_SESSIONS")) {
      sessionPreview.value = null;
      sessionEmptySummary.value = conflictSessionSummary(error);
      potentialPreview.value = null;
      potentialEmpty.value = false;
      step.value = 2;
      return;
    }
    requestError.value = formatApiError(error, "加载潜在 bad case 失败").message;
  } finally {
    pending.value = "";
  }
}

/** Fetch another page of policy-included cases without re-running the match. */
async function changePotentialPage(next: number): Promise<void> {
  if (!potentialPreview.value || next < 1 || next > potentialPageCount.value) {
    return;
  }
  pending.value = "potential";
  requestError.value = "";
  try {
    const result = await previewPotential(props.wid, {
      ...condition(),
      policy: currentPolicy(),
      page: next,
      pageSize: POTENTIAL_PAGE_SIZE,
    });
    potentialPreview.value = result;
    potentialPage.value = result.page;
  } catch (error) {
    requestError.value = formatApiError(error, "加载潜在 bad case 失败").message;
  } finally {
    pending.value = "";
  }
}

/** Run the read-only attribution preview and advance to step 4. */
async function goToAttribution(): Promise<void> {
  if (!hasPotential.value) {
    return;
  }
  pending.value = "attribution";
  requestError.value = "";
  try {
    attributionPreview.value = await previewAttribution(props.wid, {
      ...condition(),
      policy: currentPolicy(),
      cacheEnabled: cacheEnabled.value,
    });
    step.value = 4;
  } catch (error) {
    if (hasCode(error, "NO_POTENTIAL_MATCHED")) {
      potentialPreview.value = null;
      potentialEmpty.value = true;
      step.value = 3;
      return;
    }
    requestError.value = formatApiError(error, "加载归因预览失败").message;
  } finally {
    pending.value = "";
  }
}

/** Re-request the attribution preview after the cache switch changes. */
async function refreshAttribution(): Promise<void> {
  if (step.value !== 4) {
    return;
  }
  pending.value = "attribution";
  requestError.value = "";
  try {
    attributionPreview.value = await previewAttribution(props.wid, {
      ...condition(),
      policy: currentPolicy(),
      cacheEnabled: cacheEnabled.value,
    });
  } catch (error) {
    requestError.value = formatApiError(error, "加载归因预览失败").message;
  } finally {
    pending.value = "";
  }
}

/** Accept one full run or cluster-only preview and leave the wizard. */
async function launch(mode: "full" | "cluster_only"): Promise<void> {
  if (!selectedTarget.value || !hasPotential.value || isBusy.value) {
    return;
  }
  pending.value = "launch";
  launchError.value = "";
  try {
    const body = {
      ...condition(),
      mode,
      policy: currentPolicy(),
      cacheEnabled: cacheEnabled.value,
      page: 1,
      pageSize: POTENTIAL_PAGE_SIZE,
    };
    const accepted =
      mode === "full"
        ? await startEvolutionRun(props.wid, body)
        : await startClusterPreview(props.wid, body);
    emit("launched", mode, accepted.runId);
  } catch (error) {
    launchError.value = formatApiError(error, "启动运行失败").message;
  } finally {
    pending.value = "";
  }
}

/** Open one potential case's attribution tab in a new tab. */
function openPotentialCase(item: PotentialPreviewItem): void {
  window.open(
    `${workspacePath(props.wid, `sessions/${encodeURIComponent(item.sessionId)}/errors`)}?case=${encodeURIComponent(item.badCaseId)}&tab=attr`,
    "_blank",
    "noopener",
  );
}

/** Move back one step while keeping the already-loaded preview. */
function backToStep(next: WizardStep): void {
  requestError.value = "";
  launchError.value = "";
  step.value = next;
}

const reasonEntries = computed(() => {
  const summary = potentialSummary.value;
  if (!summary) {
    return [];
  }
  return (
    [
      ["self_report", summary.byReason.selfReport],
      ["after_object", summary.byReason.afterObject],
      ["both", summary.byReason.both],
      ["order_unknown", summary.byReason.orderUnknown],
    ] as const
  )
    .filter(([, count]) => count > 0)
    .map(([key, count]) => ({
      key,
      label: HIT_REASON_LABELS[key] ?? key,
      count,
    }));
});
</script>

<template>
  <div
    class="evov"
    data-testid="launch-wizard"
    role="dialog"
    aria-modal="true"
    :aria-labelledby="WIZARD_TITLE_ID"
    @click.self="emit('close')"
  >
    <div class="modal">
      <div class="modal-head">
        <h2 :id="WIZARD_TITLE_ID">
          启动自进化
        </h2>
        <button
          ref="closeButton"
          class="x"
          type="button"
          aria-label="关闭向导"
          @click="emit('close')"
        >
          ✕
        </button>
      </div>

      <div
        v-if="catalogs.isPending.value"
        class="modal-body"
      >
        <p class="wz-loading">
          正在读取当前空间的进化对象…
        </p>
      </div>
      <div
        v-else-if="catalogs.isError.value"
        class="modal-body"
      >
        <div
          class="wz-empty"
          data-testid="wizard-catalog-error"
        >
          <div>
            <div
              aria-hidden="true"
              class="wz-empty-icon"
            >
              !
            </div>
            <h3>进化对象清单读取失败</h3>
            <p>{{ catalogError || "请检查网络后重试。" }}</p>
            <button
              class="btn"
              type="button"
              data-testid="wizard-catalog-retry"
              @click="catalogs.refetch()"
            >
              重试
            </button>
          </div>
        </div>
      </div>
      <div
        v-else-if="!hasAnyTarget"
        class="modal-body"
      >
        <div
          class="wz-empty"
          data-testid="wizard-config-empty"
        >
          <div>
            <div
              aria-hidden="true"
              class="wz-empty-icon"
            >
              ∅
            </div>
            <h3>当前空间还没有启用的进化对象</h3>
            <p>请先在「进化对象配置」中新增 skill / agent，并确认已启用，再回到这里启动自进化。</p>
            <button
              class="btn primary"
              type="button"
              data-testid="wizard-target-config-link"
              @click="goTargetConfig"
            >
              前往配置 →
            </button>
          </div>
        </div>
      </div>
      <template v-else>
        <div class="modal-body">
          <div class="wz-steps">
            <span :class="{ on: step === 1 }">① 选择范围</span>
            →
            <span :class="{ on: step === 2 }">② Session 关联</span>
            →
            <span :class="{ on: step === 3 }">③ 潜在 bad case</span>
            →
            <span :class="{ on: step === 4 }">④ 归因预览与启动</span>
          </div>

          <template v-if="step === 1">
            <div class="f-row">
              <div class="f-label">
                工作空间
              </div>
              <div class="f-inline">
                <span class="v2-badge">{{ workspaceName }}</span>
                <span class="f-note">启动后只处理该空间上报的 bad case</span>
              </div>
            </div>

            <div class="f-row">
              <div class="f-label">
                进化对象 <span class="req">*</span>
              </div>
              <div class="f-inline wz-controls">
                <div class="seg">
                  <button
                    :class="{ active: targetType === 'skill' }"
                    type="button"
                    @click="selectType('skill')"
                  >
                    skill
                  </button>
                  <button
                    :class="{ active: targetType === 'agent' }"
                    type="button"
                    @click="selectType('agent')"
                  >
                    agent
                  </button>
                </div>
                <div class="wz-field">
                  <select
                    class="inp"
                    :class="{ 'input-error': fieldErrors.target }"
                    data-testid="wizard-target"
                    :value="targetId ?? ''"
                    :aria-invalid="fieldErrors.target ? 'true' : undefined"
                    aria-describedby="wizard-target-error"
                    @change="selectTargetId(($event.target as HTMLSelectElement).value)"
                  >
                    <option value="">
                      {{ catalogs.isPending.value ? "读取对象…" : "选择对象" }}
                    </option>
                    <option
                      v-for="target in targetOptions"
                      :key="target.id"
                      :value="target.id"
                    >
                      {{ target.name }}
                    </option>
                  </select>
                  <p
                    v-if="fieldErrors.target"
                    id="wizard-target-error"
                    data-testid="wizard-target-error"
                    class="field-error"
                    role="alert"
                  >
                    请选择进化对象
                  </p>
                  <p
                    v-else-if="!targetOptions.length"
                    class="field-error"
                  >
                    当前类型没有已启用的对象，可切换到另一种类型或前往配置。
                  </p>
                </div>
                <span class="wz-inline-label">版本</span>
                <div class="wz-field">
                  <select
                    v-model="targetVersion"
                    class="inp"
                    :class="{ 'input-error': fieldErrors.version }"
                    data-testid="wizard-version"
                    :aria-invalid="fieldErrors.version ? 'true' : undefined"
                    aria-describedby="wizard-version-error"
                    @change="versionPinned = true"
                  >
                    <option value="">
                      {{ versions.isPending.value ? "读取版本…" : "版本" }}
                    </option>
                    <option
                      v-for="version in versionOptions"
                      :key="version"
                      :value="version"
                    >
                      {{ version }}
                    </option>
                  </select>
                  <p
                    v-if="fieldErrors.version"
                    id="wizard-version-error"
                    data-testid="wizard-version-error"
                    class="field-error"
                    role="alert"
                  >
                    请选择版本
                  </p>
                </div>
              </div>
              <p
                v-if="versions.isError.value"
                id="wizard-version-load-error"
                class="wizard-error"
                data-testid="wizard-version-load-error"
                role="alert"
              >
                版本列表读取失败<span v-if="versionError">：{{ versionError }}</span>。
                <button
                  class="linklike"
                  type="button"
                  data-testid="wizard-version-retry"
                  @click="retryVersions"
                >
                  重试
                </button>
              </p>
              <p class="f-note">
                只列出当前空间已启用的进化对象；点击<!-- eslint-disable vue/multiline-html-element-content-newline -- 中文句内按钮与前后文字紧邻渲染，不留多余空格 --><button
                  class="cfg-link"
                  type="button"
                  data-testid="wizard-config-link"
                  @click="goTargetConfig"
                >配置页</button><!-- eslint-enable vue/multiline-html-element-content-newline -->调整。
              </p>
            </div>

            <div class="f-row">
              <div class="f-label">
                bad case 时间段 <span class="req">*</span>
              </div>
              <div class="f-inline wz-controls">
                <div class="wz-field">
                  <input
                    v-model="windowFrom"
                    class="inp"
                    :class="{ 'input-error': fieldErrors.from }"
                    type="date"
                    data-testid="wizard-from"
                    :aria-invalid="fieldErrors.from ? 'true' : undefined"
                    aria-describedby="wizard-from-error"
                  >
                  <p
                    v-if="fieldErrors.from"
                    id="wizard-from-error"
                    data-testid="wizard-from-error"
                    class="field-error"
                    role="alert"
                  >
                    {{ windowFrom ? "起始时间不能晚于结束时间" : "请选择开始时间" }}
                  </p>
                </div>
                <span class="wz-inline-label">~</span>
                <div class="wz-field">
                  <input
                    v-model="windowTo"
                    class="inp"
                    :class="{ 'input-error': fieldErrors.to }"
                    type="date"
                    data-testid="wizard-to"
                    :aria-invalid="fieldErrors.to ? 'true' : undefined"
                    aria-describedby="wizard-to-error"
                  >
                  <p
                    v-if="fieldErrors.to"
                    id="wizard-to-error"
                    data-testid="wizard-to-error"
                    class="field-error"
                    role="alert"
                  >
                    {{ windowTo ? "起始时间不能晚于结束时间" : "请选择结束时间" }}
                  </p>
                </div>
              </div>
              <p class="f-note">
                按 bad case 的 created_at 过滤；Session 的启动时间只用于展示。
              </p>
            </div>

            <div class="f-row">
              <div class="f-label">
                潜在 bad case 策略
              </div>
              <div
                class="policy"
                :class="{ selected: policyPreset === 'default' }"
                @click="policyPreset = 'default'"
              >
                <label>
                  <input
                    v-model="policyPreset"
                    type="radio"
                    name="wizard-policy"
                    value="default"
                    data-testid="wizard-policy-default"
                  >
                  默认策略
                </label>
                <p>进化对象自身 <b>self</b> 上报的 bad case，或触发点在对象触发点之后的 bad case。</p>
              </div>
              <div
                class="policy"
                :class="{ selected: policyPreset === 'custom' }"
                @click="policyPreset = 'custom'"
              >
                <label>
                  <input
                    v-model="policyPreset"
                    type="radio"
                    name="wizard-policy"
                    value="custom"
                    data-testid="wizard-policy-custom"
                  >
                  自定义策略
                </label>
                <div
                  v-if="policyPreset === 'custom'"
                  class="policy-rules"
                >
                  <label class="switch-row">
                    <input
                      v-model="includeSelfReport"
                      type="checkbox"
                      data-testid="wizard-rule-self"
                    >
                    包含对象自身 self 上报
                  </label>
                  <label class="switch-row">
                    <input
                      v-model="includeAfterObject"
                      type="checkbox"
                      data-testid="wizard-rule-after"
                    >
                    包含触发点在对象之后
                  </label>
                  <label class="switch-row">
                    <input
                      v-model="sameObjectOnly"
                      type="checkbox"
                      data-testid="wizard-rule-same"
                    >
                    仅纳入同 object_name
                  </label>
                </div>
                <p v-else>
                  勾选规则组合成策略；两条匹配规则至少勾选一条。
                </p>
              </div>
              <p
                v-if="policyRuleError"
                id="wizard-policy-error"
                data-testid="wizard-policy-error"
                class="field-error"
                role="alert"
              >
                请至少勾选一条潜在匹配规则
              </p>
            </div>

            <div
              v-if="focusCaseId && focusCase.data.value"
              class="wz-demo"
              data-testid="wizard-focus-case"
            >
              <template v-if="focusTargetMissing">
                <b>从 bad case 启动</b> · {{ shortId(focusCaseId) }} 的对象 {{ focusCase.data.value?.objectName }} 未在配置中启用，请先前往配置页启用。
              </template>
              <template v-else>
                <b>从 bad case 启动</b> · {{ shortId(focusCaseId) }} 已锁定为关注对象；启动后可在归因列表中找到它。
              </template>
            </div>
            <p
              v-if="focusCase.isError.value"
              class="wizard-error"
              data-testid="wizard-focus-case-error"
              role="alert"
            >
              bad case 线索读取失败<span v-if="focusCaseError">：{{ focusCaseError }}</span>，将按普通条件启动。
              <button
                class="linklike"
                type="button"
                @click="retryFocusCase"
              >
                重试
              </button>
            </p>

            <p
              v-if="requestError"
              class="wizard-error"
              data-testid="wizard-error"
              role="alert"
            >
              {{ requestError }}
            </p>
          </template>

          <template v-else-if="step === 2">
            <div class="wz-condstrip">
              <span class="chip kind">{{ targetType }}:{{ selectedTarget?.name }}@{{ targetVersion || selectedTarget?.defaultRef }}</span>
              <span class="chip mono">{{ windowFrom }} ~ {{ windowTo }}</span>
              <span class="chip">{{ policyPreset === "default" ? "默认潜在策略" : "自定义潜在策略" }}</span>
              <button
                class="btn sm back"
                type="button"
                @click="backToStep(1)"
              >
                ← 修改条件
              </button>
            </div>

            <div class="wz-section-title">
              第 2 步 · Session 关联
              <span>先判断对象版本出现在哪些 Session，只有出现的 Session 才进入下一步</span>
            </div>

            <div class="wz-stats">
              <span class="st"><b>{{ sessionSummary?.reported ?? 0 }}</b><span>上报过 bad case 的 Session</span></span>
              <span class="st accent"><b>{{ sessionSummary?.associated ?? 0 }}</b><span>对象出现 · 已关联</span></span>
              <span class="st"><b>{{ sessionSummary?.skipped ?? 0 }}</b><span>未出现 · 跳过</span></span>
              <span class="st"><b>{{ sessionSummary?.versionUnresolved ?? 0 }}</b><span>版本未知</span></span>
              <span class="st"><b>{{ sessionSummary?.pending ?? 0 }}</b><span>待轨迹同步</span></span>
            </div>

            <template v-if="sessionPreview">
              <div class="rep-scroll">
                <table
                  class="rep"
                  data-testid="wizard-session-table"
                >
                  <thead>
                    <tr>
                      <th>Session</th>
                      <th>对象出现</th>
                      <th>对象触发点时间</th>
                      <th>该 Session 的 bad case 数</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="item in sessionPreview.items"
                      :key="item.sessionId"
                    >
                      <td>
                        <b>{{ item.title }}</b>
                        <span class="cell-sub mono">#{{ shortId(item.sessionId) }}</span>
                      </td>
                      <td>
                        <span class="v2-badge ok">已出现</span>
                      </td>
                      <td class="mono">
                        {{ formatMoment(item.objectTriggerAt) }}
                      </td>
                      <td class="mono">
                        {{ item.badCaseCount }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="pager">
                <button
                  class="btn"
                  type="button"
                  data-testid="wizard-session-prev"
                  :disabled="sessionPage <= 1 || isBusy"
                  @click="changeSessionPage(sessionPage - 1)"
                >
                  ← 上一页
                </button>
                <span class="pager-info">第 <b>{{ sessionPage }}</b> / {{ sessionPageCount }} 页 · 共 <b>{{ sessionPreview.total }}</b> 个关联 Session</span>
                <button
                  class="btn"
                  type="button"
                  data-testid="wizard-session-next"
                  :disabled="sessionPage >= sessionPageCount || isBusy"
                  @click="changeSessionPage(sessionPage + 1)"
                >
                  下一页 →
                </button>
              </div>
              <p class="f-note">
                只展示对象版本出现过的 Session；未出现的 Session 已跳过，下一步再按策略筛选潜在 bad case。
              </p>
            </template>
            <div
              v-else
              class="wz-empty"
              data-testid="wizard-session-empty"
            >
              <div>
                <div
                  aria-hidden="true"
                  class="wz-empty-icon"
                >
                  ∅
                </div>
                <h3>没有对象版本出现过的 Session</h3>
                <p>可回第 1 步调整时间段或对象版本后重试。</p>
              </div>
            </div>

            <p
              v-if="requestError"
              class="wizard-error"
              data-testid="wizard-error"
              role="alert"
            >
              {{ requestError }}
            </p>
          </template>

          <template v-else-if="step === 3">
            <div class="wz-condstrip">
              <span class="chip kind">{{ targetType }}:{{ selectedTarget?.name }}@{{ targetVersion || selectedTarget?.defaultRef }}</span>
              <span class="chip mono">{{ windowFrom }} ~ {{ windowTo }}</span>
              <span class="chip">{{ policyPreset === "default" ? "默认潜在策略" : "自定义潜在策略" }}</span>
              <button
                class="btn sm back"
                type="button"
                @click="backToStep(1)"
              >
                ← 修改条件
              </button>
            </div>

            <div class="wz-section-title">
              第 3 步 · 潜在 bad case
              <span>{{ policyPreset === "default" ? "默认策略：对象自身 self 上报 或 触发点在对象触发点之后" : "自定义策略：按第 1 步勾选的规则组合" }}</span>
            </div>

            <div class="wz-stats">
              <span class="st"><b>{{ potentialSummary?.badCases ?? 0 }}</b><span>时间段内 bad case</span></span>
              <span class="st accent"><b>{{ potentialSummary?.potential ?? 0 }}</b><span>潜在 bad case</span></span>
              <span
                v-for="entry in reasonEntries"
                :key="entry.key"
                class="st"
              >
                <b>{{ entry.count }}</b><span>{{ entry.label }}</span>
              </span>
            </div>

            <template v-if="potentialPreview">
              <div class="rep-scroll">
                <table
                  class="rep"
                  data-testid="wizard-potential-table"
                >
                  <thead>
                    <tr>
                      <th>bad case</th>
                      <th>object_name</th>
                      <th>类型</th>
                      <th>触发点时间</th>
                      <th>来源 Session</th>
                      <th>命中原因</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="item in potentialPreview.items"
                      :key="item.badCaseId"
                    >
                      <td>
                        <button
                          class="linklike"
                          type="button"
                          :title="item.badCaseId"
                          @click="openPotentialCase(item)"
                        >
                          {{ shortId(item.badCaseId) }}
                        </button>
                      </td>
                      <td>
                        {{ item.objectName }}
                      </td>
                      <td>
                        {{ item.badCaseType }}
                      </td>
                      <td class="mono">
                        {{ formatMoment(item.triggerAt) }}
                      </td>
                      <td class="mono">
                        #{{ shortId(item.sessionId) }}
                      </td>
                      <td>
                        <span class="hit-reason">{{ HIT_REASON_LABELS[item.hitReason] ?? item.hitReason }}</span>
                        <span
                          v-if="item.orderState === 'unknown'"
                          class="order-note"
                        >触发点顺序待轨迹时间戳重放</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="pager">
                <button
                  class="btn"
                  type="button"
                  data-testid="wizard-potential-prev"
                  :disabled="potentialPage <= 1 || isBusy"
                  @click="changePotentialPage(potentialPage - 1)"
                >
                  ← 上一页
                </button>
                <span class="pager-info">第 <b>{{ potentialPage }}</b> / {{ potentialPageCount }} 页 · 共 <b>{{ potentialPreview.total }}</b> 个潜在 bad case</span>
                <button
                  class="btn"
                  type="button"
                  data-testid="wizard-potential-next"
                  :disabled="potentialPage >= potentialPageCount || isBusy"
                  @click="changePotentialPage(potentialPage + 1)"
                >
                  下一页 →
                </button>
              </div>
              <p class="f-note">
                默认策略 = 对象自身 self 上报 或 触发点在对象之后；修改策略需回第 1 步。归因在下一步预览，不在向导内执行。
              </p>
            </template>
            <div
              v-else
              class="wz-empty"
              data-testid="wizard-potential-empty"
            >
              <div>
                <div
                  aria-hidden="true"
                  class="wz-empty-icon"
                >
                  ∅
                </div>
                <h3>当前策略没有命中潜在 bad case</h3>
                <p>可返回第 1 步调整时间段或策略后重试。</p>
              </div>
            </div>

            <p
              v-if="requestError"
              class="wizard-error"
              data-testid="wizard-error"
              role="alert"
            >
              {{ requestError }}
            </p>
          </template>

          <template v-else>
            <div class="wz-condstrip">
              <span class="chip kind">{{ targetType }}:{{ selectedTarget?.name }}@{{ targetVersion || selectedTarget?.defaultRef }}</span>
              <span class="chip mono">{{ windowFrom }} ~ {{ windowTo }}</span>
              <span
                class="v2-badge"
                :class="{ ok: policyPreset === 'default' }"
              >{{ policyPreset === "default" ? "默认潜在策略" : "自定义潜在策略" }}</span>
              <span
                class="v2-badge"
                :class="{ warn: !cacheEnabled }"
              >{{ cacheEnabled ? "复用缓存" : "不复用缓存" }}</span>
              <button
                class="btn sm back"
                type="button"
                @click="backToStep(1)"
              >
                ← 修改条件
              </button>
            </div>

            <div class="wz-section-title">
              第 4 步 · 归因预览与启动
              <span>确认缓存策略后启动；归因结果会写回该对象版本</span>
            </div>

            <div class="cache-option">
              <div>
                <b>复用缓存归因</b>
                <div class="f-note">
                  如果该对象版本已经对某个潜在 bad case 做过归因，直接复用最近一次成功结果。
                </div>
              </div>
              <label class="switch">
                <input
                  v-model="cacheEnabled"
                  type="checkbox"
                  data-testid="wizard-cache"
                  aria-label="复用缓存归因"
                  :disabled="isBusy"
                  @change="refreshAttribution"
                >
                <span class="slider" />
              </label>
            </div>

            <div
              class="preview-stats"
              data-testid="wizard-attribution-stats"
            >
              <div class="preview-stat">
                <strong>{{ attributionSummary?.potential ?? 0 }}</strong>
                <span>潜在 bad case</span>
              </div>
              <div class="preview-stat">
                <strong>{{ attributionSummary?.reused ?? 0 }}</strong>
                <span>复用缓存</span>
              </div>
              <div class="preview-stat">
                <strong>{{ attributionSummary?.fresh ?? 0 }}</strong>
                <span>本次新增归因</span>
              </div>
              <div class="preview-stat">
                <strong>{{ attributionSummary?.nonTargetKnown ?? 0 }}</strong>
                <span>历史非该对象</span>
              </div>
            </div>

            <div class="notice">
              启动后先生成 {{ attributionSummary?.potential ?? 0 }} 条对象级归因，再进入迭代优化。可归因 {{ attributionSummary?.potential ?? 0 }} 个 · 非该对象 {{ attributionSummary?.nonTargetKnown ?? 0 }} 个 · 缓存命中 {{ attributionSummary?.reused ?? 0 }} 个。
            </div>
            <p class="f-note">
              缓存键包含工作空间、bad case、对象身份/版本、策略版本与归因模型版本；「非该对象问题」不会修改 bad case 本身。
            </p>

            <p
              v-if="requestError"
              class="wizard-error"
              data-testid="wizard-error"
              role="alert"
            >
              {{ requestError }}
            </p>
            <p
              v-if="launchError"
              class="wizard-error"
              data-testid="wizard-launch-error"
              role="alert"
            >
              {{ launchError }}
            </p>
          </template>
        </div>

        <div class="modal-foot">
          <template v-if="step === 1">
            <button
              class="btn primary"
              type="button"
              data-testid="wizard-next"
              :disabled="isBusy"
              @click="goToSessions"
            >
              下一步：关联 Session →
            </button>
          </template>
          <template v-else-if="step === 2">
            <button
              class="btn"
              type="button"
              data-testid="wizard-back"
              :disabled="isBusy"
              @click="backToStep(1)"
            >
              ← 上一步
            </button>
            <button
              class="btn primary"
              type="button"
              data-testid="wizard-step2-next"
              :disabled="!hasAssociatedSessions || isBusy"
              @click="goToPotential"
            >
              下一步：潜在 bad case →
            </button>
          </template>
          <template v-else-if="step === 3">
            <button
              class="btn"
              type="button"
              data-testid="wizard-back"
              :disabled="isBusy"
              @click="backToStep(2)"
            >
              ← 上一步
            </button>
            <button
              class="btn primary"
              type="button"
              data-testid="wizard-step3-next"
              :disabled="!hasPotential || isBusy"
              @click="goToAttribution"
            >
              下一步：归因预览 →
            </button>
          </template>
          <template v-else>
            <button
              class="btn"
              type="button"
              data-testid="wizard-back"
              :disabled="isBusy"
              @click="backToStep(3)"
            >
              ← 上一步
            </button>
            <button
              class="btn accent"
              type="button"
              data-testid="wizard-cluster"
              :disabled="!hasPotential || isBusy"
              @click="launch('cluster_only')"
            >
              仅聚类
            </button>
            <button
              class="btn primary"
              type="button"
              data-testid="wizard-start"
              :disabled="!hasPotential || isBusy"
              @click="launch('full')"
            >
              启动自进化 →
            </button>
          </template>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.evov {
  position: fixed;
  inset: 0;
  background: var(--overlay-scrim);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 48px 16px;
  z-index: 600;
  overflow-y: auto;
}

.modal {
  width: 720px;
  max-width: 100%;
  background: var(--bg-card);
  border-radius: 14px;
  box-shadow: var(--shadow-modal);
  overflow: hidden;
}

.modal-head {
  display: flex;
  align-items: center;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
}

.modal-head h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
}

.modal-head .x {
  margin-left: auto;
  cursor: pointer;
  color: var(--text-faint);
  font-size: 16px;
  border: none;
  background: none;
}

.modal-body {
  padding: 18px;
  max-height: 66vh;
  overflow-y: auto;
}

.modal-foot {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  padding: 13px 18px;
  border-top: 1px solid var(--border);
  background: var(--bg-panel);
}

.btn {
  font: inherit;
  font-size: 12.5px;
  cursor: pointer;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  color: var(--text-dim);
  padding: 6px 14px;
  white-space: nowrap;
}

.btn:hover {
  border-color: var(--border-strong);
  color: var(--text);
}

.btn.primary {
  background: var(--blue);
  border-color: var(--blue);
  color: white;
  font-weight: 600;
}

.btn.accent {
  color: var(--blue);
  border-color: color-mix(in srgb, var(--blue) 45%, transparent);
  background: color-mix(in srgb, var(--blue) 9%, var(--bg-card));
  font-weight: 600;
}

.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.btn.sm {
  padding: 3px 8px;
  font-size: 11px;
}

.wz-loading {
  margin: 0;
  padding: 40px 16px;
  text-align: center;
  color: var(--text-faint);
  font-size: 12.5px;
}

.wz-steps {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 11.5px;
  color: var(--text-faint);
  margin-bottom: 16px;
}

.wz-steps .on {
  color: var(--blue);
  font-weight: 600;
}

.wz-section-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
  margin: 2px 0 10px;
  font-size: 13px;
  font-weight: 650;
  color: var(--text);
}

.wz-section-title span {
  color: var(--text-faint);
  font-size: 11.5px;
  font-weight: 400;
}

.wz-condstrip {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  border: 1px solid var(--border);
  background: var(--bg-panel);
  border-radius: 8px;
  padding: 6px 10px;
  margin-bottom: 12px;
  font-size: 11.5px;
}

.wz-condstrip .chip {
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 1px 8px;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-dim);
}

.wz-condstrip .back {
  margin-left: auto;
}

.v2-badge {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 1px 9px;
  font-size: 11px;
  color: var(--text-dim);
  white-space: nowrap;
}

.v2-badge.ok {
  color: var(--green, var(--blue));
  border-color: color-mix(in srgb, var(--green, var(--blue)) 45%, transparent);
}

.v2-badge.warn {
  color: var(--orange);
  border-color: color-mix(in srgb, var(--orange) 45%, transparent);
}

.f-row {
  margin-bottom: 14px;
}

.f-label {
  font-size: 12px;
  color: var(--text-dim);
  font-weight: 600;
  margin-bottom: 6px;
}

.f-label .req {
  color: var(--red);
}

.f-inline {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.wz-controls {
  align-items: flex-start;
}

.wz-field {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  min-width: 140px;
}

.wz-field .inp {
  width: 100%;
}

.wz-inline-label {
  padding-top: 8px;
  color: var(--text-faint);
  font-size: 12px;
}

.f-note {
  margin: 6px 0 0;
  color: var(--text-faint);
  font-size: 11.5px;
  line-height: 1.6;
}

.f-inline .f-note {
  margin: 6px 0 0;
}

.seg {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.seg button {
  font: inherit;
  font-size: 12.5px;
  padding: 6px 16px;
  border: none;
  background: var(--bg-card);
  color: var(--text-dim);
  cursor: pointer;
}

.seg button.active {
  background: var(--blue);
  color: white;
  font-weight: 600;
}

select.inp,
input.inp {
  font: inherit;
  font-size: 12.5px;
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 10px;
  background: var(--bg-card);
  outline: none;
}

select.inp:focus,
input.inp:focus {
  border-color: var(--blue);
}

.input-error {
  border-color: var(--red);
}

.input-error:focus {
  border-color: var(--red);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--red) 14%, transparent);
}

.field-error {
  margin: 4px 0 0;
  color: var(--red);
  font-size: 12px;
  line-height: 1.45;
}

.cfg-link {
  font: inherit;
  color: var(--blue);
  cursor: pointer;
  border: none;
  background: none;
  padding: 0;
  text-decoration: underline solid;
  text-underline-offset: 2px;
}

.cfg-link:hover {
  color: var(--blue-deep);
  text-decoration-thickness: 2px;
}

.cfg-link:focus-visible {
  outline: 2px solid var(--blue);
  outline-offset: 2px;
}

.policy {
  margin-top: 6px;
  cursor: pointer;
}

.policy label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text);
}

.policy p {
  margin: 3px 0 0 22px;
  color: var(--text-faint);
  font-size: 11.5px;
  line-height: 1.6;
}

.policy-rules {
  display: flex;
  gap: 6px 16px;
  flex-wrap: wrap;
  margin: 6px 0 0 24px;
}

.switch-row {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-dim);
}

.wz-demo {
  border: 1px solid color-mix(in srgb, var(--blue) 35%, transparent);
  background: color-mix(in srgb, var(--blue) 6%, transparent);
  border-radius: 8px;
  padding: 8px 12px;
  margin-bottom: 12px;
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1.6;
}

.wz-stats {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.wz-stats .st b {
  font-family: var(--mono);
  font-weight: 650;
  font-size: 14px;
  margin-right: 3px;
}

.wz-stats .st span {
  color: var(--text-faint);
  font-size: 11px;
}

.wz-stats .st.accent b {
  color: var(--blue);
}

.rep-scroll {
  margin-top: 10px;
  overflow-x: auto;
  overscroll-behavior-x: contain;
}

table.rep {
  width: 100%;
  min-width: 620px;
  border-collapse: collapse;
  font-size: 12px;
}

table.rep th,
table.rep td {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

table.rep th {
  font-size: 11px;
  color: var(--text-faint);
  font-weight: 600;
}

.cell-sub {
  display: block;
  margin-top: 2px;
  color: var(--text-faint);
  font-size: 10.5px;
}

.linklike {
  font: inherit;
  color: var(--blue);
  cursor: pointer;
  border: none;
  background: none;
  border-bottom: 1px dashed color-mix(in srgb, var(--blue) 50%, transparent);
  padding: 0;
}

.mono {
  font-family: var(--mono);
}

.hit-reason {
  color: var(--text-dim);
}

.order-note {
  display: block;
  margin-top: 2px;
  color: var(--text-faint);
  font-size: 10.5px;
  white-space: normal;
}

.pager {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}

.pager-info {
  font-size: 11.5px;
  color: var(--text-dim);
}

.pager-info b {
  font-family: var(--mono);
}

.pager .btn {
  padding: 3px 12px;
  font-size: 11.5px;
}

.cache-option {
  display: flex;
  align-items: center;
  gap: 14px;
  justify-content: space-between;
  border: 1px solid color-mix(in srgb, var(--blue) 28%, transparent);
  border-radius: 8px;
  padding: 11px 13px;
  margin-bottom: 12px;
  background: color-mix(in srgb, var(--blue) 5%, var(--bg-card));
  font-size: 12.5px;
}

.preview-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.preview-stat {
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-panel);
  padding: 10px 12px;
}

.preview-stat strong {
  display: block;
  font-family: var(--mono);
  font-size: 17px;
  color: var(--text);
}

.preview-stat span {
  display: block;
  margin-top: 1px;
  color: var(--text-faint);
  font-size: 10px;
}

.notice {
  margin: 4px 0 8px;
  color: var(--text-dim);
  font-size: 11.5px;
  line-height: 1.6;
}

.switch {
  position: relative;
  display: inline-flex;
  width: 40px;
  height: 20px;
  flex: none;
}

.switch input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.switch .slider {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: var(--border);
  transition: background 0.15s ease;
}

.switch .slider::before {
  content: "";
  position: absolute;
  width: 16px;
  height: 16px;
  left: 2px;
  top: 2px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 3px rgba(30, 40, 60, 0.18);
  transition: transform 0.15s ease;
}

.switch input:checked + .slider {
  background: var(--blue);
}

.switch input:checked + .slider::before {
  transform: translateX(20px);
}

.wizard-error {
  margin: 10px 0 0;
  color: var(--red);
  font-size: 12px;
  line-height: 1.5;
}

.wz-empty {
  display: grid;
  place-items: center;
  min-height: 218px;
  padding: 24px 18px;
  border: 1px dashed color-mix(in srgb, var(--border) 72%, var(--text-faint));
  border-radius: 10px;
  text-align: center;
  background: color-mix(in srgb, var(--bg-panel) 58%, transparent);
}

.wz-empty-icon {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  margin: 0 auto 10px;
  border-radius: 50%;
  color: var(--text-faint);
  background: var(--bg-panel);
  border: 1px solid var(--border);
  font-size: 17px;
}

.wz-empty h3 {
  margin: 0;
  color: var(--text);
  font-size: 15px;
}

.wz-empty p {
  max-width: 390px;
  margin: 7px auto 0;
  color: var(--text-faint);
  font-size: 12px;
  line-height: 1.65;
}

.wz-empty .btn {
  margin-top: 12px;
}

@media (max-width: 640px) {
  .evov {
    padding: 16px 12px;
  }

  .modal-body {
    max-height: none;
    padding: 14px;
  }

  .modal-foot {
    flex-wrap: wrap;
  }

  .wz-stats {
    gap: 10px 16px;
  }

  .preview-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
