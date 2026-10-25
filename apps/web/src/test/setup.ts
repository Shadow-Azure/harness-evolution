import { config } from "@vue/test-utils";
import ElButton from "element-plus/es/components/button/index";
import ElInput from "element-plus/es/components/input/index";

/** Element Plus controls mounted explicitly by tests that bypass Vite component transforms. */
export const elementPlusComponents = {
  ElButton,
  ElInput,
};

config.global.components = {
  ...config.global.components,
  ...elementPlusComponents,
};
