<script setup lang="ts">
import LoginForm from "./LoginForm.vue";

defineOptions({ name: "LoginPage" });
</script>

<template>
  <section class="auth-page">
    <article class="auth-card">
      <div class="brand-lockup">
        <span
          class="brand-mark"
          aria-hidden="true"
        />
        <div>
          <strong>Harness Evolution</strong>
          <span>轨迹诊断与自进化</span>
        </div>
      </div>
      <div class="heading">
        <p class="eyebrow">
          SESSION
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
  padding: 24px;
  background: var(--bg);
}

.auth-card {
  width: min(420px, 100%);
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

.heading p,
.footnote {
  margin: 0;
  color: var(--text-dim);
  font-size: 12.5px;
  line-height: 1.65;
}

.footnote {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
  color: var(--text-faint);
  font-size: 11px;
  line-height: 1.65;
}
</style>
