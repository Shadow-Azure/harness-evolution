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
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";

import { getBadCase } from "../../../api/badCases";
import { useAttributionSkillPackages } from "../../../composables/useAttributionSkillPackages";
import { getTargetAttributionSkill } from "../../../api/attributionSkills";
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
type PreviewAction = "sessions" | "potential" | "attribution";
type PreviewFromStep = 1 | 2 | 3;

interface PreviewStage {
  label: string;
  detail: string;
}

interface PreviewBusy {
  fromStep: PreviewFromStep;
  failed: boolean;
  elapsed: number;
  timeoutMessage: string;
}

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

const ANCHOR_SOURCE_LABELS: Record<
  PotentialPreviewItem["anchorSource"],
  string
> = {
  event: "事件锚点",
  node: "节点锚点",
  post_process: "后处理上报",
  unknown: "锚点未知",
};

const ANCHOR_SOURCE_HINTS: Record<
  PotentialPreviewItem["anchorSource"],
  string
> = {
  event: "bad case 命中上报 Agent 的触发事件。",
  node: "bad case 挂在 Agent 节点上，没有事件下标。",
  post_process: "上报对象没有可定位的触发事件，按 post-process 锚点参与归因。",
  unknown: "上报 Agent 无法解析，锚点位置未知。",
};

const CONTENT_REASON_COPY: Record<string, string> = {
  content_not_found:
    "在该版本下找不到目标文件（skill 需 SKILL.md，agent 需 AGENT.md）。请确认版本、仓库地址与子目录。",
  file_not_found:
    "该版本下没有目标文件（skill 需 SKILL.md，agent 需 AGENT.md）。请检查子目录。",
  ref_not_found:
    "该版本在仓库中不存在。请确认 tag、分支或 commit id，或换一个版本后重试。",
  repo_unreachable:
    "无法访问目标仓库。请检查仓库地址、网络与读取权限。",
  empty_definition_body:
    "目标文件内容为空，无法计算 body hash。请换一个包含有效内容的版本。",
  content_timeout:
    "读取目标文件超时。请稍后重试，或检查仓库网络与代理。",
  timeout: "读取目标文件超时。请稍后重试，或检查仓库网络与代理。",
  git_unavailable: "服务端无法调用 git。请联系管理员检查运行环境。",
  path_invalid: "目标文件路径无效。请检查配置的子目录。",
  ref_invalid: "版本名不是合法的 git ref。请重新输入 tag、分支或 commit id。",
  content_unavailable:
    "目标文件暂时不可读取。请确认仓库地址、子目录与读取权限后重试。",
  knowledge_content_source_unavailable:
    "服务端尚未配置知识库内容来源，无法解析该版本。",
  unsupported_object_type: "当前对象类型不支持内容解析。",
};

const auth = useAuthStore();
const router = useRouter();

const step = ref<WizardStep>(1);
const targetType = ref<"skill" | "agent">("skill");
const targetId = ref<string | null>(null);
const targetVersion = ref("");
const versionPinned = ref(false);
const versionOpen = ref(false);
const versionFormatError = ref("");
const windowFrom = ref("");
const windowTo = ref("");
const policyPreset = ref<"default" | "custom">("default");
const includeSelfReport = ref(true);
const includeAfterObject = ref(true);
const sameObjectOnly = ref(false);
const cacheEnabled = ref(true);
const library = useAttributionSkillPackages(() => props.wid);
const overridePackage = ref("");
watch(() => [props.wid, targetId.value], () => { overridePackage.value = ""; });

const sessionPreview = ref<SessionPreviewResult | null>(null);
const sessionEmptySummary = ref<SessionPreviewSummary | null>(null);
const potentialPreview = ref<PotentialPreviewResult | null>(null);
const potentialEmpty = ref(false);
const attributionPreview = ref<AttributionPreviewResult | null>(null);
const sessionPage = ref(1);
const potentialPage = ref(1);
const pending = ref<PendingAction>("");
const previewBusy = ref<PreviewBusy | null>(null);
const previewCard = ref<HTMLElement | null>(null);
const requestError = ref("");
const launchError = ref("");
const contentUnresolved = ref(false);
const contentError = ref("");
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

/**
 * Incremented whenever a preview starts or is cancelled. A response may only
 * apply state when its captured generation still matches, because the shared
 * transport has no abort support.
 */
let previewGeneration = 0;
let elapsedTimer: ReturnType<typeof setInterval> | null = null;

/**
 * The server runs the mirror clone and Session matching inside one request and
 * never reports substage progress. Keep the first stage current for the whole
 * request instead of faking a transition to the second stage.
 */
const PREVIEW_CURRENT_STAGE = 0;

const workspaceName = computed(
  () => auth.workspaceById(props.wid)?.name ?? "当前空间",
);

/** Treat Escape like the overlay click so the dialog can be dismissed from the keyboard. */
function handleKeydown(event: KeyboardEvent): void {
  if (event.key !== "Escape") {
    return;
  }
  event.preventDefault();
  if (versionOpen.value) {
    versionOpen.value = false;
    return;
  }
  emit("close");
}

/** Close the version suggestions when a click lands outside the combobox. */
function handleDocumentClick(event: MouseEvent): void {
  if (!versionOpen.value) {
    return;
  }
  const target = event.target;
  if (target instanceof Element && target.closest(".wz-version-combo")) {
    return;
  }
  versionOpen.value = false;
}

onMounted(() => {
  triggerElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  window.addEventListener("keydown", handleKeydown);
  document.addEventListener("click", handleDocumentClick);
  closeButton.value?.focus();
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleKeydown);
  document.removeEventListener("click", handleDocumentClick);
  stopElapsedTimer();
  previewGeneration += 1;
  if (triggerElement?.isConnected) {
    triggerElement.focus();
  }
  triggerElement = null;
});

watch(
  () => [Boolean(previewBusy.value), previewBusy.value?.failed] as const,
  async () => {
    if (!previewBusy.value) {
      return;
    }
    await nextTick();
    previewCard.value?.scrollIntoView?.({ block: "nearest" });
  },
);

const catalogs = useQuery({
  queryKey: computed(() => queryKeys.targetCatalog(props.wid)),
  queryFn: () => getTargetCatalog(props.wid),
});
const versions = useEvolutionTargetVersions(
  computed(() => props.wid),
  computed(() => (step.value === 1 ? targetId.value : null)),
);
const effectiveSkill = useQuery({
  queryKey: computed(() =>
    queryKeys.targetAttributionSkill(props.wid, targetId.value ?? "empty"),
  ),
  queryFn: () => getTargetAttributionSkill(props.wid, targetId.value as string),
  enabled: computed(() => Boolean(targetId.value)),
  retry: false,
});
const selectedPackage = computed({
  get: () => overridePackage.value || library.packages.data.value?.items.find(
    item => item.id === effectiveSkill.data.value?.id,
  )?.id || "",
  set: (id: string) => { overridePackage.value = id; },
});
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
const versionSuggestions = computed(() => {
  const values: string[] = [];
  const remoteDefault =
    versions.data.value?.defaultRef || selectedTarget.value?.defaultRef;
  if (remoteDefault) {
    values.push(remoteDefault);
  }
  const options = versions.data.value?.versions.length
    ? versions.data.value.versions
    : selectedTarget.value?.versions ?? [];
  for (const version of options) {
    if (!values.includes(version)) {
      values.push(version);
    }
  }
  return values;
});

/**
 * Pick the default version for the current target.
 * @returns `defaultRef` when present, otherwise the first suggestion.
 */
function defaultVersion(): string {
  const remoteDefault =
    versions.data.value?.defaultRef || selectedTarget.value?.defaultRef;
  if (remoteDefault) {
    return remoteDefault;
  }
  return versionSuggestions.value[0] ?? "";
}

/** Identify whether a suggestion is the configured baseline or a tag. */
function versionKind(version: string): string {
  const tags = versions.data.value?.versions.length
    ? versions.data.value.versions
    : selectedTarget.value?.versions ?? [];
  return tags.includes(version) ? "tag" : "基线";
}

/** Toggle the tag suggestion menu without losing a typed value. */
function toggleVersionMenu(): void {
  versionOpen.value = !versionOpen.value;
}

/** Apply one tag suggestion and mark the field as user-pinned. */
function pickVersion(version: string): void {
  targetVersion.value = version;
  versionPinned.value = true;
  versionOpen.value = false;
  fieldErrors.version = false;
  clearContentUnresolved();
}

/** Mark a typed ref as intentional so async suggestions cannot overwrite it. */
function onVersionInput(): void {
  versionPinned.value = true;
}

watch(
  versionSuggestions,
  () => {
    if (versionPinned.value && targetVersion.value) {
      return;
    }
    targetVersion.value = defaultVersion();
    versionPinned.value = false;
  },
  { immediate: true },
);

watch(targetId, () => {
  fieldErrors.target = false;
  clearContentUnresolved();
});
watch(targetVersion, () => {
  fieldErrors.version = false;
  versionFormatError.value = "";
  clearContentUnresolved();
  if (sessionPreview.value || potentialPreview.value || attributionPreview.value) {
    resetDownstream();
  }
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
const previewInFlight = computed(
  () => Boolean(previewBusy.value && !previewBusy.value.failed),
);
const formLocked = computed(() => previewInFlight.value);
const nextButtonTestId = computed(() => {
  switch (previewBusy.value?.fromStep) {
    case 2:
      return "wizard-step2-next";
    case 3:
      return "wizard-step3-next";
    default:
      return "wizard-next";
  }
});

const previewStages = computed<PreviewStage[]>(() => {
  const fromStep = previewBusy.value?.fromStep ?? 1;
  if (fromStep === 1) {
    return [
      {
        label: "读取目标版本",
        detail:
          "读取 SKILL.md / AGENT.md 并计算 body hash；缓存为空时先从远程仓库克隆。",
      },
      {
        label: "关联 Session",
        detail: `在 ${windowFrom.value} ~ ${windowTo.value} 内匹配对象出现过的 Session。`,
      },
    ];
  }
  if (fromStep === 2) {
    return [
      {
        label: "筛选潜在 bad case",
        detail: "按当前策略过滤关联 Session 中的 bad case。",
      },
    ];
  }
  return [
    {
      label: "检查归因缓存",
      detail: "只读检查该对象版本已有的归因结果。",
    },
  ];
});
const currentPreviewStage = computed(
  () => previewStages.value[PREVIEW_CURRENT_STAGE] ?? previewStages.value[0],
);
const previewHeading = computed(() => {
  const stage = currentPreviewStage.value;
  const busy = previewBusy.value;
  if (!stage || !busy) {
    return "";
  }
  return busy.failed
    ? `${stage.label}超时`
    : `正在准备第 ${busy.fromStep + 1} 步 · ${stage.label}`;
});
const previewLead = computed(() => {
  const busy = previewBusy.value;
  if (!busy) {
    return "";
  }
  if (busy.failed) {
    return `${busy.timeoutMessage} 服务端读取达到上限，未能读完目标文件；这不是 Session 数据为空。`;
  }
  return busy.fromStep === 1
    ? "先读取目标版本内容并计算 body hash（缓存为空时会从远程仓库克隆），再在所选时间段内关联 Session。通常 2–5 秒；首次读取需要先克隆仓库，服务端单次读取上限约 20 秒，超时会给出重试。"
    : "这一步只读预览，不会写入或启动运行。完成后自动进入下一步。";
});
const previewHint = computed(() =>
  previewBusy.value?.failed
    ? "排查：确认版本、仓库地址与子目录；也可以换一个版本。首次成功读取后服务端会缓存 mirror，重试通常更快。"
    : "可以取消等待并修改条件；启动前不会写入归因。",
);
const previewButtonLabel = computed(() => {
  const stage = currentPreviewStage.value;
  return stage ? `正在${stage.label}…` : "正在准备…";
});
const previewStageRows = computed(() => {
  const failed = previewBusy.value?.failed ?? false;
  return previewStages.value.map((stage, index) => {
    const state =
      failed && index === PREVIEW_CURRENT_STAGE
        ? "failed"
        : index < PREVIEW_CURRENT_STAGE
          ? "done"
          : index === PREVIEW_CURRENT_STAGE
            ? "current"
            : "pending";
    return {
      ...stage,
      state,
      stateLabel:
        state === "done"
          ? "完成"
          : state === "current"
            ? "进行中"
            : state === "failed"
              ? "超时"
              : "等待",
    };
  });
});
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
const canRecompute = computed(() => attributionPreview.value?.canRecompute === true);
const attributionSummary = computed(() => attributionPreview.value?.summary ?? null);
const canLaunch = computed(() => {
  if (!hasPotential.value || isBusy.value || requestError.value) return false;
  if (cacheEnabled.value) return (attributionSummary.value?.reused ?? 0) > 0;
  return canRecompute.value && Boolean(selectedPackage.value);
});
const previewTargetRevision = computed<string | null | undefined>(() => {
  const revisions = [
    attributionPreview.value?.targetRevision,
    potentialPreview.value?.targetRevision,
    sessionPreview.value?.targetRevision,
  ];
  const revision = revisions.find(
    (value) => typeof value === "string" && value.length > 0,
  );
  if (revision) {
    return revision;
  }
  return attributionPreview.value || potentialPreview.value || sessionPreview.value
    ? null
    : undefined;
});

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
    caseData.objectVersion ||
    target.defaultRef ||
    target.versions[0] ||
    "";
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
  versionOpen.value = false;
  resetDownstream();
}

/** Record the chosen target id and reset its dependent version. */
function selectTargetId(id: string): void {
  targetId.value = id || null;
  targetVersion.value = "";
  versionPinned.value = false;
  versionOpen.value = false;
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

/** Return a local git-ref format error, matching the server's safe-ref rules. */
function versionRefFormatError(value: string): string {
  const ref = value.trim();
  if (!ref) {
    return "请选择或输入版本";
  }
  if (ref.length > 96) {
    return "版本不能超过 96 个字符";
  }
  if (ref.startsWith("-") || ref.startsWith("/")) {
    return "版本不能以 - 或 / 开头";
  }
  if (ref.endsWith("/") || ref.endsWith(".") || ref.endsWith(".lock")) {
    return "版本不能以 /、. 或 .lock 结尾";
  }
  if (ref.includes("..") || ref.includes("@{") || ref.includes("//")) {
    return "版本不是合法的 git ref";
  }
  const reserved = "~^:?*[\\";
  if (
    Array.from(ref).some(
      (char) =>
        /\s/.test(char) || reserved.includes(char) || char.charCodeAt(0) < 0x20,
    )
  ) {
    return "版本不能包含空格或 git ref 保留字符";
  }
  return "";
}

/** Build the shared preview/launch condition from the current step-1 form. */
function condition() {
  return {
    targetType: targetType.value,
    targetName: selectedTarget.value?.name ?? "",
    targetVersion: targetVersion.value.trim() || undefined,
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
  versionFormatError.value = versionRefFormatError(targetVersion.value);
  fieldErrors.target = !selectedTarget.value;
  fieldErrors.version =
    Boolean(versionFormatError.value) || contentUnresolved.value;
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

/** Clear the target-content failure once the user changes or retries the version. */
function clearContentUnresolved(): void {
  contentUnresolved.value = false;
  contentError.value = "";
  if (previewBusy.value?.failed) {
    stopElapsedTimer();
    previewBusy.value = null;
  }
}

/** Read the stable reason string carried by a target-content failure. */
function contentFailureReason(error: unknown): string {
  const details =
    error instanceof ApiError &&
    error.details &&
    typeof error.details === "object" &&
    !Array.isArray(error.details)
      ? (error.details as { reason?: unknown })
      : null;
  return typeof details?.reason === "string" ? details.reason : "";
}

/**
 * Only timeout reasons use the failed progress card; every other content
 * failure keeps the existing inline version-field error.
 */
function isContentTimeout(error: unknown): boolean {
  if (!hasCode(error, "TARGET_CONTENT_UNRESOLVED")) {
    return false;
  }
  const reason = contentFailureReason(error);
  return reason === "content_timeout" || reason === "timeout";
}

/** Build actionable copy from a `TARGET_CONTENT_UNRESOLVED` reason. */
function contentUnresolvedMessage(error: unknown): string {
  const reason = contentFailureReason(error);
  return (
    CONTENT_REASON_COPY[reason] ??
    "服务端无法把所选版本解析为 body hash。请确认 tag、仓库地址与子目录；也可换一个版本后重试。"
  );
}

/** Format elapsed seconds, switching to minutes once a wait passes one minute. */
function formatElapsed(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  if (total < 60) {
    return `${total} 秒`;
  }
  return `${Math.floor(total / 60)} 分 ${String(total % 60).padStart(2, "0")} 秒`;
}

/** Stop the one-second elapsed ticker if it is running. */
function stopElapsedTimer(): void {
  if (elapsedTimer !== null) {
    clearInterval(elapsedTimer);
    elapsedTimer = null;
  }
}

/** Tick the elapsed counter once per second while a preview is in flight. */
function startElapsedTimer(): void {
  stopElapsedTimer();
  elapsedTimer = setInterval(() => {
    if (previewBusy.value && !previewBusy.value.failed) {
      previewBusy.value.elapsed += 1;
    }
  }, 1000);
}

/**
 * Start one forward preview and return its generation token.
 * @param fromStep Step the user is waiting on.
 * @param action Preview endpoint being called.
 * @returns The generation that may still apply the response.
 */
function beginPreview(fromStep: PreviewFromStep, action: PreviewAction): number {
  previewGeneration += 1;
  const generation = previewGeneration;
  stopElapsedTimer();
  previewBusy.value = {
    fromStep,
    failed: false,
    elapsed: 0,
    timeoutMessage: "",
  };
  pending.value = action;
  requestError.value = "";
  startElapsedTimer();
  return generation;
}

/**
 * Settle a preview only when it is still the active generation. A cancelled
 * request may resolve later and must never advance the wizard or clear a newer
 * request's pending state.
 * @param generation Token returned by {@link beginPreview}.
 */
function finishPreview(generation: number): void {
  if (generation !== previewGeneration) {
    return;
  }
  pending.value = "";
  stopElapsedTimer();
  if (previewBusy.value && !previewBusy.value.failed) {
    previewBusy.value = null;
  }
}

/** Cancel the wait, keep the current step and its values, and ignore late results. */
function cancelPreview(): void {
  previewGeneration += 1;
  stopElapsedTimer();
  previewBusy.value = null;
  pending.value = "";
}

/**
 * Turn a content-resolver 422 into an actionable version-field failure, or a
 * failed progress card when the reason is a timeout and a preview was running.
 * @param error Failure raised by the shared API transport.
 * @returns Whether the failure is a target-content 422.
 */
function handleContentUnresolved(error: unknown): boolean {
  if (!hasCode(error, "TARGET_CONTENT_UNRESOLVED")) {
    return false;
  }
  const timeoutCard = isContentTimeout(error) && previewBusy.value !== null;
  step.value = 1;
  contentUnresolved.value = true;
  contentError.value = contentUnresolvedMessage(error);
  fieldErrors.version = !timeoutCard;
  sessionPreview.value = null;
  sessionEmptySummary.value = null;
  potentialPreview.value = null;
  potentialEmpty.value = false;
  attributionPreview.value = null;
  requestError.value = "";
  launchError.value = "";
  if (timeoutCard && previewBusy.value) {
    // Content resolution always belongs to step 1's target read, even when a
    // later preview surfaced it; keep the failed card on that stage.
    previewBusy.value.fromStep = 1;
    previewBusy.value.failed = true;
    previewBusy.value.timeoutMessage = contentError.value;
    stopElapsedTimer();
  }
  return true;
}

/** Retry the preview after a transient content-resolution failure. */
function retryContentResolution(): void {
  clearContentUnresolved();
  fieldErrors.version = false;
  void goToSessions();
}

/** Dismiss the timeout card and keep the user on step 1 with the form editable. */
function returnToEditing(): void {
  previewGeneration += 1;
  stopElapsedTimer();
  previewBusy.value = null;
  pending.value = "";
  clearContentUnresolved();
  fieldErrors.version = false;
  step.value = 1;
  requestError.value = "";
}

/** Run the Session association preview and advance to step 2. */
async function goToSessions(): Promise<void> {
  if (!validateStep1()) {
    versionOpen.value = false;
    return;
  }
  versionOpen.value = false;
  const generation = beginPreview(1, "sessions");
  try {
    const result = await previewSessions(props.wid, {
      ...condition(),
      page: 1,
      pageSize: SESSION_PAGE_SIZE,
    });
    if (generation !== previewGeneration) return;
    sessionPreview.value = result;
    sessionEmptySummary.value = null;
    sessionPage.value = result.page;
    potentialPreview.value = null;
    potentialEmpty.value = false;
    attributionPreview.value = null;
    step.value = 2;
  } catch (error) {
    if (generation !== previewGeneration) return;
    if (handleContentUnresolved(error)) return;
    if (hasCode(error, "NO_ASSOCIATED_SESSIONS")) {
      sessionPreview.value = null;
      sessionEmptySummary.value = conflictSessionSummary(error);
      sessionPage.value = 1;
      step.value = 2;
      return;
    }
    requestError.value = formatApiError(error, "加载 Session 关联失败").message;
  } finally {
    finishPreview(generation);
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
    if (handleContentUnresolved(error)) return;
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
  const generation = beginPreview(2, "potential");
  try {
    const result = await previewPotential(props.wid, {
      ...condition(),
      policy: currentPolicy(),
      page: 1,
      pageSize: POTENTIAL_PAGE_SIZE,
    });
    if (generation !== previewGeneration) return;
    potentialPreview.value = result;
    potentialEmpty.value = false;
    potentialPage.value = result.page;
    attributionPreview.value = null;
    step.value = 3;
  } catch (error) {
    if (generation !== previewGeneration) return;
    if (handleContentUnresolved(error)) return;
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
    finishPreview(generation);
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
    if (handleContentUnresolved(error)) return;
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
  const generation = beginPreview(3, "attribution");
  try {
    const result = await previewAttribution(props.wid, {
      ...condition(),
      policy: currentPolicy(),
      cacheEnabled: cacheEnabled.value,
    });
    if (generation !== previewGeneration) return;
    attributionPreview.value = result;
    step.value = 4;
  } catch (error) {
    if (generation !== previewGeneration) return;
    if (handleContentUnresolved(error)) return;
    if (hasCode(error, "NO_POTENTIAL_MATCHED")) {
      potentialPreview.value = null;
      potentialEmpty.value = true;
      step.value = 3;
      return;
    }
    requestError.value = formatApiError(error, "加载归因预览失败").message;
  } finally {
    finishPreview(generation);
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
    if (handleContentUnresolved(error)) return;
    requestError.value = formatApiError(error, "加载归因预览失败").message;
  } finally {
    pending.value = "";
  }
}

/** Accept one full run or cluster-only preview and leave the wizard. */
async function launch(mode: "full" | "cluster_only"): Promise<void> {
  if (!selectedTarget.value || !canLaunch.value) {
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
      ...(!cacheEnabled.value && { attributionPackageId: selectedPackage.value }),
      page: 1,
      pageSize: POTENTIAL_PAGE_SIZE,
    };
    const accepted =
      mode === "full"
        ? await startEvolutionRun(props.wid, body)
        : await startClusterPreview(props.wid, body);
    emit("launched", mode, accepted.runId);
  } catch (error) {
    if (handleContentUnresolved(error)) return;
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
  versionOpen.value = false;
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

          <div
            v-if="previewBusy"
            ref="previewCard"
            class="wz-progress"
            :class="{ failed: previewBusy.failed }"
            :data-testid="previewBusy.failed ? 'wizard-progress-failed' : 'wizard-progress'"
            :role="previewBusy.failed ? 'alert' : 'status'"
          >
            <div class="wz-progress-head">
              <span
                v-if="previewBusy.failed"
                class="wz-error-mark"
                aria-hidden="true"
              >!</span>
              <span
                v-else
                class="wz-spinner"
                aria-hidden="true"
              />
              <div class="wz-progress-title">
                <b>{{ previewHeading }}</b>
                <span class="wz-progress-sub">{{ previewBusy.failed ? "本次预览未完成，表单内容已保留" : "只读预览，不会写入数据" }}</span>
              </div>
              <span
                class="wz-progress-elapsed"
                data-testid="wizard-elapsed"
                aria-hidden="true"
              >已等待 {{ formatElapsed(previewBusy.elapsed) }}</span>
            </div>
            <p
              :id="previewBusy.failed ? 'wizard-content-error' : undefined"
              class="wz-progress-lead"
            >
              {{ previewLead }}
            </p>
            <ol class="wz-progress-steps">
              <li
                v-for="row in previewStageRows"
                :key="row.label"
                :class="row.state"
                data-testid="wizard-progress-stage"
              >
                <span
                  class="dot"
                  aria-hidden="true"
                >
                  <span
                    v-if="row.state === 'current'"
                    class="wz-spinner"
                  />
                  <template v-else-if="row.state === 'done'">✓</template>
                  <template v-else-if="row.state === 'failed'">!</template>
                </span>
                <div class="wz-progress-stage-body">
                  <b>{{ row.label }}</b>
                  <span>{{ row.detail }}</span>
                </div>
                <span class="state">{{ row.stateLabel }}</span>
              </li>
            </ol>
            <div
              v-if="previewBusy.failed"
              class="wz-progress-actions"
            >
              <button
                class="btn primary"
                type="button"
                data-testid="wizard-progress-retry"
                @click="retryContentResolution"
              >
                重试解析
              </button>
              <button
                class="btn"
                type="button"
                data-testid="wizard-content-back"
                @click="returnToEditing"
              >
                返回修改条件
              </button>
            </div>
            <p class="wz-progress-hint">
              {{ previewHint }}
            </p>
          </div>

          <div
            class="wz-form"
            :class="{ locked: formLocked }"
            :inert="formLocked || undefined"
            data-testid="wizard-form"
          >
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
                    <div class="wz-version-combo">
                      <input
                        v-model="targetVersion"
                        class="inp"
                        :class="{ 'input-error': fieldErrors.version || contentUnresolved }"
                        data-testid="wizard-version"
                        :placeholder="versions.isPending.value ? '读取版本…' : 'tag / 分支名 / commit id'"
                        autocomplete="off"
                        spellcheck="false"
                        role="combobox"
                        aria-controls="wizard-version-menu"
                        :aria-expanded="versionOpen ? 'true' : 'false'"
                        :aria-invalid="fieldErrors.version || contentUnresolved ? 'true' : undefined"
                        :aria-describedby="fieldErrors.version ? 'wizard-version-error' : contentUnresolved ? 'wizard-content-error' : undefined"
                        @input="onVersionInput"
                        @focus="versionOpen = true"
                        @keydown.down.prevent="versionOpen = true"
                      >
                      <button
                        type="button"
                        class="wz-version-toggle"
                        data-testid="wizard-version-toggle"
                        aria-label="展开 tag 建议"
                        @click="toggleVersionMenu"
                      >
                        ▾
                      </button>
                      <ul
                        v-if="versionOpen"
                        id="wizard-version-menu"
                        class="wz-version-menu"
                        data-testid="wizard-version-menu"
                        role="listbox"
                      >
                        <li
                          v-for="version in versionSuggestions"
                          :key="version"
                        >
                          <button
                            type="button"
                            class="wz-version-option"
                            :class="{ current: version === targetVersion }"
                            data-testid="wizard-version-option"
                            role="option"
                            :aria-selected="version === targetVersion ? 'true' : 'false'"
                            @click="pickVersion(version)"
                          >
                            <span class="mono">{{ version }}</span>
                            <span class="wz-version-kind">{{ versionKind(version) }}</span>
                          </button>
                        </li>
                      </ul>
                    </div>
                    <p
                      v-if="fieldErrors.version"
                      id="wizard-version-error"
                      data-testid="wizard-version-error"
                      class="field-error"
                      role="alert"
                    >
                      {{ contentUnresolved ? contentError : versionFormatError || "请选择或输入版本" }}
                      <button
                        v-if="contentUnresolved"
                        class="linklike"
                        type="button"
                        data-testid="wizard-content-retry"
                        @click="retryContentResolution"
                      >
                        重试解析
                      </button>
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
                  版本可直接输入 tag、分支名或 commit id；下拉建议来自当前对象的 tag 与基线。服务端会先用 git 校验该 ref 是否存在，再读取 SKILL.md / AGENT.md 并解析 body hash 作为目标 revision；解析结果可在运行详情查看。只列出当前空间已启用的进化对象；点击<!-- eslint-disable vue/multiline-html-element-content-newline -- 中文句内按钮与前后文字紧邻渲染，不留多余空格 --><button
                    class="cfg-link"
                    type="button"
                    data-testid="wizard-target-config-link"
                    @click="goTargetConfig"
                  >配置页</button><!-- eslint-enable vue/multiline-html-element-content-newline -->调整。
                </p>
              </div>

              <div
                v-if="previewTargetRevision !== undefined"
                class="f-row"
              >
                <div class="f-label">
                  目标 revision
                </div>
                <div class="f-inline">
                  <span
                    v-if="previewTargetRevision"
                    class="revision-chip"
                    data-testid="wizard-target-revision"
                    :title="previewTargetRevision"
                  >{{ targetVersion }} → {{ previewTargetRevision }}</span>
                  <span
                    v-else
                    class="revision-unresolved"
                    data-testid="wizard-target-revision-unresolved"
                  >未解析到 revision：服务端未返回 body hash；请确认 tag、仓库地址与子目录，或换一个版本后重试。</span>
                </div>
                <p class="f-note">
                  只读结果，来自最近一次预览；不会回退到 tag 猜测。
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
                <span
                  v-if="previewTargetRevision !== undefined"
                  class="chip revision"
                  :class="{ unresolved: !previewTargetRevision }"
                  data-testid="wizard-condition-revision"
                  :title="previewTargetRevision ?? '服务端未返回 targetRevision，不猜测 tag'"
                >{{ previewTargetRevision ? `revision ${previewTargetRevision}` : "revision 未解析" }}</span>
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
                <span>先判断对象出现在哪些 Session，只有出现的 Session 才进入下一步</span>
              </div>

              <div class="wz-stats">
                <span class="st"><b>{{ sessionSummary?.reported ?? 0 }}</b><span>上报过 bad case 的 Session</span></span>
                <span class="st accent"><b>{{ sessionSummary?.associated ?? 0 }}</b><span>对象出现 · 已关联</span></span>
                <span class="st"><b>{{ sessionSummary?.skipped ?? 0 }}</b><span>未出现 · 跳过</span></span>
                <span class="st"><b>{{ sessionSummary?.pending ?? 0 }}</b><span>待轨迹同步</span></span>
              </div>

              <template v-if="sessionPreview">
                <div class="rep-scroll">
                  <table
                    class="rep wz-session-table"
                    data-testid="wizard-session-table"
                  >
                    <colgroup>
                      <col class="wz-session-col-title">
                      <col class="wz-session-col-appear">
                      <col class="wz-session-col-trigger">
                      <col class="wz-session-col-cases">
                    </colgroup>
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
                          <b
                            class="wz-session-title"
                            data-testid="wizard-session-title"
                            :title="item.title"
                          >{{ item.short || item.title }}</b>
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
                  只展示对象出现过的 Session；未出现的 Session 已跳过，下一步再按策略筛选潜在 bad case。
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
                  <h3>没有对象出现过的 Session</h3>
                  <p>可回第 1 步调整时间段或选择其他对象后重试。</p>
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
                <span
                  v-if="previewTargetRevision !== undefined"
                  class="chip revision"
                  :class="{ unresolved: !previewTargetRevision }"
                  data-testid="wizard-condition-revision"
                  :title="previewTargetRevision ?? '服务端未返回 targetRevision，不猜测 tag'"
                >{{ previewTargetRevision ? `revision ${previewTargetRevision}` : "revision 未解析" }}</span>
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
                        <th>锚点来源</th>
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
                        <td>
                          <span
                            class="anchor-source"
                            :class="{ post: item.anchorSource === 'post_process' }"
                            :data-anchor-source="item.anchorSource"
                            :title="ANCHOR_SOURCE_HINTS[item.anchorSource]"
                          >{{ ANCHOR_SOURCE_LABELS[item.anchorSource] }}</span>
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
                <span
                  v-if="previewTargetRevision !== undefined"
                  class="chip revision"
                  :class="{ unresolved: !previewTargetRevision }"
                  data-testid="wizard-condition-revision"
                  :title="previewTargetRevision ?? '服务端未返回 targetRevision，不猜测 tag'"
                >{{ previewTargetRevision ? `revision ${previewTargetRevision}` : "revision 未解析" }}</span>
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
                    :disabled="isBusy || (cacheEnabled && !canRecompute)"
                    @change="refreshAttribution"
                  >
                  <span class="slider" />
                </label>
              </div>

              <p
                v-if="attributionPreview && !canRecompute"
                class="f-note"
              >
                当前部署仅支持复用已有报告。管理员配置 HE_ATTRIBUTION_AGENT 后可选择 Skill 重新归因。
              </p>

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

              <div
                class="notice"
                data-testid="wizard-effective-skill"
              >
                <b>已有问题报告</b>
                <p
                  v-for="(count, skill) in attributionSummary?.bySkill"
                  :key="skill"
                >
                  {{ skill }} · {{ count }} 份
                </p>
                <p>尚无报告 {{ attributionSummary?.missing ?? 0 }} 个 Badcase<span v-if="cacheEnabled">，本次跳过</span>。</p>
              </div>
              <label
                v-if="!cacheEnabled && canRecompute"
                class="cache-option"
              >
                本次重算使用的归因 Skill
                <select
                  v-model="selectedPackage"
                  aria-label="本次重算使用的归因 Skill"
                >
                  <option
                    value=""
                    disabled
                  >请选择空间内的归因 Skill</option>
                  <option
                    v-for="item in library.packages.data.value?.items"
                    :key="item.id"
                    :value="item.id"
                  >{{ item.skillName }}</option>
                </select>
              </label>

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
        </div>

        <div class="modal-foot">
          <template v-if="previewInFlight">
            <button
              class="btn"
              type="button"
              data-testid="wizard-cancel-wait"
              @click="cancelPreview"
            >
              取消等待
            </button>
            <button
              class="btn primary"
              type="button"
              :data-testid="nextButtonTestId"
              disabled
            >
              <span
                class="wz-spinner"
                aria-hidden="true"
              />
              {{ previewButtonLabel }}
            </button>
          </template>
          <template v-else-if="step === 1">
            <button
              class="btn primary"
              type="button"
              data-testid="wizard-next"
              :disabled="isBusy || contentUnresolved"
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
              :disabled="!canLaunch"
              @click="launch('cluster_only')"
            >
              仅聚类
            </button>
            <button
              class="btn primary"
              type="button"
              data-testid="wizard-start"
              :disabled="!canLaunch"
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

.wz-form.locked {
  opacity: 0.55;
  pointer-events: none;
  user-select: none;
}

.wz-spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  flex: none;
  border-radius: 50%;
  border: 2px solid color-mix(in srgb, var(--blue) 25%, transparent);
  border-top-color: var(--blue);
  animation: wz-spin 0.7s linear infinite;
}

@keyframes wz-spin {
  to {
    transform: rotate(360deg);
  }
}

.wz-progress {
  max-width: 100%;
  margin-bottom: 14px;
  padding: 12px 14px;
  border: 1px solid color-mix(in srgb, var(--blue) 28%, var(--border));
  border-radius: 10px;
  background: color-mix(in srgb, var(--blue) 5%, var(--bg-card));
  overflow-wrap: anywhere;
}

.wz-progress.failed {
  border-color: color-mix(in srgb, var(--red) 35%, var(--border));
  background: color-mix(in srgb, var(--red) 5%, var(--bg-card));
}

.wz-progress-head {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  flex-wrap: wrap;
}

.wz-progress-head .wz-spinner {
  margin-top: 3px;
}

.wz-error-mark {
  display: grid;
  width: 18px;
  height: 18px;
  flex: none;
  margin-top: 1px;
  place-items: center;
  border: 1px solid color-mix(in srgb, var(--red) 45%, var(--border));
  border-radius: 50%;
  background: color-mix(in srgb, var(--red) 8%, var(--bg-card));
  color: var(--red);
  font-size: 10px;
}

.wz-progress-title {
  min-width: 0;
}

.wz-progress-title b {
  display: block;
  font-size: 12.5px;
  color: var(--text);
}

.wz-progress.failed .wz-progress-title b {
  color: var(--red);
}

.wz-progress-sub {
  display: block;
  margin-top: 2px;
  color: var(--text-faint);
  font-size: 11px;
  line-height: 1.5;
}

.wz-progress-elapsed {
  margin-left: auto;
  color: var(--text-dim);
  font-size: 11px;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.wz-progress-lead {
  margin: 8px 0 0 21px;
  color: var(--text-dim);
  font-size: 11.5px;
  line-height: 1.6;
}

.wz-progress-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
}

.wz-progress-steps li {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  color: var(--text-faint);
  font-size: 11.5px;
  line-height: 1.5;
}

.wz-progress-stage-body {
  min-width: 0;
}

.wz-progress-steps li b {
  display: block;
  color: var(--text-dim);
  font-weight: 600;
}

.wz-progress-steps li.current b,
.wz-progress-steps li.done b {
  color: var(--text);
}

.wz-progress-steps li .state {
  margin-left: auto;
  color: var(--text-faint);
  font-size: 10.5px;
  white-space: nowrap;
}

.wz-progress-steps li.current .state {
  color: var(--blue);
}

.wz-progress-steps li.done .state {
  color: var(--green);
}

.wz-progress-steps li.failed b,
.wz-progress-steps li.failed .state {
  color: var(--red);
}

.wz-progress-steps .dot {
  display: grid;
  width: 16px;
  height: 16px;
  flex: none;
  margin-top: 1px;
  place-items: center;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--bg-card);
  color: var(--text-faint);
  font-size: 9px;
}

.wz-progress-steps li.done .dot {
  border-color: color-mix(in srgb, var(--green) 45%, var(--border));
  background: color-mix(in srgb, var(--green) 10%, var(--bg-card));
  color: var(--green);
}

.wz-progress-steps li.current .dot {
  border-color: color-mix(in srgb, var(--blue) 45%, var(--border));
  background: color-mix(in srgb, var(--blue) 8%, var(--bg-card));
}

.wz-progress-steps li.failed .dot {
  border-color: color-mix(in srgb, var(--red) 45%, var(--border));
  background: color-mix(in srgb, var(--red) 8%, var(--bg-card));
  color: var(--red);
}

.wz-progress-steps .dot .wz-spinner {
  width: 10px;
  height: 10px;
  border-width: 2px;
}

.wz-progress-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin: 10px 0 0 21px;
}

.wz-progress-actions .btn {
  font-size: 11.5px;
  padding: 5px 12px;
}

.wz-progress-hint {
  margin: 9px 0 0 21px;
  color: var(--text-faint);
  font-size: 11px;
  line-height: 1.55;
}

.btn .wz-spinner {
  margin-right: 6px;
  vertical-align: -2px;
}

.btn.primary .wz-spinner {
  border-color: color-mix(in srgb, white 35%, transparent);
  border-top-color: white;
}

@media (prefers-reduced-motion: reduce) {
  .wz-spinner {
    animation: none;
  }

  .switch .slider,
  .switch .slider::before {
    transition: none;
  }
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

.wz-condstrip .chip.revision {
  border-color: color-mix(in srgb, var(--purple) 32%, var(--border));
  background: color-mix(in srgb, var(--purple) 6%, transparent);
  color: var(--purple);
  overflow-wrap: anywhere;
}

.wz-condstrip .chip.revision.unresolved {
  border-color: color-mix(in srgb, var(--orange) 38%, var(--border));
  background: color-mix(in srgb, var(--orange) 7%, transparent);
  color: var(--orange);
}

.revision-chip {
  display: inline-block;
  max-width: 100%;
  padding: 1px 9px;
  border: 1px solid color-mix(in srgb, var(--purple) 32%, var(--border));
  border-radius: 999px;
  background: color-mix(in srgb, var(--purple) 6%, transparent);
  color: var(--purple);
  font-family: var(--mono);
  font-size: 11px;
  overflow-wrap: anywhere;
}

.revision-unresolved {
  color: var(--orange);
  font-size: 11.5px;
  line-height: 1.55;
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

.wz-version-combo {
  position: relative;
  width: 100%;
}

.wz-version-combo .inp {
  width: 100%;
  padding-right: 30px;
}

.wz-version-toggle {
  position: absolute;
  top: 50%;
  right: 3px;
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-faint);
  font-size: 12px;
  cursor: pointer;
  transform: translateY(-50%);
}

.wz-version-toggle:hover {
  background: var(--bg-panel);
  color: var(--text);
}

.wz-version-menu {
  position: absolute;
  z-index: 20;
  top: calc(100% + 4px);
  right: 0;
  left: 0;
  max-height: 190px;
  margin: 0;
  padding: 4px;
  overflow-y: auto;
  list-style: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  box-shadow: var(--shadow-popover);
}

.wz-version-option {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 5px 7px;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.wz-version-option:hover,
.wz-version-option.current {
  background: color-mix(in srgb, var(--blue) 10%, transparent);
}

.wz-version-kind {
  margin-left: auto;
  color: var(--text-faint);
  font-size: 10.5px;
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

.wz-session-table {
  table-layout: fixed;
}

.wz-session-col-title {
  width: 38%;
}

.wz-session-col-appear {
  width: 15%;
}

.wz-session-col-trigger {
  width: 22%;
}

.wz-session-col-cases {
  width: 25%;
}

table.rep.wz-session-table th {
  white-space: normal;
}

.wz-session-title {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

.anchor-source {
  display: inline-block;
  padding: 1px 7px;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-faint);
  font-size: 10.5px;
  white-space: nowrap;
}

.anchor-source.post {
  border-color: color-mix(in srgb, var(--orange) 38%, var(--border));
  background: color-mix(in srgb, var(--orange) 7%, transparent);
  color: var(--orange);
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
  background: var(--bg-card);
  box-shadow: 0 1px 3px color-mix(in srgb, var(--text) 18%, transparent);
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
