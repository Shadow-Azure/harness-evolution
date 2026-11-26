<script setup lang="ts">
import { computed } from "vue";

import type { TargetOverviewItemView } from "../../../api/overview";
import ErrorState from "../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import AttributionRuntimeNotice from "../../evolution/targets/components/AttributionRuntimeNotice.vue";

const PAGE_SIZE = 5;

const props = defineProps({
  runtimeUnavailable: Boolean,
  items: {
    type: Array as () => TargetOverviewItemView[],
    default: () => [],
  },
  page: {
    type: Number,
    default: 1,
  },
  selected: {
    type: Array as () => string[],
    default: () => [],
  },
  canManage: {
    type: Boolean,
    default: false,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: Object as () => Error | null,
    default: null,
  },
  code: {
    type: String,
    default: "OVERVIEW_TARGETS_UNAVAILABLE",
  },
});

const emit = defineEmits<{
  "update:page": [value: number];
  toggle: [targetId: string];
  create: [];
  edit: [item: TargetOverviewItemView];
  remove: [item: TargetOverviewItemView];
  retry: [];
}>();

const pages = computed(() =>
  Math.max(1, Math.ceil(props.items.length / PAGE_SIZE)),
);
const safePage = computed(() =>
  Math.min(Math.max(1, props.page), pages.value),
);
const visible = computed(() =>
  props.items.slice((safePage.value - 1) * PAGE_SIZE, safePage.value * PAGE_SIZE),
);
const selectedSet = computed(() => new Set(props.selected));

function isSelected(id: string): boolean {
  return selectedSet.value.has(id);
}

function membersOf(item: TargetOverviewItemView) {
  return item.members && item.members.length > 0 ? item.members : [];
}

function primaryVersion(item: TargetOverviewItemView): string {
  return (
    item.versionOptions?.[0]?.ref ??
    item.versions[0] ??
    "—"
  );
}

function evolvable(item: TargetOverviewItemView): number {
  return item.attributed + item.unanalyzed;
}
</script>

<template>
  <aside
    class="side-card"
    data-testid="ov-target-side-list"
  >
    <header class="side-head">
      <div>
        <h3>进化对象</h3>
        <p>按可进化潜在 bad case 排序</p>
      </div>
      <button
        v-if="canManage"
        class="btn"
        data-testid="ov-target-side-create"
        type="button"
        @click="emit('create')"
      >
        + 新增
      </button>
    </header>

    <LoadingSkeleton
      v-if="loading"
      data-testid="ov-target-side-loading"
      label="正在读取进化对象"
      :rows="4"
    />
    <ErrorState
      v-else-if="error"
      :code="code"
      data-testid="ov-target-side-error"
      message="进化对象列表加载失败，请重试。"
      @retry="emit('retry')"
    />
    <div
      v-else-if="items.length === 0"
      class="empty"
      data-testid="ov-target-side-empty"
    >
      <b>当前空间还没有进化对象</b>
      <span>{{ canManage ? "先新增一个 skill、agent 或知识库对象。" : "请联系空间管理员配置进化对象。" }}</span>
      <button
        v-if="canManage"
        class="btn primary"
        data-testid="ov-target-side-empty-create"
        type="button"
        @click="emit('create')"
      >
        去配置进化对象 →
      </button>
    </div>
    <template v-else>
      <div class="side-list">
        <div
          v-for="item in visible"
          :key="item.targetId"
          class="side-item"
          :class="{ selected: isSelected(item.targetId) }"
          :data-testid="`ov-target-side-item-${item.targetId}`"
          :title="`${item.objectName} · 潜在 ${item.potential} · 是 ${item.attributed} / 非 ${item.nonTarget} / 未 ${item.unanalyzed}`"
        >
          <button
            class="select"
            type="button"
            :aria-pressed="isSelected(item.targetId)"
            @click="emit('toggle', item.targetId)"
          >
            <span class="top">
              <span class="title">
                <span class="chip kind">{{ item.objectType }}</span>
                <b>{{ item.objectName }}</b>
                <span class="mono">@{{ primaryVersion(item) }}</span>
              </span>
            </span>
            <span
              v-if="membersOf(item).length > 1"
              class="members"
              data-testid="ov-target-side-members"
            >
              <span
                v-for="member in membersOf(item)"
                :key="`${member.objectType}:${member.objectName}`"
                class="chip"
                :title="member.subDir"
              >{{ member.objectType }}:{{ member.objectName }}</span>
            </span>
            <span class="meta">
              归因 Skill · {{ item.attributionSkillName || "未绑定" }}
              <AttributionRuntimeNotice
                v-if="runtimeUnavailable && item.attributionSkillName"
                badge
              />
            </span>
            <span class="meta">
              <span><b>{{ item.sessions }}</b> 关联 Session</span>
              <span><b>{{ item.potential }}</b> 潜在 bad case</span>
            </span>
            <span class="evolvable">
              可进化潜在 bad case 数量 <b>{{ evolvable(item) }}</b>
              <span>（是问题 {{ item.attributed }}；未分析 {{ item.unanalyzed }}）</span>
            </span>
          </button>
          <div
            v-if="canManage"
            class="actions"
          >
            <button
              class="btn"
              :data-testid="`ov-target-side-edit-${item.targetId}`"
              type="button"
              @click.stop="emit('edit', item)"
            >
              编辑
            </button>
            <button
              class="btn danger"
              :data-testid="`ov-target-side-remove-${item.targetId}`"
              type="button"
              @click.stop="emit('remove', item)"
            >
              移除
            </button>
          </div>
        </div>
      </div>
      <div
        class="pager"
        data-testid="ov-target-side-pager"
      >
        <span class="info">共 {{ items.length }} 个 · 第 {{ safePage }} / {{ pages }} 页</span>
        <button
          :disabled="safePage <= 1"
          data-testid="ov-target-side-prev"
          type="button"
          @click="emit('update:page', safePage - 1)"
        >
          ← 上一页
        </button>
        <button
          :disabled="safePage >= pages"
          data-testid="ov-target-side-next"
          type="button"
          @click="emit('update:page', safePage + 1)"
        >
          下一页 →
        </button>
      </div>
    </template>
  </aside>
</template>

<style scoped>
.side-card {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 14px 14px 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.side-head {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 8px;
}

.side-head h3 {
  margin: 0;
  color: var(--text);
  font-size: 14px;
}

.side-head p {
  margin: 2px 0 0;
  color: var(--text-faint);
  font-size: 10px;
}

.btn {
  height: 26px;
  padding: 0 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 10.5px;
  white-space: nowrap;
  cursor: pointer;
}

.btn:hover {
  border-color: var(--blue);
  color: var(--text);
}

.btn.primary {
  border-color: var(--blue);
  background: var(--blue);
  color: var(--bg-card);
}

.btn.danger {
  border-color: color-mix(in srgb, var(--red) 28%, var(--border));
  color: var(--red);
}

.side-list {
  flex: 1 1 auto;
  min-height: 0;
}

.side-item {
  padding: 7px 0;
  border-top: 1px solid var(--border);
}

.side-item:first-child {
  border-top: 0;
}

.side-item.selected {
  border-radius: 7px;
  background: color-mix(in srgb, var(--blue) 5%, transparent);
  box-shadow: inset 2px 0 0 var(--blue);
}

.select {
  display: block;
  width: 100%;
  padding: 0 6px;
  border: 0;
  background: none;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.top {
  display: block;
}

.title {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  min-width: 0;
}

.title b {
  color: var(--text);
  font-size: 12.5px;
}

.chip.kind {
  padding: 0 5px;
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 9px;
}

.mono {
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 10px;
}

.members {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.members .chip {
  padding: 0 6px;
  border: 1px solid color-mix(in srgb, var(--purple) 30%, var(--border));
  border-radius: 999px;
  color: var(--purple);
  font-family: var(--mono);
  font-size: 9px;
}

.meta {
  display: flex;
  gap: 12px;
  margin-top: 4px;
  color: var(--text-dim);
  font-size: 10px;
}

.meta b {
  color: var(--text);
  font-family: var(--mono);
  font-size: 12px;
}

.evolvable {
  display: block;
  margin-top: 3px;
  color: var(--text-dim);
  font-size: 10px;
}

.evolvable b {
  color: var(--text);
  font-family: var(--mono);
  font-size: 12px;
}

.evolvable span {
  color: var(--text-faint);
}

.actions {
  display: flex;
  gap: 5px;
  justify-content: flex-end;
  margin-top: 4px;
}

.actions .btn {
  height: auto;
  padding: 1px 6px;
  font-size: 9.5px;
}

.empty {
  display: flex;
  flex-direction: column;
  gap: 5px;
  align-items: flex-start;
  padding: 24px 8px;
  color: var(--text-faint);
  font-size: 10.5px;
}

.empty b {
  color: var(--text-dim);
  font-size: 12px;
}

.empty .btn {
  margin-top: 4px;
  height: 28px;
  padding: 0 10px;
}

.pager {
  display: flex;
  gap: 7px;
  align-items: center;
  margin-top: auto;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.pager .info {
  flex: 1;
  color: var(--text-faint);
  font-size: 9px;
}

.pager button {
  padding: 2px 7px;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 9.5px;
  cursor: pointer;
}

.pager button:disabled {
  color: var(--text-faint);
  cursor: not-allowed;
  opacity: 0.55;
}
</style>
