// @vitest-environment jsdom

import { describe, expect, it } from "vitest";

import { ApiError } from "../../../api/http";
import { targetServerError } from "./targetErrors";

describe("targetServerError", () => {
  it("maps member-scoped REPO_INVALID details to the member row", () => {
    const error = new ApiError(422, "REPO_INVALID", "invalid member", {
      field: "members[1].subDir",
      reason: "sub_dir_format",
    });

    expect(targetServerError(error)).toMatchObject({
      field: "members[1].subDir",
      reason: "sub_dir_format",
      message: "子目录必须是仓库内的相对路径",
    });
  });

  it("maps duplicate members inside one configuration to the duplicate row", () => {
    const error = new ApiError(422, "REPO_INVALID", "duplicated member", {
      field: "members[2].objectName",
      reason: "member_duplicated",
    });

    expect(targetServerError(error)).toMatchObject({
      field: "members[2].objectName",
      message: "同一配置里成员重复",
    });
  });

  it("maps MEMBER_ALREADY_CONFIGURED details to the member row", () => {
    const error = new ApiError(409, "MEMBER_ALREADY_CONFIGURED", "conflict", {
      field: "members[0].objectName",
      member: { objectType: "skill", objectName: "deep-research" },
      targetId: "other-target",
    });

    expect(targetServerError(error)).toMatchObject({
      field: "members[0].objectName",
      summary: "该成员已属于另一条配置",
      suggestion: expect.any(String),
    });
  });

  it("keeps shared target fields unchanged", () => {
    const error = new ApiError(422, "REPO_INVALID", "invalid ref", {
      field: "defaultRef",
      reason: "ref_not_found",
    });

    expect(targetServerError(error)).toMatchObject({
      field: "defaultRef",
      reason: "ref_not_found",
    });
  });
});
