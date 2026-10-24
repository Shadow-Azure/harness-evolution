import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const apiProxyUrl = process.env.HE_API_PROXY_URL ?? "http://127.0.0.1:8787";
const webPort = Number(process.env.HE_WEB_PORT ?? 5173);

export default defineConfig({
  plugins: [react()],
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
    outDir: "dist"
  }
});
