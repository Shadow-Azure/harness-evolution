import { config } from "@vue/test-utils";
import ElButton from "element-plus/es/components/button/index";
import ElInput from "element-plus/es/components/input/index";
import { beforeEach } from "vitest";

/** Element Plus controls mounted explicitly by tests that bypass Vite component transforms. */
export const elementPlusComponents = {
  ElButton,
  ElInput,
};

config.global.components = {
  ...config.global.components,
  ...elementPlusComponents,
};

/** Minimal jsdom observer used by Vue Flow layout measurement. */
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

function installResizeObserver() {
  Object.defineProperty(globalThis, "ResizeObserver", {
    configurable: true,
    value: ResizeObserverMock,
  });
  if (typeof window !== "undefined") {
    Object.defineProperty(window, "ResizeObserver", {
      configurable: true,
      value: ResizeObserverMock,
    });
  }
}

beforeEach(installResizeObserver);
