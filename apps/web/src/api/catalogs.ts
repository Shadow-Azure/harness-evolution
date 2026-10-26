import type { CatalogModels, CatalogTargets } from "@harness/contracts";

import { request } from "./http";

/**
 * Read enabled evolution targets grouped for the launch wizard.
 * @returns Enabled skill and Agent target catalogs.
 */
export function getTargetCatalog(): Promise<CatalogTargets> {
  return request<CatalogTargets>("/api/catalogs/targets");
}

/**
 * Read normalized Agent model usage for the launch wizard.
 * @returns Model usage catalog.
 */
export function getModelCatalog(): Promise<CatalogModels> {
  return request<CatalogModels>("/api/catalogs/models");
}
