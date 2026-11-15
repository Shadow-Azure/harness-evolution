// @vitest-environment jsdom

import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

import { queryKeys } from "../../api/queryKeys";
import { useAuthStore } from "../../stores/auth";
import { testWorkspace } from "../../test/auth";
import WorkspacePicker from "./WorkspacePicker.vue";

const workspaces = [
  testWorkspace({ id: "ws-a", name: "空间 A", mark: "A", role: "space_admin" }),
  testWorkspace({ id: "ws-b", name: "空间 B", mark: "B", role: "viewer" }),
];

async function mountPicker(path = "/workspaces/ws-a/sessions") {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.setSession({
    accessToken: "access",
    expiresIn: 1_800,
    user: {
      id: "u-1",
      username: "operator",
      displayName: "操作员",
      role: "member",
      mustChangePassword: false,
    },
  });
  auth.setWorkspaceSession({
    user: auth.user!,
    workspaces,
    truncated: false,
  });
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/workspaces/:wid/sessions", component: { template: "<div />" } },
      { path: "/workspaces/:wid/evolution", component: { template: "<div />" } },
      {
        path: "/workspaces/:wid/evolution/runs/:runId",
        component: { template: "<div />" },
      },
    ],
  });
  await router.push(path);
  await router.isReady();
  const queryClient = new QueryClient({
    defaultOptions: { queries: { gcTime: 0, retry: false } },
  });
  const invalidate = vi.spyOn(queryClient, "invalidateQueries");
  const wrapper = mount(WorkspacePicker, {
    global: {
      plugins: [[VueQueryPlugin, { queryClient }], pinia, router],
    },
  });
  await flushPromises();
  return { auth, invalidate, queryClient, router, wrapper };
}

describe("WorkspacePicker", () => {
  it("shows the current workspace and its effective role", async () => {
    const { wrapper } = await mountPicker();

    expect(wrapper.get("[data-testid='workspace-picker']").text()).toContain(
      "空间 A",
    );
    expect(wrapper.text()).toContain("空间管理员");
    expect(wrapper.text()).toContain("空间数据与权限相互隔离");
  });

  it("switches to the same section in another workspace and invalidates the old tree", async () => {
    const { invalidate, queryClient, router, wrapper } = await mountPicker();
    queryClient.setQueryData(queryKeys.sessions("ws-a"), [{ id: "s-1" }]);
    queryClient.setQueryData(queryKeys.sessions("ws-b"), [{ id: "s-2" }]);

    await wrapper.get("[data-testid='workspace-option-ws-b']").trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.fullPath).toBe("/workspaces/ws-b/sessions");
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.workspace("ws-a"),
    });
    expect(
      queryClient.getQueryState(queryKeys.sessions("ws-b"))?.isInvalidated,
    ).not.toBe(true);
  });

  it("drops a run id owned by the previous workspace", async () => {
    const { router, wrapper } = await mountPicker(
      "/workspaces/ws-a/evolution/runs/run-1",
    );

    await wrapper.get("[data-testid='workspace-option-ws-b']").trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.fullPath).toBe("/workspaces/ws-b/evolution");
  });

  it("does not navigate when the active workspace is selected again", async () => {
    const { invalidate, router, wrapper } = await mountPicker();

    await wrapper.get("[data-testid='workspace-option-ws-a']").trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.fullPath).toBe("/workspaces/ws-a/sessions");
    expect(invalidate).not.toHaveBeenCalled();
  });
});
