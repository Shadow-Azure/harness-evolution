<script setup lang="ts">
import type { StepCondition } from "@harness/contracts";
import { computed, ref } from "vue";
import { type LocationQueryRaw, useRoute, useRouter } from "vue-router";

import ErrorState from "../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../components/ui/LoadingSkeleton.vue";
import { useEvolutionRunDetail } from "../../composables/useEvolutionRunDetail";
import { useEvolutionRunStep } from "../../composables/useEvolutionRunStep";
import RunStepContent from "./components/RunStepContent.vue";
import RunStepper from "./components/RunStepper.vue";
import { resolveRunStepKey } from "./runDetail";

defineOptions({ name: "EvolutionRunDetailPage" });

const route = useRoute();
const router = useRouter();

const runId = computed(() => String(route.params.runId ?? ""));
const {
  data: run,
  error: runError,
  isPending: runPending,
  refetch: refetchRun,
} = useEvolutionRunDetail(runId);

const steps = computed(() => run.value?.steps ?? []);
const selectedKey = computed(() => resolveRunStepKey(route.query.step, steps.value));
const selectedStep = computed(
  () => steps.value.find((step) => step.key === selectedKey.value) ?? null,
);
const focusCluster = computed(() =>
  typeof route.query.cluster === "string" ? route.query.cluster : undefined,
);
const branchCopied = ref(false);

const {
  data: stepData,
  error: stepError,
  isPending: stepPending,
  refetch: refetchStep,
} = useEvolutionRunStep(
  runId,
  selectedKey,
  computed(() => selectedStep.value?.clickable === true),
);

const statusLabel = computed(() => {
  switch (run.value?.status) {
    case "preparing":
      return "准备中";
    case "running":
      return "正在执行";
    case "blocked":
      return "已阻塞";
    case "completed":
      if (!run.value.final) return "已完成 · 终评未知";
      return run.value.final.verdict ? "✓ 已完成 · 自进化有效" : "已完成 · 无收益";
    case "failed":
      return "失败";
    case "interrupted":
      return "已中断";
    default:
      return "";
  }
});

const statusClass = computed(() => {
  const status = run.value?.status;
  if (status === "completed") {
    if (!run.value?.final) return "pending";
    return run.value.final.verdict ? "accepted" : "rejected";
  }
  if (status === "blocked" || status === "interrupted") return "blocked";
  if (status === "failed") return "failed";
  return "running";
});

const windowLabel = computed(() => {
  const value = run.value?.window;
  if (!value) return "—";
  if (value.from && value.to) return `${value.from} ~ ${value.to}`;
  if (value.from) return `${value.from} ~ 至今`;
  if (value.to) return `起始未知 ~ ${value.to}`;
  return "时间窗未设置";
});

const createdMeta = computed(() => {
  if (!run.value) return "";
  const date = run.value.createdAt.replace("T", " ").slice(0, 16);
  return run.value.createdBy ? `${run.value.createdBy} · ${date}` : date;
});

const distribution = computed(() => {
  const stats = run.value?.stats.byAttributeType;
  if (!stats) return [];
  return [
    { key: "error", label: "错误", value: stats.error, color: "var(--red)" },
    { key: "prompt", label: "prompt", value: stats.prompt, color: "var(--orange)" },
    { key: "model", label: "模型", value: stats.model, color: "var(--purple)" },
    { key: "nonIssue", label: "非问题", value: stats.nonIssue, color: "var(--text-faint)" },
  ];
});

const analyzedCount = computed(() =>
  distribution.value.reduce((sum, item) => sum + item.value, 0),
);

const unanalyzedCount = computed(() =>
  Math.max((run.value?.stats.probes ?? 0) - analyzedCount.value, 0),
);

const condition = computed<StepCondition>(() => ({
  targetType: run.value?.target.type ?? "skill",
  targetName: run.value?.target.name ?? "",
  targetVersion: run.value?.target.version ?? "",
  from: run.value?.window.from ?? null,
  to: run.value?.window.to ?? null,
  models: run.value?.models ?? [],
}));

const stepErrorCode = computed(() => {
  const error = stepError.value;
  if (error && typeof error === "object" && "code" in error) {
    return String(error.code);
  }
  return "";
});

const runErrorCode = computed(() => {
  const error = runError.value;
  if (error && typeof error === "object" && "code" in error) {
    return String(error.code);
  }
  return "";
});

function selectStep(key: typeof selectedKey.value): void {
  const step = steps.value.find((candidate) => candidate.key === key);
  if (!step?.clickable) return;
  const query: LocationQueryRaw = { ...route.query, step: key };
  if (key !== "clusters") delete query.cluster;
  void router.replace({
    query,
  });
}

function retryRun(): void {
  void refetchRun();
}

function retryStep(): void {
  void refetchStep();
}

async function copyBranch(): Promise<void> {
  const branch = run.value?.workspace.branchName;
  if (!branch) return;
  try {
    await navigator.clipboard.writeText(branch);
    branchCopied.value = true;
  } catch {
    branchCopied.value = false;
  }
}

function clearMissingClusterFocus(): void {
  if (!("cluster" in route.query)) return;
  const query: LocationQueryRaw = { ...route.query };
  delete query.cluster;
  void router.replace({ query });
}
</script>

<template>
  <section
    class="run-detail-page"
    data-testid="evolution-run-detail"
  >
    <RouterLink
      class="back"
      to="/evolution"
    >
      ← 返回自进化列表
    </RouterLink>

    <LoadingSkeleton
      v-if="runPending"
      label="正在读取运行详情"
      :rows="4"
    />
    <ErrorState
      v-else-if="runErrorCode === 'RUN_NOT_FOUND'"
      code="EVOLUTION_RUN_NOT_FOUND"
      message="运行不存在或已被删除"
      :retryable="false"
    />
    <ErrorState
      v-else-if="runError"
      code="EVOLUTION_RUN_UNAVAILABLE"
      message="运行详情读取失败，请重试"
      @retry="retryRun"
    />
    <template v-else-if="run">
      <header class="detail-head">
        <h1>{{ run.title }}</h1>
        <span
          class="badge"
          :class="statusClass"
        >{{ statusLabel }}</span>
        <span class="spacer" />
        <span class="created-meta">{{ createdMeta }}</span>
      </header>

      <div
        v-if="run.status === 'blocked'"
        class="blocked-banner"
        data-testid="blocked-banner"
        role="alert"
      >
        <span class="blocked-title">运行在 {{ run.blockedStage ?? run.error?.stage ?? "未知阶段" }} 阻塞</span>
        <span>{{ run.error?.message ?? "错误详情暂不可用" }}</span>
        <span class="mono muted">自动重试 {{ run.retryAttempts }} 次</span>
        <span
          v-if="run.nextRetryAt"
          class="mono muted"
        >下次重试 {{ run.nextRetryAt }}</span>
        <span
          v-if="run.error"
          class="mono muted"
        >{{ run.error.at }}</span>
        <span class="retry-copy">自动恢复能力由后续运行恢复切片提供。</span>
      </div>
      <div
        v-else-if="run.error"
        class="error-banner"
        role="alert"
      >
        <b>{{ run.error.stage }}</b>
        <span>{{ run.error.message }}</span>
        <span class="mono muted">{{ run.error.at }}</span>
      </div>

      <article class="card panel info-panel">
        <h2 class="sec-title">
          目标与输入
          <span class="sub">筛选条件命中的问题报告即本次进化的输入</span>
        </h2>
        <div class="kv-grid">
          <div class="kv">
            <div class="k">
              进化对象
            </div>
            <div class="v">
              <span class="chip kind">{{ run.target.type }}:{{ run.target.name }}</span>
            </div>
          </div>
          <div class="kv">
            <div class="k">
              版本
            </div>
            <div class="v mono">
              {{ run.target.version }}
            </div>
          </div>
          <div class="kv">
            <div class="k">
              时间段（session 启动）
            </div>
            <div class="v mono">
              {{ windowLabel }}
            </div>
          </div>
          <div class="kv">
            <div class="k">
              模型（多选）
            </div>
            <div class="v">
              <span
                v-for="model in run.models"
                :key="model"
                class="chip model"
              >{{ model }}</span>
              <span
                v-if="run.models.length === 0"
                class="muted"
              >全部模型</span>
            </div>
          </div>
          <div class="kv">
            <div class="k">
              时间段内 session 数
            </div>
            <div class="v big">
              {{ run.stats.sessions }}
            </div>
          </div>
          <div class="kv">
            <div class="k">
              问题报告数
            </div>
            <div class="v big">
              {{ run.stats.probes }}
            </div>
          </div>
          <div class="kv">
            <div class="k">
              已分析 / 未分析
            </div>
            <div class="v big">
              {{ analyzedCount }}
              <span class="muted">/ {{ unanalyzedCount }}</span>
            </div>
          </div>
          <div class="kv">
            <div class="k">
              最终用于进化的问题数
            </div>
            <div class="v big accent">
              {{ run.stats.usedProbes }}
            </div>
          </div>
        </div>
        <p class="cb-label">
          已分析问题的归因类型分布（{{ analyzedCount }} 份）
        </p>
        <div
          class="typebar"
          aria-label="归因类型分布"
        >
          <span
            v-for="item in distribution"
            :key="item.key"
            :style="{
              width: `${analyzedCount ? (item.value / analyzedCount) * 100 : 0}%`,
              background: item.color,
            }"
          />
        </div>
        <div class="legend">
          <span
            v-for="item in distribution"
            :key="item.key"
          >
            <span
              class="dot"
              :style="{ background: item.color }"
            />
            {{ item.label }} <b>{{ item.value }}</b>
          </span>
          <span class="muted">＝ 用于进化的 {{ run.stats.usedProbes }}（非问题剔除）</span>
        </div>
      </article>

      <article class="card panel workspace-panel">
        <h2 class="sec-title">
          工作区
          <span class="sub">候选 commit 与 run 分支在这里推进，不提供人工推进入口</span>
        </h2>
        <div class="workspace-grid">
          <div class="kv">
            <div class="k">
              run 分支
            </div>
            <div class="v">
              <button
                v-if="run.workspace.branchName"
                class="branch-copy mono"
                type="button"
                data-testid="copy-branch"
                :title="`点击复制分支名 ${run.workspace.branchName}`"
                @click="copyBranch"
              >
                {{ run.workspace.branchName }}
                <span aria-live="polite">{{ branchCopied ? " · 已复制" : " · 复制" }}</span>
              </button>
              <span
                v-else
                class="muted"
              >尚未创建</span>
            </div>
          </div>
          <div class="kv">
            <div class="k">
              基线 ref / commit
            </div>
            <div class="v mono">
              {{ run.workspace.baseRef ?? "—" }} /
              {{ run.workspace.baseCommit?.slice(0, 12) ?? "—" }}
            </div>
          </div>
          <div class="kv">
            <div class="k">
              仓库
            </div>
            <div class="v mono workspace-path">
              {{ run.workspace.repoUrl }}
            </div>
          </div>
          <div class="kv">
            <div class="k">
              子目录
            </div>
            <div class="v mono">
              {{ run.workspace.subDir }}
            </div>
          </div>
          <div class="kv">
            <div class="k">
              推送状态
            </div>
            <div class="v mono">
              {{ run.workspace.pushStatus }}
            </div>
          </div>
          <div class="kv">
            <div class="k">
              推送时间
            </div>
            <div class="v mono">
              {{ run.workspace.pushedAt?.replace("T", " ").slice(0, 16) ?? "尚未推送" }}
            </div>
          </div>
          <div class="kv">
            <div class="k">
              评测状态
            </div>
            <div class="v mono">
              {{ run.evalStatus }}
            </div>
          </div>
        </div>
        <p
          v-if="run.workspace.pushError"
          class="workspace-error"
        >
          推送错误：{{ run.workspace.pushError }}
        </p>
        <details
          v-if="run.workspace.workspacePath || run.workspace.repoPath"
          class="workspace-paths"
        >
          <summary>查看本地路径</summary>
          <p class="mono">
            workspace: {{ run.workspace.workspacePath ?? "—" }}<br>
            repo: {{ run.workspace.repoPath ?? "—" }}
          </p>
        </details>
      </article>

      <article class="card panel">
        <h2 class="sec-title">
          流程进度
          <span class="sub">
            当前查看：第 {{ (selectedStep?.index ?? 0) + 1 }} 步 ·
            {{ selectedStep?.title ?? "筛选输入" }}
          </span>
        </h2>
        <RunStepper
          :steps="steps"
          :selected="selectedKey"
          @select="selectStep"
        />
      </article>

      <div
        v-if="run.status === 'preparing'"
        class="preparing-copy"
      >
        <span class="pulse" />
        已受理，正在准备筛选与聚类。此步骤完成前后续节点保持禁用。
      </div>

      <ErrorState
        v-if="stepError && stepErrorCode !== 'STEP_NOT_READY'"
        code="EVOLUTION_RUN_STEP_UNAVAILABLE"
        message="当前步骤读取失败，请重试"
        @retry="retryStep"
      />
      <p
        v-else-if="stepErrorCode === 'STEP_NOT_READY'"
        class="pending-copy"
      >
        该步骤尚未到达。
      </p>
      <RunStepContent
        v-else
        :run="run"
        :step="stepData"
        :condition="condition"
        :is-pending="selectedStep?.clickable === true && stepPending"
        :is-unreached="selectedStep?.clickable !== true"
        :focus-cluster="focusCluster"
        @missing-cluster-focus="clearMissingClusterFocus"
      />
    </template>
  </section>
</template>

<style scoped>
.run-detail-page {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 14px;
  min-width: 0;
}

.back {
  color: var(--text-dim);
  font-size: 12px;
  text-decoration: none;
}

.back:hover {
  color: var(--blue);
}

.detail-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.detail-head h1 {
  margin: 0;
  color: var(--text);
  font-size: 17px;
  font-weight: 700;
}

.spacer {
  flex: 1;
}

.created-meta {
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 11.5px;
}

.badge {
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}

.badge.running {
  background: color-mix(in srgb, var(--blue) 13%, transparent);
  color: var(--blue);
}

.badge.accepted {
  background: color-mix(in srgb, var(--green) 13%, transparent);
  color: var(--green);
}

.badge.rejected,
.badge.pending {
  background: color-mix(in srgb, var(--text-faint) 18%, transparent);
  color: var(--text-dim);
}

.badge.blocked {
  background: color-mix(in srgb, var(--orange) 12%, transparent);
  color: var(--orange);
}

.badge.failed {
  background: color-mix(in srgb, var(--red) 11%, transparent);
  color: var(--red);
}

.blocked-banner,
.error-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 14px;
  border-radius: 10px;
  flex-wrap: wrap;
  font-size: 12.5px;
}

.blocked-banner {
  border: 1px solid color-mix(in srgb, var(--orange) 42%, transparent);
  background: color-mix(in srgb, var(--orange) 8%, transparent);
  color: var(--text-dim);
}

.error-banner {
  border: 1px solid color-mix(in srgb, var(--red) 38%, transparent);
  background: color-mix(in srgb, var(--red) 7%, transparent);
  color: var(--text-dim);
}

.blocked-title {
  color: var(--orange);
  font-weight: 700;
}

.retry-copy {
  margin-left: auto;
  color: var(--text-faint);
  font-size: 11.5px;
}

.card {
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.panel {
  padding: 16px 18px;
}

.sec-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  color: var(--text);
  font-size: 13.5px;
  font-weight: 650;
}

.sub {
  color: var(--text-faint);
  font-size: 11.5px;
  font-weight: 400;
}

.kv-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px 20px;
  margin-bottom: 14px;
}

.workspace-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px 20px;
}

.workspace-path {
  word-break: break-all;
}

.branch-copy {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-dim);
  font-size: inherit;
  text-align: left;
  cursor: pointer;
}

.branch-copy:hover,
.branch-copy:focus-visible {
  color: var(--blue);
}

.branch-copy span {
  color: var(--text-faint);
  font-size: 10.5px;
}

.workspace-paths {
  margin-top: 12px;
  color: var(--text-dim);
  font-size: 11.5px;
}

.workspace-error {
  margin: 10px 0 0;
  color: var(--red);
  font-size: 11.5px;
}

.workspace-paths summary {
  cursor: pointer;
  color: var(--text-faint);
}

.workspace-paths p {
  margin: 8px 0 0;
  word-break: break-all;
}

.k,
.cb-label {
  margin: 0 0 2px;
  color: var(--text-faint);
  font-size: 11px;
}

.v {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
  color: var(--text);
  font-size: 13px;
  font-weight: 600;
}

.v.big {
  font-family: var(--mono);
  font-size: 15px;
}

.v.accent {
  color: var(--blue);
}

.chip {
  display: inline-block;
  padding: 1px 9px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 10.5px;
}

.chip.kind {
  border-color: color-mix(in srgb, var(--purple) 35%, transparent);
  background: color-mix(in srgb, var(--purple) 9%, transparent);
  color: var(--purple);
  font-family: var(--mono);
}

.chip.model {
  border-color: color-mix(in srgb, var(--cyan) 35%, transparent);
  background: color-mix(in srgb, var(--cyan) 9%, transparent);
  color: var(--cyan);
  font-family: var(--mono);
}

.typebar {
  display: flex;
  height: 10px;
  margin: 6px 0 8px;
  overflow: hidden;
  border-radius: 5px;
}

.typebar span {
  display: block;
  height: 100%;
}

.legend {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  color: var(--text-dim);
  font-size: 11.5px;
}

.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 5px;
  border-radius: 2px;
}

.legend b {
  font-family: var(--mono);
}

.mono {
  font-family: var(--mono);
}

.muted {
  color: var(--text-faint);
}

.preparing-copy,
.pending-copy {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 12px 14px;
  border: 1px dashed var(--border);
  border-radius: 10px;
  color: var(--text-dim);
  font-size: 12.5px;
}

.pulse {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--blue);
  animation: pulse 1.4s infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.25;
  }
}

@media (max-width: 860px) {
  .kv-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .workspace-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .kv-grid {
    grid-template-columns: 1fr;
  }

  .workspace-grid {
    grid-template-columns: 1fr;
  }

  .created-meta,
  .retry-copy {
    width: 100%;
    margin-left: 0;
  }
}
</style>
