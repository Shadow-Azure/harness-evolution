import vue from "@vitejs/plugin-vue";
import AutoImport from "unplugin-auto-import/vite";
import Components from "unplugin-vue-components/vite";
import { ElementPlusResolver } from "unplugin-vue-components/resolvers";
import type { ComponentResolver } from "unplugin-vue-components/types";
import { defineConfig } from "vitest/config";

const apiProxyUrl = process.env.HE_API_PROXY_URL ?? "http://127.0.0.1:8787";
const webPort = Number(process.env.HE_WEB_PORT ?? 5173);
const elementPlusDirectories: Readonly<Record<string, string>> = {
  ElButton: "button",
  ElDialog: "dialog",
  ElForm: "form",
  ElFormItem: "form",
  ElInput: "input",
  ElOption: "select",
  ElRadioButton: "radio",
  ElRadioGroup: "radio",
  ElSelect: "select",
  ElSwitch: "switch",
};

function elementPlusOnDemandResolver(): ComponentResolver {
  return {
    type: "component",
    resolve(name: string) {
      const directory = elementPlusDirectories[name];
      if (!directory) {
        return;
      }
      return {
        name,
        from: `element-plus/es/components/${directory}/index`,
        sideEffects: [
          "element-plus/es/components/base/style/css",
          `element-plus/es/components/${directory}/style/css`,
        ],
      };
    },
  };
}

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      dts: "src/auto-imports.d.ts",
      imports: [],
      resolvers: [ElementPlusResolver()],
    }),
    Components({
      dts: "src/components.d.ts",
      resolvers: [elementPlusOnDemandResolver()],
    }),
  ],
  optimizeDeps: {
    exclude: ["element-plus"],
  },
  server: {
    port: webPort,
    strictPort: true,
    proxy: {
      "/api": {
        target: apiProxyUrl,
        changeOrigin: true
      }
    }
  },
  build: {
    manifest: true,
    outDir: "dist",
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes("@vue-flow")) {
            return "vendor-vue-flow";
          }
          if (id.includes("/node_modules/element-plus/")) {
            return "vendor-element-plus";
          }
          if (id.includes("/node_modules/vue/") || id.includes("/node_modules/vue-router/") || id.includes("/node_modules/pinia/") || id.includes("/node_modules/@tanstack/")) {
            return "vendor-vue";
          }
          return undefined;
        }
      }
    }
  },
  test: {
    setupFiles: ["./src/test/setup.ts"]
  }
});
