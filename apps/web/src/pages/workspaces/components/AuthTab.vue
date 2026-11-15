<script setup lang="ts">
defineOptions({ name: "WorkspaceAuthTab" });

const authItems = [
  {
    title: "Cookie 会话",
    badge: "已预留",
    tone: "ok",
    description:
      "登录成功后写入 HttpOnly 会话 Cookie（SameSite=Lax）；前端启动时调用 GET /api/auth/session 恢复用户与可用空间，不把身份放进 localStorage。",
  },
  {
    title: "登录 / 登出",
    badge: "已预留",
    tone: "ok",
    description:
      "POST /api/auth/login 校验凭据并下发 Cookie；POST /api/auth/logout 清理会话。不提供公开注册端点，账号由管理员创建或邀请。",
  },
  {
    title: "用户信息映射",
    badge: "已预留",
    tone: "ok",
    description:
      "外部身份只需映射 id / email / name / avatar，再关联 workspace_members；全局管理员唯一，普通用户的角色由成员关系决定。",
  },
  {
    title: "SSO / OIDC 回调",
    badge: "待接入",
    tone: "",
    description:
      "GET /api/auth/callback 接收 IdP 回调，按 sub 或 email 匹配用户；未匹配时拒绝登录，不自动创建账号（不放开注册）。",
  },
  {
    title: "空间授权",
    badge: "已预留",
    tone: "ok",
    description:
      "所有读写在服务端按 workspace_id + user_id 校验角色；前端隐藏入口只是体验优化，不能替代服务端校验。",
  },
] as const;

const contract = `GET /api/auth/session
200 {
  "user": { "id": "u_1024", "email": "li.wei@example.com", "name": "李伟",
             "avatar": "李", "globalRole": "user" },
  "workspaces": [
    { "id": "ws_harness", "name": "Harness 核心研发", "role": "space_admin", "quota": 60, "used": 25 }
  ]
}

POST /api/auth/login   { "username": "...", "password": "..." }
200 { "accessToken": "...", "expiresIn": 1800, "user": { ... } }

POST /api/auth/logout
204`;

const checks = [
  "Cookie 会话 ✓",
  "用户映射 ✓",
  "注册关闭 ✓",
  "SSO/OIDC 回调待接入",
];
</script>

<template>
  <div data-testid="auth-tab">
    <div class="admin-head">
      <div>
        <h2>鉴权接入（预留）</h2>
        <p class="sub">
          当前使用账号密码与 Cookie 会话；生产接入只需替换身份提供方，业务权限仍由本服务的成员关系判定。
        </p>
      </div>
      <div class="actions">
        <span class="badge warn">注册未开放</span>
      </div>
    </div>

    <div class="auth-list">
      <div
        v-for="(item, index) in authItems"
        :key="item.title"
        class="auth-item"
      >
        <span class="ai-ico">{{ index + 1 }}</span>
        <div class="ai-main">
          <b>{{ item.title }}</b>
          <div class="ai-desc">
            {{ item.description }}
          </div>
        </div>
        <span
          class="badge"
          :class="item.tone"
        >{{ item.badge }}</span>
      </div>
    </div>

    <div class="ingest-card">
      <h3>接入契约（替换身份提供方即可）</h3>
      <pre
        class="codebox"
        data-testid="auth-contract"
      >{{ contract }}</pre>
      <p class="field-help">
        前端只需要把演示账号替换成 GET /api/auth/session 的返回值；角色判断继续复用 workspace_members，不需要改业务页面。
      </p>
    </div>

    <p class="checks">
      接入检查：{{ checks.join(" · ") }}
    </p>
  </div>
</template>

<style scoped>
.admin-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.admin-head h2 {
  margin: 0;
  color: var(--text);
  font-size: 15px;
  font-weight: 650;
}

.admin-head .sub {
  margin: 2px 0 0;
  color: var(--text-faint);
  font-size: 11px;
  line-height: 1.6;
}

.admin-head .actions {
  margin-left: auto;
  flex-shrink: 0;
}

.badge {
  padding: 0 7px;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-faint);
  font-size: 9.5px;
  white-space: nowrap;
}

.badge.ok {
  border-color: color-mix(in srgb, var(--green) 32%, transparent);
  background: color-mix(in srgb, var(--green) 9%, transparent);
  color: var(--green);
}

.badge.warn {
  border-color: color-mix(in srgb, var(--orange) 38%, transparent);
  background: color-mix(in srgb, var(--orange) 9%, transparent);
  color: var(--orange);
}

.auth-list {
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.auth-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
}

.ai-ico {
  display: grid;
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  place-items: center;
  border: 1px solid color-mix(in srgb, var(--blue) 25%, transparent);
  border-radius: 6px;
  background: color-mix(in srgb, var(--blue) 10%, var(--bg-card));
  color: var(--blue);
  font-size: 10px;
  font-weight: 700;
}

.ai-main {
  flex: 1;
  min-width: 0;
}

.ai-main b {
  display: block;
  color: var(--text);
  font-size: 12px;
  font-weight: 600;
}

.ai-desc {
  margin-top: 2px;
  color: var(--text-faint);
  font-size: 10.5px;
  line-height: 1.6;
}

.ingest-card {
  margin-top: 12px;
  padding: 12px 13px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-panel);
}

.ingest-card h3 {
  margin: 0 0 6px;
  color: var(--text-dim);
  font-size: 11.5px;
  font-weight: 650;
}

.codebox {
  max-height: 320px;
  margin: 8px 0 0;
  padding: 9px 11px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-inset);
  color: var(--text-dim);
  font-family: var(--mono);
  font-size: 10px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.field-help {
  margin: 6px 0 0;
  color: var(--text-faint);
  font-size: 10.5px;
  line-height: 1.6;
}

.checks {
  margin: 12px 0 0;
  color: var(--text-faint);
  font-size: 10.5px;
}
</style>
