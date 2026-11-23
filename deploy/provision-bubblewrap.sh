#!/usr/bin/env bash
# 幂等安装并验证 bubblewrap（归因 Skill 的 Linux 运行时前置）。
# 用法: provision-bubblewrap.sh [--install | --check | --dry-run]
#   --install  默认。已安装则 no-op；缺失才 apt-get update + 安装；最后验证。
#   --check    只验证，不改主机；缺包/不可用/服务账号缺失时非零退出。
#   --dry-run  只打印将执行的动作，不改主机、不探测。
# 退出码: 0 ready/no-op；2 用法或权限错误；10 缺包；11 命名空间不可用；
#         12 服务账号缺失；20 apt 安装失败。机器可读结果行:
#         provision.bubblewrap state=<ready|missing|unusable|...> error_code=<code|NONE>
# 权限: root（--check 与 --install 需要 runuser 切换到服务账号；--dry-run 不需要）。
# 日志只含固定文案与路径，不打印环境变量或凭据。
set -euo pipefail

readonly SERVICE_USER="harness"
readonly EXIT_USAGE=2
readonly EXIT_BWRAP_MISSING=10
readonly EXIT_BWRAP_UNUSABLE=11
readonly EXIT_SERVICE_USER_MISSING=12
readonly EXIT_APT_FAILED=20
readonly PROBE_PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

MODE="install"

log() {
  printf '[provision-bubblewrap] %s\n' "$*" >&2
}

emit() {
  printf 'provision.bubblewrap state=%s error_code=%s\n' "$1" "$2"
}

usage() {
  cat >&2 <<'USAGE'
用法: provision-bubblewrap.sh [--install | --check | --dry-run]
  --install  幂等安装并验证 bubblewrap（默认；需要 root）
  --check    只验证，不改主机（需要 root）
  --dry-run  只打印计划，不改主机
USAGE
}

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    log "需要 root 运行（sudo bash $0 --${MODE}）"
    exit "$EXIT_USAGE"
  fi
}

bwrap_binary() {
  command -v bwrap 2>/dev/null || true
}

check_version() {
  local binary="$1"
  "$binary" --version >/dev/null 2>&1
}

service_user_exists() {
  id -u "$SERVICE_USER" >/dev/null 2>&1
}

namespace_probe() {
  local binary="$1"
  if ! command -v runuser >/dev/null 2>&1; then
    log "缺少 runuser，无法以 $SERVICE_USER 身份探测命名空间"
    return 1
  fi
  runuser -u "$SERVICE_USER" -- env -i "PATH=$PROBE_PATH" "$binary" \
    --unshare-all --share-net --die-with-parent --ro-bind / / -- /bin/true
}

# Ubuntu 24.04+ 默认用 AppArmor 限制 unprivileged userns；bwrap 需要新建
# user namespace，因此要么关闭主机级限制（面太大），要么给 /usr/bin/bwrap
# 一个只放行 userns 的专用 profile。这里选择后者。
apparmor_userns_restricted() {
  local value
  [ -r /proc/sys/kernel/apparmor_restrict_unprivileged_userns ] || return 1
  value="$(cat /proc/sys/kernel/apparmor_restrict_unprivileged_userns 2>/dev/null || true)"
  [ "$value" = "1" ]
}

install_apparmor_profile() {
  local parser profile
  parser="$(command -v apparmor_parser 2>/dev/null || true)"
  if [ -z "$parser" ]; then
    log "主机启用了 AppArmor userns 限制，但缺少 apparmor_parser"
    return 1
  fi
  profile=/etc/apparmor.d/bwrap-userns-restrict
  log "安装 bwrap 专用 AppArmor profile: $profile"
  cat > "$profile" <<'PROFILE'
# 只放行 /usr/bin/bwrap 的 unprivileged user namespace 创建。
# Ubuntu 24.04+ 默认由 AppArmor 限制 userns；主机级 kernel.apparmor_restrict_unprivileged_userns
# 保持为 1，不扩大到其他程序。
abi <abi/4.0>,
include <tunables/global>

profile bwrap /usr/bin/bwrap flags=(unconfined) {
  userns,

  include if exists <local/bwrap>
}
PROFILE
  chmod 644 "$profile"
  "$parser" -r "$profile"
}

# 只读检查；成功时 emit ready 并返回 0，否则 emit 稳定错误码并返回对应退出码。
verify_bubblewrap() {
  local binary
  binary="$(bwrap_binary)"
  if [ -z "$binary" ]; then
    log "未找到 bwrap（bubblewrap 未安装或不在 PATH）"
    emit missing ATTRIBUTION_BWRAP_MISSING
    return "$EXIT_BWRAP_MISSING"
  fi
  log "bwrap 路径: $binary"
  if ! check_version "$binary"; then
    log "bwrap --version 失败：二进制不可执行或损坏"
    emit unusable ATTRIBUTION_BWRAP_UNUSABLE
    return "$EXIT_BWRAP_UNUSABLE"
  fi
  log "bwrap 版本: $("$binary" --version 2>/dev/null | head -n 1)"
  if ! service_user_exists; then
    log "服务账号 $SERVICE_USER 不存在；先完成 bootstrap"
    emit service-user-missing PROVISION_SERVICE_USER_MISSING
    return "$EXIT_SERVICE_USER_MISSING"
  fi
  if ! namespace_probe "$binary"; then
    log "以 $SERVICE_USER 运行命名空间探针失败"
    emit unusable ATTRIBUTION_BWRAP_UNUSABLE
    return "$EXIT_BWRAP_UNUSABLE"
  fi
  log "以 $SERVICE_USER 运行命名空间探针成功"
  emit ready NONE
  return 0
}

# install 模式专用：先验证；若只因 AppArmor userns 限制失败，安装专用 profile 后重试。
probe_or_fix() {
  local status
  if verify_bubblewrap; then
    return 0
  else
    status=$?
  fi
  if [ "$status" -ne "$EXIT_BWRAP_UNUSABLE" ]; then
    return "$status"
  fi
  if ! apparmor_userns_restricted; then
    return "$status"
  fi
  log "检测到 AppArmor unprivileged userns 限制；安装 bwrap 专用 profile 后重试"
  if ! install_apparmor_profile; then
    emit unusable ATTRIBUTION_BWRAP_UNUSABLE
    return "$EXIT_BWRAP_UNUSABLE"
  fi
  verify_bubblewrap
}

dry_run() {
  local binary
  binary="$(bwrap_binary)"
  if [ -n "$binary" ]; then
    log "bwrap 已安装（$binary）；--install 将只运行 --version 与命名空间探针，不执行 apt-get"
  else
    log "bwrap 缺失；--install 将运行 apt-get update 和 apt-get install -y --no-install-recommends bubblewrap"
  fi
  if apparmor_userns_restricted; then
    log "主机启用了 AppArmor userns 限制；若探针失败，--install 会安装 bwrap 专用 profile"
  fi
  log "服务账号: $SERVICE_USER"
  log "dry-run 未改动主机"
  emit dry-run NONE
  return 0
}

install_bubblewrap() {
  local binary
  require_root
  binary="$(bwrap_binary)"
  if [ -n "$binary" ]; then
    log "bwrap 已存在（${binary}），跳过 apt-get；继续验证"
  else
    log "bwrap 缺失，安装 bubblewrap"
    export DEBIAN_FRONTEND=noninteractive
    if ! apt-get update -y; then
      log "apt-get update 失败"
      emit install-failed PROVISION_APT_FAILED
      return "$EXIT_APT_FAILED"
    fi
    if ! apt-get install -y --no-install-recommends bubblewrap; then
      log "apt-get install bubblewrap 失败"
      emit install-failed PROVISION_APT_FAILED
      return "$EXIT_APT_FAILED"
    fi
  fi
  probe_or_fix
}

for arg in "$@"; do
  case "$arg" in
    --install) MODE="install" ;;
    --check) MODE="check" ;;
    --dry-run) MODE="dry-run" ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      log "未知参数: $arg"
      usage
      exit "$EXIT_USAGE"
      ;;
  esac
done

case "$MODE" in
  install) install_bubblewrap ;;
  check)
    require_root
    verify_bubblewrap
    ;;
  dry-run) dry_run ;;
  *)
    usage
    exit "$EXIT_USAGE"
    ;;
esac
