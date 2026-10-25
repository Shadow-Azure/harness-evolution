import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

const apiProxyUrl = process.env.HE_API_PROXY_URL ?? "http://127.0.0.1:8787";
const webPort = Number(process.env.HE_WEB_PORT ?? 5173);

export default defineConfig({
  plugins: [vue()],
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
          if (id.includes("/node_modules/vue/") || id.includes("/node_modules/vue-router/") || id.includes("/node_modules/pinia/") || id.includes("/node_modules/@tanstack/")) {
            return "vendor-vue";
          }
          return undefined;
        }
      }
    }
  }
});
