import { config } from "@vue/test-utils";
import ElAutocomplete from "element-plus/es/components/autocomplete/index";
import ElButton from "element-plus/es/components/button/index";
import ElDialog from "element-plus/es/components/dialog/index";
import { ElForm, ElFormItem } from "element-plus/es/components/form/index";
import ElInput from "element-plus/es/components/input/index";
import {
  ElRadioButton,
  ElRadioGroup,
} from "element-plus/es/components/radio/index";
import {
  ElOption,
  ElSelect,
} from "element-plus/es/components/select/index";
import ElSwitch from "element-plus/es/components/switch/index";
import { beforeEach } from "vitest";

/** Element Plus controls mounted explicitly by tests that bypass Vite component transforms. */
export const elementPlusComponents = {
  ElAutocomplete,
  ElButton,
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElOption,
  ElRadioButton,
  ElRadioGroup,
  ElSelect,
  ElSwitch,
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
