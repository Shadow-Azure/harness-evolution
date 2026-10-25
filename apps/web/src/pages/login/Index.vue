<script setup lang="ts">
import LoginForm from "./LoginForm.vue";

defineOptions({ name: "LoginPage" });
</script>

<template>
  <section class="auth-page">
    <article class="auth-card">
      <div class="brand-lockup">
        <span class="brand-mark">HL</span>
        <div>
          <strong>Harness Lens</strong>
          <span>组织内部系统</span>
        </div>
      </div>
      <div class="heading">
        <p class="eyebrow">
          WELCOME BACK
        </p>
        <h1>登录</h1>
        <p>
          使用管理员分配的账号进入轨迹诊断服务。
        </p>
      </div>
      <LoginForm />
      <p class="footnote">
        账号由组织管理员创建；首次登录需要设置自己的密码。
      </p>
    </article>
  </section>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: var(--space-lg);
  background: var(--page-gradient);
}

.auth-card {
  width: min(420px, 100%);
  padding: var(--space-xl);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--surface-raised);
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
  color: var(--text-muted);
  font-size: 12px;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: var(--radius-md);
  background: var(--brand-gradient);
  color: var(--surface-base);
  font-weight: var(--weight-bold);
}

.heading {
  margin: var(--space-xl) 0 var(--space-lg);
}

.eyebrow {
  margin: 0 0 var(--space-xs);
  color: var(--brand-accent);
  font-size: 11px;
  letter-spacing: 0.16em;
}

h1 {
  margin: 0 0 var(--space-xs);
  font-size: 32px;
}

.heading p,
.footnote {
  margin: 0;
  color: var(--text-muted);
}

.footnote {
  margin-top: var(--space-md);
  font-size: 12px;
  line-height: 1.65;
}
</style>
