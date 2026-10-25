import type { App } from "vue";

/**
 * Install the shell-level Vue error boundary notification.
 * @param app Application whose uncaught render and handler errors are captured.
 * @param notify Presentation callback used for a user-safe generic message.
 * @returns No value.
 */
export function installGlobalErrorHandler(
  app: App,
  notify: (message: string) => void,
): void {
  app.config.errorHandler = (error, _instance, info) => {
    console.error("[vue]", error, info);
    notify("操作失败，请稍后重试");
  };
}
