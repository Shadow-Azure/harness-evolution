import type {
  AttributionSkillPackage,
  AttributionSkillPackageList,
  SkillResourceDetail,
} from "@harness/contracts";

import { request } from "./http";

function basePath(workspaceId: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/attribution-skill-packages`;
}

/**
 * List built-in and uploaded Skill package metadata.
 * @param workspaceId Owning workspace identifier.
 * @returns Workspace package list.
 */
export function listAttributionSkillPackages(
  workspaceId: string,
): Promise<AttributionSkillPackageList> {
  return request(basePath(workspaceId));
}

/**
 * Upload one Skill folder ZIP without activating it.
 * @param workspaceId Owning workspace identifier.
 * @param file ZIP selected by the administrator.
 * @returns Persisted package metadata.
 */
export function uploadAttributionSkillPackage(
  workspaceId: string,
  file: File,
): Promise<AttributionSkillPackage> {
  const body = new FormData();
  body.append("file", file);
  return request(basePath(workspaceId), { method: "POST", body });
}

/**
 * Read the selected resource.
 * @param workspaceId Owning workspace.
 * @param packageId Selected Skill.
 * @returns Prompt, archived file paths and bound targets.
 */
export function getSkillResource(workspaceId: string, packageId: string): Promise<SkillResourceDetail> {
  return request(`${basePath(workspaceId)}/${encodeURIComponent(packageId)}`);
}

/**
 * Download one package through authenticated transport.
 * @param workspaceId Owning workspace identifier.
 * @param packageId Downloaded package identifier.
 * @returns Regenerated ZIP blob.
 */
export function downloadAttributionSkillPackage(
  workspaceId: string,
  packageId: string,
): Promise<Blob> {
  return request(
    `${basePath(workspaceId)}/${encodeURIComponent(packageId)}/download`,
    undefined,
    { responseType: "blob" },
  );
}

/**
 * Delete one custom package and its optional active binding.
 * @param workspaceId Owning workspace identifier.
 * @param packageId Deleted package identifier.
 * @returns No value.
 */
export function deleteAttributionSkillPackage(
  workspaceId: string,
  packageId: string,
): Promise<void> {
  return request(`${basePath(workspaceId)}/${encodeURIComponent(packageId)}`, {
    method: "DELETE",
  });
}
