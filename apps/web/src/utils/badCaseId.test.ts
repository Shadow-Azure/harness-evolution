import { describe, expect, it } from "vitest";

import { badCaseDeepLink, shortBadCaseId } from "./badCaseId";

describe("bad-case IDs", () => {
  it("uses one stable eight-character display form", () => {
    expect(shortBadCaseId("case-00000001")).toBe("case-000");
    expect(shortBadCaseId("short")).toBe("short");
  });

  it("builds canonical description and attribution deep links", () => {
    expect(
      badCaseDeepLink(
        "ws-test",
        "session/root",
        "case id",
        "desc",
      ),
    ).toBe(
      "/workspaces/ws-test/sessions/session%2Froot/errors?case=case+id&tab=desc",
    );
    expect(
      badCaseDeepLink("ws-test", "root-1", "case-error", "attr"),
    ).toBe(
      "/workspaces/ws-test/sessions/root-1/errors?case=case-error&tab=attr",
    );
  });
});
