import { createPinia } from "pinia";
import { createApp } from "vue";
import { ElMessage } from "element-plus/es/components/message/index";
import "element-plus/es/components/base/style/css";
import "element-plus/es/components/message/style/css";

import App from "./App.vue";
import { createAppQueryClient } from "./api/queryClient";
import { presentConflict } from "./app/apiError";
import { installGlobalErrorHandler } from "./app/globalError";
import { bootstrapApp } from "./bootstrap";
import { createAppRouter } from "./router";
import "./styles/main.css";
import "./styles/element-overrides.css";

const app = createApp(App);
const notifyError = (message: string) => {
  ElMessage.error(message);
};
installGlobalErrorHandler(app, notifyError);

void bootstrapApp({
  app,
  mountTarget: "#app",
  pinia: createPinia(),
  queryClient: createAppQueryClient({
    onError: (error) => {
      presentConflict(error, notifyError);
    },
  }),
  router: createAppRouter(),
});
