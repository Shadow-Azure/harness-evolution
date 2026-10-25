<script setup lang="ts">
import { computed, ref } from "vue";

import { authErrorCode, useChangePassword } from "../../composables/useAuth";

defineOptions({ name: "ChangePasswordCard" });

const oldPassword = ref("");
const newPassword = ref("");
const confirmPassword = ref("");
const validationError = ref("");
const { error, isLoading, refetch: changePassword } = useChangePassword();

const errorMessage = computed(() => {
  if (validationError.value) {
    return validationError.value;
  }
  if (!error.value) {
    return "";
  }
  if (authErrorCode(error.value) === "AUTH_INVALID") {
    return "当前密码错误";
  }
  return error.value.message || "修改密码失败，请稍后重试";
});

const isSubmitDisabled = computed(
  () =>
    isLoading.value ||
    !oldPassword.value ||
    newPassword.value.length < 8 ||
    !confirmPassword.value,
);

async function submit() {
  validationError.value = "";
  if (newPassword.value !== confirmPassword.value) {
    validationError.value = "两次输入的新密码不一致";
    return;
  }
  if (newPassword.value === oldPassword.value) {
    validationError.value = "新密码不能与当前密码相同";
    return;
  }
  if (newPassword.value.length < 8) {
    validationError.value = "新密码至少需要 8 个字符";
    return;
  }
  try {
    await changePassword({
      oldPassword: oldPassword.value,
      newPassword: newPassword.value,
    });
  } catch {
    // The composable exposes the unified error for inline rendering.
  }
}
</script>

<template>
  <article class="auth-card">
    <div class="brand-lockup">
      <span
        class="brand-mark"
        aria-hidden="true"
      />
      <div>
        <strong>Harness Evolution</strong>
        <span>首次登录</span>
      </div>
    </div>
    <div class="heading">
      <p class="eyebrow">
        SECURITY CHECK
      </p>
      <h1>设置新密码</h1>
      <p>
        初始密码由管理员分配。首次登录请设置自己的密码，完成后继续使用系统。
      </p>
    </div>
    <form @submit.prevent="submit">
      <label for="old-password">当前密码</label>
      <ElInput
        id="old-password"
        v-model="oldPassword"
        autocomplete="current-password"
        name="oldPassword"
        placeholder="输入管理员分配的密码"
        show-password
        type="password"
      />
      <label for="new-password">新密码</label>
      <ElInput
        id="new-password"
        v-model="newPassword"
        autocomplete="new-password"
        name="newPassword"
        placeholder="至少 8 个字符"
        show-password
        type="password"
      />
      <label for="confirm-password">确认新密码</label>
      <ElInput
        id="confirm-password"
        v-model="confirmPassword"
        autocomplete="new-password"
        name="confirmPassword"
        placeholder="再次输入新密码"
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
        data-testid="change-password-submit"
        :disabled="isSubmitDisabled"
        :loading="isLoading"
        native-type="submit"
        type="primary"
      >
        {{ isLoading ? "保存中…" : "保存并继续" }}
      </ElButton>
    </form>
  </article>
</template>

<style scoped>
.auth-card {
  width: min(440px, 100%);
  padding: 28px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.brand-lockup {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.brand-lockup > div {
  display: grid;
}

.brand-lockup span {
  color: var(--text-faint);
  font-size: 10px;
}

.brand-mark {
  width: 24px;
  height: 24px;
  border-radius: 7px;
  background: var(--brand-gradient);
  box-shadow: var(--shadow-mark);
}

.brand-lockup strong {
  font-size: 13.5px;
  font-weight: 700;
  letter-spacing: 0.2px;
}

.heading {
  margin: 28px 0 20px;
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--blue);
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

h1 {
  margin: 0 0 5px;
  font-size: 24px;
  font-weight: 650;
}

.heading p {
  margin: 0;
  color: var(--text-dim);
  font-size: 12.5px;
  line-height: 1.65;
}

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
