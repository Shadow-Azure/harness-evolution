import { h } from "vue";

import LoadingSkeleton from "../../../components/ui/LoadingSkeleton.vue";

/**
 * Full-height placeholder rendered by the async AgentFlow chunk while it loads.
 * The 720px/420px height is applied by the tree panel in SessionOverview so the
 * right column keeps the prototype-scale flow footprint.
 */
export const AgentFlowLoading = {
  name: "AgentFlowLoading",
  inheritAttrs: false,
  render: () => h("div", {
    class: "tree-loading",
    "data-testid": "tree-loading",
  }, [
    h(LoadingSkeleton, {
      label: "正在加载 Agent 执行流视图",
      rows: 8,
    }),
  ]),
};

/**
 * Placeholder rendered when the async AgentFlow chunk fails to load.
 * The alert role announces the failure instead of silently collapsing.
 */
export const AgentFlowError = {
  name: "AgentFlowError",
  inheritAttrs: false,
  render: () => h("div", {
    class: "tree-loading tree-loading-error",
    role: "alert",
    "data-testid": "tree-load-error",
  }, [
    h("strong", "Agent 执行流视图加载失败"),
    h("span", "请刷新页面后重试。"),
  ]),
};
