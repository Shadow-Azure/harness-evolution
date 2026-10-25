<script setup lang="ts">
import { computed, ref } from "vue";

import { authErrorCode, useLogin } from "../../composables/useAuth";

defineOptions({ name: "LoginForm" });

const username = ref("");
const password = ref("");
const validationError = ref("");
const { error, isLoading, refetch: login } = useLogin();

const errorMessage = computed(() => {
  if (validationError.value) {
    return validationError.value;
  }
  if (!error.value) {
    return "";
  }
  const code = authErrorCode(error.value);
  if (code === "AUTH_INVALID") {
    return "用户名或密码错误";
  }
  if (code === "RATE_LIMITED") {
    return "登录尝试过多，请稍后重试";
  }
  return error.value.message || "登录失败，请稍后重试";
});

const isSubmitDisabled = computed(
  () => isLoading.value || !username.value.trim() || !password.value,
);

async function submit() {
  validationError.value = "";
  if (!username.value.trim() || !password.value) {
    validationError.value = "请输入用户名和密码";
    return;
  }
  try {
    await login({
      username: username.value.trim(),
      password: password.value,
    });
  } catch {
    // The composable exposes the unified error for inline rendering.
  }
}
</script>

<template>
  <form @submit.prevent="submit">
    <label for="login-username">用户名</label>
    <ElInput
      id="login-username"
      v-model="username"
      autocomplete="username"
      name="username"
      placeholder="请输入用户名"
    />
    <label for="login-password">密码</label>
    <ElInput
      id="login-password"
      v-model="password"
      autocomplete="current-password"
      name="password"
      placeholder="请输入密码"
      show-password
      type="password"
    />
    <p
      v-if="errorMessage"
      class="error-message"
      role="alert"
      aria-live="polite"
    >
      {{ errorMessage }}
    </p>
    <ElButton
      class="submit"
      data-testid="login-submit"
      :disabled="isSubmitDisabled"
      :loading="isLoading"
      native-type="submit"
      type="primary"
    >
      {{ isLoading ? "登录中…" : "登录" }}
    </ElButton>
  </form>
</template>

<style scoped>
form {
  display: grid;
  gap: var(--space-xs);
}

label {
  margin-top: var(--space-sm);
  color: var(--text-secondary);
  font-size: 13px;
}

.error-message {
  margin: var(--space-xs) 0 0;
  padding: 9px 11px;
  border: 1px solid var(--state-error-border);
  border-radius: var(--radius-md);
  background: var(--state-error-surface);
  color: var(--state-error-text);
}

.submit {
  width: 100%;
  margin-top: var(--space-md);
}
</style>
