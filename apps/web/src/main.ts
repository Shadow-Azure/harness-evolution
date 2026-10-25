import { createPinia } from "pinia";
import { createApp } from "vue";

import App from "./App.vue";
import { createAppQueryClient } from "./api/queryClient";
import { bootstrapApp } from "./bootstrap";
import { createAppRouter } from "./router";
import "./styles/main.css";
import "./styles/element-overrides.css";

void bootstrapApp({
  app: createApp(App),
  mountTarget: "#app",
  pinia: createPinia(),
  queryClient: createAppQueryClient(),
  router: createAppRouter(),
});
