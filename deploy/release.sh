#!/usr/bin/env bash
# 服务器端发布脚本：由 GitHub Actions 通过 SSH 调用。
# 用法: release.sh /opt/harness/releases/<sha>
# 行为: 安装 API 依赖 → Alembic 迁移 → 原子切换 current 软链 → 重启服务 →
#       健康检查（/api/health，最多 60s）→ 失败回滚上一 release 并重启。
# 权限: deploy 用户仅对 systemctl restart/start harness-api 免密 sudo。
set -euo pipefail

RELEASE="${1:?用法: release.sh <release-dir>}"
API_DIR="$RELEASE/api"
SHARED=/opt/harness/shared
CURRENT=/opt/harness/current
VENV="$SHARED/venv"
ENV_FILE="$SHARED/.env"
HEALTH_URL="http://127.0.0.1:8787/api/health"

if [ ! -f "$ENV_FILE" ]; then
  echo "[release] 缺少 $ENV_FILE（先完成 bootstrap）" >&2
  exit 2
fi
if [ ! -d "$API_DIR" ]; then
  echo "[release] release 目录不存在: $API_DIR" >&2
  exit 2
fi

# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a

PREV_TARGET=""
if [ -L "$CURRENT" ]; then
  PREV_TARGET=$(readlink -f "$CURRENT")
fi

echo "[release] 安装 API 依赖（共享 venv: $VENV）"
"$VENV/bin/pip" install --quiet "$API_DIR"

echo "[release] 数据库迁移（Alembic upgrade head）"
cp "$API_DIR/alembic.ini" "$API_DIR/alembic.ini.release"
# ini 中 sqlalchemy.url 为空，发布时注入 HE_DB_URL；转义替换串里的 & 与 |
ESC_URL=${HE_DB_URL//&/\\&}
ESC_URL=${ESC_URL//|/\\|}
sed -i "s|^sqlalchemy.url *=.*|sqlalchemy.url = ${ESC_URL}|" "$API_DIR/alembic.ini.release"
(cd "$API_DIR" && "$VENV/bin/alembic" -c alembic.ini.release upgrade head)

echo "[release] 原子切换 current -> $RELEASE"
ln -sfn "$RELEASE" "$CURRENT.tmp"
mv -T "$CURRENT.tmp" "$CURRENT"

rollback() {
  echo "[release] 回滚到 $PREV_TARGET" >&2
  if [ -n "$PREV_TARGET" ] && [ -d "$PREV_TARGET" ]; then
    ln -sfn "$PREV_TARGET" "$CURRENT.tmp"
    mv -T "$CURRENT.tmp" "$CURRENT"
  fi
  sudo /usr/bin/systemctl restart harness-api
}

echo "[release] 重启 harness-api"
sudo /usr/bin/systemctl restart harness-api

echo "[release] 健康检查（最长 60s）"
ok=0
for _ in $(seq 1 30); do
  if curl -sf "$HEALTH_URL" > /dev/null; then ok=1; break; fi
  sleep 2
done

if [ "$ok" -ne 1 ]; then
  echo "[release] 健康检查失败" >&2
  rollback
  exit 1
fi

# 只保留最近 5 个 release
cd "$SHARED/../releases" 2>/dev/null || cd /opt/harness/releases
ls -1t | tail -n +6 | while read -r old; do
  echo "[release] 清理旧版本: $old"
  rm -rf "/opt/harness/releases/$old"
done

echo "[release] 完成: $RELEASE"
