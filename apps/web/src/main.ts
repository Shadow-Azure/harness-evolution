import { VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia } from "pinia";
import { createApp } from "vue";

import App from "./App.vue";
import { createAppQueryClient } from "./api/queryClient";
import { createAppRouter } from "./router";
import "./styles/main.css";

createApp(App)
  .use(createPinia())
  .use(VueQueryPlugin, { queryClient: createAppQueryClient() })
  .use(createAppRouter())
  .mount("#app");
