<script setup lang="ts">
import type {
  TargetOverviewDisabledItem,
  TargetOverviewItem,
} from "@harness/contracts";
import { computed } from "vue";

import ErrorState from "../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import AttributionRuntimeNotice from "../../evolution/targets/components/AttributionRuntimeNotice.vue";

const PAGE_SIZE = 5;

type EditItem = TargetOverviewItem | TargetOverviewDisabledItem;

type SideRow = {
  kind: "enabled" | "disabled";
  item: EditItem;
  id: string;
  objectType: TargetOverviewItem["objectType"];
  objectName: string;
  version: string;
  attributionSkillName: string | null;
  sessions: number;
  potential: number;
  attributed: number;
  nonTarget: number;
  unanalyzed: number;
  evolvable: number;
};

const props = defineProps({
  runtimeUnavailable: Boolean,
  items: {
    type: Array as () => TargetOverviewItem[],
    default: () => [],
  },
  disabled: {
    type: Array as () => TargetOverviewDisabledItem[],
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
  enable: [item: EditItem];
  edit: [item: EditItem];
  remove: [item: EditItem];
  retry: [];
}>();

const rows = computed<SideRow[]>(() => [
  ...props.items.map<SideRow>((item) => ({
    kind: "enabled",
    item,
    id: item.targetId,
    objectType: item.objectType,
    objectName: item.objectName,
    version: primaryVersion(item),
    attributionSkillName: item.attributionSkillName ?? null,
    sessions: item.sessions,
    potential: item.potential,
    attributed: item.attributed,
    nonTarget: item.nonTarget,
    unanalyzed: item.unanalyzed,
    evolvable: item.attributed + item.unanalyzed,
  })),
  ...props.disabled.map<SideRow>((item) => ({
    kind: "disabled",
    item,
    id: item.targetId,
    objectType: item.objectType,
    objectName: item.objectName,
    version: item.defaultRef,
    attributionSkillName: item.attributionSkillName ?? null,
    sessions: 0,
    potential: 0,
    attributed: 0,
    nonTarget: 0,
    unanalyzed: 0,
    evolvable: 0,
  })),
]);
const pages = computed(() =>
  Math.max(1, Math.ceil(rows.value.length / PAGE_SIZE)),
);
const safePage = computed(() =>
  Math.min(Math.max(1, props.page), pages.value),
);
const visible = computed(() =>
  rows.value.slice((safePage.value - 1) * PAGE_SIZE, safePage.value * PAGE_SIZE),
);
const selectedSet = computed(() => new Set(props.selected));
const pagerInfo = computed(() => {
  const disabled = props.disabled.length
    ? ` · ${props.disabled.length} 个已停用`
    : "";
  return `共 ${rows.value.length} 个${disabled} · 第 ${safePage.value} / ${pages.value} 页`;
});

function isSelected(id: string): boolean {
  return selectedSet.value.has(id);
}

function showsDisabledDivider(index: number): boolean {
  const row = visible.value[index];
  if (!row || row.kind !== "disabled") return false;
  const previous = visible.value[index - 1];
  return !previous || previous.kind !== "disabled";
}

function primaryVersion(item: TargetOverviewItem): string {
  return (
    item.versionOptions?.[0]?.ref ??
    item.versions[0] ??
    "—"
  );
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
      v-else-if="rows.length === 0"
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
        <template
          v-for="(row, index) in visible"
          :key="`${row.kind}-${row.id}`"
        >
          <div
            v-if="showsDisabledDivider(index)"
            class="side-group"
            data-testid="ov-target-side-disabled-group"
          >
            已停用对象 · 仅展示，不参与统计
          </div>
          <div
            v-if="row.kind === 'enabled'"
            class="side-item"
            :class="{ selected: isSelected(row.id) }"
            :data-testid="`ov-target-side-item-${row.id}`"
            :title="`${row.objectName} · 潜在 ${row.potential} · 是 ${row.attributed} / 非 ${row.nonTarget} / 未 ${row.unanalyzed}`"
          >
            <button
              class="select"
              type="button"
              :aria-pressed="isSelected(row.id)"
              @click="emit('toggle', row.id)"
            >
              <span class="top">
                <span class="title">
                  <span class="chip kind">{{ row.objectType }}</span>
                  <b>{{ row.objectName }}</b>
                  <span class="mono">@{{ row.version }}</span>
                </span>
              </span>
              <span class="meta">
                归因 Skill · {{ row.attributionSkillName || "未绑定" }}
                <AttributionRuntimeNotice
                  v-if="runtimeUnavailable && row.attributionSkillName"
                  badge
                />
              </span>
              <span class="meta">
                <span><b>{{ row.sessions }}</b> 关联 Session</span>
                <span><b>{{ row.potential }}</b> 潜在 bad case</span>
              </span>
              <span class="evolvable">
                可进化潜在 bad case 数量 <b>{{ row.evolvable }}</b>
                <span>（是问题 {{ row.attributed }}；未分析 {{ row.unanalyzed }}）</span>
              </span>
            </button>
            <div
              v-if="canManage"
              class="actions"
            >
              <button
                class="btn"
                :data-testid="`ov-target-side-edit-${row.id}`"
                type="button"
                @click.stop="emit('edit', row.item)"
              >
                编辑
              </button>
              <button
                class="btn danger"
                :data-testid="`ov-target-side-remove-${row.id}`"
                type="button"
                @click.stop="emit('remove', row.item)"
              >
                移除
              </button>
            </div>
          </div>
          <div
            v-else
            class="side-item is-disabled"
            :data-testid="`ov-target-side-disabled-row-${row.id}`"
            :title="`${row.objectName} · 已停用 · 不参与统计`"
          >
            <div class="top">
              <span class="title">
                <span class="chip kind">{{ row.objectType }}</span>
                <b>{{ row.objectName }}</b>
                <span class="mono">@{{ row.version }}</span>
                <span class="badge off">已停用</span>
              </span>
            </div>
            <span class="meta">归因 Skill · {{ row.attributionSkillName || "未绑定" }}</span>
            <span class="note">保留配置；重新启用后才进入筛选、图表与其它统计。</span>
            <div
              v-if="canManage"
              class="actions"
            >
              <button
                class="btn enable"
                :data-testid="`ov-target-side-enable-${row.id}`"
                type="button"
                @click.stop="emit('enable', row.item)"
              >
                启用
              </button>
              <button
                class="btn"
                :data-testid="`ov-target-side-edit-${row.id}`"
                type="button"
                @click.stop="emit('edit', row.item)"
              >
                编辑
              </button>
              <button
                class="btn danger"
                :data-testid="`ov-target-side-remove-${row.id}`"
                type="button"
                @click.stop="emit('remove', row.item)"
              >
                移除
              </button>
            </div>
          </div>
        </template>
      </div>
      <div
        class="pager"
        data-testid="ov-target-side-pager"
      >
        <span class="info">{{ pagerInfo }}</span>
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

.side-group {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed var(--border);
  color: var(--text-faint);
  font-size: 9.5px;
}

.side-item.is-disabled {
  margin-top: 6px;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-panel);
}

.side-item.is-disabled:first-child {
  border-top: 1px solid var(--border);
}

.side-item.is-disabled .title b {
  color: var(--text-faint);
}

.side-item.is-disabled .chip.kind {
  opacity: 0.55;
}

.side-item.is-disabled .meta,
.side-item.is-disabled .note {
  color: var(--text-faint);
}

.note {
  display: block;
  margin-top: 4px;
  font-size: 9.5px;
}

.badge.off {
  padding: 0 5px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-panel);
  color: var(--text-faint);
  font-size: 9px;
}

.btn.enable {
  border-color: color-mix(in srgb, var(--green) 40%, var(--border));
  color: var(--green);
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
