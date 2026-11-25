// @vitest-environment jsdom

import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_BRAND } from "../api/appConfig";
import { useAppConfigStore } from "./appConfig";

const { fetchAppConfigMock } = vi.hoisted(() => ({
  fetchAppConfigMock: vi.fn(),
}));

vi.mock("../api/appConfig", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/appConfig")>();
  return { ...actual, fetchAppConfig: fetchAppConfigMock };
});

beforeEach(() => {
  vi.clearAllMocks();
  setActivePinia(createPinia());
  document.title = "pre-load-title";
});

describe("app-config store", () => {
  it("starts from the shipped default brand", () => {
    const store = useAppConfigStore();

    expect(store.brand).toEqual(DEFAULT_BRAND);
    expect(store.isLoaded).toBe(false);
  });

  it("loads the configured brand once and applies the document title", async () => {
    fetchAppConfigMock.mockResolvedValue({
      brand: {
        name: "Acme Diagnostics",
        subtitle: "Acme Self-Evolution",
      },
    });
    const store = useAppConfigStore();

    await store.load();
    await store.load();

    expect(fetchAppConfigMock).toHaveBeenCalledTimes(1);
    expect(store.brand).toEqual({
      name: "Acme Diagnostics",
      subtitle: "Acme Self-Evolution",
    });
    expect(store.isLoaded).toBe(true);
    expect(document.title).toBe("Acme Diagnostics");
  });

  it("deduplicates concurrent loads into one request", async () => {
    fetchAppConfigMock.mockResolvedValue({
      brand: {
        name: "Acme Diagnostics",
        subtitle: "Acme Self-Evolution",
      },
    });
    const store = useAppConfigStore();

    await Promise.all([store.load(), store.load()]);

    expect(fetchAppConfigMock).toHaveBeenCalledTimes(1);
  });

  it("keeps the defaults and title when loading fails without throwing", async () => {
    fetchAppConfigMock.mockRejectedValue(new Error("offline"));
    document.title = "pre-load-title";
    const store = useAppConfigStore();

    await expect(store.load()).resolves.toBeUndefined();

    expect(store.brand).toEqual(DEFAULT_BRAND);
    expect(store.isLoaded).toBe(true);
    expect(document.title).toBe(DEFAULT_BRAND.name);
  });
});
