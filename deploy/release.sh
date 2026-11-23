#!/usr/bin/env bash
# 服务器端发布脚本：由 GitHub Actions 通过 SSH 调用。
# 用法: release.sh /opt/harness/releases/<sha>
# 行为: 校验数据目录 → 安装 API 依赖 → 归因预检 → Alembic 迁移 → 原子切换 current 软链 →
#       重启服务 → 健康检查（/api/health，最多 60s）→ 失败回滚上一 release。
# 失败时恢复注入前的 .env（注入器备份到 /opt/harness/shared/.env.bak.<sha>）。
# 权限: deploy 用户仅对 systemctl restart/start harness-api 免密 sudo。
set -euo pipefail

RELEASE="${1:?用法: release.sh <release-dir>}"
API_DIR="$RELEASE/api"
SHARED=/opt/harness/shared
CURRENT=/opt/harness/current
RELEASES_ROOT=/opt/harness/releases
VENV="$SHARED/venv"
ENV_FILE="$SHARED/.env"
ENV_BACKUP="$SHARED/.env.bak.$(basename "$RELEASE")"
HEALTH_URL="http://127.0.0.1:8787/api/health"
DEFAULT_DATA_DIR=/var/lib/harness-evolution/data

if [ ! -f "$ENV_FILE" ]; then
  echo "[release] 缺少 $ENV_FILE（先完成 bootstrap）" >&2
  exit 2
fi
if [ ! -d "$API_DIR" ]; then
  echo "[release] release 目录不存在: $API_DIR" >&2
  exit 2
fi

read_env_value() {
  sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1
}

fail() {
  echo "[release] $*" >&2
  exit 1
}

restore_env() {
  if [ -f "$ENV_BACKUP" ]; then
    echo "[release] 恢复部署前的 .env: $ENV_BACKUP" >&2
    if cp -p "$ENV_BACKUP" "$ENV_FILE"; then
      rm -f "$ENV_BACKUP"
    else
      echo "[release] 警告: 恢复 $ENV_BACKUP 失败，请手工检查" >&2
    fi
  fi
}

RELEASE_OK=0
cleanup() {
  status=$?
  trap - EXIT
  if [ "$RELEASE_OK" -ne 1 ]; then
    restore_env
  fi
  exit "$status"
}
trap cleanup EXIT

# Inspect the candidate release before migrating or replacing the current symlink.
while IFS= read -r asset; do
  [ -s "$API_DIR/release-assets/$asset" ] || fail "归因资源缺失或为空: $asset"
done < "$SHARED/config/attribution-assets.list"

validate_data_dir_path() {
  local dir="$1"
  if [ -z "$dir" ]; then
    fail "HE_DATA_DIR 未配置：deploy 流水线应注入绝对路径（默认 $DEFAULT_DATA_DIR）"
  fi
  case "$dir" in
    *[[:space:]]*) fail "HE_DATA_DIR 不得包含空白或换行: $dir" ;;
  esac
  case "$dir" in
    /*) ;;
    *) fail "HE_DATA_DIR 必须是绝对路径: $dir" ;;
  esac
  case "/$dir/" in
    */../*) fail "HE_DATA_DIR 不得包含 ..: $dir" ;;
  esac
  case "$dir" in
    "$CURRENT"|"$CURRENT"/*|"$RELEASES_ROOT"|"$RELEASES_ROOT"/*)
      fail "HE_DATA_DIR 不得位于发布目录（current/releases）: $dir" ;;
  esac
}

state_directory_covers() {
  local dir="$1" state entry
  state="$(systemctl show -p StateDirectory --value harness-api 2>/dev/null || true)"
  for entry in $state; do
    [ -n "$entry" ] || continue
    case "$dir" in
      "/var/lib/$entry"|"/var/lib/$entry/"*) return 0 ;;
    esac
  done
  return 1
}

check_data_dir_ready() {
  local dir="$1" owner mode perm
  if [ -d "$dir" ]; then
    owner="$(stat -c '%U:%G' "$dir" 2>/dev/null || true)"
    if [ "$owner" != "harness:harness" ]; then
      fail "HE_DATA_DIR 目录属主应为 harness:harness，实为 ${owner:-unknown}: $dir"
    fi
    mode="$(stat -c '%a' "$dir" 2>/dev/null || true)"
    if ! [[ "$mode" =~ ^[0-7]+$ ]]; then
      fail "无法读取 HE_DATA_DIR 目录权限: $dir"
    fi
    perm=$(( 8#$mode ))
    if (( (perm & 0200) == 0 )); then
      fail "HE_DATA_DIR 目录对属主不可写（mode $mode）: $dir"
    fi
    return 0
  fi
  if state_directory_covers "$dir"; then
    echo "[release] HE_DATA_DIR 尚未创建，unit StateDirectory 已覆盖: $dir"
    return 0
  fi
  fail "HE_DATA_DIR 目录不存在且未被 unit StateDirectory 覆盖: $dir"
}

# 先校验 .env 里的原始值，避免 source 一条格式错误的赋值语句；再 source 后校验目录。
RAW_DATA_DIR="$(read_env_value HE_DATA_DIR)"
validate_data_dir_path "$RAW_DATA_DIR"

# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a

validate_data_dir_path "${HE_DATA_DIR:-}"
check_data_dir_ready "${HE_DATA_DIR:-}"

PREV_TARGET=""
if [ -L "$CURRENT" ]; then
  PREV_TARGET=$(readlink -f "$CURRENT")
fi

echo "[release] 安装 API 依赖（共享 venv: $VENV）"
"$VENV/bin/pip" install --quiet "$API_DIR"

# Use the candidate API and the shared service environment, including the provider default.
(cd "$API_DIR" && "$VENV/bin/python" -m app.third_party_api.ai_agent.preflight) ||
  fail "归因运行时预检失败，尚未执行迁移或切换 current。ATTRIBUTION_BWRAP_MISSING 表示主机缺 bubblewrap，运行 Actions → Provision（mode=install）；ATTRIBUTION_BWRAP_UNUSABLE 表示 harness 命名空间探针失败；其余错误码见 docs/deployment.md 的 Provision 入口。旧 release 继续服务。"

echo "[release] 数据库迁移（Alembic upgrade head）"
# ini 中 sqlalchemy.url 为空，发布时注入 HE_DB_URL；转义替换串里的 & 与 |
ESC_URL=${HE_DB_URL//&/\\&}
ESC_URL=${ESC_URL//|/\\|}
(umask 077; sed "s|^sqlalchemy.url *=.*|sqlalchemy.url = ${ESC_URL}|" "$API_DIR/alembic.ini" > "$API_DIR/alembic.ini.release")
(cd "$API_DIR" && "$VENV/bin/alembic" -c alembic.ini.release upgrade head)

echo "[release] 原子切换 current -> $RELEASE"
ln -sfn "$RELEASE" "$CURRENT.tmp"
mv -T "$CURRENT.tmp" "$CURRENT"

rollback() {
  echo "[release] 回滚到 $PREV_TARGET" >&2
  if [ -n "$PREV_TARGET" ] && [ -d "$PREV_TARGET" ]; then
    ln -sfn "$PREV_TARGET" "$CURRENT.tmp"
    mv -T "$CURRENT.tmp" "$CURRENT"
  else
    echo "[release] 警告: 没有可回滚的上一 release，保留当前代码" >&2
  fi
  # 先恢复 .env 再重启，避免坏值让回滚后的 release 也起不来。
  restore_env
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

RELEASE_OK=1

# 只保留最近 5 个 release 与 5 份 .env 备份
cd "$SHARED/../releases" 2>/dev/null || cd "$RELEASES_ROOT"
ls -1t | tail -n +6 | while read -r old; do
  echo "[release] 清理旧版本: $old"
  rm -rf "$RELEASES_ROOT/$old"
done
if compgen -G "$SHARED/.env.bak.*" > /dev/null; then
  while IFS= read -r old_backup; do
    echo "[release] 清理旧 .env 备份: $old_backup"
    rm -f "$old_backup"
  done < <(ls -1t "$SHARED"/.env.bak.* 2>/dev/null | tail -n +6)
fi

echo "[release] 完成: $RELEASE"
