<script setup lang="ts">
import LoginForm from "./LoginForm.vue";

defineOptions({ name: "LoginPage" });
</script>

<template>
  <section class="auth-page">
    <article
      class="auth-card"
      data-testid="login-card"
    >
      <section
        class="login-brand"
        data-testid="login-brand"
        aria-labelledby="login-brand-title"
      >
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
        <div class="brand-heading">
          <h1 id="login-brand-title">
            工作空间 · 归因 · 进化
          </h1>
          <p class="brand-sub">
            在同一个工作空间里查看 Session 轨迹、按对象归因 bad case，并把结论送进自进化流程。
          </p>
        </div>
        <ul
          class="login-points"
          data-testid="login-capabilities"
        >
          <li class="login-point">
            <span
              class="lp-ico"
              aria-hidden="true"
            >1</span>
            <span><b>工作空间隔离</b>：数据、成员、额度与进化对象都按空间收口。</span>
          </li>
          <li class="login-point">
            <span
              class="lp-ico"
              aria-hidden="true"
            >2</span>
            <span><b>归因进入进化流程</b>：同一 bad case 可以拥有多个对象的归因结论。</span>
          </li>
          <li class="login-point">
            <span
              class="lp-ico"
              aria-hidden="true"
            >3</span>
            <span><b>默认 10 个 Session</b>：输入 root session ID 回车，精确拉取目标会话。</span>
          </li>
        </ul>
        <p class="brand-foot">
          轨迹诊断服务 · 内部部署 · 不开放公开注册
        </p>
      </section>
      <section
        class="login-form-wrap"
        data-testid="login-form-region"
        aria-labelledby="login-form-title"
      >
        <h2 id="login-form-title">
          登录
        </h2>
        <p class="form-sub">
          使用管理员分配的账号进入轨迹诊断服务。
        </p>
        <div class="form-body">
          <LoginForm />
        </div>
        <p class="footnote">
          账号由组织管理员创建；首次登录需要设置自己的密码。
        </p>
      </section>
    </article>
  </section>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 30px;
  background:
    radial-gradient(
      900px 420px at 12% 0%,
      color-mix(in srgb, var(--blue) 10%, transparent),
      transparent 70%
    ),
    radial-gradient(
      800px 420px at 92% 100%,
      color-mix(in srgb, var(--purple) 9%, transparent),
      transparent 70%
    ),
    var(--bg);
}

.auth-card {
  width: min(920px, 100%);
  display: grid;
  grid-template-columns: 1.02fr 0.98fr;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  box-shadow: var(--shadow-auth-card);
}

.login-brand {
  display: flex;
  flex-direction: column;
  padding: 38px 40px 34px;
  border-right: 1px solid var(--border);
  background: linear-gradient(
    145deg,
    color-mix(in srgb, var(--blue) 7%, var(--bg-card)),
    color-mix(in srgb, var(--purple) 5%, var(--bg-card))
  );
}

.brand-lockup {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.brand-lockup > div {
  display: grid;
  gap: 2px;
}

.brand-lockup span {
  color: var(--text-faint);
  font-size: 11px;
}

.brand-mark {
  width: 38px;
  height: 38px;
  border-radius: 11px;
  background: var(--brand-gradient);
  box-shadow: 0 6px 16px color-mix(in srgb, var(--blue) 26%, transparent);
}

.brand-lockup strong {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.2px;
}

.brand-heading {
  margin-top: 26px;
}

h1 {
  max-width: 330px;
  margin: 0;
  font-size: 23px;
  font-weight: 700;
  line-height: 1.35;
  letter-spacing: 0.2px;
}

.brand-sub {
  max-width: 340px;
  margin: 10px 0 0;
  color: var(--text-dim);
  font-size: 12.5px;
  line-height: 1.7;
}

.login-points {
  display: flex;
  flex-direction: column;
  gap: 9px;
  margin: 28px 0 0;
  padding: 0;
  list-style: none;
}

.login-point {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1.65;
}

.login-point b {
  color: var(--text);
  font-weight: 600;
}

.lp-ico {
  display: grid;
  flex: none;
  place-items: center;
  width: 18px;
  height: 18px;
  border: 1px solid color-mix(in srgb, var(--blue) 28%, transparent);
  border-radius: 5px;
  background: color-mix(in srgb, var(--blue) 12%, var(--bg-card));
  color: var(--blue);
  font-size: 10px;
  font-weight: 700;
}

.brand-foot {
  margin: auto 0 0;
  padding-top: 28px;
  color: var(--text-faint);
  font-size: 10.5px;
  line-height: 1.6;
}

.login-form-wrap {
  display: flex;
  flex-direction: column;
  padding: 34px 36px;
}

h2 {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
}

.form-sub {
  margin: 3px 0 0;
  color: var(--text-faint);
  font-size: 11.5px;
  line-height: 1.6;
}

.form-body {
  margin-top: 18px;
}

.footnote {
  margin: auto 0 0;
  padding-top: 14px;
  border-top: 1px solid var(--border);
  color: var(--text-faint);
  font-size: 11px;
  line-height: 1.65;
}

@media (max-width: 760px) {
  .auth-card {
    grid-template-columns: 1fr;
  }

  .login-brand {
    padding: 26px 24px;
    border-right: none;
    border-bottom: 1px solid var(--border);
  }

  .login-points,
  .brand-foot {
    display: none;
  }

  .login-form-wrap {
    padding: 24px;
  }
}

@media (max-width: 420px) {
  .auth-page {
    padding: 16px;
  }
}
</style>
