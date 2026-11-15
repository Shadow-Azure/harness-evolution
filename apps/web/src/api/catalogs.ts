import type { CatalogModels, CatalogTargets } from "@harness/contracts";

import { request } from "./http";

/**
 * Read enabled evolution targets of one workspace grouped for the launch wizard.
 * @param workspaceId Route workspace identifier.
 * @returns Enabled skill and Agent target catalogs.
 */
export function getTargetCatalog(workspaceId: string): Promise<CatalogTargets> {
  return request<CatalogTargets>(
    `/api/workspaces/${encodeURIComponent(workspaceId)}/catalogs/targets`,
  );
}

/**
 * Read normalized Agent model usage of one workspace for the launch wizard.
 * @param workspaceId Route workspace identifier.
 * @returns Model usage catalog.
 */
export function getModelCatalog(workspaceId: string): Promise<CatalogModels> {
  return request<CatalogModels>(
    `/api/workspaces/${encodeURIComponent(workspaceId)}/catalogs/models`,
  );
}
