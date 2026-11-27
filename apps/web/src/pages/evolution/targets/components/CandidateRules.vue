<script setup lang="ts">
import ElPagination from "element-plus/es/components/pagination/index";
import ElDialog from "element-plus/es/components/dialog/index";
import { computed, ref, watch } from "vue";
import type {
  CandidatePolicy,
  SourceCount,
  SourceReportPage,
  SourceRule,
} from "@harness/contracts";
import { request } from "../../../../api/http";

const props = defineProps<{
  workspaceId: string;
  window?: { from: string; to: string } | null;
  create?: boolean;
  readonly?: boolean;
  own?: { objectType: string; objectName: string };
}>();
const policy = defineModel<CandidatePolicy>({ required: true });
const rules = computed(() => policy.value.rules ?? []);
const modes = [
  ["default", "默认规则", "纳入对象自身的 self，以及触发点在目标之后的 case。"],
  [
    "combined",
    "默认规则 + 自定义来源",
    "在默认候选基础上，加入命中来源规则的 case。",
  ],
  ["custom", "仅自定义来源", "候选须命中至少一条来源规则。"],
] as const;
const sources = ref<SourceCount[]>([]);
const sourceError = ref("");
const sourceLoading = ref(false);
const refresh = ref(0);
const root = computed(
  () =>
    "/api/workspaces/" + encodeURIComponent(props.workspaceId) + "/evolution/",
);
const period = computed(() =>
  new URLSearchParams(props.window ?? {}).toString(),
);
watch(
  [root, period, refresh, () => policy.value.mode === "default"],
  async (_, __, onCleanup) => {
    let stale = false;
    onCleanup(() => {
      stale = true;
    });
    sources.value = [];
    sourceError.value = "";
    if (!props.workspaceId || policy.value.mode === "default") return;
    sourceLoading.value = true;
    try {
      const result = await request<SourceCount[]>(
        root.value + "candidate-sources?" + period.value,
      );
      if (!stale) sources.value = result;
    } catch {
      if (!stale) sourceError.value = "来源加载失败";
    } finally {
      if (!stale) sourceLoading.value = false;
    }
  },
  { immediate: true },
);
const viewing = ref<SourceRule | null>(null);
const popup = ref(false);
const labels = ref<(string | null)[]>([]);
const filterType = ref("");
const page = ref(1);
const result = ref<SourceReportPage | null>(null);
const reportError = ref(false);
function view(rule: SourceRule) {
  viewing.value = rule;
  labels.value = [];
  filterType.value = "";
  page.value = 1;
  popup.value = !!props.create;
}
function initialView() {
  viewing.value = null;
  if (props.create) return;
  if (policy.value.mode !== "default") {
    if (rules.value[0]) view(rules.value[0]);
    return;
  }
  if (
    props.own &&
    (props.own.objectType === "agent" || props.own.objectType === "skill")
  )
    view({
      kind: props.own.objectType,
      name: props.own.objectName,
      types: ["self"],
      relation: "any",
    });
}
watch(() => policy.value.mode, initialView, { immediate: true });
function add() {
  if (policy.value.mode === "default") policy.value.mode = "combined";
  (policy.value.rules ??= []).push({
    kind: "skill",
    name: "",
    types: ["self", "discovery"],
    relation: "any",
  });
}
function clearView(rule: SourceRule) {
  if (viewing.value === rule) viewing.value = null;
}
function toggleTag(tag: string | null) {
  labels.value = labels.value.includes(tag)
    ? labels.value.filter((x) => x !== tag)
    : [...labels.value, tag];
  page.value = 1;
}
const query = computed(() => {
  const rule = viewing.value;
  if (
    !rule ||
    !rule.name ||
    !rule.types.length ||
    (props.create && !popup.value)
  )
    return "";
  const q = new URLSearchParams(period.value);
  q.set("kind", rule.kind);
  q.set("name", rule.name);
  q.set("page", String(page.value));
  rule.types.forEach((t) => q.append("types", t));
  if (filterType.value) q.set("filterType", filterType.value);
  labels.value.forEach((l) =>
    l === null ? q.set("unlabelled", "true") : q.append("labels", l),
  );
  return root.value + "candidate-source-reports?" + q;
});
watch(
  [query, refresh],
  async (_, __, onCleanup) => {
    let stale = false;
    onCleanup(() => {
      stale = true;
    });
    result.value = null;
    reportError.value = false;
    if (!query.value) return;
    try {
      const data = await request<SourceReportPage>(query.value);
      if (!stale) result.value = data;
    } catch {
      if (!stale) reportError.value = true;
    }
  },
  { immediate: true },
);
</script>
<template>
  <div
    class="candidate-layout"
    :class="{ single: create }"
  >
    <section class="editor">
      <h3>策略模式</h3>
      <label
        v-for="[value, title, description] in modes"
        :key="value"
        class="mode"
        :class="{ selected: policy.mode === value }"
      >
        <input
          v-model="policy.mode"
          type="radio"
          :value="value"
          :disabled="readonly"
        >
        <span><b>{{ title }}</b><small>{{ description }}</small></span>
      </label>
      <header>
        <h3>来源规则</h3>
        <button
          v-if="!readonly"
          type="button"
          class="btn"
          @click="add"
        >
          ＋ 添加来源
        </button>
      </header>
      <small>来源名称取自当前工作区已有上报的 Skill 或 Agent。</small>
      <p
        v-if="sourceError"
        role="alert"
      >
        {{ sourceError }} <button
          type="button"
          @click="refresh++"
        >
          重试
        </button>
      </p>
      <p v-if="policy.mode === 'default'">
        选择包含自定义来源的模式即可配置。
      </p>
      <template v-else>
        <fieldset
          v-for="(rule, i) in rules"
          :key="i"
          :class="{ current: viewing === rule }"
        >
          <legend>来源 {{ i + 1 }}</legend>
          <button
            v-if="!readonly"
            class="remove"
            type="button"
            @click="
              clearView(rule);
              rules.splice(i, 1);
            "
          >
            移除
          </button>
          <div class="fields">
            <label>来源类型<select
              v-model="rule.kind"
              :disabled="readonly"
              @change="
                clearView(rule);
                rule.name = '';
              "
            >
              <option value="skill">Skill</option>
              <option value="agent">Agent</option>
            </select></label>
            <div class="name-field">
              <span>来源名称</span>
              <ElSelect
                v-model="rule.name"
                aria-label="来源名称"
                placeholder="请选择已上报的对象"
                :disabled="readonly"
                :loading="sourceLoading"
                fit-input-width
                no-data-text="暂无已上报的对象"
                popper-class="candidate-source-menu"
                @change="clearView(rule)"
              >
                <template #header>
                  <div class="source-option">
                    <span>所选时段</span><span>self</span><span>discovery</span>
                  </div>
                </template>
                <ElOption
                  v-for="s in sources.filter((item) => item.kind === rule.kind)"
                  :key="s.name"
                  :value="s.name"
                  :label="s.name"
                >
                  <div class="source-option">
                    <span>{{ s.name }}</span><span>{{ s.selfCount }}</span><span>{{ s.discoveryCount }}</span>
                  </div>
                </ElOption>
              </ElSelect>
            </div>
          </div>
          <div class="types">
            上报类型
            <label
              v-for="t in ['self', 'discovery']"
              :key="t"
            ><input
              v-model="rule.types"
              :disabled="readonly"
              type="checkbox"
              :value="t"
              @change="clearView(rule)"
            >{{ t }}</label>
            <button
              type="button"
              class="btn"
              :disabled="!rule.name || !rule.types.length"
              @click="view(rule)"
            >
              查看 badcase
            </button>
          </div>
          <label>轨迹顺序<select
            v-model="rule.relation"
            :disabled="readonly"
          >
            <option value="any">同一 Session 内执行过目标</option>
            <option value="before">目标在 case 锚点之前执行</option>
            <option value="after">目标在 case 锚点之后执行</option>
          </select></label>
        </fieldset>
      </template>
    </section>
    <component
      :is="create ? ElDialog : 'section'"
      v-if="!create || popup"
      v-bind="
        create
          ? {
            modelValue: popup,
            title: '查看 badcase',
            appendToBody: true,
            width: 'min(560px, 94vw)',
          }
          : {}
      "
      @close="popup = false"
    >
      <section class="reports">
        <header>
          <h3>来源已上报的 bad case</h3>
          <span v-if="viewing">{{ viewing.kind }} · {{ viewing.name }}</span>
        </header>
        <p v-if="!viewing">
          选择来源后点击「查看 badcase」。
        </p>
        <template v-else>
          <small v-if="window">{{ window.from }} 至 {{ window.to }}</small>
          <div class="filters">
            类型
            <button
              type="button"
              :aria-pressed="!filterType"
              @click="
                filterType = '';
                page = 1;
              "
            >
              全部
            </button>
            <button
              v-for="t in viewing.types"
              :key="t"
              type="button"
              :aria-pressed="filterType === t"
              @click="
                filterType = t;
                page = 1;
              "
            >
              {{ t }}
            </button>
          </div>
          <template v-if="result">
            <div class="filters">
              标签
              <button
                type="button"
                :aria-pressed="!labels.length"
                @click="
                  labels = [];
                  page = 1;
                "
              >
                全部
              </button>
              <button
                v-for="tag in result.labels"
                :key="JSON.stringify(tag)"
                type="button"
                :aria-pressed="labels.includes(tag)"
                @click="toggleTag(tag)"
              >
                {{ tag ?? "无标签" }}
              </button>
            </div>
            <p>显示 {{ result.total }} / {{ result.sourceTotal }} 条上报</p>
            <article
              v-for="row in result.items"
              :key="row.id"
            >
              <header>
                <span>{{ row.id }}</span><time>{{ row.createdAt.slice(0, 10) }}</time>
              </header>
              <b>{{ row.title }}</b><small>{{ viewing.name }} · {{ row.reportType }}
                {{ row.label }}</small>
            </article>
            <p v-if="!result.total">
              当前来源和筛选条件下没有上报记录。
            </p>
            <ElPagination
              v-if="result.total > 20"
              v-model:current-page="page"
              layout="prev, pager, next"
              :total="result.total"
              :page-size="20"
            />
          </template>
          <p
            v-else-if="reportError"
            role="alert"
          >
            上报记录加载失败
            <button
              type="button"
              @click="refresh++"
            >
              重试
            </button>
          </p>
          <p v-else>
            正在读取上报记录…
          </p>
        </template>
      </section>
    </component>
  </div>
</template>
<style scoped>
.candidate-layout {
  display: grid;
  grid-template-columns: minmax(325px, 2fr) minmax(0, 3fr);
  height: 100%;
}
.candidate-layout.single {
  display: block;
  height: auto;
}
.candidate-layout:not(.single) > * {
  overflow-y: auto;
  min-height: 0;
}
.candidate-layout:not(.single) > .editor,
.candidate-layout:not(.single) > section > .reports {
  padding: 18px 24px;
}
.candidate-layout:not(.single) > section:has(> .reports) {
  border-left: 1px solid var(--border);
  background: var(--bg-panel);
}
.editor,
.reports,
.fields > * {
  min-width: 0;
}
.editor h3,
.reports h3 {
  margin: 0;
  font-size: 14px;
}
.editor header,
.reports header,
.types,
.filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.editor header,
.reports header {
  justify-content: space-between;
  margin: 14px 0 8px;
}
.mode,
fieldset,
article {
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  margin: 6px 0;
  background: var(--bg-card);
}
.mode {
  display: flex;
  align-items: start;
  gap: 8px;
}
.selected {
  border-color: var(--blue);
  background: var(--surface-selected);
}
fieldset.current { border-color: var(--blue); }
small {
  display: block;
  color: var(--text-dim);
  font-size: 12px;
}
fieldset {
  min-width: 0;
  position: relative;
}
legend,
.remove,
.reports header span {
  color: var(--blue);
}
.remove {
  position: absolute;
  right: 12px;
  top: -16px;
  border: 0;
  background: var(--bg-card);
  cursor: pointer;
}
.fields {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  gap: 8px;
}
.editor select {
  width: 100%;
  height: 32px;
  color: var(--text);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 5px;
}
.name-field span,
fieldset select {
  display: block;
}
.types,
.filters {
  margin: 12px 0;
  font-size: 12px;
}
.types button {
  margin-left: auto;
}
.reports {
  background: var(--bg-panel);
  padding: 12px;
  border-radius: 8px;
}
.filters button {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-card);
  padding: 3px 8px;
  color: var(--text-dim);
  cursor: pointer;
}
.filters [aria-pressed="true"] {
  color: var(--blue);
  border-color: var(--blue);
}
.source-option {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 48px 72px;
  gap: 5px;
  align-items: center;
  font-size: 12px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.source-option span:first-child {
  text-align: left;
  white-space: normal;
  overflow-wrap: anywhere;
  line-height: 1.3;
}
:global(.candidate-source-menu .el-select-dropdown__item) {
  height: auto;
  min-height: 44px;
  padding: 8px;
  align-content: center;
}
:global(.candidate-source-menu .el-select-dropdown__header) {
  padding-inline: 8px;
}
@media (max-width: 720px) {
  .candidate-layout {
    display: block;
  }
  .reports {
    margin-top: 12px;
  }
}
</style>
