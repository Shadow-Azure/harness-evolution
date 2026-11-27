<script setup lang="ts">
import type { EvolutionStepRange } from "@harness/contracts";
import { computed } from "vue";

type RangeMember = NonNullable<
  EvolutionStepRange["payload"]["condition"]["targets"]
>[number];

const props = withDefaults(
  defineProps<{
    step: EvolutionStepRange;
    targetRevision?: string | null;
    sharedProject?: {
      validationProjectId: string;
      testProjectId: string;
      primaryMetricKey: string;
    } | null;
    subDirs?: string[];
  }>(),
  {
    targetRevision: null,
    sharedProject: null,
    subDirs: () => [],
  },
);

const condition = computed(() => props.step.payload.condition);
const stats = computed(() => props.step.payload.stats);
const effectiveTargetRevision = computed(
  () => condition.value.targetRevision || props.targetRevision || null,
);

const members = computed<RangeMember[]>(() => {
  const configured = condition.value.targets ?? [];
  if (configured.length > 0) {
    return configured;
  }
  return [
    {
      objectType: condition.value.targetType,
      objectName: condition.value.targetName,
      targetVersion: condition.value.targetVersion,
      targetRevision: condition.value.targetRevision,
      subDir: "",
    },
  ];
});

const targetLabel = computed(() => {
  const list = members.value;
  const first = list[0];
  if (!first) {
    return "—";
  }
  const extra = list.length > 1 ? ` +${list.length - 1}` : "";
  return `${first.objectType}:${first.objectName}${extra}@${first.targetVersion}`;
});

const changeScope = computed(() => {
  const configured = props.subDirs ?? [];
  if (configured.length > 0) {
    return configured;
  }
  return members.value
    .map((member) => member.subDir)
    .filter((subDir): subDir is string => Boolean(subDir));
});

const windowLabel = computed(() => {
  const { from, to } = condition.value;
  if (from && to) return `${from} ~ ${to}`;
  if (from) return `${from} ~ 至今`;
  if (to) return `起始未知 ~ ${to}`;
  return "时间窗未设置";
});

const policyPreset = computed(() => {
  const preset = condition.value.policy.preset;
  return typeof preset === "string" ? preset : "";
});

const isDefaultPolicy = computed(
  () =>
    policyPreset.value === "default" ||
    Object.keys(condition.value.policy).length === 0,
);

const policyLabel = computed(() =>
  isDefaultPolicy.value ? "默认策略" : "自定义策略",
);

const policyDetail = computed(() => {
  if (!isDefaultPolicy.value) {
    return JSON.stringify(condition.value.policy);
  }
  return members.value.length > 1
    ? "任一成员自身 self 上报 或 触发点在任一成员之后"
    : "对象自身 self 上报 或 触发点在对象之后";
});

const cacheLabel = computed(() =>
  condition.value.cacheEnabled ? "复用最近一次成功归因" : "全部重新归因",
);
</script>

<template>
  <article class="card panel">
    <h3 class="sec-title">
      第 1 步 · 选择范围
      <span class="sub">进化对象 + 版本 + bad case 时间段</span>
    </h3>
    <div class="wz-stats">
      <span class="st"><b>{{ stats.sessions }}</b><span>时间段内 Session</span></span>
      <span class="st"><b>{{ stats.badCases }}</b><span>时间段内 bad case</span></span>
      <span class="st accent"><b>{{ stats.potential }}</b><span>潜在 bad case</span></span>
    </div>
    <table class="rep">
      <tbody>
        <tr>
          <th>进化对象</th>
          <td><span class="chip kind">{{ targetLabel }}</span></td>
          <th>工作空间</th>
          <td
            class="mono"
            :title="condition.workspaceId"
          >
            {{ condition.workspaceId }}
          </td>
        </tr>
        <tr>
          <th>成员与子目录</th>
          <td
            colspan="3"
            data-testid="step-range-members"
          >
            <div class="scope-members">
              <div
                v-for="member in members"
                :key="`${member.objectType}:${member.objectName}`"
                class="scope-member"
              >
                <span class="chip kind">{{ member.objectType }}:{{ member.objectName }}</span>
                <span class="mono sub">{{ member.subDir || "—" }}</span>
                <span
                  v-if="member.targetRevision"
                  class="mono revision-inline"
                  :title="member.targetRevision"
                >{{ member.targetRevision }}</span>
              </div>
              <p
                v-if="members.length > 1"
                class="member-note"
              >
                全部成员共用版本 {{ condition.targetVersion }}；每个成员各自冻结定义并提交评测资产。
              </p>
            </div>
          </td>
        </tr>
        <tr
          v-if="sharedProject"
          data-testid="step-range-test-project"
        >
          <th>测试工程</th>
          <td
            colspan="3"
            class="mono project-cell"
          >
            验证集 {{ sharedProject.validationProjectId || "—" }} · 测试集 {{ sharedProject.testProjectId || "—" }} · 主指标 {{ sharedProject.primaryMetricKey || "—" }}
            <span class="member-note">成员共用一套；一次评测提交全部成员资产</span>
          </td>
        </tr>
        <tr>
          <th>目标 revision</th>
          <td
            class="mono revision-cell"
            colspan="3"
          >
            <span
              v-if="effectiveTargetRevision"
              data-testid="step-target-revision"
              :title="effectiveTargetRevision"
            >{{ effectiveTargetRevision }}</span>
            <span
              v-else
              class="revision-missing"
              data-testid="step-target-revision-missing"
            >历史运行未记录 revision</span>
          </td>
        </tr>
        <tr>
          <th>bad case 时间段</th>
          <td class="mono">
            {{ windowLabel }}
          </td>
          <th>缓存归因</th>
          <td>{{ cacheLabel }}</td>
        </tr>
        <tr>
          <th>潜在策略</th>
          <td colspan="3">
            <span
              class="policy-badge"
              :class="{ default: isDefaultPolicy }"
            >{{ policyLabel }}</span>
            <span class="policy-detail">{{ policyDetail }}</span>
          </td>
        </tr>
        <tr
          v-if="changeScope.length > 0"
          data-testid="step-range-change-scope"
        >
          <th>改动范围</th>
          <td
            colspan="3"
            class="mono"
          >
            <div
              v-for="dir in changeScope"
              :key="dir"
            >
              {{ dir }}/**
            </div>
            <span class="member-note">agent-edit 只允许改这些目录</span>
          </td>
        </tr>
      </tbody>
    </table>
  </article>
</template>

<style scoped>
.card {
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

.wz-stats {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.st {
  color: var(--text-faint);
  font-size: 11px;
}

.st b {
  margin-right: 3px;
  color: var(--text);
  font-family: var(--mono);
  font-size: 14px;
  font-weight: 650;
}

.st.accent b {
  color: var(--blue);
}

table.rep {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

table.rep th,
table.rep td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}

table.rep th {
  width: 150px;
  color: var(--text-faint);
  font-size: 11px;
  font-weight: 600;
}

table.rep tr:last-child th,
table.rep tr:last-child td {
  border-bottom: 0;
}

.chip {
  display: inline-block;
  padding: 1px 9px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 10.5px;
  white-space: nowrap;
}

.chip.kind {
  border-color: color-mix(in srgb, var(--purple) 35%, transparent);
  background: color-mix(in srgb, var(--purple) 9%, transparent);
  color: var(--purple);
  font-family: var(--mono);
}

.policy-badge {
  display: inline-block;
  margin-right: 8px;
  padding: 1px 9px;
  border: 1px solid color-mix(in srgb, var(--orange) 35%, transparent);
  border-radius: 999px;
  color: var(--orange);
  font-size: 10.5px;
  white-space: nowrap;
}

.policy-badge.default {
  border-color: color-mix(in srgb, var(--green) 32%, transparent);
  color: var(--green);
}

.policy-detail {
  color: var(--text-dim);
  font-size: 11.5px;
  word-break: break-all;
}

.scope-members {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.scope-member {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.scope-member .sub {
  color: var(--text-faint);
  font-size: 11px;
}

.revision-inline {
  overflow-wrap: anywhere;
  color: var(--text-faint);
  font-size: 10px;
}

.member-note {
  display: inline-block;
  margin-left: 8px;
  color: var(--text-faint);
  font-family: inherit;
  font-size: 11px;
}

.project-cell {
  overflow-wrap: anywhere;
  font-size: 11.5px;
}

.mono {
  font-family: var(--mono);
}

.revision-cell {
  overflow-wrap: anywhere;
  font-size: 10.5px;
}

.revision-missing {
  color: var(--text-faint);
  font-family: inherit;
  font-size: 11.5px;
}
</style>
