#!/usr/bin/env bash
# 部署 provisioning 契约（干净 Ubuntu 主机，root 运行）。
#
# 目的：把“部署运行时前置”变成 PR 必过检查，而不是等合并后的 Deploy 才发现主机缺包。
# 顺序：
#   1. 移除预装 bwrap，验证 Provision --check 的缺包错误码；
#   2. 以 harness 身份验证缺包时默认和显式开启均报错，显式关闭可就绪；
#   3. 用真实 Provision 安装并运行命名空间探针，再验证默认沙箱就绪。
#
# 用法: sudo bash apps/api/tests/deploy/verify_provisioning_contract.sh
# 前置: 已安装 apps/api/.venv（CI job 负责），主机为 Ubuntu 22.04/24.04。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
PROVISION="$ROOT/deploy/provision-bubblewrap.sh"
PREFLIGHT_DIR="$ROOT/apps/api"
PYTHON="$PREFLIGHT_DIR/.venv/bin/python"
SERVICE_USER="harness"
PROBE_PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

log() { printf '[deploy-contract] %s\n' "$*"; }
fail() {
  printf '[deploy-contract] FAIL: %s\n' "$*" >&2
  exit 1
}

assert_preflight() {
  local expected_status="$1" expected_line="$2" output status=0
  shift 2
  output="$(cd "$PREFLIGHT_DIR" && runuser -u "$SERVICE_USER" -- env -i \
    "PATH=$PREFLIGHT_DIR/.venv/bin:$PROBE_PATH" HOME=/tmp \
    HE_JWT_SECRET=deploy-contract-only AI_AGENT_PROVIDER=claude-code \
    "$@" "$PYTHON" -m app.third_party_api.ai_agent.preflight 2>&1)" || status=$?
  printf '%s\n' "$output"
  [ "$status" -eq "$expected_status" ] || fail "attribution.preflight 期望退出 $expected_status，实际 $status"
  grep -Fxq "$expected_line" <<<"$output" || fail "preflight 缺少预期结果 $expected_line"
}

[ "$(id -u)" -eq 0 ] || fail "必须以 root 运行"
[ -x "$PROVISION" ] || fail "缺少可执行脚本: $PROVISION"
[ -x "$PYTHON" ] || fail "缺少 API venv: $PYTHON（先安装 apps/api 依赖）"

log "1/5 确认主机没有 bwrap"
if command -v bwrap >/dev/null 2>&1; then
  log "镜像预装了 bwrap，先移除，确保负例验证的是真实缺包路径"
  DEBIAN_FRONTEND=noninteractive apt-get remove -y bubblewrap >/dev/null
  hash -r
fi
if command -v bwrap >/dev/null 2>&1; then
  fail "无法移除预装 bwrap，负例不可信"
fi

log "2/5 Provision --check 识别缺包"
set +e
negative_output="$("$PROVISION" --check 2>&1)"
negative_status=$?
set -e
printf '%s\n' "$negative_output"
[ "$negative_status" -eq 10 ] || fail "--check 期望退出 10，实际 $negative_status"
grep -q 'state=missing' <<<"$negative_output" || fail "--check 未输出 state=missing"
grep -q 'error_code=ATTRIBUTION_BWRAP_MISSING' <<<"$negative_output" ||
  fail "--check 未输出 ATTRIBUTION_BWRAP_MISSING"

log "3/5 验证缺包时两种归因模式的发布预检"
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi
missing='attribution.preflight provider=claude-code bwrap_enabled=True error_code=ATTRIBUTION_BWRAP_MISSING'
assert_preflight 1 "$missing"
assert_preflight 1 "$missing" HE_ATTRIBUTION_BWRAP_ENABLED=true
assert_preflight 0 'attribution.preflight provider=claude-code bwrap_enabled=False ready=True' \
  HE_ATTRIBUTION_BWRAP_ENABLED=false

log "4/5 真实 Provision 安装并验证命名空间"
set +e
provision_output="$("$PROVISION" --install 2>&1)"
provision_status=$?
set -e
printf '%s\n' "$provision_output"
[ "$provision_status" -eq 0 ] || fail "--install 期望退出 0，实际 $provision_status"
grep -q 'state=ready' <<<"$provision_output" || fail "--install 未到达 state=ready"
hash -r
command -v bwrap >/dev/null 2>&1 || fail "安装后 PATH 中没有 bwrap"
bwrap --version || fail "bwrap --version 失败"
runuser -u "$SERVICE_USER" -- env -i "PATH=$PROBE_PATH" \
  bwrap --unshare-all --share-net --die-with-parent --ro-bind / / -- /bin/true ||
  fail "服务账号 $SERVICE_USER 的命名空间探针失败"

log "5/5 验证服务账号 $SERVICE_USER 使用默认沙箱的发布预检"
assert_preflight 0 'attribution.preflight provider=claude-code bwrap_enabled=True ready=True'

log "PASS：默认沙箱与显式关闭时的部署契约均通过"
