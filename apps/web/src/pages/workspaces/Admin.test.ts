// @vitest-environment jsdom

import type {
  AttributionSkillPackageList,
  PublicUser,
  SessionWorkspace,
  Workspace,
  WorkspaceCredential,
  WorkspaceMember,
  WorkspaceRole,
} from "@harness/contracts";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { createAppRouter } from "../../router";
import { useAuthStore } from "../../stores/auth";
import { server } from "../../test/server";
import { elementPlusComponents } from "../../test/setup";
import AdminPage from "./Admin.vue";

const workspaceId = "ws-test";
const ws = `/workspaces/${workspaceId}`;
const base = `/api/workspaces/${workspaceId}`;
const wrappers: VueWrapper[] = [];

const adminUser: PublicUser = {
  id: "u-admin",
  username: "admin",
  displayName: "管理员",
  role: "admin",
  mustChangePassword: false,
};

const memberUser: PublicUser = {
  id: "u-member",
  username: "member",
  displayName: "成员甲",
  role: "member",
  mustChangePassword: false,
};

const workspace: Workspace = {
  id: workspaceId,
  name: "测试空间",
  mark: "WT",
  quota: 60,
  used: 12,
  memberCount: 2,
  spaceAdmins: [{ id: "u-admin", displayName: "管理员" }],
  knowledgeRoots: [],
  createdAt: "2026-11-01T10:00:00+08:00",
};

const members: WorkspaceMember[] = [
  {
    workspaceId,
    userId: "u-admin",
    username: "admin",
    displayName: "管理员",
    role: "space_admin",
    joinedAt: "2026-11-01T10:01:00+08:00",
    updatedAt: "2026-11-01T10:01:00+08:00",
  },
  {
    workspaceId,
    userId: "u-member",
    username: "member",
    displayName: "成员甲",
    role: "space_admin",
    joinedAt: "2026-11-02T10:01:00+08:00",
    updatedAt: "2026-11-02T10:01:00+08:00",
  },
  {
    workspaceId,
    userId: "u-viewer",
    username: "viewer",
    displayName: "只读乙",
    role: "viewer",
    joinedAt: "2026-11-03T10:01:00+08:00",
    updatedAt: "2026-11-03T10:01:00+08:00",
  },
];

const credentials: WorkspaceCredential[] = [
  {
    id: "cred-1",
    prefix: "whk_9f2e3a",
    createdAt: "2026-11-03T10:00:00+08:00",
    lastUsedAt: null,
    revokedAt: null,
  },
  {
    id: "cred-old",
    prefix: "whk_old123",
    createdAt: "2026-11-01T10:00:00+08:00",
    lastUsedAt: "2026-11-02T10:00:00+08:00",
    revokedAt: "2026-11-03T10:00:00+08:00",
  },
];

const skillPackages: AttributionSkillPackageList = {
  items: [
    {
      id: "default-attribute-badcases",
      skillName: "attribute-badcases",
      uploaderName: "default",
      archiveName: "attribute-badcases.zip",
      fileCount: 1,
      sizeBytes: 4096,
      contentHash: "a".repeat(64),
      isActive: true,
      builtIn: true,
      uploadedAt: null,
    },
    {
      id: "skill-custom",
      skillName: "incident-attribution",
      uploaderName: "成员甲",
      archiveName: "incident-attribution.zip",
      fileCount: 3,
      sizeBytes: 8192,
      contentHash: "b".repeat(64),
      isActive: false,
      builtIn: false,
      uploadedAt: "2026-11-18T12:00:00+08:00",
    },
  ],
  effective: {
    id: "default-attribute-badcases",
    skillName: "attribute-badcases",
    uploaderName: "default",
    archiveName: "attribute-badcases.zip",
    fileCount: 1,
    sizeBytes: 4096,
    contentHash: "a".repeat(64),
    isActive: true,
    builtIn: true,
    uploadedAt: null,
    prompt: "---\nname: attribute-badcases\n---\n# 默认归因提示词",
  },
};

function sessionWorkspace(
  role: WorkspaceRole,
  overrides: Partial<SessionWorkspace> = {},
): SessionWorkspace {
  return {
    id: workspaceId,
    name: workspace.name,
    mark: workspace.mark,
    role,
    quota: workspace.quota,
    used: workspace.used,
    memberCount: workspace.memberCount,
    spaceAdminCount: 1,
    ...overrides,
  };
}

function installWorkspaceAdminHandlers(): void {
  server.use(
    http.get("/api/workspaces", () =>
      HttpResponse.json({ items: [workspace] }),
    ),
    http.get("/api/users", () =>
      HttpResponse.json({ items: [adminUser, memberUser] }),
    ),
    http.get(`${base}/members`, () =>
      HttpResponse.json({ items: members }),
    ),
    http.get(`${base}/member-candidates`, () =>
      HttpResponse.json({ items: [memberUser] }),
    ),
    http.get(`${base}/credentials`, () =>
      HttpResponse.json({ items: credentials }),
    ),
    http.get(`${base}/attribution-skill-packages`, () =>
      HttpResponse.json(skillPackages),
    ),
  );
}

async function mountPage(
  role: WorkspaceRole,
  user: PublicUser = adminUser,
  tab = "spaces",
): Promise<VueWrapper> {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.setSession({
    accessToken: "access",
    expiresIn: 1_800,
    user,
  });
  auth.setWorkspaceSession({
    user,
    workspaces: [sessionWorkspace(role)],
    truncated: false,
  });
  const router = createAppRouter();
  await router.push(`${ws}/admin?tab=${tab}`);
  await router.isReady();
  const wrapper = mount(AdminPage, {
    global: {
      components: elementPlusComponents,
      plugins: [
        [
          VueQueryPlugin,
          {
            queryClient: new QueryClient({
              defaultOptions: { queries: { gcTime: 0, retry: false } },
            }),
          },
        ],
        pinia,
        router,
      ],
    },
  });
  wrappers.push(wrapper);
  await flushPromises();
  return wrapper;
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  server.resetHandlers();
  vi.restoreAllMocks();
});
afterAll(() => server.close());

describe("workspace admin page", () => {
  it("renders all five tabs and the global workspace table for the global administrator", async () => {
    installWorkspaceAdminHandlers();
    const wrapper = await mountPage("global_admin");

    expect(wrapper.get("h1").text()).toBe("工作空间管理");
    expect(wrapper.findAll(".admin-nav button")).toHaveLength(5);
    expect(wrapper.get("[data-testid='admin-tab-spaces']").classes("active")).toBe(
      true,
    );
    expect(wrapper.get(`[data-testid='workspace-row-${workspaceId}']`).text()).toContain(
      "测试空间",
    );
    expect(wrapper.get(`[data-testid='workspace-row-${workspaceId}']`).text()).toContain(
      "12 / 60",
    );
    expect(wrapper.get("[data-testid='create-workspace']").text()).toContain(
      "创建工作空间",
    );
    expect(wrapper.find("[data-testid='admin-readonly-badge']").exists()).toBe(
      false,
    );
  });

  it("shows the current-space quota editor to a space administrator without create entry", async () => {
    installWorkspaceAdminHandlers();
    const wrapper = await mountPage("space_admin", memberUser);

    expect(wrapper.get("h1").text()).toBe("空间管理");
    expect(wrapper.find("[data-testid='create-workspace']").exists()).toBe(
      false,
    );
    expect(wrapper.get("[data-testid='edit-current-quota']").text()).toContain(
      "调整额度",
    );
    expect(
      wrapper.get("[data-testid='manage-current-members']").text(),
    ).toContain("管理成员");
    expect(wrapper.get("[data-testid='admin-role-badge']").text()).toBe(
      "空间管理员",
    );
  });

  it("hides every write entry for members and viewers while keeping read-only tabs", async () => {
    installWorkspaceAdminHandlers();
    const wrapper = await mountPage("viewer", memberUser);

    expect(wrapper.get("[data-testid='admin-readonly-badge']").text()).toBe(
      "只读",
    );
    expect(wrapper.find("[data-testid='create-workspace']").exists()).toBe(
      false,
    );
    expect(wrapper.find("[data-testid='edit-current-quota']").exists()).toBe(
      false,
    );
    expect(wrapper.find("[data-testid='spaces-readonly-note']").exists()).toBe(
      true,
    );
  });

  it("locks space-admin rows for a space administrator and exposes member writes", async () => {
    installWorkspaceAdminHandlers();
    const wrapper = await mountPage("space_admin", memberUser, "members");

    const adminRow = wrapper.get("[data-testid='member-row-u-admin']");
    expect(adminRow.get("[data-testid='member-locked-role']").text()).toBe(
      "空间管理员",
    );
    expect(wrapper.find("[data-testid='member-role-u-admin']").exists()).toBe(
      false,
    );
    expect(
      wrapper.find("[data-testid='member-row-u-viewer'] [data-testid='member-role-u-viewer']")
        .exists(),
    ).toBe(true);
    expect(
      wrapper.get("[data-testid='add-workspace-member']").text(),
    ).toContain("添加成员");
    expect(wrapper.find("[data-testid='appoint-self-admin']").exists()).toBe(
      false,
    );
  });

  it("keeps read-only members from the credential and member write surfaces", async () => {
    installWorkspaceAdminHandlers();
    const wrapper = await mountPage("member", memberUser, "members");

    expect(wrapper.find("[data-testid='add-workspace-member']").exists()).toBe(
      false,
    );
    expect(wrapper.find("[data-testid='appoint-self-admin']").exists()).toBe(
      false,
    );
    expect(wrapper.find("[data-testid='member-role-u-member']").exists()).toBe(
      false,
    );
    expect(wrapper.find(".link.danger").exists()).toBe(false);
  });

  it("renders a read-only member notice for viewers instead of requesting the member list", async () => {
    installWorkspaceAdminHandlers();
    const wrapper = await mountPage("viewer", memberUser, "members");

    expect(wrapper.get("[data-testid='members-readonly']").text()).toContain(
      "只读成员不能查看成员列表",
    );
    expect(wrapper.find("[data-testid='add-workspace-member']").exists()).toBe(
      false,
    );
    expect(wrapper.find("[data-testid='member-role-u-viewer']").exists()).toBe(
      false,
    );
  });

  it("reveals a new credential exactly once and never re-renders its plaintext", async () => {
    const secret = "whk_test_plaintext_secret_value";
    installWorkspaceAdminHandlers();
    server.use(
      http.post(`${base}/credentials`, () =>
        HttpResponse.json(
          { credentialId: "cred-new", prefix: "whk_new", credential: secret },
          { status: 201 },
        ),
      ),
    );
    const wrapper = await mountPage("space_admin", memberUser, "ingest");

    expect(wrapper.get("[data-testid='ingest-endpoint']").text()).toContain(
      `/api/workspaces/${workspaceId}/bad-cases`,
    );
    expect(wrapper.get("[data-testid='ingest-tab']").text()).toContain(
      "body 不接受 workspace 字段，多带会返回",
    );
    expect(wrapper.get("[data-testid='credential-row-cred-1']").text()).toContain(
      "whk_9f2e3a",
    );
    expect(wrapper.text()).not.toContain(secret);

    await wrapper.get("[data-testid='rotate-credential']").trigger("click");
    await flushPromises();

    expect(wrapper.get("[data-testid='new-credential-plaintext']").text()).toBe(
      secret,
    );
    await wrapper.get("[data-testid='acknowledge-credential']").trigger("click");
    await flushPromises();

    await vi.waitFor(() => {
      expect(
        wrapper.find("[data-testid='new-credential-plaintext']").exists(),
      ).toBe(false);
    });
    expect(wrapper.text()).not.toContain(secret);
    expect(wrapper.get("[data-testid='ingest-curl-example']").text()).toContain(
      "<workspace credential>",
    );
  });

  it("renders the ingest read-only notice for viewers instead of credentials", async () => {
    installWorkspaceAdminHandlers();
    const wrapper = await mountPage("viewer", memberUser, "ingest");

    expect(wrapper.get("[data-testid='ingest-readonly']").text()).toContain(
      "只有空间管理员及以上可以查看与轮换上报凭据",
    );
    expect(wrapper.find("[data-testid='rotate-credential']").exists()).toBe(
      false,
    );
    expect(wrapper.find("[data-testid='credential-row-cred-1']").exists()).toBe(
      false,
    );
  });

  it("renders attribution Skill packages and the effective SKILL.md prompt", async () => {
    let activatedPackage = "";
    installWorkspaceAdminHandlers();
    server.use(
      http.post(`${base}/attribution-skill-packages/:packageId/activate`, ({ params }) => {
        activatedPackage = String(params.packageId);
        return HttpResponse.json({
          ...skillPackages.items[1],
          isActive: true,
          prompt: "---\nname: incident-attribution\n---\n# 自定义提示词",
        });
      }),
    );
    const wrapper = await mountPage(
      "space_admin",
      memberUser,
      "attribution-skills",
    );

    expect(wrapper.get("[data-testid='attribution-skills-tab']").text()).toContain(
      "上传自定义归因 Skill",
    );
    expect(
      wrapper.get("[data-testid='skill-package-default-attribute-badcases']").text(),
    ).toContain("当前生效");
    expect(wrapper.get("[data-testid='skill-package-skill-custom']").text()).toContain(
      "成员甲",
    );
    expect(wrapper.get("[data-testid='activate-skill-skill-custom']").text()).toBe(
      "设为生效",
    );
    expect(wrapper.get("[data-testid='effective-skill-prompt']").text()).toContain(
      "# 默认归因提示词",
    );

    await wrapper.get("[data-testid='activate-skill-skill-custom']").trigger("click");
    await flushPromises();
    expect(activatedPackage).toBe("skill-custom");
  });

  it("keeps attribution Skill write actions hidden for a viewer", async () => {
    installWorkspaceAdminHandlers();
    const wrapper = await mountPage("viewer", memberUser, "attribution-skills");

    expect(wrapper.find("[data-testid='upload-attribution-skill']").exists()).toBe(
      false,
    );
    expect(wrapper.find("[data-testid='activate-skill-skill-custom']").exists()).toBe(
      false,
    );
    expect(wrapper.find("[data-testid='delete-skill-skill-custom']").exists()).toBe(
      false,
    );
    expect(wrapper.find("[data-testid='download-skill-skill-custom']").exists()).toBe(
      true,
    );
  });

  it("renders the read-only auth contract and switches tabs through the URL", async () => {
    installWorkspaceAdminHandlers();
    const wrapper = await mountPage("space_admin", memberUser, "auth");

    expect(wrapper.get("[data-testid='auth-tab']").text()).toContain(
      "鉴权接入（预留）",
    );
    expect(wrapper.get("[data-testid='auth-contract']").text()).toContain(
      "GET /api/auth/session",
    );

    await wrapper.get("[data-testid='admin-tab-members']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-testid='members-tab']").exists()).toBe(true);
  });

  it("states that a global administrator can grant themself a space-admin role", async () => {
    installWorkspaceAdminHandlers();
    const wrapper = await mountPage("global_admin");

    expect(wrapper.get("[data-testid='spaces-tab']").text()).toContain(
      "管理员可以把任意用户（包括自己）加入空间并任命为空间管理员",
    );
  });

  it("renders the username and session contract without demo accounts", async () => {
    installWorkspaceAdminHandlers();
    const wrapper = await mountPage("space_admin", memberUser, "auth");

    const text = wrapper.get("[data-testid='auth-tab']").text();
    const contract = wrapper.get("[data-testid='auth-contract']").text();
    for (const field of [
      "username",
      "displayName",
      "mustChangePassword",
      "accessToken",
      "expiresIn",
      "refresh_token",
      "SameSite=Strict",
      "truncated",
    ]) {
      expect(contract).toContain(field);
    }
    expect(contract).not.toContain("globalRole");
    expect(text).not.toContain("演示账号");
  });

  it("renders the camelCase ingest body example with the workspace 422 boundary", async () => {
    installWorkspaceAdminHandlers();
    const wrapper = await mountPage("space_admin", memberUser, "ingest");

    const example = wrapper.get("[data-testid='ingest-body-example']").text();
    for (const field of [
      "badCaseId",
      "sessionId",
      "badCaseType",
      "objectName",
      "objectType",
      "title",
      "reason",
      "metaData",
      "createdAt",
    ]) {
      expect(example).toContain(`"${field}"`);
    }
    expect(example).not.toContain("session_id");
    expect(wrapper.get("[data-testid='ingest-tab']").text()).toContain(
      "body 不接受 workspace 字段，多带会返回",
    );
  });
});
