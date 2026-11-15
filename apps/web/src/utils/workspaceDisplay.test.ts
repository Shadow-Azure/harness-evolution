import { describe, expect, it } from "vitest";

import {
  canManageWorkspace,
  workspaceMark,
  workspaceQuotaPercent,
  workspaceRoleLabel,
} from "./workspaceDisplay";

describe("workspace display helpers", () => {
  it("labels every effective role", () => {
    expect(workspaceRoleLabel("global_admin")).toBe("全局管理员");
    expect(workspaceRoleLabel("space_admin")).toBe("空间管理员");
    expect(workspaceRoleLabel("member")).toBe("成员");
    expect(workspaceRoleLabel("viewer")).toBe("只读成员");
  });

  it("prefers a short explicit mark and falls back to the name", () => {
    expect(workspaceMark({ mark: "HC", name: "Harness 核心研发" })).toBe("HC");
    expect(
      workspaceMark({
        mark: "迁移回填：无空间上下文的存量数据",
        name: "默认空间",
      }),
    ).toBe("默认");
  });

  it("clamps quota percentages", () => {
    expect(workspaceQuotaPercent(15, 60)).toBe(25);
    expect(workspaceQuotaPercent(80, 60)).toBe(100);
    expect(workspaceQuotaPercent(1, 0)).toBe(0);
  });

  it("lets only administrators manage a workspace", () => {
    expect(canManageWorkspace("global_admin")).toBe(true);
    expect(canManageWorkspace("space_admin")).toBe(true);
    expect(canManageWorkspace("member")).toBe(false);
    expect(canManageWorkspace(undefined)).toBe(false);
  });
});
