<script setup lang="ts">
import type {
  OverviewWindow,
  TargetDetailResponse,
  TargetVersionOption,
} from "@harness/contracts";
import { computed } from "vue";

import type { TargetOverviewItemView } from "../../../api/overview";
import ErrorState from "../../../components/ui/ErrorState.vue";
import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";
import type {
  DetailVersionLimit,
  OverviewUrlState,
} from "../overviewUrl";

const LIMITS: DetailVersionLimit[] = [5, 10, 20, "all"];

const props = defineProps({
  targets: {
    type: Array as () => TargetOverviewItemView[],
    default: () => [],
  },
  state: {
    type: Object as () => OverviewUrlState,
    required: true,
  },
  sharedWindow: {
    type: Object as () => OverviewWindow | null,
    default: null,
  },
  detail: {
    type: Object as () => TargetDetailResponse | null,
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
  code: {
    type: String,
    default: "OVERVIEW_TARGET_DETAIL_UNAVAILABLE",
  },
});

const emit = defineEmits<{
  "update:target": [targetId: string];
  "update:versions": [versions: string[]];
  "update:window": [window: { from: string; to: string } | null];
  "update:limit": [limit: DetailVersionLimit];
  create: [];
  retry: [];
}>();

const activeTarget = computed(
  () =>
    props.targets.find((item) => item.targetId === props.state.detailTarget) ??
    props.targets[0] ??
    null,
);
const versionOptions = computed<string[]>(
  () => props.detail?.target.versions ?? activeTarget.value?.versions ?? [],
);
const versionMeta = computed(() => {
  const options: TargetVersionOption[] =
    props.detail?.target.versionOptions ??
    activeTarget.value?.versionOptions ??
    [];
  return new Map(
    options.map((option) => [
      option.version,
      { ref: option.ref ?? null, commit: option.commit ?? null },
    ]),
  );
});
const selectedVersions = computed(() => new Set(props.state.detailVersions));
const activeMembers = computed(() => activeTarget.value?.members ?? []);
const activeMemberCount = computed(() =>
  activeMembers.value.length > 1 ? activeMembers.value.length : 0,
);

function versionRef(version: string): string {
  return versionMeta.value.get(version)?.ref ?? version;
}

function versionCommit(version: string): string | null {
  return versionMeta.value.get(version)?.commit ?? null;
}
const effectiveFrom = computed(
  () => props.state.detailFrom || props.sharedWindow?.from || "",
);
const effectiveTo = computed(
  () => props.state.detailTo || props.sharedWindow?.to || "",
);
const overridden = computed(
  () => Boolean(props.state.detailFrom && props.state.detailTo),
);
const versionSummary = computed(() => {
  if (props.state.detailVersions.length > 0) {
    return `已选 ${props.state.detailVersions.length} 个版本`;
  }
  const total = versionOptions.value.length;
  if (props.state.detailLimit === "all" || total <= props.state.detailLimit) {
    return `全部 ${total} 个版本`;
  }
  return `最近 ${props.state.detailLimit} 个版本`;
});
const scopeText = computed(() => {
  const total = versionOptions.value.length;
  const shown = props.detail?.stats.versions ?? 0;
  if (props.state.detailVersions.length > 0) {
    return `当前查看已选的 ${shown} 个`;
  }
  if (props.state.detailLimit === "all" || shown >= total) {
    return `当前查看全部 ${total} 个`;
  }
  return `当前查看最近 ${shown} 个`;
});
const nextLimit = computed<DetailVersionLimit>(() => {
  const shown = props.detail?.stats.versions ?? 0;
  if (shown < 10) return 10;
  if (shown < 20) return 20;
  return "all";
});
const canExpand = computed(
  () =>
    props.state.detailVersions.length === 0 &&
    props.state.detailLimit !== "all" &&
    versionOptions.value.length > (props.detail?.stats.versions ?? 0),
);
const maxVersionPotential = computed(() =>
  Math.max(1, ...(props.detail?.byVersion.map((row) => row.potential) ?? [1])),
);
const maxSourceTotal = computed(() =>
  Math.max(1, ...(props.detail?.bySource.map((row) => row.total) ?? [1])),
);
const scopedCounts = computed(() => {
  const rows = props.detail?.byVersion ?? [];
  return rows.reduce(
    (sum, row) => ({
      attributed: sum.attributed + row.attributed,
      nonTarget: sum.nonTarget + row.nonTarget,
      unanalyzed: sum.unanalyzed + row.unanalyzed,
    }),
    { attributed: 0, nonTarget: 0, unanalyzed: 0 },
  );
});

function limitLabel(limit: DetailVersionLimit): string {
  return limit === "all" ? "全部" : String(limit);
}

function toggleVersion(version: string, checked: boolean): void {
  const next = new Set(props.state.detailVersions);
  if (checked) next.add(version);
  else next.delete(version);
  emit("update:versions", [...next]);
}

function windowChanged(field: "from" | "to", event: Event): void {
  const value = (event.target as HTMLInputElement).value;
  const from = field === "from" ? value : effectiveFrom.value;
  const to = field === "to" ? value : effectiveTo.value;
  if (from && to && from <= to) {
    emit("update:window", { from, to });
  }
}

function targetChanged(event: Event): void {
  emit("update:target", (event.target as HTMLSelectElement).value);
}

function versionChanged(version: string, event: Event): void {
  toggleVersion(version, (event.target as HTMLInputElement).checked);
}
</script>

<template>
  <section
    class="td-card"
    data-testid="ov-target-detail"
  >
    <div class="td-head">
      <h2>单个进化对象分析</h2>
      <p>选一个对象，按版本与时间看它的关联 Session、潜在 bad case 与来源构成</p>
    </div>

    <div
      v-if="targets.length === 0"
      class="td-empty"
      data-testid="ov-target-detail-empty"
    >
      <b>当前空间还没有启用中的进化对象</b>
      <span>先到进化对象配置新增并启用对象，再回来查看单个对象的关联 Session 与来源分布。</span>
      <button
        class="btn primary"
        data-testid="ov-target-detail-empty-create"
        type="button"
        @click="emit('create')"
      >
        去配置进化对象 →
      </button>
    </div>

    <template v-else>
      <div class="td-toolbar">
        <label class="group">
          <span class="label">进化对象</span>
          <select
            class="inp"
            data-testid="ov-target-detail-target"
            :value="activeTarget?.targetId ?? ''"
            @change="targetChanged"
          >
            <option
              v-for="item in targets"
              :key="item.targetId"
              :value="item.targetId"
            >
              {{ item.objectName }} · {{ item.objectType }}<template v-if="(item.members?.length ?? 0) > 1"> · {{ item.members?.length }} 个对象</template>
            </option>
          </select>
        </label>

        <span class="sep" />

        <div class="group">
          <span class="label">版本</span>
          <details
            class="version-multi"
            data-testid="ov-target-detail-versions"
          >
            <summary>
              {{ versionSummary }}
              <span
                class="caret"
                aria-hidden="true"
              >⌄</span>
            </summary>
            <div class="version-menu">
              <label
                v-for="version in versionOptions"
                :key="version"
                class="version-option"
              >
                <input
                  type="checkbox"
                  :checked="selectedVersions.has(version)"
                  :data-version="version"
                  :data-testid="`ov-target-detail-version-${version}`"
                  @change="versionChanged(version, $event)"
                >
                <span class="mono">{{ versionRef(version) }}</span>
                <span
                  v-if="versionCommit(version)"
                  class="mono commit"
                >{{ versionCommit(version) }}</span>
              </label>
              <p
                v-if="versionOptions.length === 0"
                class="no-options"
              >
                当前窗口没有已观测版本
              </p>
              <div class="limit-row">
                <span>默认显示最近</span>
                <span class="limit-btns">
                  <button
                    v-for="limit in LIMITS"
                    :key="limit"
                    type="button"
                    :class="{ on: state.detailLimit === limit }"
                    :data-testid="`ov-target-detail-limit-${limit}`"
                    @click="emit('update:limit', limit)"
                  >
                    {{ limitLabel(limit) }}
                  </button>
                </span>
              </div>
            </div>
          </details>
        </div>

        <span class="spacer" />

        <div class="group">
          <span class="label">时间</span>
          <input
            class="inp"
            data-testid="ov-target-detail-from"
            type="date"
            :value="effectiveFrom"
            aria-label="对象卡开始日期"
            @change="windowChanged('from', $event)"
          >
          <span class="label">~</span>
          <input
            class="inp"
            data-testid="ov-target-detail-to"
            type="date"
            :value="effectiveTo"
            aria-label="对象卡结束日期"
            @change="windowChanged('to', $event)"
          >
          <button
            v-if="overridden"
            class="follow"
            data-testid="ov-target-detail-follow"
            type="button"
            @click="emit('update:window', null)"
          >
            跟随总览
          </button>
        </div>
      </div>

      <div
        v-if="activeMemberCount > 1"
        class="member-strip"
        data-testid="ov-target-detail-members"
      >
        <span class="label">配置成员</span>
        <span
          v-for="member in activeMembers"
          :key="`${member.objectType}:${member.objectName}`"
          class="chip member"
          :title="member.subDir"
        >{{ member.objectType }}:{{ member.objectName }}</span>
        <span class="hint">单对象分析按该配置首个成员展开；成员明细来自后端 members。</span>
      </div>

      <LoadingSkeleton
        v-if="loading"
        data-testid="ov-target-detail-loading"
        label="正在加载对象分析"
        :rows="3"
      />
      <ErrorState
        v-else-if="error"
        :code="code"
        data-testid="ov-target-detail-error"
        message="单对象分析加载失败，请重试；其它区块不受影响。"
        @retry="emit('retry')"
      />
      <template v-else>
        <div class="statstrip">
          <div class="cell">
            <b data-testid="ov-target-detail-sessions">{{ detail?.stats.sessions ?? 0 }}</b>
            <span>关联 Session</span>
          </div>
          <div class="cell">
            <b data-testid="ov-target-detail-potential">{{ detail?.stats.potential ?? 0 }}</b>
            <span>潜在 bad case</span>
          </div>
          <div class="cell">
            <b data-testid="ov-target-detail-distinct">{{ detail?.stats.distinctCases ?? 0 }}</b>
            <span>去重后 bad case</span>
          </div>
          <div class="cell">
            <b data-testid="ov-target-detail-versions-count">{{ detail?.stats.versions ?? 0 }}</b>
            <span>覆盖版本</span>
          </div>
        </div>

        <div class="td-grid">
          <section class="sec">
            <div class="sec-head">
              <div class="sec-title">
                潜在 bad case 分布 <span>按版本汇总；柱长按最大值归一</span>
              </div>
              <div class="legend">
                <span><i class="dot attributed" />是 {{ scopedCounts.attributed }}</span>
                <span><i class="dot nonTarget" />非 {{ scopedCounts.nonTarget }}</span>
                <span><i class="dot unanalyzed" />未 {{ scopedCounts.unanalyzed }}</span>
              </div>
            </div>
            <p
              v-if="(detail?.byVersion.length ?? 0) === 0"
              class="waiting"
            >
              当前条件下没有关联 Session 或潜在 bad case
            </p>
            <div
              v-for="row in detail?.byVersion ?? []"
              :key="row.version"
              class="row"
              data-testid="ov-target-detail-version-row"
              :title="`${row.ref ?? row.version}${row.commit ? ' ' + row.commit : ''} · 潜在 ${row.potential} · 是 ${row.attributed} / 非 ${row.nonTarget} / 未 ${row.unanalyzed}`"
            >
              <span
                class="name mono"
                data-testid="ov-target-detail-version-label"
              >
                <span>{{ row.ref ?? row.version }}</span>
                <span
                  v-if="row.commit"
                  class="commit"
                >{{ row.commit }}</span>
              </span>
              <span class="bar">
                <span
                  class="fill"
                  :style="{ width: `${(row.potential / maxVersionPotential) * 100}%` }"
                >
                  <span
                    class="seg attributed"
                    :style="{ width: `${row.potential ? (row.attributed / row.potential) * 100 : 0}%` }"
                  />
                  <span
                    class="seg nonTarget"
                    :style="{ width: `${row.potential ? (row.nonTarget / row.potential) * 100 : 0}%` }"
                  />
                  <span
                    class="seg unanalyzed"
                    :style="{ width: `${row.potential ? (row.unanalyzed / row.potential) * 100 : 0}%` }"
                  />
                </span>
              </span>
              <span class="num">
                <b>{{ row.potential }}</b> · 是 {{ row.attributed }} / 非 {{ row.nonTarget }} / 未 {{ row.unanalyzed }}
              </span>
            </div>
          </section>

          <section class="sec">
            <div class="sec-head">
              <div class="sec-title">
                bad case 来源分布 <span>当前对象、版本与时间段</span>
              </div>
            </div>
            <p
              v-if="(detail?.bySource.length ?? 0) === 0"
              class="waiting"
            >
              当前条件下没有潜在 bad case
            </p>
            <div
              v-for="row in detail?.bySource ?? []"
              :key="row.source"
              class="row"
              data-testid="ov-target-detail-source-row"
              :title="`${row.source} · 潜在 bad case ${row.total} 条 · 去重后 ${row.distinctCases} 个`"
            >
              <span class="name">{{ row.source }}</span>
              <span class="bar">
                <span
                  class="fill source"
                  :style="{ width: `${(row.total / maxSourceTotal) * 100}%` }"
                />
              </span>
              <span class="num"><b>{{ row.total }}</b><span class="faint"> · 去重 {{ row.distinctCases }}</span></span>
            </div>
          </section>
        </div>

        <div class="footnote">
          共 {{ versionOptions.length }} 个版本 · {{ scopeText }}
          <button
            v-if="canExpand"
            type="button"
            :data-testid="`ov-target-detail-expand-${nextLimit}`"
            @click="emit('update:limit', nextLimit)"
          >
            {{ nextLimit === "all" ? "查看全部" : `展开到 ${nextLimit}` }}
          </button>
        </div>
      </template>
    </template>
  </section>
</template>

<style scoped>
.td-card {
  margin-bottom: 14px;
  padding: 16px 18px 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.td-head {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  align-items: baseline;
}

.td-head h2 {
  margin: 0;
  color: var(--text);
  font-size: 15px;
}

.td-head p {
  margin: 0;
  color: var(--text-faint);
  font-size: 11px;
}

.td-empty {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
  padding: 24px 10px;
  color: var(--text-faint);
  font-size: 11px;
}

.td-empty b {
  color: var(--text-dim);
  font-size: 12.5px;
}

.btn {
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 11px;
  cursor: pointer;
}

.btn.primary {
  border-color: var(--blue);
  background: var(--blue);
  color: var(--bg-card);
}

.member-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin: 0 0 10px;
  color: var(--text-faint);
  font-size: 11px;
}

.chip.member {
  padding: 1px 8px;
  border: 1px solid color-mix(in srgb, var(--purple) 30%, var(--border));
  border-radius: 999px;
  color: var(--purple);
  font-family: var(--mono);
  font-size: 10px;
}

.member-strip .hint {
  color: var(--text-faint);
  font-size: 10.5px;
}

.td-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  align-items: center;
  margin: 12px 0 10px;
  padding: 7px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-panel);
}

.group {
  display: flex;
  gap: 7px;
  align-items: center;
}

.label {
  color: var(--text-faint);
  font-size: 10px;
  white-space: nowrap;
}

.inp {
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  color: var(--text);
  font-size: 11.5px;
}

.inp:focus-visible {
  border-color: var(--blue);
  outline: none;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--blue) 10%, transparent);
}

select.inp {
  min-width: 168px;
  max-width: 240px;
}

.sep {
  width: 1px;
  height: 18px;
  background: var(--border);
}

.spacer {
  flex: 1;
}

.version-multi {
  position: relative;
}

.version-multi summary {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 168px;
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 11.5px;
  list-style: none;
  cursor: pointer;
}

.version-multi summary::-webkit-details-marker {
  display: none;
}

.version-multi[open] summary,
.version-multi summary:hover {
  border-color: var(--blue);
  color: var(--text);
}

.caret {
  margin-left: auto;
  color: var(--text-faint);
  font-size: 9px;
}

.version-menu {
  position: absolute;
  top: calc(100% + 5px);
  left: 0;
  z-index: 40;
  display: flex;
  flex-direction: column;
  width: 296px;
  max-height: 290px;
  padding: 5px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  box-shadow: var(--shadow-popover);
}

.version-option {
  display: flex;
  gap: 7px;
  align-items: center;
  padding: 5px 7px;
  border-radius: 5px;
  color: var(--text-dim);
  font-size: 11px;
  cursor: pointer;
}

.version-option:hover {
  background: var(--bg-panel);
}

.version-option input {
  accent-color: var(--blue);
}

.mono {
  font-family: var(--mono);
}

.commit {
  margin-left: 4px;
  color: var(--text-faint);
}

.no-options {
  margin: 6px 7px;
  color: var(--text-faint);
  font-size: 10.5px;
}

.limit-row {
  display: flex;
  gap: 6px;
  align-items: center;
  justify-content: space-between;
  margin-top: 4px;
  padding: 5px 6px 1px;
  border-top: 1px solid var(--border);
  color: var(--text-faint);
  font-size: 10px;
}

.limit-btns {
  display: flex;
  gap: 4px;
}

.limit-btns button {
  padding: 1px 7px;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: var(--bg-card);
  color: var(--text-dim);
  font-size: 10px;
  cursor: pointer;
}

.limit-btns button.on {
  border-color: var(--blue);
  color: var(--blue);
}

.follow {
  height: 28px;
  padding: 0 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--blue);
  font-size: 10.5px;
  cursor: pointer;
}

.statstrip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-bottom: 16px;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 10px;
}

.cell {
  padding: 9px 14px;
  border-right: 1px solid var(--border);
}

.cell:last-child {
  border-right: 0;
}

.cell b {
  display: block;
  color: var(--text);
  font-family: var(--mono);
  font-variant-numeric: tabular-nums;
  font-size: 18px;
  line-height: 1.2;
}

.cell span {
  color: var(--text-faint);
  font-size: 10px;
}

.td-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.18fr) minmax(0, 1fr);
}

.sec {
  min-width: 0;
}

.sec:first-child {
  padding-right: 22px;
}

.sec + .sec {
  padding-left: 22px;
  border-left: 1px solid var(--border);
}

.sec-head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 10px;
  align-items: baseline;
  margin-bottom: 6px;
}

.sec-title {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  align-items: baseline;
  color: var(--text);
  font-size: 12px;
  font-weight: 650;
}

.sec-title span {
  color: var(--text-faint);
  font-size: 10px;
  font-weight: 400;
}

.legend {
  display: flex;
  gap: 10px;
  margin-left: auto;
  color: var(--text-faint);
  font-size: 10px;
  white-space: nowrap;
}

.dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  margin-right: 4px;
  border-radius: 50%;
}

.dot.attributed {
  background: var(--green);
}

.dot.nonTarget {
  background: var(--orange);
}

.dot.unanalyzed {
  background: var(--border-strong);
}

.row {
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr) 172px;
  gap: 10px;
  align-items: center;
  padding: 4px 0;
}

.name {
  overflow: hidden;
  color: var(--text-dim);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bar {
  height: 7px;
  overflow: hidden;
  border-radius: 4px;
  background: var(--density-track);
}

.fill {
  display: flex;
  height: 100%;
  overflow: hidden;
  border-radius: 4px;
  background: var(--density-track);
}

.seg {
  height: 100%;
}

.seg.attributed {
  background: var(--green);
}

.seg.nonTarget {
  background: var(--orange);
}

.seg.unanalyzed {
  background: var(--border-strong);
}

.fill.source {
  background: var(--purple);
}

.num {
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 9.5px;
  white-space: nowrap;
}

.num b {
  color: var(--text);
  font-size: 11px;
  font-weight: 600;
}

.faint {
  color: var(--text-faint);
}

.waiting {
  margin: 4px 0;
  color: var(--text-faint);
  font-size: 10.5px;
}

.footnote {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
  color: var(--text-faint);
  font-size: 10px;
}

.footnote button {
  padding: 1px 7px;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: var(--bg-card);
  color: var(--blue);
  font-size: 10px;
  cursor: pointer;
}

@media (max-width: 1100px) {
  .td-grid {
    grid-template-columns: 1fr;
  }

  .sec:first-child {
    padding-right: 0;
  }

  .sec + .sec {
    margin-top: 14px;
    padding-top: 12px;
    padding-left: 0;
    border-top: 1px solid var(--border);
    border-left: 0;
  }

  .statstrip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .cell:nth-child(2) {
    border-right: 0;
  }
}
</style>
