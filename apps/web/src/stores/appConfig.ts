import { defineStore } from "pinia";
import { ref } from "vue";

import { DEFAULT_BRAND, fetchAppConfig, type Brand } from "../api/appConfig";

function applyDocumentTitle(name: string): void {
  if (typeof document !== "undefined") {
    document.title = name;
  }
}

/** Runtime brand configuration backed by the public app-config endpoint. */
export const useAppConfigStore = defineStore("appConfig", () => {
  const brand = ref<Brand>({ ...DEFAULT_BRAND });
  const isLoaded = ref(false);
  let loadPromise: Promise<void> | null = null;

  async function loadOnce(): Promise<void> {
    try {
      const response = await fetchAppConfig();
      brand.value = response.brand;
      isLoaded.value = true;
    } catch {
      brand.value = { ...DEFAULT_BRAND };
      isLoaded.value = true;
    } finally {
      applyDocumentTitle(brand.value.name);
    }
  }

  /**
   * Load the deployment brand once and mirror the name into the document title.
   *
   * Transport or payload failures keep the shipped defaults and never throw, so
   * application mounting is never blocked by branding.
   * @returns No value.
   */
  async function load(): Promise<void> {
    loadPromise ??= loadOnce();
    await loadPromise;
  }

  return { brand, isLoaded, load };
});
