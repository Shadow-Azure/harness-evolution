<script setup lang="ts">
import type { BadCase, SessionListItem, SessionTree } from "@harness/contracts";
import {
  computed,
  defineAsyncComponent,
  nextTick,
  ref,
  watch,
} from "vue";

import BadCaseList from "../../../components/bad-cases/BadCaseList.vue";
import { workspacePath } from "../../../router/workspace";
import ErrorState from "../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import {
  AgentFlowError,
  AgentFlowLoading,
} from "./agentFlowPlaceholder";
import StatStrip from "../../../components/ui/StatStrip.vue";
import {
  formatDuration,
  formatStartedAt,
  formatTokens,
} from "../../../utils/sessionDisplay";

const AgentFlow = defineAsyncComponent({
  loader: () => import("../../../components/agent-tree/AgentFlow.vue"),
  loadingComponent: AgentFlowLoading,
  errorComponent: AgentFlowError,
  delay: 0,
});

const props = defineProps({
  wid: {
    type: String,
    required: true,
  },
  item: {
    type: Object as () => SessionListItem | null,
    default: null,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: Object as () => Error | null,
    default: null,
  },
  tree: {
    type: Object as () => SessionTree | null,
    default: null,
  },
  treeLoading: {
    type: Boolean,
    default: false,
  },
  treeError: {
    type: Object as () => Error | null,
    default: null,
  },
  problems: {
    type: Array as () => BadCase[],
    default: () => [],
  },
  problemsLoading: {
    type: Boolean,
    default: false,
  },
  problemsError: {
    type: Object as () => Error | null,
    default: null,
  },
  expandedAgentIds: {
    type: Array as () => string[],
    default: () => [],
  },
  activeAgentId: {
    type: String as () => string | null,
    default: null,
  },
  activeEventIndex: {
    type: Number as () => number | null,
    default: null,
  },
  searchActive: {
    type: Boolean,
    default: false,
  },
  listEmpty: {
    type: Boolean,
    default: false,
  },
  filterActive: {
    type: Boolean,
    default: false,
  },
  pendingSessions: {
    type: Number,
    default: 0,
  },
});

const emit = defineEmits<{
  retry: [];
  "tree-retry": [];
  "problems-retry": [];
  "node-select": [agentId: string];
  "toggle-expanded": [agentId: string];
  "collapse-all": [];
  "badcase-select": [badCaseId: string];
}>();

const agentFlowRef = ref<{
  locateBadCase: (badCaseId: string) => void | Promise<void>;
} | null>(null);
const badCaseListRef = ref<{
  scrollToProblem: (badCaseId: string) => void;
} | null>(null);
const activeBadCaseId = ref<string | null>(null);

watch(
  () => props.item?.id,
  () => {
    activeBadCaseId.value = null;
  },
);

watch(
  () => props.problems,
  (problems) => {
    if (
      activeBadCaseId.value &&
      !problems.some(
        (problem) => problem.badCaseId === activeBadCaseId.value,
      )
    ) {
      activeBadCaseId.value = null;
    }
  },
);

async function selectBadCase(badCaseId: string) {
  activeBadCaseId.value = badCaseId;
  emit("badcase-select", badCaseId);
  await nextTick();
  await agentFlowRef.value?.locateBadCase?.(badCaseId);
  await nextTick();
  badCaseListRef.value?.scrollToProblem(badCaseId);
}

const statusLabel = computed(() =>
  props.item?.status === "ok" ? "完成" : "有失败",
);
const statusClass = computed(() => {
  if (props.item?.status === "ok") return "ok";
  return props.item?.status === "fail" ? "fail" : "problem";
});

const stats = computed<Array<{
  label: string;
  value: string | number;
  tone?: "bad" | "warn";
}>>(() => {
  const value = props.item;
  if (!value) return [];
  return [
    { label: "用户轮次", value: value.stats.userTurns },
    { label: "消息", value: value.stats.messages },
    { label: "工具调用", value: value.stats.tools },
    { label: "失败", value: value.stats.errors, tone: "bad" },
    { label: "子 Agent", value: value.stats.agents },
    { label: "Skill", value: value.skills.length },
    { label: "Token", value: formatTokens(value.stats.tokens) },
    { label: "失败/百消息", value: value.stats.failPer100Messages.toFixed(1), tone: "bad" },
    { label: "问题/百消息", value: value.stats.badCasesPer100Messages.toFixed(1), tone: "warn" },
  ];
});
</script>

<template>
  <section
    class="overview"
    data-testid="session-overview"
  >
    <LoadingSkeleton
      v-if="loading"
      label="正在读取 Session 概览"
      :rows="5"
    />
    <ErrorState
      v-else-if="error"
      code="SESSION_UNAVAILABLE"
      message="Session 概览加载失败，请重试。"
      @retry="emit('retry')"
    />
    <div
      v-else-if="item"
      class="overview-content"
    >
      <header class="overview-head">
        <div class="heading-copy">
          <div class="title-row">
            <span
              class="status-dot"
              :class="item.status"
              aria-hidden="true"
            />
            <h2>{{ item.title }}</h2>
            <span
              class="status-badge"
              :class="statusClass"
            >
              {{ statusLabel }}
            </span>
          </div>
          <div class="meta">
            <time :datetime="item.startedAt">{{ formatStartedAt(item.startedAt) }}</time>
            <span
              class="root-session-id"
              data-testid="session-overview-root-session-id"
              :title="`根会话 ID: ${item.id}`"
            >根会话 ID · <span class="mono">{{ item.id }}</span></span>
            <span class="repo-chip">{{ item.repo }}</span>
            <span>{{ formatDuration(item.durationSeconds) }}</span>
            <span>{{ item.model ?? "未知模型" }}</span>
          </div>
        </div>
        <div class="section-actions">
          <RouterLink
            class="detail-cta"
            data-testid="detail-cta"
            :to="workspacePath(wid, `sessions/${encodeURIComponent(item.id)}/errors`)"
          >
            打开错误详情
          </RouterLink>
        </div>
      </header>

      <StatStrip :items="stats" />

      <section
        class="tree-panel"
        data-testid="agent-tree-container"
        aria-labelledby="agent-tree-title"
      >
        <header class="tree-head">
          <strong id="agent-tree-title">Agent 执行流</strong>
          <span>默认执行序 lane DAG；结构树保留为切换视图。</span>
        </header>
        <div
          v-if="treeLoading"
          class="tree-loading"
          data-testid="tree-loading"
        >
          <LoadingSkeleton
            label="正在读取 Agent 执行流"
            :rows="4"
          />
        </div>
        <div
          v-else-if="treeError"
          class="tree-loading"
        >
          <ErrorState
            code="SESSION_TREE_UNAVAILABLE"
            message="执行流读取失败，请重试。"
            @retry="emit('tree-retry')"
          />
        </div>
        <template v-else-if="tree">
          <AgentFlow
            ref="agentFlowRef"
            :active-bad-case-id="activeBadCaseId"
            :active-agent-id="activeAgentId"
            :active-event-index="activeEventIndex"
            :expanded="expandedAgentIds"
            :problems="problems"
            :tree="tree"
            @badcase-select="selectBadCase"
            @collapse-all="emit('collapse-all')"
            @node-select="emit('node-select', $event)"
            @toggle-expanded="emit('toggle-expanded', $event)"
          />
        </template>
        <div
          v-else
          class="tree-placeholder"
          data-testid="tree-placeholder"
        >
          <strong>Agent 执行流</strong>
          <span>当前 Session 没有可展示的 Agent 节点。</span>
        </div>
      </section>
      <BadCaseList
        ref="badCaseListRef"
        :wid="wid"
        :active-bad-case-id="activeBadCaseId"
        :error="problemsError"
        :loading="problemsLoading"
        :problems="problems"
        @retry="emit('problems-retry')"
        @select="selectBadCase"
      />
    </div>
    <div
      v-else
      class="overview-empty"
      data-testid="session-overview-empty"
    >
      <template v-if="searchActive">
        <strong>未找到该 Session</strong>
        <span>输入完整 root session ID 后回车重新查询；清空输入并回车可恢复最新 10 个 Session。</span>
      </template>
      <template v-else-if="listEmpty && filterActive">
        <strong>没有匹配当前筛选的 session</strong>
        <span>调整状态筛选，或清空输入后回车恢复最新 10 个 Session。</span>
      </template>
      <template v-else-if="listEmpty && pendingSessions > 0">
        <strong>该工作空间暂无可展示的 Session</strong>
        <span>{{ pendingSessions }} 个待同步根会话的轨迹仍在补齐，补齐后刷新页面可见。</span>
      </template>
      <template v-else-if="listEmpty">
        <strong>该工作空间还没有上报 bad case</strong>
        <span>上报 bad case 后，这里会显示最新 10 个 Session。</span>
      </template>
      <template v-else>
        <strong>未选择 Session</strong>
        <span>从左侧选择一个会话查看家族树。</span>
      </template>
    </div>
  </section>
</template>

<style scoped>
.overview {
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  padding: 18px 20px;
}

.overview > :deep(.loading-state),
.overview > :deep(.error-state) {
  min-height: 100%;
}

.overview-content {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 100%;
}

.overview-content > :deep(.problem-list) {
  flex: 1 0 auto;
}

.overview-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.heading-copy {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.title-row h2 {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--text);
  font-size: 17px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-dot {
  width: 8px;
  height: 8px;
  flex-shrink: 0;
  border-radius: 50%;
}

.status-dot.ok {
  background: var(--green);
}

.status-dot.partial {
  background: var(--orange);
}

.status-dot.fail {
  background: var(--red);
}

.status-badge {
  margin-left: auto;
  padding: 2px 10px;
  border-radius: var(--radius-pill);
  font-size: 10.5px;
  font-weight: 600;
}

.status-badge.ok {
  background: color-mix(in srgb, var(--green) 14%, transparent);
  color: var(--green);
}

.status-badge.problem {
  background: color-mix(in srgb, var(--orange) 14%, transparent);
  color: var(--orange);
}

.status-badge.fail {
  background: color-mix(in srgb, var(--red) 14%, transparent);
  color: var(--red);
}

.meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 9px;
  color: var(--text-dim);
  font-size: 11px;
}

.meta time {
  font-family: var(--mono);
}

.root-session-id {
  color: var(--text-faint);
  overflow-wrap: anywhere;
}

.root-session-id .mono {
  color: var(--text-dim);
  font-family: var(--mono);
}

.repo-chip {
  padding: 0 6px;
  border-radius: 5px;
  background: color-mix(in srgb, var(--cyan) 12%, transparent);
  color: var(--cyan);
  font-family: var(--mono);
}

.section-actions {
  display: flex;
  margin-left: auto;
}

.detail-cta {
  padding: 5px 12px;
  border: 1px solid color-mix(in srgb, var(--blue) 40%, transparent);
  border-radius: 7px;
  background: color-mix(in srgb, var(--blue) 8%, var(--bg-card));
  color: var(--blue);
  font: inherit;
  font-size: 11.5px;
  text-decoration: none;
}

.detail-cta:hover {
  border-color: var(--blue);
  background: color-mix(in srgb, var(--blue) 14%, var(--bg-card));
}

.tree-panel {
  position: relative;
  display: grid;
  gap: 10px;
  padding: 10px 12px 12px;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.tree-panel :deep(.agent-flow) {
  min-width: 0;
}

.tree-panel :deep(.ld-view),
.tree-panel :deep(.agent-tree) {
  border: 0;
  border-radius: 0;
  background: var(--bg-panel);
}

.tree-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.tree-head strong {
  color: var(--text-dim);
  font-size: 12px;
}

.tree-head span {
  color: var(--text-faint);
  font-size: 10.5px;
}

.tree-placeholder {
  display: grid;
  place-content: center;
  min-height: 720px;
  padding: 28px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background:
    radial-gradient(circle at 1px 1px, var(--border) 1px, transparent 0) 0 0 / 18px 18px,
    var(--bg-card);
  text-align: center;
}

.tree-panel :deep(.tree-loading) {
  display: grid;
  align-content: center;
  min-height: 720px;
  padding: 12px;
}

.tree-panel :deep(.tree-loading-error) {
  place-content: center;
  gap: 4px;
  color: var(--text-dim);
  font-size: 12px;
  text-align: center;
}

.tree-panel :deep(.tree-loading-error strong) {
  color: var(--text-dim);
  font-size: 13px;
}

.tree-panel :deep(.tree-loading-error span) {
  color: var(--text-faint);
  font-size: 11.5px;
}

.tree-placeholder strong {
  color: var(--text-dim);
  font-size: 13px;
}

.tree-placeholder span {
  margin-top: 5px;
  color: var(--text-faint);
  font-size: 11.5px;
}

.overview-empty {
  display: grid;
  place-content: center;
  min-height: 100%;
  padding: 20px;
  color: var(--text-faint);
  font-size: 12px;
  text-align: center;
}

.overview-empty strong {
  color: var(--text-dim);
  font-size: 13px;
}

.overview-empty span {
  margin-top: 5px;
  max-width: 360px;
  line-height: 1.6;
}

@media (max-width: 860px) {
  .tree-placeholder {
    min-height: 420px;
  }

  .tree-panel :deep(.tree-loading) {
    min-height: 420px;
  }
}
</style>
