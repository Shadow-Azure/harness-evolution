<script setup lang="ts">
import type {
  ProbePreviewItem,
  ProbeQueryRequest,
  ProbeQueryResult,
} from "@harness/contracts";
import { useQuery } from "@tanstack/vue-query";
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";

import {
  queryProbeHits,
  startClusterPreview,
  startEvolutionRun,
} from "../../../api/evolutionRuns";
import { getModelCatalog, getTargetCatalog } from "../../../api/catalogs";
import { queryKeys } from "../../../api/queryKeys";
import { useEvolutionTargetVersions } from "../../../composables/useEvolutionTargets";

const emit = defineEmits<{
  close: [];
  launched: [mode: "full" | "cluster_only", runId: string];
}>();

type AttributeKey = "model" | "prompt" | "error" | "nonIssue";

const WIZARD_PAGE_SIZE = 8;
const SHORT_ID_HEAD = 4;
const SHORT_ID_TAIL = 4;
const SHORT_ID_MIN_LENGTH = SHORT_ID_HEAD + SHORT_ID_TAIL + 1;
const ATTRIBUTE_LABELS: Record<AttributeKey, string> = {
  model: "是问题-模型问题",
  prompt: "是问题-prompt缺失某些提示词",
  error: "是问题-错误",
  nonIssue: "非问题",
};
const ATTRIBUTE_COLORS: Record<AttributeKey, string> = {
  model: "var(--purple)",
  prompt: "var(--orange)",
  error: "var(--red)",
  nonIssue: "var(--text-faint)",
};

const router = useRouter();

const step = ref<1 | 2>(1);
const targetType = ref<"skill" | "agent">("skill");
const targetId = ref<string | null>(null);
const targetVersion = ref("");
const versionPinned = ref(false);
const windowFrom = ref("");
const windowTo = ref("");
const selectedModels = reactive(new Set<string>());
const preview = ref<ProbeQueryResult | null>(null);
const previewError = ref("");
const launching = ref(false);
const launchError = ref("");
const page = ref(1);

const WIZARD_TITLE_ID = "launch-wizard-title";
const closeButton = ref<HTMLButtonElement | null>(null);
let triggerElement: HTMLElement | null = null;

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

const catalogs = useQuery({ queryKey: queryKeys.targetCatalog, queryFn: getTargetCatalog });
const models = useQuery({ queryKey: queryKeys.modelCatalog, queryFn: getModelCatalog });
const versions = useEvolutionTargetVersions(
  computed(() => (step.value === 1 ? targetId.value : null)),
);

const catalogTargets = computed(() => catalogs.data.value?.[targetType.value] ?? []);
const selectedTarget = computed(
  () => catalogTargets.value.find((target) => target.id === targetId.value) ?? null,
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
  },
  { immediate: true },
);

const versionError = computed(() => {
  const error = versions.error.value;
  if (!error) {
    return "";
  }
  return error instanceof Error ? error.message : String(error);
});

/** Retry the failed remote version list without leaving step 1. */
function retryVersions(): void {
  void versions.refetch();
}

/** Reset the cascading name and version selections when the type changes. */
function selectType(next: "skill" | "agent"): void {
  if (targetType.value === next) {
    return;
  }
  targetType.value = next;
  targetId.value = catalogs.data.value?.[next][0]?.id ?? null;
  targetVersion.value = "";
  versionPinned.value = false;
  resetPreview();
}

/** Record the chosen target id and reset its dependent version. */
function selectTargetId(id: string): void {
  targetId.value = id || null;
  targetVersion.value = "";
  versionPinned.value = false;
  resetPreview();
}

/** Toggle one model chip; clearing every chip means every model. */
function toggleModel(model: string): void {
  if (selectedModels.has(model)) {
    selectedModels.delete(model);
  } else {
    selectedModels.add(model);
  }
  resetPreview();
}

function resetPreview(): void {
  step.value = 1;
  preview.value = null;
  previewError.value = "";
  page.value = 1;
}

function condition(): ProbeQueryRequest {
  return {
    targetType: targetType.value,
    targetName: selectedTarget.value?.name ?? "",
    targetVersion: targetVersion.value || undefined,
    from: windowFrom.value || undefined,
    to: windowTo.value || undefined,
    models: [...selectedModels],
    page: page.value,
    pageSize: WIZARD_PAGE_SIZE,
    mode: "full",
  };
}

function windowInvalid(): boolean {
  return Boolean(windowFrom.value && windowTo.value && windowFrom.value > windowTo.value);
}

/** Run the probe preview and advance to step 2 when hits exist. */
async function runQuery(): Promise<void> {
  if (!selectedTarget.value || windowInvalid()) {
    return;
  }
  previewError.value = "";
  page.value = 1;
  try {
    preview.value = await queryProbeHits(condition());
    step.value = 2;
  } catch (error) {
    preview.value = null;
    previewError.value = error instanceof Error ? error.message : String(error);
  }
}

/** Fetch another page of probe rows while staying on step 2. */
async function changePage(next: number): Promise<void> {
  if (!preview.value || next < 1) {
    return;
  }
  page.value = next;
  try {
    preview.value = await queryProbeHits(condition());
  } catch (error) {
    previewError.value = error instanceof Error ? error.message : String(error);
  }
}

async function launch(mode: "full" | "cluster_only"): Promise<void> {
  if (!selectedTarget.value || launching.value) {
    return;
  }
  launching.value = true;
  launchError.value = "";
  try {
    const body = { ...condition(), mode };
    const accepted =
      mode === "full" ? await startEvolutionRun(body) : await startClusterPreview(body);
    emit("launched", mode, accepted.runId);
  } catch (error) {
    launchError.value = error instanceof Error ? error.message : String(error);
  } finally {
    launching.value = false;
  }
}

function openSourceCase(item: ProbePreviewItem): void {
  const caseId = item.sourceBadCaseIds[0];
  if (!caseId) {
    return;
  }
  window.open(
    `/sessions/${encodeURIComponent(item.sessionId)}/errors?case=${encodeURIComponent(caseId)}&tab=attr`,
    "_blank",
    "noopener",
  );
}

/** Keep both ends of an id so rows from the same family stay distinguishable. */
function shortId(id: string): string {
  if (id.length < SHORT_ID_MIN_LENGTH) {
    return id;
  }
  return `${id.slice(0, SHORT_ID_HEAD)}…${id.slice(-SHORT_ID_TAIL)}`;
}

/** Close the wizard and open the target configuration page. */
function goTargetConfig(): void {
  emit("close");
  void router.push("/evolution/targets");
}

const distribution = computed(() => {
  const stats = preview.value?.summary.byAttributeType;
  return (Object.keys(ATTRIBUTE_LABELS) as AttributeKey[])
    .map((key) => ({
      key,
      label: ATTRIBUTE_LABELS[key],
      color: ATTRIBUTE_COLORS[key],
      count: stats ? stats[key] : 0,
    }))
    .filter((entry) => entry.count > 0);
});
const distributionTotal = computed(() =>
  distribution.value.reduce((sum, entry) => sum + entry.count, 0),
);
const pageCount = computed(() =>
  preview.value ? Math.max(1, Math.ceil(preview.value.total / preview.value.pageSize)) : 1,
);
const versionPlaceholder = computed(() =>
  versions.isPending.value ? "读取版本…" : "版本",
);
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
      <div class="modal-body">
        <div class="wz-steps">
          <span :class="{ on: step === 1 }">① 设置筛选条件</span>
          →
          <span :class="{ on: step === 2 }">② 确认查询结果并启动</span>
        </div>

        <template v-if="step === 2 && preview">
          <div class="wz-condstrip">
            <span class="chip kind">{{ targetType }}:{{ preview.items[0]?.probeObject ?? selectedTarget?.name }}@{{ targetVersion || selectedTarget?.defaultRef }}</span>
            <span
              v-if="windowFrom || windowTo"
              class="chip mono"
            >{{ windowFrom || "…" }} ~ {{ windowTo || "…" }}</span>
            <span
              v-for="model in selectedModels"
              :key="model"
              class="chip model"
            >{{ model }}</span>
            <button
              class="btn sm back"
              type="button"
              @click="resetPreview"
            >
              ← 修改条件
            </button>
          </div>
          <div class="match-summary">
            <div class="wz-stats">
              <span class="st"><b>{{ preview.summary.sessions }}</b><span>命中 session</span></span>
              <span class="st"><b>{{ preview.summary.badCases }}</b><span>问题报告</span></span>
              <span class="st"><b>{{ preview.summary.analyzed }}</b><span>已分析</span></span>
              <span class="st"><b>{{ preview.summary.unanalyzed }}</b><span>未分析</span></span>
              <span class="st accent"><b>{{ preview.summary.usedProbes }}</b><span>「是问题」进入聚类</span></span>
            </div>
            <div
              v-if="distributionTotal"
              class="wz-typebar"
            >
              <span
                v-for="entry in distribution"
                :key="entry.key"
                :style="{
                  width: `${(entry.count / distributionTotal) * 100}%`,
                  background: entry.color,
                }"
              />
            </div>
            <div
              v-if="distribution.length"
              class="wz-legend"
            >
              <span
                v-for="entry in distribution"
                :key="entry.key"
              >
                <span
                  class="dot"
                  :style="{ background: entry.color }"
                />{{ entry.label }}
                <b>{{ entry.count }}</b>
              </span>
            </div>
            <div class="rep-scroll">
              <table class="rep">
                <thead>
                  <tr>
                    <th>报告 ID</th>
                    <th>归属会话</th>
                    <th>模型</th>
                    <th>根因对象@版本</th>
                    <th>归因</th>
                    <th>来源问题</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="item in preview.items"
                    :key="item.probeId"
                  >
                    <td class="id">
                      <button
                        class="linklike"
                        type="button"
                        :title="item.probeId"
                        @click="openSourceCase(item)"
                      >
                        {{ shortId(item.probeId) }}
                      </button>
                    </td>
                    <td :title="item.sessionTitle ?? item.sessionId">
                      {{ item.sessionTitle ?? shortId(item.sessionId) }}
                    </td>
                    <td class="mono model-cell">
                      {{ item.model ?? "—" }}
                    </td>
                    <td class="mono">
                      {{ item.probeObject }}@{{ item.objectVersion ?? "—" }}
                    </td>
                    <td>
                      <span
                        class="type-chip"
                        :style="{ color: ATTRIBUTE_COLORS[item.attributeType] }"
                      >{{ ATTRIBUTE_LABELS[item.attributeType] }}</span>
                    </td>
                    <td class="mono">
                      {{ item.sourceBadCaseIds.map(shortId).join(", ") }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="pager">
              <button
                class="btn"
                type="button"
                :disabled="page <= 1"
                @click="changePage(page - 1)"
              >
                ← 上一页
              </button>
              <span class="pager-info">第 <b>{{ page }}</b> / {{ pageCount }} 页 · 共 <b>{{ preview.total }}</b> 份</span>
              <button
                class="btn"
                type="button"
                :disabled="page >= pageCount"
                @click="changePage(page + 1)"
              >
                下一页 →
              </button>
            </div>
          </div>
          <p
            v-if="launchError"
            class="wizard-error"
            role="alert"
          >
            {{ launchError }}
          </p>
        </template>

        <template v-else>
          <div class="f-row">
            <div class="f-label">
              进化对象 <span class="req">*</span>
            </div>
            <div class="f-inline">
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
              <select
                class="inp"
                data-testid="wizard-target"
                :value="targetId ?? ''"
                @change="selectTargetId(($event.target as HTMLSelectElement).value)"
              >
                <option
                  value=""
                  disabled
                >
                  {{ catalogs.isPending.value ? "读取对象…" : "选择对象" }}
                </option>
                <option
                  v-for="target in catalogTargets"
                  :key="target.id"
                  :value="target.id"
                >
                  {{ target.name }}
                </option>
              </select>
              <span class="f-hint">版本</span>
              <select
                v-model="targetVersion"
                class="inp"
                data-testid="wizard-version"
                @change="versionPinned = true"
              >
                <option
                  value=""
                  disabled
                >
                  {{ versionPlaceholder }}
                </option>
                <option
                  v-for="version in versionOptions"
                  :key="version"
                  :value="version"
                >
                  {{ version }}
                </option>
              </select>
            </div>
            <p
              v-if="versions.isError.value"
              class="wizard-error"
              data-testid="wizard-version-error"
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
              未配置的进化对象不会出现在列表中；点击<!-- eslint-disable vue/multiline-html-element-content-newline -- 中文句内按钮与前后文字紧邻渲染，不留多余空格 --><button
                class="cfg-link"
                type="button"
                data-testid="wizard-target-config-link"
                @click="goTargetConfig"
              >配置页</button><!-- eslint-enable vue/multiline-html-element-content-newline -->前往。
            </p>
          </div>
          <div class="f-row">
            <div class="f-label">
              时间段（session 启动时间） <span class="req">*</span>
            </div>
            <div class="f-inline">
              <input
                v-model="windowFrom"
                class="inp"
                type="date"
                data-testid="wizard-from"
              >
              <span class="f-hint">~</span>
              <input
                v-model="windowTo"
                class="inp"
                type="date"
                data-testid="wizard-to"
              >
            </div>
            <p
              v-if="windowInvalid()"
              class="wizard-error"
              role="alert"
            >
              起始时间不能晚于结束时间
            </p>
          </div>
          <div class="f-row">
            <div class="f-label">
              模型（多选，只纳入这些模型跑出的报告；全不选 = 全部模型）
            </div>
            <div class="pick">
              <span
                v-for="entry in models.data.value?.items ?? []"
                :key="entry.model"
                class="opt"
                :class="{ on: selectedModels.has(entry.model) }"
                role="button"
                tabindex="0"
                :title="`session ${entry.sessionCount} · agent ${entry.agentCount}`"
                @click="toggleModel(entry.model)"
                @keydown.enter.prevent="toggleModel(entry.model)"
              >{{ entry.model }}</span>
            </div>
          </div>
          <p class="f-note">
            确认条件后点「下一步」执行查询并核对命中的问题报告。
          </p>
          <p
            v-if="previewError"
            class="wizard-error"
            role="alert"
          >
            {{ previewError }}
          </p>
        </template>
      </div>
      <div class="modal-foot">
        <template v-if="step === 2 && preview">
          <button
            class="btn"
            type="button"
            @click="resetPreview"
          >
            ← 上一步
          </button>
          <button
            class="btn accent"
            type="button"
            data-testid="wizard-cluster"
            :disabled="launching"
            @click="launch('cluster_only')"
          >
            启动问题聚类分析
          </button>
          <button
            class="btn primary"
            type="button"
            data-testid="wizard-start"
            :disabled="launching"
            @click="launch('full')"
          >
            启动自进化 →
          </button>
        </template>
        <template v-else>
          <button
            class="btn primary"
            type="button"
            data-testid="wizard-next"
            :disabled="!selectedTarget || !targetVersion || windowInvalid()"
            @click="runQuery"
          >
            下一步：查询匹配报告 →
          </button>
        </template>
      </div>
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
  padding: 3px 10px;
  font-size: 11.5px;
}

.wz-steps {
  display: flex;
  gap: 8px;
  font-size: 11.5px;
  color: var(--text-faint);
  margin-bottom: 16px;
}

.wz-steps .on {
  color: var(--blue);
  font-weight: 600;
}

.wz-condstrip {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  border: 1px solid var(--border);
  background: var(--bg-panel);
  border-radius: 8px;
  padding: 7px 12px;
  margin-bottom: 12px;
  font-size: 12px;
}

.wz-condstrip .chip {
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 2px 10px;
  font-family: var(--mono);
  color: var(--text-dim);
}

.wz-condstrip .back {
  margin-left: auto;
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

.f-hint,
.f-note {
  color: var(--text-faint);
  font-size: 12px;
}

.f-note {
  margin: 6px 0 0;
  font-size: 11.5px;
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

.pick {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.pick .opt {
  font-size: 12px;
  cursor: pointer;
  user-select: none;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 3px 12px;
  color: var(--text-dim);
  background: var(--bg-card);
  font-family: var(--mono);
}

.pick .opt.on {
  color: var(--text);
  border-color: var(--blue);
  background: color-mix(in srgb, var(--blue) 13%, transparent);
}

.match-summary {
  border: 1px solid color-mix(in srgb, var(--blue) 35%, transparent);
  background: color-mix(in srgb, var(--blue) 6%, transparent);
  border-radius: 10px;
  padding: 12px 14px;
  font-size: 12.5px;
}

.match-summary b {
  font-family: var(--mono);
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

.wz-typebar {
  display: flex;
  height: 8px;
  border-radius: 4px;
  overflow: hidden;
  margin: 2px 0 6px;
}

.wz-typebar span {
  display: block;
  height: 100%;
}

.wz-legend {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 11px;
  color: var(--text-dim);
  margin-bottom: 4px;
}

.wz-legend .dot {
  width: 7px;
  height: 7px;
  border-radius: 2px;
  display: inline-block;
  margin-right: 4px;
  vertical-align: -1px;
}

.rep-scroll {
  margin-top: 10px;
  overflow-x: auto;
  overscroll-behavior-x: contain;
}

table.rep {
  width: 100%;
  min-width: 560px;
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

table.rep td.id {
  font-family: var(--mono);
}

.linklike {
  font: inherit;
  color: var(--blue);
  cursor: pointer;
  border: none;
  background: none;
  border-bottom: 1px dashed color-mix(in srgb, var(--blue) 50%, transparent);
}

.mono {
  font-family: var(--mono);
}

.model-cell {
  color: var(--cyan);
}

.type-chip {
  font-size: 11.5px;
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

.wizard-error {
  margin: 10px 0 0;
  color: var(--red);
  font-size: 12px;
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

  .match-summary {
    padding: 10px 12px;
  }
}
</style>
