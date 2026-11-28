import type { EvolutionTarget } from "@harness/contracts";

/** One writable member row of an evolution target configuration. */
export interface TargetMember {
  objectType: "skill" | "agent" | "knowledge";
  objectName: string;
  subDir: string;
  matchByName: boolean;
}

/**
 * Read the member rows of one configuration.
 *
 * Responses always carry `members`; the top-level object fields remain as a
 * first-member compatibility projection and are used only for legacy fixtures.
 * @param target Persisted target configuration, or null when creating.
 * @returns Member rows in display order.
 */
export function targetMembers(target: EvolutionTarget | null): TargetMember[] {
  if (!target) return [];
  if (target.members?.length) {
    return target.members.map(({ objectType, objectName, subDir, matchByName }) => ({
      objectType,
      objectName,
      subDir,
      matchByName: matchByName ?? false,
    }));
  }
  if (target.objectName) {
    return [
      {
        objectType: target.objectType ?? "skill",
        objectName: target.objectName,
        subDir: target.subDir ?? "",
        matchByName: false,
      },
    ];
  }
  return [];
}

/**
 * Human-readable configuration name used by rows and delete confirmation.
 * @param target Persisted target configuration.
 * @returns First member name with a `+N` suffix when more members exist.
 */
export function targetDisplayName(target: EvolutionTarget): string {
  const members = targetMembers(target);
  const first = members[0];
  if (!first) return "未命名配置";
  return members.length > 1
    ? `${first.objectName} +${members.length - 1}`
    : first.objectName;
}
