<script setup lang="ts">
import type { SessionListItem, SessionTree } from "@harness/contracts";
import { computed, defineAsyncComponent } from "vue";

import ErrorState from "../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import StatStrip from "../../../components/ui/StatStrip.vue";
import {
  formatDuration,
  formatStartedAt,
  formatTokens,
} from "../../../utils/sessionDisplay";

const AgentTree = defineAsyncComponent(
  () => import("../../../components/agent-tree/AgentTree.vue"),
);

const props = defineProps({
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
  expandedAgentIds: {
    type: Array as () => string[],
    default: () => [],
  },
  activeAgentId: {
    type: String as () => string | null,
    default: null,
  },
});

const emit = defineEmits<{
  retry: [];
  "tree-retry": [];
  "node-select": [agentId: string];
  "toggle-expanded": [agentId: string];
  "collapse-all": [];
}>();

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
            <span class="repo-chip">{{ item.repo }}</span>
            <span>{{ formatDuration(item.durationSeconds) }}</span>
            <span>{{ item.model ?? "未知模型" }}</span>
          </div>
        </div>
        <div class="section-actions">
          <button
            class="detail-cta"
            data-testid="detail-cta"
            type="button"
            title="错误详情将在后续 milestone 提供"
            disabled
          >
            打开错误详情
          </button>
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
          <span>横条长度表示轨迹行数，状态记号定位 Skill、Agent 与 Workflow 触发点。</span>
          <button
            v-if="expandedAgentIds.length"
            class="collapse-tree"
            data-testid="collapse-tree"
            type="button"
            @click="emit('collapse-all')"
          >
            收起分支
          </button>
        </header>
        <LoadingSkeleton
          v-if="treeLoading"
          label="正在读取 Agent 执行流"
          :rows="4"
        />
        <ErrorState
          v-else-if="treeError"
          code="SESSION_TREE_UNAVAILABLE"
          message="执行流读取失败，请重试。"
          @retry="emit('tree-retry')"
        />
        <AgentTree
          v-else-if="tree"
          :active-agent-id="activeAgentId"
          :expanded="expandedAgentIds"
          :tree="tree"
          @node-select="emit('node-select', $event)"
          @toggle-expanded="emit('toggle-expanded', $event)"
        />
        <div
          v-if="tree"
          class="tree-legend"
          aria-label="执行流图例"
        >
          <span class="skill">◆ Skill</span>
          <span class="subagent">◆ Subagent</span>
          <span class="workflow">◆ Workflow</span>
          <span class="gap">×N 消息</span>
        </div>
        <div
          v-else
          class="tree-placeholder"
          data-testid="tree-placeholder"
        >
          <strong>Agent 执行流</strong>
          <span>当前 Session 没有可展示的 Agent 节点。</span>
        </div>
      </section>
    </div>
    <div
      v-else
      class="overview-empty"
    >
      从左侧选择一个 Session 查看概览。
    </div>
  </section>
</template>

<style scoped>
.overview {
  min-width: 0;
  overflow-y: auto;
  padding: 18px 20px;
}

.overview-content {
  display: grid;
  gap: 14px;
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
}

.detail-cta:disabled {
  cursor: not-allowed;
  opacity: .55;
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

.tree-legend {
  position: absolute;
  bottom: 17px;
  left: 18px;
  z-index: 6;
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: calc(100% - 96px);
  padding: 4px 9px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: color-mix(in srgb, var(--bg-card) 88%, transparent);
  color: var(--text-faint);
  font-size: 10px;
  flex-wrap: wrap;
}

.tree-legend .skill {
  color: var(--cyan);
}

.tree-legend .subagent {
  color: var(--purple);
}

.tree-legend .workflow {
  color: var(--orange);
}

.collapse-tree {
  margin-left: 4px;
  padding: 3px 9px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-dim);
  cursor: pointer;
  font: inherit;
  font-size: 11px;
}

.collapse-tree:hover {
  border-color: var(--border-strong);
  color: var(--text);
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
  place-items: center;
  min-height: 320px;
  color: var(--text-faint);
  font-size: 12px;
}

@media (max-width: 860px) {
  .tree-placeholder,
  .tree-panel :deep(.agent-tree) {
    min-height: 420px;
  }

}
</style>
