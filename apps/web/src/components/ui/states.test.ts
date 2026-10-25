// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import EmptyState from "./EmptyState.vue";
import ErrorState from "./ErrorState.vue";
import LoadingSkeleton from "./LoadingSkeleton.vue";

describe("shared page states", () => {
  it("announces loading through a stable accessible status", () => {
    const wrapper = mount(LoadingSkeleton, {
      props: { label: "正在加载会话" },
    });

    expect(wrapper.get("[role='status']").attributes("aria-label")).toBe(
      "正在加载会话",
    );
    expect(wrapper.text()).toContain("正在加载会话");
  });

  it("keeps empty-state actions in the supplied slot", () => {
    const wrapper = mount(EmptyState, {
      props: {
        description: "后续 milestone 接入",
        title: "暂无会话",
      },
      slots: {
        action: '<button data-testid="empty-action">刷新</button>',
      },
    });

    expect(wrapper.text()).toContain("暂无会话");
    expect(wrapper.get("[data-testid='empty-action']").text()).toBe("刷新");
  });

  it("shows an error code and emits one retry per user action", async () => {
    const wrapper = mount(ErrorState, {
      props: {
        code: "JOB_NOT_FOUND",
        message: "任务不存在或已删除",
      },
    });

    expect(wrapper.text()).toContain("JOB_NOT_FOUND");
    expect(wrapper.text()).toContain("任务不存在或已删除");
    expect(wrapper.emitted("retry")).toBeUndefined();

    await wrapper.get("button").trigger("click");
    expect(wrapper.emitted("retry")).toEqual([[]]);
  });

  it("does not offer retry when the caller marks the error terminal", () => {
    const wrapper = mount(ErrorState, {
      props: {
        code: "NOT_FOUND",
        message: "页面不存在或已删除",
        retryable: false,
      },
    });

    expect(wrapper.find("button").exists()).toBe(false);
  });
});
